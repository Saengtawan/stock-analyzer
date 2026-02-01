#!/usr/bin/env python3
"""
Comprehensive Backtest: OLD vs NEW Exit Rules
Proves that new rules prevent November losses

Comparison:
- OLD: -10% stop, 20 day hold, no regime check, no trailing
- NEW: -6% stop, 10 day hold, regime check, -3% trailing
"""

import sys
sys.path.append('src')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger

# Import our components
try:
    from advanced_exit_rules import AdvancedExitRules
    from market_regime_detector import MarketRegimeDetector
    ADVANCED_AVAILABLE = True
except ImportError:
    logger.warning("Advanced components not available")
    ADVANCED_AVAILABLE = False


class OldExitRules:
    """OLD Exit Rules (v1.0) - Loose and slow"""

    def __init__(self):
        self.hard_stop = -10.0  # Loose stop
        self.max_hold = 20      # Long hold

    def should_exit(self, position, current_date, hist_data, spy_data=None):
        """Check exit with OLD rules - no regime, no trailing"""
        try:
            entry_price = position['entry_price']
            days_held = position.get('days_held', 0)

            # Get current price
            current_data = hist_data[hist_data.index <= current_date]
            if current_data.empty:
                return False, None, None

            current_price = float(current_data['Close'].iloc[-1])
            current_return = ((current_price - entry_price) / entry_price) * 100

            # 1. Hard stop only
            if current_return <= self.hard_stop:
                return True, 'OLD_STOP_LOSS', current_price

            # 2. Max hold only
            if days_held >= self.max_hold:
                return True, 'OLD_MAX_HOLD', current_price

            # NO regime check, NO trailing stop, NO filter check
            return False, None, current_price

        except Exception as e:
            logger.error(f"OLD exit check error: {e}")
            return False, None, None


def backtest_single_stock(symbol, start_date, end_date, entry_price=None):
    """
    Backtest one stock with both OLD and NEW rules

    Returns: (old_result, new_result)
    """
    try:
        # Get data
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date - timedelta(days=90),
                             end=end_date + timedelta(days=10))

        if hist.empty or len(hist) < 30:
            logger.warning(f"Insufficient data for {symbol}")
            return None, None

        # Get SPY data
        spy = yf.Ticker('SPY')
        spy_hist = spy.history(start=start_date - timedelta(days=90),
                              end=end_date + timedelta(days=10))

        # Find entry point
        entry_idx = None
        for i, date in enumerate(hist.index):
            if date.date() >= start_date.date():
                entry_idx = i
                break

        if entry_idx is None or entry_idx >= len(hist) - 5:
            logger.warning(f"No valid entry point for {symbol}")
            return None, None

        actual_entry_price = float(hist['Close'].iloc[entry_idx])
        actual_entry_date = hist.index[entry_idx]

        # Initialize exit rules
        old_rules = OldExitRules()
        new_rules = AdvancedExitRules() if ADVANCED_AVAILABLE else None

        # Simulate with OLD rules
        old_result = simulate_trade(
            symbol, hist, spy_hist, entry_idx, actual_entry_price,
            actual_entry_date, old_rules, use_new=False
        )

        # Simulate with NEW rules
        new_result = simulate_trade(
            symbol, hist, spy_hist, entry_idx, actual_entry_price,
            actual_entry_date, new_rules, use_new=True
        )

        return old_result, new_result

    except Exception as e:
        logger.error(f"Backtest error for {symbol}: {e}")
        return None, None


def simulate_trade(symbol, hist, spy_hist, entry_idx, entry_price,
                   entry_date, exit_rules, use_new=False):
    """Simulate one trade to exit"""

    position = {
        'symbol': symbol,
        'entry_price': entry_price,
        'entry_date': entry_date,
        'highest_price': entry_price,
        'days_held': 0,
    }

    max_days = 25
    peak_price = entry_price

    for day in range(1, max_days):
        check_idx = entry_idx + day

        if check_idx >= len(hist):
            break

        check_date = hist.index[check_idx]
        current_price = float(hist['Close'].iloc[check_idx])

        # Update position
        position['days_held'] = day
        if current_price > peak_price:
            peak_price = current_price
            position['highest_price'] = peak_price

        # Check exit
        should_exit, reason, exit_price = exit_rules.should_exit(
            position, check_date, hist, spy_hist
        )

        if should_exit:
            ret = ((exit_price - entry_price) / entry_price) * 100
            return {
                'symbol': symbol,
                'entry_date': entry_date,
                'entry_price': entry_price,
                'exit_date': check_date,
                'exit_price': exit_price,
                'return': ret,
                'days_held': day,
                'exit_reason': reason,
                'peak_price': peak_price,
                'peak_return': ((peak_price - entry_price) / entry_price) * 100,
                'rule_type': 'NEW' if use_new else 'OLD'
            }

    # Hit max days
    final_idx = min(entry_idx + max_days, len(hist) - 1)
    final_price = float(hist['Close'].iloc[final_idx])
    final_ret = ((final_price - entry_price) / entry_price) * 100

    return {
        'symbol': symbol,
        'entry_date': entry_date,
        'entry_price': entry_price,
        'exit_date': hist.index[final_idx],
        'exit_price': final_price,
        'return': final_ret,
        'days_held': max_days,
        'exit_reason': 'MAX_DAYS',
        'peak_price': peak_price,
        'peak_return': ((peak_price - entry_price) / entry_price) * 100,
        'rule_type': 'NEW' if use_new else 'OLD'
    }


def main():
    print("=" * 100)
    print("🔬 COMPREHENSIVE BACKTEST: OLD vs NEW EXIT RULES")
    print("=" * 100)

    if not ADVANCED_AVAILABLE:
        print("\n❌ Advanced exit rules not available - cannot run comparison")
        return

    # Test stocks across different months
    test_data = [
        # November 2025 - THE BAD MONTH (focus here)
        ('AAPL', datetime(2025, 11, 1), datetime(2025, 11, 30)),
        ('NVDA', datetime(2025, 11, 1), datetime(2025, 11, 30)),
        ('TSLA', datetime(2025, 11, 1), datetime(2025, 11, 30)),
        ('META', datetime(2025, 11, 1), datetime(2025, 11, 30)),
        ('GOOGL', datetime(2025, 11, 1), datetime(2025, 11, 30)),

        # June 2025 - GOOD MONTH (for comparison)
        ('AAPL', datetime(2025, 6, 1), datetime(2025, 6, 30)),
        ('NVDA', datetime(2025, 6, 1), datetime(2025, 6, 30)),
        ('TSLA', datetime(2025, 6, 1), datetime(2025, 6, 30)),
    ]

    print(f"\n📊 Testing {len(test_data)} trades...")
    print(f"   Focus: November 2025 (bad month) improvement")
    print(f"   Baseline: June 2025 (good month)")

    results = []

    for symbol, start, end in test_data:
        logger.info(f"Testing {symbol} {start.strftime('%Y-%m')}...")
        old, new = backtest_single_stock(symbol, start, end)

        if old and new:
            results.append({
                'symbol': symbol,
                'month': start.strftime('%Y-%m'),
                'old': old,
                'new': new,
                'improvement': new['return'] - old['return']
            })

    if not results:
        print("\n❌ No valid backtest results")
        return

    # Analyze results
    print("\n" + "=" * 100)
    print("📊 DETAILED RESULTS")
    print("=" * 100)

    print(f"\n{'Symbol':<8} {'Month':<10} {'OLD Return':<12} {'OLD Reason':<18} "
          f"{'NEW Return':<12} {'NEW Reason':<18} {'Improvement':<12}")
    print("-" * 100)

    november_old = []
    november_new = []
    june_old = []
    june_new = []

    for r in results:
        old = r['old']
        new = r['new']
        imp = r['improvement']

        # Categorize by month
        if r['month'] == '2025-11':
            november_old.append(old['return'])
            november_new.append(new['return'])
        elif r['month'] == '2025-06':
            june_old.append(old['return'])
            june_new.append(new['return'])

        # Color code
        imp_color = "✅" if imp > 1 else ("🟡" if imp > 0 else "🔴")

        print(f"{r['symbol']:<8} {r['month']:<10} "
              f"{old['return']:>6.2f}%{'':<5} {old['exit_reason']:<18} "
              f"{new['return']:>6.2f}%{'':<5} {new['exit_reason']:<18} "
              f"{imp:+6.2f}% {imp_color}")

    print("-" * 100)

    # Summary statistics
    print("\n" + "=" * 100)
    print("🎯 SUMMARY BY MONTH")
    print("=" * 100)

    if november_old and november_new:
        print(f"\n📉 NOVEMBER 2025 (Bad Month):")
        print(f"   OLD Rules: Avg {np.mean(november_old):+.2f}% "
              f"(Best: {max(november_old):+.2f}%, Worst: {min(november_old):+.2f}%)")
        print(f"   NEW Rules: Avg {np.mean(november_new):+.2f}% "
              f"(Best: {max(november_new):+.2f}%, Worst: {min(november_new):+.2f}%)")
        nov_improvement = np.mean(november_new) - np.mean(november_old)
        print(f"   📈 IMPROVEMENT: {nov_improvement:+.2f}%")

        if nov_improvement > 0:
            pct_better = (nov_improvement / abs(np.mean(november_old))) * 100
            print(f"   ✅ {pct_better:.1f}% better in bad month!")

    if june_old and june_new:
        print(f"\n📈 JUNE 2025 (Good Month):")
        print(f"   OLD Rules: Avg {np.mean(june_old):+.2f}%")
        print(f"   NEW Rules: Avg {np.mean(june_new):+.2f}%")
        june_improvement = np.mean(june_new) - np.mean(june_old)
        print(f"   📈 IMPROVEMENT: {june_improvement:+.2f}%")

    # Overall
    all_old = [r['old']['return'] for r in results]
    all_new = [r['new']['return'] for r in results]

    print(f"\n📊 OVERALL ({len(results)} trades):")
    print(f"   OLD Rules: Avg {np.mean(all_old):+.2f}%")
    print(f"   NEW Rules: Avg {np.mean(all_new):+.2f}%")
    overall_improvement = np.mean(all_new) - np.mean(all_old)
    print(f"   📈 IMPROVEMENT: {overall_improvement:+.2f}%")

    # Exit reason analysis
    print("\n" + "=" * 100)
    print("📋 EXIT REASON BREAKDOWN")
    print("=" * 100)

    old_reasons = {}
    new_reasons = {}

    for r in results:
        old_reason = r['old']['exit_reason']
        new_reason = r['new']['exit_reason']

        old_reasons[old_reason] = old_reasons.get(old_reason, 0) + 1
        new_reasons[new_reason] = new_reasons.get(new_reason, 0) + 1

    print("\nOLD Rules Exit Reasons:")
    for reason, count in sorted(old_reasons.items(), key=lambda x: -x[1]):
        pct = (count / len(results)) * 100
        print(f"   {reason:<20} {count:>3} trades ({pct:>5.1f}%)")

    print("\nNEW Rules Exit Reasons:")
    for reason, count in sorted(new_reasons.items(), key=lambda x: -x[1]):
        pct = (count / len(results)) * 100
        print(f"   {reason:<20} {count:>3} trades ({pct:>5.1f}%)")

    # Final verdict
    print("\n" + "=" * 100)
    print("✅ FINAL VERDICT")
    print("=" * 100)

    if november_old and november_new:
        nov_avg_old = np.mean(november_old)
        nov_avg_new = np.mean(november_new)

        print(f"\n🎯 Primary Goal: Fix November Losses")
        print(f"   Before: {nov_avg_old:+.2f}% average")
        print(f"   After:  {nov_avg_new:+.2f}% average")

        if nov_avg_new > nov_avg_old:
            reduction = nov_avg_new - nov_avg_old
            print(f"   ✅ SUCCESS! Improved by {reduction:+.2f}%")

            if nov_avg_old < 0 and nov_avg_new > nov_avg_old:
                pct_reduction = ((nov_avg_new - nov_avg_old) / abs(nov_avg_old)) * 100
                print(f"   ✅ Reduced losses by {pct_reduction:.1f}%!")
        else:
            print(f"   ⚠️ Still needs work")

    print(f"\n🚀 Overall Performance:")
    print(f"   Average improvement: {overall_improvement:+.2f}%")
    print(f"   Better in bad months: {'✅ YES' if nov_improvement > 0 else '❌ NO'}")
    print(f"   Better overall: {'✅ YES' if overall_improvement > 0 else '❌ NO'}")

    print("\n" + "=" * 100)


if __name__ == "__main__":
    main()
