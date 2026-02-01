#!/usr/bin/env python3
"""
Quick test to verify v6.0 improvements are working
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
from screeners.premarket_scanner import PremarketScanner

def test_v6_improvements():
    """Test that v6.0 improvements are working"""

    print("=" * 100)
    print("🧪 TESTING v6.0 CONFIDENCE IMPROVEMENTS")
    print("=" * 100)

    client = YahooFinanceClient()
    scanner = PremarketScanner(client)

    # Test case 1: High consistency (should be penalized)
    print("\n1️⃣ Testing Overbought Detection (>95% consistency):")
    print("-" * 100)

    # Simulate a stock with very high consistency
    test_conf_overbought = scanner._calculate_trade_confidence(
        gap_score=8.0,
        gap_percent=2.5,  # In sweet spot
        risk_indicators={'fade_probability': 'Low', 'volatility_risk': 'Low'},
        volume_ratio=3.0,
        current_price=100.0,
        premarket_high=101.0,
        premarket_low=99.0,
        consistency_ratio=1.0  # 100% consistency = OVERBOUGHT
    )

    test_conf_good = scanner._calculate_trade_confidence(
        gap_score=8.0,
        gap_percent=2.5,  # In sweet spot
        risk_indicators={'fade_probability': 'Low', 'volatility_risk': 'Low'},
        volume_ratio=3.0,
        current_price=100.0,
        premarket_high=101.0,
        premarket_low=99.0,
        consistency_ratio=0.7  # 70% consistency = SWEET SPOT
    )

    print(f"   100% consistency (OVERBOUGHT): Confidence = {test_conf_overbought}/100")
    print(f"   70% consistency (GOOD):        Confidence = {test_conf_good}/100")

    if test_conf_good > test_conf_overbought:
        print(f"   ✅ CORRECT: 70% consistency ({test_conf_good}) > 100% consistency ({test_conf_overbought})")
    else:
        print(f"   ❌ WRONG: Should penalize 100% consistency!")

    # Test case 2: Gap sweet spot
    print("\n2️⃣ Testing Gap Sweet Spot (2-3% better than 3-4%):")
    print("-" * 100)

    test_conf_sweet = scanner._calculate_trade_confidence(
        gap_score=8.0,
        gap_percent=2.5,  # Sweet spot
        risk_indicators={'fade_probability': 'Low', 'volatility_risk': 'Low'},
        volume_ratio=3.0,
        current_price=100.0,
        premarket_high=101.0,
        premarket_low=99.0,
        consistency_ratio=0.6
    )

    test_conf_large = scanner._calculate_trade_confidence(
        gap_score=8.0,
        gap_percent=4.0,  # Larger gap
        risk_indicators={'fade_probability': 'Low', 'volatility_risk': 'Low'},
        volume_ratio=3.0,
        current_price=100.0,
        premarket_high=101.0,
        premarket_low=99.0,
        consistency_ratio=0.6
    )

    print(f"   2.5% gap (SWEET SPOT): Confidence = {test_conf_sweet}/100")
    print(f"   4.0% gap (LARGER):     Confidence = {test_conf_large}/100")

    if test_conf_sweet > test_conf_large:
        print(f"   ✅ CORRECT: Sweet spot ({test_conf_sweet}) > Larger gap ({test_conf_large})")
    else:
        print(f"   ❌ WRONG: Should prefer 2-3% range!")

    # Test case 3: Very large gaps should be heavily penalized
    print("\n3️⃣ Testing Large Gap Penalty (>7% should be penalized):")
    print("-" * 100)

    test_conf_normal = scanner._calculate_trade_confidence(
        gap_score=8.0,
        gap_percent=2.5,
        risk_indicators={'fade_probability': 'Low', 'volatility_risk': 'Low'},
        volume_ratio=3.0,
        current_price=100.0,
        premarket_high=101.0,
        premarket_low=99.0,
        consistency_ratio=0.6
    )

    test_conf_extreme = scanner._calculate_trade_confidence(
        gap_score=8.0,
        gap_percent=8.0,  # Very large gap
        risk_indicators={'fade_probability': 'Low', 'volatility_risk': 'Low'},
        volume_ratio=3.0,
        current_price=100.0,
        premarket_high=101.0,
        premarket_low=99.0,
        consistency_ratio=0.6
    )

    print(f"   2.5% gap (NORMAL):  Confidence = {test_conf_normal}/100")
    print(f"   8.0% gap (EXTREME): Confidence = {test_conf_extreme}/100")

    penalty = test_conf_normal - test_conf_extreme
    print(f"   Penalty for extreme gap: {penalty} points")

    if penalty >= 15:
        print(f"   ✅ CORRECT: Strong penalty ({penalty} points) for extreme gap")
    else:
        print(f"   ❌ WRONG: Should heavily penalize large gaps!")

    # Summary
    print("\n" + "=" * 100)
    print("📊 TEST SUMMARY")
    print("=" * 100)

    tests_passed = 0
    tests_total = 3

    if test_conf_good > test_conf_overbought:
        tests_passed += 1
        print("✅ Test 1 PASSED: Overbought detection working")
    else:
        print("❌ Test 1 FAILED: Overbought not penalized")

    if test_conf_sweet > test_conf_large:
        tests_passed += 1
        print("✅ Test 2 PASSED: Gap sweet spot working")
    else:
        print("❌ Test 2 FAILED: Gap sweet spot not working")

    if penalty >= 15:
        tests_passed += 1
        print("✅ Test 3 PASSED: Large gap penalty working")
    else:
        print("❌ Test 3 FAILED: Large gap not penalized enough")

    print(f"\n🎯 Results: {tests_passed}/{tests_total} tests passed")

    if tests_passed == tests_total:
        print("✅ All v6.0 improvements are working correctly!")
    else:
        print("❌ Some improvements need fixing")

    print("=" * 100)

if __name__ == '__main__':
    test_v6_improvements()
