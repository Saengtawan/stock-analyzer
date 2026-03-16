#!/usr/bin/env python3
"""
insider_collector.py — v7.5
============================
Collect SEC Form 4 insider purchase transactions for universe stocks.
Focuses on PURCHASES only (acquired, non-derivative, shares > 0, value > $10K).

Data source: SEC EDGAR full-text search + individual filing XML parse.
Latency: ~2 business days from transaction date.

Cron (TZ=America/New_York — auto-handles EDT/EST DST):
  30 16 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/insider_collector.py >> logs/insider_collector.log 2>&1

(4:30 PM ET Mon-Fri — after market close at 4:00 PM, before OVN scan at 3:45 PM next day)

Usage:
  python3 scripts/insider_collector.py              # last 2 days
  python3 scripts/insider_collector.py --days 7     # last 7 days
  python3 scripts/insider_collector.py --date 2026-03-10  # specific date
  python3 scripts/insider_collector.py --dry-run    # preview only
"""
import argparse
import os
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta

import requests

DB_PATH    = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
LOG_DIR    = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

SEC_SEARCH_URL = 'https://efts.sec.gov/LATEST/search-index'
SEC_ARCHIVES   = 'https://www.sec.gov/Archives/edgar/data'
# SEC requires proper identification in User-Agent
SEC_USER_AGENT = 'StockAnalyzer research@stockanalyzer.local'

HEADERS = {
    'User-Agent': SEC_USER_AGENT,
    'Accept-Encoding': 'gzip, deflate',
}

MIN_PURCHASE_VALUE = 10_000  # $10K — filter noise (options exercises, tiny grants)


def _ensure_table(conn: sqlite3.Connection):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS insider_transactions (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            filing_date        TEXT NOT NULL,
            transaction_date   TEXT,
            symbol             TEXT NOT NULL,
            cik                TEXT,
            insider_name       TEXT,
            insider_title      TEXT,
            transaction_type   TEXT,
            shares             INTEGER,
            price_per_share    REAL,
            total_value        REAL,
            shares_owned_after INTEGER,
            accession_number   TEXT UNIQUE,
            collected_at       TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_insider_symbol ON insider_transactions(symbol)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_insider_date ON insider_transactions(transaction_date)')
    conn.commit()


def _get_universe_symbols(conn: sqlite3.Connection) -> set:
    try:
        rows = conn.execute("SELECT symbol FROM universe_stocks").fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _search_form4(start_date: str, end_date: str) -> list:
    """
    Search SEC EDGAR for Form 4 filings. Returns list of dicts with:
    {accession_number, xml_filename, filing_date, ciks, display_names}
    """
    filings = []
    from_val = 0
    page_size = 100

    while True:
        params = {
            'forms': '4',
            'dateRange': 'custom',
            'startdt': start_date,
            'enddt': end_date,
            'from': from_val,
        }
        try:
            resp = requests.get(SEC_SEARCH_URL, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  SEC search error: {e}")
            break

        hits = data.get('hits', {}).get('hits', [])
        if not hits:
            break

        for hit in hits:
            raw_id = hit.get('_id', '')
            src = hit.get('_source', {})
            # _id format: "{accession_number}:{xml_filename}"
            acc, _, xml_file = raw_id.partition(':')
            ciks = src.get('ciks', [])
            display_names = src.get('display_names', [])
            filings.append({
                'accession_number': acc,
                'xml_filename':     xml_file,
                'filing_date':      (src.get('file_date', '') or '')[:10],
                'ciks':             ciks,
                'display_names':    display_names,
            })

        total = data.get('hits', {}).get('total', {}).get('value', 0)
        from_val += len(hits)
        if from_val >= total or from_val >= 2000:
            break
        time.sleep(0.11)  # SEC rate limit: max 10 req/sec

    return filings


def _parse_form4_xml(cik: str, accession_number: str, xml_filename: str) -> list:
    """
    Fetch and parse Form 4 XML. Returns non-derivative purchase transactions.
    cik: WITH leading zeros (e.g. '0001400568') — needed for URL
    """
    acc_clean = accession_number.replace('-', '')
    url = f"{SEC_ARCHIVES}/{cik}/{acc_clean}/{xml_filename}"

    try:
        time.sleep(0.11)  # rate limit
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
    except Exception:
        return []

    transactions = []

    # Issuer ticker
    issuer_ticker = ''
    el = root.find('.//issuer/issuerTradingSymbol')
    if el is not None:
        issuer_ticker = (el.text or '').strip().upper()

    # Reporter (insider) info
    insider_name  = ''
    insider_title = ''
    reporter = root.find('.//reportingOwner')
    if reporter is not None:
        for tag, dest in [('.//rptOwnerName', 'name'), ('.//officerTitle', 'title')]:
            el = reporter.find(tag)
            if el is not None and el.text:
                if dest == 'name':
                    insider_name = el.text.strip()
                else:
                    insider_title = el.text.strip()
        if not insider_title:
            for role, tag in [('Director', './/isDirector'), ('10pct Owner', './/isTenPercentOwner')]:
                el = reporter.find(tag)
                if el is not None and (el.text or '').strip() == '1':
                    insider_title = role
                    break

    # Non-derivative (stock) transactions only
    for txn in root.findall('.//nonDerivativeTransaction'):
        try:
            # A=acquired (purchase), D=disposed (sale)
            code_el = txn.find('.//transactionAcquiredDisposedCode/value')
            if code_el is None or (code_el.text or '').strip() != 'A':
                continue

            date_el = txn.find('.//transactionDate/value')
            txn_date = (date_el.text or '').strip()[:10] if date_el is not None else ''

            shares_el = txn.find('.//transactionShares/value')
            shares = int(float(shares_el.text or 0)) if shares_el is not None else 0
            if shares <= 0:
                continue

            price_el = txn.find('.//transactionPricePerShare/value')
            price = float(price_el.text or 0) if price_el is not None else 0.0

            total_value = round(shares * price, 2)
            if total_value < MIN_PURCHASE_VALUE:
                continue

            owned_el = txn.find('.//sharesOwnedFollowingTransaction/value')
            owned_after = int(float(owned_el.text or 0)) if owned_el is not None else None

            transactions.append({
                'symbol':             issuer_ticker,
                'insider_name':       insider_name,
                'insider_title':      insider_title,
                'transaction_date':   txn_date,
                'transaction_type':   'purchase',
                'shares':             shares,
                'price_per_share':    round(price, 4),
                'total_value':        total_value,
                'shares_owned_after': owned_after,
            })
        except Exception:
            continue

    return transactions


def collect(start_date: str, end_date: str, universe: set, dry_run: bool = False) -> int:
    conn = sqlite3.connect(DB_PATH)
    _ensure_table(conn)

    print(f"  Searching Form 4 filings {start_date} → {end_date}...")
    filings = _search_form4(start_date, end_date)
    print(f"  Found {len(filings)} Form 4 filings total")

    saved = 0
    skipped = 0
    for filing in filings:
        acc = filing['accession_number']
        xml_file = filing['xml_filename']
        ciks = filing['ciks']

        if not xml_file or not ciks:
            continue

        # Skip if already collected
        exists = conn.execute(
            "SELECT id FROM insider_transactions WHERE accession_number = ?", (acc,)
        ).fetchone()
        if exists:
            skipped += 1
            continue

        # Filer CIK is index 0 (the insider), WITH leading zeros for URL
        cik = ciks[0]  # e.g. '0001400568'

        txns = _parse_form4_xml(cik, acc, xml_file)

        for txn in txns:
            sym = txn['symbol']
            if universe and sym not in universe:
                continue

            if dry_run:
                print(f"  [DRY] {sym} {txn['transaction_date']}: {txn['insider_name']} "
                      f"bought {txn['shares']:,} @ ${txn['price_per_share']:.2f} "
                      f"= ${txn['total_value']:,.0f}")
                saved += 1
                continue

            try:
                conn.execute('''
                    INSERT OR IGNORE INTO insider_transactions
                        (filing_date, transaction_date, symbol, cik, insider_name, insider_title,
                         transaction_type, shares, price_per_share, total_value,
                         shares_owned_after, accession_number, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ''', (
                    filing['filing_date'], txn['transaction_date'], sym, cik,
                    txn['insider_name'], txn['insider_title'], txn['transaction_type'],
                    txn['shares'], txn['price_per_share'], txn['total_value'],
                    txn['shares_owned_after'], acc,
                ))
                saved += 1
            except Exception as e:
                print(f"  DB error {sym}: {e}")

    if not dry_run:
        conn.commit()
    conn.close()
    print(f"  {'[DRY] ' if dry_run else ''}Saved {saved} purchases (skipped {skipped} already collected)")
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=2)
    parser.add_argument('--date', type=str)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] insider_collector")

    conn = sqlite3.connect(DB_PATH)
    universe = _get_universe_symbols(conn)
    conn.close()
    print(f"  Universe: {len(universe)} symbols")

    if args.date:
        start_date = end_date = args.date
    else:
        today = date.today()
        end_date   = today.strftime('%Y-%m-%d')
        start_date = (today - timedelta(days=args.days)).strftime('%Y-%m-%d')

    collect(start_date, end_date, universe, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
