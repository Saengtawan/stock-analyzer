"""
Test the FAST v4.0 screener with pre-defined universe
"""
import sys
import os
from datetime import datetime
from loguru import logger

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from main import StockAnalyzer
from screeners.growth_catalyst_screener import GrowthCatalystScreener

logger.remove()
logger.add(sys.stdout, level="INFO", format="<level>{message}</level>")

def test_fast_screener():
    """Test v4.0 FAST mode with pre-defined universe"""
    print("=" * 80)
    print(f"🧪 Testing Growth Catalyst Screener v4.0 FAST MODE")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Test with 2x multiplier (60 stocks)
    print("\n📊 Running screen with FAST parameters:")
    print("   - Target: 5% in 30 days")
    print("   - Min Technical: 30+")
    print("   - Min AI Prob: 30%+")
    print("   - Max Stocks: 30")
    print("   - Universe: 2x (60 stocks) - FAST MODE")
    print()

    results = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=5.0,
        timeframe_days=30,
        min_price=3.0,
        min_catalyst_score=0.0,
        min_technical_score=30.0,
        min_ai_probability=30.0,
        max_stocks=30,
        universe_multiplier=2  # FAST: 60 stocks
    )

    print(f"\n" + "=" * 80)
    print(f"📊 RESULTS: Found {len(results)} stocks")
    print("=" * 80)

    if len(results) > 0:
        print("\n✅ SUCCESS! Found stocks:")
        print()

        # Check if we found the expected good stocks
        expected_good = ['MU', 'GOOGL', 'META', 'TSLA', 'LRCX', 'ARWR', 'CRM']
        found_symbols = [s['symbol'] for s in results]

        matches = [s for s in expected_good if s in found_symbols]
        print(f"Expected good stocks found: {len(matches)}/{len(expected_good)}")
        if matches:
            print(f"   Matched: {', '.join(matches)}")

        print(f"\nTop 10 results:")
        for i, stock in enumerate(results[:10], 1):
            symbol = stock['symbol']
            entry_score = stock.get('entry_score', 0)
            momentum = stock.get('momentum_score', 0)
            technical = stock.get('technical_score', 0)
            ai_prob = stock.get('ai_probability', 0)

            # Check if it's one of our expected good stocks
            marker = "🎯" if symbol in expected_good else "  "

            print(f"{i:2d}. {marker} {symbol:6s} | Entry: {entry_score:5.1f}/140 | "
                  f"Mom: {momentum:5.1f}/100 | Tech: {technical:4.1f} | AI: {ai_prob:4.1f}%")

            # Show momentum metrics for expected stocks
            if symbol in expected_good:
                mm = stock.get('momentum_metrics', {})
                if mm:
                    print(f"       RSI: {mm.get('rsi', 0):5.1f} | "
                          f"MA50: {mm.get('price_above_ma50', 0):+6.1f}% | "
                          f"Mom30d: {mm.get('momentum_30d', 0):+6.1f}%")
    else:
        print("\n⚠️ No stocks found")
        print("\nThis could mean:")
        print("1. Market conditions are very weak right now")
        print("2. Technical/AI filters are too strict")
        print("3. Or there's still an issue")

    print(f"\n" + "=" * 80)
    print("✅ Test Complete")
    print("=" * 80)

    return results

if __name__ == "__main__":
    test_fast_screener()
