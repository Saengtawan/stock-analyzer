#!/usr/bin/env python3
"""
Backtest WITH Stop Loss - แก้ปัญหา Big Losses
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np

def backtest_with_stoploss(
    target_pct=5.0,
    stop_loss_pct=-6.0,  # Hard stop
    max_hold_days=30,
    test_period_months=6
):
    """
    Backtest ด้วย Stop Loss -6% (เหมือน Portfolio Manager v3.3)
    """

    print("=" * 80)
    print(f"BACKTEST WITH STOP LOSS: {stop_loss_pct}%")
    print("=" * 80)
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
    winning_trades = []
    losing_trades = []
    stopped_out = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty or len(hist) < max_hold_days:
                continue

            for i in range(0, len(hist) - max_hold_days, 7):
                entry_price = hist['Close'].iloc[i]
                hit_target = False
                hit_stop = False
                exit_day = max_hold_days
                exit_price = hist['Close'].iloc[i + min(max_hold_days, len(hist) - i - 1)]

                for day in range(1, min(max_hold_days + 1, len(hist) - i)):
                    current_price = hist['Close'].iloc[i + day]
                    gain_pct = ((current_price - entry_price) / entry_price) * 100

                    # Check STOP LOSS first (priority!)
                    if gain_pct <= stop_loss_pct:
                        hit_stop = True
                        exit_price = current_price
                        exit_day = day
                        break

                    # Then check target
                    if gain_pct >= target_pct:
                        hit_target = True
                        exit_price = current_price
                        exit_day = day
                        break

                final_return = ((exit_price - entry_price) / entry_price) * 100

                trade = {
                    'symbol': symbol,
                    'return_pct': final_return,
                    'hit_target': hit_target,
                    'hit_stop': hit_stop,
                    'exit_day': exit_day
                }

                all_trades.append(trade)

                if hit_target:
                    winning_trades.append(trade)
                elif hit_stop:
                    stopped_out.append(trade)
                    losing_trades.append(trade)
                else:
                    losing_trades.append(trade)

        except Exception as e:
            continue

    # Analysis
    print("=" * 80)
    print("RESULTS WITH STOP LOSS")
    print("=" * 80)
    print()

    total = len(all_trades)
    winners = len(winning_trades)
    stopped = len(stopped_out)
    other_losers = len(losing_trades) - stopped

    print(f"Total Trades: {total}")
    print(f"Winners (hit {target_pct}%): {winners} ({winners/total*100:.1f}%)")
    print(f"Stopped Out (hit {stop_loss_pct}%): {stopped} ({stopped/total*100:.1f}%)")
    print(f"Other Losers: {other_losers} ({other_losers/total*100:.1f}%)")
    print(f"Total Losers: {len(losing_trades)} ({len(losing_trades)/total*100:.1f}%)")
    print()

    # Win/Loss stats
    winning_returns = [t['return_pct'] for t in winning_trades]
    losing_returns = [t['return_pct'] for t in losing_trades]
    stopped_returns = [t['return_pct'] for t in stopped_out]

    avg_win = np.mean(winning_returns) if winning_returns else 0
    avg_loss = np.mean(losing_returns) if losing_returns else 0
    avg_stopped = np.mean(stopped_returns) if stopped_returns else 0

    print("=" * 80)
    print("PERFORMANCE METRICS")
    print("=" * 80)
    print()

    print(f"Average Win:  {avg_win:+.2f}%")
    print(f"Average Loss: {avg_loss:+.2f}%")
    print(f"  - Stopped Out: {avg_stopped:+.2f}%")
    print()

    # R:R Ratio
    rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    print(f"Reward:Risk Ratio: {rr_ratio:.2f}:1")

    if rr_ratio > 1:
        print(f"   ✅ IMPROVED! กำไรเฉลี่ยมากกว่าขาดทุนเฉลี่ย")
    else:
        print(f"   Still needs work")
    print()

    # EV
    win_rate = winners / total
    loss_rate = len(losing_trades) / total
    ev = (win_rate * avg_win) + (loss_rate * avg_loss)

    print(f"Expected Value: {ev:+.2f}%")
    print()

    # Net Profit Simulation
    print("=" * 80)
    print("NET PROFIT (100 Trades × $1000)")
    print("=" * 80)
    print()

    total_win_profit = winners * 1000 * (avg_win / 100)
    total_loss = len(losing_trades) * 1000 * (avg_loss / 100)
    net_profit = total_win_profit + total_loss

    print(f"Win Profit:  ${total_win_profit:,.2f}")
    print(f"Loss Amount: ${total_loss:,.2f}")
    print(f"NET PROFIT:  ${net_profit:,.2f}")
    print(f"ROI: {(net_profit / 100000) * 100:+.2f}%")
    print()

    loss_impact = abs(total_loss / total_win_profit) * 100 if total_win_profit > 0 else 0
    print(f"Loss Impact: {loss_impact:.1f}% of wins")
    print()

    # Compare with NO STOP LOSS
    print("=" * 80)
    print("COMPARISON: With vs Without Stop Loss")
    print("=" * 80)
    print()

    print(f"{'Metric':<25} | {'Without SL':<15} | {'With SL -6%':<15} | {'Change'}")
    print("-" * 80)
    print(f"{'Win Rate':<25} | {'76.5%':<15} | {f'{win_rate*100:.1f}%':<15} | {f'{win_rate*100-76.5:+.1f}%'}")
    print(f"{'Avg Loss':<25} | {'-13.01%':<15} | {f'{avg_loss:+.2f}%':<15} | {f'BETTER!' if avg_loss > -13.01 else 'WORSE'}")
    print(f"{'R:R Ratio':<25} | {'0.65:1':<15} | {f'{rr_ratio:.2f}:1':<15} | {f'BETTER!' if rr_ratio > 0.65 else 'WORSE'}")
    print(f"{'Expected Value':<25} | {'+3.37%':<15} | {f'{ev:+.2f}%':<15} | {f'{ev-3.37:+.2f}%'}")
    print(f"{'Loss Impact':<25} | {'46.9%':<15} | {f'{loss_impact:.1f}%':<15} | {f'{loss_impact-46.9:+.1f}%'}")
    print()

    # Worst case analysis
    worst_loss = np.min(losing_returns) if losing_returns else 0
    print("=" * 80)
    print("WORST CASE PROTECTION")
    print("=" * 80)
    print()

    print(f"Without Stop Loss:")
    print(f"  Worst Loss: -42.67%")
    print()

    print(f"With Stop Loss -6%:")
    print(f"  Worst Loss: {worst_loss:+.2f}%")
    print(f"  Protection: {abs(worst_loss - (-42.67)):.2f}% prevented!")
    print()

    # Summary
    print("=" * 80)
    print("💡 VERDICT")
    print("=" * 80)
    print()

    if rr_ratio > 0.65 and avg_loss > -13:
        print("✅ STOP LOSS WORKS!")
        print(f"   - R:R improved from 0.65:1 to {rr_ratio:.2f}:1")
        print(f"   - Avg loss reduced from -13.01% to {avg_loss:.2f}%")
        print(f"   - Worst loss capped at ~{stop_loss_pct}%")
        print()
        print("🎯 Recommendation:")
        print(f"   - USE -6% hard stop loss")
        print(f"   - This is ALREADY in Portfolio Manager v3.3!")
        print(f"   - Backtest should reflect actual trading rules")
    else:
        print("⚠️  Stop loss helps but may need adjustment")

    print()

    return {
        'win_rate': win_rate * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'rr_ratio': rr_ratio,
        'ev': ev,
        'worst_loss': worst_loss
    }


if __name__ == "__main__":
    results = backtest_with_stoploss(
        target_pct=5.0,
        stop_loss_pct=-6.0,  # Portfolio Manager rule
        max_hold_days=30,
        test_period_months=6
    )
