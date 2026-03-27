#!/usr/bin/env python3
"""
Backfill market_breadth from stock_daily_ohlc data in DB.
Computes pct_above_20d_ma, pct_above_50d_ma, advance/decline,
52w highs/lows for each trading day 2020-01-02 to 2022-02-20.

No yfinance downloads needed — all computed from existing OHLC.
"""
import sqlite3
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'


def get_trading_days_to_fill(conn, start='2020-01-02', end='2022-02-21'):
    """Get trading days from OHLC that are NOT in market_breadth."""
    existing = set(r[0] for r in conn.execute(
        "SELECT date FROM market_breadth WHERE date >= ? AND date <= ?",
        (start, end)
    ).fetchall())

    trading_days = sorted(set(r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM stock_daily_ohlc WHERE date >= ? AND date <= ? ORDER BY date",
        (start, end)
    ).fetchall()))

    to_fill = [d for d in trading_days if d not in existing]
    logger.info(f"Trading days in range: {len(trading_days)}, already in DB: {len(existing)}, to fill: {len(to_fill)}")
    return to_fill


def load_all_ohlc(conn, min_date):
    """Load all OHLC data from min_date onward into memory for fast access.
    Returns: {symbol: [(date, open, high, low, close, volume), ...]} sorted by date.
    """
    logger.info(f"Loading OHLC data from {min_date}...")
    rows = conn.execute(
        "SELECT symbol, date, open, high, low, close, volume "
        "FROM stock_daily_ohlc WHERE date >= ? ORDER BY symbol, date",
        (min_date,)
    ).fetchall()

    data = defaultdict(list)
    for sym, dt, o, h, l, c, v in rows:
        data[sym].append((dt, o, h, l, c, v))

    logger.info(f"Loaded {len(rows):,} rows for {len(data)} symbols")
    return data


def compute_breadth(ohlc_data, target_date):
    """Compute breadth metrics for a single target_date.
    ohlc_data: {symbol: [(date, o, h, l, c, v), ...]} already sorted by date.
    """
    above_20 = 0
    above_50 = 0
    advances = 0
    declines = 0
    unchanged = 0
    highs_52w = 0
    lows_52w = 0
    total = 0

    for sym, rows in ohlc_data.items():
        # Get all rows up to target_date
        hist = [r for r in rows if r[0] <= target_date]
        if len(hist) < 2:
            continue

        closes = [r[4] for r in hist]  # close prices
        today_close = closes[-1]
        if today_close is None or today_close <= 0:
            continue

        # Must be ON target_date
        if hist[-1][0] != target_date:
            continue

        total += 1

        # Advance/decline
        prev_close = closes[-2]
        if prev_close and prev_close > 0:
            if today_close > prev_close * 1.001:
                advances += 1
            elif today_close < prev_close * 0.999:
                declines += 1
            else:
                unchanged += 1

        # 20d MA
        if len(closes) >= 20:
            ma20 = np.mean(closes[-20:])
            if today_close > ma20:
                above_20 += 1

        # 50d MA
        if len(closes) >= 50:
            ma50 = np.mean(closes[-50:])
            if today_close > ma50:
                above_50 += 1

        # 52w high/low (~252 trading days)
        window = closes[-252:]
        if len(window) >= 2:
            high_52w = max(window[:-1])
            low_52w = min(window[:-1])
            if high_52w and today_close >= high_52w * 0.999:
                highs_52w += 1
            if low_52w and today_close <= low_52w * 1.001:
                lows_52w += 1

    if total == 0:
        return None

    return {
        'pct_above_20d_ma': round(above_20 / total * 100, 1),
        'pct_above_50d_ma': round(above_50 / total * 100, 1),
        'advance_count': advances,
        'decline_count': declines,
        'unchanged_count': unchanged,
        'ad_ratio': round(advances / declines, 3) if declines > 0 else None,
        'new_52w_highs': highs_52w,
        'new_52w_lows': lows_52w,
        'total_symbols': total,
    }


def main():
    conn = None  # via get_session(), timeout=60)

    # Get days to fill
    days_to_fill = get_trading_days_to_fill(conn)
    if not days_to_fill:
        logger.info("No days to fill!")
        conn.close()
        return

    # Load all OHLC data (need 252 trading days before earliest target for 52w calcs)
    # Earliest target ~ 2020-01-02, so load from ~2019-01-01
    earliest = days_to_fill[0]
    load_from = f"{int(earliest[:4])-1}-01-01"
    ohlc_data = load_all_ohlc(conn, load_from)

    before = conn.execute("SELECT COUNT(*) FROM market_breadth").fetchone()[0]

    # Process each day
    for i, day in enumerate(days_to_fill):
        metrics = compute_breadth(ohlc_data, day)
        if metrics is None:
            logger.warning(f"  {day}: no data")
            continue

        conn.execute("""
            INSERT INTO market_breadth
                (date, pct_above_20d_ma, pct_above_50d_ma,
                 advance_count, decline_count, unchanged_count,
                 ad_ratio, new_52w_highs, new_52w_lows, total_symbols)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(date) DO UPDATE SET
                pct_above_20d_ma = excluded.pct_above_20d_ma,
                pct_above_50d_ma = excluded.pct_above_50d_ma,
                advance_count    = excluded.advance_count,
                decline_count    = excluded.decline_count,
                unchanged_count  = excluded.unchanged_count,
                ad_ratio         = excluded.ad_ratio,
                new_52w_highs    = excluded.new_52w_highs,
                new_52w_lows     = excluded.new_52w_lows,
                total_symbols    = excluded.total_symbols,
                updated_at       = datetime('now')
        """, (day, metrics['pct_above_20d_ma'], metrics['pct_above_50d_ma'],
              metrics['advance_count'], metrics['decline_count'], metrics['unchanged_count'],
              metrics['ad_ratio'], metrics['new_52w_highs'], metrics['new_52w_lows'],
              metrics['total_symbols']))

        if (i + 1) % 50 == 0 or i == len(days_to_fill) - 1:
            conn.commit()
            m = metrics
            logger.info(
                f"  [{i+1}/{len(days_to_fill)}] {day}: "
                f"above20={m['pct_above_20d_ma']}% A/D={m['advance_count']}/{m['decline_count']} "
                f"52wH/L={m['new_52w_highs']}/{m['new_52w_lows']} n={m['total_symbols']}"
            )

    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM market_breadth").fetchone()[0]

    # Verify
    date_range = conn.execute("SELECT MIN(date), MAX(date) FROM market_breadth").fetchone()
    logger.info("=" * 60)
    logger.info(f"BREADTH BACKFILL COMPLETE")
    logger.info(f"  Rows before: {before}")
    logger.info(f"  Rows after:  {after}")
    logger.info(f"  Rows added:  {after - before}")
    logger.info(f"  Date range:  {date_range[0]} to {date_range[1]}")
    logger.info("=" * 60)

    conn.close()


if __name__ == '__main__':
    main()
