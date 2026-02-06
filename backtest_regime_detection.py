#!/usr/bin/env python3
"""
Backtest: Regime Detection (P6)

Hypothesis:
  H0: Regime detection helps avoid bad trades in BEAR markets
  H1: Regime detection blocks good mean-reversion trades

Current Setting:
  - VIX > 25 = BEAR
  - SPY below SMA50 = BEAR
  - Multiple sector weakness = BEAR

Test Cases:
  1. NO_REGIME: Trade all conditions equally
  2. VIX_ONLY: Use VIX threshold only
  3. SPY_TREND: Use SPY SMA only
  4. COMBINED: VIX + SPY (current)
  5. AGGRESSIVE_BEAR: Lower VIX threshold (20)
  6. RELAXED_BEAR: Higher VIX threshold (30)

Metrics:
  - Performance by regime
  - Blocked trades analysis
  - Regime accuracy
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


# Regime detection configurations
REGIME_CONFIGS = {
    'NO_REGIME': {
        'vix_bear': 999,
        'spy_sma': False,
        'action': 'trade_all',
        'desc': 'No regime filter',
    },
    'VIX_20': {
        'vix_bear': 20,
        'spy_sma': False,
        'action': 'skip_bear',
        'desc': 'VIX > 20 = BEAR, skip',
    },
    'VIX_25': {
        'vix_bear': 25,
        'spy_sma': False,
        'action': 'skip_bear',
        'desc': 'VIX > 25 = BEAR, skip (current)',
    },
    'VIX_30': {
        'vix_bear': 30,
        'spy_sma': False,
        'action': 'skip_bear',
        'desc': 'VIX > 30 = BEAR, skip',
    },
    'SPY_SMA50': {
        'vix_bear': 999,
        'spy_sma': True,
        'spy_sma_period': 50,
        'action': 'skip_bear',
        'desc': 'SPY < SMA50 = BEAR, skip',
    },
    'SPY_SMA20': {
        'vix_bear': 999,
        'spy_sma': True,
        'spy_sma_period': 20,
        'action': 'skip_bear',
        'desc': 'SPY < SMA20 = BEAR, skip',
    },
    'COMBINED_25': {
        'vix_bear': 25,
        'spy_sma': True,
        'spy_sma_period': 50,
        'action': 'skip_bear',
        'desc': 'VIX>25 OR SPY<SMA50 = BEAR',
    },
    'REDUCE_SIZE': {
        'vix_bear': 25,
        'spy_sma': True,
        'spy_sma_period': 50,
        'action': 'reduce_bear',  # 50% size in BEAR
        'desc': 'Reduce size 50% in BEAR',
    },
}


# Sample stocks
SAMPLE_STOCKS = [
    'AAPL', 'MSFT', 'NVDA', 'AMD', 'INTC', 'AVGO', 'QCOM', 'CRM', 'ADBE',
    'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN',
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'V', 'MA',
    'AMZN', 'TSLA', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'WMT', 'COST',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY',
    'CAT', 'DE', 'UNP', 'HON', 'GE', 'RTX',
    'GOOGL', 'META', 'NFLX', 'DIS', 'VZ', 'T',
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


def get_market_data(start_date: str, end_date: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Get SPY and VIX data"""
    try:
        spy = yf.Ticker('SPY').history(start=start_date, end=end_date)
        vix = yf.Ticker('^VIX').history(start=start_date, end=end_date)

        # Calculate SMAs for SPY
        spy['sma20'] = spy['Close'].rolling(window=20).mean()
        spy['sma50'] = spy['Close'].rolling(window=50).mean()
        spy['sma200'] = spy['Close'].rolling(window=200).mean()

        return spy, vix
    except Exception as e:
        print(f"Error getting market data: {e}")
        return None, None


def detect_regime(date: pd.Timestamp, spy: pd.DataFrame, vix: pd.DataFrame,
                  config: Dict) -> Tuple[str, Dict]:
    """
    Detect market regime for a given date.
    Returns (regime, details)
    """
    try:
        # Find closest date in data
        spy_dates = spy.index[spy.index <= date]
        vix_dates = vix.index[vix.index <= date]

        if len(spy_dates) == 0 or len(vix_dates) == 0:
            return 'NEUTRAL', {}

        spy_row = spy.loc[spy_dates[-1]]
        vix_row = vix.loc[vix_dates[-1]]

        vix_value = vix_row['Close']
        spy_close = spy_row['Close']
        spy_sma50 = spy_row.get('sma50', spy_close)
        spy_sma20 = spy_row.get('sma20', spy_close)

        details = {
            'vix': vix_value,
            'spy_close': spy_close,
            'spy_sma50': spy_sma50,
            'spy_sma20': spy_sma20,
        }

        # Check BEAR conditions
        is_bear = False

        # VIX check
        if vix_value > config['vix_bear']:
            is_bear = True
            details['bear_reason'] = 'VIX'

        # SPY SMA check
        if config.get('spy_sma', False):
            sma_period = config.get('spy_sma_period', 50)
            sma_value = spy_sma50 if sma_period == 50 else spy_sma20
            if not pd.isna(sma_value) and spy_close < sma_value:
                is_bear = True
                details['bear_reason'] = details.get('bear_reason', '') + '+SPY'

        # Determine regime
        if config['action'] == 'trade_all':
            regime = 'NEUTRAL'  # Treat all as neutral
        elif is_bear:
            regime = 'BEAR'
        elif vix_value < 15 and spy_close > spy_sma50:
            regime = 'BULL'
        else:
            regime = 'NEUTRAL'

        return regime, details

    except Exception as e:
        return 'NEUTRAL', {}


def get_all_signals(start_date: str, end_date: str, spy: pd.DataFrame,
                    vix: pd.DataFrame) -> List[Dict]:
    """Get all signals with regime information"""
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
                signal_date = hist.index[i]

                yesterday_ret = row.get('yesterday_return', 0)
                today_ret = row.get('daily_return', 0)
                rsi = row.get('rsi', 50)

                if pd.isna(yesterday_ret) or pd.isna(today_ret) or pd.isna(rsi):
                    continue

                # Dip-bounce filter
                if not (yesterday_ret <= -2.0 and today_ret >= 1.0):
                    continue

                # Calculate score
                score = 50
                if yesterday_ret <= -3:
                    score += 30
                elif yesterday_ret <= -2:
                    score += 20
                if today_ret >= 2:
                    score += 15
                elif today_ret >= 1:
                    score += 10
                if 25 <= rsi <= 40:
                    score += 35
                elif 40 < rsi <= 50:
                    score += 20

                sma20_above = row['Close'] > row['sma20'] if not pd.isna(row['sma20']) else False
                sma50_above = row['Close'] > row['sma50'] if not pd.isna(row['sma50']) else False
                if sma50_above and sma20_above:
                    score += 25
                elif sma20_above:
                    score += 15

                if score < 80:
                    continue

                # Get VIX and SPY values for this date
                try:
                    vix_dates = vix.index[vix.index <= signal_date]
                    spy_dates = spy.index[spy.index <= signal_date]

                    if len(vix_dates) > 0 and len(spy_dates) > 0:
                        vix_value = vix.loc[vix_dates[-1]]['Close']
                        spy_row = spy.loc[spy_dates[-1]]
                        spy_close = spy_row['Close']
                        spy_sma50 = spy_row.get('sma50', spy_close)
                        spy_sma20 = spy_row.get('sma20', spy_close)
                    else:
                        vix_value = 20
                        spy_close = 0
                        spy_sma50 = 0
                        spy_sma20 = 0
                except:
                    vix_value = 20
                    spy_close = 0
                    spy_sma50 = 0
                    spy_sma20 = 0

                # Calculate outcome
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
                    'date': signal_date,
                    'score': score,
                    'vix': vix_value,
                    'spy_close': spy_close,
                    'spy_sma50': spy_sma50,
                    'spy_sma20': spy_sma20,
                    'exit_return': exit_return,
                    'is_winner': exit_return > 0,
                })

        except Exception as e:
            continue

    return all_signals


def apply_regime_filter(signals: List[Dict], config: Dict) -> Tuple[List[Dict], List[Dict]]:
    """Apply regime filter to signals"""
    passed = []
    blocked = []

    for signal in signals:
        vix = signal['vix']
        spy_close = signal['spy_close']
        spy_sma50 = signal['spy_sma50']
        spy_sma20 = signal['spy_sma20']

        is_bear = False

        # VIX check
        if vix > config['vix_bear']:
            is_bear = True

        # SPY SMA check
        if config.get('spy_sma', False) and spy_close > 0:
            sma_period = config.get('spy_sma_period', 50)
            sma_value = spy_sma50 if sma_period == 50 else spy_sma20
            if sma_value > 0 and spy_close < sma_value:
                is_bear = True

        # Apply action
        if config['action'] == 'trade_all':
            signal['regime'] = 'ALL'
            passed.append(signal)
        elif config['action'] == 'skip_bear' and is_bear:
            signal['regime'] = 'BEAR'
            blocked.append(signal)
        elif config['action'] == 'reduce_bear' and is_bear:
            signal['regime'] = 'BEAR_REDUCED'
            signal['size_multiplier'] = 0.5
            passed.append(signal)
        else:
            signal['regime'] = 'BULL/NEUTRAL'
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
        }

    wins = [s for s in signals if s['is_winner']]
    losses = [s for s in signals if not s['is_winner']]

    # Adjust for size multiplier if present
    total_return = sum(s['exit_return'] * s.get('size_multiplier', 1) for s in signals)

    win_rate = len(wins) / len(signals) * 100
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


def analyze_by_vix_bucket(signals: List[Dict]) -> Dict:
    """Analyze performance by VIX level"""
    buckets = {
        'VIX_0-15': lambda v: v <= 15,
        'VIX_15-20': lambda v: 15 < v <= 20,
        'VIX_20-25': lambda v: 20 < v <= 25,
        'VIX_25-30': lambda v: 25 < v <= 30,
        'VIX_30+': lambda v: v > 30,
    }

    results = {}
    for name, condition in buckets.items():
        bucket_signals = [s for s in signals if condition(s['vix'])]
        if bucket_signals:
            metrics = calculate_metrics(bucket_signals)
            results[name] = metrics
        else:
            results[name] = {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    return results


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 70)
    print("BACKTEST: Regime Detection (P6)")
    print("=" * 70)
    print("Testing regime detection configurations")
    print()

    # Date range
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

    print(f"Period: {start_date} to {end_date}")
    print()

    # Get market data
    print("Loading SPY and VIX data...")
    spy, vix = get_market_data(start_date, end_date)
    if spy is None or vix is None:
        print("Failed to load market data")
        return

    print(f"SPY: {len(spy)} days, VIX: {len(vix)} days")
    print()

    # Get all signals
    print("Collecting signals...")
    all_signals = get_all_signals(start_date, end_date, spy, vix)
    print(f"Total signals found: {len(all_signals)}")
    print()

    if not all_signals:
        print("No signals found!")
        return

    # VIX bucket analysis
    print("=" * 70)
    print("VIX LEVEL ANALYSIS (All Signals)")
    print("=" * 70)
    print()
    print(f"{'VIX Level':<12} {'Trades':<8} {'Win%':<10} {'E[R]':<10} {'Total%':<10}")
    print("-" * 55)

    vix_results = analyze_by_vix_bucket(all_signals)
    for bucket, stats in vix_results.items():
        if stats['trades'] > 0:
            print(f"{bucket:<12} {stats['trades']:<8} {stats['win_rate']:.1f}%{'':<5} "
                  f"{stats['expectancy']:+.3f}%{'':<4} {stats['total_return']:+.1f}%")

    print()

    # Test each regime config
    print("=" * 70)
    print("REGIME FILTER COMPARISON")
    print("=" * 70)
    print()
    print(f"{'Config':<15} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'Total%':<10} {'Blocked':<8} {'BlkWin':<8}")
    print("-" * 75)

    results = {}
    for name, config in REGIME_CONFIGS.items():
        passed, blocked = apply_regime_filter(all_signals, config)
        metrics = calculate_metrics(passed)

        blocked_winners = len([s for s in blocked if s['is_winner']])
        blocked_losers = len([s for s in blocked if not s['is_winner']])

        results[name] = {
            **metrics,
            'blocked': len(blocked),
            'blocked_winners': blocked_winners,
            'blocked_losers': blocked_losers,
        }

        marker = ""
        if name == 'VIX_25':
            marker = " ← current"
        elif name == 'NO_REGIME':
            marker = " ← baseline"

        print(f"{name:<15} {metrics['trades']:<8} {metrics['win_rate']:.1f}%{'':<3} "
              f"{metrics['expectancy']:+.3f}%{'':<4} {metrics['total_return']:+.1f}%{'':<5} "
              f"{len(blocked):<8} {blocked_winners:<8}{marker}")

    print()

    # Analysis
    print("=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print()

    baseline = results['NO_REGIME']
    current = results['VIX_25']

    print("VIX Level Insights:")
    for bucket, stats in vix_results.items():
        if stats['trades'] >= 5:
            quality = "GOOD" if stats['expectancy'] > 0.3 else ("OK" if stats['expectancy'] > 0 else "BAD")
            print(f"  {bucket}: E[R]={stats['expectancy']:+.3f}%, Win%={stats['win_rate']:.1f}% ({quality})")

    print()
    print(f"Current (VIX_25) vs NO_REGIME:")
    print(f"  - Trades: {current['trades']} vs {baseline['trades']}")
    print(f"  - Win Rate: {current['win_rate']:.1f}% vs {baseline['win_rate']:.1f}%")
    print(f"  - E[R]: {current['expectancy']:+.3f}% vs {baseline['expectancy']:+.3f}%")
    print(f"  - Blocked: {current['blocked']} ({current['blocked_winners']} winners, {current['blocked_losers']} losers)")

    print()

    # Recommendation
    print("=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    print()

    # Find best config
    valid_configs = {k: v for k, v in results.items() if v['trades'] >= 20}
    best_name = max(valid_configs.keys(), key=lambda k: valid_configs[k]['expectancy'])
    best = valid_configs[best_name]

    if best_name == 'NO_REGIME':
        print("⚠️ CONSIDER: Remove regime filter")
        print("   No filter has best expectancy")
    elif best_name == 'VIX_25':
        print("✅ KEEP current VIX_25 regime filter")
    else:
        improvement = best['expectancy'] - current['expectancy']
        if improvement > 0.05:
            print(f"⚠️ CONSIDER: Switch to {best_name}")
            print(f"   Improves E[R] by {improvement:+.3f}%")
        else:
            print("✅ KEEP current VIX_25 regime filter")
            print("   No significant improvement from alternatives")

    # VIX threshold recommendation
    print()
    vix_30_perf = vix_results.get('VIX_30+', {})
    vix_25_30_perf = vix_results.get('VIX_25-30', {})

    if vix_30_perf.get('trades', 0) >= 3:
        if vix_30_perf['expectancy'] < 0:
            print(f"  VIX 30+: E[R]={vix_30_perf['expectancy']:+.3f}% → SKIP these trades")
        else:
            print(f"  VIX 30+: E[R]={vix_30_perf['expectancy']:+.3f}% → OK to trade")


if __name__ == '__main__':
    main()
