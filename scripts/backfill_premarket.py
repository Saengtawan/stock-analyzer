#!/usr/bin/env python3
"""
Backfill pre-market data from Alpaca for backfill signal dates.
For each (scan_date, symbol) in backfill_signal_outcomes:
  - Fetch 4:00-9:30 AM ET bars from Alpaca
  - Compute: PM volume, PM return, PM gap from prev close

Stores in premarket_features table.
Rate limit: 200 req/min on Alpaca free tier.
"""
import sqlite3
import os
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

DB = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# Load Alpaca keys from .env
ENV_FILE = Path(__file__).resolve().parents[1] / '.env'
api_key = api_secret = None
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith('ALPACA_API_KEY='):
            api_key = line.split('=', 1)[1].strip().strip('"').strip("'")
        elif line.startswith('ALPACA_SECRET_KEY='):
            api_secret = line.split('=', 1)[1].strip().strip('"').strip("'")

if not api_key or not api_secret:
    api_key = os.environ.get('ALPACA_API_KEY')
    api_secret = os.environ.get('ALPACA_SECRET_KEY')

HEADERS = {
    'APCA-API-KEY-ID': api_key or '',
    'APCA-API-SECRET-KEY': api_secret or '',
}
BASE_URL = 'https://data.alpaca.markets/v2/stocks'


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS premarket_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            pm_volume INTEGER,
            pm_return_pct REAL,
            pm_high REAL,
            pm_low REAL,
            pm_vwap REAL,
            pm_bar_count INTEGER,
            prev_close REAL,
            pm_gap_pct REAL,
            UNIQUE(scan_date, symbol)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pmf_date ON premarket_features(scan_date)")
    conn.commit()


def fetch_premarket(symbol, date_str):
    """Fetch pre-market bars (4AM-9:30AM ET) for a specific date."""
    # Convert to UTC: 4AM ET = 9AM UTC (or 8AM during DST)
    # Use wide window and let Alpaca handle timezone
    start = f"{date_str}T08:00:00Z"  # ~4AM ET (conservative)
    end = f"{date_str}T13:30:00Z"    # 9:30AM ET

    params = {
        'start': start,
        'end': end,
        'timeframe': '5Min',
        'limit': 100,
        'adjustment': 'split',
    }

    try:
        resp = requests.get(f"{BASE_URL}/{symbol}/bars",
                            headers=HEADERS, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            bars = data.get('bars', [])
            return bars
        elif resp.status_code == 422:
            return []  # no data for this date
        else:
            return None
    except Exception:
        return None


def compute_pm_features(bars, prev_close):
    """Compute pre-market summary features from 5-min bars."""
    if not bars:
        return None

    total_vol = sum(b.get('v', 0) for b in bars)
    if total_vol == 0:
        return None

    first_open = bars[0].get('o', 0)
    last_close = bars[-1].get('c', 0)
    high = max(b.get('h', 0) for b in bars)
    low = min(b.get('l', 999999) for b in bars)

    vwap_num = sum(b.get('vw', b.get('c', 0)) * b.get('v', 0) for b in bars)
    vwap = vwap_num / total_vol if total_vol > 0 else last_close

    pm_return = (last_close / first_open - 1) * 100 if first_open > 0 else 0
    pm_gap = (first_open / prev_close - 1) * 100 if prev_close and prev_close > 0 else 0

    return {
        'pm_volume': total_vol,
        'pm_return_pct': round(pm_return, 4),
        'pm_high': round(high, 2),
        'pm_low': round(low, 2),
        'pm_vwap': round(vwap, 2),
        'pm_bar_count': len(bars),
        'pm_gap_pct': round(pm_gap, 4),
    }


def main():
    if not api_key:
        print("ERROR: ALPACA_API_KEY not found in .env")
        return

    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    ensure_table(conn)

    # Get unique (date, symbol) pairs from backfill that we don't have yet
    # Limit to recent 2 years (Alpaca free tier historical limit)
    existing = set()
    for r in conn.execute("SELECT scan_date, symbol FROM premarket_features"):
        existing.add((r[0], r[1]))

    pairs = conn.execute("""
        SELECT DISTINCT b.scan_date, b.symbol, d0.close as prev_close
        FROM backfill_signal_outcomes b
        JOIN signal_daily_bars d0 ON b.scan_date = d0.scan_date
            AND b.symbol = d0.symbol AND d0.day_offset = 0
        JOIN stock_fundamentals sf ON b.symbol = sf.symbol
        WHERE b.outcome_5d IS NOT NULL
        AND sf.market_cap >= 30e9
        AND b.scan_date >= '2024-01-01'
        ORDER BY b.scan_date DESC
    """).fetchall()
    conn.close()

    todo = [(d, s, pc) for d, s, pc in pairs if (d, s) not in existing]
    print(f"Total pairs: {len(pairs):,}, already done: {len(existing):,}, todo: {len(todo):,}")

    if not todo:
        print("All done!")
        return

    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    total = 0
    errors = 0
    empty = 0
    t0 = time.time()

    # Batch by date for efficiency
    by_date = defaultdict(list)
    for d, s, pc in todo:
        by_date[d].append((s, pc))

    for di, (date_str, syms) in enumerate(sorted(by_date.items(), reverse=True)):
        for sym, prev_close in syms:
            bars = fetch_premarket(sym, date_str)

            if bars is None:
                errors += 1
            elif not bars:
                empty += 1
            else:
                features = compute_pm_features(bars, prev_close)
                if features:
                    conn.execute("""
                        INSERT OR IGNORE INTO premarket_features
                        (scan_date, symbol, pm_volume, pm_return_pct, pm_high, pm_low,
                         pm_vwap, pm_bar_count, prev_close, pm_gap_pct)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (date_str, sym, features['pm_volume'], features['pm_return_pct'],
                          features['pm_high'], features['pm_low'], features['pm_vwap'],
                          features['pm_bar_count'], prev_close, features['pm_gap_pct']))
                    total += 1

            # Rate limit: 200/min = ~3.3/sec
            time.sleep(0.35)

        conn.commit()

        if (di + 1) % 5 == 0:
            elapsed = time.time() - t0
            done = sum(len(v) for d, v in sorted(by_date.items(), reverse=True)[:di+1])
            rate = done / elapsed if elapsed > 0 else 0
            remaining = len(todo) - done
            eta = remaining / rate if rate > 0 else 0
            print(f"  dates [{di+1}/{len(by_date)}] +{total:,} rows, "
                  f"{empty:,} empty, {errors} errors, ETA {eta/60:.0f}min")

    conn.commit()
    final = conn.execute("SELECT COUNT(*) FROM premarket_features").fetchone()[0]
    print(f"\nDone: {total:,} new rows, {final:,} total in premarket_features")
    conn.close()


if __name__ == '__main__':
    main()
