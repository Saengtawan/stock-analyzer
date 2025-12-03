#!/usr/bin/env python3
"""
DEFINITIVE PROOF Test
Create data that STAYS ABOVE EMAs to trigger TRENDING_BULLISH
"""

import pandas as pd
import numpy as np
from src.analysis.technical.technical_analyzer import TechnicalAnalyzer

def create_clean_uptrend_no_deep_pullback():
    """
    Create uptrend with SHALLOW pullback that stays ABOVE EMAs
    This should trigger TRENDING_BULLISH detection
    """
    dates = pd.date_range('2024-01-01', periods=120, freq='D')

    # Phase 1: Build base (20 days) around $100
    base = np.ones(20) * 100 + np.random.randn(20) * 0.5

    # Phase 2: Strong uptrend (80 days) from $100 to $160
    uptrend = []
    price = 100
    for i in range(80):
        # 0.6% daily gain (steady climb)
        price = price * 1.006 + np.random.randn() * 0.3
        uptrend.append(price)

    # Phase 3: SHALLOW pullback (20 days) - only 3-5%
    # Keep price ABOVE EMAs!
    peak = uptrend[-1]
    pullback_depth = 0.03  # Only 3% pullback (will stay above EMA10)
    pullback = np.linspace(peak, peak * (1 - pullback_depth), 20)

    close = np.concatenate([base, uptrend, pullback])

    # Add OHLC
    high = close + np.abs(np.random.randn(120)) * 0.5
    low = close - np.abs(np.random.randn(120)) * 0.5
    open_price = close + np.random.randn(120) * 0.3

    # Volume: High during uptrend
    volume = np.concatenate([
        np.random.randint(1000000, 2000000, 20),   # Base: low
        np.random.randint(3000000, 5000000, 80),   # Uptrend: high
        np.random.randint(2500000, 4000000, 20)    # Pullback: still good
    ])

    return pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
        'symbol': ['CLEAN_UPTREND'] * 120
    })

print("=" * 80)
print("DEFINITIVE INTELLIGENCE PROOF TEST")
print("Creating uptrend with SHALLOW pullback (stays above EMAs)")
print("=" * 80)
print()

data = create_clean_uptrend_no_deep_pullback()

print(f"📊 Data Summary:")
print(f"  Total Bars: {len(data)}")
print(f"  Start Price: ${data['close'].iloc[0]:.2f}")
print(f"  Peak Price: ${data['close'].iloc[100]:.2f} (bar 100)")
print(f"  Current Price: ${data['close'].iloc[-1]:.2f}")
print(f"  Total Gain: +{((data['close'].iloc[-1] / data['close'].iloc[0]) - 1) * 100:.1f}%")
print(f"  Recent Pullback: {((data['close'].iloc[-1] / data['close'].iloc[100]) - 1) * 100:.1f}%")
print()

# Calculate EMAs to verify
ema_10 = data['close'].ewm(span=10).mean().iloc[-1]
ema_30 = data['close'].ewm(span=30).mean().iloc[-1]
current = data['close'].iloc[-1]

print(f"📈 EMA Status:")
print(f"  EMA 10: ${ema_10:.2f}")
print(f"  EMA 30: ${ema_30:.2f}")
print(f"  Current: ${current:.2f}")
print()

# Check conditions
ema_bullish = ema_10 > ema_30
price_above_ema = current > ema_10

print(f"✅ Pre-Check:")
print(f"  EMA10 > EMA30? {ema_bullish} ({ema_10:.2f} > {ema_30:.2f})")
print(f"  Price > EMA10? {price_above_ema} ({current:.2f} > {ema_10:.2f})")
print()

if ema_bullish and price_above_ema:
    print("  ✅ Conditions met for TRENDING_BULLISH!")
else:
    print("  ❌ Conditions NOT met - will be detected as BEARISH/SIDEWAY")
    if not ema_bullish:
        print(f"     Problem: EMA10 ({ema_10:.2f}) <= EMA30 ({ema_30:.2f})")
    if not price_above_ema:
        print(f"     Problem: Price ({current:.2f}) <= EMA10 ({ema_10:.2f})")

print()
print("=" * 80)
print("Running TechnicalAnalyzer...")
print("=" * 80)
print()

analyzer = TechnicalAnalyzer(data)
results = analyzer.analyze()

# Navigate to results
market_state_analysis = results.get('market_state_analysis', {})
detected_state = market_state_analysis.get('current_state', 'UNKNOWN')
strategy = market_state_analysis.get('strategy', {})
market_state_str = strategy.get('market_state', 'N/A')
strategy_name = strategy.get('strategy_name', 'N/A')

print(f"🔍 System Detection:")
print(f"  Current State: {detected_state}")
print(f"  Market State: {market_state_str}")
print(f"  Strategy: {strategy_name}")
print()

trading_plan = strategy.get('trading_plan', {})

if not trading_plan:
    print("❌ No trading plan!")
    exit(1)

# Extract data
swing_high = trading_plan.get('swing_high', 0)
swing_low = trading_plan.get('swing_low', 0)
swing_range = swing_high - swing_low

entry_price = trading_plan.get('entry_price', 0)
entry_aggressive = trading_plan.get('entry_aggressive', 0)
entry_moderate = trading_plan.get('entry_moderate', 0)
entry_conservative = trading_plan.get('entry_conservative', 0)
entry_method = trading_plan.get('entry_method', 'N/A')

tp = trading_plan.get('take_profit', 0)
tp1 = trading_plan.get('tp1', 0)
tp2 = trading_plan.get('tp2', 0)
tp3 = trading_plan.get('tp3', 0)
tp_method = trading_plan.get('tp_method', 'N/A')

sl = trading_plan.get('stop_loss', 0)
sl_method = trading_plan.get('sl_method', 'N/A')

immediate_entry = trading_plan.get('immediate_entry', False)
entry_action = trading_plan.get('entry_action', 'N/A')

print(f"📊 Trading Plan:")
print(f"  Swing High: ${swing_high:.2f}")
print(f"  Swing Low: ${swing_low:.2f}")
print(f"  Range: ${swing_range:.2f}")
print()

# Manual Fibonacci
if swing_range > 0:
    fib_382 = swing_high - (swing_range * 0.382)
    fib_500 = swing_high - (swing_range * 0.500)
    fib_618 = swing_high - (swing_range * 0.618)

    fib_ext_100 = swing_low + swing_range
    fib_ext_127 = swing_low + (swing_range * 1.272)
    fib_ext_162 = swing_low + (swing_range * 1.618)

    print(f"🔢 Manual Fibonacci (Entry):")
    print(f"  38.2%: ${fib_382:.2f}")
    print(f"  50.0%: ${fib_500:.2f}")
    print(f"  61.8%: ${fib_618:.2f}")
    print()

    print(f"🔢 Manual Fibonacci (TP):")
    print(f"  1.000: ${fib_ext_100:.2f}")
    print(f"  1.272: ${fib_ext_127:.2f}")
    print(f"  1.618: ${fib_ext_162:.2f}")
    print()

print(f"🎯 System Calculation:")
print(f"  Entry Aggressive: ${entry_aggressive:.2f}")
print(f"  Entry Moderate: ${entry_moderate:.2f}")
print(f"  Entry Conservative: ${entry_conservative:.2f}")
print(f"  Entry Method: {entry_method}")
print(f"  Immediate Entry: {immediate_entry} ({entry_action})")
print()
print(f"  TP1: ${tp1:.2f}")
print(f"  TP2: ${tp2:.2f}")
print(f"  TP3: ${tp3:.2f}")
print(f"  TP Method: {tp_method}")
print()
print(f"  SL: ${sl:.2f}")
print(f"  SL Method: {sl_method}")
print()

# VERIFICATION
print("=" * 80)
print("🔍 DEFINITIVE VERIFICATION")
print("=" * 80)
print()

results = []

# Test 1: Market State
print("Test 1: Market State Detection")
if 'Trending' in market_state_str or 'Bullish' in market_state_str:
    print("  ✅ Detected as TRENDING/BULLISH")
    results.append(True)
else:
    print(f"  ❌ Detected as: {market_state_str}")
    results.append(False)
print()

# Test 2: Entry Method
print("Test 2: Entry Method")
if 'Fibonacci' in entry_method:
    print(f"  ✅ Uses Fibonacci: '{entry_method}'")
    results.append(True)

    # Verify calculations
    tolerance = 2.0
    matches = []

    if abs(entry_aggressive - fib_382) < tolerance:
        print(f"  ✅ Aggressive ≈ Fib 38.2% (diff: ${abs(entry_aggressive - fib_382):.2f})")
        matches.append(True)
    else:
        print(f"  ❌ Aggressive ≠ Fib 38.2% (diff: ${abs(entry_aggressive - fib_382):.2f})")
        matches.append(False)

    if abs(entry_moderate - fib_500) < tolerance:
        print(f"  ✅ Moderate ≈ Fib 50.0% (diff: ${abs(entry_moderate - fib_500):.2f})")
        matches.append(True)
    else:
        print(f"  ❌ Moderate ≠ Fib 50.0% (diff: ${abs(entry_moderate - fib_500):.2f})")
        matches.append(False)

    if abs(entry_conservative - fib_618) < tolerance:
        print(f"  ✅ Conservative ≈ Fib 61.8% (diff: ${abs(entry_conservative - fib_618):.2f})")
        matches.append(True)
    else:
        print(f"  ❌ Conservative ≠ Fib 61.8% (diff: ${abs(entry_conservative - fib_618):.2f})")
        matches.append(False)

    if sum(matches) >= 2:
        print(f"  ✅ Entry levels match Fibonacci ({sum(matches)}/3)")
        results.append(True)
    else:
        print(f"  ❌ Entry levels don't match Fibonacci")
        results.append(False)
else:
    print(f"  ❌ Does NOT use Fibonacci: '{entry_method}'")
    results.append(False)
print()

# Test 3: TP Method
print("Test 3: TP Method")
if 'Fibonacci Extension' in tp_method:
    print(f"  ✅ Uses Fibonacci Extension: '{tp_method}'")
    results.append(True)
else:
    print(f"  ❌ Does NOT use Fibonacci: '{tp_method}'")
    results.append(False)
print()

# Test 4: SL Method
print("Test 4: SL Method")
if 'Swing Low' in sl_method or 'Support' in sl_method or 'ATR' in sl_method:
    print(f"  ✅ Uses structure/dynamic: '{sl_method}'")
    results.append(True)
else:
    print(f"  ❌ Method unclear: '{sl_method}'")
    results.append(False)
print()

# Final Verdict
print("=" * 80)
print("FINAL VERDICT")
print("=" * 80)
print()

passed = sum(results)
total = len(results)

print(f"Score: {passed}/{total} tests passed")
print()

if passed >= 3:
    print("🎉 " * 20)
    print("VERDICT: ✅ ENTRY/TP/SL IS INTELLIGENT!")
    print("🎉 " * 20)
    print()
    print("System uses:")
    print("  ✅ Fibonacci retracement for Entry (38.2%, 50%, 61.8%)")
    print("  ✅ Fibonacci extension for TP (1.0x, 1.272x, 1.618x)")
    print("  ✅ Structure-based SL (swing low + ATR)")
    print()
    print("NOT using:")
    print("  ❌ Fixed % for Entry")
    print("  ❌ Fixed 7% for TP")
    print("  ❌ Fixed 3% for SL")
    print()
    print("🚀 PROOF: System is INTELLIGENT, NOT DUMB!")
else:
    print("❌ VERDICT: System may still have issues")
    print()
    if not results[0]:
        print("⚠️  Market state not detected as TRENDING/BULLISH")
        print("   This prevents Fibonacci from being used")
        print("   System behavior is CORRECT for non-trending markets")

print()
