#!/usr/bin/env python3
"""
Backfill analyst upgrades/downgrades history from yfinance.
Fetches upgrades_downgrades for all universe stocks → analyst_ratings_history table.
Expected: ~500K rows going back to 2012-2015.
Runtime: ~30-45 minutes for 1000 stocks.
"""
import sqlite3
import time
import sys
from pathlib import Path

import yfinance as yf

DB = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyst_ratings_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            firm TEXT,
            to_grade TEXT,
            from_grade TEXT,
            action TEXT,
            price_target REAL,
            prior_price_target REAL,
            UNIQUE(symbol, date, firm)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_arh_symbol_date
        ON analyst_ratings_history(symbol, date)
    """)
    conn.commit()


def fetch_and_store(conn, symbol):
    """Fetch upgrades_downgrades for one stock and store in DB."""
    try:
        t = yf.Ticker(symbol)
        ud = t.upgrades_downgrades
        if ud is None or len(ud) == 0:
            return 0

        inserted = 0
        for grade_date, row in ud.iterrows():
            date_str = str(grade_date)[:10]  # YYYY-MM-DD
            firm = row.get('Firm', '')
            to_grade = row.get('ToGrade', '')
            from_grade = row.get('FromGrade', '')
            action = row.get('Action', '')
            pt = row.get('currentPriceTarget')
            prior_pt = row.get('priorPriceTarget')

            # Convert NaN to None
            if pt is not None and (pt != pt or pt == 0):
                pt = None
            if prior_pt is not None and (prior_pt != prior_pt or prior_pt == 0):
                prior_pt = None

            try:
                conn.execute("""
                    INSERT OR IGNORE INTO analyst_ratings_history
                    (symbol, date, firm, to_grade, from_grade, action, price_target, prior_price_target)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (symbol, date_str, firm, to_grade, from_grade, action, pt, prior_pt))
                inserted += 1
            except Exception:
                pass

        conn.commit()
        return inserted
    except Exception as e:
        return -1


def main():
    conn = sqlite3.connect(str(DB))
    ensure_table(conn)

    # Get all universe symbols
    symbols = [r[0] for r in conn.execute(
        "SELECT symbol FROM stock_fundamentals ORDER BY market_cap DESC"
    )]

    # Check what we already have
    existing = set(r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM analyst_ratings_history"
    ))

    todo = [s for s in symbols if s not in existing]
    print(f"Total symbols: {len(symbols)}, already done: {len(existing)}, todo: {len(todo)}")

    if not todo:
        print("All done!")
        total = conn.execute("SELECT COUNT(*) FROM analyst_ratings_history").fetchone()[0]
        print(f"Total rows: {total:,}")
        conn.close()
        return

    t0 = time.time()
    total_inserted = 0
    errors = 0

    for i, sym in enumerate(todo):
        n = fetch_and_store(conn, sym)
        if n < 0:
            errors += 1
            n = 0
        total_inserted += n

        if (i + 1) % 50 == 0 or i == len(todo) - 1:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(todo) - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{len(todo)}] +{total_inserted:,} rows, "
                  f"{errors} errors, {elapsed:.0f}s elapsed, ETA {eta:.0f}s")

        # Rate limit: ~2 req/sec to avoid throttling
        time.sleep(0.4)

    total = conn.execute("SELECT COUNT(*) FROM analyst_ratings_history").fetchone()[0]
    print(f"\nDone! Total rows in analyst_ratings_history: {total:,}")
    print(f"Date range: {conn.execute('SELECT MIN(date), MAX(date) FROM analyst_ratings_history').fetchone()}")
    conn.close()


if __name__ == '__main__':
    main()
