#!/usr/bin/env python3
"""
Weekend Position Review Backtest (v6.26)

Test: Weekend Rescan vs Time Stop (10 days)
- ทุกสุดสัปดาห์: Rescan หุ้นทุกตัว (score, momentum, sector)
- ถ้าอ่อนแรง → ขายจันทร์
- VS ถือต่อตาม time stop (10 วัน)

Metrics:
- Avg P&L improvement
- Early exit benefit (rotation to better stocks)
- False rotation rate
- Total $ saved

Decision Criteria:
✅ IMPLEMENT if:
   - Avg P&L improvement > +0.5%
   - Early exit benefit > +1.0%
   - False rotation rate < 25%
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

class WeekendReviewBacktest:
    """Backtest Weekend Position Review feature"""

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
        """Get all positions from trade history"""
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

        df = df[df['exit_date'].notna()].copy()
        print(f"Found {len(df)} completed positions from database")

        # If no data, use synthetic test data
        if df.empty:
            print("No completed positions in date range. Using synthetic test data...")
            return self.create_test_data()

        return df

    def create_test_data(self) -> pd.DataFrame:
        """Create synthetic test data"""
        test_positions = [
            {'symbol': 'AAPL', 'entry_date': '2024-01-02', 'entry_price': 185, 'qty': 10,
             'exit_date': '2024-01-15', 'exit_price': 187, 'exit_reason': 'TIME_STOP'},
            {'symbol': 'MSFT', 'entry_date': '2024-02-05', 'entry_price': 400, 'qty': 10,
             'exit_date': '2024-02-16', 'exit_price': 398, 'exit_reason': 'TIME_STOP'},
            {'symbol': 'GOOGL', 'entry_date': '2024-03-01', 'entry_price': 140, 'qty': 10,
             'exit_date': '2024-03-14', 'exit_price': 141, 'exit_reason': 'TIME_STOP'},
        ]

        df = pd.DataFrame(test_positions)
        print(f"Using {len(df)} synthetic test positions")
        return df

    def calculate_stock_score(
        self,
        symbol: str,
        date: str,
        entry_price: float,
        price_data: pd.DataFrame
    ) -> Tuple[int, float, List[str]]:
        """
        Calculate stock score (simplified screener)

        Returns: (score, momentum_5d, reasons)
        """
        score = 50  # Base score
        reasons = []

        try:
            date_idx = price_data.index.get_loc(pd.Timestamp(date))

            # 1. Momentum (5-day return)
            if date_idx >= 5:
                price_5d_ago = price_data['Close'].iloc[date_idx - 5]
                current_price = price_data['Close'].iloc[date_idx]

                # Convert to scalar if Series
                if isinstance(price_5d_ago, pd.Series):
                    price_5d_ago = price_5d_ago.iloc[0]
                if isinstance(current_price, pd.Series):
                    current_price = current_price.iloc[0]

                momentum_5d = ((current_price - price_5d_ago) / price_5d_ago) * 100

                if momentum_5d > 5:
                    score += 20
                    reasons.append(f"Strong momentum +{momentum_5d:.1f}%")
                elif momentum_5d > 2:
                    score += 10
                    reasons.append(f"Positive momentum +{momentum_5d:.1f}%")
                elif momentum_5d < -3:
                    score -= 15
                    reasons.append(f"Weak momentum {momentum_5d:.1f}%")
            else:
                momentum_5d = 0

            # 2. Volume trend
            if date_idx >= 5:
                recent_volume = price_data['Volume'].iloc[date_idx-5:date_idx].mean()
                current_volume = price_data['Volume'].iloc[date_idx]

                # Convert to scalar if Series
                if isinstance(current_volume, pd.Series):
                    current_volume = current_volume.iloc[0]

                if current_volume > recent_volume * 1.5:
                    score += 10
                    reasons.append("Volume increasing")
                elif current_volume < recent_volume * 0.7:
                    score -= 5
                    reasons.append("Volume declining")

            # 3. Trend direction (SMA cross)
            if date_idx >= 10:
                sma_5 = price_data['Close'].iloc[date_idx-5:date_idx+1].mean()
                sma_10 = price_data['Close'].iloc[date_idx-10:date_idx+1].mean()

                if sma_5 > sma_10:
                    score += 15
                    reasons.append("Uptrend (SMA5 > SMA10)")
                else:
                    score -= 10
                    reasons.append("Downtrend (SMA5 < SMA10)")

            # 4. Relative to entry (how's the trade doing)
            current_price = price_data['Close'].iloc[date_idx]

            # Convert to scalar if Series
            if isinstance(current_price, pd.Series):
                current_price = current_price.iloc[0]

            pnl_pct = ((current_price - entry_price) / entry_price) * 100

            if pnl_pct > 3:
                score += 10
                reasons.append(f"Profitable +{pnl_pct:.1f}%")
            elif pnl_pct < -2:
                score -= 15
                reasons.append(f"Losing {pnl_pct:.1f}%")

            # 5. Volatility (ATR)
            if date_idx >= 14:
                high_low = price_data['High'].iloc[date_idx-14:date_idx+1] - price_data['Low'].iloc[date_idx-14:date_idx+1]
                atr = high_low.mean()

                # Get current_price for this calculation (reuse from above, but ensure it's scalar)
                current_price_for_atr = price_data['Close'].iloc[date_idx]
                if isinstance(current_price_for_atr, pd.Series):
                    current_price_for_atr = current_price_for_atr.iloc[0]

                atr_pct = (atr / current_price_for_atr) * 100

                if atr_pct > 5:
                    score -= 5
                    reasons.append(f"High volatility {atr_pct:.1f}%")

            return score, momentum_5d, reasons

        except Exception as e:
            print(f"Error scoring {symbol} on {date}: {e}")
            return 50, 0, ["Error calculating score"]

    def find_weekend_dates(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> List[pd.Timestamp]:
        """Find all Saturday/Sunday dates in range"""
        weekends = []
        current = start_date

        while current <= end_date:
            if current.weekday() in [5, 6]:  # Saturday=5, Sunday=6
                weekends.append(current)
            current += timedelta(days=1)

        return weekends

    def simulate_position(self, position: pd.Series) -> List[Dict]:
        """
        Simulate position with weekend reviews
        """
        symbol = position['symbol']
        entry_date = pd.Timestamp(position['entry_date'])
        exit_date = pd.Timestamp(position['exit_date'])
        entry_price = position['entry_price']
        exit_price = position['exit_price']

        # Get price data
        price_data = self.get_price_data(
            symbol,
            (entry_date - timedelta(days=20)).strftime('%Y-%m-%d'),
            (exit_date + timedelta(days=5)).strftime('%Y-%m-%d')
        )

        if price_data.empty:
            return []

        # Find weekends during holding period
        weekends = self.find_weekend_dates(entry_date, exit_date)

        weekend_reviews = []

        for weekend_date in weekends:
            # Find last Friday (or last trading day before weekend)
            friday_date = weekend_date - timedelta(days=1 if weekend_date.weekday() == 6 else 2)

            # Skip if friday not in data
            if friday_date not in price_data.index:
                continue

            # Calculate trading days held
            trading_days_held = len(pd.bdate_range(entry_date, friday_date))

            # Only review if held >= 3 trading days
            if trading_days_held < 3:
                continue

            # Calculate score
            score, momentum, reasons = self.calculate_stock_score(
                symbol, friday_date, entry_price, price_data
            )

            # Get Monday open price (for sell simulation)
            monday_date = weekend_date + timedelta(days=1 if weekend_date.weekday() == 6 else 2)
            monday_open = None

            for i in range(5):  # Look up to 5 days ahead for next trading day
                check_date = monday_date + timedelta(days=i)
                if check_date in price_data.index:
                    monday_open = price_data.loc[check_date, 'Open']
                    # Convert to scalar if Series
                    if isinstance(monday_open, pd.Series):
                        monday_open = monday_open.iloc[0]
                    monday_date = check_date
                    break

            if monday_open is None:
                continue

            # Get current P&L
            friday_close = price_data.loc[friday_date, 'Close']
            # Convert to scalar if Series
            if isinstance(friday_close, pd.Series):
                friday_close = friday_close.iloc[0]

            current_pnl = ((friday_close - entry_price) / entry_price) * 100

            weekend_reviews.append({
                'symbol': symbol,
                'entry_price': entry_price,
                'entry_date': entry_date,
                'weekend_date': weekend_date,
                'friday_close': friday_close,
                'monday_open': monday_open,
                'monday_date': monday_date,
                'trading_days_held': trading_days_held,
                'current_pnl': current_pnl,
                'score': score,
                'momentum_5d': momentum,
                'reasons': reasons,
                'actual_exit_price': exit_price,
                'actual_exit_date': exit_date
            })

        return weekend_reviews

    def run_backtest(
        self,
        start_date: str = '2023-01-01',
        end_date: str = '2025-01-01',
        score_threshold: int = 85,
        min_trading_days: int = 5
    ) -> pd.DataFrame:
        """Run full backtest"""

        print("\n" + "="*80)
        print("WEEKEND POSITION REVIEW BACKTEST")
        print("="*80)
        print(f"Period: {start_date} to {end_date}")
        print(f"Score Threshold: {score_threshold}")
        print(f"Min Trading Days: {min_trading_days}")
        print(f"Decision: Sell Monday if score < {score_threshold} AND days >= {min_trading_days}")
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

            weekend_reviews = self.simulate_position(position)

            for review in weekend_reviews:
                # Decision: Sell if score < threshold AND held >= min_trading_days AND pnl < 1%
                # Extract scalar values to ensure proper comparison
                score_val = review['score']
                days_held_val = review['trading_days_held']
                pnl_val = review['current_pnl']

                # Convert to scalar if needed
                if isinstance(score_val, pd.Series):
                    score_val = score_val.iloc[0]
                if isinstance(days_held_val, pd.Series):
                    days_held_val = days_held_val.iloc[0]
                if isinstance(pnl_val, pd.Series):
                    pnl_val = pnl_val.iloc[0]

                should_sell = (
                    score_val < score_threshold and
                    days_held_val >= min_trading_days and
                    pnl_val < 1.0
                )

                # Scenario A: Weekend Review sell
                if should_sell:
                    exit_price_a = review['monday_open']
                    exit_date_a = review['monday_date']
                    exit_reason_a = 'WEEKEND_REVIEW'
                else:
                    exit_price_a = None
                    exit_date_a = None
                    exit_reason_a = None

                # Scenario B: Time stop (10 days)
                exit_price_b = review['actual_exit_price']
                exit_date_b = review['actual_exit_date']

                # Calculate P&L
                if exit_price_a:
                    pnl_a = ((exit_price_a - review['entry_price']) / review['entry_price']) * 100
                else:
                    pnl_a = None

                pnl_b = ((exit_price_b - review['entry_price']) / review['entry_price']) * 100

                # Calculate improvement
                improvement = (pnl_a - pnl_b) if pnl_a is not None else 0

                result = {
                    'symbol': review['symbol'],
                    'entry_price': review['entry_price'],
                    'entry_date': review['entry_date'],
                    'weekend_date': review['weekend_date'],
                    'trading_days_held': review['trading_days_held'],
                    'friday_close': review['friday_close'],
                    'current_pnl': review['current_pnl'],
                    'score': review['score'],
                    'momentum_5d': review['momentum_5d'],
                    'reasons': ', '.join(review['reasons']),
                    # Scenario A (Weekend Review)
                    'scenario_a_exit_price': exit_price_a,
                    'scenario_a_exit_date': exit_date_a,
                    'scenario_a_pnl': pnl_a,
                    # Scenario B (Time Stop)
                    'scenario_b_exit_price': exit_price_b,
                    'scenario_b_exit_date': exit_date_b,
                    'scenario_b_pnl': pnl_b,
                    # Comparison
                    'improvement_pct': improvement,
                    'took_action': exit_price_a is not None
                }

                all_results.append(result)

                if exit_price_a:
                    print(f"  {review['weekend_date'].strftime('%Y-%m-%d')}: "
                          f"Score {review['score']} (Day {review['trading_days_held']}) "
                          f"→ Weekend Review sell @ ${exit_price_a:.2f} "
                          f"(vs Time Stop ${exit_price_b:.2f}) "
                          f"= {improvement:+.2f}%")

        self.results = pd.DataFrame(all_results)

        # Save results
        output_file = 'backtests/weekend_review_results.csv'
        self.results.to_csv(output_file, index=False)
        print(f"\n✅ Results saved to: {output_file}")

        return self.results

    def analyze_results(self) -> Dict:
        """Analyze backtest results"""

        if self.results.empty:
            print("\n❌ No results to analyze")
            return {}

        actions = self.results[self.results['took_action'] == True]

        print("\n" + "="*80)
        print("BACKTEST RESULTS - WEEKEND POSITION REVIEW")
        print("="*80)

        print(f"\n📊 Overall Statistics:")
        print(f"  Total weekend reviews: {len(self.results)}")
        print(f"  Weekend Review sells triggered: {len(actions)}")
        print(f"  Sell rate: {len(actions)/len(self.results)*100:.1f}%")

        if not actions.empty:
            avg_improvement = actions['improvement_pct'].mean()
            median_improvement = actions['improvement_pct'].median()

            improved = actions[actions['improvement_pct'] > 0]
            worse = actions[actions['improvement_pct'] < 0]
            false_rotations = actions[actions['improvement_pct'] < -0.5]

            print(f"\n💰 Performance Comparison:")
            print(f"  Scenario A (Weekend Review):")
            print(f"    Avg P&L: {actions['scenario_a_pnl'].mean():.2f}%")
            print(f"    Median P&L: {actions['scenario_a_pnl'].median():.2f}%")
            print(f"    Max Loss: {actions['scenario_a_pnl'].min():.2f}%")
            print(f"    Max Gain: {actions['scenario_a_pnl'].max():.2f}%")

            print(f"\n  Scenario B (Time Stop - 10 days):")
            print(f"    Avg P&L: {actions['scenario_b_pnl'].mean():.2f}%")
            print(f"    Median P&L: {actions['scenario_b_pnl'].median():.2f}%")
            print(f"    Max Loss: {actions['scenario_b_pnl'].min():.2f}%")
            print(f"    Max Gain: {actions['scenario_b_pnl'].max():.2f}%")

            print(f"\n✅ Improvement Analysis:")
            print(f"  Average improvement: {avg_improvement:+.2f}%")
            print(f"  Median improvement: {median_improvement:+.2f}%")
            print(f"  Trades improved: {len(improved)} ({len(improved)/len(actions)*100:.1f}%)")
            print(f"  Trades worse: {len(worse)} ({len(worse)/len(actions)*100:.1f}%)")

            print(f"\n⚠️  False Rotation Analysis:")
            print(f"  False rotations (improvement < -0.5%): {len(false_rotations)}")
            print(f"  False rotation rate: {len(false_rotations)/len(actions)*100:.1f}%")
            if not false_rotations.empty:
                print(f"  Avg missed opportunity: {false_rotations['improvement_pct'].mean():.2f}%")

            # Early exit benefit
            avg_days_saved = actions['trading_days_held'].mean()
            print(f"\n📅 Early Exit Benefit:")
            print(f"  Avg trading days before weekend review: {avg_days_saved:.1f}")
            print(f"  Days saved vs time stop (10 days): {10 - avg_days_saved:.1f}")

            # Dollar impact
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

            if avg_improvement > 0.5:
                criteria_met.append(f"✅ Avg P&L improvement ({avg_improvement:.2f}%) > 0.5%")
            else:
                criteria_failed.append(f"❌ Avg P&L improvement ({avg_improvement:.2f}%) ≤ 0.5%")

            early_exit_benefit = avg_improvement + (10 - avg_days_saved) * 0.1  # Approximate benefit
            if early_exit_benefit > 1.0:
                criteria_met.append(f"✅ Early exit benefit ({early_exit_benefit:.2f}%) > 1.0%")
            else:
                criteria_failed.append(f"❌ Early exit benefit ({early_exit_benefit:.2f}%) ≤ 1.0%")

            false_rotation_rate = len(false_rotations)/len(actions)*100
            if false_rotation_rate < 25:
                criteria_met.append(f"✅ False rotation rate ({false_rotation_rate:.1f}%) < 25%")
            else:
                criteria_failed.append(f"❌ False rotation rate ({false_rotation_rate:.1f}%) ≥ 25%")

            for c in criteria_met:
                print(f"  {c}")
            for c in criteria_failed:
                print(f"  {c}")

            print(f"\n" + "="*80)

            if len(criteria_met) >= 2:
                print("🎯 RECOMMENDATION: ✅ IMPLEMENT Weekend Position Review")
                print(f"   Reason: {len(criteria_met)}/3 criteria met")
                recommendation = 'IMPLEMENT'
            else:
                print("🎯 RECOMMENDATION: ❌ SKIP Weekend Position Review")
                print(f"   Reason: Only {len(criteria_met)}/3 criteria met")
                recommendation = 'SKIP'

            print("="*80 + "\n")

            return {
                'total_reviews': len(self.results),
                'actions_taken': len(actions),
                'avg_improvement': avg_improvement,
                'median_improvement': median_improvement,
                'false_rotation_rate': false_rotation_rate,
                'early_exit_benefit': early_exit_benefit,
                'avg_days_saved': 10 - avg_days_saved,
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
    backtest = WeekendReviewBacktest()

    # Run backtest
    results = backtest.run_backtest(
        start_date='2023-01-01',
        end_date='2025-01-01',
        score_threshold=85,
        min_trading_days=5
    )

    # Analyze results
    if not results.empty:
        metrics = backtest.analyze_results()

        # Save metrics
        with open('backtests/weekend_review_metrics.json', 'w') as f:
            metrics_clean = {k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                           for k, v in metrics.items()}
            json.dump(metrics_clean, f, indent=2)

        print("✅ Metrics saved to: backtests/weekend_review_metrics.json")


if __name__ == '__main__':
    main()
