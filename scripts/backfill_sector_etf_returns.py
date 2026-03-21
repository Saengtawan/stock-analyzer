#!/usr/bin/env python3
"""
backfill_sector_etf_returns.py — Backfill sector_etf_daily_returns from yfinance.

Usage:
  python3 scripts/backfill_sector_etf_returns.py --start 2022-01-01 --end 2025-08-24
  python3 scripts/backfill_sector_etf_returns.py --start 2022-01-01 --end 2025-08-24 --force

Fetches 12 sector ETFs + SPY + safe-haven assets (GLD, TLT, UVXY).
Computes pct_change and vs_spy for each trading day.
"""
import argparse
import os
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')

# Sector ETFs (existing 12)
SECTOR_ETFS = {
    'XLK': 'Technology',
    'XLF': 'Financial Services',
    'XLV': 'Healthcare',
    'XLE': 'Energy',
    'XLY': 'Consumer Cyclical',
    'XLP': 'Consumer Defensive',
    'XLI': 'Industrials',
    'XLB': 'Basic Materials',
    'XLRE': 'Real Estate',
    'XLU': 'Utilities',
    'XLC': 'Communication Services',
}

# Safe-haven / crisis assets (NEW)
SAFE_HAVEN_ETFS = {
    'GLD': 'Gold',
    'TLT': 'Treasury Long',
    'UUP': 'US Dollar',
}

ALL_ETFS = {**SECTOR_ETFS, **SAFE_HAVEN_ETFS}


def main():
    parser = argparse.ArgumentParser(description='Backfill sector ETF daily returns')
    parser.add_argument('--start', required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end', required=True, help='End date YYYY-MM-DD')
    parser.add_argument('--force', action='store_true', help='Overwrite existing rows')
    args = parser.parse_args()

    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()

    conn = sqlite3.connect(DB_PATH, timeout=30)

    # Get existing (date, etf) pairs to skip
    existing = set()
    if not args.force:
        rows = conn.execute("SELECT date, etf FROM sector_etf_daily_returns").fetchall()
        existing = set((r[0], r[1]) for r in rows)
        print(f"Existing rows: {len(existing)}")

    # Download all ETFs + SPY in one batch
    all_symbols = list(ALL_ETFS.keys()) + ['SPY']
    fetch_start = (start - timedelta(days=5)).strftime('%Y-%m-%d')
    fetch_end = (end + timedelta(days=1)).strftime('%Y-%m-%d')

    print(f"Downloading {len(all_symbols)} symbols: {fetch_start} to {fetch_end}...")
    data = yf.download(all_symbols, start=fetch_start, end=fetch_end,
                       auto_adjust=True, progress=True, group_by='ticker')

    if data.empty:
        print("ERROR: No data downloaded")
        conn.close()
        return

    # Extract SPY daily returns for vs_spy calculation
    try:
        spy_close = data['SPY']['Close'].dropna()
        spy_returns = spy_close.pct_change() * 100  # in %
    except Exception as e:
        print(f"ERROR extracting SPY: {e}")
        conn.close()
        return

    # Process each ETF
    trading_days = pd.bdate_range(start, end)
    inserted = 0
    skipped = 0

    for etf, sector in ALL_ETFS.items():
        try:
            etf_data = data[etf]
            if etf_data.empty:
                print(f"  WARNING: No data for {etf}")
                continue
        except KeyError:
            print(f"  WARNING: {etf} not in downloaded data")
            continue

        etf_close = etf_data['Close'].dropna()
        etf_returns = etf_close.pct_change() * 100

        for td in trading_days:
            d_str = td.strftime('%Y-%m-%d')

            if (d_str, etf) in existing:
                skipped += 1
                continue

            # Get OHLCV for this date
            try:
                mask = etf_data.index.date == td.date()
                if not mask.any():
                    continue
                row = etf_data[mask].iloc[0]

                o = float(row['Open']) if pd.notna(row['Open']) else None
                h = float(row['High']) if pd.notna(row['High']) else None
                l = float(row['Low']) if pd.notna(row['Low']) else None
                c = float(row['Close']) if pd.notna(row['Close']) else None
                v = int(row['Volume']) if pd.notna(row['Volume']) else None

                if c is None:
                    continue

                # pct_change
                pct_chg = None
                if td in etf_returns.index:
                    val = etf_returns.loc[td]
                    if hasattr(val, 'iloc'):
                        val = val.iloc[0]
                    if pd.notna(val):
                        pct_chg = round(float(val), 4)

                # vs_spy
                vs_spy_val = None
                if pct_chg is not None and td in spy_returns.index:
                    spy_ret = spy_returns.loc[td]
                    if hasattr(spy_ret, 'iloc'):
                        spy_ret = spy_ret.iloc[0]
                    if pd.notna(spy_ret):
                        vs_spy_val = round(pct_chg - float(spy_ret), 4)

                conn.execute("""
                    INSERT OR REPLACE INTO sector_etf_daily_returns
                        (date, etf, sector, open, high, low, close, volume, pct_change, vs_spy)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (d_str, etf, sector, o, h, l, c, v, pct_chg, vs_spy_val))
                inserted += 1

            except Exception:
                continue

        print(f"  {etf} ({sector}): processed")

    # Also insert SPY rows
    for td in trading_days:
        d_str = td.strftime('%Y-%m-%d')
        if (d_str, 'SPY') in existing:
            skipped += 1
            continue

        try:
            spy_data_full = data['SPY']
            mask = spy_data_full.index.date == td.date()
            if not mask.any():
                continue
            row = spy_data_full[mask].iloc[0]

            o = float(row['Open']) if pd.notna(row['Open']) else None
            h = float(row['High']) if pd.notna(row['High']) else None
            l = float(row['Low']) if pd.notna(row['Low']) else None
            c = float(row['Close']) if pd.notna(row['Close']) else None
            v = int(row['Volume']) if pd.notna(row['Volume']) else None

            if c is None:
                continue

            pct_chg = None
            if td in spy_returns.index:
                val = spy_returns.loc[td]
                if hasattr(val, 'iloc'):
                    val = val.iloc[0]
                if pd.notna(val):
                    pct_chg = round(float(val), 4)

            conn.execute("""
                INSERT OR REPLACE INTO sector_etf_daily_returns
                    (date, etf, sector, open, high, low, close, volume, pct_change, vs_spy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """, (d_str, 'SPY', 'S&P 500', o, h, l, c, v, pct_chg))
            inserted += 1
        except Exception:
            continue

    print(f"  SPY (S&P 500): processed")

    conn.commit()

    # Verify
    total = conn.execute("SELECT COUNT(*) FROM sector_etf_daily_returns").fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(date), MAX(date) FROM sector_etf_daily_returns"
    ).fetchone()
    sector_count = conn.execute(
        "SELECT COUNT(DISTINCT sector) FROM sector_etf_daily_returns"
    ).fetchone()[0]

    conn.close()

    print(f"\nDone: inserted={inserted}, skipped={skipped}")
    print(f"sector_etf_daily_returns: {total} rows ({date_range[0]} to {date_range[1]})")
    print(f"Sectors: {sector_count}")


if __name__ == '__main__':
    main()
