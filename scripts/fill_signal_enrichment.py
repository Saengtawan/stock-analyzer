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
    distance_from_200d_ma — (price / 200d MA - 1) x 100
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
import argparse
from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')

# Sector name -> ETF mapping (match sector_cache values)
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


def fill_timing_and_eps(session) -> int:
    """Fill timing (BMO/AMC) and eps_surprise_pct from earnings_history."""
    rows = session.execute(text("""
        SELECT id, symbol, scan_date
        FROM signal_outcomes
        WHERE (eps_surprise_pct IS NULL)
          AND signal_source IN ('pem', 'ped', 'overnight_gap', 'dip_bounce')
    """)).fetchall()

    updated = 0
    for r in rows:
        sym   = r[1]
        sdate = r[2]

        # Find nearest earnings within +/-5 days (PEM = earnings day +/-1, PED = D-5)
        eh = session.execute(text("""
            SELECT report_date, timing, eps_actual, eps_estimate, surprise_pct
            FROM earnings_history
            WHERE symbol = :p0
              AND report_date BETWEEN date(:p1, '-5 days') AND date(:p2, '+2 days')
            ORDER BY ABS(julianday(report_date) - julianday(:p3))
            LIMIT 1
        """), {'p0': sym, 'p1': sdate, 'p2': sdate, 'p3': sdate}).fetchone()

        if not eh:
            continue

        timing = eh[1] or None  # empty string -> None
        eps_surprise = eh[4]
        if eps_surprise is None:
            ea = eh[2]
            ee = eh[3]
            if ea is not None and ee and float(ee) != 0:
                eps_surprise = round((float(ea) - float(ee)) / abs(float(ee)) * 100, 2)

        if timing is None and eps_surprise is None:
            continue

        session.execute(text("""
            UPDATE signal_outcomes
            SET timing = COALESCE(timing, :p0),
                eps_surprise_pct = COALESCE(eps_surprise_pct, :p1)
            WHERE id = :p2
        """), {'p0': timing, 'p1': eps_surprise, 'p2': r[0]})
        updated += 1
    return updated


def fill_entry_time(session) -> int:
    """Fill entry_time_et from trades table (BUY timestamp)."""
    rows = session.execute(text("""
        SELECT so.id, so.trade_id, t.timestamp
        FROM signal_outcomes so
        JOIN trades t ON t.id = so.trade_id AND t.action = 'BUY'
        WHERE so.entry_time_et IS NULL
          AND so.trade_id IS NOT NULL
    """)).fetchall()

    updated = 0
    for r in rows:
        ts = r[2]
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

        session.execute(text("""
            UPDATE signal_outcomes SET entry_time_et = :p0 WHERE id = :p1
        """), {'p0': entry_time, 'p1': r[0]})
        updated += 1
    return updated


def get_daily_closes(session, symbol: str,
                      before_date: str, n: int = 210) -> list[float]:
    """
    Get last N daily closing prices for symbol before before_date.
    Uses signal_candidate_bars: picks the last bar of each trading day (15:55-15:59).
    """
    rows = session.execute(text("""
        SELECT date, close
        FROM signal_candidate_bars
        WHERE symbol = :p0 AND date < :p1
          AND time_et BETWEEN '15:55' AND '15:59'
        ORDER BY date DESC, time_et DESC
        LIMIT :p2
    """), {'p0': symbol, 'p1': before_date, 'p2': n}).fetchall()

    # Deduplicate (one per date) — most recent time_et per date already ordered
    seen_dates: set[str] = set()
    closes: list[float] = []
    for r in rows:
        d = r[0]
        if d not in seen_dates:
            seen_dates.add(d)
            v = r[1]
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
    """Compute (price / 200d MA - 1) x 100."""
    if len(closes) < 100:
        return None
    ma200 = sum(closes[:min(200, len(closes))]) / min(200, len(closes))
    if ma200 <= 0:
        return None
    price = scan_price if scan_price and scan_price > 0 else (closes[0] if closes else 0)
    if not price:
        return None
    return round((price / ma200 - 1) * 100, 2)


def fill_consecutive_and_200d(session, table: str,
                               date_filter: str | None = None) -> int:
    """Fill consecutive_down_days and distance_from_200d_ma for a table.
    NOTE: Requires signal_candidate_bars to have >=20 trading days of history.
    This data accumulates over time — skip rows where bars are insufficient.
    """
    where = "WHERE (consecutive_down_days IS NULL OR distance_from_200d_ma IS NULL)"
    params: dict = {}
    if date_filter:
        where += " AND scan_date >= :p0"
        params['p0'] = date_filter

    rows = session.execute(text(f"""
        SELECT id, symbol, scan_date, scan_price
        FROM {table}
        {where}
        LIMIT 2000
    """), params).fetchall()

    # Check available bar dates
    available_dates = session.execute(
        text("SELECT COUNT(DISTINCT date) FROM signal_candidate_bars")
    ).fetchone()[0]

    if available_dates < 5:
        print(f"    Only {available_dates} bar-days in DB — skipping 200d/CDD (need >=5)")
        return 0

    # Batch: group by symbol to reduce DB queries
    from collections import defaultdict
    sym_rows: dict[str, list] = defaultdict(list)
    for r in rows:
        sym_rows[r[1]].append(r)

    updated = 0
    for sym, sym_list in sym_rows.items():
        # Use the earliest scan_date for this symbol's rows as reference
        earliest_date = min(r[2] for r in sym_list)
        closes = get_daily_closes(session, sym, earliest_date, n=210)

        if not closes:
            continue

        for r in sym_list:
            cdd = compute_consecutive_down_days(closes)
            d200 = compute_distance_from_200d_ma(closes, r[3] or 0)

            if cdd is None and d200 is None:
                continue

            session.execute(text(f"""
                UPDATE {table}
                SET consecutive_down_days = COALESCE(consecutive_down_days, :p0),
                    distance_from_200d_ma = COALESCE(distance_from_200d_ma, :p1)
                WHERE id = :p2
            """), {'p0': cdd, 'p1': d200, 'p2': r[0]})
            updated += 1
    return updated


def fill_sector_etf_1d(session, table: str,
                        date_filter: str | None = None) -> int:
    """Fill sector_etf_1d_pct from sector_etf_daily_returns."""
    where = "WHERE sector_etf_1d_pct IS NULL AND sector IS NOT NULL"
    params: dict = {}
    if date_filter:
        where += " AND scan_date >= :p0"
        params['p0'] = date_filter

    rows = session.execute(text(f"""
        SELECT id, symbol, scan_date, sector
        FROM {table}
        {where}
    """), params).fetchall()

    # Cache ETF returns
    etf_cache: dict[tuple, float | None] = {}

    def get_etf_pct(etf: str, dt: str) -> float | None:
        key = (etf, dt)
        if key in etf_cache:
            return etf_cache[key]
        row = session.execute(text("""
            SELECT pct_change FROM sector_etf_daily_returns
            WHERE etf = :p0 AND date = :p1
        """), {'p0': etf, 'p1': dt}).fetchone()
        val = row[0] if row else None
        etf_cache[key] = val
        return val

    updated = 0
    for r in rows:
        etf = get_etf_for_sector(r[3])
        if not etf:
            # Try looking up sector from sector_cache
            sc = session.execute(
                text("SELECT sector FROM sector_cache WHERE symbol = :p0"), {'p0': r[1]}
            ).fetchone()
            if sc and sc[0]:
                etf = get_etf_for_sector(sc[0])

        if not etf:
            continue

        pct = get_etf_pct(etf, r[2])
        if pct is None:
            continue

        session.execute(text(f"""
            UPDATE {table}
            SET sector_etf_1d_pct = :p0
            WHERE id = :p1
        """), {'p0': pct, 'p1': r[0]})
        updated += 1

    # Also fill sector_1d_change in signal_outcomes (same data, different column name)
    if table == 'signal_outcomes':
        rows2 = session.execute(text("""
            SELECT id, symbol, scan_date, sector
            FROM signal_outcomes
            WHERE sector_1d_change IS NULL AND sector IS NOT NULL
              AND sector_etf_1d_pct IS NOT NULL
        """)).fetchall()
        for r in rows2:
            etf = get_etf_for_sector(r[3])
            if not etf:
                continue
            pct = get_etf_pct(etf, r[2])
            if pct is None:
                continue
            session.execute(text("""
                UPDATE signal_outcomes SET sector_1d_change = :p0 WHERE id = :p1
            """), {'p0': pct, 'p1': r[0]})
    return updated


def fill_earnings_beat_streak(session) -> int:
    """Fill earnings_beat_streak = consecutive EPS beats before scan_date."""
    rows = session.execute(text("""
        SELECT id, symbol, scan_date
        FROM signal_outcomes
        WHERE earnings_beat_streak IS NULL
          AND signal_source IN ('pem', 'ped', 'overnight_gap', 'dip_bounce')
    """)).fetchall()

    updated = 0
    for r in rows:
        # Get last 8 earnings before scan_date
        eh_rows = session.execute(text("""
            SELECT report_date, eps_actual, eps_estimate
            FROM earnings_history
            WHERE symbol = :p0 AND report_date < :p1
            ORDER BY report_date DESC
            LIMIT 8
        """), {'p0': r[1], 'p1': r[2]}).fetchall()

        streak = 0
        for eh in eh_rows:
            ea = eh[1]
            ee = eh[2]
            if ea is None or ee is None:
                break
            if float(ea) > float(ee):
                streak += 1
            else:
                break

        if streak == 0 and not eh_rows:
            continue  # No data — leave NULL

        session.execute(text("""
            UPDATE signal_outcomes SET earnings_beat_streak = :p0 WHERE id = :p1
        """), {'p0': streak, 'p1': r[0]})
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

    with get_session() as session:

        # Step 1: timing + eps_surprise_pct
        if args.step in (None, 'timing'):
            n = fill_timing_and_eps(session)
            print(f"  Step 1 timing/eps_surprise: {n} updated")

        # Step 2: entry_time_et
        if args.step in (None, 'entry_time'):
            n = fill_entry_time(session)
            print(f"  Step 2 entry_time_et: {n} updated")

        # Step 3: consecutive_down_days + distance_from_200d_ma
        if args.step in (None, 'consecutive'):
            n = fill_consecutive_and_200d(session, 'signal_outcomes', date_filter)
            print(f"  Step 3a signal_outcomes consecutive/200d: {n} updated")
            n = fill_consecutive_and_200d(session, 'screener_rejections', date_filter)
            print(f"  Step 3b screener_rejections consecutive/200d: {n} updated")

        # Step 4: sector_etf_1d_pct
        if args.step in (None, 'sector_etf'):
            n = fill_sector_etf_1d(session, 'signal_outcomes', date_filter)
            print(f"  Step 4a signal_outcomes sector_etf_1d: {n} updated")
            n = fill_sector_etf_1d(session, 'screener_rejections', date_filter)
            print(f"  Step 4b screener_rejections sector_etf_1d: {n} updated")

        # Step 5: earnings_beat_streak
        if args.step in (None, 'beat_streak'):
            n = fill_earnings_beat_streak(session)
            print(f"  Step 5 earnings_beat_streak: {n} updated")
        print("  Done.")


if __name__ == '__main__':
    main()
