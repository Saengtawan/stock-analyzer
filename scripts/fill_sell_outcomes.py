#!/usr/bin/env python3
"""
fill_sell_outcomes.py
=====================
Fill post-sell outcome columns for sell_outcomes rows.

For rows where post_sell_pnl_pct_5d IS NULL and enough trading days have passed,
download daily bars and compute:
  post_sell_close_1d/3d/5d   — closing price on D+1/3/5
  post_sell_max_5d/min_5d    — max high / min low within 5 days
  post_sell_pnl_pct_1d/5d    — % change from sell_price

Answers: "Did we sell too early?"

Cron (TZ=America/New_York):
  15 5 * * 2-6  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_sell_outcomes.py >> logs/fill_sell_outcomes.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import os
import time
from datetime import datetime, date, timedelta
from collections import defaultdict

import yfinance as yf
import pandas as pd



def fill():
    # conn via get_session()

    cutoff = (date.today() - timedelta(days=7)).isoformat()

    rows = conn.execute("""
        SELECT id, symbol, sell_date, sell_price
        FROM sell_outcomes
        WHERE post_sell_pnl_pct_5d IS NULL
          AND sell_price IS NOT NULL AND sell_price > 0
          AND sell_date <= ?
        ORDER BY sell_date
    """, (cutoff,)).fetchall()

    if not rows:
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] No sell_outcomes to fill.")
        return

    print(f"[{datetime.now():%Y-%m-%d %H:%M}] {len(rows)} sell_outcomes to fill")

    by_symbol = defaultdict(list)
    for r in rows:
        by_symbol[r['symbol']].append(dict(r))

    symbols = list(by_symbol.keys())
    min_date = min(r['sell_date'] for r in rows)
    start = (datetime.strptime(min_date[:10], '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

    filled = 0

    try:
        data = yf.download(' '.join(symbols), start=start, interval='1d',
                           auto_adjust=True, progress=False, threads=False)
    except Exception as e:
        print(f"  Download error: {e}")
        return

    if data.empty:
        print("  No data downloaded")
        return

    for sym in symbols:
        try:
            if len(symbols) == 1:
                df = data
            else:
                if sym not in data.columns.get_level_values(1):
                    continue
                df = data.xs(sym, axis=1, level=1)

            if df is None or df.empty:
                continue

            for row in by_symbol.get(sym, []):
                sell_dt = pd.Timestamp(row['sell_date'][:10])
                future = df[df.index > sell_dt]

                if len(future) < 5:
                    continue

                sell_price = row['sell_price']
                updates = {}

                # Close on D+1, D+3, D+5
                for day_n, col in [(1, 'post_sell_close_1d'), (3, 'post_sell_close_3d'), (5, 'post_sell_close_5d')]:
                    if len(future) >= day_n:
                        updates[col] = round(float(future['Close'].iloc[day_n - 1]), 2)

                # Max/min within 5 days
                n = min(5, len(future))
                sl = future.iloc[:n]
                updates['post_sell_max_5d'] = round(float(sl['High'].max()), 2)
                updates['post_sell_min_5d'] = round(float(sl['Low'].min()), 2)

                # PnL percentages
                if 'post_sell_close_1d' in updates:
                    updates['post_sell_pnl_pct_1d'] = round((updates['post_sell_close_1d'] / sell_price - 1) * 100, 2)
                if 'post_sell_close_5d' in updates:
                    updates['post_sell_pnl_pct_5d'] = round((updates['post_sell_close_5d'] / sell_price - 1) * 100, 2)

                if updates:
                    set_parts = ', '.join(f"{k}=?" for k in updates)
                    vals = list(updates.values()) + [row['id']]
                    conn.execute(f"UPDATE sell_outcomes SET {set_parts}, updated_at=datetime('now') WHERE id=?", vals)
                    filled += 1

        except Exception as e:
            print(f"  Error {sym}: {e}")
            continue
    print(f"  Done. filled={filled}/{len(rows)}")


if __name__ == '__main__':
    fill()
