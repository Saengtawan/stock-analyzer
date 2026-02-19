#!/usr/bin/env python3
"""
Next-Day Surge Predictor - FORWARD TESTING (No Hindsight Bias)

Correct Strategy:
1. Find ALL days with predictive signals (volume spike + strong close)
2. Check what % actually surged 10%+ the next day
3. Calculate TRUE win rate (not hindsight-biased)

This is the CORRECT way to backtest prediction strategies.
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

class NextDaySurgeForwardTest:
    """Forward test next-day surge prediction (NO HINDSIGHT BIAS)"""

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

    def detect_signals_forward(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """
        FORWARD TESTING: Find ALL days with predictive signals
        Then check what % actually surged

        NO HINDSIGHT - We scan for signals first, THEN see what happened
        """
        data = self.get_price_data(symbol, start_date, end_date)

        if data.empty or len(data) < 22:
            return []

        signals = []

        # Calculate indicators
        data['volume_20d_avg'] = data['Volume'].rolling(20).mean()
        data['volume_ratio'] = data['Volume'] / data['volume_20d_avg']
        data['close_position'] = ((data['Close'] - data['Low']) / (data['High'] - data['Low']))
        data['daily_return'] = data['Close'].pct_change(1) * 100
        data['next_day_return'] = data['Close'].pct_change(1).shift(-1) * 100

        for i in range(20, len(data) - 1):  # Need 20 days for volume avg, and 1 day for next_day_return
            # TODAY's signals (what we can see NOW)
            volume_ratio = data['volume_ratio'].iloc[i]
            close_position = data['close_position'].iloc[i]
            prev_day_return = data['daily_return'].iloc[i]

            # Check for SCHEDULED_CATALYST signal (90% conf)
            if volume_ratio >= 2.5 and close_position >= 0.8 and prev_day_return >= 3:
                signal_type = 'SCHEDULED_CATALYST'
                confidence = 90
            # PROBABLE_CATALYST (80% conf)
            elif volume_ratio >= 2.0 and close_position >= 0.75 and prev_day_return >= 2:
                signal_type = 'PROBABLE_CATALYST'
                confidence = 80
            # POSSIBLE_CATALYST (70% conf)
            elif volume_ratio >= 1.5 and close_position >= 0.7:
                signal_type = 'POSSIBLE_CATALYST'
                confidence = 70
            else:
                continue  # No signal

            # TOMORROW's outcome (what actually happened)
            next_day_return = data['next_day_return'].iloc[i]
            surged = next_day_return >= 10.0 if not pd.isna(next_day_return) else False

            today_date = data.index[i]
            tomorrow_date = data.index[i + 1]

            signals.append({
                'symbol': symbol,
                'signal_date': today_date,
                'next_date': tomorrow_date,
                'signal_type': signal_type,
                'confidence': confidence,
                'volume_ratio': volume_ratio,
                'close_position': close_position,
                'prev_day_return': prev_day_return,
                # Outcome
                'next_day_return': next_day_return if not pd.isna(next_day_return) else 0,
                'surged_10pct': surged,
                'buy_price': data['Close'].iloc[i],
                'sell_price': data['Close'].iloc[i + 1] if i + 1 < len(data) else data['Close'].iloc[i]
            })

        return signals

    def run_backtest(
        self,
        symbols: List[str],
        start_date: str = '2023-01-01',
        end_date: str = '2025-01-01'
    ) -> pd.DataFrame:
        """
        Run FORWARD backtest (correct way)
        """

        print("\n" + "="*80)
        print("NEXT-DAY SURGE FORWARD TEST - No Hindsight Bias")
        print("="*80)
        print(f"Period: {start_date} to {end_date}")
        print(f"Symbols: {len(symbols)}")
        print("Testing ALL signals, not just successful ones")
        print("="*80 + "\n")

        all_results = []

        # Scan each symbol for signals
        for idx, symbol in enumerate(symbols):
            print(f"[{idx+1}/{len(symbols)}] Scanning {symbol}...", end='')

            signals = self.detect_signals_forward(symbol, start_date, end_date)

            if not signals:
                print(" No signals")
                continue

            surges = sum(1 for s in signals if s['surged_10pct'])
            print(f" {len(signals)} signals, {surges} surged (win rate: {surges/len(signals)*100:.1f}%)")

            all_results.extend(signals)

        self.results = pd.DataFrame(all_results)

        # Save results
        output_file = 'backtests/next_day_surge_forward_results.csv'
        self.results.to_csv(output_file, index=False)
        print(f"\n✅ Results saved to: {output_file}")

        return self.results

    def analyze_results(self) -> Dict:
        """Analyze forward test results"""

        if self.results.empty:
            print("\n❌ No signals found")
            return {'recommendation': 'SKIP', 'reason': 'No signals found'}

        print("\n" + "="*80)
        print("FORWARD TEST ANALYSIS (TRUE WIN RATES)")
        print("="*80)

        total_signals = len(self.results)
        surges = self.results[self.results['surged_10pct'] == True]
        total_surges = len(surges)
        true_win_rate = (total_surges / total_signals) * 100

        print(f"\n📊 Overall Statistics:")
        print(f"  Total signals generated: {total_signals}")
        print(f"  Actually surged 10%+: {total_surges}")
        print(f"  TRUE WIN RATE: {true_win_rate:.1f}%")

        # Confidence breakdown
        print(f"\n🎯 Performance by Confidence Level:")
        for conf_level in sorted(self.results['confidence'].unique(), reverse=True):
            subset = self.results[self.results['confidence'] == conf_level]
            subset_surges = subset[subset['surged_10pct'] == True]
            subset_win_rate = len(subset_surges) / len(subset) * 100
            subset_avg_return = subset['next_day_return'].mean()

            print(f"\n  {conf_level}% Confidence ({subset.iloc[0]['signal_type']}):")
            print(f"    Total signals: {len(subset)}")
            print(f"    Surges: {len(subset_surges)}")
            print(f"    Win rate: {subset_win_rate:.1f}%")
            print(f"    Avg next-day return: {subset_avg_return:+.1f}%")

            if subset_win_rate >= 70:
                print(f"    ✅ USABLE (win rate >= 70%)")
            else:
                print(f"    ❌ NOT USABLE (win rate < 70%)")

        # Signal type breakdown
        print(f"\n📈 Performance by Signal Type:")
        signal_types = self.results.groupby('signal_type')
        for signal_type, group in signal_types:
            surged = group[group['surged_10pct'] == True]
            win_rate = len(surged) / len(group) * 100
            avg_return = group['next_day_return'].mean()

            print(f"  {signal_type}: {len(group)} signals, {win_rate:.1f}% win, {avg_return:+.1f}% avg")

        # Average returns
        avg_return_all = self.results['next_day_return'].mean()
        avg_return_surges = surges['next_day_return'].mean() if len(surges) > 0 else 0

        print(f"\n💰 Returns:")
        print(f"  Avg next-day return (all signals): {avg_return_all:+.1f}%")
        print(f"  Avg next-day return (surges only): {avg_return_surges:+.1f}%")

        # Frequency
        days_in_period = (pd.to_datetime(self.results['signal_date']).max() -
                         pd.to_datetime(self.results['signal_date']).min()).days
        signals_per_month = total_signals / (days_in_period / 30)
        surges_per_month = total_surges / (days_in_period / 30)

        print(f"\n📅 Frequency:")
        print(f"  Signals per month: {signals_per_month:.1f}")
        print(f"  Actual surges per month: {surges_per_month:.1f}")

        # Decision criteria
        print(f"\n" + "="*80)
        print("DECISION CRITERIA:")
        print("="*80)

        criteria_met = []
        criteria_failed = []

        if true_win_rate >= 50:
            criteria_met.append(f"✅ Win rate ({true_win_rate:.1f}%) >= 50%")
        else:
            criteria_failed.append(f"❌ Win rate ({true_win_rate:.1f}%) < 50%")

        if avg_return_all >= 2.0:
            criteria_met.append(f"✅ Avg return ({avg_return_all:.1f}%) >= 2%")
        else:
            criteria_failed.append(f"❌ Avg return ({avg_return_all:.1f}%) < 2%")

        if surges_per_month >= 1.0:
            criteria_met.append(f"✅ Frequency ({surges_per_month:.1f}/month) >= 1")
        else:
            criteria_failed.append(f"❌ Frequency ({surges_per_month:.1f}/month) < 1")

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

        return {
            'total_signals': total_signals,
            'total_surges': total_surges,
            'true_win_rate': true_win_rate,
            'avg_return_all': avg_return_all,
            'avg_return_surges': avg_return_surges,
            'signals_per_month': signals_per_month,
            'surges_per_month': surges_per_month,
            'recommendation': recommendation,
            'criteria_met': len(criteria_met)
        }


def main():
    """Run forward backtest"""

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

    backtest = NextDaySurgeForwardTest()

    # Run forward backtest
    results = backtest.run_backtest(
        symbols=test_symbols,
        start_date='2023-01-01',
        end_date='2025-01-01'
    )

    # Analyze results
    if not results.empty:
        metrics = backtest.analyze_results()

        # Save metrics
        with open('backtests/next_day_surge_forward_metrics.json', 'w') as f:
            metrics_clean = {k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                           for k, v in metrics.items()}
            json.dump(metrics_clean, f, indent=2)

        print("✅ Metrics saved to: backtests/next_day_surge_forward_metrics.json")


if __name__ == '__main__':
    main()
