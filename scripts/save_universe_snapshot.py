#!/usr/bin/env python3
"""
save_universe_snapshot.py — v7.6
==================================
Save daily snapshot of the prefilter universe (top ~987 stocks).
Enables simulation replay: "what stocks were eligible on date X?"

Without this, backtesting cannot replay which stocks the prefilter would
have passed on a given historical date — universe_stocks only keeps ONE
current snapshot and gets overwritten on each refresh.

Cron (TZ=America/New_York — run after evening prefilter refreshes pool):
  15 20 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/save_universe_snapshot.py >> logs/save_universe_snapshot.log 2>&1
"""
import os
import sqlite3
from datetime import datetime, date
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
ET = ZoneInfo('America/New_York')


def main():
    today = datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] save_universe_snapshot date={today}")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    # Check if already saved today
    existing = conn.execute(
        "SELECT COUNT(*) FROM universe_daily_snapshot WHERE date = ?", (today,)
    ).fetchone()[0]
    if existing > 0:
        print(f"  Already saved {existing} rows for {today} — skipping")
        conn.close()
        return

    # Load current universe_stocks (ranked by dollar_vol descending)
    stocks = conn.execute("""
        SELECT symbol, dollar_vol, sector,
               ROW_NUMBER() OVER (ORDER BY dollar_vol DESC) as rank
        FROM universe_stocks
        WHERE status = 'active'
    """).fetchall()

    if not stocks:
        print("  universe_stocks empty — nothing to snapshot")
        conn.close()
        return

    rows = [(today, r['symbol'], r['dollar_vol'], r['sector'], r['rank'])
            for r in stocks]

    conn.executemany("""
        INSERT OR IGNORE INTO universe_daily_snapshot (date, symbol, dollar_vol, sector, rank)
        VALUES (?,?,?,?,?)
    """, rows)
    conn.commit()
    conn.close()

    print(f"  Saved {len(rows)} stocks for {today}")
    print(f"  Done.")


if __name__ == '__main__':
    main()
