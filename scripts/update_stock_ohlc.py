#!/usr/bin/env python3
"""Daily update: download latest OHLC for all stocks in universe."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text

import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)



def main():
    # conn via get_session())

    # Get all symbols
    symbols = [r[0] for r in conn.execute('SELECT DISTINCT symbol FROM stock_fundamentals').fetchall()]
    logger.info(f"Updating OHLC for {len(symbols)} symbols")

    # Get last date in DB
    last = conn.execute('SELECT MAX(date) FROM stock_daily_ohlc').fetchone()[0]
    logger.info(f"Last date in DB: {last}")

    import yfinance as yf
    import time

    inserted = 0
    batch_size = 50
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        try:
            data = yf.download(' '.join(batch), period='5d', interval='1d',
                               auto_adjust=True, progress=False, threads=False)
            if data.empty:
                continue

            for sym in batch:
                try:
                    if len(batch) == 1:
                        df = data
                    else:
                        if sym not in data.columns.get_level_values(1):
                            continue
                        df = data.xs(sym, axis=1, level=1)

                    for date, row in df.iterrows():
                        dt = date.strftime('%Y-%m-%d')
                        if last and dt <= last:
                            continue
                        if row['Close'] > 0:
                            conn.execute("""
                                INSERT OR IGNORE INTO stock_daily_ohlc
                                (symbol, date, open, high, low, close, volume)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (sym, dt, float(row['Open']), float(row['High']),
                                  float(row['Low']), float(row['Close']),
                                  int(row['Volume']) if row['Volume'] else 0))
                            inserted += 1
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Batch error: {e}")

        if i + batch_size < len(symbols):
            time.sleep(1)
    logger.info(f"Done: {inserted} new rows inserted")


if __name__ == '__main__':
    main()
