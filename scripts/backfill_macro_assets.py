#!/usr/bin/env python3
"""
backfill_macro_assets.py
========================
One-time backfill of gold_close, crude_close, hyg_close for existing macro_snapshots rows.

Usage: python3 scripts/backfill_macro_assets.py
"""
import os
import sqlite3
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')


def main():
    conn = None  # via get_session()

    # Ensure columns exist
    for col in ['gold_close', 'crude_close', 'hyg_close']:
        try:
            conn.execute(f"ALTER TABLE macro_snapshots ADD COLUMN {col} REAL")
        except Exception:
            pass
    conn.commit()

    # Get dates needing backfill
    rows = conn.execute("""
        SELECT date FROM macro_snapshots
        WHERE gold_close IS NULL OR crude_close IS NULL OR hyg_close IS NULL
        ORDER BY date
    """).fetchall()

    if not rows:
        print("Nothing to backfill — all rows have gold/crude/hyg data.")
        conn.close()
        return

    dates = [r[0] for r in rows]
    print(f"[{datetime.now():%H:%M:%S}] Backfilling {len(dates)} dates: {dates[0]} → {dates[-1]}")

    # Download all 3 assets for the full range
    start = (datetime.strptime(dates[0], '%Y-%m-%d') - timedelta(days=3)).strftime('%Y-%m-%d')
    end = (datetime.strptime(dates[-1], '%Y-%m-%d') + timedelta(days=2)).strftime('%Y-%m-%d')

    symbols = {'GC=F': 'gold_close', 'CL=F': 'crude_close', 'HYG': 'hyg_close'}
    filled = 0

    for sym, col_name in symbols.items():
        print(f"  Downloading {sym}...")
        try:
            df = yf.download(sym, start=start, end=end, interval='1d',
                             auto_adjust=True, progress=False)
            if df.empty:
                print(f"  ⚠ No data for {sym}")
                continue

            # Build date→close lookup
            close_by_date = {}
            for idx, row in df.iterrows():
                d = idx.strftime('%Y-%m-%d')
                val = float(row['Close'].iloc[0] if hasattr(row['Close'], 'iloc') else row['Close'])
                close_by_date[d] = round(val, 2)

            # Update each target date (use exact match or most recent available)
            sorted_available = sorted(close_by_date.keys())
            for target_date in dates:
                # Find the most recent available date <= target_date
                val = close_by_date.get(target_date)
                if val is None:
                    # Look for most recent before target
                    for d in reversed(sorted_available):
                        if d <= target_date:
                            val = close_by_date[d]
                            break
                if val is not None:
                    conn.execute(f"UPDATE macro_snapshots SET {col_name}=? WHERE date=? AND {col_name} IS NULL",
                                 (val, target_date))
                    filled += 1

        except Exception as e:
            print(f"  ⚠ Error downloading {sym}: {e}")

    conn.commit()
    conn.close()
    print(f"\n✅ Done. Updated {filled} cells across {len(dates)} dates.")


if __name__ == '__main__':
    main()
