#!/usr/bin/env python3
"""
Quick validation test for v5.0 Momentum Continuation implementation
Test that the new filters work correctly
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from loguru import logger

def test_v5_filters():
    """Test v5.0 momentum gates with sample data"""

    logger.info("🧪 Testing v5.0 Momentum Continuation Filters")
    logger.info("=" * 80)

    # Test cases based on historical winners and losers
    test_cases = [
        {
            'name': 'ARWR (Winner +70%)',
            'metrics': {
                'rsi': 52.03,
                'momentum_30d': 7.07,  # Low momentum - should FAIL v5.0
                'volume_ratio': 0.98,
                'price_above_ma50': 11.20,
                'position_in_52w_range': 85.0,  # Strong position
                'ma20_vs_ma50': 3.0,
                'momentum_5d': 2.0,
            },
            'expected': False,  # Should fail because momentum < 15%
        },
        {
            'name': 'MU (Winner +31%)',
            'metrics': {
                'rsi': 66.50,
                'momentum_30d': 18.84,  # Good continuation zone
                'volume_ratio': 0.86,
                'price_above_ma50': 20.11,
                'position_in_52w_range': 92.0,  # Very strong
                'ma20_vs_ma50': 5.0,
                'momentum_5d': 3.0,
            },
            'expected': False,  # Should fail because RSI > 65
        },
        {
            'name': 'MU (Winner +38%) - Adjusted RSI',
            'metrics': {
                'rsi': 45.59,  # Good RSI
                'momentum_30d': 14.76,  # Just below 15% - should FAIL
                'volume_ratio': 0.80,
                'price_above_ma50': 10.82,
                'position_in_52w_range': 88.0,
                'ma20_vs_ma50': 4.0,
                'momentum_5d': 2.0,
            },
            'expected': False,  # Should fail because momentum < 15%
        },
        {
            'name': 'SCCO (Winner +16%)',
            'metrics': {
                'rsi': 69.69,  # Too high
                'momentum_30d': 9.31,  # Too low
                'volume_ratio': 0.85,
                'price_above_ma50': 9.51,
                'position_in_52w_range': 95.0,
                'ma20_vs_ma50': 3.0,
                'momentum_5d': 1.0,
            },
            'expected': False,  # Should fail both RSI and momentum
        },
        {
            'name': 'LRCX (Winner +25%)',
            'metrics': {
                'rsi': 65.03,  # At upper limit - should FAIL
                'momentum_30d': 10.17,  # Too low
                'volume_ratio': 0.98,
                'price_above_ma50': 13.02,
                'position_in_52w_range': 90.0,
                'ma20_vs_ma50': 4.0,
                'momentum_5d': 2.0,
            },
            'expected': False,  # Should fail both
        },
        {
            'name': 'GOOGL (Winner +8.6%)',
            'metrics': {
                'rsi': 55.86,  # Perfect
                'momentum_30d': 19.84,  # Good continuation zone
                'volume_ratio': 1.59,  # High volume OK for high momentum
                'price_above_ma50': 10.81,
                'position_in_52w_range': 88.0,  # Strong
                'ma20_vs_ma50': 3.0,
                'momentum_5d': 1.0,
            },
            'expected': True,  # Should PASS all v5.0 filters!
        },
        {
            'name': 'NVDA (Loser -12%)',
            'metrics': {
                'rsi': 63.48,
                'momentum_30d': 9.46,  # Too low - no continuation
                'volume_ratio': 1.05,
                'price_above_ma50': 8.22,
                'position_in_52w_range': 55.0,  # Weak position
                'ma20_vs_ma50': 2.0,
                'momentum_5d': 0.5,
            },
            'expected': False,  # Should fail momentum and 52w position
        },
        {
            'name': 'SNOW (Loser -18.8%)',
            'metrics': {
                'rsi': 67.13,  # Too high
                'momentum_30d': 19.21,  # Good momentum
                'volume_ratio': 0.74,  # Too low
                'price_above_ma50': 11.38,
                'position_in_52w_range': 65.0,  # Below 70%
                'ma20_vs_ma50': 3.0,
                'momentum_5d': 1.0,
            },
            'expected': False,  # Should fail RSI, volume, and 52w position
        },
        {
            'name': 'Perfect v5.0 Stock',
            'metrics': {
                'rsi': 55.0,  # Neutral zone
                'momentum_30d': 20.0,  # High momentum (90.9% win rate zone)
                'volume_ratio': 1.2,  # Strong volume for high momentum
                'price_above_ma50': 12.0,
                'position_in_52w_range': 85.0,  # Near 52w high
                'ma20_vs_ma50': 5.0,
                'momentum_5d': 3.0,
            },
            'expected': True,  # Should PASS!
        },
    ]

    # Test each case (using static methods directly)
    results = []

    logger.info("")
    for case in test_cases:
        passes, reason = GrowthCatalystScreener._passes_momentum_gates(case['metrics'])

        status = "✅ PASS" if passes else "❌ FAIL"
        match = "✓" if passes == case['expected'] else "✗ MISMATCH"

        logger.info(f"{match} {case['name']}: {status}")
        if not passes:
            logger.info(f"   Reason: {reason}")

        # Calculate score
        score = GrowthCatalystScreener._calculate_momentum_score(case['metrics'])
        logger.info(f"   Score: {score}/100")
        logger.info(f"   Momentum: {case['metrics']['momentum_30d']:.1f}%, RSI: {case['metrics']['rsi']:.1f}, 52w: {case['metrics']['position_in_52w_range']:.1f}%")
        logger.info("")

        results.append({
            'name': case['name'],
            'passed': passes,
            'expected': case['expected'],
            'match': passes == case['expected'],
            'score': score,
            'reason': reason
        })

    # Summary
    logger.info("=" * 80)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 80)

    total = len(results)
    matches = sum(1 for r in results if r['match'])
    passed = sum(1 for r in results if r['passed'])

    logger.info(f"Total tests: {total}")
    logger.info(f"Matching expected: {matches}/{total} ({matches/total*100:.1f}%)")
    logger.info(f"Passed filters: {passed}/{total} ({passed/total*100:.1f}%)")

    if matches == total:
        logger.info("✅ ALL TESTS PASSED - v5.0 filters working correctly!")
    else:
        logger.warning("⚠️  Some tests didn't match expectations - review implementation")

    logger.info("")
    logger.info("🎯 v5.0 Philosophy Validation:")
    logger.info("   - Momentum 15-25%: Required for continuation")
    logger.info("   - 52w position >70%: Strong stocks only")
    logger.info("   - Context volume: Dependent on momentum level")
    logger.info("   - RSI 45-65: Filter extremes only")

if __name__ == "__main__":
    test_v5_filters()
