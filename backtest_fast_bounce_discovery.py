#!/usr/bin/env python3
"""
Fast Bounce Strategy Discovery

Objective: หา Entry Signal ใหม่ที่ bounce เร็วใน 3-7 วัน (ไม่ใช่ 18 วัน)

Target:
- Bounce ≥ 3% ภายใน 5-7 วัน
- TP hit rate ≥ 40% ภายใน 7 วัน
- E[R] ≥ +0.7% per trade
- Avg hold ≤ 7 วัน
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


# Sample stocks
STOCKS_BY_SECTOR = {
    'Technology': ['AAPL', 'MSFT', 'NVDA', 'AMD', 'AVGO', 'QCOM', 'CRM', 'ADBE'],
    'Healthcare': ['JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN'],
    'Financial': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'V'],
    'Consumer': ['AMZN', 'TSLA', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'WMT'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO'],
    'Industrial': ['CAT', 'DE', 'UNP', 'HON', 'GE', 'RTX', 'LMT', 'UPS'],
    'Communication': ['GOOGL', 'META', 'NFLX', 'DIS', 'VZ', 'T', 'TMUS'],
}

SYMBOL_TO_SECTOR = {}
ALL_SYMBOLS = []
for sector, symbols in STOCKS_BY_SECTOR.items():
    for symbol in symbols:
        SYMBOL_TO_SECTOR[symbol] = sector
        ALL_SYMBOLS.append(symbol)


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def get_vix_data(start_date: str, end_date: str) -> pd.DataFrame:
    """Get VIX data for regime detection"""
    try:
        vix = yf.Ticker('^VIX').history(start=start_date, end=end_date)
        return vix
    except:
        return pd.DataFrame()


def get_all_signals_detailed(start_date: str, end_date: str, vix_data: pd.DataFrame) -> List[Dict]:
    """Get all potential dip signals with detailed metrics for analysis"""
    all_signals = []

    for symbol in ALL_SYMBOLS:
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

            # Volume ratio
            hist['vol_avg20'] = hist['Volume'].rolling(window=20).mean()
            hist['volume_ratio'] = hist['Volume'] / hist['vol_avg20']

            # ATR
            hist['tr'] = pd.concat([
                hist['High'] - hist['Low'],
                (hist['High'] - hist['Close'].shift(1)).abs(),
                (hist['Low'] - hist['Close'].shift(1)).abs()
            ], axis=1).max(axis=1)
            hist['atr'] = hist['tr'].rolling(window=14).mean()
            hist['atr_pct'] = hist['atr'] / hist['Close'] * 100

            # Gap calculation
            hist['gap_pct'] = (hist['Open'] - hist['prev_close']) / hist['prev_close'] * 100

            # Support level (20-day low)
            hist['support_20d'] = hist['Low'].rolling(window=20).min()
            hist['near_support'] = (hist['Low'] - hist['support_20d']) / hist['support_20d'] * 100

            # 5-day sector return (approximated by stock's 5d return)
            hist['return_5d'] = (hist['Close'] - hist['Close'].shift(5)) / hist['Close'].shift(5) * 100

            # Intraday recovery
            hist['intraday_range'] = hist['High'] - hist['Low']
            hist['intraday_recovery'] = (hist['Close'] - hist['Low']) / hist['intraday_range'] * 100

            sector = SYMBOL_TO_SECTOR.get(symbol, 'Unknown')

            for i in range(50, len(hist) - 35):
                row = hist.iloc[i]
                signal_date = hist.index[i]

                yesterday_ret = row.get('yesterday_return', 0)
                today_ret = row.get('daily_return', 0)
                rsi = row.get('rsi', 50)
                atr_pct = row.get('atr_pct', 3.0)
                volume_ratio = row.get('volume_ratio', 1.0)
                gap_pct = row.get('gap_pct', 0)
                near_support = row.get('near_support', 10)
                return_5d = row.get('return_5d', 0)
                intraday_recovery = row.get('intraday_recovery', 50)

                if pd.isna(yesterday_ret) or pd.isna(today_ret):
                    continue

                # Basic dip-bounce filter (looser to capture more signals)
                if not (yesterday_ret <= -1.5 and today_ret >= 0.5):
                    continue

                # Get VIX level
                vix_level = 20.0  # Default
                if not vix_data.empty:
                    vix_dates = vix_data.index[vix_data.index <= signal_date]
                    if len(vix_dates) > 0:
                        vix_level = vix_data.loc[vix_dates[-1]]['Close']

                # Day of week (0=Monday)
                day_of_week = signal_date.dayofweek

                # Future prices for outcome analysis
                future_data = []
                entry_price = row['Close']

                for day in range(1, 31):
                    future_idx = i + day
                    if future_idx < len(hist):
                        fh = hist.iloc[future_idx]['High']
                        fl = hist.iloc[future_idx]['Low']
                        fc = hist.iloc[future_idx]['Close']

                        future_data.append({
                            'day': day,
                            'high_return': (fh - entry_price) / entry_price * 100,
                            'low_return': (fl - entry_price) / entry_price * 100,
                            'close_return': (fc - entry_price) / entry_price * 100,
                        })

                # Determine if fast bounce (hit 3% within 5 days)
                fast_bounce = False
                days_to_3pct = None
                peak_return = 0
                peak_day = 0

                for fd in future_data:
                    if fd['high_return'] > peak_return:
                        peak_return = fd['high_return']
                        peak_day = fd['day']

                    if not fast_bounce and fd['high_return'] >= 3.0:
                        fast_bounce = True
                        days_to_3pct = fd['day']

                all_signals.append({
                    'symbol': symbol,
                    'sector': sector,
                    'date': signal_date,
                    'entry_idx': i,
                    'entry_price': entry_price,
                    'dip_size': abs(yesterday_ret),
                    'bounce_day1': today_ret,
                    'rsi': rsi,
                    'atr_pct': atr_pct if not pd.isna(atr_pct) else 3.0,
                    'volume_ratio': volume_ratio if not pd.isna(volume_ratio) else 1.0,
                    'gap_pct': gap_pct if not pd.isna(gap_pct) else 0,
                    'near_support_pct': near_support if not pd.isna(near_support) else 10,
                    'return_5d': return_5d if not pd.isna(return_5d) else 0,
                    'intraday_recovery': intraday_recovery if not pd.isna(intraday_recovery) else 50,
                    'vix_level': vix_level,
                    'day_of_week': day_of_week,
                    'future_data': future_data,
                    'fast_bounce': fast_bounce,
                    'days_to_3pct': days_to_3pct,
                    'peak_return': peak_return,
                    'peak_day': peak_day,
                    'hist': hist,
                })

        except Exception as e:
            continue

    return all_signals


def analyze_fast_vs_slow(signals: List[Dict]) -> Dict:
    """Analyze differences between fast and slow bounces"""
    fast = [s for s in signals if s['days_to_3pct'] is not None and s['days_to_3pct'] <= 5]
    slow = [s for s in signals if s['days_to_3pct'] is None or s['days_to_3pct'] > 14]
    medium = [s for s in signals if s['days_to_3pct'] is not None and 5 < s['days_to_3pct'] <= 14]

    def get_stats(group, name):
        if not group:
            return {}
        return {
            'name': name,
            'count': len(group),
            'pct': len(group) / len(signals) * 100,
            'avg_dip': statistics.mean([s['dip_size'] for s in group]),
            'avg_rsi': statistics.mean([s['rsi'] for s in group]),
            'avg_volume_ratio': statistics.mean([s['volume_ratio'] for s in group]),
            'avg_bounce_d1': statistics.mean([s['bounce_day1'] for s in group]),
            'avg_gap': statistics.mean([s['gap_pct'] for s in group]),
            'avg_vix': statistics.mean([s['vix_level'] for s in group]),
            'avg_near_support': statistics.mean([s['near_support_pct'] for s in group]),
            'avg_intraday_recovery': statistics.mean([s['intraday_recovery'] for s in group]),
            'sector_dist': defaultdict(int),
            'day_of_week_dist': defaultdict(int),
        }

    fast_stats = get_stats(fast, 'Fast (≤5d)')
    slow_stats = get_stats(slow, 'Slow (>14d)')
    medium_stats = get_stats(medium, 'Medium (5-14d)')

    # Sector distribution
    for group, stats in [(fast, fast_stats), (slow, slow_stats), (medium, medium_stats)]:
        if not group:
            continue
        for s in group:
            stats['sector_dist'][s['sector']] += 1
            stats['day_of_week_dist'][s['day_of_week']] += 1

    return {
        'fast': fast_stats,
        'slow': slow_stats,
        'medium': medium_stats,
        'total': len(signals),
    }


def test_hypothesis(signals: List[Dict], condition_func, condition_name: str) -> Dict:
    """Test a hypothesis about what predicts fast bounce"""
    matching = [s for s in signals if condition_func(s)]
    non_matching = [s for s in signals if not condition_func(s)]

    def calc_fast_rate(group):
        if not group:
            return 0
        fast = sum(1 for s in group if s['days_to_3pct'] is not None and s['days_to_3pct'] <= 5)
        return fast / len(group) * 100

    match_fast_rate = calc_fast_rate(matching)
    non_match_fast_rate = calc_fast_rate(non_matching)

    return {
        'condition': condition_name,
        'matching_count': len(matching),
        'matching_fast_rate': match_fast_rate,
        'non_matching_fast_rate': non_match_fast_rate,
        'lift': match_fast_rate - non_match_fast_rate,
    }


def simulate_trade(signal: Dict, tp_pct: float, sl_pct: float, max_hold: int,
                   trail_enabled: bool = False, trail_activation: float = 2.0,
                   trail_lock: float = 60) -> Dict:
    """Simulate a trade"""
    entry_price = signal['entry_price']
    hist = signal['hist']
    entry_idx = signal['entry_idx']

    tp_price = entry_price * (1 + tp_pct / 100)
    sl_price = entry_price * (1 - sl_pct / 100)

    result = {
        'exit_return': 0,
        'exit_type': 'MAX_HOLD',
        'exit_day': max_hold,
    }

    trailing_sl = None
    peak_price = entry_price

    for day in range(1, min(max_hold + 1, len(hist) - entry_idx)):
        idx = entry_idx + day
        if idx >= len(hist):
            break

        high = hist.iloc[idx]['High']
        low = hist.iloc[idx]['Low']
        close = hist.iloc[idx]['Close']

        if high > peak_price:
            peak_price = high

        # Trailing stop
        if trail_enabled and trailing_sl is None:
            current_gain = (high - entry_price) / entry_price * 100
            if current_gain >= trail_activation:
                locked_gain = current_gain * trail_lock / 100
                trailing_sl = entry_price * (1 + locked_gain / 100)

        if trailing_sl is not None:
            current_gain = (high - entry_price) / entry_price * 100
            new_locked = current_gain * trail_lock / 100
            new_trail_sl = entry_price * (1 + new_locked / 100)
            if new_trail_sl > trailing_sl:
                trailing_sl = new_trail_sl

        # Check SL
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            break

        # Check trailing SL
        if trailing_sl is not None and low <= trailing_sl:
            trail_exit_gain = (trailing_sl - entry_price) / entry_price * 100
            result['exit_return'] = trail_exit_gain
            result['exit_type'] = 'TRAIL_STOP'
            result['exit_day'] = day
            break

        # Check TP
        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_day'] = day
            break

        result['exit_return'] = (close - entry_price) / entry_price * 100

    return result


def run_signal_backtest(signals: List[Dict], tp_pct: float, sl_pct: float,
                        max_hold: int, trail_config: Dict = None) -> Dict:
    """Run backtest on a set of signals"""
    if not signals:
        return {'trades': 0, 'expectancy': 0}

    trades = []
    exit_types = defaultdict(int)
    tp_by_day = defaultdict(int)

    trail_enabled = trail_config.get('enabled', False) if trail_config else False
    trail_activation = trail_config.get('activation', 2.0) if trail_config else 2.0
    trail_lock = trail_config.get('lock', 60) if trail_config else 60

    for signal in signals:
        result = simulate_trade(signal, tp_pct, sl_pct, max_hold,
                                trail_enabled, trail_activation, trail_lock)
        trades.append({**signal, **result})
        exit_types[result['exit_type']] += 1
        if result['exit_type'] == 'TAKE_PROFIT':
            tp_by_day[result['exit_day']] += 1

    wins = [t for t in trades if t['exit_return'] > 0]
    losses = [t for t in trades if t['exit_return'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
    avg_hold = statistics.mean([t['exit_day'] for t in trades])

    # TP hit by day
    tp_cum = {}
    running = 0
    for day in range(1, max_hold + 1):
        running += tp_by_day.get(day, 0)
        tp_cum[day] = running / len(trades) * 100

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'avg_hold': avg_hold,
        'tp_rate': exit_types['TAKE_PROFIT'] / len(trades) * 100,
        'sl_rate': exit_types['STOP_LOSS'] / len(trades) * 100,
        'max_hold_rate': exit_types['MAX_HOLD'] / len(trades) * 100,
        'tp_by_day_5': tp_cum.get(5, 0),
        'tp_by_day_7': tp_cum.get(7, 0),
    }


# Signal filter functions
def signal_current(s: Dict) -> bool:
    """Current Stock-D filter"""
    return s['dip_size'] >= 2.0 and s['bounce_day1'] >= 1.0


def signal_deep_dip(s: Dict) -> bool:
    """Deep Dip: Dip ≥ 5%"""
    return s['dip_size'] >= 5.0 and s['bounce_day1'] >= 1.0


def signal_deep_dip_volume(s: Dict) -> bool:
    """Deep Dip + Volume Spike"""
    return s['dip_size'] >= 4.0 and s['volume_ratio'] >= 1.5 and s['bounce_day1'] >= 1.0


def signal_rsi_extreme(s: Dict) -> bool:
    """RSI Extreme (< 30)"""
    return s['rsi'] <= 30 and s['bounce_day1'] >= 1.0


def signal_rsi_extreme_bounce(s: Dict) -> bool:
    """RSI Extreme + Strong Bounce"""
    return s['rsi'] <= 30 and s['bounce_day1'] >= 1.5


def signal_gap_recovery(s: Dict) -> bool:
    """Gap Down Recovery"""
    return s['gap_pct'] <= -2.0 and s['bounce_day1'] >= 1.0


def signal_support_bounce(s: Dict) -> bool:
    """Near Support Bounce"""
    return s['near_support_pct'] <= 2.0 and s['dip_size'] >= 2.0 and s['bounce_day1'] >= 1.0


def signal_high_vix(s: Dict) -> bool:
    """High VIX environment"""
    return s['vix_level'] >= 25 and s['dip_size'] >= 2.0 and s['bounce_day1'] >= 1.0


def signal_strong_bounce(s: Dict) -> bool:
    """Strong bounce confirmation"""
    return s['dip_size'] >= 2.0 and s['bounce_day1'] >= 2.0


def signal_combo_1(s: Dict) -> bool:
    """Combo 1: Deep Dip + Low RSI"""
    return s['dip_size'] >= 4.0 and s['rsi'] <= 35 and s['bounce_day1'] >= 1.5


def signal_combo_2(s: Dict) -> bool:
    """Combo 2: Volume + Gap Down"""
    return s['volume_ratio'] >= 1.5 and s['gap_pct'] <= -1.5 and s['bounce_day1'] >= 1.0


def signal_combo_3(s: Dict) -> bool:
    """Combo 3: Multi-factor score ≥ 4"""
    score = 0
    if s['dip_size'] >= 4.0:
        score += 2
    if s['rsi'] <= 35:
        score += 2
    if s['volume_ratio'] >= 1.5:
        score += 1
    if s['bounce_day1'] >= 1.5:
        score += 1
    return score >= 4


def signal_combo_4(s: Dict) -> bool:
    """Combo 4: Deep + RSI + Volume"""
    return s['dip_size'] >= 4.0 and s['rsi'] <= 40 and s['volume_ratio'] >= 1.3 and s['bounce_day1'] >= 1.0


def signal_monday_dip(s: Dict) -> bool:
    """Monday dip bounce"""
    return s['day_of_week'] == 0 and s['dip_size'] >= 2.5 and s['bounce_day1'] >= 1.0


def signal_high_recovery(s: Dict) -> bool:
    """High intraday recovery"""
    return s['intraday_recovery'] >= 70 and s['dip_size'] >= 2.0


SIGNAL_FUNCS = {
    'Current (Stock-D)': signal_current,
    'A: Deep Dip (≥5%)': signal_deep_dip,
    'B: Deep Dip + Volume': signal_deep_dip_volume,
    'C: RSI Extreme (≤30)': signal_rsi_extreme,
    'D: RSI + Strong Bounce': signal_rsi_extreme_bounce,
    'E: Gap Down Recovery': signal_gap_recovery,
    'F: Support Bounce': signal_support_bounce,
    'G: High VIX': signal_high_vix,
    'H: Strong Bounce (≥2%)': signal_strong_bounce,
    'I: Deep + Low RSI': signal_combo_1,
    'J: Volume + Gap': signal_combo_2,
    'K: Multi-factor': signal_combo_3,
    'L: Deep+RSI+Vol': signal_combo_4,
    'M: Monday Dip': signal_monday_dip,
    'N: High Recovery': signal_high_recovery,
}


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 85)
    print("FAST BOUNCE STRATEGY DISCOVERY")
    print("=" * 85)
    print("Target: TP hit ≥40% within 7 days, E[R] ≥+0.7%, Avg hold ≤7 days")
    print()

    # Date range
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

    print(f"Period: {start_date} to {end_date}")
    print(f"Stocks: {len(ALL_SYMBOLS)}")
    print()

    # Get VIX data
    print("Loading VIX data...")
    vix_data = get_vix_data(start_date, end_date)
    print(f"VIX data points: {len(vix_data)}")
    print()

    # Get all signals
    print("Collecting detailed signals...")
    all_signals = get_all_signals_detailed(start_date, end_date, vix_data)
    print(f"Total signals: {len(all_signals)}")
    print()

    if not all_signals:
        print("No signals found!")
        return

    # ============================================================
    # SECTION A: FAST vs SLOW BOUNCE ANALYSIS
    # ============================================================
    print("=" * 85)
    print("A. FAST vs SLOW BOUNCE ANALYSIS")
    print("=" * 85)
    print()

    analysis = analyze_fast_vs_slow(all_signals)

    for group_key in ['fast', 'medium', 'slow']:
        stats = analysis[group_key]
        if not stats:
            continue
        print(f"{stats['name']}:")
        print(f"  ├── Count: {stats['count']} ({stats['pct']:.1f}%)")
        print(f"  ├── Avg dip size: -{stats['avg_dip']:.2f}%")
        print(f"  ├── Avg RSI: {stats['avg_rsi']:.1f}")
        print(f"  ├── Avg volume ratio: {stats['avg_volume_ratio']:.2f}x")
        print(f"  ├── Avg bounce Day 1: +{stats['avg_bounce_d1']:.2f}%")
        print(f"  ├── Avg gap: {stats['avg_gap']:+.2f}%")
        print(f"  ├── Avg VIX: {stats['avg_vix']:.1f}")
        print(f"  ├── Avg near support: {stats['avg_near_support']:.1f}%")
        print(f"  └── Avg intraday recovery: {stats['avg_intraday_recovery']:.1f}%")
        print()

    # Key differences
    if analysis['fast'] and analysis['slow']:
        f = analysis['fast']
        s = analysis['slow']
        print("KEY DIFFERENCES (Fast vs Slow):")
        print(f"  Dip size: -{f['avg_dip']:.2f}% vs -{s['avg_dip']:.2f}% (diff: {f['avg_dip'] - s['avg_dip']:+.2f}%)")
        print(f"  RSI: {f['avg_rsi']:.1f} vs {s['avg_rsi']:.1f} (diff: {f['avg_rsi'] - s['avg_rsi']:+.1f})")
        print(f"  Volume ratio: {f['avg_volume_ratio']:.2f}x vs {s['avg_volume_ratio']:.2f}x")
        print(f"  Bounce D1: +{f['avg_bounce_d1']:.2f}% vs +{s['avg_bounce_d1']:.2f}%")
        print(f"  VIX: {f['avg_vix']:.1f} vs {s['avg_vix']:.1f}")
        print()

    # ============================================================
    # SECTION B: HYPOTHESIS TESTING
    # ============================================================
    print("=" * 85)
    print("B. HYPOTHESIS TESTING (What predicts fast bounce?)")
    print("=" * 85)
    print()

    hypotheses = [
        (lambda s: s['dip_size'] >= 5.0, "H1: Dip ≥ 5%"),
        (lambda s: s['dip_size'] >= 4.0, "H1b: Dip ≥ 4%"),
        (lambda s: s['volume_ratio'] >= 2.0, "H2: Volume ≥ 2x"),
        (lambda s: s['volume_ratio'] >= 1.5, "H2b: Volume ≥ 1.5x"),
        (lambda s: s['rsi'] <= 30, "H3: RSI ≤ 30"),
        (lambda s: s['rsi'] <= 35, "H3b: RSI ≤ 35"),
        (lambda s: s['vix_level'] >= 25, "H5: VIX ≥ 25"),
        (lambda s: s['vix_level'] >= 20, "H5b: VIX ≥ 20"),
        (lambda s: s['bounce_day1'] >= 2.0, "H6: Bounce D1 ≥ 2%"),
        (lambda s: s['bounce_day1'] >= 1.5, "H6b: Bounce D1 ≥ 1.5%"),
        (lambda s: s['gap_pct'] <= -2.0, "H7: Gap ≤ -2%"),
        (lambda s: s['gap_pct'] <= -1.0, "H7b: Gap ≤ -1%"),
        (lambda s: s['day_of_week'] == 0, "H8: Monday"),
        (lambda s: s['day_of_week'] in [0, 1], "H8b: Mon/Tue"),
        (lambda s: s['near_support_pct'] <= 2.0, "H10: Near support"),
        (lambda s: s['intraday_recovery'] >= 70, "H11: High recovery"),
    ]

    print(f"{'Hypothesis':<25} {'Match':<8} {'Fast%':<10} {'Non-Fast%':<12} {'Lift':<8}")
    print("-" * 70)

    hypothesis_results = []
    for cond_func, cond_name in hypotheses:
        result = test_hypothesis(all_signals, cond_func, cond_name)
        hypothesis_results.append(result)
        print(f"{result['condition']:<25} {result['matching_count']:<8} "
              f"{result['matching_fast_rate']:.1f}%{'':<5} "
              f"{result['non_matching_fast_rate']:.1f}%{'':<7} "
              f"{result['lift']:+.1f}%")

    print()

    # Top predictors
    sorted_hyp = sorted(hypothesis_results, key=lambda x: x['lift'], reverse=True)
    print("TOP 3 FAST BOUNCE PREDICTORS:")
    for i, h in enumerate(sorted_hyp[:3]):
        print(f"  {i+1}. {h['condition']}: +{h['lift']:.1f}% lift (Fast rate: {h['matching_fast_rate']:.1f}%)")
    print()

    # ============================================================
    # SECTION C: NEW SIGNAL BACKTESTS
    # ============================================================
    print("=" * 85)
    print("C. NEW SIGNAL BACKTESTS")
    print("=" * 85)
    print()

    # Test with TP 3% (target for fast bounce), SL 2.5%, Max 7 days
    tp_pct = 3.0
    sl_pct = 2.5
    max_hold = 7

    print(f"Testing with TP={tp_pct}%, SL={sl_pct}%, Max Hold={max_hold} days")
    print()

    print(f"{'Signal':<25} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'TP≤5d':<8} {'TP≤7d':<8} {'AvgHold':<8}")
    print("-" * 85)

    signal_results = {}
    for name, func in SIGNAL_FUNCS.items():
        filtered = [s for s in all_signals if func(s)]
        if len(filtered) < 20:
            continue

        result = run_signal_backtest(filtered, tp_pct, sl_pct, max_hold)
        signal_results[name] = result

        marker = " ← current" if name == 'Current (Stock-D)' else ""
        print(f"{name:<25} {result['trades']:<8} {result['win_rate']:.1f}%{'':<3} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['tp_by_day_5']:.1f}%{'':<3} "
              f"{result['tp_by_day_7']:.1f}%{'':<3} {result['avg_hold']:.1f}d{marker}")

    print()

    # Best signal by TP hit rate within 7 days
    best_tp7 = max(signal_results.keys(), key=lambda k: signal_results[k]['tp_by_day_7'])
    print(f"Best by TP≤7d: {best_tp7} ({signal_results[best_tp7]['tp_by_day_7']:.1f}%)")

    # Best by E[R]
    best_er = max(signal_results.keys(), key=lambda k: signal_results[k]['expectancy'])
    print(f"Best by E[R]: {best_er} ({signal_results[best_er]['expectancy']:+.3f}%)")
    print()

    # ============================================================
    # SECTION D: EXIT STRATEGY OPTIMIZATION
    # ============================================================
    print("=" * 85)
    print("D. EXIT STRATEGY OPTIMIZATION (for best signal)")
    print("=" * 85)
    print()

    # Use best signal
    best_signal_name = best_er
    best_signal_func = SIGNAL_FUNCS[best_signal_name]
    best_signals = [s for s in all_signals if best_signal_func(s)]

    print(f"Optimizing exit for: {best_signal_name} ({len(best_signals)} trades)")
    print()

    exit_configs = [
        (2.5, 2.0, 5, {'enabled': False}, 'Fast-A (2.5/2.0/5d)'),
        (3.0, 2.0, 5, {'enabled': False}, 'Fast-B (3.0/2.0/5d)'),
        (3.0, 2.5, 7, {'enabled': False}, 'Fast-C (3.0/2.5/7d)'),
        (4.0, 2.5, 7, {'enabled': False}, 'Fast-D (4.0/2.5/7d)'),
        (3.0, 2.0, 7, {'enabled': True, 'activation': 2.0, 'lock': 60}, 'Fast-E (3.0/2.0/7d+Trail)'),
        (4.0, 2.0, 7, {'enabled': True, 'activation': 1.5, 'lock': 70}, 'Fast-F (4.0/2.0/7d+Trail)'),
        (3.5, 2.5, 10, {'enabled': False}, 'Fast-G (3.5/2.5/10d)'),
    ]

    print(f"{'Exit Config':<25} {'Win%':<8} {'E[R]':<10} {'TP%':<8} {'AvgHold':<8}")
    print("-" * 65)

    exit_results = {}
    for tp, sl, hold, trail, name in exit_configs:
        result = run_signal_backtest(best_signals, tp, sl, hold, trail)
        exit_results[name] = result

        print(f"{name:<25} {result['win_rate']:.1f}%{'':<3} {result['expectancy']:+.3f}%{'':<4} "
              f"{result['tp_rate']:.1f}%{'':<3} {result['avg_hold']:.1f}d")

    print()

    best_exit = max(exit_results.keys(), key=lambda k: exit_results[k]['expectancy'])
    print(f"Best Exit Config: {best_exit} (E[R]: {exit_results[best_exit]['expectancy']:+.3f}%)")
    print()

    # ============================================================
    # SECTION E: COMPARE NEW vs CURRENT
    # ============================================================
    print("=" * 85)
    print("E. COMPARISON: NEW FAST BOUNCE vs CURRENT (v5.6)")
    print("=" * 85)
    print()

    # Current v5.6 config
    current_signals = [s for s in all_signals if signal_current(s)]
    v56_result = run_signal_backtest(current_signals, 11.0, 3.5, 30, {'enabled': False})

    # Best new config
    best_new_result = exit_results[best_exit]

    # Parse best exit config
    for tp, sl, hold, trail, name in exit_configs:
        if name == best_exit:
            best_tp, best_sl, best_hold = tp, sl, hold
            break

    v56_e = f"{v56_result['expectancy']:+.3f}%"
    new_e = f"{best_new_result['expectancy']:+.3f}%"
    v56_wr = f"{v56_result['win_rate']:.1f}%"
    new_wr = f"{best_new_result['win_rate']:.1f}%"
    v56_tp_str = f"{v56_result['tp_rate']:.1f}%"
    new_tp_str = f"{best_new_result['tp_rate']:.1f}%"
    v56_hold = f"{v56_result['avg_hold']:.1f} days"
    new_hold_str = f"{best_new_result['avg_hold']:.1f} days"
    best_tp_str = f"{best_tp}%"
    best_sl_str = f"{best_sl}%"
    best_hold_str = f"{best_hold} days"

    print(f"{'Metric':<25} {'v5.6 (Current)':<20} {'New Fast Bounce':<20}")
    print("-" * 70)
    print(f"{'Signal':<25} {'Stock-D':<20} {best_signal_name:<20}")
    print(f"{'TP':<25} {'5.0x ATR (~11%)':<20} {best_tp_str:<20}")
    print(f"{'SL':<25} {'1.5x ATR (~3.5%)':<20} {best_sl_str:<20}")
    print(f"{'Max Hold':<25} {'30 days':<20} {best_hold_str:<20}")
    print("-" * 70)
    print(f"{'Trades':<25} {v56_result['trades']:<20} {best_new_result['trades']:<20}")
    print(f"{'E[R]':<25} {v56_e:<20} {new_e:<20}")
    print(f"{'Win Rate':<25} {v56_wr:<20} {new_wr:<20}")
    print(f"{'TP Hit Rate':<25} {v56_tp_str:<20} {new_tp_str:<20}")
    print(f"{'Avg Hold':<25} {v56_hold:<20} {new_hold_str:<20}")
    print()

    # Annualized comparison
    print("ANNUALIZED COMPARISON (assuming continuous trading):")
    v56_trades_year = 365 / v56_result['avg_hold'] * (v56_result['trades'] / 730 * 365)
    new_trades_year = 365 / best_new_result['avg_hold'] * (best_new_result['trades'] / 730 * 365)

    v56_annual = v56_result['expectancy'] * v56_trades_year / 100 * 100  # Simplified
    new_annual = best_new_result['expectancy'] * new_trades_year / 100 * 100

    v56_ty_str = f"~{v56_trades_year:.0f}"
    new_ty_str = f"~{new_trades_year:.0f}"
    print(f"{'Est. Trades/Year':<25} {v56_ty_str:<20} {new_ty_str:<20}")
    print(f"{'Capital Turnover':<25} {'Low (long holds)':<20} {'High (fast turns)':<20}")
    print()

    # ============================================================
    # SECTION F: SUCCESS CRITERIA
    # ============================================================
    print("=" * 85)
    print("F. SUCCESS CRITERIA CHECK")
    print("=" * 85)
    print()

    criteria = [
        ('TP hit ≥ 40% within 7 days', best_new_result['tp_by_day_7'] >= 40,
         f"{best_new_result['tp_by_day_7']:.1f}%"),
        ('Avg hold ≤ 7 days', best_new_result['avg_hold'] <= 7,
         f"{best_new_result['avg_hold']:.1f} days"),
        ('E[R] ≥ +0.7%', best_new_result['expectancy'] >= 0.7,
         f"{best_new_result['expectancy']:+.3f}%"),
        ('Win rate ≥ 55%', best_new_result['win_rate'] >= 55,
         f"{best_new_result['win_rate']:.1f}%"),
        ('More trades than current', best_new_result['trades'] >= v56_result['trades'],
         f"{best_new_result['trades']} vs {v56_result['trades']}"),
    ]

    passed = 0
    for name, result, detail in criteria:
        status = '✅' if result else '❌'
        print(f"  {status} {name}: {detail}")
        if result:
            passed += 1

    print()
    print(f"Passed: {passed}/{len(criteria)}")
    print()

    # ============================================================
    # SECTION G: FINAL RECOMMENDATION
    # ============================================================
    print("=" * 85)
    print("G. FINAL RECOMMENDATION")
    print("=" * 85)
    print()

    # Extract top predictors
    top_predictors = [h['condition'] for h in sorted_hyp[:3]]

    print("┌" + "─" * 75 + "┐")
    print("│  FAST BOUNCE STRATEGY DISCOVERY" + " " * 42 + "│")
    print("├" + "─" * 75 + "┤")
    print("│" + " " * 75 + "│")
    print(f"│  FAST BOUNCE PREDICTORS (Top 3):" + " " * 41 + "│")
    for i, p in enumerate(top_predictors):
        print(f"│  {i+1}. {p:<69}│")
    print("│" + " " * 75 + "│")
    print(f"│  BEST NEW SIGNAL:" + " " * 57 + "│")
    print(f"│  ├── Name: {best_signal_name:<62}│")
    print(f"│  ├── Trades: {best_new_result['trades']:<61}│")
    print(f"│  └── TP hit ≤7d: {best_new_result['tp_by_day_7']:.1f}%" + " " * 55 + "│")
    print("│" + " " * 75 + "│")
    print(f"│  OPTIMAL EXIT:" + " " * 60 + "│")
    print(f"│  ├── TP: {best_tp}%" + " " * 62 + "│")
    print(f"│  ├── SL: {best_sl}%" + " " * 62 + "│")
    print(f"│  └── Max Hold: {best_hold} days" + " " * 54 + "│")
    print("│" + " " * 75 + "│")
    print(f"│  PERFORMANCE:" + " " * 61 + "│")
    print(f"│  ├── E[R]: {best_new_result['expectancy']:+.3f}%" + " " * 55 + "│")
    print(f"│  ├── Win Rate: {best_new_result['win_rate']:.1f}%" + " " * 52 + "│")
    print(f"│  ├── TP Hit: {best_new_result['tp_rate']:.1f}%" + " " * 54 + "│")
    print(f"│  └── Avg Hold: {best_new_result['avg_hold']:.1f} days" + " " * 50 + "│")
    print("│" + " " * 75 + "│")
    print(f"│  vs CURRENT (v5.6):" + " " * 55 + "│")
    print(f"│  ├── E[R]: {best_new_result['expectancy']:+.3f}% vs {v56_result['expectancy']:+.3f}%" + " " * 35 + "│")
    print(f"│  ├── Avg Hold: {best_new_result['avg_hold']:.1f}d vs {v56_result['avg_hold']:.1f}d" + " " * 38 + "│")
    print(f"│  └── Trades: {best_new_result['trades']} vs {v56_result['trades']}" + " " * 43 + "│")
    print("│" + " " * 75 + "│")

    # Decision
    if passed >= 4 and best_new_result['expectancy'] >= 0.5:
        decision = "IMPLEMENT NEW FAST BOUNCE"
        confidence = 75
    elif passed >= 3 and best_new_result['expectancy'] > 0:
        decision = "CONSIDER HYBRID APPROACH"
        confidence = 60
    else:
        decision = "KEEP CURRENT v5.6"
        confidence = 70

    print(f"│  RECOMMENDATION: {decision:<56}│")
    print(f"│  CONFIDENCE: {confidence}%" + " " * 59 + "│")
    print("└" + "─" * 75 + "┘")
    print()

    # Config output
    if "IMPLEMENT" in decision or "HYBRID" in decision:
        print("=" * 85)
        print("H. FAST BOUNCE CONFIGURATION")
        print("=" * 85)
        print()
        print("```python")
        print("FAST_BOUNCE_CONFIG = {")
        print(f"    # Entry Signal: {best_signal_name}")
        print("    'entry': {")
        if 'Deep' in best_signal_name:
            print("        'min_dip': 4.0,  # Deep dip")
        if 'RSI' in best_signal_name or 'Low RSI' in best_signal_name:
            print("        'max_rsi': 35,  # Low RSI")
        if 'Volume' in best_signal_name or 'Vol' in best_signal_name:
            print("        'min_volume_ratio': 1.3,  # Volume spike")
        print("        'min_bounce': 1.0,  # Bounce confirmation")
        print("    },")
        print()
        print("    # Exit")
        print(f"    'tp_pct': {best_tp},")
        print(f"    'sl_pct': {best_sl},")
        print(f"    'max_hold': {best_hold},")
        print("    'trail_enabled': False,")
        print("}")
        print("```")


if __name__ == '__main__':
    main()
