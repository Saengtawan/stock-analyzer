#!/usr/bin/env python3
"""
Test Trade Confidence Scores
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
from screeners.premarket_scanner import PremarketScanner

def test_confidence_scores():
    print("=" * 100)
    print("🎯 TRADE CONFIDENCE SCORE TEST")
    print("=" * 100)

    client = YahooFinanceClient()
    scanner = PremarketScanner(client)

    print("\n🔍 Scanning with 2% gap threshold...")

    opportunities = scanner.scan_premarket_opportunities(
        min_gap_pct=2.0,
        min_volume_ratio=2.0,
        market_caps=['large', 'mid'],
        prioritize_tech=True,
        max_stocks=20
    )

    print(f"\n{'='*100}")
    print(f"✅ Found {len(opportunities)} opportunities (sorted by Trade Confidence)")
    print(f"{'='*100}\n")

    if opportunities:
        # Header
        print(f"{'#':<4} {'Symbol':<8} {'Conf':<6} {'Badge':<15} {'Gap %':<8} {'Score':<7} {'Risk':<15} {'Rec':<12}")
        print("-" * 100)

        for i, opp in enumerate(opportunities, 1):
            conf = opp.get('trade_confidence', 0)

            # Determine badge
            if conf >= 75:
                badge = '🟢 STRONG BUY'
            elif conf >= 60:
                badge = '🟡 BUY'
            elif conf >= 45:
                badge = '🟠 WATCH'
            else:
                badge = '🔴 AVOID'

            # Get highest risk
            risks = opp.get('risk_indicators', {})
            high_risks = [k for k, v in risks.items() if v in ['High', 'Extreme']]
            risk_str = high_risks[0] if high_risks else 'Low Risk'

            print(f"{i:<4} {opp['symbol']:<8} {conf:<6}% {badge:<15} "
                  f"{opp['gap_percent']:>6.2f}% {opp['gap_score']:>5.1f}/10 {risk_str:<15} {opp['recommendation']:<12}")

        # Show detailed analysis for top 3
        print("\n" + "="*100)
        print("📊 DETAILED ANALYSIS - Top 3 by Confidence")
        print("="*100)

        for i, opp in enumerate(opportunities[:3], 1):
            conf = opp.get('trade_confidence', 0)

            print(f"\n{i}. {opp['symbol']} - Confidence: {conf}%")
            print(f"   {'-'*80}")
            print(f"   Gap: {opp['gap_percent']:.2f}% | Score: {opp['gap_score']:.1f}/10 | Rec: {opp['recommendation']}")
            print(f"   Price: ${opp['previous_close']:.2f} → ${opp['current_price']:.2f}")
            print(f"   PM Range: ${opp['premarket_low']:.2f} - ${opp['premarket_high']:.2f}")

            # Calculate price position
            if opp['premarket_high'] > opp['premarket_low']:
                price_pos = (opp['current_price'] - opp['premarket_low']) / (opp['premarket_high'] - opp['premarket_low']) * 100
                print(f"   Price Position: {price_pos:.1f}% of PM range (higher = stronger)")

            # Risk factors
            risks = opp.get('risk_indicators', {})
            print(f"   Risk Indicators:")
            for risk_type, risk_level in risks.items():
                if risk_level != 'Low':
                    emoji = '⚠️' if risk_level in ['High', 'Extreme'] else '⚡'
                    print(f"     {emoji} {risk_type.replace('_', ' ').title()}: {risk_level}")

            print(f"   {'-'*80}")
            print(f"   💡 Why {conf}% confidence:")

            # Explain confidence
            if conf >= 75:
                print(f"      ✅ Excellent setup with minimal risk factors")
            elif conf >= 60:
                print(f"      ✅ Good setup, worth considering")
            elif conf >= 45:
                print(f"      ⚠️  Mixed signals, proceed with caution")
            else:
                print(f"      ❌ High risk, likely to fade")

    else:
        print("❌ No opportunities found")

    print("\n" + "="*100)
    print("TEST COMPLETE")
    print("="*100)

if __name__ == '__main__':
    test_confidence_scores()
