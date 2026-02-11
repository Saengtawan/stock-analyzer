#!/usr/bin/env python3
"""
Test Pre-filter Auto-Refresh Feature (v6.18)
"""
import sys
sys.path.insert(0, 'src')

from config.strategy_config import RapidRotationConfig
from screeners.rapid_rotation_screener import RapidRotationScreener

print("=" * 70)
print("🧪 PRE-FILTER AUTO-REFRESH - TEST")
print("=" * 70)
print()

# Load config
config = RapidRotationConfig.from_yaml('config/trading.yaml')

print("✅ Config loaded:")
print(f"   pre_filter_on_demand_enabled: {config.pre_filter_on_demand_enabled}")
print(f"   pre_filter_on_demand_min_pool: {config.pre_filter_on_demand_min_pool}")
print(f"   pre_filter_max_per_day: {config.pre_filter_max_per_day}")
print()

# Initialize screener
print("Initializing screener...")
screener = RapidRotationScreener(config)
print("✅ Screener initialized")
print()

# Check current pool size
import json
import os

pre_filter_file = 'data/pre_filtered.json'
if os.path.exists(pre_filter_file):
    with open(pre_filter_file) as f:
        pool = json.load(f)
    pool_size = len(pool.get('stocks', {}))
    print(f"📊 Current pool size: {pool_size}")
    print(f"   Min threshold: {config.pre_filter_on_demand_min_pool}")

    if pool_size < config.pre_filter_on_demand_min_pool:
        print(f"   ⚠️ Pool is LOW ({pool_size} < {config.pre_filter_on_demand_min_pool})")
        print()
        print("🔄 Testing auto-refresh...")

        # Trigger pool check
        refreshed = screener._check_prefilter_pool_health()

        if refreshed:
            print("   ✅ Auto-refresh TRIGGERED!")
            print("   📝 Check logs: tail -f nohup.out | grep refresh")
            print("   ⏱️ Wait 2-3 minutes for new pool")
        else:
            print("   ❌ Auto-refresh NOT triggered")
            print(f"   Refresh count: {screener._prefilter_refresh_count}/{config.pre_filter_max_per_day}")
    else:
        print(f"   ✅ Pool is HEALTHY ({pool_size} >= {config.pre_filter_on_demand_min_pool})")
        print("   No refresh needed")
else:
    print("❌ Pre-filtered pool not found!")
    print("   Creating initial pool...")
    refreshed = screener._check_prefilter_pool_health()
    if refreshed:
        print("   ✅ Initial refresh TRIGGERED!")

print()
print("=" * 70)
print("✅ TEST COMPLETE")
print("=" * 70)
