#!/usr/bin/env python3
"""
Quick Validation Backtest for v7.3.1
Tests recommendation accuracy with focused stock selection
"""
import sys
import os
from datetime import datetime
import time

# Setup paths
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from src.main import StockAnalyzer

def test_stock(symbol, time_horizon, capital=100000):
    """Test a single stock"""
    try:
        analyzer = StockAnalyzer()
        result = analyzer.analyze_stock(symbol, time_horizon, capital)

        if not result or result.get('error'):
            return None

        unified = result.get('unified_recommendation', {})
        if not unified:
            return None

        trading_plan = unified.get('trading_plan', {})

        # Calculate R/R
        entry = trading_plan.get('entry_price')
        tp = trading_plan.get('take_profit')
        sl = trading_plan.get('stop_loss')
        rr = 0
        if entry and tp and sl and entry > 0:
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = reward / risk if risk > 0 else 0

        return {
            'symbol': symbol,
            'time_horizon': time_horizon,
            'recommendation': unified.get('recommendation', 'UNKNOWN'),
            'score': unified.get('score', 0),
            'confidence': unified.get('confidence', 'UNKNOWN'),
            'volatility': trading_plan.get('volatility_class', 'UNKNOWN'),
            'rr_ratio': rr
        }
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def run_quick_backtest():
    """Run quick focused backtest"""
    print("\n" + "="*80)
    print("QUICK VALIDATION BACKTEST v7.3.1")
    print("="*80)
    print(f"Start: {datetime.now()}\n")

    # Focused test set - diverse but smaller
    stocks = {
        'High Vol': ['PLTR', 'NVDA', 'TSLA'],
        'Med Vol': ['AAPL', 'MSFT', 'GOOGL'],
        'Low Vol': ['JNJ', 'PG', 'KO'],
        'Finance': ['JPM', 'BAC'],
        'Energy': ['XOM', 'CVX'],
    }

    time_horizons = ['swing', 'short', 'medium', 'long']

    results = []
    stats = {th: {'total': 0, 'buy': 0, 'scores': [], 'rr': []} for th in time_horizons}
    vol_stats = {v: {'total': 0, 'buy': 0} for v in ['HIGH', 'MEDIUM', 'LOW']}

    start_time = time.time()
    total_tests = sum(len(s) for s in stocks.values()) * len(time_horizons)
    current = 0

    for sector, symbols in stocks.items():
        print(f"\n{'='*60}")
        print(f"SECTOR: {sector}")
        print(f"{'='*60}")

        for symbol in symbols:
            for th in time_horizons:
                current += 1
                elapsed = time.time() - start_time
                eta = (total_tests - current) * (elapsed / current) if current > 0 else 0

                print(f"[{current}/{total_tests}] {symbol} {th.upper()} | ETA: {eta/60:.1f}m", end=' ')

                result = test_stock(symbol, th)

                if result:
                    results.append(result)
                    rec = result['recommendation']
                    vol = result['volatility']

                    # Update stats by time_horizon
                    stats[th]['total'] += 1
                    if rec in ['BUY', 'STRONG_BUY']:
                        stats[th]['buy'] += 1
                    stats[th]['scores'].append(result['score'])
                    if result['rr_ratio'] > 0:
                        stats[th]['rr'].append(result['rr_ratio'])

                    # Update vol stats
                    if vol in vol_stats:
                        vol_stats[vol]['total'] += 1
                        if rec in ['BUY', 'STRONG_BUY']:
                            vol_stats[vol]['buy'] += 1

                    print(f"✅ {rec} {result['score']:.1f}/10 ({vol})")
                else:
                    print("❌ Failed")

                time.sleep(0.3)  # Rate limiting

    # Print Results
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)

    total_time = time.time() - start_time
    print(f"\nTotal Time: {total_time/60:.1f} min ({len(results)} tests, {total_time/len(results):.1f}s/test)")

    print("\n📊 BY TIME HORIZON:")
    print("-" * 60)
    for th in time_horizons:
        s = stats[th]
        if s['total'] == 0:
            continue
        buy_rate = s['buy'] / s['total'] * 100
        avg_score = sum(s['scores']) / len(s['scores']) if s['scores'] else 0
        avg_rr = sum(s['rr']) / len(s['rr']) if s['rr'] else 0
        print(f"{th.upper():8} | BUY: {buy_rate:5.1f}% | Score: {avg_score:.2f}/10 | R/R: {avg_rr:.2f}:1 | Tests: {s['total']}")

    print("\n📈 BY VOLATILITY:")
    print("-" * 60)
    for vol in ['HIGH', 'MEDIUM', 'LOW']:
        s = vol_stats[vol]
        if s['total'] == 0:
            continue
        buy_rate = s['buy'] / s['total'] * 100
        print(f"{vol:7} | BUY Rate: {buy_rate:5.1f}% | Tests: {s['total']}")

    # Key insights
    all_buy = sum(1 for r in results if r['recommendation'] in ['BUY', 'STRONG_BUY'])
    overall_buy_rate = all_buy / len(results) * 100
    all_scores = [r['score'] for r in results]
    avg_score = sum(all_scores) / len(all_scores)
    all_rr = [r['rr_ratio'] for r in results if r['rr_ratio'] > 0]
    avg_rr = sum(all_rr) / len(all_rr) if all_rr else 0

    print("\n🎯 KEY INSIGHTS:")
    print("-" * 60)
    print(f"Overall BUY Rate: {overall_buy_rate:.1f}%")
    print(f"Average Score: {avg_score:.2f}/10")
    print(f"Average R/R: {avg_rr:.2f}:1")

    swing_buy = stats['swing']['buy'] / stats['swing']['total'] * 100 if stats['swing']['total'] > 0 else 0
    long_buy = stats['long']['buy'] / stats['long']['total'] * 100 if stats['long']['total'] > 0 else 0
    print(f"\nSwing (most aggressive): {swing_buy:.1f}% BUY")
    print(f"Long (most conservative): {long_buy:.1f}% BUY")

    high_buy = vol_stats['HIGH']['buy'] / vol_stats['HIGH']['total'] * 100 if vol_stats['HIGH']['total'] > 0 else 0
    low_buy = vol_stats['LOW']['buy'] / vol_stats['LOW']['total'] * 100 if vol_stats['LOW']['total'] > 0 else 0
    print(f"\nHIGH volatility: {high_buy:.1f}% BUY")
    print(f"LOW volatility: {low_buy:.1f}% BUY")

    # Save results
    import json
    output_file = f"quick_backtest_v7_3_1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump({
            'metadata': {
                'version': 'v7.3.1',
                'timestamp': datetime.now().isoformat(),
                'total_tests': len(results),
                'total_time_minutes': total_time / 60
            },
            'results': results,
            'summary': {
                'overall_buy_rate': overall_buy_rate,
                'avg_score': avg_score,
                'avg_rr': avg_rr,
                'by_time_horizon': {
                    th: {
                        'buy_rate': s['buy'] / s['total'] * 100 if s['total'] > 0 else 0,
                        'avg_score': sum(s['scores']) / len(s['scores']) if s['scores'] else 0,
                        'avg_rr': sum(s['rr']) / len(s['rr']) if s['rr'] else 0
                    }
                    for th, s in stats.items()
                },
                'by_volatility': {
                    vol: {
                        'buy_rate': s['buy'] / s['total'] * 100 if s['total'] > 0 else 0
                    }
                    for vol, s in vol_stats.items() if s['total'] > 0
                }
            }
        }, f, indent=2)

    print(f"\n✅ Results saved to: {output_file}")
    print("\n" + "="*80)
    print(f"End: {datetime.now()}")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_quick_backtest()
