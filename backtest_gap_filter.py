#!/usr/bin/env python3
"""
Backtest: Gap Filter (P5)

Hypothesis:
  H0: Gap filter helps avoid bad entries (gaps often reverse)
  H1: Gap filter blocks good momentum trades

Current Setting:
  Gap filter may skip stocks that gap up/down significantly at open

Test Cases:
  1. NO_FILTER: Allow all gaps
  2. SKIP_GAP_UP_3: Skip if gap up > 3%
  3. SKIP_GAP_UP_5: Skip if gap up > 5%
  4. SKIP_GAP_DOWN_3: Skip if gap down > 3%
  5. SKIP_ANY_GAP_3: Skip if |gap| > 3%
  6. SKIP_ANY_GAP_5: Skip if |gap| > 5%
  7. PREFER_GAP_DOWN: Prefer gap down entries (mean reversion)

Metrics:
  - Trade count
  - Win rate
  - Expectancy
  - Analysis by gap size buckets
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("yfinance not available")


# Gap filter configurations
GAP_FILTERS = {
    'NO_FILTER': {'gap_up_max': 999, 'gap_down_max': 999, 'desc': 'No gap filter'},
    'SKIP_GAP_UP_3': {'gap_up_max': 3, 'gap_down_max': 999, 'desc': 'Skip gap up > 3%'},
    'SKIP_GAP_UP_5': {'gap_up_max': 5, 'gap_down_max': 999, 'desc': 'Skip gap up > 5%'},
    'SKIP_GAP_DOWN_3': {'gap_up_max': 999, 'gap_down_max': 3, 'desc': 'Skip gap down > 3%'},
    'SKIP_ANY_GAP_3': {'gap_up_max': 3, 'gap_down_max': 3, 'desc': 'Skip any gap > 3%'},
    'SKIP_ANY_GAP_5': {'gap_up_max': 5, 'gap_down_max': 5, 'desc': 'Skip any gap > 5%'},
    'ONLY_GAP_DOWN': {'gap_up_max': 0, 'gap_down_max': 999, 'desc': 'Only trade gap downs'},
}


# Sample stocks (diverse sectors)
SAMPLE_STOCKS = [
    # Technology
    'AAPL', 'MSFT', 'NVDA', 'AMD', 'INTC', 'AVGO', 'QCOM', 'CRM', 'ADBE', 'NOW',
    # Healthcare
    'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD', 'REGN',
    # Financial
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'V',
    # Consumer
    'AMZN', 'TSLA', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'WMT', 'COST', 'LOW',
    # Energy
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX', 'DVN',
    # Industrial
    'CAT', 'DE', 'UNP', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'UPS', 'FDX',
    # Communication
    'GOOGL', 'META', 'NFLX', 'DIS', 'VZ', 'T', 'TMUS', 'CMCSA',
]


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_score(yesterday_return: float, today_return: float, rsi: float,
                   sma20_above: bool, sma50_above: bool, atr_pct: float) -> int:
    """Calculate signal score (simplified v5.3.1)"""
    score = 50

    # Dip-bounce
    if yesterday_return <= -3:
        score += 30
    elif yesterday_return <= -2:
        score += 20
    elif yesterday_return <= -1:
        score += 10

    # Bounce strength
    if today_return >= 3:
        score += 20
    elif today_return >= 2:
        score += 15
    elif today_return >= 1:
        score += 10

    # RSI
    if 25 <= rsi <= 40:
        score += 35
    elif 40 < rsi <= 50:
        score += 20

    # Trend
    if sma50_above and sma20_above:
        score += 25
    elif sma20_above:
        score += 15

    # Volatility
    if atr_pct > 5:
        score += 20
    elif atr_pct > 4:
        score += 15
    elif atr_pct > 3:
        score += 10

    return score


def get_all_signals(start_date: str, end_date: str) -> List[Dict]:
    """
    Get all dip-bounce signals with gap information.
    """
    all_signals = []

    for symbol in SAMPLE_STOCKS:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist is None or len(hist) < 50:
                continue

            # Calculate indicators
            hist['prev_close'] = hist['Close'].shift(1)
            hist['daily_return'] = (hist['Close'] - hist['prev_close']) / hist['prev_close'] * 100
            hist['yesterday_return'] = hist['daily_return'].shift(1)
            hist['rsi'] = calculate_rsi(hist['Close'])
            hist['sma20'] = hist['Close'].rolling(window=20).mean()
            hist['sma50'] = hist['Close'].rolling(window=50).mean()

            # Gap calculation: (Open - Previous Close) / Previous Close
            hist['gap_pct'] = (hist['Open'] - hist['prev_close']) / hist['prev_close'] * 100

            # ATR
            hist['tr'] = pd.concat([
                hist['High'] - hist['Low'],
                (hist['High'] - hist['Close'].shift(1)).abs(),
                (hist['Low'] - hist['Close'].shift(1)).abs()
            ], axis=1).max(axis=1)
            hist['atr'] = hist['tr'].rolling(window=14).mean()
            hist['atr_pct'] = hist['atr'] / hist['Close'] * 100

            for i in range(50, len(hist) - 5):
                row = hist.iloc[i]

                yesterday_ret = row.get('yesterday_return', 0)
                today_ret = row.get('daily_return', 0)
                rsi = row.get('rsi', 50)
                gap_pct = row.get('gap_pct', 0)

                if pd.isna(yesterday_ret) or pd.isna(today_ret) or pd.isna(rsi) or pd.isna(gap_pct):
                    continue

                # Dip-bounce filter
                if not (yesterday_ret <= -2.0 and today_ret >= 1.0):
                    continue

                # Calculate score
                sma20_above = row['Close'] > row['sma20'] if not pd.isna(row['sma20']) else False
                sma50_above = row['Close'] > row['sma50'] if not pd.isna(row['sma50']) else False
                atr_pct = row['atr_pct'] if not pd.isna(row['atr_pct']) else 3.0

                score = calculate_score(yesterday_ret, today_ret, rsi, sma20_above, sma50_above, atr_pct)

                if score < 80:  # MIN_SCORE filter
                    continue

                # Calculate outcome (TP +4%, SL -2%, max 4 days)
                entry_price = row['Close']
                future_prices = hist.iloc[i+1:i+6]['Close'].values

                if len(future_prices) < 3:
                    continue

                exit_return = 0
                for j, future_price in enumerate(future_prices[:4], 1):
                    pct_change = (future_price - entry_price) / entry_price * 100
                    if pct_change >= 4.0:
                        exit_return = 4.0
                        break
                    elif pct_change <= -2.0:
                        exit_return = -2.0
                        break
                    exit_return = pct_change

                all_signals.append({
                    'symbol': symbol,
                    'date': hist.index[i],
                    'score': score,
                    'gap_pct': gap_pct,
                    'exit_return': exit_return,
                    'is_winner': exit_return > 0,
                })

        except Exception as e:
            continue

    return all_signals


def apply_gap_filter(signals: List[Dict], config: Dict) -> Tuple[List[Dict], List[Dict]]:
    """
    Apply gap filter to signals.
    Returns (passed, blocked)
    """
    passed = []
    blocked = []

    gap_up_max = config['gap_up_max']
    gap_down_max = config['gap_down_max']

    for signal in signals:
        gap = signal['gap_pct']

        # Check gap up
        if gap > 0 and gap > gap_up_max:
            blocked.append(signal)
            continue

        # Check gap down
        if gap < 0 and abs(gap) > gap_down_max:
            blocked.append(signal)
            continue

        passed.append(signal)

    return passed, blocked


def calculate_metrics(signals: List[Dict]) -> Dict:
    """Calculate performance metrics"""
    if not signals:
        return {
            'trades': 0,
            'win_rate': 0,
            'total_return': 0,
            'expectancy': 0,
            'avg_win': 0,
            'avg_loss': 0,
        }

    wins = [s for s in signals if s['is_winner']]
    losses = [s for s in signals if not s['is_winner']]

    win_rate = len(wins) / len(signals) * 100
    total_return = sum(s['exit_return'] for s in signals)
    avg_win = statistics.mean([s['exit_return'] for s in wins]) if wins else 0
    avg_loss = statistics.mean([s['exit_return'] for s in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)

    return {
        'trades': len(signals),
        'win_rate': win_rate,
        'total_return': total_return,
        'expectancy': expectancy,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
    }


def analyze_by_gap_bucket(signals: List[Dict]) -> Dict:
    """Analyze performance by gap size buckets"""
    buckets = {
        'gap_down_5+': lambda g: g <= -5,
        'gap_down_3-5': lambda g: -5 < g <= -3,
        'gap_down_1-3': lambda g: -3 < g <= -1,
        'gap_down_0-1': lambda g: -1 < g <= 0,
        'gap_up_0-1': lambda g: 0 < g <= 1,
        'gap_up_1-3': lambda g: 1 < g <= 3,
        'gap_up_3-5': lambda g: 3 < g <= 5,
        'gap_up_5+': lambda g: g > 5,
    }

    results = {}
    for bucket_name, condition in buckets.items():
        bucket_signals = [s for s in signals if condition(s['gap_pct'])]
        if bucket_signals:
            metrics = calculate_metrics(bucket_signals)
            results[bucket_name] = metrics
        else:
            results[bucket_name] = {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    return results


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 70)
    print("BACKTEST: Gap Filter (P5)")
    print("=" * 70)
    print("Testing gap filter configurations")
    print()

    # Date range: last 2 years
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

    print(f"Period: {start_date} to {end_date}")
    print(f"Stocks: {len(SAMPLE_STOCKS)}")
    print()

    # Get all signals
    print("Collecting signals...")
    all_signals = get_all_signals(start_date, end_date)
    print(f"Total signals found: {len(all_signals)}")
    print()

    if not all_signals:
        print("No signals found!")
        return

    # Gap bucket analysis first
    print("=" * 70)
    print("GAP SIZE ANALYSIS (All Signals)")
    print("=" * 70)
    print()
    print(f"{'Gap Bucket':<15} {'Trades':<8} {'Win%':<10} {'E[R]':<10} {'Total%':<10}")
    print("-" * 55)

    bucket_results = analyze_by_gap_bucket(all_signals)
    for bucket, stats in bucket_results.items():
        if stats['trades'] > 0:
            print(f"{bucket:<15} {stats['trades']:<8} {stats['win_rate']:.1f}%{'':<5} "
                  f"{stats['expectancy']:+.3f}%{'':<4} {stats['total_return']:+.1f}%")

    print()

    # Test each filter
    print("=" * 70)
    print("GAP FILTER COMPARISON")
    print("=" * 70)
    print()
    print(f"{'Filter':<18} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'Total%':<10} {'Blocked':<8} {'BlkWin':<8}")
    print("-" * 75)

    results = {}
    for name, config in GAP_FILTERS.items():
        passed, blocked = apply_gap_filter(all_signals, config)
        metrics = calculate_metrics(passed)

        blocked_winners = len([s for s in blocked if s['is_winner']])
        blocked_losers = len([s for s in blocked if not s['is_winner']])

        results[name] = {
            **metrics,
            'blocked': len(blocked),
            'blocked_winners': blocked_winners,
            'blocked_losers': blocked_losers,
        }

        marker = " ← baseline" if name == 'NO_FILTER' else ""
        print(f"{name:<18} {metrics['trades']:<8} {metrics['win_rate']:.1f}%{'':<3} "
              f"{metrics['expectancy']:+.3f}%{'':<4} {metrics['total_return']:+.1f}%{'':<5} "
              f"{len(blocked):<8} {blocked_winners:<8}{marker}")

    print()

    # Find best filter
    print("=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print()

    baseline = results['NO_FILTER']

    # Show gap patterns
    print("Gap Pattern Insights:")
    for bucket, stats in bucket_results.items():
        if stats['trades'] >= 5:
            quality = "GOOD" if stats['expectancy'] > baseline['expectancy'] else "BAD"
            print(f"  {bucket}: E[R]={stats['expectancy']:+.3f}% ({quality})")

    print()

    # Recommendation
    print("=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    print()

    # Find best filter by expectancy with reasonable trade count
    valid_filters = {k: v for k, v in results.items() if v['trades'] >= 20}
    if valid_filters:
        best_name = max(valid_filters.keys(), key=lambda k: valid_filters[k]['expectancy'])
        best = valid_filters[best_name]

        if best_name == 'NO_FILTER':
            print("✅ NO GAP FILTER NEEDED")
            print("   Baseline (no filter) has best or comparable expectancy")
        else:
            improvement = best['expectancy'] - baseline['expectancy']
            if improvement > 0.05:  # Meaningful improvement
                print(f"⚠️ CONSIDER: {best_name}")
                print(f"   Improves expectancy by {improvement:+.3f}%")
                print(f"   Blocks {best['blocked']} trades ({best['blocked_winners']} winners, {best['blocked_losers']} losers)")
            else:
                print("✅ NO GAP FILTER NEEDED")
                print("   No significant improvement from gap filtering")

    # Specific gap insights
    print()
    print("Gap-specific findings:")

    gap_up_5_bucket = bucket_results.get('gap_up_5+', {})
    gap_down_5_bucket = bucket_results.get('gap_down_5+', {})

    if gap_up_5_bucket.get('trades', 0) >= 3:
        print(f"  - Gap up 5%+: E[R]={gap_up_5_bucket['expectancy']:+.3f}% "
              f"({'SKIP' if gap_up_5_bucket['expectancy'] < 0 else 'KEEP'})")

    if gap_down_5_bucket.get('trades', 0) >= 3:
        print(f"  - Gap down 5%+: E[R]={gap_down_5_bucket['expectancy']:+.3f}% "
              f"({'SKIP' if gap_down_5_bucket['expectancy'] < 0 else 'KEEP'})")


if __name__ == '__main__':
    main()
