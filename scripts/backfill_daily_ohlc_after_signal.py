#!/usr/bin/env python3
"""
Backfill daily OHLC for D+1 through D+5 after each signal.
Creates table: signal_daily_bars
Columns: scan_date, symbol, day_offset (1-5), open, high, low, close, volume

This enables:
- max_gain per day (intraday high)
- max_dd per day (intraday low)
- D+1 open gap (pre-market move)
- Precise TP/SL hit timing
"""
import sqlite3
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'


def create_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS signal_daily_bars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            day_offset INTEGER NOT NULL,  -- 0=signal day, 1-5=days after
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(scan_date, symbol, day_offset)
        )
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_sdb_symbol ON signal_daily_bars(symbol)
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_sdb_scan_date ON signal_daily_bars(scan_date)
    ''')
    conn.commit()


def get_signals_needing_bars(conn):
    """Get (scan_date, symbol) pairs that don't have bars yet."""
    cur = conn.cursor()
    cur.execute('''
        SELECT DISTINCT b.scan_date, b.symbol
        FROM backfill_signal_outcomes b
        LEFT JOIN signal_daily_bars s
            ON b.scan_date = s.scan_date AND b.symbol = s.symbol AND s.day_offset = 1
        WHERE s.id IS NULL
        ORDER BY b.symbol, b.scan_date
    ''')
    return cur.fetchall()


def get_trading_days_after(scan_date_str, n_days, trading_days_cache):
    """Get next N trading days after scan_date from cache."""
    if scan_date_str not in trading_days_cache:
        return []
    idx = trading_days_cache[scan_date_str]
    all_days = sorted(trading_days_cache.keys(), key=lambda x: trading_days_cache[x])
    result = []
    for d in all_days:
        if trading_days_cache[d] > idx and len(result) < n_days:
            result.append(d)
    return result


def backfill_symbol(conn, symbol, signals):
    """Download OHLC and fill bars for all signals of one symbol."""
    if not signals:
        return 0

    # Get date range needed
    min_date = min(s[0] for s in signals)
    max_date = max(s[0] for s in signals)

    # Download with extra buffer for D+5
    start = (datetime.strptime(min_date, '%Y-%m-%d') - timedelta(days=5)).strftime('%Y-%m-%d')
    end = (datetime.strptime(max_date, '%Y-%m-%d') + timedelta(days=15)).strftime('%Y-%m-%d')

    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    except Exception as e:
        logger.warning(f"  {symbol}: download failed: {e}")
        return 0

    if df.empty:
        return 0

    # Handle MultiIndex columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.index = pd.to_datetime(df.index).strftime('%Y-%m-%d')
    trading_dates = sorted(df.index.tolist())
    date_to_idx = {d: i for i, d in enumerate(trading_dates)}

    inserted = 0
    for scan_date, sym in signals:
        if scan_date not in date_to_idx:
            continue

        idx = date_to_idx[scan_date]

        for offset in range(0, 6):  # D+0 through D+5
            target_idx = idx + offset
            if target_idx >= len(trading_dates):
                break
            target_date = trading_dates[target_idx]
            row = df.loc[target_date]

            try:
                conn.execute('''
                    INSERT OR IGNORE INTO signal_daily_bars
                    (scan_date, symbol, day_offset, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (scan_date, symbol, offset,
                      float(row['Open']), float(row['High']),
                      float(row['Low']), float(row['Close']),
                      int(row['Volume']) if pd.notna(row['Volume']) else None))
                inserted += 1
            except Exception:
                pass

    conn.commit()
    return inserted


def main():
    conn = sqlite3.connect(str(DB_PATH))
    create_table(conn)

    # Get all signals needing bars
    needed = get_signals_needing_bars(conn)
    logger.info(f"Signals needing bars: {len(needed)}")

    if not needed:
        logger.info("All signals have bars. Done.")
        return

    # Group by symbol
    by_symbol = {}
    for scan_date, symbol in needed:
        by_symbol.setdefault(symbol, []).append((scan_date, symbol))

    logger.info(f"Unique symbols: {len(by_symbol)}")

    total_inserted = 0
    for i, (symbol, signals) in enumerate(sorted(by_symbol.items())):
        n = backfill_symbol(conn, symbol, signals)
        total_inserted += n
        if (i + 1) % 50 == 0:
            logger.info(f"  Progress: {i+1}/{len(by_symbol)} symbols, {total_inserted} bars inserted")

        # Rate limit: yfinance doesn't like rapid requests
        if (i + 1) % 10 == 0:
            time.sleep(1)

    # Verify
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM signal_daily_bars")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT scan_date || symbol) FROM signal_daily_bars WHERE day_offset = 1")
    signals_with_bars = cur.fetchone()[0]

    logger.info(f"\nDone! Total bars: {total}, Signals with D+1 bars: {signals_with_bars}")
    logger.info(f"Inserted this run: {total_inserted}")

    conn.close()


if __name__ == '__main__':
    main()
