#!/usr/bin/env python3
"""
Test that signals flow correctly from individual trackers to aggregator
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from data_sources.analyst_ratings import AnalystRatingsTracker
from data_sources.aggregator import AlternativeDataAggregator

def main():
    print("\n" + "="*80)
    print("🔍 SIGNAL FLOW TEST")
    print("Testing that analyst upgrades flow from tracker → aggregator")
    print("="*80)

    analyst_tracker = AnalystRatingsTracker()
    aggregator = AlternativeDataAggregator()

    # Test with AAPL and TSLA (we know they have upgrades)
    test_symbols = ['AAPL', 'TSLA']

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        print("-" * 40)

        # Test analyst tracker directly
        analyst_data = analyst_tracker.get_analyst_data(symbol)
        if analyst_data:
            print(f"  ✓ Analyst Tracker:")
            print(f"    has_recent_upgrade: {analyst_data['has_recent_upgrade']}")
            print(f"    upgrade_score: {analyst_data['upgrade_score']:+.1f}")

        # Test aggregator
        agg_data = aggregator.get_comprehensive_data(symbol)
        if agg_data:
            print(f"  ✓ Aggregator:")
            print(f"    has_analyst_upgrade: {agg_data['has_analyst_upgrade']}")
            print(f"    positive_signals: {agg_data['positive_signals']}/6")
            print(f"    overall_score: {agg_data['overall_score']:.1f}/100")

            # Check match
            if analyst_data and analyst_data['has_recent_upgrade'] == agg_data['has_analyst_upgrade']:
                print(f"  ✅ MATCH - Signal flowing correctly!")
            else:
                print(f"  ❌ MISMATCH - Signal not flowing!")

    print("\n" + "="*80)
    print("✅ Test complete!")
    print("="*80)

if __name__ == "__main__":
    main()
