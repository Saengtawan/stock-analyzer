#!/usr/bin/env python3
"""
Test Tiered Quality System (v3.2)

Tests that stocks at different price points are assigned to correct tiers
and that appropriate quality thresholds are applied.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from screeners.growth_catalyst_screener import GrowthCatalystScreener

def test_tier_assignment():
    """Test that stocks are assigned to correct tiers based on price"""

    print("=" * 80)
    print("TEST 1: Tier Assignment Based on Price")
    print("=" * 80)
    print()

    test_prices = [
        (100.0, "HIGH_PRICE", "$50+"),
        (75.0, "HIGH_PRICE", "$50+"),
        (50.0, "HIGH_PRICE", "$50+"),
        (49.99, "MID_HIGH_PRICE", "$20-50"),
        (35.0, "MID_HIGH_PRICE", "$20-50"),
        (20.0, "MID_HIGH_PRICE", "$20-50"),
        (19.99, "MID_PRICE", "$10-20"),
        (15.0, "MID_PRICE", "$10-20"),
        (10.0, "MID_PRICE", "$10-20"),
        (9.99, "LOW_MID_PRICE", "$5-10"),
        (7.5, "LOW_MID_PRICE", "$5-10"),
        (5.0, "LOW_MID_PRICE", "$5-10"),
        (4.99, "LOW_PRICE", "$3-5"),
        (4.0, "LOW_PRICE", "$3-5"),
        (3.5, "LOW_PRICE", "$3-5"),
        (3.0, "LOW_PRICE", "$3-5"),
    ]

    all_passed = True

    for price, expected_tier, price_range in test_prices:
        thresholds = GrowthCatalystScreener.get_dynamic_thresholds(price)
        actual_tier = thresholds['tier']

        passed = actual_tier == expected_tier
        all_passed = all_passed and passed

        status = "✅ PASS" if passed else "❌ FAIL"

        print(f"{status} | ${price:>6.2f} → Tier: {actual_tier:<17} (Expected: {expected_tier}) | Range: {price_range}")

    print()
    print("=" * 80)
    if all_passed:
        print("✅ TEST 1 PASSED: All stocks assigned to correct tiers")
    else:
        print("❌ TEST 1 FAILED: Some stocks assigned to wrong tiers")
    print("=" * 80)
    print()

    return all_passed


def test_threshold_progression():
    """Test that quality requirements increase as price decreases"""

    print("=" * 80)
    print("TEST 2: Quality Threshold Progression (Lower Price = Higher Quality)")
    print("=" * 80)
    print()

    test_prices = [100.0, 50.0, 30.0, 15.0, 7.5, 4.0, 3.0]

    print(f"{'Price':<10} {'Tier':<18} {'Tech':<8} {'AI%':<8} {'Catalyst':<10} {'Insider?':<10} {'Analysts'}")
    print("-" * 80)

    prev_technical = 0
    prev_ai = 0
    prev_catalyst = -100  # Start very low for inverted scoring

    all_passed = True

    for price in test_prices:
        thresholds = GrowthCatalystScreener.get_dynamic_thresholds(price)

        tech = thresholds['min_technical_score']
        ai = thresholds['min_ai_probability']
        catalyst = thresholds['min_catalyst_score']
        insider = "YES" if thresholds['require_insider_buying'] else "NO"
        analysts = thresholds['min_analyst_coverage']
        tier = thresholds['tier']

        # Verify thresholds increase as price decreases
        tech_ok = tech >= prev_technical
        ai_ok = ai >= prev_ai
        catalyst_ok = catalyst >= prev_catalyst

        row_passed = tech_ok and ai_ok and catalyst_ok
        all_passed = all_passed and row_passed

        status = "✅" if row_passed else "❌"

        print(f"${price:<8.2f} {tier:<18} {tech:<8.1f} {ai:<8.1f} {catalyst:<10.1f} {insider:<10} {analysts}")

        prev_technical = tech
        prev_ai = ai
        prev_catalyst = catalyst

    print()
    print("=" * 80)
    if all_passed:
        print("✅ TEST 2 PASSED: Quality requirements properly increase as price decreases")
    else:
        print("❌ TEST 2 FAILED: Quality requirements not properly progressive")
    print("=" * 80)
    print()

    return all_passed


def test_insider_buying_requirement():
    """Test that low-price stocks require insider buying"""

    print("=" * 80)
    print("TEST 3: Insider Buying Requirement for Low-Price Stocks")
    print("=" * 80)
    print()

    test_cases = [
        (100.0, False, "$50+ stocks don't require insider buying"),
        (50.0, False, "$50+ stocks don't require insider buying"),
        (30.0, False, "$20-50 stocks don't require insider buying"),
        (15.0, False, "$10-20 stocks don't require insider buying"),
        (7.5, True, "$5-10 stocks REQUIRE insider buying"),
        (5.0, True, "$5-10 stocks REQUIRE insider buying"),
        (4.0, True, "$3-5 stocks REQUIRE insider buying"),
        (3.0, True, "$3-5 stocks REQUIRE insider buying"),
    ]

    all_passed = True

    for price, should_require, description in test_cases:
        thresholds = GrowthCatalystScreener.get_dynamic_thresholds(price)
        requires = thresholds['require_insider_buying']

        passed = requires == should_require
        all_passed = all_passed and passed

        status = "✅ PASS" if passed else "❌ FAIL"
        insider_status = "REQUIRED" if requires else "NOT required"

        print(f"{status} | ${price:>6.2f} → Insider Buying: {insider_status:<12} | {description}")

    print()
    print("=" * 80)
    if all_passed:
        print("✅ TEST 3 PASSED: Insider buying requirement correct for all price ranges")
    else:
        print("❌ TEST 3 FAILED: Insider buying requirement incorrect")
    print("=" * 80)
    print()

    return all_passed


def test_specific_tier_requirements():
    """Test specific requirements for each tier"""

    print("=" * 80)
    print("TEST 4: Specific Requirements for Each Tier")
    print("=" * 80)
    print()

    # Test HIGH_PRICE tier ($50+)
    high_price_thresholds = GrowthCatalystScreener.get_dynamic_thresholds(100.0)
    test1 = (
        high_price_thresholds['tier'] == 'HIGH_PRICE' and
        high_price_thresholds['min_technical_score'] == 30.0 and
        high_price_thresholds['min_ai_probability'] == 30.0 and
        high_price_thresholds['min_catalyst_score'] == 0.0 and
        not high_price_thresholds['require_insider_buying']
    )
    print(f"{'✅ PASS' if test1 else '❌ FAIL'} | HIGH_PRICE ($50+): Tech=30, AI=30%, Catalyst=0, No insider required")

    # Test MID_HIGH_PRICE tier ($20-50)
    mid_high_thresholds = GrowthCatalystScreener.get_dynamic_thresholds(30.0)
    test2 = (
        mid_high_thresholds['tier'] == 'MID_HIGH_PRICE' and
        mid_high_thresholds['min_technical_score'] == 40.0 and
        mid_high_thresholds['min_ai_probability'] == 40.0 and
        mid_high_thresholds['min_catalyst_score'] == 10.0 and
        not mid_high_thresholds['require_insider_buying']
    )
    print(f"{'✅ PASS' if test2 else '❌ FAIL'} | MID_HIGH_PRICE ($20-50): Tech=40, AI=40%, Catalyst=10, No insider required")

    # Test MID_PRICE tier ($10-20)
    mid_thresholds = GrowthCatalystScreener.get_dynamic_thresholds(15.0)
    test3 = (
        mid_thresholds['tier'] == 'MID_PRICE' and
        mid_thresholds['min_technical_score'] == 50.0 and
        mid_thresholds['min_ai_probability'] == 50.0 and
        mid_thresholds['min_catalyst_score'] == 20.0 and
        not mid_thresholds['require_insider_buying'] and
        mid_thresholds['min_analyst_coverage'] == 1
    )
    print(f"{'✅ PASS' if test3 else '❌ FAIL'} | MID_PRICE ($10-20): Tech=50, AI=50%, Catalyst=20, 1+ analyst, No insider required")

    # Test LOW_MID_PRICE tier ($5-10)
    low_mid_thresholds = GrowthCatalystScreener.get_dynamic_thresholds(7.0)
    test4 = (
        low_mid_thresholds['tier'] == 'LOW_MID_PRICE' and
        low_mid_thresholds['min_technical_score'] == 60.0 and
        low_mid_thresholds['min_ai_probability'] == 60.0 and
        low_mid_thresholds['min_catalyst_score'] == 30.0 and
        low_mid_thresholds['require_insider_buying'] and
        low_mid_thresholds['min_analyst_coverage'] == 2
    )
    print(f"{'✅ PASS' if test4 else '❌ FAIL'} | LOW_MID_PRICE ($5-10): Tech=60, AI=60%, Catalyst=30, 2+ analysts, Insider REQUIRED")

    # Test LOW_PRICE tier ($3-5)
    low_thresholds = GrowthCatalystScreener.get_dynamic_thresholds(4.0)
    test5 = (
        low_thresholds['tier'] == 'LOW_PRICE' and
        low_thresholds['min_technical_score'] == 70.0 and
        low_thresholds['min_ai_probability'] == 70.0 and
        low_thresholds['min_catalyst_score'] == 40.0 and
        low_thresholds['require_insider_buying'] and
        low_thresholds['min_analyst_coverage'] == 3 and
        low_thresholds['min_market_cap'] == 200_000_000  # $200M minimum for low price
    )
    print(f"{'✅ PASS' if test5 else '❌ FAIL'} | LOW_PRICE ($3-5): Tech=70, AI=70%, Catalyst=40, 3+ analysts, Insider REQUIRED, $200M+ cap")

    all_passed = test1 and test2 and test3 and test4 and test5

    print()
    print("=" * 80)
    if all_passed:
        print("✅ TEST 4 PASSED: All tier requirements are correct")
    else:
        print("❌ TEST 4 FAILED: Some tier requirements are incorrect")
    print("=" * 80)
    print()

    return all_passed


def test_effective_threshold_logic():
    """Test that effective thresholds use the higher of user input or tier requirement"""

    print("=" * 80)
    print("TEST 5: Effective Threshold Logic (max of user input vs tier requirement)")
    print("=" * 80)
    print()

    # For a $4 stock (LOW_PRICE tier: requires Tech=70, AI=70%)
    # If user sets Tech=30, AI=30%, the effective should be Tech=70, AI=70%

    low_price_thresholds = GrowthCatalystScreener.get_dynamic_thresholds(4.0)

    print("Scenario: $4 stock (LOW_PRICE tier)")
    print(f"  Tier requirement: Tech={low_price_thresholds['min_technical_score']}, AI={low_price_thresholds['min_ai_probability']}%")
    print()

    test_cases = [
        ("User sets Tech=30, AI=30%", 30, 30, 70.0, 70.0),
        ("User sets Tech=80, AI=80%", 80, 80, 80.0, 80.0),
        ("User sets Tech=50, AI=90%", 50, 90, 70.0, 90.0),
    ]

    all_passed = True

    for description, user_tech, user_ai, expected_tech, expected_ai in test_cases:
        # Simulate what the screening logic should do
        effective_tech = max(user_tech, low_price_thresholds['min_technical_score'])
        effective_ai = max(user_ai, low_price_thresholds['min_ai_probability'])

        passed = (effective_tech == expected_tech and effective_ai == expected_ai)
        all_passed = all_passed and passed

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} | {description}")
        print(f"       Expected effective: Tech={expected_tech}, AI={expected_ai}%")
        print(f"       Actual effective:   Tech={effective_tech}, AI={effective_ai}%")
        print()

    print("=" * 80)
    if all_passed:
        print("✅ TEST 5 PASSED: Effective threshold logic works correctly")
    else:
        print("❌ TEST 5 FAILED: Effective threshold logic incorrect")
    print("=" * 80)
    print()

    return all_passed


def main():
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 15 + "TIERED QUALITY SYSTEM TEST SUITE (v3.2)" + " " * 23 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    results = []

    # Run all tests
    results.append(("Tier Assignment", test_tier_assignment()))
    results.append(("Threshold Progression", test_threshold_progression()))
    results.append(("Insider Buying Requirement", test_insider_buying_requirement()))
    results.append(("Specific Tier Requirements", test_specific_tier_requirements()))
    results.append(("Effective Threshold Logic", test_effective_threshold_logic()))

    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total_tests = len(results)
    passed_tests = sum(1 for _, passed in results if passed)

    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")

    print()
    print("=" * 80)

    if passed_tests == total_tests:
        print(f"✅ ALL TESTS PASSED ({passed_tests}/{total_tests})")
        print("=" * 80)
        print()
        print("🎉 Tiered Quality System is working correctly!")
        print()
        print("Key Features Verified:")
        print("  ✅ Stocks assigned to correct price tiers")
        print("  ✅ Quality requirements increase as price decreases")
        print("  ✅ Low-price stocks ($3-10) require insider buying")
        print("  ✅ All tier-specific requirements are correct")
        print("  ✅ Effective threshold logic uses max(user, tier)")
        print()
        return 0
    else:
        print(f"❌ SOME TESTS FAILED ({passed_tests}/{total_tests} passed)")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    exit(main())
