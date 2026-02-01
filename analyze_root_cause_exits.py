#!/usr/bin/env python3
"""
ROOT CAUSE Analysis: ทำไมหุ้นถึงแพ้? หา SIGNALS ที่บอกล่วงหน้า
ไม่ใช่แค่ตั้ง Time Stop แบบไม่มีเหตุผล
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np

def analyze_losing_trades_root_cause():
    """
    วิเคราะห์ว่าหุ้นที่แพ้มี SIGNALS อะไรบ้าง
    - Volume แห้ง?
    - ทะลุ support?
    - Momentum หาย?
    """

    print("=" * 80)
    print("ROOT CAUSE ANALYSIS: Why Do Trades Fail?")
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
    start_date = end_date - timedelta(days=30 * 6)

    # Collect losing trades with technical signals
    losing_trades = []
    winning_trades = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date - timedelta(days=30), end=end_date)

            if hist.empty or len(hist) < 60:
                continue

            # Calculate technical indicators
            hist['SMA_20'] = hist['Close'].rolling(20).mean()
            hist['Volume_MA'] = hist['Volume'].rolling(20).mean()
            hist['RSI'] = calculate_rsi(hist['Close'], 14)

            for i in range(30, len(hist) - 30, 7):
                entry_date = hist.index[i]
                entry_price = hist['Close'].iloc[i]
                entry_volume = hist['Volume'].iloc[i]
                entry_volume_ma = hist['Volume_MA'].iloc[i]
                entry_sma20 = hist['SMA_20'].iloc[i]

                # Track for 30 days
                hit_target = False
                signals_on_entry = {}
                signals_before_failure = {}

                # Entry signals
                signals_on_entry['above_sma20'] = entry_price > entry_sma20
                signals_on_entry['volume_ratio'] = entry_volume / entry_volume_ma if entry_volume_ma > 0 else 1

                max_gain = 0
                failure_day = None
                failure_signals = {}

                for day in range(1, min(31, len(hist) - i)):
                    current_price = hist['Close'].iloc[i + day]
                    current_volume = hist['Volume'].iloc[i + day]
                    current_volume_ma = hist['Volume_MA'].iloc[i + day]
                    current_sma20 = hist['SMA_20'].iloc[i + day]
                    current_rsi = hist['RSI'].iloc[i + day]

                    gain_pct = ((current_price - entry_price) / entry_price) * 100

                    if gain_pct > max_gain:
                        max_gain = gain_pct

                    # Hit target
                    if gain_pct >= 5.0:
                        hit_target = True
                        break

                    # Analyze signals during holding period
                    # Signal 1: Breaking below SMA20
                    if current_price < current_sma20 and not failure_signals.get('broke_sma20'):
                        failure_signals['broke_sma20'] = day
                        failure_signals['price_vs_sma20'] = ((current_price - current_sma20) / current_sma20) * 100

                    # Signal 2: Volume drying up
                    volume_ratio = current_volume / current_volume_ma if current_volume_ma > 0 else 1
                    if volume_ratio < 0.5 and day >= 5:
                        if not failure_signals.get('volume_dry'):
                            failure_signals['volume_dry'] = day

                    # Signal 3: RSI falling below 40
                    if current_rsi < 40 and not failure_signals.get('weak_rsi'):
                        failure_signals['weak_rsi'] = day
                        failure_signals['rsi_value'] = current_rsi

                    # Signal 4: Lower lows (downtrend)
                    if day >= 5:
                        recent_low = hist['Low'].iloc[i+day-5:i+day+1].min()
                        if recent_low < hist['Low'].iloc[i:i+5].min():
                            if not failure_signals.get('lower_lows'):
                                failure_signals['lower_lows'] = day

                    # Signal 5: Failed breakout (hit 3%+ but reversed)
                    if max_gain >= 3.0 and gain_pct < 1.0 and not failure_signals.get('failed_breakout'):
                        failure_signals['failed_breakout'] = day
                        failure_signals['peak_before_fail'] = max_gain

                # Final outcome
                final_price = hist['Close'].iloc[i + min(30, len(hist) - i - 1)]
                final_return = ((final_price - entry_price) / entry_price) * 100

                trade = {
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'return_pct': final_return,
                    'max_gain': max_gain,
                    'hit_target': hit_target,
                    'entry_signals': signals_on_entry,
                    'failure_signals': failure_signals,
                    'days_held': min(30, len(hist) - i - 1)
                }

                if hit_target:
                    winning_trades.append(trade)
                else:
                    losing_trades.append(trade)

        except Exception as e:
            continue

    # Analysis
    print(f"Total Losing Trades: {len(losing_trades)}")
    print(f"Total Winning Trades: {len(winning_trades)}")
    print()

    # Analyze failure signals
    print("=" * 80)
    print("🔍 FAILURE SIGNALS ANALYSIS")
    print("=" * 80)
    print()

    # Signal 1: Breaking SMA20
    broke_sma20_losers = [t for t in losing_trades if 'broke_sma20' in t['failure_signals']]
    print(f"1. Breaking Below SMA20:")
    print(f"   Losers with signal: {len(broke_sma20_losers)}/{len(losing_trades)} ({len(broke_sma20_losers)/len(losing_trades)*100:.1f}%)")

    if broke_sma20_losers:
        avg_day = np.mean([t['failure_signals']['broke_sma20'] for t in broke_sma20_losers])
        avg_return = np.mean([t['return_pct'] for t in broke_sma20_losers])
        print(f"   Average day of break: {avg_day:.0f}")
        print(f"   Average final return: {avg_return:+.2f}%")
        print(f"   → EXIT SIGNAL: ทะลุลง SMA20 = แนวโน้มเปลี่ยน!")

    print()

    # Signal 2: Volume drying up
    volume_dry_losers = [t for t in losing_trades if 'volume_dry' in t['failure_signals']]
    print(f"2. Volume Drying Up (< 50% of MA):")
    print(f"   Losers with signal: {len(volume_dry_losers)}/{len(losing_trades)} ({len(volume_dry_losers)/len(losing_trades)*100:.1f}%)")

    if volume_dry_losers:
        avg_day = np.mean([t['failure_signals']['volume_dry'] for t in volume_dry_losers])
        avg_return = np.mean([t['return_pct'] for t in volume_dry_losers])
        print(f"   Average day detected: {avg_day:.0f}")
        print(f"   Average final return: {avg_return:+.2f}%")
        print(f"   → EXIT SIGNAL: Volume หาย = ไม่มีคนสนใจ!")

    print()

    # Signal 3: Weak RSI
    weak_rsi_losers = [t for t in losing_trades if 'weak_rsi' in t['failure_signals']]
    print(f"3. Weak RSI (< 40):")
    print(f"   Losers with signal: {len(weak_rsi_losers)}/{len(losing_trades)} ({len(weak_rsi_losers)/len(losing_trades)*100:.1f}%)")

    if weak_rsi_losers:
        avg_day = np.mean([t['failure_signals']['weak_rsi'] for t in weak_rsi_losers])
        avg_rsi = np.mean([t['failure_signals']['rsi_value'] for t in weak_rsi_losers])
        avg_return = np.mean([t['return_pct'] for t in weak_rsi_losers])
        print(f"   Average day detected: {avg_day:.0f}")
        print(f"   Average RSI: {avg_rsi:.1f}")
        print(f"   Average final return: {avg_return:+.2f}%")
        print(f"   → EXIT SIGNAL: RSI อ่อนแอ = momentum หาย!")

    print()

    # Signal 4: Lower lows (downtrend)
    lower_lows_losers = [t for t in losing_trades if 'lower_lows' in t['failure_signals']]
    print(f"4. Making Lower Lows (Downtrend):")
    print(f"   Losers with signal: {len(lower_lows_losers)}/{len(losing_trades)} ({len(lower_lows_losers)/len(losing_trades)*100:.1f}%)")

    if lower_lows_losers:
        avg_day = np.mean([t['failure_signals']['lower_lows'] for t in lower_lows_losers])
        avg_return = np.mean([t['return_pct'] for t in lower_lows_losers])
        print(f"   Average day detected: {avg_day:.0f}")
        print(f"   Average final return: {avg_return:+.2f}%")
        print(f"   → EXIT SIGNAL: Lower lows = downtrend เริ่มแล้ว!")

    print()

    # Signal 5: Failed breakout
    failed_breakout_losers = [t for t in losing_trades if 'failed_breakout' in t['failure_signals']]
    print(f"5. Failed Breakout (Hit 3%+ then reversed):")
    print(f"   Losers with signal: {len(failed_breakout_losers)}/{len(losing_trades)} ({len(failed_breakout_losers)/len(losing_trades)*100:.1f}%)")

    if failed_breakout_losers:
        avg_day = np.mean([t['failure_signals']['failed_breakout'] for t in failed_breakout_losers])
        avg_peak = np.mean([t['failure_signals']['peak_before_fail'] for t in failed_breakout_losers])
        avg_return = np.mean([t['return_pct'] for t in failed_breakout_losers])
        print(f"   Average day detected: {avg_day:.0f}")
        print(f"   Average peak before fail: {avg_peak:.1f}%")
        print(f"   Average final return: {avg_return:+.2f}%")
        print(f"   → EXIT SIGNAL: Breakout ล้มเหลว = ออกก่อนแย่!")

    print()

    # Combined signals
    print("=" * 80)
    print("🎯 SMART EXIT RULES (Signal-Based)")
    print("=" * 80)
    print()

    print("แทนที่จะใช้:")
    print("  ❌ Time Stop: 10 วัน ถ้า < 2% (ไม่มีเหตุผล)")
    print("  ❌ Partial Exit: Peak 4% → 3% (arbitrary)")
    print()

    print("ใช้ EXIT SIGNALS แทน:")
    print()
    print("1. 📉 Breaking SMA20 (ทะลุแนวรับ)")
    print(f"   → {len(broke_sma20_losers)/len(losing_trades)*100:.0f}% ของ losers มี signal นี้")
    print(f"   → Exit เมื่อ: Close < SMA20 AND แนวโน้มลง")
    print()

    print("2. 📊 Volume Drying (ไม่มีคนสนใจ)")
    print(f"   → {len(volume_dry_losers)/len(losing_trades)*100:.0f}% ของ losers มี signal นี้")
    print(f"   → Exit เมื่อ: Volume < 50% of MA20 เป็นเวลา 3 วันติด")
    print()

    print("3. 💪 Weak Momentum (RSI < 40)")
    print(f"   → {len(weak_rsi_losers)/len(losing_trades)*100:.0f}% ของ losers มี signal นี้")
    print(f"   → Exit เมื่อ: RSI < 40 AND ลดลงต่อเนื่อง")
    print()

    print("4. 📈 Failed Breakout (ขึ้นแล้วกลับ)")
    print(f"   → {len(failed_breakout_losers)/len(losing_trades)*100:.0f}% ของ losers มี signal นี้")
    print(f"   → Exit เมื่อ: Peak 3%+ แล้วกลับมาต่ำกว่า entry +1%")
    print()

    print("5. 📉 Lower Lows (Downtrend ชัดเจน)")
    print(f"   → {len(lower_lows_losers)/len(losing_trades)*100:.0f}% ของ losers มี signal นี้")
    print(f"   → Exit เมื่อ: ทำ lower low 2 ครั้งติด")
    print()

    # Coverage analysis
    print("=" * 80)
    print("📊 SIGNAL COVERAGE (How many losers would we catch?)")
    print("=" * 80)
    print()

    # Count how many losers have at least one signal
    losers_with_any_signal = [
        t for t in losing_trades
        if any(k in t['failure_signals'] for k in ['broke_sma20', 'volume_dry', 'weak_rsi', 'lower_lows', 'failed_breakout'])
    ]

    print(f"Losers with at least 1 signal: {len(losers_with_any_signal)}/{len(losing_trades)} ({len(losers_with_any_signal)/len(losing_trades)*100:.1f}%)")
    print()

    if losers_with_any_signal:
        avg_return_caught = np.mean([t['return_pct'] for t in losers_with_any_signal])
        print(f"Average return of caught losers: {avg_return_caught:+.2f}%")

    # Losers with NO signals (would still hold)
    losers_no_signals = [t for t in losing_trades if t not in losers_with_any_signal]
    if losers_no_signals:
        avg_return_missed = np.mean([t['return_pct'] for t in losers_no_signals])
        print(f"Losers we'd miss (no signals): {len(losers_no_signals)} ({len(losers_no_signals)/len(losing_trades)*100:.1f}%)")
        print(f"Average return of missed losers: {avg_return_missed:+.2f}%")

    print()

    # Final recommendation
    print("=" * 80)
    print("💡 RECOMMENDATION: SIGNAL-BASED EXITS")
    print("=" * 80)
    print()

    print("Portfolio Manager v3.5 (SIGNAL-BASED):")
    print()
    print("Core Exits:")
    print("  1. Target: +5% (take profit)")
    print("  2. Hard Stop: -6% (protect capital)")
    print("  3. Max Hold: 30 days (fallback)")
    print()

    print("SMART Exits (Signal-Based): 🆕")
    print("  4. Breaking SMA20: Close < SMA20 for 2 days")
    print("  5. Volume Dry: Volume < 50% MA for 3 days")
    print("  6. Weak RSI: RSI < 35 (very weak)")
    print("  7. Failed Breakout: Peak 3%+ → < entry +0.5%")
    print()

    print("ทำไมดีกว่า Time Stop/Partial Exit?")
    print(f"  ✅ มี REASON ชัดเจน (มี signal บอก)")
    print(f"  ✅ Coverage สูง ({len(losers_with_any_signal)/len(losing_trades)*100:.0f}% ของ losers)")
    print(f"  ✅ ไม่ exit ตาม time แบบไร้สาเหตุ")
    print(f"  ✅ ถ้าหุ้นยัง strong (above SMA, volume ok) → ถือต่อได้")
    print()


def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


if __name__ == "__main__":
    analyze_losing_trades_root_cause()
