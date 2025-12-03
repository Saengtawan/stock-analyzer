#!/usr/bin/env python3
"""
Test complete integration of v5.0 + v5.1 features
Verify that data flows from technical_analyzer → unified_recommendation → API
"""

import pandas as pd
import numpy as np
from src.analysis.technical.technical_analyzer import TechnicalAnalyzer
from src.analysis.unified_recommendation import create_unified_recommendation

def create_test_data():
    """Create simple test data"""
    dates = pd.date_range('2024-01-01', periods=100, freq='D')

    # Simple uptrend
    close = np.linspace(100, 150, 100) + np.random.randn(100) * 0.5
    high = close + np.abs(np.random.randn(100)) * 0.5
    low = close - np.abs(np.random.randn(100)) * 0.5
    open_price = close + np.random.randn(100) * 0.3

    # High volume
    volume = np.random.randint(3000000, 5000000, 100)

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
print("INTEGRATION TEST - v5.0 + v5.1 Features")
print("=" * 80)
print()

# Step 1: Technical Analysis
print("Step 1: Running TechnicalAnalyzer...")
data = create_test_data()
analyzer = TechnicalAnalyzer(data)
tech_results = analyzer.analyze()

market_state_analysis = tech_results.get('market_state_analysis', {})
strategy = market_state_analysis.get('strategy', {})
trading_plan = strategy.get('trading_plan', {})

print(f"  ✅ TechnicalAnalyzer complete")
print(f"  Market State: {market_state_analysis.get('current_state')}")
print(f"  Trading Plan fields: {len(trading_plan)}")
print()

# Step 2: Check trading_plan has v5.0 + v5.1 fields
print("Step 2: Checking trading_plan fields...")

required_fields = {
    'v5.0 Swing Points': ['swing_high', 'swing_low'],
    'v5.0 Entry Levels': ['entry_aggressive', 'entry_moderate', 'entry_conservative', 'entry_price', 'entry_method'],
    'v5.0 TP Levels': ['tp1', 'tp2', 'tp3', 'take_profit', 'tp_method'],
    'v5.0 SL Details': ['stop_loss', 'sl_method', 'risk_pct'],
    'v5.1 Immediate Entry': ['immediate_entry', 'immediate_entry_confidence', 'immediate_entry_reasons', 'entry_action']
}

all_present = True
for category, fields in required_fields.items():
    present = all(f in trading_plan for f in fields)
    status = "✅" if present else "❌"
    print(f"  {status} {category}: {present}")
    if not present:
        missing = [f for f in fields if f not in trading_plan]
        print(f"     Missing: {missing}")
        all_present = False

print()

if not all_present:
    print("❌ FAIL: trading_plan missing required fields")
    exit(1)

# Step 3: Test unified_recommendation extraction
print("Step 3: Testing unified_recommendation extraction...")

# Mock minimal analysis_results
analysis_results = {
    'symbol': 'TEST',
    'technical_analysis': tech_results,
    'fundamental_analysis': {
        'overall_score': 7.0,
        'financial_health': {'score': 7.0},
        'valuation': {'score': 6.5},
        'growth_metrics': {'score': 7.5}
    },
    'price_change_analysis': {
        'day_change_pct': 2.5,
        'week_change_pct': 5.0,
        'month_change_pct': 10.0
    },
    'insider_data': {
        'recent_purchases': 5,
        'recent_sales': 1
    },
    'performance_expectations': {
        'time_horizon': 'short'
    }
}

try:
    unified_rec = create_unified_recommendation(analysis_results)
    print(f"  ✅ create_unified_recommendation() executed")
except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Step 4: Check unified_recommendation has v5.0 + v5.1 fields
print()
print("Step 4: Checking unified_recommendation output...")

required_output_fields = {
    'v5.1 Immediate Entry': 'immediate_entry_info',
    'v5.0 Entry Levels': 'entry_levels',
    'v5.0 TP Levels': 'tp_levels',
    'v5.0 SL Details': 'sl_details',
    'v5.0 Swing Points': 'swing_points'
}

all_output_present = True
for category, field in required_output_fields.items():
    present = field in unified_rec
    has_data = present and unified_rec[field]
    status = "✅" if has_data else ("⚠️" if present else "❌")
    print(f"  {status} {category}: {field} - {'present' if present else 'MISSING'}")

    if has_data and isinstance(unified_rec[field], dict):
        print(f"     Fields: {list(unified_rec[field].keys())[:5]}")

    if not present:
        all_output_present = False

print()

# Step 5: Validate data structure
print("Step 5: Validating data structures...")

checks = []

# Check immediate_entry_info
if 'immediate_entry_info' in unified_rec:
    info = unified_rec['immediate_entry_info']
    has_action = 'action' in info
    has_confidence = 'confidence' in info
    checks.append(('immediate_entry_info has action', has_action))
    checks.append(('immediate_entry_info has confidence', has_confidence))
    print(f"  {'✅' if has_action else '❌'} immediate_entry_info.action: {info.get('action', 'N/A')}")
    print(f"  {'✅' if has_confidence else '❌'} immediate_entry_info.confidence: {info.get('confidence', 'N/A')}")

# Check entry_levels
if 'entry_levels' in unified_rec:
    levels = unified_rec['entry_levels']
    has_aggressive = 'aggressive' in levels and levels['aggressive']
    has_method = 'method' in levels
    checks.append(('entry_levels has aggressive', has_aggressive))
    checks.append(('entry_levels has method', has_method))
    print(f"  {'✅' if has_aggressive else '❌'} entry_levels.aggressive: {levels.get('aggressive', 'N/A')}")
    print(f"  {'✅' if has_method else '❌'} entry_levels.method: {levels.get('method', 'N/A')}")

# Check tp_levels
if 'tp_levels' in unified_rec:
    tp = unified_rec['tp_levels']
    has_tp1 = 'tp1' in tp and tp['tp1']
    has_method = 'method' in tp
    checks.append(('tp_levels has tp1', has_tp1))
    checks.append(('tp_levels has method', has_method))
    print(f"  {'✅' if has_tp1 else '❌'} tp_levels.tp1: {tp.get('tp1', 'N/A')}")
    print(f"  {'✅' if has_method else '❌'} tp_levels.method: {tp.get('method', 'N/A')}")

# Check sl_details
if 'sl_details' in unified_rec:
    sl = unified_rec['sl_details']
    has_value = 'value' in sl and sl['value']
    has_method = 'method' in sl
    checks.append(('sl_details has value', has_value))
    checks.append(('sl_details has method', has_method))
    print(f"  {'✅' if has_value else '❌'} sl_details.value: {sl.get('value', 'N/A')}")
    print(f"  {'✅' if has_method else '❌'} sl_details.method: {sl.get('method', 'N/A')}")

print()

# Final verdict
print("=" * 80)
print("FINAL VERDICT")
print("=" * 80)
print()

passed = sum(1 for _, result in checks if result)
total = len(checks)

print(f"Validation Checks: {passed}/{total} passed")
print()

for check_name, result in checks:
    status = "✅" if result else "❌"
    print(f"{status} {check_name}")

print()

if passed == total and all_output_present:
    print("🎉 " * 20)
    print("INTEGRATION COMPLETE!")
    print("🎉 " * 20)
    print()
    print("✅ technical_analyzer produces v5.0 + v5.1 data")
    print("✅ unified_recommendation extracts all fields")
    print("✅ Data structures are correct")
    print()
    print("🚀 Ready for API and UI integration!")
elif passed >= total * 0.8:
    print("⚠️  MOSTLY WORKING")
    print(f"   {total - passed} checks failed - review needed")
else:
    print("❌ INTEGRATION INCOMPLETE")
    print(f"   {total - passed} checks failed")

print()
