#!/usr/bin/env python3
"""
Test Support Level Screener
"""
import sys
from main import StockAnalyzer
from screeners.support_level_screener import SupportLevelScreener

def test_support_screener():
    """Test the support level screener with a small sample"""
    print("🔍 Testing Support Level Screener...")

    # Initialize
    analyzer = StockAnalyzer()
    screener = SupportLevelScreener(analyzer)

    # AI-only screener - no need to set stock_universe manually
    print(f"Testing AI-powered support level screener...")

    try:
        # Screen for opportunities
        opportunities = screener.screen_support_opportunities(
            max_distance_from_support=0.05,  # 5% below support max
            min_fundamental_score=4.0,        # Lower threshold for testing
            min_technical_score=3.0,          # Lower threshold for testing
            max_stocks=10,
            time_horizon='medium'
        )

        # Display results
        results_text = screener.format_results(opportunities)
        print(results_text)

        # Additional detailed info for found opportunities
        if opportunities:
            print(f"\n📊 Detailed Analysis of Top Opportunities:")
            for i, opp in enumerate(opportunities[:3], 1):
                print(f"\n{i}. {opp['symbol']} - Detailed Breakdown:")
                print(f"   Current Price: ${opp['current_price']:.2f}")
                print(f"   Support Level 1: ${opp['support_1']:.2f}")
                print(f"   Support Level 2: ${opp['support_2']:.2f}")
                print(f"   Resistance Level 1: ${opp['resistance_1']:.2f}")
                print(f"   Distance from Support: {opp['distance_from_support_pct']:.2f}%")
                print(f"   Attractiveness Score: {opp['attractiveness_score']:.1f}/10")
                print(f"   Risk/Reward Ratio: {opp['risk_reward_ratio']:.1f}:1")
                print(f"   Upside to Resistance: {opp['upside_to_resistance']:.1f}%")

        return len(opportunities) > 0

    except Exception as e:
        print(f"❌ Screener test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_support_screener()
    sys.exit(0 if success else 1)