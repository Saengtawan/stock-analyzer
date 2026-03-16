#!/usr/bin/env python3
"""
collect_stock_fundamentals.py — v7.8
=======================================
Collect per-symbol fundamental data: P/E, beta, float, market cap.
Stores in stock_fundamentals table (one row per symbol, updated weekly).

Data from yfinance Ticker.info:
  - pe_trailing    : trailing 12m P/E ratio
  - pe_forward     : forward P/E (analyst consensus estimate)
  - beta           : 5-year monthly beta vs SPX
  - float_shares   : shares available for trading (excludes insiders)
  - shares_out     : total shares outstanding
  - market_cap     : total market cap ($)
  - avg_volume     : 10-day average daily volume
  - sector         : sector name
  - industry       : sub-industry name

Analysis enabled:
  - "Do high-beta stocks have worse DIP win rate in bear markets?"
  - "Do low P/E stocks hold better after DIP entry?"
  - "Small float (<50M shares) → higher volatility, wider SL needed"
  - "Market cap tier affects ATR — micro cap vs large cap SL sizing"
  - "Industry peers: if AAPL dips, do other tech dip too?"

Weekly refresh (fundamentals don't change daily).

Cron (TZ=America/New_York):
  0 8 * * 0  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_stock_fundamentals.py >> logs/collect_stock_fundamentals.log 2>&1
"""
import os
import sqlite3
import time
import argparse
from datetime import datetime

import yfinance as yf
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
ET = ZoneInfo('America/New_York')

DELAY_EVERY = 20
DELAY_SECS = 0.3


def fetch_fundamentals(sym: str) -> dict | None:
    """Fetch fundamental fields from yfinance Ticker.info."""
    try:
        info = yf.Ticker(sym).info
        if not info or 'symbol' not in info and 'shortName' not in info:
            return None

        pe_trailing = info.get('trailingPE')
        pe_forward  = info.get('forwardPE')
        beta        = info.get('beta')
        float_sh    = info.get('floatShares')
        shares_out  = info.get('sharesOutstanding')
        market_cap  = info.get('marketCap')
        avg_vol     = info.get('averageVolume10days') or info.get('averageVolume')
        sector      = info.get('sector')
        industry    = info.get('industry')

        # Must have at least beta or market_cap to be useful
        if beta is None and market_cap is None:
            return None

        return {
            'pe_trailing':  round(float(pe_trailing), 2) if pe_trailing and pe_trailing < 10000 else None,
            'pe_forward':   round(float(pe_forward), 2) if pe_forward and pe_forward < 10000 else None,
            'beta':         round(float(beta), 3) if beta is not None else None,
            'float_shares': int(float_sh) if float_sh else None,
            'shares_out':   int(shares_out) if shares_out else None,
            'market_cap':   int(market_cap) if market_cap else None,
            'avg_volume':   int(avg_vol) if avg_vol else None,
            'sector':       sector[:100] if sector else None,
            'industry':     industry[:100] if industry else None,
        }
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description='Collect stock fundamental data')
    parser.add_argument('--force', action='store_true',
                        help='Re-fetch all symbols (ignore 7-day freshness check)')
    parser.add_argument('--symbol', default=None, help='Single symbol (for testing)')
    parser.add_argument('--limit', type=int, default=0, help='Limit symbols for testing')
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] collect_stock_fundamentals "
          f"force={args.force}")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    if args.symbol:
        symbols = [args.symbol.upper()]
    else:
        symbols = [r[0] for r in conn.execute(
            "SELECT symbol FROM universe_stocks WHERE status='active' ORDER BY dollar_vol DESC"
        ).fetchall()]

    if not args.force:
        # Skip symbols refreshed in last 7 days
        fresh = set(r[0] for r in conn.execute("""
            SELECT symbol FROM stock_fundamentals
            WHERE updated_at >= datetime('now', '-7 days')
        """).fetchall())
        symbols = [s for s in symbols if s not in fresh]
        print(f"  {len(symbols)} stale symbols (skipping {len(fresh)} fresh)")
    else:
        print(f"  Force mode: {len(symbols)} symbols")

    if args.limit > 0:
        symbols = symbols[:args.limit]
        print(f"  (limited to {args.limit})")

    if not symbols:
        print("  All symbols fresh — done.")
        conn.close()
        return

    ok = 0
    fail = 0

    for i, sym in enumerate(symbols):
        data = fetch_fundamentals(sym)
        if data:
            conn.execute("""
                INSERT INTO stock_fundamentals
                    (symbol, pe_trailing, pe_forward, beta, float_shares,
                     shares_out, market_cap, avg_volume, sector, industry)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol) DO UPDATE SET
                    pe_trailing  = excluded.pe_trailing,
                    pe_forward   = excluded.pe_forward,
                    beta         = excluded.beta,
                    float_shares = excluded.float_shares,
                    shares_out   = excluded.shares_out,
                    market_cap   = excluded.market_cap,
                    avg_volume   = excluded.avg_volume,
                    sector       = COALESCE(excluded.sector, sector),
                    industry     = COALESCE(excluded.industry, industry),
                    updated_at   = datetime('now')
            """, (sym, data['pe_trailing'], data['pe_forward'], data['beta'],
                  data['float_shares'], data['shares_out'], data['market_cap'],
                  data['avg_volume'], data['sector'], data['industry']))
            ok += 1
        else:
            fail += 1

        if (i + 1) % 100 == 0:
            conn.commit()
            pct = round((i + 1) / len(symbols) * 100)
            print(f"  [{i+1}/{len(symbols)} {pct}%] ok={ok} fail={fail}")

        if (i + 1) % DELAY_EVERY == 0:
            time.sleep(DELAY_SECS)

    conn.commit()
    conn.close()
    print(f"\n  Done. ok={ok} fail={fail}")


if __name__ == '__main__':
    main()
