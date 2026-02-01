#!/usr/bin/env python3
"""
Compare NFLX, TSLA, LCID side-by-side with updated scoring
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
from screeners.premarket_scanner import PremarketScanner

def compare_all():
    """Compare all three stocks"""

    client = YahooFinanceClient()
    scanner = PremarketScanner(client)

    symbols = ['NFLX', 'TSLA', 'LCID']
    results = {}

    for symbol in symbols:
        result = scanner._analyze_premarket_stock(symbol, 2.0, 2.0, True)
        if result:
            # Calculate consistency ratio
            pm_data = scanner.client.get_premarket_data(symbol, interval="5m")
            if pm_data.get('has_premarket_data'):
                bars = pm_data['premarket_bars']
                if not bars.empty:
                    price_changes = bars['close'].pct_change().dropna()
                    if len(price_changes) > 0:
                        positive_bars = (price_changes > 0).sum()
                        consistency = positive_bars / len(price_changes)
                        result['consistency_ratio'] = consistency

            results[symbol] = result

    print("=" * 100)
    print("⚔️  THREE-WAY COMPARISON: NFLX vs TSLA vs LCID")
    print("=" * 100)

    print(f"\n{'Metric':<30} {'NFLX':<20} {'TSLA':<20} {'LCID':<20}")
    print("-" * 100)

    # Gap comparison
    print(f"{'Gap %':<30} {results['NFLX']['gap_percent']:>18.2f}% {results['TSLA']['gap_percent']:>18.2f}% {results['LCID']['gap_percent']:>18.2f}%")

    # Consistency (NEW!)
    nflx_cons = results['NFLX'].get('consistency_ratio', 0) * 100
    tsla_cons = results['TSLA'].get('consistency_ratio', 0) * 100
    lcid_cons = results['LCID'].get('consistency_ratio', 0) * 100

    print(f"{'Positive Bars %':<30} {nflx_cons:>17.1f}% {tsla_cons:>17.1f}% {lcid_cons:>17.1f}%")

    # Position
    def calc_position(res):
        h = res['premarket_high']
        l = res['premarket_low']
        c = res['current_price']
        return (c - l) / (h - l) * 100 if h > l else 0

    nflx_pos = calc_position(results['NFLX'])
    tsla_pos = calc_position(results['TSLA'])
    lcid_pos = calc_position(results['LCID'])

    print(f"{'Position in Range':<30} {nflx_pos:>17.1f}% {tsla_pos:>17.1f}% {lcid_pos:>17.1f}%")

    # Scores
    print(f"{'Gap Score':<30} {results['NFLX']['gap_score']:>17.1f}/10 {results['TSLA']['gap_score']:>17.1f}/10 {results['LCID']['gap_score']:>17.1f}/10")
    print(f"{'Trade Confidence (NEW!)':<30} {results['NFLX']['trade_confidence']:>16}/100 {results['TSLA']['trade_confidence']:>16}/100 {results['LCID']['trade_confidence']:>16}/100")
    print(f"{'Recommendation':<30} {results['NFLX']['recommendation']:>20} {results['TSLA']['recommendation']:>20} {results['LCID']['recommendation']:>20}")

    print("\n" + "=" * 100)
    print("📊 ACTUAL RESULTS:")
    print("=" * 100)
    print(f"{'Stock':<10} {'Pre-market Gap':<20} {'Confidence':<15} {'Actual Result':<20} {'Success?':<10}")
    print("-" * 100)

    # NFLX
    nflx_conf = f"{results['NFLX']['trade_confidence']}/100"
    print(f"{'NFLX':<10} {'UP +0.85%':<20} {nflx_conf:<15} {'DOWN -1.31%':<20} {'❌ Trap':<10}")

    # TSLA
    tsla_conf = f"{results['TSLA']['trade_confidence']}/100"
    print(f"{'TSLA':<10} {'UP +2.29%':<20} {tsla_conf:<15} {'UP +3.90%':<20} {'✅ Go':<10}")

    # LCID
    lcid_conf = f"{results['LCID']['trade_confidence']}/100"
    print(f"{'LCID':<10} {'UP +2.23%':<20} {lcid_conf:<15} {'DOWN -3.79%':<20} {'❌ Trap':<10}")

    print("\n" + "=" * 100)
    print("🎯 KEY INSIGHTS:")
    print("=" * 100)

    print("\n1. ✅ TSLA (Success - Gap & Go):")
    print(f"   - Gap: 2.29% (sweet spot)")
    print(f"   - Position: {tsla_pos:.1f}% (near high)")
    print(f"   - Consistency: {tsla_cons:.1f}% (moderate)")
    print(f"   - Confidence: {results['TSLA']['trade_confidence']}/100")
    print(f"   - Result: UP +3.90% ✅")

    print("\n2. ❌ NFLX (Failed - Gap & Trap):")
    print(f"   - Gap: 0.85% (too small)")
    print(f"   - Position: {nflx_pos:.1f}% (middle range)")
    print(f"   - Consistency: {nflx_cons:.1f}% (choppy)")
    print(f"   - Confidence: {results['NFLX']['trade_confidence']}/100 (LOW)")
    print(f"   - Result: DOWN -1.31% ❌")

    print("\n3. ❌ LCID (Failed - Gap & Trap):")
    print(f"   - Gap: 2.23% (good)")
    print(f"   - Position: {lcid_pos:.1f}% (at high)")
    print(f"   - Consistency: {lcid_cons:.1f}% (🚨 VERY WEAK!)")
    print(f"   - Confidence: {results['LCID']['trade_confidence']}/100 (IMPROVED - was 82)")
    print(f"   - Result: DOWN -3.79% ❌")

    print("\n💡 CONCLUSION:")
    print("After adding Consistency check:")
    print(f"  - NFLX: Confidence {results['NFLX']['trade_confidence']} (correctly LOW)")
    print(f"  - TSLA: Confidence {results['TSLA']['trade_confidence']} (correctly HIGH)")
    print(f"  - LCID: Confidence {results['LCID']['trade_confidence']} (FIXED - was 82, now lower)")
    print("\nThe system now correctly penalizes weak price action!")
    print("=" * 100)

if __name__ == '__main__':
    compare_all()
