#!/usr/bin/env python3
"""
Quick test of improved catalyst discovery on a few stocks
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from main import StockAnalyzer
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_single_stock(screener, symbol):
    """Test catalyst discovery for a single stock"""
    print(f"\n{'='*60}")
    print(f"Testing: {symbol}")
    print(f"{'='*60}")

    try:
        # Analyze stock using the same method as the screener
        analyzer = screener.analyzer
        results = analyzer.analyze_stock_fast(symbol, time_horizon='short')

        if not results or 'error' in results:
            print(f"❌ Analysis failed for {symbol}")
            return

        current_price = results.get('current_price', 0)
        if current_price == 0:
            print(f"❌ No price for {symbol}")
            return

        fundamental = results.get('fundamental_analysis', {})
        technical = results.get('technical_analysis', {})

        # Get price data separately
        price_data = analyzer.data_manager.get_price_data(symbol, period='1mo')
        if price_data is None or price_data.empty:
            print(f"❌ No price data for {symbol}")
            return

        # Discover catalysts
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info

        catalyst_result = screener._discover_catalysts(
            symbol, fundamental, technical, current_price
        )

        print(f"\n📊 Catalyst Analysis Results:")
        print(f"   Total Catalyst Score: {catalyst_result['catalyst_score']:.1f}/100")
        print(f"   Number of Catalysts: {len(catalyst_result['catalysts'])}")

        if catalyst_result['catalysts']:
            print(f"\n   Detected Catalysts:")
            for cat in catalyst_result['catalysts']:
                print(f"      • [{cat['type']}] {cat['description']}")
                print(f"        Impact: {cat['impact']}, Score: {cat['score']} pts")

        # Show what each catalyst type contributed
        catalyst_breakdown = {}
        for cat in catalyst_result['catalysts']:
            cat_type = cat['type']
            if cat_type not in catalyst_breakdown:
                catalyst_breakdown[cat_type] = 0
            catalyst_breakdown[cat_type] += cat['score']

        if catalyst_breakdown:
            print(f"\n   Catalyst Breakdown by Type:")
            for cat_type, score in sorted(catalyst_breakdown.items(), key=lambda x: x[1], reverse=True):
                print(f"      {cat_type}: {score} pts")

        print(f"\n✅ Analysis complete for {symbol}")

    except Exception as e:
        print(f"❌ Error analyzing {symbol}: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("="*60)
    print("QUICK CATALYST DISCOVERY TEST")
    print("Testing improved catalyst detection on sample stocks")
    print("="*60)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Test on a few diverse stocks
    test_stocks = ['TSLA', 'NVDA', 'AAPL', 'META']

    for symbol in test_stocks:
        test_single_stock(screener, symbol)

    print(f"\n{'='*60}")
    print("TEST COMPLETE")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
