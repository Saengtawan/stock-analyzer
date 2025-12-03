"""
Comprehensive Backtest for v7.0 System
Tests multiple stocks × multiple timeframes to verify improvements
"""
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger
import json

sys.path.insert(0, str(Path(__file__).parent))
from backtest_analyzer import BacktestAnalyzer


def comprehensive_backtest():
    """
    Run comprehensive backtest covering:
    - Multiple stock types (swing, regular, high volatility)
    - Multiple timeframes (short, medium, long)
    - 30-day period with 7-day intervals (5 tests per stock per timeframe)
    """

    # Define test cases
    test_stocks = {
        'Swing Stocks (HIGH PRIORITY - Expected 0% → 70-80%)': [
            'PLTR',  # Palantir - High volatility swing
            'SOFI',  # SoFi - Medium-high volatility swing
        ],
        'Regular Stocks (Expected 40-60% → 65-70%)': [
            'AAPL',  # Apple - Low volatility
            'NVDA',  # Nvidia - Medium volatility
            'MSFT',  # Microsoft - Low-medium volatility
        ],
        'High Volatility Stocks': [
            'TSLA',  # Tesla - High volatility
        ]
    }

    timeframes = ['short', 'medium', 'long']

    backtester = BacktestAnalyzer()

    all_results = {}
    summary = {
        'total_tests': 0,
        'by_stock_type': {},
        'by_timeframe': {},
        'by_stock': {}
    }

    logger.info("=" * 100)
    logger.info("🚀 COMPREHENSIVE BACKTEST v7.0")
    logger.info("=" * 100)
    logger.info("Test Configuration:")
    logger.info("  Period: 30 days back")
    logger.info("  Interval: 7 days")
    logger.info("  Tests per stock per timeframe: ~5")
    logger.info("  Total stocks: 6")
    logger.info("  Total timeframes: 3")
    logger.info(f"  Expected total tests: ~90")
    logger.info("=" * 100 + "\n")

    # Run tests for each stock type
    for stock_type, symbols in test_stocks.items():
        logger.info(f"\n{'=' * 100}")
        logger.info(f"📊 Testing: {stock_type}")
        logger.info(f"{'=' * 100}\n")

        type_results = {
            'stocks': {},
            'aggregate': {}
        }

        for symbol in symbols:
            logger.info(f"\n{'─' * 100}")
            logger.info(f"🔍 Stock: {symbol}")
            logger.info(f"{'─' * 100}\n")

            stock_results = {}

            for timeframe in timeframes:
                logger.info(f"\n  ⏱️  Timeframe: {timeframe.upper()}")
                logger.info(f"  {'─' * 80}\n")

                # Run backtest
                results = backtester.backtest_multiple(
                    symbol=symbol,
                    days_back=30,
                    interval_days=7,
                    time_horizon=timeframe
                )

                # Store results
                stock_results[timeframe] = results

                # Update summary
                if timeframe not in summary['by_timeframe']:
                    summary['by_timeframe'][timeframe] = {
                        'total': 0,
                        'correct': 0,
                        'wins': 0,
                        'avg_return': 0,
                        'tp_hits': 0,
                        'sl_hits': 0
                    }

                tf_summary = summary['by_timeframe'][timeframe]
                tf_summary['total'] += len(results)
                tf_summary['correct'] += sum(1 for r in results if r['recommendation_correct'])
                tf_summary['wins'] += sum(1 for r in results if r['actual_performance']['return_pct'] > 0)
                tf_summary['avg_return'] += sum(r['actual_performance']['return_pct'] for r in results)
                tf_summary['tp_hits'] += sum(1 for r in results if r['actual_performance']['tp_hit'])
                tf_summary['sl_hits'] += sum(1 for r in results if r['actual_performance']['sl_hit'])

                summary['total_tests'] += len(results)

            type_results['stocks'][symbol] = stock_results

            # Stock-level summary
            all_stock_results = []
            for tf_results in stock_results.values():
                all_stock_results.extend(tf_results)

            if symbol not in summary['by_stock']:
                summary['by_stock'][symbol] = {
                    'total': len(all_stock_results),
                    'correct': sum(1 for r in all_stock_results if r['recommendation_correct']),
                    'wins': sum(1 for r in all_stock_results if r['actual_performance']['return_pct'] > 0),
                    'avg_return': sum(r['actual_performance']['return_pct'] for r in all_stock_results) / len(all_stock_results) if all_stock_results else 0,
                    'tp_hits': sum(1 for r in all_stock_results if r['actual_performance']['tp_hit']),
                    'sl_hits': sum(1 for r in all_stock_results if r['actual_performance']['sl_hit'])
                }

        all_results[stock_type] = type_results

    # Calculate final aggregates
    for timeframe, stats in summary['by_timeframe'].items():
        if stats['total'] > 0:
            stats['avg_return'] = stats['avg_return'] / stats['total']

    # Print comprehensive summary
    print_comprehensive_summary(summary, all_results)

    # Save results to file
    save_results(all_results, summary)

    return all_results, summary


def print_comprehensive_summary(summary, all_results):
    """Print comprehensive summary of all tests"""
    logger.info("\n" + "=" * 100)
    logger.info("📊 COMPREHENSIVE BACKTEST SUMMARY (v7.0)")
    logger.info("=" * 100)

    # Overall statistics
    logger.info(f"\n🎯 OVERALL RESULTS:")
    logger.info(f"  Total Tests Run: {summary['total_tests']}")

    # By Stock Type
    logger.info(f"\n📈 RESULTS BY STOCK TYPE:")
    logger.info("-" * 100)

    for stock_type, type_data in all_results.items():
        logger.info(f"\n{stock_type}")

        # Aggregate for this type
        type_total = 0
        type_correct = 0
        type_wins = 0
        type_avg_return = 0
        type_tp_hits = 0

        for symbol, stock_data in type_data['stocks'].items():
            stock_stats = summary['by_stock'][symbol]
            type_total += stock_stats['total']
            type_correct += stock_stats['correct']
            type_wins += stock_stats['wins']
            type_avg_return += stock_stats['avg_return'] * stock_stats['total']
            type_tp_hits += stock_stats['tp_hits']

        if type_total > 0:
            type_avg_return = type_avg_return / type_total

            logger.info(f"  Recommendation Accuracy: {type_correct}/{type_total} ({type_correct/type_total*100:.1f}%)")
            logger.info(f"  Win Rate: {type_wins}/{type_total} ({type_wins/type_total*100:.1f}%)")
            logger.info(f"  Average Return: {type_avg_return:+.2f}%")
            logger.info(f"  TP Hit Rate: {type_tp_hits}/{type_total} ({type_tp_hits/type_total*100:.1f}%)")

    # By Stock
    logger.info(f"\n📊 RESULTS BY STOCK:")
    logger.info("-" * 100)
    logger.info(f"{'Stock':<8} {'Tests':<8} {'Rec Acc':<12} {'Win Rate':<12} {'Avg Return':<12} {'TP Hit':<12}")
    logger.info("-" * 100)

    for symbol, stats in summary['by_stock'].items():
        rec_acc = f"{stats['correct']}/{stats['total']} ({stats['correct']/stats['total']*100:.1f}%)"
        win_rate = f"{stats['wins']}/{stats['total']} ({stats['wins']/stats['total']*100:.1f}%)"
        avg_ret = f"{stats['avg_return']:+.2f}%"
        tp_hit = f"{stats['tp_hits']}/{stats['total']} ({stats['tp_hits']/stats['total']*100:.1f}%)"

        logger.info(f"{symbol:<8} {stats['total']:<8} {rec_acc:<12} {win_rate:<12} {avg_ret:<12} {tp_hit:<12}")

    # By Timeframe
    logger.info(f"\n⏱️  RESULTS BY TIMEFRAME:")
    logger.info("-" * 100)
    logger.info(f"{'Timeframe':<12} {'Tests':<8} {'Rec Acc':<12} {'Win Rate':<12} {'Avg Return':<12} {'TP Hit':<12}")
    logger.info("-" * 100)

    for timeframe, stats in summary['by_timeframe'].items():
        rec_acc = f"{stats['correct']}/{stats['total']} ({stats['correct']/stats['total']*100:.1f}%)"
        win_rate = f"{stats['wins']}/{stats['total']} ({stats['wins']/stats['total']*100:.1f}%)"
        avg_ret = f"{stats['avg_return']:+.2f}%"
        tp_hit = f"{stats['tp_hits']}/{stats['total']} ({stats['tp_hits']/stats['total']*100:.1f}%)"

        logger.info(f"{timeframe.upper():<12} {stats['total']:<8} {rec_acc:<12} {win_rate:<12} {avg_ret:<12} {tp_hit:<12}")

    # Key Insights
    logger.info(f"\n💡 KEY INSIGHTS:")
    logger.info("-" * 100)

    # Check swing stocks improvement
    if 'PLTR' in summary['by_stock'] and 'SOFI' in summary['by_stock']:
        pltr_acc = summary['by_stock']['PLTR']['correct'] / summary['by_stock']['PLTR']['total'] * 100
        sofi_acc = summary['by_stock']['SOFI']['correct'] / summary['by_stock']['SOFI']['total'] * 100
        avg_swing_acc = (pltr_acc + sofi_acc) / 2

        logger.info(f"  🎯 Swing Stocks (PLTR, SOFI) Accuracy: {avg_swing_acc:.1f}%")
        if avg_swing_acc >= 70:
            logger.info(f"     ✅ TARGET MET! (Expected 70-80%, Got {avg_swing_acc:.1f}%)")
        elif avg_swing_acc >= 50:
            logger.info(f"     ⚠️  IMPROVED but below target (Expected 70-80%, Got {avg_swing_acc:.1f}%)")
        else:
            logger.info(f"     ❌ BELOW EXPECTATIONS (Expected 70-80%, Got {avg_swing_acc:.1f}%)")

    # Overall accuracy
    overall_correct = sum(stats['correct'] for stats in summary['by_stock'].values())
    overall_total = sum(stats['total'] for stats in summary['by_stock'].values())
    overall_acc = overall_correct / overall_total * 100 if overall_total > 0 else 0

    logger.info(f"  📊 Overall System Accuracy: {overall_acc:.1f}%")
    if overall_acc >= 68:
        logger.info(f"     ✅ TARGET MET! (Expected 68-72%, Got {overall_acc:.1f}%)")
    elif overall_acc >= 60:
        logger.info(f"     ⚠️  IMPROVED but below target (Expected 68-72%, Got {overall_acc:.1f}%)")
    else:
        logger.info(f"     ❌ BELOW EXPECTATIONS (Expected 68-72%, Got {overall_acc:.1f}%)")

    logger.info("=" * 100 + "\n")


def save_results(all_results, summary):
    """Save results to JSON file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'backtest_results_v7_{timestamp}.json'

    output = {
        'timestamp': timestamp,
        'version': 'v7.0',
        'summary': summary,
        'detailed_results': all_results
    }

    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    logger.info(f"📝 Results saved to: {filename}")


if __name__ == '__main__':
    logger.info("Starting Comprehensive Backtest v7.0...")
    logger.info("This will test 6 stocks × 3 timeframes × ~5 tests = ~90 total tests")
    logger.info("Estimated time: 10-15 minutes\n")

    comprehensive_backtest()
