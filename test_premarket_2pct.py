#!/usr/bin/env python3
"""
Test Pre-market Scanner with 2% Gap threshold
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
from screeners.premarket_scanner import PremarketScanner
from datetime import datetime
import pytz

def test_premarket_2pct():
    """Test with 2% gap threshold"""

    print("=" * 80)
    print("PRE-MARKET SCANNER TEST - 2% Gap Threshold")
    print("=" * 80)

    # Check current time
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    print(f"\nCurrent Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # Initialize
    client = YahooFinanceClient()
    scanner = PremarketScanner(client)

    print("\n🔍 Running scan with 2% gap threshold:")
    print("   - Min Gap: 2%")
    print("   - Min Volume Ratio: 2x")
    print("   - Market Caps: Large + Mid")
    print("   - Tech Priority: Yes")
    print("   - Max Stocks: 15")

    opportunities = scanner.scan_premarket_opportunities(
        min_gap_pct=2.0,  # 2% threshold
        min_volume_ratio=2.0,
        market_caps=['large', 'mid'],
        prioritize_tech=True,
        max_stocks=15
    )

    print(f"\n{'='*80}")
    print(f"✅ RESULTS: Found {len(opportunities)} opportunities")
    print(f"{'='*80}\n")

    if opportunities:
        print("Top Opportunities:")
        print("-" * 80)
        print(f"{'Rank':<5} {'Symbol':<8} {'Gap %':<8} {'Vol Ratio':<11} {'Score':<7} {'Rec':<12} {'Warning'}")
        print("-" * 80)

        for i, opp in enumerate(opportunities, 1):
            warning = "⚠️ BELOW THRESHOLD" if opp.get('below_threshold_warning') else ""
            vol_ratio_str = f"{opp['volume_ratio']:.1f}x" if opp['volume_ratio'] > 0 else "N/A"

            print(f"{i:<5} {opp['symbol']:<8} {opp['gap_percent']:>6.2f}% {vol_ratio_str:<11} "
                  f"{opp['gap_score']:>5.1f}/10 {opp['recommendation']:<12} {warning}")

        print("-" * 80)

        # Show detailed info for top 3
        print("\n📊 Detailed Info for Top 3:")
        for i, opp in enumerate(opportunities[:3], 1):
            print(f"\n{i}. {opp['symbol']} - {opp['market_cap_category']} ({opp['sector']})")
            print(f"   Previous Close: ${opp['previous_close']:.2f}")
            print(f"   PM Price: ${opp['current_price']:.2f}")
            print(f"   Gap: {opp['gap_percent']:.2f}% ({opp['gap_direction']})")
            print(f"   PM Range: ${opp['premarket_low']:.2f} - ${opp['premarket_high']:.2f}")
            print(f"   Score: {opp['gap_score']:.1f}/10")
            print(f"   Recommendation: {opp['recommendation']}")

            risk = opp.get('risk_indicators', {})
            if risk:
                high_risks = [k for k, v in risk.items() if v in ['High', 'Extreme']]
                if high_risks:
                    print(f"   ⚠️  Risk Factors: {', '.join(high_risks)}")
    else:
        print("❌ No gap-up opportunities found")
        print("\nPossible reasons:")
        print("1. Market is not volatile today")
        print("2. No stocks are gapping up")
        print("3. All gap-up stocks are below 2% threshold")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    test_premarket_2pct()
