#!/usr/bin/env python3
"""
Backtest: วิเคราะห์ว่าใช้กี่วันถึงกำไร 5%
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np
from collections import defaultdict

def backtest_days_to_target(symbols_to_test=None, target_pct=5.0, max_hold_days=30, test_period_months=6):
    """
    Backtest: วิเคราะห์ว่าใช้กี่วันถึงกำไร target_pct%

    Args:
        symbols_to_test: List of symbols (if None, use common growth stocks)
        target_pct: Target profit percentage (default 5%)
        max_hold_days: Maximum holding period (default 30 days)
        test_period_months: How many months back to test (default 6)
    """

    print("=" * 80)
    print(f"BACKTEST: Days to {target_pct}% Profit Analysis")
    print("=" * 80)
    print()

    # Default test symbols (mix of growth stocks)
    if symbols_to_test is None:
        symbols_to_test = [
            # Tech/Growth
            'NVDA', 'AMD', 'AVGO', 'PLTR', 'SNOW', 'CRWD',
            # Biotech
            'MRNA', 'BNTX', 'VRTX', 'REGN',
            # EV/Clean Energy
            'TSLA', 'RIVN', 'LCID', 'ENPH',
            # Fintech
            'SQ', 'COIN', 'SOFI',
            # Other Growth
            'SHOP', 'NET', 'DDOG', 'ZS', 'MDB'
        ]

    # Calculate test period
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30 * test_period_months)

    print(f"Test Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Target: {target_pct}% profit")
    print(f"Max Hold: {max_hold_days} days")
    print(f"Testing {len(symbols_to_test)} stocks")
    print()

    # Results storage
    all_trades = []
    days_to_target_list = []
    winning_trades = []
    losing_trades = []

    # Test each symbol
    for symbol in symbols_to_test:
        try:
            # Get price data
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty or len(hist) < max_hold_days:
                continue

            # Simulate entries every 7 days (weekly)
            for i in range(0, len(hist) - max_hold_days, 7):
                entry_date = hist.index[i]
                entry_price = hist['Close'].iloc[i]

                # Track performance for max_hold_days
                hit_target = False
                days_to_target = None
                max_gain = 0
                exit_price = entry_price
                exit_day = max_hold_days

                for day in range(1, min(max_hold_days + 1, len(hist) - i)):
                    current_price = hist['Close'].iloc[i + day]
                    gain_pct = ((current_price - entry_price) / entry_price) * 100

                    if gain_pct > max_gain:
                        max_gain = gain_pct

                    # Check if hit target
                    if gain_pct >= target_pct and not hit_target:
                        hit_target = True
                        days_to_target = day
                        exit_price = current_price
                        exit_day = day
                        break

                # If didn't hit target, exit at max_hold_days
                if not hit_target:
                    exit_price = hist['Close'].iloc[i + min(max_hold_days, len(hist) - i - 1)]
                    exit_day = min(max_hold_days, len(hist) - i - 1)

                final_return = ((exit_price - entry_price) / entry_price) * 100

                trade = {
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'exit_day': exit_day,
                    'return_pct': final_return,
                    'hit_target': hit_target,
                    'days_to_target': days_to_target,
                    'max_gain': max_gain
                }

                all_trades.append(trade)

                if hit_target:
                    winning_trades.append(trade)
                    days_to_target_list.append(days_to_target)
                else:
                    losing_trades.append(trade)

        except Exception as e:
            print(f"Error testing {symbol}: {e}")
            continue

    # Analysis
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()

    total_trades = len(all_trades)
    winners = len(winning_trades)
    losers = len(losing_trades)
    win_rate = (winners / total_trades * 100) if total_trades > 0 else 0

    print(f"Total Trades: {total_trades}")
    print(f"Winners: {winners} ({win_rate:.1f}%)")
    print(f"Losers: {losers} ({100-win_rate:.1f}%)")
    print()

    if days_to_target_list:
        avg_days = np.mean(days_to_target_list)
        median_days = np.median(days_to_target_list)
        min_days = np.min(days_to_target_list)
        max_days = np.max(days_to_target_list)

        print("=" * 80)
        print(f"⏱️  DAYS TO {target_pct}% PROFIT (Winners Only)")
        print("=" * 80)
        print()
        print(f"Average:    {avg_days:.1f} days")
        print(f"Median:     {median_days:.1f} days")
        print(f"Fastest:    {min_days} days")
        print(f"Slowest:    {max_days} days")
        print()

        # Distribution
        print("Distribution:")
        print(f"  1-3 days:   {sum(1 for d in days_to_target_list if d <= 3)} trades ({sum(1 for d in days_to_target_list if d <= 3)/len(days_to_target_list)*100:.1f}%)")
        print(f"  4-7 days:   {sum(1 for d in days_to_target_list if 4 <= d <= 7)} trades ({sum(1 for d in days_to_target_list if 4 <= d <= 7)/len(days_to_target_list)*100:.1f}%)")
        print(f"  8-14 days:  {sum(1 for d in days_to_target_list if 8 <= d <= 14)} trades ({sum(1 for d in days_to_target_list if 8 <= d <= 14)/len(days_to_target_list)*100:.1f}%)")
        print(f"  15-21 days: {sum(1 for d in days_to_target_list if 15 <= d <= 21)} trades ({sum(1 for d in days_to_target_list if 15 <= d <= 21)/len(days_to_target_list)*100:.1f}%)")
        print(f"  22-30 days: {sum(1 for d in days_to_target_list if 22 <= d <= 30)} trades ({sum(1 for d in days_to_target_list if 22 <= d <= 30)/len(days_to_target_list)*100:.1f}%)")
        print()

    # Analyze losers
    if losing_trades:
        losing_returns = [t['return_pct'] for t in losing_trades]
        avg_loss = np.mean(losing_returns)

        print("=" * 80)
        print("📉 TRADES THAT DIDN'T HIT TARGET")
        print("=" * 80)
        print()
        print(f"Average Return: {avg_loss:.2f}%")
        print(f"How close they got:")

        # Check how close they got to target
        close_calls = sum(1 for t in losing_trades if t['max_gain'] >= target_pct * 0.8)
        print(f"  Reached 80%+ of target: {close_calls} trades ({close_calls/len(losing_trades)*100:.1f}%)")
        print()

    # Best performers
    print("=" * 80)
    print("🏆 FASTEST WINNERS (Top 10)")
    print("=" * 80)
    print()

    fastest = sorted(winning_trades, key=lambda x: x['days_to_target'])[:10]
    for i, trade in enumerate(fastest, 1):
        print(f"{i:2d}. {trade['symbol']:6} - {trade['days_to_target']:2d} days ({trade['entry_date'].strftime('%Y-%m-%d')}) - Final: {trade['return_pct']:+.1f}%")

    print()

    # Summary
    print("=" * 80)
    print("💡 INSIGHTS")
    print("=" * 80)
    print()

    if days_to_target_list:
        if median_days <= 7:
            print(f"✅ Typical winning trade hits {target_pct}% in ~{median_days:.0f} days (VERY FAST)")
            print(f"   → 7-day timeframe is GOOD")
        elif median_days <= 14:
            print(f"✅ Typical winning trade hits {target_pct}% in ~{median_days:.0f} days")
            print(f"   → 14-day timeframe is optimal")
        elif median_days <= 21:
            print(f"⚠️  Typical winning trade hits {target_pct}% in ~{median_days:.0f} days")
            print(f"   → Consider 21-day timeframe")
        else:
            print(f"⚠️  Typical winning trade hits {target_pct}% in ~{median_days:.0f} days (SLOW)")
            print(f"   → May need 30-day timeframe or lower target")

    print()
    print(f"Win Rate: {win_rate:.1f}%")
    if win_rate >= 60:
        print("   → Excellent! (60%+)")
    elif win_rate >= 55:
        print("   → Good (55-60%)")
    elif win_rate >= 50:
        print("   → Acceptable (50-55%)")
    else:
        print("   → Low (<50%) - may need better filtering")

    print()

    return {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'avg_days_to_target': np.mean(days_to_target_list) if days_to_target_list else None,
        'median_days_to_target': np.median(days_to_target_list) if days_to_target_list else None,
        'days_distribution': days_to_target_list
    }


if __name__ == "__main__":
    # Run backtest
    results = backtest_days_to_target(
        target_pct=5.0,
        max_hold_days=30,
        test_period_months=6
    )
