#!/usr/bin/env python3
"""
Daily cron job: Maintain FULL_UNIVERSE at ~1000 stocks
- Remove delisted/invalid symbols
- Add new liquid stocks from Alpaca to fill back to TARGET_SIZE

Cron: 0 3 * * 0 python3 scripts/maintain_universe_1000.py >> data/logs/universe_maintenance.log 2>&1
"""
import json
import os
import sys
import time
from datetime import datetime

import yfinance as yf
import pandas as pd

sys.path.insert(0, 'src')
from dotenv import load_dotenv
load_dotenv()

print(f"=== Universe Maintenance {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")

DATA_DIR = 'data'
CACHE_FILE = os.path.join(DATA_DIR, 'full_universe_cache.json')
DELISTED_LOG = os.path.join(DATA_DIR, 'delisted_log.txt')
TARGET_SIZE = 1000    # Target universe size
BATCH_SIZE = 500      # Stocks per yf.download batch
SECTOR_BATCH = 50     # Stocks per sector-lookup batch

# Liquidity thresholds (same as pre-filter)
MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 5_000_000   # $5M/day average

# ─────────────────────────────────────────────────────────────
# 1. Load current universe
# ─────────────────────────────────────────────────────────────
try:
    with open(CACHE_FILE) as f:
        cache = json.load(f)
except FileNotFoundError:
    cache = {}

print(f"Current universe: {len(cache)} stocks")
current_symbols = set(cache.keys())

# ─────────────────────────────────────────────────────────────
# 2. Remove delisted — batch yf.download all current stocks
# ─────────────────────────────────────────────────────────────
print(f"\n[Step 1] Checking {len(current_symbols)} stocks for delisted...")
delisted = []

all_current = list(current_symbols)
for i in range(0, len(all_current), BATCH_SIZE):
    batch = all_current[i:i + BATCH_SIZE]
    try:
        df = yf.download(batch, period='5d', interval='1d',
                         progress=False, auto_adjust=True, threads=True)
        close_df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
        for sym in batch:
            col = sym if sym in close_df.columns else None
            if col is None or close_df[col].dropna().empty:
                delisted.append(sym)
                print(f"  ❌ {sym} - no data (delisted)")
    except Exception as e:
        print(f"  ⚠️  Batch error: {e}")
    time.sleep(1)
    print(f"  Progress: {min(i+BATCH_SIZE, len(all_current))}/{len(all_current)}, delisted so far: {len(delisted)}")

if delisted:
    for sym in delisted:
        cache.pop(sym, None)
    with open(DELISTED_LOG, 'a') as f:
        f.write(f"{datetime.now().isoformat()}: REMOVED {len(delisted)}: {', '.join(sorted(delisted))}\n")
    print(f"\n✅ Removed {len(delisted)} delisted stocks. Universe now: {len(cache)}")
else:
    print("\n✅ No delisted stocks found")

# ─────────────────────────────────────────────────────────────
# 3. Find new candidates from Alpaca (tradable + easy_to_borrow)
# ─────────────────────────────────────────────────────────────
need = TARGET_SIZE - len(cache)
print(f"\n[Step 2] Need {need} new stocks to reach TARGET_SIZE={TARGET_SIZE}")

if need <= 0:
    print("Universe already at or above target, skipping candidate search")
else:
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetAssetsRequest
        from alpaca.trading.enums import AssetClass, AssetStatus

        api_key = os.getenv('ALPACA_API_KEY')
        secret_key = os.getenv('ALPACA_SECRET_KEY')
        client = TradingClient(api_key, secret_key, paper=True)

        req = GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status=AssetStatus.ACTIVE)
        assets = client.get_all_assets(req)

        # Filter: tradable + major exchange + easy_to_borrow (liquidity proxy)
        candidates_raw = [
            a.symbol for a in assets
            if a.tradable
            and a.easy_to_borrow
            and a.exchange.value in ('NYSE', 'NASDAQ', 'ARCA')
            and a.symbol not in current_symbols    # not already in universe
            and '.' not in a.symbol                # skip class shares (BRK.B etc)
            and len(a.symbol) <= 5                 # skip long symbols
        ]
        print(f"Alpaca candidates (tradable+ETB, not in universe): {len(candidates_raw)}")

    except Exception as e:
        print(f"⚠️  Alpaca API failed: {e}")
        candidates_raw = []

    # ─────────────────────────────────────────────────────────
    # 4. Batch download 30d price data to check liquidity
    # ─────────────────────────────────────────────────────────
    print(f"\n[Step 3] Checking liquidity for {len(candidates_raw)} candidates...")
    liquid_candidates = []   # [(symbol, avg_dollar_vol)]

    for i in range(0, len(candidates_raw), BATCH_SIZE):
        batch = candidates_raw[i:i + BATCH_SIZE]
        try:
            df = yf.download(batch, period='30d', interval='1d',
                             progress=False, auto_adjust=True, threads=True)
            if isinstance(df.columns, pd.MultiIndex):
                close_df = df['Close']
                vol_df = df['Volume']
            else:
                close_df = df[['Close']]
                vol_df = df[['Volume']]

            for sym in batch:
                try:
                    if sym not in close_df.columns:
                        continue
                    prices = close_df[sym].dropna()
                    volumes = vol_df[sym].dropna()
                    if len(prices) < 10:
                        continue
                    avg_price = float(prices.mean())
                    avg_vol = float(volumes.mean())
                    avg_dollar_vol = avg_price * avg_vol
                    if avg_price >= MIN_PRICE and avg_dollar_vol >= MIN_DOLLAR_VOL:
                        liquid_candidates.append((sym, avg_dollar_vol))
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️  Batch {i//BATCH_SIZE+1} error: {e}")
        time.sleep(1)
        print(f"  Progress: {min(i+BATCH_SIZE, len(candidates_raw))}/{len(candidates_raw)}, liquid: {len(liquid_candidates)}")

    # Sort by dollar volume descending (most liquid first)
    liquid_candidates.sort(key=lambda x: x[1], reverse=True)
    top_candidates = [sym for sym, _ in liquid_candidates[:need * 3]]  # fetch 3x needed for sector lookup
    print(f"\n✅ Found {len(liquid_candidates)} liquid candidates, checking top {len(top_candidates)} for sector")

    # ─────────────────────────────────────────────────────────
    # 5. Get sector for top candidates via yfinance
    # ─────────────────────────────────────────────────────────
    print(f"\n[Step 4] Fetching sector for {len(top_candidates)} candidates...")
    sector_map = {}

    for i in range(0, len(top_candidates), SECTOR_BATCH):
        batch = top_candidates[i:i + SECTOR_BATCH]
        for sym in batch:
            try:
                info = yf.Ticker(sym).fast_info
                # fast_info doesn't have sector — fallback to info
                full_info = yf.Ticker(sym).info
                sector = full_info.get('sector', 'Unknown')
                sector_map[sym] = sector if sector else 'Unknown'
            except Exception:
                sector_map[sym] = 'Unknown'
        time.sleep(2)
        print(f"  Progress: {min(i+SECTOR_BATCH, len(top_candidates))}/{len(top_candidates)}")

    # ─────────────────────────────────────────────────────────
    # 6. Add best candidates to cache until TARGET_SIZE
    # ─────────────────────────────────────────────────────────
    added = 0
    now_ts = time.time()
    for sym, dollar_vol in liquid_candidates:
        if len(cache) >= TARGET_SIZE:
            break
        if sym not in top_candidates:
            continue
        sector = sector_map.get(sym, 'Unknown')
        cache[sym] = {
            'sector': sector,
            'ts': now_ts,
            'status': 'active',
            'dollar_vol': round(dollar_vol)
        }
        added += 1
        print(f"  ➕ Added {sym} (sector={sector}, dollar_vol=${dollar_vol/1e6:.1f}M)")

    print(f"\n✅ Added {added} new stocks. Universe now: {len(cache)}")

# ─────────────────────────────────────────────────────────────
# 7. Save updated cache
# ─────────────────────────────────────────────────────────────
with open(CACHE_FILE, 'w') as f:
    json.dump(cache, f, indent=2)

print(f"\n{'='*60}")
print(f"SUMMARY")
print(f"  Removed (delisted): {len(delisted)}")
print(f"  Added (new):        {added if need > 0 else 0}")
print(f"  Final universe:     {len(cache)} stocks")
print(f"  Saved to:           {CACHE_FILE}")
if delisted:
    print(f"  Delisted:           {', '.join(sorted(delisted))}")
print(f"{'='*60}")
