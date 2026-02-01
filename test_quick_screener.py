"""
Quick test of Growth Catalyst Screener v4.0 - test specific stocks
"""
import sys
import os
from datetime import datetime, timedelta
from loguru import logger

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from main import StockAnalyzer
from screeners.growth_catalyst_screener import GrowthCatalystScreener

logger.remove()
logger.add(sys.stdout, level="INFO", format="<level>{message}</level>")

def test_specific_stocks():
    """Test v4.0 with specific stocks we know should work"""
    print("=" * 80)
    print(f"🧪 Quick Test: Growth Catalyst Screener v4.0")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 80)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Test stocks from our backtest that passed v4.0
    test_stocks = ['MU', 'NVDA', 'AAPL', 'GOOGL', 'META', 'TSLA', 'AMD', 'MSFT']

    print(f"\n🔍 Testing {len(test_stocks)} specific stocks:")
    print(f"   {', '.join(test_stocks)}")

    passed = []
    failed = []

    for symbol in test_stocks:
        print(f"\n{'='*60}")
        print(f"📊 Testing: {symbol}")
        print(f"{'='*60}")

        result = screener._analyze_stock_comprehensive(
            symbol=symbol,
            target_gain_pct=5.0,
            timeframe_days=30
        )

        if result and result.get('passed_filters'):
            passed.append(result)
            print(f"✅ {symbol} PASSED")
            print(f"   Entry Score: {result.get('entry_score', 0):.1f}/140")
            print(f"   Momentum: {result.get('momentum_score', 0):.1f}/100")
            print(f"   Technical: {result.get('technical_score', 0):.1f}/100")
            print(f"   AI Prob: {result.get('ai_probability', 0):.1f}%")

            momentum_metrics = result.get('momentum_metrics', {})
            if momentum_metrics:
                print(f"   RSI: {momentum_metrics.get('rsi', 0):.1f}")
                print(f"   MA50: {momentum_metrics.get('price_above_ma50', 0):+.1f}%")
                print(f"   Mom30d: {momentum_metrics.get('momentum_30d', 0):+.1f}%")
        else:
            failed.append(symbol)
            if result:
                print(f"❌ {symbol} REJECTED")
                rejection = result.get('rejection_reason', 'Unknown')
                print(f"   Reason: {rejection}")

                momentum_metrics = result.get('momentum_metrics', {})
                if momentum_metrics:
                    print(f"   RSI: {momentum_metrics.get('rsi', 0):.1f}")
                    print(f"   MA50: {momentum_metrics.get('price_above_ma50', 0):+.1f}%")
                    print(f"   Mom30d: {momentum_metrics.get('momentum_30d', 0):+.1f}%")
            else:
                print(f"❌ {symbol} ERROR - No result")

    # Summary
    print(f"\n{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Passed: {len(passed)} stocks")
    if passed:
        print("   " + ", ".join([s['symbol'] for s in passed]))

    print(f"❌ Failed: {len(failed)} stocks")
    if failed:
        print("   " + ", ".join(failed))

    # Market analysis
    print(f"\n{'='*80}")
    print(f"💡 ANALYSIS")
    print(f"{'='*80}")

    if len(passed) == 0:
        print("❌ NO STOCKS PASSED!")
        print("\nThis means:")
        print("1. ⚠️ Market conditions are POOR right now")
        print("2. 🔒 Momentum gates are working (rejecting weak stocks)")
        print("3. ⏳ Wait for better market conditions")
        print("\nv4.0 Momentum Gates:")
        print("   • RSI: 35-70 (not oversold/overbought)")
        print("   • MA50: >-5% (not in downtrend)")
        print("   • Mom30d: >5% (has positive momentum)")
        print("\nIf ALL stocks fail these gates → Market is weak!")
    elif len(passed) < len(test_stocks) / 2:
        print("⚠️ FEW STOCKS PASSED")
        print(f"\nPassed: {len(passed)}/{len(test_stocks)} ({len(passed)*100//len(test_stocks)}%)")
        print("Market is mixed - be selective!")
    else:
        print("✅ GOOD MARKET CONDITIONS")
        print(f"\nPassed: {len(passed)}/{len(test_stocks)} ({len(passed)*100//len(test_stocks)}%)")
        print("Multiple opportunities available!")

    # What to do
    print(f"\n{'='*80}")
    print(f"🎯 WHAT TO DO")
    print(f"{'='*80}")

    if len(passed) > 0:
        print(f"✅ Trade the {len(passed)} stocks that passed!")
        print("\nTop stock(s):")
        sorted_passed = sorted(passed, key=lambda x: x.get('entry_score', 0), reverse=True)
        for i, stock in enumerate(sorted_passed[:3], 1):
            print(f"{i}. {stock['symbol']} - Entry Score: {stock.get('entry_score', 0):.1f}")
    else:
        print("⏳ WAIT for better market conditions")
        print("\nWhen to check again:")
        print("• When SPY breaks above MA20")
        print("• When market sentiment improves")
        print("• Check again in 2-3 days")
        print("\n📊 Alternative: Check sector-specific opportunities")
        print("   Some sectors may be strong even if overall market is weak")

    return passed, failed

if __name__ == "__main__":
    test_specific_stocks()
