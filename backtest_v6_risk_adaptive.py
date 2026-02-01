#!/usr/bin/env python3
"""
v6: RISK-ADAPTIVE SYSTEM
========================

แนวคิด: ไม่ใช้ stop/target แบบเดียวกันทุก stock
แต่ปรับตามลักษณะของแต่ละ stock และความมั่นใจในการเข้า

ADAPTIVE DIMENSIONS:
1. Volatility-Based: High volatility → wider stops, higher targets
2. Confidence-Based: Strong entry → more room, weak entry → quick exit
3. Momentum-Based: Strong momentum → higher targets

Risk Tiers:
- HIGH RISK: High volatility (ATR > 3%) + Low confidence (< 6)
  → Tight stop -3%, Low target 3%

- MEDIUM RISK: Normal volatility + Medium confidence
  → Medium stop -3.5%, Medium target 4%

- LOW RISK: Low volatility + High confidence (8+)
  → Wider stop -4.5%, Higher target 5%

ผลที่คาดหวัง:
- Win Rate เพิ่มขึ้น (เพราะ target ปรับตาม volatility)
- Loss Impact ลดลง (เพราะ stop ปรับตาม risk)
- Profit เพิ่มขึ้น (เพราะให้ stock ที่ดีวิ่งมากขึ้น)
"""

import sys
import os
sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer')

from backtest_v5_smart_exits import (
    calculate_momentum_reversal, calculate_volume_health,
    check_break_below_entry, detect_failed_pump
)

from backtest_complete_system_v2 import (
    calculate_sma, calculate_rsi, check_lower_lows,
    calculate_6layer_score_v2, should_enter_trade_v2,
    get_sector_regime
)

from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np


def calculate_atr(hist_data, period=14):
    """
    Calculate Average True Range (ATR) - measure of volatility

    Returns:
        atr: ATR value
        atr_pct: ATR as % of current price
    """
    if len(hist_data) < period + 1:
        return None, None

    high = hist_data['High'].values[-period:]
    low = hist_data['Low'].values[-period:]
    close = hist_data['Close'].values[-period-1:-1]

    tr1 = high - low
    tr2 = np.abs(high - close)
    tr3 = np.abs(low - close)

    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    atr = np.mean(tr)

    current_price = hist_data['Close'].iloc[-1]
    atr_pct = (atr / current_price) * 100

    return atr, atr_pct


def determine_risk_profile(score_data, atr_pct, momentum_score):
    """
    Determine risk profile for adaptive stop/target

    Returns:
        risk_tier: 'LOW', 'MEDIUM', 'HIGH'
        target_pct: Target percentage
        stop_pct: Stop loss percentage
        description: Human-readable description
    """

    confidence = score_data.get('confidence', 5.0)
    total_score = score_data.get('total_score', 5.0)

    # Calculate risk score (0-10, higher = riskier)
    volatility_risk = min(atr_pct / 0.5, 10)  # 5% ATR = max risk
    confidence_risk = 10 - confidence  # Low confidence = high risk
    momentum_risk = 10 - momentum_score  # Low momentum = high risk

    total_risk = (volatility_risk + confidence_risk + momentum_risk) / 3

    # Determine tier
    if total_risk < 4:  # Low risk
        risk_tier = 'LOW'
        target_pct = 5.0  # Higher target
        stop_pct = -4.5   # Wider stop (give room)
        description = f"Low Risk: High confidence ({confidence:.1f}), Low volatility ({atr_pct:.2f}%)"

    elif total_risk < 6.5:  # Medium risk
        risk_tier = 'MEDIUM'
        target_pct = 4.0
        stop_pct = -3.5
        description = f"Medium Risk: Med confidence ({confidence:.1f}), Med volatility ({atr_pct:.2f}%)"

    else:  # High risk
        risk_tier = 'HIGH'
        target_pct = 3.0  # Lower target (take profit faster)
        stop_pct = -3.0   # Tighter stop (cut losses faster)
        description = f"High Risk: Low confidence ({confidence:.1f}), High volatility ({atr_pct:.2f}%)"

    return risk_tier, target_pct, stop_pct, description


def backtest_v6_risk_adaptive(
    symbols=None,
    start_date='2024-06-01',
    end_date='2024-12-01',
    max_hold_days=30,
    entry_interval_days=7
):
    """
    v6: Risk-Adaptive System
    - Stop/target adapt to each stock's risk profile
    - Smart exits adapt to risk tier
    """

    if symbols is None:
        symbols = [
            'NVDA', 'AMD', 'AVGO', 'QCOM', 'MU',
            'PLTR', 'SNOW', 'CRWD', 'ZS', 'NET', 'DDOG', 'MDB',
            'MRNA', 'BNTX', 'VRTX', 'REGN', 'GILD',
            'TSLA', 'RIVN', 'LCID',
            'SQ', 'COIN', 'SOFI',
            'SHOP', 'MELI'
        ]

    results = []
    total_entries_attempted = 0
    total_entries_made = 0

    risk_tier_counts = {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0}

    print("\n📊 Backtesting v6 RISK-ADAPTIVE...\n")

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start='2024-05-01', end=end_date)

            if len(hist) < 50 + max_hold_days:
                print(f"Processing {symbol}... ❌ Insufficient data")
                continue

            sector_regime = get_sector_regime(symbol)
            entries_made = 0

            for i in range(50, len(hist) - max_hold_days, entry_interval_days):
                total_entries_attempted += 1

                entry_date = hist.index[i]
                hist_at_entry = hist.iloc[:i+1]

                score_data = calculate_6layer_score_v2(hist_at_entry, ticker, symbol)

                if not score_data:
                    continue

                # Entry criteria (same as v5)
                should_enter, reason = should_enter_trade_v2(
                    score_data, sector_regime,
                    min_score=5.0, min_confidence=3.5, allow_sideways=True
                )

                if not should_enter:
                    continue

                # Calculate volatility (ATR)
                atr, atr_pct = calculate_atr(hist_at_entry)
                if not atr_pct:
                    atr_pct = 2.0  # Default if can't calculate

                # Get momentum score
                momentum_score = score_data['layer_scores'].get('momentum', 5.0)

                # ADAPTIVE: Determine risk profile for THIS specific entry
                risk_tier, target_pct, stop_pct, risk_desc = determine_risk_profile(
                    score_data, atr_pct, momentum_score
                )

                risk_tier_counts[risk_tier] += 1

                total_entries_made += 1
                entries_made += 1

                entry_idx = i
                entry_price = hist['Close'].iloc[entry_idx]

                max_gain = 0
                exit_price = None
                exit_reason = None
                exit_day = None

                for day in range(1, max_hold_days + 1):
                    if entry_idx + day >= len(hist):
                        exit_price = hist['Close'].iloc[-1]
                        exit_reason = 'MAX_HOLD'
                        exit_day = day
                        break

                    current_price = hist['Close'].iloc[entry_idx + day]
                    gain_pct = (current_price - entry_price) / entry_price * 100

                    max_gain = max(max_gain, gain_pct)
                    drawdown = gain_pct - max_gain

                    # Priority 1: ADAPTIVE TARGET (varies per trade!)
                    if gain_pct >= target_pct:
                        exit_price = current_price
                        exit_reason = f'TARGET_{risk_tier}'
                        exit_day = day
                        break

                    # Priority 2: ADAPTIVE HARD STOP (varies per trade!)
                    if gain_pct <= stop_pct:
                        exit_price = current_price
                        exit_reason = f'STOP_{risk_tier}'
                        exit_day = day
                        break

                    # v6: ADAPTIVE Smart Exits
                    if day >= 2:
                        current_idx = entry_idx + day
                        hist_data = hist

                        # HIGH RISK: More aggressive exits
                        if risk_tier == 'HIGH':
                            # Gap down (aggressive)
                            if day >= 1:
                                current_open = hist_data['Open'].iloc[current_idx]
                                prev_close = hist_data['Close'].iloc[current_idx - 1]
                                gap_pct = (current_open - prev_close) / prev_close * 100
                                if gap_pct < -1.0 and gain_pct < -0.5:
                                    exit_price = current_price
                                    exit_reason = 'SMART_GAP_DOWN_HIGH'
                                    exit_day = day
                                    break

                            # Breaking down (aggressive)
                            if day >= 2:
                                prev_price = hist_data['Close'].iloc[current_idx - 1]
                                daily_change = (current_price - prev_price) / prev_price * 100
                                if daily_change < -1.2 and gain_pct < 0:
                                    exit_price = current_price
                                    exit_reason = 'SMART_BREAKING_HIGH'
                                    exit_day = day
                                    break

                        # MEDIUM RISK: Normal exits (same as v5)
                        elif risk_tier == 'MEDIUM':
                            # Gap down
                            if day >= 1:
                                current_open = hist_data['Open'].iloc[current_idx]
                                prev_close = hist_data['Close'].iloc[current_idx - 1]
                                gap_pct = (current_open - prev_close) / prev_close * 100
                                if gap_pct < -1.5 and gain_pct < -1.0:
                                    exit_price = current_price
                                    exit_reason = 'SMART_GAP_DOWN_MED'
                                    exit_day = day
                                    break

                            # Breaking down
                            if day >= 2:
                                prev_price = hist_data['Close'].iloc[current_idx - 1]
                                daily_change = (current_price - prev_price) / prev_price * 100
                                if daily_change < -1.5 and gain_pct < -0.5:
                                    exit_price = current_price
                                    exit_reason = 'SMART_BREAKING_MED'
                                    exit_day = day
                                    break

                        # LOW RISK: More patient exits (give room to run)
                        else:  # LOW
                            # Gap down (less aggressive)
                            if day >= 1:
                                current_open = hist_data['Open'].iloc[current_idx]
                                prev_close = hist_data['Close'].iloc[current_idx - 1]
                                gap_pct = (current_open - prev_close) / prev_close * 100
                                if gap_pct < -2.5 and gain_pct < -1.5:
                                    exit_price = current_price
                                    exit_reason = 'SMART_GAP_DOWN_LOW'
                                    exit_day = day
                                    break

                            # Breaking down (patient)
                            if day >= 2:
                                prev_price = hist_data['Close'].iloc[current_idx - 1]
                                daily_change = (current_price - prev_price) / prev_price * 100
                                if daily_change < -2.0 and gain_pct < -1.0:
                                    exit_price = current_price
                                    exit_reason = 'SMART_BREAKING_LOW'
                                    exit_day = day
                                    break

                        # Common smart signals (all tiers)

                        # Momentum Reversal
                        reversal, reversal_severity = calculate_momentum_reversal(
                            hist_data, entry_idx, current_idx
                        )
                        if reversal and reversal_severity > 5.0 and gain_pct < 1.0:
                            exit_price = current_price
                            exit_reason = 'SMART_MOMENTUM_REV'
                            exit_day = day
                            break

                        # Failed Pump
                        if detect_failed_pump(hist_data, entry_idx, current_idx, entry_price):
                            exit_price = current_price
                            exit_reason = 'SMART_FAILED_PUMP'
                            exit_day = day
                            break

                        # SMA20 Break (only if losing)
                        if gain_pct < -1.0:
                            prices_for_sma = hist_data['Close'].iloc[:current_idx+1].values
                            sma20 = calculate_sma(prices_for_sma, period=20)
                            if sma20 and current_price < sma20:
                                distance_pct = (current_price - sma20) / sma20 * 100
                                if distance_pct < -1.0:
                                    exit_price = current_price
                                    exit_reason = 'SMART_SMA20_BREAK'
                                    exit_day = day
                                    break

                    # Adaptive Trailing Stop
                    trailing_threshold = -3.0 if risk_tier == 'HIGH' else -3.5 if risk_tier == 'MEDIUM' else -4.0
                    if drawdown < trailing_threshold:
                        exit_price = current_price
                        exit_reason = f'TRAILING_{risk_tier}'
                        exit_day = day
                        break

                # Fallback MAX_HOLD
                if not exit_price and entry_idx + max_hold_days < len(hist):
                    exit_price = hist['Close'].iloc[entry_idx + max_hold_days]
                    exit_reason = 'MAX_HOLD'
                    exit_day = max_hold_days

                # Record result
                if exit_price:
                    final_gain = (exit_price - entry_price) / entry_price * 100
                    results.append({
                        'symbol': symbol,
                        'entry_date': entry_date,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'exit_reason': exit_reason,
                        'exit_day': exit_day,
                        'gain_pct': final_gain,
                        'is_winner': final_gain >= target_pct,
                        'risk_tier': risk_tier,
                        'target_pct': target_pct,
                        'stop_pct': stop_pct,
                        'atr_pct': atr_pct,
                        'confidence': score_data.get('confidence', 0)
                    })

            print(f"Processing {symbol}... ✅ {entries_made} entries")

        except Exception as e:
            print(f"Processing {symbol}... ❌ {str(e)}")

    # Analysis
    if not results:
        print("\n❌ No trades found!")
        return

    df = pd.DataFrame(results)

    winners = df[df['is_winner'] == True]
    losers = df[df['is_winner'] == False]

    print("\n" + "="*80)
    print("📊 RESULTS v6 (RISK-ADAPTIVE)")
    print("="*80)
    print(f"\nTotal Trades: {len(df)}")
    print(f"Winners: {len(winners)} ({len(winners)/len(df)*100:.1f}%)")
    print(f"Losers: {len(losers)} ({len(losers)/len(df)*100:.1f}%)")
    print(f"\nEntry Success: {total_entries_made}/{total_entries_attempted} ({total_entries_made/total_entries_attempted*100:.1f}%)")

    # Risk tier distribution
    print("\n" + "="*80)
    print("🎲 RISK TIER DISTRIBUTION")
    print("="*80)
    print()

    for tier in ['LOW', 'MEDIUM', 'HIGH']:
        tier_trades = df[df['risk_tier'] == tier]
        if len(tier_trades) > 0:
            tier_winners = tier_trades[tier_trades['is_winner'] == True]
            win_rate = len(tier_winners) / len(tier_trades) * 100
            avg_gain = tier_trades['gain_pct'].mean()
            avg_target = tier_trades['target_pct'].mean()
            avg_stop = tier_trades['stop_pct'].mean()

            print(f"{tier:8} | {len(tier_trades):3} trades | Win: {win_rate:5.1f}% | Avg: {avg_gain:+6.2f}% | Target: {avg_target:4.1f}% | Stop: {avg_stop:5.1f}%")

    # Exit reasons
    print("\n" + "="*80)
    print("🚪 EXIT REASONS")
    print("="*80)
    print()

    for reason in sorted(df['exit_reason'].unique()):
        trades = df[df['exit_reason'] == reason]
        count = len(trades)
        pct = count / len(df) * 100
        avg_gain = trades['gain_pct'].mean()
        avg_day = trades['exit_day'].mean()

        emoji = '🎯' if 'TARGET' in reason else '⚠️' if 'STOP' in reason or 'TRAILING' in reason else '🧠'
        print(f"{emoji} {reason:28} | {count:3} ({pct:5.1f}%) | Avg: {avg_gain:+6.2f}% | Day: {avg_day:4.1f}")

    # Performance
    print("\n" + "="*80)
    print("💰 PERFORMANCE")
    print("="*80)
    print()

    avg_win = winners['gain_pct'].mean() if len(winners) > 0 else 0
    avg_loss = losers['gain_pct'].mean() if len(losers) > 0 else 0

    print(f"Average Win:   {avg_win:+.2f}%")
    print(f"Average Loss:  {avg_loss:+.2f}%")
    print(f"Best Win:      {df['gain_pct'].max():+.2f}%")
    print(f"Worst Loss:    {df['gain_pct'].min():+.2f}%")
    print()

    if avg_loss != 0:
        rr_ratio = abs(avg_win / avg_loss)
        print(f"Reward:Risk Ratio: {rr_ratio:.2f}:1")
    print()

    win_rate = len(winners) / len(df)
    expected_value = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
    print(f"Expected Value: {expected_value:+.2f}%")

    # Net profit
    print("\n" + "="*80)
    print("💵 NET PROFIT (100 Trades × $1000)")
    print("="*80)
    print()

    scale = 100 / len(df)
    winners_count = int(len(winners) * scale)
    losers_count = 100 - winners_count

    winners_profit = winners_count * 10 * avg_win
    losers_loss = losers_count * 10 * avg_loss
    net = winners_profit + losers_loss

    print(f"Winners: {winners_count} trades → ${winners_profit:,.2f}")
    print(f"Losers:  {losers_count} trades → ${losers_loss:,.2f}")
    print(f"NET PROFIT: ${net:,.2f}")
    print()

    if winners_profit > 0:
        loss_impact = abs(losers_loss) / winners_profit * 100
        print(f"Loss Impact: {loss_impact:.1f}% of wins")

    # Comparison
    print("\n" + "="*80)
    print("📊 COMPARISON: v2 → v5 → v6")
    print("="*80)
    print()

    print(f"{'Metric':<25} | {'v2 (Base)':<12} | {'v5 (Smart)':<12} | {'v6 (Adaptive)':<15} | {'Target':<15} | {'Status':<10}")
    print("-" * 105)

    win_status = "✅" if win_rate * 100 > 40 else "❌"
    print(f"{'Win Rate':<25} | {37.6:<12.1f} | {39.6:<12.1f} | {win_rate*100:<15.1f} | {'> 40%':<15} | {win_status:<10}")

    loss_status = "✅" if -3.0 <= avg_loss <= -2.5 else "⚠️"
    print(f"{'Avg Loss':<25} | {-3.76:<12.2f} | {-2.98:<12.2f} | {avg_loss:<15.2f} | {'-2.5 to -3.0':<15} | {loss_status:<10}")

    if winners_profit > 0:
        impact_status = "✅" if loss_impact < 60 else "❌"
        print(f"{'Loss Impact':<25} | {82.7:<12.1f} | {67.1:<12.1f} | {loss_impact:<15.1f} | {'< 60%':<15} | {impact_status:<10}")

    if avg_loss != 0:
        rr_status = "✅" if rr_ratio >= 1.5 else "❌"
        print(f"{'R:R Ratio':<25} | {2.03:<12.2f} | {2.33:<12.2f} | {rr_ratio:<15.2f} | {'>= 1.5':<15} | {rr_status:<10}")

    profit_status = "✅" if net > 700 else "❌"
    print(f"{'Net Profit':<25} | {'$488':<12} | {'$890':<12} | ${net:<14,.0f} | {'> $700':<15} | {profit_status:<10}")

    print("\n" + "="*80)
    print("🎯 VERDICT v6")
    print("="*80)
    print()

    targets_met = 0
    total_targets = 4

    if win_rate * 100 > 40:
        print(f"✅ Win Rate: {win_rate*100:.1f}% (target > 40%)")
        targets_met += 1
    else:
        print(f"❌ Win Rate: {win_rate*100:.1f}% (target > 40%)")

    if winners_profit > 0 and loss_impact < 60:
        print(f"✅ Loss Impact: {loss_impact:.1f}% (target < 60%)")
        targets_met += 1
    else:
        if winners_profit > 0:
            print(f"❌ Loss Impact: {loss_impact:.1f}% (target < 60%)")

    if -3.0 <= avg_loss <= -2.5:
        print(f"✅ Avg Loss: {avg_loss:.2f}% (target -2.5 to -3.0%)")
        targets_met += 1
    else:
        print(f"⚠️  Avg Loss: {avg_loss:.2f}% (target -2.5 to -3.0%)")

    if net > 700:
        print(f"✅ Net Profit: ${net:.0f} (target > $700)")
        targets_met += 1
    else:
        print(f"❌ Net Profit: ${net:.0f} (target > $700)")

    print()
    print(f"📊 Targets Met: {targets_met}/{total_targets}")
    print()

    return df


if __name__ == '__main__':
    print("=" * 80)
    print("BACKTEST v6: RISK-ADAPTIVE SYSTEM")
    print("=" * 80)
    print()
    print("Innovation: ปรับ stop/target ให้เหมาะกับแต่ละ trade!")
    print()
    print("Risk Tiers:")
    print("  🟢 LOW RISK (High confidence + Low volatility)")
    print("     - Target: 5.0%, Stop: -4.5%, Patient exits")
    print()
    print("  🟡 MEDIUM RISK (Medium confidence + volatility)")
    print("     - Target: 4.0%, Stop: -3.5%, Normal exits")
    print()
    print("  🔴 HIGH RISK (Low confidence + High volatility)")
    print("     - Target: 3.0%, Stop: -3.0%, Aggressive exits")
    print()
    print("Benefits:")
    print("  ✅ High confidence trades get more room to run")
    print("  ✅ Risky trades exit faster (less loss)")
    print("  ✅ Targets adapt to each stock's potential")
    print()

    backtest_v6_risk_adaptive()
