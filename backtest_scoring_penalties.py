#!/usr/bin/env python3
"""
Backtest: Scoring Penalties Impact Analysis

Hypothesis:
  H0: Scoring penalties (RSI, Volume) help filter bad trades
  H1: Scoring penalties hurt expectancy by filtering good momentum trades

Current Penalties (v5.3 mild):
  RSI > 70  → -4 points
  RSI > 60  → -2 points
  Vol < 0.3 → -3 points
  Vol < 0.5 → -2 points

Test Cases:
  1. BASE: No penalties (score = raw score)
  2. MILD: Current v5.3 penalties
  3. AGGRESSIVE: Stronger penalties (RSI -8/-5, Vol -5/-3)
  4. RSI_ONLY: Only RSI penalties, no volume
  5. VOL_ONLY: Only volume penalties, no RSI

Approach:
  Simulate dip-bounce trades with different penalty configs.
  Use historical data with RSI and volume calculations.
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
    print("yfinance not available - install with: pip install yfinance")


# Penalty configurations to test
PENALTY_CONFIGS = {
    'NO_PENALTY': {
        'rsi_70': 0, 'rsi_60': 0,
        'vol_03': 0, 'vol_05': 0,
        'description': 'No penalties (baseline)',
    },
    'MILD_V53': {
        'rsi_70': -4, 'rsi_60': -2,
        'vol_03': -3, 'vol_05': -2,
        'description': 'Current v5.3 mild penalties',
    },
    'AGGRESSIVE': {
        'rsi_70': -10, 'rsi_60': -6,
        'vol_03': -5, 'vol_05': -3,
        'description': 'Aggressive penalties',
    },
    'RSI_ONLY': {
        'rsi_70': -8, 'rsi_60': -4,
        'vol_03': 0, 'vol_05': 0,
        'description': 'RSI penalties only (stronger)',
    },
    'MEDIUM_RSI_PENALTY': {
        # Penalize MEDIUM RSI (50-70) instead of HIGH
        'rsi_70': 0, 'rsi_60': -5,  # Only penalize 60-70 range
        'vol_03': 0, 'vol_05': 0,
        'description': 'Penalize medium RSI (60-70)',
    },
    'RSI_BONUS': {
        'rsi_70': +5, 'rsi_60': +2,  # BONUS for high RSI!
        'vol_03': 0, 'vol_05': 0,
        'description': 'RSI bonus (high RSI = good)',
    },
}

# Min score threshold for trades (lower to see penalty effects)
MIN_SCORE = 70

# Sample stocks for simulation (diverse sectors)
SAMPLE_STOCKS = [
    # Technology
    'AAPL', 'MSFT', 'NVDA', 'AMD', 'INTC', 'AVGO', 'QCOM',
    # Healthcare
    'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY',
    # Financial
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C',
    # Consumer
    'AMZN', 'TSLA', 'HD', 'NKE', 'MCD', 'SBUX',
    # Energy
    'XOM', 'CVX', 'COP', 'SLB', 'EOG',
    # Industrial
    'CAT', 'DE', 'UNP', 'HON', 'GE',
    # Communication
    'GOOGL', 'META', 'NFLX', 'DIS', 'VZ',
]


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI from price series"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_volume_ratio(volume: pd.Series, period: int = 20) -> pd.Series:
    """Calculate volume ratio vs average"""
    avg_volume = volume.rolling(window=period, min_periods=period).mean()
    return volume / avg_volume


def calculate_base_score(yesterday_return: float, today_return: float,
                         sma20_above: bool, sma50_above: bool,
                         atr_pct: float, dist_from_high: float) -> int:
    """
    Calculate base score WITHOUT RSI/Volume penalties.
    Simplified version of screener scoring.
    """
    score = 50  # Base score

    # 1. Dip-bounce pattern
    if yesterday_return <= -3:
        score += 25
    elif yesterday_return <= -2:
        score += 20
    elif yesterday_return <= -1:
        score += 10

    # 2. Today's bounce strength
    if today_return >= 2:
        score += 15
    elif today_return >= 1:
        score += 10

    # 3. Trend context
    if sma50_above and sma20_above:
        score += 25
    elif sma20_above:
        score += 15

    # 4. Volatility (higher = better for mean reversion)
    if atr_pct > 5:
        score += 20
    elif atr_pct > 4:
        score += 15
    elif atr_pct > 3:
        score += 10

    # 5. Room to recover
    if 10 <= dist_from_high <= 25:
        score += 20
    elif 6 <= dist_from_high < 10:
        score += 10

    return score


def apply_penalties(base_score: int, rsi: float, volume_ratio: float, config: Dict) -> Tuple[int, Dict]:
    """
    Apply penalties to base score based on config.
    Returns (final_score, penalty_details)
    """
    score = base_score
    details = {'base': base_score, 'rsi_penalty': 0, 'vol_penalty': 0}

    # RSI penalties
    if rsi > 70:
        penalty = config['rsi_70']
        score += penalty
        details['rsi_penalty'] = penalty
    elif rsi > 60:
        penalty = config['rsi_60']
        score += penalty
        details['rsi_penalty'] = penalty

    # Volume penalties
    if volume_ratio < 0.3:
        penalty = config['vol_03']
        score += penalty
        details['vol_penalty'] = penalty
    elif volume_ratio < 0.5:
        penalty = config['vol_05']
        score += penalty
        details['vol_penalty'] = penalty

    details['final'] = score
    return score, details


def get_signals_for_symbol(symbol: str, start_date: str, end_date: str) -> List[Dict]:
    """
    Find dip-bounce signals with RSI and volume data.
    Returns raw signal data without penalty filtering.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date)

        if hist is None or len(hist) < 50:
            return []

        # Calculate indicators
        hist['prev_close'] = hist['Close'].shift(1)
        hist['daily_return'] = (hist['Close'] - hist['prev_close']) / hist['prev_close'] * 100
        hist['yesterday_return'] = hist['daily_return'].shift(1)
        hist['rsi'] = calculate_rsi(hist['Close'])
        hist['volume_ratio'] = calculate_volume_ratio(hist['Volume'])
        hist['sma20'] = hist['Close'].rolling(window=20).mean()
        hist['sma50'] = hist['Close'].rolling(window=50).mean()
        hist['high_52w'] = hist['High'].rolling(window=252, min_periods=50).max()
        hist['dist_from_high'] = (hist['high_52w'] - hist['Close']) / hist['high_52w'] * 100

        # ATR calculation
        hist['tr'] = pd.concat([
            hist['High'] - hist['Low'],
            (hist['High'] - hist['Close'].shift(1)).abs(),
            (hist['Low'] - hist['Close'].shift(1)).abs()
        ], axis=1).max(axis=1)
        hist['atr'] = hist['tr'].rolling(window=14).mean()
        hist['atr_pct'] = hist['atr'] / hist['Close'] * 100

        signals = []

        for i in range(50, len(hist) - 5):
            row = hist.iloc[i]

            yesterday_ret = row.get('yesterday_return', 0)
            today_ret = row.get('daily_return', 0)
            rsi = row.get('rsi', 50)
            volume_ratio = row.get('volume_ratio', 1.0)

            if pd.isna(yesterday_ret) or pd.isna(today_ret) or pd.isna(rsi):
                continue

            # Check dip-bounce pattern
            is_dip = yesterday_ret <= -2.0
            is_bounce = today_ret >= 1.0

            if not (is_dip and is_bounce):
                continue

            entry_price = row['Close']
            entry_date = hist.index[i]

            # Calculate base score
            sma20_above = entry_price > row['sma20'] if not pd.isna(row['sma20']) else False
            sma50_above = entry_price > row['sma50'] if not pd.isna(row['sma50']) else False
            atr_pct = row['atr_pct'] if not pd.isna(row['atr_pct']) else 3.0
            dist_from_high = row['dist_from_high'] if not pd.isna(row['dist_from_high']) else 10.0

            base_score = calculate_base_score(
                yesterday_ret, today_ret, sma20_above, sma50_above, atr_pct, dist_from_high
            )

            # Simulate exit
            tp_price = entry_price * 1.04
            sl_price = entry_price * 0.975

            exit_price = None
            exit_reason = None

            for j in range(i + 1, min(i + 6, len(hist))):
                day = hist.iloc[j]
                high, low, close = day['High'], day['Low'], day['Close']

                if low <= sl_price:
                    exit_price = sl_price
                    exit_reason = 'SL'
                    break
                if high >= tp_price:
                    exit_price = tp_price
                    exit_reason = 'TP'
                    break
                if j == i + 5:
                    exit_price = close
                    exit_reason = 'MAX_HOLD'
                    break

            if exit_price is None:
                continue

            pnl_pct = (exit_price - entry_price) / entry_price * 100

            signals.append({
                'symbol': symbol,
                'entry_date': entry_date,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'pnl_pct': round(pnl_pct, 2),
                'base_score': base_score,
                'rsi': round(rsi, 1),
                'volume_ratio': round(volume_ratio, 2),
                'yesterday_dip': round(yesterday_ret, 2),
                'today_bounce': round(today_ret, 2),
                'atr_pct': round(atr_pct, 2),
            })

        return signals

    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return []


def filter_by_score(signals: List[Dict], config: Dict, min_score: int) -> Tuple[List[Dict], List[Dict]]:
    """
    Filter signals by applying penalties and checking min_score.
    Returns (accepted, rejected)
    """
    accepted = []
    rejected = []

    for sig in signals:
        final_score, details = apply_penalties(
            sig['base_score'], sig['rsi'], sig['volume_ratio'], config
        )
        sig_copy = {**sig, 'final_score': final_score, 'penalty_details': details}

        if final_score >= min_score:
            accepted.append(sig_copy)
        else:
            rejected.append(sig_copy)

    return accepted, rejected


def calculate_metrics(trades: List[Dict], label: str) -> Dict:
    """Calculate trading metrics"""
    if not trades:
        return {
            'label': label, 'count': 0, 'win_rate': 0,
            'avg_win': 0, 'avg_loss': 0, 'expectancy': 0,
            'total_pnl': 0, 'max_dd': 0,
        }

    wins = [t for t in trades if t.get('pnl_pct', 0) > 0]
    losses = [t for t in trades if t.get('pnl_pct', 0) <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([abs(t['pnl_pct']) for t in losses]) if losses else 0

    expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)
    total_pnl = sum(t.get('pnl_pct', 0) for t in trades)

    # Max drawdown
    cumulative = 0
    peak = 0
    max_dd = 0
    for t in trades:
        cumulative += t.get('pnl_pct', 0)
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

    return {
        'label': label,
        'count': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(win_rate, 1),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'expectancy': round(expectancy, 3),
        'total_pnl': round(total_pnl, 2),
        'max_dd': round(max_dd, 2),
    }


def analyze_rejected_trades(rejected: List[Dict]) -> Dict:
    """Analyze what we're missing by rejecting trades"""
    if not rejected:
        return {'count': 0, 'would_have_won': 0, 'would_have_lost': 0, 'net_impact': 0}

    winners = [t for t in rejected if t.get('pnl_pct', 0) > 0]
    losers = [t for t in rejected if t.get('pnl_pct', 0) <= 0]

    return {
        'count': len(rejected),
        'would_have_won': len(winners),
        'would_have_lost': len(losers),
        'missed_profit': round(sum(t.get('pnl_pct', 0) for t in winners), 2),
        'avoided_loss': round(sum(abs(t.get('pnl_pct', 0)) for t in losers), 2),
        'net_impact': round(sum(t.get('pnl_pct', 0) for t in rejected), 2),
    }


def analyze_high_rsi_trades(signals: List[Dict]) -> Dict:
    """Analyze performance of high RSI trades specifically"""
    high_rsi = [s for s in signals if s.get('rsi', 0) > 70]
    medium_rsi = [s for s in signals if 50 <= s.get('rsi', 0) <= 70]
    low_rsi = [s for s in signals if s.get('rsi', 0) < 50]

    return {
        'high_rsi_70+': calculate_metrics(high_rsi, 'RSI>70'),
        'medium_rsi_50-70': calculate_metrics(medium_rsi, 'RSI 50-70'),
        'low_rsi_<50': calculate_metrics(low_rsi, 'RSI<50'),
    }


def analyze_low_volume_trades(signals: List[Dict]) -> Dict:
    """Analyze performance of low volume trades specifically"""
    low_vol = [s for s in signals if s.get('volume_ratio', 1) < 0.5]
    medium_vol = [s for s in signals if 0.5 <= s.get('volume_ratio', 1) <= 1.5]
    high_vol = [s for s in signals if s.get('volume_ratio', 1) > 1.5]

    return {
        'low_vol_<0.5': calculate_metrics(low_vol, 'Vol<0.5'),
        'medium_vol_0.5-1.5': calculate_metrics(medium_vol, 'Vol 0.5-1.5'),
        'high_vol_>1.5': calculate_metrics(high_vol, 'Vol>1.5'),
    }


def run_backtest():
    """Run the scoring penalties backtest"""
    if not YFINANCE_AVAILABLE:
        print("yfinance required for this backtest")
        return

    print("=" * 70)
    print("BACKTEST: Scoring Penalties Impact Analysis")
    print("=" * 70)
    print(f"\nMin Score Threshold: {MIN_SCORE}")

    # Date range
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    print(f"Period: {start_date} to {end_date}")

    # Collect all signals
    print(f"\nScanning {len(SAMPLE_STOCKS)} stocks for dip-bounce signals...")
    all_signals = []

    for i, symbol in enumerate(SAMPLE_STOCKS):
        print(f"  [{i+1}/{len(SAMPLE_STOCKS)}] {symbol}...", end=" ", flush=True)
        signals = get_signals_for_symbol(symbol, start_date, end_date)
        print(f"{len(signals)} signals")
        all_signals.extend(signals)

    all_signals.sort(key=lambda x: x['entry_date'])
    print(f"\nTotal raw signals: {len(all_signals)}")

    if not all_signals:
        print("No signals found. Check date range or stock data.")
        return

    # ================================================================
    # TEST 1: Compare penalty configurations
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 1: Penalty Configuration Comparison")
    print("=" * 70)

    results = {}
    for config_name, config in PENALTY_CONFIGS.items():
        accepted, rejected = filter_by_score(all_signals, config, MIN_SCORE)
        metrics = calculate_metrics(accepted, config_name)
        rejected_analysis = analyze_rejected_trades(rejected)
        results[config_name] = {
            'metrics': metrics,
            'rejected': rejected_analysis,
            'config': config,
        }

    # Print comparison table
    print(f"\n{'Config':<15} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'Total%':<10} {'Rejected':<10}")
    print("-" * 70)

    baseline_exp = results['NO_PENALTY']['metrics']['expectancy']
    for config_name in PENALTY_CONFIGS.keys():
        m = results[config_name]['metrics']
        r = results[config_name]['rejected']
        delta = m['expectancy'] - baseline_exp
        delta_str = f"({delta:+.3f})" if config_name != 'NO_PENALTY' else ""
        print(f"{config_name:<15} {m['count']:<8} {m['win_rate']:<8.1f} {m['expectancy']:<10.3f} {m['total_pnl']:<10.2f} {r['count']:<10}")

    # ================================================================
    # TEST 2: RSI Analysis
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 2: RSI Impact Analysis (Using ALL signals, no filter)")
    print("=" * 70)

    rsi_analysis = analyze_high_rsi_trades(all_signals)
    print(f"\n{'RSI Range':<20} {'Count':<8} {'Win%':<8} {'E[R]':<10} {'Avg Win':<10} {'Avg Loss':<10}")
    print("-" * 70)
    for label, metrics in rsi_analysis.items():
        print(f"{label:<20} {metrics['count']:<8} {metrics['win_rate']:<8.1f} {metrics['expectancy']:<10.3f} {metrics['avg_win']:<10.2f} {metrics['avg_loss']:<10.2f}")

    # ================================================================
    # TEST 3: Volume Analysis
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 3: Volume Impact Analysis (Using ALL signals, no filter)")
    print("=" * 70)

    vol_analysis = analyze_low_volume_trades(all_signals)
    print(f"\n{'Volume Range':<20} {'Count':<8} {'Win%':<8} {'E[R]':<10} {'Avg Win':<10} {'Avg Loss':<10}")
    print("-" * 70)
    for label, metrics in vol_analysis.items():
        print(f"{label:<20} {metrics['count']:<8} {metrics['win_rate']:<8.1f} {metrics['expectancy']:<10.3f} {metrics['avg_win']:<10.2f} {metrics['avg_loss']:<10.2f}")

    # ================================================================
    # TEST 4: Detailed rejection analysis for MILD_V53
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 4: Current Config (MILD_V53) Rejection Analysis")
    print("=" * 70)

    mild_accepted, mild_rejected = filter_by_score(all_signals, PENALTY_CONFIGS['MILD_V53'], MIN_SCORE)

    print(f"\nAccepted: {len(mild_accepted)} trades")
    print(f"Rejected: {len(mild_rejected)} trades")

    if mild_rejected:
        rej_analysis = analyze_rejected_trades(mild_rejected)
        print(f"\nRejected trades breakdown:")
        print(f"  Would have WON:  {rej_analysis['would_have_won']} (+{rej_analysis['missed_profit']:.2f}%)")
        print(f"  Would have LOST: {rej_analysis['would_have_lost']} (-{rej_analysis['avoided_loss']:.2f}%)")
        print(f"  NET IMPACT: {rej_analysis['net_impact']:+.2f}%")

        # Why were they rejected?
        high_rsi_rejected = [r for r in mild_rejected if r.get('rsi', 0) > 60]
        low_vol_rejected = [r for r in mild_rejected if r.get('volume_ratio', 1) < 0.5]
        score_rejected = [r for r in mild_rejected if r.get('rsi', 0) <= 60 and r.get('volume_ratio', 1) >= 0.5]

        print(f"\nRejection reasons:")
        print(f"  High RSI (>60): {len(high_rsi_rejected)}")
        print(f"  Low Volume (<0.5): {len(low_vol_rejected)}")
        print(f"  Base score too low: {len(score_rejected)}")

    # ================================================================
    # CONCLUSION
    # ================================================================
    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)

    no_penalty = results['NO_PENALTY']['metrics']
    mild = results['MILD_V53']['metrics']
    aggressive = results['AGGRESSIVE']['metrics']

    mild_delta = mild['expectancy'] - no_penalty['expectancy']
    aggressive_delta = aggressive['expectancy'] - no_penalty['expectancy']

    print(f"\nExpectancy vs NO_PENALTY baseline:")
    print(f"  MILD_V53 (current): {mild_delta:+.3f}%")
    print(f"  AGGRESSIVE:         {aggressive_delta:+.3f}%")

    # Determine recommendation
    if mild_delta < -0.1:
        print(f"\n🔴 CURRENT PENALTIES HURT EXPECTANCY: {mild_delta:+.3f}%")
        print("   Recommendation: REMOVE or REDUCE penalties")
    elif mild_delta > 0.1:
        print(f"\n🟢 CURRENT PENALTIES HELP: {mild_delta:+.3f}%")
        print("   Recommendation: KEEP current settings")
    else:
        print(f"\n🟡 CURRENT PENALTIES NEUTRAL: {mild_delta:+.3f}%")
        print("   Recommendation: Consider removing for simplicity")

    # RSI-specific recommendation
    rsi_high = rsi_analysis['high_rsi_70+']
    rsi_low = rsi_analysis['low_rsi_<50']
    if rsi_high['count'] > 0 and rsi_low['count'] > 0:
        if rsi_high['expectancy'] > rsi_low['expectancy']:
            print(f"\n⚠️  HIGH RSI trades ({rsi_high['expectancy']:.3f}) outperform LOW RSI ({rsi_low['expectancy']:.3f})")
            print("   RSI penalty may be counterproductive!")

    # Show sample rejected winners
    if mild_rejected:
        winners = [r for r in mild_rejected if r.get('pnl_pct', 0) > 0][:5]
        if winners:
            print("\n--- Sample Rejected Winners (MILD_V53) ---")
            for w in winners:
                print(f"  {w['symbol']}: +{w['pnl_pct']:.2f}% (RSI={w['rsi']:.0f}, Vol={w['volume_ratio']:.2f}, Base={w['base_score']}, Final={w['final_score']})")


if __name__ == '__main__':
    run_backtest()
