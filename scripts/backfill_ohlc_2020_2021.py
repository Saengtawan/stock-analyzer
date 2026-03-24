#!/usr/bin/env python3
"""
Backfill stock_daily_ohlc for 2020-01-01 to 2022-03-20.
Fills the gap before existing data (which starts 2022-03-21).
Uses universe_stocks + stock_fundamentals for symbol list.
"""
import sqlite3
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

import yfinance as yf
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'
BATCH_SIZE = 50
SLEEP_BETWEEN = 2  # seconds between batches
START_DATE = '2020-01-01'
END_DATE = '2022-03-21'  # exclusive end for yfinance


def get_symbols(conn):
    """Get all symbols from universe + fundamentals."""
    rows = conn.execute('''
        SELECT DISTINCT symbol FROM (
            SELECT symbol FROM universe_stocks
            UNION
            SELECT symbol FROM stock_fundamentals
        ) ORDER BY symbol
    ''').fetchall()
    return [r[0] for r in rows]


def get_existing_symbols(conn):
    """Symbols that already have data in the backfill range."""
    rows = conn.execute('''
        SELECT DISTINCT symbol FROM stock_daily_ohlc
        WHERE date >= ? AND date < ?
    ''', (START_DATE, END_DATE)).fetchall()
    return set(r[0] for r in rows)


def download_batch(symbols, start, end):
    """Download OHLC for a batch of symbols."""
    try:
        df = yf.download(
            symbols, start=start, end=end,
            interval='1d', auto_adjust=True,
            progress=False, threads=True, group_by='ticker'
        )
        if df is None or df.empty:
            return {}

        result = {}
        if len(symbols) == 1:
            sym = symbols[0]
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=['Close'])
            if not df.empty:
                result[sym] = df
        else:
            for sym in symbols:
                try:
                    if sym in df.columns.get_level_values(0):
                        sym_df = df[sym].dropna(subset=['Close'])
                        if not sym_df.empty:
                            result[sym] = sym_df
                except Exception:
                    pass
        return result
    except Exception as e:
        logger.error(f"Batch download error: {e}")
        return {}


def insert_ohlc(conn, symbol, df):
    """Insert OHLC rows, skip existing."""
    rows = 0
    for dt, row in df.iterrows():
        date_str = dt.strftime('%Y-%m-%d')
        try:
            conn.execute(
                'INSERT OR IGNORE INTO stock_daily_ohlc '
                '(symbol, date, open, high, low, close, volume) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (symbol, date_str,
                 float(row['Open']), float(row['High']),
                 float(row['Low']), float(row['Close']),
                 int(row['Volume']) if pd.notna(row['Volume']) else 0)
            )
            rows += 1
        except Exception:
            pass
    return rows


def main():
    conn = sqlite3.connect(str(DB_PATH), timeout=60)

    # Ensure table + indexes exist
    conn.execute('''
        CREATE TABLE IF NOT EXISTS stock_daily_ohlc (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER,
            UNIQUE(symbol, date)
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_sdo_date ON stock_daily_ohlc(date)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_sdo_symbol ON stock_daily_ohlc(symbol, date)')
    conn.commit()

    all_symbols = get_symbols(conn)
    existing = get_existing_symbols(conn)

    # Filter to symbols that don't already have data in the range
    symbols = [s for s in all_symbols if s not in existing]

    logger.info(f"Total symbols: {len(all_symbols)}, already have data: {len(existing)}, to download: {len(symbols)}")

    if not symbols:
        logger.info("All symbols already backfilled!")
        conn.close()
        return

    # Before count
    before = conn.execute('SELECT COUNT(*) FROM stock_daily_ohlc').fetchone()[0]

    batches = [symbols[i:i+BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
    total_batches = len(batches)
    total_inserted = 0
    symbols_done = 0

    for bn, batch in enumerate(batches, 1):
        t0 = time.time()
        bars = download_batch(batch, START_DATE, END_DATE)

        batch_rows = 0
        for sym, df in bars.items():
            rows = insert_ohlc(conn, sym, df)
            batch_rows += rows
        conn.commit()

        symbols_done += len(batch)
        total_inserted += batch_rows
        elapsed = time.time() - t0

        logger.info(
            f"[{bn}/{total_batches}] {len(bars)}/{len(batch)} symbols, "
            f"+{batch_rows} rows, total={total_inserted}, "
            f"{elapsed:.1f}s, progress={symbols_done}/{len(symbols)}"
        )

        if bn < total_batches:
            time.sleep(SLEEP_BETWEEN)

    # Final stats
    after = conn.execute('SELECT COUNT(*) FROM stock_daily_ohlc').fetchone()[0]
    date_range = conn.execute(
        'SELECT MIN(date), MAX(date) FROM stock_daily_ohlc'
    ).fetchone()
    sym_count = conn.execute(
        'SELECT COUNT(DISTINCT symbol) FROM stock_daily_ohlc WHERE date < ?',
        (END_DATE,)
    ).fetchone()[0]

    logger.info("=" * 60)
    logger.info(f"BACKFILL COMPLETE: {START_DATE} to {END_DATE}")
    logger.info(f"  Rows before: {before:,}")
    logger.info(f"  Rows after:  {after:,}")
    logger.info(f"  Rows added:  {after - before:,}")
    logger.info(f"  Symbols in range: {sym_count}")
    logger.info(f"  Full date range: {date_range[0]} to {date_range[1]}")
    logger.info("=" * 60)

    conn.close()


if __name__ == '__main__':
    main()
