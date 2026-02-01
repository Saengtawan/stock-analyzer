#!/usr/bin/env python3
"""
Test Scoring Weights - Verify composite score calculation
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from api.data_manager import DataManager
from screeners.growth_catalyst_screener import GrowthCatalystScreener
import logging

logging.basicConfig(level=logging.WARNING)

def test_scoring_weights():
    print("\n" + "="*80)
    print("🧪 SCORING WEIGHTS VERIFICATION")
    print("="*80)

    data_manager = DataManager()
    screener = GrowthCatalystScreener(data_manager)

    # Test AMAT (our #1 pick)
    symbol = 'AMAT'
    print(f"\nTesting {symbol}...")

    result = screener._analyze_stock_comprehensive(symbol, 5.0, 30)

    if not result:
        print("❌ Failed to analyze")
        return

    print("\n" + "="*80)
    print(f"📊 COMPONENT SCORES FOR {symbol}")
    print("="*80)

    # Get component scores
    alt_data = result.get('alt_data_score', 0)
    technical = result.get('technical_score', 0)
    sector = result.get('sector_score', 0)
    valuation = result.get('valuation_score', 0)
    catalyst = result.get('catalyst_score', 0)
    ai_prob = result.get('ai_probability', 0)

    print(f"\n{'Component':<20} {'Score':<10} {'Weight':<10} {'Contribution':<15}")
    print("-" * 80)
    print(f"{'Alt Data':<20} {alt_data:>6.1f}/100  {'25%':<10} {alt_data * 0.25:>10.2f}")
    print(f"{'Technical':<20} {technical:>6.1f}/100  {'25%':<10} {technical * 0.25:>10.2f}")
    print(f"{'Sector':<20} {sector:>6.1f}/100  {'20%':<10} {sector * 0.20:>10.2f}")
    print(f"{'Valuation':<20} {valuation:>6.1f}/100  {'15%':<10} {valuation * 0.15:>10.2f}")
    print(f"{'Catalyst':<20} {catalyst:>6.1f}/100  {'10%':<10} {catalyst * 0.10:>10.2f}")
    print(f"{'AI Probability':<20} {ai_prob:>6.1f}/100  {'5%':<10} {ai_prob * 0.05:>10.2f}")
    print("-" * 80)

    # Calculate manually
    base_composite = (
        alt_data * 0.25 +
        technical * 0.25 +
        sector * 0.20 +
        valuation * 0.15 +
        catalyst * 0.10 +
        ai_prob * 0.05
    )

    print(f"{'Base Composite':<20} {'':<10} {'100%':<10} {base_composite:>10.2f}")

    # Sector rotation boost
    boost = result.get('sector_rotation_boost', 1.0)
    final_composite = base_composite * boost

    print(f"\n{'Sector Rotation':<20} {'':<10} {'Boost':<10} {boost:>9.2f}x")
    print(f"{'Final Composite':<20} {'':<10} {'':<10} {final_composite:>10.2f}")

    # Verify
    actual_composite = result.get('composite_score', 0)

    print("\n" + "="*80)
    print("✅ VERIFICATION")
    print("="*80)

    print(f"\nCalculated Composite: {final_composite:.1f}")
    print(f"Actual Composite:     {actual_composite:.1f}")
    print(f"Difference:           {abs(final_composite - actual_composite):.1f}")

    if abs(final_composite - actual_composite) < 0.1:
        print("\n✅ WEIGHTS CORRECT - Calculation matches!")
    else:
        print("\n❌ WEIGHTS INCORRECT - Calculation mismatch!")

    # Check weight totals
    print("\n" + "="*80)
    print("📊 WEIGHT DISTRIBUTION")
    print("="*80)

    weights = {
        'Alt Data': 0.25,
        'Technical': 0.25,
        'Sector': 0.20,
        'Valuation': 0.15,
        'Catalyst': 0.10,
        'AI Probability': 0.05,
    }

    print(f"\n{'Component':<20} {'Weight':<10} {'Percentage':<15}")
    print("-" * 60)
    for comp, weight in weights.items():
        print(f"{comp:<20} {weight:<10.2f} {weight*100:>6.1f}%")
    print("-" * 60)
    total_weight = sum(weights.values())
    print(f"{'TOTAL':<20} {total_weight:<10.2f} {total_weight*100:>6.1f}%")

    if abs(total_weight - 1.0) < 0.001:
        print("\n✅ WEIGHTS SUM TO 100%")
    else:
        print(f"\n❌ WEIGHTS DON'T SUM TO 100% (={total_weight*100:.1f}%)")

    # Show sector rotation impact
    print("\n" + "="*80)
    print("🚀 SECTOR ROTATION IMPACT")
    print("="*80)

    sector_name = result.get('sector', 'Unknown')
    sector_momentum = result.get('sector_momentum', 0)
    sector_status = result.get('sector_rotation_status', 'unknown')

    print(f"\nSector: {sector_name}")
    print(f"Status: {sector_status}")
    print(f"Momentum: {sector_momentum:+.1f}%")
    print(f"Boost: {boost:.2f}x")

    print(f"\nWithout Sector Boost: {base_composite:.1f}")
    print(f"With Sector Boost:    {final_composite:.1f}")
    print(f"Improvement:          +{((final_composite - base_composite) / base_composite * 100):.1f}%")

    if sector_status == 'hot' and boost > 1.0:
        print(f"\n✅ Hot sector boost working correctly!")
    elif sector_status == 'cold' and boost < 1.0:
        print(f"\n✅ Cold sector penalty working correctly!")
    elif sector_status == 'neutral' and boost == 1.0:
        print(f"\n✅ Neutral sector (no boost) working correctly!")

    # Check for alt data boost
    print("\n" + "="*80)
    print("💡 ALT DATA BONUS")
    print("="*80)

    signals = result.get('alt_data_signals', 0)
    print(f"\nAlternative Data Signals: {signals}/6")

    if signals >= 3:
        print(f"✅ Qualifies for 10% alt data boost (≥3 signals)")
        print(f"   Base alt score would be ~{alt_data / 1.1:.1f}")
        print(f"   Boosted to: {alt_data:.1f}")
    else:
        print(f"❌ No alt data boost (<3 signals)")

    print("\n" + "="*80)
    print("✅ Test Complete!")
    print("="*80)


if __name__ == "__main__":
    test_scoring_weights()
