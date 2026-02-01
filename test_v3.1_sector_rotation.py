#!/usr/bin/env python3
"""
Test v3.1: Growth Catalyst Screener with Sector Rotation
Verify ≥3 signals filter and sector rotation boost working
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from sector_rotation import SectorRotationDetector
import logging

logging.basicConfig(level=logging.INFO)

def test_sector_rotation():
    """Test sector rotation detector"""
    print("\n" + "="*80)
    print("🧪 TEST 1: Sector Rotation Detector")
    print("="*80)

    detector = SectorRotationDetector()
    detector.print_sector_report()

    # Test specific stocks
    print("\n" + "="*80)
    print("📊 Sector Status for Test Stocks")
    print("="*80)

    test_stocks = [
        ('LRCX', 'Technology'),  # From screening results - semiconductor
        ('AVGO', 'Technology'),  # From backtest - 3/6 signals
        ('NVDA', 'Technology'),  # AI/semiconductor
    ]

    for symbol, sector in test_stocks:
        status = detector.get_stock_sector_status(symbol, sector)
        boost = detector.get_sector_boost(sector)
        print(f"\n{symbol} ({sector}):")
        print(f"  Status: {status['status']}")
        print(f"  Momentum: {status['momentum_score']:+.1f}%")
        print(f"  Boost: {boost:.2f}x")
        print(f"  {status['recommendation']}")


def test_screener():
    """Test growth catalyst screener with v3.1"""
    print("\n" + "="*80)
    print("🧪 TEST 2: Growth Catalyst Screener v3.1")
    print("="*80)
    print("Expected: Only stocks with ≥3/6 signals")
    print("Expected: Sector rotation boost applied to composite scores")
    print("="*80)

    screener = GrowthCatalystScreener()

    # Screen with small universe for testing
    test_universe = [
        'LRCX',   # 3/6 signals from user's results
        'MRVL',   # 2/6 signals - should be filtered out
        'SNOW',   # 2/6 signals - should be filtered out
        'QCOM',   # 1/6 signals - should be filtered out
        'AVGO',   # 3/6 signals from backtest - should pass
        'RIVN',   # 3/6 signals from backtest - should pass
        'NVDA',   # Check if it has 3+ signals
    ]

    print(f"\n🔍 Scanning {len(test_universe)} stocks...")
    print(f"Universe: {', '.join(test_universe)}")

    results = []
    for symbol in test_universe:
        try:
            print(f"\n{'='*40}")
            print(f"Analyzing {symbol}...")
            result = screener._analyze_stock_comprehensive(symbol)

            if result:
                results.append(result)
                print(f"✅ {symbol} PASSED!")
                print(f"   Signals: {result.get('alt_data_signals', 0)}/6")
                print(f"   Composite: {result.get('composite_score', 0):.1f}")
                print(f"   Sector: {result.get('sector', 'Unknown')}")
                print(f"   Sector Status: {result.get('sector_rotation_status', 'unknown')}")
                print(f"   Sector Momentum: {result.get('sector_momentum', 0):+.1f}%")
                print(f"   Sector Boost: {result.get('sector_rotation_boost', 1.0):.2f}x")
            else:
                print(f"❌ {symbol} FILTERED OUT")

        except Exception as e:
            print(f"⚠️ {symbol} ERROR: {e}")

    # Summary
    print("\n" + "="*80)
    print("📊 RESULTS SUMMARY")
    print("="*80)
    print(f"\nTotal Scanned: {len(test_universe)}")
    print(f"Passed Filter: {len(results)}")
    print(f"Filtered Out: {len(test_universe) - len(results)}")

    if results:
        print(f"\n{'Symbol':<8} {'Signals':<10} {'Score':<8} {'Sector':<20} {'Momentum':<12} {'Boost':<8}")
        print("-" * 80)
        for r in sorted(results, key=lambda x: x.get('composite_score', 0), reverse=True):
            print(f"{r['symbol']:<8} {r.get('alt_data_signals', 0)}/6{'':<6} "
                  f"{r.get('composite_score', 0):>6.1f}  "
                  f"{r.get('sector', 'Unknown'):<20} "
                  f"{r.get('sector_momentum', 0):>+6.1f}%{'':<4} "
                  f"{r.get('sector_rotation_boost', 1.0):.2f}x")

    print("\n" + "="*80)
    print("✅ Test Complete!")
    print("="*80)


if __name__ == "__main__":
    # Test 1: Sector Rotation
    test_sector_rotation()

    # Test 2: Screener with v3.1
    test_screener()
