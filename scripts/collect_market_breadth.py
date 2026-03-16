#!/usr/bin/env python3
"""
collect_market_breadth.py — v7.8
===================================
After market close: compute daily market breadth metrics across all universe stocks.
Stores in market_breadth table (one row per trading day).

Metrics:
  - pct_above_20d_ma   : % of stocks where close > 20-day MA
  - pct_above_50d_ma   : % of stocks where close > 50-day MA
  - advance_count      : stocks that closed higher than previous day
  - decline_count      : stocks that closed lower than previous day
  - unchanged_count    : flat
  - ad_ratio           : advance_count / decline_count
  - new_52w_highs      : stocks at 52-week high today
  - new_52w_lows       : stocks at 52-week low today
  - total_symbols      : total symbols processed

Why this matters for DIP strategy:
  - pct_above_20d_ma < 40% → broad market weakness → DIP less reliable
  - ad_ratio < 0.8 → more declines than advances → risk-off
  - new_52w_highs > new_52w_lows → healthy bull breadth

Cron (TZ=America/New_York):
  0 17 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_market_breadth.py >> logs/collect_market_breadth.log 2>&1
"""
import os
import sqlite3
import time
import argparse
from datetime import datetime, date, timedelta

import numpy as np
import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
ET = ZoneInfo('America/New_York')

BATCH_SIZE = 100    # symbols per yfinance batch download
HISTORY_DAYS = 280  # enough for 52w high + 50d MA


def _ensure_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_breadth (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL UNIQUE,
            pct_above_20d_ma    REAL,
            pct_above_50d_ma    REAL,
            advance_count   INTEGER,
            decline_count   INTEGER,
            unchanged_count INTEGER,
            ad_ratio        REAL,
            new_52w_highs   INTEGER,
            new_52w_lows    INTEGER,
            total_symbols   INTEGER,
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def download_daily_batch(symbols: list[str], start_dt: str, end_dt: str) -> dict[str, pd.DataFrame]:
    """Download daily bars for a batch of symbols. Returns {symbol: df}."""
    result = {}
    if not symbols:
        return result
    try:
        df = yf.download(symbols, start=start_dt, end=end_dt,
                         interval='1d', auto_adjust=True, progress=False,
                         group_by='ticker')
        if df is None or df.empty:
            return result

        if len(symbols) == 1:
            sym = symbols[0]
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                result[sym] = df
        else:
            for sym in symbols:
                try:
                    sym_df = df[sym].dropna(how='all')
                    if not sym_df.empty:
                        result[sym] = sym_df
                except Exception:
                    pass
    except Exception as e:
        print(f"    Batch error: {e}")
    return result


def compute_breadth_for_date(bars_map: dict[str, pd.DataFrame], target_date: str) -> dict | None:
    """Compute breadth metrics for target_date from bars_map."""
    target_dt = pd.Timestamp(target_date)
    high_52w_days = 252  # ~1 year of trading days

    above_20 = 0
    above_50 = 0
    advances = 0
    declines = 0
    unchanged = 0
    highs_52w = 0
    lows_52w = 0
    total = 0

    for sym, df in bars_map.items():
        try:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.index = pd.to_datetime(df.index)

            # Filter to up to target_date
            hist = df[df.index.date <= target_dt.date()]
            if hist.empty or len(hist) < 2:
                continue

            close = hist['Close'].values.astype(float)
            today_close = close[-1]

            if today_close <= 0:
                continue

            total += 1

            # Advance/decline vs previous day
            prev_close = close[-2]
            if today_close > prev_close * 1.001:
                advances += 1
            elif today_close < prev_close * 0.999:
                declines += 1
            else:
                unchanged += 1

            # 20d MA
            if len(close) >= 20:
                ma20 = np.mean(close[-20:])
                if today_close > ma20:
                    above_20 += 1

            # 50d MA
            if len(close) >= 50:
                ma50 = np.mean(close[-50:])
                if today_close > ma50:
                    above_50 += 1

            # 52w high / low
            window = close[-high_52w_days:]
            if len(window) >= 2:
                high_52w = float(window[:-1].max())   # exclude today to check if today broke out
                low_52w  = float(window[:-1].min())
                if today_close >= high_52w * 0.999:   # within 0.1% of 52w high
                    highs_52w += 1
                if today_close <= low_52w * 1.001:    # within 0.1% of 52w low
                    lows_52w += 1

        except Exception:
            continue

    if total == 0:
        return None

    return {
        'pct_above_20d_ma': round(above_20 / total * 100, 1),
        'pct_above_50d_ma': round(above_50 / total * 100, 1),
        'advance_count':    advances,
        'decline_count':    declines,
        'unchanged_count':  unchanged,
        'ad_ratio':         round(advances / declines, 3) if declines > 0 else None,
        'new_52w_highs':    highs_52w,
        'new_52w_lows':     lows_52w,
        'total_symbols':    total,
    }


def main():
    parser = argparse.ArgumentParser(description='Compute daily market breadth metrics')
    parser.add_argument('--date', default=None, help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--days', type=int, default=1,
                        help='Number of past days to compute (default: 1)')
    parser.add_argument('--force', action='store_true',
                        help='Overwrite existing rows for target dates')
    args = parser.parse_args()

    target_date = args.date or datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] collect_market_breadth "
          f"date={target_date} days={args.days}")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    _ensure_table(conn)

    # Build list of dates to compute
    base_dt = datetime.strptime(target_date, '%Y-%m-%d')
    dates_to_compute = [
        (base_dt - timedelta(days=i)).strftime('%Y-%m-%d')
        for i in range(args.days)
        if (base_dt - timedelta(days=i)).weekday() < 5
    ]

    # Skip dates already in DB (unless --force)
    if not args.force:
        existing = set(r[0] for r in conn.execute(
            "SELECT date FROM market_breadth WHERE date >= ?",
            (dates_to_compute[-1],)
        ).fetchall())
        dates_to_compute = [d for d in dates_to_compute if d not in existing]

    if not dates_to_compute:
        print("  All dates already in DB — done. Use --force to recompute.")
        conn.close()
        return

    print(f"  Computing breadth for {len(dates_to_compute)} date(s): {dates_to_compute}")

    # Get all active universe symbols
    symbols = [r[0] for r in conn.execute(
        "SELECT symbol FROM universe_stocks WHERE status='active' ORDER BY dollar_vol DESC"
    ).fetchall()]

    print(f"  {len(symbols)} universe symbols")

    # Download history (need enough for 52w MA)
    earliest_date = min(dates_to_compute)
    start_dt = (datetime.strptime(earliest_date, '%Y-%m-%d') - timedelta(days=HISTORY_DAYS)).strftime('%Y-%m-%d')
    end_dt = (base_dt + timedelta(days=1)).strftime('%Y-%m-%d')

    print(f"  Downloading {start_dt} to {end_dt} in batches of {BATCH_SIZE}...")

    # Collect all bars
    bars_map: dict[str, pd.DataFrame] = {}
    total_batches = (len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i+BATCH_SIZE]
        batch_bars = download_daily_batch(batch, start_dt, end_dt)
        bars_map.update(batch_bars)

        bn = i // BATCH_SIZE + 1
        print(f"  [{bn}/{total_batches}] {len(bars_map)} symbols downloaded so far")

        if i + BATCH_SIZE < len(symbols):
            time.sleep(0.3)

    print(f"  Downloaded {len(bars_map)} / {len(symbols)} symbols")

    # Compute breadth for each target date
    for d in dates_to_compute:
        metrics = compute_breadth_for_date(bars_map, d)
        if metrics is None:
            print(f"  {d}: no data — skipping")
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
        """, (d, metrics['pct_above_20d_ma'], metrics['pct_above_50d_ma'],
              metrics['advance_count'], metrics['decline_count'], metrics['unchanged_count'],
              metrics['ad_ratio'], metrics['new_52w_highs'], metrics['new_52w_lows'],
              metrics['total_symbols']))
        conn.commit()

        m = metrics
        print(f"  {d}: above20={m['pct_above_20d_ma']}% above50={m['pct_above_50d_ma']}% "
              f"A/D={m['advance_count']}/{m['decline_count']} "
              f"52wH/L={m['new_52w_highs']}/{m['new_52w_lows']} n={m['total_symbols']}")

    conn.close()
    print("  Done.")


if __name__ == '__main__':
    main()
