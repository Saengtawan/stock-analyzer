#!/usr/bin/env python3
"""
Simple Verification Test
Verify that our v5.0 + v5.1 features are present and working
"""

import pandas as pd
import numpy as np
from src.analysis.technical.technical_analyzer import TechnicalAnalyzer

def create_strong_uptrend():
    """Create obvious uptrend data"""
    dates = pd.date_range('2024-01-01', periods=100, freq='D')

    # Strong consistent uptrend
    close = np.linspace(100, 150, 100)  # Linear uptrend
    close += np.random.randn(100) * 0.5  # Small noise

    high = close + np.random.rand(100) * 1
    low = close - np.random.rand(100) * 1
    open_price = close + np.random.randn(100) * 0.5
    volume = np.random.randint(2000000, 3000000, 100)

    return pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
        'symbol': ['TEST'] * 100
    })

print("=" * 80)
print("SIMPLE VERIFICATION TEST - v5.0 + v5.1")
print("=" * 80)
print()

data = create_strong_uptrend()
print(f"Data: {len(data)} bars from ${data['close'].iloc[0]:.2f} to ${data['close'].iloc[-1]:.2f}")
print()

analyzer = TechnicalAnalyzer(data)
results = analyzer.analyze()

# Navigate to trading plan
market_state_analysis = results.get('market_state_analysis', {})
strategy = market_state_analysis.get('strategy', {})
trading_plan = strategy.get('trading_plan', {})

print("✅ Step 1: Check if trading_plan exists")
if trading_plan:
    print(f"   trading_plan has {len(trading_plan)} fields")
    print(f"   ✅ PASS")
else:
    print("   ❌ FAIL - No trading plan!")
    exit(1)

print()
print("✅ Step 2: Check v5.0 Features (Intelligent Entry/TP/SL)")

v5_features = {
    'Swing Points': ['swing_high', 'swing_low'],
    'Smart Entry': ['entry_aggressive', 'entry_moderate', 'entry_conservative', 'entry_method'],
    'Intelligent TP': ['tp1', 'tp2', 'tp3', 'tp_method'],
    'Intelligent SL': ['stop_loss', 'sl_method', 'risk_pct']
}

v5_passed = True
for feature, fields in v5_features.items():
    all_present = all(f in trading_plan for f in fields)
    status = "✅" if all_present else "❌"
    print(f"   {status} {feature}: {all_present}")
    if not all_present:
        missing = [f for f in fields if f not in trading_plan]
        print(f"      Missing: {missing}")
        v5_passed = False

print()
if v5_passed:
    print("   ✅ v5.0 Features: ALL PRESENT")
else:
    print("   ❌ v5.0 Features: SOME MISSING")

print()
print("✅ Step 3: Check v5.1 Features (Immediate Entry Logic)")

v5_1_features = [
    'immediate_entry',
    'immediate_entry_confidence',
    'immediate_entry_reasons',
    'entry_action'
]

v5_1_passed = all(f in trading_plan for f in v5_1_features)
for field in v5_1_features:
    present = field in trading_plan
    status = "✅" if present else "❌"
    value = trading_plan.get(field, 'N/A')
    if field == 'immediate_entry_reasons' and isinstance(value, list):
        value = f"list with {len(value)} items"
    print(f"   {status} {field}: {value}")

print()
if v5_1_passed:
    print("   ✅ v5.1 Features: ALL PRESENT")
else:
    print("   ❌ v5.1 Features: SOME MISSING")

print()
print("✅ Step 4: Check Calculation Quality")

current_price = data['close'].iloc[-1]
entry = trading_plan.get('entry_price', 0)
tp = trading_plan.get('take_profit', 0)
sl = trading_plan.get('stop_loss', 0)
entry_method = trading_plan.get('entry_method', 'N/A')
tp_method = trading_plan.get('tp_method', 'N/A')
sl_method = trading_plan.get('sl_method', 'N/A')

print(f"   Current Price: ${current_price:.2f}")
print(f"   Entry: ${entry:.2f} ({entry_method})")
print(f"   TP: ${tp:.2f} ({tp_method})")
print(f"   SL: ${sl:.2f} ({sl_method})")

quality_checks = [
    (entry > 0, "Entry price > 0"),
    (entry_method != 'Fixed Percentages', "Entry NOT fixed %"),
    (tp_method in ['Fibonacci Extension', 'Resistance Level', 'ATR Multiple'], "TP is intelligent"),
    (sl_method in ['Below Swing Low + ATR Buffer', 'Below Support (2%)', 'ATR-based (2x ATR)'], "SL is intelligent")
]

quality_passed = True
for check, description in quality_checks:
    status = "✅" if check else "❌"
    print(f"   {status} {description}")
    if not check:
        quality_passed = False

print()
if quality_passed:
    print("   ✅ Calculation Quality: GOOD")
else:
    print("   ❌ Calculation Quality: NEEDS IMPROVEMENT")

print()
print("=" * 80)
print("FINAL RESULT")
print("=" * 80)

all_passed = v5_passed and v5_1_passed and quality_passed

if all_passed:
    print()
    print("🎉 " * 20)
    print("ALL VERIFICATION PASSED!")
    print("🎉 " * 20)
    print()
    print("✅ v5.0: Intelligent Entry/TP/SL (Fibonacci + Swing Points)")
    print("✅ v5.1: Immediate Entry Logic")
    print("✅ Calculation Quality: Good")
    print()
    print("🚀 System is working as expected!")
    print()
else:
    print()
    print("⚠️  VERIFICATION INCOMPLETE")
    print()
    if not v5_passed:
        print("❌ v5.0 features incomplete")
    if not v5_1_passed:
        print("❌ v5.1 features incomplete")
    if not quality_passed:
        print("❌ Calculation quality needs improvement")
    print()
