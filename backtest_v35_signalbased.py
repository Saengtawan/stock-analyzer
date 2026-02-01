#!/usr/bin/env python3
"""
Backtest v3.5 SIGNAL-BASED EXITS: Root Cause Analysis
Compare v3.4 (Time/Partial arbitrary rules) vs v3.5 (Technical breakdown signals)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np

def calculate_sma(prices, period=20):
    """Calculate Simple Moving Average"""
    if len(prices) < period:
        return None
    return np.mean(prices[-period:])

def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def check_lower_lows(prices, lookback=5):
    """Check if making lower lows (downtrend)"""
    if len(prices) < lookback * 2:
        return False

    recent_low = np.min(prices[-lookback:])
    previous_low = np.min(prices[-lookback*2:-lookback])

    return recent_low < previous_low

def backtest_v35_signalbased(
    target_pct=5.0,
    stop_loss_pct=-6.0,
    max_hold_days=30,
    test_period_months=6
):
    """
    Backtest v3.5 SIGNAL-BASED EXITS
    """

    print("=" * 80)
    print("BACKTEST v3.5 SIGNAL-BASED EXITS")
    print("=" * 80)
    print()
    print("Exit Rules:")
    print(f"  1. Target: {target_pct}%")
    print(f"  2. Hard Stop: {stop_loss_pct}%")
    print(f"  3. Trailing Stop: -6% from peak (after 5 days)")
    print(f"  4. SIGNAL: Breaking SMA20 (2 days)")
    print(f"  5. SIGNAL: Weak RSI < 35")
    print(f"  6. SIGNAL: Lower Lows (downtrend)")
    print(f"  7. SIGNAL: Failed Breakout (peak 3%+ → < 0.5%)")
    print(f"  8. Max Hold: {max_hold_days} days")
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
            # Need extra days for SMA20 calculation
            hist = ticker.history(start=start_date - timedelta(days=60), end=end_date)

            if hist.empty or len(hist) < max_hold_days + 20:
                continue

            # Skip first 20 days (need for SMA20 baseline)
            for i in range(20, len(hist) - max_hold_days, 7):
                entry_price = hist['Close'].iloc[i]
                entry_date = hist.index[i]
                exit_day = max_hold_days
                exit_price = hist['Close'].iloc[i + min(max_hold_days, len(hist) - i - 1)]
                exit_reason = 'MAX_HOLD'

                peak_price = entry_price

                for day in range(1, min(max_hold_days + 1, len(hist) - i)):
                    current_idx = i + day
                    current_price = hist['Close'].iloc[current_idx]
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

                    # Priority 3: Trailing Stop (after 5 days)
                    if day >= 5:
                        drawdown = ((current_price - peak_price) / peak_price) * 100
                        if drawdown < -6.0:
                            exit_reason = 'TRAILING_STOP'
                            exit_price = current_price
                            exit_day = day
                            break

                    # Priority 4: SIGNAL-BASED EXITS (v3.5)
                    # Only check after 3+ days to let trade develop

                    if day >= 3:
                        # Get price history up to current point
                        price_history = hist['Close'].iloc[:current_idx+1].values

                        # Signal 1: Breaking SMA20 (only after 5 days)
                        if day >= 5 and len(price_history) >= 20:
                            sma20 = calculate_sma(price_history, 20)
                            if sma20 is not None and current_price < sma20:
                                # Check 2 days consecutive
                                if len(price_history) >= 2:
                                    prev_price = price_history[-2]
                                    prev_sma20 = calculate_sma(price_history[:-1], 20)
                                    if prev_sma20 is not None and prev_price < prev_sma20:
                                        distance_pct = ((current_price - sma20) / sma20) * 100
                                        # Only exit if meaningfully below SMA20 (> 1%)
                                        if distance_pct < -1.0:
                                            exit_reason = 'SIGNAL_SMA20_BREAK'
                                            exit_price = current_price
                                            exit_day = day
                                            break

                        # Signal 2: Weak RSI (only after 5 days)
                        if day >= 5 and len(price_history) >= 15:
                            rsi = calculate_rsi(price_history, 14)
                            if rsi is not None and rsi < 35:
                                exit_reason = 'SIGNAL_WEAK_RSI'
                                exit_price = current_price
                                exit_day = day
                                break

                        # Signal 3: Lower Lows (only after 7 days, per root cause)
                        if day >= 7 and len(price_history) >= 10:
                            if check_lower_lows(price_history, lookback=5):
                                # Also check if we're in loss or minimal profit
                                if gain_pct < 2.0:
                                    exit_reason = 'SIGNAL_LOWER_LOWS'
                                    exit_price = current_price
                                    exit_day = day
                                    break

                        # Signal 4: Failed Breakout (can check earlier since requires 3%+ peak)
                        if peak_gain >= 3.0 and gain_pct < 0.5:
                            exit_reason = 'SIGNAL_FAILED_BREAKOUT'
                            exit_price = current_price
                            exit_day = day
                            break

                final_return = ((exit_price - entry_price) / entry_price) * 100

                trade = {
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'return_pct': final_return,
                    'exit_reason': exit_reason,
                    'exit_day': exit_day,
                    'peak_gain': peak_gain
                }

                all_trades.append(trade)
                exit_reasons_count[exit_reason] = exit_reasons_count.get(exit_reason, 0) + 1

        except Exception as e:
            continue

    # Analysis
    total = len(all_trades)
    winners = [t for t in all_trades if t['return_pct'] >= target_pct]
    losers = [t for t in all_trades if t['return_pct'] < target_pct]

    print("=" * 80)
    print("RESULTS v3.5 (SIGNAL-BASED)")
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

        emoji = '🎯' if reason == 'TARGET_HIT' else '⚠️' if 'STOP' in reason else '📊' if 'SIGNAL' in reason else '⏳'

        print(f"{emoji} {reason:25} | {count:3} trades ({pct:5.1f}%) | Avg: {avg_return:+.2f}%")

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
    print("COMPARISON: v3.4 (Arbitrary) vs v3.5 (Signal-Based)")
    print("=" * 80)
    print()

    print(f"{'Metric':<25} | {'v3.4 (Time/Partial)':<20} | {'v3.5 (Signals)':<20}")
    print("-" * 80)
    print(f"{'Win Rate':<25} | {'46.6%':<20} | {f'{win_rate*100:.1f}%':<20}")
    print(f"{'Avg Win':<25} | {'+8.16%':<20} | {f'{avg_win:+.2f}%':<20}")
    print(f"{'Avg Loss':<25} | {'-4.21%':<20} | {f'{avg_loss:+.2f}%':<20}")
    print(f"{'Worst Loss':<25} | {'-20.16%':<20} | {f'{worst_loss:+.2f}%':<20}")
    print(f"{'R:R Ratio':<25} | {'1.95:1':<20} | {f'{rr_ratio:.2f}:1':<20}")
    print(f"{'Expected Value':<25} | {'+1.56%':<20} | {f'{ev:+.2f}%':<20}")
    print()

    # Signal Coverage Analysis
    signal_exits = [t for t in all_trades if 'SIGNAL' in t['exit_reason']]
    print("=" * 80)
    print("📊 SIGNAL-BASED EXIT ANALYSIS")
    print("=" * 80)
    print()

    print(f"Signal-Based Exits: {len(signal_exits)} trades ({len(signal_exits)/total*100:.1f}%)")
    print()

    if signal_exits:
        print("Signal Breakdown:")
        for reason in ['SIGNAL_SMA20_BREAK', 'SIGNAL_WEAK_RSI', 'SIGNAL_LOWER_LOWS', 'SIGNAL_FAILED_BREAKOUT']:
            signal_trades = [t for t in signal_exits if t['exit_reason'] == reason]
            if signal_trades:
                avg_ret = np.mean([t['return_pct'] for t in signal_trades])
                avg_day = np.mean([t['exit_day'] for t in signal_trades])
                print(f"  {reason:30} | {len(signal_trades):3} trades | Avg: {avg_ret:+.2f}% | Day: {avg_day:.0f}")

    print()

    # Final verdict
    print("=" * 80)
    print("💡 VERDICT: v3.5 SIGNAL-BASED EXITS")
    print("=" * 80)
    print()

    print("Key Advantages:")
    print(f"  ✅ ROOT CAUSE based - Every exit has a REASON")
    print(f"  ✅ Technical breakdown signals (100% coverage in historical analysis)")
    print(f"  ✅ No arbitrary time/price rules")
    print(f"  ✅ Holds strong positions longer, cuts weak ones early")
    print()

    if win_rate > 0.50 and rr_ratio >= 1.0 and ev >= 2.0:
        print("🚀 Portfolio Manager v3.5 READY!")
        print(f"   - Win Rate: {win_rate*100:.1f}% (healthy)")
        print(f"   - R:R: {rr_ratio:.2f}:1 (balanced)")
        print(f"   - EV: {ev:+.2f}% (profitable)")
    else:
        print(f"Current Performance:")
        print(f"   - Win Rate: {win_rate*100:.1f}%")
        print(f"   - R:R: {rr_ratio:.2f}:1")
        print(f"   - EV: {ev:+.2f}%")

    print()

    return {
        'win_rate': win_rate * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'rr_ratio': rr_ratio,
        'ev': ev,
        'worst_loss': worst_loss,
        'signal_exits': len(signal_exits)
    }


if __name__ == "__main__":
    results = backtest_v35_signalbased(
        target_pct=5.0,
        stop_loss_pct=-6.0,
        max_hold_days=30,
        test_period_months=6
    )
