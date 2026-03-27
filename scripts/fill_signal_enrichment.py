#!/usr/bin/env python3
"""
fill_signal_enrichment.py — v7.8
===================================
Fill missing enrichment columns in signal_outcomes and screener_rejections.

Columns filled:
  signal_outcomes:
    timing                — BMO/AMC from earnings_history
    eps_surprise_pct      — actual vs estimate from earnings_history
    entry_time_et         — BUY timestamp from trades table (HH:MM ET)
    consecutive_down_days — count of consecutive daily closes below prev close
    sector_etf_1d_pct     — sector ETF pct_change on scan_date
    distance_from_200d_ma — (price / 200d MA - 1) × 100
    earnings_beat_streak  — consecutive beats from earnings_history
    sector_1d_change      — same as sector_etf_1d_pct (fills existing col if NULL)

  screener_rejections:
    consecutive_down_days
    sector_etf_1d_pct
    distance_from_200d_ma

Data sources:
  - earnings_history table (timing, eps_surprise_pct, earnings_beat_streak)
  - trades table (entry_time_et)
  - signal_candidate_bars (consecutive_down_days)
  - sector_etf_daily_returns + sector_cache (sector_etf_1d_pct)
  - signal_candidate_bars daily close (distance_from_200d_ma)

Cron (TZ=America/New_York):
  15 17 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_signal_enrichment.py >> logs/fill_signal_enrichment.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import os
import argparse
from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')

# Sector name → ETF mapping (match sector_cache values)
SECTOR_TO_ETF = {
    'technology':              'XLK',
    'financial services':      'XLF',
    'healthcare':              'XLV',
    'consumer cyclical':       'XLY',
    'consumer defensive':      'XLP',
    'energy':                  'XLE',
    'industrials':             'XLI',
    'basic materials':         'XLB',
    'real estate':             'XLRE',
    'utilities':               'XLU',
    'communication services':  'XLC',
    # common aliases
    'financials':              'XLF',
    'health care':             'XLV',
    'consumer staples':        'XLP',
    'consumer discretionary':  'XLY',
    'information technology':  'XLK',
    'materials':               'XLB',
    'telecom':                 'XLC',
    'communications':          'XLC',
}


def get_etf_for_sector(sector: str) -> str | None:
    if not sector:
        return None
    return SECTOR_TO_ETF.get(sector.strip().lower())


def fill_timing_and_eps(conn: object) -> int:
    """Fill timing (BMO/AMC) and eps_surprise_pct from earnings_history."""
    rows = conn.execute("""
        SELECT id, symbol, scan_date
        FROM signal_outcomes
        WHERE (eps_surprise_pct IS NULL)
          AND signal_source IN ('pem', 'ped', 'overnight_gap', 'dip_bounce')
    """).fetchall()

    updated = 0
    for r in rows:
        sym   = r['symbol']
        sdate = r['scan_date']

        # Find nearest earnings within ±5 days (PEM = earnings day ±1, PED = D-5)
        eh = conn.execute("""
            SELECT report_date, timing, eps_actual, eps_estimate, surprise_pct
            FROM earnings_history
            WHERE symbol = ?
              AND report_date BETWEEN date(?, '-5 days') AND date(?, '+2 days')
            ORDER BY ABS(julianday(report_date) - julianday(?))
            LIMIT 1
        """, (sym, sdate, sdate, sdate)).fetchone()

        if not eh:
            continue

        timing = eh['timing'] or None  # empty string → None
        eps_surprise = eh['surprise_pct']
        if eps_surprise is None:
            ea = eh['eps_actual']
            ee = eh['eps_estimate']
            if ea is not None and ee and float(ee) != 0:
                eps_surprise = round((float(ea) - float(ee)) / abs(float(ee)) * 100, 2)

        if timing is None and eps_surprise is None:
            continue

        conn.execute("""
            UPDATE signal_outcomes
            SET timing = COALESCE(timing, ?),
                eps_surprise_pct = COALESCE(eps_surprise_pct, ?)
            WHERE id = ?
        """, (timing, eps_surprise, r['id']))
        updated += 1
    return updated


def fill_entry_time(conn: object) -> int:
    """Fill entry_time_et from trades table (BUY timestamp)."""
    rows = conn.execute("""
        SELECT so.id, so.trade_id, t.timestamp
        FROM signal_outcomes so
        JOIN trades t ON t.id = so.trade_id AND t.action = 'BUY'
        WHERE so.entry_time_et IS NULL
          AND so.trade_id IS NOT NULL
    """).fetchall()

    updated = 0
    for r in rows:
        ts = r['timestamp']
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo:
                dt = dt.astimezone(ET)
            entry_time = dt.strftime('%H:%M')
        except Exception:
            try:
                entry_time = ts[11:16]
            except Exception:
                continue

        conn.execute("""
            UPDATE signal_outcomes SET entry_time_et = ? WHERE id = ?
        """, (entry_time, r['id']))
        updated += 1
    return updated


def get_daily_closes(conn: object, symbol: str,
                      before_date: str, n: int = 210) -> list[float]:
    """
    Get last N daily closing prices for symbol before before_date.
    Uses signal_candidate_bars: picks the last bar of each trading day (15:55-15:59).
    """
    rows = conn.execute("""
        SELECT date, close
        FROM signal_candidate_bars
        WHERE symbol = ? AND date < ?
          AND time_et BETWEEN '15:55' AND '15:59'
        ORDER BY date DESC, time_et DESC
        LIMIT ?
    """, (symbol, before_date, n)).fetchall()

    # Deduplicate (one per date) — most recent time_et per date already ordered
    seen_dates: set[str] = set()
    closes: list[float] = []
    for r in rows:
        d = r['date']
        if d not in seen_dates:
            seen_dates.add(d)
            v = r['close']
            if v and float(v) > 0:
                closes.append(float(v))
    return closes


def compute_consecutive_down_days(closes: list[float]) -> int | None:
    """Count consecutive daily closes below previous close (most recent first)."""
    if len(closes) < 2:
        return None
    count = 0
    for i in range(len(closes) - 1):
        if closes[i] < closes[i + 1]:
            count += 1
        else:
            break
    return count


def compute_distance_from_200d_ma(closes: list[float], scan_price: float) -> float | None:
    """Compute (price / 200d MA - 1) × 100."""
    if len(closes) < 100:
        return None
    ma200 = sum(closes[:min(200, len(closes))]) / min(200, len(closes))
    if ma200 <= 0:
        return None
    price = scan_price if scan_price and scan_price > 0 else (closes[0] if closes else 0)
    if not price:
        return None
    return round((price / ma200 - 1) * 100, 2)


def fill_consecutive_and_200d(conn: object, table: str,
                               date_filter: str | None = None) -> int:
    """Fill consecutive_down_days and distance_from_200d_ma for a table.
    NOTE: Requires signal_candidate_bars to have ≥20 trading days of history.
    This data accumulates over time — skip rows where bars are insufficient.
    """
    where = "WHERE (consecutive_down_days IS NULL OR distance_from_200d_ma IS NULL)"
    params: list = []
    if date_filter:
        where += " AND scan_date >= ?"
        params.append(date_filter)

    rows = conn.execute(f"""
        SELECT id, symbol, scan_date, scan_price
        FROM {table}
        {where}
        LIMIT 2000
    """, params).fetchall()

    # Check available bar dates
    available_dates = conn.execute(
        "SELECT COUNT(DISTINCT date) FROM signal_candidate_bars"
    ).fetchone()[0]

    if available_dates < 5:
        print(f"    ⚠️  Only {available_dates} bar-days in DB — skipping 200d/CDD (need ≥5)")
        return 0

    # Batch: group by symbol to reduce DB queries
    from collections import defaultdict
    sym_rows: dict[str, list] = defaultdict(list)
    for r in rows:
        sym_rows[r['symbol']].append(r)

    updated = 0
    for sym, sym_list in sym_rows.items():
        # Use the earliest scan_date for this symbol's rows as reference
        earliest_date = min(r['scan_date'] for r in sym_list)
        closes = get_daily_closes(conn, sym, earliest_date, n=210)

        if not closes:
            continue

        for r in sym_list:
            cdd = compute_consecutive_down_days(closes)
            d200 = compute_distance_from_200d_ma(closes, r['scan_price'] or 0)

            if cdd is None and d200 is None:
                continue

            conn.execute(f"""
                UPDATE {table}
                SET consecutive_down_days = COALESCE(consecutive_down_days, ?),
                    distance_from_200d_ma = COALESCE(distance_from_200d_ma, ?)
                WHERE id = ?
            """, (cdd, d200, r['id']))
            updated += 1
    return updated


def fill_sector_etf_1d(conn: object, table: str,
                        date_filter: str | None = None) -> int:
    """Fill sector_etf_1d_pct from sector_etf_daily_returns."""
    where = "WHERE sector_etf_1d_pct IS NULL AND sector IS NOT NULL"
    params = []
    if date_filter:
        where += " AND scan_date >= ?"
        params.append(date_filter)

    rows = conn.execute(f"""
        SELECT id, symbol, scan_date, sector
        FROM {table}
        {where}
    """, params).fetchall()

    # Cache ETF returns
    etf_cache: dict[tuple, float | None] = {}

    def get_etf_pct(etf: str, date: str) -> float | None:
        key = (etf, date)
        if key in etf_cache:
            return etf_cache[key]
        row = conn.execute("""
            SELECT pct_change FROM sector_etf_daily_returns
            WHERE etf = ? AND date = ?
        """, (etf, date)).fetchone()
        val = row['pct_change'] if row else None
        etf_cache[key] = val
        return val

    updated = 0
    for r in rows:
        etf = get_etf_for_sector(r['sector'])
        if not etf:
            # Try looking up sector from sector_cache
            sc = conn.execute(
                "SELECT sector FROM sector_cache WHERE symbol = ?", (r['symbol'],)
            ).fetchone()
            if sc and sc['sector']:
                etf = get_etf_for_sector(sc['sector'])

        if not etf:
            continue

        pct = get_etf_pct(etf, r['scan_date'])
        if pct is None:
            continue

        conn.execute(f"""
            UPDATE {table}
            SET sector_etf_1d_pct = ?
            WHERE id = ?
        """, (pct, r['id']))
        updated += 1

    # Also fill sector_1d_change in signal_outcomes (same data, different column name)
    if table == 'signal_outcomes':
        rows2 = conn.execute("""
            SELECT id, symbol, scan_date, sector
            FROM signal_outcomes
            WHERE sector_1d_change IS NULL AND sector IS NOT NULL
              AND sector_etf_1d_pct IS NOT NULL
        """).fetchall()
        for r in rows2:
            etf = get_etf_for_sector(r['sector'])
            if not etf:
                continue
            pct = get_etf_pct(etf, r['scan_date'])
            if pct is None:
                continue
            conn.execute("""
                UPDATE signal_outcomes SET sector_1d_change = ? WHERE id = ?
            """, (pct, r['id']))
    return updated


def fill_earnings_beat_streak(conn: object) -> int:
    """Fill earnings_beat_streak = consecutive EPS beats before scan_date."""
    rows = conn.execute("""
        SELECT id, symbol, scan_date
        FROM signal_outcomes
        WHERE earnings_beat_streak IS NULL
          AND signal_source IN ('pem', 'ped', 'overnight_gap', 'dip_bounce')
    """).fetchall()

    updated = 0
    for r in rows:
        # Get last 8 earnings before scan_date
        eh_rows = conn.execute("""
            SELECT report_date, eps_actual, eps_estimate
            FROM earnings_history
            WHERE symbol = ? AND report_date < ?
            ORDER BY report_date DESC
            LIMIT 8
        """, (r['symbol'], r['scan_date'])).fetchall()

        streak = 0
        for eh in eh_rows:
            ea = eh['eps_actual']
            ee = eh['eps_estimate']
            if ea is None or ee is None:
                break
            if float(ea) > float(ee):
                streak += 1
            else:
                break

        if streak == 0 and not eh_rows:
            continue  # No data — leave NULL

        conn.execute("""
            UPDATE signal_outcomes SET earnings_beat_streak = ? WHERE id = ?
        """, (streak, r['id']))
        updated += 1
    return updated


def main():
    parser = argparse.ArgumentParser(description='Fill signal enrichment columns')
    parser.add_argument('--date', default=None,
                        help='Only process rows with scan_date >= this date')
    parser.add_argument('--all', action='store_true',
                        help='Process all rows (no date filter)')
    parser.add_argument('--step', default=None,
                        choices=['timing', 'entry_time', 'consecutive', 'sector_etf',
                                 'beat_streak'],
                        help='Run only one step (for debugging)')
    args = parser.parse_args()

    today = datetime.now(ET).date().strftime('%Y-%m-%d')

    if args.all:
        date_filter = None
    elif args.date:
        date_filter = args.date
    else:
        # Default: last 30 days (plus backfill)
        date_filter = (datetime.now(ET).date() - timedelta(days=30)).strftime('%Y-%m-%d')

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] fill_signal_enrichment "
          f"date_filter={date_filter} step={args.step}")

    # conn via get_session()

    # Step 1: timing + eps_surprise_pct
    if args.step in (None, 'timing'):
        n = fill_timing_and_eps(conn)
        print(f"  Step 1 timing/eps_surprise: {n} updated")

    # Step 2: entry_time_et
    if args.step in (None, 'entry_time'):
        n = fill_entry_time(conn)
        print(f"  Step 2 entry_time_et: {n} updated")

    # Step 3: consecutive_down_days + distance_from_200d_ma
    if args.step in (None, 'consecutive'):
        n = fill_consecutive_and_200d(conn, 'signal_outcomes', date_filter)
        print(f"  Step 3a signal_outcomes consecutive/200d: {n} updated")
        n = fill_consecutive_and_200d(conn, 'screener_rejections', date_filter)
        print(f"  Step 3b screener_rejections consecutive/200d: {n} updated")

    # Step 4: sector_etf_1d_pct
    if args.step in (None, 'sector_etf'):
        n = fill_sector_etf_1d(conn, 'signal_outcomes', date_filter)
        print(f"  Step 4a signal_outcomes sector_etf_1d: {n} updated")
        n = fill_sector_etf_1d(conn, 'screener_rejections', date_filter)
        print(f"  Step 4b screener_rejections sector_etf_1d: {n} updated")

    # Step 5: earnings_beat_streak
    if args.step in (None, 'beat_streak'):
        n = fill_earnings_beat_streak(conn)
        print(f"  Step 5 earnings_beat_streak: {n} updated")
    print("  Done.")


if __name__ == '__main__':
    main()
