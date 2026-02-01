#!/usr/bin/env python3
"""
Test screening with adjusted thresholds
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
    print("TESTING WITH ADJUSTED THRESHOLDS (NEW DEFAULTS)")
    print("="*70)
    print("\nOLD defaults that gave 0 results:")
    print("  ❌ Min Catalyst Score: 30")
    print("  ❌ Min Technical Score: 50  <- TOO HIGH")
    print("  ❌ Min AI Probability: 50%  <- TOO HIGH")
    print("\nNEW defaults:")
    print("  ✅ Min Catalyst Score: 30")
    print("  ✅ Min Technical Score: 40  <- LOWERED")
    print("  ✅ Min AI Probability: 40%  <- LOWERED")
    print("="*70)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Run with adjusted parameters
    print("\n🔍 Running screening with new thresholds...")

    results = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=10.0,
        timeframe_days=30,
        min_catalyst_score=30.0,
        min_technical_score=40.0,  # Lowered from 50
        min_ai_probability=40.0,    # Lowered from 50
        max_stocks=20
    )

    print(f"\n{'='*70}")
    print(f"RESULTS")
    print(f"{'='*70}")
    print(f"✅ Found {len(results)} high-quality growth opportunities\n")

    if len(results) > 0:
        print("Top 10 Opportunities:\n")
        for i, opp in enumerate(results[:10], 1):
            print(f"{i:2d}. {opp['symbol']:6s} - Composite: {opp['composite_score']:4.1f} | "
                  f"Catalyst: {opp['catalyst_score']:4.1f} | "
                  f"Technical: {opp['technical_score']:4.1f} | "
                  f"AI Prob: {opp['ai_probability']:4.1f}%")

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

        print(f"\n✅ SUCCESS! The screening now finds opportunities with adjusted thresholds.")
    else:
        print("⚠️  Still 0 results. May need to lower thresholds further.")

    print(f"\n{'='*70}")

if __name__ == "__main__":
    main()
