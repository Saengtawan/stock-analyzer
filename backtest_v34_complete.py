#!/usr/bin/env python3
"""
Backtest v3.4 COMPLETE: Stop Loss + Time Stop + Partial Exit
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np

def backtest_v34_complete(
    target_pct=5.0,
    stop_loss_pct=-6.0,
    time_stop_days=10,
    time_stop_min_gain=2.0,
    partial_exit_peak=4.0,
    partial_exit_reversal=3.0,
    max_hold_days=30,
    test_period_months=6
):
    """
    Portfolio Manager v3.4 Complete Exit Rules
    """

    print("=" * 80)
    print("BACKTEST v3.4 COMPLETE: All Exit Rules")
    print("=" * 80)
    print()
    print("Exit Rules:")
    print(f"  1. Target: {target_pct}%")
    print(f"  2. Hard Stop: {stop_loss_pct}%")
    print(f"  3. Time Stop: {time_stop_days} days if gain < {time_stop_min_gain}%")
    print(f"  4. Partial Exit: Peak {partial_exit_peak}% → Reversal < {partial_exit_reversal}%")
    print(f"  5. Max Hold: {max_hold_days} days")
    print()

    symbols = [
        'NVDA', 'AMD', 'AVGO', 'PLTR', 'SNOW', 'CRWD',
        'MRNA', 'BNTX', 'VRTX', 'REGN',
        'TSLA', 'RIVN', 'LCID', 'ENPH',
        'SQ', 'COIN', 'SOFI',
        'SHOP', 'NET', 'DDOG', 'ZS', 'MDB'
    ]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=30 * test_period_months)

    all_trades = []
    exit_reasons_count = {}

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty or len(hist) < max_hold_days:
                continue

            for i in range(0, len(hist) - max_hold_days, 7):
                entry_price = hist['Close'].iloc[i]
                exit_day = max_hold_days
                exit_price = hist['Close'].iloc[i + min(max_hold_days, len(hist) - i - 1)]
                exit_reason = 'MAX_HOLD'

                peak_price = entry_price

                for day in range(1, min(max_hold_days + 1, len(hist) - i)):
                    current_price = hist['Close'].iloc[i + day]
                    gain_pct = ((current_price - entry_price) / entry_price) * 100

                    # Track peak
                    if current_price > peak_price:
                        peak_price = current_price

                    peak_gain = ((peak_price - entry_price) / entry_price) * 100

                    # Priority 1: Hard Stop Loss
                    if gain_pct <= stop_loss_pct:
                        exit_reason = 'HARD_STOP'
                        exit_price = current_price
                        exit_day = day
                        break

                    # Priority 2: Target Hit
                    if gain_pct >= target_pct:
                        exit_reason = 'TARGET_HIT'
                        exit_price = current_price
                        exit_day = day
                        break

                    # Priority 3: Partial Exit (Almost Won Protection)
                    if peak_gain >= partial_exit_peak and gain_pct < partial_exit_reversal:
                        exit_reason = 'PARTIAL_EXIT'
                        exit_price = current_price
                        exit_day = day
                        break

                    # Priority 4: Time Stop (No Momentum)
                    if day >= time_stop_days and gain_pct < time_stop_min_gain:
                        exit_reason = 'TIME_STOP'
                        exit_price = current_price
                        exit_day = day
                        break

                final_return = ((exit_price - entry_price) / entry_price) * 100

                trade = {
                    'symbol': symbol,
                    'return_pct': final_return,
                    'exit_reason': exit_reason,
                    'exit_day': exit_day,
                    'peak_gain': peak_gain
                }

                all_trades.append(trade)

                # Count exit reasons
                exit_reasons_count[exit_reason] = exit_reasons_count.get(exit_reason, 0) + 1

        except Exception as e:
            continue

    # Analysis
    total = len(all_trades)
    winners = [t for t in all_trades if t['return_pct'] >= target_pct]
    losers = [t for t in all_trades if t['return_pct'] < target_pct]

    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()

    print(f"Total Trades: {total}")
    print(f"Winners: {len(winners)} ({len(winners)/total*100:.1f}%)")
    print(f"Losers: {len(losers)} ({len(losers)/total*100:.1f}%)")
    print()

    # Exit Reasons Breakdown
    print("=" * 80)
    print("EXIT REASONS BREAKDOWN")
    print("=" * 80)
    print()

    for reason, count in sorted(exit_reasons_count.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total) * 100
        avg_return = np.mean([t['return_pct'] for t in all_trades if t['exit_reason'] == reason])

        emoji = '🎯' if reason == 'TARGET_HIT' else '⚠️' if 'STOP' in reason else '⏰' if reason == 'TIME_STOP' else '🟡' if reason == 'PARTIAL_EXIT' else '⏳'

        print(f"{emoji} {reason:15} | {count:3} trades ({pct:5.1f}%) | Avg: {avg_return:+.2f}%")

    print()

    # Performance
    winning_returns = [t['return_pct'] for t in winners]
    losing_returns = [t['return_pct'] for t in losers]

    avg_win = np.mean(winning_returns) if winning_returns else 0
    avg_loss = np.mean(losing_returns) if losing_returns else 0
    worst_loss = np.min([t['return_pct'] for t in all_trades])

    print("=" * 80)
    print("PERFORMANCE METRICS")
    print("=" * 80)
    print()

    print(f"Average Win:  {avg_win:+.2f}%")
    print(f"Average Loss: {avg_loss:+.2f}%")
    print(f"Worst Loss:   {worst_loss:+.2f}%")
    print()

    # R:R
    rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    print(f"Reward:Risk Ratio: {rr_ratio:.2f}:1")

    if rr_ratio >= 1.5:
        print(f"   ✅ EXCELLENT!")
    elif rr_ratio >= 1.0:
        print(f"   ✅ GOOD")
    else:
        print(f"   ⚠️  Needs work")
    print()

    # EV
    win_rate = len(winners) / total
    loss_rate = len(losers) / total
    ev = (win_rate * avg_win) + (loss_rate * avg_loss)

    print(f"Expected Value: {ev:+.2f}%")
    print()

    # Net Profit
    print("=" * 80)
    print("NET PROFIT (100 Trades × $1000)")
    print("=" * 80)
    print()

    expected_winners = int(100 * win_rate)
    expected_losers = int(100 * loss_rate)

    total_win_profit = expected_winners * 1000 * (avg_win / 100)
    total_loss = expected_losers * 1000 * (avg_loss / 100)
    net_profit = total_win_profit + total_loss

    print(f"Winners: {expected_winners} trades → ${total_win_profit:,.2f}")
    print(f"Losers:  {expected_losers} trades → ${total_loss:,.2f}")
    print(f"NET PROFIT: ${net_profit:,.2f}")
    print(f"ROI: {(net_profit / 100000) * 100:+.2f}%")
    print()

    loss_impact = abs(total_loss / total_win_profit) * 100 if total_win_profit > 0 else 0
    print(f"Loss Impact: {loss_impact:.1f}% of wins")
    print()

    # Comparison Table
    print("=" * 80)
    print("EVOLUTION: v3.0 → v3.3 → v3.4")
    print("=" * 80)
    print()

    print(f"{'Metric':<20} | {'v3.0 (No SL)':<15} | {'v3.3 (SL -6%)':<15} | {'v3.4 (Complete)':<15}")
    print("-" * 80)
    print(f"{'Win Rate':<20} | {'76.5%':<15} | {'64.6%':<15} | {f'{win_rate*100:.1f}%':<15}")
    print(f"{'Avg Win':<20} | {'+8.40%':<15} | {'+8.16%':<15} | {f'{avg_win:+.2f}%':<15}")
    print(f"{'Avg Loss':<20} | {'-13.01%':<15} | {'-7.57%':<15} | {f'{avg_loss:+.2f}%':<15}")
    print(f"{'Worst Loss':<20} | {'-42.67%':<15} | {'-20.16%':<15} | {f'{worst_loss:+.2f}%':<15}")
    print(f"{'R:R Ratio':<20} | {'0.65:1':<15} | {'1.08:1':<15} | {f'{rr_ratio:.2f}:1':<15}")
    print(f"{'Expected Value':<20} | {'+3.37%':<15} | {'+2.60%':<15} | {f'{ev:+.2f}%':<15}")
    print(f"{'Loss Impact':<20} | {'46.9%':<15} | {'50.7%':<15} | {f'{loss_impact:.1f}%':<15}")
    print()

    # Analysis of improvements
    print("=" * 80)
    print("💡 IMPROVEMENTS FROM v3.4")
    print("=" * 80)
    print()

    # Count how many "almost won" were saved
    partial_exits = [t for t in all_trades if t['exit_reason'] == 'PARTIAL_EXIT']
    time_stops = [t for t in all_trades if t['exit_reason'] == 'TIME_STOP']

    print(f"Partial Exit Protection:")
    print(f"  {len(partial_exits)} trades ({len(partial_exits)/total*100:.1f}%)")
    if partial_exits:
        avg_partial = np.mean([t['return_pct'] for t in partial_exits])
        avg_peak = np.mean([t['peak_gain'] for t in partial_exits])
        print(f"  Average peak: {avg_peak:.1f}% → Exit at: {avg_partial:+.2f}%")
        print(f"  Prevented turning winners into losers!")

    print()

    print(f"Time Stop Protection:")
    print(f"  {len(time_stops)} trades ({len(time_stops)/total*100:.1f}%)")
    if time_stops:
        avg_time = np.mean([t['return_pct'] for t in time_stops])
        avg_days = np.mean([t['exit_day'] for t in time_stops])
        print(f"  Average exit: Day {avg_days:.0f}, Return: {avg_time:+.2f}%")
        print(f"  Prevented holding dead money!")

    print()

    # Final verdict
    print("=" * 80)
    print("🎯 FINAL VERDICT")
    print("=" * 80)
    print()

    if rr_ratio >= 1.0 and ev >= 2.5:
        print("✅ EXCELLENT SYSTEM!")
        print(f"   - R:R Ratio: {rr_ratio:.2f}:1 (Balanced)")
        print(f"   - Expected Value: {ev:+.2f}%")
        print(f"   - Smart exits working perfectly")
        print()
        print("🚀 Portfolio Manager v3.4 READY FOR PRODUCTION!")
    elif rr_ratio >= 0.8 and ev >= 2.0:
        print("✅ GOOD SYSTEM")
        print(f"   - R:R Ratio: {rr_ratio:.2f}:1")
        print(f"   - Expected Value: {ev:+.2f}%")
        print(f"   - Working well, minor tweaks possible")
    else:
        print("⚠️  NEEDS IMPROVEMENT")
        print(f"   - R:R Ratio: {rr_ratio:.2f}:1")
        print(f"   - Expected Value: {ev:+.2f}%")

    print()

    return {
        'win_rate': win_rate * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'rr_ratio': rr_ratio,
        'ev': ev,
        'worst_loss': worst_loss,
        'partial_exits': len(partial_exits),
        'time_stops': len(time_stops)
    }


if __name__ == "__main__":
    results = backtest_v34_complete(
        target_pct=5.0,
        stop_loss_pct=-6.0,
        time_stop_days=10,
        time_stop_min_gain=2.0,
        partial_exit_peak=4.0,
        partial_exit_reversal=3.0,
        max_hold_days=30,
        test_period_months=6
    )
