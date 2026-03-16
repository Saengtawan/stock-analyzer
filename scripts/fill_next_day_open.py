#!/usr/bin/env python3
"""
fill_next_day_open.py — v7.5

Fill next_day_open_pct for OVN (overnight_gap) trades from yesterday.
Run at 9:35 AM ET each trading day via cron.

next_day_open_pct = (today_open / sell_price - 1) × 100

Cron entry (TZ=America/New_York — auto-handles EDT/EST DST):
  35 9 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_next_day_open.py >> logs/fill_next_day_open.log 2>&1
"""
import sys
import os
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import yfinance as yf

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')


def main():
    print(f"[{datetime.now().isoformat()}] fill_next_day_open.py starting")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Find OVN/PED sells from yesterday with no next_day_open_pct
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    rows = conn.execute("""
        SELECT id, symbol, price as sell_price
        FROM trades
        WHERE action = 'SELL' AND signal_source IN ('overnight_gap', 'ped')
          AND date = ? AND next_day_open_pct IS NULL
    """, (yesterday,)).fetchall()

    if not rows:
        print(f"No OVN/PED sells from {yesterday} to fill.")
        conn.close()
        return

    symbols = list(set(r['symbol'] for r in rows))
    print(f"Filling next_day_open_pct for {len(rows)} OVN trades: {symbols}")

    updated = 0
    for row in rows:
        try:
            df = yf.download(row['symbol'], period='2d', interval='1d',
                             progress=False, auto_adjust=True)
            if df is None or len(df) < 1:
                print(f"  {row['symbol']}: no yfinance data")
                continue
            today_open = float(df['Open'].iloc[-1])
            if today_open <= 0:
                print(f"  {row['symbol']}: open={today_open} invalid")
                continue
            sell_price = float(row['sell_price'])
            if sell_price <= 0:
                print(f"  {row['symbol']}: sell_price={sell_price} invalid")
                continue
            pct = round((today_open / sell_price - 1) * 100, 3)
            conn.execute(
                "UPDATE trades SET next_day_open_pct = ? WHERE id = ?",
                (pct, row['id'])
            )
            print(f"  {row['symbol']}: sell=${sell_price:.2f} → open=${today_open:.2f} = {pct:+.3f}%")
            updated += 1
        except Exception as e:
            print(f"  {row['symbol']}: error — {e}")

    conn.commit()
    conn.close()
    print(f"Done. Updated {updated}/{len(rows)} rows.")


if __name__ == '__main__':
    main()
