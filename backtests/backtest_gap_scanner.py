#!/usr/bin/env python3
"""
Gap Scanner Backtest - High Confidence Pre-Market Movers

Strategy:
- Scan for stocks with 80%+ confidence to gap up 5-25%
- Focus on catalysts: Earnings, FDA, M&A, Contracts
- Rotate existing positions to capture gap moves
- Quality > Quantity (1-2 setups/month is enough)

Test:
- Historical gap-up events (5%+ premarket)
- Identify catalyst type
- Filter for high-confidence only
- Compare rotation vs hold strategy
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

class GapScannerBacktest:
    """Backtest high-confidence gap-up scanner"""

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

    def detect_gap_events(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Detect gap-up events (5%+ from prev close to open)
        Returns list of gap events with details
        """
        data = self.get_price_data(symbol, start_date, end_date)

        if data.empty or len(data) < 2:
            return []

        gap_events = []

        for i in range(1, len(data)):
            prev_close = data['Close'].iloc[i-1]
            today_open = data['Open'].iloc[i]
            today_high = data['High'].iloc[i]
            today_close = data['Close'].iloc[i]
            today_volume = data['Volume'].iloc[i]

            # Calculate gap %
            gap_pct = ((today_open - prev_close) / prev_close) * 100

            # Only gaps >= 5%
            if gap_pct >= 5.0:
                # Calculate if gap held (close above open)
                gap_held = today_close >= today_open

                # Calculate day's performance
                day_return = ((today_close - today_open) / today_open) * 100

                # Calculate high from open
                high_from_open = ((today_high - today_open) / today_open) * 100

                gap_events.append({
                    'symbol': symbol,
                    'date': data.index[i],
                    'prev_close': prev_close,
                    'open': today_open,
                    'high': today_high,
                    'close': today_close,
                    'volume': today_volume,
                    'gap_pct': gap_pct,
                    'day_return': day_return,
                    'high_from_open': high_from_open,
                    'gap_held': gap_held
                })

        return gap_events

    def classify_catalyst(self, gap_event: Dict) -> Tuple[str, float]:
        """
        Classify catalyst type and assign confidence score

        Real implementation would:
        - Check earnings calendar
        - Scan news for FDA/M&A
        - Check analyst upgrades
        - Detect short squeeze

        For backtest, we use statistical proxies:
        - Large gaps (15%+) + volume = likely major catalyst
        - Medium gaps (8-15%) + volume = possible catalyst
        - Small gaps (5-8%) = uncertain
        """
        gap_pct = gap_event['gap_pct']
        day_return = gap_event['day_return']
        gap_held = gap_event['gap_held']

        # Statistical classification (proxy for real catalyst detection)

        # Tier S: 85-95% confidence
        if gap_pct >= 15 and gap_held and day_return >= 5:
            return 'MAJOR_CATALYST', 90

        # Tier A: 75-85% confidence
        elif gap_pct >= 10 and gap_held and day_return >= 3:
            return 'CATALYST', 80

        # Tier B: 65-75% confidence
        elif gap_pct >= 8 and gap_held:
            return 'POSSIBLE_CATALYST', 70

        # Tier C: < 65% confidence (reject)
        else:
            return 'UNCERTAIN', 50

    def run_backtest(
        self,
        symbols: List[str],
        start_date: str = '2023-01-01',
        end_date: str = '2025-01-01',
        min_confidence: int = 80
    ) -> pd.DataFrame:
        """
        Run gap scanner backtest

        Args:
            symbols: List of symbols to scan
            start_date: Backtest start date
            end_date: Backtest end date
            min_confidence: Minimum confidence score (80 = only Tier S/A)
        """

        print("\n" + "="*80)
        print("GAP SCANNER BACKTEST - High Confidence Pre-Market Movers")
        print("="*80)
        print(f"Period: {start_date} to {end_date}")
        print(f"Symbols: {len(symbols)}")
        print(f"Min Confidence: {min_confidence}%")
        print("="*80 + "\n")

        all_results = []

        # Scan each symbol for gap events
        for idx, symbol in enumerate(symbols):
            print(f"[{idx+1}/{len(symbols)}] Scanning {symbol}...", end='')

            gap_events = self.detect_gap_events(symbol, start_date, end_date)

            if not gap_events:
                print(" No gaps found")
                continue

            print(f" Found {len(gap_events)} gaps")

            # Classify each gap event
            for event in gap_events:
                catalyst_type, confidence = self.classify_catalyst(event)

                # Filter by confidence
                if confidence >= min_confidence:
                    result = {
                        'symbol': event['symbol'],
                        'date': event['date'],
                        'gap_pct': event['gap_pct'],
                        'day_return': event['day_return'],
                        'high_from_open': event['high_from_open'],
                        'gap_held': event['gap_held'],
                        'catalyst_type': catalyst_type,
                        'confidence': confidence,
                        'open': event['open'],
                        'close': event['close'],
                        'high': event['high']
                    }

                    all_results.append(result)

                    print(f"  ✅ {event['date'].strftime('%Y-%m-%d')}: "
                          f"+{event['gap_pct']:.1f}% gap, "
                          f"{catalyst_type} ({confidence}% conf), "
                          f"Day: {event['day_return']:+.1f}%")

        self.results = pd.DataFrame(all_results)

        # Save results
        output_file = 'backtests/gap_scanner_results.csv'
        self.results.to_csv(output_file, index=False)
        print(f"\n✅ Results saved to: {output_file}")

        return self.results

    def analyze_results(self) -> Dict:
        """Analyze gap scanner performance"""

        if self.results.empty:
            print("\n❌ No high-confidence gaps found")
            return {'recommendation': 'SKIP', 'reason': 'No setups found'}

        print("\n" + "="*80)
        print("GAP SCANNER ANALYSIS")
        print("="*80)

        total_setups = len(self.results)

        # Win rate (gap held = win)
        wins = self.results[self.results['gap_held'] == True]
        win_rate = len(wins) / total_setups * 100

        # Average returns
        avg_gap = self.results['gap_pct'].mean()
        avg_day_return = self.results['day_return'].mean()
        avg_high_from_open = self.results['high_from_open'].mean()

        # Best/worst
        best_gap = self.results.loc[self.results['gap_pct'].idxmax()]
        worst_gap = self.results.loc[self.results['day_return'].idxmin()]

        # Frequency
        days_in_period = (self.results['date'].max() - self.results['date'].min()).days
        setups_per_month = total_setups / (days_in_period / 30)

        print(f"\n📊 Overall Statistics:")
        print(f"  Total high-confidence setups: {total_setups}")
        print(f"  Win rate (gap held): {win_rate:.1f}%")
        print(f"  Frequency: {setups_per_month:.1f} setups/month")
        print(f"  Period: {days_in_period} days ({days_in_period/365:.1f} years)")

        print(f"\n💰 Performance:")
        print(f"  Avg gap size: {avg_gap:.1f}%")
        print(f"  Avg day return (open→close): {avg_day_return:+.1f}%")
        print(f"  Avg high from open: {avg_high_from_open:+.1f}%")
        print(f"  Best gap: {best_gap['symbol']} {best_gap['date'].strftime('%Y-%m-%d')} +{best_gap['gap_pct']:.1f}%")
        print(f"  Worst day: {worst_gap['symbol']} {worst_gap['date'].strftime('%Y-%m-%d')} {worst_gap['day_return']:+.1f}%")

        # Catalyst breakdown
        print(f"\n🎯 Catalyst Breakdown:")
        catalyst_counts = self.results['catalyst_type'].value_counts()
        for catalyst, count in catalyst_counts.items():
            pct = count / total_setups * 100
            subset = self.results[self.results['catalyst_type'] == catalyst]
            subset_win_rate = (subset['gap_held'] == True).sum() / len(subset) * 100
            print(f"  {catalyst}: {count} ({pct:.1f}%) - Win rate: {subset_win_rate:.1f}%")

        # Monthly breakdown
        self.results['month'] = pd.to_datetime(self.results['date']).dt.to_period('M')
        monthly_counts = self.results.groupby('month').size()
        print(f"\n📅 Monthly Distribution:")
        print(f"  Avg: {monthly_counts.mean():.1f} setups/month")
        print(f"  Min: {monthly_counts.min()} (quietest month)")
        print(f"  Max: {monthly_counts.max()} (busiest month)")

        # Rotation strategy simulation
        print(f"\n🔄 Rotation Strategy Simulation:")
        print(f"  If we rotated into each setup:")

        # Assume entry at open, exit at close
        total_return = self.results['day_return'].sum()
        avg_return_per_setup = self.results['day_return'].mean()

        print(f"    Total return (sum of all): {total_return:+.1f}%")
        print(f"    Avg return per setup: {avg_return_per_setup:+.1f}%")
        print(f"    Estimated monthly: {avg_return_per_setup * setups_per_month:+.1f}%")

        # Compare to baseline (hold 5% avg position)
        baseline_monthly = 5.0  # Assume Rapid Rotation gives 5%/month
        rotation_monthly = avg_return_per_setup * setups_per_month

        print(f"\n📊 vs Baseline (Rapid Rotation 5%/month):")
        if rotation_monthly > baseline_monthly:
            improvement = rotation_monthly - baseline_monthly
            print(f"  ✅ Gap Scanner better: +{improvement:.1f}%/month")
            recommendation = 'IMPLEMENT'
        else:
            degradation = baseline_monthly - rotation_monthly
            print(f"  ❌ Gap Scanner worse: -{degradation:.1f}%/month")
            recommendation = 'SKIP'

        # Decision criteria
        print(f"\n" + "="*80)
        print("DECISION CRITERIA:")
        print("="*80)

        criteria_met = []
        criteria_failed = []

        if win_rate >= 75:
            criteria_met.append(f"✅ Win rate ({win_rate:.1f}%) >= 75%")
        else:
            criteria_failed.append(f"❌ Win rate ({win_rate:.1f}%) < 75%")

        if avg_day_return >= 3.0:
            criteria_met.append(f"✅ Avg day return ({avg_day_return:.1f}%) >= 3%")
        else:
            criteria_failed.append(f"❌ Avg day return ({avg_day_return:.1f}%) < 3%")

        if setups_per_month >= 1.0:
            criteria_met.append(f"✅ Frequency ({setups_per_month:.1f}/month) >= 1")
        else:
            criteria_failed.append(f"❌ Frequency ({setups_per_month:.1f}/month) < 1")

        for c in criteria_met:
            print(f"  {c}")
        for c in criteria_failed:
            print(f"  {c}")

        print(f"\n" + "="*80)

        if len(criteria_met) >= 2:
            print("🎯 RECOMMENDATION: ✅ IMPLEMENT Gap Scanner")
            print(f"   Reason: {len(criteria_met)}/3 criteria met")
        else:
            print("🎯 RECOMMENDATION: ❌ SKIP Gap Scanner")
            print(f"   Reason: Only {len(criteria_met)}/3 criteria met")

        print("="*80 + "\n")

        return {
            'total_setups': total_setups,
            'win_rate': win_rate,
            'avg_gap': avg_gap,
            'avg_day_return': avg_day_return,
            'setups_per_month': setups_per_month,
            'total_return': total_return,
            'rotation_monthly': rotation_monthly,
            'recommendation': recommendation,
            'criteria_met': len(criteria_met),
            'criteria_failed': len(criteria_failed)
        }


def main():
    """Run gap scanner backtest"""

    # Test symbols (high-volume stocks that gap frequently)
    test_symbols = [
        # Tech
        'NVDA', 'AMD', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN',
        # Biotech (frequent FDA news)
        'MRNA', 'BNTX', 'NVAX', 'VRTX', 'REGN',
        # High volatility
        'GME', 'AMC', 'PLTR', 'COIN', 'HOOD',
        # Growth
        'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS'
    ]

    backtest = GapScannerBacktest()

    # Run backtest (80%+ confidence only)
    results = backtest.run_backtest(
        symbols=test_symbols,
        start_date='2023-01-01',
        end_date='2025-01-01',
        min_confidence=80  # Only Tier S/A catalysts
    )

    # Analyze results
    if not results.empty:
        metrics = backtest.analyze_results()

        # Save metrics
        with open('backtests/gap_scanner_metrics.json', 'w') as f:
            metrics_clean = {k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                           for k, v in metrics.items()}
            json.dump(metrics_clean, f, indent=2)

        print("✅ Metrics saved to: backtests/gap_scanner_metrics.json")


if __name__ == '__main__':
    main()
