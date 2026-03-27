#!/usr/bin/env python3
"""
collect_options_flow.py — v7.8
================================
After market close: download options put/call data for top universe symbols.
Stores in options_flow table for use in backtesting and signal quality analysis.

Why options flow matters:
  - High put/call ratio → bearish sentiment → DIP signals less reliable
  - Unusual call activity → institutional accumulation → entry confirmation
  - Low put/call (<0.5) + high call volume → bullish momentum

Data collected per symbol (nearest expiry within 1-4 weeks):
  - call_volume, put_volume → put_call_ratio
  - call_oi (open interest), put_oi
  - unusual_call flag: call_volume > 3× call_oi
  - unusual_put flag: put_volume > 3× put_oi

Runs top 500 symbols by dollar volume (full 1000 takes too long for yfinance).

Cron (TZ=America/New_York):
  30 17 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_options_flow.py >> logs/collect_options_flow.log 2>&1
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

# Process top N symbols by dollar volume (options data less relevant for illiquid stocks)
DEFAULT_TOP_N = 500
# Delay between symbols to avoid rate limiting
DELAY_EVERY = 20
DELAY_SECS = 0.3


def _ensure_table(conn: object):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS options_flow (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            date        TEXT NOT NULL,
            call_volume INTEGER,
            put_volume  INTEGER,
            put_call_ratio REAL,
            call_oi     INTEGER,
            put_oi      INTEGER,
            unusual_call INTEGER DEFAULT 0,
            unusual_put  INTEGER DEFAULT 0,
            updated_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(symbol, date)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_options_flow_date ON options_flow(date)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_options_flow_symbol ON options_flow(symbol, date)
    """)


def fetch_options_for_symbol(sym: str) -> dict | None:
    """
    Fetch nearest-expiry options chain. Returns aggregated metrics or None on failure.
    Looks for expiry 7-35 days out (nearest standard weekly/monthly).
    """
    try:
        t = yf.Ticker(sym)
        expirations = t.options
        if not expirations:
            return None

        # Find first expiry 7-35 days out
        today = date.today()
        target_expiry = None
        for exp in expirations:
            try:
                exp_dt = datetime.strptime(exp, '%Y-%m-%d').date()
                days_out = (exp_dt - today).days
                if 7 <= days_out <= 35:
                    target_expiry = exp
                    break
            except Exception:
                continue

        # Fallback: use nearest expiry that's in the future
        if not target_expiry:
            for exp in expirations:
                try:
                    exp_dt = datetime.strptime(exp, '%Y-%m-%d').date()
                    if exp_dt >= today:
                        target_expiry = exp
                        break
                except Exception:
                    continue

        if not target_expiry:
            return None

        chain = t.option_chain(target_expiry)
        calls = chain.calls
        puts = chain.puts

        if calls is None or puts is None or calls.empty or puts.empty:
            return None

        call_vol = int(calls['volume'].fillna(0).sum())
        put_vol  = int(puts['volume'].fillna(0).sum())
        call_oi  = int(calls['openInterest'].fillna(0).sum())
        put_oi   = int(puts['openInterest'].fillna(0).sum())

        # put/call ratio — avoid division by zero
        put_call_ratio = None
        if call_vol > 0:
            put_call_ratio = round(put_vol / call_vol, 3)

        # Unusual activity: volume > 3x open_interest (institutional signal)
        unusual_call = 1 if (call_oi > 0 and call_vol > 3 * call_oi) else 0
        unusual_put  = 1 if (put_oi > 0 and put_vol > 3 * put_oi) else 0

        return {
            'call_volume':    call_vol,
            'put_volume':     put_vol,
            'put_call_ratio': put_call_ratio,
            'call_oi':        call_oi,
            'put_oi':         put_oi,
            'unusual_call':   unusual_call,
            'unusual_put':    unusual_put,
        }

    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description='Collect options put/call data for universe symbols')
    parser.add_argument('--date', default=None, help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--top', type=int, default=DEFAULT_TOP_N,
                        help=f'Top N symbols by dollar volume (default: {DEFAULT_TOP_N})')
    parser.add_argument('--symbol', default=None, help='Single symbol (for testing)')
    args = parser.parse_args()

    target_date = args.date or datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] collect_options_flow "
          f"date={target_date}")

    # conn via get_session()
    _ensure_table(conn)

    if args.symbol:
        symbols = [args.symbol.upper()]
    else:
        # Get top N by dollar volume
        symbols = [r[0] for r in conn.execute("""
            SELECT symbol FROM universe_stocks
            WHERE status='active'
            ORDER BY dollar_vol DESC
            LIMIT ?
        """, (args.top,)).fetchall()]

    # Skip symbols already fetched today
    existing = set(r[0] for r in conn.execute(
        "SELECT symbol FROM options_flow WHERE date = ?", (target_date,)
    ).fetchall())
    symbols = [s for s in symbols if s not in existing]

    print(f"  {len(symbols)} symbols to fetch (skipping {len(existing)} already in DB)")

    if not symbols:
        print("  All symbols already collected — done.")
        return

    total_ok = 0
    total_fail = 0

    for i, sym in enumerate(symbols):
        data = fetch_options_for_symbol(sym)
        if data:
            conn.execute("""
                INSERT INTO options_flow
                    (symbol, date, call_volume, put_volume, put_call_ratio,
                     call_oi, put_oi, unusual_call, unusual_put)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    call_volume    = excluded.call_volume,
                    put_volume     = excluded.put_volume,
                    put_call_ratio = excluded.put_call_ratio,
                    call_oi        = excluded.call_oi,
                    put_oi         = excluded.put_oi,
                    unusual_call   = excluded.unusual_call,
                    unusual_put    = excluded.unusual_put,
                    updated_at     = datetime('now')
            """, (sym, target_date,
                  data['call_volume'], data['put_volume'], data['put_call_ratio'],
                  data['call_oi'], data['put_oi'], data['unusual_call'], data['unusual_put']))
            total_ok += 1
        else:
            total_fail += 1

        if (i + 1) % 50 == 0:
            pct = round((i + 1) / len(symbols) * 100)
            print(f"  [{i+1}/{len(symbols)} {pct}%] ok={total_ok} fail={total_fail}")

        if (i + 1) % DELAY_EVERY == 0:
            time.sleep(DELAY_SECS)
    print(f"\n  Done. ok={total_ok} fail={total_fail} date={target_date}")


if __name__ == '__main__':
    main()
