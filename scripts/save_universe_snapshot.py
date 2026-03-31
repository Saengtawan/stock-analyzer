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
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')


def main():
    today = datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] save_universe_snapshot date={today}")

    with get_session() as session:

        # Check if already saved today
        existing = session.execute(
            text("SELECT COUNT(*) FROM universe_daily_snapshot WHERE date = :p0"), {'p0': today}
        ).fetchone()[0]
        if existing > 0:
            print(f"  Already saved {existing} rows for {today} — skipping")
            return

        # Load current universe_stocks (ranked by dollar_vol descending)
        stocks = session.execute(text("""
            SELECT symbol, dollar_vol, sector,
                   ROW_NUMBER() OVER (ORDER BY dollar_vol DESC) as rank
            FROM universe_stocks
            WHERE status = 'active'
        """)).fetchall()

        if not stocks:
            print("  universe_stocks empty — nothing to snapshot")
            return

        for r in stocks:
            session.execute(text("""
                INSERT OR IGNORE INTO universe_daily_snapshot (date, symbol, dollar_vol, sector, rank)
                VALUES (:p0,:p1,:p2,:p3,:p4)
            """), {'p0': today, 'p1': r[0], 'p2': r[1], 'p3': r[2], 'p4': r[3]})

        print(f"  Saved {len(stocks)} stocks for {today}")
        print(f"  Done.")


if __name__ == '__main__':
    main()
