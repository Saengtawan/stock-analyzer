"""
Test current Growth Catalyst Screener v4.0 to see if it finds stocks
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

def test_screener():
    """Test v4.0 screener with current market"""
    print("=" * 80)
    print(f"🧪 Testing Growth Catalyst Screener v4.0")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Test with parameters from web UI
    print("\n📊 Running screen with Web UI parameters:")
    print("   - Target: 5% in 30 days")
    print("   - Min Price: $3+")
    print("   - Min Catalyst: 0+")
    print("   - Min Technical: 30+")
    print("   - Min AI Prob: 30%+")
    print("   - Max Stocks: 30")
    print("   - Universe: 5x (150 stocks)")

    results = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=5.0,
        timeframe_days=30,
        min_price=3.0,
        min_catalyst_score=0.0,
        min_technical_score=30.0,
        min_ai_probability=30.0,
        max_stocks=30,
        universe_multiplier=5
    )

    print(f"\n" + "=" * 80)
    print(f"📊 RESULTS: Found {len(results)} stocks")
    print("=" * 80)

    if len(results) == 0:
        print("\n❌ NO STOCKS FOUND!")
        print("\nPossible reasons:")
        print("1. Market conditions: All stocks failing momentum gates")
        print("2. Too strict filters: Try relaxing parameters")
        print("3. Data issues: API rate limiting or data unavailable")

        # Try with more relaxed parameters
        print("\n" + "=" * 80)
        print("🔄 Trying RELAXED parameters...")
        print("=" * 80)
        print("   - Min Technical: 0 (vs 30)")
        print("   - Min AI Prob: 0% (vs 30%)")

        results_relaxed = screener.screen_growth_catalyst_opportunities(
            target_gain_pct=5.0,
            timeframe_days=30,
            min_price=3.0,
            min_catalyst_score=0.0,
            min_technical_score=0.0,  # RELAXED
            min_ai_probability=0.0,    # RELAXED
            max_stocks=30,
            universe_multiplier=5
        )

        print(f"\n📊 RELAXED RESULTS: Found {len(results_relaxed)} stocks")

        if len(results_relaxed) > 0:
            print("\n✅ Found stocks with relaxed parameters!")
            print("\nTop 5 stocks:")
            for i, stock in enumerate(results_relaxed[:5], 1):
                print(f"\n{i}. {stock['symbol']} - ${stock['current_price']:.2f}")
                print(f"   Entry Score: {stock.get('entry_score', 0):.1f}/140")
                print(f"   Momentum: {stock.get('momentum_score', 0):.1f}/100")
                print(f"   Technical: {stock.get('technical_score', 0):.1f}/100")
                print(f"   AI Prob: {stock.get('ai_probability', 0):.1f}%")
                print(f"   Alt Data: {stock.get('alt_data_signals', 0)}/6")

                # Momentum metrics
                momentum_metrics = stock.get('momentum_metrics', {})
                if momentum_metrics:
                    print(f"   RSI: {momentum_metrics.get('rsi', 0):.1f}")
                    print(f"   MA50: {momentum_metrics.get('price_above_ma50', 0):+.1f}%")
                    print(f"   Mom30d: {momentum_metrics.get('momentum_30d', 0):+.1f}%")
        else:
            print("\n❌ Still no stocks found even with relaxed parameters!")
            print("\n🔍 This suggests:")
            print("   1. Momentum gates are rejecting ALL stocks")
            print("   2. Market is in poor condition right now")
            print("   3. Or there's a data/API issue")

    else:
        print("\n✅ Found stocks!")
        print("\nTop 10 stocks:")
        for i, stock in enumerate(results[:10], 1):
            print(f"\n{i}. {stock['symbol']} - ${stock['current_price']:.2f}")
            print(f"   Entry Score: {stock.get('entry_score', 0):.1f}/140")
            print(f"   Momentum: {stock.get('momentum_score', 0):.1f}/100")
            print(f"   Technical: {stock.get('technical_score', 0):.1f}/100")
            print(f"   AI Prob: {stock.get('ai_probability', 0):.1f}%")
            print(f"   Alt Data: {stock.get('alt_data_signals', 0)}/6")

            # Momentum metrics
            momentum_metrics = stock.get('momentum_metrics', {})
            if momentum_metrics:
                print(f"   RSI: {momentum_metrics.get('rsi', 0):.1f}")
                print(f"   MA50: {momentum_metrics.get('price_above_ma50', 0):+.1f}%")
                print(f"   Mom30d: {momentum_metrics.get('momentum_30d', 0):+.1f}%")

    print("\n" + "=" * 80)
    return results

if __name__ == "__main__":
    test_screener()
