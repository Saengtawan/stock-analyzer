#!/usr/bin/env python3
"""
Post-Earnings Momentum Strategy - Buy After Good Earnings, Ride Momentum

Strategy:
- Wait for earnings announcement + positive gap (8%+)
- Buy at market open on earnings day
- Hold for 1-5 days to capture continuation momentum
- Test optimal holding period

Question:
- After a good earnings gap, does momentum continue?
- How many days should we hold?
- What's the win rate for each holding period?
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import json

class PostEarningsMomentumBacktest:
    """Backtest post-earnings momentum strategy"""

    def __init__(self):
        self.results = []
        self.cache_dir = 'backtests/cache'
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_price_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Get price data with cache"""
        cache_file = os.path.join(self.cache_dir, f"{symbol}_{start_date}_{end_date}.csv")

        if os.path.exists(cache_file):
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df

        try:
            data = yf.download(symbol, start=start_date, end=end_date, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            if not data.empty:
                data.to_csv(cache_file)
            return data
        except Exception as e:
            print(f"Error downloading {symbol}: {e}")
            return pd.DataFrame()

    def detect_positive_earnings_gaps(self, data: pd.DataFrame) -> List[Dict]:
        """
        Detect positive earnings gaps (likely good earnings):
        - Gap up 8%+ from prev close to open
        - High volume (3x+ average)
        """
        if len(data) < 22:
            return []

        # Calculate metrics
        data['volume_20d_avg'] = data['Volume'].rolling(20).mean()
        data['volume_ratio'] = data['Volume'] / data['volume_20d_avg']
        data['gap_pct'] = ((data['Open'] - data['Close'].shift(1)) / data['Close'].shift(1)) * 100

        positive_gaps = []

        for i in range(20, len(data)):
            gap_pct = data['gap_pct'].iloc[i]
            volume_ratio = data['volume_ratio'].iloc[i]

            # Positive earnings gap: 8%+ gap up + 3x volume
            if gap_pct >= 8.0 and volume_ratio >= 3.0:
                positive_gaps.append({
                    'index': i,
                    'date': data.index[i],
                    'gap_pct': gap_pct,
                    'volume_ratio': volume_ratio,
                    'prev_close': data['Close'].iloc[i-1],
                    'open': data['Open'].iloc[i],
                    'close': data['Close'].iloc[i]
                })

        return positive_gaps

    def backtest_momentum_holds(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        hold_periods: List[int] = [1, 2, 3, 5, 7]
    ) -> List[Dict]:
        """
        Backtest different holding periods after positive earnings gap

        Strategy:
        - Buy at open on earnings day (after gap up)
        - Test selling after 1, 2, 3, 5, 7 days
        - Calculate returns for each holding period
        """
        data = self.get_price_data(symbol, start_date, end_date)

        if data.empty or len(data) < 25:
            return []

        positive_gaps = self.detect_positive_earnings_gaps(data)

        if not positive_gaps:
            return []

        trades = []

        for gap_event in positive_gaps:
            earnings_idx = gap_event['index']
            earnings_date = gap_event['date']
            buy_price = gap_event['open']  # Buy at open on earnings day

            # Test each holding period
            for hold_days in hold_periods:
                sell_idx = earnings_idx + hold_days
                if sell_idx >= len(data):
                    continue

                sell_date = data.index[sell_idx]
                sell_price = data['Close'].iloc[sell_idx]

                # Calculate return
                total_return = ((sell_price - buy_price) / buy_price) * 100

                # Intraday return on earnings day
                earnings_day_return = ((gap_event['close'] - buy_price) / buy_price) * 100

                trades.append({
                    'symbol': symbol,
                    'earnings_date': earnings_date,
                    'sell_date': sell_date,
                    'hold_days': hold_days,
                    'gap_pct': gap_event['gap_pct'],
                    'volume_ratio': gap_event['volume_ratio'],
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    'earnings_day_return': earnings_day_return,
                    'total_return': total_return,
                    'profitable': total_return >= 0
                })

        return trades

    def run_backtest(
        self,
        symbols: List[str],
        start_date: str = '2023-01-01',
        end_date: str = '2025-01-01',
        hold_periods: List[int] = [1, 2, 3, 5, 7]
    ) -> pd.DataFrame:
        """Run post-earnings momentum backtest"""

        print("\n" + "="*80)
        print("POST-EARNINGS MOMENTUM STRATEGY")
        print("="*80)
        print(f"Period: {start_date} to {end_date}")
        print(f"Symbols: {len(symbols)}")
        print(f"Hold periods tested: {hold_periods}")
        print("Strategy: Buy at open after positive earnings gap, test different exits")
        print("="*80 + "\n")

        all_results = []

        for idx, symbol in enumerate(symbols):
            print(f"[{idx+1}/{len(symbols)}] Testing {symbol}...", end='')

            trades = self.backtest_momentum_holds(symbol, start_date, end_date, hold_periods)

            if not trades:
                print(" No positive earnings gaps")
                continue

            num_events = len(set(t['earnings_date'] for t in trades))
            print(f" {num_events} earnings gaps, {len(trades)} total trades")

            all_results.extend(trades)

        self.results = pd.DataFrame(all_results)

        # Save results
        output_file = 'backtests/post_earnings_momentum_results.csv'
        self.results.to_csv(output_file, index=False)
        print(f"\n✅ Results saved to: {output_file}")

        return self.results

    def analyze_results(self) -> Dict:
        """Analyze post-earnings momentum results"""

        if self.results.empty:
            print("\n❌ No positive earnings gaps found")
            return {'recommendation': 'SKIP', 'reason': 'No trades'}

        print("\n" + "="*80)
        print("POST-EARNINGS MOMENTUM ANALYSIS")
        print("="*80)

        # Overall stats
        total_events = len(self.results['earnings_date'].unique())
        print(f"\n📊 Overall Statistics:")
        print(f"  Total positive earnings gaps: {total_events}")

        # Analyze by holding period
        print(f"\n📈 Performance by Holding Period:")
        print(f"  {'Hold Days':<12} {'Trades':<8} {'Win Rate':<12} {'Avg Return':<12} {'Median':<12}")
        print(f"  {'-'*60}")

        hold_period_stats = {}

        for hold_days in sorted(self.results['hold_days'].unique()):
            subset = self.results[self.results['hold_days'] == hold_days]

            wins = subset[subset['profitable'] == True]
            win_rate = len(wins) / len(subset) * 100
            avg_return = subset['total_return'].mean()
            median_return = subset['total_return'].median()

            print(f"  {hold_days:<12} {len(subset):<8} {win_rate:>6.1f}%     {avg_return:>+6.1f}%      {median_return:>+6.1f}%")

            hold_period_stats[hold_days] = {
                'trades': len(subset),
                'win_rate': win_rate,
                'avg_return': avg_return,
                'median_return': median_return
            }

        # Find optimal holding period
        best_hold = max(hold_period_stats.items(), key=lambda x: x[1]['avg_return'])
        print(f"\n  ⭐ Best holding period: {best_hold[0]} days ({best_hold[1]['avg_return']:+.1f}% avg)")

        # Best and worst trades
        best_trade = self.results.loc[self.results['total_return'].idxmax()]
        worst_trade = self.results.loc[self.results['total_return'].idxmin()]

        print(f"\n💰 Best/Worst Trades:")
        print(f"  Best: {best_trade['symbol']} {best_trade['earnings_date']} "
              f"({best_trade['hold_days']}d hold) → {best_trade['total_return']:+.1f}%")
        print(f"  Worst: {worst_trade['symbol']} {worst_trade['earnings_date']} "
              f"({worst_trade['hold_days']}d hold) → {worst_trade['total_return']:+.1f}%")

        # Gap size vs continuation
        print(f"\n🚀 Gap Size vs Momentum Continuation:")
        small_gaps = self.results[self.results['gap_pct'] < 10]
        medium_gaps = self.results[(self.results['gap_pct'] >= 10) & (self.results['gap_pct'] < 15)]
        large_gaps = self.results[self.results['gap_pct'] >= 15]

        if len(small_gaps) > 0:
            print(f"  Small gaps (8-10%): {len(small_gaps)} trades, "
                  f"{(small_gaps['profitable']==True).sum()/len(small_gaps)*100:.1f}% win, "
                  f"{small_gaps['total_return'].mean():+.1f}% avg")
        if len(medium_gaps) > 0:
            print(f"  Medium gaps (10-15%): {len(medium_gaps)} trades, "
                  f"{(medium_gaps['profitable']==True).sum()/len(medium_gaps)*100:.1f}% win, "
                  f"{medium_gaps['total_return'].mean():+.1f}% avg")
        if len(large_gaps) > 0:
            print(f"  Large gaps (15%+): {len(large_gaps)} trades, "
                  f"{(large_gaps['profitable']==True).sum()/len(large_gaps)*100:.1f}% win, "
                  f"{large_gaps['total_return'].mean():+.1f}% avg")

        # Earnings day performance
        earnings_day_data = self.results.drop_duplicates(subset=['symbol', 'earnings_date'])
        avg_earnings_day = earnings_day_data['earnings_day_return'].mean()
        earnings_day_wins = (earnings_day_data['earnings_day_return'] >= 0).sum()
        earnings_day_win_rate = earnings_day_wins / len(earnings_day_data) * 100

        print(f"\n📅 Earnings Day (Day 0) Performance:")
        print(f"  Avg return (open to close): {avg_earnings_day:+.1f}%")
        print(f"  Win rate: {earnings_day_win_rate:.1f}%")

        # Frequency
        days_in_period = (pd.to_datetime(self.results['earnings_date']).max() -
                         pd.to_datetime(self.results['earnings_date']).min()).days
        events_per_month = total_events / (days_in_period / 30)

        print(f"\n📅 Frequency:")
        print(f"  Positive earnings gaps per month: {events_per_month:.1f}")

        # Decision criteria (using best holding period)
        best_hold_subset = self.results[self.results['hold_days'] == best_hold[0]]
        best_win_rate = best_hold[1]['win_rate']
        best_avg_return = best_hold[1]['avg_return']

        print(f"\n" + "="*80)
        print("DECISION CRITERIA (Best Holding Period):")
        print("="*80)

        criteria_met = []
        criteria_failed = []

        if best_win_rate >= 60:
            criteria_met.append(f"✅ Win rate ({best_win_rate:.1f}%) >= 60%")
        else:
            criteria_failed.append(f"❌ Win rate ({best_win_rate:.1f}%) < 60%")

        if best_avg_return >= 3.0:
            criteria_met.append(f"✅ Avg return ({best_avg_return:.1f}%) >= 3%")
        else:
            criteria_failed.append(f"❌ Avg return ({best_avg_return:.1f}%) < 3%")

        if events_per_month >= 1.5:
            criteria_met.append(f"✅ Frequency ({events_per_month:.1f}/month) >= 1.5")
        else:
            criteria_failed.append(f"❌ Frequency ({events_per_month:.1f}/month) < 1.5")

        for c in criteria_met:
            print(f"  {c}")
        for c in criteria_failed:
            print(f"  {c}")

        print(f"\n" + "="*80)

        if len(criteria_met) >= 2:
            print("🎯 RECOMMENDATION: ✅ IMPLEMENT Post-Earnings Momentum")
            print(f"   Optimal: Hold {best_hold[0]} days after positive earnings gap")
            recommendation = 'IMPLEMENT'
        else:
            print("🎯 RECOMMENDATION: ❌ SKIP")
            print(f"   Reason: Only {len(criteria_met)}/3 criteria met")
            recommendation = 'SKIP'

        print("="*80 + "\n")

        return {
            'total_events': total_events,
            'best_hold_days': best_hold[0],
            'best_win_rate': best_win_rate,
            'best_avg_return': best_avg_return,
            'events_per_month': events_per_month,
            'recommendation': recommendation,
            'criteria_met': len(criteria_met),
            'hold_period_stats': hold_period_stats
        }


def main():
    """Run post-earnings momentum backtest"""

    # Test symbols
    test_symbols = [
        # Tech giants
        'NVDA', 'AMD', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NFLX',
        # Biotech
        'MRNA', 'BNTX', 'NVAX', 'VRTX', 'REGN',
        # High volatility
        'GME', 'AMC', 'PLTR', 'COIN', 'HOOD',
        # Growth/Cloud
        'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS', 'SHOP', 'ROKU',
        # Speculative
        'PLUG', 'RIVN', 'LCID', 'SOFI', 'UPST', 'RBLX'
    ]

    backtest = PostEarningsMomentumBacktest()

    # Run backtest
    results = backtest.run_backtest(
        symbols=test_symbols,
        start_date='2023-01-01',
        end_date='2025-01-01',
        hold_periods=[1, 2, 3, 5, 7]
    )

    # Analyze results
    if not results.empty:
        metrics = backtest.analyze_results()

        # Save metrics
        with open('backtests/post_earnings_momentum_metrics.json', 'w') as f:
            # Convert nested dict properly
            metrics_clean = {}
            for k, v in metrics.items():
                if k == 'hold_period_stats':
                    # Convert hold period stats
                    metrics_clean[k] = {
                        str(hold): {
                            stat_k: float(stat_v) if isinstance(stat_v, (np.integer, np.floating)) else stat_v
                            for stat_k, stat_v in stats.items()
                        }
                        for hold, stats in v.items()
                    }
                else:
                    metrics_clean[k] = float(v) if isinstance(v, (np.integer, np.floating)) else v
            json.dump(metrics_clean, f, indent=2)

        print("✅ Metrics saved to: backtests/post_earnings_momentum_metrics.json")


if __name__ == '__main__':
    main()
