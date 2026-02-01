#!/usr/bin/env python3
"""
Full End-to-End Test of Growth Catalyst Screener v3.1
Verify ≥3 signals filter and sector rotation working in real screening
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from api.data_manager import DataManager
from screeners.growth_catalyst_screener import GrowthCatalystScreener
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

def main():
    print("\n" + "="*80)
    print("🧪 FULL END-TO-END TEST: Growth Catalyst Screener v3.1")
    print("="*80)

    # Initialize components
    print("\n1️⃣ Initializing screener...")
    data_manager = DataManager()
    screener = GrowthCatalystScreener(data_manager)

    # Test with small universe (stocks we know from user's results)
    test_universe = [
        'LRCX',   # 3/6 signals - should PASS
        'MRVL',   # 2/6 signals - should be FILTERED
        'SNOW',   # 2/6 signals - should be FILTERED
        'QCOM',   # 1/6 signals - should be FILTERED
        'ANET',   # 1/6 signals - should be FILTERED
        'HUBS',   # 1/6 signals - should be FILTERED
        'AVGO',   # 3/6 signals from backtest - might PASS
        'NVDA',   # Check if has 3+ signals
    ]

    print(f"\n2️⃣ Testing with {len(test_universe)} stocks...")
    print(f"Universe: {', '.join(test_universe)}")

    # Run screening
    print("\n3️⃣ Running screener with v3.1 filters...")
    print("-" * 80)

    results = screener.screen_growth_catalyst_opportunities(
        custom_universe=test_universe,
        target_gain_pct=5.0,
        timeframe_days=30,
        max_results=10
    )

    # Display results
    print("\n" + "="*80)
    print("📊 SCREENING RESULTS")
    print("="*80)

    if results:
        print(f"\n✅ Found {len(results)} stocks (all with ≥3 signals)")
        print()
        print(f"{'Rank':<6} {'Symbol':<8} {'Signals':<10} {'Score':<8} {'Sector':<20} {'Momentum':<12} {'Boost':<8}")
        print("-" * 90)

        for i, stock in enumerate(results, 1):
            rank_emoji = {1: '🥇', 2: '🥈', 3: '🥉'}.get(i, f'#{i}')

            print(f"{rank_emoji:<6} "
                  f"{stock['symbol']:<8} "
                  f"{stock.get('alt_data_signals', 0)}/6{'':<6} "
                  f"{stock.get('composite_score', 0):>6.1f}  "
                  f"{stock.get('sector', 'Unknown')[:18]:<20} "
                  f"{stock.get('sector_momentum', 0):>+6.1f}%{'':<4} "
                  f"{stock.get('sector_rotation_boost', 1.0):.2f}x")

        # Show details for top stock
        if results:
            print("\n" + "="*80)
            print("🔍 TOP PICK DETAILS")
            print("="*80)
            top = results[0]
            print(f"\nSymbol: {top['symbol']}")
            print(f"Composite Score: {top.get('composite_score', 0):.1f}")
            print(f"Alternative Data Signals: {top.get('alt_data_signals', 0)}/6 ✅")

            alt_data = top.get('alt_data_analysis', {})
            if alt_data:
                print(f"\nSignal Breakdown:")
                if alt_data.get('has_insider_buying'):
                    print(f"  👔 Insider Buying")
                if alt_data.get('has_analyst_upgrade'):
                    print(f"  📊 Analyst Upgrade")
                if alt_data.get('has_squeeze_potential'):
                    print(f"  📉 Short Squeeze Potential")
                if alt_data.get('has_social_buzz'):
                    print(f"  🗣️ Social Media Buzz")

            print(f"\nSector Analysis:")
            print(f"  Sector: {top.get('sector', 'Unknown')}")
            print(f"  Status: {top.get('sector_rotation_status', 'unknown')}")
            print(f"  Momentum: {top.get('sector_momentum', 0):+.1f}%")
            print(f"  Boost Applied: {top.get('sector_rotation_boost', 1.0):.2f}x")

            print(f"\nComponent Scores:")
            print(f"  Technical: {top.get('technical_score', 0):.1f}")
            print(f"  AI Probability: {top.get('ai_probability', 0):.1f}%")
            print(f"  Sector Score: {top.get('sector_score', 0):.1f}")

    else:
        print("\n❌ No stocks found")
        print("This could mean:")
        print("  - No stocks have ≥3 alternative data signals")
        print("  - All stocks filtered by technical/valuation criteria")

    # Verification
    print("\n" + "="*80)
    print("✅ VERIFICATION")
    print("="*80)

    print("\n1️⃣ Signal Filter Working?")
    if results:
        all_have_3plus = all(r.get('alt_data_signals', 0) >= 3 for r in results)
        if all_have_3plus:
            print("   ✅ YES - All stocks have ≥3 signals")
        else:
            print("   ❌ NO - Some stocks have <3 signals (BUG!)")
    else:
        print("   ⚠️  No results to verify")

    print("\n2️⃣ Sector Rotation Working?")
    if results:
        has_boost = any(r.get('sector_rotation_boost', 1.0) != 1.0 for r in results)
        if has_boost:
            print("   ✅ YES - Sector rotation boost/penalty applied")
        else:
            print("   ⚠️  All neutral sectors (no boost/penalty)")
    else:
        print("   ⚠️  No results to verify")

    print("\n3️⃣ Expected Results:")
    print("   - LRCX should appear (3/6 signals)")
    print("   - LRCX should get Semiconductors +7.7% boost (1.2x)")
    print("   - MRVL, SNOW, QCOM, ANET, HUBS should be filtered out (<3 signals)")

    print("\n" + "="*80)
    print("✅ Test Complete!")
    print("="*80)


if __name__ == "__main__":
    main()
