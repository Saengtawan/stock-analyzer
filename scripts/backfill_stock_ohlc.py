#!/usr/bin/env python3
"""
Backfill ALL stocks daily OHLC for the last 4 years.
Table: stock_daily_ohlc (symbol, date, open, high, low, close, volume)
Source: stock_fundamentals table for symbol list, yfinance for data.
"""
import sqlite3
import yfinance as yf
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'
BATCH_SIZE = 50
SLEEP_BETWEEN_BATCHES = 2


def create_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS stock_daily_ohlc (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            UNIQUE(symbol, date)
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_sdo_date ON stock_daily_ohlc(date)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_sdo_symbol ON stock_daily_ohlc(symbol, date)')
    conn.commit()


def get_symbols(conn):
    rows = conn.execute('SELECT DISTINCT symbol FROM stock_fundamentals ORDER BY symbol').fetchall()
    return [r[0] for r in rows]


def download_and_insert(conn, symbols, batch_num, total_batches):
    batch_str = ' '.join(symbols)
    logger.info(f"Batch {batch_num}/{total_batches}: downloading {len(symbols)} symbols...")

    try:
        df = yf.download(batch_str, period='4y', interval='1d', auto_adjust=True,
                         progress=False, threads=True, group_by='ticker')
    except Exception as e:
        logger.error(f"Batch {batch_num} download failed: {e}")
        return 0

    rows_inserted = 0

    if len(symbols) == 1:
        # Single symbol: df columns are Open/High/Low/Close/Volume directly
        sym = symbols[0]
        if df.empty:
            return 0
        for dt, row in df.iterrows():
            date_str = dt.strftime('%Y-%m-%d')
            try:
                conn.execute(
                    'INSERT OR IGNORE INTO stock_daily_ohlc (symbol, date, open, high, low, close, volume) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (sym, date_str, float(row['Open']), float(row['High']),
                     float(row['Low']), float(row['Close']), int(row['Volume']))
                )
                rows_inserted += 1
            except Exception:
                pass
    else:
        # Multi-symbol: df has multi-level columns (ticker, field)
        for sym in symbols:
            try:
                sym_df = df[sym] if sym in df.columns.get_level_values(0) else None
            except Exception:
                sym_df = None

            if sym_df is None or sym_df.empty:
                continue

            # Drop rows where Close is NaN (no data for that date)
            sym_df = sym_df.dropna(subset=['Close'])

            for dt, row in sym_df.iterrows():
                date_str = dt.strftime('%Y-%m-%d')
                try:
                    conn.execute(
                        'INSERT OR IGNORE INTO stock_daily_ohlc (symbol, date, open, high, low, close, volume) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (sym, date_str, float(row['Open']), float(row['High']),
                         float(row['Low']), float(row['Close']), int(row['Volume']))
                    )
                    rows_inserted += 1
                except Exception:
                    pass

    conn.commit()
    logger.info(f"Batch {batch_num}: inserted {rows_inserted} rows")
    return rows_inserted


def main():
    conn = None  # via get_session())
    create_table(conn)

    symbols = get_symbols(conn)
    logger.info(f"Total symbols: {len(symbols)}")

    # Check existing count
    existing = conn.execute('SELECT COUNT(*) FROM stock_daily_ohlc').fetchone()[0]
    logger.info(f"Existing rows before backfill: {existing}")

    batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
    total_batches = len(batches)
    total_inserted = 0

    for i, batch in enumerate(batches, 1):
        inserted = download_and_insert(conn, batch, i, total_batches)
        total_inserted += inserted

        if i < total_batches:
            time.sleep(SLEEP_BETWEEN_BATCHES)

    # Final report
    total_rows = conn.execute('SELECT COUNT(*) FROM stock_daily_ohlc').fetchone()[0]
    total_symbols = conn.execute('SELECT COUNT(DISTINCT symbol) FROM stock_daily_ohlc').fetchone()[0]
    date_range = conn.execute(
        'SELECT MIN(date), MAX(date) FROM stock_daily_ohlc'
    ).fetchone()

    logger.info("=" * 60)
    logger.info(f"BACKFILL COMPLETE")
    logger.info(f"  Total rows in table: {total_rows}")
    logger.info(f"  Rows inserted this run: {total_inserted}")
    logger.info(f"  Symbols with data: {total_symbols}")
    logger.info(f"  Date range: {date_range[0]} to {date_range[1]}")
    logger.info("=" * 60)

    conn.close()


if __name__ == '__main__':
    main()
