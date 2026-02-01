#!/usr/bin/env python3
"""
Test with final adjusted thresholds
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from main import StockAnalyzer
import logging

logging.basicConfig(level=logging.WARNING)

def main():
    print("="*70)
    print("FINAL THRESHOLD TEST - NEW DEFAULTS FOR UI")
    print("="*70)
    print("\n✅ NEW OPTIMIZED DEFAULTS:")
    print("  - Min Catalyst Score:   30    (PASS: 30-45 range typical)")
    print("  - Min Technical Score:  30    (PASS: 25-40 range typical)")
    print("  - Min AI Probability:   35%   (PASS: 28-55% range typical)")
    print("  - Max Price:            $2000 (include META, etc.)")
    print("="*70)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Run with final optimized parameters
    print("\n🔍 Running screening...")

    results = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=10.0,
        timeframe_days=30,
        min_catalyst_score=30.0,
        min_technical_score=30.0,   # Lowered from 40
        min_ai_probability=35.0,     # Lowered from 40
        max_price=2000.0,            # Increased from 500
        max_stocks=20
    )

    print(f"\n{'='*70}")
    print(f"RESULTS")
    print(f"{'='*70}")
    print(f"✅ Found {len(results)} high-quality growth opportunities\n")

    if len(results) > 0:
        print("Top Opportunities:\n")
        print(f"{'#':<3} {'Symbol':<8} {'Composite':<10} {'Catalyst':<10} {'Technical':<10} {'AI Prob':<10} {'Price':<10}")
        print("-" * 70)

        for i, opp in enumerate(results[:15], 1):
            print(f"{i:<3} {opp['symbol']:<8} "
                  f"{opp['composite_score']:>6.1f}/100  "
                  f"{opp['catalyst_score']:>6.1f}/100  "
                  f"{opp['technical_score']:>6.1f}/100  "
                  f"{opp['ai_probability']:>6.1f}%     "
                  f"${opp['current_price']:>7.2f}")

        # Show average scores
        avg_catalyst = sum(r['catalyst_score'] for r in results) / len(results)
        avg_technical = sum(r['technical_score'] for r in results) / len(results)
        avg_ai_prob = sum(r['ai_probability'] for r in results) / len(results)
        avg_composite = sum(r['composite_score'] for r in results) / len(results)

        print(f"\n📊 Average Scores:")
        print(f"   Catalyst:   {avg_catalyst:.1f}/100")
        print(f"   Technical:  {avg_technical:.1f}/100")
        print(f"   AI Prob:    {avg_ai_prob:.1f}%")
        print(f"   Composite:  {avg_composite:.1f}/100")

        # Show top 3 with catalysts
        print(f"\n🎯 Top 3 with Catalyst Details:\n")
        for i, opp in enumerate(results[:3], 1):
            print(f"{i}. {opp['symbol']} - Composite Score: {opp['composite_score']:.1f}/100")
            if opp.get('catalysts'):
                print(f"   Catalysts:")
                for cat in opp['catalysts'][:3]:
                    print(f"      • {cat['description']} ({cat['score']} pts)")
            print()

        print(f"✅ SUCCESS! The screening finds {len(results)} opportunities with optimized thresholds.")
    else:
        print("⚠️  Still 0 results.")

    print(f"\n{'='*70}")

if __name__ == "__main__":
    main()
