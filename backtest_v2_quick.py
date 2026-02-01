#!/usr/bin/env python3
"""
Quick Backtest V2 - Test 3 Key Months Only
==========================================

Test only June, September, October 2025 to validate fixes quickly.
"""

import sys
from backtest_complete_6layer import CompleteSystemBacktest

if __name__ == "__main__":
    print("="*80)
    print("🚀 QUICK BACKTEST V2 - 3 KEY MONTHS")
    print("="*80)
    print("Testing: June, September, October 2025")
    print("Expected: ~15-20 trades in 3 months")
    print()

    # Test June (2 trades in V1, expect 4-6 in V2)
    print("\n" + "="*80)
    print("📅 JUNE 2025")
    print("="*80)
    june = CompleteSystemBacktest('2025-06-01', '2025-06-30')
    june.run_backtest()

    # Test September (2 trades in V1, expect 4-6 in V2)
    print("\n" + "="*80)
    print("📅 SEPTEMBER 2025")
    print("="*80)
    sept = CompleteSystemBacktest('2025-09-01', '2025-09-30')
    sept.run_backtest()

    # Test October (1 trade in V1, expect 2-4 in V2)
    print("\n" + "="*80)
    print("📅 OCTOBER 2025")
    print("="*80)
    oct = CompleteSystemBacktest('2025-10-01', '2025-10-31')
    oct.run_backtest()

    # Combined summary
    print("\n" + "="*80)
    print("📊 COMBINED 3-MONTH SUMMARY")
    print("="*80)

    all_trades = june.closed_trades + sept.closed_trades + oct.closed_trades

    if all_trades:
        import pandas as pd

        df = pd.DataFrame(all_trades)

        total_trades = len(df)
        winners = len(df[df['return_pct'] > 0])
        win_rate = (winners / total_trades) * 100

        avg_return = df['return_pct'].mean()
        total_return = df['return_pct'].sum()

        print(f"\n🎯 Overall Performance:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Win Rate: {win_rate:.1f}%")
        print(f"   Avg Return: {avg_return:+.2f}%")
        print(f"   Total Return: {total_return:+.2f}%")
        print(f"   Monthly Average: {total_return/3:+.2f}%")

        # Compare to V1
        print(f"\n📊 Comparison to V1:")
        print(f"   V1 (June+Sept+Oct): 5 trades, +0.68%/month avg")
        print(f"   V2 (June+Sept+Oct): {total_trades} trades, {total_return/3:+.2f}%/month avg")
        print(f"   Improvement: {((total_return/3 - 0.68) / 0.68 * 100) if 0.68 != 0 else 0:+.1f}%")
    else:
        print("❌ No trades executed!")
