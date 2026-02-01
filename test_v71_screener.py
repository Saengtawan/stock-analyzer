#!/usr/bin/env python3
"""
Quick test of v7.1 screener changes
"""

import sys
sys.path.insert(0, 'src')

def test_momentum_gates():
    """Test the updated momentum gates"""
    from screeners.growth_catalyst_screener import GrowthCatalystScreener

    # Test cases based on backtest winners/losers
    test_cases = [
        # Winners (should pass)
        {'price_above_ma20': 5, 'position_52w': 65, 'momentum_20d': 8, 'momentum_3d': 2, 'rsi': 55, 'atr_pct': 2, 'volume_ratio': 1.2},
        {'price_above_ma20': 8, 'position_52w': 75, 'momentum_20d': 10, 'momentum_3d': 3, 'rsi': 52, 'atr_pct': 2.5, 'volume_ratio': 1.5},
        # Edge cases (may pass or fail)
        {'price_above_ma20': 2, 'position_52w': 60, 'momentum_20d': 5, 'momentum_3d': 1, 'rsi': 58, 'atr_pct': 3, 'volume_ratio': 0.8},
        # Should fail (bad metrics)
        {'price_above_ma20': -8, 'position_52w': 50, 'momentum_20d': 15, 'momentum_3d': 5, 'rsi': 55, 'atr_pct': 2, 'volume_ratio': 1},
        {'price_above_ma20': 5, 'position_52w': 75, 'momentum_20d': -5, 'momentum_3d': -2, 'rsi': 55, 'atr_pct': 2, 'volume_ratio': 1},
        {'price_above_ma20': 5, 'position_52w': 75, 'momentum_20d': 10, 'momentum_3d': 2, 'rsi': 75, 'atr_pct': 2, 'volume_ratio': 1},
    ]

    print("Testing v7.1 Momentum Gates:")
    print("-" * 50)
    for i, metrics in enumerate(test_cases):
        passed, reason = GrowthCatalystScreener._passes_momentum_gates(metrics)
        status = "PASS" if passed else f"FAIL: {reason}"
        print(f"Case {i+1}: mom={metrics['momentum_20d']:.0f}%, rsi={metrics['rsi']:.0f} → {status}")


def test_momentum_score():
    """Test the updated momentum scoring"""
    from screeners.growth_catalyst_screener import GrowthCatalystScreener

    # Test different metric combinations
    test_cases = [
        # Perfect sweet spot (should be ~100)
        {'momentum_20d': 10, 'rsi': 54, 'position_52w': 72},
        # Good but not perfect (~80-90)
        {'momentum_20d': 7, 'rsi': 50, 'position_52w': 65},
        # Edge of sweet spot (~70-80)
        {'momentum_20d': 5, 'rsi': 45, 'position_52w': 60},
        # Outside optimal range (~50-60)
        {'momentum_20d': 3, 'rsi': 40, 'position_52w': 55},
        # Poor metrics (~30-40)
        {'momentum_20d': 1, 'rsi': 72, 'position_52w': 95},
    ]

    print("\nTesting v7.1 Momentum Score:")
    print("-" * 50)
    for i, metrics in enumerate(test_cases):
        score = GrowthCatalystScreener._calculate_momentum_score(metrics)
        print(f"Case {i+1}: mom={metrics['momentum_20d']:.0f}%, rsi={metrics['rsi']:.0f}, pos={metrics['position_52w']:.0f}% → Score: {score:.0f}")


def test_quality_thresholds():
    """Test the updated quality thresholds"""
    from screeners.growth_catalyst_screener import GrowthCatalystScreener

    prices = [100, 35, 15, 7, 4]

    print("\nTesting v7.1 Quality Thresholds:")
    print("-" * 50)
    for price in prices:
        thresholds = GrowthCatalystScreener._get_tiered_quality_thresholds(price)
        print(f"${price:3}: {thresholds['tier']:15} → min_tech_score: {thresholds['min_technical_score']}")


if __name__ == "__main__":
    test_momentum_gates()
    test_momentum_score()
    test_quality_thresholds()
    print("\n✅ All tests completed!")
