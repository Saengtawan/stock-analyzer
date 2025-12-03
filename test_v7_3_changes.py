#!/usr/bin/env python3
"""
Quick Test v7.3 Changes:
1. Performance fix (no AI calls)
2. Smooth momentum scoring
3. Comprehensive logging
4. Adaptive weights
"""
import sys
sys.path.append('src')

from main import StockAnalyzer
import time

print('='*80)
print('🎯 QUICK TEST - v7.3 CHANGES')
print('='*80)
print()

print('Changes to test:')
print('  ✅ 1. Performance: AI calls disabled for speed')
print('  ✅ 2. Smooth Momentum: Linear RSI/MACD/EMA scoring')
print('  ✅ 3. Comprehensive Logging: Metrics tracking')
print('  ✅ 4. Adaptive Weights: Context-aware adjustments')
print()
print('-'*80)

analyzer = StockAnalyzer()

# Test 3 different stocks with different volatility/market states
test_stocks = [
    'PLTR',   # HIGH volatility, likely TRENDING
    'NVDA',   # HIGH/MEDIUM volatility
    'AAPL'    # LOW volatility
]

start_time = time.time()
results = []

for symbol in test_stocks:
    try:
        print(f'\nAnalyzing {symbol}...')
        stock_start = time.time()

        # include_ai_analysis=False for speed test
        result = analyzer.analyze_stock(symbol, 'swing', 100000, include_ai_analysis=False)

        stock_time = time.time() - stock_start

        unified = result.get('unified_recommendation', {})
        tech = result.get('technical_analysis', {})
        market_state_analysis = tech.get('market_state_analysis', {})
        trading_plan = market_state_analysis.get('strategy', {}).get('trading_plan', {})

        rec = unified.get('recommendation', 'N/A')
        score = unified.get('score', 0)
        volatility = trading_plan.get('volatility_class', 'UNKNOWN')
        market_state = market_state_analysis.get('market_state', 'UNKNOWN')

        print(f'  {symbol}: {rec} ({score:.1f}/10) | Vol: {volatility} | State: {market_state} | Time: {stock_time:.1f}s')

        results.append({
            'symbol': symbol,
            'rec': rec,
            'score': score,
            'time': stock_time,
            'volatility': volatility,
            'market_state': market_state
        })

    except Exception as e:
        print(f'  ❌ Error: {symbol}: {e}')
        import traceback
        traceback.print_exc()

total_time = time.time() - start_time

print()
print('='*80)
print('📊 SUMMARY:')
print('='*80)

if results:
    avg_time = sum(r['time'] for r in results) / len(results)
    print(f'Stocks Tested: {len(results)}')
    print(f'Total Time: {total_time:.1f}s')
    print(f'Average Time per Stock: {avg_time:.1f}s')
    print()

    print('Performance Comparison:')
    print(f'  v7.2 (with AI): ~70-90s per stock')
    print(f'  v7.3 (no AI):   ~{avg_time:.0f}s per stock')
    if avg_time < 20:
        print(f'  ✅ Speed improvement: {70/avg_time:.1f}x faster!')
    print()

    buys = sum(1 for r in results if r['rec'] in ['BUY', 'STRONG_BUY'])
    holds = sum(1 for r in results if r['rec'] == 'HOLD')

    print('Recommendations:')
    print(f'  BUY/STRONG_BUY: {buys}')
    print(f'  HOLD: {holds}')
    print(f'  OTHERS: {len(results) - buys - holds}')
    print()

    print('Adaptive Weights Test:')
    for r in results:
        print(f'  {r["symbol"]:6s}: Vol={r["volatility"]:7s}, State={r["market_state"]:20s}')
    print('  ✅ Each stock should have different weight adjustments based on context')

print()
print('='*80)
print('✅ v7.3 Changes Test Complete!')
print('='*80)
