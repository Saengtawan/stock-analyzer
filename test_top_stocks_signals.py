#!/usr/bin/env python3
"""
Test top stocks from screener to see what signals they have
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from data_sources.aggregator import AlternativeDataAggregator

def main():
    print("\n" + "="*80)
    print("🔍 TOP STOCKS SIGNAL ANALYSIS")
    print("="*80)

    aggregator = AlternativeDataAggregator()

    # Test stocks from screener results
    test_stocks = [
        ('IRTC', '1/6'),
        ('DOCS', '0/6'),
        ('GDOT', '0/6'),
        ('HEI', '1/6'),
        ('SOFI', '0/6'),
        ('SNOW', '1/6')
    ]

    for symbol, expected_signals in test_stocks:
        print(f"\n{symbol} (Expected: {expected_signals}):")
        print("-" * 80)

        data = aggregator.get_comprehensive_data(symbol)
        if data:
            actual_signals = data['positive_signals']
            print(f"  ✓ Signals: {actual_signals}/6")
            print(f"  ✓ Overall Score: {data['overall_score']:.1f}/100")

            # Show which signals are active
            print(f"\n  Signal Breakdown:")
            print(f"    👔 Insider Buying:    {'✅' if data['has_insider_buying'] else '❌'}")
            print(f"    📊 Analyst Upgrade:   {'✅' if data['has_analyst_upgrade'] else '❌'}")
            print(f"    🔥 Squeeze Potential: {'✅' if data['has_squeeze_potential'] else '❌'}")
            print(f"    🔥 Social Buzz:       {'✅' if data['has_social_buzz'] else '❌'}")
            print(f"    📈 Sector Momentum:   {'✅' if data['has_sector_momentum'] else '❌'}")
            print(f"    🎯 Follows Leader:    {'✅' if data['follows_strong_leader'] else '❌'}")

            # Show component scores
            print(f"\n  Component Scores:")
            for key, score in data['component_scores'].items():
                print(f"    {key.capitalize():<15} {score:>6.1f}/100")
        else:
            print("  ❌ No data")

    print("\n" + "="*80)
    print("✅ Analysis complete!")
    print("="*80)

if __name__ == "__main__":
    main()
