#!/usr/bin/env python3
"""
Test Growth Catalyst Screener v3.0 with Alternative Data
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from ai_stock_analyzer import AIStockAnalyzer
from screeners.growth_catalyst_screener import GrowthCatalystScreener

def test_screener_v3():
    print("\n" + "="*80)
    print("🚀 TESTING SCREENER v3.0 - ALTERNATIVE DATA INTEGRATION")
    print("="*80)

    # Initialize
    analyzer = AIStockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    print(f"\nRunning screener v3.0...")
    print(f"Target: 5%+ gain in 30 days")
    print(f"Max stocks: 10\n")

    # Run screener
    results = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=5.0,
        timeframe_days=30,
        max_stocks=10
    )

    # Display results
    print("\n" + "="*80)
    print(f"📊 SCREENING RESULTS")
    print("="*80)

    print(f"\nผลการคัดกรอง: พบหุ้นที่มีศักยภาพ {len(results)} ตัว")

    if len(results) > 0:
        print("\n" + "-"*80)
        print(f"{'#':<4} {'Symbol':<8} {'Price':<10} {'Score':<8} {'Alt Data':<10} {'Signals':<8}")
        print("-"*80)

        for i, stock in enumerate(results, 1):
            print(f"{i:<4} {stock['symbol']:<8} ${stock['current_price']:<9.2f} {stock['risk_adjusted_score']:<8.1f} {stock['alt_data_score']:<10.1f} {stock['alt_data_signals']}/6")

        # Show detailed alt data for top stock
        if results:
            top = results[0]
            print("\n" + "="*80)
            print(f"📌 TOP PICK DETAILED ANALYSIS: {top['symbol']}")
            print("="*80)

            print(f"\n💰 Price: ${top['current_price']:.2f}")
            print(f"📊 Overall Score: {top['risk_adjusted_score']:.1f}/100")

            print(f"\n🎯 COMPONENT SCORES:")
            print(f"   Alternative Data: {top['alt_data_score']:.1f}/100 (weight: 25%)")
            print(f"   Technical:        {top['technical_score']:.1f}/100 (weight: 25%)")
            print(f"   Sector:           {top['sector_score']:.1f}/100 (weight: 20%)")
            print(f"   Valuation:        {top['valuation_score']:.1f}/100 (weight: 15%)")
            print(f"   Catalyst:         {top['catalyst_score']:.1f}/100 (weight: 10%)")
            print(f"   AI Probability:   {top['ai_probability']:.1f}/100 (weight: 5%)")

            print(f"\n✅ ALTERNATIVE DATA SIGNALS ({top['alt_data_signals']}/6):")
            signals = [
                ('Insider buying', top['has_insider_buying']),
                ('Analyst upgrade', top['has_analyst_upgrade']),
                ('Squeeze potential', top['has_squeeze_potential']),
                ('Social buzz', top['has_social_buzz']),
            ]

            for name, value in signals:
                status = "✅" if value else "❌"
                print(f"   {status} {name}")

            if top.get('alt_data_analysis'):
                alt = top['alt_data_analysis']
                if alt.get('component_scores'):
                    print(f"\n📊 ALT DATA BREAKDOWN:")
                    for key, score in alt['component_scores'].items():
                        bar = "█" * int(score / 10)
                        print(f"   {key.capitalize():<15} {score:>5.1f}/100 {bar}")

    else:
        print("\n⚠️ No stocks passed the screening criteria")

    print("\n" + "="*80)
    print("✅ TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    test_screener_v3()
