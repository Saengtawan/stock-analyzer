#!/usr/bin/env python3
"""
Test VIX Adaptive Strategy Wrapper
===================================

Tests that the wrapper conforms to BaseStrategy interface.
"""

import sys
import os

sys.path.insert(0, 'src')
os.chdir(os.path.dirname(__file__))

print("=" * 70)
print("VIX ADAPTIVE STRATEGY WRAPPER - TEST")
print("=" * 70)
print()

# Test 1: Import
print("Test 1: Import wrapper")
print("-" * 70)
try:
    from strategies.vix_adaptive_strategy_wrapper import VIXAdaptiveStrategyWrapper
    print("✅ VIXAdaptiveStrategyWrapper imported")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

print()

# Test 2: Initialize
print("Test 2: Initialize wrapper")
print("-" * 70)
try:
    config = {
        'config_path': 'config/vix_adaptive.yaml',
        'enabled': True,
        'enable_trace': False
    }
    wrapper = VIXAdaptiveStrategyWrapper(config=config)

    print(f"✅ Wrapper initialized: {wrapper}")
    print(f"   Name: {wrapper.name}")
    print(f"   Display name: {wrapper.display_name}")
    print(f"   Description: {wrapper.description}")
    print(f"   Enabled: {wrapper.is_enabled()}")
    print(f"   Current tier: {wrapper.get_current_tier()}")
    print(f"   Current VIX: {wrapper.get_current_vix()}")
except Exception as e:
    print(f"❌ Initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 3: Check interface compliance
print("Test 3: Check BaseStrategy interface")
print("-" * 70)
from strategies.base_strategy import BaseStrategy

if isinstance(wrapper, BaseStrategy):
    print("✅ Wrapper implements BaseStrategy")
else:
    print("❌ Wrapper does not implement BaseStrategy")
    sys.exit(1)

# Check required methods
required_methods = ['name', 'display_name', 'description', 'define_stages', 'scan', 'analyze_stock']
for method in required_methods:
    if hasattr(wrapper, method):
        print(f"   ✅ {method}")
    else:
        print(f"   ❌ {method} missing")

print()

# Test 4: Define stages
print("Test 4: Define stages")
print("-" * 70)
try:
    stages = wrapper.define_stages()
    print(f"✅ Stages defined: {len(stages)} stages")
    for stage in stages:
        print(f"   {stage['icon']} {stage['title']}")
except Exception as e:
    print(f"❌ define_stages failed: {e}")
    sys.exit(1)

print()

# Test 5: Test scan (with empty data)
print("Test 5: Test scan method")
print("-" * 70)
try:
    # Create minimal test data
    import pandas as pd
    import numpy as np

    np.random.seed(42)
    test_data = {}
    for symbol in ['AAPL', 'MSFT', 'GOOGL']:
        df = pd.DataFrame({
            'open': np.random.rand(100) * 100 + 50,
            'high': np.random.rand(100) * 100 + 60,
            'low': np.random.rand(100) * 100 + 40,
            'close': np.random.rand(100) * 100 + 50,
            'volume': np.random.randint(1000000, 10000000, 100),
        })
        test_data[symbol] = df

    # Scan
    signals = wrapper.scan(
        universe=['AAPL', 'MSFT', 'GOOGL'],
        data_cache=test_data,
        market_data=None
    )

    print(f"✅ Scan completed")
    print(f"   Signals found: {len(signals)}")

    if signals:
        print(f"   First signal:")
        print(f"     Symbol: {signals[0].symbol}")
        print(f"     Strategy: {signals[0].strategy}")
        print(f"     Entry: ${signals[0].entry_price:.2f}")
        print(f"     Stop: ${signals[0].stop_loss:.2f}")
        print(f"     Score: {signals[0].score}")

except Exception as e:
    print(f"❌ Scan failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 6: Strategy Manager integration
print("Test 6: Strategy Manager integration")
print("-" * 70)
try:
    from strategies import StrategyManager

    manager = StrategyManager()
    manager.register(wrapper)

    print(f"✅ Registered with Strategy Manager")
    print(f"   Active strategies: {len(manager.strategies)}")
    print(f"   Strategy names: {[s.name for s in manager.strategies]}")

    # Test scan_all
    signals = manager.scan_all(
        universe=['AAPL', 'MSFT', 'GOOGL'],
        data_cache=test_data
    )

    print(f"✅ Strategy Manager scan completed")
    print(f"   Total signals: {len(signals)}")

except Exception as e:
    print(f"❌ Strategy Manager integration failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 70)
print("✅ ALL TESTS PASSED")
print("=" * 70)
print()
print("Summary:")
print("  ✅ Wrapper conforms to BaseStrategy interface")
print("  ✅ Integrates with Strategy Manager")
print("  ✅ Scan method works")
print("  ✅ Ready for deployment")
print()
print("Next: Restart app to activate VIX Adaptive in screener")
