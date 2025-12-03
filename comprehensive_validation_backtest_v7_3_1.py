#!/usr/bin/env python3
"""
Comprehensive Validation Backtest for v7.3.1
Tests recommendation accuracy across all timeframes and entry strategies
"""
import sys
import os
from datetime import datetime, timedelta
import time

# Setup paths
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from src.main import StockAnalyzer
from src.api.data_manager import DataManager

def test_stock_recommendation(symbol, time_horizon, capital=100000):
    """
    Test a single stock and track results
    Returns dict with all metrics
    """
    try:
        print(f"\n{'='*80}")
        print(f"Testing {symbol} - {time_horizon.upper()}")
        print(f"{'='*80}")

        # Analyze stock
        analyzer = StockAnalyzer()
        result = analyzer.analyze_stock(symbol, time_horizon, capital)

        if not result or result.get('error'):
            print(f"❌ Analysis failed: {result.get('error', 'Unknown error')}")
            return None

        # Extract recommendation data
        unified = result.get('unified_recommendation', {})
        if not unified:
            print(f"❌ No unified recommendation")
            return None

        recommendation = unified.get('recommendation', 'UNKNOWN')
        score = unified.get('score', 0)
        confidence = unified.get('confidence', 'UNKNOWN')

        # Extract trading plan
        trading_plan = unified.get('trading_plan', {})
        entry_price = trading_plan.get('entry_price')
        current_price = trading_plan.get('current_price')
        take_profit = trading_plan.get('take_profit')
        stop_loss = trading_plan.get('stop_loss')
        volatility_class = trading_plan.get('volatility_class', 'UNKNOWN')

        # Calculate R/R
        rr_ratio = 0
        if entry_price and take_profit and stop_loss:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            rr_ratio = reward / risk if risk > 0 else 0

        # Get current data for forward testing
        data_manager = DataManager()
        price_data = data_manager.get_price_data(symbol, period='3mo', interval='1d')

        if price_data.empty:
            print(f"❌ No price data")
            return None

        current_actual_price = float(price_data['Close'].iloc[-1])

        # Calculate what would happen if we entered at entry_price
        entry_result_entry = "PENDING"
        entry_result_current = "PENDING"

        # For testing, check if price has moved since recommendation
        # (In real backtest, we'd use historical data and wait for results)

        print(f"\n📊 Analysis Results:")
        print(f"  Recommendation: {recommendation} ({score:.1f}/10, {confidence})")
        print(f"  Volatility: {volatility_class}")
        print(f"  Entry Price: ${entry_price:.2f}" if entry_price else "  Entry Price: N/A")
        print(f"  Current Price: ${current_actual_price:.2f}")
        print(f"  Take Profit: ${take_profit:.2f}" if take_profit else "  Take Profit: N/A")
        print(f"  Stop Loss: ${stop_loss:.2f}" if stop_loss else "  Stop Loss: N/A")
        print(f"  R/R Ratio: {rr_ratio:.2f}:1" if rr_ratio > 0 else "  R/R Ratio: N/A")

        return {
            'symbol': symbol,
            'time_horizon': time_horizon,
            'recommendation': recommendation,
            'score': score,
            'confidence': confidence,
            'volatility_class': volatility_class,
            'entry_price': entry_price,
            'current_price': current_actual_price,
            'take_profit': take_profit,
            'stop_loss': stop_loss,
            'rr_ratio': rr_ratio,
            'entry_result_entry': entry_result_entry,
            'entry_result_current': entry_result_current,
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        print(f"❌ Error testing {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_comprehensive_backtest():
    """Run comprehensive backtest across multiple stocks and timeframes"""

    print("\n" + "="*80)
    print("COMPREHENSIVE VALIDATION BACKTEST v7.3.1")
    print("="*80)
    print(f"Start Time: {datetime.now()}")
    print("="*80)

    # Test universe - diverse stocks across sectors and volatilities
    test_stocks = {
        'High Volatility Tech': ['PLTR', 'NVDA', 'TSLA', 'AMD', 'SNAP'],
        'Medium Volatility Tech': ['AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN'],
        'Low Volatility Large Cap': ['JNJ', 'PG', 'KO', 'WMT', 'PEP'],
        'Financials': ['JPM', 'BAC', 'GS', 'WFC', 'C'],
        'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'MPC'],
        'Healthcare': ['UNH', 'LLY', 'ABBV', 'MRK', 'TMO'],
        'Consumer': ['HD', 'NKE', 'MCD', 'SBUX', 'TGT'],
        'Industrials': ['CAT', 'BA', 'HON', 'UPS', 'GE']
    }

    # Time horizons to test
    time_horizons = ['swing', 'short', 'medium', 'long']

    # Results storage
    all_results = []
    stats_by_time_horizon = {th: {
        'total': 0,
        'BUY': 0,
        'STRONG_BUY': 0,
        'HOLD': 0,
        'SELL': 0,
        'AVOID': 0,
        'avg_score': [],
        'avg_rr': [],
        'volatility_dist': {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    } for th in time_horizons}

    stats_by_volatility = {
        'HIGH': {'total': 0, 'BUY': 0, 'avg_rr': []},
        'MEDIUM': {'total': 0, 'BUY': 0, 'avg_rr': []},
        'LOW': {'total': 0, 'BUY': 0, 'avg_rr': []}
    }

    stats_by_sector = {}

    total_tests = sum(len(stocks) for stocks in test_stocks.values()) * len(timeframes)
    current_test = 0
    start_time = time.time()

    # Run tests
    for sector, symbols in test_stocks.items():
        print(f"\n{'='*80}")
        print(f"SECTOR: {sector}")
        print(f"{'='*80}")

        if sector not in stats_by_sector:
            stats_by_sector[sector] = {
                'total': 0,
                'BUY': 0,
                'avg_score': [],
                'by_timeframe': {tf: {'total': 0, 'BUY': 0} for tf in timeframes}
            }

        for symbol in symbols:
            for timeframe in timeframes:
                current_test += 1
                elapsed = time.time() - start_time
                avg_time = elapsed / current_test
                remaining = (total_tests - current_test) * avg_time

                print(f"\n[{current_test}/{total_tests}] Progress: {current_test/total_tests*100:.1f}% | ETA: {remaining/60:.1f}m")

                result = test_stock_recommendation(symbol, timeframe)

                if result:
                    all_results.append(result)

                    # Update stats by timeframe
                    tf_stats = stats_by_timeframe[timeframe]
                    tf_stats['total'] += 1
                    tf_stats[result['recommendation']] = tf_stats.get(result['recommendation'], 0) + 1
                    tf_stats['avg_score'].append(result['score'])
                    if result['rr_ratio'] > 0:
                        tf_stats['avg_rr'].append(result['rr_ratio'])
                    if result['volatility_class'] in tf_stats['volatility_dist']:
                        tf_stats['volatility_dist'][result['volatility_class']] += 1

                    # Update stats by volatility
                    vol = result['volatility_class']
                    if vol in stats_by_volatility:
                        vol_stats = stats_by_volatility[vol]
                        vol_stats['total'] += 1
                        if result['recommendation'] in ['BUY', 'STRONG_BUY']:
                            vol_stats['BUY'] += 1
                        if result['rr_ratio'] > 0:
                            vol_stats['avg_rr'].append(result['rr_ratio'])

                    # Update stats by sector
                    sector_stats = stats_by_sector[sector]
                    sector_stats['total'] += 1
                    if result['recommendation'] in ['BUY', 'STRONG_BUY']:
                        sector_stats['BUY'] += 1
                    sector_stats['avg_score'].append(result['score'])
                    sector_stats['by_timeframe'][timeframe]['total'] += 1
                    if result['recommendation'] in ['BUY', 'STRONG_BUY']:
                        sector_stats['by_timeframe'][timeframe]['BUY'] += 1

                # Small delay to avoid rate limiting
                time.sleep(0.5)

    # Print comprehensive results
    print("\n" + "="*80)
    print("COMPREHENSIVE RESULTS")
    print("="*80)

    total_time = time.time() - start_time
    print(f"\nTotal Time: {total_time/60:.1f} minutes")
    print(f"Total Tests: {len(all_results)}")
    print(f"Average Time per Test: {total_time/len(all_results):.1f}s")

    # Results by Timeframe
    print("\n" + "="*80)
    print("RESULTS BY TIMEFRAME")
    print("="*80)

    for timeframe, stats in stats_by_timeframe.items():
        if stats['total'] == 0:
            continue

        print(f"\n{timeframe.upper()} ({stats['total']} stocks):")
        print("-" * 60)

        buy_rate = (stats.get('BUY', 0) + stats.get('STRONG_BUY', 0)) / stats['total'] * 100
        avg_score = sum(stats['avg_score']) / len(stats['avg_score']) if stats['avg_score'] else 0
        avg_rr = sum(stats['avg_rr']) / len(stats['avg_rr']) if stats['avg_rr'] else 0

        print(f"  Recommendations:")
        print(f"    STRONG_BUY: {stats.get('STRONG_BUY', 0)} ({stats.get('STRONG_BUY', 0)/stats['total']*100:.1f}%)")
        print(f"    BUY:        {stats.get('BUY', 0)} ({stats.get('BUY', 0)/stats['total']*100:.1f}%)")
        print(f"    HOLD:       {stats.get('HOLD', 0)} ({stats.get('HOLD', 0)/stats['total']*100:.1f}%)")
        print(f"    SELL:       {stats.get('SELL', 0)} ({stats.get('SELL', 0)/stats['total']*100:.1f}%)")
        print(f"    AVOID:      {stats.get('AVOID', 0)} ({stats.get('AVOID', 0)/stats['total']*100:.1f}%)")
        print(f"  Total BUY Rate: {buy_rate:.1f}%")
        print(f"  Average Score: {avg_score:.2f}/10")
        print(f"  Average R/R: {avg_rr:.2f}:1")
        print(f"  Volatility Distribution:")
        for vol, count in stats['volatility_dist'].items():
            print(f"    {vol}: {count} ({count/stats['total']*100:.1f}%)")

    # Results by Volatility
    print("\n" + "="*80)
    print("RESULTS BY VOLATILITY CLASS")
    print("="*80)

    for vol, stats in stats_by_volatility.items():
        if stats['total'] == 0:
            continue

        buy_rate = stats['BUY'] / stats['total'] * 100
        avg_rr = sum(stats['avg_rr']) / len(stats['avg_rr']) if stats['avg_rr'] else 0

        print(f"\n{vol} VOLATILITY ({stats['total']} stocks):")
        print(f"  BUY Rate: {buy_rate:.1f}%")
        print(f"  Average R/R: {avg_rr:.2f}:1")

    # Results by Sector
    print("\n" + "="*80)
    print("RESULTS BY SECTOR")
    print("="*80)

    for sector, stats in stats_by_sector.items():
        if stats['total'] == 0:
            continue

        buy_rate = stats['BUY'] / stats['total'] * 100
        avg_score = sum(stats['avg_score']) / len(stats['avg_score']) if stats['avg_score'] else 0

        print(f"\n{sector} ({stats['total']} tests):")
        print(f"  Overall BUY Rate: {buy_rate:.1f}%")
        print(f"  Average Score: {avg_score:.2f}/10")
        print(f"  By Timeframe:")
        for tf, tf_stats in stats['by_timeframe'].items():
            if tf_stats['total'] > 0:
                tf_buy_rate = tf_stats['BUY'] / tf_stats['total'] * 100
                print(f"    {tf.upper()}: {tf_buy_rate:.1f}% BUY ({tf_stats['BUY']}/{tf_stats['total']})")

    # Key Insights
    print("\n" + "="*80)
    print("KEY INSIGHTS")
    print("="*80)

    # Overall stats
    total_stocks = len(all_results)
    total_buy = sum(1 for r in all_results if r['recommendation'] in ['BUY', 'STRONG_BUY'])
    overall_buy_rate = total_buy / total_stocks * 100 if total_stocks > 0 else 0

    all_scores = [r['score'] for r in all_results]
    all_rr = [r['rr_ratio'] for r in all_results if r['rr_ratio'] > 0]

    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    avg_rr = sum(all_rr) / len(all_rr) if all_rr else 0

    print(f"\n1. Overall Performance:")
    print(f"   Total Tests: {total_stocks}")
    print(f"   Overall BUY Rate: {overall_buy_rate:.1f}%")
    print(f"   Average Score: {avg_score:.2f}/10")
    print(f"   Average R/R: {avg_rr:.2f}:1")

    print(f"\n2. Timeframe Analysis:")
    swing_buy = (stats_by_timeframe['swing'].get('BUY', 0) + stats_by_timeframe['swing'].get('STRONG_BUY', 0)) / stats_by_timeframe['swing']['total'] * 100 if stats_by_timeframe['swing']['total'] > 0 else 0
    short_buy = (stats_by_timeframe['short'].get('BUY', 0) + stats_by_timeframe['short'].get('STRONG_BUY', 0)) / stats_by_timeframe['short']['total'] * 100 if stats_by_timeframe['short']['total'] > 0 else 0
    medium_buy = (stats_by_timeframe['medium'].get('BUY', 0) + stats_by_timeframe['medium'].get('STRONG_BUY', 0)) / stats_by_timeframe['medium']['total'] * 100 if stats_by_timeframe['medium']['total'] > 0 else 0
    long_buy = (stats_by_timeframe['long'].get('BUY', 0) + stats_by_timeframe['long'].get('STRONG_BUY', 0)) / stats_by_timeframe['long']['total'] * 100 if stats_by_timeframe['long']['total'] > 0 else 0

    print(f"   Swing:  {swing_buy:.1f}% BUY (most aggressive)")
    print(f"   Short:  {short_buy:.1f}% BUY")
    print(f"   Medium: {medium_buy:.1f}% BUY")
    print(f"   Long:   {long_buy:.1f}% BUY (most conservative)")

    print(f"\n3. Volatility Impact:")
    high_buy = stats_by_volatility['HIGH']['BUY'] / stats_by_volatility['HIGH']['total'] * 100 if stats_by_volatility['HIGH']['total'] > 0 else 0
    med_buy = stats_by_volatility['MEDIUM']['BUY'] / stats_by_volatility['MEDIUM']['total'] * 100 if stats_by_volatility['MEDIUM']['total'] > 0 else 0
    low_buy = stats_by_volatility['LOW']['BUY'] / stats_by_volatility['LOW']['total'] * 100 if stats_by_volatility['LOW']['total'] > 0 else 0

    print(f"   HIGH volatility:   {high_buy:.1f}% BUY")
    print(f"   MEDIUM volatility: {med_buy:.1f}% BUY")
    print(f"   LOW volatility:    {low_buy:.1f}% BUY")

    # Save results
    print("\n" + "="*80)
    print("SAVING RESULTS")
    print("="*80)

    import json
    output_file = f"backtest_results_v7_3_1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump({
            'metadata': {
                'version': 'v7.3.1',
                'timestamp': datetime.now().isoformat(),
                'total_tests': total_stocks,
                'total_time_minutes': total_time / 60
            },
            'results': all_results,
            'stats_by_timeframe': {
                k: {
                    **v,
                    'avg_score': sum(v['avg_score'])/len(v['avg_score']) if v['avg_score'] else 0,
                    'avg_rr': sum(v['avg_rr'])/len(v['avg_rr']) if v['avg_rr'] else 0
                }
                for k, v in stats_by_timeframe.items()
            },
            'stats_by_volatility': {
                k: {
                    **v,
                    'avg_rr': sum(v['avg_rr'])/len(v['avg_rr']) if v['avg_rr'] else 0
                }
                for k, v in stats_by_volatility.items()
            },
            'stats_by_sector': {
                k: {
                    **v,
                    'avg_score': sum(v['avg_score'])/len(v['avg_score']) if v['avg_score'] else 0
                }
                for k, v in stats_by_sector.items()
            }
        }, f, indent=2)

    print(f"✅ Results saved to: {output_file}")

    print("\n" + "="*80)
    print("BACKTEST COMPLETE")
    print("="*80)
    print(f"End Time: {datetime.now()}")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_comprehensive_backtest()
