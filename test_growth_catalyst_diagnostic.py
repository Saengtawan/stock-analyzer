#!/usr/bin/env python3
"""
Diagnostic Test for Growth Catalyst Screener v7.1
Purpose: Find out why screener returns 0 stocks
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from main import StockAnalyzer
from screeners.growth_catalyst_screener import GrowthCatalystScreener
from loguru import logger

# Configure logger to show DEBUG messages
logger.remove()
logger.add(sys.stderr, level="DEBUG")

def test_with_relaxed_filters():
    """Test screener with progressively relaxed filters to find the bottleneck"""

    print("=" * 80)
    print("🔍 Growth Catalyst Screener v7.1 - Diagnostic Test")
    print("=" * 80)

    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    print("\n📊 Testing with current settings (10% target):")
    print("   - Target: 10%")
    print("   - Min Catalyst Score: 0")
    print("   - Min Technical Score: 30")
    print("   - Min AI Probability: 30%")
    print("-" * 80)

    # Test 1: Current settings
    print("\n🧪 Test 1: Current Settings")
    try:
        opportunities = screener.screen_growth_catalyst_opportunities(
            target_gain_pct=10.0,
            timeframe_days=30,
            min_catalyst_score=0.0,
            min_technical_score=30.0,
            min_ai_probability=30.0,
            max_stocks=20
        )
        print(f"✅ Result: Found {len(opportunities)} stocks")
        if opportunities:
            for opp in opportunities[:5]:
                print(f"   - {opp['symbol']}: Score {opp['composite_score']:.1f}")
        else:
            print("   ❌ No stocks found!")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 2: Even more relaxed
    print("\n🧪 Test 2: Ultra Relaxed Settings")
    print("   (Target: 5%, Min Scores: 0/20/20)")
    try:
        opportunities = screener.screen_growth_catalyst_opportunities(
            target_gain_pct=5.0,
            timeframe_days=30,
            min_catalyst_score=0.0,
            min_technical_score=20.0,
            min_ai_probability=20.0,
            max_stocks=20
        )
        print(f"✅ Result: Found {len(opportunities)} stocks")
        if opportunities:
            for opp in opportunities[:10]:
                print(f"   - {opp['symbol']}: Score {opp['composite_score']:.1f}, Beta {opp.get('beta', 'N/A'):.2f}")
        else:
            print("   ❌ Still no stocks found!")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 3: Test specific stock manually
    print("\n🧪 Test 3: Manual Test with Known Stocks")
    print("   Testing GOOGL, META, AAPL manually...")

    test_symbols = ['GOOGL', 'META', 'AAPL', 'MSFT', 'NVDA']

    for symbol in test_symbols:
        print(f"\n   Testing {symbol}:")
        try:
            result = screener._analyze_stock_comprehensive(
                symbol=symbol,
                target_gain_pct=10.0,
                timeframe_days=30
            )

            if result:
                print(f"   ✅ {symbol} PASSED all hard filters!")
                print(f"      - Beta: {result.get('beta', 'N/A'):.2f}")
                print(f"      - Sector Score: {result.get('sector_score', 'N/A'):.1f}")
                print(f"      - Valuation Score: {result.get('valuation_score', 'N/A'):.1f}")
                print(f"      - Catalyst Score: {result.get('catalyst_score', 'N/A'):.1f}")
                print(f"      - Technical Score: {result.get('technical_score', 'N/A'):.1f}")
                print(f"      - Composite Score: {result.get('composite_score', 'N/A'):.1f}")
            else:
                print(f"   ❌ {symbol} FAILED hard filters")

        except Exception as e:
            print(f"   ❌ {symbol} Error: {e}")

    print("\n" + "=" * 80)
    print("🎯 DIAGNOSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_with_relaxed_filters()
