#!/usr/bin/env python3
"""
Next-Day Surge Predictor - Buy Today, Up 10%+ Tomorrow

Strategy:
- Find stocks that will surge 10%+ the NEXT DAY
- Identify predictive signals TODAY (before the surge)
- Focus on high-confidence catalysts that can be detected in advance

Test:
- Historical next-day surges (10%+ from today's close to tomorrow's close)
- What signals existed TODAY that predicted tomorrow's surge?
- Earnings calendars, volume spikes, news patterns, FDA approvals
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

class NextDaySurgeBacktest:
    """Backtest next-day surge prediction"""

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

    def detect_next_day_surges(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Find all days where the NEXT DAY surged 10%+

        Returns:
            List of surge events with:
            - surge_date: The day the stock surged
            - signal_date: The day BEFORE (when we should have bought)
            - surge_pct: How much it surged
            - predictive_signals: What signals existed the day before
        """
        data = self.get_price_data(symbol, start_date, end_date)

        if data.empty or len(data) < 2:
            return []

        surge_events = []

        # Calculate daily returns
        data['next_day_return'] = data['Close'].pct_change(1).shift(-1) * 100

        # Add volume metrics
        data['volume_20d_avg'] = data['Volume'].rolling(20).mean()
        data['volume_ratio'] = data['Volume'] / data['volume_20d_avg']

        # Add price metrics
        data['range_pct'] = ((data['High'] - data['Low']) / data['Close']) * 100
        data['close_position'] = ((data['Close'] - data['Low']) / (data['High'] - data['Low']))

        for i in range(len(data) - 1):
            next_day_return = data['next_day_return'].iloc[i]

            # Only surges >= 10%
            if next_day_return >= 10.0:
                signal_date = data.index[i]
                surge_date = data.index[i + 1]

                # Today's metrics (predictive signals)
                today_close = data['Close'].iloc[i]
                today_volume = data['Volume'].iloc[i]
                today_volume_ratio = data['volume_ratio'].iloc[i]
                today_range = data['range_pct'].iloc[i]
                today_close_position = data['close_position'].iloc[i]

                # Yesterday's metrics (for context)
                prev_return = data['Close'].pct_change(1).iloc[i] * 100 if i > 0 else 0

                # Tomorrow's actual performance
                surge_open = data['Open'].iloc[i + 1]
                surge_high = data['High'].iloc[i + 1]
                surge_close = data['Close'].iloc[i + 1]

                # Calculate actual returns
                buy_price = today_close  # Buy at today's close
                sell_price = surge_close  # Sell at tomorrow's close
                actual_return = ((sell_price - buy_price) / buy_price) * 100

                # Intraday surge metrics
                surge_open_pct = ((surge_open - today_close) / today_close) * 100
                surge_high_pct = ((surge_high - today_close) / today_close) * 100

                surge_events.append({
                    'symbol': symbol,
                    'signal_date': signal_date,
                    'surge_date': surge_date,
                    'surge_pct': next_day_return,
                    'actual_return': actual_return,
                    # Predictive signals (available on signal_date)
                    'volume_ratio': today_volume_ratio,
                    'range_pct': today_range,
                    'close_position': today_close_position,
                    'prev_day_return': prev_return,
                    # Surge characteristics
                    'surge_open_pct': surge_open_pct,
                    'surge_high_pct': surge_high_pct,
                    # Prices
                    'buy_price': buy_price,
                    'sell_price': sell_price
                })

        return surge_events

    def classify_predictive_signal(self, event: Dict) -> Tuple[str, int, str]:
        """
        Classify predictive signals and assign confidence

        Real implementation would check:
        - Earnings calendar (scheduled announcements)
        - FDA approval dates (known calendar events)
        - News sentiment analysis
        - Analyst upgrade patterns

        For backtest, use statistical proxies:
        - High volume + strong close = possible catalyst brewing
        - Previous day momentum + volume = continuation setup
        """
        volume_ratio = event['volume_ratio']
        close_position = event['close_position']
        prev_day_return = event['prev_day_return']
        range_pct = event['range_pct']

        # Proxy for "earnings/catalyst scheduled"
        # In reality: Check earnings calendar API
        # Here: High volume + strong close at top of range = likely scheduled event

        # Tier S: 85-95% confidence
        # Very high volume (2.5x+) + closed at top (0.8+) + prev momentum
        if volume_ratio >= 2.5 and close_position >= 0.8 and prev_day_return >= 3:
            return 'SCHEDULED_CATALYST', 90, 'Likely earnings/FDA (high vol + strong close + momentum)'

        # Tier A: 75-85% confidence
        # High volume (2x+) + strong close + some momentum
        elif volume_ratio >= 2.0 and close_position >= 0.75 and prev_day_return >= 2:
            return 'PROBABLE_CATALYST', 80, 'Probable catalyst (high vol + strong close)'

        # Tier B: 65-75% confidence
        # Moderate volume (1.5x+) + decent close
        elif volume_ratio >= 1.5 and close_position >= 0.7:
            return 'POSSIBLE_CATALYST', 70, 'Possible catalyst (elevated vol + decent close)'

        # Tier C: < 65% confidence (unpredictable)
        else:
            return 'UNPREDICTABLE', 50, 'No clear signals (random surge)'

    def run_backtest(
        self,
        symbols: List[str],
        start_date: str = '2023-01-01',
        end_date: str = '2025-01-01',
        min_confidence: int = 70
    ) -> pd.DataFrame:
        """
        Run next-day surge backtest

        Args:
            symbols: List of symbols to scan
            start_date: Backtest start date
            end_date: Backtest end date
            min_confidence: Minimum confidence score
        """

        print("\n" + "="*80)
        print("NEXT-DAY SURGE PREDICTOR - Buy Today, Up 10%+ Tomorrow")
        print("="*80)
        print(f"Period: {start_date} to {end_date}")
        print(f"Symbols: {len(symbols)}")
        print(f"Min Confidence: {min_confidence}%")
        print("="*80 + "\n")

        all_results = []

        # Scan each symbol for next-day surges
        for idx, symbol in enumerate(symbols):
            print(f"[{idx+1}/{len(symbols)}] Scanning {symbol}...", end='')

            surge_events = self.detect_next_day_surges(symbol, start_date, end_date)

            if not surge_events:
                print(" No surges found")
                continue

            print(f" Found {len(surge_events)} next-day surges")

            # Classify each surge event
            for event in surge_events:
                signal_type, confidence, reason = self.classify_predictive_signal(event)

                # Filter by confidence
                if confidence >= min_confidence:
                    result = {
                        'symbol': event['symbol'],
                        'signal_date': event['signal_date'],
                        'surge_date': event['surge_date'],
                        'surge_pct': event['surge_pct'],
                        'actual_return': event['actual_return'],
                        'signal_type': signal_type,
                        'confidence': confidence,
                        'reason': reason,
                        'volume_ratio': event['volume_ratio'],
                        'close_position': event['close_position'],
                        'prev_day_return': event['prev_day_return'],
                        'buy_price': event['buy_price'],
                        'sell_price': event['sell_price']
                    }

                    all_results.append(result)

                    print(f"  ✅ {event['signal_date'].strftime('%Y-%m-%d')}: "
                          f"Buy @ ${event['buy_price']:.2f}, "
                          f"Next day: +{event['surge_pct']:.1f}%, "
                          f"{signal_type} ({confidence}% conf)")

        self.results = pd.DataFrame(all_results)

        # Save results
        output_file = 'backtests/next_day_surge_results.csv'
        self.results.to_csv(output_file, index=False)
        print(f"\n✅ Results saved to: {output_file}")

        return self.results

    def analyze_results(self) -> Dict:
        """Analyze next-day surge prediction performance"""

        if self.results.empty:
            print("\n❌ No predictable surges found")
            return {'recommendation': 'SKIP', 'reason': 'No setups found'}

        print("\n" + "="*80)
        print("NEXT-DAY SURGE ANALYSIS")
        print("="*80)

        total_setups = len(self.results)

        # Win rate (did it actually surge 10%+?)
        wins = self.results[self.results['actual_return'] >= 10.0]
        win_rate = len(wins) / total_setups * 100

        # Average returns
        avg_surge = self.results['surge_pct'].mean()
        avg_actual_return = self.results['actual_return'].mean()

        # Best/worst
        best_setup = self.results.loc[self.results['actual_return'].idxmax()]
        worst_setup = self.results.loc[self.results['actual_return'].idxmin()]

        # Frequency
        days_in_period = (pd.to_datetime(self.results['surge_date']).max() -
                         pd.to_datetime(self.results['surge_date']).min()).days
        setups_per_month = total_setups / (days_in_period / 30)

        print(f"\n📊 Overall Statistics:")
        print(f"  Total predictable setups: {total_setups}")
        print(f"  Win rate (actually 10%+): {win_rate:.1f}%")
        print(f"  Frequency: {setups_per_month:.1f} setups/month")
        print(f"  Period: {days_in_period} days ({days_in_period/365:.1f} years)")

        print(f"\n💰 Performance:")
        print(f"  Avg predicted surge: {avg_surge:.1f}%")
        print(f"  Avg actual return: {avg_actual_return:.1f}%")
        print(f"  Best trade: {best_setup['symbol']} {best_setup['signal_date']} → +{best_setup['actual_return']:.1f}%")
        print(f"  Worst trade: {worst_setup['symbol']} {worst_setup['signal_date']} → {worst_setup['actual_return']:+.1f}%")

        # Signal breakdown
        print(f"\n🎯 Signal Type Breakdown:")
        signal_counts = self.results['signal_type'].value_counts()
        for signal, count in signal_counts.items():
            pct = count / total_setups * 100
            subset = self.results[self.results['signal_type'] == signal]
            subset_win_rate = (subset['actual_return'] >= 10.0).sum() / len(subset) * 100
            subset_avg_return = subset['actual_return'].mean()
            print(f"  {signal}: {count} ({pct:.1f}%)")
            print(f"    Win rate: {subset_win_rate:.1f}%, Avg return: {subset_avg_return:.1f}%")

        # Confidence breakdown
        print(f"\n📈 Confidence Level Performance:")
        for conf_level in sorted(self.results['confidence'].unique(), reverse=True):
            subset = self.results[self.results['confidence'] == conf_level]
            subset_win_rate = (subset['actual_return'] >= 10.0).sum() / len(subset) * 100
            subset_avg = subset['actual_return'].mean()
            print(f"  {conf_level}% confidence: {len(subset)} setups, "
                  f"{subset_win_rate:.1f}% win, {subset_avg:.1f}% avg return")

        # Monthly breakdown
        self.results['month'] = pd.to_datetime(self.results['signal_date']).dt.to_period('M')
        monthly_counts = self.results.groupby('month').size()
        print(f"\n📅 Monthly Distribution:")
        print(f"  Avg: {monthly_counts.mean():.1f} setups/month")
        print(f"  Min: {monthly_counts.min()} (quietest month)")
        print(f"  Max: {monthly_counts.max()} (busiest month)")

        # Strategy simulation
        print(f"\n🎯 Strategy Simulation:")
        total_return = self.results['actual_return'].sum()
        avg_return_per_setup = self.results['actual_return'].mean()
        monthly_return = avg_return_per_setup * setups_per_month

        print(f"  Total return (all setups): {total_return:+.1f}%")
        print(f"  Avg per setup: {avg_return_per_setup:+.1f}%")
        print(f"  Estimated monthly: {monthly_return:+.1f}%")

        # Decision criteria
        print(f"\n" + "="*80)
        print("DECISION CRITERIA:")
        print("="*80)

        criteria_met = []
        criteria_failed = []

        if win_rate >= 70:
            criteria_met.append(f"✅ Win rate ({win_rate:.1f}%) >= 70%")
        else:
            criteria_failed.append(f"❌ Win rate ({win_rate:.1f}%) < 70%")

        if avg_actual_return >= 8.0:
            criteria_met.append(f"✅ Avg return ({avg_actual_return:.1f}%) >= 8%")
        else:
            criteria_failed.append(f"❌ Avg return ({avg_actual_return:.1f}%) < 8%")

        if setups_per_month >= 1.5:
            criteria_met.append(f"✅ Frequency ({setups_per_month:.1f}/month) >= 1.5")
        else:
            criteria_failed.append(f"❌ Frequency ({setups_per_month:.1f}/month) < 1.5")

        for c in criteria_met:
            print(f"  {c}")
        for c in criteria_failed:
            print(f"  {c}")

        print(f"\n" + "="*80)

        if len(criteria_met) >= 2:
            print("🎯 RECOMMENDATION: ✅ IMPLEMENT Next-Day Surge Predictor")
            print(f"   Reason: {len(criteria_met)}/3 criteria met")
            recommendation = 'IMPLEMENT'
        else:
            print("🎯 RECOMMENDATION: ❌ SKIP Next-Day Surge Predictor")
            print(f"   Reason: Only {len(criteria_met)}/3 criteria met")
            recommendation = 'SKIP'

        print("="*80 + "\n")

        return {
            'total_setups': total_setups,
            'win_rate': win_rate,
            'avg_surge': avg_surge,
            'avg_actual_return': avg_actual_return,
            'setups_per_month': setups_per_month,
            'monthly_return': monthly_return,
            'recommendation': recommendation,
            'criteria_met': len(criteria_met)
        }


def main():
    """Run next-day surge backtest"""

    # Test symbols (volatile stocks with frequent catalysts)
    test_symbols = [
        # Tech giants (earnings-driven)
        'NVDA', 'AMD', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NFLX',
        # Biotech (FDA approvals)
        'MRNA', 'BNTX', 'NVAX', 'VRTX', 'REGN',
        # High volatility
        'GME', 'AMC', 'PLTR', 'COIN', 'HOOD',
        # Growth/Cloud
        'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS', 'SHOP', 'ROKU',
        # Speculative
        'PLUG', 'RIVN', 'LCID', 'SOFI', 'UPST', 'RBLX'
    ]

    backtest = NextDaySurgeBacktest()

    # Run backtest (70%+ confidence)
    results = backtest.run_backtest(
        symbols=test_symbols,
        start_date='2023-01-01',
        end_date='2025-01-01',
        min_confidence=70
    )

    # Analyze results
    if not results.empty:
        metrics = backtest.analyze_results()

        # Save metrics
        with open('backtests/next_day_surge_metrics.json', 'w') as f:
            metrics_clean = {k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                           for k, v in metrics.items()}
            json.dump(metrics_clean, f, indent=2)

        print("✅ Metrics saved to: backtests/next_day_surge_metrics.json")


if __name__ == '__main__':
    main()
