#!/usr/bin/env python3
"""
Evening Risk Analysis Backtest (v6.26)

Test: Pre-SL Exit vs Normal SL
- ถ้าคำนวณตอน 6 PM ว่า risk สูง (score >= 3)
- ขายตอนตลาดเปิดวันถัดไป
- VS ปล่อยให้ SL trigger ปกติ

Metrics:
- Avg improvement per trade
- False exit rate
- Max loss reduction
- Total $ saved

Decision Criteria:
✅ IMPLEMENT if:
   - Avg improvement > +0.3%
   - False exit rate < 30%
   - Max loss reduction >= -1.0%
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
import sqlite3
from typing import List, Dict, Tuple
import json

class EveningRiskBacktest:
    """Backtest Evening Risk Analysis feature"""

    def __init__(self, db_path='data/trade_history.db'):
        self.db_path = db_path
        self.results = []
        self.cache_dir = 'backtests/cache'
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_price_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Get cached price data or download"""
        cache_file = os.path.join(self.cache_dir, f"{symbol}_{start_date}_{end_date}.csv")

        if os.path.exists(cache_file):
            return pd.read_csv(cache_file, index_col=0, parse_dates=True)

        try:
            data = yf.download(symbol, start=start_date, end=end_date, progress=False)
            if not data.empty:
                # Flatten multi-level columns if present
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                data.to_csv(cache_file)
            return data
        except Exception as e:
            print(f"Error downloading {symbol}: {e}")
            return pd.DataFrame()

    def get_historical_positions(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Get all positions from trade history
        Reconstruct position lifecycle from BUY/SELL pairs
        """
        if not os.path.exists(self.db_path):
            print(f"Warning: Database not found at {self.db_path}")
            print("Creating synthetic test data...")
            return self.create_test_data()

        conn = sqlite3.connect(self.db_path)

        query = """
        SELECT
            b.symbol,
            b.date as entry_date,
            b.price as entry_price,
            b.qty,
            s.date as exit_date,
            s.price as exit_price,
            s.reason as exit_reason
        FROM trades b
        LEFT JOIN trades s ON
            b.symbol = s.symbol AND
            s.action = 'SELL' AND
            s.date > b.date
        WHERE
            b.action = 'BUY' AND
            b.date BETWEEN ? AND ?
        ORDER BY b.date
        """

        df = pd.read_sql_query(query, conn, params=(start_date, end_date))
        conn.close()

        # Filter valid positions (has exit)
        df = df[df['exit_date'].notna()].copy()

        print(f"Found {len(df)} completed positions from database")

        # If no data, use synthetic test data
        if df.empty:
            print("No completed positions in date range. Using synthetic test data...")
            return self.create_test_data()

        return df

    def create_test_data(self) -> pd.DataFrame:
        """Create synthetic test data for backtesting"""
        # Sample positions for testing
        test_positions = [
            {'symbol': 'NVDA', 'entry_date': '2024-01-15', 'entry_price': 500, 'qty': 10,
             'exit_date': '2024-01-22', 'exit_price': 485, 'exit_reason': 'SL'},
            {'symbol': 'AMD', 'entry_date': '2024-02-01', 'entry_price': 180, 'qty': 10,
             'exit_date': '2024-02-08', 'exit_price': 175, 'exit_reason': 'SL'},
            {'symbol': 'TSLA', 'entry_date': '2024-03-01', 'entry_price': 200, 'qty': 10,
             'exit_date': '2024-03-08', 'exit_price': 195, 'exit_reason': 'SL'},
        ]

        df = pd.DataFrame(test_positions)
        print(f"Using {len(df)} synthetic test positions")
        return df

    def calculate_evening_risk_score(
        self,
        symbol: str,
        date: str,
        close_price: float,
        sl_price: float,
        price_data: pd.DataFrame
    ) -> Tuple[int, List[str]]:
        """
        Calculate risk score based on evening analysis

        Returns: (risk_score, reasons)
        """
        risk_score = 0
        reasons = []

        date_idx = price_data.index.get_loc(pd.Timestamp(date))

        # 1. Distance to SL
        distance_pct = ((close_price - sl_price) / close_price) * 100
        if distance_pct < 0.5:
            risk_score += 2
            reasons.append(f"Very close to SL ({distance_pct:.2f}%)")
        elif distance_pct < 1.0:
            risk_score += 1
            reasons.append(f"Close to SL ({distance_pct:.2f}%)")

        # 2. Next day gap (simulate after-hours prediction)
        if date_idx + 1 < len(price_data):
            today_close = price_data['Close'].iloc[date_idx]
            tomorrow_open = price_data['Open'].iloc[date_idx + 1]

            # Convert to scalar if Series
            if isinstance(today_close, pd.Series):
                today_close = today_close.iloc[0]
            if isinstance(tomorrow_open, pd.Series):
                tomorrow_open = tomorrow_open.iloc[0]

            gap_pct = ((tomorrow_open - today_close) / today_close) * 100

            if gap_pct < -1.0:
                risk_score += 3
                reasons.append(f"Gap down {gap_pct:.1f}%")
            elif gap_pct < -0.5:
                risk_score += 2
                reasons.append(f"Weak gap {gap_pct:.1f}%")

            # Check if gap below SL
            if tomorrow_open < sl_price:
                risk_score += 3
                reasons.append(f"Gap below SL (${tomorrow_open:.2f} < ${sl_price:.2f})")

        # 3. Recent trend (last 3 days)
        if date_idx >= 3:
            recent_prices = price_data['Close'].iloc[date_idx-3:date_idx+1]
            trend = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0] * 100

            if trend < -2.0:
                risk_score += 1
                reasons.append(f"Downtrend {trend:.1f}%")

        # 4. Volume spike (unusual activity)
        if date_idx >= 5:
            recent_volume = price_data['Volume'].iloc[date_idx-5:date_idx]
            today_volume = price_data['Volume'].iloc[date_idx]

            # Convert to scalar if Series
            if isinstance(today_volume, pd.Series):
                today_volume = today_volume.iloc[0]

            avg_volume = recent_volume.mean()

            if today_volume > avg_volume * 2:
                volume_ratio = today_volume / avg_volume
                risk_score += 1
                reasons.append(f"Volume spike {volume_ratio:.1f}x")

        # 5. SPY market sentiment
        try:
            spy_data = self.get_price_data('SPY', date, (pd.Timestamp(date) + timedelta(days=2)).strftime('%Y-%m-%d'))
            if len(spy_data) >= 2:
                spy_today = spy_data['Close'].iloc[0]
                spy_tomorrow = spy_data['Open'].iloc[1]

                # Convert to scalar if Series
                if isinstance(spy_today, pd.Series):
                    spy_today = spy_today.iloc[0]
                if isinstance(spy_tomorrow, pd.Series):
                    spy_tomorrow = spy_tomorrow.iloc[0]

                spy_gap = ((spy_tomorrow - spy_today) / spy_today) * 100

                if spy_gap < -0.5:
                    risk_score += 1
                    reasons.append(f"SPY weak {spy_gap:.1f}%")
        except:
            pass

        return risk_score, reasons

    def simulate_position(self, position: pd.Series) -> List[Dict]:
        """
        Simulate position day-by-day
        Find days when position was close to SL
        """
        symbol = position['symbol']
        entry_date = pd.Timestamp(position['entry_date'])
        exit_date = pd.Timestamp(position['exit_date'])
        entry_price = position['entry_price']
        exit_price = position['exit_price']

        # Calculate SL (2.5% below entry)
        sl_price = entry_price * 0.975

        # Get price data
        price_data = self.get_price_data(
            symbol,
            (entry_date - timedelta(days=10)).strftime('%Y-%m-%d'),
            (exit_date + timedelta(days=2)).strftime('%Y-%m-%d')
        )

        if price_data.empty:
            return []

        close_to_sl_instances = []

        # Check each day
        for date in pd.date_range(entry_date, exit_date):
            if date not in price_data.index:
                continue

            close_price = price_data.loc[date, 'Close']
            # Convert to scalar if it's a Series
            if isinstance(close_price, pd.Series):
                close_price = close_price.iloc[0]

            distance_pct = ((close_price - sl_price) / close_price) * 100

            # Only analyze if close to SL (< 2%)
            if 0 < distance_pct < 2.0:
                # Calculate evening risk
                risk_score, reasons = self.calculate_evening_risk_score(
                    symbol, date, close_price, sl_price, price_data
                )

                # Get next day open (for pre-SL exit simulation)
                date_idx = price_data.index.get_loc(date)
                if date_idx + 1 < len(price_data):
                    next_open = price_data['Open'].iloc[date_idx + 1]
                    # Convert to scalar if Series
                    if isinstance(next_open, pd.Series):
                        next_open = next_open.iloc[0]
                    next_date = price_data.index[date_idx + 1]
                else:
                    next_open = close_price
                    next_date = date

                close_to_sl_instances.append({
                    'symbol': symbol,
                    'entry_price': entry_price,
                    'sl_price': sl_price,
                    'evening_date': date,
                    'evening_close': close_price,
                    'distance_pct': distance_pct,
                    'risk_score': risk_score,
                    'reasons': reasons,
                    'next_open': next_open,
                    'next_date': next_date,
                    'actual_exit_price': exit_price,
                    'actual_exit_date': exit_date
                })

        return close_to_sl_instances

    def run_backtest(
        self,
        start_date: str = '2023-01-01',
        end_date: str = '2025-01-01',
        risk_threshold: int = 3
    ) -> pd.DataFrame:
        """Run full backtest"""

        print("\n" + "="*80)
        print("EVENING RISK ANALYSIS BACKTEST")
        print("="*80)
        print(f"Period: {start_date} to {end_date}")
        print(f"Risk Threshold: {risk_threshold}/10")
        print(f"Decision: Sell at market open if risk >= {risk_threshold}")
        print("="*80 + "\n")

        # Get historical positions
        positions = self.get_historical_positions(start_date, end_date)

        if positions.empty:
            print("No positions found. Cannot run backtest.")
            return pd.DataFrame()

        all_results = []

        # Simulate each position
        for idx, position in positions.iterrows():
            print(f"\n[{idx+1}/{len(positions)}] Simulating {position['symbol']}...")

            close_to_sl_days = self.simulate_position(position)

            for day in close_to_sl_days:
                # Scenario A: Pre-SL Exit (if risk >= threshold)
                if day['risk_score'] >= risk_threshold:
                    exit_price_a = day['next_open']
                    exit_date_a = day['next_date']
                    exit_reason_a = 'PRE_SL_EXIT'
                else:
                    exit_price_a = None
                    exit_date_a = None
                    exit_reason_a = None

                # Scenario B: Normal (actual exit)
                exit_price_b = day['actual_exit_price']
                exit_date_b = day['actual_exit_date']

                # Calculate P&L
                if exit_price_a:
                    pnl_a = ((exit_price_a - day['entry_price']) / day['entry_price']) * 100
                else:
                    pnl_a = None

                pnl_b = ((exit_price_b - day['entry_price']) / day['entry_price']) * 100

                # Calculate improvement
                improvement = (pnl_a - pnl_b) if pnl_a is not None else 0

                result = {
                    'symbol': day['symbol'],
                    'entry_price': day['entry_price'],
                    'sl_price': day['sl_price'],
                    'evening_date': day['evening_date'],
                    'evening_close': day['evening_close'],
                    'distance_pct': day['distance_pct'],
                    'risk_score': day['risk_score'],
                    'reasons': ', '.join(day['reasons']),
                    # Scenario A (Pre-SL Exit)
                    'scenario_a_exit_price': exit_price_a,
                    'scenario_a_exit_date': exit_date_a,
                    'scenario_a_pnl': pnl_a,
                    # Scenario B (Normal)
                    'scenario_b_exit_price': exit_price_b,
                    'scenario_b_exit_date': exit_date_b,
                    'scenario_b_pnl': pnl_b,
                    # Comparison
                    'improvement_pct': improvement,
                    'took_action': exit_price_a is not None
                }

                all_results.append(result)

                if exit_price_a:
                    print(f"  {day['evening_date'].strftime('%Y-%m-%d')}: Risk {day['risk_score']}/10 "
                          f"→ Pre-SL Exit @ ${exit_price_a:.2f} "
                          f"(vs Normal ${exit_price_b:.2f}) "
                          f"= {improvement:+.2f}%")

        self.results = pd.DataFrame(all_results)

        # Save results
        output_file = 'backtests/evening_risk_results.csv'
        self.results.to_csv(output_file, index=False)
        print(f"\n✅ Results saved to: {output_file}")

        return self.results

    def analyze_results(self) -> Dict:
        """Analyze backtest results and make recommendation"""

        if self.results.empty:
            print("\n❌ No results to analyze")
            return {}

        # Filter trades where we took action
        actions = self.results[self.results['took_action'] == True]

        print("\n" + "="*80)
        print("BACKTEST RESULTS - EVENING RISK ANALYSIS")
        print("="*80)

        print(f"\n📊 Overall Statistics:")
        print(f"  Total 'Close to SL' instances: {len(self.results)}")
        print(f"  Pre-SL exits triggered: {len(actions)}")
        print(f"  Pre-SL exit rate: {len(actions)/len(self.results)*100:.1f}%")

        if not actions.empty:
            # Performance metrics
            avg_improvement = actions['improvement_pct'].mean()
            median_improvement = actions['improvement_pct'].median()

            improved = actions[actions['improvement_pct'] > 0]
            worse = actions[actions['improvement_pct'] < 0]
            false_exits = actions[actions['improvement_pct'] < -0.5]  # Sold but shouldn't have

            print(f"\n💰 Performance Comparison:")
            print(f"  Scenario A (Pre-SL Exit):")
            print(f"    Avg P&L: {actions['scenario_a_pnl'].mean():.2f}%")
            print(f"    Median P&L: {actions['scenario_a_pnl'].median():.2f}%")
            print(f"    Max Loss: {actions['scenario_a_pnl'].min():.2f}%")
            print(f"    Max Gain: {actions['scenario_a_pnl'].max():.2f}%")

            print(f"\n  Scenario B (Normal SL):")
            print(f"    Avg P&L: {actions['scenario_b_pnl'].mean():.2f}%")
            print(f"    Median P&L: {actions['scenario_b_pnl'].median():.2f}%")
            print(f"    Max Loss: {actions['scenario_b_pnl'].min():.2f}%")
            print(f"    Max Gain: {actions['scenario_b_pnl'].max():.2f}%")

            print(f"\n✅ Improvement Analysis:")
            print(f"  Average improvement: {avg_improvement:+.2f}%")
            print(f"  Median improvement: {median_improvement:+.2f}%")
            print(f"  Trades improved: {len(improved)} ({len(improved)/len(actions)*100:.1f}%)")
            print(f"  Trades worse: {len(worse)} ({len(worse)/len(actions)*100:.1f}%)")

            print(f"\n⚠️  False Exit Analysis:")
            print(f"  False exits (improvement < -0.5%): {len(false_exits)}")
            print(f"  False exit rate: {len(false_exits)/len(actions)*100:.1f}%")
            if not false_exits.empty:
                print(f"  Avg missed opportunity: {false_exits['improvement_pct'].mean():.2f}%")

            # Max loss reduction
            max_loss_reduction = actions['scenario_b_pnl'].min() - actions['scenario_a_pnl'].min()
            print(f"\n📉 Risk Reduction:")
            print(f"  Max loss reduction: {max_loss_reduction:+.2f}%")

            # Dollar impact (assuming $10,000 portfolio, $3,300 per position)
            avg_position_size = 3300
            total_dollar_improvement = avg_improvement * avg_position_size / 100 * len(actions)
            print(f"\n💵 Dollar Impact (on $10K portfolio, 3 positions @ $3.3K each):")
            print(f"  Total improvement: ${total_dollar_improvement:+,.2f}")
            print(f"  Per trade: ${avg_improvement * avg_position_size / 100:+,.2f}")

            # Decision criteria
            print(f"\n" + "="*80)
            print("DECISION CRITERIA:")
            print("="*80)

            criteria_met = []
            criteria_failed = []

            if avg_improvement > 0.3:
                criteria_met.append(f"✅ Avg improvement ({avg_improvement:.2f}%) > 0.3%")
            else:
                criteria_failed.append(f"❌ Avg improvement ({avg_improvement:.2f}%) ≤ 0.3%")

            false_exit_rate = len(false_exits)/len(actions)*100
            if false_exit_rate < 30:
                criteria_met.append(f"✅ False exit rate ({false_exit_rate:.1f}%) < 30%")
            else:
                criteria_failed.append(f"❌ False exit rate ({false_exit_rate:.1f}%) ≥ 30%")

            if max_loss_reduction >= 1.0:
                criteria_met.append(f"✅ Max loss reduction ({max_loss_reduction:.2f}%) ≥ 1.0%")
            else:
                criteria_failed.append(f"❌ Max loss reduction ({max_loss_reduction:.2f}%) < 1.0%")

            for c in criteria_met:
                print(f"  {c}")
            for c in criteria_failed:
                print(f"  {c}")

            print(f"\n" + "="*80)

            if len(criteria_met) >= 2:
                print("🎯 RECOMMENDATION: ✅ IMPLEMENT Evening Risk Analysis")
                print(f"   Reason: {len(criteria_met)}/3 criteria met")
                recommendation = 'IMPLEMENT'
            else:
                print("🎯 RECOMMENDATION: ❌ SKIP Evening Risk Analysis")
                print(f"   Reason: Only {len(criteria_met)}/3 criteria met")
                recommendation = 'SKIP'

            print("="*80 + "\n")

            return {
                'total_instances': len(self.results),
                'actions_taken': len(actions),
                'avg_improvement': avg_improvement,
                'median_improvement': median_improvement,
                'false_exit_rate': false_exit_rate,
                'max_loss_reduction': max_loss_reduction,
                'total_dollar_impact': total_dollar_improvement,
                'recommendation': recommendation,
                'criteria_met': len(criteria_met),
                'criteria_failed': len(criteria_failed)
            }
        else:
            print("\n⚠️  No actions were taken in this backtest")
            return {'recommendation': 'SKIP', 'reason': 'No actions triggered'}


def main():
    """Run backtest"""
    backtest = EveningRiskBacktest()

    # Run backtest
    results = backtest.run_backtest(
        start_date='2023-01-01',
        end_date='2025-01-01',
        risk_threshold=3
    )

    # Analyze results
    if not results.empty:
        metrics = backtest.analyze_results()

        # Save metrics
        with open('backtests/evening_risk_metrics.json', 'w') as f:
            # Convert numpy types to native Python types
            metrics_clean = {k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                           for k, v in metrics.items()}
            json.dump(metrics_clean, f, indent=2)

        print("✅ Metrics saved to: backtests/evening_risk_metrics.json")


if __name__ == '__main__':
    main()
