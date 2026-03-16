#!/usr/bin/env python3
"""
fill_rejected_outcomes.py
=========================
Fill outcome_1d..5d for rejected_outcomes rows (pre-filter rejects).

For rows where outcome_5d IS NULL and enough trading days have passed since scan_date,
download daily bars and compute outcomes relative to scan_price.

Cron (TZ=America/New_York):
  10 5 * * 2-6  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_rejected_outcomes.py >> logs/fill_rejected_outcomes.log 2>&1
"""
import os
import sqlite3
import time
from datetime import datetime, date, timedelta
from collections import defaultdict

import yfinance as yf
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')


def fill():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Cutoff: only fill rows where D+5 trading days have elapsed (~7 calendar days)
    cutoff = (date.today() - timedelta(days=7)).isoformat()

    rows = conn.execute("""
        SELECT id, symbol, scan_date, scan_price
        FROM rejected_outcomes
        WHERE outcome_5d IS NULL
          AND scan_price IS NOT NULL AND scan_price > 0
          AND scan_date <= ?
        ORDER BY scan_date
    """, (cutoff,)).fetchall()

    if not rows:
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] No rows to fill.")
        conn.close()
        return

    print(f"[{datetime.now():%Y-%m-%d %H:%M}] {len(rows)} rows to fill (scan_date <= {cutoff})")

    # Group by symbol
    by_symbol = defaultdict(list)
    for r in rows:
        by_symbol[r['symbol']].append(dict(r))

    symbols = list(by_symbol.keys())
    min_date = min(r['scan_date'] for r in rows)
    start = (datetime.strptime(min_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

    filled = 0
    errors = 0
    batch_size = 50

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        batch_str = ' '.join(batch)
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size
        print(f"  Batch {batch_num}/{total_batches}: {len(batch)} symbols")

        try:
            data = yf.download(batch_str, start=start, interval='1d',
                               auto_adjust=True, progress=False, threads=False)
        except Exception as e:
            print(f"  Download error: {e}")
            errors += len(batch)
            continue

        if data.empty:
            continue

        for sym in batch:
            try:
                if len(batch) == 1:
                    df = data
                else:
                    if sym not in data.columns.get_level_values(1):
                        continue
                    df = data.xs(sym, axis=1, level=1)

                if df is None or df.empty:
                    continue

                for row in by_symbol.get(sym, []):
                    scan_dt = pd.Timestamp(row['scan_date'])
                    future = df[df.index > scan_dt]

                    if len(future) < 5:
                        continue  # Not enough trading days

                    scan_price = row['scan_price']
                    outcomes = {}

                    for day_n in [1, 2, 3, 4, 5]:
                        if len(future) >= day_n:
                            close_n = float(future['Close'].iloc[day_n - 1])
                            outcomes[f'outcome_{day_n}d'] = round((close_n / scan_price - 1) * 100, 2)

                    if len(future) >= 1:
                        n = min(5, len(future))
                        sl = future.iloc[:n]
                        max_high = float(sl['High'].max())
                        min_low = float(sl['Low'].min())
                        outcomes['outcome_max_gain_5d'] = round((max_high / scan_price - 1) * 100, 2)
                        outcomes['outcome_max_dd_5d'] = round((min_low / scan_price - 1) * 100, 2)

                    if outcomes and 'outcome_5d' in outcomes:
                        set_parts = ', '.join(f"{k}=?" for k in outcomes)
                        vals = list(outcomes.values()) + [row['id']]
                        conn.execute(f"UPDATE rejected_outcomes SET {set_parts}, updated_at=datetime('now') WHERE id=?", vals)
                        filled += 1

            except Exception as e:
                errors += 1
                continue

        if filled % 50 == 0 and filled > 0:
            conn.commit()

        # Rate limit
        if i + batch_size < len(symbols):
            time.sleep(1)

    conn.commit()
    conn.close()
    print(f"  Done. filled={filled} errors={errors}")


if __name__ == '__main__':
    fill()
