#!/usr/bin/env python3
"""
Backtest v7.1 - Match Original Methodology
Hold full 30 days, no early exit, BULL market only

This matches the original v7.1 backtest:
- Entry: v7.1 filters (Beta, Vol, RS, Sector, Valuation)
- Hold: Full 30 days (no early exit)
- Period: BULL market only (skip BEAR periods)
- Goal: Validate 10%+ monthly returns
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

# Test stocks (comprehensive list)
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


class BacktestV71HoldFull:
    """Backtest matching v7.1 methodology - hold full 30 days, BULL only"""

    def __init__(self, lookback_months=2):
        self.lookback_months = lookback_months
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=lookback_months * 30)

        # v7.1 Entry Filters (STRICT)
        self.entry_filters = {
            'beta_min': 0.8,
            'beta_max': 2.0,
            'volatility_min': 25.0,
            'rs_min': 0.0,
            'sector_score_min': 40,
            'valuation_score_min': 20,
        }

        # Regime detector
        self.regime_detector = MarketRegimeDetector()

        print(f"📊 Backtest Period: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
        print(f"   Methodology: HOLD FULL 30 DAYS, BULL MARKET ONLY")
        print(f"   Matching v7.1 original backtest methodology")

    def check_entry_filters(self, symbol: str, entry_date: datetime) -> Tuple[bool, Dict]:
        """Check v7.1 entry filters + regime must be BULL"""
        try:
            # Check regime FIRST - must be BULL
            regime_info = self.regime_detector.get_current_regime(entry_date)

            if regime_info['regime'] != 'BULL':
                return False, {'reason': f"Not BULL market (regime: {regime_info['regime']})"}

            # Also check SPY trend
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

            # Filter 3: Relative Strength (30-day)
            if len(hist) >= 30:
                # Get SPY data
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

            # Filter 4: Valuation (simplified - just check P/E)
            pe = info.get('trailingPE', 0)
            if pe > 100:
                return False, {'reason': f'P/E {pe:.1f} too high'}

            # All filters passed
            return True, {
                'beta': beta,
                'volatility': volatility,
                'rs': rs,
                'pe': pe,
                'entry_price': entry_price,
                'regime': regime_info['regime'],
            }

        except Exception as e:
            return False, {'reason': f'Error: {str(e)}'}

    def hold_full_30_days(self, symbol: str, entry_date: datetime,
                          entry_price: float) -> Dict:
        """
        Hold for FULL 30 days - match v7.1 methodology
        No early exits, measure max return achieved
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get 30-day price data
            end_date = entry_date + timedelta(days=40)  # Extra buffer
            hist = ticker.history(start=entry_date, end=min(end_date, self.end_date))

            if hist.empty or len(hist) < 2:
                return None

            # Track max return over 30 days
            max_return = 0
            max_price = entry_price
            day_of_max = 0

            exit_price = entry_price
            exit_date = entry_date  # Initialize
            days_held = 0

            for i, (date, row) in enumerate(hist.iterrows()):
                if i == 0:
                    continue  # Skip entry day

                current_price = row['Close']
                current_return = ((current_price - entry_price) / entry_price) * 100

                # Always update exit price/date (in case we don't hit break)
                exit_price = current_price
                days_held = i
                date_naive = date.to_pydatetime().replace(tzinfo=None) if hasattr(date, 'to_pydatetime') else date
                exit_date = date_naive

                # Track max return
                if current_return > max_return:
                    max_return = current_return
                    max_price = current_price
                    day_of_max = i

                # Exit at 30 days OR max available data
                if i >= 30 or date_naive >= self.end_date:
                    break

            final_return = ((exit_price - entry_price) / entry_price) * 100

            # Determine if hit 5% target
            hit_target = max_return >= 5.0

            # Format exit_date properly
            exit_date_str = exit_date.strftime('%Y-%m-%d') if hasattr(exit_date, 'strftime') else str(exit_date)

            return {
                'symbol': symbol,
                'entry_date': entry_date.strftime('%Y-%m-%d'),
                'entry_price': entry_price,
                'exit_date': exit_date_str,
                'exit_price': exit_price,
                'days_held': days_held,
                'final_return': final_return,
                'max_return': max_return,
                'max_price': max_price,
                'day_of_max': day_of_max,
                'hit_target': hit_target,
            }

        except Exception as e:
            print(f"⚠️  Error simulating {symbol}: {e}")
            return None

    def run_backtest(self):
        """Run backtest - BULL market entry dates only, hold full 30 days"""

        print("\n" + "="*100)
        print("🧪 BACKTEST v7.1 METHODOLOGY - HOLD FULL 30 DAYS, BULL MARKET ONLY")
        print("="*100)

        print("\n📋 Configuration:")
        print(f"   Entry Filters (v7.1):")
        print(f"      - Beta: {self.entry_filters['beta_min']:.1f} - {self.entry_filters['beta_max']:.1f}")
        print(f"      - Volatility: > {self.entry_filters['volatility_min']:.0f}%")
        print(f"      - RS (30d): > {self.entry_filters['rs_min']:.0f}%")
        print(f"      - Regime: BULL only")

        print(f"\n   Holding Period:")
        print(f"      - Hold: FULL 30 DAYS (no early exit)")
        print(f"      - Measure: MAX return achieved in 30 days")
        print(f"      - Target: 5%+ (same as v7.1)")

        # Test entry points - weekly
        entry_dates = []
        current = self.start_date
        while current < self.end_date - timedelta(days=30):
            entry_dates.append(current)
            current += timedelta(days=7)

        all_trades = []

        print(f"\n🔍 Testing {len(TEST_STOCKS)} stocks at {len(entry_dates)} entry points...")

        # Test each entry date
        for entry_date in entry_dates:
            # Check if BULL market
            regime = self.regime_detector.get_current_regime(entry_date)

            if regime['regime'] != 'BULL':
                print(f"\n📅 Entry Date: {entry_date.strftime('%Y-%m-%d')} - SKIPPED ({regime['regime']} market)")
                continue

            print(f"\n📅 Entry Date: {entry_date.strftime('%Y-%m-%d')} - BULL MARKET ✅")

            for symbol in TEST_STOCKS:
                # Check entry filters
                passes, details = self.check_entry_filters(symbol, entry_date)

                if passes:
                    # Hold for full 30 days
                    result = self.hold_full_30_days(
                        symbol,
                        entry_date,
                        details['entry_price']
                    )

                    if result:
                        result['entry_details'] = details
                        all_trades.append(result)

                        status = "✅ HIT" if result['hit_target'] else "❌ MISS"
                        print(f"  {symbol:6s}: {status} Max: {result['max_return']:+6.2f}% "
                              f"(day {result['day_of_max']}), Final: {result['final_return']:+6.2f}% ({result['days_held']}d)")

        # Analyze results
        return self.analyze_results(all_trades)

    def analyze_results(self, trades: List[Dict]) -> Dict:
        """Analyze results matching v7.1 format"""

        if not trades:
            print("\n❌ No trades found!")
            return {}

        print("\n" + "="*100)
        print("📊 BACKTEST RESULTS - v7.1 METHODOLOGY")
        print("="*100)

        # Calculate metrics
        total_trades = len(trades)
        hit_target = [t for t in trades if t['hit_target']]
        missed_target = [t for t in trades if not t['hit_target']]

        win_rate = len(hit_target) / total_trades * 100 if total_trades > 0 else 0

        max_returns = [t['max_return'] for t in trades]
        final_returns = [t['final_return'] for t in trades]

        avg_max_return = np.mean(max_returns)
        avg_final_return = np.mean(final_returns)

        avg_days_to_max = np.mean([t['day_of_max'] for t in trades])

        # Print summary
        print(f"\n🎯 Overall Performance:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Hit 5% Target: {len(hit_target)} ({win_rate:.1f}%)")
        print(f"   Missed Target: {len(missed_target)} ({100-win_rate:.1f}%)")
        print(f"   ")
        print(f"   Average MAX Return: {avg_max_return:+.2f}%")
        print(f"   Average FINAL Return (30d): {avg_final_return:+.2f}%")
        print(f"   Average Days to Max: {avg_days_to_max:.1f} days")

        # Top performers
        print(f"\n🏆 Top 10 Performers (by MAX return):")
        sorted_trades = sorted(trades, key=lambda x: x['max_return'], reverse=True)
        for i, t in enumerate(sorted_trades[:10], 1):
            print(f"   {i:2d}. {t['symbol']:6s}: Max {t['max_return']:+6.2f}% (day {t['day_of_max']:2d}), "
                  f"Final {t['final_return']:+6.2f}% - Entry: {t['entry_date']}")

        # Worst performers
        print(f"\n💔 Bottom 10 Performers:")
        for i, t in enumerate(sorted_trades[-10:], 1):
            print(f"   {i:2d}. {t['symbol']:6s}: Max {t['max_return']:+6.2f}% (day {t['day_of_max']:2d}), "
                  f"Final {t['final_return']:+6.2f}% - Entry: {t['entry_date']}")

        # Monthly breakdown
        print(f"\n📅 MONTHLY BREAKDOWN:")
        monthly_stats = {}
        for t in trades:
            month = t['entry_date'][:7]  # YYYY-MM
            if month not in monthly_stats:
                monthly_stats[month] = []
            monthly_stats[month].append(t)

        for month in sorted(monthly_stats.keys()):
            month_trades = monthly_stats[month]
            month_hit = sum(1 for t in month_trades if t['hit_target'])
            month_win_rate = month_hit / len(month_trades) * 100
            month_avg_max = np.mean([t['max_return'] for t in month_trades])
            month_avg_final = np.mean([t['final_return'] for t in month_trades])

            print(f"\n{month}:")
            print(f"   Trades: {len(month_trades)}")
            print(f"   Win Rate: {month_win_rate:.1f}%")
            print(f"   Avg MAX Return: {month_avg_max:+.2f}%")
            print(f"   Avg FINAL Return: {month_avg_final:+.2f}%")

        print("\n" + "="*100)
        print("✅ BACKTEST COMPLETE")
        print("="*100)

        print(f"\n🎯 Key Takeaways:")
        print(f"   Win Rate: {win_rate:.1f}%")
        print(f"   Average MAX Return: {avg_max_return:+.2f}%")
        print(f"   Average FINAL Return: {avg_final_return:+.2f}%")

        if avg_max_return >= 10.0:
            print(f"\n💡 Interpretation:")
            print(f"   ✅ EXCELLENT! Avg max return {avg_max_return:.1f}% matches v7.1 target (10%+)")
        elif avg_max_return >= 5.0:
            print(f"\n💡 Interpretation:")
            print(f"   ✅ GOOD. Avg max return {avg_max_return:.1f}% above 5% target")
        else:
            print(f"\n💡 Interpretation:")
            print(f"   ⚠️ BELOW TARGET. Avg max return {avg_max_return:.1f}% below 5%")

        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_max_return': avg_max_return,
            'avg_final_return': avg_final_return,
            'all_trades': trades
        }


def main():
    print("🚀 Starting v7.1 Methodology Backtest...")
    print("   Hold full 30 days, BULL market only")
    print("   This will take 2-3 minutes...\n")

    backtest = BacktestV71HoldFull(lookback_months=2)
    results = backtest.run_backtest()


if __name__ == "__main__":
    main()
