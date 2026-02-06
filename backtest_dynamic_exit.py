#!/usr/bin/env python3
"""
Dynamic Exit System Backtest

ปัญหาของ MAX_HOLD_DAYS hardcoded:
- ไม่ฉลาด - ไม่สนใจว่า trade กำลังทำอะไร
- บาง trade ควร hold นาน บางอันควร exit เร็ว

Solution: Dynamic Exit Conditions with Max Hold as Fallback

Exit Conditions to Test:
1. Momentum Fade - price momentum หายไป
2. Sector Regime Flip - sector เปลี่ยนจาก BULL → BEAR
3. RSI Overbought Exit - RSI > 70-80 + มี profit
4. Volatility Spike - ATR พุ่งขึ้น = risk เพิ่ม
5. Trend Break - price < SMA (moving average cross)
6. Profit Target Dynamic - scale out at different levels
7. Time Decay - lower expectations as time passes

Primary Metric: Expectancy (NOT Win Rate)
Baseline: v5.6 with no dynamic exit
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Callable
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
# DYNAMIC EXIT CONDITIONS
# ============================================================

class DynamicExitCondition:
    """Base class for exit conditions"""
    name: str = "base"

    def should_exit(self, position: Dict, day: int, hist: pd.DataFrame) -> Tuple[bool, str]:
        """Returns (should_exit, reason)"""
        raise NotImplementedError


class MomentumFadeExit(DynamicExitCondition):
    """Exit when momentum fades significantly from entry"""
    name = "momentum_fade"

    def __init__(self, fade_threshold: float = 0.5, min_days: int = 2):
        self.fade_threshold = fade_threshold  # Exit if momentum < threshold * entry_momentum
        self.min_days = min_days  # Don't exit too early

    def should_exit(self, position: Dict, day: int, hist: pd.DataFrame) -> Tuple[bool, str]:
        if day < self.min_days:
            return False, None

        entry_idx = position['entry_idx']
        current_idx = entry_idx + day

        if current_idx >= len(hist) - 1:
            return False, None

        # Entry momentum = yesterday's dip + today's bounce
        entry_momentum = abs(position.get('yesterday_return', 2)) + position.get('today_return', 1)

        # Current momentum = recent 2-day return
        if current_idx >= 2:
            current_close = hist.iloc[current_idx]['Close']
            prev_2d_close = hist.iloc[current_idx - 2]['Close']
            current_momentum = (current_close - prev_2d_close) / prev_2d_close * 100
        else:
            current_momentum = 0

        # Exit if momentum faded
        if current_momentum < entry_momentum * self.fade_threshold:
            return True, f"momentum_fade({current_momentum:.1f}%<{entry_momentum*self.fade_threshold:.1f}%)"

        return False, None


class SectorRegimeFlipExit(DynamicExitCondition):
    """Exit when sector regime flips from BULL to BEAR/SIDEWAYS"""
    name = "sector_flip"

    def __init__(self, sector_data: Dict, require_profit: bool = False):
        self.sector_data = sector_data
        self.require_profit = require_profit

    def should_exit(self, position: Dict, day: int, hist: pd.DataFrame) -> Tuple[bool, str]:
        entry_regime = position.get('sector_regime', 'SIDEWAYS')
        if entry_regime != 'BULL':
            return False, None  # Only applies to BULL entries

        entry_idx = position['entry_idx']
        current_idx = entry_idx + day
        current_date = hist.index[current_idx] if current_idx < len(hist) else None

        if current_date is None:
            return False, None

        sector = position.get('sector', 'Unknown')
        if sector not in self.sector_data:
            return False, None

        # Get current sector regime
        sector_df = self.sector_data[sector]
        dates = sector_df.index[sector_df.index <= current_date]
        if len(dates) == 0:
            return False, None

        row = sector_df.loc[dates[-1]]
        return_20d = row.get('return_20d', 0)

        if pd.isna(return_20d):
            return False, None

        # Determine current regime
        if return_20d < -3.0:
            current_regime = 'BEAR'
        elif return_20d > 3.0:
            current_regime = 'BULL'
        else:
            current_regime = 'SIDEWAYS'

        # Check if flipped
        if entry_regime == 'BULL' and current_regime in ['BEAR', 'SIDEWAYS']:
            # Optionally require profit before exiting
            if self.require_profit:
                entry_price = position['entry_price']
                current_price = hist.iloc[current_idx]['Close']
                pnl_pct = (current_price - entry_price) / entry_price * 100
                if pnl_pct <= 0:
                    return False, None

            return True, f"sector_flip({entry_regime}→{current_regime})"

        return False, None


class RSIOverboughtExit(DynamicExitCondition):
    """Exit when RSI hits overbought and we have profit"""
    name = "rsi_overbought"

    def __init__(self, rsi_threshold: float = 70, min_profit_pct: float = 2.0):
        self.rsi_threshold = rsi_threshold
        self.min_profit_pct = min_profit_pct

    def should_exit(self, position: Dict, day: int, hist: pd.DataFrame) -> Tuple[bool, str]:
        entry_idx = position['entry_idx']
        current_idx = entry_idx + day

        if current_idx >= len(hist):
            return False, None

        current_rsi = hist.iloc[current_idx].get('rsi', 50)
        if pd.isna(current_rsi):
            return False, None

        entry_price = position['entry_price']
        current_price = hist.iloc[current_idx]['Close']
        pnl_pct = (current_price - entry_price) / entry_price * 100

        if current_rsi >= self.rsi_threshold and pnl_pct >= self.min_profit_pct:
            return True, f"rsi_overbought(RSI={current_rsi:.0f},profit={pnl_pct:.1f}%)"

        return False, None


class VolatilitySpikeExit(DynamicExitCondition):
    """Exit when volatility spikes significantly (risk increased)"""
    name = "volatility_spike"

    def __init__(self, spike_multiplier: float = 1.5, require_profit: bool = True):
        self.spike_multiplier = spike_multiplier
        self.require_profit = require_profit

    def should_exit(self, position: Dict, day: int, hist: pd.DataFrame) -> Tuple[bool, str]:
        entry_idx = position['entry_idx']
        current_idx = entry_idx + day

        if current_idx >= len(hist):
            return False, None

        entry_atr = position.get('atr_pct', 3.0)
        current_atr = hist.iloc[current_idx].get('atr_pct', entry_atr)

        if pd.isna(current_atr):
            return False, None

        if current_atr >= entry_atr * self.spike_multiplier:
            if self.require_profit:
                entry_price = position['entry_price']
                current_price = hist.iloc[current_idx]['Close']
                pnl_pct = (current_price - entry_price) / entry_price * 100
                if pnl_pct <= 0:
                    return False, None

            return True, f"volatility_spike(ATR:{entry_atr:.1f}%→{current_atr:.1f}%)"

        return False, None


class TrendBreakExit(DynamicExitCondition):
    """Exit when price breaks below moving average"""
    name = "trend_break"

    def __init__(self, ma_period: int = 10, min_days: int = 3, require_profit: bool = False):
        self.ma_period = ma_period
        self.min_days = min_days
        self.require_profit = require_profit

    def should_exit(self, position: Dict, day: int, hist: pd.DataFrame) -> Tuple[bool, str]:
        if day < self.min_days:
            return False, None

        entry_idx = position['entry_idx']
        current_idx = entry_idx + day

        if current_idx >= len(hist):
            return False, None

        current_price = hist.iloc[current_idx]['Close']

        # Calculate MA from entry to current
        start_idx = max(0, current_idx - self.ma_period)
        ma = hist.iloc[start_idx:current_idx + 1]['Close'].mean()

        if current_price < ma:
            if self.require_profit:
                entry_price = position['entry_price']
                pnl_pct = (current_price - entry_price) / entry_price * 100
                if pnl_pct <= 0:
                    return False, None

            return True, f"trend_break(price<MA{self.ma_period})"

        return False, None


class ProfitDecayExit(DynamicExitCondition):
    """Exit if profit decays from peak (not trailing stop, just exit signal)"""
    name = "profit_decay"

    def __init__(self, decay_threshold: float = 0.5, min_peak_profit: float = 3.0):
        self.decay_threshold = decay_threshold  # Exit if profit < threshold * peak_profit
        self.min_peak_profit = min_peak_profit  # Only activate if peak was above this

    def should_exit(self, position: Dict, day: int, hist: pd.DataFrame) -> Tuple[bool, str]:
        entry_idx = position['entry_idx']
        current_idx = entry_idx + day
        entry_price = position['entry_price']

        if current_idx >= len(hist):
            return False, None

        # Calculate peak profit so far
        peak_price = entry_price
        for i in range(entry_idx + 1, current_idx + 1):
            if i < len(hist):
                high = hist.iloc[i]['High']
                if high > peak_price:
                    peak_price = high

        peak_profit = (peak_price - entry_price) / entry_price * 100

        if peak_profit < self.min_peak_profit:
            return False, None

        current_price = hist.iloc[current_idx]['Close']
        current_profit = (current_price - entry_price) / entry_price * 100

        if current_profit < peak_profit * self.decay_threshold:
            return True, f"profit_decay(peak={peak_profit:.1f}%,now={current_profit:.1f}%)"

        return False, None


class TimeDecayExit(DynamicExitCondition):
    """Exit based on time with decaying profit expectation"""
    name = "time_decay"

    def __init__(self, day_thresholds: Dict[int, float] = None):
        # day -> min_profit to continue holding
        self.day_thresholds = day_thresholds or {
            3: 1.0,   # After 3 days, need at least +1% to continue
            5: 2.0,   # After 5 days, need at least +2%
            7: 3.0,   # After 7 days, need at least +3%
            10: 4.0,  # After 10 days, need at least +4%
        }

    def should_exit(self, position: Dict, day: int, hist: pd.DataFrame) -> Tuple[bool, str]:
        entry_idx = position['entry_idx']
        current_idx = entry_idx + day

        if current_idx >= len(hist):
            return False, None

        entry_price = position['entry_price']
        current_price = hist.iloc[current_idx]['Close']
        pnl_pct = (current_price - entry_price) / entry_price * 100

        for threshold_day, min_profit in sorted(self.day_thresholds.items()):
            if day >= threshold_day and pnl_pct < min_profit:
                return True, f"time_decay(day{day},profit={pnl_pct:.1f}%<{min_profit}%)"

        return False, None


# ============================================================
# EXIT CONDITION CONFIGURATIONS
# ============================================================

EXIT_CONFIGS = {
    'BASELINE': {
        'conditions': [],
        'max_hold_fallback': 30,
        'desc': 'No dynamic exit, max hold 30 days',
    },
    'MOMENTUM_ONLY': {
        'conditions': ['momentum_fade'],
        'max_hold_fallback': 14,
        'desc': 'Exit on momentum fade',
    },
    'RSI_ONLY': {
        'conditions': ['rsi_overbought'],
        'max_hold_fallback': 14,
        'desc': 'Exit on RSI overbought + profit',
    },
    'TREND_ONLY': {
        'conditions': ['trend_break'],
        'max_hold_fallback': 14,
        'desc': 'Exit on trend break (price < MA)',
    },
    'PROFIT_DECAY_ONLY': {
        'conditions': ['profit_decay'],
        'max_hold_fallback': 14,
        'desc': 'Exit on profit decay from peak',
    },
    'TIME_DECAY_ONLY': {
        'conditions': ['time_decay'],
        'max_hold_fallback': 14,
        'desc': 'Exit based on time+profit thresholds',
    },
    'VOLATILITY_ONLY': {
        'conditions': ['volatility_spike'],
        'max_hold_fallback': 14,
        'desc': 'Exit on volatility spike',
    },
    'SECTOR_FLIP_ONLY': {
        'conditions': ['sector_flip'],
        'max_hold_fallback': 14,
        'desc': 'Exit on sector regime flip',
    },
    'RSI_MOMENTUM': {
        'conditions': ['rsi_overbought', 'momentum_fade'],
        'max_hold_fallback': 14,
        'desc': 'RSI + Momentum combined',
    },
    'RSI_PROFIT_DECAY': {
        'conditions': ['rsi_overbought', 'profit_decay'],
        'max_hold_fallback': 14,
        'desc': 'RSI + Profit decay',
    },
    'RSI_TIME_DECAY': {
        'conditions': ['rsi_overbought', 'time_decay'],
        'max_hold_fallback': 14,
        'desc': 'RSI + Time decay',
    },
    'FULL_COMBO': {
        'conditions': ['rsi_overbought', 'momentum_fade', 'profit_decay', 'trend_break'],
        'max_hold_fallback': 14,
        'desc': 'All major conditions',
    },
    'SMART_EXIT': {
        'conditions': ['rsi_overbought', 'profit_decay', 'time_decay'],
        'max_hold_fallback': 10,
        'desc': 'RSI + Profit decay + Time decay',
    },
    'CONSERVATIVE': {
        'conditions': ['rsi_overbought', 'volatility_spike'],
        'max_hold_fallback': 7,
        'desc': 'Conservative: RSI + Vol spike, shorter fallback',
    },
}


# v5.6 SL/TP Settings
V56_SLTP = {
    'sl_mult': 1.5, 'tp_mult': 5.0,
    'sl_min': 2.0, 'sl_max': 4.0,
    'tp_min': 6.0, 'tp_max': 12.0,
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

SECTOR_ETFS = {
    'Technology': 'XLK', 'Healthcare': 'XLV', 'Financial': 'XLF',
    'Consumer': 'XLY', 'Energy': 'XLE', 'Industrial': 'XLI',
    'Communication': 'XLC',
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


def get_sector_data(start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    """Get sector ETF data"""
    sector_data = {}
    for sector, etf in SECTOR_ETFS.items():
        try:
            hist = yf.Ticker(etf).history(start=start_date, end=end_date)
            if hist is not None and len(hist) > 20:
                hist['return_20d'] = (hist['Close'] - hist['Close'].shift(20)) / hist['Close'].shift(20) * 100
                sector_data[sector] = hist
        except Exception:
            pass
    return sector_data


def get_sector_regime(sector: str, date: pd.Timestamp, sector_data: Dict) -> str:
    if sector not in sector_data:
        return 'SIDEWAYS'

    df = sector_data[sector]
    dates = df.index[df.index <= date]
    if len(dates) == 0:
        return 'SIDEWAYS'

    row = df.loc[dates[-1]]
    return_20d = row.get('return_20d', 0)

    if pd.isna(return_20d):
        return 'SIDEWAYS'

    if return_20d > 3.0:
        return 'BULL'
    elif return_20d < -3.0:
        return 'BEAR'
    else:
        return 'SIDEWAYS'


def calculate_sl_tp(atr_pct: float) -> Tuple[float, float]:
    sl_raw = atr_pct * V56_SLTP['sl_mult']
    tp_raw = atr_pct * V56_SLTP['tp_mult']
    sl = max(V56_SLTP['sl_min'], min(V56_SLTP['sl_max'], sl_raw))
    tp = max(V56_SLTP['tp_min'], min(V56_SLTP['tp_max'], tp_raw))
    return sl, tp


def create_exit_conditions(condition_names: List[str], sector_data: Dict) -> List[DynamicExitCondition]:
    """Create exit condition instances"""
    conditions = []

    for name in condition_names:
        if name == 'momentum_fade':
            conditions.append(MomentumFadeExit(fade_threshold=0.3, min_days=2))
        elif name == 'sector_flip':
            conditions.append(SectorRegimeFlipExit(sector_data, require_profit=False))
        elif name == 'rsi_overbought':
            conditions.append(RSIOverboughtExit(rsi_threshold=70, min_profit_pct=2.0))
        elif name == 'volatility_spike':
            conditions.append(VolatilitySpikeExit(spike_multiplier=1.5, require_profit=True))
        elif name == 'trend_break':
            conditions.append(TrendBreakExit(ma_period=10, min_days=3, require_profit=False))
        elif name == 'profit_decay':
            conditions.append(ProfitDecayExit(decay_threshold=0.5, min_peak_profit=3.0))
        elif name == 'time_decay':
            conditions.append(TimeDecayExit())

    return conditions


def simulate_trade_dynamic(hist: pd.DataFrame, entry_idx: int, entry_price: float,
                           sl_pct: float, tp_pct: float, position: Dict,
                           exit_conditions: List[DynamicExitCondition],
                           max_hold_fallback: int) -> Dict:
    """
    Simulate trade with dynamic exit conditions.
    SL and TP still apply, but dynamic conditions can exit earlier.
    """
    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100)

    result = {
        'exit_return': 0,
        'exit_type': 'MAX_HOLD',
        'exit_reason': 'max_hold_fallback',
        'exit_day': max_hold_fallback,
        'peak_gain': 0,
        'dynamic_exit_day': None,
    }

    peak_price = entry_price
    peak_gain = 0

    for day in range(1, min(max_hold_fallback + 1, len(hist) - entry_idx)):
        idx = entry_idx + day
        if idx >= len(hist):
            break

        high = hist.iloc[idx]['High']
        low = hist.iloc[idx]['Low']
        close = hist.iloc[idx]['Close']

        # Update peak
        if high > peak_price:
            peak_price = high
            peak_gain = (peak_price - entry_price) / entry_price * 100

        # Check SL first (hard exit)
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_reason'] = 'stop_loss'
            result['exit_day'] = day
            result['peak_gain'] = peak_gain
            break

        # Check TP (hard exit)
        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_reason'] = 'take_profit'
            result['exit_day'] = day
            result['peak_gain'] = peak_gain
            break

        # Check dynamic exit conditions
        for condition in exit_conditions:
            should_exit, reason = condition.should_exit(position, day, hist)
            if should_exit:
                current_return = (close - entry_price) / entry_price * 100
                result['exit_return'] = current_return
                result['exit_type'] = 'DYNAMIC_EXIT'
                result['exit_reason'] = reason
                result['exit_day'] = day
                result['peak_gain'] = peak_gain
                result['dynamic_exit_day'] = day
                return result

        # Update exit at close
        result['exit_return'] = (close - entry_price) / entry_price * 100
        result['peak_gain'] = peak_gain

    return result


def get_all_signals(start_date: str, end_date: str, sector_data: Dict) -> List[Dict]:
    """Get all dip-bounce signals"""
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

            for i in range(50, len(hist) - 35):
                row = hist.iloc[i]
                signal_date = hist.index[i]

                yesterday_ret = row.get('yesterday_return', 0)
                today_ret = row.get('daily_return', 0)
                rsi = row.get('rsi', 50)
                atr_pct = row.get('atr_pct', 3.0)

                if pd.isna(yesterday_ret) or pd.isna(today_ret) or pd.isna(rsi):
                    continue

                # Dip-bounce filter
                if not (yesterday_ret <= -2.0 and today_ret >= 1.0):
                    continue

                # Score calculation (v5.6)
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

                if score < 85:
                    continue

                sector_regime = get_sector_regime(sector, signal_date, sector_data)

                all_signals.append({
                    'symbol': symbol,
                    'sector': sector,
                    'date': signal_date,
                    'entry_idx': i,
                    'entry_price': row['Close'],
                    'score': score,
                    'atr_pct': atr_pct if not pd.isna(atr_pct) else 3.0,
                    'rsi': rsi,
                    'yesterday_return': yesterday_ret,
                    'today_return': today_ret,
                    'sector_regime': sector_regime,
                    'hist': hist,
                })

        except Exception:
            continue

    return all_signals


def run_dynamic_exit_backtest(signals: List[Dict], config_name: str,
                               config: Dict, sector_data: Dict) -> Dict:
    """Run backtest with specific dynamic exit configuration"""
    trades = []
    exit_types = defaultdict(int)
    exit_reasons = defaultdict(int)

    # Create exit conditions
    exit_conditions = create_exit_conditions(config['conditions'], sector_data)
    max_hold = config['max_hold_fallback']

    for signal in signals:
        sl_pct, tp_pct = calculate_sl_tp(signal['atr_pct'])

        result = simulate_trade_dynamic(
            signal['hist'],
            signal['entry_idx'],
            signal['entry_price'],
            sl_pct,
            tp_pct,
            signal,
            exit_conditions,
            max_hold
        )

        trades.append({
            **signal,
            **result,
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
        })
        exit_types[result['exit_type']] += 1
        exit_reasons[result['exit_reason']] += 1

    if not trades:
        return {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    wins = [t for t in trades if t['exit_return'] > 0]
    losses = [t for t in trades if t['exit_return'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
    total_return = sum(t['exit_return'] for t in trades)

    # Dynamic exit specific metrics
    dynamic_exits = [t for t in trades if t['exit_type'] == 'DYNAMIC_EXIT']
    dynamic_exit_wins = [t for t in dynamic_exits if t['exit_return'] > 0]

    avg_hold_days = statistics.mean([t['exit_day'] for t in trades]) if trades else 0

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'total_return': total_return,
        'exit_types': dict(exit_types),
        'exit_reasons': dict(exit_reasons),
        'tp_rate': exit_types['TAKE_PROFIT'] / len(trades) * 100,
        'sl_rate': exit_types['STOP_LOSS'] / len(trades) * 100,
        'dynamic_rate': exit_types['DYNAMIC_EXIT'] / len(trades) * 100,
        'max_hold_rate': exit_types['MAX_HOLD'] / len(trades) * 100,
        'dynamic_win_rate': len(dynamic_exit_wins) / len(dynamic_exits) * 100 if dynamic_exits else 0,
        'avg_hold_days': avg_hold_days,
    }


def analyze_exit_reasons(signals: List[Dict], config: Dict, sector_data: Dict) -> Dict:
    """Detailed analysis of each exit reason's performance"""
    exit_conditions = create_exit_conditions(config['conditions'], sector_data)
    max_hold = config['max_hold_fallback']

    reason_performance = defaultdict(list)

    for signal in signals:
        sl_pct, tp_pct = calculate_sl_tp(signal['atr_pct'])

        result = simulate_trade_dynamic(
            signal['hist'],
            signal['entry_idx'],
            signal['entry_price'],
            sl_pct,
            tp_pct,
            signal,
            exit_conditions,
            max_hold
        )

        reason = result['exit_reason']
        reason_performance[reason].append(result['exit_return'])

    analysis = {}
    for reason, returns in reason_performance.items():
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        win_rate = len(wins) / len(returns) * 100 if returns else 0
        avg_win = statistics.mean(wins) if wins else 0
        avg_loss = statistics.mean(losses) if losses else 0
        expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)

        analysis[reason] = {
            'count': len(returns),
            'win_rate': win_rate,
            'avg_return': statistics.mean(returns) if returns else 0,
            'expectancy': expectancy,
        }

    return analysis


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 85)
    print("DYNAMIC EXIT SYSTEM BACKTEST")
    print("=" * 85)
    print("Baseline: v5.6 (Trail disabled, TP_MULT=5.0)")
    print("Goal: Find intelligent exit conditions vs hardcoded max hold")
    print()

    # Date range
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

    print(f"Period: {start_date} to {end_date}")
    print(f"Stocks: {len(ALL_SYMBOLS)} across {len(STOCKS_BY_SECTOR)} sectors")
    print()

    # Get sector data
    print("Loading sector data...")
    sector_data = get_sector_data(start_date, end_date)
    print(f"Loaded {len(sector_data)} sectors")
    print()

    # Get signals
    print("Collecting signals...")
    all_signals = get_all_signals(start_date, end_date, sector_data)
    print(f"Total signals: {len(all_signals)}")
    print()

    if not all_signals:
        print("No signals found!")
        return

    # ============================================================
    # SECTION A: INDIVIDUAL EXIT CONDITIONS
    # ============================================================
    print("=" * 85)
    print("A. INDIVIDUAL EXIT CONDITIONS COMPARISON")
    print("=" * 85)
    print()

    print(f"{'Config':<20} {'Trades':<7} {'Win%':<7} {'E[R]':<10} {'TP%':<6} {'SL%':<6} {'Dyn%':<6} {'Hold%':<6} {'AvgDay':<7}")
    print("-" * 95)

    results = {}
    for name, config in EXIT_CONFIGS.items():
        result = run_dynamic_exit_backtest(all_signals, name, config, sector_data)
        results[name] = result

        marker = ""
        if name == 'BASELINE':
            marker = " ← baseline"

        print(f"{name:<20} {result['trades']:<7} {result['win_rate']:.1f}%{'':<2} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['tp_rate']:.0f}%{'':<2} "
              f"{result['sl_rate']:.0f}%{'':<2} {result['dynamic_rate']:.0f}%{'':<2} "
              f"{result['max_hold_rate']:.0f}%{'':<2} {result['avg_hold_days']:.1f}{marker}")

    print()

    # Best single condition
    single_conditions = ['MOMENTUM_ONLY', 'RSI_ONLY', 'TREND_ONLY', 'PROFIT_DECAY_ONLY',
                         'TIME_DECAY_ONLY', 'VOLATILITY_ONLY', 'SECTOR_FLIP_ONLY']
    best_single = max(single_conditions, key=lambda k: results[k]['expectancy'])

    print(f"Best Single Condition: {best_single}")
    print(f"  E[R]: {results[best_single]['expectancy']:+.3f}% vs Baseline: {results['BASELINE']['expectancy']:+.3f}%")
    print()

    # ============================================================
    # SECTION B: COMBINED CONDITIONS
    # ============================================================
    print("=" * 85)
    print("B. COMBINED CONDITIONS ANALYSIS")
    print("=" * 85)
    print()

    combined_configs = ['RSI_MOMENTUM', 'RSI_PROFIT_DECAY', 'RSI_TIME_DECAY',
                        'FULL_COMBO', 'SMART_EXIT', 'CONSERVATIVE']

    print(f"{'Config':<20} {'E[R]':<10} {'DynRate%':<10} {'DynWin%':<10} {'Description':<30}")
    print("-" * 85)

    for name in combined_configs:
        result = results[name]
        config = EXIT_CONFIGS[name]
        print(f"{name:<20} {result['expectancy']:+.3f}%{'':<4} {result['dynamic_rate']:.1f}%{'':<5} "
              f"{result['dynamic_win_rate']:.1f}%{'':<5} {config['desc']:<30}")

    print()

    # Best combined
    best_combined = max(combined_configs, key=lambda k: results[k]['expectancy'])
    print(f"Best Combined Config: {best_combined}")
    print(f"  E[R]: {results[best_combined]['expectancy']:+.3f}%")
    print()

    # ============================================================
    # SECTION C: EXIT REASON BREAKDOWN (Best Config)
    # ============================================================
    print("=" * 85)
    print(f"C. EXIT REASON ANALYSIS ({best_combined})")
    print("=" * 85)
    print()

    reason_analysis = analyze_exit_reasons(all_signals, EXIT_CONFIGS[best_combined], sector_data)

    print(f"{'Exit Reason':<30} {'Count':<8} {'Win%':<8} {'AvgRet':<10} {'E[R]':<10}")
    print("-" * 70)

    for reason, stats in sorted(reason_analysis.items(), key=lambda x: -x[1]['count']):
        print(f"{reason:<30} {stats['count']:<8} {stats['win_rate']:.1f}%{'':<3} "
              f"{stats['avg_return']:+.2f}%{'':<4} {stats['expectancy']:+.3f}%")

    print()

    # ============================================================
    # SECTION D: OPTIMAL FALLBACK HOLD ANALYSIS
    # ============================================================
    print("=" * 85)
    print("D. OPTIMAL FALLBACK MAX HOLD")
    print("=" * 85)
    print()

    # Test different fallback values with best conditions
    best_conditions = EXIT_CONFIGS[best_combined]['conditions']
    fallback_tests = [5, 7, 10, 14, 21, 30]

    print(f"Testing with conditions: {best_conditions}")
    print()

    print(f"{'Fallback':<12} {'E[R]':<10} {'TP%':<8} {'Dyn%':<8} {'MaxHold%':<10}")
    print("-" * 50)

    fallback_results = {}
    for fallback in fallback_tests:
        test_config = {
            'conditions': best_conditions,
            'max_hold_fallback': fallback,
        }
        result = run_dynamic_exit_backtest(all_signals, f"FB_{fallback}", test_config, sector_data)
        fallback_results[fallback] = result

        print(f"{fallback} days{'':<5} {result['expectancy']:+.3f}%{'':<4} "
              f"{result['tp_rate']:.1f}%{'':<3} {result['dynamic_rate']:.1f}%{'':<3} "
              f"{result['max_hold_rate']:.1f}%")

    print()

    best_fallback = max(fallback_tests, key=lambda k: fallback_results[k]['expectancy'])
    print(f"Optimal Fallback: {best_fallback} days (E[R]: {fallback_results[best_fallback]['expectancy']:+.3f}%)")
    print()

    # ============================================================
    # SECTION E: FINAL COMPARISON
    # ============================================================
    print("=" * 85)
    print("E. FINAL COMPARISON: STATIC vs DYNAMIC")
    print("=" * 85)
    print()

    # Static configs for comparison
    static_5d = run_dynamic_exit_backtest(all_signals, "STATIC_5D",
                                           {'conditions': [], 'max_hold_fallback': 5}, sector_data)
    static_10d = run_dynamic_exit_backtest(all_signals, "STATIC_10D",
                                            {'conditions': [], 'max_hold_fallback': 10}, sector_data)
    static_30d = run_dynamic_exit_backtest(all_signals, "STATIC_30D",
                                            {'conditions': [], 'max_hold_fallback': 30}, sector_data)

    # Best dynamic
    best_dynamic_config = {
        'conditions': best_conditions,
        'max_hold_fallback': best_fallback,
    }
    best_dynamic = run_dynamic_exit_backtest(all_signals, "BEST_DYNAMIC", best_dynamic_config, sector_data)

    print(f"{'Method':<25} {'E[R]':<10} {'Win%':<8} {'TP%':<7} {'AvgHold':<8}")
    print("-" * 60)
    print(f"{'Static 5d (v5.6)':<25} {static_5d['expectancy']:+.3f}%{'':<4} "
          f"{static_5d['win_rate']:.1f}%{'':<3} {static_5d['tp_rate']:.1f}%{'':<3} "
          f"{static_5d['avg_hold_days']:.1f}d")
    print(f"{'Static 10d':<25} {static_10d['expectancy']:+.3f}%{'':<4} "
          f"{static_10d['win_rate']:.1f}%{'':<3} {static_10d['tp_rate']:.1f}%{'':<3} "
          f"{static_10d['avg_hold_days']:.1f}d")
    print(f"{'Static 30d (no limit)':<25} {static_30d['expectancy']:+.3f}%{'':<4} "
          f"{static_30d['win_rate']:.1f}%{'':<3} {static_30d['tp_rate']:.1f}%{'':<3} "
          f"{static_30d['avg_hold_days']:.1f}d")
    print(f"{'DYNAMIC (Best)':<25} {best_dynamic['expectancy']:+.3f}%{'':<4} "
          f"{best_dynamic['win_rate']:.1f}%{'':<3} {best_dynamic['tp_rate']:.1f}%{'':<3} "
          f"{best_dynamic['avg_hold_days']:.1f}d")
    print()

    improvement = best_dynamic['expectancy'] - static_5d['expectancy']
    print(f"Dynamic vs Static 5d: {improvement:+.3f}% E[R] improvement")
    print()

    # ============================================================
    # SECTION F: SUCCESS CRITERIA
    # ============================================================
    print("=" * 85)
    print("F. SUCCESS CRITERIA")
    print("=" * 85)
    print()

    criteria = [
        ('Dynamic E[R] > Static 5d', best_dynamic['expectancy'] > static_5d['expectancy'],
         f"{best_dynamic['expectancy']:+.3f}% vs {static_5d['expectancy']:+.3f}%"),
        ('Dynamic E[R] > Static 30d', best_dynamic['expectancy'] > static_30d['expectancy'],
         f"{best_dynamic['expectancy']:+.3f}% vs {static_30d['expectancy']:+.3f}%"),
        ('Dynamic triggers >10%', best_dynamic['dynamic_rate'] > 10,
         f"{best_dynamic['dynamic_rate']:.1f}%"),
        ('Dynamic exits are profitable', best_dynamic['dynamic_win_rate'] > 50,
         f"{best_dynamic['dynamic_win_rate']:.1f}% win rate"),
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

    print("┌" + "─" * 75 + "┐")
    print("│  DYNAMIC EXIT SYSTEM RECOMMENDATION" + " " * 38 + "│")
    print("├" + "─" * 75 + "┤")
    print("│" + " " * 75 + "│")
    print(f"│  Best Conditions: {', '.join(best_conditions):<54}│")
    print(f"│  Fallback Max Hold: {best_fallback} days" + " " * 50 + "│")
    print("│" + " " * 75 + "│")
    print(f"│  Performance:" + " " * 61 + "│")
    print(f"│  ├── E[R]: {best_dynamic['expectancy']:+.3f}% (vs Static 5d: {static_5d['expectancy']:+.3f}%)" + " " * 30 + "│")
    print(f"│  ├── Dynamic Exit Rate: {best_dynamic['dynamic_rate']:.1f}%" + " " * 45 + "│")
    print(f"│  ├── Dynamic Win Rate: {best_dynamic['dynamic_win_rate']:.1f}%" + " " * 45 + "│")
    print(f"│  └── Avg Hold Days: {best_dynamic['avg_hold_days']:.1f}" + " " * 49 + "│")
    print("│" + " " * 75 + "│")

    if passed >= 3 and improvement > 0.1:
        decision = "IMPLEMENT DYNAMIC EXIT"
        confidence = 80
    elif passed >= 2 and improvement > 0:
        decision = "CONSIDER DYNAMIC EXIT"
        confidence = 65
    else:
        decision = "KEEP STATIC (longer hold)"
        confidence = 70

    print(f"│  DECISION: {decision:<62}│")
    print(f"│  CONFIDENCE: {confidence}%" + " " * 59 + "│")
    print("└" + "─" * 75 + "┘")
    print()

    # Config output
    if "IMPLEMENT" in decision or "CONSIDER" in decision:
        print("=" * 85)
        print("H. IMPLEMENTATION CONFIG")
        print("=" * 85)
        print()
        print("```python")
        print("DYNAMIC_EXIT_CONFIG = {")
        print(f"    'conditions': {best_conditions},")
        print(f"    'max_hold_fallback': {best_fallback},")
        print()
        print("    # Condition parameters")
        print("    'rsi_overbought_threshold': 70,")
        print("    'rsi_overbought_min_profit': 2.0,")
        print("    'profit_decay_threshold': 0.5,")
        print("    'profit_decay_min_peak': 3.0,")
        print("    'time_decay_thresholds': {3: 1.0, 5: 2.0, 7: 3.0, 10: 4.0},")
        print("}")
        print("```")


if __name__ == '__main__':
    main()
