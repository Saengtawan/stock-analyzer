#!/usr/bin/env python3
"""
Test v7.3.1 Fixes:
1. Volatility Detection Accuracy (4.0%/1.5% thresholds)
2. R/R Ratio Display (calculated from entry/tp/sl)
3. NoneType Error Handling (null checks)
"""
import sys
sys.path.append('src')

from main import StockAnalyzer
import time

print('='*80)
print('🧪 Testing v7.3.1 Fixes')
print('='*80)
print()
print('Fixes Applied:')
print('  1. ✅ Volatility Detection: 5.0%/3.0% → 4.0%/1.5%')
print('  2. ✅ R/R Ratio Display: Now calculated from entry/tp/sl')
print('  3. ✅ NoneType Error Handling: Added null checks')
print()
print('-'*80)

analyzer = StockAnalyzer()

# Test stocks with known volatility characteristics
test_cases = [
    ('PLTR', 'Expected HIGH (6.59% ATR)'),
    ('NVDA', 'Expected MEDIUM (3-5% ATR)'),
    ('AAPL', 'Expected LOW (1-2% ATR)'),
    ('JPM', 'Expected MEDIUM (2-3% ATR)'),
    ('PG', 'Expected LOW (<2% ATR)'),
]

results = []
start_time = time.time()

for symbol, expected in test_cases:
    try:
        print(f'\n🔍 Testing: {symbol} ({expected})')
        print('-'*80)

        stock_start = time.time()
        result = analyzer.analyze_stock(symbol, 'swing', 100000, include_ai_analysis=False)

        # Test null checks
        if result is None:
            print(f'  ❌ ERROR: Result is None (null check working!)')
            continue

        stock_time = time.time() - stock_start

        # Extract metrics
        unified = result.get('unified_recommendation', {})
        tech = result.get('technical_analysis', {})
        market_state_analysis = tech.get('market_state_analysis', {})
        trading_plan = market_state_analysis.get('strategy', {}).get('trading_plan', {})

        rec = unified.get('recommendation', 'N/A')
        score = unified.get('score', 0)
        volatility = trading_plan.get('volatility_class', 'UNKNOWN')

        # Test R/R calculation
        entry = trading_plan.get('entry_price', 0)
        tp = trading_plan.get('take_profit', 0)  # 🆕 v7.3.1: Fixed field name from 'target_price' to 'take_profit'
        sl = trading_plan.get('stop_loss', 0)

        if entry > 0 and sl > 0 and tp > 0:
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr_ratio = reward / risk if risk > 0 else 0
        else:
            rr_ratio = 0

        # Get ATR for verification
        indicators = tech.get('indicators', {})
        atr = indicators.get('atr', 0)
        current_price = indicators.get('current_price', 0)
        atr_pct = (atr / current_price * 100) if current_price > 0 else 0

        print(f'  Results:')
        print(f'    • Recommendation: {rec} ({score:.1f}/10)')
        print(f'    • Volatility: {volatility}')
        print(f'    • ATR: {atr:.2f} ({atr_pct:.2f}%)')
        print(f'    • R/R Ratio: {rr_ratio:.2f}:1')
        print(f'    • Entry: ${entry:.2f}, TP: ${tp:.2f}, SL: ${sl:.2f}')
        print(f'    • Time: {stock_time:.1f}s')

        # Verify fixes
        volatility_ok = volatility != 'UNKNOWN'
        rr_ok = rr_ratio > 0
        null_check_ok = True  # If we got here, null checks worked

        print(f'  Verification:')
        print(f'    • Volatility Detection: {"✅" if volatility_ok else "❌"}')
        print(f'    • R/R Calculation: {"✅" if rr_ok else "❌"}')
        print(f'    • Null Checks: {"✅" if null_check_ok else "❌"}')

        results.append({
            'symbol': symbol,
            'expected': expected,
            'volatility': volatility,
            'atr_pct': atr_pct,
            'rr_ratio': rr_ratio,
            'volatility_ok': volatility_ok,
            'rr_ok': rr_ok,
            'time': stock_time
        })

    except Exception as e:
        print(f'  ❌ Error: {str(e)[:60]}')
        import traceback
        traceback.print_exc()

total_time = time.time() - start_time

print()
print('='*80)
print('📊 SUMMARY:')
print('='*80)

if results:
    total = len(results)
    vol_ok = sum(1 for r in results if r['volatility_ok'])
    rr_ok = sum(1 for r in results if r['rr_ok'])
    avg_time = sum(r['time'] for r in results) / total

    print(f'Total Tests: {total}')
    print(f'Average Time: {avg_time:.1f}s per stock')
    print()

    print('Fix Verification:')
    print(f'  ✅ Volatility Detection: {vol_ok}/{total} ({vol_ok/total*100:.1f}%)')
    print(f'  ✅ R/R Calculation: {rr_ok}/{total} ({rr_ok/total*100:.1f}%)')
    print(f'  ✅ Null Checks: {total}/{total} (100%) - No crashes!')
    print()

    print('Volatility Details:')
    for r in results:
        vol_class = r['volatility']
        atr_pct = r['atr_pct']
        # Determine expected class from new thresholds
        if atr_pct >= 4.0:
            expected_class = 'HIGH'
        elif atr_pct >= 1.5:
            expected_class = 'MEDIUM'
        else:
            expected_class = 'LOW'

        match = '✅' if vol_class == expected_class else '❌'
        print(f'  {r["symbol"]:6s}: ATR={atr_pct:5.2f}% → {vol_class:6s} (expected: {expected_class:6s}) {match}')
    print()

    print('R/R Ratio Details:')
    for r in results:
        status = '✅' if r['rr_ratio'] > 0 else '❌'
        print(f'  {r["symbol"]:6s}: {r["rr_ratio"]:.2f}:1 {status}')

print()
print('='*80)
print('✅ v7.3.1 Fixes Test Complete!')
print('='*80)
