#!/usr/bin/env python3
"""
COMPLETE SYSTEM BACKTEST: Entry Screening + v3.5 Signal-Based Exits
====================================================================

ทดสอบระบบทั้งหมด:
1. Entry: 6-Layer Scoring + Confidence Filtering (เหมือนการค้นหาจริง)
2. Exit: v3.5 Signal-Based Exits (SMA20, RSI, Lower Lows, Failed Breakout)

เพื่อดูว่าเมื่อใช้ร่วมกันแล้ว ผลลัพธ์เป็นอย่างไร
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np
from loguru import logger

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

def calculate_6layer_score(hist, symbol):
    """
    Calculate 6-Layer Scoring (simplified version)

    Layers:
    1. Fundamental (P/E, Revenue Growth) - Simulated
    2. Technical (RSI, SMA, Support/Resistance)
    3. Momentum (Price change, Volume)
    4. Valuation (P/B, EV/EBITDA) - Simulated
    5. Sentiment (Insider buying, Analyst) - Simulated
    6. Catalyst (Earnings, News) - Simulated
    """

    if len(hist) < 50:
        return None

    close_prices = hist['Close'].values
    volumes = hist['Volume'].values

    # Calculate technical indicators
    current_price = close_prices[-1]
    sma20 = calculate_sma(close_prices, 20)
    sma50 = calculate_sma(close_prices, 50)
    rsi = calculate_rsi(close_prices, 14)

    # Price change metrics
    price_change_5d = ((close_prices[-1] - close_prices[-6]) / close_prices[-6]) * 100 if len(close_prices) > 5 else 0
    price_change_20d = ((close_prices[-1] - close_prices[-21]) / close_prices[-21]) * 100 if len(close_prices) > 20 else 0

    # Volume metrics
    avg_volume = np.mean(volumes[-20:]) if len(volumes) > 20 else np.mean(volumes)
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1

    # Support/Resistance
    recent_high = np.max(close_prices[-20:]) if len(close_prices) > 20 else current_price
    recent_low = np.min(close_prices[-20:]) if len(close_prices) > 20 else current_price

    # Layer Scoring (0-10 each)
    scores = {}

    # Layer 1: Fundamental (simulated - assume average)
    scores['fundamental'] = 6.0  # Neutral fundamental score

    # Layer 2: Technical (RSI, SMA position)
    tech_score = 0
    if rsi and sma20:
        # RSI scoring (40-70 is good)
        if 40 <= rsi <= 70:
            tech_score += 5
        elif rsi > 70:
            tech_score += 2  # Overbought
        else:
            tech_score += 3  # Oversold

        # SMA position
        if current_price > sma20:
            tech_score += 3
        if sma50 and current_price > sma50:
            tech_score += 2

    scores['technical'] = min(tech_score, 10)

    # Layer 3: Momentum (price change, volume)
    momentum_score = 0
    if price_change_5d > 0:
        momentum_score += 3
    if price_change_20d > 0:
        momentum_score += 3
    if volume_ratio > 1.2:
        momentum_score += 4

    scores['momentum'] = min(momentum_score, 10)

    # Layer 4: Valuation (simulated)
    scores['valuation'] = 5.0  # Neutral

    # Layer 5: Sentiment (simulated)
    scores['sentiment'] = 5.0  # Neutral

    # Layer 6: Catalyst (simulated - check for recent breakout)
    catalyst_score = 0
    if current_price >= recent_high * 0.98:  # Near recent high
        catalyst_score += 5
    if volume_ratio > 1.5:  # High volume
        catalyst_score += 5

    scores['catalyst'] = min(catalyst_score, 10)

    # Calculate weighted average (6 layers equally weighted)
    total_score = sum(scores.values()) / len(scores)

    # Confidence calculation (based on consistency)
    consistency = 0
    above_5 = sum(1 for s in scores.values() if s >= 5)
    consistency = (above_5 / len(scores)) * 10  # 0-10 scale

    return {
        'total_score': total_score,
        'layer_scores': scores,
        'confidence': consistency,
        'rsi': rsi,
        'sma20': sma20,
        'current_price': current_price,
        'volume_ratio': volume_ratio
    }

def should_enter_trade(score_data, min_score=5.0, min_confidence=3.0):
    """
    Determine if we should enter trade based on screening criteria

    Criteria (similar to actual screening):
    - Total score >= min_score (usually 5-6)
    - Confidence >= min_confidence (at least 3/6 layers good)
    - Technical score >= 3 (not too weak)
    """

    if not score_data:
        return False

    # Check minimum thresholds
    if score_data['total_score'] < min_score:
        return False

    if score_data['confidence'] < min_confidence:
        return False

    if score_data['layer_scores']['technical'] < 3:
        return False

    return True

def backtest_complete_system(
    symbols_universe=None,
    test_period_months=6,
    min_entry_score=5.0,
    min_entry_confidence=3.0,
    target_pct=5.0,
    stop_loss_pct=-6.0,
    max_hold_days=30
):
    """
    Complete system backtest
    """

    print("=" * 80)
    print("COMPLETE SYSTEM BACKTEST: Entry Screening + v3.5 Exits")
    print("=" * 80)
    print()
    print("Entry Criteria (6-Layer Scoring):")
    print(f"  - Minimum Total Score: {min_entry_score}/10")
    print(f"  - Minimum Confidence: {min_entry_confidence}/6 layers")
    print(f"  - Minimum Technical Score: 3/10")
    print()
    print("Exit Rules (v3.5 Signal-Based):")
    print(f"  1. Target: {target_pct}%")
    print(f"  2. Hard Stop: {stop_loss_pct}%")
    print(f"  3. Trailing Stop: -6% from peak (after 5 days)")
    print(f"  4. SIGNAL: Breaking SMA20 (Day 5+, >1% below)")
    print(f"  5. SIGNAL: Weak RSI < 35 (Day 5+)")
    print(f"  6. SIGNAL: Lower Lows (Day 7+, gain < 2%)")
    print(f"  7. SIGNAL: Failed Breakout (peak 3%+ → < 0.5%)")
    print(f"  8. Max Hold: {max_hold_days} days")
    print()

    # Default universe (tech, biotech, fintech, etc.)
    if not symbols_universe:
        symbols_universe = [
            # Tech
            'NVDA', 'AMD', 'AVGO', 'QCOM', 'MU', 'AMAT',
            'PLTR', 'SNOW', 'CRWD', 'ZS', 'NET', 'DDOG', 'MDB',
            # Biotech
            'MRNA', 'BNTX', 'VRTX', 'REGN', 'GILD',
            # EV
            'TSLA', 'RIVN', 'LCID', 'ENPH',
            # Fintech
            'SQ', 'COIN', 'SOFI', 'AFRM',
            # E-commerce
            'SHOP', 'MELI',
            # Cloud/SaaS
            'WDAY', 'TEAM', 'OKTA'
        ]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=30 * test_period_months)

    all_trades = []
    entry_rejections = {
        'low_score': 0,
        'low_confidence': 0,
        'low_technical': 0,
        'no_data': 0
    }
    exit_reasons_count = {}

    print(f"📊 Backtesting {len(symbols_universe)} symbols from {start_date.date()} to {end_date.date()}...")
    print()

    for symbol in symbols_universe:
        try:
            ticker = yf.Ticker(symbol)
            # Fetch extra days for indicator calculation
            hist = ticker.history(start=start_date - timedelta(days=60), end=end_date)

            if hist.empty or len(hist) < max_hold_days + 50:
                entry_rejections['no_data'] += 1
                continue

            # Simulate weekly entry attempts (every 7 days)
            for i in range(50, len(hist) - max_hold_days, 7):
                entry_date = hist.index[i]

                # Calculate 6-layer score at entry point
                hist_at_entry = hist.iloc[:i+1]
                score_data = calculate_6layer_score(hist_at_entry, symbol)

                if not score_data:
                    entry_rejections['no_data'] += 1
                    continue

                # Check entry criteria (SCREENING)
                if not should_enter_trade(score_data, min_entry_score, min_entry_confidence):
                    # Track why rejected
                    if score_data['total_score'] < min_entry_score:
                        entry_rejections['low_score'] += 1
                    elif score_data['confidence'] < min_entry_confidence:
                        entry_rejections['low_confidence'] += 1
                    elif score_data['layer_scores']['technical'] < 3:
                        entry_rejections['low_technical'] += 1
                    continue

                # PASSED SCREENING - Enter trade!
                entry_price = hist['Close'].iloc[i]
                exit_day = max_hold_days
                exit_price = hist['Close'].iloc[i + min(max_hold_days, len(hist) - i - 1)]
                exit_reason = 'MAX_HOLD'

                peak_price = entry_price

                # Simulate holding period with v3.5 exits
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
                    if day >= 3:
                        price_history = hist['Close'].iloc[:current_idx+1].values

                        # Signal 1: Breaking SMA20 (Day 5+)
                        if day >= 5 and len(price_history) >= 20:
                            sma20 = calculate_sma(price_history, 20)
                            if sma20 is not None and current_price < sma20:
                                # Check 2 days consecutive
                                if len(price_history) >= 2:
                                    prev_price = price_history[-2]
                                    prev_sma20 = calculate_sma(price_history[:-1], 20)
                                    if prev_sma20 is not None and prev_price < prev_sma20:
                                        distance_pct = ((current_price - sma20) / sma20) * 100
                                        if distance_pct < -1.0:
                                            exit_reason = 'SIGNAL_SMA20_BREAK'
                                            exit_price = current_price
                                            exit_day = day
                                            break

                        # Signal 2: Weak RSI (Day 5+)
                        if day >= 5 and len(price_history) >= 15:
                            rsi = calculate_rsi(price_history, 14)
                            if rsi is not None and rsi < 35:
                                exit_reason = 'SIGNAL_WEAK_RSI'
                                exit_price = current_price
                                exit_day = day
                                break

                        # Signal 3: Lower Lows (Day 7+)
                        if day >= 7 and len(price_history) >= 10:
                            if check_lower_lows(price_history, lookback=5):
                                if gain_pct < 2.0:
                                    exit_reason = 'SIGNAL_LOWER_LOWS'
                                    exit_price = current_price
                                    exit_day = day
                                    break

                        # Signal 4: Failed Breakout
                        if peak_gain >= 3.0 and gain_pct < 0.5:
                            exit_reason = 'SIGNAL_FAILED_BREAKOUT'
                            exit_price = current_price
                            exit_day = day
                            break

                final_return = ((exit_price - entry_price) / entry_price) * 100

                trade = {
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'return_pct': final_return,
                    'exit_reason': exit_reason,
                    'exit_day': exit_day,
                    'peak_gain': peak_gain,
                    'entry_score': score_data['total_score'],
                    'entry_confidence': score_data['confidence']
                }

                all_trades.append(trade)
                exit_reasons_count[exit_reason] = exit_reasons_count.get(exit_reason, 0) + 1

        except Exception as e:
            logger.warning(f"{symbol}: Error - {e}")
            continue

    # ===== ANALYSIS =====

    total = len(all_trades)

    if total == 0:
        print("❌ No trades found! Entry criteria may be too strict.")
        print()
        print("Entry Rejections:")
        for reason, count in entry_rejections.items():
            print(f"  {reason}: {count}")
        return

    winners = [t for t in all_trades if t['return_pct'] >= target_pct]
    losers = [t for t in all_trades if t['return_pct'] < target_pct]

    print("=" * 80)
    print("📊 COMPLETE SYSTEM RESULTS")
    print("=" * 80)
    print()

    print(f"Total Trades Entered: {total}")
    print(f"  (Passed 6-layer screening)")
    print(f"Winners: {len(winners)} ({len(winners)/total*100:.1f}%)")
    print(f"Losers: {len(losers)} ({len(losers)/total*100:.1f}%)")
    print()

    # Entry Quality
    print("=" * 80)
    print("📈 ENTRY QUALITY (6-Layer Scoring)")
    print("=" * 80)
    print()

    avg_entry_score = np.mean([t['entry_score'] for t in all_trades])
    avg_entry_confidence = np.mean([t['entry_confidence'] for t in all_trades])

    print(f"Average Entry Score: {avg_entry_score:.1f}/10")
    print(f"Average Entry Confidence: {avg_entry_confidence:.1f}/10")
    print()

    print("Entry Rejection Breakdown:")
    total_rejections = sum(entry_rejections.values())
    for reason, count in sorted(entry_rejections.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_rejections * 100) if total_rejections > 0 else 0
        print(f"  {reason:20}: {count:5} ({pct:5.1f}%)")
    print()
    print(f"Entry Success Rate: {total}/{total + total_rejections} ({total/(total + total_rejections)*100:.1f}%)")
    print()

    # Exit Breakdown
    print("=" * 80)
    print("🚪 EXIT REASONS BREAKDOWN (v3.5)")
    print("=" * 80)
    print()

    for reason, count in sorted(exit_reasons_count.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total) * 100
        avg_return = np.mean([t['return_pct'] for t in all_trades if t['exit_reason'] == reason])
        avg_day = np.mean([t['exit_day'] for t in all_trades if t['exit_reason'] == reason])

        emoji = '🎯' if reason == 'TARGET_HIT' else '⚠️' if 'STOP' in reason else '📊' if 'SIGNAL' in reason else '⏳'

        print(f"{emoji} {reason:25} | {count:3} ({pct:5.1f}%) | Avg: {avg_return:+6.2f}% | Day: {avg_day:4.1f}")

    print()

    # Performance Metrics
    winning_returns = [t['return_pct'] for t in winners]
    losing_returns = [t['return_pct'] for t in losers]

    avg_win = np.mean(winning_returns) if winning_returns else 0
    avg_loss = np.mean(losing_returns) if losing_returns else 0
    worst_loss = np.min([t['return_pct'] for t in all_trades]) if all_trades else 0
    best_win = np.max([t['return_pct'] for t in all_trades]) if all_trades else 0

    print("=" * 80)
    print("💰 PERFORMANCE METRICS")
    print("=" * 80)
    print()

    print(f"Average Win:   {avg_win:+.2f}%")
    print(f"Average Loss:  {avg_loss:+.2f}%")
    print(f"Best Win:      {best_win:+.2f}%")
    print(f"Worst Loss:    {worst_loss:+.2f}%")
    print()

    # R:R Ratio
    rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    print(f"Reward:Risk Ratio: {rr_ratio:.2f}:1")

    if rr_ratio >= 2.0:
        print(f"   ✅ EXCELLENT!")
    elif rr_ratio >= 1.5:
        print(f"   ✅ VERY GOOD")
    elif rr_ratio >= 1.0:
        print(f"   ✅ GOOD")
    else:
        print(f"   ⚠️  Needs improvement")
    print()

    # Expected Value
    win_rate = len(winners) / total
    loss_rate = len(losers) / total
    ev = (win_rate * avg_win) + (loss_rate * avg_loss)

    print(f"Expected Value: {ev:+.2f}%")
    print()

    # Net Profit Simulation
    print("=" * 80)
    print("💵 NET PROFIT (100 Trades × $1000 Each)")
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

    # Signal Performance
    signal_exits = [t for t in all_trades if 'SIGNAL' in t['exit_reason']]

    print("=" * 80)
    print("📊 SIGNAL-BASED EXIT PERFORMANCE")
    print("=" * 80)
    print()

    print(f"Signal-Based Exits: {len(signal_exits)} ({len(signal_exits)/total*100:.1f}%)")
    print()

    if signal_exits:
        print("Signal Breakdown:")
        for reason in ['SIGNAL_SMA20_BREAK', 'SIGNAL_WEAK_RSI', 'SIGNAL_LOWER_LOWS', 'SIGNAL_FAILED_BREAKOUT']:
            signal_trades = [t for t in signal_exits if t['exit_reason'] == reason]
            if signal_trades:
                avg_ret = np.mean([t['return_pct'] for t in signal_trades])
                avg_day = np.mean([t['exit_day'] for t in signal_trades])
                print(f"  {reason:30} | {len(signal_trades):3} | Avg: {avg_ret:+6.2f}% | Day: {avg_day:4.1f}")

    print()

    # Final Verdict
    print("=" * 80)
    print("🎯 FINAL VERDICT")
    print("=" * 80)
    print()

    if win_rate >= 0.40 and rr_ratio >= 1.5 and ev >= 1.0:
        print("✅ EXCELLENT SYSTEM!")
        print(f"   - Win Rate: {win_rate*100:.1f}% (healthy)")
        print(f"   - R:R: {rr_ratio:.2f}:1 (strong)")
        print(f"   - EV: {ev:+.2f}% (profitable)")
        print(f"   - Entry screening works!")
        print(f"   - Signal-based exits work!")
        print()
        print("🚀 SYSTEM IS PRODUCTION READY!")
    elif win_rate >= 0.35 and rr_ratio >= 1.0 and ev >= 0.5:
        print("✅ GOOD SYSTEM")
        print(f"   - Win Rate: {win_rate*100:.1f}%")
        print(f"   - R:R: {rr_ratio:.2f}:1")
        print(f"   - EV: {ev:+.2f}%")
        print(f"   - System is working, minor improvements possible")
    else:
        print("⚠️  NEEDS IMPROVEMENT")
        print(f"   - Win Rate: {win_rate*100:.1f}%")
        print(f"   - R:R: {rr_ratio:.2f}:1")
        print(f"   - EV: {ev:+.2f}%")

    print()

    return {
        'total_trades': total,
        'win_rate': win_rate * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'rr_ratio': rr_ratio,
        'ev': ev,
        'net_profit': net_profit,
        'signal_exits': len(signal_exits),
        'avg_entry_score': avg_entry_score,
        'avg_entry_confidence': avg_entry_confidence
    }


if __name__ == "__main__":
    results = backtest_complete_system(
        test_period_months=6,
        min_entry_score=5.0,      # Minimum 5/10 total score
        min_entry_confidence=3.0,  # At least 3/6 layers good
        target_pct=5.0,
        stop_loss_pct=-6.0,
        max_hold_days=30
    )
