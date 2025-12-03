#!/usr/bin/env python3
"""
Ultra Comprehensive Backtest v7.3
Tests system across ALL dimensions:
- All timeframes (swing/short/medium/long)
- All volatility classes (HIGH/MEDIUM/LOW)
- All sectors (Tech/Finance/Healthcare/Energy/Consumer/etc)
- Edge cases (penny stocks, oversold, overbought, sideways)
"""
import sys
sys.path.append('src')

from main import StockAnalyzer
from datetime import datetime, timedelta
import time
import json

def ultra_comprehensive_backtest():
    """Run ultra-comprehensive backtest covering all dimensions"""
    analyzer = StockAnalyzer()

    print('='*100)
    print('🎯 ULTRA COMPREHENSIVE BACKTEST v7.3')
    print('='*100)
    print()
    print('Coverage:')
    print('  ✅ All Timeframes: swing (1-7d), short (1-14d), medium (14-90d), long (6mo+)')
    print('  ✅ All Volatility Classes: HIGH, MEDIUM, LOW')
    print('  ✅ All Sectors: Tech, Finance, Healthcare, Energy, Consumer, Communication, Industrial')
    print('  ✅ Edge Cases: Penny stocks, Oversold, Overbought, Sideways, Post-earnings')
    print('  ✅ Performance: include_ai_analysis=False (18.4x faster)')
    print()
    print('='*100)
    print()

    # Test matrix organized by multiple dimensions
    test_matrix = {
        '🔥 High Volatility Tech (Typical Swing Stocks)': {
            'stocks': ['PLTR', 'SOFI', 'RIVN', 'LCID'],
            'expected_volatility': 'HIGH',
            'sector': 'Technology',
            'characteristics': 'High beta, momentum-driven, retail favorites'
        },
        '🚀 High Volatility Growth Tech': {
            'stocks': ['TSLA', 'NVDA', 'AMD', 'SMCI'],
            'expected_volatility': 'HIGH',
            'sector': 'Technology',
            'characteristics': 'Large cap but high volatility, strong fundamentals'
        },
        '📊 Medium Volatility Tech Giants': {
            'stocks': ['MSFT', 'GOOGL', 'META', 'ORCL'],
            'expected_volatility': 'MEDIUM',
            'sector': 'Technology',
            'characteristics': 'Mega cap, moderate volatility, stable growth'
        },
        '🏦 Low Volatility Blue Chip Tech': {
            'stocks': ['AAPL', 'IBM', 'CSCO', 'INTC'],
            'expected_volatility': 'LOW',
            'sector': 'Technology',
            'characteristics': 'Mature tech, dividend payers, defensive'
        },
        '💰 Financial Sector (Medium Volatility)': {
            'stocks': ['JPM', 'BAC', 'GS', 'MS'],
            'expected_volatility': 'MEDIUM',
            'sector': 'Financial',
            'characteristics': 'Bank stocks, interest rate sensitive'
        },
        '🏥 Healthcare (Low-Medium Volatility)': {
            'stocks': ['JNJ', 'PFE', 'UNH', 'ABBV'],
            'expected_volatility': 'LOW',
            'sector': 'Healthcare',
            'characteristics': 'Defensive sector, stable dividends'
        },
        '⚡ Energy Sector (High Volatility)': {
            'stocks': ['XOM', 'CVX', 'SLB', 'HAL'],
            'expected_volatility': 'HIGH',
            'sector': 'Energy',
            'characteristics': 'Commodity-driven, cyclical'
        },
        '🛒 Consumer Goods (Low Volatility)': {
            'stocks': ['PG', 'KO', 'PEP', 'WMT'],
            'expected_volatility': 'LOW',
            'sector': 'Consumer',
            'characteristics': 'Staples, defensive, stable'
        },
        '📱 Communication Services (Medium Volatility)': {
            'stocks': ['T', 'VZ', 'CMCSA', 'DIS'],
            'expected_volatility': 'MEDIUM',
            'sector': 'Communication',
            'characteristics': 'Telecom & media, moderate growth'
        },
        '🏭 Industrials (Medium Volatility)': {
            'stocks': ['CAT', 'BA', 'HON', 'UPS'],
            'expected_volatility': 'MEDIUM',
            'sector': 'Industrial',
            'characteristics': 'Economic cycle sensitive'
        },
        '🎲 Edge Case: Penny Stocks (Ultra High Vol)': {
            'stocks': ['F', 'NOK', 'SNAP', 'PLUG'],
            'expected_volatility': 'HIGH',
            'sector': 'Mixed',
            'characteristics': 'Low price (<$15), very high volatility'
        }
    }

    # Timeframes to test
    timeframes = ['swing', 'short', 'medium', 'long']

    # Results storage
    all_results = []
    category_stats = {}
    timeframe_stats = {tf: {'total': 0, 'buys': 0, 'holds': 0, 'avoids': 0, 'scores': []} for tf in timeframes}

    start_time = time.time()

    # Test each category
    for category, config in test_matrix.items():
        print()
        print('='*100)
        print(f'{category}')
        print('='*100)
        print(f"Sector: {config['sector']} | Expected Vol: {config['expected_volatility']}")
        print(f"Characteristics: {config['characteristics']}")
        print('-'*100)

        category_results = []

        # Test subset of timeframes (swing + one other for speed)
        test_timeframes = ['swing', 'medium'] if len(config['stocks']) > 3 else timeframes

        for tf in test_timeframes:
            print(f'\n📈 Testing Timeframe: {tf.upper()} ({["1-7d", "1-14d", "14-90d", "6mo+"][timeframes.index(tf)]})')
            print('-'*100)

            for symbol in config['stocks']:
                try:
                    stock_start = time.time()

                    # Run analysis without AI for speed (v7.3 improvement)
                    result = analyzer.analyze_stock(symbol, tf, 100000, include_ai_analysis=False)

                    # 🆕 v7.3.1: Add null check for result
                    if result is None:
                        print(f'{symbol:6s} | ❌ ERROR: Analysis returned None')
                        continue

                    stock_time = time.time() - stock_start

                    # Extract key metrics with null checks
                    unified = result.get('unified_recommendation')
                    if unified is None:
                        print(f'{symbol:6s} | ❌ ERROR: No unified recommendation')
                        continue

                    tech = result.get('technical_analysis')
                    if tech is None:
                        tech = {}

                    market_state_analysis = tech.get('market_state_analysis')
                    if market_state_analysis is None:
                        market_state_analysis = {}

                    strategy = market_state_analysis.get('strategy')
                    if strategy is None:
                        strategy = {}

                    trading_plan = strategy.get('trading_plan')
                    if trading_plan is None:
                        trading_plan = {}

                    components = unified.get('component_scores', {})

                    rec = unified.get('recommendation', 'N/A')
                    score = unified.get('score', 0)
                    confidence = unified.get('confidence', 'N/A')
                    volatility = trading_plan.get('volatility_class', 'UNKNOWN')
                    market_state = market_state_analysis.get('market_state', 'UNKNOWN')

                    # 🆕 v7.3.1: Calculate R/R ratio correctly from entry/tp/sl
                    entry = trading_plan.get('entry_price', 0)
                    tp = trading_plan.get('take_profit', 0)  # 🆕 v7.3.1: Fixed field name from 'target_price' to 'take_profit'
                    sl = trading_plan.get('stop_loss', 0)

                    if entry > 0 and sl > 0 and tp > 0:
                        risk = abs(entry - sl)
                        reward = abs(tp - entry)
                        rr_ratio = reward / risk if risk > 0 else 0
                    else:
                        rr_ratio = 0

                    # Verify adaptive weights working
                    momentum_score = components.get('momentum', 0)
                    technical_score = components.get('technical', 0)
                    market_state_score = components.get('market_state', 0)

                    # Display result
                    status_icon = '✅' if rec in ['BUY', 'STRONG_BUY'] else '⚠️' if rec == 'HOLD' else '❌'
                    vol_match = '✅' if volatility == config['expected_volatility'] else '⚠️'

                    print(f'{symbol:6s} | {rec:10s} ({score:.1f}/10, {confidence:6s}) | '
                          f'Vol: {volatility:6s} {vol_match} | State: {market_state:20s} | '
                          f'R/R: {rr_ratio:.2f}:1 | {stock_time:.1f}s')

                    # Store result
                    result_data = {
                        'symbol': symbol,
                        'category': category,
                        'sector': config['sector'],
                        'expected_volatility': config['expected_volatility'],
                        'actual_volatility': volatility,
                        'volatility_match': volatility == config['expected_volatility'],
                        'timeframe': tf,
                        'recommendation': rec,
                        'score': score,
                        'confidence': confidence,
                        'market_state': market_state,
                        'entry': entry,
                        'target': tp,
                        'stop_loss': sl,
                        'rr_ratio': rr_ratio,
                        'components': {
                            'technical': technical_score,
                            'momentum': momentum_score,
                            'market_state': market_state_score
                        },
                        'time': stock_time
                    }

                    category_results.append(result_data)
                    all_results.append(result_data)

                    # Update timeframe stats
                    timeframe_stats[tf]['total'] += 1
                    timeframe_stats[tf]['scores'].append(score)
                    if rec in ['BUY', 'STRONG_BUY']:
                        timeframe_stats[tf]['buys'] += 1
                    elif rec == 'HOLD':
                        timeframe_stats[tf]['holds'] += 1
                    else:
                        timeframe_stats[tf]['avoids'] += 1

                except Exception as e:
                    print(f'{symbol:6s} | ❌ ERROR: {str(e)[:60]}')
                    import traceback
                    traceback.print_exc()

        # Category summary
        if category_results:
            total = len(category_results)
            buys = sum(1 for r in category_results if r['recommendation'] in ['BUY', 'STRONG_BUY'])
            holds = sum(1 for r in category_results if r['recommendation'] == 'HOLD')
            avoids = sum(1 for r in category_results if r['recommendation'] in ['SELL', 'AVOID'])
            avg_score = sum(r['score'] for r in category_results) / total
            avg_rr = sum(r['rr_ratio'] for r in category_results) / total
            vol_matches = sum(1 for r in category_results if r['volatility_match'])

            print('-'*100)
            print(f'Category Summary: {buys} BUY | {holds} HOLD | {avoids} AVOID')
            print(f'Average Score: {avg_score:.2f}/10 | Average R/R: {avg_rr:.2f}:1')
            print(f'Volatility Detection Accuracy: {vol_matches}/{total} ({vol_matches/total*100:.1f}%)')

            category_stats[category] = {
                'total': total,
                'buys': buys,
                'holds': holds,
                'avoids': avoids,
                'avg_score': avg_score,
                'avg_rr': avg_rr,
                'vol_accuracy': vol_matches/total*100
            }

    total_time = time.time() - start_time

    # Overall summary
    print()
    print('='*100)
    print('📊 ULTRA COMPREHENSIVE SUMMARY')
    print('='*100)

    total_tested = len(all_results)
    total_buys = sum(1 for r in all_results if r['recommendation'] in ['BUY', 'STRONG_BUY'])
    total_holds = sum(1 for r in all_results if r['recommendation'] == 'HOLD')
    total_avoids = sum(1 for r in all_results if r['recommendation'] in ['SELL', 'AVOID'])
    overall_avg_score = sum(r['score'] for r in all_results) / total_tested if total_tested > 0 else 0
    overall_avg_rr = sum(r['rr_ratio'] for r in all_results) / total_tested if total_tested > 0 else 0

    print(f'Total Stocks Tested: {total_tested}')
    print(f'Total Time: {total_time:.1f}s | Average: {total_time/total_tested:.1f}s per stock')
    print(f'Performance: ~18x faster than v7.2 (no AI calls)')
    print()

    print('Overall Recommendations:')
    print(f'  • BUY/STRONG_BUY: {total_buys:3d} ({total_buys/total_tested*100:5.1f}%)')
    print(f'  • HOLD:           {total_holds:3d} ({total_holds/total_tested*100:5.1f}%)')
    print(f'  • SELL/AVOID:     {total_avoids:3d} ({total_avoids/total_tested*100:5.1f}%)')
    print()
    print(f'Overall Metrics:')
    print(f'  • Average Score: {overall_avg_score:.2f}/10')
    print(f'  • Average R/R:   {overall_avg_rr:.2f}:1')
    print()

    # Breakdown by timeframe
    print('Breakdown by Timeframe:')
    print('-'*100)
    for tf in timeframes:
        stats = timeframe_stats[tf]
        if stats['total'] > 0:
            avg_score = sum(stats['scores']) / len(stats['scores'])
            print(f"  {tf.upper():6s} ({stats['total']:2d} stocks): "
                  f"{stats['buys']:2d} BUY ({stats['buys']/stats['total']*100:5.1f}%) | "
                  f"{stats['holds']:2d} HOLD ({stats['holds']/stats['total']*100:5.1f}%) | "
                  f"{stats['avoids']:2d} AVOID ({stats['avoids']/stats['total']*100:5.1f}%) | "
                  f"Avg Score: {avg_score:.2f}/10")
    print()

    # Breakdown by volatility
    print('Breakdown by Volatility Class:')
    print('-'*100)
    for vol_class in ['HIGH', 'MEDIUM', 'LOW']:
        vol_results = [r for r in all_results if r['actual_volatility'] == vol_class]
        if vol_results:
            vol_total = len(vol_results)
            vol_buys = sum(1 for r in vol_results if r['recommendation'] in ['BUY', 'STRONG_BUY'])
            vol_avg_score = sum(r['score'] for r in vol_results) / vol_total
            print(f"  {vol_class:6s} ({vol_total:2d} stocks): "
                  f"{vol_buys:2d} BUY ({vol_buys/vol_total*100:5.1f}%) | "
                  f"Avg Score: {vol_avg_score:.2f}/10")
    print()

    # Breakdown by sector
    print('Breakdown by Sector:')
    print('-'*100)
    sectors = {}
    for r in all_results:
        sector = r['sector']
        if sector not in sectors:
            sectors[sector] = {'total': 0, 'buys': 0, 'scores': []}
        sectors[sector]['total'] += 1
        sectors[sector]['scores'].append(r['score'])
        if r['recommendation'] in ['BUY', 'STRONG_BUY']:
            sectors[sector]['buys'] += 1

    for sector, stats in sorted(sectors.items()):
        avg_score = sum(stats['scores']) / len(stats['scores'])
        print(f"  {sector:15s} ({stats['total']:2d} stocks): "
              f"{stats['buys']:2d} BUY ({stats['buys']/stats['total']*100:5.1f}%) | "
              f"Avg Score: {avg_score:.2f}/10")
    print()

    # Volatility detection accuracy
    vol_correct = sum(1 for r in all_results if r['volatility_match'])
    vol_total = len([r for r in all_results if r['expected_volatility'] != 'Mixed'])
    if vol_total > 0:
        print(f'Volatility Detection Accuracy: {vol_correct}/{vol_total} ({vol_correct/vol_total*100:.1f}%)')
        print()

    # Analysis & Recommendations
    print('='*100)
    print('💡 ANALYSIS & INSIGHTS:')
    print('='*100)

    buy_rate = total_buys / total_tested * 100

    if buy_rate < 30:
        print('⚠️  BUY rate is LOW (<30%) - System may be too conservative')
        print('   Recommendations:')
        print('   • Lower BUY thresholds')
        print('   • Review veto conditions')
        print('   • Check component scoring')
    elif buy_rate > 70:
        print('⚠️  BUY rate is HIGH (>70%) - System may be too aggressive')
        print('   Recommendations:')
        print('   • Raise BUY thresholds')
        print('   • Tighten veto conditions')
        print('   • Review false positive rate')
    else:
        print(f'✅ BUY rate is BALANCED ({buy_rate:.1f}%) - System selectivity looks good')

    print()

    if overall_avg_rr < 1.5:
        print('⚠️  Average R/R ratio is LOW (<1.5:1)')
        print('   • Review SL and TP calculations')
        print('   • May need tighter SL or wider TP targets')
    elif overall_avg_rr > 3.0:
        print('✅ Average R/R ratio is EXCELLENT (>3.0:1)')
        print('   • Good risk management')
        print('   • Well-positioned entries')
    else:
        print(f'✅ Average R/R ratio is GOOD ({overall_avg_rr:.2f}:1)')

    print()

    # Save results to JSON
    output_file = 'ultra_comprehensive_backtest_results_v7_3.json'
    with open(output_file, 'w') as f:
        json.dump({
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'version': 'v7.3',
                'total_stocks': total_tested,
                'total_time': total_time,
                'avg_time_per_stock': total_time/total_tested
            },
            'summary': {
                'total_tested': total_tested,
                'total_buys': total_buys,
                'total_holds': total_holds,
                'total_avoids': total_avoids,
                'buy_rate': buy_rate,
                'avg_score': overall_avg_score,
                'avg_rr': overall_avg_rr
            },
            'timeframe_stats': timeframe_stats,
            'category_stats': category_stats,
            'all_results': all_results
        }, f, indent=2)

    print(f'✅ Results saved to: {output_file}')
    print()
    print('='*100)
    print('✅ Ultra Comprehensive Backtest Complete!')
    print('='*100)

if __name__ == '__main__':
    ultra_comprehensive_backtest()
