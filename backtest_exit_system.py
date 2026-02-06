#!/usr/bin/env python3
"""
Complete Exit System Design Backtest

ออกแบบ Exit System ที่มี edge (ไม่ใช่แค่รอเฉยๆ)

Exit Types to Test:
1. Trailing Stop (redesigned with lower TP)
2. Time-Based Profit Taking
3. RSI-Based Exit
4. Momentum Fade Exit
5. VIX Adaptive Exit
6. Combined Smart Exit

Target:
- Reduce Avg Hold to ≤ 7 days
- Reduce Max Hold Exit to ≤ 20%
- Maintain E[R] ≥ +1.3%
- Protect profits
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
    try:
        return yf.Ticker('^VIX').history(start=start_date, end=end_date)
    except:
        return pd.DataFrame()


def get_all_signals(start_date: str, end_date: str, vix_data: pd.DataFrame) -> List[Dict]:
    """Get all dip-bounce signals"""
    all_signals = []

    for symbol in ALL_SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist is None or len(hist) < 50:
                continue

            hist['prev_close'] = hist['Close'].shift(1)
            hist['daily_return'] = (hist['Close'] - hist['prev_close']) / hist['prev_close'] * 100
            hist['yesterday_return'] = hist['daily_return'].shift(1)
            hist['rsi'] = calculate_rsi(hist['Close'])

            hist['tr'] = pd.concat([
                hist['High'] - hist['Low'],
                (hist['High'] - hist['Close'].shift(1)).abs(),
                (hist['Low'] - hist['Close'].shift(1)).abs()
            ], axis=1).max(axis=1)
            hist['atr'] = hist['tr'].rolling(window=14).mean()
            hist['atr_pct'] = hist['atr'] / hist['Close'] * 100

            # 3-day momentum
            hist['momentum_3d'] = (hist['Close'] - hist['Close'].shift(3)) / hist['Close'].shift(3) * 100

            sector = SYMBOL_TO_SECTOR.get(symbol, 'Unknown')

            for i in range(50, len(hist) - 35):
                row = hist.iloc[i]
                signal_date = hist.index[i]

                yesterday_ret = row.get('yesterday_return', 0)
                today_ret = row.get('daily_return', 0)
                rsi = row.get('rsi', 50)
                atr_pct = row.get('atr_pct', 3.0)

                if pd.isna(yesterday_ret) or pd.isna(today_ret):
                    continue

                # Dip-bounce filter
                if not (yesterday_ret <= -2.0 and today_ret >= 1.0):
                    continue

                # VIX
                vix_level = 20.0
                if not vix_data.empty:
                    vix_dates = vix_data.index[vix_data.index <= signal_date]
                    if len(vix_dates) > 0:
                        vix_level = vix_data.loc[vix_dates[-1]]['Close']

                all_signals.append({
                    'symbol': symbol,
                    'sector': sector,
                    'date': signal_date,
                    'entry_idx': i,
                    'entry_price': row['Close'],
                    'entry_rsi': rsi if not pd.isna(rsi) else 50,
                    'atr_pct': atr_pct if not pd.isna(atr_pct) else 3.0,
                    'vix_level': vix_level if not pd.isna(vix_level) else 20,
                    'hist': hist,
                })

        except Exception:
            continue

    return all_signals


def simulate_baseline(signal: Dict, tp_mult: float, sl_mult: float, max_hold: int) -> Dict:
    """Baseline simulation (v5.6 style - no smart exit)"""
    entry_price = signal['entry_price']
    atr_pct = signal['atr_pct']
    hist = signal['hist']
    entry_idx = signal['entry_idx']

    tp_pct = max(6.0, min(12.0, atr_pct * tp_mult))
    sl_pct = max(2.0, min(4.0, atr_pct * sl_mult))

    tp_price = entry_price * (1 + tp_pct / 100)
    sl_price = entry_price * (1 - sl_pct / 100)

    result = {'exit_return': 0, 'exit_type': 'MAX_HOLD', 'exit_day': max_hold,
              'peak_profit': 0, 'exit_profit': 0}

    for day in range(1, min(max_hold + 1, len(hist) - entry_idx)):
        idx = entry_idx + day
        if idx >= len(hist):
            break

        high = hist.iloc[idx]['High']
        low = hist.iloc[idx]['Low']
        close = hist.iloc[idx]['Close']

        current_profit = (high - entry_price) / entry_price * 100
        if current_profit > result['peak_profit']:
            result['peak_profit'] = current_profit

        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            result['exit_profit'] = -sl_pct
            break

        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_day'] = day
            result['exit_profit'] = tp_pct
            break

        result['exit_return'] = (close - entry_price) / entry_price * 100
        result['exit_profit'] = result['exit_return']

    return result


def simulate_trailing(signal: Dict, tp_mult: float, sl_mult: float, max_hold: int,
                      trail_activation: float, trail_lock_pct: float) -> Dict:
    """Trailing stop simulation"""
    entry_price = signal['entry_price']
    atr_pct = signal['atr_pct']
    hist = signal['hist']
    entry_idx = signal['entry_idx']

    tp_pct = max(4.0, min(10.0, atr_pct * tp_mult))
    sl_pct = max(2.0, min(4.0, atr_pct * sl_mult))

    tp_price = entry_price * (1 + tp_pct / 100)
    sl_price = entry_price * (1 - sl_pct / 100)

    result = {'exit_return': 0, 'exit_type': 'MAX_HOLD', 'exit_day': max_hold,
              'peak_profit': 0, 'trail_triggered': False}

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
            result['peak_profit'] = (peak_price - entry_price) / entry_price * 100

        # Trail activation
        current_gain = (high - entry_price) / entry_price * 100
        if trailing_sl is None and current_gain >= trail_activation:
            locked = current_gain * trail_lock_pct / 100
            trailing_sl = entry_price * (1 + locked / 100)
            result['trail_triggered'] = True

        # Update trailing
        if trailing_sl is not None:
            new_locked = current_gain * trail_lock_pct / 100
            new_trail = entry_price * (1 + new_locked / 100)
            if new_trail > trailing_sl:
                trailing_sl = new_trail

        # Check exits
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            break

        if trailing_sl is not None and low <= trailing_sl:
            trail_gain = (trailing_sl - entry_price) / entry_price * 100
            result['exit_return'] = trail_gain
            result['exit_type'] = 'TRAIL_STOP'
            result['exit_day'] = day
            break

        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_day'] = day
            break

        result['exit_return'] = (close - entry_price) / entry_price * 100

    return result


def simulate_time_based(signal: Dict, sl_mult: float, max_hold: int,
                        profit_schedule: Dict[int, float]) -> Dict:
    """Time-based profit taking"""
    entry_price = signal['entry_price']
    atr_pct = signal['atr_pct']
    hist = signal['hist']
    entry_idx = signal['entry_idx']

    sl_pct = max(2.0, min(4.0, atr_pct * sl_mult))
    sl_price = entry_price * (1 - sl_pct / 100)

    result = {'exit_return': 0, 'exit_type': 'MAX_HOLD', 'exit_day': max_hold, 'peak_profit': 0}

    for day in range(1, min(max_hold + 1, len(hist) - entry_idx)):
        idx = entry_idx + day
        if idx >= len(hist):
            break

        high = hist.iloc[idx]['High']
        low = hist.iloc[idx]['Low']
        close = hist.iloc[idx]['Close']

        current_profit = (high - entry_price) / entry_price * 100
        close_profit = (close - entry_price) / entry_price * 100
        if current_profit > result['peak_profit']:
            result['peak_profit'] = current_profit

        # SL check
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            break

        # Time-based profit check
        target = None
        for threshold_day, target_profit in sorted(profit_schedule.items()):
            if day <= threshold_day:
                target = target_profit
                break

        if target is None:
            target = profit_schedule.get(max(profit_schedule.keys()), 1.0)

        if close_profit >= target:
            result['exit_return'] = close_profit
            result['exit_type'] = 'TIME_PROFIT'
            result['exit_day'] = day
            break

        result['exit_return'] = close_profit

    return result


def simulate_rsi_exit(signal: Dict, tp_mult: float, sl_mult: float, max_hold: int,
                      rsi_threshold: float, min_profit: float) -> Dict:
    """RSI-based exit"""
    entry_price = signal['entry_price']
    atr_pct = signal['atr_pct']
    hist = signal['hist']
    entry_idx = signal['entry_idx']

    tp_pct = max(6.0, min(12.0, atr_pct * tp_mult))
    sl_pct = max(2.0, min(4.0, atr_pct * sl_mult))

    tp_price = entry_price * (1 + tp_pct / 100)
    sl_price = entry_price * (1 - sl_pct / 100)

    result = {'exit_return': 0, 'exit_type': 'MAX_HOLD', 'exit_day': max_hold, 'peak_profit': 0}

    for day in range(1, min(max_hold + 1, len(hist) - entry_idx)):
        idx = entry_idx + day
        if idx >= len(hist):
            break

        high = hist.iloc[idx]['High']
        low = hist.iloc[idx]['Low']
        close = hist.iloc[idx]['Close']
        current_rsi = hist.iloc[idx].get('rsi', 50)

        close_profit = (close - entry_price) / entry_price * 100
        current_profit = (high - entry_price) / entry_price * 100
        if current_profit > result['peak_profit']:
            result['peak_profit'] = current_profit

        # SL
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            break

        # RSI exit
        if not pd.isna(current_rsi) and current_rsi >= rsi_threshold and close_profit >= min_profit:
            result['exit_return'] = close_profit
            result['exit_type'] = 'RSI_EXIT'
            result['exit_day'] = day
            break

        # TP
        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_day'] = day
            break

        result['exit_return'] = close_profit

    return result


def simulate_momentum_exit(signal: Dict, tp_mult: float, sl_mult: float, max_hold: int,
                           min_profit: float) -> Dict:
    """Momentum fade exit"""
    entry_price = signal['entry_price']
    atr_pct = signal['atr_pct']
    hist = signal['hist']
    entry_idx = signal['entry_idx']

    tp_pct = max(6.0, min(12.0, atr_pct * tp_mult))
    sl_pct = max(2.0, min(4.0, atr_pct * sl_mult))

    tp_price = entry_price * (1 + tp_pct / 100)
    sl_price = entry_price * (1 - sl_pct / 100)

    result = {'exit_return': 0, 'exit_type': 'MAX_HOLD', 'exit_day': max_hold, 'peak_profit': 0}

    for day in range(1, min(max_hold + 1, len(hist) - entry_idx)):
        idx = entry_idx + day
        if idx >= len(hist):
            break

        high = hist.iloc[idx]['High']
        low = hist.iloc[idx]['Low']
        close = hist.iloc[idx]['Close']
        momentum_3d = hist.iloc[idx].get('momentum_3d', 0)

        close_profit = (close - entry_price) / entry_price * 100
        current_profit = (high - entry_price) / entry_price * 100
        if current_profit > result['peak_profit']:
            result['peak_profit'] = current_profit

        # SL
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            break

        # Momentum fade exit (only after day 3)
        if day >= 3 and not pd.isna(momentum_3d) and momentum_3d < 0 and close_profit >= min_profit:
            result['exit_return'] = close_profit
            result['exit_type'] = 'MOMENTUM_FADE'
            result['exit_day'] = day
            break

        # TP
        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_day'] = day
            break

        result['exit_return'] = close_profit

    return result


def simulate_vix_adaptive(signal: Dict, sl_mult: float) -> Dict:
    """VIX adaptive exit - adjust TP/Hold based on VIX"""
    vix = signal['vix_level']

    if vix >= 30:
        tp_mult, max_hold, trail_act, trail_lock = 2.0, 5, 2.0, 60
    elif vix >= 25:
        tp_mult, max_hold, trail_act, trail_lock = 2.5, 7, 2.5, 55
    elif vix >= 20:
        tp_mult, max_hold, trail_act, trail_lock = 3.0, 10, 3.0, 50
    else:
        tp_mult, max_hold, trail_act, trail_lock = 4.0, 14, 3.5, 45

    entry_price = signal['entry_price']
    atr_pct = signal['atr_pct']
    hist = signal['hist']
    entry_idx = signal['entry_idx']

    tp_pct = max(4.0, min(12.0, atr_pct * tp_mult))
    sl_pct = max(2.0, min(4.0, atr_pct * sl_mult))

    tp_price = entry_price * (1 + tp_pct / 100)
    sl_price = entry_price * (1 - sl_pct / 100)

    result = {'exit_return': 0, 'exit_type': 'MAX_HOLD', 'exit_day': max_hold,
              'peak_profit': 0, 'vix_tier': 'VIX30+' if vix >= 30 else ('VIX25+' if vix >= 25 else ('VIX20+' if vix >= 20 else 'VIX<20'))}

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
            result['peak_profit'] = (peak_price - entry_price) / entry_price * 100

        # Trail
        current_gain = (high - entry_price) / entry_price * 100
        if trailing_sl is None and current_gain >= trail_act:
            trailing_sl = entry_price * (1 + current_gain * trail_lock / 100 / 100)

        if trailing_sl is not None:
            new_trail = entry_price * (1 + current_gain * trail_lock / 100 / 100)
            if new_trail > trailing_sl:
                trailing_sl = new_trail

        # SL
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            break

        # Trail
        if trailing_sl is not None and low <= trailing_sl:
            result['exit_return'] = (trailing_sl - entry_price) / entry_price * 100
            result['exit_type'] = 'TRAIL_STOP'
            result['exit_day'] = day
            break

        # TP
        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_day'] = day
            break

        result['exit_return'] = (close - entry_price) / entry_price * 100

    return result


def simulate_combined(signal: Dict, sl_mult: float, max_hold: int = 14) -> Dict:
    """Combined smart exit system"""
    entry_price = signal['entry_price']
    atr_pct = signal['atr_pct']
    hist = signal['hist']
    entry_idx = signal['entry_idx']

    tp_pct = max(6.0, min(10.0, atr_pct * 3.5))
    sl_pct = max(2.0, min(4.0, atr_pct * sl_mult))

    tp_price = entry_price * (1 + tp_pct / 100)
    sl_price = entry_price * (1 - sl_pct / 100)

    # Trailing params
    trail_activation = 2.5
    trail_lock = 55

    # Time-based targets
    time_targets = {3: 4.0, 5: 3.0, 7: 2.5, 10: 2.0, 14: 1.0}

    result = {'exit_return': 0, 'exit_type': 'MAX_HOLD', 'exit_day': max_hold, 'peak_profit': 0}

    trailing_sl = None
    peak_price = entry_price

    for day in range(1, min(max_hold + 1, len(hist) - entry_idx)):
        idx = entry_idx + day
        if idx >= len(hist):
            break

        high = hist.iloc[idx]['High']
        low = hist.iloc[idx]['Low']
        close = hist.iloc[idx]['Close']
        current_rsi = hist.iloc[idx].get('rsi', 50)
        momentum_3d = hist.iloc[idx].get('momentum_3d', 0)

        close_profit = (close - entry_price) / entry_price * 100
        current_profit = (high - entry_price) / entry_price * 100
        if current_profit > result['peak_profit']:
            result['peak_profit'] = current_profit

        # Trail activation
        if trailing_sl is None and current_profit >= trail_activation:
            trailing_sl = entry_price * (1 + current_profit * trail_lock / 100 / 100)

        if trailing_sl is not None:
            new_trail = entry_price * (1 + current_profit * trail_lock / 100 / 100)
            if new_trail > trailing_sl:
                trailing_sl = new_trail

        # Priority 1: SL
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            break

        # Priority 2: RSI overbought + profit
        if not pd.isna(current_rsi) and current_rsi >= 70 and close_profit >= 2.0:
            result['exit_return'] = close_profit
            result['exit_type'] = 'RSI_EXIT'
            result['exit_day'] = day
            break

        # Priority 3: Time-based profit
        target = None
        for threshold_day, target_profit in sorted(time_targets.items()):
            if day <= threshold_day:
                target = target_profit
                break
        if target and close_profit >= target:
            result['exit_return'] = close_profit
            result['exit_type'] = 'TIME_PROFIT'
            result['exit_day'] = day
            break

        # Priority 4: Trailing stop
        if trailing_sl is not None and low <= trailing_sl:
            result['exit_return'] = (trailing_sl - entry_price) / entry_price * 100
            result['exit_type'] = 'TRAIL_STOP'
            result['exit_day'] = day
            break

        # Priority 5: Momentum fade (after day 3)
        if day >= 3 and not pd.isna(momentum_3d) and momentum_3d < 0 and close_profit >= 1.5:
            result['exit_return'] = close_profit
            result['exit_type'] = 'MOMENTUM_FADE'
            result['exit_day'] = day
            break

        # Priority 6: TP
        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_day'] = day
            break

        result['exit_return'] = close_profit

    return result


def calc_metrics(trades: List[Dict]) -> Dict:
    """Calculate metrics from trades"""
    if not trades:
        return {'trades': 0, 'expectancy': 0, 'win_rate': 0, 'avg_hold': 0}

    wins = [t for t in trades if t['exit_return'] > 0]
    losses = [t for t in trades if t['exit_return'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
    avg_hold = statistics.mean([t['exit_day'] for t in trades])

    exit_dist = defaultdict(int)
    for t in trades:
        exit_dist[t['exit_type']] += 1

    return {
        'trades': len(trades),
        'expectancy': expectancy,
        'win_rate': win_rate,
        'avg_hold': avg_hold,
        'exit_dist': dict(exit_dist),
        'max_hold_pct': exit_dist.get('MAX_HOLD', 0) / len(trades) * 100,
        'tp_pct': exit_dist.get('TAKE_PROFIT', 0) / len(trades) * 100,
        'sl_pct': exit_dist.get('STOP_LOSS', 0) / len(trades) * 100,
    }


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 90)
    print("COMPLETE EXIT SYSTEM DESIGN BACKTEST")
    print("=" * 90)
    print("Target: Reduce hold time while maintaining E[R]")
    print()

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

    print(f"Period: {start_date} to {end_date}")
    print()

    print("Loading VIX data...")
    vix_data = get_vix_data(start_date, end_date)
    print()

    print("Collecting signals...")
    all_signals = get_all_signals(start_date, end_date, vix_data)
    print(f"Total signals: {len(all_signals)}")
    print()

    if not all_signals:
        print("No signals!")
        return

    # ============================================================
    # BASELINE (v5.6)
    # ============================================================
    print("=" * 90)
    print("A. BASELINE (v5.6): TP 5.0x, SL 1.5x, Max Hold 30d, No trailing")
    print("=" * 90)

    baseline_trades = [simulate_baseline(s, 5.0, 1.5, 30) for s in all_signals]
    baseline = calc_metrics(baseline_trades)

    print(f"Trades: {baseline['trades']}")
    print(f"E[R]: {baseline['expectancy']:+.3f}%")
    print(f"Win Rate: {baseline['win_rate']:.1f}%")
    print(f"Avg Hold: {baseline['avg_hold']:.1f} days")
    print(f"Exit Distribution:")
    for exit_type, count in sorted(baseline['exit_dist'].items(), key=lambda x: -x[1]):
        pct = count / baseline['trades'] * 100
        print(f"  {exit_type}: {count} ({pct:.1f}%)")
    print()

    # Analyze max hold exits
    max_hold_trades = [t for t in baseline_trades if t['exit_type'] == 'MAX_HOLD']
    if max_hold_trades:
        mh_profits = [t['exit_return'] for t in max_hold_trades]
        mh_wins = [t for t in max_hold_trades if t['exit_return'] > 0]
        print("MAX HOLD EXIT ANALYSIS:")
        print(f"├── Count: {len(max_hold_trades)} ({baseline['max_hold_pct']:.1f}%)")
        print(f"├── Avg P&L at exit: {statistics.mean(mh_profits):+.2f}%")
        print(f"├── Win rate: {len(mh_wins)/len(max_hold_trades)*100:.1f}%")
        print(f"├── Peak profit before exit: {statistics.mean([t['peak_profit'] for t in max_hold_trades]):.2f}%")
        print(f"└── Problem: Exiting with profit but no logic")
    print()

    # ============================================================
    # TRAILING STOP TESTS
    # ============================================================
    print("=" * 90)
    print("B. TRAILING STOP VARIANTS")
    print("=" * 90)
    print()

    trailing_configs = [
        ('T1: 2%/50% + TP 3.0x', 3.0, 2.0, 50),
        ('T2: 3%/50% + TP 3.0x', 3.0, 3.0, 50),
        ('T3: 2%/60% + TP 2.5x', 2.5, 2.0, 60),
        ('T4: 3%/60% + TP 2.5x', 2.5, 3.0, 60),
        ('T5: 2%/70% + TP 2.5x', 2.5, 2.0, 70),
        ('T6: 4%/50% + TP 3.5x', 3.5, 4.0, 50),
        ('T7: 2.5%/55% + TP 3.0x', 3.0, 2.5, 55),
    ]

    print(f"{'Config':<25} {'E[R]':<10} {'AvgHold':<10} {'Win%':<8} {'TP%':<7} {'Trail%':<8} {'MaxH%':<7}")
    print("-" * 80)

    trail_results = {}
    for name, tp_m, trail_act, trail_lock in trailing_configs:
        trades = [simulate_trailing(s, tp_m, 1.5, 14, trail_act, trail_lock) for s in all_signals]
        m = calc_metrics(trades)
        trail_pct = m['exit_dist'].get('TRAIL_STOP', 0) / m['trades'] * 100

        trail_results[name] = m
        print(f"{name:<25} {m['expectancy']:+.3f}%{'':<4} {m['avg_hold']:.1f}d{'':<5} "
              f"{m['win_rate']:.1f}%{'':<3} {m['tp_pct']:.1f}%{'':<2} {trail_pct:.1f}%{'':<3} "
              f"{m['max_hold_pct']:.1f}%")

    best_trail = max(trail_results.keys(), key=lambda k: trail_results[k]['expectancy'])
    print(f"\nBest Trailing: {best_trail} (E[R]: {trail_results[best_trail]['expectancy']:+.3f}%)")
    print()

    # ============================================================
    # TIME-BASED PROFIT TAKING
    # ============================================================
    print("=" * 90)
    print("C. TIME-BASED PROFIT TAKING")
    print("=" * 90)
    print()

    time_configs = [
        ('Aggressive', {2: 4.0, 4: 3.0, 7: 2.0, 10: 1.0}),
        ('Moderate', {2: 5.0, 4: 4.0, 7: 3.0, 10: 2.0}),
        ('Relaxed', {2: 6.0, 5: 5.0, 8: 4.0, 12: 3.0}),
        ('Quick Exit', {2: 3.0, 3: 2.5, 5: 2.0, 7: 1.5}),
    ]

    print(f"{'Config':<15} {'E[R]':<10} {'AvgHold':<10} {'Win%':<8} {'TimeExit%':<10} {'MaxH%':<8}")
    print("-" * 65)

    time_results = {}
    for name, schedule in time_configs:
        trades = [simulate_time_based(s, 1.5, 14, schedule) for s in all_signals]
        m = calc_metrics(trades)
        time_exit_pct = m['exit_dist'].get('TIME_PROFIT', 0) / m['trades'] * 100

        time_results[name] = m
        print(f"{name:<15} {m['expectancy']:+.3f}%{'':<4} {m['avg_hold']:.1f}d{'':<5} "
              f"{m['win_rate']:.1f}%{'':<3} {time_exit_pct:.1f}%{'':<5} {m['max_hold_pct']:.1f}%")

    best_time = max(time_results.keys(), key=lambda k: time_results[k]['expectancy'])
    print(f"\nBest Time-Based: {best_time} (E[R]: {time_results[best_time]['expectancy']:+.3f}%)")
    print()

    # ============================================================
    # RSI-BASED EXIT
    # ============================================================
    print("=" * 90)
    print("D. RSI-BASED EXIT")
    print("=" * 90)
    print()

    rsi_configs = [
        ('R1: RSI≥70, +2%', 70, 2.0),
        ('R2: RSI≥65, +2%', 65, 2.0),
        ('R3: RSI≥70, +3%', 70, 3.0),
        ('R4: RSI≥60, +3%', 60, 3.0),
        ('R5: RSI≥75, +2%', 75, 2.0),
    ]

    print(f"{'Config':<20} {'E[R]':<10} {'AvgHold':<10} {'Win%':<8} {'RSIExit%':<10} {'MaxH%':<8}")
    print("-" * 70)

    rsi_results = {}
    for name, rsi_thresh, min_profit in rsi_configs:
        trades = [simulate_rsi_exit(s, 5.0, 1.5, 14, rsi_thresh, min_profit) for s in all_signals]
        m = calc_metrics(trades)
        rsi_exit_pct = m['exit_dist'].get('RSI_EXIT', 0) / m['trades'] * 100

        rsi_results[name] = m
        print(f"{name:<20} {m['expectancy']:+.3f}%{'':<4} {m['avg_hold']:.1f}d{'':<5} "
              f"{m['win_rate']:.1f}%{'':<3} {rsi_exit_pct:.1f}%{'':<5} {m['max_hold_pct']:.1f}%")

    best_rsi = max(rsi_results.keys(), key=lambda k: rsi_results[k]['expectancy'])
    print(f"\nBest RSI: {best_rsi} (E[R]: {rsi_results[best_rsi]['expectancy']:+.3f}%)")
    print()

    # ============================================================
    # MOMENTUM FADE EXIT
    # ============================================================
    print("=" * 90)
    print("E. MOMENTUM FADE EXIT")
    print("=" * 90)
    print()

    momentum_configs = [
        ('M1: +1.5% min', 1.5),
        ('M2: +2.0% min', 2.0),
        ('M3: +2.5% min', 2.5),
        ('M4: +3.0% min', 3.0),
    ]

    print(f"{'Config':<20} {'E[R]':<10} {'AvgHold':<10} {'Win%':<8} {'MomExit%':<10} {'MaxH%':<8}")
    print("-" * 70)

    momentum_results = {}
    for name, min_profit in momentum_configs:
        trades = [simulate_momentum_exit(s, 5.0, 1.5, 14, min_profit) for s in all_signals]
        m = calc_metrics(trades)
        mom_exit_pct = m['exit_dist'].get('MOMENTUM_FADE', 0) / m['trades'] * 100

        momentum_results[name] = m
        print(f"{name:<20} {m['expectancy']:+.3f}%{'':<4} {m['avg_hold']:.1f}d{'':<5} "
              f"{m['win_rate']:.1f}%{'':<3} {mom_exit_pct:.1f}%{'':<5} {m['max_hold_pct']:.1f}%")

    best_momentum = max(momentum_results.keys(), key=lambda k: momentum_results[k]['expectancy'])
    print(f"\nBest Momentum: {best_momentum} (E[R]: {momentum_results[best_momentum]['expectancy']:+.3f}%)")
    print()

    # ============================================================
    # VIX ADAPTIVE EXIT
    # ============================================================
    print("=" * 90)
    print("F. VIX ADAPTIVE EXIT")
    print("=" * 90)
    print()

    vix_trades = [simulate_vix_adaptive(s, 1.5) for s in all_signals]
    vix_m = calc_metrics(vix_trades)

    print(f"E[R]: {vix_m['expectancy']:+.3f}%")
    print(f"Avg Hold: {vix_m['avg_hold']:.1f} days")
    print(f"Win Rate: {vix_m['win_rate']:.1f}%")
    print(f"Max Hold Exit: {vix_m['max_hold_pct']:.1f}%")
    print(f"Exit Distribution:")
    for exit_type, count in sorted(vix_m['exit_dist'].items(), key=lambda x: -x[1]):
        pct = count / vix_m['trades'] * 100
        print(f"  {exit_type}: {count} ({pct:.1f}%)")
    print()

    # ============================================================
    # COMBINED SMART EXIT
    # ============================================================
    print("=" * 90)
    print("G. COMBINED SMART EXIT SYSTEM")
    print("=" * 90)
    print()

    combined_trades = [simulate_combined(s, 1.5, 14) for s in all_signals]
    combined_m = calc_metrics(combined_trades)

    print(f"E[R]: {combined_m['expectancy']:+.3f}%")
    print(f"Avg Hold: {combined_m['avg_hold']:.1f} days")
    print(f"Win Rate: {combined_m['win_rate']:.1f}%")
    print(f"Max Hold Exit: {combined_m['max_hold_pct']:.1f}%")
    print(f"\nExit Distribution:")
    for exit_type, count in sorted(combined_m['exit_dist'].items(), key=lambda x: -x[1]):
        pct = count / combined_m['trades'] * 100
        print(f"  {exit_type}: {count} ({pct:.1f}%)")
    print()

    # ============================================================
    # COMPARISON TABLE
    # ============================================================
    print("=" * 90)
    print("H. COMPARISON: ALL EXIT SYSTEMS")
    print("=" * 90)
    print()

    all_systems = {
        'Baseline (v5.6)': baseline,
        f'Best Trail ({best_trail})': trail_results[best_trail],
        f'Best Time ({best_time})': time_results[best_time],
        f'Best RSI ({best_rsi})': rsi_results[best_rsi],
        f'Best Mom ({best_momentum})': momentum_results[best_momentum],
        'VIX Adaptive': vix_m,
        'Combined Smart': combined_m,
    }

    print(f"{'System':<30} {'E[R]':<10} {'AvgHold':<10} {'Win%':<8} {'MaxH%':<8} {'Score'}")
    print("-" * 80)

    for name, m in sorted(all_systems.items(), key=lambda x: x[1]['expectancy'], reverse=True):
        # Score: E[R] weight 40%, Hold weight 30%, MaxH% weight 30%
        er_score = min(10, max(0, m['expectancy'] / 0.15))
        hold_score = min(10, max(0, (15 - m['avg_hold']) / 1.5))
        maxh_score = min(10, max(0, (50 - m['max_hold_pct']) / 5))
        total_score = er_score * 40 + hold_score * 30 + maxh_score * 30

        marker = " ← BEST" if m['expectancy'] == max(s['expectancy'] for s in all_systems.values()) else ""
        print(f"{name:<30} {m['expectancy']:+.3f}%{'':<4} {m['avg_hold']:.1f}d{'':<5} "
              f"{m['win_rate']:.1f}%{'':<3} {m['max_hold_pct']:.1f}%{'':<3} {total_score:.0f}{marker}")

    print()

    # ============================================================
    # SUCCESS CRITERIA
    # ============================================================
    print("=" * 90)
    print("I. SUCCESS CRITERIA CHECK")
    print("=" * 90)
    print()

    # Best system overall
    best_system_name = max(all_systems.keys(), key=lambda k: all_systems[k]['expectancy'])
    best = all_systems[best_system_name]

    criteria = [
        ('Avg Hold ≤ 7 days', best['avg_hold'] <= 7, f"{best['avg_hold']:.1f} days"),
        ('Max Hold Exit ≤ 20%', best['max_hold_pct'] <= 20, f"{best['max_hold_pct']:.1f}%"),
        ('E[R] ≥ +1.3%', best['expectancy'] >= 1.3, f"{best['expectancy']:+.3f}%"),
        ('Win Rate ≥ 45%', best['win_rate'] >= 45, f"{best['win_rate']:.1f}%"),
        ('E[R] ≥ Baseline', best['expectancy'] >= baseline['expectancy'],
         f"{best['expectancy']:+.3f}% vs {baseline['expectancy']:+.3f}%"),
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
    # FINAL RECOMMENDATION
    # ============================================================
    print("=" * 90)
    print("J. FINAL RECOMMENDATION")
    print("=" * 90)
    print()

    print("┌" + "─" * 80 + "┐")
    print("│  EXIT SYSTEM RESEARCH RESULTS" + " " * 50 + "│")
    print("├" + "─" * 80 + "┤")
    print("│" + " " * 80 + "│")
    print(f"│  BEST EXIT SYSTEM: {best_system_name:<59}│")
    print("│" + " " * 80 + "│")
    print(f"│  PERFORMANCE vs BASELINE (v5.6):" + " " * 46 + "│")
    print(f"│  ├── E[R]: {best['expectancy']:+.3f}% vs {baseline['expectancy']:+.3f}%" + " " * 45 + "│")
    print(f"│  ├── Avg Hold: {best['avg_hold']:.1f}d vs {baseline['avg_hold']:.1f}d" + " " * 45 + "│")
    print(f"│  ├── Max Hold Exits: {best['max_hold_pct']:.1f}% vs {baseline['max_hold_pct']:.1f}%" + " " * 35 + "│")
    print(f"│  └── Win Rate: {best['win_rate']:.1f}% vs {baseline['win_rate']:.1f}%" + " " * 41 + "│")
    print("│" + " " * 80 + "│")
    print(f"│  EXIT DISTRIBUTION ({best_system_name}):" + " " * 40 + "│")
    for exit_type, count in sorted(best['exit_dist'].items(), key=lambda x: -x[1])[:5]:
        pct = count / best['trades'] * 100
        print(f"│  ├── {exit_type}: {pct:.1f}%" + " " * 55 + "│")
    print("│" + " " * 80 + "│")

    if passed >= 3 and best['expectancy'] >= baseline['expectancy']:
        decision = f"IMPLEMENT {best_system_name}"
        confidence = 80
    elif passed >= 2:
        decision = f"CONSIDER {best_system_name}"
        confidence = 65
    else:
        decision = "KEEP BASELINE v5.6"
        confidence = 70

    print(f"│  RECOMMENDATION: {decision:<61}│")
    print(f"│  CONFIDENCE: {confidence}%" + " " * 64 + "│")
    print("└" + "─" * 80 + "┘")


if __name__ == '__main__':
    main()
