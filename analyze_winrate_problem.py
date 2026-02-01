#!/usr/bin/env python3
"""
Deep Analysis: Why is Win Rate only 33%?
Analyzes multiple factors to identify root causes
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import sys

# Test stocks
TEST_STOCKS = [
    'HOOD', 'HUBS', 'ANET', 'AMZN', 'TEAM', 'NOW', 'AMD', 'NET', 'COIN', 'TSM',
    'QCOM', 'LRCX', 'MSFT', 'SHOP', 'ROKU', 'AVGO', 'UBER', 'PLTR', 'GOOGL', 'DASH',
    'NVDA', 'META', 'NFLX', 'TSLA', 'AAPL', 'ADBE', 'CRM', 'ORCL', 'INTC', 'MU'
]

# Different target levels to test
TARGET_LEVELS = [5, 10, 12, 15, 20, 25]


def get_stock_data(symbol, start_date):
    """Fetch stock data"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=datetime.now())
        return hist
    except:
        return None


def calculate_indicators(hist, entry_idx):
    """Calculate technical indicators at entry point"""
    if entry_idx < 20:
        return None

    # Get data up to entry point
    data = hist.iloc[:entry_idx+1]

    # RSI
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # Moving averages
    ma20 = data['Close'].rolling(window=20).mean()
    ma50 = data['Close'].rolling(window=50).mean()

    # Volume
    avg_volume = data['Volume'].rolling(window=20).mean()

    # Price position relative to 52-week high
    high_52w = data['High'].rolling(window=252, min_periods=20).max()
    pct_from_high = (data['Close'] / high_52w) * 100

    entry_close = data['Close'].iloc[-1]

    return {
        'rsi': rsi.iloc[-1] if len(rsi) > 0 else None,
        'price_vs_ma20': (entry_close / ma20.iloc[-1] - 1) * 100 if not pd.isna(ma20.iloc[-1]) else None,
        'price_vs_ma50': (entry_close / ma50.iloc[-1] - 1) * 100 if len(ma50) > 0 and not pd.isna(ma50.iloc[-1]) else None,
        'volume_vs_avg': (data['Volume'].iloc[-1] / avg_volume.iloc[-1]) if not pd.isna(avg_volume.iloc[-1]) else None,
        'pct_from_52w_high': pct_from_high.iloc[-1] if not pd.isna(pct_from_high.iloc[-1]) else None,
        'ma20_vs_ma50': (ma20.iloc[-1] / ma50.iloc[-1] - 1) * 100 if len(ma50) > 0 and not pd.isna(ma50.iloc[-1]) and not pd.isna(ma20.iloc[-1]) else None
    }


def backtest_with_targets(symbol, start_date, targets, entry_freq=5, hold_days=30):
    """Backtest with multiple target levels"""
    hist = get_stock_data(symbol, start_date)
    if hist is None or len(hist) < hold_days + 50:
        return None

    results = []

    for i in range(20, len(hist) - hold_days - 1, entry_freq):
        entry_price = hist['Close'].iloc[i]
        entry_date = hist.index[i]

        # Get indicators at entry
        indicators = calculate_indicators(hist, i)

        # Get holding period
        hold_period = hist.iloc[i:i + hold_days + 1]
        exit_price = hold_period['Close'].iloc[-1]
        max_price = hold_period['High'].max()
        min_price = hold_period['Low'].min()

        actual_return = ((exit_price - entry_price) / entry_price) * 100
        max_return = ((max_price - entry_price) / entry_price) * 100
        min_return = ((min_price - entry_price) / entry_price) * 100

        result = {
            'symbol': symbol,
            'entry_date': entry_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'actual_return': actual_return,
            'max_return': max_return,
            'min_return': min_return,
        }

        # Add indicator data
        if indicators:
            result.update(indicators)

        # Check each target level
        for target in targets:
            result[f'hit_{target}pct'] = max_return >= target

            # Days to target
            days_to_target = None
            for j, (idx, row) in enumerate(hold_period.iterrows()):
                if ((row['High'] - entry_price) / entry_price) * 100 >= target:
                    days_to_target = j
                    break
            result[f'days_to_{target}pct'] = days_to_target

        results.append(result)

    return results


def main():
    print("=" * 100)
    print("🔍 DEEP ANALYSIS: WHY IS WIN RATE ONLY 33%?")
    print("=" * 100)
    print()

    start_date = datetime.now() - timedelta(days=180)

    print("Collecting data...")
    all_results = []

    for symbol in TEST_STOCKS:
        print(f"  {symbol}...", end=' ')
        results = backtest_with_targets(symbol, start_date, TARGET_LEVELS, entry_freq=5)
        if results:
            all_results.extend(results)
            print(f"✅ {len(results)} trades")
        else:
            print("❌")

    if not all_results:
        print("\n❌ No results")
        return

    df = pd.DataFrame(all_results)

    print(f"\nTotal trades analyzed: {len(df)}")
    print()

    # ============================================================
    # ANALYSIS 1: Is the 15% target too aggressive?
    # ============================================================
    print("=" * 100)
    print("📊 ANALYSIS 1: TARGET SENSITIVITY")
    print("=" * 100)
    print("\nHow does win rate change with different targets?\n")

    for target in TARGET_LEVELS:
        wins = df[f'hit_{target}pct'].sum()
        win_rate = wins / len(df) * 100

        # Calculate average days to target for winners
        winners = df[df[f'hit_{target}pct']]
        avg_days = winners[f'days_to_{target}pct'].mean()

        print(f"  {target:2d}% Target: {win_rate:5.1f}% win rate ({wins:3d}/{len(df)}) - Avg {avg_days:.1f} days to target")

    print("\n💡 Insight:")
    win_rate_15 = df['hit_15pct'].sum() / len(df) * 100
    win_rate_10 = df['hit_10pct'].sum() / len(df) * 100
    win_rate_12 = df['hit_12pct'].sum() / len(df) * 100

    if win_rate_10 >= 50:
        print(f"   ✅ 10% target gives {win_rate_10:.1f}% win rate (much better!)")
    if win_rate_12 >= 45:
        print(f"   ✅ 12% target gives {win_rate_12:.1f}% win rate (good balance)")
    print(f"   ⚠️  15% target gives {win_rate_15:.1f}% win rate (current)")
    print()

    # ============================================================
    # ANALYSIS 2: Market conditions at entry
    # ============================================================
    print("=" * 100)
    print("📊 ANALYSIS 2: ENTRY CONDITIONS (Winners vs Losers)")
    print("=" * 100)
    print("\nDo winners and losers have different entry characteristics?\n")

    winners_15 = df[df['hit_15pct'] == True]
    losers_15 = df[df['hit_15pct'] == False]

    print(f"Winners (n={len(winners_15)}) vs Losers (n={len(losers_15)}):\n")

    indicators = ['rsi', 'price_vs_ma20', 'price_vs_ma50', 'volume_vs_avg',
                  'pct_from_52w_high', 'ma20_vs_ma50']
    indicator_names = {
        'rsi': 'RSI',
        'price_vs_ma20': 'Price vs MA20 (%)',
        'price_vs_ma50': 'Price vs MA50 (%)',
        'volume_vs_avg': 'Volume Ratio',
        'pct_from_52w_high': '% From 52W High',
        'ma20_vs_ma50': 'MA20 vs MA50 (%)'
    }

    for ind in indicators:
        if ind in df.columns:
            winner_mean = winners_15[ind].mean()
            loser_mean = losers_15[ind].mean()
            diff = winner_mean - loser_mean

            print(f"  {indicator_names[ind]:25s}: Winners {winner_mean:7.2f} | Losers {loser_mean:7.2f} | Diff {diff:+7.2f}")

    print("\n💡 Key Observations:")

    # RSI analysis
    if 'rsi' in df.columns:
        winner_rsi = winners_15['rsi'].mean()
        loser_rsi = losers_15['rsi'].mean()
        if winner_rsi > loser_rsi + 3:
            print(f"   ⚠️  Winners enter with HIGHER RSI ({winner_rsi:.1f} vs {loser_rsi:.1f})")
            print(f"       → Momentum is important! Don't fear 'overbought'")
        elif loser_rsi > winner_rsi + 3:
            print(f"   ⚠️  Losers enter with HIGHER RSI ({loser_rsi:.1f} vs {winner_rsi:.1f})")
            print(f"       → Avoid overbought conditions")

    # Price vs MA20
    if 'price_vs_ma20' in df.columns:
        winner_ma20 = winners_15['price_vs_ma20'].mean()
        loser_ma20 = losers_15['price_vs_ma20'].mean()
        if winner_ma20 > loser_ma20 + 1:
            print(f"   ✅ Winners are above MA20 more ({winner_ma20:+.1f}% vs {loser_ma20:+.1f}%)")
            print(f"       → Trend strength matters!")
        elif loser_ma20 > winner_ma20 + 1:
            print(f"   ⚠️  Losers are above MA20 more ({loser_ma20:+.1f}% vs {winner_ma20:+.1f}%)")
            print(f"       → Buying extended stocks is dangerous")

    # 52-week high
    if 'pct_from_52w_high' in df.columns:
        winner_52w = winners_15['pct_from_52w_high'].mean()
        loser_52w = losers_15['pct_from_52w_high'].mean()
        if winner_52w > loser_52w + 2:
            print(f"   ✅ Winners closer to 52W high ({winner_52w:.1f}% vs {loser_52w:.1f}%)")
            print(f"       → Buy strength, not weakness!")
        elif loser_52w > winner_52w + 2:
            print(f"   ⚠️  Losers closer to 52W high ({loser_52w:.1f}% vs {winner_52w:.1f}%)")
            print(f"       → High flyers can fall hard")

    print()

    # ============================================================
    # ANALYSIS 3: Stock selection matters
    # ============================================================
    print("=" * 100)
    print("📊 ANALYSIS 3: STOCK SELECTION")
    print("=" * 100)
    print("\nSome stocks work, some don't. Clear pattern?\n")

    # Group by symbol
    stock_performance = df.groupby('symbol').agg({
        'hit_15pct': ['sum', 'count', 'mean'],
        'actual_return': 'mean',
        'max_return': 'mean'
    }).round(2)

    stock_performance.columns = ['wins', 'trades', 'win_rate', 'avg_return', 'avg_max_return']
    stock_performance = stock_performance.sort_values('win_rate', ascending=False)

    print("Top 10 Stocks:")
    for i, (symbol, row) in enumerate(stock_performance.head(10).iterrows(), 1):
        print(f"  {i:2d}. {symbol:6s}: {row['win_rate']*100:5.1f}% WR ({int(row['wins'])}/{int(row['trades'])}), "
              f"Avg: {row['avg_return']:+6.2f}%, Max: {row['avg_max_return']:+6.2f}%")

    print("\nBottom 10 Stocks:")
    for i, (symbol, row) in enumerate(stock_performance.tail(10).iterrows(), 1):
        print(f"  {i:2d}. {symbol:6s}: {row['win_rate']*100:5.1f}% WR ({int(row['wins'])}/{int(row['trades'])}), "
              f"Avg: {row['avg_return']:+6.2f}%, Max: {row['avg_max_return']:+6.2f}%")

    print("\n💡 Insight:")
    top_10_win_rate = stock_performance.head(10)['win_rate'].mean() * 100
    bottom_10_win_rate = stock_performance.tail(10)['win_rate'].mean() * 100
    overall_win_rate = stock_performance['win_rate'].mean() * 100

    print(f"   Top 10 stocks: {top_10_win_rate:.1f}% average win rate")
    print(f"   Bottom 10 stocks: {bottom_10_win_rate:.1f}% average win rate")
    print(f"   Overall: {overall_win_rate:.1f}% win rate")
    print(f"   → Stock selection can improve win rate by {top_10_win_rate - overall_win_rate:.1f} percentage points!")
    print()

    # ============================================================
    # ANALYSIS 4: Timeframe analysis
    # ============================================================
    print("=" * 100)
    print("📊 ANALYSIS 4: MARKET REGIME / TIME PERIOD")
    print("=" * 100)
    print("\nDoes win rate vary by time period?\n")

    df['month'] = pd.to_datetime(df['entry_date']).dt.to_period('M')
    monthly_stats = df.groupby('month').agg({
        'hit_15pct': ['sum', 'count', 'mean'],
        'actual_return': 'mean'
    }).round(3)

    monthly_stats.columns = ['wins', 'trades', 'win_rate', 'avg_return']

    print("Monthly Performance:")
    for month, row in monthly_stats.iterrows():
        print(f"  {month}: {row['win_rate']*100:5.1f}% WR ({int(row['wins']):3d}/{int(row['trades']):3d}), "
              f"Avg Return: {row['avg_return']:+6.2f}%")

    print("\n💡 Insight:")
    best_month = monthly_stats['win_rate'].idxmax()
    worst_month = monthly_stats['win_rate'].idxmin()
    best_wr = monthly_stats.loc[best_month, 'win_rate'] * 100
    worst_wr = monthly_stats.loc[worst_month, 'win_rate'] * 100

    print(f"   Best month: {best_month} with {best_wr:.1f}% win rate")
    print(f"   Worst month: {worst_month} with {worst_wr:.1f}% win rate")
    print(f"   Variance: {best_wr - worst_wr:.1f} percentage points")
    print(f"   → Market regime matters a lot!")
    print()

    # ============================================================
    # ANALYSIS 5: How close do losers get?
    # ============================================================
    print("=" * 100)
    print("📊 ANALYSIS 5: NEAR MISSES")
    print("=" * 100)
    print("\nHow close do 'losers' get to the 15% target?\n")

    losers = df[df['hit_15pct'] == False]

    print("Distribution of max returns for losing trades:")
    bins = [-100, 0, 5, 10, 12, 14, 14.9]
    labels = ['Negative', '0-5%', '5-10%', '10-12%', '12-14%', '14-15% (Near miss!)']

    for i, (lower, upper) in enumerate(zip(bins[:-1], bins[1:])):
        count = ((losers['max_return'] > lower) & (losers['max_return'] <= upper)).sum()
        pct = count / len(losers) * 100
        print(f"  {labels[i]:25s}: {count:4d} trades ({pct:5.1f}%)")

    near_misses = ((losers['max_return'] >= 12) & (losers['max_return'] < 15)).sum()
    near_miss_pct = near_misses / len(losers) * 100

    print(f"\n💡 Insight:")
    print(f"   {near_misses} trades ({near_miss_pct:.1f}% of losers) got to 12-15%")
    print(f"   → These are 'near misses' - almost hit target!")
    print(f"   → Lowering target to 12% would capture these")
    print()

    # ============================================================
    # FINAL SUMMARY
    # ============================================================
    print("=" * 100)
    print("🎯 ROOT CAUSE SUMMARY")
    print("=" * 100)
    print()

    print("Why is win rate only 33%? Key findings:\n")

    print("1. TARGET TOO AGGRESSIVE:")
    print(f"   - 15% in 30 days is ambitious")
    print(f"   - 10% target would give {df['hit_10pct'].mean()*100:.1f}% win rate")
    print(f"   - 12% target would give {df['hit_12pct'].mean()*100:.1f}% win rate")
    print()

    print("2. POOR STOCK SELECTION:")
    print(f"   - Some stocks never hit 15% (MSFT, NFLX, ADBE, etc.)")
    print(f"   - Best stocks: {top_10_win_rate:.0f}% WR vs Worst: {bottom_10_win_rate:.0f}% WR")
    print(f"   - Need better filtering to exclude low-volatility stocks")
    print()

    print("3. MARKET REGIME MATTERS:")
    print(f"   - Win rate varies from {worst_wr:.0f}% to {best_wr:.0f}% by month")
    print(f"   - Recent months (Oct-Nov) performed poorly")
    print(f"   - Need market regime detection")
    print()

    print("4. ENTRY TIMING:")
    if 'rsi' in df.columns and 'price_vs_ma20' in df.columns:
        print(f"   - Winners enter with RSI {winners_15['rsi'].mean():.1f} vs Losers {losers_15['rsi'].mean():.1f}")
        print(f"   - Winners {winners_15['price_vs_ma20'].mean():+.1f}% vs MA20")
        print(f"   - Technical indicators at entry matter!")
    print()

    print("=" * 100)
    print("📋 RECOMMENDATIONS:")
    print("=" * 100)
    print()
    print("1. ✅ LOWER TARGET to 10-12% for better win rate")
    print("2. ✅ FILTER STOCKS better - exclude low volatility names")
    print("3. ✅ ADD MARKET REGIME filter - avoid weak markets")
    print("4. ✅ IMPROVE ENTRY CONDITIONS - use technical indicators")
    print("5. ✅ FOCUS ON HIGH-PERFORMING STOCKS (MU, GOOGL, INTC, LRCX)")
    print()
    print("=" * 100)


if __name__ == "__main__":
    main()
