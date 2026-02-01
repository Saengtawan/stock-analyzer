#!/usr/bin/env python3
"""
Test Alternative Data with Lowered Thresholds (30 days)
Verify that insider trading and analyst ratings are working with new thresholds
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from data_sources.insider_trading import InsiderTradingTracker
from data_sources.analyst_ratings import AnalystRatingsTracker
from data_sources.aggregator import AlternativeDataAggregator
import logging

logging.basicConfig(level=logging.INFO)

def test_individual_sources():
    """Test insider trading and analyst ratings separately"""
    print("\n" + "="*80)
    print("🔍 TESTING INDIVIDUAL DATA SOURCES (30-DAY THRESHOLDS)")
    print("="*80)

    insider_tracker = InsiderTradingTracker()
    analyst_tracker = AnalystRatingsTracker()

    # Test with popular stocks that likely have data
    test_symbols = ['AAPL', 'TSLA', 'NVDA', 'AMD', 'META']

    for symbol in test_symbols:
        print(f"\n{'='*80}")
        print(f"Testing {symbol}")
        print('='*80)

        # Test Insider Trading
        print(f"\n📊 Insider Trading (30-day lookback):")
        insider_data = insider_tracker.get_insider_activity(symbol)
        if insider_data:
            print(f"  Buys (30d): {insider_data['insider_buys_30d']}")
            print(f"  Sentiment: {insider_data['insider_sentiment']}")
            print(f"  Score: {insider_data['insider_score']:.1f}/100")
            print(f"  Has Recent Buying: {insider_data['has_recent_buying']}")
        else:
            print("  ❌ No data")

        # Test Analyst Ratings
        print(f"\n📈 Analyst Ratings (30-day lookback):")
        analyst_data = analyst_tracker.get_analyst_data(symbol)
        if analyst_data:
            print(f"  Recommendation: {analyst_data['recommendation']} ({analyst_data['recommendation_score']:.2f})")
            print(f"  Target Upside: {analyst_data['upside_potential']:+.1f}%")
            print(f"  Upgrades/Downgrades (30d): {analyst_data['recent_upgrades']}/{analyst_data['recent_downgrades']}")
            print(f"  Score: {analyst_data['upgrade_score']:+.1f}/100")
            print(f"  Has Recent Upgrade: {analyst_data['has_recent_upgrade']}")
        else:
            print("  ❌ No data")


def test_aggregator():
    """Test full aggregator to see signal counts"""
    print("\n" + "="*80)
    print("🎯 TESTING AGGREGATOR (SIGNAL COUNTS)")
    print("="*80)

    aggregator = AlternativeDataAggregator()

    test_symbols = ['AAPL', 'TSLA', 'NVDA', 'AMD', 'META']

    results = []
    for symbol in test_symbols:
        data = aggregator.get_comprehensive_data(symbol)
        if data:
            results.append({
                'symbol': symbol,
                'score': data['overall_score'],
                'signals': data['positive_signals'],
                'insider': data['has_insider_buying'],
                'analyst': data['has_analyst_upgrade'],
                'squeeze': data['has_squeeze_potential'],
                'social': data['has_social_buzz']
            })

    # Display results
    print(f"\n{'Symbol':<8} {'Score':<8} {'Signals':<10} {'Insider':<10} {'Analyst':<10} {'Squeeze':<10} {'Social':<10}")
    print("-" * 80)
    for r in results:
        print(f"{r['symbol']:<8} {r['score']:>6.1f}  {r['signals']:>8}/6  "
              f"{'✅' if r['insider'] else '❌':<10} "
              f"{'✅' if r['analyst'] else '❌':<10} "
              f"{'✅' if r['squeeze'] else '❌':<10} "
              f"{'✅' if r['social'] else '❌':<10}")

    print(f"\n📊 Summary:")
    avg_signals = sum(r['signals'] for r in results) / len(results) if results else 0
    print(f"  Average Signals: {avg_signals:.1f}/6")
    print(f"  Stocks with ≥1 signal: {sum(1 for r in results if r['signals'] > 0)}/{len(results)}")
    print(f"  Stocks with ≥2 signals: {sum(1 for r in results if r['signals'] >= 2)}/{len(results)}")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("🧪 ALTERNATIVE DATA THRESHOLD TEST")
    print("Testing 30-day thresholds (lowered from 7 days)")
    print("="*80)

    # Test individual sources first
    test_individual_sources()

    # Test full aggregator
    test_aggregator()

    print("\n" + "="*80)
    print("✅ Test Complete!")
    print("="*80)
