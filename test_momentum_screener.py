#!/usr/bin/env python3
"""
Test Momentum Growth Screener v1.0
==================================
"""

import sys
sys.path.insert(0, 'src')

from screeners.momentum_growth_screener import MomentumGrowthScreener
from main import StockAnalyzer
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")

print("=" * 80)
print("🧪 Testing Momentum Growth Screener v1.0")
print("=" * 80)
print("\nBased on actual performance analysis:")
print("  ✅ Winners had RSI ~48 (vs Losers 27)")
print("  ✅ Winners +12% above MA50 (vs Losers -5%)")
print("  ✅ Winners +8% momentum 10d (vs Losers -3%)")
print("  ✅ Winners +22% momentum 30d (vs Losers +5%)")

print("\n" + "=" * 80)
print("🔍 SCREENING WITH PROVEN FILTERS")
print("=" * 80)
print("\nFilters:")
print("  ✓ RSI 40-70 (healthy momentum)")
print("  ✓ Price > MA20 (uptrend)")
print("  ✓ Price > MA50 (strong uptrend)")
print("  ✓ Momentum 10d > 0% (rising)")
print("  ✓ Momentum 30d > 10% (strong 30-day trend)")
print("  ✓ Market Cap > $1B")

analyzer = StockAnalyzer()
screener = MomentumGrowthScreener(analyzer)

print("\n🔍 Screening...")
results = screener.screen_opportunities(
    min_rsi=40.0,
    max_rsi=70.0,
    min_price_above_ma20=0.0,    # Must be above MA20
    min_price_above_ma50=0.0,    # Must be above MA50
    min_momentum_10d=0.0,         # Must have positive 10d momentum
    min_momentum_30d=10.0,        # Must have strong 30d momentum
    min_market_cap=1_000_000_000,
    min_price=5.0,
    max_price=500.0,
    min_volume=500_000,
    max_stocks=20,
    universe_size=100
)

print("\n" + "=" * 80)
print("📊 RESULTS")
print("=" * 80)

print(f"\n✅ Found {len(results)} opportunities")

if results:
    print(f"\n🏆 Top Opportunities (Sorted by Entry Score):")
    print()
    print(f"{'Rank':<5} {'Symbol':<8} {'Price':>8} {'Sector':<20} {'RSI':>6} {'MA50%':>7} {'Mom10d':>8} {'Mom30d':>8} {'Score':>6}")
    print("-" * 100)

    for i, opp in enumerate(results, 1):
        print(f"{i:<5} {opp['symbol']:<8} ${opp['current_price']:>7.2f} {opp['sector'][:18]:<20} "
              f"{opp['rsi']:>6.1f} {opp['price_above_ma50']:>6.1f}% "
              f"{opp['momentum_10d']:>7.1f}% {opp['momentum_30d']:>7.1f}% "
              f"{opp['entry_score']:>6.1f}")

    # Summary stats
    print("\n" + "-" * 100)
    avg_rsi = sum(o['rsi'] for o in results) / len(results)
    avg_ma50 = sum(o['price_above_ma50'] for o in results) / len(results)
    avg_mom10 = sum(o['momentum_10d'] for o in results) / len(results)
    avg_mom30 = sum(o['momentum_30d'] for o in results) / len(results)
    avg_score = sum(o['entry_score'] for o in results) / len(results)

    print(f"{'AVERAGE':<5} {'':<8} {'':<8} {'':<20} "
          f"{avg_rsi:>6.1f} {avg_ma50:>6.1f}% "
          f"{avg_mom10:>7.1f}% {avg_mom30:>7.1f}% "
          f"{avg_score:>6.1f}")

    print(f"\n📈 Quality Check:")
    print(f"   Average RSI: {avg_rsi:.1f} (target: 45-55)")
    print(f"   Average above MA50: {avg_ma50:.1f}% (Winners had +12%)")
    print(f"   Average Mom 10d: {avg_mom10:.1f}% (Winners had +8%)")
    print(f"   Average Mom 30d: {avg_mom30:.1f}% (Winners had +22%)")

    if avg_rsi >= 45 and avg_ma50 >= 5 and avg_mom10 >= 5 and avg_mom30 >= 15:
        print(f"\n   ✅ EXCELLENT! Results match WINNER profile!")
    elif avg_rsi >= 40 and avg_ma50 >= 0 and avg_mom10 >= 0 and avg_mom30 >= 10:
        print(f"\n   ✅ GOOD! Results are in acceptable range")
    else:
        print(f"\n   ⚠️  Results are weaker than ideal - consider market conditions")

    # Sector breakdown
    from collections import Counter
    sectors = Counter(o['sector'] for o in results)

    print(f"\n📊 Sector Breakdown:")
    for sector, count in sectors.most_common():
        pct = count / len(results) * 100
        print(f"   {sector[:30]:<30} {count:>2} ({pct:>5.1f}%)")

else:
    print("\n⚠️  No opportunities found")
    print("\nPossible reasons:")
    print("  1. Market is in DOWNTREND (most stocks below MA50)")
    print("  2. Low momentum overall (few stocks rising)")
    print("  3. Need to relax filters slightly")
    print("\nSuggestions:")
    print("  - Try min_momentum_30d = 5.0 (instead of 10.0)")
    print("  - Try min_rsi = 35.0 (instead of 40.0)")
    print("  - Check market regime first")

print("\n" + "=" * 80)
print("✅ SCREENING COMPLETE")
print("=" * 80)
print("\n💡 Note: This screener uses PROVEN metrics from actual performance")
print("   These stocks should have similar characteristics to past winners!")
