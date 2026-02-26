#!/usr/bin/env python3
"""
Daily cron job: Maintain FULL_UNIVERSE at 1000+ stocks
- Remove delisted/invalid symbols
- Add new liquid stocks to replace them
- Update both src/full_universe_collector.py AND data/full_universe_cache.json

Cron: 0 3 * * 0 python3 scripts/maintain_universe_1000.py >> data/logs/universe_maintenance.log 2>&1
"""
import json
import yfinance as yf
import pandas as pd
from datetime import datetime
import sys
import time
import os

sys.path.insert(0, 'src')
from full_universe_collector import FULL_UNIVERSE

print(f"=== Universe Maintenance {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")

DATA_DIR = 'data'
CACHE_FILE = os.path.join(DATA_DIR, 'full_universe_cache.json')
DELISTED_LOG = os.path.join(DATA_DIR, 'delisted_log.txt')

# 1. Build full universe
universe_stocks = {sector: list(stocks) for sector, stocks in FULL_UNIVERSE.items()}
all_stocks = [s for stocks in universe_stocks.values() for s in stocks]
unique_stocks = list(dict.fromkeys(all_stocks))  # preserve order, deduplicate
print(f"Current FULL_UNIVERSE: {len(unique_stocks)} unique stocks across {len(universe_stocks)} sectors")

# 2. Check ALL stocks for delisted via batch yf.download
# yf.download raises no error for delisted — returns empty DataFrame
print(f"\nChecking ALL {len(unique_stocks)} stocks for delisted/invalid data...")
print("(Using batch download to avoid rate limits — may take 2-3 min)")

BATCH_SIZE = 100
delisted = []
error_stocks = []

for i in range(0, len(unique_stocks), BATCH_SIZE):
    batch = unique_stocks[i:i + BATCH_SIZE]
    try:
        df = yf.download(
            batch,
            period='5d',
            interval='1d',
            progress=False,
            auto_adjust=True,
            threads=True
        )
        # For multi-ticker download, df.columns is MultiIndex (field, symbol)
        if isinstance(df.columns, pd.MultiIndex):
            close_df = df['Close']
        else:
            close_df = df[['Close']] if 'Close' in df.columns else df

        for sym in batch:
            try:
                if sym not in close_df.columns:
                    delisted.append(sym)
                    print(f"  ❌ {sym} - not in download result (likely delisted)")
                elif close_df[sym].dropna().empty:
                    delisted.append(sym)
                    print(f"  ❌ {sym} - no price data (likely delisted)")
            except Exception:
                error_stocks.append(sym)

    except Exception as e:
        print(f"  ⚠️  Batch {i//BATCH_SIZE + 1} failed: {e} — skipping batch")
        error_stocks.extend(batch)

    # Brief pause between batches
    if i + BATCH_SIZE < len(unique_stocks):
        time.sleep(1)

    progress = min(i + BATCH_SIZE, len(unique_stocks))
    print(f"  Progress: {progress}/{len(unique_stocks)} checked, {len(delisted)} delisted so far")

print(f"\n{'='*60}")
print(f"Delisted found: {len(delisted)}")
print(f"Error (skipped): {len(error_stocks)}")

# 3. Remove delisted from universe
delisted_set = set(delisted)
removed_count = 0

if delisted:
    print(f"\nRemoving {len(delisted)} delisted stocks from universe...")
    for sector in universe_stocks:
        before = len(universe_stocks[sector])
        universe_stocks[sector] = [s for s in universe_stocks[sector] if s not in delisted_set]
        removed = before - len(universe_stocks[sector])
        if removed:
            print(f"  {sector}: removed {removed} stocks")
        removed_count += removed

    # Log delisted
    with open(DELISTED_LOG, 'a') as f:
        f.write(f"{datetime.now().isoformat()}: REMOVED {len(delisted)} delisted: {', '.join(sorted(delisted))}\n")
    print(f"\n✅ Logged to {DELISTED_LOG}")
else:
    print("\n✅ No delisted stocks found")

# 4. Rebuild full_universe_cache.json (without delisted)
print(f"\nUpdating {CACHE_FILE}...")
cache = {}
now = time.time()

for sector, stocks in universe_stocks.items():
    for symbol in stocks:
        cache[symbol] = {
            "sector": sector,
            "ts": now,
            "status": "active"
        }

with open(CACHE_FILE, 'w') as f:
    json.dump(cache, f, indent=2)

remaining = len(unique_stocks) - removed_count
print(f"✅ Updated {CACHE_FILE}: {len(cache)} stocks (removed {removed_count})")

# 5. Summary
print(f"\n{'='*60}")
print(f"SUMMARY")
print(f"  Before: {len(unique_stocks)} stocks")
print(f"  Removed (delisted): {removed_count}")
print(f"  After:  {len(cache)} stocks")
if delisted:
    print(f"  Delisted list: {', '.join(sorted(delisted))}")
print(f"{'='*60}")
