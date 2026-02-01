#!/usr/bin/env python3
"""
Backtest v2.2 - SMART EXITS (ออกให้ถูกจังหวะ!)

Key Changes from v2.1:
1. ✅ Keep: BULL market entry only (regime filter)
2. ✅ Keep: Hard stop -6%
3. ✅ Keep: Trailing stop -3% from peak
4. ❌ REMOVE: Time stop 10 days (ออกเร็วเกิน!)
5. ✅ NEW: Take profit at +10% (พอใจแล้วออก)
6. ✅ NEW: Calculate monthly returns with reinvestment

Goal: Exit at the RIGHT PRICE to maximize monthly returns
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

from market_regime_detector import MarketRegimeDetector

# Test stocks
TEST_STOCKS = [
    # v7.1 Winners
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


class BacktestV22SmartExits:
    """Backtest with SMART exits - exit at the RIGHT price!"""

    def __init__(self, lookback_months=2):
        self.lookback_months = lookback_months
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=lookback_months * 30)

        # v7.1 Entry Filters
        self.entry_filters = {
            'beta_min': 0.8,
            'beta_max': 2.0,
            'volatility_min': 25.0,
            'rs_min': 0.0,
            'sector_score_min': 40,
            'valuation_score_min': 20,
        }

        # v2.2 SMART Exit Rules
        self.exit_rules = {
            'hard_stop': -6.0,              # Cut losses
            'trailing_stop': -3.0,          # Lock profits
            'trailing_trigger': 5.0,        # Activate after +5%
            'take_profit': 10.0,            # Exit at +10% (good enough!)
            # NO TIME STOP! Let winners run!
        }

        # Regime detector
        self.regime_detector = MarketRegimeDetector()

        print(f"📊 Backtest Period: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
        print(f"   Strategy: v2.2 SMART EXITS")
        print(f"   Exit at the RIGHT PRICE, not fixed time!")

    def check_entry_filters(self, symbol: str, entry_date: datetime) -> Tuple[bool, Dict]:
        """Check v7.1 filters + BULL regime"""
        try:
            # Check regime - must be BULL
            regime_info = self.regime_detector.get_current_regime(entry_date)

            if regime_info['regime'] != 'BULL':
                return False, {'reason': f"Not BULL (regime: {regime_info['regime']})"}

            # Check SPY trend
            spy_details = regime_info['details']
            if spy_details['dist_ma20'] < -3.0 or spy_details['dist_ma50'] < -5.0:
                return False, {'reason': f"SPY trend weak"}

            ticker = yf.Ticker(symbol)

            # Get historical data
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
                    return False, {'reason': f'Volatility {volatility:.1f}% too low'}
            else:
                return False, {'reason': 'Insufficient data for volatility'}

            # Filter 3: Relative Strength
            if len(hist) >= 30:
                spy = yf.Ticker('SPY')
                spy_hist = spy.history(start=entry_date - timedelta(days=90),
                                      end=entry_date + timedelta(days=1))

                if len(spy_hist) >= 30:
                    stock_ret = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-30]) - 1) * 100
                    spy_ret = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-30]) - 1) * 100
                    rs = stock_ret - spy_ret

                    if rs < self.entry_filters['rs_min']:
                        return False, {'reason': f'RS {rs:.1f}% below threshold'}
                else:
                    return False, {'reason': 'Insufficient SPY data'}
            else:
                return False, {'reason': 'Insufficient data for RS'}

            # Filter 4: Valuation
            pe = info.get('trailingPE', 0)
            if pe > 100:
                return False, {'reason': f'P/E {pe:.1f} too high'}

            # All passed
            return True, {
                'beta': beta,
                'volatility': volatility,
                'rs': rs,
                'pe': pe,
                'entry_price': entry_price,
            }

        except Exception as e:
            return False, {'reason': f'Error: {str(e)}'}

    def simulate_smart_exit(self, symbol: str, entry_date: datetime,
                           entry_price: float, max_days: int = 30) -> Dict:
        """
        Simulate with SMART exits - exit at the RIGHT price!

        Exit Rules:
        1. Hard stop: -6%
        2. Trailing stop: -3% from peak (after +5%)
        3. Take profit: +10%
        4. Max hold: 30 days (if no other exit)

        NO TIME STOP! Let winners run!
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get price data
            end_sim = min(entry_date + timedelta(days=max_days + 10), self.end_date)
            hist = ticker.history(start=entry_date, end=end_sim)

            if hist.empty or len(hist) < 2:
                return None

            # Track
            highest_price = entry_price
            peak_return = 0
            days_held = 0
            exit_price = entry_price
            exit_reason = 'MAX_HOLD'
            exit_date = entry_date

            # Simulate day by day
            for i, (date, row) in enumerate(hist.iterrows()):
                if i == 0:
                    continue  # Skip entry day

                current_price = row['Close']
                days_held = i

                # Convert date
                date_naive = date.to_pydatetime().replace(tzinfo=None) if hasattr(date, 'to_pydatetime') else date
                exit_date = date_naive
                exit_price = current_price

                # Calculate returns
                current_return = ((current_price - entry_price) / entry_price) * 100

                # Update peak
                if current_price > highest_price:
                    highest_price = current_price
                    peak_return = current_return

                drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100

                # Exit checks

                # 1. HARD STOP (-6%)
                if current_return <= self.exit_rules['hard_stop']:
                    exit_reason = 'HARD_STOP'
                    break

                # 2. TAKE PROFIT (+10%) - NEW!
                if current_return >= self.exit_rules['take_profit']:
                    exit_reason = 'TAKE_PROFIT'
                    break

                # 3. TRAILING STOP (-3% from peak after +5%)
                if peak_return >= self.exit_rules['trailing_trigger']:
                    if drawdown_from_peak <= self.exit_rules['trailing_stop']:
                        exit_reason = 'TRAILING_STOP'
                        break

                # 4. REGIME EXIT
                regime_info = self.regime_detector.get_current_regime(date_naive)
                if regime_info['regime'] == 'BEAR':
                    exit_reason = 'REGIME_BEAR'
                    break

                # 5. MAX HOLD (30 days)
                if i >= max_days or date_naive >= self.end_date:
                    exit_reason = 'MAX_HOLD'
                    break

            # Calculate final return
            final_return = ((exit_price - entry_price) / entry_price) * 100

            return {
                'symbol': symbol,
                'entry_date': entry_date.strftime('%Y-%m-%d'),
                'entry_price': entry_price,
                'exit_date': exit_date.strftime('%Y-%m-%d') if hasattr(exit_date, 'strftime') else str(exit_date),
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
        """Run backtest with smart exits"""

        print("\n" + "="*100)
        print("🧪 BACKTEST v2.2 - SMART EXITS (ออกให้ถูกจังหวะ!)")
        print("="*100)

        print("\n📋 Entry Filters (v7.1):")
        print(f"   - Beta: {self.entry_filters['beta_min']:.1f} - {self.entry_filters['beta_max']:.1f}")
        print(f"   - Volatility: > {self.entry_filters['volatility_min']:.0f}%")
        print(f"   - RS (30d): > {self.entry_filters['rs_min']:.0f}%")
        print(f"   - Regime: BULL only")

        print(f"\n📋 Exit Rules (v2.2 SMART):")
        print(f"   1. Hard Stop:     {self.exit_rules['hard_stop']:.0f}% (ป้องกันขาดทุน)")
        print(f"   2. Take Profit:   +{self.exit_rules['take_profit']:.0f}% (พอใจแล้วออก!)")
        print(f"   3. Trailing Stop: {self.exit_rules['trailing_stop']:.0f}% from peak (จับจุดสูงสุด!)")
        print(f"   4. Max Hold:      30 days (ถ้ายังไม่ถึงเงื่อนไขอื่น)")
        print(f"   ❌ NO Time Stop! ให้หุ้นขึ้นไปเรื่อยๆ!")

        # Test entry points
        entry_dates = []
        current = self.start_date
        while current < self.end_date - timedelta(days=30):
            entry_dates.append(current)
            current += timedelta(days=7)

        all_trades = []

        print(f"\n🔍 Testing {len(TEST_STOCKS)} stocks at {len(entry_dates)} entry points...")

        # Test each entry date
        for entry_date in entry_dates:
            # Check regime
            regime = self.regime_detector.get_current_regime(entry_date)

            if regime['regime'] != 'BULL':
                print(f"\n📅 {entry_date.strftime('%Y-%m-%d')} - SKIPPED ({regime['regime']})")
                continue

            print(f"\n📅 {entry_date.strftime('%Y-%m-%d')} - BULL ✅")

            for symbol in TEST_STOCKS:
                passes, details = self.check_entry_filters(symbol, entry_date)

                if passes:
                    result = self.simulate_smart_exit(
                        symbol,
                        entry_date,
                        details['entry_price']
                    )

                    if result:
                        result['entry_details'] = details
                        all_trades.append(result)

                        status = "✅ WIN" if result['winner'] else "❌ LOSS"
                        print(f"  {symbol:6s}: {status} {result['return_pct']:+6.2f}% "
                              f"({result['days_held']:2d}d) - {result['exit_reason']}")

        # Analyze results
        return self.analyze_results(all_trades)

    def analyze_results(self, trades: List[Dict]) -> Dict:
        """Analyze results with focus on monthly returns"""

        if not trades:
            print("\n❌ No trades found!")
            return {}

        print("\n" + "="*100)
        print("📊 BACKTEST RESULTS - v2.2 SMART EXITS")
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

        # Monthly returns
        total_return = sum(returns)

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
        print(f"   Total Return (sum): {total_return:+.2f}%")

        # Exit reasons
        print(f"\n📊 Exit Reasons:")
        for reason in sorted(exit_reasons.keys(), key=lambda x: exit_reasons[x], reverse=True):
            count = exit_reasons[reason]
            pct = count / total_trades * 100
            print(f"   {reason:15s}: {count:3d} ({pct:5.1f}%)")

        # Top/Worst performers
        print(f"\n🏆 Top 10 Winners:")
        sorted_trades = sorted(trades, key=lambda x: x['return_pct'], reverse=True)
        for i, t in enumerate(sorted_trades[:10], 1):
            print(f"   {i:2d}. {t['symbol']:6s}: {t['return_pct']:+6.2f}% ({t['days_held']:2d}d) "
                  f"- {t['exit_reason']} - Entry: {t['entry_date']}")

        print(f"\n💔 Worst 10 Losers:")
        for i, t in enumerate(sorted_trades[-10:], 1):
            print(f"   {i:2d}. {t['symbol']:6s}: {t['return_pct']:+6.2f}% ({t['days_held']:2d}d) "
                  f"- {t['exit_reason']} - Entry: {t['entry_date']}")

        # Monthly breakdown
        print(f"\n📅 MONTHLY BREAKDOWN:")
        monthly_stats = {}
        for t in trades:
            month = t['entry_date'][:7]
            if month not in monthly_stats:
                monthly_stats[month] = []
            monthly_stats[month].append(t)

        for month in sorted(monthly_stats.keys()):
            month_trades = monthly_stats[month]
            month_winners = sum(1 for t in month_trades if t['winner'])
            month_win_rate = month_winners / len(month_trades) * 100
            month_avg_return = np.mean([t['return_pct'] for t in month_trades])
            month_total_return = sum([t['return_pct'] for t in month_trades])
            month_avg_days = np.mean([t['days_held'] for t in month_trades])

            print(f"\n{month}:")
            print(f"   Trades: {len(month_trades)}")
            print(f"   Win Rate: {month_win_rate:.1f}%")
            print(f"   Avg Return: {month_avg_return:+.2f}%")
            print(f"   Total Return: {month_total_return:+.2f}%")
            print(f"   Avg Days Held: {month_avg_days:.1f} days")

        print("\n" + "="*100)
        print("✅ BACKTEST COMPLETE")
        print("="*100)

        print(f"\n🎯 Key Takeaways:")
        print(f"   Win Rate: {win_rate:.1f}%")
        print(f"   Avg Return per Trade: {avg_return:+.2f}%")
        print(f"   Avg Days Held: {avg_days:.1f} days")

        # Calculate potential monthly return with reinvestment
        trades_per_month = 30 / avg_days if avg_days > 0 else 0
        monthly_return_estimate = avg_return * trades_per_month

        print(f"\n💰 Monthly Return Estimate (with reinvestment):")
        print(f"   Avg holding: {avg_days:.1f} days")
        print(f"   Potential trades/month: {trades_per_month:.1f}")
        print(f"   Estimated monthly return: {monthly_return_estimate:+.2f}%")

        if monthly_return_estimate >= 10.0:
            print(f"\n💡 Interpretation:")
            print(f"   ✅ EXCELLENT! Estimated {monthly_return_estimate:.1f}%/month >= 10% target!")
        elif monthly_return_estimate >= 5.0:
            print(f"\n💡 Interpretation:")
            print(f"   ✅ GOOD! Estimated {monthly_return_estimate:.1f}%/month")
        else:
            print(f"\n💡 Interpretation:")
            print(f"   ⚠️ BELOW TARGET. Estimated {monthly_return_estimate:.1f}%/month < 5%")

        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'avg_days': avg_days,
            'monthly_return_estimate': monthly_return_estimate,
            'all_trades': trades
        }


def main():
    print("🚀 Starting v2.2 SMART EXITS Backtest...")
    print("   Exit at the RIGHT PRICE for maximum monthly returns!")
    print("   This will take 2-3 minutes...\n")

    backtest = BacktestV22SmartExits(lookback_months=2)
    results = backtest.run_backtest()


if __name__ == "__main__":
    main()
