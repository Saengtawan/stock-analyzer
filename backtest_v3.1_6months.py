#!/usr/bin/env python3
"""
Growth Catalyst v3.1 - 6 MONTH BACKTEST

Test v3.1 over 6 months to include SUSTAINED BULL periods:
- June-July: Strong BULL
- Aug-Sept: Strong BULL
- Oct-Dec: Weak/mixed

This will show if v3.1 works during real BULL markets.
"""

import sys
sys.path.append('src')

# Import from v3.1
from backtest_v3.1_bull_momentum import BacktestV31BullMomentum

def main():
    print("🚀 Starting v3.1 Bull Momentum Backtest - 6 MONTHS")
    print("   Testing over sustained BULL periods (June-Dec)")
    print("   This will take 5-10 minutes...\n")

    # 6 months lookback
    backtest = BacktestV31BullMomentum(lookback_months=6)
    results = backtest.run_backtest()


if __name__ == "__main__":
    main()
