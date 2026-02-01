#!/usr/bin/env python3
"""
Test v6.0 implementation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from screeners.growth_catalyst_screener import GrowthCatalystScreener

# Test the static method directly
print("="*60)
print("TESTING v6.0 MOMENTUM GATES")
print("="*60)

# Test case 1: Should PASS - good volume, gap, momentum
test1 = {
    'price_above_ma20': 5.0,
    'volume_ratio': 1.5,
    'gap': 2.0,
    'momentum_20d': 8.0,
    'momentum_3d': 3.0,
    'rsi': 55,
}
passes, reason = GrowthCatalystScreener._passes_momentum_gates(test1)
print(f"\nTest 1 - Good stock (should PASS):")
print(f"  Volume: {test1['volume_ratio']}x, Gap: {test1['gap']}%, Mom3d: {test1['momentum_3d']}%, RSI: {test1['rsi']}")
print(f"  Result: {'PASS' if passes else 'FAIL'} {reason}")
assert passes, f"Test 1 should pass! Reason: {reason}"

# Test case 2: Should FAIL - volume too low
test2 = {
    'price_above_ma20': 5.0,
    'volume_ratio': 0.8,  # TOO LOW
    'gap': 2.0,
    'momentum_20d': 8.0,
    'momentum_3d': 3.0,
    'rsi': 55,
}
passes, reason = GrowthCatalystScreener._passes_momentum_gates(test2)
print(f"\nTest 2 - Low volume (should FAIL):")
print(f"  Volume: {test2['volume_ratio']}x, Gap: {test2['gap']}%, Mom3d: {test2['momentum_3d']}%, RSI: {test2['rsi']}")
print(f"  Result: {'PASS' if passes else 'FAIL'} - {reason}")
assert not passes, "Test 2 should fail (low volume)"

# Test case 3: Should FAIL - no gap
test3 = {
    'price_above_ma20': 5.0,
    'volume_ratio': 1.5,
    'gap': 0.3,  # TOO LOW
    'momentum_20d': 8.0,
    'momentum_3d': 3.0,
    'rsi': 55,
}
passes, reason = GrowthCatalystScreener._passes_momentum_gates(test3)
print(f"\nTest 3 - No gap (should FAIL):")
print(f"  Volume: {test3['volume_ratio']}x, Gap: {test3['gap']}%, Mom3d: {test3['momentum_3d']}%, RSI: {test3['rsi']}")
print(f"  Result: {'PASS' if passes else 'FAIL'} - {reason}")
assert not passes, "Test 3 should fail (no gap)"

# Test case 4: Should FAIL - RSI too high
test4 = {
    'price_above_ma20': 5.0,
    'volume_ratio': 1.5,
    'gap': 2.0,
    'momentum_20d': 8.0,
    'momentum_3d': 3.0,
    'rsi': 72,  # TOO HIGH
}
passes, reason = GrowthCatalystScreener._passes_momentum_gates(test4)
print(f"\nTest 4 - High RSI (should FAIL):")
print(f"  Volume: {test4['volume_ratio']}x, Gap: {test4['gap']}%, Mom3d: {test4['momentum_3d']}%, RSI: {test4['rsi']}")
print(f"  Result: {'PASS' if passes else 'FAIL'} - {reason}")
assert not passes, "Test 4 should fail (high RSI)"

# Test case 5: Should FAIL - mom_3d too high (extended)
test5 = {
    'price_above_ma20': 5.0,
    'volume_ratio': 1.5,
    'gap': 2.0,
    'momentum_20d': 8.0,
    'momentum_3d': 12.0,  # TOO HIGH
    'rsi': 55,
}
passes, reason = GrowthCatalystScreener._passes_momentum_gates(test5)
print(f"\nTest 5 - Mom3d too high (should FAIL):")
print(f"  Volume: {test5['volume_ratio']}x, Gap: {test5['gap']}%, Mom3d: {test5['momentum_3d']}%, RSI: {test5['rsi']}")
print(f"  Result: {'PASS' if passes else 'FAIL'} - {reason}")
assert not passes, "Test 5 should fail (mom3d too high)"

# Test case 6: Should FAIL - below MA20
test6 = {
    'price_above_ma20': -2.0,  # BELOW MA20
    'volume_ratio': 1.5,
    'gap': 2.0,
    'momentum_20d': 8.0,
    'momentum_3d': 3.0,
    'rsi': 55,
}
passes, reason = GrowthCatalystScreener._passes_momentum_gates(test6)
print(f"\nTest 6 - Below MA20 (should FAIL):")
print(f"  Above MA20: {test6['price_above_ma20']}%, Volume: {test6['volume_ratio']}x")
print(f"  Result: {'PASS' if passes else 'FAIL'} - {reason}")
assert not passes, "Test 6 should fail (below MA20)"

print("\n" + "="*60)
print("ALL UNIT TESTS PASSED!")
print("="*60)

# Now test with real data
print("\n" + "="*60)
print("TESTING WITH REAL STOCK DATA")
print("="*60)

from api.data_manager import DataManager

dm = DataManager()
test_stocks = ['NVDA', 'TSLA', 'AAPL', 'GOOGL', 'META', 'AMZN']

print("\nChecking current stocks against v6.0 criteria:")
print(f"{'Stock':<8} {'Vol':>6} {'Gap':>6} {'Mom20':>6} {'Mom3':>6} {'RSI':>5} {'Result':<10}")
print("-"*60)

for sym in test_stocks:
    try:
        df = dm.get_price_data(sym, period="3mo", interval="1d")
        if df is None or len(df) < 50:
            continue

        metrics = GrowthCatalystScreener._calculate_momentum_metrics(df)
        if metrics is None:
            continue

        passes, reason = GrowthCatalystScreener._passes_momentum_gates(metrics)

        vol = metrics.get('volume_ratio', 0)
        gap = metrics.get('gap', 0)
        mom20 = metrics.get('momentum_20d', 0)
        mom3 = metrics.get('momentum_3d', 0)
        rsi = metrics.get('rsi', 0)

        status = "PASS" if passes else reason[:30]
        print(f"{sym:<8} {vol:>5.1f}x {gap:>+5.1f}% {mom20:>+5.1f}% {mom3:>+5.1f}% {rsi:>4.0f} {status}")

    except Exception as e:
        print(f"{sym:<8} Error: {e}")

print("\n" + "="*60)
print("v6.0 CRITERIA SUMMARY")
print("="*60)
print("""
ENTRY (all must pass):
  1. Above MA20
  2. Volume >= 1.2x (20d avg)
  3. Gap >= 1%
  4. Momentum 20d >= 5%
  5. Momentum 3d: 1% - 8%
  6. RSI < 65

EXIT:
  - Stop loss -6%
  - Hold max 14 days
""")
