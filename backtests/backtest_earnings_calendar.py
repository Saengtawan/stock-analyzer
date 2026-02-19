#!/usr/bin/env python3
"""
Earnings Calendar Strategy - Buy Before Earnings, Sell After

Strategy:
- Identify earnings announcement dates (historical)
- Buy 1 day before earnings (at close)
- Sell 1 day after earnings (at close)
- Test if this is profitable with high confidence

Method:
Since we don't have historical earnings calendar API, we'll use:
1. Detect likely earnings dates by pattern (huge volume + big move)
2. Test buying 1-2 days before these events
3. Calculate win rate and returns
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

class EarningsCalendarBacktest:
    """Backtest earnings-based trading strategy"""

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

    def detect_likely_earnings_dates(self, data: pd.DataFrame) -> List[int]:
        """
        Detect likely earnings dates using patterns:
        - Big move (8%+ up or down)
        - High volume (3x+ average)
        - These are strong indicators of earnings announcements
        """
        if len(data) < 22:
            return []

        # Calculate metrics
        data['volume_20d_avg'] = data['Volume'].rolling(20).mean()
        data['volume_ratio'] = data['Volume'] / data['volume_20d_avg']
        data['daily_return'] = data['Close'].pct_change(1) * 100
        data['abs_return'] = data['daily_return'].abs()

        likely_earnings = []

        for i in range(20, len(data)):
            volume_ratio = data['volume_ratio'].iloc[i]
            abs_return = data['abs_return'].iloc[i]

            # Pattern: Big move (8%+) + High volume (3x+) = Likely earnings
            if abs_return >= 8.0 and volume_ratio >= 3.0:
                likely_earnings.append(i)

        return likely_earnings

    def backtest_earnings_strategy(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """
        Backtest strategy:
        1. Detect likely earnings dates
        2. Simulate buying 1 day before
        3. Selling 1 day after
        4. Calculate returns
        """
        data = self.get_price_data(symbol, start_date, end_date)

        if data.empty or len(data) < 25:
            return []

        likely_earnings_indices = self.detect_likely_earnings_dates(data)

        if not likely_earnings_indices:
            return []

        trades = []

        for earnings_idx in likely_earnings_indices:
            # Buy 1 day before earnings (if possible)
            buy_idx = earnings_idx - 1
            if buy_idx < 0:
                continue

            # Sell 1 day after earnings (if possible)
            sell_idx = earnings_idx + 1
            if sell_idx >= len(data):
                continue

            buy_date = data.index[buy_idx]
            earnings_date = data.index[earnings_idx]
            sell_date = data.index[sell_idx]

            buy_price = data['Close'].iloc[buy_idx]
            earnings_close = data['Close'].iloc[earnings_idx]
            sell_price = data['Close'].iloc[sell_idx]

            # Calculate returns
            earnings_day_return = ((earnings_close - buy_price) / buy_price) * 100
            total_return = ((sell_price - buy_price) / buy_price) * 100

            # Earnings metrics
            earnings_volume_ratio = data['volume_ratio'].iloc[earnings_idx]
            earnings_move = data['daily_return'].iloc[earnings_idx]
            earnings_abs_move = abs(earnings_move)

            # Classify result
            if total_return >= 10.0:
                result = 'BIG_WIN'
            elif total_return >= 5.0:
                result = 'WIN'
            elif total_return >= 0:
                result = 'SMALL_WIN'
            elif total_return >= -5.0:
                result = 'SMALL_LOSS'
            else:
                result = 'BIG_LOSS'

            trades.append({
                'symbol': symbol,
                'buy_date': buy_date,
                'earnings_date': earnings_date,
                'sell_date': sell_date,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'earnings_day_return': earnings_day_return,
                'total_return': total_return,
                'earnings_move': earnings_move,
                'earnings_abs_move': earnings_abs_move,
                'earnings_volume_ratio': earnings_volume_ratio,
                'result': result,
                'profitable': total_return >= 0
            })

        return trades

    def run_backtest(
        self,
        symbols: List[str],
        start_date: str = '2023-01-01',
        end_date: str = '2025-01-01'
    ) -> pd.DataFrame:
        """Run earnings calendar backtest"""

        print("\n" + "="*80)
        print("EARNINGS CALENDAR STRATEGY - Buy Before, Sell After")
        print("="*80)
        print(f"Period: {start_date} to {end_date}")
        print(f"Symbols: {len(symbols)}")
        print("Strategy: Buy 1 day before earnings, Sell 1 day after")
        print("="*80 + "\n")

        all_results = []

        for idx, symbol in enumerate(symbols):
            print(f"[{idx+1}/{len(symbols)}] Testing {symbol}...", end='')

            trades = self.backtest_earnings_strategy(symbol, start_date, end_date)

            if not trades:
                print(" No earnings detected")
                continue

            wins = sum(1 for t in trades if t['profitable'])
            avg_return = np.mean([t['total_return'] for t in trades])

            print(f" {len(trades)} earnings, {wins}/{len(trades)} wins ({wins/len(trades)*100:.1f}%), avg: {avg_return:+.1f}%")

            all_results.extend(trades)

        self.results = pd.DataFrame(all_results)

        # Save results
        output_file = 'backtests/earnings_calendar_results.csv'
        self.results.to_csv(output_file, index=False)
        print(f"\n✅ Results saved to: {output_file}")

        return self.results

    def analyze_results(self) -> Dict:
        """Analyze earnings strategy results"""

        if self.results.empty:
            print("\n❌ No earnings trades found")
            return {'recommendation': 'SKIP', 'reason': 'No trades'}

        print("\n" + "="*80)
        print("EARNINGS STRATEGY ANALYSIS")
        print("="*80)

        total_trades = len(self.results)
        profitable_trades = self.results[self.results['profitable'] == True]
        win_count = len(profitable_trades)
        win_rate = (win_count / total_trades) * 100

        # Returns
        avg_return = self.results['total_return'].mean()
        median_return = self.results['total_return'].median()
        best_trade = self.results.loc[self.results['total_return'].idxmax()]
        worst_trade = self.results.loc[self.results['total_return'].idxmin()]

        print(f"\n📊 Overall Statistics:")
        print(f"  Total earnings trades: {total_trades}")
        print(f"  Profitable: {win_count}")
        print(f"  Win rate: {win_rate:.1f}%")

        print(f"\n💰 Returns:")
        print(f"  Avg return: {avg_return:+.1f}%")
        print(f"  Median return: {median_return:+.1f}%")
        print(f"  Best: {best_trade['symbol']} {best_trade['earnings_date']} → {best_trade['total_return']:+.1f}%")
        print(f"  Worst: {worst_trade['symbol']} {worst_trade['earnings_date']} → {worst_trade['total_return']:+.1f}%")

        # Result breakdown
        print(f"\n🎯 Result Breakdown:")
        result_counts = self.results['result'].value_counts()
        for result, count in result_counts.items():
            pct = count / total_trades * 100
            print(f"  {result}: {count} ({pct:.1f}%)")

        # Earnings move direction analysis
        print(f"\n📈 Earnings Move Analysis:")
        positive_earnings = self.results[self.results['earnings_move'] > 0]
        negative_earnings = self.results[self.results['earnings_move'] < 0]

        if len(positive_earnings) > 0:
            pos_win_rate = (positive_earnings['profitable'] == True).sum() / len(positive_earnings) * 100
            pos_avg_return = positive_earnings['total_return'].mean()
            print(f"  Positive earnings moves: {len(positive_earnings)}")
            print(f"    Win rate: {pos_win_rate:.1f}%")
            print(f"    Avg return: {pos_avg_return:+.1f}%")

        if len(negative_earnings) > 0:
            neg_win_rate = (negative_earnings['profitable'] == True).sum() / len(negative_earnings) * 100
            neg_avg_return = negative_earnings['total_return'].mean()
            print(f"  Negative earnings moves: {len(negative_earnings)}")
            print(f"    Win rate: {neg_win_rate:.1f}%")
            print(f"    Avg return: {neg_avg_return:+.1f}%")

        # Big movers (10%+) analysis
        big_movers = self.results[self.results['earnings_abs_move'] >= 10]
        if len(big_movers) > 0:
            print(f"\n🚀 Big Earnings Moves (10%+):")
            print(f"  Count: {len(big_movers)}")
            big_win_rate = (big_movers['profitable'] == True).sum() / len(big_movers) * 100
            big_avg_return = big_movers['total_return'].mean()
            print(f"  Win rate: {big_win_rate:.1f}%")
            print(f"  Avg return: {big_avg_return:+.1f}%")

        # Frequency
        days_in_period = (pd.to_datetime(self.results['earnings_date']).max() -
                         pd.to_datetime(self.results['earnings_date']).min()).days
        trades_per_month = total_trades / (days_in_period / 30)

        print(f"\n📅 Frequency:")
        print(f"  Earnings trades per month: {trades_per_month:.1f}")

        # Decision criteria
        print(f"\n" + "="*80)
        print("DECISION CRITERIA:")
        print("="*80)

        criteria_met = []
        criteria_failed = []

        if win_rate >= 55:
            criteria_met.append(f"✅ Win rate ({win_rate:.1f}%) >= 55%")
        else:
            criteria_failed.append(f"❌ Win rate ({win_rate:.1f}%) < 55%")

        if avg_return >= 2.0:
            criteria_met.append(f"✅ Avg return ({avg_return:.1f}%) >= 2%")
        else:
            criteria_failed.append(f"❌ Avg return ({avg_return:.1f}%) < 2%")

        if trades_per_month >= 2.0:
            criteria_met.append(f"✅ Frequency ({trades_per_month:.1f}/month) >= 2")
        else:
            criteria_failed.append(f"❌ Frequency ({trades_per_month:.1f}/month) < 2")

        for c in criteria_met:
            print(f"  {c}")
        for c in criteria_failed:
            print(f"  {c}")

        print(f"\n" + "="*80)

        if len(criteria_met) >= 2:
            print("🎯 RECOMMENDATION: ✅ IMPLEMENT (with caution)")
            print(f"   Reason: {len(criteria_met)}/3 criteria met")
            recommendation = 'IMPLEMENT'
        else:
            print("🎯 RECOMMENDATION: ❌ SKIP")
            print(f"   Reason: Only {len(criteria_met)}/3 criteria met")
            recommendation = 'SKIP'

        print("="*80 + "\n")

        print("⚠️  IMPORTANT NOTES:")
        print("  - This assumes you can predict earnings dates (need real calendar)")
        print("  - Real-world: earnings dates known weeks in advance")
        print("  - Risk: earnings can gap down just as easily as up")
        print("  - Better strategy: wait for post-earnings gap, then trade momentum")

        return {
            'total_trades': total_trades,
            'win_count': win_count,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'median_return': median_return,
            'trades_per_month': trades_per_month,
            'recommendation': recommendation,
            'criteria_met': len(criteria_met)
        }


def main():
    """Run earnings calendar backtest"""

    # Test symbols (companies with quarterly earnings)
    test_symbols = [
        # Tech giants (earnings-driven stocks)
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

    backtest = EarningsCalendarBacktest()

    # Run backtest
    results = backtest.run_backtest(
        symbols=test_symbols,
        start_date='2023-01-01',
        end_date='2025-01-01'
    )

    # Analyze results
    if not results.empty:
        metrics = backtest.analyze_results()

        # Save metrics
        with open('backtests/earnings_calendar_metrics.json', 'w') as f:
            metrics_clean = {k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                           for k, v in metrics.items()}
            json.dump(metrics_clean, f, indent=2)

        print("✅ Metrics saved to: backtests/earnings_calendar_metrics.json")


if __name__ == '__main__':
    main()
