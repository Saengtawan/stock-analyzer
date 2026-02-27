#!/usr/bin/env python3
"""
Earnings Dates Fetcher

Fetches next earnings date for all stocks in full_universe_cache.json
and stores in trade_history.db/earnings_calendar.

Run once manually to seed the DB, then the engine refreshes daily at 7 AM ET.

Usage:
    python3 src/batch/fetch_earnings_dates.py            # fetch all stale (default)
    python3 src/batch/fetch_earnings_dates.py --all      # force re-fetch all 987
    python3 src/batch/fetch_earnings_dates.py --symbol AAPL  # single symbol test
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from loguru import logger

try:
    import yfinance as yf
    import pandas as pd
    YF_OK = True
except ImportError:
    YF_OK = False

from database.repositories.earnings_calendar_repository import EarningsCalendarRepository

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
UNIVERSE_FILE = os.path.join(DATA_DIR, 'full_universe_cache.json')

MAX_WORKERS = 30          # Parallel yfinance calls
BATCH_COMMIT = 50         # Write to DB every N symbols
RATE_LIMIT_SLEEP = 0.05   # Seconds between thread submissions (avoid rate limit)


def load_universe() -> List[str]:
    with open(UNIVERSE_FILE) as f:
        return list(json.load(f).keys())


def fetch_next_earnings(symbol: str) -> tuple:
    """
    Fetch next earnings date for a symbol.
    Returns (symbol, date_str_or_None).
    """
    today = date.today()
    try:
        ticker = yf.Ticker(symbol)

        # Primary: earnings_dates (tz-aware DatetimeIndex, most reliable)
        ed = ticker.earnings_dates
        if ed is not None and not ed.empty:
            future = sorted([
                datetime.strptime(i.strftime('%Y-%m-%d'), '%Y-%m-%d').date()
                for i in ed.index
                if i.strftime('%Y-%m-%d') > today.strftime('%Y-%m-%d')
            ])
            if future:
                return symbol, future[0].isoformat()

        # Fallback: calendar
        cal = ticker.calendar
        if cal and isinstance(cal, dict):
            dates = cal.get('Earnings Date', [])
            if not isinstance(dates, (list, tuple)):
                dates = [dates]
            for d in dates:
                if hasattr(d, 'date'):
                    d = d.date()
                elif isinstance(d, str):
                    d = datetime.strptime(d[:10], '%Y-%m-%d').date()
                if d > today:
                    return symbol, d.isoformat()

        return symbol, None
    except Exception:
        return symbol, None


def run_fetch(symbols: List[str], label: str = '') -> Dict[str, Optional[str]]:
    """Parallel fetch for a list of symbols. Returns {symbol: date_str_or_None}."""
    results: Dict[str, Optional[str]] = {}
    total = len(symbols)
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_next_earnings, sym): sym for sym in symbols}
        for future in as_completed(futures):
            sym, dt = future.result()
            results[sym] = dt
            done += 1
            if done % 50 == 0 or done == total:
                pct = done / total * 100
                found = sum(1 for v in results.values() if v)
                logger.info(f"  {label}[{done}/{total}] {pct:.0f}% — upcoming earnings found: {found}")

    return results


def main():
    parser = argparse.ArgumentParser(description='Fetch earnings dates for full universe')
    parser.add_argument('--all', action='store_true', help='Force re-fetch all symbols (ignore staleness)')
    parser.add_argument('--symbol', type=str, help='Test single symbol')
    args = parser.parse_args()

    if not YF_OK:
        logger.error('yfinance not available')
        sys.exit(1)

    repo = EarningsCalendarRepository()

    # ── Single symbol test ───────────────────────────────────────────────────
    if args.symbol:
        sym = args.symbol.upper()
        logger.info(f'Fetching earnings for {sym}...')
        _, dt = fetch_next_earnings(sym)
        logger.info(f'  {sym}: next_earnings = {dt}')
        repo.upsert(sym, dt)
        days = repo.get_days_until(sym)
        logger.info(f'  {sym}: days_until = {days}')
        return

    # ── Load universe ────────────────────────────────────────────────────────
    try:
        universe = load_universe()
    except FileNotFoundError:
        logger.error(f'Universe file not found: {UNIVERSE_FILE}')
        sys.exit(1)

    logger.info(f'Universe: {len(universe)} symbols')

    # ── Determine which symbols to fetch ────────────────────────────────────
    if args.all:
        to_fetch = universe
        logger.info(f'--all flag: fetching all {len(to_fetch)} symbols')
    else:
        to_fetch = repo.get_stale_symbols(universe, max_age_hours=26.0)
        logger.info(f'Stale symbols (>26h or missing): {len(to_fetch)} / {len(universe)}')

    if not to_fetch:
        logger.info('All symbols up to date. Nothing to fetch.')
        return

    # ── Fetch ────────────────────────────────────────────────────────────────
    start = time.time()
    logger.info(f'Fetching {len(to_fetch)} symbols with {MAX_WORKERS} workers...')
    results = run_fetch(to_fetch, label='')

    # ── Save to DB ───────────────────────────────────────────────────────────
    written = repo.upsert_batch(results)
    elapsed = time.time() - start

    found = sum(1 for v in results.values() if v)
    logger.info(f'Done in {elapsed:.1f}s — {written} symbols saved, {found} with upcoming earnings')
    logger.info(f'DB total: {repo.count()} symbols')


if __name__ == '__main__':
    main()
