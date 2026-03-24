#!/usr/bin/env python3
"""
Collect short interest for all universe stocks from yfinance.
Only current + prior month available (no deep history).
Stores snapshot in short_interest_history table.
"""
import sqlite3
import time
from pathlib import Path
from datetime import date

import yfinance as yf

DB = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS short_interest_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            collected_date TEXT NOT NULL,
            shares_short INTEGER,
            short_ratio REAL,
            short_pct_float REAL,
            shares_short_prior INTEGER,
            date_short_interest TEXT,
            UNIQUE(symbol, collected_date)
        )
    """)
    conn.commit()


def main():
    conn = sqlite3.connect(str(DB))
    ensure_table(conn)

    today = date.today().isoformat()

    # Check if already collected today
    existing = conn.execute(
        "SELECT COUNT(*) FROM short_interest_history WHERE collected_date = ?", (today,)
    ).fetchone()[0]
    if existing > 100:
        print(f"Already collected {existing} stocks today. Skipping.")
        conn.close()
        return

    symbols = [r[0] for r in conn.execute(
        "SELECT symbol FROM stock_fundamentals ORDER BY market_cap DESC")]

    print(f"Collecting short interest for {len(symbols)} symbols...")
    total = 0
    errors = 0

    for i, sym in enumerate(symbols):
        try:
            info = yf.Ticker(sym).info
            shares_short = info.get('sharesShort')
            short_ratio = info.get('shortRatio')
            short_pct = info.get('shortPercentOfFloat')
            prior = info.get('sharesShortPriorMonth')
            si_date = info.get('dateShortInterest')

            if shares_short is not None:
                conn.execute("""
                    INSERT OR REPLACE INTO short_interest_history
                    (symbol, collected_date, shares_short, short_ratio,
                     short_pct_float, shares_short_prior, date_short_interest)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (sym, today, shares_short, short_ratio, short_pct,
                      prior, str(si_date) if si_date else None))
                total += 1

        except Exception:
            errors += 1

        if (i + 1) % 100 == 0:
            conn.commit()
            print(f"  [{i+1}/{len(symbols)}] +{total:,} rows, {errors} errors")

        time.sleep(0.4)

    conn.commit()
    print(f"\nDone: {total:,} stocks with short interest data, {errors} errors")
    conn.close()


if __name__ == '__main__':
    main()
