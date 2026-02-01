#!/usr/bin/env python3
"""
Quick Validation: Test if alt data signals correlate with performance
Use stocks we already screened + their actual 30-day performance
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

import yfinance as yf
from datetime import datetime, timedelta

def test_signal_effectiveness():
    """
    Test stocks we already know have signals
    Measure their actual 30-day performance
    """

    # Stocks from our screener with known signals
    test_stocks = [
        # 3/6 signals
        {'symbol': 'AVGO', 'signals': 3, 'has_insider': True, 'has_analyst': True, 'score': 62.4},
        {'symbol': 'RIVN', 'signals': 3, 'has_insider': True, 'has_analyst': True, 'score': 59.5},

        # 2/6 signals
        {'symbol': 'GOOGL', 'signals': 2, 'has_insider': True, 'has_analyst': True, 'score': 57.6},
        {'symbol': 'SNOW', 'signals': 2, 'has_insider': True, 'has_analyst': True, 'score': 55.9},
        {'symbol': 'AMD', 'signals': 2, 'has_insider': True, 'has_analyst': True, 'score': 53.3},
        {'symbol': 'CRWD', 'signals': 2, 'has_insider': True, 'has_analyst': True, 'score': 60.6},
        {'symbol': 'LCID', 'signals': 2, 'has_insider': True, 'has_analyst': False, 'score': 70.8},
        {'symbol': 'GM', 'signals': 2, 'has_insider': True, 'has_analyst': True, 'score': 56.8},
        {'symbol': 'NFLX', 'signals': 2, 'has_insider': True, 'has_analyst': True, 'score': 59.3},
        {'symbol': 'UBER', 'signals': 2, 'has_insider': True, 'has_analyst': True, 'score': 60.2},
        {'symbol': 'JPM', 'signals': 2, 'has_insider': True, 'has_analyst': True, 'score': 46.1},

        # 1/6 signals
        {'symbol': 'NET', 'signals': 1, 'has_insider': True, 'has_analyst': False, 'score': 45.2},
        {'symbol': 'DOCS', 'signals': 1, 'has_insider': True, 'has_analyst': False, 'score': 49.3},
        {'symbol': 'GS', 'signals': 1, 'has_insider': True, 'has_analyst': False, 'score': 36.2},
        {'symbol': 'SOFI', 'signals': 1, 'has_insider': True, 'has_analyst': False, 'score': 45.8},

        # 0/6 signals (control group)
        {'symbol': 'META', 'signals': 0, 'has_insider': False, 'has_analyst': False, 'score': 43.1},
    ]

    print("\n" + "="*80)
    print("🔬 QUICK VALIDATION: Alt Data Signal Effectiveness")
    print("Testing 30-day performance from 30 days ago")
    print("="*80)

    # Test period: 30 days ago → today
    entry_date = datetime.now() - timedelta(days=30)
    exit_date = datetime.now()

    print(f"\nEntry Date: {entry_date.date()}")
    print(f"Exit Date: {exit_date.date()}")
    print(f"Target: 5% gain")

    results = []

    print(f"\n{'Symbol':<8} {'Signals':<10} {'Alt Score':<12} {'Performance':<15} {'Win?':<6}")
    print("-" * 80)

    for stock in test_stocks:
        symbol = stock['symbol']
        performance = get_performance(symbol, entry_date, exit_date)

        if performance is not None:
            win = performance >= 5.0
            result = {
                **stock,
                'performance': performance,
                'win': win
            }
            results.append(result)

            signals_str = f"{stock['signals']}/6"
            signals_icons = []
            if stock['has_insider']: signals_icons.append('👔')
            if stock['has_analyst']: signals_icons.append('📊')

            print(f"{symbol:<8} {signals_str:<5} {' '.join(signals_icons):<5} "
                  f"{stock['score']:>6.1f}/100  "
                  f"{performance:>+6.2f}%{'':<7} "
                  f"{'✅' if win else '❌'}")

    # Analyze results
    analyze_results(results)


def get_performance(symbol: str, entry_date: datetime, exit_date: datetime) -> float:
    """Get actual performance between two dates"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=entry_date, end=exit_date)

        if hist.empty or len(hist) < 2:
            return None

        # Use first and last available prices
        entry_price = hist.iloc[0]['Close']
        exit_price = hist.iloc[-1]['Close']

        return ((exit_price - entry_price) / entry_price) * 100

    except Exception as e:
        return None


def analyze_results(results):
    """Analyze if signals correlate with performance"""

    print("\n" + "="*80)
    print("📊 ANALYSIS")
    print("="*80)

    # Overall stats
    total = len(results)
    wins = sum(1 for r in results if r['win'])
    win_rate = wins / total * 100 if total > 0 else 0
    avg_return = sum(r['performance'] for r in results) / total if total > 0 else 0

    print(f"\n🎯 Overall Performance:")
    print(f"  Total Stocks: {total}")
    print(f"  Wins (≥5%): {wins} ({win_rate:.1f}%)")
    print(f"  Average Return: {avg_return:+.2f}%")

    # By signal count
    print(f"\n📊 Performance by Signal Count:")
    print(f"{'Signals':<10} {'Count':<8} {'Win Rate':<12} {'Avg Return':<12}")
    print("-" * 60)

    by_signals = {}
    for result in results:
        sig = result['signals']
        if sig not in by_signals:
            by_signals[sig] = []
        by_signals[sig].append(result)

    for sig_count in sorted(by_signals.keys(), reverse=True):
        stocks = by_signals[sig_count]
        sig_wins = sum(1 for s in stocks if s['win'])
        sig_wr = sig_wins / len(stocks) * 100
        sig_ret = sum(s['performance'] for s in stocks) / len(stocks)

        print(f"{sig_count}/6{'':<6} {len(stocks):<8} {sig_wr:>6.1f}%{'':<6} {sig_ret:>+6.2f}%")

    # By specific signals
    print(f"\n📈 Performance by Specific Signals:")

    # Insider
    with_insider = [r for r in results if r['has_insider']]
    without_insider = [r for r in results if not r['has_insider']]

    if with_insider:
        insider_wr = sum(1 for r in with_insider if r['win']) / len(with_insider) * 100
        insider_ret = sum(r['performance'] for r in with_insider) / len(with_insider)
        print(f"\n  👔 With Insider ({len(with_insider)} stocks):")
        print(f"     Win Rate: {insider_wr:.1f}%")
        print(f"     Avg Return: {insider_ret:+.2f}%")

    if without_insider:
        no_insider_wr = sum(1 for r in without_insider if r['win']) / len(without_insider) * 100
        no_insider_ret = sum(r['performance'] for r in without_insider) / len(without_insider)
        print(f"\n  ❌ Without Insider ({len(without_insider)} stocks):")
        print(f"     Win Rate: {no_insider_wr:.1f}%")
        print(f"     Avg Return: {no_insider_ret:+.2f}%")

    # Analyst
    with_analyst = [r for r in results if r['has_analyst']]
    without_analyst = [r for r in results if not r['has_analyst']]

    if with_analyst:
        analyst_wr = sum(1 for r in with_analyst if r['win']) / len(with_analyst) * 100
        analyst_ret = sum(r['performance'] for r in with_analyst) / len(with_analyst)
        print(f"\n  📊 With Analyst ({len(with_analyst)} stocks):")
        print(f"     Win Rate: {analyst_wr:.1f}%")
        print(f"     Avg Return: {analyst_ret:+.2f}%")

    if without_analyst:
        no_analyst_wr = sum(1 for r in without_analyst if r['win']) / len(without_analyst) * 100
        no_analyst_ret = sum(r['performance'] for r in without_analyst) / len(without_analyst)
        print(f"\n  ❌ Without Analyst ({len(without_analyst)} stocks):")
        print(f"     Win Rate: {no_analyst_wr:.1f}%")
        print(f"     Avg Return: {no_analyst_ret:+.2f}%")

    # Conclusion
    print(f"\n" + "="*80)
    print("💡 CONCLUSION:")
    print("="*80)

    target_wr = 55.0
    if win_rate >= target_wr:
        print(f"✅ SUCCESS! Win rate {win_rate:.1f}% meets target {target_wr}%")
    else:
        print(f"⚠️  Win rate {win_rate:.1f}% below target {target_wr}%")
        print(f"   Gap: {target_wr - win_rate:.1f}%")

    # Check correlation
    if len(by_signals) > 1:
        max_sig = max(by_signals.keys())
        min_sig = min(by_signals.keys())

        max_wr = sum(1 for s in by_signals[max_sig] if s['win']) / len(by_signals[max_sig]) * 100
        min_wr = sum(1 for s in by_signals[min_sig] if s['win']) / len(by_signals[min_sig]) * 100

        if max_wr > min_wr:
            print(f"✅ More signals = Better performance ({max_sig}/6: {max_wr:.1f}% vs {min_sig}/6: {min_wr:.1f}%)")
        else:
            print(f"❌ Signals don't correlate with performance")

    # Signal effectiveness
    if with_insider and without_insider:
        if insider_wr > no_insider_wr + 5:
            print(f"✅ Insider signal is EFFECTIVE (+{insider_wr - no_insider_wr:.1f}% win rate)")
        else:
            print(f"⚠️  Insider signal weak effect ({insider_wr - no_insider_wr:+.1f}% difference)")

    if with_analyst and without_analyst:
        if analyst_wr > no_analyst_wr + 5:
            print(f"✅ Analyst signal is EFFECTIVE (+{analyst_wr - no_analyst_wr:.1f}% win rate)")
        else:
            print(f"⚠️  Analyst signal weak effect ({analyst_wr - no_analyst_wr:+.1f}% difference)")


if __name__ == "__main__":
    test_signal_effectiveness()
