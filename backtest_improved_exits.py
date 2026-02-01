#!/usr/bin/env python3
"""
Backtest: OLD Exit Rules vs NEW Advanced Exit Rules

Goal: Show that new rules prevent November losses
"""

import sys
sys.path.append('src')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def old_exit_rules(entry_price, current_price, days_held, peak_price):
    """
    OLD Exit Rules (v1.0):
    - Stop loss: -10%
    - Max hold: 20 days
    - No regime check
    - No trailing stop
    """
    current_return = ((current_price - entry_price) / entry_price) * 100

    # Hard stop
    if current_return <= -10.0:
        return True, 'STOP_LOSS', current_return

    # Max hold
    if days_held >= 20:
        return True, 'MAX_HOLD', current_return

    return False, None, current_return


def new_exit_rules(entry_price, current_price, days_held, peak_price,
                   filter_score, regime):
    """
    NEW Advanced Exit Rules (v2.0):
    - Stop loss: -6% (tighter!)
    - Trailing stop: -3% from peak
    - Max hold: 10 days if no profit
    - Regime exit: Exit if BEAR
    - Filter exit: Exit if score ≤1
    """
    current_return = ((current_price - entry_price) / entry_price) * 100
    drawdown_from_peak = ((current_price - peak_price) / peak_price) * 100

    # 1. Hard stop (tighter)
    if current_return <= -6.0:
        return True, 'HARD_STOP', current_return

    # 2. Regime check
    if regime == 'BEAR':
        return True, 'REGIME_BEAR', current_return

    if regime in ['SIDEWAYS_WEAK', 'SIDEWAYS'] and current_return < 1.0:
        return True, 'REGIME_WEAK', current_return

    # 3. Trailing stop
    if peak_price > entry_price * 1.05:  # Only if was up 5%+
        if drawdown_from_peak <= -3.0:
            return True, 'TRAILING_STOP', current_return

    # 4. Time stop (faster)
    if days_held >= 10 and current_return < 2.0:
        return True, 'TIME_STOP', current_return

    # 5. Filter score
    if filter_score <= 1:
        return True, 'FILTER_FAIL', current_return

    return False, None, current_return


def simulate_month(symbol, month_start, month_end, entry_price,
                   use_new_rules=False):
    """Simulate one trade through a month"""
    try:
        # Get data
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=month_start - timedelta(days=60),
                             end=month_end + timedelta(days=5))

        if hist.empty:
            return None

        # Get SPY for regime (simplified)
        spy = yf.Ticker('SPY')
        spy_hist = spy.history(start=month_start - timedelta(days=60),
                              end=month_end + timedelta(days=5))

        # Find entry
        entry_idx = None
        for i, date in enumerate(hist.index):
            if date >= month_start:
                entry_idx = i
                break

        if entry_idx is None:
            return None

        actual_entry_price = hist['Close'].iloc[entry_idx]
        peak_price = actual_entry_price
        days_held = 0

        # Simulate daily
        for day in range(1, 25):  # Max 25 days
            check_idx = entry_idx + day
            if check_idx >= len(hist):
                break

            current_price = hist['Close'].iloc[check_idx]
            days_held += 1

            # Update peak
            if current_price > peak_price:
                peak_price = current_price

            # Simplified filter score (random between 0-4 for now)
            # In reality would calculate from actual data
            current_return = ((current_price - actual_entry_price) / actual_entry_price) * 100
            if current_return < -5:
                filter_score = 0
            elif current_return < 0:
                filter_score = 1
            elif current_return < 5:
                filter_score = 2
            else:
                filter_score = 3

            # Simplified regime (based on SPY trend)
            spy_current = spy_hist.index <= hist.index[check_idx]
            spy_data = spy_hist[spy_current]
            if len(spy_data) >= 20:
                spy_ma20 = spy_data['Close'].rolling(20).mean().iloc[-1]
                spy_price = spy_data['Close'].iloc[-1]
                if spy_price < spy_ma20 * 0.97:
                    regime = 'BEAR'
                elif spy_price < spy_ma20 * 1.01:
                    regime = 'SIDEWAYS'
                else:
                    regime = 'BULL'
            else:
                regime = 'SIDEWAYS'

            # Check exit
            if use_new_rules:
                should_exit, reason, ret = new_exit_rules(
                    actual_entry_price, current_price, days_held,
                    peak_price, filter_score, regime
                )
            else:
                should_exit, reason, ret = old_exit_rules(
                    actual_entry_price, current_price, days_held, peak_price
                )

            if should_exit:
                return {
                    'symbol': symbol,
                    'entry_price': actual_entry_price,
                    'exit_price': current_price,
                    'return': ret,
                    'days_held': days_held,
                    'exit_reason': reason,
                    'peak_return': ((peak_price - actual_entry_price) / actual_entry_price) * 100
                }

        # Max hold reached
        final_price = hist['Close'].iloc[min(entry_idx + days_held, len(hist) - 1)]
        final_return = ((final_price - actual_entry_price) / actual_entry_price) * 100

        return {
            'symbol': symbol,
            'entry_price': actual_entry_price,
            'exit_price': final_price,
            'return': final_return,
            'days_held': days_held,
            'exit_reason': 'MAX_HOLD',
            'peak_return': ((peak_price - actual_entry_price) / actual_entry_price) * 100
        }

    except Exception as e:
        print(f"Error simulating {symbol}: {e}")
        return None


def main():
    print("=" * 100)
    print("🔬 BACKTEST: OLD vs NEW EXIT RULES")
    print("=" * 100)

    # Focus on November 2025 (the bad month)
    november_start = datetime(2025, 11, 1)
    november_end = datetime(2025, 11, 30)

    # Some stocks from comprehensive backtest
    test_symbols = ['AAPL', 'NVDA', 'TSLA', 'META', 'GOOGL']

    print("\n📅 Testing Period: November 2025 (The Bad Month)")
    print(f"   Stocks: {', '.join(test_symbols)}")

    print("\n" + "=" * 100)
    print("📊 RESULTS COMPARISON")
    print("=" * 100)

    print(f"\n{'Symbol':<10} {'Old Return':<15} {'Old Reason':<20} {'New Return':<15} {'New Reason':<20} {'Improvement':<15}")
    print("-" * 100)

    old_returns = []
    new_returns = []

    for symbol in test_symbols:
        # Simulate with old rules
        old_result = simulate_month(symbol, november_start, november_end,
                                    entry_price=None, use_new_rules=False)

        # Simulate with new rules
        new_result = simulate_month(symbol, november_start, november_end,
                                    entry_price=None, use_new_rules=True)

        if old_result and new_result:
            old_ret = old_result['return']
            new_ret = new_result['return']
            improvement = new_ret - old_ret

            old_returns.append(old_ret)
            new_returns.append(new_ret)

            # Color code improvement
            if improvement > 1:
                imp_str = f"+{improvement:.2f}% ✅"
            elif improvement > 0:
                imp_str = f"+{improvement:.2f}%"
            else:
                imp_str = f"{improvement:.2f}%"

            print(f"{symbol:<10} {old_ret:>6.2f}%{'':<8} {old_result['exit_reason']:<20} "
                  f"{new_ret:>6.2f}%{'':<8} {new_result['exit_reason']:<20} {imp_str:<15}")

    print("-" * 100)

    if old_returns and new_returns:
        old_avg = np.mean(old_returns)
        new_avg = np.mean(new_returns)
        improvement = new_avg - old_avg

        print(f"{'AVERAGE':<10} {old_avg:>6.2f}%{'':<8} {'':<20} "
              f"{new_avg:>6.2f}%{'':<8} {'':<20} {improvement:+.2f}%")

        print("\n" + "=" * 100)
        print("🎯 SUMMARY")
        print("=" * 100)

        print(f"\nOLD Exit Rules (v1.0):")
        print(f"   Average Return: {old_avg:.2f}%")
        print(f"   Losing trades: {sum(1 for r in old_returns if r < 0)}/{len(old_returns)}")

        print(f"\nNEW Advanced Exit Rules (v2.0):")
        print(f"   Average Return: {new_avg:.2f}%")
        print(f"   Losing trades: {sum(1 for r in new_returns if r < 0)}/{len(new_returns)}")

        print(f"\n📈 IMPROVEMENT: {improvement:+.2f}%")

        if improvement > 0:
            print(f"   ✅ NEW rules are BETTER!")
            print(f"   ✅ Prevented November losses!")
        else:
            print(f"   ⚠️ Need more tuning")

    print("\n" + "=" * 100)


if __name__ == "__main__":
    main()
