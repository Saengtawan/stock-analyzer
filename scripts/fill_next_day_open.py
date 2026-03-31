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
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text

import yfinance as yf



def main():
    print(f"[{datetime.now().isoformat()}] fill_next_day_open.py starting")

    with get_session() as session:

        # Find OVN/PED sells from yesterday with no next_day_open_pct
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        rows = session.execute(text("""
            SELECT id, symbol, price as sell_price
            FROM trades
            WHERE action = 'SELL' AND signal_source IN ('overnight_gap', 'ped')
              AND date = :p0 AND next_day_open_pct IS NULL
        """), {'p0': yesterday}).fetchall()

        if not rows:
            print(f"No OVN/PED sells from {yesterday} to fill.")
            return

        symbols = list(set(r[1] for r in rows))
        print(f"Filling next_day_open_pct for {len(rows)} OVN trades: {symbols}")

        updated = 0
        for row in rows:
            try:
                df = yf.download(row[1], period='2d', interval='1d',
                                 progress=False, auto_adjust=True)
                if df is None or len(df) < 1:
                    print(f"  {row[1]}: no yfinance data")
                    continue
                today_open = float(df['Open'].iloc[-1])
                if today_open <= 0:
                    print(f"  {row[1]}: open={today_open} invalid")
                    continue
                sell_price = float(row[2])
                if sell_price <= 0:
                    print(f"  {row[1]}: sell_price={sell_price} invalid")
                    continue
                pct = round((today_open / sell_price - 1) * 100, 3)
                session.execute(
                    text("UPDATE trades SET next_day_open_pct = :p0 WHERE id = :p1"),
                    {'p0': pct, 'p1': row[0]}
                )
                print(f"  {row[1]}: sell=${sell_price:.2f} -> open=${today_open:.2f} = {pct:+.3f}%")
                updated += 1
            except Exception as e:
                print(f"  {row[1]}: error — {e}")
        print(f"Done. Updated {updated}/{len(rows)} rows.")


if __name__ == '__main__':
    main()
