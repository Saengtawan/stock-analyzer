#!/usr/bin/env python3
"""
Backtest Pre-market Gap Scanner with Price Filter
Focus on Gap Trap Analysis: How many gap-up stocks actually fade?
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
import json

def backtest_with_price_filter(symbols, days=60, min_price=5.0):
    """
    Backtest gap strategy with price filter
    Measure gap trap frequency
    """

    print("=" * 120)
    print(f"📊 GAP TRAP ANALYSIS - Price Filter: ${min_price}+")
    print("=" * 120)
    print(f"Testing {len(symbols)} stocks over {days} trading days")
    print(f"Gap Trap = Stock gaps up 2%+ but closes BELOW open (fades)")
    print()

    all_trades = []
    price_filtered_out = []

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
            df['TotalReturn'] = ((df['Close'] - df['PrevClose']) / df['PrevClose'] * 100)

            # Filter gap trades (gap >= 2%)
            gap_trades = df[df['Gap'] >= 2.0].copy()

            if gap_trades.empty:
                continue

            # Calculate consistency
            for idx, row in gap_trades.iterrows():
                open_price = row['Open']

                # PRICE FILTER CHECK
                if open_price < min_price:
                    price_filtered_out.append({
                        'symbol': symbol,
                        'date': idx.strftime('%Y-%m-%d'),
                        'price': open_price,
                        'gap': row['Gap'],
                        'day_return': row['DayReturn'],
                        'is_gap_trap': row['DayReturn'] < 0
                    })
                    continue  # Skip this trade due to price filter

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

                # Calculate confidence (with price penalty)
                confidence = calculate_confidence_with_price(
                    gap_pct=row['Gap'],
                    consistency_ratio=consistency,
                    price=open_price
                )

                # Identify gap trap
                is_gap_trap = row['DayReturn'] < 0  # Closed below open = fade
                is_major_trap = row['TotalReturn'] < 0  # Closed below previous close = full reversal

                # Record trade
                trade = {
                    'symbol': symbol,
                    'date': idx.strftime('%Y-%m-%d'),
                    'price': open_price,
                    'gap': row['Gap'],
                    'consistency': consistency * 100,
                    'confidence': confidence,
                    'day_return': row['DayReturn'],
                    'total_return': row['TotalReturn'],
                    'success': row['DayReturn'] > 0,  # Held the gap
                    'is_gap_trap': is_gap_trap,
                    'is_major_trap': is_major_trap
                }
                all_trades.append(trade)

        except Exception as e:
            print(f"⚠️  Error processing {symbol}: {e}")
            continue

    if not all_trades:
        print("❌ No trades found in backtest period")
        return None

    # Analyze results
    return analyze_gap_trap_results(all_trades, price_filtered_out, min_price)

def calculate_confidence_with_price(gap_pct, consistency_ratio, price):
    """
    Confidence calculation WITH price penalty (v7.0 - UPDATED 2025-12-17)
    Matches the actual scanner logic with backtest-proven penalties
    """
    confidence = 50  # Start at neutral

    # Simplified gap_score calculation (assuming average of 5.0)
    gap_score = 5.0
    confidence += (gap_score - 5.0) * 5  # Factor 1: Gap Score

    # Factor 2: Gap size (v7.0 - BACKTEST VALIDATED)
    if 2.0 <= gap_pct <= 3.0:
        confidence += 15  # SWEET SPOT - 41% trap rate
    elif 1.5 <= gap_pct < 2.0:
        confidence += 3
    elif 3.0 < gap_pct <= 5.0:
        confidence -= 25  # DANGER ZONE! 63% trap rate
    elif 5.0 < gap_pct <= 7.0:
        confidence -= 15  # Still risky (47% trap rate)
    elif gap_pct > 7.0:
        confidence -= 20  # Very high fade risk (50% trap)

    # Factor 3: Consistency
    if consistency_ratio >= 0.95:
        confidence -= 5  # Overbought
    elif consistency_ratio >= 0.8:
        confidence += 8
    elif consistency_ratio >= 0.6:
        confidence += 10  # Sweet spot
    elif consistency_ratio >= 0.5:
        confidence += 5
    elif consistency_ratio >= 0.4:
        confidence += 0
    elif consistency_ratio >= 0.3:
        confidence -= 15
    else:
        confidence -= 30

    # Factor 4: PRICE PENALTY (v7.0 - UPDATED!)
    if price < 10:  # $5-10 range
        confidence -= 10
    elif price < 15:  # $10-15 range
        confidence -= 5
    elif 15 <= price < 50:  # $15-50 range
        confidence -= 20  # DANGER! 78% trap rate

    return max(0, min(100, int(confidence)))

def analyze_gap_trap_results(trades, filtered_out, min_price):
    """Analyze gap trap frequency"""

    df = pd.DataFrame(trades)
    total_trades = len(df)

    print(f"\n📈 BACKTEST RESULTS (Price >= ${min_price}):")
    print("-" * 120)
    print(f"Total Trades Analyzed: {total_trades}")
    print(f"Trades Filtered Out (Price < ${min_price}): {len(filtered_out)}")
    print(f"Date Range: {df['date'].min()} to {df['date'].max()}")

    # GAP TRAP ANALYSIS
    print(f"\n🚨 GAP TRAP ANALYSIS:")
    print("-" * 120)

    gap_traps = df[df['is_gap_trap'] == True]
    major_traps = df[df['is_major_trap'] == True]
    successful_gaps = df[df['success'] == True]

    gap_trap_rate = len(gap_traps) / total_trades * 100 if total_trades > 0 else 0
    major_trap_rate = len(major_traps) / total_trades * 100 if total_trades > 0 else 0
    success_rate = len(successful_gaps) / total_trades * 100 if total_trades > 0 else 0

    print(f"✅ Successful (held gap):   {len(successful_gaps):>4} trades ({success_rate:>5.1f}%) - Avg Return: {successful_gaps['day_return'].mean():+.2f}%")
    print(f"⚠️  Gap Trap (faded):       {len(gap_traps):>4} trades ({gap_trap_rate:>5.1f}%) - Avg Return: {gap_traps['day_return'].mean():+.2f}%")
    print(f"🔴 Major Trap (full rev):  {len(major_traps):>4} trades ({major_trap_rate:>5.1f}%) - Avg Return: {major_traps['total_return'].mean():+.2f}%")

    # Overall stats
    avg_return = df['day_return'].mean()
    avg_total_return = df['total_return'].mean()

    print(f"\n🎯 OVERALL PERFORMANCE:")
    print(f"   Win Rate: {success_rate:.1f}% ({len(successful_gaps)}/{total_trades})")
    print(f"   Avg Intraday Return: {avg_return:+.2f}%")
    print(f"   Avg Total Return: {avg_total_return:+.2f}%")
    print(f"   Avg Gap Size: {df['gap'].mean():.2f}%")

    # Performance by confidence level
    print(f"\n📊 PERFORMANCE BY CONFIDENCE LEVEL:")
    print("-" * 120)
    print(f"{'Confidence':<20} {'Trades':<10} {'Win Rate':<15} {'Gap Trap %':<15} {'Avg Return':<15} {'Recommendation':<20}")
    print("-" * 120)

    confidence_bins = [
        (80, 100, "80-100 (HIGH)"),
        (70, 80, "70-79 (GOOD)"),
        (60, 70, "60-69 (MODERATE)"),
        (50, 60, "50-59 (LOW-MOD)"),
        (40, 50, "40-49 (LOW)"),
        (0, 40, "0-39 (VERY LOW)")
    ]

    for min_conf, max_conf, label in confidence_bins:
        subset = df[(df['confidence'] >= min_conf) & (df['confidence'] < max_conf)]

        if len(subset) > 0:
            win_rate = (subset['success'].sum() / len(subset) * 100)
            trap_rate = (subset['is_gap_trap'].sum() / len(subset) * 100)
            avg_ret = subset['day_return'].mean()

            # Recommendation
            if win_rate >= 55 and trap_rate < 45:
                rec = "✅ TRADE"
            elif win_rate >= 50:
                rec = "⚠️  CAUTION"
            else:
                rec = "❌ AVOID"

            print(f"{label:<20} {len(subset):<10} {win_rate:>6.1f}%        {trap_rate:>6.1f}%        {avg_ret:>+7.2f}%      {rec:<20}")
        else:
            print(f"{label:<20} {0:<10} {'N/A':<15} {'N/A':<15} {'N/A':<15} {'-':<20}")

    # Performance by gap size
    print(f"\n📊 GAP TRAP FREQUENCY BY GAP SIZE:")
    print("-" * 120)
    print(f"{'Gap Range':<20} {'Trades':<10} {'Win Rate':<15} {'Gap Trap %':<15} {'Avg Return':<15}")
    print("-" * 120)

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
            trap_rate = (subset['is_gap_trap'].sum() / len(subset) * 100)
            avg_ret = subset['day_return'].mean()

            print(f"{label:<20} {len(subset):<10} {win_rate:>6.1f}%        {trap_rate:>6.1f}%        {avg_ret:>+7.2f}%")

    # Price range analysis
    print(f"\n📊 PERFORMANCE BY PRICE RANGE:")
    print("-" * 120)
    print(f"{'Price Range':<20} {'Trades':<10} {'Win Rate':<15} {'Gap Trap %':<15} {'Avg Return':<15}")
    print("-" * 120)

    price_bins = [
        (5, 10, "$5-10 (Low)"),
        (10, 15, "$10-15 (Moderate)"),
        (15, 50, "$15-50 (Mid)"),
        (50, 1000, "$50+ (High)")
    ]

    for min_p, max_p, label in price_bins:
        subset = df[(df['price'] >= min_p) & (df['price'] < max_p)]

        if len(subset) > 0:
            win_rate = (subset['success'].sum() / len(subset) * 100)
            trap_rate = (subset['is_gap_trap'].sum() / len(subset) * 100)
            avg_ret = subset['day_return'].mean()

            print(f"{label:<20} {len(subset):<10} {win_rate:>6.1f}%        {trap_rate:>6.1f}%        {avg_ret:>+7.2f}%")

    # What if we didn't filter by price?
    if filtered_out:
        print(f"\n📊 STOCKS FILTERED OUT (Price < ${min_price}):")
        print("-" * 120)
        df_filtered = pd.DataFrame(filtered_out)
        filtered_traps = df_filtered[df_filtered['is_gap_trap'] == True]
        filtered_success = df_filtered[df_filtered['is_gap_trap'] == False]

        print(f"Total Filtered Out: {len(df_filtered)}")
        print(f"Would-be Successful: {len(filtered_success)} ({len(filtered_success)/len(df_filtered)*100:.1f}%)")
        print(f"Would-be Gap Traps: {len(filtered_traps)} ({len(filtered_traps)/len(df_filtered)*100:.1f}%)")
        print(f"Avg Return if traded: {df_filtered['day_return'].mean():+.2f}%")

        print(f"\n💡 By filtering out stocks < ${min_price}, we:")
        if len(filtered_traps)/len(df_filtered) > gap_trap_rate/100:
            print(f"   ✅ AVOIDED {len(filtered_traps)/len(df_filtered)*100 - gap_trap_rate:.1f}% MORE gap traps!")
        else:
            print(f"   ⚠️  Didn't significantly reduce gap traps")

    # Top gap traps
    print(f"\n🚨 TOP 10 WORST GAP TRAPS (High Confidence but Failed):")
    print("-" * 120)
    worst_traps = df[(df['is_gap_trap'] == True) & (df['confidence'] >= 50)].nsmallest(10, 'day_return')
    if not worst_traps.empty:
        print(f"{'Date':<12} {'Symbol':<8} {'Price':<10} {'Gap%':<8} {'Conf':<8} {'Return%':<10}")
        print("-" * 120)
        for _, trade in worst_traps.iterrows():
            print(f"{trade['date']:<12} {trade['symbol']:<8} ${trade['price']:>7.2f}  {trade['gap']:>6.2f}% {trade['confidence']:>5}/100 {trade['day_return']:>+8.2f}%")

    print("\n" + "=" * 120)

    return {
        'total_trades': total_trades,
        'success_rate': success_rate,
        'gap_trap_rate': gap_trap_rate,
        'avg_return': avg_return,
        'filtered_out': len(filtered_out)
    }

def run_comparison_backtest():
    """Run backtest with different price filters"""

    test_symbols = [
        # Tech
        'AAPL', 'MSFT', 'GOOGL', 'META', 'NVDA', 'AMD', 'TSLA',
        'NFLX', 'AMZN', 'INTC', 'QCOM', 'AVGO', 'PLTR', 'SNOW',
        # Consumer
        'DIS', 'NKE', 'SBUX', 'MCD', 'COST', 'WMT', 'TGT',
        # Healthcare
        'JNJ', 'PFE', 'MRNA', 'UNH', 'CVS', 'LLY',
        # Finance
        'JPM', 'BAC', 'GS', 'MS', 'V', 'MA',
        # Other
        'BA', 'CAT', 'GE', 'F', 'GM', 'UBER', 'SHOP',
        # Smaller cap tech
        'MRVL', 'MU', 'PANW', 'CRWD', 'ZS', 'DDOG', 'NET'
    ]

    print("\n🚀 Starting Gap Trap Analysis Backtest...")
    print(f"Symbols: {len(test_symbols)}")
    print(f"Period: Last 60 trading days")
    print()

    # Test different price filters
    price_filters = [0, 5, 10, 15, 20]
    results = {}

    for min_price in price_filters:
        label = f"${min_price}+" if min_price > 0 else "No Filter"
        print(f"\n{'='*120}")
        print(f"Testing with Price Filter: {label}")
        print(f"{'='*120}")

        result = backtest_with_price_filter(test_symbols, days=60, min_price=min_price)
        if result:
            results[min_price] = result

    # Summary comparison
    print("\n" + "=" * 120)
    print("📊 PRICE FILTER COMPARISON SUMMARY")
    print("=" * 120)
    print(f"{'Filter':<15} {'Trades':<10} {'Win Rate':<15} {'Gap Trap %':<15} {'Avg Return':<15} {'Filtered Out':<15}")
    print("-" * 120)

    for min_price in price_filters:
        if min_price in results:
            r = results[min_price]
            label = f"${min_price}+" if min_price > 0 else "No Filter"
            trap_rate = r['gap_trap_rate']

            print(f"{label:<15} {r['total_trades']:<10} {r['success_rate']:>6.1f}%        {trap_rate:>6.1f}%        {r['avg_return']:>+7.2f}%      {r['filtered_out']:<15}")

    print("\n" + "=" * 120)
    print("💡 RECOMMENDATIONS:")
    print("=" * 120)
    print("Look for:")
    print("  1. Which price filter gives LOWEST gap trap %")
    print("  2. Which filter gives HIGHEST win rate")
    print("  3. Balance between filtering out bad trades vs keeping good opportunities")
    print("=" * 120)

if __name__ == '__main__':
    run_comparison_backtest()
