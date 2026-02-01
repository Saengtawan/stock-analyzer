#!/usr/bin/env python3
"""
Test if macro caching works and finds Sept trades
"""

from backtest_complete_6layer import CompleteSystemBacktest

if __name__ == "__main__":
    print("Testing June-Sept with macro caching")
    print("Expected: June trades + Sept trades (AVGO on Sept 10)")
    print()

    backtest = CompleteSystemBacktest(
        start_date='2025-06-01',
        end_date='2025-09-30'
    )

    backtest.run_backtest()

    print("\n" + "=" * 80)
    print(f"Result: {len(backtest.closed_trades)} total trades")
    print("=" * 80)

    # Check if we got Sept trades
    import pandas as pd
    if backtest.closed_trades:
        df = pd.DataFrame(backtest.closed_trades)
        df['month'] = pd.to_datetime(df['entry_date']).dt.month

        june_trades = len(df[df['month'] == 6])
        july_trades = len(df[df['month'] == 7])
        aug_trades = len(df[df['month'] == 8])
        sept_trades = len(df[df['month'] == 9])

        print(f"\nJune: {june_trades} trades")
        print(f"July: {july_trades} trades")
        print(f"Aug: {aug_trades} trades")
        print(f"Sept: {sept_trades} trades")

        if sept_trades > 0:
            print("\n✅ SUCCESS - Sept trades found!")
        else:
            print("\n❌ STILL BROKEN - No Sept trades")
    else:
        print("\n❌ No trades at all!")
