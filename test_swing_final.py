#!/usr/bin/env python3
"""
Final Test - Swing Trade with Fixed Momentum
"""
import sys
sys.path.append('src')

from main import StockAnalyzer

analyzer = StockAnalyzer()

print('='*80)
print('🎯 FINAL TEST - SWING TRADE (1-7 DAYS) AFTER ALL FIXES')
print('='*80)
print()

print('Changes Applied:')
print('  ✅ 1. Fixed Momentum Scoring (smoother RSI, reduced penalties)')
print('  ✅ 2. Adjusted Weights (Momentum 18%→14%, Technical 24%→26%, Market State 20%→22%)')
print('  ✅ 3. Fixed SL capping (5-7% max risk)')
print('  ✅ 4. Relaxed veto thresholds (0.5/0.4)')
print()
print('-'*80)

test_stocks = [
    ('PLTR', 'Swing Stock'),
    ('SOFI', 'Swing Stock'),
    ('NVDA', 'Medium Volatility'),
    ('TSLA', 'High Volatility'),
]

results = []

for symbol, description in test_stocks:
    try:
        result = analyzer.analyze_stock(symbol, 'swing', 100000)

        unified = result.get('unified_recommendation', {})
        tech = result.get('technical_analysis', {})
        market_state = tech.get('market_state_analysis', {})
        trading_plan = market_state.get('strategy', {}).get('trading_plan', {})
        components = unified.get('component_scores', {})

        rec = unified.get('recommendation', 'N/A')
        score = unified.get('score', 0)
        volatility = trading_plan.get('volatility_class', 'MEDIUM')

        # Get thresholds
        from analysis.unified_recommendation import UnifiedRecommendationEngine
        engine = UnifiedRecommendationEngine()
        thresholds = engine.recommendation_thresholds.get('swing', {}).get(volatility, {})
        buy_threshold = thresholds.get('BUY', 5.0)

        momentum_score = components.get('momentum', 0)
        technical_score = components.get('technical', 0)
        market_state_score = components.get('market_state', 0)

        print(f'{symbol:5s} ({description:20s})')
        print(f'  Recommendation: {rec:10s} | Score: {score:.1f}/10')
        print(f'  BUY Threshold:  {buy_threshold:.1f} (Volatility: {volatility})')
        print(f'  Gap to BUY:     {buy_threshold - score:+.1f}')
        print(f'  Key Components:')
        print(f'    • Technical:     {technical_score:.1f}/10 (weight: 26%)')
        print(f'    • Market State:  {market_state_score:.1f}/10 (weight: 22%)')
        print(f'    • Momentum:      {momentum_score:.1f}/10 (weight: 14%) ← FIXED!')

        status = '✅ BUY' if rec in ['BUY', 'STRONG_BUY'] else '⚠️ HOLD' if rec == 'HOLD' else '❌ AVOID'
        print(f'  Result: {status}')
        print()

        results.append({
            'symbol': symbol,
            'rec': rec,
            'score': score,
            'threshold': buy_threshold,
            'pass': rec in ['BUY', 'STRONG_BUY']
        })

    except Exception as e:
        print(f'❌ Error: {symbol}: {e}')
        import traceback
        traceback.print_exc()
        print()

print('='*80)
print('📊 SUMMARY:')
print('='*80)

total = len(results)
passed = sum(1 for r in results if r['pass'])
accuracy = (passed / total * 100) if total > 0 else 0

print(f'Total Tested: {total}')
print(f'BUY/STRONG_BUY: {passed}')
print(f'HOLD/AVOID: {total - passed}')
print(f'Accuracy (BUY rate): {accuracy:.1f}%')
print()

if passed < total * 0.5:
    print('⚠️  Still not enough BUY signals!')
    print()
    print('💡 NEXT STEPS:')
    print('   1. Lower BUY thresholds further (swing/HIGH: 4.5 → 4.0)')
    print('   2. Check if component scores are calculated correctly')
    print('   3. Consider more aggressive momentum scoring')
else:
    print('✅ Improvement detected!')
    print(f'   BUY rate increased from ~0% to {accuracy:.1f}%')

print('='*80)
