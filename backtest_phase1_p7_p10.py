#!/usr/bin/env python3
"""
Phase 1 Backtest: P7 (SL/TP) + P10 (Sector Scoring)

Objective: Validate และ optimize P7 และ P10 ใช้ v5.4 เป็น baseline

P7: ATR-based SL/TP multipliers
P10: Sector regime scoring (BULL bonus, BEAR penalty)

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
# P7: SL/TP CONFIGURATIONS
# ============================================================
P7_CONFIGS = {
    'P7-A_TIGHT': {
        'sl_mult': 1.0, 'tp_mult': 2.0,
        'sl_min': 1.5, 'sl_max': 3.0,
        'tp_min': 3.0, 'tp_max': 6.0,
        'desc': 'Tight SL/TP (1:2)',
    },
    'P7-B_CURRENT': {
        'sl_mult': 1.5, 'tp_mult': 3.0,
        'sl_min': 2.0, 'sl_max': 4.0,
        'tp_min': 4.0, 'tp_max': 8.0,
        'desc': 'Current v5.4 (1:2)',
    },
    'P7-C_WIDE': {
        'sl_mult': 2.0, 'tp_mult': 4.0,
        'sl_min': 2.5, 'sl_max': 5.0,
        'tp_min': 5.0, 'tp_max': 10.0,
        'desc': 'Wide SL/TP (1:2)',
    },
    'P7-D_ASYMMETRIC': {
        'sl_mult': 1.5, 'tp_mult': 4.0,
        'sl_min': 2.0, 'sl_max': 4.0,
        'tp_min': 5.0, 'tp_max': 10.0,
        'desc': 'Asymmetric (1:2.67)',
    },
    'P7-E_TIGHT_SL': {
        'sl_mult': 1.0, 'tp_mult': 3.0,
        'sl_min': 1.5, 'sl_max': 3.0,
        'tp_min': 4.0, 'tp_max': 8.0,
        'desc': 'Tight SL only (1:3)',
    },
    'P7-F_WIDE_TP': {
        'sl_mult': 1.5, 'tp_mult': 5.0,
        'sl_min': 2.0, 'sl_max': 4.0,
        'tp_min': 6.0, 'tp_max': 12.0,
        'desc': 'Wide TP only (1:3.33)',
    },
}


# ============================================================
# P10: SECTOR SCORING CONFIGURATIONS
# ============================================================
P10_CONFIGS = {
    'P10-A_SYMMETRIC': {
        'bull_bonus': 5, 'bear_penalty': -5,
        'threshold': 3.0,
        'desc': 'Symmetric (+5/-5)',
    },
    'P10-B_CURRENT': {
        'bull_bonus': 5, 'bear_penalty': -10,
        'threshold': 3.0,
        'desc': 'Current v5.4 (+5/-10)',
    },
    'P10-C_AGGRESSIVE': {
        'bull_bonus': 10, 'bear_penalty': -15,
        'threshold': 3.0,
        'desc': 'Aggressive (+10/-15)',
    },
    'P10-D_RELAXED': {
        'bull_bonus': 3, 'bear_penalty': -5,
        'threshold': 5.0,
        'desc': 'Relaxed (+3/-5, 5%)',
    },
    'P10-E_NO_PENALTY': {
        'bull_bonus': 5, 'bear_penalty': 0,
        'threshold': 3.0,
        'desc': 'No penalty (+5/0)',
    },
    'P10-F_NO_SCORING': {
        'bull_bonus': 0, 'bear_penalty': 0,
        'threshold': 3.0,
        'desc': 'Disabled (0/0)',
    },
}


# Sector ETF mapping
SECTOR_ETFS = {
    'Technology': 'XLK',
    'Healthcare': 'XLV',
    'Financial': 'XLF',
    'Consumer': 'XLY',
    'Energy': 'XLE',
    'Industrial': 'XLI',
    'Communication': 'XLC',
    'Utilities': 'XLU',
    'Materials': 'XLB',
    'RealEstate': 'XLRE',
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


def get_sector_returns(start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    """Get sector ETF data for regime detection"""
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


def get_sector_regime(sector: str, date: pd.Timestamp, sector_data: Dict,
                      threshold: float = 3.0) -> Tuple[str, float]:
    """Get sector regime (BULL/BEAR/SIDEWAYS) for a date"""
    if sector not in sector_data:
        return 'SIDEWAYS', 0.0

    df = sector_data[sector]
    dates = df.index[df.index <= date]
    if len(dates) == 0:
        return 'SIDEWAYS', 0.0

    row = df.loc[dates[-1]]
    return_20d = row.get('return_20d', 0)

    if pd.isna(return_20d):
        return 'SIDEWAYS', 0.0

    if return_20d > threshold:
        return 'BULL', return_20d
    elif return_20d < -threshold:
        return 'BEAR', return_20d
    else:
        return 'SIDEWAYS', return_20d


def calculate_sl_tp(atr_pct: float, config: Dict) -> Tuple[float, float]:
    """Calculate SL and TP based on ATR and config"""
    sl_raw = atr_pct * config['sl_mult']
    tp_raw = atr_pct * config['tp_mult']

    sl = max(config['sl_min'], min(config['sl_max'], sl_raw))
    tp = max(config['tp_min'], min(config['tp_max'], tp_raw))

    return sl, tp


def simulate_trade(hist: pd.DataFrame, entry_idx: int, entry_price: float,
                   sl_pct: float, tp_pct: float, max_days: int = 5) -> Dict:
    """
    Simulate a trade with given SL/TP.
    Returns trade result with detailed metrics.
    """
    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100)

    result = {
        'exit_return': 0,
        'exit_type': 'MAX_HOLD',
        'exit_day': max_days,
        'hit_sl': False,
        'hit_tp': False,
        'max_drawdown': 0,
        'max_profit': 0,
        'would_recover': False,  # Did price recover after SL hit?
    }

    max_dd = 0
    max_profit = 0

    for day in range(1, min(max_days + 1, len(hist) - entry_idx)):
        idx = entry_idx + day
        if idx >= len(hist):
            break

        high = hist.iloc[idx]['High']
        low = hist.iloc[idx]['Low']
        close = hist.iloc[idx]['Close']

        # Track max drawdown and profit
        low_pct = (low - entry_price) / entry_price * 100
        high_pct = (high - entry_price) / entry_price * 100
        max_dd = min(max_dd, low_pct)
        max_profit = max(max_profit, high_pct)

        # Check SL first (conservative)
        if low <= sl_price:
            result['exit_return'] = -sl_pct
            result['exit_type'] = 'STOP_LOSS'
            result['exit_day'] = day
            result['hit_sl'] = True

            # Check if price would have recovered
            for future_day in range(day + 1, min(max_days + 1, len(hist) - entry_idx)):
                future_idx = entry_idx + future_day
                if future_idx < len(hist):
                    future_high = hist.iloc[future_idx]['High']
                    if future_high >= entry_price:
                        result['would_recover'] = True
                        break
            break

        # Check TP
        if high >= tp_price:
            result['exit_return'] = tp_pct
            result['exit_type'] = 'TAKE_PROFIT'
            result['exit_day'] = day
            result['hit_tp'] = True
            break

        # Update exit at close if no SL/TP hit
        result['exit_return'] = (close - entry_price) / entry_price * 100

    result['max_drawdown'] = max_dd
    result['max_profit'] = max_profit

    return result


def get_all_signals(start_date: str, end_date: str, sector_data: Dict) -> List[Dict]:
    """Get all dip-bounce signals with full data"""
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

                # Dip-bounce filter (v5.4)
                if not (yesterday_ret <= -2.0 and today_ret >= 1.0):
                    continue

                # Base score calculation (v5.4 - no RSI/volume penalty)
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

                # Get sector regime
                sector_regime, sector_return = get_sector_regime(sector, signal_date, sector_data)

                all_signals.append({
                    'symbol': symbol,
                    'sector': sector,
                    'date': signal_date,
                    'entry_idx': i,
                    'entry_price': row['Close'],
                    'base_score': score,
                    'atr_pct': atr_pct if not pd.isna(atr_pct) else 3.0,
                    'rsi': rsi,
                    'sector_regime': sector_regime,
                    'sector_return': sector_return,
                    'hist': hist,  # Store for simulation
                })

        except Exception as e:
            continue

    return all_signals


def apply_sector_scoring(signal: Dict, config: Dict) -> int:
    """Apply sector scoring to base score"""
    score = signal['base_score']
    regime = signal['sector_regime']

    if regime == 'BULL':
        score += config['bull_bonus']
    elif regime == 'BEAR':
        score += config['bear_penalty']

    return score


def run_p7_backtest(signals: List[Dict], p7_config: Dict, min_score: int = 85) -> Dict:
    """Run backtest with specific P7 (SL/TP) config"""
    trades = []
    sl_hits = 0
    tp_hits = 0
    false_stops = 0

    for signal in signals:
        if signal['base_score'] < min_score:
            continue

        sl_pct, tp_pct = calculate_sl_tp(signal['atr_pct'], p7_config)

        result = simulate_trade(
            signal['hist'],
            signal['entry_idx'],
            signal['entry_price'],
            sl_pct,
            tp_pct
        )

        trades.append({
            **signal,
            **result,
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
        })

        if result['hit_sl']:
            sl_hits += 1
            if result['would_recover']:
                false_stops += 1
        if result['hit_tp']:
            tp_hits += 1

    if not trades:
        return {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    wins = [t for t in trades if t['exit_return'] > 0]
    losses = [t for t in trades if t['exit_return'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
    total_return = sum(t['exit_return'] for t in trades)

    gross_profit = sum(t['exit_return'] for t in wins)
    gross_loss = abs(sum(t['exit_return'] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    avg_exit_day = statistics.mean([t['exit_day'] for t in trades])

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'total_return': total_return,
        'profit_factor': profit_factor,
        'sl_hit_rate': sl_hits / len(trades) * 100,
        'tp_hit_rate': tp_hits / len(trades) * 100,
        'false_stop_rate': false_stops / len(trades) * 100 if trades else 0,
        'avg_exit_day': avg_exit_day,
    }


def run_p10_backtest(signals: List[Dict], p10_config: Dict, p7_config: Dict,
                     min_score: int = 85) -> Dict:
    """Run backtest with specific P10 (Sector Scoring) config"""
    trades = []
    by_sector_regime = defaultdict(list)

    for signal in signals:
        # Apply sector scoring
        final_score = apply_sector_scoring(signal, p10_config)

        if final_score < min_score:
            continue

        sl_pct, tp_pct = calculate_sl_tp(signal['atr_pct'], p7_config)

        result = simulate_trade(
            signal['hist'],
            signal['entry_idx'],
            signal['entry_price'],
            sl_pct,
            tp_pct
        )

        trade = {
            **signal,
            **result,
            'final_score': final_score,
            'score_adjustment': final_score - signal['base_score'],
        }
        trades.append(trade)
        by_sector_regime[signal['sector_regime']].append(trade)

    if not trades:
        return {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    wins = [t for t in trades if t['exit_return'] > 0]
    losses = [t for t in trades if t['exit_return'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
    total_return = sum(t['exit_return'] for t in trades)

    # By sector regime
    regime_stats = {}
    for regime in ['BULL', 'BEAR', 'SIDEWAYS']:
        regime_trades = by_sector_regime[regime]
        if regime_trades:
            r_wins = [t for t in regime_trades if t['exit_return'] > 0]
            r_losses = [t for t in regime_trades if t['exit_return'] <= 0]
            r_win_rate = len(r_wins) / len(regime_trades) * 100
            r_avg_win = statistics.mean([t['exit_return'] for t in r_wins]) if r_wins else 0
            r_avg_loss = statistics.mean([t['exit_return'] for t in r_losses]) if r_losses else 0
            r_expectancy = (r_win_rate / 100 * r_avg_win) + ((100 - r_win_rate) / 100 * r_avg_loss)
            regime_stats[regime] = {
                'trades': len(regime_trades),
                'win_rate': r_win_rate,
                'expectancy': r_expectancy,
            }
        else:
            regime_stats[regime] = {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'total_return': total_return,
        'regime_stats': regime_stats,
        'bull_pct': len(by_sector_regime['BULL']) / len(trades) * 100,
        'bear_pct': len(by_sector_regime['BEAR']) / len(trades) * 100,
    }


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 75)
    print("PHASE 1 BACKTEST: P7 (SL/TP) + P10 (Sector Scoring)")
    print("=" * 75)
    print()

    # Date range
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

    print(f"Period: {start_date} to {end_date}")
    print(f"Stocks: {len(ALL_SYMBOLS)} across {len(STOCKS_BY_SECTOR)} sectors")
    print()

    # Get sector data
    print("Loading sector ETF data...")
    sector_data = get_sector_returns(start_date, end_date)
    print(f"Loaded {len(sector_data)} sectors")
    print()

    # Get all signals
    print("Collecting signals...")
    all_signals = get_all_signals(start_date, end_date, sector_data)
    print(f"Total signals found: {len(all_signals)}")
    print()

    if not all_signals:
        print("No signals found!")
        return

    # ============================================================
    # SECTION A: P7 SL/TP ANALYSIS
    # ============================================================
    print("=" * 75)
    print("A. P7: SL/TP CONFIGURATION ANALYSIS")
    print("=" * 75)
    print()

    print(f"{'Config':<18} {'Trades':<8} {'Win%':<8} {'AvgWin':<8} {'AvgLoss':<9} {'E[R]':<10} {'PF':<6} {'SL%':<7} {'TP%':<7}")
    print("-" * 90)

    p7_results = {}
    for name, config in P7_CONFIGS.items():
        result = run_p7_backtest(all_signals, config)
        p7_results[name] = result

        marker = " ← current" if name == 'P7-B_CURRENT' else ""
        print(f"{name:<18} {result['trades']:<8} {result['win_rate']:.1f}%{'':<3} "
              f"+{result['avg_win']:.2f}%{'':<2} {result['avg_loss']:.2f}%{'':<3} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['profit_factor']:.2f}{'':<2} "
              f"{result['sl_hit_rate']:.0f}%{'':<3} {result['tp_hit_rate']:.0f}%{marker}")

    print()

    # False stop analysis
    print("False Stop Analysis (SL hit but price recovered):")
    for name, result in p7_results.items():
        print(f"  {name}: {result['false_stop_rate']:.1f}% false stops")
    print()

    # Best P7 config
    best_p7_name = max(p7_results.keys(), key=lambda k: p7_results[k]['expectancy'])
    best_p7 = p7_results[best_p7_name]
    current_p7 = p7_results['P7-B_CURRENT']

    print(f"Best P7 Config: {best_p7_name}")
    print(f"  E[R]: {best_p7['expectancy']:+.3f}% vs Current: {current_p7['expectancy']:+.3f}%")
    print(f"  Improvement: {best_p7['expectancy'] - current_p7['expectancy']:+.3f}%")
    print()

    # ============================================================
    # SECTION B: P10 SECTOR SCORING ANALYSIS
    # ============================================================
    print("=" * 75)
    print("B. P10: SECTOR SCORING CONFIGURATION ANALYSIS")
    print("=" * 75)
    print()

    # Use current P7 config for P10 testing
    p7_baseline = P7_CONFIGS['P7-B_CURRENT']

    print(f"{'Config':<20} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'BULL E[R]':<12} {'BEAR E[R]':<12}")
    print("-" * 75)

    p10_results = {}
    for name, config in P10_CONFIGS.items():
        result = run_p10_backtest(all_signals, config, p7_baseline)
        p10_results[name] = result

        bull_e = result['regime_stats']['BULL']['expectancy']
        bear_e = result['regime_stats']['BEAR']['expectancy']

        marker = " ← current" if name == 'P10-B_CURRENT' else ""
        print(f"{name:<20} {result['trades']:<8} {result['win_rate']:.1f}%{'':<3} "
              f"{result['expectancy']:+.3f}%{'':<4} {bull_e:+.3f}%{'':<6} {bear_e:+.3f}%{marker}")

    print()

    # Sector distribution
    print("Sector Regime Distribution (P10-B_CURRENT):")
    current_p10 = p10_results['P10-B_CURRENT']
    print(f"  BULL sectors: {current_p10['bull_pct']:.1f}%")
    print(f"  BEAR sectors: {current_p10['bear_pct']:.1f}%")
    print(f"  SIDEWAYS: {100 - current_p10['bull_pct'] - current_p10['bear_pct']:.1f}%")
    print()

    # Best P10 config
    best_p10_name = max(p10_results.keys(), key=lambda k: p10_results[k]['expectancy'])
    best_p10 = p10_results[best_p10_name]

    print(f"Best P10 Config: {best_p10_name}")
    print(f"  E[R]: {best_p10['expectancy']:+.3f}% vs Current: {current_p10['expectancy']:+.3f}%")
    print(f"  Improvement: {best_p10['expectancy'] - current_p10['expectancy']:+.3f}%")
    print()

    # ============================================================
    # SECTION C: INTERACTION ANALYSIS
    # ============================================================
    print("=" * 75)
    print("C. P7 + P10 INTERACTION ANALYSIS")
    print("=" * 75)
    print()

    # Test best P7 with all P10 configs
    print("Testing Best P7 with all P10 configs:")
    best_p7_config = P7_CONFIGS[best_p7_name]

    print(f"{'P10 Config':<20} {'E[R] w/ Current P7':<20} {'E[R] w/ Best P7':<20} {'Synergy':<10}")
    print("-" * 70)

    for p10_name, p10_config in P10_CONFIGS.items():
        result_current_p7 = run_p10_backtest(all_signals, p10_config, p7_baseline)
        result_best_p7 = run_p10_backtest(all_signals, p10_config, best_p7_config)

        synergy = result_best_p7['expectancy'] - result_current_p7['expectancy']
        synergy_type = "POSITIVE" if synergy > 0.02 else ("NEGATIVE" if synergy < -0.02 else "NEUTRAL")

        print(f"{p10_name:<20} {result_current_p7['expectancy']:+.3f}%{'':<14} "
              f"{result_best_p7['expectancy']:+.3f}%{'':<14} {synergy_type}")

    print()

    # ============================================================
    # SECTION D: COMBINED VALIDATION
    # ============================================================
    print("=" * 75)
    print("D. COMBINED VALIDATION (v5.5 CANDIDATE)")
    print("=" * 75)
    print()

    # Test combinations
    combinations = [
        ('v5.4 Baseline', 'P7-B_CURRENT', 'P10-B_CURRENT'),
        ('Best P7 + Current P10', best_p7_name, 'P10-B_CURRENT'),
        ('Current P7 + Best P10', 'P7-B_CURRENT', best_p10_name),
        ('Best P7 + Best P10', best_p7_name, best_p10_name),
    ]

    print(f"{'Combination':<30} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'Total%':<10}")
    print("-" * 70)

    combo_results = {}
    for combo_name, p7_name, p10_name in combinations:
        p7_cfg = P7_CONFIGS[p7_name]
        p10_cfg = P10_CONFIGS[p10_name]
        result = run_p10_backtest(all_signals, p10_cfg, p7_cfg)
        combo_results[combo_name] = result

        print(f"{combo_name:<30} {result['trades']:<8} {result['win_rate']:.1f}%{'':<3} "
              f"{result['expectancy']:+.3f}%{'':<4} {result['total_return']:+.1f}%")

    print()

    # ============================================================
    # SECTION E: KEY QUESTIONS ANSWERED
    # ============================================================
    print("=" * 75)
    print("E. KEY QUESTIONS ANSWERED")
    print("=" * 75)
    print()

    print("Q1: SL/TP optimal config?")
    print(f"    Best: {best_p7_name}")
    print(f"    SL_MULT: {P7_CONFIGS[best_p7_name]['sl_mult']}")
    print(f"    TP_MULT: {P7_CONFIGS[best_p7_name]['tp_mult']}")
    print(f"    E[R] improvement: {best_p7['expectancy'] - current_p7['expectancy']:+.3f}%")
    print()

    print("Q2: Sector Scoring optimal config?")
    print(f"    Best: {best_p10_name}")
    print(f"    BULL bonus: {P10_CONFIGS[best_p10_name]['bull_bonus']}")
    print(f"    BEAR penalty: {P10_CONFIGS[best_p10_name]['bear_penalty']}")
    print(f"    E[R] improvement: {best_p10['expectancy'] - current_p10['expectancy']:+.3f}%")
    print()

    print("Q3: Do P7 and P10 interact?")
    baseline = combo_results['v5.4 Baseline']['expectancy']
    best_combo = combo_results['Best P7 + Best P10']['expectancy']
    p7_only = combo_results['Best P7 + Current P10']['expectancy']
    p10_only = combo_results['Current P7 + Best P10']['expectancy']

    individual_sum = (p7_only - baseline) + (p10_only - baseline)
    actual_combined = best_combo - baseline

    if individual_sum != 0:
        synergy_ratio = actual_combined / individual_sum
    else:
        synergy_ratio = 1.0

    synergy_type = "POSITIVE" if synergy_ratio > 1.1 else ("NEGATIVE" if synergy_ratio < 0.9 else "NEUTRAL")
    print(f"    Individual improvements: {individual_sum:+.3f}%")
    print(f"    Combined improvement: {actual_combined:+.3f}%")
    print(f"    Synergy ratio: {synergy_ratio:.2f}x")
    print(f"    Interaction type: {synergy_type}")
    print()

    # ============================================================
    # SECTION F: SUCCESS CRITERIA CHECK
    # ============================================================
    print("=" * 75)
    print("F. SUCCESS CRITERIA CHECK")
    print("=" * 75)
    print()

    v54_baseline = combo_results['v5.4 Baseline']
    v55_candidate = combo_results['Best P7 + Best P10']

    criteria = [
        ('E[R] improved', v55_candidate['expectancy'] > v54_baseline['expectancy'],
         f"{v55_candidate['expectancy']:+.3f}% vs {v54_baseline['expectancy']:+.3f}%"),
        ('Win Rate acceptable', v55_candidate['win_rate'] >= v54_baseline['win_rate'] - 5,
         f"{v55_candidate['win_rate']:.1f}% vs {v54_baseline['win_rate']:.1f}%"),
        ('Trades maintained', v55_candidate['trades'] >= v54_baseline['trades'] * 0.8,
         f"{v55_candidate['trades']} vs {v54_baseline['trades']}"),
        ('P7+P10 no conflict', synergy_ratio >= 0.9, f"Synergy: {synergy_ratio:.2f}x"),
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
    print("=" * 75)
    print("G. FINAL RECOMMENDATION")
    print("=" * 75)
    print()

    print("┌" + "─" * 68 + "┐")
    print("│  PHASE 1 RESULTS — P7 + P10" + " " * 39 + "│")
    print("├" + "─" * 68 + "┤")
    print("│" + " " * 68 + "│")
    print(f"│  P7: SL/TP" + " " * 57 + "│")
    print(f"│  ├── Current: SL {P7_CONFIGS['P7-B_CURRENT']['sl_mult']}x, TP {P7_CONFIGS['P7-B_CURRENT']['tp_mult']}x" + " " * 36 + "│")
    print(f"│  ├── Optimal: SL {P7_CONFIGS[best_p7_name]['sl_mult']}x, TP {P7_CONFIGS[best_p7_name]['tp_mult']}x" + " " * 36 + "│")
    p7_imp = best_p7['expectancy'] - current_p7['expectancy']
    print(f"│  └── Impact: {p7_imp:+.3f}% E[R]" + " " * 44 + "│")
    print("│" + " " * 68 + "│")
    print(f"│  P10: Sector Scoring" + " " * 47 + "│")
    print(f"│  ├── Current: +{P10_CONFIGS['P10-B_CURRENT']['bull_bonus']} / {P10_CONFIGS['P10-B_CURRENT']['bear_penalty']}" + " " * 43 + "│")
    print(f"│  ├── Optimal: +{P10_CONFIGS[best_p10_name]['bull_bonus']} / {P10_CONFIGS[best_p10_name]['bear_penalty']}" + " " * 43 + "│")
    p10_imp = best_p10['expectancy'] - current_p10['expectancy']
    print(f"│  └── Impact: {p10_imp:+.3f}% E[R]" + " " * 44 + "│")
    print("│" + " " * 68 + "│")
    print(f"│  COMBINED (v5.5):" + " " * 50 + "│")
    print(f"│  ├── E[R]: {v55_candidate['expectancy']:+.3f}% (vs v5.4: {v54_baseline['expectancy']:+.3f}%)" + " " * 25 + "│")
    total_imp = v55_candidate['total_return'] - v54_baseline['total_return']
    print(f"│  └── Total: {v55_candidate['total_return']:+.1f}% (vs v5.4: {v54_baseline['total_return']:+.1f}%)" + " " * 22 + "│")
    print("│" + " " * 68 + "│")

    # Decision
    if passed >= 3 and v55_candidate['expectancy'] > v54_baseline['expectancy']:
        decision = "IMPLEMENT v5.5"
        confidence = 80
    elif passed >= 2:
        decision = "CONSIDER v5.5"
        confidence = 60
    else:
        decision = "KEEP v5.4"
        confidence = 70

    print(f"│  DECISION: {decision:<56}│")
    print(f"│  CONFIDENCE: {confidence}%" + " " * 52 + "│")
    print("└" + "─" * 68 + "┘")
    print()

    # Implementation config if approved
    if "IMPLEMENT" in decision or "CONSIDER" in decision:
        print("=" * 75)
        print("H. v5.5 CANDIDATE CONFIGURATION")
        print("=" * 75)
        print()
        print("```python")
        print("V55_CONFIG = {")
        print("    # From v5.4 (keep)")
        print('    "stock_d_filter": True,')
        print('    "bear_dd_exempt": True,')
        print('    "rsi_penalty": None,')
        print('    "volume_penalty": None,')
        print('    "min_score": 85,')
        print('    "vix_regime": None,')
        print()
        print("    # P7: SL/TP (optimized)")
        print(f'    "sl_atr_mult": {P7_CONFIGS[best_p7_name]["sl_mult"]},')
        print(f'    "tp_atr_mult": {P7_CONFIGS[best_p7_name]["tp_mult"]},')
        print(f'    "sl_min": {P7_CONFIGS[best_p7_name]["sl_min"]},')
        print(f'    "sl_max": {P7_CONFIGS[best_p7_name]["sl_max"]},')
        print(f'    "tp_min": {P7_CONFIGS[best_p7_name]["tp_min"]},')
        print(f'    "tp_max": {P7_CONFIGS[best_p7_name]["tp_max"]},')
        print()
        print("    # P10: Sector Scoring (optimized)")
        print(f'    "sector_bull_bonus": {P10_CONFIGS[best_p10_name]["bull_bonus"]},')
        print(f'    "sector_bear_penalty": {P10_CONFIGS[best_p10_name]["bear_penalty"]},')
        print("}")
        print("```")


if __name__ == '__main__':
    main()
