#!/usr/bin/env python3
"""
collect_candidate_bars.py — v7.7
===================================
After market close: download 1-minute OHLCV bars for ALL signal candidates today.
Includes pre-market (4:00 AM) and post-market (up to 8:00 PM) bars.
Stores in signal_candidate_bars table for use in backtesting simulation.

"Signal candidates" = all unique symbols in:
  - screener_rejections (scan_date = today)  — all screener-evaluated stocks
  - signal_outcomes (scan_date = today)      — all engine-evaluated signals

Why 1m bars (including pre-market)?
  - GAP strategy runs 6:00-9:32 AM ET — needs pre-market price to compute gap %
  - Simulate limit order fill: "would scan_price + 0.5% have filled in the next 30 min?"
  - Simulate SL hit: "did price touch SL level intraday (Day 0/1/2)?"
  - Compute MFE/MAE: best and worst price during hold period
  - Simulate trailing stop: when did trailing level lock?

Storage estimate:
  ~1000 unique candidates/day × 960 bars/day (4AM-8PM) = 960K rows/day
  At ~40 bytes/row = ~38 MB/day = ~9.6 GB/year (manageable with periodic cleanup)

Cron (TZ=America/New_York):
  35 16 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_candidate_bars.py >> logs/collect_candidate_bars.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import os
import sys
import time
from datetime import datetime, date, timedelta
import argparse

import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')

# Max symbols per yfinance batch (avoid throttling)
BATCH_SIZE = 50


def get_candidate_symbols(conn: object, target_date: str) -> list[str]:
    """Get all unique symbols evaluated by screeners on target_date."""
    sr = conn.execute("""
        SELECT DISTINCT symbol FROM screener_rejections
        WHERE scan_date = ? AND symbol IS NOT NULL
    """, (target_date,)).fetchall()

    so = conn.execute("""
        SELECT DISTINCT symbol FROM signal_outcomes
        WHERE scan_date = ? AND symbol IS NOT NULL
    """, (target_date,)).fetchall()

    symbols = list(set([r[0] for r in sr] + [r[0] for r in so]))
    return symbols


def download_1m_bars(symbol: str, target_date: str) -> pd.DataFrame | None:
    """Download 1m bars for a specific date. Returns None on failure."""
    try:
        end_dt = (datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        df = yf.download(symbol, start=target_date, end=end_dt,
                         interval='1m', auto_adjust=True, progress=False,
                         prepost=True)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


def download_1m_bars_batch(symbols: list[str], target_date: str) -> dict[str, pd.DataFrame]:
    """Download 1m bars for multiple symbols at once. More efficient than one-by-one."""
    result = {}
    if not symbols:
        return result
    try:
        end_dt = (datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        df = yf.download(symbols, start=target_date, end=end_dt,
                         interval='1m', auto_adjust=True, progress=False,
                         prepost=True, group_by='ticker')
        if df is None or df.empty:
            return result

        if len(symbols) == 1:
            sym = symbols[0]
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                result[sym] = df
        else:
            for sym in symbols:
                try:
                    sym_df = df[sym].dropna(how='all')
                    if not sym_df.empty:
                        result[sym] = sym_df
                except Exception:
                    pass
    except Exception as e:
        print(f"    Batch download error: {e}")
    return result


def bars_to_rows(sym: str, target_date: str, df: pd.DataFrame) -> list[tuple]:
    """Convert DataFrame to list of DB rows."""
    rows = []
    try:
        # Convert index to ET timezone
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize('UTC').tz_convert(ET)
        else:
            df.index = df.index.tz_convert(ET)

        for ts, bar in df.iterrows():
            # Only keep bars from today (filter pre/post market if needed)
            if ts.strftime('%Y-%m-%d') != target_date:
                continue
            time_et = ts.strftime('%H:%M')
            try:
                rows.append((
                    target_date, sym, time_et,
                    round(float(bar['Open']), 4),
                    round(float(bar['High']), 4),
                    round(float(bar['Low']), 4),
                    round(float(bar['Close']), 4),
                    int(bar['Volume']),
                ))
            except Exception:
                continue
    except Exception as e:
        pass
    return rows


def main():
    parser = argparse.ArgumentParser(description='Collect 1m bars for signal candidates')
    parser.add_argument('--date', default=None,
                        help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--days', type=int, default=1,
                        help='Number of past days to collect (default: 1 = today only)')
    args = parser.parse_args()

    target_date = args.date or datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] collect_candidate_bars "
          f"date={target_date} days={args.days}")

    # conn via get_session()

    base_dt = datetime.strptime(target_date, '%Y-%m-%d')
    dates_to_collect = [
        (base_dt - timedelta(days=i)).strftime('%Y-%m-%d')
        for i in range(args.days)
        if (base_dt - timedelta(days=i)).weekday() < 5  # weekdays only
    ]

    total_rows = 0

    for fill_date in dates_to_collect:
        print(f"\n  --- {fill_date} ---")

        # Check how many symbols already have bars for this date
        existing_syms = set(r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM signal_candidate_bars WHERE date = ?",
            (fill_date,)
        ).fetchall())

        symbols = get_candidate_symbols(conn, fill_date)
        new_symbols = [s for s in symbols if s not in existing_syms]

        print(f"    Candidates: {len(symbols)} total, {len(new_symbols)} new (not yet in DB)")

        if not new_symbols:
            print(f"    All symbols already have bars — skipping")
            continue

        # Process in batches
        date_rows = 0
        fetched_syms = 0
        for i in range(0, len(new_symbols), BATCH_SIZE):
            batch = new_symbols[i:i+BATCH_SIZE]
            bars_map = download_1m_bars_batch(batch, fill_date)

            batch_db_rows = []
            for sym, df in bars_map.items():
                rows = bars_to_rows(sym, fill_date, df)
                batch_db_rows.extend(rows)
                if rows:
                    fetched_syms += 1

            if batch_db_rows:
                conn.executemany("""
                    INSERT OR IGNORE INTO signal_candidate_bars
                        (date, symbol, time_et, open, high, low, close, volume)
                    VALUES (?,?,?,?,?,?,?,?)
                """, batch_db_rows)
                date_rows += len(batch_db_rows)

            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(new_symbols) + BATCH_SIZE - 1) // BATCH_SIZE
            print(f"    [{batch_num}/{total_batches}] fetched {fetched_syms} symbols so far, {date_rows} bars")

            # Small delay to avoid rate limiting
            if i + BATCH_SIZE < len(new_symbols):
                time.sleep(0.5)

        total_rows += date_rows
        print(f"    Saved {date_rows} bars for {fetched_syms}/{len(new_symbols)} symbols")
    print(f"\n  Total bars saved: {total_rows}")
    print(f"  Done.")


if __name__ == '__main__':
    main()
