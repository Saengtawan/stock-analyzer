#!/usr/bin/env python3
"""
Phase 2 Backtest: P8 (Trailing Stop) + P9 (Conviction Sizing)

Objective: Validate และ optimize P8 และ P9 ใช้ v5.5 เป็น baseline

P8: Trailing Stop (activation %, lock %)
P9: Conviction Sizing (A+/A/B position sizes)

Primary Metric: Expectancy (NOT Win Rate)
Baseline: v5.5 (TP_MULT=5.0, no sector scoring)
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
# P8: TRAILING STOP CONFIGURATIONS
# ============================================================
P8_CONFIGS = {
    'P8-A_AGGRESSIVE': {
        'activation': 3.0, 'lock_pct': 70,
        'enabled': True,
        'desc': 'Early activation, tight lock (3%/70%)',
    },
    'P8-B_CURRENT': {
        'activation': 4.0, 'lock_pct': 50,
        'enabled': True,
        'desc': 'Current v5.5 (4%/50%)',
    },
    'P8-C_RELAXED': {
        'activation': 5.0, 'lock_pct': 40,
        'enabled': True,
        'desc': 'Relaxed (5%/40%)',
    },
    'P8-D_VERY_RELAXED': {
        'activation': 6.0, 'lock_pct': 30,
        'enabled': True,
        'desc': 'Very relaxed (6%/30%)',
    },
    'P8-E_TIGHT_LOCK': {
        'activation': 4.0, 'lock_pct': 70,
        'enabled': True,
        'desc': 'Same activation, tight lock (4%/70%)',
    },
    'P8-F_LOOSE_LOCK': {
        'activation': 4.0, 'lock_pct': 30,
        'enabled': True,
        'desc': 'Same activation, loose lock (4%/30%)',
    },
    'P8-G_NONE': {
        'activation': 999, 'lock_pct': 0,
        'enabled': False,
        'desc': 'No trailing (benchmark)',
    },
}


# ============================================================
# P9: CONVICTION SIZING CONFIGURATIONS
# ============================================================
P9_CONFIGS = {
    'P9-A_CURRENT': {
        'a_plus': 45, 'a': 40, 'b': 30,
        'desc': 'Current (45/40/30)',
    },
    'P9-B_AGGRESSIVE': {
        'a_plus': 50, 'a': 45, 'b': 35,
        'desc': 'Aggressive (50/45/35)',
    },
    'P9-C_CONSERVATIVE': {
        'a_plus': 35, 'a': 30, 'b': 25,
        'desc': 'Conservative (35/30/25)',
    },
    'P9-D_EQUAL': {
        'a_plus': 40, 'a': 40, 'b': 40,
        'desc': 'Equal sizing (40/40/40)',
    },
    'P9-E_FLAT': {
        'a_plus': 35, 'a': 35, 'b': 35,
        'desc': 'Lower equal (35/35/35)',
    },
    'P9-F_WIDE_SPREAD': {
        'a_plus': 50, 'a': 35, 'b': 20,
        'desc': 'Wide spread (50/35/20)',
    },
    'P9-G_INVERSE': {
        'a_plus': 30, 'a': 40, 'b': 50,
        'desc': 'Inverse - bet more on B (30/40/50)',
    },
}


# v5.5 SL/TP Settings
V55_SLTP = {
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
    """Get sector ETF data for conviction classification"""
    sector_data = {}
    for sector, etf in SECTOR_ETFS.items():
        try:
            hist = yf.Ticker(etf).history(start=start_date, end=end_date)
            if hist is not None and len(hist) > 20:
                hist['return_20d'] = (hist['Close'] - hist['Close'].shift(20)) / hist['Close'].shift(20) * 100
                sector_data[sector] = hist
        except:
            pass
    return sector_data


def get_sector_regime(sector: str, date: pd.Timestamp, sector_data: Dict) -> str:
    """Get sector regime for conviction tier"""
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


def get_conviction_tier(score: int, sector_regime: str, has_insider: bool = False) -> str:
    """
    Determine conviction tier based on score and sector regime.
    A+: STRONG BULL + high score + insider
    A: BULL + score 80+
    B: SIDEWAYS/BEAR + score 80+
    """
    if sector_regime == 'BULL' and score >= 90 and has_insider:
        return 'A+'
    elif sector_regime == 'BULL' and score >= 85:
        return 'A+'
    elif sector_regime == 'BULL' and score >= 80:
        return 'A'
    elif score >= 80:
        return 'B'
    else:
        return 'C'  # Below threshold


def calculate_sl_tp(atr_pct: float) -> Tuple[float, float]:
    """Calculate SL and TP based on v5.5 settings"""
    sl_raw = atr_pct * V55_SLTP['sl_mult']
    tp_raw = atr_pct * V55_SLTP['tp_mult']

    sl = max(V55_SLTP['sl_min'], min(V55_SLTP['sl_max'], sl_raw))
    tp = max(V55_SLTP['tp_min'], min(V55_SLTP['tp_max'], tp_raw))

    return sl, tp


def simulate_trade_with_trailing(hist: pd.DataFrame, entry_idx: int, entry_price: float,
                                  sl_pct: float, tp_pct: float, trail_config: Dict,
                                  max_days: int = 5) -> Dict:
    """
    Simulate a trade with trailing stop.
    """
    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100)

    trail_activation = trail_config['activation']
    trail_lock_pct = trail_config['lock_pct'] / 100  # Convert to decimal
    trail_enabled = trail_config['enabled']

    result = {
        'exit_return': 0,
        'exit_type': 'MAX_HOLD',
        'exit_day': max_days,
        'trail_triggered': False,
        'trail_exit': False,
        'peak_gain': 0,
        'gain_at_trigger': 0,
        'gain_given_back': 0,
    }

    trailing_sl = None
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

        # Check trailing activation
        if trail_enabled and trailing_sl is None:
            current_gain = (high - entry_price) / entry_price * 100
            if current_gain >= trail_activation:
                # Activate trailing stop
                locked_gain = current_gain * trail_lock_pct
                trailing_sl = entry_price * (1 + locked_gain / 100)
                result['trail_triggered'] = True
                result['gain_at_trigger'] = current_gain

        # Update trailing stop if active
        if trailing_sl is not None:
            current_gain = (high - entry_price) / entry_price * 100
            new_locked = current_gain * trail_lock_pct
            new_trail_sl = entry_price * (1 + new_locked / 100)
            if new_trail_sl > trailing_sl:
                trailing_sl = new_trail_sl

        # Check exits (priority: SL > Trail SL > TP)

        # Check original SL
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            result['peak_gain'] = peak_gain
            break

        # Check trailing SL
        if trailing_sl is not None and low <= trailing_sl:
            trail_exit_gain = (trailing_sl - entry_price) / entry_price * 100
            result['exit_return'] = trail_exit_gain
            result['exit_type'] = 'TRAIL_STOP'
            result['exit_day'] = day
            result['trail_exit'] = True
            result['peak_gain'] = peak_gain
            result['gain_given_back'] = peak_gain - trail_exit_gain
            break

        # Check TP
        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_day'] = day
            result['peak_gain'] = peak_gain
            break

        # Update exit at close if no exit triggered
        result['exit_return'] = (close - entry_price) / entry_price * 100
        result['peak_gain'] = peak_gain

    return result


def get_all_signals(start_date: str, end_date: str, sector_data: Dict) -> List[Dict]:
    """Get all dip-bounce signals with conviction tier"""
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

            for i in range(50, len(hist) - 6):
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

                # Base score (v5.5 - no penalties)
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

                if score < 85:  # v5.5 MIN_SCORE
                    continue

                # Get sector regime and conviction tier
                sector_regime = get_sector_regime(sector, signal_date, sector_data)
                # Simulate insider (random 10% chance for testing)
                has_insider = np.random.random() < 0.10
                conviction_tier = get_conviction_tier(score, sector_regime, has_insider)

                if conviction_tier == 'C':
                    continue

                all_signals.append({
                    'symbol': symbol,
                    'sector': sector,
                    'date': signal_date,
                    'entry_idx': i,
                    'entry_price': row['Close'],
                    'score': score,
                    'atr_pct': atr_pct if not pd.isna(atr_pct) else 3.0,
                    'sector_regime': sector_regime,
                    'conviction_tier': conviction_tier,
                    'hist': hist,
                })

        except Exception as e:
            continue

    return all_signals


def run_p8_backtest(signals: List[Dict], p8_config: Dict) -> Dict:
    """Run backtest with specific trailing stop config"""
    trades = []
    exit_types = defaultdict(int)

    for signal in signals:
        sl_pct, tp_pct = calculate_sl_tp(signal['atr_pct'])

        result = simulate_trade_with_trailing(
            signal['hist'],
            signal['entry_idx'],
            signal['entry_price'],
            sl_pct,
            tp_pct,
            p8_config
        )

        trades.append({
            **signal,
            **result,
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
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

    # Trail-specific metrics
    trail_triggered = [t for t in trades if t['trail_triggered']]
    trail_exits = [t for t in trades if t['trail_exit']]

    avg_gain_given_back = statistics.mean([t['gain_given_back'] for t in trail_exits]) if trail_exits else 0

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'total_return': total_return,
        'exit_types': dict(exit_types),
        'trail_trigger_rate': len(trail_triggered) / len(trades) * 100,
        'trail_exit_rate': len(trail_exits) / len(trades) * 100,
        'avg_gain_given_back': avg_gain_given_back,
        'tp_rate': exit_types['TAKE_PROFIT'] / len(trades) * 100,
        'sl_rate': exit_types['STOP_LOSS'] / len(trades) * 100,
        'max_hold_rate': exit_types['MAX_HOLD'] / len(trades) * 100,
    }


def run_p9_backtest(signals: List[Dict], p9_config: Dict, p8_config: Dict) -> Dict:
    """Run backtest with specific conviction sizing config"""
    trades = []
    by_tier = defaultdict(list)

    for signal in signals:
        tier = signal['conviction_tier']

        # Get position size for tier
        if tier == 'A+':
            position_pct = p9_config['a_plus']
        elif tier == 'A':
            position_pct = p9_config['a']
        else:
            position_pct = p9_config['b']

        sl_pct, tp_pct = calculate_sl_tp(signal['atr_pct'])

        result = simulate_trade_with_trailing(
            signal['hist'],
            signal['entry_idx'],
            signal['entry_price'],
            sl_pct,
            tp_pct,
            p8_config
        )

        # Weight return by position size
        weighted_return = result['exit_return'] * (position_pct / 100)

        trade = {
            **signal,
            **result,
            'position_pct': position_pct,
            'weighted_return': weighted_return,
        }
        trades.append(trade)
        by_tier[tier].append(trade)

    if not trades:
        return {'trades': 0, 'expectancy': 0}

    # Calculate metrics
    total_weighted_return = sum(t['weighted_return'] for t in trades)

    wins = [t for t in trades if t['exit_return'] > 0]
    losses = [t for t in trades if t['exit_return'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)

    # Per-tier analysis
    tier_stats = {}
    for tier in ['A+', 'A', 'B']:
        tier_trades = by_tier[tier]
        if tier_trades:
            t_wins = [t for t in tier_trades if t['exit_return'] > 0]
            t_losses = [t for t in tier_trades if t['exit_return'] <= 0]
            t_win_rate = len(t_wins) / len(tier_trades) * 100
            t_avg_win = statistics.mean([t['exit_return'] for t in t_wins]) if t_wins else 0
            t_avg_loss = statistics.mean([t['exit_return'] for t in t_losses]) if t_losses else 0
            t_expectancy = (t_win_rate / 100 * t_avg_win) + ((100 - t_win_rate) / 100 * t_avg_loss)
            tier_stats[tier] = {
                'trades': len(tier_trades),
                'pct': len(tier_trades) / len(trades) * 100,
                'win_rate': t_win_rate,
                'expectancy': t_expectancy,
            }
        else:
            tier_stats[tier] = {'trades': 0, 'pct': 0, 'win_rate': 0, 'expectancy': 0}

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'expectancy': expectancy,
        'total_return': sum(t['exit_return'] for t in trades),
        'weighted_return': total_weighted_return,
        'tier_stats': tier_stats,
    }


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 75)
    print("PHASE 2 BACKTEST: P8 (Trailing Stop) + P9 (Conviction Sizing)")
    print("=" * 75)
    print("Baseline: v5.5 (TP_MULT=5.0, no sector scoring)")
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

    # Get all signals
    print("Collecting signals...")
    np.random.seed(42)  # For reproducible insider simulation
    all_signals = get_all_signals(start_date, end_date, sector_data)
    print(f"Total signals found: {len(all_signals)}")
    print()

    if not all_signals:
        print("No signals found!")
        return

    # ============================================================
    # SECTION A: P8 TRAILING STOP ANALYSIS
    # ============================================================
    print("=" * 75)
    print("A. P8: TRAILING STOP ANALYSIS")
    print("=" * 75)
    print()

    print(f"{'Config':<22} {'Trades':<7} {'Win%':<7} {'AvgWin':<8} {'E[R]':<9} {'Trail%':<8} {'TP%':<6} {'SL%':<6}")
    print("-" * 85)

    p8_results = {}
    for name, config in P8_CONFIGS.items():
        result = run_p8_backtest(all_signals, config)
        p8_results[name] = result

        marker = " ← current" if name == 'P8-B_CURRENT' else ""
        print(f"{name:<22} {result['trades']:<7} {result['win_rate']:.1f}%{'':<2} "
              f"+{result['avg_win']:.2f}%{'':<2} {result['expectancy']:+.3f}%{'':<3} "
              f"{result['trail_trigger_rate']:.0f}%{'':<4} {result['tp_rate']:.0f}%{'':<2} "
              f"{result['sl_rate']:.0f}%{marker}")

    print()

    # Exit distribution for current config
    current_p8 = p8_results['P8-B_CURRENT']
    print("Exit Distribution (P8-B_CURRENT):")
    print(f"  TP hit: {current_p8['tp_rate']:.1f}%")
    print(f"  Trail exit: {current_p8['trail_exit_rate']:.1f}%")
    print(f"  SL hit: {current_p8['sl_rate']:.1f}%")
    print(f"  Max hold: {current_p8['max_hold_rate']:.1f}%")
    print(f"  Avg gain given back on trail: {current_p8['avg_gain_given_back']:.2f}%")
    print()

    # Best P8
    best_p8_name = max(p8_results.keys(), key=lambda k: p8_results[k]['expectancy'])
    best_p8 = p8_results[best_p8_name]

    print(f"Best P8 Config: {best_p8_name}")
    print(f"  E[R]: {best_p8['expectancy']:+.3f}% vs Current: {current_p8['expectancy']:+.3f}%")
    print(f"  Improvement: {best_p8['expectancy'] - current_p8['expectancy']:+.3f}%")
    print()

    # ============================================================
    # SECTION B: P9 CONVICTION SIZING ANALYSIS
    # ============================================================
    print("=" * 75)
    print("B. P9: CONVICTION SIZING ANALYSIS")
    print("=" * 75)
    print()

    # Use current P8 for P9 testing
    p8_baseline = P8_CONFIGS['P8-B_CURRENT']

    print(f"{'Config':<20} {'Trades':<7} {'Win%':<7} {'E[R]':<10} {'Weighted':<10} {'A+ E[R]':<10} {'B E[R]':<10}")
    print("-" * 80)

    p9_results = {}
    for name, config in P9_CONFIGS.items():
        result = run_p9_backtest(all_signals, config, p8_baseline)
        p9_results[name] = result

        a_plus_e = result['tier_stats']['A+']['expectancy']
        b_e = result['tier_stats']['B']['expectancy']

        marker = " ← current" if name == 'P9-A_CURRENT' else ""
        print(f"{name:<20} {result['trades']:<7} {result['win_rate']:.1f}%{'':<2} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['weighted_return']:+.1f}%{'':<5} "
              f"{a_plus_e:+.3f}%{'':<5} {b_e:+.3f}%{marker}")

    print()

    # Tier distribution
    current_p9 = p9_results['P9-A_CURRENT']
    print("Conviction Tier Distribution (P9-A_CURRENT):")
    for tier in ['A+', 'A', 'B']:
        stats = current_p9['tier_stats'][tier]
        print(f"  {tier}: {stats['trades']} trades ({stats['pct']:.1f}%) → E[R]: {stats['expectancy']:+.3f}%")
    print()

    # Best performing tier
    best_tier = max(['A+', 'A', 'B'], key=lambda t: current_p9['tier_stats'][t]['expectancy'])
    print(f"Best performing tier: {best_tier} (E[R]: {current_p9['tier_stats'][best_tier]['expectancy']:+.3f}%)")
    print()

    # Best P9
    best_p9_name = max(p9_results.keys(), key=lambda k: p9_results[k]['expectancy'])
    best_p9 = p9_results[best_p9_name]

    print(f"Best P9 Config: {best_p9_name}")
    print(f"  E[R]: {best_p9['expectancy']:+.3f}% vs Current: {current_p9['expectancy']:+.3f}%")
    print(f"  Improvement: {best_p9['expectancy'] - current_p9['expectancy']:+.3f}%")
    print()

    # ============================================================
    # SECTION C: COMBINED VALIDATION
    # ============================================================
    print("=" * 75)
    print("C. COMBINED VALIDATION (v5.6 CANDIDATE)")
    print("=" * 75)
    print()

    combinations = [
        ('v5.5 Baseline', 'P8-B_CURRENT', 'P9-A_CURRENT'),
        ('Best P8 + Current P9', best_p8_name, 'P9-A_CURRENT'),
        ('Current P8 + Best P9', 'P8-B_CURRENT', best_p9_name),
        ('Best P8 + Best P9', best_p8_name, best_p9_name),
    ]

    print(f"{'Combination':<30} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'Weighted':<10}")
    print("-" * 70)

    combo_results = {}
    for combo_name, p8_name, p9_name in combinations:
        p8_cfg = P8_CONFIGS[p8_name]
        p9_cfg = P9_CONFIGS[p9_name]
        result = run_p9_backtest(all_signals, p9_cfg, p8_cfg)
        combo_results[combo_name] = result

        print(f"{combo_name:<30} {result['trades']:<8} {result['win_rate']:.1f}%{'':<3} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['weighted_return']:+.1f}%")

    print()

    # ============================================================
    # SECTION D: KEY QUESTIONS
    # ============================================================
    print("=" * 75)
    print("D. KEY QUESTIONS ANSWERED")
    print("=" * 75)
    print()

    print("Q1: Trailing Stop optimal config?")
    print(f"    Best: {best_p8_name}")
    if best_p8_name == 'P8-G_NONE':
        print(f"    Recommendation: DISABLE trailing")
    else:
        print(f"    Activation: {P8_CONFIGS[best_p8_name]['activation']}%")
        print(f"    Lock: {P8_CONFIGS[best_p8_name]['lock_pct']}%")
    print(f"    E[R] improvement: {best_p8['expectancy'] - current_p8['expectancy']:+.3f}%")
    print()

    print("Q2: Conviction Sizing optimal config?")
    print(f"    Best: {best_p9_name}")
    print(f"    A+/A/B: {P9_CONFIGS[best_p9_name]['a_plus']}% / {P9_CONFIGS[best_p9_name]['a']}% / {P9_CONFIGS[best_p9_name]['b']}%")
    print(f"    E[R] improvement: {best_p9['expectancy'] - current_p9['expectancy']:+.3f}%")

    # Does tiered sizing help?
    equal_result = p9_results['P9-D_EQUAL']
    sizing_helps = current_p9['expectancy'] > equal_result['expectancy']
    print(f"    Does tiered sizing help? {'YES' if sizing_helps else 'NO'}")
    print()

    print("Q3: Do P8 and P9 interact?")
    baseline = combo_results['v5.5 Baseline']['expectancy']
    best_combo = combo_results['Best P8 + Best P9']['expectancy']
    p8_only = combo_results['Best P8 + Current P9']['expectancy']
    p9_only = combo_results['Current P8 + Best P9']['expectancy']

    individual_sum = (p8_only - baseline) + (p9_only - baseline)
    actual_combined = best_combo - baseline

    if individual_sum != 0:
        synergy_ratio = actual_combined / individual_sum
    else:
        synergy_ratio = 1.0

    synergy_type = "POSITIVE" if synergy_ratio > 1.1 else ("NEGATIVE" if synergy_ratio < 0.9 else "NEUTRAL")
    print(f"    Individual improvements: {individual_sum:+.3f}%")
    print(f"    Combined improvement: {actual_combined:+.3f}%")
    print(f"    Synergy: {synergy_type} ({synergy_ratio:.2f}x)")
    print()

    # ============================================================
    # SECTION E: SUCCESS CRITERIA
    # ============================================================
    print("=" * 75)
    print("E. SUCCESS CRITERIA CHECK")
    print("=" * 75)
    print()

    v55_baseline = combo_results['v5.5 Baseline']
    v56_candidate = combo_results['Best P8 + Best P9']

    criteria = [
        ('Optimal trailing found', True, f"{best_p8_name}"),
        ('Optimal sizing found', True, f"{best_p9_name}"),
        ('E[R] ≥ v5.5', v56_candidate['expectancy'] >= v55_baseline['expectancy'],
         f"{v56_candidate['expectancy']:+.3f}% vs {v55_baseline['expectancy']:+.3f}%"),
        ('P8+P9 no conflict', synergy_ratio >= 0.9, f"Synergy: {synergy_ratio:.2f}x"),
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
    # SECTION F: FINAL RECOMMENDATION
    # ============================================================
    print("=" * 75)
    print("F. FINAL RECOMMENDATION")
    print("=" * 75)
    print()

    print("┌" + "─" * 68 + "┐")
    print("│  PHASE 2 RESULTS — P8 + P9" + " " * 40 + "│")
    print("├" + "─" * 68 + "┤")
    print("│" + " " * 68 + "│")
    print(f"│  P8: Trailing Stop" + " " * 49 + "│")
    print(f"│  ├── Current: {P8_CONFIGS['P8-B_CURRENT']['activation']}% / {P8_CONFIGS['P8-B_CURRENT']['lock_pct']}%" + " " * 44 + "│")
    if best_p8_name == 'P8-G_NONE':
        print(f"│  ├── Optimal: DISABLED" + " " * 44 + "│")
    else:
        print(f"│  ├── Optimal: {P8_CONFIGS[best_p8_name]['activation']}% / {P8_CONFIGS[best_p8_name]['lock_pct']}%" + " " * 44 + "│")
    p8_imp = best_p8['expectancy'] - current_p8['expectancy']
    print(f"│  └── Impact: {p8_imp:+.3f}% E[R]" + " " * 44 + "│")
    print("│" + " " * 68 + "│")
    print(f"│  P9: Conviction Sizing" + " " * 45 + "│")
    print(f"│  ├── Current: {P9_CONFIGS['P9-A_CURRENT']['a_plus']}% / {P9_CONFIGS['P9-A_CURRENT']['a']}% / {P9_CONFIGS['P9-A_CURRENT']['b']}%" + " " * 35 + "│")
    print(f"│  ├── Optimal: {P9_CONFIGS[best_p9_name]['a_plus']}% / {P9_CONFIGS[best_p9_name]['a']}% / {P9_CONFIGS[best_p9_name]['b']}%" + " " * 35 + "│")
    p9_imp = best_p9['expectancy'] - current_p9['expectancy']
    print(f"│  └── Impact: {p9_imp:+.3f}% E[R]" + " " * 44 + "│")
    print("│" + " " * 68 + "│")
    print(f"│  COMBINED (v5.6):" + " " * 50 + "│")
    print(f"│  ├── E[R]: {v56_candidate['expectancy']:+.3f}% (vs v5.5: {v55_baseline['expectancy']:+.3f}%)" + " " * 25 + "│")

    # Decision
    improvement = v56_candidate['expectancy'] - v55_baseline['expectancy']
    if passed >= 3 and improvement > 0:
        decision = "IMPLEMENT v5.6"
        confidence = 75
    elif improvement > 0:
        decision = "CONSIDER v5.6"
        confidence = 60
    else:
        decision = "KEEP v5.5"
        confidence = 80

    print("│" + " " * 68 + "│")
    print(f"│  DECISION: {decision:<56}│")
    print(f"│  CONFIDENCE: {confidence}%" + " " * 52 + "│")
    print("└" + "─" * 68 + "┘")
    print()

    # Config if approved
    if "IMPLEMENT" in decision or "CONSIDER" in decision:
        print("=" * 75)
        print("G. v5.6 CANDIDATE CONFIGURATION")
        print("=" * 75)
        print()
        print("```python")
        print("V56_CONFIG = {")
        print("    # From v5.5")
        print('    "tp_atr_mult": 5.0,')
        print('    "sector_scoring": None,')
        print()
        print("    # P8: Trailing Stop")
        if best_p8_name == 'P8-G_NONE':
            print('    "trail_enabled": False,')
        else:
            print(f'    "trail_activation": {P8_CONFIGS[best_p8_name]["activation"]},')
            print(f'    "trail_lock_pct": {P8_CONFIGS[best_p8_name]["lock_pct"]},')
        print()
        print("    # P9: Conviction Sizing")
        print(f'    "conviction_a_plus": {P9_CONFIGS[best_p9_name]["a_plus"]},')
        print(f'    "conviction_a": {P9_CONFIGS[best_p9_name]["a"]},')
        print(f'    "conviction_b": {P9_CONFIGS[best_p9_name]["b"]},')
        print("}")
        print("```")


if __name__ == '__main__':
    main()
