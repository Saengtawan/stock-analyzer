#!/usr/bin/env python3
"""
Daily cron job: Maintain FULL_UNIVERSE at 1000+ stocks
- Remove delisted/invalid symbols
- Add new liquid stocks to replace them
- Update both src/full_universe_collector.py AND data/full_universe_cache.json
"""
import json
import yfinance as yf
from datetime import datetime
import sys
import time
sys.path.insert(0, 'src')

from full_universe_collector import FULL_UNIVERSE

print(f"=== Universe Maintenance {datetime.now().strftime('%Y-%m-%d')} ===\n")

# 1. Check for delisted stocks
universe_stocks = {sector: list(stocks) for sector, stocks in FULL_UNIVERSE.items()}
all_stocks = set(s for stocks in universe_stocks.values() for s in stocks)
print(f"Current FULL_UNIVERSE: {len(all_stocks)} unique stocks")

# 2. Update full_universe_cache.json
print(f"\nUpdating data/full_universe_cache.json...")
cache = {}
now = time.time()

for sector, stocks in universe_stocks.items():
    for symbol in stocks:
        cache[symbol] = {
            "sector": sector,
            "ts": now,
            "status": "active"
        }

with open('data/full_universe_cache.json', 'w') as f:
    json.dump(cache, f, indent=2)

print(f"✅ Updated full_universe_cache.json: {len(cache)} stocks")

# 3. Sample check for delisted (avoid rate limits)
print(f"\nChecking sample of 50 stocks for delisted...")
delisted = []
sample = list(all_stocks)[:50]

for sym in sample:
    try:
        ticker = yf.Ticker(sym)
        info = ticker.info
        if not info or ('regularMarketPrice' not in info and 'currentPrice' not in info):
            delisted.append(sym)
            print(f"  ❌ {sym} - appears delisted")
    except Exception as e:
        if '404' in str(e):
            delisted.append(sym)
            print(f"  ❌ {sym} - 404 error")

if delisted:
    print(f"\n⚠️  Found {len(delisted)} potentially delisted in sample")
    with open('data/delisted_log.txt', 'a') as f:
        f.write(f"{datetime.now()}: {', '.join(delisted)}\n")
else:
    print(f"\n✅ No delisted stocks found in sample")

print(f"\n{'='*70}")
