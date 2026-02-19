#!/usr/bin/env python3
"""
Comprehensive Gap Scanner Backtest

Tests:
1. After-hours gaps (4PM-8PM)
2. Pre-market gaps (6AM-9:30AM)
3. Intraday breakouts (9:30AM-4PM) ← เพิ่มใหม่
4. Multiple confidence levels (70%, 80%, 90%)
5. Risk analysis (what if wrong?)
6. Rotation timing comparison
7. Hold period analysis

Goal: มั่นใจจริงๆ ก่อน implement
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

class ComprehensiveGapBacktest:
    """Comprehensive backtest for gap scanner"""

    def __init__(self):
        self.results = []
        self.cache_dir = 'backtests/cache'
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_price_data(self, symbol: str, start_date: str, end_date: str, interval='1d') -> pd.DataFrame:
        """Get price data with cache"""
        cache_file = os.path.join(
            self.cache_dir,
            f"{symbol}_{start_date}_{end_date}_{interval}.csv"
        )

        if os.path.exists(cache_file):
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df

        try:
            data = yf.download(symbol, start=start_date, end=end_date, interval=interval, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            if not data.empty:
                data.to_csv(cache_file)
            return data
        except Exception as e:
            print(f"Error downloading {symbol}: {e}")
            return pd.DataFrame()

    def detect_overnight_gaps(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """Detect overnight gaps (close → next open)"""
        data = self.get_price_data(symbol, start_date, end_date, interval='1d')

        if data.empty or len(data) < 2:
            return []

        gaps = []

        for i in range(1, len(data)):
            prev_close = data['Close'].iloc[i-1]
            today_open = data['Open'].iloc[i]
            today_high = data['High'].iloc[i]
            today_close = data['Close'].iloc[i]
            today_volume = data['Volume'].iloc[i]

            gap_pct = ((today_open - prev_close) / prev_close) * 100

            if gap_pct >= 5.0:
                day_return = ((today_close - today_open) / today_open) * 100
                high_from_open = ((today_high - today_open) / today_open) * 100
                gap_held = today_close >= today_open

                gaps.append({
                    'symbol': symbol,
                    'type': 'OVERNIGHT_GAP',
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

        return gaps

    def detect_intraday_breakouts(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Detect intraday breakouts (9:30 AM - 4 PM)
        Spike 8%+ within 1 hour during market hours
        """
        # Get 1-hour data
        data = self.get_price_data(symbol, start_date, end_date, interval='1h')

        if data.empty or len(data) < 2:
            return []

        breakouts = []

        for i in range(1, len(data)):
            # Skip if not market hours (9:30 AM - 4 PM ET)
            hour = data.index[i].hour
            if hour < 9 or hour >= 16:
                continue

            prev_close = data['Close'].iloc[i-1]
            curr_open = data['Open'].iloc[i]
            curr_high = data['High'].iloc[i]
            curr_close = data['Close'].iloc[i]
            curr_volume = data['Volume'].iloc[i]

            # Calculate 1-hour spike
            spike_pct = ((curr_high - prev_close) / prev_close) * 100

            # Intraday breakout: 8%+ spike in 1 hour
            if spike_pct >= 8.0:
                # Get end-of-day price
                day_date = data.index[i].date()
                eod_data = self.get_price_data(symbol, str(day_date), str(day_date + timedelta(days=1)), '1d')

                if not eod_data.empty:
                    eod_close = eod_data['Close'].iloc[0]
                    eod_return = ((eod_close - curr_high) / curr_high) * 100

                    breakouts.append({
                        'symbol': symbol,
                        'type': 'INTRADAY_BREAKOUT',
                        'date': data.index[i],
                        'hour': hour,
                        'prev_close': prev_close,
                        'breakout_price': curr_high,
                        'eod_close': eod_close,
                        'volume': curr_volume,
                        'spike_pct': spike_pct,
                        'eod_return': eod_return,
                        'held': eod_close >= curr_high * 0.98  # Held within 2%
                    })

        return breakouts

    def classify_event(self, event: Dict) -> Tuple[str, int]:
        """
        Classify event and assign confidence

        Overnight gaps:
        - 15%+ gap + held + 5%+ day = 90% confidence
        - 10%+ gap + held + 3%+ day = 80% confidence
        - 8%+ gap + held = 70% confidence

        Intraday breakouts:
        - 12%+ spike + held EOD = 85% confidence
        - 10%+ spike + held EOD = 75% confidence
        - 8%+ spike + held EOD = 65% confidence
        """

        if event['type'] == 'OVERNIGHT_GAP':
            gap_pct = event['gap_pct']
            day_return = event['day_return']
            gap_held = event['gap_held']

            if gap_pct >= 15 and gap_held and day_return >= 5:
                return 'MAJOR_CATALYST', 90
            elif gap_pct >= 10 and gap_held and day_return >= 3:
                return 'CATALYST', 80
            elif gap_pct >= 8 and gap_held:
                return 'POSSIBLE_CATALYST', 70
            else:
                return 'UNCERTAIN', 50

        elif event['type'] == 'INTRADAY_BREAKOUT':
            spike_pct = event['spike_pct']
            held = event['held']

            if spike_pct >= 12 and held:
                return 'INTRADAY_MAJOR', 85
            elif spike_pct >= 10 and held:
                return 'INTRADAY_CATALYST', 75
            elif spike_pct >= 8 and held:
                return 'INTRADAY_POSSIBLE', 65
            else:
                return 'UNCERTAIN', 50

        return 'UNKNOWN', 50

    def calculate_rotation_impact(
        self,
        event: Dict,
        current_position_avg_return: float = 2.0
    ) -> Dict:
        """
        Calculate impact of rotating to this event

        Assumes:
        - Current position avg return: 2% (conservative)
        - Rotation cost: 0.1% (slippage + fees)
        """

        if event['type'] == 'OVERNIGHT_GAP':
            # Gain from gap mover
            gap_gain = event['day_return']

        elif event['type'] == 'INTRADAY_BREAKOUT':
            # Gain from breakout to EOD
            gap_gain = event['eod_return']
        else:
            gap_gain = 0

        # Cost of rotation
        rotation_cost = 0.1

        # Opportunity cost (what we gave up)
        opportunity_cost = current_position_avg_return

        # Net benefit
        net_benefit = gap_gain - rotation_cost - opportunity_cost

        return {
            'gap_gain': gap_gain,
            'rotation_cost': rotation_cost,
            'opportunity_cost': opportunity_cost,
            'net_benefit': net_benefit,
            'worth_rotating': net_benefit > 0
        }

    def run_backtest(
        self,
        symbols: List[str],
        start_date: str = '2023-01-01',
        end_date: str = '2025-01-01',
        min_confidence: int = 70
    ) -> pd.DataFrame:
        """Run comprehensive backtest"""

        print("\n" + "="*80)
        print("COMPREHENSIVE GAP SCANNER BACKTEST")
        print("="*80)
        print(f"Period: {start_date} to {end_date}")
        print(f"Symbols: {len(symbols)}")
        print(f"Min Confidence: {min_confidence}%")
        print(f"Scanning: Overnight gaps + Intraday breakouts")
        print("="*80 + "\n")

        all_results = []

        for idx, symbol in enumerate(symbols):
            print(f"\n[{idx+1}/{len(symbols)}] {symbol}")
            print("-" * 40)

            # 1. Overnight gaps
            print(f"  Scanning overnight gaps...", end='')
            overnight_gaps = self.detect_overnight_gaps(symbol, start_date, end_date)
            print(f" {len(overnight_gaps)} found")

            for event in overnight_gaps:
                catalyst_type, confidence = self.classify_event(event)

                if confidence >= min_confidence:
                    rotation_impact = self.calculate_rotation_impact(event)

                    result = {
                        'symbol': event['symbol'],
                        'type': event['type'],
                        'date': event['date'],
                        'hour': None,
                        'move_pct': event['gap_pct'],
                        'return_pct': event['day_return'],
                        'held': event['gap_held'],
                        'catalyst_type': catalyst_type,
                        'confidence': confidence,
                        **rotation_impact
                    }

                    all_results.append(result)

                    worth = "✅" if rotation_impact['worth_rotating'] else "❌"
                    print(f"    {event['date'].strftime('%Y-%m-%d')}: "
                          f"+{event['gap_pct']:.1f}% gap → "
                          f"{event['day_return']:+.1f}% day "
                          f"({confidence}% conf) "
                          f"{worth} Net: {rotation_impact['net_benefit']:+.1f}%")

            # 2. Intraday breakouts
            print(f"  Scanning intraday breakouts...", end='')
            intraday_breakouts = self.detect_intraday_breakouts(symbol, start_date, end_date)
            print(f" {len(intraday_breakouts)} found")

            for event in intraday_breakouts:
                catalyst_type, confidence = self.classify_event(event)

                if confidence >= min_confidence:
                    rotation_impact = self.calculate_rotation_impact(event)

                    result = {
                        'symbol': event['symbol'],
                        'type': event['type'],
                        'date': event['date'],
                        'hour': event['hour'],
                        'move_pct': event['spike_pct'],
                        'return_pct': event['eod_return'],
                        'held': event['held'],
                        'catalyst_type': catalyst_type,
                        'confidence': confidence,
                        **rotation_impact
                    }

                    all_results.append(result)

                    worth = "✅" if rotation_impact['worth_rotating'] else "❌"
                    print(f"    {event['date'].strftime('%Y-%m-%d %H:%M')}: "
                          f"+{event['spike_pct']:.1f}% spike → "
                          f"{event['eod_return']:+.1f}% EOD "
                          f"({confidence}% conf) "
                          f"{worth} Net: {rotation_impact['net_benefit']:+.1f}%")

        self.results = pd.DataFrame(all_results)

        # Save results
        output_file = 'backtests/gap_scanner_comprehensive_results.csv'
        self.results.to_csv(output_file, index=False)
        print(f"\n✅ Results saved to: {output_file}")

        return self.results

    def analyze_results(self) -> Dict:
        """Comprehensive analysis"""

        if self.results.empty:
            print("\n❌ No results found")
            return {'recommendation': 'SKIP'}

        print("\n" + "="*80)
        print("COMPREHENSIVE ANALYSIS")
        print("="*80)

        total = len(self.results)

        # Breakdown by type
        overnight = self.results[self.results['type'] == 'OVERNIGHT_GAP']
        intraday = self.results[self.results['type'] == 'INTRADAY_BREAKOUT']

        print(f"\n📊 Event Breakdown:")
        print(f"  Total events: {total}")
        print(f"  Overnight gaps: {len(overnight)} ({len(overnight)/total*100:.1f}%)")
        print(f"  Intraday breakouts: {len(intraday)} ({len(intraday)/total*100:.1f}%)")

        # Win rate
        wins = self.results[self.results['held'] == True]
        win_rate = len(wins) / total * 100

        print(f"\n💰 Performance:")
        print(f"  Win rate (held): {win_rate:.1f}%")
        print(f"  Avg move: {self.results['move_pct'].mean():.1f}%")
        print(f"  Avg return: {self.results['return_pct'].mean():+.1f}%")

        # Rotation worthiness
        worth_rotating = self.results[self.results['worth_rotating'] == True]
        rotation_rate = len(worth_rotating) / total * 100

        print(f"\n🔄 Rotation Analysis:")
        print(f"  Worth rotating: {len(worth_rotating)}/{total} ({rotation_rate:.1f}%)")
        print(f"  Avg net benefit (when rotating): {worth_rotating['net_benefit'].mean():+.1f}%")
        print(f"  Not worth rotating: {total - len(worth_rotating)} (better to hold current)")

        # Confidence breakdown
        print(f"\n🎯 Confidence Breakdown:")
        for conf_level in sorted(self.results['confidence'].unique(), reverse=True):
            subset = self.results[self.results['confidence'] == conf_level]
            subset_win_rate = (subset['held'] == True).sum() / len(subset) * 100
            subset_worth = (subset['worth_rotating'] == True).sum() / len(subset) * 100
            print(f"  {conf_level}%: {len(subset)} events, "
                  f"Win: {subset_win_rate:.1f}%, "
                  f"Worth: {subset_worth:.1f}%")

        # Timing analysis
        print(f"\n⏰ Timing Analysis:")
        print(f"  Overnight gaps:")
        if len(overnight) > 0:
            print(f"    Count: {len(overnight)}")
            print(f"    Win rate: {(overnight['held']==True).sum()/len(overnight)*100:.1f}%")
            print(f"    Avg return: {overnight['return_pct'].mean():+.1f}%")
            print(f"    Worth rotating: {(overnight['worth_rotating']==True).sum()/len(overnight)*100:.1f}%")

        print(f"  Intraday breakouts:")
        if len(intraday) > 0:
            print(f"    Count: {len(intraday)}")
            print(f"    Win rate: {(intraday['held']==True).sum()/len(intraday)*100:.1f}%")
            print(f"    Avg return: {intraday['return_pct'].mean():+.1f}%")
            print(f"    Worth rotating: {(intraday['worth_rotating']==True).sum()/len(intraday)*100:.1f}%")

            # Hour distribution
            if 'hour' in intraday.columns:
                hour_dist = intraday.groupby('hour').size()
                print(f"    Peak hours: {dict(hour_dist.nlargest(3))}")

        # Risk analysis
        print(f"\n⚠️  Risk Analysis:")
        losses = self.results[self.results['return_pct'] < 0]
        print(f"  Losing trades: {len(losses)}/{total} ({len(losses)/total*100:.1f}%)")
        if len(losses) > 0:
            print(f"  Avg loss: {losses['return_pct'].mean():.1f}%")
            print(f"  Max loss: {losses['return_pct'].min():.1f}%")

        # Monthly estimate
        days_in_period = (self.results['date'].max() - self.results['date'].min()).days
        events_per_month = len(worth_rotating) / (days_in_period / 30)
        monthly_return = worth_rotating['net_benefit'].mean() * events_per_month if len(worth_rotating) > 0 else 0

        print(f"\n📈 Projected Performance:")
        print(f"  Rotation-worthy events: {events_per_month:.1f}/month")
        print(f"  Estimated monthly return: {monthly_return:+.1f}%")
        print(f"  vs Baseline (Rapid Rotation 5%/month): {monthly_return - 5:+.1f}%")

        # Final recommendation
        print(f"\n" + "="*80)
        print("DECISION CRITERIA:")
        print("="*80)

        criteria_met = []
        criteria_failed = []

        if win_rate >= 70:
            criteria_met.append(f"✅ Win rate ({win_rate:.1f}%) >= 70%")
        else:
            criteria_failed.append(f"❌ Win rate ({win_rate:.1f}%) < 70%")

        if rotation_rate >= 60:
            criteria_met.append(f"✅ Rotation worthiness ({rotation_rate:.1f}%) >= 60%")
        else:
            criteria_failed.append(f"❌ Rotation worthiness ({rotation_rate:.1f}%) < 60%")

        if monthly_return >= 5.0:
            criteria_met.append(f"✅ Monthly return ({monthly_return:.1f}%) >= 5%")
        else:
            criteria_failed.append(f"❌ Monthly return ({monthly_return:.1f}%) < 5%")

        if events_per_month >= 0.5:
            criteria_met.append(f"✅ Frequency ({events_per_month:.1f}/month) >= 0.5")
        else:
            criteria_failed.append(f"❌ Frequency ({events_per_month:.1f}/month) < 0.5")

        for c in criteria_met:
            print(f"  {c}")
        for c in criteria_failed:
            print(f"  {c}")

        print(f"\n" + "="*80)

        if len(criteria_met) >= 3:
            print("🎯 RECOMMENDATION: ✅ IMPLEMENT Gap Scanner with Rotation")
            print(f"   Reason: {len(criteria_met)}/4 criteria met")
            recommendation = 'IMPLEMENT'
        else:
            print("🎯 RECOMMENDATION: ❌ SKIP Gap Scanner")
            print(f"   Reason: Only {len(criteria_met)}/4 criteria met")
            recommendation = 'SKIP'

        print("="*80 + "\n")

        return {
            'total_events': total,
            'overnight_count': len(overnight),
            'intraday_count': len(intraday),
            'win_rate': win_rate,
            'rotation_rate': rotation_rate,
            'events_per_month': events_per_month,
            'monthly_return': monthly_return,
            'recommendation': recommendation,
            'criteria_met': len(criteria_met)
        }


def main():
    """Run comprehensive backtest"""

    # Expanded symbol list
    test_symbols = [
        # Mega cap tech
        'NVDA', 'AMD', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NFLX',
        # Biotech
        'MRNA', 'BNTX', 'NVAX', 'VRTX', 'REGN', 'BIIB', 'GILD',
        # High volatility
        'GME', 'AMC', 'PLTR', 'COIN', 'HOOD', 'RBLX',
        # Growth/Cloud
        'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS', 'SHOP', 'SQ',
        # Momentum
        'ROKU', 'PLUG', 'LCID', 'RIVN', 'SOFI', 'UPST'
    ]

    backtest = ComprehensiveGapBacktest()

    # Run with 70% min confidence to see more data
    results = backtest.run_backtest(
        symbols=test_symbols,
        start_date='2023-01-01',
        end_date='2025-01-01',
        min_confidence=70
    )

    if not results.empty:
        metrics = backtest.analyze_results()

        # Save metrics
        with open('backtests/gap_scanner_comprehensive_metrics.json', 'w') as f:
            metrics_clean = {k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                           for k, v in metrics.items()}
            json.dump(metrics_clean, f, indent=2)

        print("✅ Metrics saved to: backtests/gap_scanner_comprehensive_metrics.json")


if __name__ == '__main__':
    main()
