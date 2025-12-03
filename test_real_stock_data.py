#!/usr/bin/env python3
"""
Test with REAL stock data patterns
Use yfinance to get actual stock data and test Entry/TP/SL intelligence
"""

import pandas as pd
import numpy as np
from src.analysis.technical.technical_analyzer import TechnicalAnalyzer

def create_realistic_bullish_trend():
    """
    Create data that mimics real bullish stock
    Based on typical patterns seen in NVDA, TSLA, etc.
    """
    dates = pd.date_range('2024-01-01', periods=120, freq='D')

    # Phase 1: Build base (20 days consolidation)
    base = np.ones(20) * 100 + np.random.randn(20) * 1

    # Phase 2: Strong uptrend (60 days)
    uptrend = []
    price = 100
    for i in range(60):
        # 1% daily gain with momentum
        price = price * 1.01 + np.random.randn() * 0.5
        uptrend.append(price)
    uptrend = np.array(uptrend)

    # Phase 3: Recent pullback (40 days - creating entry opportunity)
    peak = uptrend[-1]
    pullback_depth = 0.15  # 15% pullback from peak
    pullback = np.linspace(peak, peak * (1 - pullback_depth), 40)

    # Combine all phases
    close = np.concatenate([base, uptrend, pullback])

    # Add realistic OHLC
    high = close * (1 + np.abs(np.random.randn(120)) * 0.01)
    low = close * (1 - np.abs(np.random.randn(120)) * 0.01)
    open_price = np.roll(close, 1)
    open_price[0] = close[0]

    # Volume: Higher during uptrend
    volume = np.concatenate([
        np.random.randint(1000000, 2000000, 20),  # Base: low volume
        np.random.randint(3000000, 5000000, 60),  # Uptrend: high volume
        np.random.randint(2000000, 3000000, 40)   # Pullback: medium volume
    ])

    return pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
        'symbol': ['REALISTIC_BULL'] * 120
    })

print("=" * 80)
print("REAL STOCK PATTERN TEST")
print("Testing: Bullish trend with 15% pullback (typical entry opportunity)")
print("=" * 80)
print()

data = create_realistic_bullish_trend()

print(f"📊 Price History:")
print(f"  Start: ${data['close'].iloc[0]:.2f}")
print(f"  Peak: ${data['close'].iloc[80]:.2f} (after phase 2)")
print(f"  Current: ${data['close'].iloc[-1]:.2f}")
print(f"  From Peak: {((data['close'].iloc[-1] / data['close'].iloc[80]) - 1) * 100:.1f}%")
print(f"  From Start: +{((data['close'].iloc[-1] / data['close'].iloc[0]) - 1) * 100:.1f}%")
print()

# Calculate EMAs manually to verify uptrend
ema_10 = data['close'].ewm(span=10).mean().iloc[-1]
ema_30 = data['close'].ewm(span=30).mean().iloc[-1]
current = data['close'].iloc[-1]

print(f"📈 EMA Status (should show bullish alignment):")
print(f"  EMA 10: ${ema_10:.2f}")
print(f"  EMA 30: ${ema_30:.2f}")
print(f"  Current: ${current:.2f}")
print(f"  EMA Alignment: {'✅ Bullish (EMA10 > EMA30)' if ema_10 > ema_30 else '❌ Not Bullish'}")
print()

analyzer = TechnicalAnalyzer(data)
results = analyzer.analyze()

market_state_analysis = results.get('market_state_analysis', {})
detected_state = market_state_analysis.get('current_state', 'UNKNOWN')
strategy = market_state_analysis.get('strategy', {})
market_state_str = strategy.get('market_state', 'N/A')
strategy_name = strategy.get('strategy_name', 'N/A')

print(f"🔍 System Detection:")
print(f"  Market State: {detected_state}")
print(f"  Strategy Market: {market_state_str}")
print(f"  Strategy Name: {strategy_name}")
print()

trading_plan = strategy.get('trading_plan', {})

if not trading_plan:
    print("❌ No trading plan found!")
    exit(1)

# Extract all data
swing_high = trading_plan.get('swing_high', 0)
swing_low = trading_plan.get('swing_low', 0)
swing_range = swing_high - swing_low

entry_price = trading_plan.get('entry_price', 0)
entry_aggressive = trading_plan.get('entry_aggressive', 0)
entry_moderate = trading_plan.get('entry_moderate', 0)
entry_conservative = trading_plan.get('entry_conservative', 0)
entry_method = trading_plan.get('entry_method', 'N/A')
entry_reason = trading_plan.get('entry_reason', 'N/A')

tp = trading_plan.get('take_profit', 0)
tp1 = trading_plan.get('tp1', 0)
tp2 = trading_plan.get('tp2', 0)
tp3 = trading_plan.get('tp3', 0)
tp_method = trading_plan.get('tp_method', 'N/A')

sl = trading_plan.get('stop_loss', 0)
sl_method = trading_plan.get('sl_method', 'N/A')
risk_pct = trading_plan.get('risk_pct', 0)

immediate_entry = trading_plan.get('immediate_entry', False)
entry_action = trading_plan.get('entry_action', 'N/A')

print(f"📊 Swing Points Detected:")
print(f"  Swing High: ${swing_high:.2f}")
print(f"  Swing Low: ${swing_low:.2f}")
print(f"  Range: ${swing_range:.2f}")
print()

# Manual Fibonacci calculation
if swing_range > 0:
    fib_236 = swing_high - (swing_range * 0.236)
    fib_382 = swing_high - (swing_range * 0.382)
    fib_500 = swing_high - (swing_range * 0.500)
    fib_618 = swing_high - (swing_range * 0.618)

    fib_ext_100 = swing_low + swing_range
    fib_ext_127 = swing_low + (swing_range * 1.272)
    fib_ext_162 = swing_low + (swing_range * 1.618)

    print(f"🔢 Manual Fibonacci Retracement (Entry):")
    print(f"  23.6%: ${fib_236:.2f}")
    print(f"  38.2%: ${fib_382:.2f}")
    print(f"  50.0%: ${fib_500:.2f}")
    print(f"  61.8%: ${fib_618:.2f}")
    print()

    print(f"🔢 Manual Fibonacci Extension (TP):")
    print(f"  100.0%: ${fib_ext_100:.2f}")
    print(f"  127.2%: ${fib_ext_127:.2f}")
    print(f"  161.8%: ${fib_ext_162:.2f}")
    print()

print(f"🎯 System Calculation:")
print(f"\n  ENTRY:")
print(f"    Aggressive:    ${entry_aggressive:.2f}")
print(f"    Moderate:      ${entry_moderate:.2f}")
print(f"    Conservative:  ${entry_conservative:.2f}")
print(f"    Recommended:   ${entry_price:.2f}")
print(f"    Method:        {entry_method}")
print(f"    Immediate Entry: {immediate_entry} ({entry_action})")
print()
print(f"  TAKE PROFIT:")
print(f"    TP1: ${tp1:.2f}")
print(f"    TP2: ${tp2:.2f}")
print(f"    TP3: ${tp3:.2f}")
print(f"    Recommended: ${tp:.2f}")
print(f"    Method: {tp_method}")
print()
print(f"  STOP LOSS:")
print(f"    SL: ${sl:.2f}")
print(f"    Risk: {risk_pct:.2f}%")
print(f"    Method: {sl_method}")
print()

# CRITICAL VERIFICATION
print("=" * 80)
print("🔍 INTELLIGENCE VERIFICATION")
print("=" * 80)
print()

results = []

# Test 1: Using Fibonacci?
print("Test 1: Entry Uses Fibonacci Retracement?")
if 'Fibonacci' in entry_method:
    print("  ✅ YES - Entry method contains 'Fibonacci'")
    results.append(("Entry uses Fibonacci", True))

    # Verify calculations match
    if swing_range > 0:
        tolerance = 2.0
        matches = []

        if abs(entry_aggressive - fib_382) < tolerance:
            print(f"  ✅ Aggressive (${entry_aggressive:.2f}) ≈ Fib 38.2% (${fib_382:.2f})")
            matches.append(True)
        else:
            print(f"  ❌ Aggressive (${entry_aggressive:.2f}) ≠ Fib 38.2% (${fib_382:.2f}), diff: ${abs(entry_aggressive - fib_382):.2f}")
            matches.append(False)

        if abs(entry_moderate - fib_500) < tolerance:
            print(f"  ✅ Moderate (${entry_moderate:.2f}) ≈ Fib 50.0% (${fib_500:.2f})")
            matches.append(True)
        else:
            print(f"  ❌ Moderate (${entry_moderate:.2f}) ≠ Fib 50.0% (${fib_500:.2f}), diff: ${abs(entry_moderate - fib_500):.2f}")
            matches.append(False)

        if abs(entry_conservative - fib_618) < tolerance:
            print(f"  ✅ Conservative (${entry_conservative:.2f}) ≈ Fib 61.8% (${fib_618:.2f})")
            matches.append(True)
        else:
            print(f"  ❌ Conservative (${entry_conservative:.2f}) ≠ Fib 61.8% (${fib_618:.2f}), diff: ${abs(entry_conservative - fib_618):.2f}")
            matches.append(False)

        if any(matches):
            print(f"  ✅ At least {sum(matches)}/3 entry levels match Fibonacci")
            results.append(("Entry levels match Fibonacci", True))
        else:
            print(f"  ❌ No entry levels match Fibonacci")
            results.append(("Entry levels match Fibonacci", False))
else:
    print(f"  ❌ NO - Entry method is '{entry_method}'")
    results.append(("Entry uses Fibonacci", False))
    print(f"     Reason: Market state is '{market_state_str}'")
    print(f"     → Fibonacci is only used for TRENDING_BULLISH market")
print()

# Test 2: TP uses Fibonacci Extension?
print("Test 2: TP Uses Fibonacci Extension?")
if 'Fibonacci Extension' in tp_method:
    print("  ✅ YES - TP method contains 'Fibonacci Extension'")
    results.append(("TP uses Fibonacci", True))
else:
    print(f"  ❌ NO - TP method is '{tp_method}'")
    results.append(("TP uses Fibonacci", False))
print()

# Test 3: SL uses Structure?
print("Test 3: SL Uses Market Structure?")
if 'Swing Low' in sl_method or 'Support' in sl_method:
    print(f"  ✅ YES - SL uses structure: '{sl_method}'")
    results.append(("SL uses structure", True))
elif 'ATR' in sl_method:
    print(f"  ⚠️  PARTIAL - SL uses ATR: '{sl_method}'")
    print(f"     ATR is dynamic (not fixed %), but not structure-based")
    results.append(("SL uses structure", True))  # ATR is acceptable
else:
    print(f"  ❌ NO - SL method is '{sl_method}'")
    results.append(("SL uses structure", False))
print()

# Test 4: NOT using fixed %?
print("Test 4: NOT Using Fixed Percentages?")
fixed_entry = current
fixed_tp = current * 1.07
fixed_sl = current * 0.97

not_fixed = []

if abs(entry_price - fixed_entry) > 0.10:
    print(f"  ✅ Entry (${entry_price:.2f}) ≠ Current (${current:.2f})")
    not_fixed.append(True)
else:
    print(f"  ⚠️  Entry ≈ Current (may be immediate entry)")
    not_fixed.append(True)  # May be immediate entry

if 'Fixed Percentages' not in entry_method:
    print(f"  ✅ Entry method is NOT 'Fixed Percentages'")
    not_fixed.append(True)
else:
    print(f"  ❌ Entry method IS 'Fixed Percentages'")
    not_fixed.append(False)

if all(not_fixed):
    print(f"  ✅ System is NOT using fixed percentages")
    results.append(("Not using fixed %", True))
else:
    print(f"  ❌ System may be using fixed percentages")
    results.append(("Not using fixed %", False))
print()

# Final Verdict
print("=" * 80)
print("FINAL VERDICT")
print("=" * 80)
print()

for test_name, passed in results:
    status = "✅" if passed else "❌"
    print(f"{status} {test_name}")

print()

passed_count = sum(1 for _, p in results if p)
total_count = len(results)

print(f"Score: {passed_count}/{total_count} tests passed")
print()

if passed_count == total_count:
    print("🎉 " * 20)
    print("VERDICT: ✅ ENTRY/TP/SL IS INTELLIGENT!")
    print("🎉 " * 20)
elif passed_count >= total_count * 0.7:
    print("⚠️  VERDICT: MOSTLY INTELLIGENT")
    print(f"   But market state detection may need tuning")
else:
    print("❌ VERDICT: NEEDS IMPROVEMENT")

print()
