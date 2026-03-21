#!/usr/bin/env python3
"""
backfill_short_outcomes.py
==========================
Backfill outcome_1d, outcome_2d, outcome_3d, outcome_4d into backfill_signal_outcomes.

The table already has outcome_5d, outcome_max_gain_5d, outcome_max_dd_5d.
This script adds the shorter-horizon outcome columns.

Algorithm:
    outcome_Nd = (close_on_trading_day_D+N / scan_price - 1) * 100

Price sources:
    1. stocks.db stock_prices table (2024-01-30 to 2026-01-30) — primary
    2. yfinance — for dates after 2026-01-30 or symbols missing from stocks.db
"""
import os
import sys
import sqlite3
import time
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
import yfinance as yf

TRADE_DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
STOCKS_DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'database', 'stocks.db')

LOG_PREFIX = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"


def add_columns_if_missing(conn):
    """Add outcome_1d..4d columns if they don't exist yet."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(backfill_signal_outcomes)").fetchall()}
    for col in ['outcome_1d', 'outcome_2d', 'outcome_3d', 'outcome_4d']:
        if col not in existing:
            conn.execute(f"ALTER TABLE backfill_signal_outcomes ADD COLUMN {col} REAL")
            print(f"{LOG_PREFIX} Added column {col}")
    conn.commit()


def load_stocks_db_prices(symbol: str) -> pd.DataFrame:
    """Load all price data for a symbol from stocks.db. Returns DataFrame indexed by date."""
    conn = sqlite3.connect(STOCKS_DB)
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close FROM stock_prices WHERE symbol = ? ORDER BY date",
        conn, params=(symbol,)
    )
    conn.close()
    if df.empty:
        return df
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    return df


def download_yfinance_prices(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Download daily prices from yfinance. Returns DataFrame indexed by date."""
    try:
        df = yf.download(symbol, start=start_date, end=end_date,
                         interval='1d', auto_adjust=True, progress=False)
        if df.empty:
            return df
        df.index = pd.to_datetime(df.index).tz_localize(None)
        # Flatten MultiIndex columns if needed (yfinance sometimes returns multi-level)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # Normalize column names to lowercase
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        print(f"{LOG_PREFIX}   yfinance error for {symbol}: {e}")
        return pd.DataFrame()


def get_combined_prices(symbol: str, earliest_scan: str, latest_scan: str) -> pd.DataFrame:
    """
    Get price data from stocks.db first, then supplement with yfinance for dates
    beyond stocks.db coverage (after 2026-01-30).
    Returns DataFrame with lowercase columns: close, high, low, indexed by datetime.
    """
    # Load from stocks.db
    local_df = load_stocks_db_prices(symbol)

    # Determine if we need yfinance data
    # We need prices for up to D+4 after the latest_scan_date
    latest_needed = pd.Timestamp(latest_scan) + timedelta(days=10)  # buffer for weekends
    stocks_db_max = pd.Timestamp('2026-01-30')

    if local_df.empty:
        # No local data at all — download everything from yfinance
        start = (pd.Timestamp(earliest_scan) - timedelta(days=1)).strftime('%Y-%m-%d')
        end = (latest_needed + timedelta(days=1)).strftime('%Y-%m-%d')
        return download_yfinance_prices(symbol, start, end)

    # If we need data beyond stocks.db coverage
    if latest_needed > stocks_db_max:
        # Download from a bit before the gap to ensure overlap
        yf_start = (stocks_db_max - timedelta(days=1)).strftime('%Y-%m-%d')
        yf_end = (latest_needed + timedelta(days=1)).strftime('%Y-%m-%d')
        yf_df = download_yfinance_prices(symbol, yf_start, yf_end)

        if not yf_df.empty:
            # Combine: use stocks.db where available, yfinance for the rest
            # Only take yfinance rows that are after stocks.db max
            yf_new = yf_df[yf_df.index > stocks_db_max]
            if not yf_new.empty:
                # Rename local columns to match
                combined = pd.concat([local_df, yf_new[['close', 'high', 'low']]])
                combined = combined[~combined.index.duplicated(keep='first')]
                combined.sort_index(inplace=True)
                return combined

    return local_df


def compute_short_outcomes(price_df: pd.DataFrame, scan_date: str, scan_price: float) -> dict:
    """
    Compute outcome_1d..4d relative to scan_price.
    Returns dict like {'outcome_1d': 1.23, 'outcome_2d': -0.5, ...}
    """
    if price_df.empty or scan_price <= 0:
        return {}

    dt = pd.Timestamp(scan_date)
    trading_days = price_df.index[price_df.index > dt]

    result = {}
    for offset in range(1, 5):  # 1d, 2d, 3d, 4d
        if offset > len(trading_days):
            break
        td = trading_days[offset - 1]
        if td not in price_df.index:
            continue
        row = price_df.loc[td]
        close_val = float(row['close'].iloc[0]) if hasattr(row['close'], 'iloc') else float(row['close'])
        pct = (close_val - scan_price) / scan_price * 100
        result[f'outcome_{offset}d'] = round(pct, 2)

    return result


def main():
    print(f"{LOG_PREFIX} backfill_short_outcomes.py starting")
    print(f"{LOG_PREFIX} Trade DB: {os.path.abspath(TRADE_DB)}")
    print(f"{LOG_PREFIX} Stocks DB: {os.path.abspath(STOCKS_DB)}")

    conn = sqlite3.connect(TRADE_DB)
    conn.row_factory = sqlite3.Row

    # Step 1: Add columns
    add_columns_if_missing(conn)

    # Step 2: Query all rows
    rows = conn.execute("""
        SELECT id, symbol, scan_date, scan_price
        FROM backfill_signal_outcomes
        WHERE scan_price > 0
        ORDER BY symbol, scan_date
    """).fetchall()

    total = len(rows)
    print(f"{LOG_PREFIX} Total rows: {total}")

    if not rows:
        conn.close()
        return

    # Step 3: Group by symbol
    by_symbol: dict[str, list] = defaultdict(list)
    for r in rows:
        by_symbol[r['symbol']].append({
            'id': r['id'],
            'symbol': r['symbol'],
            'scan_date': r['scan_date'],
            'scan_price': r['scan_price'],
        })

    num_symbols = len(by_symbol)
    print(f"{LOG_PREFIX} Unique symbols: {num_symbols}")

    filled = 0
    skipped = 0
    errors = 0
    yf_calls = 0

    for i, (symbol, entries) in enumerate(by_symbol.items()):
        if i % 50 == 0:
            print(f"{LOG_PREFIX}   [{i}/{num_symbols}] symbols processed | filled={filled} skipped={skipped} errors={errors}")

        dates = [e['scan_date'] for e in entries]
        earliest = min(dates)
        latest = max(dates)

        try:
            price_df = get_combined_prices(symbol, earliest, latest)
            if price_df.empty:
                skipped += len(entries)
                continue
        except Exception as e:
            print(f"{LOG_PREFIX}   ERROR loading prices for {symbol}: {e}")
            errors += len(entries)
            continue

        batch_filled = 0
        for entry in entries:
            outcomes = compute_short_outcomes(price_df, entry['scan_date'], entry['scan_price'])
            if not outcomes:
                skipped += 1
                continue

            try:
                conn.execute("""
                    UPDATE backfill_signal_outcomes SET
                        outcome_1d = ?,
                        outcome_2d = ?,
                        outcome_3d = ?,
                        outcome_4d = ?
                    WHERE id = ?
                """, (
                    outcomes.get('outcome_1d'),
                    outcomes.get('outcome_2d'),
                    outcomes.get('outcome_3d'),
                    outcomes.get('outcome_4d'),
                    entry['id'],
                ))
                filled += 1
                batch_filled += 1
            except Exception as e:
                print(f"{LOG_PREFIX}   DB ERROR {symbol} rowid={entry['rowid']}: {e}")
                errors += 1

        conn.commit()

        # Rate limit yfinance calls
        if latest > '2026-01-30':
            yf_calls += 1
            if yf_calls % 5 == 0:
                time.sleep(0.2)

    conn.close()

    print(f"{LOG_PREFIX} ── DONE ──")
    print(f"{LOG_PREFIX}   Total rows:  {total}")
    print(f"{LOG_PREFIX}   Filled:      {filled}")
    print(f"{LOG_PREFIX}   Skipped:     {skipped}")
    print(f"{LOG_PREFIX}   Errors:      {errors}")
    print(f"{LOG_PREFIX}   yf calls:    {yf_calls}")


if __name__ == '__main__':
    main()
