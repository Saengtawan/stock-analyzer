#!/usr/bin/env python3
"""
fill_trade_mfe_mae.py — v7.6
==============================
Fill mfe_pct and mae_pct for BUY trades using yfinance 1m bars over hold period.

  mfe_pct = (max_high_during_hold / entry_price - 1) × 100  [best gain available]
  mae_pct = (1 - min_low_during_hold / entry_price) × 100   [worst drawdown seen]

These are critical for backtesting simulation:
  - MFE shows "how much headroom did we have?" → validates TP/trailing stop settings
  - MAE shows "how close did we get to SL?" → validates SL placement

Hold period = entry BUY date to SELL date (inclusive).
Uses signal_candidate_bars first (fast, in-DB), falls back to yfinance download.

Cron (TZ=America/New_York):
  0 22 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_trade_mfe_mae.py >> logs/fill_trade_mfe_mae.log 2>&1
"""
import os
import sqlite3
import time
from datetime import datetime, timedelta
import argparse

import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
ET = ZoneInfo('America/New_York')


def get_hold_dates(entry_date: str, exit_date: str | None) -> list[str]:
    """Get all calendar dates from entry to exit (inclusive)."""
    start = datetime.strptime(entry_date, '%Y-%m-%d')
    end = datetime.strptime(exit_date, '%Y-%m-%d') if exit_date else start + timedelta(days=5)
    dates = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # weekdays only
            dates.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)
    return dates


def get_hold_bars_from_db(conn: sqlite3.Connection, symbol: str,
                          dates: list[str]) -> tuple[float | None, float | None]:
    """Get max_high and min_low from signal_candidate_bars for hold period."""
    if not dates:
        return None, None
    placeholders = ','.join('?' * len(dates))
    row = conn.execute(f"""
        SELECT MAX(high) as max_high, MIN(low) as min_low
        FROM signal_candidate_bars
        WHERE symbol = ? AND date IN ({placeholders})
    """, [symbol] + dates).fetchone()
    if row and row[0] is not None:
        return float(row[0]), float(row[1])
    return None, None


def get_hold_bars_from_yfinance(symbol: str, entry_date: str,
                                 exit_date: str | None) -> tuple[float | None, float | None]:
    """Download 1m bars for hold period from yfinance (fallback)."""
    try:
        start = entry_date
        end_dt = datetime.strptime(exit_date or entry_date, '%Y-%m-%d') + timedelta(days=1)
        end = end_dt.strftime('%Y-%m-%d')
        df = yf.download(symbol, start=start, end=end,
                         interval='1m', auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None, None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return float(df['High'].max()), float(df['Low'].min())
    except Exception:
        return None, None


def main():
    parser = argparse.ArgumentParser(description='Fill MFE/MAE for BUY trades')
    parser.add_argument('--days', type=int, default=30,
                        help='Look back N days for trades (default: 30)')
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] fill_trade_mfe_mae days={args.days}")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    cutoff = (datetime.now(ET) - timedelta(days=args.days)).strftime('%Y-%m-%d')

    # Get BUY trades missing MFE/MAE
    buys = conn.execute("""
        SELECT b.id, b.symbol, b.date as entry_date, b.price as entry_price,
               s.date as exit_date
        FROM trades b
        LEFT JOIN trades s ON s.symbol = b.symbol
                           AND s.action = 'SELL'
                           AND s.date >= b.date
                           AND s.date <= date(b.date, '+10 days')
        WHERE b.action = 'BUY'
          AND b.date >= ?
          AND b.mfe_pct IS NULL
          AND b.price IS NOT NULL AND b.price > 0
        GROUP BY b.id
        ORDER BY b.date DESC
    """, (cutoff,)).fetchall()

    if not buys:
        print("  Nothing to fill.")
        conn.close()
        return

    print(f"  {len(buys)} BUY trades to fill")
    updated = 0
    db_hits = 0
    yf_hits = 0

    for trade in buys:
        sym = trade['symbol']
        entry_price = float(trade['entry_price'])
        entry_date = trade['entry_date']
        exit_date = trade['exit_date']

        hold_dates = get_hold_dates(entry_date, exit_date)

        # Try DB first (fast)
        max_high, min_low = get_hold_bars_from_db(conn, sym, hold_dates)

        if max_high is None:
            # Fallback to yfinance
            max_high, min_low = get_hold_bars_from_yfinance(sym, entry_date, exit_date)
            if max_high is not None:
                yf_hits += 1
            time.sleep(0.1)
        else:
            db_hits += 1

        if max_high is None or min_low is None:
            continue

        mfe = round((max_high / entry_price - 1) * 100, 3)
        mae = round((1 - min_low / entry_price) * 100, 3)

        conn.execute(
            "UPDATE trades SET mfe_pct = ?, mae_pct = ? WHERE id = ?",
            (mfe, mae, trade['id'])
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f"  Updated {updated}/{len(buys)} trades "
          f"(from DB: {db_hits}, from yfinance: {yf_hits})")
    print(f"  Done.")


if __name__ == '__main__':
    main()
