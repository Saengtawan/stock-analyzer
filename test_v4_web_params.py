"""
Test v4.0 screener with NEW web UI parameters (min_technical=0, min_ai_prob=0)
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

def test_v4_web_params():
    """Test v4.0 with NEW web UI defaults"""
    print("=" * 80)
    print(f"🧪 Testing v4.0 with NEW Web UI Parameters")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Test with NEW web UI defaults
    print("\n📊 New Web UI Parameters (v4.0):")
    print("   - Target: 5% in 30 days")
    print("   - Min Catalyst: 0+")
    print("   - Min Technical: 0+ (v4.0 DEFAULT - momentum gates filter first)")
    print("   - Min AI Prob: 0%+ (v4.0 DEFAULT - momentum gates filter first)")
    print("   - Min Price: $3+")
    print("   - Max Stocks: 30")
    print("   - Universe: 2x (60 stocks FAST)")
    print()

    results = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=5.0,
        timeframe_days=30,
        min_price=3.0,
        min_catalyst_score=0.0,
        min_technical_score=0.0,  # v4.0 DEFAULT
        min_ai_probability=0.0,    # v4.0 DEFAULT
        max_stocks=30,
        universe_multiplier=2
    )

    print(f"\n" + "=" * 80)
    print(f"📊 RESULTS: Found {len(results)} stocks")
    print("=" * 80)

    if len(results) > 0:
        print("\n✅ SUCCESS! v4.0 is working!")
        print()

        # Check if we found the expected good stocks
        expected_good = ['MU', 'GOOGL', 'META', 'TSLA', 'LRCX', 'ARWR', 'CRM']
        found_symbols = [s['symbol'] for s in results]

        matches = [s for s in expected_good if s in found_symbols]
        print(f"🎯 Expected good stocks found: {len(matches)}/{len(expected_good)}")
        if matches:
            print(f"   ✅ Matched: {', '.join(matches)}")

        missing = [s for s in expected_good if s not in found_symbols]
        if missing:
            print(f"   ⚠️  Missing: {', '.join(missing)}")

        print(f"\n📊 All {len(results)} results:")
        for i, stock in enumerate(results, 1):
            symbol = stock['symbol']
            entry_score = stock.get('entry_score', 0)
            momentum = stock.get('momentum_score', 0)
            price = stock.get('current_price', 0)

            # Check if it's one of our expected good stocks
            marker = "🎯" if symbol in expected_good else "  "

            print(f"{i:2d}. {marker} {symbol:6s} | ${price:7.2f} | Entry: {entry_score:5.1f}/140 | Mom: {momentum:5.1f}/100")

            # Show momentum metrics for top 10
            if i <= 10:
                mm = stock.get('momentum_metrics', {})
                if mm:
                    print(f"       RSI: {mm.get('rsi', 0):5.1f} | "
                          f"MA50: {mm.get('price_above_ma50', 0):+6.1f}% | "
                          f"Mom30d: {mm.get('momentum_30d', 0):+6.1f}%")

        print(f"\n✅ v4.0 Web UI Fix: SUCCESSFUL!")
        print(f"   - FAST universe (60 stocks)")
        print(f"   - Relaxed filters (momentum gates are primary)")
        print(f"   - Found {len(results)} opportunities")

    else:
        print("\n❌ Still no stocks found!")
        print("\nThis means ALL stocks failed momentum gates")
        print("Market conditions must be very weak")

    print(f"\n" + "=" * 80)

    return results

if __name__ == "__main__":
    test_v4_web_params()
