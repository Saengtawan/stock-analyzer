#!/usr/bin/env python3
"""
Generate synthetic signal_outcomes by simulating the DIP screener on historical data.

For each trading day in the lookback period:
  1. Compute DIP-like features for all universe stocks
  2. Identify candidates (similar to how the live scanner would)
  3. Record features + actual 5-day forward return

This creates a much larger training dataset for Discovery v3.

Output: backfill_signal_outcomes table in trade_history.db
"""
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────
LOOKBACK_MONTHS = 6       # How far back to simulate
MIN_PRICE = 5.0           # Min stock price
MIN_DOLLAR_VOL = 5_000_000
BATCH_SIZE = 100          # Stocks per yfinance batch
MAX_CANDIDATES_PER_DAY = 50  # Cap to keep data manageable

# DIP candidate criteria (simplified from live screener)
DIP_CRITERIA = {
    'min_atr_pct': 1.5,
    'max_atr_pct': 8.0,
    'min_rsi': 20,
    'max_rsi': 75,
    'max_distance_from_20d_high': 0,    # Must be at or below 20d high
    'min_distance_from_20d_high': -25,  # Not too far below
}


def get_universe():
    """Get universe stocks with sectors."""
    conn = None  # via get_session())
    # From stock_fundamentals
    rows = conn.execute("""
        SELECT symbol, sector FROM stock_fundamentals
        WHERE sector IS NOT NULL AND sector != ''
    """).fetchall()
    conn.close()
    universe = {r[0]: r[1] for r in rows}
    print(f"Universe: {len(universe)} stocks with sectors")
    return universe


def get_vix_history(start_date, end_date):
    """Download VIX history."""
    print(f"Downloading VIX data {start_date} to {end_date}...")
    vix = yf.download('^VIX', start=start_date, end=end_date, progress=False, auto_adjust=True)
    if vix.empty:
        print("WARNING: No VIX data")
        return {}
    vix_dict = {}
    for dt, row in vix.iterrows():
        date_str = dt.strftime('%Y-%m-%d')
        close_val = row['Close']
        if isinstance(close_val, pd.Series):
            close_val = close_val.iloc[0]
        vix_dict[date_str] = float(close_val)
    print(f"VIX data: {len(vix_dict)} days")
    return vix_dict


def compute_features(df_close, df_high, df_low, df_volume, symbol, date_idx):
    """Compute DIP features for a stock at a specific date index."""
    if date_idx < 25:  # Need at least 25 bars for indicators
        return None

    close = df_close[symbol].iloc[:date_idx + 1].dropna()
    high = df_high[symbol].iloc[:date_idx + 1].dropna() if symbol in df_high.columns else None
    low = df_low[symbol].iloc[:date_idx + 1].dropna() if symbol in df_low.columns else None
    volume = df_volume[symbol].iloc[:date_idx + 1].dropna() if symbol in df_volume.columns else None

    if len(close) < 25:
        return None

    price = float(close.iloc[-1])
    if price < MIN_PRICE:
        return None

    # ATR (14-day)
    if high is not None and low is not None and len(high) >= 15 and len(low) >= 15:
        tr_values = []
        for i in range(-14, 0):
            h = float(high.iloc[i])
            l = float(low.iloc[i])
            c_prev = float(close.iloc[i - 1]) if (i - 1) >= -len(close) else float(close.iloc[i])
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_values.append(tr)
        atr = np.mean(tr_values)
        atr_pct = (atr / price) * 100
    else:
        return None

    # RSI (14-day)
    if len(close) >= 16:
        deltas = close.diff().iloc[-15:]
        gains = deltas.where(deltas > 0, 0.0)
        losses = (-deltas).where(deltas < 0, 0.0)
        avg_gain = float(gains.mean())
        avg_loss = float(losses.mean())
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
    else:
        return None

    # Distance from 20-day high (negative convention: 0 = at high) — use High prices
    if high is not None and len(high) >= 20:
        high_20d = float(high.iloc[-20:].max())
    else:
        high_20d = float(close.iloc[-20:].max())
    distance_from_20d_high = ((price - high_20d) / high_20d) * 100

    # Momentum 5d
    if len(close) >= 6:
        price_5d_ago = float(close.iloc[-6])
        momentum_5d = ((price - price_5d_ago) / price_5d_ago) * 100
    else:
        return None

    # Momentum 20d
    if len(close) >= 21:
        price_20d_ago = float(close.iloc[-21])
        momentum_20d = ((price - price_20d_ago) / price_20d_ago) * 100
    else:
        momentum_20d = None

    # Volume ratio (today vs 20d avg)
    if volume is not None and len(volume) >= 21:
        vol_today = float(volume.iloc[-1])
        vol_20d_avg = float(volume.iloc[-21:-1].mean())
        volume_ratio = vol_today / vol_20d_avg if vol_20d_avg > 0 else 0
        avg_dollar_vol = float(volume.iloc[-20:].mean()) * price
        if avg_dollar_vol < MIN_DOLLAR_VOL:
            return None
    else:
        volume_ratio = None

    # Apply DIP criteria
    c = DIP_CRITERIA
    if atr_pct < c['min_atr_pct'] or atr_pct > c['max_atr_pct']:
        return None
    if rsi < c['min_rsi'] or rsi > c['max_rsi']:
        return None
    if distance_from_20d_high > c['max_distance_from_20d_high']:
        return None
    if distance_from_20d_high < c['min_distance_from_20d_high']:
        return None

    return {
        'scan_price': price,
        'atr_pct': round(atr_pct, 3),
        'entry_rsi': round(rsi, 1),
        'distance_from_20d_high': round(distance_from_20d_high, 2),
        'momentum_5d': round(momentum_5d, 2),
        'momentum_20d': round(momentum_20d, 2) if momentum_20d else None,
        'volume_ratio': round(volume_ratio, 3) if volume_ratio else None,
    }


def compute_outcome(df_close, symbol, date_idx, horizon=5):
    """Compute forward return and max gain/dd over horizon days."""
    close = df_close[symbol].iloc[date_idx + 1:date_idx + 1 + horizon].dropna()
    if len(close) == 0:
        return None, None, None

    scan_price = float(df_close[symbol].iloc[date_idx])
    if scan_price <= 0:
        return None, None, None

    returns = ((close - scan_price) / scan_price * 100).values
    outcome_5d = float(returns[-1]) if len(returns) >= horizon else float(returns[-1])
    max_gain = float(np.max(returns))
    max_dd = float(np.min(returns))

    return round(outcome_5d, 2), round(max_gain, 2), round(max_dd, 2)


def ensure_table():
    """Create backfill_signal_outcomes table."""
    conn = None  # via get_session())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backfill_signal_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            sector TEXT,
            scan_price REAL,
            atr_pct REAL,
            entry_rsi REAL,
            distance_from_20d_high REAL,
            momentum_5d REAL,
            momentum_20d REAL,
            volume_ratio REAL,
            vix_at_signal REAL,
            outcome_5d REAL,
            outcome_max_gain_5d REAL,
            outcome_max_dd_5d REAL,
            UNIQUE(scan_date, symbol)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bso_date ON backfill_signal_outcomes(scan_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bso_symbol ON backfill_signal_outcomes(scan_date, symbol)")
    conn.commit()
    conn.close()


def main():
    print("=" * 60)
    print("  SYNTHETIC SIGNAL_OUTCOMES BACKFILL")
    print(f"  Lookback: {LOOKBACK_MONTHS} months")
    print("=" * 60)

    universe = get_universe()
    symbols = list(universe.keys())

    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=LOOKBACK_MONTHS * 30 + 60)  # Extra for warmup
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    # Get VIX
    vix_history = get_vix_history(start_str, end_str)

    # Download price data in batches
    print(f"\nDownloading price data for {len(symbols)} stocks...")
    all_close = []
    all_high = []
    all_low = []
    all_volume = []

    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i + BATCH_SIZE]
        print(f"  Batch {i // BATCH_SIZE + 1}/{(len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE}: {len(batch)} stocks...")
        try:
            df = yf.download(batch, start=start_str, end=end_str,
                             progress=False, auto_adjust=True, threads=True)
            if df.empty:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                all_close.append(df['Close'])
                all_high.append(df['High'])
                all_low.append(df['Low'])
                all_volume.append(df['Volume'])
            else:
                # Single stock
                all_close.append(df[['Close']].rename(columns={'Close': batch[0]}))
                all_high.append(df[['High']].rename(columns={'High': batch[0]}))
                all_low.append(df[['Low']].rename(columns={'Low': batch[0]}))
                all_volume.append(df[['Volume']].rename(columns={'Volume': batch[0]}))
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(0.5)

    if not all_close:
        print("ERROR: No price data downloaded")
        sys.exit(1)

    df_close = pd.concat(all_close, axis=1)
    df_high = pd.concat(all_high, axis=1)
    df_low = pd.concat(all_low, axis=1)
    df_volume = pd.concat(all_volume, axis=1)

    print(f"\nPrice data: {len(df_close)} days × {len(df_close.columns)} stocks")
    print(f"Date range: {df_close.index[0].strftime('%Y-%m-%d')} to {df_close.index[-1].strftime('%Y-%m-%d')}")

    # Determine scan dates (skip first 30 bars for warmup, last 5 for outcomes)
    trading_dates = df_close.index[30:-5]

    # Only use dates within lookback period
    cutoff = end_date - timedelta(days=LOOKBACK_MONTHS * 30)
    trading_dates = [d for d in trading_dates if d >= pd.Timestamp(cutoff)]
    print(f"Scan dates to process: {len(trading_dates)}")

    ensure_table()
    conn = None  # via get_session())

    # Check existing data
    existing = set()
    for row in conn.execute("SELECT scan_date, symbol FROM backfill_signal_outcomes"):
        existing.add((row[0], row[1]))
    print(f"Existing rows: {len(existing)}")

    total_inserted = 0
    total_dates_processed = 0

    for dt in trading_dates:
        date_str = dt.strftime('%Y-%m-%d')
        date_idx = df_close.index.get_loc(dt)

        # Get VIX for this date
        vix = vix_history.get(date_str)
        if vix is None:
            # Try nearby dates
            for offset in range(-2, 3):
                alt_date = (dt + timedelta(days=offset)).strftime('%Y-%m-%d')
                vix = vix_history.get(alt_date)
                if vix:
                    break
        if vix is None:
            continue

        candidates = []
        stock_list = [s for s in df_close.columns if s in universe]

        for symbol in stock_list:
            if (date_str, symbol) in existing:
                continue

            if symbol not in df_close.columns:
                continue

            # Check if stock has data at this date
            if pd.isna(df_close[symbol].iloc[date_idx]):
                continue

            features = compute_features(df_close, df_high, df_low, df_volume,
                                        symbol, date_idx)
            if features is None:
                continue

            # Compute 5-day forward outcome
            outcome_5d, max_gain, max_dd = compute_outcome(df_close, symbol, date_idx)
            if outcome_5d is None:
                continue

            candidates.append({
                'scan_date': date_str,
                'symbol': symbol,
                'sector': universe.get(symbol, 'Unknown'),
                'vix_at_signal': round(vix, 2),
                'outcome_5d': outcome_5d,
                'outcome_max_gain_5d': max_gain,
                'outcome_max_dd_5d': max_dd,
                **features,
            })

        # Random sample to avoid selection bias (old: sorted by dist → 93% zeros)
        import random
        random.shuffle(candidates)
        candidates = candidates[:MAX_CANDIDATES_PER_DAY]

        # Insert
        for c in candidates:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO backfill_signal_outcomes
                    (scan_date, symbol, sector, scan_price, atr_pct, entry_rsi,
                     distance_from_20d_high, momentum_5d, momentum_20d,
                     volume_ratio, vix_at_signal, outcome_5d,
                     outcome_max_gain_5d, outcome_max_dd_5d)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (c['scan_date'], c['symbol'], c['sector'], c['scan_price'],
                      c['atr_pct'], c['entry_rsi'], c['distance_from_20d_high'],
                      c['momentum_5d'], c['momentum_20d'], c['volume_ratio'],
                      c['vix_at_signal'], c['outcome_5d'],
                      c['outcome_max_gain_5d'], c['outcome_max_dd_5d']))
                total_inserted += 1
            except Exception as e:
                pass

        total_dates_processed += 1

        if total_dates_processed % 10 == 0:
            conn.commit()
            print(f"  Processed {total_dates_processed}/{len(trading_dates)} dates, "
                  f"inserted {total_inserted} rows, "
                  f"candidates today: {len(candidates)}")

    conn.commit()

    # Final summary
    total = conn.execute("SELECT COUNT(*) FROM backfill_signal_outcomes").fetchone()[0]
    dates_count = conn.execute("SELECT COUNT(DISTINCT scan_date) FROM backfill_signal_outcomes").fetchone()[0]
    symbols_count = conn.execute("SELECT COUNT(DISTINCT symbol) FROM backfill_signal_outcomes").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"  BACKFILL COMPLETE")
    print(f"{'='*60}")
    print(f"  New rows inserted: {total_inserted}")
    print(f"  Total rows:        {total}")
    print(f"  Unique dates:      {dates_count}")
    print(f"  Unique symbols:    {symbols_count}")

    # Quick stats
    stats = conn.execute("""
        SELECT COUNT(*), ROUND(AVG(outcome_5d),2),
               ROUND(AVG(CASE WHEN outcome_5d > 0 THEN 1.0 ELSE 0.0 END)*100,1),
               MIN(scan_date), MAX(scan_date)
        FROM backfill_signal_outcomes WHERE outcome_5d IS NOT NULL
    """).fetchone()
    print(f"  WR (overall):      {stats[2]}%")
    print(f"  Avg Return 5d:     {stats[1]}%")
    print(f"  Date range:        {stats[3]} to {stats[4]}")

    # Per-month breakdown
    print(f"\n  Per-Month Breakdown:")
    monthly = conn.execute("""
        SELECT strftime('%Y-%m', scan_date) as month,
               COUNT(*) as n,
               ROUND(AVG(CASE WHEN outcome_5d > 0 THEN 1.0 ELSE 0.0 END)*100,1) as wr,
               ROUND(AVG(outcome_5d),2) as avg_ret,
               ROUND(AVG(vix_at_signal),1) as avg_vix
        FROM backfill_signal_outcomes
        GROUP BY month ORDER BY month
    """).fetchall()
    print(f"    {'Month':<10} {'n':>6} {'WR%':>6} {'AvgRet':>8} {'AvgVIX':>7}")
    for row in monthly:
        print(f"    {row[0]:<10} {row[1]:>6} {row[2]:>5.1f}% {row[3]:>+7.2f}% {row[4]:>6.1f}")

    conn.close()
    print(f"\n  Data saved to: backfill_signal_outcomes table")


if __name__ == '__main__':
    main()
