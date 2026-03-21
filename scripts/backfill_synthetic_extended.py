#!/usr/bin/env python3
"""
backfill_synthetic_extended.py — Extended backfill for backfill_signal_outcomes.

Generates synthetic DIP candidates + 5-day outcomes for historical dates.
Runs in 6-month chunks to manage memory and yfinance rate limits.

Usage:
  python3 scripts/backfill_synthetic_extended.py --start 2022-01-01 --end 2025-08-31
  python3 scripts/backfill_synthetic_extended.py --start 2023-01-01 --end 2023-12-31 --chunk-months 4

Based on backfill_synthetic_outcomes.py but with:
- Configurable date range (--start / --end)
- Automatic chunking (--chunk-months, default 4)
- Additional outcome horizons (outcome_1d, 2d, 3d)
- Sector preservation for kernel training
"""
import argparse
import sqlite3
import sys
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# Config
MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 5_000_000
BATCH_SIZE = 100
MAX_CANDIDATES_PER_DAY = 50
WARMUP_DAYS = 60  # extra days before start for technical indicators

DIP_CRITERIA = {
    'min_atr_pct': 1.5,
    'max_atr_pct': 8.0,
    'min_rsi': 20,
    'max_rsi': 75,
    'max_distance_from_20d_high': 0,
    'min_distance_from_20d_high': -25,
}


def get_universe():
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("""
        SELECT symbol, sector FROM stock_fundamentals
        WHERE sector IS NOT NULL AND sector != ''
    """).fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def get_existing_pairs():
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT scan_date, symbol FROM backfill_signal_outcomes").fetchall()
    conn.close()
    return set((r[0], r[1]) for r in rows)


def compute_features(df_close, df_high, df_low, df_volume, symbol, date_idx):
    if date_idx < 25:
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

    # ATR 14d
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

    # RSI 14d
    if len(close) >= 16:
        deltas = close.diff().iloc[-15:]
        gains = deltas.where(deltas > 0, 0.0)
        losses = (-deltas).where(deltas < 0, 0.0)
        avg_gain = float(gains.mean())
        avg_loss = float(losses.mean())
        rsi = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    else:
        return None

    # Distance from 20d high
    if high is not None and len(high) >= 20:
        high_20d = float(high.iloc[-20:].max())
    else:
        high_20d = float(close.iloc[-20:].max())
    distance_from_20d_high = ((price - high_20d) / high_20d) * 100

    # Momentum 5d
    if len(close) >= 6:
        momentum_5d = ((price - float(close.iloc[-6])) / float(close.iloc[-6])) * 100
    else:
        return None

    # Momentum 20d
    momentum_20d = None
    if len(close) >= 21:
        momentum_20d = ((price - float(close.iloc[-21])) / float(close.iloc[-21])) * 100

    # Volume ratio
    volume_ratio = None
    if volume is not None and len(volume) >= 21:
        vol_today = float(volume.iloc[-1])
        vol_20d_avg = float(volume.iloc[-21:-1].mean())
        volume_ratio = vol_today / vol_20d_avg if vol_20d_avg > 0 else 0
        avg_dollar_vol = float(volume.iloc[-20:].mean()) * price
        if avg_dollar_vol < MIN_DOLLAR_VOL:
            return None

    # DIP criteria
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


def compute_outcomes(df_close, symbol, date_idx):
    """Compute 1d, 2d, 3d, 5d forward returns."""
    scan_price = float(df_close[symbol].iloc[date_idx])
    if scan_price <= 0:
        return None

    results = {}
    for horizon in [1, 2, 3, 5]:
        future = df_close[symbol].iloc[date_idx + 1:date_idx + 1 + horizon].dropna()
        if len(future) >= horizon:
            ret = (float(future.iloc[-1]) / scan_price - 1) * 100
            results[f'outcome_{horizon}d'] = round(ret, 2)
        else:
            results[f'outcome_{horizon}d'] = None

    # Max gain/dd over 5 days
    future_5 = df_close[symbol].iloc[date_idx + 1:date_idx + 6].dropna()
    if len(future_5) > 0:
        rets = ((future_5 - scan_price) / scan_price * 100).values
        results['outcome_max_gain_5d'] = round(float(np.max(rets)), 2)
        results['outcome_max_dd_5d'] = round(float(np.min(rets)), 2)
    else:
        results['outcome_max_gain_5d'] = None
        results['outcome_max_dd_5d'] = None

    return results


def ensure_columns():
    """Add outcome_1d/2d/3d columns if missing."""
    conn = sqlite3.connect(str(DB_PATH))
    for col in ['outcome_1d', 'outcome_2d', 'outcome_3d']:
        try:
            conn.execute(f"ALTER TABLE backfill_signal_outcomes ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def process_chunk(chunk_start, chunk_end, universe, existing, vix_history):
    """Process one time chunk."""
    symbols = list(universe.keys())

    # Download dates: warmup before chunk_start, extra after chunk_end for outcomes
    dl_start = (chunk_start - timedelta(days=WARMUP_DAYS + 280)).strftime('%Y-%m-%d')
    dl_end = (chunk_end + timedelta(days=10)).strftime('%Y-%m-%d')

    print(f"\n  Downloading {len(symbols)} stocks: {dl_start} to {dl_end}...")

    all_close, all_high, all_low, all_volume = [], [], [], []

    total_batches = (len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i + BATCH_SIZE]
        bn = i // BATCH_SIZE + 1
        try:
            df = yf.download(batch, start=dl_start, end=dl_end,
                             progress=False, auto_adjust=True, threads=True)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    all_close.append(df['Close'])
                    all_high.append(df['High'])
                    all_low.append(df['Low'])
                    all_volume.append(df['Volume'])
                else:
                    all_close.append(df[['Close']].rename(columns={'Close': batch[0]}))
                    all_high.append(df[['High']].rename(columns={'High': batch[0]}))
                    all_low.append(df[['Low']].rename(columns={'Low': batch[0]}))
                    all_volume.append(df[['Volume']].rename(columns={'Volume': batch[0]}))
        except Exception as e:
            print(f"    Batch {bn} error: {e}")

        if bn % 3 == 0:
            print(f"    [{bn}/{total_batches}] downloaded")
        time.sleep(0.3)

    if not all_close:
        print("  ERROR: No data downloaded for this chunk")
        return 0

    df_close = pd.concat(all_close, axis=1)
    df_high = pd.concat(all_high, axis=1)
    df_low = pd.concat(all_low, axis=1)
    df_volume = pd.concat(all_volume, axis=1)

    print(f"  Data: {len(df_close)} days × {len(df_close.columns)} stocks")

    # Determine scan dates within chunk
    chunk_start_ts = pd.Timestamp(chunk_start)
    chunk_end_ts = pd.Timestamp(chunk_end)

    trading_dates = [d for d in df_close.index
                     if chunk_start_ts <= d <= chunk_end_ts
                     and df_close.index.get_loc(d) >= 30  # warmup
                     and df_close.index.get_loc(d) < len(df_close) - 6]  # room for outcomes

    print(f"  Scan dates: {len(trading_dates)}")

    conn = sqlite3.connect(str(DB_PATH))
    inserted = 0

    for dt in trading_dates:
        date_str = dt.strftime('%Y-%m-%d')
        date_idx = df_close.index.get_loc(dt)

        vix = vix_history.get(date_str)
        if vix is None:
            for offset in range(-2, 3):
                alt = (dt + timedelta(days=offset)).strftime('%Y-%m-%d')
                vix = vix_history.get(alt)
                if vix:
                    break
        if vix is None:
            continue

        candidates = []
        for symbol in df_close.columns:
            if symbol not in universe:
                continue
            if (date_str, symbol) in existing:
                continue
            if pd.isna(df_close[symbol].iloc[date_idx]):
                continue

            features = compute_features(df_close, df_high, df_low, df_volume,
                                        symbol, date_idx)
            if features is None:
                continue

            outcomes = compute_outcomes(df_close, symbol, date_idx)
            if outcomes is None or outcomes.get('outcome_5d') is None:
                continue

            candidates.append({
                'scan_date': date_str,
                'symbol': symbol,
                'sector': universe.get(symbol, 'Unknown'),
                'vix_at_signal': round(vix, 2),
                **features,
                **outcomes,
            })

        random.shuffle(candidates)
        candidates = candidates[:MAX_CANDIDATES_PER_DAY]

        for c in candidates:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO backfill_signal_outcomes
                    (scan_date, symbol, sector, scan_price, atr_pct, entry_rsi,
                     distance_from_20d_high, momentum_5d, momentum_20d,
                     volume_ratio, vix_at_signal,
                     outcome_1d, outcome_2d, outcome_3d, outcome_5d,
                     outcome_max_gain_5d, outcome_max_dd_5d)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (c['scan_date'], c['symbol'], c['sector'], c['scan_price'],
                      c['atr_pct'], c['entry_rsi'], c['distance_from_20d_high'],
                      c['momentum_5d'], c['momentum_20d'], c['volume_ratio'],
                      c['vix_at_signal'],
                      c.get('outcome_1d'), c.get('outcome_2d'), c.get('outcome_3d'),
                      c['outcome_5d'], c['outcome_max_gain_5d'], c['outcome_max_dd_5d']))
                inserted += 1
                existing.add((date_str, c['symbol']))
            except Exception:
                pass

        if trading_dates.index(dt) % 20 == 0:
            conn.commit()
            print(f"    {date_str}: {len(candidates)} candidates, total={inserted}")

    conn.commit()
    conn.close()
    return inserted


def main():
    parser = argparse.ArgumentParser(description='Extended synthetic signal backfill')
    parser.add_argument('--start', required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end', required=True, help='End date YYYY-MM-DD')
    parser.add_argument('--chunk-months', type=int, default=4, help='Months per chunk (default 4)')
    args = parser.parse_args()

    start = datetime.strptime(args.start, '%Y-%m-%d')
    end = datetime.strptime(args.end, '%Y-%m-%d')

    print("=" * 70)
    print(f"  EXTENDED SYNTHETIC BACKFILL: {args.start} to {args.end}")
    print(f"  Chunk size: {args.chunk_months} months")
    print("=" * 70)

    universe = get_universe()
    print(f"Universe: {len(universe)} stocks")

    existing = get_existing_pairs()
    print(f"Existing rows: {len(existing)}")

    ensure_columns()

    # Load VIX from macro_snapshots (already backfilled) — avoids yfinance rate limit
    conn_vix = sqlite3.connect(str(DB_PATH))
    vix_rows = conn_vix.execute(
        "SELECT date, vix_close FROM macro_snapshots WHERE vix_close IS NOT NULL"
    ).fetchall()
    conn_vix.close()
    vix_history = {r[0]: r[1] for r in vix_rows}
    print(f"VIX from macro_snapshots: {len(vix_history)} days")

    if len(vix_history) == 0:
        # Fallback to yfinance
        vix_start = (start - timedelta(days=10)).strftime('%Y-%m-%d')
        vix_end = (end + timedelta(days=10)).strftime('%Y-%m-%d')
        print(f"Fallback: downloading VIX {vix_start} to {vix_end}...")
        vix_df = yf.download('^VIX', start=vix_start, end=vix_end, progress=False, auto_adjust=True)
        for dt_v, row in vix_df.iterrows():
            d = dt_v.strftime('%Y-%m-%d')
            val = row['Close']
            if isinstance(val, pd.Series):
                val = val.iloc[0]
            vix_history[d] = float(val)
        print(f"VIX from yfinance: {len(vix_history)} days")

    # Process in chunks
    chunk_start = start
    total_inserted = 0
    chunk_num = 0

    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=args.chunk_months * 30), end)
        chunk_num += 1

        print(f"\n{'='*70}")
        print(f"  CHUNK {chunk_num}: {chunk_start.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')}")
        print(f"{'='*70}")

        inserted = process_chunk(chunk_start.date(), chunk_end.date(),
                                 universe, existing, vix_history)
        total_inserted += inserted
        print(f"  Chunk {chunk_num} done: {inserted} rows inserted")

        chunk_start = chunk_end + timedelta(days=1)

    # Final summary
    conn = sqlite3.connect(str(DB_PATH))
    total = conn.execute("SELECT COUNT(*) FROM backfill_signal_outcomes").fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(scan_date), MAX(scan_date) FROM backfill_signal_outcomes"
    ).fetchone()
    dates_count = conn.execute(
        "SELECT COUNT(DISTINCT scan_date) FROM backfill_signal_outcomes"
    ).fetchone()[0]

    print(f"\n{'='*70}")
    print(f"  BACKFILL COMPLETE")
    print(f"{'='*70}")
    print(f"  New rows: {total_inserted}")
    print(f"  Total rows: {total}")
    print(f"  Unique dates: {dates_count}")
    print(f"  Date range: {date_range[0]} to {date_range[1]}")

    # Monthly summary
    monthly = conn.execute("""
        SELECT substr(scan_date, 1, 7) as month,
               COUNT(*) as n,
               ROUND(AVG(CASE WHEN outcome_5d > 0 THEN 1.0 ELSE 0.0 END)*100,1) as wr,
               ROUND(AVG(outcome_5d),2) as avg_ret
        FROM backfill_signal_outcomes
        GROUP BY month ORDER BY month
    """).fetchall()

    print(f"\n  {'Month':<10} {'N':>6} {'WR%':>6} {'Avg5d':>8}")
    for r in monthly:
        print(f"  {r[0]:<10} {r[1]:>6} {r[2]:>5.1f}% {r[3]:>+7.2f}%")

    conn.close()


if __name__ == '__main__':
    main()
