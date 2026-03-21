#!/usr/bin/env python3
"""
backfill_macro_snapshots.py — Backfill macro_snapshots table from yfinance.

Usage:
  python3 scripts/backfill_macro_snapshots.py --start 2025-09-01 --end 2026-03-16

Fetches VIX, VIX3M, SPY, DXY, TNX, IRX, Gold, Crude, HYG for each trading day.
Skips dates already in DB (use --force to overwrite).
"""
import argparse
import os
import sqlite3
from datetime import datetime, date, timedelta

import pandas as pd
import yfinance as yf

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')

SYMBOLS = {
    'vix_close': '^VIX',
    'vix3m_close': '^VIX3M',
    'spy_close': 'SPY',
    'dxy_close': 'DX-Y.NYB',
    'yield_10y': '^TNX',
    'yield_3m': '^IRX',
    'gold_close': 'GC=F',
    'crude_close': 'CL=F',
    'hyg_close': 'HYG',
}


def main():
    parser = argparse.ArgumentParser(description='Backfill macro_snapshots from yfinance')
    parser.add_argument('--start', required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end', required=True, help='End date YYYY-MM-DD')
    parser.add_argument('--force', action='store_true', help='Overwrite existing rows')
    args = parser.parse_args()

    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    # Ensure all columns exist
    for col in ['vix3m_close', 'dxy_change_pct', 'regime_label', 'spy_regime',
                'gold_close', 'crude_close', 'hyg_close']:
        try:
            conn.execute(f"ALTER TABLE macro_snapshots ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass
    conn.commit()

    # Get existing dates
    existing = set()
    if not args.force:
        rows = conn.execute("SELECT date FROM macro_snapshots").fetchall()
        existing = set(r[0] for r in rows)

    # Download all symbols in one batch for the full range
    fetch_start = (start - timedelta(days=10)).strftime('%Y-%m-%d')
    fetch_end = (end + timedelta(days=1)).strftime('%Y-%m-%d')

    print(f"Downloading macro data {fetch_start} to {fetch_end}...")
    all_syms = list(SYMBOLS.values())
    data = yf.download(all_syms, start=fetch_start, end=fetch_end,
                       auto_adjust=True, progress=False)

    if data.empty:
        print("ERROR: No data downloaded")
        conn.close()
        return

    # Build per-date rows
    trading_days = pd.bdate_range(start, end)
    inserted = 0
    skipped = 0

    prev_dxy = None
    prev_spy = None

    # Get previous values from DB for delta calculations
    prev_row = conn.execute(
        "SELECT dxy_close, spy_close FROM macro_snapshots WHERE date < ? ORDER BY date DESC LIMIT 1",
        (start.strftime('%Y-%m-%d'),)
    ).fetchone()
    if prev_row:
        prev_dxy = prev_row[0]
        prev_spy = prev_row[1]

    for td in trading_days:
        d_str = td.strftime('%Y-%m-%d')
        d_date = td.date()

        if d_str in existing:
            skipped += 1
            continue

        # Extract values for this date
        vals = {}
        for col_name, sym in SYMBOLS.items():
            try:
                if len(all_syms) == 1:
                    row_data = data.loc[td]
                else:
                    row_data = data['Close'][sym]
                    if hasattr(row_data, 'loc'):
                        # Find closest date <= td
                        mask = row_data.index.date <= d_date
                        if mask.any():
                            val = float(row_data[mask].iloc[-1])
                            vals[col_name] = round(val, 4) if val == val else None
                        else:
                            vals[col_name] = None
                    else:
                        vals[col_name] = None
            except Exception:
                vals[col_name] = None

        # Skip if no VIX (market was likely closed)
        if vals.get('vix_close') is None:
            continue

        # Compute derived fields
        y10 = vals.get('yield_10y')
        y3m = vals.get('yield_3m')
        yield_spread = round(y10 - y3m, 4) if y10 and y3m else None

        dxy = vals.get('dxy_close')
        dxy_change_pct = None
        if dxy and prev_dxy and prev_dxy > 0:
            dxy_change_pct = round((dxy / prev_dxy - 1) * 100, 4)

        spy = vals.get('spy_close')
        vix = vals.get('vix_close')

        regime_label = None
        if vix:
            if vix < 20: regime_label = 'NORMAL'
            elif vix < 24: regime_label = 'SKIP'
            elif vix < 38: regime_label = 'HIGH'
            else: regime_label = 'EXTREME'

        spy_regime = None
        if spy and prev_spy and prev_spy > 0:
            spy_regime = 'BULL' if spy > prev_spy else 'BEAR'

        conn.execute("""
            INSERT OR REPLACE INTO macro_snapshots
                (date, yield_10y, yield_3m, yield_spread, vix_close, vix3m_close,
                 spy_close, dxy_close, dxy_change_pct,
                 gold_close, crude_close, hyg_close,
                 regime_label, spy_regime, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (d_str, y10, y3m, yield_spread, vix, vals.get('vix3m_close'),
              spy, dxy, dxy_change_pct,
              vals.get('gold_close'), vals.get('crude_close'), vals.get('hyg_close'),
              regime_label, spy_regime))

        inserted += 1
        prev_dxy = dxy or prev_dxy
        prev_spy = spy or prev_spy

    conn.commit()

    # Verify
    total = conn.execute("SELECT COUNT(*) FROM macro_snapshots").fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(date), MAX(date) FROM macro_snapshots"
    ).fetchone()
    conn.close()

    print(f"Done: inserted={inserted}, skipped={skipped}")
    print(f"macro_snapshots: {total} rows ({date_range[0]} to {date_range[1]})")


if __name__ == '__main__':
    main()
