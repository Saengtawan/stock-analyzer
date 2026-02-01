#!/usr/bin/env python3
"""
Quick September Test - Does continuous backtest enter on Sept 10?
"""

from backtest_complete_6layer import CompleteSystemBacktest

if __name__ == "__main__":
    print("Testing: June 1 - Sept 15 (should include Sept 10 AVGO entry)")
    print()

    backtest = CompleteSystemBacktest(
        start_date='2025-06-01',
        end_date='2025-09-15'
    )

    backtest.run_backtest()
