#!/usr/bin/env python3
"""
Debug full screening pipeline to identify where stocks are filtered out
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from main import StockAnalyzer
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

def debug_single_stock(screener, symbol):
    """Debug full analysis pipeline for a single stock"""
    print(f"\n{'='*70}")
    print(f"DEBUGGING: {symbol}")
    print(f"{'='*70}")

    try:
        # Analyze with same parameters as default screening
        result = screener._analyze_stock_comprehensive(
            symbol=symbol,
            target_gain_pct=10.0,
            timeframe_days=30
        )

        if result is None:
            print(f"❌ Stock filtered out during analysis")

            # Try to understand why by running partial analysis
            try:
                fast_results = screener.analyzer.analyze_stock_fast(symbol, time_horizon='short')
                if 'error' in fast_results:
                    print(f"   Reason: Fast analysis failed - {fast_results.get('error')}")
                    return

                current_price = fast_results.get('current_price', 0)
                if current_price == 0:
                    print(f"   Reason: No current price available")
                    return

                print(f"   Current Price: ${current_price:.2f}")

                # Get price data
                price_data = screener.analyzer.data_manager.get_price_data(symbol, period='1mo')
                if price_data is None or price_data.empty:
                    print(f"   Reason: No price data available")
                    return

                print(f"   Price data: ✅ Available")

            except Exception as e:
                print(f"   Reason: Analysis error - {e}")

            return

        # Stock passed all filters - show the scores
        print(f"✅ Stock PASSED all filters!\n")
        print(f"📊 Scores:")
        print(f"   Composite Score:    {result['composite_score']:.1f}/100")
        print(f"   Catalyst Score:     {result['catalyst_score']:.1f}/100 (min: 30.0)")
        print(f"   Technical Score:    {result['technical_score']:.1f}/100 (min: 50.0)")
        print(f"   AI Probability:     {result['ai_probability']:.1f}% (min: 50.0%)")
        print(f"   AI Confidence:      {result['ai_confidence']:.1f}%")

        # Show which filters it passed
        print(f"\n✓ Filter Results:")
        print(f"   Catalyst >= 30:     {'PASS' if result['catalyst_score'] >= 30 else 'FAIL'}")
        print(f"   Technical >= 50:    {'PASS' if result['technical_score'] >= 50 else 'FAIL'}")
        print(f"   AI Prob >= 50:      {'PASS' if result['ai_probability'] >= 50 else 'FAIL'}")

        # Show top catalysts
        if result.get('catalysts'):
            print(f"\n🎯 Top Catalysts:")
            for i, cat in enumerate(result['catalysts'][:3], 1):
                print(f"   {i}. {cat['description']} ({cat['score']} pts)")

        return result

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("="*70)
    print("GROWTH CATALYST SCREENER - FULL PIPELINE DEBUG")
    print("="*70)
    print("\nTesting with default parameters:")
    print("  - Min Catalyst Score: 30")
    print("  - Min Technical Score: 50")
    print("  - Min AI Probability: 50%")
    print("="*70)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Test stocks that showed good catalyst scores
    test_stocks = [
        'META',   # Had 40/100 catalyst score
        'AAPL',   # Had 35/100 catalyst score
        'NVDA',   # Had 30/100 catalyst score
        'MSFT',   # Should have good scores
        'GOOGL',  # Should have good scores
    ]

    passed = []
    failed = []

    for symbol in test_stocks:
        result = debug_single_stock(screener, symbol)
        if result:
            passed.append(symbol)
        else:
            failed.append(symbol)

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Passed all filters: {len(passed)} stocks")
    if passed:
        print(f"  {', '.join(passed)}")

    print(f"\nFiltered out: {len(failed)} stocks")
    if failed:
        print(f"  {', '.join(failed)}")

    if len(passed) == 0:
        print(f"\n⚠️  NO STOCKS PASSED - Main bottleneck likely:")
        print(f"   1. Technical Score < 50")
        print(f"   2. AI Probability < 50%")
        print(f"\n💡 Recommendation:")
        print(f"   Lower the min_technical_score to 40")
        print(f"   Lower the min_ai_probability to 40")

if __name__ == "__main__":
    main()
