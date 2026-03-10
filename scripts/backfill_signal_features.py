#!/usr/bin/env python3
"""
Backfill missing features in signal_outcomes
=============================================
Fills: momentum_20d, spy_pct_above_sma, sector_1d_change (new col), vix_at_signal (N/A - forward only)

Columns added:
  momentum_20d      - 20-day price return at scan_date (already in schema, all NULL)
  distance_from_high - % below 52w high at scan_date (already in schema, all NULL)
  spy_pct_above_sma  - SPY % above SMA20 at scan_date (new col, already added)
  sector_1d_change   - sector ETF daily return on scan_date (new col, must ADD first)

Strategy:
  1. Group rows by scan_date (reduce yfinance calls)
  2. For each date: fetch SPY + all needed symbols + sector ETFs in one batch download
  3. Update DB in bulk

Run: python3 scripts/backfill_signal_features.py [--dry-run] [--date YYYY-MM-DD]
"""

import sys
import os
import sqlite3
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import yfinance as yf
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')

SECTOR_ETF_MAP = {
    'Technology': 'XLK',
    'Real Estate': 'XLRE',
    'Energy': 'XLE',
    'Financial Services': 'XLF',
    'Healthcare': 'XLV',
    'Consumer Cyclical': 'XLY',
    'Consumer Defensive': 'XLP',
    'Industrials': 'XLI',
    'Utilities': 'XLU',
    'Basic Materials': 'XLB',
    'Communication Services': 'XLC',
}


def ensure_sector_1d_change_column(conn):
    """Add sector_1d_change column if not exists."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(signal_outcomes)").fetchall()]
    if 'sector_1d_change' not in cols:
        conn.execute("ALTER TABLE signal_outcomes ADD COLUMN sector_1d_change REAL")
        conn.commit()
        print("  Added column: sector_1d_change")


def load_rows_to_backfill(conn, target_date=None):
    """Load signal_outcomes rows that need backfilling."""
    where = ""
    params = []
    if target_date:
        where = "AND scan_date = ?"
        params.append(target_date)

    rows = conn.execute(f"""
        SELECT id, symbol, scan_date, signal_source,
               momentum_20d, distance_from_high, spy_pct_above_sma, sector_1d_change
        FROM signal_outcomes
        WHERE 1=1 {where}
        ORDER BY scan_date, symbol
    """, params).fetchall()
    return rows


def fetch_price_data_for_date(scan_date_str, symbols, extra_tickers=None):
    """
    Fetch 60d of daily bars ending on scan_date+5d for all symbols.
    Returns dict: {ticker: pd.Series of daily Close, indexed by date string}
    """
    extra_tickers = extra_tickers or []
    all_tickers = list(set(symbols + ['SPY'] + extra_tickers))

    # Need data from 30 trading days before scan_date (for SMA20 + mom20d)
    scan_dt = datetime.strptime(scan_date_str, '%Y-%m-%d')
    start = (scan_dt - timedelta(days=45)).strftime('%Y-%m-%d')
    end   = (scan_dt + timedelta(days=3)).strftime('%Y-%m-%d')

    try:
        df = yf.download(
            all_tickers if len(all_tickers) > 1 else all_tickers[0],
            start=start, end=end,
            auto_adjust=True, progress=False,
        )
        if df.empty:
            return {}

        close = df['Close']
        result = {}
        for t in all_tickers:
            try:
                s = (close[t] if len(all_tickers) > 1 else close).dropna()
                result[t] = s
            except Exception:
                pass
        return result

    except Exception as e:
        print(f"    yfinance error for {scan_date_str}: {e}")
        return {}


def compute_features(scan_date_str, symbol, sector, price_data):
    """
    Compute backfill features for one signal row.

    Returns dict with: momentum_20d, distance_from_high, spy_pct_above_sma, sector_1d_change
    All values are float or None.
    """
    result = {}

    # ── momentum_20d & distance_from_high ─────────────────────────────────────
    sym_series = price_data.get(symbol)
    if sym_series is not None and not sym_series.empty:
        # Find the close on or just before scan_date
        dates = sym_series.index.strftime('%Y-%m-%d').tolist()
        prices = sym_series.values.tolist()
        date_price = {d: p for d, p in zip(dates, prices)}

        # Get price on scan_date (or closest prior day)
        scan_price = None
        for d in sorted(date_price.keys(), reverse=True):
            if d <= scan_date_str:
                scan_price = date_price[d]
                break

        if scan_price and scan_price > 0:
            # momentum_20d: price 20 trading days before scan_date
            scan_idx = next((i for i, d in enumerate(sorted(date_price.keys())) if d >= scan_date_str), None)
            sorted_dates = sorted(date_price.keys())
            if scan_idx is not None and scan_idx >= 20:
                price_20d_ago = date_price[sorted_dates[scan_idx - 20]]
                if price_20d_ago > 0:
                    result['momentum_20d'] = round((scan_price / price_20d_ago - 1) * 100, 2)

            # distance_from_high: % below 52-week high
            lookback_dates = [d for d in sorted_dates if d <= scan_date_str][-252:]
            if lookback_dates:
                high_52w = max(date_price[d] for d in lookback_dates)
                if high_52w > 0:
                    result['distance_from_high'] = round((scan_price / high_52w - 1) * 100, 2)

    # ── spy_pct_above_sma (SMA20) ──────────────────────────────────────────────
    spy_series = price_data.get('SPY')
    if spy_series is not None and not spy_series.empty:
        spy_dates = spy_series.index.strftime('%Y-%m-%d').tolist()
        spy_prices = spy_series.values.tolist()
        spy_dp = {d: p for d, p in zip(spy_dates, spy_prices)}

        spy_sorted = sorted(spy_dp.keys())
        spy_idx = next((i for i, d in enumerate(spy_sorted) if d >= scan_date_str), None)
        if spy_idx is not None and spy_idx >= 19:
            spy_close = spy_dp[spy_sorted[spy_idx]]
            sma20 = sum(spy_dp[spy_sorted[spy_idx - i]] for i in range(20)) / 20
            if sma20 > 0:
                result['spy_pct_above_sma'] = round((spy_close / sma20 - 1) * 100, 3)

    # ── sector_1d_change ──────────────────────────────────────────────────────
    etf = SECTOR_ETF_MAP.get(sector)
    if etf:
        etf_series = price_data.get(etf)
        if etf_series is not None and not etf_series.empty:
            etf_dates = etf_series.index.strftime('%Y-%m-%d').tolist()
            etf_prices = etf_series.values.tolist()
            etf_dp = {d: p for d, p in zip(etf_dates, etf_prices)}

            etf_sorted = sorted(etf_dp.keys())
            # Find scan_date close and prev close
            scan_idx = next((i for i, d in enumerate(etf_sorted) if d >= scan_date_str), None)
            if scan_idx is not None and scan_idx >= 1:
                close_today = etf_dp[etf_sorted[scan_idx]]
                close_prev  = etf_dp[etf_sorted[scan_idx - 1]]
                if close_prev > 0:
                    result['sector_1d_change'] = round((close_today / close_prev - 1) * 100, 3)

    return result


def main():
    parser = argparse.ArgumentParser(description='Backfill signal_outcomes features')
    parser.add_argument('--dry-run', action='store_true', help='Preview only, no DB writes')
    parser.add_argument('--date', help='Process only this scan_date (YYYY-MM-DD)')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Ensure sector_1d_change column exists
    ensure_sector_1d_change_column(conn)

    # Load sector mapping for signal rows
    sector_map = {}
    for r in conn.execute("SELECT symbol, sector FROM sector_cache").fetchall():
        sector_map[r['symbol']] = r['sector']
    for r in conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall():
        if r['symbol'] not in sector_map:
            sector_map[r['symbol']] = r['sector']

    # Load rows
    rows = load_rows_to_backfill(conn, args.date)
    print(f"Total signal_outcomes rows: {len(rows)}")

    # Check how many need backfilling
    need_mom20d   = sum(1 for r in rows if r['momentum_20d'] is None)
    need_dist_hgh = sum(1 for r in rows if r['distance_from_high'] is None)
    need_spy_sma  = sum(1 for r in rows if r['spy_pct_above_sma'] is None)
    need_sect_1d  = sum(1 for r in rows if r['sector_1d_change'] is None)
    print(f"Need backfill: momentum_20d={need_mom20d}, dist_high={need_dist_hgh}, "
          f"spy_pct_above_sma={need_spy_sma}, sector_1d_change={need_sect_1d}")

    if need_mom20d + need_dist_hgh + need_spy_sma + need_sect_1d == 0:
        print("Nothing to backfill!")
        conn.close()
        return

    # Group by scan_date
    by_date = defaultdict(list)
    for r in rows:
        by_date[r['scan_date']].append(r)

    dates = sorted(by_date.keys())
    print(f"Processing {len(dates)} scan dates...")

    total_updated = 0
    total_errors  = 0

    for i, scan_date in enumerate(dates):
        date_rows = by_date[scan_date]
        # Skip if all features already filled for all rows on this date
        needs_work = [r for r in date_rows if any([
            r['momentum_20d'] is None,
            r['distance_from_high'] is None,
            r['spy_pct_above_sma'] is None,
            r['sector_1d_change'] is None,
        ])]
        if not needs_work:
            continue

        # Collect symbols + sector ETFs needed for this date
        symbols = list(set(r['symbol'] for r in needs_work))
        sectors = set(sector_map.get(r['symbol'], '') for r in needs_work)
        etfs = [SECTOR_ETF_MAP[s] for s in sectors if s in SECTOR_ETF_MAP]

        print(f"  [{i+1}/{len(dates)}] {scan_date}: {len(needs_work)} rows, "
              f"{len(symbols)} symbols, {len(etfs)} ETFs...", end=' ', flush=True)

        price_data = fetch_price_data_for_date(scan_date, symbols, etfs)
        if not price_data:
            print("no data")
            total_errors += 1
            continue

        date_updated = 0
        for r in needs_work:
            sector = sector_map.get(r['symbol'], '')
            features = compute_features(scan_date, r['symbol'], sector, price_data)
            if not features:
                continue

            # Only update columns that are still NULL
            updates = {}
            if r['momentum_20d']    is None and 'momentum_20d'    in features:
                updates['momentum_20d']    = features['momentum_20d']
            if r['distance_from_high'] is None and 'distance_from_high' in features:
                updates['distance_from_high'] = features['distance_from_high']
            if r['spy_pct_above_sma'] is None and 'spy_pct_above_sma' in features:
                updates['spy_pct_above_sma'] = features['spy_pct_above_sma']
            if r['sector_1d_change']  is None and 'sector_1d_change'  in features:
                updates['sector_1d_change']  = features['sector_1d_change']

            if not updates:
                continue

            if not args.dry_run:
                set_clause = ', '.join(f"{k} = ?" for k in updates)
                vals = list(updates.values()) + [r['id']]
                conn.execute(f"UPDATE signal_outcomes SET {set_clause} WHERE id = ?", vals)
                date_updated += 1
            else:
                date_updated += 1

        if not args.dry_run and date_updated > 0:
            conn.commit()

        total_updated += date_updated
        print(f"updated {date_updated}")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done. Updated {total_updated} rows, {total_errors} date errors.")

    # Final counts
    if not args.dry_run:
        r2 = conn.execute("""
            SELECT
              SUM(CASE WHEN momentum_20d IS NOT NULL THEN 1 ELSE 0 END) mom20d,
              SUM(CASE WHEN distance_from_high IS NOT NULL THEN 1 ELSE 0 END) dist_high,
              SUM(CASE WHEN spy_pct_above_sma IS NOT NULL THEN 1 ELSE 0 END) spy_sma,
              SUM(CASE WHEN sector_1d_change IS NOT NULL THEN 1 ELSE 0 END) sect_1d,
              COUNT(*) total
            FROM signal_outcomes
        """).fetchone()
        print(f"\nFinal coverage: momentum_20d={r2[0]}/{r2[4]}, dist_high={r2[1]}/{r2[4]}, "
              f"spy_pct_above_sma={r2[2]}/{r2[4]}, sector_1d_change={r2[3]}/{r2[4]}")

    conn.close()


if __name__ == '__main__':
    main()
