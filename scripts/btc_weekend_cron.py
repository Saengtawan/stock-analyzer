#!/usr/bin/env python3
"""
btc_weekend_cron.py — Capture BTC Saturday + Sunday close prices.
================================================================
BTC trades 24/7 but macro_snapshot_cron only runs Tue-Sat (weekday data).
This script fills the weekend gap.

Stores Saturday and Sunday rows in macro_snapshots with btc_close
(other macro fields are NULL since stock/bond markets are closed).

Use case: BTC weekend movement predicts Monday gap direction.
  - BTC drops >5% on weekend → high prob of risk-off Monday open.

Cron (TZ=America/New_York):
  0 18 * * 0  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/btc_weekend_cron.py >> logs/btc_weekend.log 2>&1

(6:00 PM ET Sunday — captures both Saturday and Sunday BTC close)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import os
from datetime import datetime, date, timedelta

import yfinance as yf

BTC = 'BTC-USD'


def _get_btc_close(target_date: date) -> float | None:
    """Fetch BTC close for a specific date."""
    try:
        start = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
        end = (target_date + timedelta(days=1)).strftime('%Y-%m-%d')
        df = yf.download(BTC, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            return None
        df = df[df.index.date <= target_date]
        if df.empty:
            return None
        val = df['Close'].iloc[-1]
        if hasattr(val, 'iloc'):
            val = val.iloc[0]
        return round(float(val), 4)
    except Exception as e:
        print(f"  BTC fetch error for {target_date}: {e}")
        return None


def main():
    today = date.today()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] btc_weekend_cron")

    # Determine Saturday and Sunday dates
    # If run on Sunday: saturday = today - 1, sunday = today
    # If run on Saturday: saturday = today, sunday not yet available
    if today.weekday() == 6:  # Sunday
        saturday = today - timedelta(days=1)
        sunday = today
    elif today.weekday() == 5:  # Saturday
        saturday = today
        sunday = None
    else:
        # Shouldn't happen in cron, but handle gracefully
        # Find most recent weekend
        days_since_sunday = today.weekday() + 1
        sunday = today - timedelta(days=days_since_sunday)
        saturday = sunday - timedelta(days=1)

    dates_to_fill = [saturday]
    if sunday:
        dates_to_fill.append(sunday)

    with get_session() as session:
        for target in dates_to_fill:
            target_str = target.strftime('%Y-%m-%d')

            # Check if already exists
            existing = session.execute(
                text("SELECT btc_close FROM macro_snapshots WHERE date = :p0"),
                {"p0": target_str}
            ).fetchone()
            if existing and existing[0] is not None:
                print(f"  {target_str}: already has BTC={existing[0]} — skip")
                continue

            btc = _get_btc_close(target)
            if btc is None:
                print(f"  {target_str}: no BTC data available")
                continue

            if existing:
                # Row exists but btc_close is NULL — update
                session.execute(
                    text("UPDATE macro_snapshots SET btc_close = :p0, collected_at = datetime('now') WHERE date = :p1"),
                    {"p0": btc, "p1": target_str}
                )
            else:
                # Insert new weekend row (only btc_close populated)
                session.execute(
                    text("INSERT INTO macro_snapshots (date, btc_close, collected_at) VALUES (:p0, :p1, datetime('now'))"),
                    {"p0": target_str, "p1": btc}
                )
            print(f"  {target_str} ({['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][target.weekday()]}): BTC={btc}")
    print("  Done.")


if __name__ == '__main__':
    main()
