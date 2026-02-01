#!/usr/bin/env python3
"""
v5: SMART SELECTIVE EXITS
=========================

v4 ปัญหา: Cut everything aggressively → ฆ่า slow starters
v5 แก้: ใช้ signals ที่ฉลาดขึ้น แยกแยะ "slow starter" vs "real loser"

SMART EXIT SIGNALS:
1. Momentum Reversal: ราคาขึ้นแล้วกลับลง (real weakness)
2. Volume Collapse + Loss: Volume แห้ง + ขาดทุน = ไม่มีคนสน
3. Break Below Entry + Weak: ทะลุจุดซื้อลงมา + แรงขายสูง
4. Sector Weakness: Sector แย่ + stock แย่ = double trouble
5. Failed Pump: Day 1-2 ทะยานแล้วร่วงทันที

Goal:
- Win Rate: 40-45%
- Avg Loss: -2.5% to -3.0%
- Loss Impact: < 60%
- Net Profit: > $700
"""

import sys
import os
sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer')

from backtest_complete_system_v2 import (
    calculate_sma, calculate_rsi, check_lower_lows,
    get_real_fundamentals, get_sector_regime,
    backtest_complete_system_v2
)
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np

def calculate_momentum_reversal(hist_data, entry_idx, current_idx):
    """
    ตรวจจับ Momentum Reversal: ราคาขึ้นแล้วกลับลง

    Returns:
        reversal_detected: bool
        severity: float (0-10, higher = worse)
    """
    if current_idx - entry_idx < 2:
        return False, 0.0

    # ดูราคา 3 วันล่าสุด
    recent_closes = hist_data['Close'].iloc[max(0, current_idx-2):current_idx+1].values

    if len(recent_closes) < 3:
        return False, 0.0

    # Reversal pattern: วันที่ 1 ขึ้น, วันที่ 2-3 ลง
    day1_gain = (recent_closes[1] - recent_closes[0]) / recent_closes[0] * 100
    day2_loss = (recent_closes[2] - recent_closes[1]) / recent_closes[1] * 100

    # ถ้าวันแรกขึ้น > 1% แล้ววันถัดไปลง > 1.5% = reversal
    if day1_gain > 1.0 and day2_loss < -1.5:
        severity = abs(day2_loss) / day1_gain * 10
        return True, min(severity, 10.0)

    return False, 0.0


def calculate_volume_health(hist_data, entry_idx, current_idx, lookback=10):
    """
    ตรวจสุขภาพ Volume: ดูว่า volume กำลังแห้งหรือไม่

    Returns:
        is_collapsing: bool
        volume_ratio: float (current / avg)
    """
    if current_idx < lookback:
        return False, 1.0

    # Volume เฉลี่ย 10 วันก่อนหน้า
    avg_volume = hist_data['Volume'].iloc[max(0, current_idx-lookback):current_idx].mean()

    # Volume วันนี้
    current_volume = hist_data['Volume'].iloc[current_idx]

    if avg_volume == 0:
        return False, 1.0

    volume_ratio = current_volume / avg_volume

    # Volume < 50% ของ avg = collapsing
    is_collapsing = volume_ratio < 0.5

    return is_collapsing, volume_ratio


def check_break_below_entry(entry_price, current_price, volume_ratio):
    """
    ตรวจจับการทะลุจุดซื้อลงมา + แรงขายสูง

    Returns:
        is_broken: bool
        severity: float (0-10)
    """
    # ทะลุจุดซื้อลงมา > 1%
    loss_pct = (current_price - entry_price) / entry_price * 100

    if loss_pct < -1.0:
        # ถ้า volume สูง (> 1.5x) = แรงขายจริงๆ
        if volume_ratio > 1.5:
            severity = abs(loss_pct) * volume_ratio
            return True, min(severity, 10.0)

    return False, 0.0


def detect_failed_pump(hist_data, entry_idx, current_idx, entry_price):
    """
    ตรวจจับ Failed Pump: Day 1-2 ทะยานแล้วร่วงทันที

    Pattern: วันแรกทะยาน > 3%, แล้ววันที่ 2-3 ร่วงกลับต่ำกว่าจุดซื้อ

    Returns:
        is_failed_pump: bool
    """
    days_held = current_idx - entry_idx

    if days_held < 2 or days_held > 3:
        return False

    # ดูราคาสูงสุดหลังซื้อ
    peak_price = hist_data['High'].iloc[entry_idx:current_idx+1].max()
    current_price = hist_data['Close'].iloc[current_idx]

    # คำนวณ peak gain
    peak_gain = (peak_price - entry_price) / entry_price * 100

    # คำนวณ current position vs entry
    current_vs_entry = (current_price - entry_price) / entry_price * 100

    # Failed pump: peak > 3% แต่ current < -0.5%
    if peak_gain > 3.0 and current_vs_entry < -0.5:
        return True

    return False


def backtest_v5_smart_exits(
    symbols=None,
    start_date='2024-06-01',
    end_date='2024-12-01',
    target_pct=4.0,  # Use 4% target (improves win rate to 46%)
    stop_loss_pct=-3.5,  # Tighter to account for price gapping
    max_hold_days=30,
    entry_interval_days=7
):
    """
    v5: Smart Selective Exits
    - ใช้ smart signals แทน blanket aggressive rules
    - แยกแยะ slow starters vs real losers
    """

    if symbols is None:
        symbols = [
            # Tech
            'NVDA', 'AMD', 'AVGO', 'QCOM', 'MU',
            'PLTR', 'SNOW', 'CRWD', 'ZS', 'NET', 'DDOG', 'MDB',
            # Biotech
            'MRNA', 'BNTX', 'VRTX', 'REGN', 'GILD',
            # EV
            'TSLA', 'RIVN', 'LCID',
            # Fintech
            'SQ', 'COIN', 'SOFI',
            # E-commerce
            'SHOP', 'MELI'
        ]

    results = []
    total_entries_attempted = 0
    total_entries_made = 0

    print("\n📊 Backtesting with SMART SELECTIVE EXITS...\n")

    from backtest_complete_system_v2 import calculate_6layer_score_v2, should_enter_trade_v2, get_sector_regime, check_entry_timing

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start='2024-05-01', end=end_date)

            if len(hist) < 50 + max_hold_days:
                print(f"Processing {symbol}... ❌ Insufficient data")
                continue

            # Get sector regime once per symbol
            sector_regime = get_sector_regime(symbol)

            entries_made = 0

            # Simulate weekly entry attempts (same as v2)
            for i in range(50, len(hist) - max_hold_days, entry_interval_days):
                total_entries_attempted += 1

                entry_date = hist.index[i]
                hist_at_entry = hist.iloc[:i+1]

                # Calculate 6-layer score with REAL data (same as v2)
                score_data = calculate_6layer_score_v2(hist_at_entry, ticker, symbol)

                if not score_data:
                    continue

                # Skip entry timing check to get more trades
                # (Smart exits will protect us from bad entries)

                # Check entry criteria (lowered to get more trades like original v2)
                should_enter, reason = should_enter_trade_v2(score_data, sector_regime, min_score=5.0, min_confidence=3.5, allow_sideways=True)

                if not should_enter:
                    continue

                # PASSED ALL FILTERS - Enter trade!
                total_entries_made += 1
                entries_made += 1

                entry_idx = i
                entry_price = hist['Close'].iloc[entry_idx]

                # Track position
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

                    # Priority 1: TARGET HIT
                    if gain_pct >= target_pct:
                        exit_price = current_price
                        exit_reason = 'TARGET_HIT'
                        exit_day = day
                        break

                    # Priority 2: HARD STOP
                    if gain_pct <= stop_loss_pct:
                        exit_price = current_price
                        exit_reason = 'HARD_STOP'
                        exit_day = day
                        break

                    # ========================================
                    # v5: SMART SELECTIVE EXITS (Day 2+)
                    # ========================================

                    if day >= 2:
                        current_idx = entry_idx + day
                        hist_data = hist

                        # SMART SIGNAL 0a: Gap Down Detection
                        # If stock opens >2% below yesterday's close and we're losing
                        if day >= 1:
                            current_open = hist_data['Open'].iloc[current_idx]
                            prev_close = hist_data['Close'].iloc[current_idx - 1]
                            gap_pct = (current_open - prev_close) / prev_close * 100
                            if gap_pct < -2.0 and gain_pct < -1.5:
                                exit_price = current_price
                                exit_reason = 'SMART_GAP_DOWN'
                                exit_day = day
                                break

                        # SMART SIGNAL 0b: Breaking Down Fast (catch before hard stop)
                        # If losing > -2.0% in a single day = exit immediately
                        if day >= 2:
                            prev_price = hist_data['Close'].iloc[current_idx - 1]
                            daily_change = (current_price - prev_price) / prev_price * 100
                            if daily_change < -2.0 and gain_pct < -0.5:
                                exit_price = current_price
                                exit_reason = 'SMART_BREAKING_DOWN'
                                exit_day = day
                                break

                        # SMART SIGNAL 1: Momentum Reversal
                        reversal, reversal_severity = calculate_momentum_reversal(
                            hist_data, entry_idx, current_idx
                        )
                        if reversal and reversal_severity > 5.0 and gain_pct < 1.0:
                            exit_price = current_price
                            exit_reason = 'SMART_MOMENTUM_REVERSAL'
                            exit_day = day
                            break

                        # SMART SIGNAL 2: Volume Collapse + Loss
                        vol_collapse, vol_ratio = calculate_volume_health(
                            hist_data, entry_idx, current_idx
                        )
                        if vol_collapse and gain_pct < -1.0:
                            exit_price = current_price
                            exit_reason = 'SMART_VOLUME_COLLAPSE'
                            exit_day = day
                            break

                        # SMART SIGNAL 3: Break Below Entry + High Volume
                        break_below, break_severity = check_break_below_entry(
                            entry_price, current_price, vol_ratio
                        )
                        if break_below and break_severity > 3.0:
                            exit_price = current_price
                            exit_reason = 'SMART_BREAK_ENTRY'
                            exit_day = day
                            break

                        # SMART SIGNAL 4: Failed Pump
                        if detect_failed_pump(hist_data, entry_idx, current_idx, entry_price):
                            exit_price = current_price
                            exit_reason = 'SMART_FAILED_PUMP'
                            exit_day = day
                            break

                        # SMART SIGNAL 5: SMA20 Break (from v4, but only if losing)
                        if gain_pct < 0:
                            prices_for_sma = hist_data['Close'].iloc[:current_idx+1].values
                            sma20 = calculate_sma(prices_for_sma, period=20)
                            if sma20 and current_price < sma20:
                                distance_pct = (current_price - sma20) / sma20 * 100
                                if distance_pct < -1.0:
                                    exit_price = current_price
                                    exit_reason = 'SMART_SMA20_BREAK'
                                    exit_day = day
                                    break

                        # SMART SIGNAL 6: Weak RSI (only if losing significantly)
                        if gain_pct < -2.0:
                            prices_for_rsi = hist_data['Close'].iloc[:current_idx+1].values
                            rsi = calculate_rsi(prices_for_rsi, period=14)
                            if rsi and rsi < 35:
                                exit_price = current_price
                                exit_reason = 'SMART_WEAK_RSI'
                                exit_day = day
                                break

                    # Priority 3: Trailing Stop (tighter from v4)
                    if drawdown < -4.0:
                        exit_price = current_price
                        exit_reason = 'TRAILING_STOP'
                        exit_day = day
                        break

                # If no exit condition met, hold to max days
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
                        'is_winner': final_gain >= target_pct
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
    print("📊 RESULTS v5 (SMART SELECTIVE EXITS)")
    print("="*80)
    print(f"\nTotal Trades: {len(df)}")
    print(f"Winners: {len(winners)} ({len(winners)/len(df)*100:.1f}%)")
    print(f"Losers: {len(losers)} ({len(losers)/len(df)*100:.1f}%)")
    print(f"\nEntry Success: {total_entries_made}/{total_entries_attempted} ({total_entries_made/total_entries_attempted*100:.1f}%)")

    # Exit reasons
    print("\n" + "="*80)
    print("🚪 EXIT REASONS")
    print("="*80)
    print()

    exit_stats = df.groupby('exit_reason').agg({
        'gain_pct': ['count', 'mean'],
        'exit_day': 'mean'
    }).round(2)

    exit_map = {
        'TARGET_HIT': '🎯',
        'HARD_STOP': '⚠️',
        'TRAILING_STOP': '⚠️',
        'SMART_MOMENTUM_REVERSAL': '🧠',
        'SMART_VOLUME_COLLAPSE': '🧠',
        'SMART_BREAK_ENTRY': '🧠',
        'SMART_FAILED_PUMP': '🧠',
        'SMART_SMA20_BREAK': '🧠',
        'SMART_WEAK_RSI': '🧠',
        'MAX_HOLD': '⏰'
    }

    for reason in sorted(df['exit_reason'].unique()):
        trades = df[df['exit_reason'] == reason]
        emoji = exit_map.get(reason, '📊')
        count = len(trades)
        pct = count / len(df) * 100
        avg_gain = trades['gain_pct'].mean()
        avg_day = trades['exit_day'].mean()

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
    print("📊 COMPARISON: v2 (5% base) → v4 (aggressive) → v5 (smart)")
    print("="*80)
    print()

    print(f"{'Metric':<25} | {'v2 (Base)':<15} | {'v4 (Aggressive)':<15} | {'v5 (Smart)':<15} | {'Target':<15}")
    print("-" * 110)
    print(f"{'Win Rate':<25} | {37.6:<15.1f} | {29.7:<15.1f} | {win_rate*100:<15.1f} | {'40-45%':<15}")
    print(f"{'Avg Loss':<25} | {-3.76:<15.2f} | {-2.31:<15.2f} | {avg_loss:<15.2f} | {'-2.5 to -3.0':<15}")

    if winners_profit > 0:
        print(f"{'Loss Impact':<25} | {82.7:<15.1f} | {86.1:<15.1f} | {loss_impact:<15.1f} | {'< 60%':<15}")

    if avg_loss != 0:
        print(f"{'R:R Ratio':<25} | {2.03:<15.2f} | {2.81:<15.2f} | {rr_ratio:<15.2f} | {'>= 1.5':<15}")

    print(f"{'Net Profit':<25} | {'$488':<15} | {'$262':<15} | ${net:<14,.0f} | {'> $700':<15}")

    print("\n" + "="*80)
    print("🎯 VERDICT")
    print("="*80)
    print()

    targets_met = []
    targets_missed = []

    if win_rate * 100 >= 40:
        targets_met.append(f"Win Rate: {win_rate*100:.1f}%")
    else:
        targets_missed.append(f"Win Rate: {win_rate*100:.1f}% (need 40-45%)")

    if -3.0 <= avg_loss <= -2.5:
        targets_met.append(f"Avg Loss: {avg_loss:.2f}%")
    else:
        targets_missed.append(f"Avg Loss: {avg_loss:.2f}% (need -2.5 to -3.0%)")

    if winners_profit > 0 and loss_impact < 60:
        targets_met.append(f"Loss Impact: {loss_impact:.1f}%")
    else:
        if winners_profit > 0:
            targets_missed.append(f"Loss Impact: {loss_impact:.1f}% (need < 60%)")

    if net > 700:
        targets_met.append(f"Net Profit: ${net:.0f}")
    else:
        targets_missed.append(f"Net Profit: ${net:.0f} (need > $700)")

    if targets_met:
        print("✅ Targets Met:")
        for t in targets_met:
            print(f"   - {t}")

    if targets_missed:
        print("\n❌ Needs Improvement:")
        for t in targets_missed:
            print(f"   - {t}")

    print()


if __name__ == '__main__':
    print("=" * 80)
    print("BACKTEST v5: SMART SELECTIVE EXITS")
    print("=" * 80)
    print()
    print("v4 Problem: Cut everything → killed slow starters")
    print("v5 Solution: Smart signals that identify REAL weakness")
    print()
    print("SMART EXIT SIGNALS:")
    print("  🧠 Momentum Reversal: ขึ้นแล้วกลับลง (real weakness)")
    print("  🧠 Volume Collapse: Volume แห้ง + ขาดทุน = ไม่มีคนสน")
    print("  🧠 Break Entry: ทะลุจุดซื้อ + แรงขายสูง")
    print("  🧠 Failed Pump: วันแรกทะยาน แล้วร่วงทันที")
    print("  🧠 SMA20 Break: เฉพาะตอนขาดทุน")
    print("  🧠 Weak RSI: เฉพาะตอนขาดทุนมาก (< -2%)")
    print()
    print("Target:")
    print("  - Win Rate: 40-45%")
    print("  - Avg Loss: -2.5% to -3.0%")
    print("  - Loss Impact: < 60%")
    print("  - Net Profit: > $700")
    print()

    backtest_v5_smart_exits()
