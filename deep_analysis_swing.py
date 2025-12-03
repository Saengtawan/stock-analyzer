#!/usr/bin/env python3
"""
Deep Root Cause Analysis - Swing Trade Timeframe
วิเคราะห์ว่าทำไม Recommendation Accuracy ต่ำ
"""
import sys
sys.path.append('src')

from main import StockAnalyzer

def analyze_stock_deep(symbol, timeframe='swing'):
    """วิเคราะห์ลึกขึ้นสำหรับ stock หนึ่งตัว"""
    analyzer = StockAnalyzer()
    result = analyzer.analyze_stock(symbol, timeframe, 100000)

    unified = result.get('unified_recommendation', {})
    tech = result.get('technical_analysis', {})
    market_state = tech.get('market_state_analysis', {})
    strategy = market_state.get('strategy', {})
    trading_plan = strategy.get('trading_plan', {})
    components = unified.get('component_scores', {})
    weights = unified.get('weights_applied', {})

    print('='*80)
    print(f'🔍 DEEP ANALYSIS: {symbol} ({timeframe.upper()} - 1-7 days)')
    print('='*80)
    print()

    # Basic info
    rec = unified.get('recommendation', 'N/A')
    score = unified.get('score', 0)
    volatility = trading_plan.get('volatility_class', 'MEDIUM')

    print(f'📊 RESULT: {rec} | Score: {score:.1f}/10 | Volatility: {volatility}')
    print()

    # Get threshold
    from analysis.unified_recommendation import UnifiedRecommendationEngine
    engine = UnifiedRecommendationEngine()
    thresholds = engine.recommendation_thresholds.get(timeframe, {}).get(volatility, {})
    buy_threshold = thresholds.get('BUY', 'N/A')

    print(f'🎯 BUY Threshold ({timeframe}/{volatility}): {buy_threshold}')
    print(f'   Current Score: {score:.1f}')
    print(f'   Gap to BUY: {buy_threshold - score:.1f}' if isinstance(buy_threshold, (int, float)) else '')
    print()

    # Component Analysis
    print('📈 COMPONENT BREAKDOWN (sorted by contribution):')
    print(f'{"Component":<20} {"Score":>6} {"Weight":>8} {"Contrib":>10} {"% Total":>8}')
    print('-'*80)

    items = []
    total_contrib = 0
    for name, component_score in components.items():
        weight = weights.get(name, 0)
        contrib = component_score * weight
        total_contrib += contrib
        items.append((name, component_score, weight, contrib))

    items.sort(key=lambda x: x[3], reverse=True)

    for name, component_score, weight, contrib in items:
        pct = (contrib / total_contrib * 100) if total_contrib > 0 else 0
        status = '✅' if component_score >= 6.0 else '⚠️' if component_score >= 4.0 else '❌'
        print(f'{name:<20} {component_score:>6.1f} {weight:>8.2f} {contrib:>10.2f} {pct:>7.1f}% {status}')

    print()
    print(f'Total Weighted Score: {total_contrib:.2f}')
    print()

    # R/R Analysis
    print('💰 RISK/REWARD ANALYSIS:')
    entry = trading_plan.get('entry_price', 0)
    tp = trading_plan.get('take_profit', 0)
    sl = trading_plan.get('stop_loss', 0)
    risk_pct = trading_plan.get('risk_pct', 0)
    rr = trading_plan.get('risk_reward_ratio', 0)

    if entry > 0:
        reward_pct = ((tp - entry) / entry * 100) if tp > entry else 0
        print(f'  Entry: ${entry:.2f}')
        print(f'  TP: ${tp:.2f} (+{reward_pct:.1f}%)')
        print(f'  SL: ${sl:.2f} (-{risk_pct:.1f}%)')
        print(f'  R/R Ratio: {rr:.2f}:1')
        print(f'  Risk/Reward Component Score: {components.get("risk_reward", 0):.1f}/10')
    print()

    # Identify bottlenecks
    print('🔧 ROOT CAUSE BOTTLENECKS:')
    bottlenecks = []

    # Issue 1: Low overall score
    if score < buy_threshold and isinstance(buy_threshold, (int, float)):
        bottlenecks.append(f'Overall score too low: {score:.1f} < {buy_threshold} (BUY threshold)')

    # Issue 2: Low-scoring high-weight components
    critical_low = [(name, s, weights.get(name, 0))
                    for name, s in components.items()
                    if s < 4.0 and weights.get(name, 0) >= 0.10]
    if critical_low:
        bottlenecks.append('Critical low-scoring components (score < 4.0, weight >= 10%):')
        for name, s, w in sorted(critical_low, key=lambda x: x[1]):
            bottlenecks.append(f'  • {name}: {s:.1f}/10 (weight: {w:.0%}) → Dragging down {s * w:.2f} points')

    # Issue 3: Good R/R but low score
    if rr >= 1.0 and components.get('risk_reward', 0) < 6.0:
        bottlenecks.append(f'R/R ratio is good ({rr:.2f}) but Risk/Reward score is only {components.get("risk_reward", 0):.1f}/10')

    # Issue 4: Veto applied
    veto_info = unified.get('veto_applied', {})
    if veto_info.get('veto'):
        bottlenecks.append('VETO applied:')
        for reason in veto_info.get('reasons', []):
            bottlenecks.append(f'  • {reason}')

    if bottlenecks:
        for b in bottlenecks:
            print(f'  {b}')
    else:
        print('  ✅ No major bottlenecks found')

    print()
    return {
        'symbol': symbol,
        'recommendation': rec,
        'score': score,
        'buy_threshold': buy_threshold,
        'bottlenecks': bottlenecks,
        'components': components,
        'weights': weights
    }


if __name__ == '__main__':
    # Test stocks from backtest
    symbols = ['PLTR', 'SOFI', 'NVDA', 'TSLA']

    print()
    print('='*80)
    print('🎯 DEEP ROOT CAUSE ANALYSIS - SWING TRADE (1-7 DAYS)')
    print('='*80)
    print()

    results = []
    for symbol in symbols:
        try:
            result = analyze_stock_deep(symbol, 'swing')
            results.append(result)
            print()
        except Exception as e:
            print(f'❌ Error analyzing {symbol}: {e}')
            import traceback
            traceback.print_exc()
            print()

    # Summary
    print('='*80)
    print('📋 SUMMARY - Common Root Causes Across All Stocks:')
    print('='*80)

    # Aggregate bottlenecks
    from collections import Counter
    all_bottlenecks = []
    for r in results:
        all_bottlenecks.extend(r['bottlenecks'])

    # Find common low components
    low_components = Counter()
    for r in results:
        for name, score in r['components'].items():
            weight = r['weights'].get(name, 0)
            if score < 5.0 and weight >= 0.10:
                low_components[name] += 1

    if low_components:
        print()
        print('🔴 Components consistently scoring low (< 5.0) across stocks:')
        for name, count in low_components.most_common(5):
            print(f'  • {name}: {count}/{len(results)} stocks')

    # Calculate average scores
    print()
    print('📊 Average Component Scores:')
    avg_scores = {}
    for name in results[0]['components'].keys():
        scores = [r['components'][name] for r in results if name in r['components']]
        if scores:
            avg_scores[name] = sum(scores) / len(scores)

    for name, avg in sorted(avg_scores.items(), key=lambda x: x[1]):
        status = '✅' if avg >= 6.0 else '⚠️' if avg >= 4.0 else '❌'
        print(f'  {name:<20}: {avg:>4.1f}/10 {status}')

    print()
    print('='*80)
    print('💡 RECOMMENDATIONS:')
    print('='*80)
    print('Based on the analysis above, the main issues are:')
    print('1. Identify which components are consistently low')
    print('2. Understand why those components score low')
    print('3. Either fix the scoring logic OR adjust their weights')
    print('='*80)
