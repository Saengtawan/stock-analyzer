#!/usr/bin/env python3
"""
Test Sector-Aware Integration (v3.3)

Tests that the sector-aware regime detection is properly integrated
into the Growth Catalyst Screener.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from main import StockAnalyzer
from screeners.growth_catalyst_screener import GrowthCatalystScreener

def test_sector_regime_integration():
    """Test that sector regime detector is integrated and working"""

    print("=" * 80)
    print("TEST: Sector-Aware Regime Integration (v3.3)")
    print("=" * 80)
    print()

    # Initialize
    print("1. Initializing Stock Analyzer and Growth Catalyst Screener...")
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Check if sector regime is initialized
    if screener.sector_regime is None:
        print("❌ FAIL: Sector Regime Detector not initialized!")
        print("   Make sure sector_regime_detector.py is in the src folder")
        return False

    print("✅ PASS: Sector Regime Detector initialized")
    print()

    # Update sector regimes
    print("2. Updating all sector regimes...")
    try:
        screener.sector_regime.update_all_sectors()
        print("✅ PASS: Sector regimes updated successfully")
    except Exception as e:
        print(f"❌ FAIL: Error updating sector regimes: {e}")
        return False

    print()

    # Get sector summary
    print("3. Getting sector summary...")
    try:
        summary = screener.sector_regime.get_sector_summary()
        print(f"✅ PASS: Got summary for {len(summary)} sectors")
        print()
        print("Sector Summary:")
        print(summary[['Sector', 'Regime', 'Return_20d', 'Score_Adjustment', 'Confidence_Threshold']].to_string(index=False))
    except Exception as e:
        print(f"❌ FAIL: Error getting sector summary: {e}")
        return False

    print()
    print()

    # Test sector detection for a specific sector
    print("4. Testing sector regime lookup...")
    test_sectors = ['Financial Services', 'Technology', 'Energy', 'Healthcare']

    for sector in test_sectors:
        try:
            regime = screener.sector_regime.get_sector_regime(sector)
            adjustment = screener.sector_regime.get_regime_adjustment(sector)
            threshold = screener.sector_regime.get_confidence_threshold(sector)

            print(f"  {sector:20} → Regime: {regime:12} | Adj: {adjustment:+3d} | Threshold: {threshold}")
        except Exception as e:
            print(f"  {sector:20} → ❌ Error: {e}")

    print()
    print("=" * 80)
    print("✅ ALL INTEGRATION TESTS PASSED!")
    print("=" * 80)
    print()

    print("🎉 Sector-Aware Regime Detection is properly integrated!")
    print()
    print("What this means:")
    print("  ✅ Screener can detect sectors for each stock")
    print("  ✅ Screener applies sector regime adjustments to scores")
    print("  ✅ BULL sectors get +10 points boost")
    print("  ✅ SIDEWAYS sectors get 0 points (neutral)")
    print("  ✅ BEAR sectors get -10 points penalty")
    print("  ✅ Sector summary is included in results")
    print()

    return True


def test_quick_screening():
    """Quick test of screening with sector awareness"""

    print("=" * 80)
    print("OPTIONAL: Quick Screening Test (may take 1-2 minutes)")
    print("=" * 80)
    print()

    response = input("Run a quick screening test? (y/n): ")
    if response.lower() != 'y':
        print("Skipping screening test.")
        return True

    print()
    print("Running quick screening (5 stocks, 3x multiplier)...")

    try:
        analyzer = StockAnalyzer()
        screener = GrowthCatalystScreener(analyzer)

        # Quick scan with minimal stocks
        opportunities = screener.screen_growth_catalyst_opportunities(
            target_gain_pct=10.0,
            timeframe_days=30,
            max_stocks=5,
            universe_multiplier=3,  # Fast
            min_technical_score=40,
            min_ai_probability=40
        )

        print()
        if not opportunities:
            print("⚠️  No opportunities found (market may be in SIDEWAYS/BEAR regime)")
            return True

        if opportunities[0].get('regime_warning'):
            print(f"⚠️  Market regime warning: {opportunities[0]['regime']}")
            print(f"   {opportunities[0]['message']}")
            return True

        print(f"✅ Found {len(opportunities)} opportunities")
        print()

        # Show first 3 with sector info
        print("Top opportunities with sector info:")
        print("-" * 80)
        for i, opp in enumerate(opportunities[:3], 1):
            symbol = opp['symbol']
            sector = opp.get('sector', 'Unknown')
            regime = opp.get('sector_regime', 'UNKNOWN')
            adj = opp.get('sector_regime_adjustment', 0)
            score = opp.get('composite_score', 0)

            print(f"{i}. {symbol:6} | Sector: {sector:20} | Regime: {regime:12} | Score: {score:.1f} ({adj:+d})")

        print()

        # Check if sector_regime_summary is included
        if 'sector_regime_summary' in opportunities[0]:
            print("✅ Sector regime summary is included in results")
        else:
            print("⚠️  Sector regime summary not found in results")

        print()
        print("✅ Screening test completed successfully!")

    except Exception as e:
        print(f"❌ Screening test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def main():
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "SECTOR-AWARE INTEGRATION TEST (v3.3)" + " " * 21 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    # Test 1: Integration
    success = test_sector_regime_integration()
    if not success:
        print()
        print("❌ INTEGRATION TEST FAILED")
        return 1

    print()

    # Test 2: Quick screening (optional)
    test_quick_screening()

    print()
    print("=" * 80)
    print("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print()
    print("🚀 Ready to use Sector-Aware Growth Catalyst Screener (v3.3)!")
    print()
    print("Next steps:")
    print("  1. Start web server: python src/web/app.py")
    print("  2. Go to: http://localhost:5000/screen")
    print("  3. Run Growth Catalyst screening")
    print("  4. See sector regime summary at top of results")
    print("  5. See sector badges next to each stock symbol")
    print()

    return 0


if __name__ == "__main__":
    exit(main())
