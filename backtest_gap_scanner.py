#!/usr/bin/env python3
"""
Backtest Pre-market Gap Scanner
Using daily gap data (Open vs Previous Close) as proxy for pre-market gaps
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
import json

def backtest_gap_strategy(symbols, days=60):
    """
    Backtest gap trading strategy

    Args:
        symbols: List of stock symbols to test
        days: Number of trading days to backtest
    """

    print("=" * 100)
    print("📊 GAP TRADING STRATEGY BACKTEST")
    print("=" * 100)
    print(f"\nTesting {len(symbols)} stocks over {days} trading days")
    print(f"Strategy: Buy at Open if Gap >= 2%, Sell at Close")
    print()

    all_trades = []

    for symbol in symbols:
        try:
            # Get historical data
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days+10}d", interval="1d")

            if df.empty or len(df) < 5:
                continue

            # Calculate gaps
            df['PrevClose'] = df['Close'].shift(1)
            df['Gap'] = ((df['Open'] - df['PrevClose']) / df['PrevClose'] * 100)
            df['DayReturn'] = ((df['Close'] - df['Open']) / df['Open'] * 100)

            # Filter gap trades (gap >= 2%)
            gap_trades = df[df['Gap'] >= 2.0].copy()

            if gap_trades.empty:
                continue

            # Calculate consistency (simplified - based on daily bars)
            for idx, row in gap_trades.iterrows():
                # Get last 5 days before this day
                prev_idx = df.index.get_loc(idx)
                if prev_idx >= 5:
                    prev_5_days = df.iloc[prev_idx-5:prev_idx]
                    daily_changes = prev_5_days['Close'].pct_change().dropna()
                    if len(daily_changes) > 0:
                        consistency = (daily_changes > 0).sum() / len(daily_changes)
                    else:
                        consistency = 0.5
                else:
                    consistency = 0.5

                # Calculate simplified confidence score
                confidence = calculate_simple_confidence(
                    gap_pct=row['Gap'],
                    consistency_ratio=consistency
                )

                # Record trade
                trade = {
                    'symbol': symbol,
                    'date': idx.strftime('%Y-%m-%d'),
                    'gap': row['Gap'],
                    'consistency': consistency * 100,
                    'confidence': confidence,
                    'day_return': row['DayReturn'],
                    'success': row['DayReturn'] > 0
                }
                all_trades.append(trade)

        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

    if not all_trades:
        print("❌ No trades found in backtest period")
        return

    # Analyze results
    analyze_backtest_results(all_trades)

def calculate_simple_confidence(gap_pct, consistency_ratio):
    """
    Simplified confidence calculation
    Based on gap size and consistency only
    """
    confidence = 50  # Start at neutral

    # Gap factor
    if 2.0 <= gap_pct <= 3.5:
        confidence += 15  # Sweet spot
    elif 1.5 <= gap_pct < 2.0 or 3.5 < gap_pct <= 4.5:
        confidence += 8
    elif gap_pct > 7.0:
        confidence -= 15  # Too big

    # Consistency factor
    if consistency_ratio >= 0.8:
        confidence += 15
    elif consistency_ratio >= 0.6:
        confidence += 10
    elif consistency_ratio >= 0.5:
        confidence += 5
    elif consistency_ratio >= 0.4:
        confidence += 0
    elif consistency_ratio >= 0.3:
        confidence -= 15
    else:
        confidence -= 30

    return max(0, min(100, int(confidence)))

def analyze_backtest_results(trades):
    """Analyze and display backtest results"""

    df = pd.DataFrame(trades)
    total_trades = len(df)

    print(f"\n📈 BACKTEST RESULTS:")
    print("-" * 100)
    print(f"Total Trades: {total_trades}")
    print(f"Date Range: {df['date'].min()} to {df['date'].max()}")

    # Overall stats
    overall_win_rate = (df['success'].sum() / total_trades * 100)
    avg_return = df['day_return'].mean()

    print(f"\n🎯 OVERALL PERFORMANCE:")
    print(f"   Win Rate: {overall_win_rate:.1f}% ({df['success'].sum()}/{total_trades})")
    print(f"   Avg Return: {avg_return:+.2f}%")
    print(f"   Avg Gap: {df['gap'].mean():.2f}%")

    # Performance by confidence level
    print(f"\n📊 PERFORMANCE BY CONFIDENCE LEVEL:")
    print("-" * 100)
    print(f"{'Confidence':<20} {'Trades':<10} {'Win Rate':<15} {'Avg Return':<15} {'Recommendation':<20}")
    print("-" * 100)

    confidence_bins = [
        (80, 100, "80-100 (HIGH)"),
        (70, 80, "70-79 (GOOD)"),
        (60, 70, "60-69 (MODERATE)"),
        (50, 60, "50-59 (LOW-MOD)"),
        (40, 50, "40-49 (LOW)"),
        (0, 40, "0-39 (VERY LOW)")
    ]

    results_by_confidence = []

    for min_conf, max_conf, label in confidence_bins:
        subset = df[(df['confidence'] >= min_conf) & (df['confidence'] < max_conf)]

        if len(subset) > 0:
            win_rate = (subset['success'].sum() / len(subset) * 100)
            avg_ret = subset['day_return'].mean()

            # Recommendation
            if win_rate >= 60 and avg_ret > 0.5:
                rec = "✅ TRADE"
            elif win_rate >= 50:
                rec = "⚠️  CAUTION"
            else:
                rec = "❌ AVOID"

            print(f"{label:<20} {len(subset):<10} {win_rate:>6.1f}% ({subset['success'].sum()}/{len(subset)})  {avg_ret:>+7.2f}%      {rec:<20}")

            results_by_confidence.append({
                'level': label,
                'trades': len(subset),
                'win_rate': win_rate,
                'avg_return': avg_ret
            })
        else:
            print(f"{label:<20} {0:<10} {'N/A':<15} {'N/A':<15} {'-':<20}")

    # Performance by gap size
    print(f"\n📊 PERFORMANCE BY GAP SIZE:")
    print("-" * 100)
    print(f"{'Gap Range':<20} {'Trades':<10} {'Win Rate':<15} {'Avg Return':<15} {'Notes':<30}")
    print("-" * 100)

    gap_bins = [
        (2.0, 3.0, "2-3% (SWEET SPOT)"),
        (3.0, 5.0, "3-5% (MODERATE)"),
        (5.0, 7.0, "5-7% (HIGH)"),
        (7.0, 100.0, "7%+ (EXTREME)")
    ]

    for min_gap, max_gap, label in gap_bins:
        subset = df[(df['gap'] >= min_gap) & (df['gap'] < max_gap)]

        if len(subset) > 0:
            win_rate = (subset['success'].sum() / len(subset) * 100)
            avg_ret = subset['day_return'].mean()

            if win_rate >= 55:
                note = "Good performance"
            elif win_rate >= 45:
                note = "Mixed results"
            else:
                note = "Poor - likely fade"

            print(f"{label:<20} {len(subset):<10} {win_rate:>6.1f}% ({subset['success'].sum()}/{len(subset)})  {avg_ret:>+7.2f}%      {note:<30}")

    # Best trades (highest confidence + success)
    print(f"\n✅ TOP 10 SUCCESSFUL TRADES:")
    print("-" * 100)
    successful = df[df['success'] == True].nlargest(10, 'confidence')
    if not successful.empty:
        print(f"{'Date':<12} {'Symbol':<8} {'Gap%':<8} {'Conf':<8} {'Return%':<10} {'Consistency%':<15}")
        print("-" * 100)
        for _, trade in successful.iterrows():
            print(f"{trade['date']:<12} {trade['symbol']:<8} {trade['gap']:>6.2f}% {trade['confidence']:>5}/100 {trade['day_return']:>+8.2f}% {trade['consistency']:>13.1f}%")

    # Worst trades (failed despite high confidence)
    print(f"\n❌ TOP 10 FAILED TRADES (High Confidence but Failed):")
    print("-" * 100)
    failed_high_conf = df[(df['success'] == False) & (df['confidence'] >= 60)].nlargest(10, 'confidence')
    if not failed_high_conf.empty:
        print(f"{'Date':<12} {'Symbol':<8} {'Gap%':<8} {'Conf':<8} {'Return%':<10} {'Consistency%':<15}")
        print("-" * 100)
        for _, trade in failed_high_conf.iterrows():
            print(f"{trade['date']:<12} {trade['symbol']:<8} {trade['gap']:>6.2f}% {trade['confidence']:>5}/100 {trade['day_return']:>+8.2f}% {trade['consistency']:>13.1f}%")

    # Summary
    print(f"\n" + "=" * 100)
    print("💡 CONCLUSIONS:")
    print("=" * 100)

    # Find best confidence threshold
    high_conf = df[df['confidence'] >= 70]
    if len(high_conf) > 0:
        high_conf_wr = (high_conf['success'].sum() / len(high_conf) * 100)
        print(f"\n1. Confidence ≥70 trades: {len(high_conf)} trades, {high_conf_wr:.1f}% win rate")
        if high_conf_wr >= 55:
            print(f"   ✅ GOOD threshold - trade these setups")
        else:
            print(f"   ⚠️  Below 55% - needs improvement")

    # Gap size analysis
    sweet_spot = df[(df['gap'] >= 2.0) & (df['gap'] <= 3.0)]
    large_gap = df[df['gap'] >= 7.0]

    if len(sweet_spot) > 0:
        sweet_wr = (sweet_spot['success'].sum() / len(sweet_spot) * 100)
        print(f"\n2. Gap 2-3% (Sweet Spot): {len(sweet_spot)} trades, {sweet_wr:.1f}% win rate")

    if len(large_gap) > 0:
        large_wr = (large_gap['success'].sum() / len(large_gap) * 100)
        print(f"3. Gap ≥7% (Large): {len(large_gap)} trades, {large_wr:.1f}% win rate")
        if large_wr < 45:
            print(f"   ⚠️  Large gaps tend to fade - avoid!")

    print("\n" + "=" * 100)

if __name__ == '__main__':
    # Test with popular stocks
    test_symbols = [
        # Tech
        'AAPL', 'MSFT', 'GOOGL', 'META', 'NVDA', 'AMD', 'TSLA',
        'NFLX', 'AMZN', 'INTC', 'QCOM', 'AVGO',
        # Consumer
        'DIS', 'NKE', 'SBUX', 'MCD', 'COST', 'WMT', 'TGT',
        # Healthcare
        'JNJ', 'PFE', 'MRNA', 'UNH', 'CVS',
        # Finance
        'JPM', 'BAC', 'GS', 'MS', 'V', 'MA',
        # Other
        'BA', 'CAT', 'GE', 'F', 'GM'
    ]

    print("\n🚀 Starting backtest...")
    print(f"Symbols: {len(test_symbols)}")
    print(f"Period: Last 60 trading days")
    print()

    backtest_gap_strategy(test_symbols, days=60)
