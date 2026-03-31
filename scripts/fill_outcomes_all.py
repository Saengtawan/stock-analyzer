#!/usr/bin/env python3
"""
fill_outcomes_all.py — v7.5
===========================
Fill outcome_1d..5d + max_gain/dd for signal_outcomes rows where outcome_1d IS NULL.

Covers: QUEUE_FULL, SKIPPED_FILTER, BOUGHT (all counterfactual + executed signals).

Outcomes relative to scan_price (signal price at scan time):
  outcome_Nd = (close_on_D+N / scan_price - 1) * 100

Run: daily at 05:00 ET Tuesday-Saturday (TZ=America/New_York in crontab — auto-handles DST)
  0 5 * * 2-6  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_outcomes_all.py >> logs/fill_outcomes_all.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import time
from datetime import datetime, date, timedelta
from collections import defaultdict

import yfinance as yf
import pandas as pd

LOG_PREFIX = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"


def get_trading_days_after(daily_df: pd.DataFrame, scan_date: str, n: int = 5) -> list[tuple[int, date]]:
    """Return [(day_offset, date), ...] for up to n trading days after scan_date."""
    dt = pd.Timestamp(scan_date)
    trading_days = daily_df.index[daily_df.index > dt]
    result = []
    for i in range(min(n, len(trading_days))):
        result.append((i + 1, trading_days[i].date()))
    return result


def compute_outcomes(daily_df: pd.DataFrame, scan_date: str, scan_price: float) -> dict:
    """
    Compute outcome_1d..5d, outcome_max_gain_5d, outcome_max_dd_5d relative to scan_price.
    Returns dict with keys matching signal_outcomes columns.
    """
    if daily_df.empty or scan_price <= 0:
        return {}

    trading_days = get_trading_days_after(daily_df, scan_date, n=5)
    if not trading_days:
        return {}

    result = {}
    gains = []
    dds = []

    for offset, td in trading_days:
        ts = pd.Timestamp(td)
        if ts not in daily_df.index:
            continue
        row = daily_df.loc[ts]
        close = float(row['Close'].iloc[0]) if hasattr(row['Close'], 'iloc') else float(row['Close'])
        high  = float(row['High'].iloc[0])  if hasattr(row['High'],  'iloc') else float(row['High'])
        low   = float(row['Low'].iloc[0])   if hasattr(row['Low'],   'iloc') else float(row['Low'])

        pct   = (close - scan_price) / scan_price * 100
        gain  = (high  - scan_price) / scan_price * 100
        dd    = (low   - scan_price) / scan_price * 100

        result[f'outcome_{offset}d'] = round(pct, 2)
        gains.append(gain)
        dds.append(dd)

    if gains:
        result['outcome_max_gain_5d'] = round(max(gains), 2)
        result['outcome_max_dd_5d']   = round(min(dds), 2)

    # Alias for schema columns
    if '1d' not in str(result.get('outcome_1d', '')):
        result.setdefault('outcome_1d', None)
    result.setdefault('outcome_2d', None)
    result.setdefault('outcome_3d', None)
    result.setdefault('outcome_4d', None)
    result.setdefault('outcome_5d', None)
    result.setdefault('outcome_max_gain_5d', None)
    result.setdefault('outcome_max_dd_5d', None)

    return result


def main():
    print(f"{LOG_PREFIX} fill_outcomes_all.py starting")

    with get_session() as session:

        # Rows needing outcome fill — scan_date must be at least 1 day ago
        cutoff = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        rows = session.execute(text("""
            SELECT id, symbol, scan_date, scan_price, action_taken, signal_source
            FROM signal_outcomes
            WHERE action_taken IN ('QUEUE_FULL', 'SKIPPED_FILTER', 'BOUGHT', 'QUEUED')
              AND outcome_1d IS NULL
              AND scan_price > 0
              AND scan_date <= :p0
            ORDER BY scan_date DESC, symbol
        """), {'p0': cutoff}).fetchall()

        if not rows:
            print(f"{LOG_PREFIX} Nothing to fill — all outcomes complete.")
            return

        print(f"{LOG_PREFIX} {len(rows)} rows to fill across {len(set(r[1] for r in rows))} symbols")

        # Group by symbol for batch yfinance download
        by_symbol: dict[str, list] = defaultdict(list)
        for r in rows:
            by_symbol[r[1]].append({'id': r[0], 'symbol': r[1], 'scan_date': r[2], 'scan_price': r[3], 'action_taken': r[4], 'signal_source': r[5]})

        filled = 0
        skipped = 0
        errors = 0

        for i, (symbol, entries) in enumerate(by_symbol.items()):
            if i % 20 == 0 and i > 0:
                print(f"{LOG_PREFIX}   [{i}/{len(by_symbol)}] processed so far: filled={filled} skipped={skipped}")

            # Find earliest scan_date for this symbol to set download range
            dates = [e['scan_date'] for e in entries]
            earliest = min(dates)
            start_dt = (pd.Timestamp(earliest) - timedelta(days=1)).strftime('%Y-%m-%d')

            try:
                df = yf.download(symbol, start=start_dt, interval='1d',
                                 auto_adjust=True, progress=False)
                if df.empty:
                    skipped += len(entries)
                    continue
                df.index = pd.to_datetime(df.index).tz_localize(None)
            except Exception as e:
                print(f"{LOG_PREFIX}   ERROR fetching {symbol}: {e}")
                errors += len(entries)
                continue

            for entry in entries:
                outcomes = compute_outcomes(df, entry['scan_date'], entry['scan_price'])
                if not outcomes or outcomes.get('outcome_1d') is None:
                    skipped += 1
                    continue

                try:
                    session.execute(text("""
                        UPDATE signal_outcomes SET
                            outcome_1d = :p0, outcome_2d = :p1, outcome_3d = :p2,
                            outcome_4d = :p3, outcome_5d = :p4,
                            outcome_max_gain_5d = :p5, outcome_max_dd_5d = :p6,
                            updated_at = datetime('now')
                        WHERE id = :p7
                    """), {
                        'p0': outcomes.get('outcome_1d'),
                        'p1': outcomes.get('outcome_2d'),
                        'p2': outcomes.get('outcome_3d'),
                        'p3': outcomes.get('outcome_4d'),
                        'p4': outcomes.get('outcome_5d'),
                        'p5': outcomes.get('outcome_max_gain_5d'),
                        'p6': outcomes.get('outcome_max_dd_5d'),
                        'p7': entry['id'],
                    })
                    filled += 1
                except Exception as e:
                    print(f"{LOG_PREFIX}   DB ERROR {symbol} id={entry['id']}: {e}")
                    errors += 1
            time.sleep(0.05)  # rate limit
        print(f"{LOG_PREFIX} signal_outcomes done. filled={filled} skipped={skipped} errors={errors}")

        # -- Part 2: Fill screener_rejections outcomes --
        _fill_screener_rejections(session, cutoff)


def _fill_screener_rejections(session, cutoff: str):
    """Fill outcome_1d/5d for screener_rejections rows (Dimension 3)."""

    rows = session.execute(text("""
        SELECT id, symbol, scan_date, scan_price
        FROM screener_rejections
        WHERE outcome_1d IS NULL
          AND scan_price IS NOT NULL AND scan_price > 0
          AND scan_date <= :p0
        ORDER BY scan_date DESC, symbol
    """), {'p0': cutoff}).fetchall()

    if not rows:
        print(f"{LOG_PREFIX} screener_rejections: nothing to fill")
        return

    print(f"{LOG_PREFIX} screener_rejections: {len(rows)} rows to fill")

    by_symbol: dict[str, list] = defaultdict(list)
    for r in rows:
        by_symbol[r[1]].append({'id': r[0], 'symbol': r[1], 'scan_date': r[2], 'scan_price': r[3]})

    filled = skipped = errors = 0

    for symbol, entries in by_symbol.items():
        dates = [e['scan_date'] for e in entries]
        earliest = min(dates)
        start_dt = (pd.Timestamp(earliest) - timedelta(days=1)).strftime('%Y-%m-%d')

        try:
            df = yf.download(symbol, start=start_dt, interval='1d',
                             auto_adjust=True, progress=False)
            if df.empty:
                skipped += len(entries)
                continue
            df.index = pd.to_datetime(df.index).tz_localize(None)
        except Exception as e:
            errors += len(entries)
            continue

        for entry in entries:
            outcomes = compute_outcomes(df, entry['scan_date'], entry['scan_price'])
            if not outcomes or outcomes.get('outcome_1d') is None:
                skipped += 1
                continue
            try:
                session.execute(text("""
                    UPDATE screener_rejections SET
                        outcome_1d = :p0, outcome_2d = :p1, outcome_3d = :p2,
                        outcome_4d = :p3, outcome_5d = :p4,
                        outcome_max_gain_5d = :p5, outcome_max_dd_5d = :p6
                    WHERE id = :p7
                """), {
                    'p0': outcomes.get('outcome_1d'),
                    'p1': outcomes.get('outcome_2d'),
                    'p2': outcomes.get('outcome_3d'),
                    'p3': outcomes.get('outcome_4d'),
                    'p4': outcomes.get('outcome_5d'),
                    'p5': outcomes.get('outcome_max_gain_5d'),
                    'p6': outcomes.get('outcome_max_dd_5d'),
                    'p7': entry['id'],
                })
                filled += 1
            except Exception as e:
                errors += 1
        time.sleep(0.05)
    print(f"{LOG_PREFIX} screener_rejections done. filled={filled} skipped={skipped} errors={errors}")

    # -- Part 3: Fill pre_filter_rejections outcomes --
    _fill_pre_filter_rejections(session, cutoff)


def _fill_pre_filter_rejections(session, cutoff: str):
    """Fill outcome_1d/5d for pre_filter_rejections rows (Dimension 0 — full pipeline)."""

    rows = session.execute(text("""
        SELECT id, symbol, scan_date, close_price as scan_price
        FROM pre_filter_rejections
        WHERE outcome_1d IS NULL
          AND close_price IS NOT NULL AND close_price > 0
          AND scan_date <= :p0
        ORDER BY scan_date DESC, symbol
    """), {'p0': cutoff}).fetchall()

    if not rows:
        print(f"{LOG_PREFIX} pre_filter_rejections: nothing to fill")
        return

    print(f"{LOG_PREFIX} pre_filter_rejections: {len(rows)} rows to fill")

    by_symbol: dict[str, list] = defaultdict(list)
    for r in rows:
        by_symbol[r[1]].append({'id': r[0], 'symbol': r[1], 'scan_date': r[2], 'scan_price': r[3]})

    filled = skipped = errors = 0

    for symbol, entries in by_symbol.items():
        dates = [e['scan_date'] for e in entries]
        earliest = min(dates)
        start_dt = (pd.Timestamp(earliest) - timedelta(days=1)).strftime('%Y-%m-%d')

        try:
            df = yf.download(symbol, start=start_dt, interval='1d',
                             auto_adjust=True, progress=False)
            if df.empty:
                skipped += len(entries)
                continue
            df.index = pd.to_datetime(df.index).tz_localize(None)
        except Exception:
            errors += len(entries)
            continue

        for entry in entries:
            outcomes = compute_outcomes(df, entry['scan_date'], entry['scan_price'])
            if not outcomes or outcomes.get('outcome_1d') is None:
                skipped += 1
                continue
            try:
                session.execute(text("""
                    UPDATE pre_filter_rejections SET
                        outcome_1d = :p0, outcome_2d = :p1, outcome_3d = :p2,
                        outcome_4d = :p3, outcome_5d = :p4,
                        outcome_max_gain_5d = :p5, outcome_max_dd_5d = :p6
                    WHERE id = :p7
                """), {
                    'p0': outcomes.get('outcome_1d'),
                    'p1': outcomes.get('outcome_2d'),
                    'p2': outcomes.get('outcome_3d'),
                    'p3': outcomes.get('outcome_4d'),
                    'p4': outcomes.get('outcome_5d'),
                    'p5': outcomes.get('outcome_max_gain_5d'),
                    'p6': outcomes.get('outcome_max_dd_5d'),
                    'p7': entry['id'],
                })
                filled += 1
            except Exception:
                errors += 1
        time.sleep(0.05)
    print(f"{LOG_PREFIX} pre_filter_rejections done. filled={filled} skipped={skipped} errors={errors}")


if __name__ == '__main__':
    main()
