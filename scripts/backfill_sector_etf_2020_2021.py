#!/usr/bin/env python3
"""Backfill sector_etf_daily_returns for 2020-01-01 to 2021-12-31."""

import sys
sys.path.insert(0, 'src')

import yfinance as yf
from database.orm.base import get_session
from sqlalchemy import text

ETF_SECTOR = {
    'GLD': 'Gold',
    'SPY': 'S&P 500',
    'TLT': 'Treasury Long',
    'UUP': 'US Dollar',
    'XLB': 'Basic Materials',
    'XLC': 'Communication Services',
    'XLE': 'Energy',
    'XLF': 'Financial Services',
    'XLI': 'Industrials',
    'XLK': 'Technology',
    'XLP': 'Consumer Defensive',
    'XLRE': 'Real Estate',
    'XLU': 'Utilities',
    'XLV': 'Healthcare',
    'XLY': 'Consumer Cyclical',
}

INSERT_SQL = text("""
    INSERT OR IGNORE INTO sector_etf_daily_returns
    (date, etf, sector, open, high, low, close, volume, pct_change)
    VALUES (:date, :etf, :sector, :open, :high, :low, :close, :volume, :pct_change)
""")

total_inserted = 0

for etf, sector in ETF_SECTOR.items():
    print(f"Downloading {etf} ({sector})...", end=" ", flush=True)
    df = yf.download(etf, start='2020-01-01', end='2022-01-01', progress=False)
    if df.empty:
        print("NO DATA")
        continue

    # Flatten multi-level columns if present
    if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
        df.columns = df.columns.get_level_values(0)

    # Compute pct_change
    df['pct_change'] = df['Close'].pct_change() * 100.0

    rows = []
    for dt, row in df.iterrows():
        if row['pct_change'] != row['pct_change']:  # skip NaN (first row)
            continue
        rows.append({
            'date': dt.strftime('%Y-%m-%d'),
            'etf': etf,
            'sector': sector,
            'open': round(float(row['Open']), 4),
            'high': round(float(row['High']), 4),
            'low': round(float(row['Low']), 4),
            'close': round(float(row['Close']), 4),
            'volume': int(row['Volume']),
            'pct_change': round(float(row['pct_change']), 4),
        })

    with get_session() as s:
        for r in rows:
            s.execute(INSERT_SQL, r)
        s.commit()

    total_inserted += len(rows)
    print(f"{len(rows)} rows")

# Final verification
with get_session() as s:
    row = s.execute(text("SELECT MIN(date), MAX(date), COUNT(*) FROM sector_etf_daily_returns")).fetchone()
    cnt_2020_2021 = s.execute(text(
        "SELECT COUNT(*) FROM sector_etf_daily_returns WHERE date < '2022-01-01'"
    )).fetchone()[0]

print(f"\nDone! Inserted {total_inserted} rows total.")
print(f"Table now: {row[0]} to {row[1]}, {row[2]} total rows")
print(f"2020-2021 rows: {cnt_2020_2021}")
