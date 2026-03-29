#!/usr/bin/env python3
"""
collect_short_interest.py — v7.8
====================================
Collect short interest data for top universe symbols.
Stores in short_interest table — answers "squeeze potential?"

Data from yfinance Ticker.info:
  - short_pct_float    : % of float sold short (key metric)
  - short_ratio        : days to cover (volume / shares_short)
  - shares_short       : current short shares
  - shares_short_prior : prior period short shares (biweekly SEC report)
  - short_change_pct   : % change in short interest (trend)

Analysis enabled:
  - "Do high short% stocks bounce harder on DIP?" (squeeze candidate)
  - "Did short interest decrease before stock ripped?" (covering rally)
  - "Stocks with >10% short + catalyst = squeeze setup"
  - "Is short change_pct increasing? → bearish pressure building"

SEC reports biweekly → refresh weekly is sufficient.

Cron (TZ=America/New_York):
  0 18 * * 3  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_short_interest.py >> logs/collect_short_interest.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import os
import time
import argparse
from datetime import datetime, date, timedelta

import yfinance as yf
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')

DEFAULT_TOP_N = 500
DELAY_EVERY = 20
DELAY_SECS = 0.3


def fetch_short_interest(sym: str) -> dict | None:
    """Fetch short interest fields from yfinance Ticker.info."""
    try:
        info = yf.Ticker(sym).info
        if not info:
            return None

        short_pct = info.get('shortPercentOfFloat')
        short_ratio = info.get('shortRatio')
        shares_short = info.get('sharesShort')
        shares_short_prior = info.get('sharesShortPriorMonth')

        # At least one metric must be available
        if short_pct is None and shares_short is None:
            return None

        short_change_pct = None
        if shares_short and shares_short_prior and shares_short_prior > 0:
            short_change_pct = round((shares_short / shares_short_prior - 1) * 100, 2)

        return {
            'short_pct_float':    round(float(short_pct) * 100, 2) if short_pct is not None else None,
            'short_ratio':        round(float(short_ratio), 2) if short_ratio is not None else None,
            'shares_short':       int(shares_short) if shares_short else None,
            'shares_short_prior': int(shares_short_prior) if shares_short_prior else None,
            'short_change_pct':   short_change_pct,
        }
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description='Collect short interest for universe symbols')
    parser.add_argument('--date', default=None, help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--top', type=int, default=DEFAULT_TOP_N,
                        help=f'Top N symbols by dollar volume (default: {DEFAULT_TOP_N})')
    parser.add_argument('--symbol', default=None, help='Single symbol (for testing)')
    args = parser.parse_args()

    target_date = args.date or datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] collect_short_interest "
          f"date={target_date}")

    with get_session() as session:
        if args.symbol:
            symbols = [args.symbol.upper()]
        else:
            symbols = [r[0] for r in session.execute(text(
                "SELECT symbol FROM universe_stocks WHERE status='active' ORDER BY dollar_vol DESC LIMIT :n"
            ), {'n': args.top}).fetchall()]

        existing = set(r[0] for r in session.execute(text(
            "SELECT symbol FROM short_interest WHERE date = :d"
        ), {'d': target_date}).fetchall())

    symbols = [s for s in symbols if s not in existing]
    print(f"  {len(symbols)} symbols (skipping {len(existing)} already in DB)")

    if not symbols:
        print("  All symbols collected — done.")
        return

    ok = 0
    fail = 0

    for i, sym in enumerate(symbols):
        data = fetch_short_interest(sym)
        if data:
            with get_session() as session:
                session.execute(text("""
                    INSERT INTO short_interest
                        (symbol, date, short_pct_float, short_ratio,
                         shares_short, shares_short_prior, short_change_pct)
                    VALUES (:s,:d,:pf,:sr,:ss,:sp,:sc)
                    ON CONFLICT(symbol, date) DO UPDATE SET
                        short_pct_float    = excluded.short_pct_float,
                        short_ratio        = excluded.short_ratio,
                        shares_short       = excluded.shares_short,
                        shares_short_prior = excluded.shares_short_prior,
                        short_change_pct   = excluded.short_change_pct
                """), {'s': sym, 'd': target_date,
                       'pf': data['short_pct_float'], 'sr': data['short_ratio'],
                       'ss': data['shares_short'], 'sp': data['shares_short_prior'],
                       'sc': data['short_change_pct']})
            ok += 1
        else:
            fail += 1

        if (i + 1) % 50 == 0:
            pct = round((i + 1) / len(symbols) * 100)
            print(f"  [{i+1}/{len(symbols)} {pct}%] ok={ok} fail={fail}")

        if (i + 1) % DELAY_EVERY == 0:
            time.sleep(DELAY_SECS)
    print(f"\n  Done. ok={ok} fail={fail} date={target_date}")


if __name__ == '__main__':
    main()
