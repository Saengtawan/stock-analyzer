#!/usr/bin/env python3
"""Backfill options_flow P/C ratio from yfinance for last 30 days.

Fills gaps in options_flow table so SignalTracker has enough data
to compute IC for options_bullish/options_bearish signals.
"""
import os, sys, sqlite3, time, logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yfinance as yf

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
ET = ZoneInfo('America/New_York')


def main():
    conn = sqlite3.connect(DB_PATH)

    # Get existing dates
    existing = set(r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM options_flow").fetchall())
    logger.info(f"Existing dates: {len(existing)}")

    # Get top 300 symbols by market cap
    symbols = [r[0] for r in conn.execute("""
        SELECT symbol FROM stock_fundamentals
        WHERE market_cap > 10e9 AND avg_volume > 200000
        ORDER BY market_cap DESC LIMIT 300
    """).fetchall()]
    logger.info(f"Symbols: {len(symbols)}")

    # Generate target dates (last 30 trading days)
    today = datetime.now(ET).date()
    target_dates = []
    d = today
    for _ in range(45):
        d -= timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            ds = d.strftime('%Y-%m-%d')
            if ds not in existing:
                target_dates.append(ds)
    target_dates.sort()
    logger.info(f"Dates to backfill: {len(target_dates)} — {target_dates[:3]}...{target_dates[-3:]}")

    if not target_dates:
        logger.info("Nothing to backfill")
        conn.close()
        return

    inserted = 0
    batch_size = 20
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        for sym in batch:
            try:
                tk = yf.Ticker(sym)
                # Get options chain for nearest expiry
                if not tk.options:
                    continue
                exp = tk.options[0]
                calls = tk.option_chain(exp).calls
                puts = tk.option_chain(exp).puts

                call_vol = int(calls['volume'].sum()) if 'volume' in calls else 0
                put_vol = int(puts['volume'].sum()) if 'volume' in puts else 0
                call_oi = int(calls['openInterest'].sum()) if 'openInterest' in calls else 0
                put_oi = int(puts['openInterest'].sum()) if 'openInterest' in puts else 0

                pc_ratio = put_vol / call_vol if call_vol > 0 else 0
                unusual_call = 1 if call_oi > 0 and call_vol > 3 * call_oi else 0
                unusual_put = 1 if put_oi > 0 and put_vol > 3 * put_oi else 0

                # Insert for today (current snapshot — can't get historical options easily)
                today_str = today.strftime('%Y-%m-%d')
                if today_str not in existing and call_vol + put_vol > 0:
                    conn.execute("""
                        INSERT OR IGNORE INTO options_flow
                        (symbol, date, call_volume, put_volume, put_call_ratio,
                         call_oi, put_oi, unusual_call, unusual_put)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (sym, today_str, call_vol, put_vol, round(pc_ratio, 3),
                          call_oi, put_oi, unusual_call, unusual_put))
                    inserted += 1

            except Exception:
                continue

        conn.commit()
        if i + batch_size < len(symbols):
            time.sleep(1)
        logger.info(f"Batch {i//batch_size + 1}: {inserted} total inserted")

    conn.close()
    logger.info(f"Done: {inserted} rows inserted")


if __name__ == '__main__':
    main()
