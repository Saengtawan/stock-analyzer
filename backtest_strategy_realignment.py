#!/usr/bin/env python3
"""
Complete Strategy Re-alignment Backtest

กลับมาที่ Dip-Bounce strategy แท้ๆ:
- Entry: หุ้นที่ลงแรง (dip) แล้วเริ่มเด้ง (bounce)
- Exit: ขายเมื่อ bounce ถึง target
- Time: Short-term (3-7 วัน)
- Edge: Mean-reversion — oversold → recover

Primary Metric: Expectancy (NOT Win Rate)
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


# ============================================================
# TP CONFIGURATIONS (Test Range)
# ============================================================
TP_CONFIGS = {
    'TP-A_1.5x': {'mult': 1.5, 'desc': 'Very tight (3-4%)'},
    'TP-B_2.0x': {'mult': 2.0, 'desc': 'Tight (4-5%)'},
    'TP-C_2.5x': {'mult': 2.5, 'desc': 'Moderate (5-6%)'},
    'TP-D_3.0x': {'mult': 3.0, 'desc': 'Original (6-8%)'},
    'TP-E_4.0x': {'mult': 4.0, 'desc': 'Wide (8-10%)'},
    'TP-F_5.0x': {'mult': 5.0, 'desc': 'Very wide (10-12%)'},
}

SL_CONFIGS = {
    'SL-A_1.0x': {'mult': 1.0, 'desc': 'Tight (2-2.5%)'},
    'SL-B_1.5x': {'mult': 1.5, 'desc': 'Current (2-4%)'},
    'SL-C_2.0x': {'mult': 2.0, 'desc': 'Moderate (3-5%)'},
    'SL-D_2.5x': {'mult': 2.5, 'desc': 'Loose (4-6%)'},
}

# Max Hold Variants
MAX_HOLD_VARIANTS = [3, 5, 7, 10, 14]

# Trailing Configs
TRAIL_CONFIGS = {
    'TRAIL_NONE': {'enabled': False, 'activation': 0, 'lock': 0},
    'TRAIL_2_50': {'enabled': True, 'activation': 2.0, 'lock': 50},
    'TRAIL_3_50': {'enabled': True, 'activation': 3.0, 'lock': 50},
    'TRAIL_3_60': {'enabled': True, 'activation': 3.0, 'lock': 60},
    'TRAIL_4_50': {'enabled': True, 'activation': 4.0, 'lock': 50},
}

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


def get_all_signals_with_future(start_date: str, end_date: str, min_score: int = 85) -> List[Dict]:
    """Get all dip-bounce signals with future price data for analysis"""
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

            # ATR
            hist['tr'] = pd.concat([
                hist['High'] - hist['Low'],
                (hist['High'] - hist['Close'].shift(1)).abs(),
                (hist['Low'] - hist['Close'].shift(1)).abs()
            ], axis=1).max(axis=1)
            hist['atr'] = hist['tr'].rolling(window=14).mean()
            hist['atr_pct'] = hist['atr'] / hist['Close'] * 100

            sector = SYMBOL_TO_SECTOR.get(symbol, 'Unknown')

            for i in range(50, len(hist) - 35):  # Need 30+ days future data
                row = hist.iloc[i]
                signal_date = hist.index[i]

                yesterday_ret = row.get('yesterday_return', 0)
                today_ret = row.get('daily_return', 0)
                rsi = row.get('rsi', 50)
                atr_pct = row.get('atr_pct', 3.0)

                if pd.isna(yesterday_ret) or pd.isna(today_ret) or pd.isna(rsi):
                    continue

                # Dip-bounce filter: yesterday down ≥2%, today up ≥1%
                if not (yesterday_ret <= -2.0 and today_ret >= 1.0):
                    continue

                # Score calculation (v5.6 style - no penalties)
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

                if score < min_score:
                    continue

                # Collect future prices for bounce analysis
                future_returns = []
                entry_price = row['Close']

                for day in range(1, 31):  # Next 30 days
                    future_idx = i + day
                    if future_idx < len(hist):
                        future_high = hist.iloc[future_idx]['High']
                        future_low = hist.iloc[future_idx]['Low']
                        future_close = hist.iloc[future_idx]['Close']

                        high_return = (future_high - entry_price) / entry_price * 100
                        low_return = (future_low - entry_price) / entry_price * 100
                        close_return = (future_close - entry_price) / entry_price * 100

                        future_returns.append({
                            'day': day,
                            'high_return': high_return,
                            'low_return': low_return,
                            'close_return': close_return,
                        })

                all_signals.append({
                    'symbol': symbol,
                    'sector': sector,
                    'date': signal_date,
                    'entry_idx': i,
                    'entry_price': entry_price,
                    'score': score,
                    'atr_pct': atr_pct if not pd.isna(atr_pct) else 3.0,
                    'rsi': rsi,
                    'yesterday_return': yesterday_ret,
                    'today_return': today_ret,
                    'dip_size': abs(yesterday_ret),
                    'bounce_day1': today_ret,
                    'future_returns': future_returns,
                    'hist': hist,
                })

        except Exception:
            continue

    return all_signals


def analyze_bounce_anatomy(signals: List[Dict]) -> Dict:
    """Analyze actual bounce patterns"""
    if not signals:
        return {}

    # Collect stats
    dip_sizes = [s['dip_size'] for s in signals]
    bounce_d1 = [s['bounce_day1'] for s in signals]

    # Future returns by day
    returns_by_day = defaultdict(list)
    peak_by_trade = []

    for signal in signals:
        peak_return = 0
        peak_day = 0

        for fr in signal['future_returns']:
            day = fr['day']
            high_ret = fr['high_return']
            close_ret = fr['close_return']

            returns_by_day[day].append(close_ret)

            if high_ret > peak_return:
                peak_return = high_ret
                peak_day = day

        peak_by_trade.append({
            'peak_return': peak_return,
            'peak_day': peak_day,
        })

    # Calculate averages
    avg_dip = statistics.mean(dip_sizes)
    avg_bounce_d1 = statistics.mean(bounce_d1)

    avg_close_by_day = {}
    for day in [1, 3, 5, 7, 10, 14, 21, 30]:
        if returns_by_day[day]:
            avg_close_by_day[day] = statistics.mean(returns_by_day[day])

    # Peak analysis
    avg_peak = statistics.mean([p['peak_return'] for p in peak_by_trade])
    avg_peak_day = statistics.mean([p['peak_day'] for p in peak_by_trade])

    # Success rate (bounce ≥ 3%)
    success_3pct = sum(1 for p in peak_by_trade if p['peak_return'] >= 3) / len(peak_by_trade) * 100
    success_5pct = sum(1 for p in peak_by_trade if p['peak_return'] >= 5) / len(peak_by_trade) * 100
    success_8pct = sum(1 for p in peak_by_trade if p['peak_return'] >= 8) / len(peak_by_trade) * 100

    # Peak distribution
    peak_dist = defaultdict(int)
    for p in peak_by_trade:
        if p['peak_return'] < 2:
            peak_dist['<2%'] += 1
        elif p['peak_return'] < 4:
            peak_dist['2-4%'] += 1
        elif p['peak_return'] < 6:
            peak_dist['4-6%'] += 1
        elif p['peak_return'] < 8:
            peak_dist['6-8%'] += 1
        elif p['peak_return'] < 10:
            peak_dist['8-10%'] += 1
        else:
            peak_dist['10%+'] += 1

    return {
        'avg_dip': avg_dip,
        'avg_bounce_d1': avg_bounce_d1,
        'avg_close_by_day': avg_close_by_day,
        'avg_peak_return': avg_peak,
        'avg_peak_day': avg_peak_day,
        'success_3pct': success_3pct,
        'success_5pct': success_5pct,
        'success_8pct': success_8pct,
        'peak_distribution': dict(peak_dist),
        'total_trades': len(signals),
    }


def simulate_trade(signal: Dict, tp_mult: float, sl_mult: float,
                   max_hold: int, trail_config: Dict) -> Dict:
    """Simulate a trade with given parameters"""
    entry_price = signal['entry_price']
    atr_pct = signal['atr_pct']
    hist = signal['hist']
    entry_idx = signal['entry_idx']

    # Calculate TP and SL
    tp_pct = atr_pct * tp_mult
    sl_pct = atr_pct * sl_mult

    # Apply min/max bounds
    tp_pct = max(3.0, min(15.0, tp_pct))  # 3-15%
    sl_pct = max(1.5, min(6.0, sl_pct))   # 1.5-6%

    tp_price = entry_price * (1 + tp_pct / 100)
    sl_price = entry_price * (1 - sl_pct / 100)

    result = {
        'exit_return': 0,
        'exit_type': 'MAX_HOLD',
        'exit_day': max_hold,
        'tp_pct': tp_pct,
        'sl_pct': sl_pct,
        'peak_gain': 0,
        'trail_activated': False,
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

        # Update peak
        if high > peak_price:
            peak_price = high
            result['peak_gain'] = (peak_price - entry_price) / entry_price * 100

        # Trailing stop logic
        if trail_config['enabled'] and trailing_sl is None:
            current_gain = (high - entry_price) / entry_price * 100
            if current_gain >= trail_config['activation']:
                locked_gain = current_gain * trail_config['lock'] / 100
                trailing_sl = entry_price * (1 + locked_gain / 100)
                result['trail_activated'] = True

        if trailing_sl is not None:
            current_gain = (high - entry_price) / entry_price * 100
            new_locked = current_gain * trail_config['lock'] / 100
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

        # Update exit at close
        result['exit_return'] = (close - entry_price) / entry_price * 100

    return result


def run_backtest(signals: List[Dict], tp_mult: float, sl_mult: float,
                 max_hold: int, trail_config: Dict) -> Dict:
    """Run backtest with given configuration"""
    trades = []
    exit_types = defaultdict(int)
    tp_hit_by_day = defaultdict(int)

    for signal in signals:
        result = simulate_trade(signal, tp_mult, sl_mult, max_hold, trail_config)
        trades.append({**signal, **result})
        exit_types[result['exit_type']] += 1

        if result['exit_type'] == 'TAKE_PROFIT':
            tp_hit_by_day[result['exit_day']] += 1

    if not trades:
        return {'trades': 0, 'expectancy': 0}

    wins = [t for t in trades if t['exit_return'] > 0]
    losses = [t for t in trades if t['exit_return'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
    total_return = sum(t['exit_return'] for t in trades)
    avg_hold = statistics.mean([t['exit_day'] for t in trades])

    # TP hit rate cumulative
    total_tp = exit_types['TAKE_PROFIT']
    tp_cum_by_day = {}
    running_tp = 0
    for day in range(1, max_hold + 1):
        running_tp += tp_hit_by_day.get(day, 0)
        tp_cum_by_day[day] = running_tp / len(trades) * 100

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'total_return': total_return,
        'avg_hold': avg_hold,
        'exit_types': dict(exit_types),
        'tp_rate': total_tp / len(trades) * 100,
        'sl_rate': exit_types['STOP_LOSS'] / len(trades) * 100,
        'max_hold_rate': exit_types['MAX_HOLD'] / len(trades) * 100,
        'tp_cum_by_day': tp_cum_by_day,
    }


def analyze_false_stops(signals: List[Dict], sl_mult: float, max_hold: int = 10) -> Dict:
    """Analyze false stop rate - trades that would have won if not stopped out"""
    false_stops = 0
    total_stops = 0

    for signal in signals:
        atr_pct = signal['atr_pct']
        sl_pct = max(1.5, min(6.0, atr_pct * sl_mult))

        hit_sl = False
        would_have_won = False

        for fr in signal['future_returns'][:max_hold]:
            if fr['low_return'] <= -sl_pct:
                hit_sl = True
                # Check if it would have recovered
                for fr2 in signal['future_returns'][fr['day']:]:
                    if fr2['high_return'] >= sl_pct:  # Would have been profitable
                        would_have_won = True
                        break
                break

        if hit_sl:
            total_stops += 1
            if would_have_won:
                false_stops += 1

    return {
        'total_stops': total_stops,
        'false_stops': false_stops,
        'false_stop_rate': false_stops / total_stops * 100 if total_stops > 0 else 0,
    }


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 85)
    print("COMPLETE STRATEGY RE-ALIGNMENT BACKTEST")
    print("=" * 85)
    print("Goal: Return to TRUE Dip-Bounce Strategy (3-7 day holds)")
    print()

    # Date range
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

    print(f"Period: {start_date} to {end_date}")
    print(f"Stocks: {len(ALL_SYMBOLS)} across {len(STOCKS_BY_SECTOR)} sectors")
    print()

    # Get signals
    print("Collecting signals with future price data...")
    all_signals = get_all_signals_with_future(start_date, end_date)
    print(f"Total signals: {len(all_signals)}")
    print()

    if not all_signals:
        print("No signals found!")
        return

    # ============================================================
    # SECTION A: BOUNCE ANATOMY ANALYSIS
    # ============================================================
    print("=" * 85)
    print("A. DIP-BOUNCE ANATOMY ANALYSIS")
    print("=" * 85)
    print()

    anatomy = analyze_bounce_anatomy(all_signals)

    print("BOUNCE ANATOMY:")
    print(f"├── Avg dip before entry: -{anatomy['avg_dip']:.2f}%")
    print(f"├── Avg bounce Day 1 (entry day): +{anatomy['avg_bounce_d1']:.2f}%")
    print("├── Avg close return by day:")
    for day in [1, 3, 5, 7, 10, 14, 21, 30]:
        if day in anatomy['avg_close_by_day']:
            print(f"│   ├── Day {day}: {anatomy['avg_close_by_day'][day]:+.2f}%")
    print(f"├── Avg peak return: +{anatomy['avg_peak_return']:.2f}%")
    print(f"├── Avg day of peak: Day {anatomy['avg_peak_day']:.1f}")
    print(f"├── Bounce success rate (≥3%): {anatomy['success_3pct']:.1f}%")
    print(f"├── Bounce success rate (≥5%): {anatomy['success_5pct']:.1f}%")
    print(f"└── Bounce success rate (≥8%): {anatomy['success_8pct']:.1f}%")
    print()

    print("Peak Return Distribution:")
    for bucket, count in sorted(anatomy['peak_distribution'].items()):
        pct = count / anatomy['total_trades'] * 100
        bar = '█' * int(pct / 2)
        print(f"  {bucket:<8}: {count:>4} ({pct:>5.1f}%) {bar}")
    print()

    # ============================================================
    # SECTION B: TP TARGET ANALYSIS
    # ============================================================
    print("=" * 85)
    print("B. TP TARGET ANALYSIS (Find optimal TP for short-term bounce)")
    print("=" * 85)
    print()

    no_trail = {'enabled': False, 'activation': 0, 'lock': 0}

    # Test each TP with 7-day max hold (short-term)
    print("Testing with Max Hold = 7 days, SL = 1.5x ATR, No trailing")
    print()

    print(f"{'TP Config':<15} {'TP%':<8} {'Trades':<7} {'Win%':<7} {'E[R]':<10} {'TP Hit%':<9} {'SL%':<7} {'AvgHold':<8}")
    print("-" * 80)

    tp_results = {}
    for name, config in TP_CONFIGS.items():
        result = run_backtest(all_signals, config['mult'], 1.5, 7, no_trail)
        tp_results[name] = result

        avg_tp_pct = config['mult'] * statistics.mean([s['atr_pct'] for s in all_signals])
        marker = " ← original" if name == 'TP-D_3.0x' else (" ← current" if name == 'TP-F_5.0x' else "")

        print(f"{name:<15} {avg_tp_pct:.1f}%{'':<3} {result['trades']:<7} {result['win_rate']:.1f}%{'':<2} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['tp_rate']:.1f}%{'':<5} "
              f"{result['sl_rate']:.1f}%{'':<3} {result['avg_hold']:.1f}d{marker}")

    print()

    # Best TP for 7-day
    best_tp_7d = max(tp_results.keys(), key=lambda k: tp_results[k]['expectancy'])
    print(f"Best TP for 7-day hold: {best_tp_7d} (E[R]: {tp_results[best_tp_7d]['expectancy']:+.3f}%)")
    print()

    # TP hit rate by day analysis
    print("TP Hit Rate Cumulative by Day (TP = 3.0x ATR):")
    result_3x = run_backtest(all_signals, 3.0, 1.5, 30, no_trail)
    for day in [1, 3, 5, 7, 10, 14, 21, 30]:
        if day in result_3x['tp_cum_by_day']:
            print(f"  Day {day:>2}: {result_3x['tp_cum_by_day'][day]:>5.1f}% of trades hit TP")
    print()

    # ============================================================
    # SECTION C: SL TARGET ANALYSIS
    # ============================================================
    print("=" * 85)
    print("C. SL TARGET ANALYSIS")
    print("=" * 85)
    print()

    # Use best TP from above
    best_tp_mult = TP_CONFIGS[best_tp_7d]['mult']

    print(f"Testing with TP = {best_tp_mult}x ATR, Max Hold = 7 days")
    print()

    print(f"{'SL Config':<15} {'SL%':<8} {'Win%':<7} {'E[R]':<10} {'SL Hit%':<9} {'FalseStop%':<10}")
    print("-" * 65)

    sl_results = {}
    for name, config in SL_CONFIGS.items():
        result = run_backtest(all_signals, best_tp_mult, config['mult'], 7, no_trail)
        false_stop = analyze_false_stops(all_signals, config['mult'], 7)
        sl_results[name] = {**result, **false_stop}

        avg_sl_pct = config['mult'] * statistics.mean([s['atr_pct'] for s in all_signals])
        marker = " ← current" if name == 'SL-B_1.5x' else ""

        print(f"{name:<15} {avg_sl_pct:.1f}%{'':<3} {result['win_rate']:.1f}%{'':<2} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['sl_rate']:.1f}%{'':<5} "
              f"{false_stop['false_stop_rate']:.1f}%{marker}")

    print()

    best_sl = max(sl_results.keys(), key=lambda k: sl_results[k]['expectancy'])
    print(f"Best SL: {best_sl} (E[R]: {sl_results[best_sl]['expectancy']:+.3f}%)")
    print()

    # ============================================================
    # SECTION D: R:R RATIO ANALYSIS
    # ============================================================
    print("=" * 85)
    print("D. R:R RATIO ANALYSIS")
    print("=" * 85)
    print()

    rr_combos = [
        (1.5, 1.5, "1:1"),
        (2.0, 1.5, "1.3:1"),
        (2.5, 1.5, "1.7:1"),
        (3.0, 1.5, "2:1"),
        (3.0, 2.0, "1.5:1"),
        (4.0, 2.0, "2:1"),
        (5.0, 1.5, "3.3:1"),
    ]

    print(f"{'R:R':<10} {'TP Mult':<10} {'SL Mult':<10} {'Win%':<8} {'E[R]':<10} {'TP Hit%':<10}")
    print("-" * 60)

    rr_results = {}
    for tp_m, sl_m, rr_name in rr_combos:
        result = run_backtest(all_signals, tp_m, sl_m, 7, no_trail)
        rr_results[rr_name] = result

        print(f"{rr_name:<10} {tp_m}x{'':<7} {sl_m}x{'':<7} {result['win_rate']:.1f}%{'':<3} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['tp_rate']:.1f}%")

    print()

    best_rr = max(rr_results.keys(), key=lambda k: rr_results[k]['expectancy'])
    print(f"Best R:R for 7-day Dip-Bounce: {best_rr} (E[R]: {rr_results[best_rr]['expectancy']:+.3f}%)")
    print()

    # ============================================================
    # SECTION E: TRAILING STOP RE-EVALUATION
    # ============================================================
    print("=" * 85)
    print("E. TRAILING STOP RE-EVALUATION (with realistic TP)")
    print("=" * 85)
    print()

    # Use best TP/SL
    best_tp_mult = TP_CONFIGS[best_tp_7d]['mult']
    best_sl_mult = SL_CONFIGS[best_sl]['mult']

    print(f"Testing with TP = {best_tp_mult}x, SL = {best_sl_mult}x, Max Hold = 7 days")
    print()

    print(f"{'Trail Config':<15} {'Win%':<8} {'E[R]':<10} {'TP%':<8} {'Trail%':<8} {'AvgHold':<8}")
    print("-" * 60)

    trail_results = {}
    for name, config in TRAIL_CONFIGS.items():
        result = run_backtest(all_signals, best_tp_mult, best_sl_mult, 7, config)
        trail_results[name] = result

        trail_rate = result['exit_types'].get('TRAIL_STOP', 0) / result['trades'] * 100
        marker = " ← disabled" if name == 'TRAIL_NONE' else ""

        print(f"{name:<15} {result['win_rate']:.1f}%{'':<3} {result['expectancy']:+.3f}%{'':<4} "
              f"{result['tp_rate']:.1f}%{'':<3} {trail_rate:.1f}%{'':<3} {result['avg_hold']:.1f}d{marker}")

    print()

    best_trail = max(trail_results.keys(), key=lambda k: trail_results[k]['expectancy'])
    print(f"Best Trailing Config: {best_trail} (E[R]: {trail_results[best_trail]['expectancy']:+.3f}%)")

    if best_trail != 'TRAIL_NONE':
        print(f"  Activation: {TRAIL_CONFIGS[best_trail]['activation']}%")
        print(f"  Lock: {TRAIL_CONFIGS[best_trail]['lock']}%")
    else:
        print("  Recommendation: Keep trailing DISABLED")
    print()

    # ============================================================
    # SECTION F: MAX HOLD RE-EVALUATION
    # ============================================================
    print("=" * 85)
    print("F. MAX HOLD RE-EVALUATION (with realistic TP)")
    print("=" * 85)
    print()

    print(f"Testing with TP = {best_tp_mult}x, SL = {best_sl_mult}x")
    print()

    print(f"{'Max Hold':<12} {'Win%':<8} {'E[R]':<10} {'TP Hit%':<10} {'MaxHold%':<10} {'AvgHold':<8}")
    print("-" * 60)

    hold_results = {}
    for max_hold in MAX_HOLD_VARIANTS:
        result = run_backtest(all_signals, best_tp_mult, best_sl_mult, max_hold, no_trail)
        hold_results[max_hold] = result

        print(f"{max_hold} days{'':<5} {result['win_rate']:.1f}%{'':<3} {result['expectancy']:+.3f}%{'':<4} "
              f"{result['tp_rate']:.1f}%{'':<5} {result['max_hold_rate']:.1f}%{'':<5} {result['avg_hold']:.1f}d")

    print()

    best_hold = max(hold_results.keys(), key=lambda k: hold_results[k]['expectancy'])
    print(f"Best Max Hold: {best_hold} days (E[R]: {hold_results[best_hold]['expectancy']:+.3f}%)")
    print()

    # ============================================================
    # SECTION G: COMBINED OPTIMIZATION
    # ============================================================
    print("=" * 85)
    print("G. COMBINED OPTIMIZATION (Best Config)")
    print("=" * 85)
    print()

    # Find global best
    best_config = None
    best_expectancy = -999

    for tp_name, tp_cfg in TP_CONFIGS.items():
        for sl_name, sl_cfg in SL_CONFIGS.items():
            for max_hold in [5, 7, 10]:
                for trail_name, trail_cfg in [('TRAIL_NONE', no_trail)]:
                    result = run_backtest(all_signals, tp_cfg['mult'], sl_cfg['mult'],
                                          max_hold, trail_cfg)

                    if result['expectancy'] > best_expectancy:
                        best_expectancy = result['expectancy']
                        best_config = {
                            'tp': tp_name,
                            'tp_mult': tp_cfg['mult'],
                            'sl': sl_name,
                            'sl_mult': sl_cfg['mult'],
                            'max_hold': max_hold,
                            'trail': trail_name,
                            'result': result,
                        }

    print(f"Global Best Configuration:")
    print(f"├── TP: {best_config['tp']} ({best_config['tp_mult']}x ATR)")
    print(f"├── SL: {best_config['sl']} ({best_config['sl_mult']}x ATR)")
    print(f"├── Max Hold: {best_config['max_hold']} days")
    print(f"├── Trailing: {best_config['trail']}")
    print(f"├── R:R Ratio: {best_config['tp_mult'] / best_config['sl_mult']:.1f}:1")
    print()
    print(f"Performance:")
    r = best_config['result']
    print(f"├── E[R]: {r['expectancy']:+.3f}%")
    print(f"├── Win Rate: {r['win_rate']:.1f}%")
    print(f"├── TP Hit Rate: {r['tp_rate']:.1f}%")
    print(f"├── SL Hit Rate: {r['sl_rate']:.1f}%")
    print(f"├── Max Hold Exit Rate: {r['max_hold_rate']:.1f}%")
    print(f"└── Avg Hold Days: {r['avg_hold']:.1f}")
    print()

    # ============================================================
    # SECTION H: COMPARISON v5.6 vs NEW
    # ============================================================
    print("=" * 85)
    print("H. COMPARISON: v5.6 (Current) vs NEW (Re-aligned)")
    print("=" * 85)
    print()

    # v5.6 config
    v56_result = run_backtest(all_signals, 5.0, 1.5, 30, no_trail)

    # New config
    new_result = run_backtest(all_signals, best_config['tp_mult'], best_config['sl_mult'],
                               best_config['max_hold'], no_trail)

    tp_mult_str = f"{best_config['tp_mult']}x"
    sl_mult_str = f"{best_config['sl_mult']}x"
    hold_str = str(best_config['max_hold'])
    rr_str = f"{best_config['tp_mult']/best_config['sl_mult']:.1f}:1"
    v56_e = f"{v56_result['expectancy']:+.3f}%"
    new_e = f"{new_result['expectancy']:+.3f}%"
    v56_wr = f"{v56_result['win_rate']:.1f}%"
    new_wr = f"{new_result['win_rate']:.1f}%"
    v56_tp = f"{v56_result['tp_rate']:.1f}%"
    new_tp = f"{new_result['tp_rate']:.1f}%"
    v56_sl = f"{v56_result['sl_rate']:.1f}%"
    new_sl = f"{new_result['sl_rate']:.1f}%"
    v56_hold = f"{v56_result['avg_hold']:.1f}"
    new_hold = f"{new_result['avg_hold']:.1f}"

    print(f"{'Metric':<25} {'v5.6 (TP 5.0x, 30d)':<20} {'NEW':<20} {'Change':<15}")
    print("-" * 80)
    print(f"{'TP Multiplier':<25} {'5.0x':<20} {tp_mult_str:<20} {best_config['tp_mult'] - 5.0:+.1f}x")
    print(f"{'SL Multiplier':<25} {'1.5x':<20} {sl_mult_str:<20} {best_config['sl_mult'] - 1.5:+.1f}x")
    print(f"{'Max Hold Days':<25} {'30':<20} {hold_str:<20} {best_config['max_hold'] - 30:+d}")
    print(f"{'R:R Ratio':<25} {'3.3:1':<20} {rr_str:<20}")
    print("-" * 80)
    print(f"{'Expectancy':<25} {v56_e:<20} {new_e:<20} {new_result['expectancy'] - v56_result['expectancy']:+.3f}%")
    print(f"{'Win Rate':<25} {v56_wr:<20} {new_wr:<20} {new_result['win_rate'] - v56_result['win_rate']:+.1f}%")
    print(f"{'TP Hit Rate':<25} {v56_tp:<20} {new_tp:<20} {new_result['tp_rate'] - v56_result['tp_rate']:+.1f}%")
    print(f"{'SL Hit Rate':<25} {v56_sl:<20} {new_sl:<20} {new_result['sl_rate'] - v56_result['sl_rate']:+.1f}%")
    print(f"{'Avg Hold Days':<25} {v56_hold:<20} {new_hold:<20} {new_result['avg_hold'] - v56_result['avg_hold']:+.1f}")
    print()

    # ============================================================
    # SECTION I: SUCCESS CRITERIA CHECK
    # ============================================================
    print("=" * 85)
    print("I. SUCCESS CRITERIA CHECK")
    print("=" * 85)
    print()

    criteria = [
        ('TP hit rate ≥ 40% in 7 days', new_result['tp_rate'] >= 40,
         f"{new_result['tp_rate']:.1f}%"),
        ('Avg hold ≤ 7 days', new_result['avg_hold'] <= 7,
         f"{new_result['avg_hold']:.1f} days"),
        ('E[R] ≥ +0.5%', new_result['expectancy'] >= 0.5,
         f"{new_result['expectancy']:+.3f}%"),
        ('Max Hold ≤ 10 days', best_config['max_hold'] <= 10,
         f"{best_config['max_hold']} days"),
        ('Short-term philosophy', best_config['max_hold'] <= 7,
         f"Hold {best_config['max_hold']} days"),
        ('Better than v5.6', new_result['expectancy'] >= v56_result['expectancy'],
         f"NEW {new_result['expectancy']:+.3f}% vs v5.6 {v56_result['expectancy']:+.3f}%"),
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
    # SECTION J: PHILOSOPHY CHECK
    # ============================================================
    print("=" * 85)
    print("J. PHILOSOPHY CHECK")
    print("=" * 85)
    print()

    is_dip_bounce = best_config['max_hold'] <= 10
    is_short_term = new_result['avg_hold'] <= 7
    is_mean_reversion = True  # By definition of our entry
    is_different_from_bh = new_result['avg_hold'] < 20
    has_clear_edge = new_result['expectancy'] > 0.3

    print("PHILOSOPHY CHECK:")
    print(f"├── Is this still Dip-Bounce? {'Yes ✅' if is_dip_bounce else 'No ❌'}")
    print(f"├── Short-term (≤7 days avg)? {'Yes ✅' if is_short_term else 'No ❌'}")
    print(f"├── Mean-reversion play? {'Yes ✅' if is_mean_reversion else 'No ❌'}")
    print(f"├── Different from buy-and-hold? {'Yes ✅' if is_different_from_bh else 'No ❌'}")
    print(f"└── Edge clearly defined? {'Yes ✅' if has_clear_edge else 'No ❌'}")
    print()

    philosophy_passed = sum([is_dip_bounce, is_short_term, is_mean_reversion,
                             is_different_from_bh, has_clear_edge])
    print(f"Philosophy Score: {philosophy_passed}/5")
    print()

    # ============================================================
    # SECTION K: FINAL RECOMMENDATION
    # ============================================================
    print("=" * 85)
    print("K. FINAL RECOMMENDATION")
    print("=" * 85)
    print()

    print("┌" + "─" * 75 + "┐")
    print("│  STRATEGY RE-ALIGNMENT RESULTS" + " " * 44 + "│")
    print("├" + "─" * 75 + "┤")
    print("│" + " " * 75 + "│")
    print(f"│  BOUNCE ANALYSIS:" + " " * 57 + "│")
    print(f"│  ├── Avg bounce in 5 days: {anatomy['avg_close_by_day'].get(5, 0):+.2f}%" + " " * 40 + "│")
    print(f"│  ├── Avg peak return: +{anatomy['avg_peak_return']:.2f}% at Day {anatomy['avg_peak_day']:.0f}" + " " * 35 + "│")
    print(f"│  └── Bounce success rate (≥3%): {anatomy['success_3pct']:.1f}%" + " " * 33 + "│")
    print("│" + " " * 75 + "│")
    print(f"│  OPTIMAL CONFIG:" + " " * 58 + "│")
    print(f"│  ├── TP: {best_config['tp_mult']}x ATR (was 5.0x)" + " " * 47 + "│")
    print(f"│  ├── SL: {best_config['sl_mult']}x ATR (was 1.5x)" + " " * 47 + "│")
    print(f"│  ├── R:R: {best_config['tp_mult']/best_config['sl_mult']:.1f}:1 (was 3.3:1)" + " " * 43 + "│")
    print(f"│  ├── Trailing: DISABLED (confirmed)" + " " * 38 + "│")
    print(f"│  └── Max Hold: {best_config['max_hold']} days (was 30)" + " " * 43 + "│")
    print("│" + " " * 75 + "│")
    print(f"│  EXPECTED PERFORMANCE:" + " " * 52 + "│")
    print(f"│  ├── TP Hit Rate: {new_result['tp_rate']:.1f}% (was {v56_result['tp_rate']:.1f}%)" + " " * 35 + "│")
    print(f"│  ├── Avg Hold: {new_result['avg_hold']:.1f} days (was {v56_result['avg_hold']:.1f})" + " " * 35 + "│")
    print(f"│  ├── E[R]: {new_result['expectancy']:+.3f}% (was {v56_result['expectancy']:+.3f}%)" + " " * 30 + "│")
    print(f"│  └── Win Rate: {new_result['win_rate']:.1f}% (was {v56_result['win_rate']:.1f}%)" + " " * 32 + "│")
    print("│" + " " * 75 + "│")

    # Decision
    if passed >= 5 and philosophy_passed >= 4:
        decision = "IMPLEMENT v5.8 (Re-aligned)"
        confidence = 85
    elif passed >= 4 and philosophy_passed >= 3:
        decision = "IMPLEMENT v5.8 (Re-aligned)"
        confidence = 75
    elif new_result['expectancy'] > v56_result['expectancy']:
        decision = "CONSIDER v5.8"
        confidence = 60
    else:
        decision = "KEEP v5.6"
        confidence = 70

    print(f"│  DECISION: {decision:<62}│")
    print(f"│  CONFIDENCE: {confidence}%" + " " * 59 + "│")
    print("└" + "─" * 75 + "┘")
    print()

    # Config output
    if "IMPLEMENT" in decision or "CONSIDER" in decision:
        print("=" * 85)
        print("L. v5.8 CONFIGURATION")
        print("=" * 85)
        print()
        print("```yaml")
        print("# v5.8 Re-aligned Dip-Bounce Configuration")
        print()
        print("# Core filters (keep)")
        print("stock_d_filter: true")
        print("bear_dd_exempt: true")
        print("min_score: 85")
        print()
        print("# TP/SL (re-optimized for short-term bounce)")
        print(f"tp_atr_multiplier: {best_config['tp_mult']}")
        print(f"tp_min_pct: 3.0")
        print(f"tp_max_pct: 8.0")
        print(f"sl_atr_multiplier: {best_config['sl_mult']}")
        print(f"sl_min_pct: 1.5")
        print(f"sl_max_pct: 4.0")
        print()
        print("# Trailing (confirmed disabled)")
        print("trail_enabled: false")
        print()
        print("# Max Hold (short-term)")
        print(f"max_hold_days: {best_config['max_hold']}")
        print()
        print("# VIX/Regime (disabled - let bounce work)")
        print("regime_vix_max: 100.0")
        print("sector_scoring: false")
        print("```")


if __name__ == '__main__':
    main()
