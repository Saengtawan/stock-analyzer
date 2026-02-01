#!/usr/bin/env python3
"""
Comprehensive Backtest: 6 months + Multiple Thresholds
Test signal effectiveness across different market conditions
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

import yfinance as yf
from datetime import datetime, timedelta
from collections import defaultdict

# Stocks with known signals (from our screening)
STOCK_UNIVERSE = [
    # 3/6 signals
    {'symbol': 'AVGO', 'signals': 3, 'has_insider': True, 'has_analyst': True},
    {'symbol': 'RIVN', 'signals': 3, 'has_insider': True, 'has_analyst': True},

    # 2/6 signals
    {'symbol': 'GOOGL', 'signals': 2, 'has_insider': True, 'has_analyst': True},
    {'symbol': 'SNOW', 'signals': 2, 'has_insider': True, 'has_analyst': True},
    {'symbol': 'AMD', 'signals': 2, 'has_insider': True, 'has_analyst': True},
    {'symbol': 'CRWD', 'signals': 2, 'has_insider': True, 'has_analyst': True},
    {'symbol': 'LCID', 'signals': 2, 'has_insider': True, 'has_analyst': False},
    {'symbol': 'GM', 'signals': 2, 'has_insider': True, 'has_analyst': True},
    {'symbol': 'NFLX', 'signals': 2, 'has_insider': True, 'has_analyst': True},
    {'symbol': 'UBER', 'signals': 2, 'has_insider': True, 'has_analyst': True},
    {'symbol': 'JPM', 'signals': 2, 'has_insider': True, 'has_analyst': True},

    # 1/6 signals
    {'symbol': 'NET', 'signals': 1, 'has_insider': True, 'has_analyst': False},
    {'symbol': 'DOCS', 'signals': 1, 'has_insider': True, 'has_analyst': False},
    {'symbol': 'GS', 'signals': 1, 'has_insider': True, 'has_analyst': False},
    {'symbol': 'SOFI', 'signals': 1, 'has_insider': True, 'has_analyst': False},

    # 0/6 signals (control)
    {'symbol': 'META', 'signals': 0, 'has_insider': False, 'has_analyst': False},
]


def get_performance(symbol: str, entry_date: datetime, exit_date: datetime) -> float:
    """Get price performance between two dates"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=entry_date, end=exit_date)

        if hist.empty or len(hist) < 2:
            return None

        entry_price = hist.iloc[0]['Close']
        exit_price = hist.iloc[-1]['Close']

        return ((exit_price - entry_price) / entry_price) * 100

    except:
        return None


def run_period_test(period_name: str, entry_date: datetime, holding_days: int = 30):
    """Test all stocks for a specific time period"""

    exit_date = entry_date + timedelta(days=holding_days)

    results = []

    print(f"\n{'='*80}")
    print(f"📅 Period: {period_name} ({entry_date.date()} → {exit_date.date()})")
    print('='*80)

    for stock in STOCK_UNIVERSE:
        symbol = stock['symbol']
        perf = get_performance(symbol, entry_date, exit_date)

        if perf is not None:
            result = {
                **stock,
                'performance': perf,
                'win': perf >= 5.0,
                'period': period_name
            }
            results.append(result)

    # Quick summary
    wins = sum(1 for r in results if r['win'])
    win_rate = wins / len(results) * 100 if results else 0
    avg_ret = sum(r['performance'] for r in results) / len(results) if results else 0

    print(f"  Stocks Tested: {len(results)}")
    print(f"  Win Rate: {win_rate:.1f}%")
    print(f"  Avg Return: {avg_ret:+.2f}%")

    return results


def analyze_by_threshold(all_results: list):
    """Analyze results with different signal thresholds"""

    print("\n" + "="*80)
    print("🎯 ANALYSIS BY SIGNAL THRESHOLD")
    print("="*80)

    thresholds = [0, 1, 2, 3]  # ≥0, ≥1, ≥2, ≥3 signals

    print(f"\n{'Threshold':<15} {'Stocks':<10} {'Trades':<10} {'Win Rate':<12} {'Avg Return':<12}")
    print("-" * 80)

    threshold_results = {}

    for threshold in thresholds:
        # Filter results by threshold
        filtered = [r for r in all_results if r['signals'] >= threshold]

        if not filtered:
            continue

        wins = sum(1 for r in filtered if r['win'])
        win_rate = wins / len(filtered) * 100
        avg_return = sum(r['performance'] for r in filtered) / len(filtered)

        # Count unique stocks
        unique_stocks = len(set(r['symbol'] for r in filtered))

        threshold_results[threshold] = {
            'stocks': unique_stocks,
            'trades': len(filtered),
            'win_rate': win_rate,
            'avg_return': avg_return
        }

        print(f"≥{threshold} signals{'':<6} {unique_stocks:<10} {len(filtered):<10} "
              f"{win_rate:>6.1f}%{'':<6} {avg_return:>+6.2f}%")

    return threshold_results


def analyze_by_period(all_results: list):
    """Analyze results by time period"""

    print("\n" + "="*80)
    print("📊 PERFORMANCE BY TIME PERIOD")
    print("="*80)

    by_period = defaultdict(list)
    for result in all_results:
        by_period[result['period']].append(result)

    print(f"\n{'Period':<20} {'Trades':<10} {'Win Rate':<12} {'Avg Return':<12}")
    print("-" * 80)

    for period in sorted(by_period.keys()):
        results = by_period[period]
        wins = sum(1 for r in results if r['win'])
        win_rate = wins / len(results) * 100
        avg_return = sum(r['performance'] for r in results) / len(results)

        print(f"{period:<20} {len(results):<10} {win_rate:>6.1f}%{'':<6} {avg_return:>+6.2f}%")


def analyze_by_signal_count(all_results: list):
    """Analyze results by exact signal count"""

    print("\n" + "="*80)
    print("📈 PERFORMANCE BY SIGNAL COUNT (Exact)")
    print("="*80)

    by_signals = defaultdict(list)
    for result in all_results:
        by_signals[result['signals']].append(result)

    print(f"\n{'Signals':<10} {'Trades':<10} {'Win Rate':<12} {'Avg Return':<12} {'Best/Worst':<20}")
    print("-" * 80)

    for sig_count in sorted(by_signals.keys(), reverse=True):
        results = by_signals[sig_count]
        wins = sum(1 for r in results if r['win'])
        win_rate = wins / len(results) * 100
        avg_return = sum(r['performance'] for r in results) / len(results)

        best = max(results, key=lambda x: x['performance'])
        worst = min(results, key=lambda x: x['performance'])

        best_worst = f"{best['symbol']}({best['performance']:+.1f}%) / {worst['symbol']}({worst['performance']:+.1f}%)"

        print(f"{sig_count}/6{'':<6} {len(results):<10} {win_rate:>6.1f}%{'':<6} "
              f"{avg_return:>+6.2f}%{'':<6} {best_worst}")


def final_recommendation(threshold_results: dict, all_results: list):
    """Provide final recommendation"""

    print("\n" + "="*80)
    print("💡 FINAL RECOMMENDATION")
    print("="*80)

    # Overall stats
    total_trades = len(all_results)
    overall_wins = sum(1 for r in all_results if r['win'])
    overall_wr = overall_wins / total_trades * 100
    overall_ret = sum(r['performance'] for r in all_results) / total_trades

    print(f"\n📊 Overall Performance (All Stocks):")
    print(f"  Total Trades: {total_trades}")
    print(f"  Win Rate: {overall_wr:.1f}%")
    print(f"  Avg Return: {overall_ret:+.2f}%")

    # Find best threshold
    best_threshold = None
    best_wr = 0

    for threshold, stats in threshold_results.items():
        if stats['win_rate'] > best_wr:
            best_wr = stats['win_rate']
            best_threshold = threshold

    if best_threshold is not None:
        stats = threshold_results[best_threshold]
        print(f"\n🎯 Best Threshold: ≥{best_threshold} signals")
        print(f"  Win Rate: {stats['win_rate']:.1f}%")
        print(f"  Avg Return: {stats['avg_return']:+.2f}%")
        print(f"  Total Trades: {stats['trades']}")

        target = 55.0
        if stats['win_rate'] >= target:
            print(f"\n✅ SUCCESS! Meets target of {target}%")
        else:
            gap = target - stats['win_rate']
            print(f"\n⚠️  Below target by {gap:.1f}%")

            # Check if any threshold meets target
            meets_target = [t for t, s in threshold_results.items() if s['win_rate'] >= target]
            if meets_target:
                best_meeting = max(meets_target, key=lambda t: threshold_results[t]['win_rate'])
                print(f"💡 Try threshold ≥{best_meeting}: {threshold_results[best_meeting]['win_rate']:.1f}% win rate")

    # Signal correlation check
    print(f"\n📊 Signal Correlation:")
    signal_counts = sorted(set(r['signals'] for r in all_results), reverse=True)
    if len(signal_counts) >= 2:
        high_sig = max(signal_counts)
        low_sig = min(signal_counts)

        high_results = [r for r in all_results if r['signals'] == high_sig]
        low_results = [r for r in all_results if r['signals'] == low_sig]

        high_wr = sum(1 for r in high_results if r['win']) / len(high_results) * 100
        low_wr = sum(1 for r in low_results if r['win']) / len(low_results) * 100

        if high_wr > low_wr + 10:
            print(f"  ✅ Strong correlation: {high_sig}/6 ({high_wr:.1f}%) >> {low_sig}/6 ({low_wr:.1f}%)")
        elif high_wr > low_wr:
            print(f"  ⚠️  Weak correlation: {high_sig}/6 ({high_wr:.1f}%) > {low_sig}/6 ({low_wr:.1f}%)")
        else:
            print(f"  ❌ No correlation: {high_sig}/6 ({high_wr:.1f}%) ≤ {low_sig}/6 ({low_wr:.1f}%)")


def main():
    print("\n" + "="*80)
    print("🔬 COMPREHENSIVE BACKTEST: 6 Months + Multiple Thresholds")
    print("="*80)
    print(f"\nUniverse: {len(STOCK_UNIVERSE)} stocks")
    print("Holding Period: 30 days")
    print("Target: 5% gain")

    # Define test periods (6 different 30-day periods)
    base_date = datetime.now()

    test_periods = [
        ("Dec 2025", base_date - timedelta(days=30)),
        ("Nov 2025", base_date - timedelta(days=60)),
        ("Oct 2025", base_date - timedelta(days=90)),
        ("Sep 2025", base_date - timedelta(days=120)),
        ("Aug 2025", base_date - timedelta(days=150)),
        ("Jul 2025", base_date - timedelta(days=180)),
    ]

    # Run tests for all periods
    all_results = []

    for period_name, entry_date in test_periods:
        period_results = run_period_test(period_name, entry_date, holding_days=30)
        all_results.extend(period_results)

    # Analyses
    print("\n" + "="*80)
    print("📊 COMPREHENSIVE ANALYSIS")
    print("="*80)

    threshold_results = analyze_by_threshold(all_results)
    analyze_by_period(all_results)
    analyze_by_signal_count(all_results)
    final_recommendation(threshold_results, all_results)

    print("\n" + "="*80)
    print("✅ Backtest Complete!")
    print("="*80)


if __name__ == "__main__":
    main()
