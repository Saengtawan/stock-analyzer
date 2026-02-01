#!/usr/bin/env python3
"""
Simple Direct Test of v3.1 Features
Test individual stock analysis with ≥3 signals filter and sector rotation
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from api.data_manager import DataManager
from screeners.growth_catalyst_screener import GrowthCatalystScreener
import logging

logging.basicConfig(level=logging.WARNING)  # Reduce noise

def test_stock(screener, symbol, expected_signals, should_pass):
    """Test a single stock"""
    print(f"\n{'='*60}")
    print(f"Testing {symbol} (Expected: {expected_signals}/6 signals)")
    print(f"Should pass filter: {'✅ YES' if should_pass else '❌ NO'}")
    print("-" * 60)

    result = screener._analyze_stock_comprehensive(
        symbol,
        target_gain_pct=5.0,
        timeframe_days=30
    )

    if result:
        print(f"✅ PASSED FILTER")
        print(f"   Signals: {result.get('alt_data_signals', 0)}/6")
        print(f"   Composite Score: {result.get('composite_score', 0):.1f}")
        print(f"   Sector: {result.get('sector', 'Unknown')}")
        print(f"   Sector Momentum: {result.get('sector_momentum', 0):+.1f}%")
        print(f"   Sector Boost: {result.get('sector_rotation_boost', 1.0):.2f}x")

        # Check if semiconductor
        if 'Semiconductor' in result.get('sector', ''):
            print(f"   🎯 SEMICONDUCTOR STOCK - Getting hot sector boost!")

        return result
    else:
        print(f"❌ FILTERED OUT")
        return None


def main():
    print("\n" + "="*80)
    print("🧪 DIRECT TEST: v3.1 Signal Filter + Sector Rotation")
    print("="*80)

    print("\nInitializing screener...")
    data_manager = DataManager()
    screener = GrowthCatalystScreener(data_manager)
    print("✅ Screener v3.1 initialized")

    # Test stocks from user's results
    print("\n" + "="*80)
    print("📊 TESTING STOCKS FROM USER'S SCREEN RESULTS")
    print("="*80)

    test_cases = [
        ('LRCX', 3, True),   # Should PASS
        ('MRVL', 2, False),  # Should be FILTERED
        ('SNOW', 2, False),  # Should be FILTERED
        ('QCOM', 1, False),  # Should be FILTERED
    ]

    results = []
    for symbol, expected_signals, should_pass in test_cases:
        result = test_stock(screener, symbol, expected_signals, should_pass)
        if result:
            results.append(result)

    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)

    print(f"\nTotal Tested: {len(test_cases)}")
    print(f"Passed Filter: {len(results)}")
    print(f"Filtered Out: {len(test_cases) - len(results)}")

    if results:
        print(f"\n{'Symbol':<8} {'Signals':<10} {'Score':<8} {'Sector':<25} {'Momentum':<12} {'Boost':<8}")
        print("-" * 85)
        for r in results:
            print(f"{r['symbol']:<8} "
                  f"{r.get('alt_data_signals', 0)}/6{'':<6} "
                  f"{r.get('composite_score', 0):>6.1f}  "
                  f"{r.get('sector', 'Unknown'):<25} "
                  f"{r.get('sector_momentum', 0):>+6.1f}%{'':<4} "
                  f"{r.get('sector_rotation_boost', 1.0):.2f}x")

    print("\n" + "="*80)
    print("✅ VERIFICATION")
    print("="*80)

    print("\n1️⃣ Signal Filter (≥3 required):")
    if results:
        all_have_3plus = all(r.get('alt_data_signals', 0) >= 3 for r in results)
        if all_have_3plus:
            print(f"   ✅ WORKING - All {len(results)} stocks have ≥3 signals")
        else:
            print(f"   ❌ BROKEN - Some stocks have <3 signals!")
    else:
        print(f"   ⚠️  No stocks passed (either filter too strict or no stocks have ≥3 signals)")

    print("\n2️⃣ Sector Rotation:")
    if results:
        has_boost = any(r.get('sector_rotation_boost', 1.0) != 1.0 for r in results)
        has_semiconductor = any('Semiconductor' in r.get('sector', '') for r in results)

        if has_boost:
            print(f"   ✅ WORKING - Boost/penalty applied")
        else:
            print(f"   ⚠️  All sectors neutral (no boost/penalty)")

        if has_semiconductor:
            semi_stock = next(r for r in results if 'Semiconductor' in r.get('sector', ''))
            print(f"   ✅ SEMICONDUCTOR MATCH - {semi_stock['symbol']} matched to '{semi_stock['sector']}'")
            print(f"      Momentum: {semi_stock.get('sector_momentum', 0):+.1f}%")
            print(f"      Boost: {semi_stock.get('sector_rotation_boost', 1.0):.2f}x")

    print("\n3️⃣ Expected vs Actual:")
    expected = "Only LRCX should pass (3/6 signals), with Semiconductors sector boost"

    actual_symbols = [r['symbol'] for r in results]
    if 'LRCX' in actual_symbols and len(results) == 1:
        print(f"   ✅ PERFECT - Matches expectation exactly")
    elif 'LRCX' in actual_symbols:
        print(f"   ⚠️  LRCX passed but also found: {', '.join([s for s in actual_symbols if s != 'LRCX'])}")
    else:
        print(f"   ❌ UNEXPECTED - Got: {', '.join(actual_symbols) if actual_symbols else 'No stocks'}")

    print("\n" + "="*80)
    print("✅ Test Complete!")
    print("="*80)


if __name__ == "__main__":
    main()
