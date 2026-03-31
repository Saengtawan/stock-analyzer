#!/usr/bin/env python3
"""
fill_first_30min.py — v7.6
===========================
Fill first_30min_return for signal_outcomes + screener_rejections.

first_30min_return = (price_at_10:00 ET / price_at_open_9:30 ET - 1) x 100

Runs at 10:05 AM ET — just after 10:00 so 30min bar is available.
Uses yfinance 2-min bars to find closest price to 9:30 and 10:00.

Supports --date YYYY-MM-DD for backfill of historical dates.

Cron (TZ=America/New_York):
  5 10 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_first_30min.py >> logs/fill_first_30min.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import os
import sys
import argparse
from datetime import datetime, date, timedelta

import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')


def _get_price_at(df: pd.DataFrame, target_hour: int, target_min: int) -> float | None:
    """Get price from 2-min bar closest to target time (ET)."""
    if df is None or df.empty:
        return None
    for col in ['Close', 'close']:
        if col in df.columns:
            close_col = df[col]
            break
    else:
        return None

    # Find bar at or just after target time
    target = df.index.tz_convert(ET) if df.index.tzinfo else df.index
    for i, ts in enumerate(target):
        if ts.hour > target_hour or (ts.hour == target_hour and ts.minute >= target_min):
            val = close_col.iloc[i]
            return float(val.iloc[0]) if hasattr(val, 'iloc') else float(val)
    return None


def _calc_30min(symbol: str, target_date: str | None = None) -> float | None:
    """Download 2-min bars for target_date (or today), return first_30min_return or None."""
    try:
        if target_date and target_date != date.today().strftime('%Y-%m-%d'):
            # Historical date: use start/end
            end_dt = datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=1)
            df = yf.download(symbol, start=target_date, end=end_dt.strftime('%Y-%m-%d'),
                             interval='2m', progress=False, auto_adjust=True)
        else:
            df = yf.download(symbol, period='1d', interval='2m',
                             progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        price_930 = _get_price_at(df, 9, 30)
        price_1000 = _get_price_at(df, 10, 0)

        if price_930 and price_1000 and price_930 > 0:
            return round((price_1000 / price_930 - 1) * 100, 3)
        return None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description='Fill first_30min_return')
    parser.add_argument('--date', default=None,
                        help='Target date YYYY-MM-DD (default: today)')
    args = parser.parse_args()

    today = args.date or date.today().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] fill_first_30min date={today}")

    with get_session() as session:
        # Collect symbols needing fill from signal_outcomes
        so_rows = session.execute(text("""
            SELECT id, symbol FROM signal_outcomes
            WHERE scan_date = :p0 AND first_30min_return IS NULL
              AND scan_price > 0
        """), {"p0": today}).fetchall()

        # Collect symbols needing fill from screener_rejections
        sr_rows = session.execute(text("""
            SELECT id, symbol FROM screener_rejections
            WHERE scan_date = :p0 AND first_30min_return IS NULL
              AND scan_price > 0
        """), {"p0": today}).fetchall()
        target_date = today

        all_symbols = list(set(
            [r[1] for r in so_rows] +
            [r[1] for r in sr_rows]
        ))

        if not all_symbols:
            print("  Nothing to fill today.")
            return

        print(f"  signal_outcomes: {len(so_rows)} rows | screener_rejections: {len(sr_rows)} rows")
        print(f"  Unique symbols: {len(all_symbols)}")

        # Fetch 30min return per symbol (deduplicated)
        cache: dict[str, float | None] = {}
        for i, sym in enumerate(all_symbols):
            pct = _calc_30min(sym, target_date)
            cache[sym] = pct
            if i % 20 == 0 and i > 0:
                print(f"  [{i}/{len(all_symbols)}] fetched so far...")

        # Update signal_outcomes
        so_updated = 0
        for row in so_rows:
            pct = cache.get(row[1])
            if pct is not None:
                session.execute(
                    text("UPDATE signal_outcomes SET first_30min_return = :p0 WHERE id = :p1"),
                    {"p0": pct, "p1": row[0]}
                )
                so_updated += 1

        # Update screener_rejections
        sr_updated = 0
        for row in sr_rows:
            pct = cache.get(row[1])
            if pct is not None:
                session.execute(
                    text("UPDATE screener_rejections SET first_30min_return = :p0 WHERE id = :p1"),
                    {"p0": pct, "p1": row[0]}
                )
                sr_updated += 1

    filled = sum(1 for v in cache.values() if v is not None)
    print(f"  Fetched {filled}/{len(all_symbols)} symbols with data")
    print(f"  Updated: signal_outcomes={so_updated} screener_rejections={sr_updated}")
    print(f"  Done.")


if __name__ == '__main__':
    main()
