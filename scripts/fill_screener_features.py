#!/usr/bin/env python3
"""
fill_screener_features.py — v7.7
===================================
Nightly enrichment: fill ALL missing features for OVN/PEM/GAP/PED screener_rejections rows.

Why needed:
  - OVN/PEM/GAP screeners reject stocks early (before RSI/ATR/volume computed)
    so these fields are NULL in screener_rejections
  - DIP screener already fills all features — this script skips DIP rows
  - Without these fields, backtesting simulation can't replay filter decisions

Fills from yfinance daily bars (280-day history per symbol):
  - RSI(14), ATR%, momentum_5d, momentum_20d, distance_from_high
  - volume_ratio = scan_date_volume / avg_20d_volume
  - sector (from sector_cache table — no API call needed)

Also fills signal_outcomes and trades gaps (if run with --full):
  - signal_outcomes.vix_at_signal  ← JOIN macro_snapshots
  - signal_outcomes.spy_pct_above_sma ← yfinance SPY historical
  - trades.mfe_pct, mae_pct  ← yfinance 1m bars over hold period

Cron (TZ=America/New_York):
  45 21 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_screener_features.py >> logs/fill_screener_features.log 2>&1
"""
import os
import sqlite3
import time
from datetime import datetime, date, timedelta
import argparse

import numpy as np
import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
ET = ZoneInfo('America/New_York')

SCREENERS_TO_FILL = ('ovn', 'pem', 'gap', 'ped')  # DIP already has full features


# ── Feature computation helpers ───────────────────────────────────────────────

def _rsi(close: np.ndarray, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.mean(gain[:period])
    avg_loss = np.mean(loss[:period])
    for i in range(period, len(delta)):
        avg_gain = (avg_gain * (period - 1) + gain[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def _atr_pct(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    tr_list = []
    for i in range(1, len(close)):
        h, l, pc = high[i], low[i], close[i-1]
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = np.mean(tr_list[-period:])
    return round(atr / close[-1] * 100, 3) if close[-1] > 0 else None


def compute_features(df: pd.DataFrame, scan_date: str) -> dict:
    """Compute all needed features from daily OHLCV DataFrame."""
    result = {'rsi': None, 'atr_pct': None, 'momentum_5d': None,
              'momentum_20d': None, 'distance_from_high': None, 'volume_ratio': None,
              'distance_from_20d_ma': None}
    if df is None or df.empty or len(df) < 5:
        return result

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Filter to rows up to and including scan_date (prevent lookahead bias)
    df.index = pd.to_datetime(df.index)
    df_hist = df[df.index.date <= datetime.strptime(scan_date, '%Y-%m-%d').date()]
    if df_hist.empty or len(df_hist) < 5:
        return result

    close = df_hist['Close'].values.astype(float)
    high  = df_hist['High'].values.astype(float)
    low   = df_hist['Low'].values.astype(float)
    volume = df_hist['Volume'].values.astype(float)

    if len(close) >= 15:
        result['rsi'] = _rsi(close)
        result['atr_pct'] = _atr_pct(high, low, close)

    if len(close) >= 6:
        result['momentum_5d'] = round((close[-1] / close[-6] - 1) * 100, 3) if close[-6] > 0 else None

    if len(close) >= 21:
        result['momentum_20d'] = round((close[-1] / close[-21] - 1) * 100, 3) if close[-21] > 0 else None

    # 52-week high distance (negative convention: 0=at high, -10=10% below)
    if len(df_hist) >= 2:
        high_52w = float(df_hist['High'].tail(252).max())
        if high_52w > 0:
            result['distance_from_high'] = round((close[-1] / high_52w - 1) * 100, 3)

    # volume_ratio = scan_date volume / avg 20-day volume
    if len(volume) >= 2:
        avg_20d_vol = float(np.mean(volume[-21:-1]))  # prior 20 days (exclude scan day)
        scan_day_vol = float(volume[-1])
        if avg_20d_vol > 0 and scan_day_vol > 0:
            result['volume_ratio'] = round(scan_day_vol / avg_20d_vol, 3)

    # distance_from_20d_ma: (close - 20d MA) / 20d MA × 100
    # positive = above MA, negative = below MA
    if len(close) >= 20:
        ma20 = float(np.mean(close[-20:]))
        if ma20 > 0:
            result['distance_from_20d_ma'] = round((close[-1] / ma20 - 1) * 100, 3)

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Fill screener features for OVN/PEM/GAP/PED')
    parser.add_argument('--date', default=None, help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--days', type=int, default=3, help='Days to look back (default: 3)')
    parser.add_argument('--all-screeners', action='store_true',
                        help='Also re-fill DIP rows missing volume_ratio/sector')
    args = parser.parse_args()

    today = args.date or datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] fill_screener_features "
          f"date={today} days={args.days}")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    screener_list = ','.join(f"'{s}'" for s in SCREENERS_TO_FILL)
    if args.all_screeners:
        screener_list = "'dip_bounce'," + screener_list

    base_dt = datetime.strptime(today, '%Y-%m-%d')
    cutoff = (base_dt - timedelta(days=args.days)).strftime('%Y-%m-%d')

    # ── Step 1: Fill sector from sector_cache (no API call needed) ────────────
    print("  Step 1: Fill missing sector from sector_cache...")
    sector_updated = conn.execute(f"""
        UPDATE screener_rejections
        SET sector = (
            SELECT sc.sector FROM sector_cache sc WHERE sc.symbol = screener_rejections.symbol LIMIT 1
        )
        WHERE sector IS NULL
          AND screener IN ({screener_list})
          AND scan_date >= ?
    """, (cutoff,)).rowcount
    conn.commit()
    print(f"    sector filled: {sector_updated} rows")

    # ── Step 2: Fill vix_at_signal in signal_outcomes from macro_snapshots ────
    print("  Step 2: Fill vix_at_signal in signal_outcomes from macro_snapshots...")
    vix_updated = conn.execute("""
        UPDATE signal_outcomes
        SET vix_at_signal = (
            SELECT m.vix_close FROM macro_snapshots m WHERE m.date = signal_outcomes.scan_date LIMIT 1
        )
        WHERE vix_at_signal IS NULL
    """).rowcount
    conn.commit()
    print(f"    vix_at_signal filled: {vix_updated} rows")

    # ── Step 3: Fill RSI/ATR/momentum/volume_ratio via yfinance daily bars ────
    print(f"  Step 3: Fill RSI/ATR/momentum/volume_ratio from yfinance (cutoff={cutoff})...")

    rows = conn.execute(f"""
        SELECT id, symbol, scan_date, screener
        FROM screener_rejections
        WHERE screener IN ({screener_list})
          AND scan_date >= ?
          AND (rsi IS NULL OR volume_ratio IS NULL)
          AND scan_price IS NOT NULL AND scan_price > 0
        ORDER BY scan_date DESC, symbol
    """, (cutoff,)).fetchall()

    if not rows:
        print("    Nothing to fill.")
        conn.close()
        return

    sym_date_pairs = list(set((r['symbol'], r['scan_date']) for r in rows))
    print(f"    {len(rows)} rows → {len(sym_date_pairs)} unique symbol-date pairs")

    id_map: dict[tuple, list[int]] = {}
    for r in rows:
        key = (r['symbol'], r['scan_date'])
        id_map.setdefault(key, []).append(r['id'])

    # ── Step 4: Compute first_15min_volume_ratio from signal_candidate_bars ─────
    # first_15min_volume_ratio = sum(volume 09:30-09:44) / (avg_daily_vol × 15/390)
    # Only available for stocks that have signal_candidate_bars data
    print("  Step 4: Compute first_15min_volume_ratio from signal_candidate_bars...")
    first15_map: dict[tuple, float | None] = {}
    pairs_needing_15min = [
        (sym, sd) for sym, sd in sym_date_pairs
        # Only fetch if at least one row is missing first_15min_volume_ratio
        if any(
            conn.execute(
                "SELECT 1 FROM screener_rejections WHERE id=? AND first_15min_volume_ratio IS NULL",
                (rid,)
            ).fetchone()
            for rid in id_map.get((sym, sd), [])
        )
    ]
    # Batch-query signal_candidate_bars for 09:30-09:44
    for sym, sd in pairs_needing_15min:
        try:
            bar_rows = conn.execute("""
                SELECT time_et, volume FROM signal_candidate_bars
                WHERE symbol = ? AND date = ? AND time_et >= '09:30' AND time_et <= '09:44'
            """, (sym, sd)).fetchall()
            if bar_rows:
                vol_15min = sum(r[1] for r in bar_rows if r[1])
                # Avg daily volume from screener_rejections (use volume_ratio × avg if available,
                # else look up from daily download cache — skip for now, use None)
                # We compute avg from daily bars in the same sym_date_pairs loop below
                first15_map[(sym, sd)] = vol_15min  # raw; divide by avg later
        except Exception:
            pass

    updated = 0
    failed = 0
    for i, (sym, scan_date) in enumerate(sym_date_pairs):
        try:
            end_dt = (datetime.strptime(scan_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
            start_dt = (datetime.strptime(scan_date, '%Y-%m-%d') - timedelta(days=280)).strftime('%Y-%m-%d')

            df = yf.download(sym, start=start_dt, end=end_dt,
                             interval='1d', auto_adjust=True, progress=False)
            if df is None or df.empty:
                failed += 1
                continue

            feat = compute_features(df, scan_date)

            # Compute first_15min_volume_ratio if we have the raw 15min volume
            first15_ratio = None
            raw_15min_vol = first15_map.get((sym, scan_date))
            if raw_15min_vol is not None and raw_15min_vol > 0:
                try:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    df.index = pd.to_datetime(df.index)
                    df_hist = df[df.index.date < datetime.strptime(scan_date, '%Y-%m-%d').date()]
                    if len(df_hist) >= 20:
                        avg_daily_vol = float(df_hist['Volume'].tail(20).mean())
                        expected_15min_vol = avg_daily_vol * (15 / 390)
                        if expected_15min_vol > 0:
                            first15_ratio = round(raw_15min_vol / expected_15min_vol, 3)
                except Exception:
                    pass

            for row_id in id_map[(sym, scan_date)]:
                conn.execute("""
                    UPDATE screener_rejections SET
                        rsi                     = COALESCE(rsi, ?),
                        atr_pct                 = COALESCE(atr_pct, ?),
                        momentum_5d             = COALESCE(momentum_5d, ?),
                        momentum_20d            = COALESCE(momentum_20d, ?),
                        distance_from_high      = COALESCE(distance_from_high, ?),
                        volume_ratio            = COALESCE(volume_ratio, ?),
                        distance_from_20d_ma    = COALESCE(distance_from_20d_ma, ?),
                        first_15min_volume_ratio = COALESCE(first_15min_volume_ratio, ?)
                    WHERE id = ?
                """, (feat['rsi'], feat['atr_pct'], feat['momentum_5d'],
                      feat['momentum_20d'], feat['distance_from_high'],
                      feat['volume_ratio'], feat['distance_from_20d_ma'],
                      first15_ratio, row_id))
            updated += len(id_map[(sym, scan_date)])

        except Exception:
            failed += 1

        if (i + 1) % 50 == 0:
            conn.commit()
            print(f"    [{i+1}/{len(sym_date_pairs)}] updated={updated} failed={failed}")
        if (i + 1) % 20 == 0:
            time.sleep(0.2)

    conn.commit()
    conn.close()
    print(f"  Final: sector={sector_updated} vix_signal={vix_updated} "
          f"features={updated} failed={failed}")
    print(f"  Done.")


if __name__ == '__main__':
    main()
