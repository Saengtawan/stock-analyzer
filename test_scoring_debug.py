#!/usr/bin/env python3
"""
Debug Scoring Calculation - Find the mismatch
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from api.data_manager import DataManager
from screeners.growth_catalyst_screener import GrowthCatalystScreener
import logging

logging.basicConfig(level=logging.WARNING)

# Test calculation directly
print("\n" + "="*80)
print("🔍 DEBUG: Manual Scoring Calculation")
print("="*80)

# AMAT scores from test
alt_data_raw = 53.3  # Before boost
alt_data_boosted = 58.6  # After 10% boost (53.3 * 1.1 = 58.63)
technical = 25.0
sector = 45.0
valuation = 95.0
catalyst = 20.0
ai_prob = 35.0

print("\n📊 Component Scores (exact values):")
print(f"Alt Data (raw):    {alt_data_raw:.2f}")
print(f"Alt Data (boost):  {alt_data_boosted:.2f} (10% boost for ≥3 signals)")
print(f"Technical:         {technical:.2f}")
print(f"Sector:            {sector:.2f}")
print(f"Valuation:         {valuation:.2f}")
print(f"Catalyst:          {catalyst:.2f}")
print(f"AI Probability:    {ai_prob:.2f}")

print("\n📐 Weighted Contributions:")
contributions = {
    'Alt Data': alt_data_boosted * 0.25,
    'Technical': technical * 0.25,
    'Sector': sector * 0.20,
    'Valuation': valuation * 0.15,
    'Catalyst': catalyst * 0.10,
    'AI Prob': ai_prob * 0.05,
}

for comp, value in contributions.items():
    print(f"{comp:<15} {value:>8.4f}")

base = sum(contributions.values())
print(f"{'BASE COMPOSITE':<15} {base:>8.4f}")

# Sector boost
boost = 1.20
final = base * boost
print(f"\nSector Boost: {boost}x")
print(f"{'FINAL':<15} {final:>8.4f}")

# Round
final_rounded = round(final, 1)
print(f"{'ROUNDED':<15} {final_rounded:>8.1f}")

print("\n" + "="*80)

# Now test actual
data_manager = DataManager()
screener = GrowthCatalystScreener(data_manager)

print("Testing AMAT with actual screener...")
result = screener._analyze_stock_comprehensive('AMAT', 5.0, 30)

if result:
    actual = result['composite_score']
    alt_actual = result['alt_data_score']

    print(f"\n✅ Actual Results:")
    print(f"Alt Data Score: {alt_actual:.1f}")
    print(f"Composite Score: {actual:.1f}")

    print(f"\n🔎 Comparison:")
    print(f"Calculated: {final_rounded:.1f}")
    print(f"Actual:     {actual:.1f}")
    print(f"Difference: {abs(final_rounded - actual):.1f}")

    if abs(final_rounded - actual) < 0.1:
        print("\n✅ MATCH!")
    else:
        print(f"\n❌ MISMATCH by {abs(final_rounded - actual):.1f} points")

        # Try to find the issue
        print("\n🔍 Investigating...")

        # Check if alt_data_score is different
        if abs(alt_actual - alt_data_boosted) > 0.1:
            print(f"   • Alt data score different: expected {alt_data_boosted:.1f}, got {alt_actual:.1f}")

        # Recalculate with actual alt score
        recalc_base = (
            alt_actual * 0.25 +
            technical * 0.25 +
            sector * 0.20 +
            valuation * 0.15 +
            catalyst * 0.10 +
            ai_prob * 0.05
        )
        recalc_final = round(recalc_base * boost, 1)

        print(f"   • Recalculated with actual alt score: {recalc_final:.1f}")

        if abs(recalc_final - actual) < 0.1:
            print(f"   ✅ MATCH after using actual alt score!")
        else:
            print(f"   ❌ Still mismatch - there's another factor")

            # Check all component scores
            print(f"\n   Checking all components:")
            print(f"   Alt Data:   expected {alt_data_boosted:.1f}, actual {result.get('alt_data_score', 0):.1f}")
            print(f"   Technical:  expected {technical:.1f}, actual {result.get('technical_score', 0):.1f}")
            print(f"   Sector:     expected {sector:.1f}, actual {result.get('sector_score', 0):.1f}")
            print(f"   Valuation:  expected {valuation:.1f}, actual {result.get('valuation_score', 0):.1f}")
            print(f"   Catalyst:   expected {catalyst:.1f}, actual {result.get('catalyst_score', 0):.1f}")
            print(f"   AI Prob:    expected {ai_prob:.1f}, actual {result.get('ai_probability', 0):.1f}")
            print(f"   Boost:      expected {boost:.2f}, actual {result.get('sector_rotation_boost', 1.0):.2f}")

print("\n" + "="*80)
