#!/usr/bin/env python3
"""
Scientific Backtest: Validate Alt Data Signals
Test if Insider Buying + Analyst Upgrades actually improve win rate
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from ai_stock_analyzer import AIStockAnalyzer

logging.basicConfig(level=logging.WARNING)

class AltDataBacktest:
    """Backtest to validate alternative data signal effectiveness"""

    def __init__(self):
        self.analyzer = AIStockAnalyzer()
        self.screener = GrowthCatalystScreener(self.analyzer)

    def run_backtest(self, test_dates: list, holding_period_days: int = 30):
        """
        Run backtest across multiple dates

        Args:
            test_dates: List of dates to run screener
            holding_period_days: How long to hold stocks
        """

        all_trades = []

        for test_date in test_dates:
            print(f"\n{'='*80}")
            print(f"📅 Testing: {test_date}")
            print('='*80)

            # Run screener (use current data as proxy for historical)
            # In production, would need historical alt data
            stocks = self._run_screener_simple(test_date)

            if not stocks:
                print("  No stocks found")
                continue

            # Track trades
            for stock in stocks:
                symbol = stock['symbol']
                entry_date = test_date
                exit_date = entry_date + timedelta(days=holding_period_days)

                # Get actual price performance
                performance = self._get_performance(symbol, entry_date, exit_date)

                if performance is not None:
                    trade = {
                        'symbol': symbol,
                        'entry_date': entry_date,
                        'exit_date': exit_date,
                        'performance': performance,
                        'alt_data_score': stock.get('alt_data_score', 0),
                        'signals': stock.get('alt_data_signals', 0),
                        'has_insider': stock.get('has_insider_buying', False),
                        'has_analyst': stock.get('has_analyst_upgrade', False),
                        'composite_score': stock.get('composite_score', 0),
                        'win': performance >= 5.0  # 5% target
                    }
                    all_trades.append(trade)

                    signal_str = f"{trade['signals']}/6"
                    signals = []
                    if trade['has_insider']: signals.append('👔')
                    if trade['has_analyst']: signals.append('📊')

                    print(f"  {symbol:<6} {signal_str} {' '.join(signals):<8} "
                          f"Score:{trade['composite_score']:>5.1f} → "
                          f"{performance:+6.2f}% {'✅' if trade['win'] else '❌'}")

        return all_trades

    def _run_screener_simple(self, test_date):
        """Run screener for a specific date (simplified)"""
        try:
            # Use a small universe of liquid stocks
            universe = [
                # Tech
                'AAPL', 'MSFT', 'GOOGL', 'META', 'NVDA', 'AMD', 'INTC', 'AVGO',
                # Cloud/Software
                'SNOW', 'CRWD', 'DDOG', 'NET', 'PLTR', 'DOCS', 'ZS',
                # Finance
                'JPM', 'BAC', 'GS', 'SOFI', 'COIN',
                # EV/Auto
                'TSLA', 'RIVN', 'LCID', 'F', 'GM',
                # Other
                'NFLX', 'DIS', 'UBER', 'ABNB', 'SHOP'
            ]

            results = []
            for symbol in universe:
                try:
                    stock = self.screener._analyze_stock_comprehensive(
                        symbol=symbol,
                        target_gain_pct=5.0,
                        timeframe_days=30
                    )

                    if stock and stock.get('composite_score', 0) > 30:
                        results.append(stock)

                except Exception as e:
                    continue

            # Sort by composite score
            results.sort(key=lambda x: x.get('composite_score', 0), reverse=True)

            return results[:20]  # Top 20

        except Exception as e:
            print(f"  Error running screener: {e}")
            return []

    def _get_performance(self, symbol: str, entry_date: datetime, exit_date: datetime) -> float:
        """Get actual price performance between two dates"""
        try:
            # Add buffer for market hours
            start = entry_date - timedelta(days=5)
            end = exit_date + timedelta(days=5)

            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start, end=end)

            if hist.empty:
                return None

            # Find closest dates
            entry_price = None
            exit_price = None

            # Get entry price (first available price on or after entry_date)
            for idx in hist.index:
                if idx.date() >= entry_date.date():
                    entry_price = hist.loc[idx, 'Close']
                    break

            # Get exit price (first available price on or after exit_date)
            for idx in hist.index:
                if idx.date() >= exit_date.date():
                    exit_price = hist.loc[idx, 'Close']
                    break

            if entry_price and exit_price:
                return ((exit_price - entry_price) / entry_price) * 100

            return None

        except Exception as e:
            return None

    def analyze_results(self, trades: list):
        """Analyze backtest results by signal count"""

        if not trades:
            print("\n❌ No trades to analyze")
            return

        print("\n" + "="*80)
        print("📊 BACKTEST RESULTS ANALYSIS")
        print("="*80)

        # Overall stats
        total_trades = len(trades)
        wins = sum(1 for t in trades if t['win'])
        win_rate = wins / total_trades * 100
        avg_return = sum(t['performance'] for t in trades) / total_trades

        print(f"\n🎯 Overall Performance:")
        print(f"  Total Trades: {total_trades}")
        print(f"  Wins: {wins} ({win_rate:.1f}%)")
        print(f"  Average Return: {avg_return:+.2f}%")

        # Break down by signal count
        print(f"\n📊 Performance by Signal Count:")
        print(f"{'Signals':<10} {'Trades':<8} {'Win Rate':<12} {'Avg Return':<12}")
        print("-" * 60)

        by_signals = defaultdict(list)
        for trade in trades:
            by_signals[trade['signals']].append(trade)

        for signal_count in sorted(by_signals.keys(), reverse=True):
            signal_trades = by_signals[signal_count]
            s_wins = sum(1 for t in signal_trades if t['win'])
            s_win_rate = s_wins / len(signal_trades) * 100
            s_avg_return = sum(t['performance'] for t in signal_trades) / len(signal_trades)

            print(f"{signal_count}/6{'':<6} {len(signal_trades):<8} "
                  f"{s_win_rate:>6.1f}%{'':<6} {s_avg_return:>+6.2f}%")

        # Break down by specific signals
        print(f"\n📈 Performance by Specific Signals:")

        # Insider buying
        with_insider = [t for t in trades if t['has_insider']]
        without_insider = [t for t in trades if not t['has_insider']]

        if with_insider:
            insider_wr = sum(1 for t in with_insider if t['win']) / len(with_insider) * 100
            insider_ret = sum(t['performance'] for t in with_insider) / len(with_insider)
            print(f"\n  👔 With Insider Buying ({len(with_insider)} trades):")
            print(f"     Win Rate: {insider_wr:.1f}%")
            print(f"     Avg Return: {insider_ret:+.2f}%")

        if without_insider:
            no_insider_wr = sum(1 for t in without_insider if t['win']) / len(without_insider) * 100
            no_insider_ret = sum(t['performance'] for t in without_insider) / len(without_insider)
            print(f"\n  ❌ Without Insider Buying ({len(without_insider)} trades):")
            print(f"     Win Rate: {no_insider_wr:.1f}%")
            print(f"     Avg Return: {no_insider_ret:+.2f}%")

        # Analyst upgrades
        with_analyst = [t for t in trades if t['has_analyst']]
        without_analyst = [t for t in trades if not t['has_analyst']]

        if with_analyst:
            analyst_wr = sum(1 for t in with_analyst if t['win']) / len(with_analyst) * 100
            analyst_ret = sum(t['performance'] for t in with_analyst) / len(with_analyst)
            print(f"\n  📊 With Analyst Upgrade ({len(with_analyst)} trades):")
            print(f"     Win Rate: {analyst_wr:.1f}%")
            print(f"     Avg Return: {analyst_ret:+.2f}%")

        if without_analyst:
            no_analyst_wr = sum(1 for t in without_analyst if t['win']) / len(without_analyst) * 100
            no_analyst_ret = sum(t['performance'] for t in without_analyst) / len(without_analyst)
            print(f"\n  ❌ Without Analyst Upgrade ({len(without_analyst)} trades):")
            print(f"     Win Rate: {no_analyst_wr:.1f}%")
            print(f"     Avg Return: {no_analyst_ret:+.2f}%")

        # Both signals
        both_signals = [t for t in trades if t['has_insider'] and t['has_analyst']]
        if both_signals:
            both_wr = sum(1 for t in both_signals if t['win']) / len(both_signals) * 100
            both_ret = sum(t['performance'] for t in both_signals) / len(both_signals)
            print(f"\n  🌟 Both Signals ({len(both_signals)} trades):")
            print(f"     Win Rate: {both_wr:.1f}%")
            print(f"     Avg Return: {both_ret:+.2f}%")

        # Conclusion
        print(f"\n" + "="*80)
        print("💡 CONCLUSION:")
        print("="*80)

        target_win_rate = 55.0
        if win_rate >= target_win_rate:
            print(f"✅ SUCCESS! Win rate {win_rate:.1f}% exceeds target {target_win_rate}%")
        else:
            print(f"⚠️  Win rate {win_rate:.1f}% below target {target_win_rate}%")
            print(f"   Gap: {target_win_rate - win_rate:.1f}%")

        # Check if signals help
        if with_insider and without_insider:
            if insider_wr > no_insider_wr:
                print(f"✅ Insider signal HELPS (+{insider_wr - no_insider_wr:.1f}% win rate)")
            else:
                print(f"❌ Insider signal doesn't help ({insider_wr - no_insider_wr:.1f}% difference)")

        if with_analyst and without_analyst:
            if analyst_wr > no_analyst_wr:
                print(f"✅ Analyst signal HELPS (+{analyst_wr - no_analyst_wr:.1f}% win rate)")
            else:
                print(f"❌ Analyst signal doesn't help ({analyst_wr - no_analyst_wr:.1f}% difference)")


def main():
    print("\n" + "="*80)
    print("🔬 SCIENTIFIC VALIDATION: Alt Data Signals")
    print("Testing if Insider + Analyst signals improve win rate")
    print("="*80)

    # Create test dates (last 2 months, weekly)
    test_dates = []
    base_date = datetime.now() - timedelta(days=60)

    for i in range(8):  # 8 weeks
        test_date = base_date + timedelta(days=i*7)
        test_dates.append(test_date)

    print(f"\nTest Period: {test_dates[0].date()} to {test_dates[-1].date()}")
    print(f"Holding Period: 30 days")
    print(f"Target: 5% gain")

    # Run backtest
    backtest = AltDataBacktest()
    trades = backtest.run_backtest(test_dates, holding_period_days=30)

    # Analyze results
    backtest.analyze_results(trades)

    print("\n" + "="*80)
    print("✅ Backtest Complete!")
    print("="*80)


if __name__ == "__main__":
    main()
