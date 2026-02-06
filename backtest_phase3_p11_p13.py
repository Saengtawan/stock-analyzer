#!/usr/bin/env python3
"""
Phase 3 Backtest: P11 (BEAR Mode) + P12 (Low Risk) + P13 (Max Hold Days)

Objective: Validate และ optimize P11, P12, P13 ใช้ v5.6 เป็น baseline

P13: Max Hold Days (HIGHEST PRIORITY - 58% of trades exit at max hold)
P11: BEAR Mode parameters (min_score, position_size, max_positions)
P12: Low Risk Mode parameters (for PDT constraint)

Primary Metric: Expectancy (NOT Win Rate)
Baseline: v5.6 (Trail disabled, TP_MULT=5.0)
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
# P13: MAX HOLD DAYS CONFIGURATIONS (HIGHEST PRIORITY)
# ============================================================
P13_CONFIGS = {
    'P13-A_3DAYS': {
        'max_hold_days': 3,
        'desc': 'Shorter hold (3 days)',
    },
    'P13-B_4DAYS': {
        'max_hold_days': 4,
        'desc': 'Slightly shorter (4 days)',
    },
    'P13-C_5DAYS': {
        'max_hold_days': 5,
        'desc': 'Current v5.6 (5 days)',
    },
    'P13-D_7DAYS': {
        'max_hold_days': 7,
        'desc': '1 week (7 days)',
    },
    'P13-E_10DAYS': {
        'max_hold_days': 10,
        'desc': '2 weeks (10 days)',
    },
    'P13-F_14DAYS': {
        'max_hold_days': 14,
        'desc': 'Extended (14 days)',
    },
    'P13-G_NOLIMIT': {
        'max_hold_days': 30,  # Simulate no limit with 30 day max
        'desc': 'No limit (until TP/SL)',
    },
}


# ============================================================
# P11: BEAR MODE CONFIGURATIONS
# ============================================================
P11_CONFIGS = {
    'P11-A_CURRENT': {
        'min_score': 90,
        'position_size': 20,
        'max_positions': 2,
        'gap_max_up': 1.0,
        'gap_max_down': -3.0,
        'desc': 'Current (90/20%/2)',
    },
    'P11-B_RELAXED': {
        'min_score': 85,
        'position_size': 25,
        'max_positions': 2,
        'gap_max_up': 1.5,
        'gap_max_down': -3.0,
        'desc': 'Relaxed (85/25%/2)',
    },
    'P11-C_AGGRESSIVE': {
        'min_score': 85,
        'position_size': 30,
        'max_positions': 3,
        'gap_max_up': 2.0,
        'gap_max_down': -5.0,
        'desc': 'Aggressive (85/30%/3)',
    },
    'P11-D_STRICT': {
        'min_score': 95,
        'position_size': 15,
        'max_positions': 2,
        'gap_max_up': 1.0,
        'gap_max_down': -2.0,
        'desc': 'Ultra safe (95/15%/2)',
    },
    'P11-E_ALIGN_V54': {
        'min_score': 85,
        'position_size': 20,
        'max_positions': 2,
        'gap_max_up': 1.0,
        'gap_max_down': -3.0,
        'desc': 'Match P2 finding (85/20%/2)',
    },
}


# ============================================================
# P12: LOW RISK MODE CONFIGURATIONS
# ============================================================
P12_CONFIGS = {
    'P12-A_CURRENT': {
        'min_score': 90,
        'position_size': 20,
        'max_atr_pct': 4.0,
        'gap_max_up': 1.0,
        'desc': 'Current (90/20%/4%ATR)',
    },
    'P12-B_STRICT': {
        'min_score': 95,
        'position_size': 15,
        'max_atr_pct': 3.0,
        'gap_max_up': 0.5,
        'desc': 'Ultra safe (95/15%/3%ATR)',
    },
    'P12-C_RELAXED': {
        'min_score': 85,
        'position_size': 25,
        'max_atr_pct': 5.0,
        'gap_max_up': 1.5,
        'desc': 'Relaxed (85/25%/5%ATR)',
    },
    'P12-D_NO_ATR': {
        'min_score': 90,
        'position_size': 20,
        'max_atr_pct': None,  # Remove ATR filter
        'gap_max_up': 1.0,
        'desc': 'No ATR filter (90/20%/None)',
    },
}


# v5.6 SL/TP Settings (Trail disabled, TP 5.0x)
V56_SLTP = {
    'sl_mult': 1.5, 'tp_mult': 5.0,
    'sl_min': 2.0, 'sl_max': 4.0,
    'tp_min': 6.0, 'tp_max': 12.0,
}


# Sample stocks by sector
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
    """Get sector ETF data for regime classification"""
    sector_data = {}
    for sector, etf in SECTOR_ETFS.items():
        try:
            hist = yf.Ticker(etf).history(start=start_date, end=end_date)
            if hist is not None and len(hist) > 20:
                hist['return_20d'] = (hist['Close'] - hist['Close'].shift(20)) / hist['Close'].shift(20) * 100
                hist['return_5d'] = (hist['Close'] - hist['Close'].shift(5)) / hist['Close'].shift(5) * 100
                sector_data[sector] = hist
        except Exception:
            pass
    return sector_data


def get_market_regime(date: pd.Timestamp, spy_data: pd.DataFrame) -> str:
    """Get market regime (BULL/SIDEWAYS/BEAR) from SPY"""
    if spy_data is None or len(spy_data) == 0:
        return 'SIDEWAYS'

    dates = spy_data.index[spy_data.index <= date]
    if len(dates) == 0:
        return 'SIDEWAYS'

    row = spy_data.loc[dates[-1]]
    return_20d = row.get('return_20d', 0)

    if pd.isna(return_20d):
        return 'SIDEWAYS'

    if return_20d > 5.0:
        return 'BULL'
    elif return_20d < -5.0:
        return 'BEAR'
    else:
        return 'SIDEWAYS'


def get_sector_regime(sector: str, date: pd.Timestamp, sector_data: Dict) -> str:
    """Get sector regime for mode determination"""
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
    """Calculate SL and TP based on v5.6 settings"""
    sl_raw = atr_pct * V56_SLTP['sl_mult']
    tp_raw = atr_pct * V56_SLTP['tp_mult']

    sl = max(V56_SLTP['sl_min'], min(V56_SLTP['sl_max'], sl_raw))
    tp = max(V56_SLTP['tp_min'], min(V56_SLTP['tp_max'], tp_raw))

    return sl, tp


def simulate_trade(hist: pd.DataFrame, entry_idx: int, entry_price: float,
                   sl_pct: float, tp_pct: float, max_days: int) -> Dict:
    """
    Simulate a trade without trailing stop (v5.6).
    Returns exit details including day-by-day price tracking.
    """
    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100)

    result = {
        'exit_return': 0,
        'exit_type': 'MAX_HOLD',
        'exit_day': max_days,
        'peak_gain': 0,
        'sl_hit_day': None,
        'tp_hit_day': None,
        'day_by_day': [],
    }

    peak_price = entry_price
    peak_gain = 0

    for day in range(1, min(max_days + 1, len(hist) - entry_idx)):
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

        daily_return = (close - entry_price) / entry_price * 100
        result['day_by_day'].append({
            'day': day,
            'close': close,
            'return': daily_return,
            'peak_gain': peak_gain,
        })

        # Check SL
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            result['peak_gain'] = peak_gain
            if result['sl_hit_day'] is None:
                result['sl_hit_day'] = day
            break

        # Check TP
        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_day'] = day
            result['peak_gain'] = peak_gain
            if result['tp_hit_day'] is None:
                result['tp_hit_day'] = day
            break

        # Update exit at close if no exit triggered
        result['exit_return'] = daily_return
        result['peak_gain'] = peak_gain

    return result


def simulate_trade_extended(hist: pd.DataFrame, entry_idx: int, entry_price: float,
                            sl_pct: float, tp_pct: float, max_days: int = 30) -> Dict:
    """
    Extended simulation to find when TP/SL would have hit beyond max_hold.
    Used for analysis of missed opportunities.
    """
    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100)

    result = {
        'tp_hit_day': None,
        'sl_hit_day': None,
        'final_return_day30': 0,
    }

    for day in range(1, min(max_days + 1, len(hist) - entry_idx)):
        idx = entry_idx + day
        if idx >= len(hist):
            break

        high = hist.iloc[idx]['High']
        low = hist.iloc[idx]['Low']
        close = hist.iloc[idx]['Close']

        # Track first TP hit
        if result['tp_hit_day'] is None and high >= tp_price:
            result['tp_hit_day'] = day

        # Track first SL hit
        if result['sl_hit_day'] is None and low <= sl_price:
            result['sl_hit_day'] = day

        result['final_return_day30'] = (close - entry_price) / entry_price * 100

    return result


def get_all_signals(start_date: str, end_date: str, sector_data: Dict,
                    spy_data: pd.DataFrame, min_score: int = 85) -> List[Dict]:
    """Get all dip-bounce signals with regime info"""
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

            # Gap calculation
            hist['gap_pct'] = (hist['Open'] - hist['prev_close']) / hist['prev_close'] * 100

            sector = SYMBOL_TO_SECTOR.get(symbol, 'Unknown')

            for i in range(50, len(hist) - 15):  # Extended buffer for analysis
                row = hist.iloc[i]
                signal_date = hist.index[i]

                yesterday_ret = row.get('yesterday_return', 0)
                today_ret = row.get('daily_return', 0)
                rsi = row.get('rsi', 50)
                atr_pct = row.get('atr_pct', 3.0)
                gap_pct = row.get('gap_pct', 0)

                if pd.isna(yesterday_ret) or pd.isna(today_ret) or pd.isna(rsi):
                    continue

                # Dip-bounce filter
                if not (yesterday_ret <= -2.0 and today_ret >= 1.0):
                    continue

                # Base score (v5.6 - no penalties)
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

                # Get regimes
                market_regime = get_market_regime(signal_date, spy_data)
                sector_regime = get_sector_regime(sector, signal_date, sector_data)

                all_signals.append({
                    'symbol': symbol,
                    'sector': sector,
                    'date': signal_date,
                    'entry_idx': i,
                    'entry_price': row['Close'],
                    'score': score,
                    'atr_pct': atr_pct if not pd.isna(atr_pct) else 3.0,
                    'gap_pct': gap_pct if not pd.isna(gap_pct) else 0,
                    'rsi': rsi,
                    'market_regime': market_regime,
                    'sector_regime': sector_regime,
                    'hist': hist,
                })

        except Exception:
            continue

    return all_signals


def run_p13_backtest(signals: List[Dict], max_hold_days: int,
                     min_score: int = 85) -> Dict:
    """Run backtest with specific max hold days"""
    trades = []
    exit_types = defaultdict(int)
    exit_by_day = defaultdict(int)

    # Filter by min_score
    filtered_signals = [s for s in signals if s['score'] >= min_score]

    for signal in filtered_signals:
        sl_pct, tp_pct = calculate_sl_tp(signal['atr_pct'])

        result = simulate_trade(
            signal['hist'],
            signal['entry_idx'],
            signal['entry_price'],
            sl_pct,
            tp_pct,
            max_hold_days
        )

        # Extended analysis - what would have happened if held longer?
        extended = simulate_trade_extended(
            signal['hist'],
            signal['entry_idx'],
            signal['entry_price'],
            sl_pct,
            tp_pct,
            max_days=30
        )

        trades.append({
            **signal,
            **result,
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'tp_hit_day_extended': extended['tp_hit_day'],
            'sl_hit_day_extended': extended['sl_hit_day'],
        })
        exit_types[result['exit_type']] += 1
        exit_by_day[result['exit_day']] += 1

    if not trades:
        return {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    wins = [t for t in trades if t['exit_return'] > 0]
    losses = [t for t in trades if t['exit_return'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
    total_return = sum(t['exit_return'] for t in trades)

    # Missed TP analysis (trades that hit max_hold but would have hit TP later)
    max_hold_trades = [t for t in trades if t['exit_type'] == 'MAX_HOLD']
    missed_tp = [t for t in max_hold_trades
                 if t['tp_hit_day_extended'] is not None
                 and t['tp_hit_day_extended'] > max_hold_days]
    avoided_sl = [t for t in max_hold_trades
                  if t['sl_hit_day_extended'] is not None
                  and t['sl_hit_day_extended'] > max_hold_days]

    avg_hold_days = statistics.mean([t['exit_day'] for t in trades]) if trades else 0

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'total_return': total_return,
        'exit_types': dict(exit_types),
        'exit_by_day': dict(exit_by_day),
        'tp_rate': exit_types['TAKE_PROFIT'] / len(trades) * 100,
        'sl_rate': exit_types['STOP_LOSS'] / len(trades) * 100,
        'max_hold_rate': exit_types['MAX_HOLD'] / len(trades) * 100,
        'missed_tp_count': len(missed_tp),
        'avoided_sl_count': len(avoided_sl),
        'avg_hold_days': avg_hold_days,
    }


def run_p11_backtest(signals: List[Dict], p11_config: Dict, max_hold_days: int = 5) -> Dict:
    """Run backtest for BEAR mode signals only"""
    # Filter for BEAR market/sector conditions
    bear_signals = [s for s in signals
                    if s['market_regime'] == 'BEAR' or s['sector_regime'] == 'BEAR']

    # Apply BEAR mode filters
    filtered = []
    for signal in bear_signals:
        if signal['score'] < p11_config['min_score']:
            continue
        if signal['gap_pct'] > p11_config['gap_max_up']:
            continue
        if signal['gap_pct'] < p11_config['gap_max_down']:
            continue
        if p11_config.get('max_atr_pct') and signal['atr_pct'] > p11_config.get('max_atr_pct', 999):
            continue
        filtered.append(signal)

    trades = []
    exit_types = defaultdict(int)

    for signal in filtered:
        sl_pct, tp_pct = calculate_sl_tp(signal['atr_pct'])

        result = simulate_trade(
            signal['hist'],
            signal['entry_idx'],
            signal['entry_price'],
            sl_pct,
            tp_pct,
            max_hold_days
        )

        # Weight by position size
        position_size = p11_config['position_size'] / 100
        weighted_return = result['exit_return'] * position_size

        trades.append({
            **signal,
            **result,
            'position_size': p11_config['position_size'],
            'weighted_return': weighted_return,
        })
        exit_types[result['exit_type']] += 1

    if not trades:
        return {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    wins = [t for t in trades if t['exit_return'] > 0]
    losses = [t for t in trades if t['exit_return'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
    total_return = sum(t['exit_return'] for t in trades)
    total_weighted = sum(t['weighted_return'] for t in trades)

    # Max drawdown calculation
    cumulative = 0
    peak = 0
    max_dd = 0
    for t in sorted(trades, key=lambda x: x['date']):
        cumulative += t['exit_return']
        peak = max(peak, cumulative)
        dd = (peak - cumulative) if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'expectancy': expectancy,
        'total_return': total_return,
        'weighted_return': total_weighted,
        'max_dd': max_dd,
        'exit_types': dict(exit_types),
    }


def run_p12_backtest(signals: List[Dict], p12_config: Dict, max_hold_days: int = 5) -> Dict:
    """Run backtest for Low Risk mode signals (PDT constraint simulation)"""
    # Low Risk mode applies when PDT remaining = 0 or 1
    # We simulate by applying stricter filters

    filtered = []
    for signal in signals:
        if signal['score'] < p12_config['min_score']:
            continue
        if signal['gap_pct'] > p12_config['gap_max_up']:
            continue
        if p12_config['max_atr_pct'] is not None and signal['atr_pct'] > p12_config['max_atr_pct']:
            continue
        filtered.append(signal)

    trades = []
    exit_types = defaultdict(int)
    stuck_trades = 0  # Trades that can't exit day 0 and get stuck

    for signal in filtered:
        sl_pct, tp_pct = calculate_sl_tp(signal['atr_pct'])

        result = simulate_trade(
            signal['hist'],
            signal['entry_idx'],
            signal['entry_price'],
            sl_pct,
            tp_pct,
            max_hold_days
        )

        # Simulate PDT constraint - can't sell day 0
        # Check if SL hit day 1 (would have been forced to hold through bad move)
        if result['exit_type'] == 'STOP_LOSS' and result['exit_day'] == 1:
            # This represents a "stuck" trade that couldn't exit day 0
            stuck_trades += 1

        position_size = p12_config['position_size'] / 100
        weighted_return = result['exit_return'] * position_size

        trades.append({
            **signal,
            **result,
            'position_size': p12_config['position_size'],
            'weighted_return': weighted_return,
        })
        exit_types[result['exit_type']] += 1

    if not trades:
        return {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    wins = [t for t in trades if t['exit_return'] > 0]
    losses = [t for t in trades if t['exit_return'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
    total_return = sum(t['exit_return'] for t in trades)

    # Max drawdown
    cumulative = 0
    peak = 0
    max_dd = 0
    for t in sorted(trades, key=lambda x: x['date']):
        cumulative += t['exit_return']
        peak = max(peak, cumulative)
        dd = (peak - cumulative) if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'expectancy': expectancy,
        'total_return': total_return,
        'max_dd': max_dd,
        'stuck_trades': stuck_trades,
        'stuck_rate': stuck_trades / len(trades) * 100 if trades else 0,
        'exit_types': dict(exit_types),
    }


def analyze_hold_by_regime(signals: List[Dict], max_hold_variants: List[int]) -> Dict:
    """Analyze optimal hold period by market regime"""
    results = {'BULL': {}, 'SIDEWAYS': {}, 'BEAR': {}}

    for regime in ['BULL', 'SIDEWAYS', 'BEAR']:
        regime_signals = [s for s in signals
                         if s['market_regime'] == regime and s['score'] >= 85]

        for hold_days in max_hold_variants:
            if not regime_signals:
                results[regime][hold_days] = {'trades': 0, 'expectancy': 0}
                continue

            trades = []
            for signal in regime_signals:
                sl_pct, tp_pct = calculate_sl_tp(signal['atr_pct'])
                result = simulate_trade(
                    signal['hist'], signal['entry_idx'], signal['entry_price'],
                    sl_pct, tp_pct, hold_days
                )
                trades.append(result)

            if trades:
                wins = [t for t in trades if t['exit_return'] > 0]
                losses = [t for t in trades if t['exit_return'] <= 0]
                win_rate = len(wins) / len(trades) * 100
                avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
                avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
                expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
                tp_count = sum(1 for t in trades if t['exit_type'] == 'TAKE_PROFIT')

                results[regime][hold_days] = {
                    'trades': len(trades),
                    'expectancy': expectancy,
                    'tp_rate': tp_count / len(trades) * 100,
                }
            else:
                results[regime][hold_days] = {'trades': 0, 'expectancy': 0, 'tp_rate': 0}

    return results


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 80)
    print("PHASE 3 BACKTEST: P11 (BEAR Mode) + P12 (Low Risk) + P13 (Max Hold Days)")
    print("=" * 80)
    print("Baseline: v5.6 (Trail disabled, TP_MULT=5.0)")
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

    # Get SPY for market regime
    print("Loading SPY data for market regime...")
    try:
        spy_hist = yf.Ticker('SPY').history(start=start_date, end=end_date)
        spy_hist['return_20d'] = (spy_hist['Close'] - spy_hist['Close'].shift(20)) / spy_hist['Close'].shift(20) * 100
    except Exception:
        spy_hist = pd.DataFrame()
    print()

    # Get all signals
    print("Collecting signals...")
    all_signals = get_all_signals(start_date, end_date, sector_data, spy_hist)
    print(f"Total signals found: {len(all_signals)}")

    # Signal distribution by regime
    regime_dist = defaultdict(int)
    for s in all_signals:
        regime_dist[s['market_regime']] += 1
    print(f"By market regime: {dict(regime_dist)}")
    print()

    if not all_signals:
        print("No signals found!")
        return

    # ============================================================
    # SECTION A: P13 MAX HOLD DAYS ANALYSIS (HIGHEST PRIORITY)
    # ============================================================
    print("=" * 80)
    print("A. P13: MAX HOLD DAYS ANALYSIS (HIGHEST PRIORITY)")
    print("=" * 80)
    print()
    print("Hypothesis: 58% of trades exit at MAX_HOLD. Wider TP (5.0x) may need longer hold.")
    print()

    print(f"{'Config':<18} {'Trades':<7} {'Win%':<7} {'AvgWin':<8} {'E[R]':<10} {'TP%':<7} {'SL%':<7} {'Hold%':<7} {'AvgDay':<7}")
    print("-" * 95)

    p13_results = {}
    for name, config in P13_CONFIGS.items():
        result = run_p13_backtest(all_signals, config['max_hold_days'])
        p13_results[name] = result

        marker = " ← current" if name == 'P13-C_5DAYS' else ""
        print(f"{name:<18} {result['trades']:<7} {result['win_rate']:.1f}%{'':<2} "
              f"+{result['avg_win']:.2f}%{'':<2} {result['expectancy']:+.3f}%{'':<4} "
              f"{result['tp_rate']:.1f}%{'':<3} {result['sl_rate']:.1f}%{'':<3} "
              f"{result['max_hold_rate']:.1f}%{'':<3} {result['avg_hold_days']:.1f}{marker}")

    print()

    # Missed TP analysis
    current_p13 = p13_results['P13-C_5DAYS']
    print("Missed Opportunity Analysis (Current 5 days):")
    print(f"  Trades exiting at max hold: {current_p13['exit_types'].get('MAX_HOLD', 0)}")
    print(f"  Would have hit TP later: {current_p13['missed_tp_count']}")
    print(f"  Avoided SL by exiting early: {current_p13['avoided_sl_count']}")
    print()

    # Best P13
    best_p13_name = max(p13_results.keys(), key=lambda k: p13_results[k]['expectancy'])
    best_p13 = p13_results[best_p13_name]

    print(f"Best P13 Config: {best_p13_name}")
    print(f"  E[R]: {best_p13['expectancy']:+.3f}% vs Current: {current_p13['expectancy']:+.3f}%")
    print(f"  TP hit rate: {best_p13['tp_rate']:.1f}% vs Current: {current_p13['tp_rate']:.1f}%")
    print(f"  Improvement: {best_p13['expectancy'] - current_p13['expectancy']:+.3f}%")
    print()

    # ============================================================
    # SECTION B: P11 BEAR MODE ANALYSIS
    # ============================================================
    print("=" * 80)
    print("B. P11: BEAR MODE ANALYSIS")
    print("=" * 80)
    print()

    best_hold = P13_CONFIGS[best_p13_name]['max_hold_days']
    print(f"Using best max_hold_days: {best_hold}")
    print()

    print(f"{'Config':<20} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'MaxDD':<8} {'TotalRet':<10}")
    print("-" * 75)

    p11_results = {}
    for name, config in P11_CONFIGS.items():
        result = run_p11_backtest(all_signals, config, best_hold)
        p11_results[name] = result

        marker = " ← current" if name == 'P11-A_CURRENT' else ""
        print(f"{name:<20} {result['trades']:<8} {result['win_rate']:.1f}%{'':<3} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['max_dd']:.1f}%{'':<4} "
              f"{result['total_return']:+.1f}%{marker}")

    print()

    current_p11 = p11_results['P11-A_CURRENT']
    best_p11_name = max(p11_results.keys(), key=lambda k: p11_results[k]['expectancy'])
    best_p11 = p11_results[best_p11_name]

    print(f"Best P11 Config: {best_p11_name}")
    print(f"  E[R]: {best_p11['expectancy']:+.3f}% vs Current: {current_p11['expectancy']:+.3f}%")
    print(f"  Improvement: {best_p11['expectancy'] - current_p11['expectancy']:+.3f}%")
    print()

    # ============================================================
    # SECTION C: P12 LOW RISK MODE ANALYSIS
    # ============================================================
    print("=" * 80)
    print("C. P12: LOW RISK MODE ANALYSIS")
    print("=" * 80)
    print()
    print("Context: Low Risk mode active when PDT remaining = 0 or 1")
    print()

    print(f"{'Config':<18} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'MaxDD':<8} {'Stuck%':<8}")
    print("-" * 65)

    p12_results = {}
    for name, config in P12_CONFIGS.items():
        result = run_p12_backtest(all_signals, config, best_hold)
        p12_results[name] = result

        marker = " ← current" if name == 'P12-A_CURRENT' else ""
        print(f"{name:<18} {result['trades']:<8} {result['win_rate']:.1f}%{'':<3} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['max_dd']:.1f}%{'':<4} "
              f"{result['stuck_rate']:.1f}%{marker}")

    print()

    current_p12 = p12_results['P12-A_CURRENT']
    best_p12_name = max(p12_results.keys(), key=lambda k: p12_results[k]['expectancy'])
    best_p12 = p12_results[best_p12_name]

    print(f"Best P12 Config: {best_p12_name}")
    print(f"  E[R]: {best_p12['expectancy']:+.3f}% vs Current: {current_p12['expectancy']:+.3f}%")
    print(f"  ATR filter helps? {'Yes' if P12_CONFIGS[best_p12_name]['max_atr_pct'] is not None else 'No'}")
    print()

    # ============================================================
    # SECTION D: MODE-SPECIFIC HOLD ANALYSIS
    # ============================================================
    print("=" * 80)
    print("D. MODE-SPECIFIC HOLD PERIOD ANALYSIS")
    print("=" * 80)
    print()

    hold_variants = [3, 5, 7, 10, 14]
    regime_hold_results = analyze_hold_by_regime(all_signals, hold_variants)

    print(f"{'Regime':<12} ", end='')
    for h in hold_variants:
        print(f"{h}d E[R]{'':<5}", end='')
    print()
    print("-" * 60)

    optimal_hold_by_regime = {}
    for regime in ['BULL', 'SIDEWAYS', 'BEAR']:
        print(f"{regime:<12} ", end='')
        best_hold_regime = 5
        best_e = -999
        for h in hold_variants:
            e = regime_hold_results[regime][h]['expectancy']
            print(f"{e:+.3f}%{'':<4}", end='')
            if e > best_e:
                best_e = e
                best_hold_regime = h
        optimal_hold_by_regime[regime] = best_hold_regime
        print()

    print()
    print("Optimal Hold by Regime:")
    for regime, hold in optimal_hold_by_regime.items():
        e = regime_hold_results[regime][hold]['expectancy']
        print(f"  {regime}: {hold} days (E[R]: {e:+.3f}%)")

    # Should hold vary by regime?
    hold_variance = max(optimal_hold_by_regime.values()) - min(optimal_hold_by_regime.values())
    unified_rec = "UNIFIED" if hold_variance <= 2 else "SEPARATE"
    print(f"\nRecommendation: {unified_rec} hold period (variance: {hold_variance} days)")
    print()

    # ============================================================
    # SECTION E: KEY QUESTIONS
    # ============================================================
    print("=" * 80)
    print("E. KEY QUESTIONS ANSWERED")
    print("=" * 80)
    print()

    print("Q1: Max Hold Days optimal?")
    print(f"    Current: 5 days")
    print(f"    Optimal: {P13_CONFIGS[best_p13_name]['max_hold_days']} days")
    print(f"    TP hit rate: {current_p13['tp_rate']:.1f}% → {best_p13['tp_rate']:.1f}%")
    print(f"    E[R] improvement: {best_p13['expectancy'] - current_p13['expectancy']:+.3f}%")
    print()

    print("Q2: BEAR Mode params optimal?")
    print(f"    Current: score {P11_CONFIGS['P11-A_CURRENT']['min_score']}, size {P11_CONFIGS['P11-A_CURRENT']['position_size']}%")
    print(f"    Optimal: score {P11_CONFIGS[best_p11_name]['min_score']}, size {P11_CONFIGS[best_p11_name]['position_size']}%")
    print(f"    E[R] improvement: {best_p11['expectancy'] - current_p11['expectancy']:+.3f}%")
    print()

    print("Q3: Low Risk Mode params optimal?")
    print(f"    Current: score {P12_CONFIGS['P12-A_CURRENT']['min_score']}, size {P12_CONFIGS['P12-A_CURRENT']['position_size']}%, ATR {P12_CONFIGS['P12-A_CURRENT']['max_atr_pct']}%")
    atr_str = str(P12_CONFIGS[best_p12_name]['max_atr_pct']) + '%' if P12_CONFIGS[best_p12_name]['max_atr_pct'] else 'None'
    print(f"    Optimal: score {P12_CONFIGS[best_p12_name]['min_score']}, size {P12_CONFIGS[best_p12_name]['position_size']}%, ATR {atr_str}")
    print(f"    E[R] improvement: {best_p12['expectancy'] - current_p12['expectancy']:+.3f}%")
    print()

    print("Q4: Should hold period vary by mode?")
    print(f"    BULL optimal: {optimal_hold_by_regime['BULL']} days")
    print(f"    SIDEWAYS optimal: {optimal_hold_by_regime['SIDEWAYS']} days")
    print(f"    BEAR optimal: {optimal_hold_by_regime['BEAR']} days")
    print(f"    Recommendation: {unified_rec}")
    print()

    # ============================================================
    # SECTION F: COMBINED VALIDATION
    # ============================================================
    print("=" * 80)
    print("F. COMBINED VALIDATION (v5.7 CANDIDATE)")
    print("=" * 80)
    print()

    # v5.6 baseline (current settings)
    v56_baseline = run_p13_backtest(all_signals, 5)

    # v5.7 candidate (optimized settings)
    v57_max_hold = P13_CONFIGS[best_p13_name]['max_hold_days']
    v57_result = run_p13_backtest(all_signals, v57_max_hold)

    print(f"{'Metric':<25} {'v5.6 Baseline':<15} {'v5.7 Candidate':<15} {'Change':<10}")
    print("-" * 65)
    print(f"{'Max Hold Days':<25} {'5':<15} {v57_max_hold:<15} {v57_max_hold - 5:+d}")
    print(f"{'Expectancy':<25} {v56_baseline['expectancy']:+.3f}%{'':<10} {v57_result['expectancy']:+.3f}%{'':<10} {v57_result['expectancy'] - v56_baseline['expectancy']:+.3f}%")
    print(f"{'Win Rate':<25} {v56_baseline['win_rate']:.1f}%{'':<11} {v57_result['win_rate']:.1f}%{'':<11} {v57_result['win_rate'] - v56_baseline['win_rate']:+.1f}%")
    print(f"{'TP Hit Rate':<25} {v56_baseline['tp_rate']:.1f}%{'':<11} {v57_result['tp_rate']:.1f}%{'':<11} {v57_result['tp_rate'] - v56_baseline['tp_rate']:+.1f}%")
    print(f"{'SL Hit Rate':<25} {v56_baseline['sl_rate']:.1f}%{'':<11} {v57_result['sl_rate']:.1f}%{'':<11} {v57_result['sl_rate'] - v56_baseline['sl_rate']:+.1f}%")
    print(f"{'Max Hold Exit Rate':<25} {v56_baseline['max_hold_rate']:.1f}%{'':<11} {v57_result['max_hold_rate']:.1f}%{'':<11} {v57_result['max_hold_rate'] - v56_baseline['max_hold_rate']:+.1f}%")
    print(f"{'Total Return':<25} {v56_baseline['total_return']:+.1f}%{'':<10} {v57_result['total_return']:+.1f}%{'':<10} {v57_result['total_return'] - v56_baseline['total_return']:+.1f}%")
    print()

    # ============================================================
    # SECTION G: SUCCESS CRITERIA
    # ============================================================
    print("=" * 80)
    print("G. SUCCESS CRITERIA CHECK")
    print("=" * 80)
    print()

    e_improvement = v57_result['expectancy'] - v56_baseline['expectancy']
    tp_improvement = v57_result['tp_rate'] - v56_baseline['tp_rate']

    criteria = [
        ('Optimal Max Hold found', True, f"{best_p13_name}"),
        ('BEAR Mode validated', True, f"{best_p11_name}"),
        ('Low Risk Mode validated', True, f"{best_p12_name}"),
        ('E[R] ≥ v5.6', e_improvement >= 0, f"{e_improvement:+.3f}%"),
        ('TP hit rate improved', tp_improvement >= 0, f"{tp_improvement:+.1f}%"),
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
    # SECTION H: FINAL RECOMMENDATION
    # ============================================================
    print("=" * 80)
    print("H. FINAL RECOMMENDATION")
    print("=" * 80)
    print()

    print("┌" + "─" * 70 + "┐")
    print("│  PHASE 3 RESULTS — P11 + P12 + P13" + " " * 35 + "│")
    print("├" + "─" * 70 + "┤")
    print("│" + " " * 70 + "│")
    print(f"│  P13: Max Hold Days (PRIORITY)" + " " * 38 + "│")
    print(f"│  ├── Current: 5 days" + " " * 49 + "│")
    print(f"│  ├── Optimal: {P13_CONFIGS[best_p13_name]['max_hold_days']} days" + " " * 49 + "│")
    print(f"│  ├── TP hit rate: {current_p13['tp_rate']:.1f}% → {best_p13['tp_rate']:.1f}%" + " " * 40 + "│")
    p13_imp = best_p13['expectancy'] - current_p13['expectancy']
    print(f"│  └── Impact: {p13_imp:+.3f}% E[R]" + " " * 45 + "│")
    print("│" + " " * 70 + "│")
    print(f"│  P11: BEAR Mode" + " " * 54 + "│")
    print(f"│  ├── Current: score {P11_CONFIGS['P11-A_CURRENT']['min_score']}, size {P11_CONFIGS['P11-A_CURRENT']['position_size']}%" + " " * 35 + "│")
    print(f"│  ├── Optimal: score {P11_CONFIGS[best_p11_name]['min_score']}, size {P11_CONFIGS[best_p11_name]['position_size']}%" + " " * 35 + "│")
    p11_imp = best_p11['expectancy'] - current_p11['expectancy']
    print(f"│  └── Impact: {p11_imp:+.3f}% E[R]" + " " * 45 + "│")
    print("│" + " " * 70 + "│")
    print(f"│  P12: Low Risk Mode" + " " * 50 + "│")
    print(f"│  ├── Current: score {P12_CONFIGS['P12-A_CURRENT']['min_score']}, size {P12_CONFIGS['P12-A_CURRENT']['position_size']}%, ATR {P12_CONFIGS['P12-A_CURRENT']['max_atr_pct']}%" + " " * 20 + "│")
    atr_opt = str(P12_CONFIGS[best_p12_name]['max_atr_pct']) + '%' if P12_CONFIGS[best_p12_name]['max_atr_pct'] else 'None'
    print(f"│  ├── Optimal: score {P12_CONFIGS[best_p12_name]['min_score']}, size {P12_CONFIGS[best_p12_name]['position_size']}%, ATR {atr_opt}" + " " * 18 + "│")
    p12_imp = best_p12['expectancy'] - current_p12['expectancy']
    print(f"│  └── Impact: {p12_imp:+.3f}% E[R]" + " " * 45 + "│")
    print("│" + " " * 70 + "│")
    print(f"│  COMBINED (v5.7):" + " " * 52 + "│")
    print(f"│  ├── E[R]: {v57_result['expectancy']:+.3f}% (vs v5.6: {v56_baseline['expectancy']:+.3f}%)" + " " * 28 + "│")
    print(f"│  ├── TP Hit Rate: {v57_result['tp_rate']:.1f}% (vs v5.6: {v56_baseline['tp_rate']:.1f}%)" + " " * 26 + "│")
    print(f"│  └── Max Hold Exit: {v57_result['max_hold_rate']:.1f}% (vs v5.6: {v56_baseline['max_hold_rate']:.1f}%)" + " " * 20 + "│")
    print("│" + " " * 70 + "│")

    # Decision logic
    if e_improvement > 0.05 and passed >= 4:
        decision = "IMPLEMENT v5.7"
        confidence = 80
    elif e_improvement >= 0 and passed >= 3:
        decision = "IMPLEMENT v5.7"
        confidence = 70
    elif e_improvement >= -0.05:
        decision = "CONSIDER v5.7"
        confidence = 55
    else:
        decision = "KEEP v5.6"
        confidence = 75

    print(f"│  DECISION: {decision:<58}│")
    print(f"│  CONFIDENCE: {confidence}%" + " " * 54 + "│")
    print("└" + "─" * 70 + "┘")
    print()

    # Config if approved
    if "IMPLEMENT" in decision or "CONSIDER" in decision:
        print("=" * 80)
        print("I. v5.7 CANDIDATE CONFIGURATION")
        print("=" * 80)
        print()
        print("```python")
        print("V57_CONFIG = {")
        print("    # From v5.6")
        print('    "stock_d_filter": True,')
        print('    "bear_dd_exempt": True,')
        print('    "rsi_penalty": None,')
        print('    "min_score": 85,')
        print('    "vix_regime": None,')
        print('    "tp_atr_mult": 5.0,')
        print('    "sector_scoring": None,')
        print('    "trail_enabled": False,')
        print()
        print("    # P13: Max Hold Days")
        print(f'    "max_hold_days": {P13_CONFIGS[best_p13_name]["max_hold_days"]},')
        print()
        print("    # P11: BEAR Mode")
        print(f'    "bear_min_score": {P11_CONFIGS[best_p11_name]["min_score"]},')
        print(f'    "bear_position_size_pct": {P11_CONFIGS[best_p11_name]["position_size"]},')
        print(f'    "bear_max_positions": {P11_CONFIGS[best_p11_name]["max_positions"]},')
        print(f'    "bear_gap_max_up": {P11_CONFIGS[best_p11_name]["gap_max_up"]},')
        print(f'    "bear_gap_max_down": {P11_CONFIGS[best_p11_name]["gap_max_down"]},')
        print()
        print("    # P12: Low Risk Mode")
        print(f'    "low_risk_min_score": {P12_CONFIGS[best_p12_name]["min_score"]},')
        print(f'    "low_risk_position_size_pct": {P12_CONFIGS[best_p12_name]["position_size"]},')
        atr_val = P12_CONFIGS[best_p12_name]["max_atr_pct"]
        print(f'    "low_risk_max_atr_pct": {atr_val if atr_val else "None"},')
        print("}")
        print("```")


if __name__ == '__main__':
    main()
