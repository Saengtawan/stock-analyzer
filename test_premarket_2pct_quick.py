#!/usr/bin/env python3
"""
Quick test with 2% gap threshold to see all opportunities
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
from screeners.premarket_scanner import PremarketScanner

def main():
    """Test with 2% gap threshold"""

    print("=" * 80)
    print("PRE-MARKET SCANNER: 2% GAP THRESHOLD TEST")
    print("=" * 80)

    client = YahooFinanceClient()
    scanner = PremarketScanner(client)

    print("\nRunning scan with 2% gap threshold:")
    print("   - Min Gap: 2%")
    print("   - Min Volume Ratio: DISABLED (demo mode)")
    print("   - Market Caps: All")
    print("   - Max Stocks: 30")

    scan_result = scanner.scan_premarket_opportunities(
        min_gap_pct=2.0,  # Lower to 2%
        min_volume_ratio=2.0,
        market_caps=['large', 'mid', 'small'],
        prioritize_tech=True,
        max_stocks=30,
        demo_mode=True  # Force demo mode
    )

    opportunities = scan_result['opportunities']
    demo_mode = scan_result['demo_mode']

    print(f"\n✅ Scan completed!")
    print(f"Found {len(opportunities)} opportunities with gap ≥2%")
    print(f"Demo Mode: {demo_mode}")

    if opportunities:
        print("\n" + "=" * 80)
        print("TOP OPPORTUNITIES (sorted by Trade Confidence)")
        print("=" * 80)
        print(f"{'#':<3} {'Symbol':<8} {'Gap%':<8} {'Prev':<10} {'PM Price':<10} {'Score':<7} {'Conf':<6} {'Rec':<12}")
        print("-" * 80)

        for i, opp in enumerate(opportunities, 1):
            print(f"{i:<3} {opp['symbol']:<8} "
                  f"{opp['gap_percent']:>6.2f}%  "
                  f"${opp['previous_close']:>8.2f}  "
                  f"${opp['current_price']:>8.2f}  "
                  f"{opp['gap_score']:>5.1f}/10  "
                  f"{opp.get('trade_confidence', 0):>4}/100  "
                  f"{opp['recommendation']:<12}")

    else:
        print("\n⚠️  No opportunities found even with 2% threshold")

    print("\n" + "=" * 80)

if __name__ == '__main__':
    main()
