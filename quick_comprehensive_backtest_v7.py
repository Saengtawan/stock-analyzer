"""
Quick Comprehensive Backtest for v7.0
Tests critical stocks with different timeframes
"""
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent))
from backtest_analyzer import BacktestAnalyzer


def quick_comprehensive_backtest():
    """Run quick but comprehensive backtest on critical stocks"""

    # Define test cases - focus on most critical ones
    test_stocks = {
        'Swing Stocks (CRITICAL - Expected 0% → 70-80%)': ['PLTR', 'SOFI'],
        'Regular Stocks (Expected 40-60% → 65-70%)': ['AAPL', 'NVDA'],
        'High Volatility': ['TSLA']
    }

    timeframes = ['short', 'medium', 'long']

    backtester = BacktestAnalyzer()
    all_results = {}

    logger.info("=" * 100)
    logger.info("🚀 QUICK COMPREHENSIVE BACKTEST v7.0")
    logger.info("=" * 100)
    logger.info("Test Configuration:")
    logger.info("  Period: 21 days back (3 weeks)")
    logger.info("  Interval: 7 days")
    logger.info("  Tests per stock per timeframe: ~3")
    logger.info("  Total stocks: 5")
    logger.info("  Total timeframes: 3")
    logger.info(f"  Expected total tests: ~45")
    logger.info("=" * 100 + "\n")

    # Summary tracking
    summary = {
        'by_stock': {},
        'by_timeframe': {tf: {'total': 0, 'correct': 0, 'wins': 0, 'avg_return': 0, 'tp_hits': 0}
                         for tf in timeframes},
        'total_tests': 0
    }

    # Run tests for each stock type
    for stock_type, symbols in test_stocks.items():
        logger.info(f"\n{'=' * 100}")
        logger.info(f"📊 Testing: {stock_type}")
        logger.info(f"{'=' * 100}\n")

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
                    days_back=21,  # 3 weeks
                    interval_days=7,  # Weekly
                    time_horizon=timeframe
                )

                stock_results[timeframe] = results

                # Update summary
                if results:
                    summary['total_tests'] += len(results)
                    summary['by_timeframe'][timeframe]['total'] += len(results)
                    summary['by_timeframe'][timeframe]['correct'] += sum(
                        1 for r in results if r['recommendation_correct']
                    )
                    summary['by_timeframe'][timeframe]['wins'] += sum(
                        1 for r in results if r['actual_performance']['return_pct'] > 0
                    )
                    summary['by_timeframe'][timeframe]['avg_return'] += sum(
                        r['actual_performance']['return_pct'] for r in results
                    )
                    summary['by_timeframe'][timeframe]['tp_hits'] += sum(
                        1 for r in results if r['actual_performance']['tp_hit']
                    )

            # Stock-level summary
            all_stock_results = []
            for tf_results in stock_results.values():
                all_stock_results.extend(tf_results)

            if all_stock_results:
                summary['by_stock'][symbol] = {
                    'total': len(all_stock_results),
                    'correct': sum(1 for r in all_stock_results if r['recommendation_correct']),
                    'wins': sum(1 for r in all_stock_results if r['actual_performance']['return_pct'] > 0),
                    'avg_return': sum(r['actual_performance']['return_pct'] for r in all_stock_results) / len(all_stock_results),
                    'tp_hits': sum(1 for r in all_stock_results if r['actual_performance']['tp_hit']),
                    'sl_hits': sum(1 for r in all_stock_results if r['actual_performance']['sl_hit'])
                }

            all_results[symbol] = stock_results

    # Calculate final averages
    for tf, stats in summary['by_timeframe'].items():
        if stats['total'] > 0:
            stats['avg_return'] = stats['avg_return'] / stats['total']

    # Print summary
    print_summary(summary, all_results, test_stocks)

    return all_results, summary


def print_summary(summary, all_results, test_stocks):
    """Print comprehensive summary"""
    logger.info("\n" + "=" * 100)
    logger.info("📊 QUICK COMPREHENSIVE BACKTEST SUMMARY (v7.0)")
    logger.info("=" * 100)

    # Overall
    logger.info(f"\n🎯 OVERALL RESULTS:")
    logger.info(f"  Total Tests Run: {summary['total_tests']}")

    if summary['total_tests'] == 0:
        logger.error("❌ NO TESTS COMPLETED!")
        return

    # By Stock Type
    logger.info(f"\n📈 RESULTS BY STOCK TYPE:")
    logger.info("-" * 100)

    for stock_type, symbols in test_stocks.items():
        logger.info(f"\n{stock_type}")

        type_total = 0
        type_correct = 0
        type_wins = 0
        type_avg_return = 0
        type_tp_hits = 0

        for symbol in symbols:
            if symbol in summary['by_stock']:
                stats = summary['by_stock'][symbol]
                type_total += stats['total']
                type_correct += stats['correct']
                type_wins += stats['wins']
                type_avg_return += stats['avg_return'] * stats['total']
                type_tp_hits += stats['tp_hits']

        if type_total > 0:
            type_avg_return = type_avg_return / type_total

            logger.info(f"  Recommendation Accuracy: {type_correct}/{type_total} ({type_correct/type_total*100:.1f}%)")
            logger.info(f"  Win Rate: {type_wins}/{type_total} ({type_wins/type_total*100:.1f}%)")
            logger.info(f"  Average Return: {type_avg_return:+.2f}%")
            logger.info(f"  TP Hit Rate: {type_tp_hits}/{type_total} ({type_tp_hits/type_total*100:.1f}%)")

    # By Stock
    logger.info(f"\n📊 RESULTS BY STOCK:")
    logger.info("-" * 100)
    logger.info(f"{'Stock':<8} {'Tests':<8} {'Rec Acc':<15} {'Win Rate':<15} {'Avg Return':<12} {'TP Hit':<15}")
    logger.info("-" * 100)

    for symbol, stats in summary['by_stock'].items():
        rec_acc = f"{stats['correct']}/{stats['total']} ({stats['correct']/stats['total']*100:.1f}%)"
        win_rate = f"{stats['wins']}/{stats['total']} ({stats['wins']/stats['total']*100:.1f}%)"
        avg_ret = f"{stats['avg_return']:+.2f}%"
        tp_hit = f"{stats['tp_hits']}/{stats['total']} ({stats['tp_hits']/stats['total']*100:.1f}%)"

        logger.info(f"{symbol:<8} {stats['total']:<8} {rec_acc:<15} {win_rate:<15} {avg_ret:<12} {tp_hit:<15}")

    # By Timeframe
    logger.info(f"\n⏱️  RESULTS BY TIMEFRAME:")
    logger.info("-" * 100)
    logger.info(f"{'Timeframe':<12} {'Tests':<8} {'Rec Acc':<15} {'Win Rate':<15} {'Avg Return':<12} {'TP Hit':<15}")
    logger.info("-" * 100)

    for timeframe, stats in summary['by_timeframe'].items():
        if stats['total'] > 0:
            rec_acc = f"{stats['correct']}/{stats['total']} ({stats['correct']/stats['total']*100:.1f}%)"
            win_rate = f"{stats['wins']}/{stats['total']} ({stats['wins']/stats['total']*100:.1f}%)"
            avg_ret = f"{stats['avg_return']:+.2f}%"
            tp_hit = f"{stats['tp_hits']}/{stats['total']} ({stats['tp_hits']/stats['total']*100:.1f}%)"

            logger.info(f"{timeframe.upper():<12} {stats['total']:<8} {rec_acc:<15} {win_rate:<15} {avg_ret:<12} {tp_hit:<15}")

    # Key Insights
    logger.info(f"\n💡 KEY INSIGHTS:")
    logger.info("-" * 100)

    # Swing stocks
    swing_symbols = ['PLTR', 'SOFI']
    swing_total = sum(summary['by_stock'][s]['total'] for s in swing_symbols if s in summary['by_stock'])
    swing_correct = sum(summary['by_stock'][s]['correct'] for s in swing_symbols if s in summary['by_stock'])

    if swing_total > 0:
        swing_acc = swing_correct / swing_total * 100
        logger.info(f"  🎯 Swing Stocks (PLTR, SOFI) Accuracy: {swing_acc:.1f}%")
        if swing_acc >= 70:
            logger.info(f"     ✅ TARGET MET! (Expected 70-80%, Got {swing_acc:.1f}%)")
        elif swing_acc >= 50:
            logger.info(f"     ⚠️  IMPROVED but below target (Expected 70-80%, Got {swing_acc:.1f}%)")
        else:
            logger.info(f"     ❌ BELOW EXPECTATIONS (Expected 70-80%, Got {swing_acc:.1f}%)")

    # Overall accuracy
    overall_total = sum(stats['total'] for stats in summary['by_stock'].values())
    overall_correct = sum(stats['correct'] for stats in summary['by_stock'].values())
    overall_acc = overall_correct / overall_total * 100 if overall_total > 0 else 0

    logger.info(f"  📊 Overall System Accuracy: {overall_acc:.1f}%")
    if overall_acc >= 68:
        logger.info(f"     ✅ TARGET MET! (Expected 68-72%, Got {overall_acc:.1f}%)")
    elif overall_acc >= 60:
        logger.info(f"     ⚠️  IMPROVED but below target (Expected 68-72%, Got {overall_acc:.1f}%)")
    else:
        logger.info(f"     ❌ BELOW EXPECTATIONS (Expected 68-72%, Got {overall_acc:.1f}%)")

    logger.info("=" * 100 + "\n")


if __name__ == '__main__':
    logger.info("Starting Quick Comprehensive Backtest v7.0...")
    logger.info("This will test 5 stocks × 3 timeframes × ~3 tests = ~45 total tests")
    logger.info("Estimated time: 5-8 minutes\n")

    quick_comprehensive_backtest()
