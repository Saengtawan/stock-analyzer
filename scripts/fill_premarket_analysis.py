#!/usr/bin/env python3
"""
fill_premarket_analysis.py — v7.8
=====================================
Compute pre-market metrics for all signal candidates from signal_candidate_bars.
Stores in premarket_analysis table (one row per symbol/date).

Pre-market metrics computed:
  - prev_close          : previous day's close (from DB bars or yfinance)
  - premarket_gap_pct   : (9:30 open / prev_close - 1) x 100
  - premarket_high_pct  : (pm_high / prev_close - 1) x 100
  - premarket_low_pct   : (pm_low / prev_close - 1) x 100
  - premarket_vol       : sum volume 04:00-09:29
  - premarket_vol_ratio : pm_vol / (avg_daily_vol x 210/390)
  - first_5min_return   : (close[09:34] / open[09:30] - 1) x 100
  - first_30min_return  : (close[09:59] / open[09:30] - 1) x 100
  - open_vs_pm_high_pct : (open[09:30] / pm_high - 1) x 100 -> negative = faded from pm high

Analysis enabled:
  - "Did GAP stocks that held pm_high at open have better follow-through?"
  - "What first_5min_return threshold predicts continuation vs reversal?"
  - "Does high pre-market volume confirm gap quality?"
  - "Stocks with premarket_gap > 5% but first_5min_return < 0 -> fade setup"

Cron (TZ=America/New_York):
  50 16 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_premarket_analysis.py >> logs/fill_premarket_analysis.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import argparse
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')


def get_avg_daily_vol(session, symbol: str, before_date: str) -> float | None:
    """Estimate avg daily volume from signal_candidate_bars (last 20 regular-session days)."""
    rows = session.execute(text("""
        SELECT date, SUM(volume) AS day_vol
        FROM signal_candidate_bars
        WHERE symbol = :p0 AND date < :p1 AND time_et >= '09:30' AND time_et < '16:00'
        GROUP BY date
        ORDER BY date DESC
        LIMIT 20
    """), {'p0': symbol, 'p1': before_date}).fetchall()
    if not rows:
        return None
    vols = [r[1] for r in rows if r[1] and r[1] > 0]
    return float(sum(vols) / len(vols)) if vols else None


def compute_premarket(session, symbol: str, target_date: str) -> dict | None:
    """Compute pre-market metrics for one symbol/date from signal_candidate_bars."""
    # Load all bars for this symbol/date
    bars = session.execute(text("""
        SELECT time_et, open, high, low, close, volume
        FROM signal_candidate_bars
        WHERE symbol = :p0 AND date = :p1
        ORDER BY time_et
    """), {'p0': symbol, 'p1': target_date}).fetchall()

    if not bars:
        return None

    # Separate pre-market (04:00-09:29) and regular (09:30+)
    pm_bars = [b for b in bars if b[0] < '09:30']
    reg_bars = [b for b in bars if b[0] >= '09:30']

    if not reg_bars:
        return None

    # 9:30 bar = open of regular session
    open_bar = reg_bars[0]
    open_price = float(open_bar[1])   # open of 09:30 bar
    if open_price <= 0:
        return None

    # Pre-market summary
    pm_vol = sum(int(b[5]) for b in pm_bars if b[5]) if pm_bars else 0
    pm_high = max(float(b[2]) for b in pm_bars) if pm_bars else None
    pm_low  = min(float(b[3]) for b in pm_bars) if pm_bars else None

    # Get previous close: last regular-session close of the day before
    prev_bars = session.execute(text("""
        SELECT close FROM signal_candidate_bars
        WHERE symbol = :p0 AND date < :p1 AND time_et >= '09:30' AND time_et < '16:00'
        ORDER BY date DESC, time_et DESC
        LIMIT 1
    """), {'p0': symbol, 'p1': target_date}).fetchone()

    prev_close = float(prev_bars[0]) if prev_bars else None

    # Compute gap %
    premarket_gap_pct = None
    if prev_close and prev_close > 0:
        premarket_gap_pct = round((open_price / prev_close - 1) * 100, 3)

    premarket_high_pct = None
    premarket_low_pct  = None
    if prev_close and prev_close > 0:
        if pm_high:
            premarket_high_pct = round((pm_high / prev_close - 1) * 100, 3)
        if pm_low:
            premarket_low_pct  = round((pm_low / prev_close - 1) * 100, 3)

    # open vs pm_high (did open fade from pre-market high?)
    open_vs_pm_high_pct = None
    if pm_high and pm_high > 0:
        open_vs_pm_high_pct = round((open_price / pm_high - 1) * 100, 3)

    # Pre-market volume ratio
    premarket_vol_ratio = None
    avg_vol = get_avg_daily_vol(session, symbol, target_date)
    if avg_vol and avg_vol > 0 and pm_vol > 0:
        expected_pm_vol = avg_vol * (210 / 390)   # 4:00-9:30 = ~210 min
        premarket_vol_ratio = round(pm_vol / expected_pm_vol, 3)

    # First 5-min return: close[09:34] / open[09:30] - 1
    first_5min_bars = [b for b in reg_bars if '09:30' <= b[0] <= '09:34']
    first_5min_return = None
    first_5min_open = None
    first_5min_close = None
    first_5min_vol = None
    if first_5min_bars:
        first_5min_open  = float(first_5min_bars[0][1])
        first_5min_close = float(first_5min_bars[-1][4])
        first_5min_vol   = sum(int(b[5]) for b in first_5min_bars if b[5])
        if first_5min_open > 0:
            first_5min_return = round((first_5min_close / first_5min_open - 1) * 100, 3)

    # First 30-min return: close[09:59] / open[09:30] - 1
    first_30min_bars = [b for b in reg_bars if '09:30' <= b[0] <= '09:59']
    first_30min_return = None
    if first_30min_bars and first_5min_open and first_5min_open > 0:
        last_close = float(first_30min_bars[-1][4])
        first_30min_return = round((last_close / first_5min_open - 1) * 100, 3)

    return {
        'prev_close':          round(prev_close, 4) if prev_close else None,
        'premarket_gap_pct':   premarket_gap_pct,
        'premarket_high_pct':  premarket_high_pct,
        'premarket_low_pct':   premarket_low_pct,
        'premarket_vol':       pm_vol if pm_vol > 0 else None,
        'premarket_vol_ratio': premarket_vol_ratio,
        'first_5min_open':     round(first_5min_open, 4) if first_5min_open else None,
        'first_5min_close':    round(first_5min_close, 4) if first_5min_close else None,
        'first_5min_return':   first_5min_return,
        'first_5min_vol':      first_5min_vol,
        'first_30min_return':  first_30min_return,
        'open_vs_pm_high_pct': open_vs_pm_high_pct,
    }


def main():
    parser = argparse.ArgumentParser(description='Fill pre-market analysis from signal_candidate_bars')
    parser.add_argument('--date', default=None, help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--days', type=int, default=1,
                        help='Number of past days to fill (default: 1)')
    parser.add_argument('--symbol', default=None, help='Single symbol (for testing)')
    args = parser.parse_args()

    target_date = args.date or datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] fill_premarket_analysis "
          f"date={target_date} days={args.days}")

    with get_session() as session:

        base_dt = datetime.strptime(target_date, '%Y-%m-%d')
        dates = [
            (base_dt - timedelta(days=i)).strftime('%Y-%m-%d')
            for i in range(args.days)
            if (base_dt - timedelta(days=i)).weekday() < 5
        ]

        total_ok = 0
        total_skip = 0

        for d in dates:
            if args.symbol:
                symbols = [args.symbol.upper()]
            else:
                # All symbols with bars on this date, not yet analyzed
                rows = session.execute(text("""
                    SELECT DISTINCT symbol FROM signal_candidate_bars
                    WHERE date = :p0 AND symbol NOT IN (
                        SELECT symbol FROM premarket_analysis WHERE date = :p1
                    )
                """), {'p0': d, 'p1': d}).fetchall()
                symbols = [r[0] for r in rows]

            print(f"\n  --- {d} --- {len(symbols)} symbols to process")

            rows_to_insert = []
            for sym in symbols:
                data = compute_premarket(session, sym, d)
                if data and data.get('first_5min_return') is not None:
                    rows_to_insert.append((sym, d,
                        data['prev_close'], data['premarket_gap_pct'],
                        data['premarket_high_pct'], data['premarket_low_pct'],
                        data['premarket_vol'], data['premarket_vol_ratio'],
                        data['first_5min_open'], data['first_5min_close'],
                        data['first_5min_return'], data['first_5min_vol'],
                        data['first_30min_return'], data['open_vs_pm_high_pct'],
                    ))
                    total_ok += 1
                else:
                    total_skip += 1

            if rows_to_insert:
                for row_vals in rows_to_insert:
                    session.execute(text("""
                        INSERT OR IGNORE INTO premarket_analysis
                            (symbol, date, prev_close, premarket_gap_pct,
                             premarket_high_pct, premarket_low_pct,
                             premarket_vol, premarket_vol_ratio,
                             first_5min_open, first_5min_close,
                             first_5min_return, first_5min_vol,
                             first_30min_return, open_vs_pm_high_pct)
                        VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13)
                    """), {
                        'p0': row_vals[0], 'p1': row_vals[1], 'p2': row_vals[2],
                        'p3': row_vals[3], 'p4': row_vals[4], 'p5': row_vals[5],
                        'p6': row_vals[6], 'p7': row_vals[7], 'p8': row_vals[8],
                        'p9': row_vals[9], 'p10': row_vals[10], 'p11': row_vals[11],
                        'p12': row_vals[12], 'p13': row_vals[13],
                    })
                print(f"    Inserted {len(rows_to_insert)} rows")
        print(f"\n  Total: ok={total_ok} skipped={total_skip}")
        print("  Done.")


if __name__ == '__main__':
    main()
