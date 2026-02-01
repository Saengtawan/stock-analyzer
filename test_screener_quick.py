#!/usr/bin/env python3
"""
Quick test of screener v3.0 with specific stocks
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from ai_stock_analyzer import AIStockAnalyzer
from screeners.growth_catalyst_screener import GrowthCatalystScreener

def test_single_stock(screener, symbol):
    """Test a single stock to see if alternative data is included"""
    print(f"\n{'='*80}")
    print(f"Testing {symbol}")
    print('='*80)

    try:
        result = screener._analyze_stock_comprehensive(
            symbol=symbol,
            target_gain_pct=5.0,
            timeframe_days=30
        )

        if result:
            print(f"\n✅ Analysis successful!")
            print(f"   Composite Score: {result['composite_score']:.1f}/100")
            print(f"   Risk Adjusted:   {result['risk_adjusted_score']:.1f}/100")

            print(f"\n📊 Component Scores:")
            print(f"   Alt Data:    {result.get('alt_data_score', 0):.1f}/100")
            print(f"   Technical:   {result.get('technical_score', 0):.1f}/100")
            print(f"   Sector:      {result.get('sector_score', 0):.1f}/100")
            print(f"   Valuation:   {result.get('valuation_score', 0):.1f}/100")

            print(f"\n✅ Alternative Data Signals ({result.get('alt_data_signals', 0)}/6):")
            print(f"   Insider buying:    {result.get('has_insider_buying', False)}")
            print(f"   Analyst upgrade:   {result.get('has_analyst_upgrade', False)}")
            print(f"   Squeeze potential: {result.get('has_squeeze_potential', False)}")
            print(f"   Social buzz:       {result.get('has_social_buzz', False)}")

            if result.get('alt_data_analysis'):
                alt = result['alt_data_analysis']
                print(f"\n📈 Alt Data Breakdown:")
                if alt.get('component_scores'):
                    for key, score in alt['component_scores'].items():
                        print(f"   {key.capitalize():<15} {score:>5.1f}/100")

            return True
        else:
            print(f"\n❌ Analysis failed - stock didn't meet criteria")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "="*80)
    print("🔧 QUICK TEST: Screener v3.0 Alternative Data")
    print("="*80)

    analyzer = AIStockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Test with top stock from previous results
    test_stocks = ['DOCN', 'AAPL']

    success_count = 0
    for symbol in test_stocks:
        if test_single_stock(screener, symbol):
            success_count += 1

    print("\n" + "="*80)
    print(f"✅ Test Complete: {success_count}/{len(test_stocks)} stocks analyzed successfully")
    print("="*80)

if __name__ == "__main__":
    main()
