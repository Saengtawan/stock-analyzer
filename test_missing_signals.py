#!/usr/bin/env python3
"""
Investigate why Short Interest, Social Buzz, and Correlation/Macro signals aren't working
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from data_sources.short_interest import ShortInterestTracker
from data_sources.social_sentiment import SocialSentimentTracker
from data_sources.correlation_pairs import CorrelationTracker
from data_sources.macro_indicators import MacroIndicatorsTracker
import yfinance as yf

def investigate_short_interest():
    """Check what short interest data we're getting"""
    print("\n" + "="*80)
    print("📊 INVESTIGATING SHORT INTEREST")
    print("="*80)

    tracker = ShortInterestTracker()
    test_symbols = ['IRTC', 'DOCS', 'GDOT', 'HEI', 'SOFI', 'SNOW']

    print(f"\n{'Symbol':<8} {'Short %':<10} {'Days2Cover':<12} {'Squeeze':<10} {'Heavily?':<10}")
    print("-" * 80)

    for symbol in test_symbols:
        data = tracker.get_short_interest(symbol)
        if data:
            print(f"{symbol:<8} {data['short_percent_float']:>7.2f}%  "
                  f"{data['short_ratio']:>10.2f}  "
                  f"{data['squeeze_score']:>8.1f}/100  "
                  f"{'✅' if data['is_heavily_shorted'] else '❌':<10}")

            # Also check raw yfinance data
            ticker = yf.Ticker(symbol)
            info = ticker.info
            short_pct = info.get('shortPercentOfFloat', 0) * 100
            print(f"  └─ Raw yfinance: {short_pct:.2f}%")

    print("\n💡 Analysis:")
    print("  Current threshold: >10% of float is considered 'heavily shorted'")
    print("  Industry average: 5-10% is normal, >15% is high")


def investigate_social_buzz():
    """Check what social sentiment data we're getting"""
    print("\n" + "="*80)
    print("🔥 INVESTIGATING SOCIAL BUZZ (Reddit)")
    print("="*80)

    tracker = SocialSentimentTracker()
    test_symbols = ['IRTC', 'DOCS', 'GDOT', 'HEI', 'SOFI', 'SNOW']

    # Also test some popular stocks that should have mentions
    popular_symbols = ['AAPL', 'TSLA', 'NVDA', 'GME', 'AMC']

    print("\n1. Testing screener stocks:")
    print(f"{'Symbol':<8} {'Mentions':<10} {'Score':<10} {'Trending?':<10}")
    print("-" * 60)

    for symbol in test_symbols:
        data = tracker.get_reddit_sentiment(symbol)
        if data:
            print(f"{symbol:<8} {data['mentions_24h']:>8}  "
                  f"{data['social_score']:>8.1f}/100  "
                  f"{'✅' if data['trending'] else '❌':<10}")
        else:
            print(f"{symbol:<8} {'N/A':>8}  {'N/A':>8}  ❌")

    print("\n2. Testing popular stocks (should have data):")
    print(f"{'Symbol':<8} {'Mentions':<10} {'Score':<10} {'Trending?':<10}")
    print("-" * 60)

    for symbol in popular_symbols:
        data = tracker.get_reddit_sentiment(symbol)
        if data:
            print(f"{symbol:<8} {data['mentions_24h']:>8}  "
                  f"{data['social_score']:>8.1f}/100  "
                  f"{'✅' if data['trending'] else '❌':<10}")
        else:
            print(f"{symbol:<8} {'N/A':>8}  {'N/A':>8}  ❌")

    print("\n💡 Analysis:")
    print("  Reddit API requires authentication (PRAW)")
    print("  Current implementation may not be working without API credentials")


def investigate_correlation():
    """Check what correlation data we're getting"""
    print("\n" + "="*80)
    print("🎯 INVESTIGATING CORRELATION & SECTOR MOMENTUM")
    print("="*80)

    tracker = CorrelationTracker()
    test_symbols = ['IRTC', 'HEI', 'SNOW']  # Just test a few

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        print("-" * 40)
        data = tracker.get_correlation_data(symbol)
        if data:
            print(f"  Correlation Score: {data['correlation_score']:.1f}/100")
            print(f"  Sector: {data['sector']}")
            print(f"  Group Leader: {data['group_leader']}")
            print(f"  Correlation to Leader: {data['correlation_to_leader']:.3f}")
            print(f"  Leader Performance: {data['leader_performance']:+.2f}%")
            print(f"  Follows Strong Leader: {'✅' if data['correlation_score'] > 60 else '❌'}")
        else:
            print("  ❌ No data")


def investigate_macro():
    """Check what macro indicators we're getting"""
    print("\n" + "="*80)
    print("📈 INVESTIGATING MACRO INDICATORS")
    print("="*80)

    tracker = MacroIndicatorsTracker()
    test_symbols = ['IRTC', 'HEI', 'SNOW']

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        print("-" * 40)
        data = tracker.get_macro_data(symbol)
        if data:
            print(f"  Sector: {data['sector']}")
            print(f"  Macro Score: {data['macro_score']:.1f}/100")
            print(f"  Sector Rotation: {data['sector_rotation_signal']}")
            print(f"  Sector Performance: {data['sector_performance']:+.2f}%")
            print(f"  Has Sector Momentum: {'✅' if data['sector_rotation_signal'] == 'into' else '❌'}")
        else:
            print("  ❌ No data")


def main():
    print("\n" + "="*80)
    print("🔍 DIAGNOSTIC: Missing Signals Analysis")
    print("="*80)

    investigate_short_interest()
    investigate_social_buzz()
    investigate_correlation()
    investigate_macro()

    print("\n" + "="*80)
    print("✅ Diagnostic complete!")
    print("="*80)

if __name__ == "__main__":
    main()
