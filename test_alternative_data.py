#!/usr/bin/env python3
"""
Test all alternative data sources
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

from data_sources.aggregator import AlternativeDataAggregator

def test_alternative_data():
    print("\n" + "="*80)
    print("🎯 TESTING ALL ALTERNATIVE DATA SOURCES")
    print("="*80)

    aggregator = AlternativeDataAggregator()

    # Test with a few stocks
    test_symbols = ['AAPL', 'NVDA']

    for symbol in test_symbols:
        print(f"\n{'='*80}")
        print(f"📊 {symbol}")
        print('='*80)

        data = aggregator.get_comprehensive_data(symbol)

        if data:
            print(f"\n🎯 OVERALL ASSESSMENT:")
            print(f"   Score: {data['overall_score']:.1f}/100")
            print(f"   Confidence: {data['confidence']:.1f}/100")
            print(f"   Signal: {data['signal_strength']}")
            print(f"   Recommendation: {data['recommendation']}")

            print(f"\n✅ POSITIVE SIGNALS ({data['positive_signals']}/6):")
            signals = [
                ('Insider buying', data['has_insider_buying']),
                ('Analyst upgrade', data['has_analyst_upgrade']),
                ('Squeeze potential', data['has_squeeze_potential']),
                ('Social buzz', data['has_social_buzz']),
                ('Sector momentum', data['has_sector_momentum']),
                ('Follows leader', data['follows_strong_leader'])
            ]

            for name, value in signals:
                status = "✅" if value else "❌"
                print(f"   {status} {name}")

            print(f"\n📊 COMPONENT SCORES:")
            for key, score in data['component_scores'].items():
                bar = "█" * int(score / 10)
                print(f"   {key.capitalize():<15} {score:>5.1f}/100 {bar}")

            # Show detailed data
            if data['insider']:
                print(f"\n📌 Insider Trading:")
                print(f"   Recent filings: {data['insider']['insider_buys_30d']}")
                print(f"   Sentiment: {data['insider']['insider_sentiment']}")

            if data['analyst']:
                print(f"\n📌 Analyst Ratings:")
                print(f"   Recommendation: {data['analyst']['recommendation']}")
                print(f"   Upside to target: {data['analyst']['upside_potential']:+.1f}%")
                print(f"   Recent upgrades/downgrades: {data['analyst']['recent_upgrades']}/{data['analyst']['recent_downgrades']}")

            if data['short_interest']:
                print(f"\n📌 Short Interest:")
                print(f"   Short % float: {data['short_interest']['short_percent_float']:.2f}%")
                print(f"   Days to cover: {data['short_interest']['short_ratio']:.2f}")
                print(f"   Squeeze risk: {data['short_interest']['squeeze_risk']}")

            if data['social']:
                print(f"\n📌 Social Sentiment:")
                print(f"   Mentions (24h): {data['social']['mentions_24h']}")
                print(f"   Sentiment: {data['social']['sentiment']} ({data['social']['sentiment_score']:+.1f})")

            if data['correlation']:
                print(f"\n📌 Correlation:")
                print(f"   Sector leader: {data['correlation']['sector_leader']}")
                if data['correlation']['correlated_stocks']:
                    top = data['correlation']['correlated_stocks'][0]
                    print(f"   Top correlation: {top[0]} ({top[1]:.2f})")

            if data['macro']:
                print(f"\n📌 Macro Environment:")
                print(f"   Sector: {data['macro']['sector']}")
                print(f"   Market regime: {data['macro']['market_regime']}")
                print(f"   Sector rank: #{data['macro']['sector_rank']}")
                print(f"   Rotation: {data['macro']['sector_rotation_signal']}")

        else:
            print("  ❌ No data available")

    print("\n" + "="*80)
    print("✅ TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    test_alternative_data()
