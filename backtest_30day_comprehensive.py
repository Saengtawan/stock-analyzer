#!/usr/bin/env python3
"""
Comprehensive 30-Day Backtest for Growth Catalyst Screener
Tests multiple entry points over the past 6 months to get reliable statistics
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import sys

# Test stocks (from Growth Catalyst screener typical results)
TEST_STOCKS = [
    'HOOD', 'HUBS', 'ANET', 'AMZN', 'TEAM', 'NOW', 'AMD', 'NET', 'COIN', 'TSM',
    'QCOM', 'LRCX', 'MSFT', 'SHOP', 'ROKU', 'AVGO', 'UBER', 'PLTR', 'GOOGL', 'DASH',
    'NVDA', 'META', 'NFLX', 'TSLA', 'AAPL', 'ADBE', 'CRM', 'ORCL', 'INTC', 'MU'
]

TARGET_GAIN = 15.0  # 15% target
HOLD_DAYS = 30      # 30-day holding period


def get_stock_data(symbol, start_date):
    """Fetch stock data from start_date to now"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=datetime.now())
        return hist
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None


def backtest_entry(hist, entry_idx, hold_days=30, target_gain=15.0):
    """
    Test a single entry point
    Returns: dict with results or None if insufficient data
    """
    if entry_idx + hold_days >= len(hist):
        return None

    entry_price = hist['Close'].iloc[entry_idx]
    entry_date = hist.index[entry_idx]

    # Get data for holding period
    hold_period = hist.iloc[entry_idx:entry_idx + hold_days + 1]

    exit_price = hold_period['Close'].iloc[-1]
    exit_date = hold_period.index[-1]

    # Find max price during holding period
    max_price = hold_period['High'].max()
    min_price = hold_period['Low'].min()

    # Calculate returns
    actual_return = ((exit_price - entry_price) / entry_price) * 100
    max_return = ((max_price - entry_price) / entry_price) * 100
    min_return = ((min_price - entry_price) / entry_price) * 100

    # Check if target was reached
    reached_target = max_return >= target_gain

    # Find when target was reached (if at all)
    days_to_target = None
    if reached_target:
        for i, (idx, row) in enumerate(hold_period.iterrows()):
            if ((row['High'] - entry_price) / entry_price) * 100 >= target_gain:
                days_to_target = i
                break

    return {
        'entry_date': entry_date,
        'exit_date': exit_date,
        'entry_price': entry_price,
        'exit_price': exit_price,
        'max_price': max_price,
        'min_price': min_price,
        'actual_return': actual_return,
        'max_return': max_return,
        'min_return': min_return,
        'reached_target': reached_target,
        'days_to_target': days_to_target
    }


def backtest_stock_comprehensive(symbol, start_date, entry_frequency=5):
    """
    Backtest a stock with multiple entry points
    entry_frequency: test entry every N days
    """
    print(f"Testing {symbol}...", end=' ')

    hist = get_stock_data(symbol, start_date)
    if hist is None or len(hist) < HOLD_DAYS + 30:
        print("❌ Insufficient data")
        return []

    results = []

    # Test entry points every N days
    for i in range(0, len(hist) - HOLD_DAYS - 1, entry_frequency):
        result = backtest_entry(hist, i, HOLD_DAYS, TARGET_GAIN)
        if result:
            result['symbol'] = symbol
            results.append(result)

    win_rate = len([r for r in results if r['reached_target']]) / len(results) * 100 if results else 0
    print(f"✅ {len(results)} trades, {win_rate:.0f}% win rate")

    return results


def main():
    print("=" * 100)
    print("📊 COMPREHENSIVE 30-DAY BACKTEST - GROWTH CATALYST SCREENER")
    print("=" * 100)
    print(f"Testing: {len(TEST_STOCKS)} stocks")
    print(f"Period: Past 6 months")
    print(f"Target: {TARGET_GAIN}% gain in {HOLD_DAYS} days")
    print(f"Strategy: Entry every 5 days, hold for {HOLD_DAYS} days")
    print("")

    # Start date: 6 months ago
    start_date = datetime.now() - timedelta(days=180)

    all_results = []

    for symbol in TEST_STOCKS:
        results = backtest_stock_comprehensive(symbol, start_date, entry_frequency=5)
        all_results.extend(results)

    if not all_results:
        print("\n❌ No results collected")
        return

    # Calculate statistics
    print("\n" + "=" * 100)
    print("📊 COMPREHENSIVE BACKTEST RESULTS")
    print("=" * 100)

    total_trades = len(all_results)
    winners = [r for r in all_results if r['reached_target']]
    losers = [r for r in all_results if not r['reached_target']]

    win_rate = (len(winners) / total_trades * 100)

    avg_return = np.mean([r['actual_return'] for r in all_results])
    median_return = np.median([r['actual_return'] for r in all_results])
    avg_max_return = np.mean([r['max_return'] for r in all_results])

    avg_winner_return = np.mean([r['max_return'] for r in winners]) if winners else 0
    avg_loser_return = np.mean([r['actual_return'] for r in losers]) if losers else 0

    # Expectancy
    expectancy = (win_rate / 100 * avg_winner_return) + ((100 - win_rate) / 100 * avg_loser_return)

    # Time to target for winners
    avg_days_to_target = np.mean([r['days_to_target'] for r in winners if r['days_to_target'] is not None]) if winners else 0

    print(f"\n📈 Overall Performance:")
    print(f"   Total Trades: {total_trades:,}")
    print(f"   Win Rate: {win_rate:.1f}% ({len(winners)}/{total_trades})")
    print(f"   Average Return: {avg_return:+.2f}%")
    print(f"   Median Return: {median_return:+.2f}%")
    print(f"   Average Max Return: {avg_max_return:+.2f}%")
    print("")

    print(f"💰 Winners ({len(winners)} trades):")
    print(f"   Average Max Return: {avg_winner_return:+.2f}%")
    print(f"   Average Days to Target: {avg_days_to_target:.1f} days")
    print("")

    print(f"📉 Losers ({len(losers)} trades):")
    print(f"   Average Return: {avg_loser_return:+.2f}%")
    print("")

    print(f"💡 Key Metrics:")
    print(f"   Expectancy: {expectancy:+.2f}%")
    print(f"   Risk/Reward: {abs(avg_winner_return / avg_loser_return):.2f}:1" if avg_loser_return != 0 else "   Risk/Reward: N/A")
    print("")

    # Return distribution
    positive_returns = [r for r in all_results if r['actual_return'] > 0]
    negative_returns = [r for r in all_results if r['actual_return'] < 0]
    flat_returns = [r for r in all_results if r['actual_return'] == 0]

    print(f"📊 Return Distribution:")
    print(f"   Positive: {len(positive_returns)} ({len(positive_returns)/total_trades*100:.1f}%)")
    print(f"   Negative: {len(negative_returns)} ({len(negative_returns)/total_trades*100:.1f}%)")
    print(f"   Flat: {len(flat_returns)} ({len(flat_returns)/total_trades*100:.1f}%)")
    print("")

    # Best and worst trades
    print(f"🏆 Top 5 Performers:")
    sorted_by_return = sorted(all_results, key=lambda x: x['max_return'], reverse=True)
    for i, r in enumerate(sorted_by_return[:5], 1):
        print(f"   {i}. {r['symbol']}: {r['max_return']:+.1f}% (entry: {r['entry_date'].strftime('%Y-%m-%d')}, {r['days_to_target']} days to target)")
    print("")

    print(f"📉 Bottom 5 Performers:")
    for i, r in enumerate(sorted_by_return[-5:], 1):
        print(f"   {i}. {r['symbol']}: {r['actual_return']:+.1f}% (entry: {r['entry_date'].strftime('%Y-%m-%d')})")
    print("")

    # Per-stock statistics
    stock_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_return': 0})
    for r in all_results:
        symbol = r['symbol']
        stock_stats[symbol]['trades'] += 1
        if r['reached_target']:
            stock_stats[symbol]['wins'] += 1
        stock_stats[symbol]['total_return'] += r['actual_return']

    # Best stocks
    print(f"🌟 Best Performing Stocks (by win rate):")
    sorted_stocks = sorted(stock_stats.items(),
                          key=lambda x: x[1]['wins'] / x[1]['trades'] if x[1]['trades'] > 0 else 0,
                          reverse=True)
    for i, (symbol, stats) in enumerate(sorted_stocks[:10], 1):
        win_rate = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
        avg_return = stats['total_return'] / stats['trades'] if stats['trades'] > 0 else 0
        print(f"   {i}. {symbol}: {win_rate:.0f}% win rate ({stats['wins']}/{stats['trades']}), avg {avg_return:+.1f}%")
    print("")

    # Worst stocks
    print(f"⚠️  Worst Performing Stocks (by win rate):")
    for i, (symbol, stats) in enumerate(sorted_stocks[-10:], 1):
        win_rate = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
        avg_return = stats['total_return'] / stats['trades'] if stats['trades'] > 0 else 0
        print(f"   {i}. {symbol}: {win_rate:.0f}% win rate ({stats['wins']}/{stats['trades']}), avg {avg_return:+.1f}%")
    print("")

    # Monthly breakdown
    monthly_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_return': 0})
    for r in all_results:
        month = r['entry_date'].strftime('%Y-%m')
        monthly_stats[month]['trades'] += 1
        if r['reached_target']:
            monthly_stats[month]['wins'] += 1
        monthly_stats[month]['total_return'] += r['actual_return']

    print(f"📅 Monthly Performance:")
    for month in sorted(monthly_stats.keys()):
        stats = monthly_stats[month]
        win_rate = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
        avg_return = stats['total_return'] / stats['trades'] if stats['trades'] > 0 else 0
        print(f"   {month}: {win_rate:.0f}% win rate ({stats['wins']}/{stats['trades']}), avg {avg_return:+.1f}%")
    print("")

    print("=" * 100)

    # Assessment
    if win_rate >= 50:
        print("✅ EXCELLENT: Win rate above 50%, strategy is viable!")
    elif win_rate >= 40:
        print("✅ GOOD: Win rate above 40%, consider optimization")
    elif win_rate >= 30:
        print("⚠️  MODERATE: Win rate above 30%, needs improvement")
    else:
        print("❌ POOR: Win rate below 30%, strategy needs significant changes")

    if expectancy > 5:
        print(f"✅ PROFITABLE: Positive expectancy of {expectancy:+.2f}% per trade")
    elif expectancy > 0:
        print(f"⚠️  MARGINALLY PROFITABLE: Low expectancy of {expectancy:+.2f}% per trade")
    else:
        print(f"❌ UNPROFITABLE: Negative expectancy of {expectancy:+.2f}% per trade")

    print("=" * 100)


if __name__ == "__main__":
    main()
