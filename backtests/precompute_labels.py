"""
Phase 1: Precompute trail PnL labels from 5-min bars for ALL rows in pkl.
Saves to /tmp/bt_labels_v91.pkl
"""

import pandas as pd
import numpy as np
import sqlite3
import time as _time
import warnings
warnings.filterwarnings('ignore')

DB_PATH = '/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db'
PKL_PATH = '/tmp/bt_features_v13_more_path.pkl'
OUTPUT_PATH = '/tmp/bt_labels_v91.pkl'


def mins_to_time(mins):
    h = 9 + (30 + mins) // 60
    m = (30 + mins) % 60
    return f"{h:02d}:{m:02d}"


def simulate_trail_numpy(times, highs, lows, closes, start_idx, entry_price, trail_mode):
    """Fast trail simulation on numpy arrays."""
    peak = entry_price
    for j in range(start_idx, len(times)):
        t = times[j]
        if trail_mode == 'decay':
            trail_pct = 0.03 if t < '10:00' else (0.02 if t < '10:30' else 0.01)
        else:
            trail_pct = 0.03

        if highs[j] > peak:
            peak = highs[j]

        trail_level = peak * (1 - trail_pct)
        if lows[j] <= trail_level:
            return (trail_level / entry_price - 1) * 100

    return (closes[-1] / entry_price - 1) * 100


def main():
    t0 = _time.time()
    print("Loading pkl...")
    df = pd.read_pickle(PKL_PATH)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    print(f"  {len(df)} rows, dates {df['date'].min()} to {df['date'].max()}")

    # Assign bucket trail mode
    df['trail_mode'] = 'fixed3'
    df.loc[df['mins_from_open'] <= 25, 'trail_mode'] = 'decay'

    # Get all unique (sym, date) pairs
    pairs = df[['sym', 'date']].drop_duplicates()
    print(f"  {len(pairs)} unique (sym, date) pairs")

    # Load ALL bars from DB in chunks by month
    all_dates = sorted(df['date'].unique())
    print(f"  Loading bars for {len(all_dates)} dates...")

    conn = sqlite3.connect(DB_PATH)

    # Build bars lookup
    bars_lookup = {}
    months = sorted(set(d[:7] for d in all_dates))
    for i, month in enumerate(months):
        mt0 = _time.time()
        query = f"""
            SELECT symbol, date, time_et, open, high, low, close
            FROM intraday_bars_5m
            WHERE date LIKE '{month}%'
              AND time_et >= '09:30' AND time_et <= '16:00'
            ORDER BY symbol, date, time_et
        """
        bars = pd.read_sql(query, conn)
        for (sym, date), grp in bars.groupby(['symbol', 'date']):
            g = grp.sort_values('time_et')
            bars_lookup[(sym, date)] = (
                g['time_et'].values,
                g['high'].values.astype(float),
                g['low'].values.astype(float),
                g['close'].values.astype(float),
                g['open'].values.astype(float),
            )
        print(f"  [{month}] loaded {len(bars)} bars ({_time.time()-mt0:.0f}s) "
              f"[{i+1}/{len(months)}]", flush=True)

    conn.close()
    print(f"  Bars lookup: {len(bars_lookup)} (sym, date) pairs")

    # Compute labels
    print("Computing labels...")
    labels_decay = np.full(len(df), np.nan)
    labels_fixed3 = np.full(len(df), np.nan)

    # Pre-compute entry time strings for all mins_from_open values
    time_cache = {}
    for m in df['mins_from_open'].unique():
        time_cache[int(m)] = mins_to_time(int(m))

    batch_size = 50000
    for start in range(0, len(df), batch_size):
        end = min(start + batch_size, len(df))
        bt0 = _time.time()

        for i in range(start, end):
            row = df.iloc[i]
            sym = row['sym']
            date = row['date']
            mins = int(row['mins_from_open'])
            entry_time = time_cache[mins]

            key = (sym, date)
            if key not in bars_lookup:
                labels_decay[i] = 0.0
                labels_fixed3[i] = 0.0
                continue

            times, highs, lows, closes, opens = bars_lookup[key]

            start_idx = np.searchsorted(times, entry_time, side='left')
            if start_idx >= len(times):
                labels_decay[i] = 0.0
                labels_fixed3[i] = 0.0
                continue

            entry_price = opens[start_idx]
            if entry_price <= 0:
                labels_decay[i] = 0.0
                labels_fixed3[i] = 0.0
                continue

            labels_decay[i] = simulate_trail_numpy(
                times, highs, lows, closes, start_idx, entry_price, 'decay')
            labels_fixed3[i] = simulate_trail_numpy(
                times, highs, lows, closes, start_idx, entry_price, 'fixed3')

        elapsed = _time.time() - bt0
        done_pct = end / len(df) * 100
        print(f"  [{end}/{len(df)} ({done_pct:.0f}%)] {elapsed:.0f}s", flush=True)

    # Save
    result = pd.DataFrame({
        'label_decay': labels_decay,
        'label_fixed3': labels_fixed3,
    }, index=df.index)

    result.to_pickle(OUTPUT_PATH)
    print(f"\nSaved to {OUTPUT_PATH}")
    print(f"  decay: mean={np.nanmean(labels_decay):.3f}%, "
          f"std={np.nanstd(labels_decay):.3f}%")
    print(f"  fixed3: mean={np.nanmean(labels_fixed3):.3f}%, "
          f"std={np.nanstd(labels_fixed3):.3f}%")
    print(f"  NaN count: decay={np.isnan(labels_decay).sum()}, "
          f"fixed3={np.isnan(labels_fixed3).sum()}")
    print(f"Total time: {_time.time()-t0:.0f}s ({(_time.time()-t0)/60:.1f} min)")


if __name__ == '__main__':
    main()
