#!/usr/bin/env python3
"""
Backfill options put/call ratio from Polygon.io (free tier).
Fetches near-money contracts per symbol, aggregates volume → put/call ratio per day.

Rate limit: 5 calls/min (free tier) → runs ~33 hours for 200 symbols.
Run: nohup python3 scripts/backfill_options_polygon.py &

Progress saved to DB — safe to restart (skips completed symbols).
"""
import sqlite3
import requests
import time
import sys
import os
from datetime import datetime, timedelta

API_KEY = 'AmAlwvIxff90cBG1yHUT8DFBE6m5d4Nj'
DB_PATH = 'data/trade_history.db'
START_DATE = '2024-04-01'
END_DATE = '2026-04-16'
RATE_DELAY = 13  # seconds between calls (5/min = 12s, add buffer)

def get_universe(conn, limit=200):
    return [r[0] for r in conn.execute(
        "SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT ?", (limit,))]

def get_completed(conn):
    try:
        return set(r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM options_polygon_history"))
    except:
        return set()

def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS options_polygon_history (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            call_volume INTEGER DEFAULT 0,
            put_volume INTEGER DEFAULT 0,
            put_call_ratio REAL,
            call_oi INTEGER DEFAULT 0,
            put_oi INTEGER DEFAULT 0,
            n_contracts INTEGER DEFAULT 0,
            PRIMARY KEY (symbol, date)
        )
    """)
    conn.commit()

def fetch_contracts(symbol, contract_type='call', limit=50):
    """Get near-money options contracts for symbol."""
    url = (f"https://api.polygon.io/v3/reference/options/contracts"
           f"?underlying_ticker={symbol}"
           f"&contract_type={contract_type}"
           f"&expired=true&limit={limit}"
           f"&order=desc&sort=expiration_date"
           f"&apiKey={API_KEY}")
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json().get('results', [])
        elif r.status_code == 429:
            print(f"    rate limited, sleeping 60s...")
            time.sleep(60)
            return fetch_contracts(symbol, contract_type, limit)
    except Exception as e:
        print(f"    error fetching contracts: {e}")
    return []

def fetch_history(ticker):
    """Get full daily bars for one options contract."""
    url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}"
           f"/range/1/day/{START_DATE}/{END_DATE}"
           f"?limit=50000&apiKey={API_KEY}")
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json().get('results', [])
        elif r.status_code == 429:
            print(f"    rate limited, sleeping 60s...")
            time.sleep(60)
            return fetch_history(ticker)
    except Exception as e:
        print(f"    error: {e}")
    return []

def ts_to_date(ts_ms):
    return datetime.fromtimestamp(ts_ms/1000).strftime('%Y-%m-%d')

def backfill_symbol(conn, symbol):
    """Backfill put/call ratio history for one symbol."""
    # Get contracts (calls + puts, near-money)
    calls = fetch_contracts(symbol, 'call', 30)
    time.sleep(RATE_DELAY)
    puts = fetch_contracts(symbol, 'put', 30)
    time.sleep(RATE_DELAY)

    if not calls and not puts:
        print(f"  {symbol}: no contracts found")
        return 0

    # Aggregate daily volume across contracts
    daily = {}  # date -> {call_vol, put_vol}

    for c in calls[:25]:  # limit to 25 contracts per side
        bars = fetch_history(c['ticker'])
        time.sleep(RATE_DELAY)
        for bar in bars:
            d = ts_to_date(bar['t'])
            if d not in daily:
                daily[d] = {'cv': 0, 'pv': 0, 'n': 0}
            daily[d]['cv'] += bar.get('v', 0)
            daily[d]['n'] += 1

    for p in puts[:25]:
        bars = fetch_history(p['ticker'])
        time.sleep(RATE_DELAY)
        for bar in bars:
            d = ts_to_date(bar['t'])
            if d not in daily:
                daily[d] = {'cv': 0, 'pv': 0, 'n': 0}
            daily[d]['pv'] += bar.get('v', 0)
            daily[d]['n'] += 1

    # Save to DB
    saved = 0
    for date, data in daily.items():
        cv = data['cv']; pv = data['pv']
        pc = pv / cv if cv > 0 else 0
        try:
            conn.execute(
                "INSERT OR REPLACE INTO options_polygon_history (symbol, date, call_volume, put_volume, put_call_ratio, n_contracts) VALUES (?,?,?,?,?,?)",
                (symbol, date, cv, pv, round(pc, 4), data['n']))
            saved += 1
        except:
            pass
    conn.commit()
    return saved

def main():
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    symbols = get_universe(conn, 200)
    completed = get_completed(conn)
    remaining = [s for s in symbols if s not in completed]

    print(f"Polygon Options Backfill")
    print(f"  Universe: {len(symbols)} symbols")
    print(f"  Completed: {len(completed)}")
    print(f"  Remaining: {len(remaining)}")
    print(f"  Rate: {RATE_DELAY}s/call (free tier)")
    print(f"  Est: ~{len(remaining) * 50 * RATE_DELAY / 3600:.1f} hours")
    print(f"  Start: {datetime.now()}")
    print()

    for i, sym in enumerate(remaining):
        t0 = time.time()
        print(f"[{i+1}/{len(remaining)}] {sym}...", end=' ', flush=True)
        days = backfill_symbol(conn, sym)
        elapsed = time.time() - t0
        print(f"{days} days saved ({elapsed:.0f}s)")

    # Summary
    total = conn.execute("SELECT COUNT(*), COUNT(DISTINCT symbol), COUNT(DISTINCT date) FROM options_polygon_history").fetchone()
    print(f"\nDone! Total: {total[0]} rows, {total[1]} symbols, {total[2]} dates")
    conn.close()

if __name__ == '__main__':
    main()
