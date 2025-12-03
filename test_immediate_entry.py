#!/usr/bin/env python3
"""
Test script for Immediate Entry Conditions (v5.1)
Tests when the system decides to enter at current price vs waiting for pullback
"""

import pandas as pd
import numpy as np
from src.analysis.technical.technical_analyzer import TechnicalAnalyzer

def create_test_data(scenario='normal'):
    """Create different price scenarios for testing"""
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    np.random.seed(42)

    if scenario == 'at_entry_zone':
        # Price at Fibonacci 50% retracement (should enter immediately)
        base = 100
        close = np.concatenate([
            np.linspace(base, 130, 50),  # Uptrend to swing high
            np.linspace(130, 125, 50)     # Pullback to ~Fib 50%
        ])
    elif scenario == 'strong_breakout':
        # Price breaking resistance with high volume (should enter immediately)
        close = np.concatenate([
            np.linspace(100, 120, 90),   # Build up to resistance
            np.linspace(120, 125, 10)    # Strong breakout
        ])
    elif scenario == 'near_support':
        # Price near support in sideways (should enter immediately)
        close = 95 + np.random.randn(100) * 2  # Sideways around 95
        close[-10:] = np.linspace(close[-11], 96, 10)  # Move near support at 95
    elif scenario == 'wait_for_pullback':
        # Price far from entry zone (should wait)
        close = np.concatenate([
            np.linspace(100, 130, 80),
            np.linspace(130, 132, 20)  # Still going up, far from pullback
        ])
    else:  # normal
        close = 100 + np.cumsum(np.random.randn(100) * 2 + 0.5)

    high = close + np.random.rand(100) * 2
    low = close - np.random.rand(100) * 2
    open_price = close + np.random.randn(100) * 1

    # Volume spike for breakout scenario
    if scenario == 'strong_breakout':
        volume = np.random.randint(1000000, 2000000, 100)
        volume[-10:] = np.random.randint(3000000, 5000000, 10)  # Volume spike
    else:
        volume = np.random.randint(1000000, 3000000, 100)

    data = pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
        'symbol': ['TEST'] * 100
    })

    return data

def test_scenario(scenario_name, data, description):
    """Test a specific scenario"""
    print("=" * 80)
    print(f"Scenario: {scenario_name}")
    print(f"Description: {description}")
    print("=" * 80)

    analyzer = TechnicalAnalyzer(data)
    results = analyzer.analyze()

    strategy = results.get('strategy_recommendation', {})
    trading_plan = strategy.get('trading_plan', {})

    current_price = data['close'].iloc[-1]
    entry_price = trading_plan.get('entry_price', 0)
    immediate_entry = trading_plan.get('immediate_entry', False)
    entry_action = trading_plan.get('entry_action', 'UNKNOWN')
    reasons = trading_plan.get('immediate_entry_reasons', [])
    confidence = trading_plan.get('immediate_entry_confidence', 0)

    print(f"\nCurrent Price: ${current_price:.2f}")
    print(f"Recommended Entry: ${entry_price:.2f}")
    print(f"Distance: {abs(entry_price - current_price):.2f} ({abs((entry_price - current_price) / current_price * 100):.2f}%)")
    print()

    if immediate_entry:
        print(f"🚀 Action: {entry_action}")
        print(f"✅ Immediate Entry: YES (Confidence: {confidence}%)")
        print(f"\nReasons:")
        for reason in reasons:
            print(f"  {reason}")
    else:
        print(f"⏳ Action: {entry_action}")
        print(f"❌ Immediate Entry: NO")
        print(f"\nReasons:")
        for reason in reasons:
            print(f"  {reason}")

    print()
    return immediate_entry

def main():
    """Run all scenario tests"""
    print("\n")
    print("🚀 " * 20)
    print("IMMEDIATE ENTRY CONDITIONS TEST (v5.1)")
    print("🚀 " * 20)
    print()

    results = {}

    # Test 1: At Entry Zone
    data1 = create_test_data('at_entry_zone')
    results['at_entry_zone'] = test_scenario(
        "At Entry Zone",
        data1,
        "Price already at Fibonacci retracement zone → Should enter immediately"
    )

    # Test 2: Strong Breakout
    data2 = create_test_data('strong_breakout')
    results['strong_breakout'] = test_scenario(
        "Strong Breakout",
        data2,
        "Price breaking resistance with volume spike → Should enter immediately"
    )

    # Test 3: Near Support (Sideways)
    data3 = create_test_data('near_support')
    results['near_support'] = test_scenario(
        "Near Support (Sideways)",
        data3,
        "Price near support level in sideways market → Should enter immediately"
    )

    # Test 4: Wait for Pullback
    data4 = create_test_data('wait_for_pullback')
    results['wait_for_pullback'] = test_scenario(
        "Wait for Pullback",
        data4,
        "Price far from entry zone, still going up → Should wait for pullback"
    )

    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()

    expected = {
        'at_entry_zone': True,
        'strong_breakout': True,
        'near_support': True,
        'wait_for_pullback': False
    }

    passed = 0
    failed = 0

    for scenario, result in results.items():
        expected_result = expected[scenario]
        status = "✅ PASS" if result == expected_result else "❌ FAIL"
        print(f"{scenario:25s} → Expected: {expected_result:5s}, Got: {result:5s} {status}")

        if result == expected_result:
            passed += 1
        else:
            failed += 1

    print()
    print(f"Total Tests: {len(results)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} {'❌' if failed > 0 else ''}")
    print()

    if failed == 0:
        print("🎉 ALL TESTS PASSED! Immediate entry logic is working correctly.")
    else:
        print("⚠️  Some tests failed. Review the logic.")
    print()

if __name__ == '__main__':
    main()
