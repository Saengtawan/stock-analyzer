#!/usr/bin/env python3
"""
collect_sector_etf_returns.py — v7.8
=====================================
Download daily OHLCV for SPY + 11 sector ETFs and store in sector_etf_daily_returns.
Also computes vs_spy (sector pct_change - SPY pct_change) for relative strength.

ETFs covered:
  SPY, XLK, XLF, XLV, XLY, XLP, XLE, XLI, XLB, XLRE, XLU, XLC

Analysis enabled:
  - "Was sector up the day before OVN entry → better next-day performance?"
  - "DIP sector down >1% on signal day → falling knife?"
  - "PEM sector up on earnings day → confirms momentum?"
  - "Sector relative strength vs SPY → sector rotation signal"

Cron (TZ=America/New_York):
  10 17 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_sector_etf_returns.py >> logs/collect_sector_etf_returns.log 2>&1
"""
import os
import sqlite3
import argparse
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
ET = ZoneInfo('America/New_York')

SECTOR_ETFS = {
    'XLK':  'Technology',
    'XLF':  'Financial Services',
    'XLV':  'Healthcare',
    'XLY':  'Consumer Cyclical',
    'XLP':  'Consumer Defensive',
    'XLE':  'Energy',
    'XLI':  'Industrials',
    'XLB':  'Basic Materials',
    'XLRE': 'Real Estate',
    'XLU':  'Utilities',
    'XLC':  'Communication Services',
}

ALL_TICKERS = ['SPY'] + list(SECTOR_ETFS.keys())


def fetch_etf_data(start_date: str, end_date: str) -> pd.DataFrame:
    """Batch download daily OHLCV for all ETFs."""
    try:
        df = yf.download(
            ALL_TICKERS,
            start=start_date,
            end=end_date,
            interval='1d',
            auto_adjust=True,
            progress=False,
            group_by='ticker',
        )
        return df
    except Exception as e:
        print(f"  Download error: {e}")
        return pd.DataFrame()


def process_and_store(conn: sqlite3.Connection, df: pd.DataFrame):
    """Extract per-ticker rows and insert into DB."""
    if df is None or df.empty:
        print("  No data returned")
        return 0

    rows = []
    is_multi = isinstance(df.columns, pd.MultiIndex)

    # Get SPY closes first for vs_spy computation
    spy_closes: dict[str, float] = {}
    spy_opens: dict[str, float] = {}
    try:
        spy_df = df['SPY'] if is_multi else df
        for idx in spy_df.index:
            date_str = pd.Timestamp(idx).strftime('%Y-%m-%d')
            spy_opens[date_str] = float(spy_df.loc[idx, 'Open'])
            spy_closes[date_str] = float(spy_df.loc[idx, 'Close'])
    except Exception:
        pass

    for ticker in ALL_TICKERS:
        sector = 'S&P 500' if ticker == 'SPY' else SECTOR_ETFS.get(ticker, '')
        try:
            tdf = df[ticker] if is_multi else df
            if tdf.empty:
                continue

            for idx in tdf.index:
                try:
                    date_str = pd.Timestamp(idx).strftime('%Y-%m-%d')
                    row = tdf.loc[idx]
                    open_  = float(row['Open'])
                    high   = float(row['High'])
                    low    = float(row['Low'])
                    close  = float(row['Close'])
                    vol    = int(row['Volume']) if pd.notna(row['Volume']) else None

                    if open_ <= 0 or close <= 0:
                        continue

                    prev_close = None
                    # compute pct from previous row
                    loc = list(tdf.index).index(idx)
                    if loc > 0:
                        prev_idx = list(tdf.index)[loc - 1]
                        prev_close = float(tdf.loc[prev_idx, 'Close'])

                    pct_change = None
                    if prev_close and prev_close > 0:
                        pct_change = round((close / prev_close - 1) * 100, 4)

                    # vs_spy: sector pct - SPY pct
                    vs_spy = None
                    if pct_change is not None and ticker != 'SPY':
                        spy_open = spy_opens.get(date_str)
                        spy_close = spy_closes.get(date_str)
                        if spy_open and spy_close and spy_open > 0:
                            spy_prev_close = None
                            spy_loc = list(df['SPY'].index).index(idx) if is_multi else None
                            if spy_loc is not None and spy_loc > 0:
                                spy_prev_idx = list(df['SPY'].index)[spy_loc - 1]
                                spy_prev_close = float(df['SPY'].loc[spy_prev_idx, 'Close'])
                            if spy_prev_close and spy_prev_close > 0:
                                spy_pct = (spy_close / spy_prev_close - 1) * 100
                                vs_spy = round(pct_change - spy_pct, 4)

                    rows.append((date_str, ticker, sector,
                                 round(open_, 4), round(high, 4),
                                 round(low, 4), round(close, 4),
                                 vol, pct_change, vs_spy))
                except Exception:
                    continue
        except Exception:
            continue

    if rows:
        conn.executemany("""
            INSERT OR IGNORE INTO sector_etf_daily_returns
                (date, etf, sector, open, high, low, close, volume, pct_change, vs_spy)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, rows)
        conn.commit()
        print(f"  Inserted {len(rows)} rows")

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description='Collect sector ETF daily returns')
    parser.add_argument('--date', default=None, help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--days', type=int, default=1, help='Days to backfill (default: 1)')
    parser.add_argument('--backfill', type=int, default=None,
                        help='Backfill N calendar days from today')
    args = parser.parse_args()

    today = datetime.now(ET).date()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] collect_sector_etf_returns")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    if args.backfill:
        days = args.backfill
    else:
        days = args.days

    if args.date:
        base = datetime.strptime(args.date, '%Y-%m-%d').date()
    else:
        base = today

    # yfinance end date is exclusive, so +1 day
    end_dt   = base + timedelta(days=1)
    start_dt = base - timedelta(days=days + 5)  # buffer for weekends

    start_str = start_dt.strftime('%Y-%m-%d')
    end_str   = end_dt.strftime('%Y-%m-%d')

    print(f"  Fetching {start_str} → {end_str} ({len(ALL_TICKERS)} tickers)")
    df = fetch_etf_data(start_str, end_str)
    inserted = process_and_store(conn, df)

    conn.close()
    print(f"  Done. {inserted} rows inserted.")


if __name__ == '__main__':
    main()
