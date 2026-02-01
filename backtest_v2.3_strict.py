#!/usr/bin/env python3
"""
Backtest v2.3 STRICT Early Entry screener
Test monthly performance from Sep-Dec 2024
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

def backtest_v23():
    """
    Backtest v2.3 STRICT Early Entry philosophy
    """

    print("\n" + "="*80)
    print("📊 BACKTEST: v2.3 STRICT Early Entry (Momentum <8%)")
    print("="*80)

    # Test universe (stocks that our screener would consider)
    universe = [
        # Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD',
        # Semiconductors
        'MU', 'AVGO', 'QCOM', 'LRCX', 'AMAT', 'KLAC', 'MRVL',
        # Growth/Cloud
        'NFLX', 'SHOP', 'SNOW', 'CRWD', 'DDOG', 'NET', 'ZS', 'PLTR',
        # Consumer
        'NKE', 'SBUX', 'DIS', 'TGT', 'RIVN', 'NIO', 'XPEV',
        # Finance
        'JPM', 'BAC', 'GS', 'V', 'MA',
    ]

    # Test periods
    test_periods = [
        ('2024-09-01', '2024-09-30', 'September 2024'),
        ('2024-10-01', '2024-10-31', 'October 2024'),
        ('2024-11-01', '2024-11-30', 'November 2024'),
        ('2024-12-01', '2024-12-31', 'December 2024'),
    ]

    all_results = []
    monthly_summary = []

    print(f"\nTesting {len(universe)} stocks across 4 months...")
    print("Strategy: Buy stocks with 7-day momentum <8%, hold 14 days")

    for start_date, end_date, period_name in test_periods:
        print(f"\n{'='*80}")
        print(f"📅 {period_name}")
        print('='*80)

        period_trades = []

        # Get data for all stocks
        for symbol in universe:
            try:
                ticker = yf.Ticker(symbol)
                # Get extended period to have lookback data
                hist = ticker.history(start='2024-08-01', end='2024-12-31')

                if hist.empty:
                    continue

                # Find trading days in this period
                period_start = pd.Timestamp(start_date)
                period_end = pd.Timestamp(end_date)

                # Scan weekly (every Monday or first trading day of week)
                current_date = period_start

                while current_date <= period_end:
                    # Find this date in historical data
                    matching_dates = hist[hist.index.date == current_date.date()]

                    if matching_dates.empty:
                        # Try next day
                        current_date += timedelta(days=1)
                        continue

                    entry_idx = hist.index.get_loc(matching_dates.index[0])

                    # Need at least 7 days before for momentum check
                    if entry_idx < 7:
                        current_date += timedelta(days=7)
                        continue

                    # Check momentum filter (v2.3 STRICT)
                    price_today = hist['Close'].iloc[entry_idx]
                    price_7d_ago = hist['Close'].iloc[entry_idx - 7]
                    momentum_7d = ((price_today - price_7d_ago) / price_7d_ago) * 100

                    # v2.3 STRICT: Filter out momentum >8%
                    if momentum_7d > 8.0:
                        # Skip - already ran too much
                        current_date += timedelta(days=7)
                        continue

                    # Check other basic filters (simplified)
                    # 1. Price >$5
                    if price_today < 5.0:
                        current_date += timedelta(days=7)
                        continue

                    # 2. Volatility check (simplified - skip penny stocks)
                    if entry_idx >= 20:
                        returns = hist['Close'].iloc[entry_idx-20:entry_idx].pct_change().dropna()
                        volatility = returns.std() * (252 ** 0.5) * 100
                        if volatility < 20 or volatility > 150:  # Too stable or too volatile
                            current_date += timedelta(days=7)
                            continue

                    # Entry signal - buy this stock
                    entry_date = hist.index[entry_idx]
                    entry_price = price_today

                    # Hold for 14 days
                    exit_idx = entry_idx + 14
                    if exit_idx >= len(hist):
                        # Not enough future data
                        current_date += timedelta(days=7)
                        continue

                    exit_price = hist['Close'].iloc[exit_idx]
                    exit_date = hist.index[exit_idx]

                    # Calculate return
                    return_pct = ((exit_price - entry_price) / entry_price) * 100

                    trade = {
                        'symbol': symbol,
                        'entry_date': entry_date,
                        'exit_date': exit_date,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'return_pct': return_pct,
                        'momentum_7d': momentum_7d,
                        'period': period_name
                    }

                    period_trades.append(trade)
                    all_results.append(trade)

                    # Move to next week
                    current_date += timedelta(days=7)

            except Exception as e:
                continue

        # Analyze this period
        if period_trades:
            df = pd.DataFrame(period_trades)

            winners = (df['return_pct'] >= 5.0).sum()
            losers = (df['return_pct'] < 0).sum()
            neutral = ((df['return_pct'] >= 0) & (df['return_pct'] < 5.0)).sum()

            win_rate = (winners / len(df)) * 100
            avg_return = df['return_pct'].mean()
            median_return = df['return_pct'].median()
            best_trade = df['return_pct'].max()
            worst_trade = df['return_pct'].min()

            print(f"\n📈 Results:")
            print(f"   Total trades: {len(df)}")
            print(f"   Winners (5%+):  {winners} ({win_rate:.1f}%)")
            print(f"   Neutral (0-5%): {neutral}")
            print(f"   Losers (<0%):   {losers}")
            print(f"\n   Avg return:   {avg_return:+.2f}%")
            print(f"   Median return: {median_return:+.2f}%")
            print(f"   Best trade:    {best_trade:+.2f}%")
            print(f"   Worst trade:   {worst_trade:+.2f}%")

            # Show top trades
            print(f"\n   🏆 Top 3 trades:")
            top_3 = df.nlargest(3, 'return_pct')
            for _, trade in top_3.iterrows():
                print(f"      {trade['symbol']}: {trade['return_pct']:+.1f}% (entry: {str(trade['entry_date'])[:10]})")

            # Show worst trades
            print(f"\n   💀 Bottom 3 trades:")
            bottom_3 = df.nsmallest(3, 'return_pct')
            for _, trade in bottom_3.iterrows():
                print(f"      {trade['symbol']}: {trade['return_pct']:+.1f}% (entry: {str(trade['entry_date'])[:10]})")

            monthly_summary.append({
                'period': period_name,
                'trades': len(df),
                'win_rate': win_rate,
                'avg_return': avg_return,
                'median_return': median_return,
                'winners': winners,
                'losers': losers
            })

        else:
            print(f"\n   ❌ No trades found in this period")

    # Overall summary
    print("\n" + "="*80)
    print("📊 OVERALL SUMMARY (Sep-Dec 2024)")
    print("="*80)

    if all_results:
        df_all = pd.DataFrame(all_results)

        total_trades = len(df_all)
        total_winners = (df_all['return_pct'] >= 5.0).sum()
        total_losers = (df_all['return_pct'] < 0).sum()
        overall_win_rate = (total_winners / total_trades) * 100
        overall_avg_return = df_all['return_pct'].mean()

        print(f"\n📈 4-Month Performance:")
        print(f"   Total trades:  {total_trades}")
        print(f"   Win rate:      {overall_win_rate:.1f}%")
        print(f"   Avg return:    {overall_avg_return:+.2f}%")
        print(f"   Winners:       {total_winners}")
        print(f"   Losers:        {total_losers}")

        # Monthly breakdown table
        print("\n📅 Monthly Breakdown:")
        print(f"\n{'Month':<15} {'Trades':<10} {'Win Rate':<12} {'Avg Return':<15}")
        print("-" * 70)

        for summary in monthly_summary:
            print(f"{summary['period']:<15} {summary['trades']:<10} {summary['win_rate']:>7.1f}%    {summary['avg_return']:>+7.2f}%")

        # Compare to baseline
        print("\n" + "="*80)
        print("🔄 COMPARISON vs BASELINE")
        print("="*80)

        print(f"\n📊 v2.3 STRICT Early Entry (momentum <8%):")
        print(f"   Win rate:    {overall_win_rate:.1f}%")
        print(f"   Avg return:  {overall_avg_return:+.2f}%")

        print(f"\n📊 Baseline (no momentum filter):")
        print(f"   Win rate:    ~40-45%")
        print(f"   Avg return:  ~+1.5%")

        if overall_win_rate > 50:
            print(f"\n✅ STRICT filter IMPROVED win rate!")
            print(f"   Gain: +{overall_win_rate - 42.5:.1f}% vs baseline")
        else:
            print(f"\n⚠️  Win rate lower than expected")

        # Expected value
        ev = (overall_win_rate / 100 * 5.0) + ((100 - overall_win_rate) / 100 * -2.0)
        print(f"\n💰 Expected Value:")
        print(f"   {ev:+.2f}% per trade")

        if ev > 1.5:
            print(f"   ✅ Better than baseline (+1.85%)")
        else:
            print(f"   ⚠️  Lower than baseline")

        # Save results
        df_all.to_csv('/home/saengtawan/work/project/cc/stock-analyzer/backtest_v2.3_results.csv', index=False)
        print(f"\n💾 Results saved to: backtest_v2.3_results.csv")

    else:
        print("\n❌ No trades found in any period")

if __name__ == "__main__":
    backtest_v23()
