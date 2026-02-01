#!/usr/bin/env python3
"""
Backtest Comparison: 14-Day vs 30-Day Growth Catalyst Screener
Test if 14-day timeframe can achieve 5% and 10% targets
Compare with 30-day results (5% target = 100% win rate)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Stocks from v7.1 backtest (the winners)
V7_1_WINNERS = ['GOOGL', 'META', 'DASH', 'TEAM', 'ROKU', 'TSM', 'LRCX']

# Additional stocks to test (mix of growth + value)
ADDITIONAL_STOCKS = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'TSLA',  # Mega caps
    'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG',   # High growth
    'AMD', 'AVGO', 'QCOM', 'AMAT', 'KLAC',   # Semiconductors
    'UBER', 'ABNB', 'COIN', 'SHOP', 'SQ',    # Consumer tech
]

ALL_TEST_STOCKS = V7_1_WINNERS + ADDITIONAL_STOCKS


def backtest_timeframe(symbol: str, timeframe_days: int, target_pct: float) -> Dict[str, Any]:
    """
    Backtest a single stock for given timeframe and target

    Args:
        symbol: Stock symbol
        timeframe_days: Number of days to test (14 or 30)
        target_pct: Target gain percentage (5 or 10)

    Returns:
        Dict with backtest results
    """
    try:
        # Get historical data (6 months to have enough data)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='6mo')

        if hist.empty or len(hist) < timeframe_days + 10:
            return None

        # Get entry point (timeframe_days ago)
        entry_price = hist['Close'].iloc[-timeframe_days]
        current_price = hist['Close'].iloc[-1]

        # Get max high during the period
        max_high = hist['High'].iloc[-timeframe_days:].max()

        # Calculate returns
        actual_return = ((current_price - entry_price) / entry_price) * 100
        max_return = ((max_high - entry_price) / entry_price) * 100

        # Check if target was reached
        reached_target = max_return >= target_pct

        return {
            'symbol': symbol,
            'timeframe_days': timeframe_days,
            'target_pct': target_pct,
            'entry_price': entry_price,
            'current_price': current_price,
            'max_high': max_high,
            'actual_return': actual_return,
            'max_return': max_return,
            'reached_target': reached_target
        }

    except Exception as e:
        print(f"  ⚠️  {symbol}: {e}")
        return None


def run_comprehensive_backtest():
    """Run comprehensive backtest comparing 14-day vs 30-day"""

    print("=" * 100)
    print("🔬 COMPREHENSIVE BACKTEST: 14-Day vs 30-Day Growth Catalyst Screener")
    print("=" * 100)
    print(f"\nTesting {len(ALL_TEST_STOCKS)} stocks:")
    print(f"  • v7.1 Winners: {', '.join(V7_1_WINNERS)}")
    print(f"  • Additional: {len(ADDITIONAL_STOCKS)} stocks")
    print("\nTest Configurations:")
    print("  1. 14-day, 5% target")
    print("  2. 14-day, 10% target")
    print("  3. 30-day, 5% target (v7.1 baseline)")
    print("  4. 30-day, 10% target")
    print("")

    # Store all results
    all_results = {
        '14d_5pct': [],
        '14d_10pct': [],
        '30d_5pct': [],
        '30d_10pct': []
    }

    # Run backtests
    for symbol in ALL_TEST_STOCKS:
        print(f"\nTesting {symbol}...")

        # Test all 4 configurations
        result_14d_5 = backtest_timeframe(symbol, 14, 5.0)
        result_14d_10 = backtest_timeframe(symbol, 14, 10.0)
        result_30d_5 = backtest_timeframe(symbol, 30, 5.0)
        result_30d_10 = backtest_timeframe(symbol, 30, 10.0)

        if result_14d_5:
            all_results['14d_5pct'].append(result_14d_5)
            print(f"  14d @ 5%:  {result_14d_5['max_return']:+6.1f}% max → {'✅' if result_14d_5['reached_target'] else '❌'}")

        if result_14d_10:
            all_results['14d_10pct'].append(result_14d_10)
            print(f"  14d @ 10%: {result_14d_10['max_return']:+6.1f}% max → {'✅' if result_14d_10['reached_target'] else '❌'}")

        if result_30d_5:
            all_results['30d_5pct'].append(result_30d_5)
            print(f"  30d @ 5%:  {result_30d_5['max_return']:+6.1f}% max → {'✅' if result_30d_5['reached_target'] else '❌'}")

        if result_30d_10:
            all_results['30d_10pct'].append(result_30d_10)
            print(f"  30d @ 10%: {result_30d_10['max_return']:+6.1f}% max → {'✅' if result_30d_10['reached_target'] else '❌'}")

    # Print summary
    print("\n" + "=" * 100)
    print("📊 BACKTEST RESULTS SUMMARY")
    print("=" * 100)

    configs = [
        ('14d_5pct', '14-day, 5% target'),
        ('14d_10pct', '14-day, 10% target'),
        ('30d_5pct', '30-day, 5% target (v7.1 baseline)'),
        ('30d_10pct', '30-day, 10% target')
    ]

    summary_table = []

    for config_key, config_name in configs:
        results = all_results[config_key]

        if not results:
            continue

        total = len(results)
        winners = [r for r in results if r['reached_target']]
        win_rate = (len(winners) / total * 100) if total > 0 else 0

        avg_max_return = np.mean([r['max_return'] for r in results])
        avg_actual_return = np.mean([r['actual_return'] for r in results])

        avg_winner_return = np.mean([r['max_return'] for r in winners]) if winners else 0
        losers = [r for r in results if not r['reached_target']]
        avg_loser_return = np.mean([r['actual_return'] for r in losers]) if losers else 0

        expectancy = (win_rate / 100 * avg_winner_return) + ((100 - win_rate) / 100 * avg_loser_return)

        summary_table.append({
            'config': config_name,
            'total': total,
            'winners': len(winners),
            'win_rate': win_rate,
            'avg_max_return': avg_max_return,
            'avg_actual_return': avg_actual_return,
            'avg_winner_return': avg_winner_return,
            'avg_loser_return': avg_loser_return,
            'expectancy': expectancy
        })

    # Print comparison table
    print("\n📈 Performance Comparison:\n")
    print(f"{'Configuration':<40} | {'Win Rate':>10} | {'Avg Max':>10} | {'Expectancy':>10}")
    print("-" * 80)

    for row in summary_table:
        print(f"{row['config']:<40} | {row['win_rate']:>9.1f}% | {row['avg_max_return']:>+9.1f}% | {row['expectancy']:>+9.1f}%")

    # Detailed breakdown
    print("\n" + "=" * 100)
    print("📋 DETAILED BREAKDOWN")
    print("=" * 100)

    for config_key, config_name in configs:
        results = all_results[config_key]

        if not results:
            continue

        summary = summary_table[[s['config'] for s in summary_table].index(config_name)]

        print(f"\n{config_name}:")
        print(f"  Total Tested: {summary['total']} stocks")
        print(f"  Win Rate: {summary['win_rate']:.1f}% ({summary['winners']}/{summary['total']})")
        print(f"  Average Max Return: {summary['avg_max_return']:+.2f}%")
        print(f"  Average Actual Return: {summary['avg_actual_return']:+.2f}%")
        print(f"  Winners Avg: {summary['avg_winner_return']:+.2f}%")
        print(f"  Losers Avg: {summary['avg_loser_return']:+.2f}%")
        print(f"  Expectancy: {summary['expectancy']:+.2f}%")

    # v7.1 Winners specific analysis
    print("\n" + "=" * 100)
    print("🏆 v7.1 WINNERS ANALYSIS (7 stocks)")
    print("=" * 100)

    for config_key, config_name in configs:
        results = all_results[config_key]

        # Filter to v7.1 winners only
        v7_1_results = [r for r in results if r['symbol'] in V7_1_WINNERS]

        if not v7_1_results:
            continue

        winners = [r for r in v7_1_results if r['reached_target']]
        win_rate = (len(winners) / len(v7_1_results) * 100) if v7_1_results else 0
        avg_max = np.mean([r['max_return'] for r in v7_1_results])

        print(f"\n{config_name}:")
        print(f"  Win Rate: {win_rate:.1f}% ({len(winners)}/{len(v7_1_results)})")
        print(f"  Avg Max Return: {avg_max:+.2f}%")
        print(f"  Stocks: ", end="")
        for r in v7_1_results:
            status = "✅" if r['reached_target'] else "❌"
            print(f"{r['symbol']}({r['max_return']:+.1f}%){status} ", end="")
        print()

    # Recommendations
    print("\n" + "=" * 100)
    print("🎯 RECOMMENDATIONS")
    print("=" * 100)

    # Compare 14d vs 30d at same target
    config_14d_5 = next(s for s in summary_table if '14-day, 5%' in s['config'])
    config_30d_5 = next(s for s in summary_table if '30-day, 5%' in s['config'])
    config_14d_10 = next(s for s in summary_table if '14-day, 10%' in s['config'])
    config_30d_10 = next(s for s in summary_table if '30-day, 10%' in s['config'])

    print("\n1. **5% Target Comparison:**")
    print(f"   14-day: {config_14d_5['win_rate']:.1f}% win rate, {config_14d_5['expectancy']:+.2f}% expectancy")
    print(f"   30-day: {config_30d_5['win_rate']:.1f}% win rate, {config_30d_5['expectancy']:+.2f}% expectancy")

    if config_30d_5['win_rate'] > config_14d_5['win_rate']:
        print(f"   ✅ **30-day is better** for 5% target (higher win rate)")
    elif config_14d_5['win_rate'] > config_30d_5['win_rate']:
        print(f"   ✅ **14-day is better** for 5% target (higher win rate)")
    else:
        print(f"   ⚖️  **Similar performance**")

    print("\n2. **10% Target Comparison:**")
    print(f"   14-day: {config_14d_10['win_rate']:.1f}% win rate, {config_14d_10['expectancy']:+.2f}% expectancy")
    print(f"   30-day: {config_30d_10['win_rate']:.1f}% win rate, {config_30d_10['expectancy']:+.2f}% expectancy")

    if config_30d_10['win_rate'] > config_14d_10['win_rate']:
        print(f"   ✅ **30-day is better** for 10% target (higher win rate)")
    elif config_14d_10['win_rate'] > config_30d_10['win_rate']:
        print(f"   ✅ **14-day is better** for 10% target (higher win rate)")
    else:
        print(f"   ⚖️  **Similar performance**")

    print("\n3. **Best Overall Configuration:**")
    best_config = max(summary_table, key=lambda x: x['expectancy'])
    print(f"   🏆 {best_config['config']}")
    print(f"   Win Rate: {best_config['win_rate']:.1f}%")
    print(f"   Expectancy: {best_config['expectancy']:+.2f}%")

    print("\n" + "=" * 100)
    print("✅ BACKTEST COMPLETE")
    print("=" * 100)
    print()


if __name__ == "__main__":
    run_comprehensive_backtest()
