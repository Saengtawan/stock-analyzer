#!/usr/bin/env python3
"""
Quick test of lowered thresholds (30 days instead of 7)
Test only insider trading and analyst ratings
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from data_sources.insider_trading import InsiderTradingTracker
from data_sources.analyst_ratings import AnalystRatingsTracker

def main():
    print("\n" + "="*80)
    print("🧪 QUICK THRESHOLD TEST (30-day lookback)")
    print("="*80)

    insider_tracker = InsiderTradingTracker()
    analyst_tracker = AnalystRatingsTracker()

    # Test with just 2 popular stocks
    test_symbols = ['AAPL', 'TSLA']

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        print("-" * 40)

        # Insider Trading
        insider_data = insider_tracker.get_insider_activity(symbol)
        if insider_data:
            print(f"  Insider Buys (30d): {insider_data['insider_buys_30d']}")
            print(f"  Insider Score: {insider_data['insider_score']:.1f}/100")
            print(f"  Has Recent Buying: {'✅' if insider_data['has_recent_buying'] else '❌'}")

        # Analyst Ratings
        analyst_data = analyst_tracker.get_analyst_data(symbol)
        if analyst_data:
            print(f"  Analyst Recommendation: {analyst_data['recommendation']}")
            print(f"  Upgrades/Downgrades (30d): {analyst_data['recent_upgrades']}/{analyst_data['recent_downgrades']}")
            print(f"  Upgrade Score: {analyst_data['upgrade_score']:+.1f}/100")
            print(f"  Has Recent Upgrade: {'✅' if analyst_data['has_recent_upgrade'] else '❌'}")

    print("\n" + "="*80)
    print("✅ Quick test complete!")
    print("="*80)

if __name__ == "__main__":
    main()
