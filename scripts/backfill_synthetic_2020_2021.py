#!/usr/bin/env python3
"""
Generate backfill_signal_outcomes for 2020-2021 from DB OHLC data.
No yfinance downloads — reads directly from stock_daily_ohlc.
Matches the format of backfill_synthetic_outcomes.py.
"""
import sqlite3
import sys
import random
import logging
from pathlib import Path
from collections import defaultdict

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 5_000_000
MAX_CANDIDATES_PER_DAY = 50
START_DATE = '2020-01-02'
END_DATE = '2021-12-31'


def load_data(conn):
    """Load all OHLC + VIX + sectors from DB."""
    # Load OHLC (need warmup from 2019-06-01 for 252-day calcs)
    logger.info("Loading OHLC data from DB...")
    rows = conn.execute("""
        SELECT symbol, date, open, high, low, close, volume
        FROM stock_daily_ohlc
        WHERE date >= '2019-06-01' AND date <= '2022-01-10'
        ORDER BY symbol, date
    """).fetchall()

    # Organize by symbol → list of dicts sorted by date
    ohlc = defaultdict(list)
    for sym, dt, o, h, l, c, v in rows:
        ohlc[sym].append({'date': dt, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v or 0})
    logger.info(f"Loaded {len(rows):,} rows for {len(ohlc)} symbols")

    # Load VIX from macro_snapshots
    vix_rows = conn.execute("""
        SELECT date, vix_close FROM macro_snapshots
        WHERE date >= '2020-01-01' AND date <= '2022-01-10' AND vix_close IS NOT NULL
    """).fetchall()
    vix = {r[0]: r[1] for r in vix_rows}
    logger.info(f"VIX data: {len(vix)} days")

    # Load sectors
    sector_rows = conn.execute("""
        SELECT symbol, sector FROM stock_fundamentals
        WHERE sector IS NOT NULL AND sector != ''
    """).fetchall()
    sectors = {r[0]: r[1] for r in sector_rows}
    logger.info(f"Sectors: {len(sectors)} symbols")

    # Get trading days in range
    trading_days = sorted(set(
        r[0] for r in conn.execute("""
            SELECT DISTINCT date FROM stock_daily_ohlc
            WHERE date >= ? AND date <= ?
            ORDER BY date
        """, (START_DATE, END_DATE)).fetchall()
    ))
    logger.info(f"Trading days in range: {len(trading_days)}")

    return ohlc, vix, sectors, trading_days


def compute_features(bars, day_idx):
    """Compute DIP features from a list of bar dicts at day_idx."""
    if day_idx < 30:
        return None

    # Slice up to day_idx inclusive
    hist = bars[:day_idx + 1]
    close_arr = [b['close'] for b in hist if b['close'] and b['close'] > 0]
    if len(close_arr) < 25:
        return None

    price = close_arr[-1]
    if price < MIN_PRICE:
        return None

    # ATR 14-day
    if day_idx < 15:
        return None
    tr_values = []
    for i in range(-14, 0):
        bar = hist[i]
        prev_c = hist[i-1]['close'] if hist[i-1]['close'] else bar['close']
        h, l = bar['high'] or bar['close'], bar['low'] or bar['close']
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_values.append(tr)
    atr = np.mean(tr_values)
    atr_pct = (atr / price) * 100

    if atr_pct < 1.5 or atr_pct > 8.0:
        return None

    # RSI 14-day
    if len(close_arr) < 16:
        return None
    deltas = np.diff(close_arr[-15:])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    if rsi < 20 or rsi > 75:
        return None

    # Distance from 20d high (use high prices)
    highs_20d = [b['high'] or b['close'] for b in hist[-20:] if (b['high'] or b['close'])]
    if len(highs_20d) < 20:
        highs_20d = close_arr[-20:]
    high_20d = max(highs_20d)
    distance_from_20d_high = ((price - high_20d) / high_20d) * 100

    if distance_from_20d_high > 0 or distance_from_20d_high < -25:
        return None

    # Momentum 5d
    if len(close_arr) < 6:
        return None
    momentum_5d = ((price - close_arr[-6]) / close_arr[-6]) * 100

    # Momentum 20d
    momentum_20d = None
    if len(close_arr) >= 21:
        momentum_20d = ((price - close_arr[-21]) / close_arr[-21]) * 100

    # Volume ratio
    vols = [b['volume'] for b in hist[-21:] if b['volume'] and b['volume'] > 0]
    volume_ratio = None
    if len(vols) >= 21:
        vol_today = vols[-1]
        vol_avg = np.mean(vols[-21:-1])
        volume_ratio = vol_today / vol_avg if vol_avg > 0 else 0
        avg_dollar_vol = np.mean(vols[-20:]) * price
        if avg_dollar_vol < MIN_DOLLAR_VOL:
            return None

    return {
        'scan_price': round(price, 2),
        'atr_pct': round(atr_pct, 3),
        'entry_rsi': round(rsi, 1),
        'distance_from_20d_high': round(distance_from_20d_high, 2),
        'momentum_5d': round(momentum_5d, 2),
        'momentum_20d': round(momentum_20d, 2) if momentum_20d else None,
        'volume_ratio': round(volume_ratio, 3) if volume_ratio else None,
    }


def compute_outcomes(bars, day_idx):
    """Compute 1d-5d forward returns and max gain/dd."""
    close_at_signal = bars[day_idx]['close']
    if not close_at_signal or close_at_signal <= 0:
        return None

    outcomes = {}
    max_forward = min(5, len(bars) - day_idx - 1)
    if max_forward < 1:
        return None

    returns = []
    for d in range(1, max_forward + 1):
        future_close = bars[day_idx + d]['close']
        if future_close and future_close > 0:
            ret = ((future_close - close_at_signal) / close_at_signal) * 100
            returns.append(round(ret, 2))
            outcomes[f'outcome_{d}d'] = round(ret, 2)
        else:
            returns.append(None)

    valid_returns = [r for r in returns if r is not None]
    if not valid_returns:
        return None

    outcomes['outcome_5d'] = outcomes.get('outcome_5d', valid_returns[-1])
    outcomes['outcome_max_gain_5d'] = round(max(valid_returns), 2)
    outcomes['outcome_max_dd_5d'] = round(min(valid_returns), 2)

    return outcomes


def main():
    conn = None  # via get_session(), timeout=60)
    ohlc, vix, sectors, trading_days = load_data(conn)

    # Ensure outcome columns exist
    for col in ['outcome_1d', 'outcome_2d', 'outcome_3d', 'outcome_4d']:
        try:
            conn.execute(f"ALTER TABLE backfill_signal_outcomes ADD COLUMN {col} REAL")
        except Exception:
            pass
    conn.commit()

    # Get existing entries
    existing = set()
    for r in conn.execute("SELECT scan_date, symbol FROM backfill_signal_outcomes"):
        existing.add((r[0], r[1]))
    logger.info(f"Existing rows: {len(existing):,}")

    # Build date index per symbol for fast lookup
    symbol_date_idx = {}
    for sym, bars in ohlc.items():
        date_to_idx = {b['date']: i for i, b in enumerate(bars)}
        symbol_date_idx[sym] = date_to_idx

    before = conn.execute("SELECT COUNT(*) FROM backfill_signal_outcomes").fetchone()[0]
    total_inserted = 0

    for di, day in enumerate(trading_days):
        # Get VIX
        vix_val = vix.get(day)
        if vix_val is None:
            # Try nearby
            from datetime import datetime, timedelta
            dt = datetime.strptime(day, '%Y-%m-%d')
            for off in [-1, 1, -2, 2]:
                alt = (dt + timedelta(days=off)).strftime('%Y-%m-%d')
                vix_val = vix.get(alt)
                if vix_val:
                    break
        if vix_val is None:
            continue

        candidates = []
        for sym, bars in ohlc.items():
            if (day, sym) in existing:
                continue
            if sym not in symbol_date_idx:
                continue

            idx = symbol_date_idx[sym].get(day)
            if idx is None:
                continue

            features = compute_features(bars, idx)
            if features is None:
                continue

            outcomes = compute_outcomes(bars, idx)
            if outcomes is None:
                continue

            candidates.append({
                'scan_date': day,
                'symbol': sym,
                'sector': sectors.get(sym, 'Unknown'),
                'vix_at_signal': round(vix_val, 2),
                **features,
                **outcomes,
            })

        # Random sample to avoid selection bias
        random.shuffle(candidates)
        candidates = candidates[:MAX_CANDIDATES_PER_DAY]

        for c in candidates:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO backfill_signal_outcomes
                    (scan_date, symbol, sector, scan_price, atr_pct, entry_rsi,
                     distance_from_20d_high, momentum_5d, momentum_20d,
                     volume_ratio, vix_at_signal, outcome_1d, outcome_2d,
                     outcome_3d, outcome_4d, outcome_5d,
                     outcome_max_gain_5d, outcome_max_dd_5d)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (c['scan_date'], c['symbol'], c['sector'], c['scan_price'],
                      c['atr_pct'], c['entry_rsi'], c['distance_from_20d_high'],
                      c['momentum_5d'], c['momentum_20d'], c['volume_ratio'],
                      c['vix_at_signal'],
                      c.get('outcome_1d'), c.get('outcome_2d'),
                      c.get('outcome_3d'), c.get('outcome_4d'),
                      c['outcome_5d'], c['outcome_max_gain_5d'], c['outcome_max_dd_5d']))
                total_inserted += 1
            except Exception:
                pass

        if (di + 1) % 50 == 0:
            conn.commit()
            logger.info(
                f"  [{di+1}/{len(trading_days)}] {day}: "
                f"+{len(candidates)} candidates, total_inserted={total_inserted}"
            )

    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM backfill_signal_outcomes").fetchone()[0]

    # Stats
    stats = conn.execute("""
        SELECT substr(scan_date,1,4) as yr, COUNT(*),
               ROUND(AVG(CASE WHEN outcome_5d > 0 THEN 1.0 ELSE 0.0 END)*100,1),
               ROUND(AVG(outcome_5d),2)
        FROM backfill_signal_outcomes
        GROUP BY yr ORDER BY yr
    """).fetchall()

    logger.info("=" * 60)
    logger.info(f"BACKFILL COMPLETE: {START_DATE} to {END_DATE}")
    logger.info(f"  Rows before: {before:,}")
    logger.info(f"  Rows after:  {after:,}")
    logger.info(f"  Rows added:  {total_inserted:,}")
    logger.info(f"  By year:")
    for yr, n, wr, avg in stats:
        logger.info(f"    {yr}: {n:,} signals, WR={wr}%, avg_ret={avg:+.2f}%")
    logger.info("=" * 60)

    conn.close()


if __name__ == '__main__':
    main()
