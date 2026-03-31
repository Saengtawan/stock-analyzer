#!/usr/bin/env python3
"""
collect_earnings_calendar.py — v7.7
=====================================
Collect full earnings history for all universe symbols.
Stores in earnings_history table for backtest simulation.

Different from earnings_calendar table (which only keeps "next date" for live engine).
This table keeps ALL known dates (historical + upcoming) for simulation replay:

  - DIP: skip if days_until_earnings in [6..11]
  - PED: buy exactly D-5 before earnings
  - OVN: no D=0 earnings filter
  - PEM: earnings gap ≥ 8% (morning after BMO or AMC earnings)
  - GAP: earnings D≤1 → skip (PEM handles it)

For simulation date X, query:
  SELECT MIN(report_date) FROM earnings_history
  WHERE symbol=? AND report_date >= ?
  → gives "next earnings from date X" → compute days_until_earnings

Run modes:
  --backfill   : download full history (~8 quarters) for all symbols (run once)
  default      : update only stale symbols (not refreshed in last 7 days)

Cron (TZ=America/New_York):
  0 21 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_earnings_calendar.py >> logs/collect_earnings_calendar.log 2>&1
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
import pandas as pd
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS earnings_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT NOT NULL,
    report_date  TEXT NOT NULL,   -- YYYY-MM-DD (date earnings were/will be reported)
    timing       TEXT,            -- 'BMO' (before market open) | 'AMC' (after close) | NULL
    eps_estimate REAL,            -- analyst consensus estimate
    eps_actual   REAL,            -- actual reported EPS (NULL if future)
    surprise_pct REAL,            -- (actual-estimate)/|estimate|*100
    updated_date TEXT NOT NULL,   -- YYYY-MM-DD when we last fetched
    created_at   TEXT,
    UNIQUE(symbol, report_date)
)
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_earnings_history_sym_date
ON earnings_history(symbol, report_date)
"""


def _ensure_table(session: object):
    session.execute(text(CREATE_TABLE))
    session.execute(text(CREATE_INDEX))


def fetch_earnings_for_symbol(sym: str) -> list[dict]:
    """
    Fetch earnings dates from yfinance.
    Returns list of dicts with: report_date, timing, eps_estimate, eps_actual, surprise_pct
    """
    try:
        t = yf.Ticker(sym)
        df = t.earnings_dates  # DataFrame: index=datetime, cols=[EPS Estimate, Reported EPS, Surprise(%)]
        if df is None or df.empty:
            return []

        results = []
        for idx, row in df.iterrows():
            try:
                report_date = pd.Timestamp(idx).strftime('%Y-%m-%d')

                eps_estimate = None
                eps_actual = None
                surprise_pct = None

                if 'EPS Estimate' in df.columns:
                    v = row['EPS Estimate']
                    eps_estimate = float(v) if pd.notna(v) else None

                if 'Reported EPS' in df.columns:
                    v = row['Reported EPS']
                    eps_actual = float(v) if pd.notna(v) else None

                if 'Surprise(%)' in df.columns:
                    v = row['Surprise(%)']
                    surprise_pct = float(v) if pd.notna(v) else None

                results.append({
                    'report_date': report_date,
                    'timing': None,   # yfinance earnings_dates doesn't provide BMO/AMC
                    'eps_estimate': eps_estimate,
                    'eps_actual': eps_actual,
                    'surprise_pct': surprise_pct,
                })
            except Exception:
                continue

        return results

    except Exception:
        return []


def upsert_earnings(session: object, sym: str,
                    entries: list[dict], today: str) -> tuple[int, int]:
    """Insert/update earnings rows. Returns (inserted, updated)."""
    inserted = updated = 0
    for e in entries:
        try:
            session.execute(text("""
                INSERT INTO earnings_history
                    (symbol, report_date, timing, eps_estimate, eps_actual, surprise_pct, updated_date)
                VALUES (:p0, :p1, :p2, :p3, :p4, :p5, :p6)
                ON CONFLICT(symbol, report_date) DO UPDATE SET
                    timing       = COALESCE(excluded.timing, timing),
                    eps_estimate = COALESCE(excluded.eps_estimate, eps_estimate),
                    eps_actual   = COALESCE(excluded.eps_actual, eps_actual),
                    surprise_pct = COALESCE(excluded.surprise_pct, surprise_pct),
                    updated_date = excluded.updated_date
            """), {"p0": sym, "p1": e['report_date'], "p2": e['timing'],
                   "p3": e['eps_estimate'], "p4": e['eps_actual'],
                   "p5": e['surprise_pct'], "p6": today})
            inserted += 1
        except Exception:
            pass
    return inserted, updated


def get_stale_symbols(session: object, all_symbols: list[str],
                      max_age_days: int = 7) -> list[str]:
    """Return symbols not updated in last max_age_days or never fetched."""
    cutoff = (date.today() - timedelta(days=max_age_days)).strftime('%Y-%m-%d')
    fresh = set(r[0] for r in session.execute(text("""
        SELECT DISTINCT symbol FROM earnings_history
        WHERE updated_date >= :p0
    """), {"p0": cutoff}).fetchall())
    return [s for s in all_symbols if s not in fresh]


def main():
    parser = argparse.ArgumentParser(description='Collect earnings history for universe symbols')
    parser.add_argument('--backfill', action='store_true',
                        help='Force re-fetch all symbols (ignores stale check)')
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit symbols for testing (0=all)')
    args = parser.parse_args()

    today = datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] collect_earnings_calendar "
          f"date={today} backfill={args.backfill}")

    with get_session() as session:
        _ensure_table(session)

        # Get all active universe symbols
        all_symbols = [r[0] for r in session.execute(
            text("SELECT symbol FROM universe_stocks WHERE status='active' ORDER BY dollar_vol DESC")
        ).fetchall()]

        if args.backfill:
            symbols = all_symbols
            print(f"  Backfill mode: {len(symbols)} symbols")
        else:
            symbols = get_stale_symbols(session, all_symbols, max_age_days=7)
            print(f"  Incremental: {len(symbols)}/{len(all_symbols)} symbols need refresh")

        if args.limit > 0:
            symbols = symbols[:args.limit]
            print(f"  (limited to {len(symbols)})")

        if not symbols:
            print("  All symbols up to date — nothing to fetch")
            return

        total_inserted = 0
        total_failed = 0

        for i, sym in enumerate(symbols):
            entries = fetch_earnings_for_symbol(sym)
            if entries:
                ins, _ = upsert_earnings(session, sym, entries, today)
                total_inserted += ins
            else:
                total_failed += 1

            if (i + 1) % 100 == 0:
                pct = round((i + 1) / len(symbols) * 100)
                print(f"  [{i+1}/{len(symbols)} {pct}%] inserted={total_inserted} failed={total_failed}")

            # Rate limit: 10 symbols/sec
            if (i + 1) % 10 == 0:
                time.sleep(0.2)

    # Summary (separate session)
    with get_session() as session:
        total_rows = session.execute(text("SELECT COUNT(*) FROM earnings_history")).fetchone()[0]
        total_syms = session.execute(text("SELECT COUNT(DISTINCT symbol) FROM earnings_history")).fetchone()[0]
        date_range = session.execute(
            text("SELECT MIN(report_date), MAX(report_date) FROM earnings_history")
        ).fetchone()

    print(f"\n  Done. inserted={total_inserted} failed={total_failed}")
    print(f"  DB: {total_rows} rows across {total_syms} symbols "
          f"({date_range[0]} → {date_range[1]})")


if __name__ == '__main__':
    main()
