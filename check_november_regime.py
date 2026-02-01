#!/usr/bin/env python3
"""
Check what the market regime was during November 2025
This explains why the month had -3.4% average return
"""

import sys
sys.path.append('src')

from datetime import datetime, timedelta
import pandas as pd
from market_regime_detector import MarketRegimeDetector

def main():
    print("=" * 80)
    print("🔍 NOVEMBER 2025 REGIME ANALYSIS")
    print("=" * 80)

    detector = MarketRegimeDetector()

    # Check regime throughout November
    november_start = datetime(2025, 11, 1)
    november_end = datetime(2025, 11, 30)

    print(f"\nChecking market regime from {november_start.date()} to {november_end.date()}...")
    print()

    # Sample key dates
    check_dates = pd.date_range(november_start, november_end, freq='3D')

    regimes = []
    for date in check_dates:
        regime_info = detector.get_current_regime(date)
        regimes.append({
            'date': date.strftime('%Y-%m-%d'),
            'regime': regime_info['regime'],
            'should_trade': regime_info['should_trade'],
            'strength': regime_info['strength'],
            'position_size': regime_info['position_size_multiplier']
        })

    # Display results
    print(f"{'Date':<12} {'Regime':<15} {'Should Trade':<15} {'Strength':<10} {'Position Size':<15}")
    print("-" * 80)

    for r in regimes:
        emoji = "🐻" if r['regime'] == 'BEAR' else ("🐂" if r['regime'] == 'BULL' else "➡️")
        trade = "✅ YES" if r['should_trade'] else "❌ NO"
        print(f"{r['date']:<12} {emoji} {r['regime']:<12} {trade:<15} "
              f"{r['strength']:<10} {r['position_size']*100:.0f}%")

    print()
    print("=" * 80)
    print("📊 REGIME SUMMARY")
    print("=" * 80)

    regime_counts = {}
    for r in regimes:
        regime_counts[r['regime']] = regime_counts.get(r['regime'], 0) + 1

    total = len(regimes)
    for regime, count in regime_counts.items():
        pct = (count / total) * 100
        print(f"   {regime:<15} {count:>2}/{total} days ({pct:>5.1f}%)")

    # Check if should have traded
    should_trade_count = sum(1 for r in regimes if r['should_trade'])
    should_not_trade = total - should_trade_count

    print(f"\n   Should Trade:     {should_trade_count}/{total} days")
    print(f"   Should NOT Trade: {should_not_trade}/{total} days")

    if should_not_trade > total / 2:
        print(f"\n   ⚠️ WARNING: Market was unfavorable for >50% of November!")
        print(f"   This explains the -3.4% monthly average.")
        print(f"   \n   ✅ SOLUTION: Daily regime monitoring would have:")
        print(f"      1. Prevented entry on bad days")
        print(f"      2. Exited positions when regime turned BEAR/SIDEWAYS_WEAK")
        print(f"      3. Protected capital during unfavorable conditions")

    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
