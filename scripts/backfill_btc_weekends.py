#!/usr/bin/env python3
"""
Backfill BTC Saturday+Sunday close prices into macro_snapshots.
Covers all weekends from 2020-01-01 to present.
"""
import sqlite3
import time
import logging
from pathlib import Path
from datetime import datetime, date, timedelta

import yfinance as yf
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'


def main():
    conn = None  # via get_session(), timeout=60)

    # Download full BTC history
    logger.info("Downloading BTC-USD full history...")
    btc = yf.download('BTC-USD', start='2020-01-01', end=(date.today() + timedelta(days=1)).strftime('%Y-%m-%d'),
                       progress=False, auto_adjust=True)
    if btc.empty:
        logger.error("No BTC data!")
        return

    # Build date→close map
    btc_closes = {}
    for dt, row in btc.iterrows():
        val = row['Close']
        if isinstance(val, pd.Series):
            val = val.iloc[0]
        btc_closes[dt.strftime('%Y-%m-%d')] = round(float(val), 4)
    logger.info(f"BTC data: {len(btc_closes)} days")

    # Get existing macro_snapshots dates with btc_close
    existing = {}
    for r in conn.execute("SELECT date, btc_close FROM macro_snapshots WHERE date >= '2020-01-01'"):
        existing[r[0]] = r[1]

    # Find all Saturdays and Sundays
    inserted = 0
    updated = 0
    d = date(2020, 1, 4)  # First Saturday in 2020
    today = date.today()

    while d <= today:
        if d.weekday() in (5, 6):  # Sat or Sun
            d_str = d.strftime('%Y-%m-%d')
            btc_val = btc_closes.get(d_str)

            if btc_val is not None:
                if d_str in existing:
                    if existing[d_str] is None:
                        conn.execute(
                            "UPDATE macro_snapshots SET btc_close = ?, collected_at = datetime('now') WHERE date = ?",
                            (btc_val, d_str)
                        )
                        updated += 1
                else:
                    conn.execute(
                        "INSERT INTO macro_snapshots (date, btc_close, collected_at) VALUES (?, ?, datetime('now'))",
                        (d_str, btc_val)
                    )
                    inserted += 1
        d += timedelta(days=1)

    conn.commit()

    # Verify
    total = conn.execute("""
        SELECT COUNT(*) FROM macro_snapshots
        WHERE strftime('%w', date) IN ('0','6') AND btc_close IS NOT NULL
    """).fetchone()[0]

    logger.info(f"Inserted: {inserted}, Updated: {updated}")
    logger.info(f"Total weekend rows with BTC: {total}")

    # Sample check
    rows = conn.execute("""
        SELECT date, btc_close FROM macro_snapshots
        WHERE date >= '2026-03-14' ORDER BY date
    """).fetchall()
    logger.info("Recent data:")
    days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    for r in rows:
        dt = datetime.strptime(r[0], '%Y-%m-%d')
        logger.info(f"  {days[dt.weekday()]} {r[0]}: BTC={r[1]}")

    conn.close()
    logger.info("Done.")


if __name__ == '__main__':
    main()
