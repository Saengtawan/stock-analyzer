#!/usr/bin/env python3
"""
Backfill insider trading (Form 4 purchases) from yfinance + OpenInsider.
yfinance: easy per-stock insider_transactions
OpenInsider: bulk historical data

Stores in insider_transactions_history table.
"""
import sqlite3
import time
import requests
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

import yfinance as yf

DB = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS insider_transactions_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            filing_date TEXT,
            trade_date TEXT NOT NULL,
            insider_name TEXT,
            insider_title TEXT,
            transaction_type TEXT,
            shares INTEGER,
            price REAL,
            value REAL,
            source TEXT DEFAULT 'yfinance',
            UNIQUE(symbol, trade_date, insider_name, transaction_type, shares)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ith_symbol_date
        ON insider_transactions_history(symbol, trade_date)
    """)
    conn.commit()


def fetch_yfinance(conn, symbols):
    """Fetch insider transactions from yfinance for all symbols."""
    print(f"Fetching insider data from yfinance for {len(symbols)} symbols...")
    total = 0
    errors = 0

    for i, sym in enumerate(symbols):
        try:
            t = yf.Ticker(sym)
            txns = t.insider_transactions
            if txns is None or len(txns) == 0:
                continue

            for _, row in txns.iterrows():
                trade_date = str(row.get('Start Date', ''))[:10]
                if not trade_date or trade_date == 'NaT':
                    continue

                txn_type = str(row.get('Transaction', '') or row.get('Text', ''))
                insider = str(row.get('Insider', '') or '')
                position = str(row.get('Position', '') or '')
                shares = row.get('Shares', 0)
                value = row.get('Value', 0)

                if shares != shares:  # NaN check
                    shares = 0
                if value != value:
                    value = 0

                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO insider_transactions_history
                        (symbol, trade_date, insider_name, insider_title,
                         transaction_type, shares, value, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'yfinance')
                    """, (sym, trade_date, insider, position, txn_type,
                          int(shares) if shares else 0,
                          float(value) if value else 0))
                    total += 1
                except Exception:
                    pass

            conn.commit()
        except Exception as e:
            errors += 1

        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(symbols)}] +{total:,} rows, {errors} errors")
        time.sleep(0.3)

    conn.commit()
    print(f"  yfinance done: {total:,} rows inserted, {errors} errors")
    return total


def fetch_openinsider(conn, days_back=1825):
    """Fetch bulk insider purchases from OpenInsider (last N days)."""
    print(f"Fetching from OpenInsider (last {days_back} days)...")
    total = 0
    page = 1
    max_pages = 200

    while page <= max_pages:
        url = (f"http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd={days_back}"
               f"&fdr=&td=0&tdr=&feession=&feession=at&xp=1&vl=&vh=&ocl=&och=&session=sic1"
               f"&cnt=100&page={page}")
        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 StockAnalyzer/1.0'},
                                timeout=30)
            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table', class_='tinytable')
            if not table:
                break

            rows = table.find_all('tr')[1:]  # skip header
            if not rows:
                break

            page_count = 0
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 12:
                    continue

                try:
                    filing_date = cells[1].text.strip()[:10]
                    trade_date = cells[2].text.strip()[:10]
                    ticker = cells[3].text.strip()
                    insider = cells[4].text.strip()
                    title = cells[5].text.strip()
                    txn_type = cells[6].text.strip()

                    # Only purchases
                    if txn_type != 'P - Purchase':
                        continue

                    price_text = cells[7].text.strip().replace('$', '').replace(',', '')
                    qty_text = cells[8].text.strip().replace(',', '').replace('+', '')
                    val_text = cells[10].text.strip().replace('$', '').replace(',', '').replace('+', '')

                    price = float(price_text) if price_text else 0
                    qty = int(qty_text) if qty_text else 0
                    value = float(val_text) if val_text else 0

                    conn.execute("""
                        INSERT OR IGNORE INTO insider_transactions_history
                        (symbol, filing_date, trade_date, insider_name, insider_title,
                         transaction_type, shares, price, value, source)
                        VALUES (?, ?, ?, ?, ?, 'Purchase', ?, ?, ?, 'openinsider')
                    """, (ticker, filing_date, trade_date, insider, title,
                          qty, price, value))
                    page_count += 1
                    total += 1
                except Exception:
                    continue

            conn.commit()
            if page_count == 0:
                break

            if page % 10 == 0:
                print(f"  page {page}: +{total:,} purchases so far")

            page += 1
            time.sleep(1.0)  # polite crawling

        except Exception as e:
            print(f"  page {page} error: {e}")
            break

    print(f"  OpenInsider done: {total:,} purchase rows")
    return total


def main():
    conn = None  # via get_session())
    ensure_table(conn)

    # Check existing
    existing = conn.execute("SELECT COUNT(*) FROM insider_transactions_history").fetchone()[0]
    print(f"Existing rows: {existing:,}")

    if existing < 1000:
        # Fetch from OpenInsider first (bulk, 5 years)
        fetch_openinsider(conn, days_back=1825)

    # Fetch from yfinance (per-stock, fills gaps)
    symbols = [r[0] for r in conn.execute(
        "SELECT symbol FROM stock_fundamentals ORDER BY market_cap DESC")]
    fetch_yfinance(conn, symbols)

    # Summary
    total = conn.execute("SELECT COUNT(*) FROM insider_transactions_history").fetchone()[0]
    purchases = conn.execute(
        "SELECT COUNT(*) FROM insider_transactions_history WHERE transaction_type LIKE '%Purchase%' OR transaction_type LIKE '%Buy%'"
    ).fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(trade_date), MAX(trade_date) FROM insider_transactions_history"
    ).fetchone()

    print(f"\nFinal: {total:,} total rows, {purchases:,} purchases")
    print(f"Date range: {date_range[0]} to {date_range[1]}")
    conn.close()


if __name__ == '__main__':
    main()
