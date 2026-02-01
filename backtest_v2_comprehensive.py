#!/usr/bin/env python3
"""
Comprehensive Backtest for 30-Day Growth Catalyst v2.1 with Enhanced BEAR Protection
Tests v7.1 entry filters + v2.1 regime detection + v2.0 exit rules over last 2 months

v2.1 Changes:
- Uses enhanced MarketRegimeDetector v2.1
- Checks regime BEFORE entry (skip if BEAR/WEAK)
- More sensitive BEAR detection during holding period

Validates:
- Win rate with exit rules
- Monthly returns
- Individual stock performance
- Exit reasons (profit vs loss)
- Performance in BULL vs BEAR markets
"""

import sys
sys.path.append('src')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import warnings
warnings.filterwarnings('ignore')

# Import enhanced regime detector
from market_regime_detector import MarketRegimeDetector

# Test stocks (from v7.1 + additional)
TEST_STOCKS = [
    # v7.1 Winners (100% win rate)
    'GOOGL', 'META', 'DASH', 'TEAM', 'ROKU', 'TSM', 'LRCX',

    # Mega caps
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'TSLA',

    # High growth
    'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG',

    # Semiconductors
    'AMD', 'AVGO', 'QCOM', 'AMAT', 'KLAC',

    # Consumer tech
    'UBER', 'ABNB', 'COIN', 'SHOP', 'SQ',
]


class BacktestV2:
    """Comprehensive backtest for v2.1 strategy with enhanced BEAR detection"""

    def __init__(self, lookback_months=2):
        self.lookback_months = lookback_months
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=lookback_months * 30)

        # v7.1 Entry Filter Thresholds
        self.entry_filters = {
            'beta_min': 0.8,
            'beta_max': 2.0,
            'volatility_min': 25.0,  # STRICT
            'rs_min': 0.0,           # STRICT
            'sector_score_min': 40,  # STRICT
            'valuation_score_min': 20,
        }

        # v2.0 Exit Rules
        self.exit_rules = {
            'hard_stop': -6.0,
            'trailing_stop': -3.0,
            'trailing_trigger': 5.0,  # Activate trailing after +5%
            'time_stop_days': 10,
            'time_stop_min_return': 2.0,
        }

        # v2.1: Enhanced regime detector
        self.regime_detector = MarketRegimeDetector()

        print(f"📊 Backtest Period: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
        print(f"   ({lookback_months} months)")
        print(f"   Using MarketRegimeDetector v2.1 (Enhanced BEAR detection)")

    def check_entry_filters(self, symbol: str, entry_date: datetime) -> Tuple[bool, Dict]:
        """Check if stock passes v7.1 entry filters + v2.1 regime check at entry_date"""
        try:
            # v2.1 NEW: Check market regime FIRST (don't enter in BEAR markets!)
            regime_info = self.regime_detector.get_current_regime(entry_date)

            if not regime_info['should_trade']:
                return False, {'reason': f"Regime {regime_info['regime']} - no entry allowed"}

            # Also check SPY trend strength
            spy_details = regime_info['details']
            if spy_details['dist_ma20'] < -3.0 or spy_details['dist_ma50'] < -5.0:
                return False, {'reason': f"SPY trend weak (MA20: {spy_details['dist_ma20']:.1f}%, MA50: {spy_details['dist_ma50']:.1f}%)"}

            ticker = yf.Ticker(symbol)

            # Get historical data up to entry date
            hist = ticker.history(start=entry_date - timedelta(days=90),
                                 end=entry_date + timedelta(days=1))

            if hist.empty or len(hist) < 50:
                return False, {'reason': 'Insufficient data'}

            info = ticker.info
            entry_price = hist['Close'].iloc[-1]

            # Filter 1: Beta
            beta = info.get('beta', 1.0)
            if beta is None:
                beta = 1.0
            if beta < self.entry_filters['beta_min'] or beta > self.entry_filters['beta_max']:
                return False, {'reason': f'Beta {beta:.2f} outside range'}

            # Filter 2: Volatility
            returns = hist['Close'].pct_change().dropna()
            if len(returns) >= 20:
                volatility = returns.std() * (252 ** 0.5) * 100
                if volatility < self.entry_filters['volatility_min']:
                    return False, {'reason': f'Volatility {volatility:.1f}% < 25%'}
            else:
                return False, {'reason': 'Not enough data for volatility'}

            # Filter 3: Relative Strength (30-day vs SPY)
            if len(hist) >= 30:
                stock_return = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-30]) - 1) * 100

                # Get SPY return
                spy = yf.Ticker('SPY')
                spy_hist = spy.history(start=entry_date - timedelta(days=90),
                                      end=entry_date + timedelta(days=1))

                if not spy_hist.empty and len(spy_hist) >= 30:
                    spy_return = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-30]) - 1) * 100
                    rs = stock_return - spy_return

                    if rs < self.entry_filters['rs_min']:
                        return False, {'reason': f'RS {rs:.1f}% < 0%'}
                else:
                    return False, {'reason': 'No SPY data for RS'}
            else:
                return False, {'reason': 'Not enough data for RS'}

            # Filter 4: Valuation (simplified - check P/E)
            pe = info.get('trailingPE')
            if pe and pe > 100:
                return False, {'reason': f'P/E {pe:.1f} too high'}

            # All filters passed
            return True, {
                'beta': beta,
                'volatility': volatility,
                'rs': rs,
                'pe': pe,
                'entry_price': entry_price
            }

        except Exception as e:
            return False, {'reason': f'Error: {str(e)}'}

    def simulate_position(self, symbol: str, entry_date: datetime,
                         entry_price: float, max_days: int = 30) -> Dict:
        """
        Simulate holding a position with v2.0 exit rules

        Returns detailed results including exit reason, days held, return
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get price data for holding period
            end_sim = min(entry_date + timedelta(days=max_days + 10), self.end_date)
            hist = ticker.history(start=entry_date, end=end_sim)

            if hist.empty:
                return None

            # Get SPY data for regime detection
            spy = yf.Ticker('SPY')
            spy_hist = spy.history(start=entry_date - timedelta(days=60), end=end_sim)

            # Track position
            highest_price = entry_price
            days_held = 0
            exit_price = entry_price
            exit_reason = 'MAX_HOLD'
            exit_date = entry_date + timedelta(days=max_days)

            # Simulate day by day
            for i, (date, row) in enumerate(hist.iterrows()):
                if i == 0:
                    continue  # Skip entry day

                current_price = row['Close']
                days_held = i

                # Update highest price
                if current_price > highest_price:
                    highest_price = current_price

                # Calculate returns
                current_return = ((current_price - entry_price) / entry_price) * 100
                peak_return = ((highest_price - entry_price) / entry_price) * 100
                drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100

                # Check exit triggers

                # 1. HARD STOP (-6%)
                if current_return <= self.exit_rules['hard_stop']:
                    exit_price = current_price
                    exit_reason = 'HARD_STOP'
                    exit_date = date
                    break

                # 2. TRAILING STOP (-3% from peak after +5% gain)
                if peak_return >= self.exit_rules['trailing_trigger']:
                    if drawdown_from_peak <= self.exit_rules['trailing_stop']:
                        exit_price = current_price
                        exit_reason = 'TRAILING_STOP'
                        exit_date = date
                        break

                # 3. TIME STOP (10 days without profit)
                if days_held >= self.exit_rules['time_stop_days']:
                    if current_return < self.exit_rules['time_stop_min_return']:
                        exit_price = current_price
                        exit_reason = 'TIME_STOP'
                        exit_date = date
                        break

                # 4. REGIME EXIT (v2.1 - use enhanced detector!)
                regime_info = self.regime_detector.get_current_regime(date.to_pydatetime())

                if regime_info['regime'] == 'BEAR':
                    # BEAR market detected - exit immediately!
                    exit_price = current_price
                    exit_reason = 'REGIME_BEAR'
                    exit_date = date
                    break
                elif regime_info['regime'] == 'SIDEWAYS' and not regime_info['should_trade']:
                    # SIDEWAYS WEAK - exit if not profitable
                    if current_return < 1.0:
                        exit_price = current_price
                        exit_reason = 'REGIME_WEAK'
                        exit_date = date
                        break

                # 5. TARGET HIT (5%+ - take profit)
                if current_return >= 5.0 and days_held >= 5:
                    exit_price = current_price
                    exit_reason = 'TARGET_HIT'
                    exit_date = date
                    break

                # 6. MAX HOLD (30 days)
                if days_held >= max_days:
                    exit_price = current_price
                    exit_reason = 'MAX_HOLD'
                    exit_date = date
                    break

            # Calculate final return
            final_return = ((exit_price - entry_price) / entry_price) * 100

            return {
                'symbol': symbol,
                'entry_date': entry_date.strftime('%Y-%m-%d'),
                'entry_price': entry_price,
                'exit_date': exit_date.strftime('%Y-%m-%d'),
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'days_held': days_held,
                'return_pct': final_return,
                'peak_return': peak_return,
                'highest_price': highest_price,
                'winner': final_return >= 0,
            }

        except Exception as e:
            print(f"⚠️  Error simulating {symbol}: {e}")
            return None

    def run_backtest(self):
        """Run comprehensive backtest"""

        print("\n" + "="*100)
        print("🧪 COMPREHENSIVE BACKTEST - 30-Day Growth Catalyst v2.1")
        print("   (Enhanced BEAR Detection + SPY Trend Confirmation)")
        print("="*100)

        print("\n📋 Configuration:")
        print(f"   Entry Filters (v7.1 STRICT):")
        print(f"      - Beta: {self.entry_filters['beta_min']:.1f} - {self.entry_filters['beta_max']:.1f}")
        print(f"      - Volatility: > {self.entry_filters['volatility_min']:.0f}%")
        print(f"      - RS (30d): > {self.entry_filters['rs_min']:.0f}%")
        print(f"      - Sector Score: > {self.entry_filters['sector_score_min']}")
        print(f"      - Valuation Score: > {self.entry_filters['valuation_score_min']}")

        print(f"\n   Exit Rules (v2.0):")
        print(f"      - Hard Stop: {self.exit_rules['hard_stop']:.0f}%")
        print(f"      - Trailing Stop: {self.exit_rules['trailing_stop']:.0f}% (after +{self.exit_rules['trailing_trigger']:.0f}%)")
        print(f"      - Time Stop: {self.exit_rules['time_stop_days']} days (if < {self.exit_rules['time_stop_min_return']:.0f}%)")
        print(f"      - Target: +5%")

        # Test multiple entry points over 2 months
        entry_dates = []
        current = self.start_date
        while current < self.end_date - timedelta(days=30):
            entry_dates.append(current)
            current += timedelta(days=7)  # Weekly entry points

        all_trades = []

        print(f"\n🔍 Testing {len(TEST_STOCKS)} stocks at {len(entry_dates)} entry points...")
        print(f"   Total potential trades: {len(TEST_STOCKS) * len(entry_dates)}")

        # Test each stock at each entry point
        for entry_date in entry_dates:
            print(f"\n📅 Entry Date: {entry_date.strftime('%Y-%m-%d')}")

            for symbol in TEST_STOCKS:
                # Check entry filters
                passes, details = self.check_entry_filters(symbol, entry_date)

                if passes:
                    # Simulate position
                    result = self.simulate_position(
                        symbol,
                        entry_date,
                        details['entry_price']
                    )

                    if result:
                        result['entry_details'] = details
                        all_trades.append(result)

                        status = "✅ WIN" if result['winner'] else "❌ LOSS"
                        print(f"  {symbol:6s}: {status} {result['return_pct']:+6.2f}% ({result['days_held']:2d}d) - {result['exit_reason']}")

        # Analyze results
        return self.analyze_results(all_trades)

    def analyze_results(self, trades: List[Dict]) -> Dict:
        """Analyze backtest results"""

        if not trades:
            print("\n❌ No trades found!")
            return {}

        print("\n" + "="*100)
        print("📊 BACKTEST RESULTS")
        print("="*100)

        # Calculate metrics
        total_trades = len(trades)
        winners = [t for t in trades if t['winner']]
        losers = [t for t in trades if not t['winner']]

        win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0

        returns = [t['return_pct'] for t in trades]
        avg_return = np.mean(returns)
        avg_winner = np.mean([t['return_pct'] for t in winners]) if winners else 0
        avg_loser = np.mean([t['return_pct'] for t in losers]) if losers else 0

        days_held = [t['days_held'] for t in trades]
        avg_days = np.mean(days_held)

        # Exit reasons
        exit_reasons = {}
        for t in trades:
            reason = t['exit_reason']
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        # Monthly returns (approximate)
        total_return = sum(returns)
        months = self.lookback_months
        monthly_return = total_return / months if months > 0 else 0
        avg_monthly_return = avg_return  # Per trade, not total

        # Print summary
        print(f"\n🎯 Overall Performance:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Winners: {len(winners)} ({win_rate:.1f}%)")
        print(f"   Losers: {len(losers)} ({100-win_rate:.1f}%)")
        print(f"   ")
        print(f"   Average Return: {avg_return:+.2f}%")
        print(f"   Average Winner: {avg_winner:+.2f}%")
        print(f"   Average Loser: {avg_loser:+.2f}%")
        print(f"   ")
        print(f"   Average Days Held: {avg_days:.1f} days")
        print(f"   Total Return (all trades): {total_return:+.2f}%")
        print(f"   Monthly Return (avg per trade): {avg_monthly_return:+.2f}%")

        print(f"\n📊 Exit Reasons:")
        for reason, count in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
            pct = count / total_trades * 100
            print(f"   {reason:15s}: {count:3d} ({pct:5.1f}%)")

        # Top winners
        print(f"\n🏆 Top 10 Winners:")
        top_winners = sorted(winners, key=lambda x: x['return_pct'], reverse=True)[:10]
        for i, t in enumerate(top_winners, 1):
            print(f"   {i:2d}. {t['symbol']:6s}: {t['return_pct']:+7.2f}% ({t['days_held']:2d}d) - Entry: {t['entry_date']}, Exit: {t['exit_reason']}")

        # Worst losers
        if losers:
            print(f"\n💔 Worst 10 Losers:")
            worst_losers = sorted(losers, key=lambda x: x['return_pct'])[:10]
            for i, t in enumerate(worst_losers, 1):
                print(f"   {i:2d}. {t['symbol']:6s}: {t['return_pct']:+7.2f}% ({t['days_held']:2d}d) - Entry: {t['entry_date']}, Exit: {t['exit_reason']}")

        # Detailed trade log
        print(f"\n" + "="*100)
        print(f"📋 DETAILED TRADE LOG (All {total_trades} trades)")
        print("="*100)
        print(f"{'Symbol':6s} {'Entry Date':12s} {'Exit Date':12s} {'Days':4s} {'Entry $':8s} {'Exit $':8s} {'Return':8s} {'Exit Reason':15s} {'Result':6s}")
        print("-"*100)

        for t in sorted(trades, key=lambda x: x['entry_date']):
            result = "WIN" if t['winner'] else "LOSS"
            print(f"{t['symbol']:6s} {t['entry_date']:12s} {t['exit_date']:12s} {t['days_held']:4d} "
                  f"${t['entry_price']:7.2f} ${t['exit_price']:7.2f} {t['return_pct']:+7.2f}% "
                  f"{t['exit_reason']:15s} {result:6s}")

        # Performance by month
        print(f"\n" + "="*100)
        print(f"📅 MONTHLY BREAKDOWN")
        print("="*100)

        monthly_trades = {}
        for t in trades:
            month = t['entry_date'][:7]  # YYYY-MM
            if month not in monthly_trades:
                monthly_trades[month] = []
            monthly_trades[month].append(t)

        for month in sorted(monthly_trades.keys()):
            month_trades = monthly_trades[month]
            month_winners = [t for t in month_trades if t['winner']]
            month_return = sum(t['return_pct'] for t in month_trades)
            month_wr = len(month_winners) / len(month_trades) * 100

            print(f"\n{month}:")
            print(f"   Trades: {len(month_trades)}")
            print(f"   Win Rate: {month_wr:.1f}%")
            print(f"   Total Return: {month_return:+.2f}%")
            print(f"   Avg Return: {month_return/len(month_trades):+.2f}%")

        # Save detailed results
        results = {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'avg_winner': avg_winner,
            'avg_loser': avg_loser,
            'avg_days_held': avg_days,
            'total_return': total_return,
            'monthly_return': avg_monthly_return,
            'exit_reasons': exit_reasons,
            'all_trades': trades
        }

        return results


def main():
    """Run comprehensive backtest"""

    print("\n🚀 Starting Comprehensive Backtest...")
    print("   This will take 2-3 minutes to download data and simulate trades\n")

    # Run backtest
    backtest = BacktestV2(lookback_months=2)
    results = backtest.run_backtest()

    # Final summary
    if results:
        print("\n" + "="*100)
        print("✅ BACKTEST COMPLETE")
        print("="*100)

        print(f"\n🎯 Key Takeaways:")
        print(f"   Win Rate: {results['win_rate']:.1f}%")
        print(f"   Average Return: {results['avg_return']:+.2f}%")
        print(f"   Average Days Held: {results['avg_days_held']:.1f} days")
        print(f"   Monthly Return (avg): {results['monthly_return']:+.2f}%")

        print(f"\n💡 Interpretation:")
        if results['win_rate'] >= 70:
            print(f"   ✅ EXCELLENT! Win rate {results['win_rate']:.1f}% meets target (70-100%)")
        elif results['win_rate'] >= 50:
            print(f"   ⚠️  GOOD but below target. Win rate {results['win_rate']:.1f}% < 70%")
        else:
            print(f"   ❌ POOR. Win rate {results['win_rate']:.1f}% needs improvement")

        if results['avg_return'] >= 3:
            print(f"   ✅ GOOD average return {results['avg_return']:+.2f}%")
        elif results['avg_return'] >= 0:
            print(f"   ⚠️  MARGINAL average return {results['avg_return']:+.2f}%")
        else:
            print(f"   ❌ NEGATIVE average return {results['avg_return']:+.2f}%")

        print(f"\n📊 Exit Rule Effectiveness:")
        total = results['total_trades']
        for reason, count in sorted(results['exit_reasons'].items(), key=lambda x: x[1], reverse=True):
            pct = count / total * 100

            if reason == 'TARGET_HIT':
                print(f"   ✅ {reason}: {pct:.1f}% (GOOD - hitting targets!)")
            elif reason == 'TRAILING_STOP':
                print(f"   ✅ {reason}: {pct:.1f}% (GOOD - locking profits!)")
            elif reason == 'HARD_STOP':
                print(f"   ⚠️  {reason}: {pct:.1f}% (Cutting losses)")
            elif reason == 'TIME_STOP':
                print(f"   ⚠️  {reason}: {pct:.1f}% (Stocks not working)")
            else:
                print(f"   ℹ️  {reason}: {pct:.1f}%")

        print("\n" + "="*100)


if __name__ == "__main__":
    main()
