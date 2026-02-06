#!/usr/bin/env python3
"""
Regime-Based Strategy Switching Backtest
Compare different regime detection, strategy assignment, and transition rules
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================

SECTOR_ETFS = {
    'Technology': 'XLK',
    'Healthcare': 'XLV',
    'Financials': 'XLF',
    'Consumer Discretionary': 'XLY',
    'Communication Services': 'XLC',
    'Industrials': 'XLI',
    'Consumer Staples': 'XLP',
    'Energy': 'XLE',
    'Utilities': 'XLU',
    'Real Estate': 'XLRE',
    'Materials': 'XLB'
}

STOCK_UNIVERSE = {
    'Technology': ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'AMD', 'CRM', 'ADBE', 'ORCL', 'CSCO', 'INTC'],
    'Healthcare': ['UNH', 'JNJ', 'LLY', 'PFE', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'BMY'],
    'Financials': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'SCHW', 'AXP', 'C', 'USB'],
    'Consumer Discretionary': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TJX', 'LOW', 'BKNG', 'CMG'],
    'Communication Services': ['GOOGL', 'META', 'NFLX', 'DIS', 'CMCSA', 'VZ', 'T', 'TMUS', 'CHTR', 'EA'],
    'Industrials': ['CAT', 'GE', 'UNP', 'HON', 'UPS', 'BA', 'RTX', 'DE', 'LMT', 'MMM'],
    'Consumer Staples': ['PG', 'KO', 'PEP', 'COST', 'WMT', 'PM', 'MO', 'CL', 'MDLZ', 'KHC'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'HAL'],
    'Utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'WEC'],
    'Real Estate': ['PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'SPG', 'O', 'WELL', 'DLR', 'AVB'],
    'Materials': ['LIN', 'APD', 'SHW', 'FCX', 'ECL', 'NEM', 'NUE', 'DD', 'DOW', 'PPG']
}

STOCK_TO_SECTOR = {}
for sector, stocks in STOCK_UNIVERSE.items():
    for stock in stocks:
        STOCK_TO_SECTOR[stock] = sector

# ============================================================================
# DATA CLASSES
# ============================================================================

class Regime(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"

@dataclass
class Trade:
    symbol: str
    sector: str
    strategy: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl_pct: float
    hold_days: int
    exit_reason: str
    regime: str
    regime_at_entry: str

@dataclass
class RegimeState:
    current: Regime
    pending: Optional[Regime] = None
    pending_days: int = 0
    days_since_switch: int = 0
    switch_count: int = 0

# ============================================================================
# DATA DOWNLOAD
# ============================================================================

def download_data(period='1y'):
    print("📥 Downloading data...")

    etf_symbols = list(SECTOR_ETFS.values()) + ['SPY', '^VIX']
    etf_data = yf.download(etf_symbols, period=period, progress=False)

    all_stocks = list(STOCK_TO_SECTOR.keys())
    stock_data = yf.download(all_stocks, period=period, progress=False)

    print(f"✅ ETF data: {len(etf_data)} days")
    print(f"✅ Stock data: {len(stock_data)} days")

    return etf_data, stock_data

def prepare_market_data(etf_data: pd.DataFrame) -> pd.DataFrame:
    """Prepare SPY and VIX data with all indicators"""
    spy_close = etf_data[('Close', 'SPY')]

    df = pd.DataFrame(index=spy_close.index)
    df['spy_close'] = spy_close
    df['spy_sma_20'] = spy_close.rolling(20).mean()
    df['spy_sma_50'] = spy_close.rolling(50).mean()
    df['spy_sma_200'] = spy_close.rolling(200).mean()
    df['spy_return_1d'] = spy_close.pct_change() * 100
    df['spy_return_5d'] = spy_close.pct_change(5) * 100
    df['spy_return_20d'] = spy_close.pct_change(20) * 100

    # RSI
    delta = spy_close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['spy_rsi'] = 100 - (100 / (1 + rs))

    # VIX
    try:
        df['vix'] = etf_data[('Close', '^VIX')]
    except:
        df['vix'] = 20  # default

    return df

# ============================================================================
# REGIME DETECTION METHODS
# ============================================================================

def regime_rd_a_sma_cross(row) -> Regime:
    """RD-A: SPY SMA Cross"""
    spy = row['spy_close']
    sma50 = row['spy_sma_50']
    sma200 = row['spy_sma_200']

    if pd.isna(sma200):
        return Regime.NEUTRAL

    if spy > sma50 and sma50 > sma200:
        return Regime.BULL
    elif spy < sma50 and sma50 < sma200:
        return Regime.BEAR
    else:
        return Regime.NEUTRAL

def regime_rd_b_return_20d(row) -> Regime:
    """RD-B: SPY 20d Return"""
    ret = row['spy_return_20d']
    if pd.isna(ret):
        return Regime.NEUTRAL

    if ret > 5:
        return Regime.BULL
    elif ret < -5:
        return Regime.BEAR
    else:
        return Regime.NEUTRAL

def regime_rd_c_vix(row) -> Regime:
    """RD-C: VIX Level"""
    vix = row['vix']
    if pd.isna(vix):
        return Regime.NEUTRAL

    if vix < 15:
        return Regime.BULL
    elif vix > 25:
        return Regime.BEAR
    else:
        return Regime.NEUTRAL

def regime_rd_d_rsi(row) -> Regime:
    """RD-D: SPY RSI"""
    rsi = row['spy_rsi']
    if pd.isna(rsi):
        return Regime.NEUTRAL

    if rsi > 60:
        return Regime.BULL
    elif rsi < 40:
        return Regime.BEAR
    else:
        return Regime.NEUTRAL

def regime_rd_e_composite(row) -> Regime:
    """RD-E: Composite Score"""
    score = 0

    if not pd.isna(row['spy_sma_50']) and row['spy_close'] > row['spy_sma_50']:
        score += 1
    else:
        score -= 1

    if not pd.isna(row['spy_return_20d']) and row['spy_return_20d'] > 0:
        score += 1
    else:
        score -= 1

    if not pd.isna(row['vix']) and row['vix'] < 20:
        score += 1
    else:
        score -= 1

    if not pd.isna(row['spy_rsi']) and row['spy_rsi'] > 50:
        score += 1
    else:
        score -= 1

    if score >= 2:
        return Regime.BULL
    elif score <= -2:
        return Regime.BEAR
    else:
        return Regime.NEUTRAL

def regime_rd_f_trend_momentum(row) -> Regime:
    """RD-F: Trend + Momentum"""
    if pd.isna(row['spy_sma_50']) or pd.isna(row['spy_return_5d']):
        return Regime.NEUTRAL

    trend_up = row['spy_close'] > row['spy_sma_50']
    momentum_strong = abs(row['spy_return_5d']) > 2

    if trend_up and momentum_strong and row['spy_return_5d'] > 0:
        return Regime.BULL
    elif not trend_up and momentum_strong and row['spy_return_5d'] < 0:
        return Regime.BEAR
    else:
        return Regime.NEUTRAL

REGIME_DETECTORS = {
    'RD-A_sma_cross': regime_rd_a_sma_cross,
    'RD-B_return_20d': regime_rd_b_return_20d,
    'RD-C_vix': regime_rd_c_vix,
    'RD-D_rsi': regime_rd_d_rsi,
    'RD-E_composite': regime_rd_e_composite,
    'RD-F_trend_mom': regime_rd_f_trend_momentum,
}

# ============================================================================
# STRATEGY ASSIGNMENT
# ============================================================================

def strategy_sa_a_binary(regime: Regime) -> List[str]:
    """SA-A: Binary Switch"""
    if regime == Regime.BULL:
        return ['SECTOR_ROTATION']
    elif regime == Regime.BEAR:
        return ['DIP_BOUNCE']
    else:
        return ['SECTOR_ROTATION']

def strategy_sa_b_conservative(regime: Regime) -> List[str]:
    """SA-B: Conservative (No trade in NEUTRAL)"""
    if regime == Regime.BULL:
        return ['SECTOR_ROTATION']
    elif regime == Regime.BEAR:
        return ['DIP_BOUNCE']
    else:
        return []  # No trade

def strategy_sa_c_aggressive(regime: Regime) -> List[str]:
    """SA-C: Aggressive (Both in NEUTRAL)"""
    if regime == Regime.BULL:
        return ['SECTOR_ROTATION']
    elif regime == Regime.BEAR:
        return ['DIP_BOUNCE']
    else:
        return ['SECTOR_ROTATION', 'DIP_BOUNCE']

def strategy_sa_d_weighted(regime: Regime) -> Dict[str, float]:
    """SA-D: Weighted Combo"""
    if regime == Regime.BULL:
        return {'SECTOR_ROTATION': 0.8, 'DIP_BOUNCE': 0.2}
    elif regime == Regime.BEAR:
        return {'SECTOR_ROTATION': 0.2, 'DIP_BOUNCE': 0.8}
    else:
        return {'SECTOR_ROTATION': 0.5, 'DIP_BOUNCE': 0.5}

def strategy_sa_e_dip_only(regime: Regime) -> List[str]:
    """SA-E: Dip-Bounce Only (baseline)"""
    return ['DIP_BOUNCE']

STRATEGY_ASSIGNMENTS = {
    'SA-A_binary': strategy_sa_a_binary,
    'SA-B_conservative': strategy_sa_b_conservative,
    'SA-C_aggressive': strategy_sa_c_aggressive,
    'SA-E_db_only': strategy_sa_e_dip_only,
}

# ============================================================================
# TRANSITION RULES
# ============================================================================

def transition_tr_a_immediate(state: RegimeState, new_regime: Regime) -> Tuple[bool, RegimeState]:
    """TR-A: Immediate Switch"""
    if new_regime != state.current:
        state.current = new_regime
        state.switch_count += 1
        state.days_since_switch = 0
        return True, state
    state.days_since_switch += 1
    return False, state

def transition_tr_b_confirm_2d(state: RegimeState, new_regime: Regime) -> Tuple[bool, RegimeState]:
    """TR-B: Confirmation Required (2 days)"""
    if new_regime != state.current:
        if state.pending == new_regime:
            state.pending_days += 1
            if state.pending_days >= 2:
                state.current = new_regime
                state.pending = None
                state.pending_days = 0
                state.switch_count += 1
                state.days_since_switch = 0
                return True, state
        else:
            state.pending = new_regime
            state.pending_days = 1
    else:
        state.pending = None
        state.pending_days = 0

    state.days_since_switch += 1
    return False, state

def transition_tr_c_cooldown_5d(state: RegimeState, new_regime: Regime) -> Tuple[bool, RegimeState]:
    """TR-C: Cooldown Period (5 days)"""
    state.days_since_switch += 1

    if new_regime != state.current:
        if state.days_since_switch >= 5:
            state.current = new_regime
            state.switch_count += 1
            state.days_since_switch = 0
            return True, state

    return False, state

def transition_tr_d_confirm_3d(state: RegimeState, new_regime: Regime) -> Tuple[bool, RegimeState]:
    """TR-D: Confirmation Required (3 days)"""
    if new_regime != state.current:
        if state.pending == new_regime:
            state.pending_days += 1
            if state.pending_days >= 3:
                state.current = new_regime
                state.pending = None
                state.pending_days = 0
                state.switch_count += 1
                state.days_since_switch = 0
                return True, state
        else:
            state.pending = new_regime
            state.pending_days = 1
    else:
        state.pending = None
        state.pending_days = 0

    state.days_since_switch += 1
    return False, state

TRANSITION_RULES = {
    'TR-A_immediate': transition_tr_a_immediate,
    'TR-B_confirm_2d': transition_tr_b_confirm_2d,
    'TR-C_cooldown_5d': transition_tr_c_cooldown_5d,
    'TR-D_confirm_3d': transition_tr_d_confirm_3d,
}

# ============================================================================
# SIGNAL GENERATION
# ============================================================================

def find_dip_bounce_signals(stock_data: pd.DataFrame, stock: str, date) -> Optional[float]:
    """Check if dip-bounce signal on given date"""
    try:
        closes = stock_data[('Close', stock)]
        idx = closes.index.get_loc(date)
        if idx < 2:
            return None

        yesterday_return = (closes.iloc[idx-1] / closes.iloc[idx-2] - 1) * 100
        today_return = (closes.iloc[idx] / closes.iloc[idx-1] - 1) * 100

        if yesterday_return <= -2 and today_return >= 1:
            return closes.iloc[idx]
        return None
    except:
        return None

def find_sector_rotation_signals(sector_metrics: dict, stock_data: pd.DataFrame,
                                  sector: str, date) -> List[Tuple[str, float]]:
    """Find SR-D signals (Relative Strength Breakout) for sector"""
    signals = []
    try:
        s = sector_metrics[sector]
        spy = sector_metrics['SPY']

        idx = s.index.get_loc(date)
        if idx < 1:
            return signals

        rs_today = s.iloc[idx]['return_20d'] - spy.iloc[idx]['return_20d']
        rs_yesterday = s.iloc[idx-1]['return_20d'] - spy.iloc[idx-1]['return_20d']
        sector_1d = s.iloc[idx]['return_1d']

        # RS Breakout condition
        if not (rs_yesterday < 0 and rs_today > 0 and sector_1d > 0.5):
            return signals

        # Find stocks with dip-bounce in this sector (Stock-D combo)
        for stock in STOCK_UNIVERSE.get(sector, []):
            entry_price = find_dip_bounce_signals(stock_data, stock, date)
            if entry_price:
                signals.append((stock, entry_price))

        # If no dip-bounce, use volume leaders
        if not signals:
            for stock in STOCK_UNIVERSE.get(sector, [])[:3]:
                try:
                    entry_price = stock_data[('Close', stock)].loc[date]
                    signals.append((stock, entry_price))
                except:
                    continue

    except Exception as e:
        pass

    return signals[:2]  # Max 2 stocks

def calculate_sector_metrics(etf_data: pd.DataFrame) -> dict:
    """Calculate metrics for each sector"""
    metrics = {}

    for sector, etf in SECTOR_ETFS.items():
        try:
            close = etf_data[('Close', etf)]
            df = pd.DataFrame(index=close.index)
            df['close'] = close
            df['return_1d'] = close.pct_change() * 100
            df['return_5d'] = close.pct_change(5) * 100
            df['return_20d'] = close.pct_change(20) * 100
            metrics[sector] = df
        except:
            pass

    # SPY
    try:
        spy_close = etf_data[('Close', 'SPY')]
        spy_df = pd.DataFrame(index=spy_close.index)
        spy_df['close'] = spy_close
        spy_df['return_1d'] = spy_close.pct_change() * 100
        spy_df['return_5d'] = spy_close.pct_change(5) * 100
        spy_df['return_20d'] = spy_close.pct_change(20) * 100
        metrics['SPY'] = spy_df
    except:
        pass

    return metrics

# ============================================================================
# TRADE SIMULATION
# ============================================================================

def simulate_trade(stock_data: pd.DataFrame, stock: str, entry_date: str,
                   entry_price: float, strategy: str, hold_days: int = 5) -> Optional[Trade]:
    """Simulate a trade"""
    try:
        closes = stock_data[('Close', stock)].dropna()
        dates = closes.index

        entry_idx = None
        for i, d in enumerate(dates):
            if d.strftime('%Y-%m-%d') == entry_date:
                entry_idx = i
                break

        if entry_idx is None:
            return None

        tp = 3.0 if strategy == 'DIP_BOUNCE' else 4.0
        sl = -2.0 if strategy == 'DIP_BOUNCE' else -2.5
        max_hold = hold_days if strategy == 'DIP_BOUNCE' else hold_days + 2

        for day in range(1, max_hold + 1):
            if entry_idx + day >= len(closes):
                break

            current_price = closes.iloc[entry_idx + day]
            pnl_pct = (current_price / entry_price - 1) * 100

            exit_reason = ''
            if pnl_pct >= tp:
                exit_reason = 'TP'
            elif pnl_pct <= sl:
                exit_reason = 'SL'
            elif day >= max_hold:
                exit_reason = f'HOLD_{max_hold}D'

            if exit_reason:
                sector = STOCK_TO_SECTOR.get(stock, 'Unknown')
                return Trade(
                    symbol=stock,
                    sector=sector,
                    strategy=strategy,
                    entry_date=entry_date,
                    entry_price=entry_price,
                    exit_date=dates[entry_idx + day].strftime('%Y-%m-%d'),
                    exit_price=current_price,
                    pnl_pct=pnl_pct,
                    hold_days=day,
                    exit_reason=exit_reason,
                    regime='',
                    regime_at_entry=''
                )

        return None
    except:
        return None

# ============================================================================
# MAIN BACKTEST ENGINE
# ============================================================================

def run_regime_backtest(market_data: pd.DataFrame, stock_data: pd.DataFrame,
                        sector_metrics: dict, regime_detector: str,
                        strategy_assignment: str, transition_rule: str) -> Tuple[List[Trade], dict]:
    """Run full regime-based backtest"""
    trades = []
    regime_history = []

    detector_func = REGIME_DETECTORS[regime_detector]
    assignment_func = STRATEGY_ASSIGNMENTS[strategy_assignment]
    transition_func = TRANSITION_RULES[transition_rule]

    # Initialize regime state
    state = RegimeState(current=Regime.NEUTRAL)

    dates = market_data.index[50:]  # Skip first 50 days for indicators

    for date in dates:
        try:
            row = market_data.loc[date]
            date_str = date.strftime('%Y-%m-%d')

            # Detect new regime
            new_regime = detector_func(row)

            # Apply transition rule
            switched, state = transition_func(state, new_regime)

            regime_history.append({
                'date': date_str,
                'regime': state.current.value,
                'switched': switched
            })

            # Get strategies for current regime
            strategies = assignment_func(state.current)
            if not strategies:
                continue

            # Generate signals based on strategies
            if 'SECTOR_ROTATION' in strategies:
                for sector in SECTOR_ETFS.keys():
                    sr_signals = find_sector_rotation_signals(
                        sector_metrics, stock_data, sector, date
                    )
                    for stock, entry_price in sr_signals:
                        trade = simulate_trade(
                            stock_data, stock, date_str, entry_price,
                            'SECTOR_ROTATION', 5
                        )
                        if trade:
                            trade.regime = state.current.value
                            trade.regime_at_entry = state.current.value
                            trades.append(trade)

            if 'DIP_BOUNCE' in strategies:
                for stock in list(STOCK_TO_SECTOR.keys()):
                    entry_price = find_dip_bounce_signals(stock_data, stock, date)
                    if entry_price:
                        trade = simulate_trade(
                            stock_data, stock, date_str, entry_price,
                            'DIP_BOUNCE', 3
                        )
                        if trade:
                            trade.regime = state.current.value
                            trade.regime_at_entry = state.current.value
                            trades.append(trade)

        except Exception as e:
            continue

    # Calculate regime statistics
    regime_stats = {
        'switch_count': state.switch_count,
        'regime_history': regime_history
    }

    return trades, regime_stats

def calculate_metrics(trades: List[Trade]) -> dict:
    """Calculate performance metrics"""
    if not trades:
        return {
            'win_rate': 0, 'avg_pnl': 0, 'total_pnl': 0,
            'sharpe': 0, 'max_dd': 0, 'trades': 0, 'profit_factor': 0
        }

    pnls = [t.pnl_pct for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / len(pnls) * 100
    avg_pnl = np.mean(pnls)
    total_pnl = sum(pnls)
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 else 0

    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0

    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    return {
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'total_pnl': total_pnl,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'trades': len(trades),
        'profit_factor': profit_factor
    }

def calculate_regime_breakdown(trades: List[Trade]) -> dict:
    """Calculate metrics by regime"""
    results = {}
    for regime in ['BULL', 'BEAR', 'NEUTRAL']:
        regime_trades = [t for t in trades if t.regime_at_entry == regime]
        if regime_trades:
            wins = [t for t in regime_trades if t.pnl_pct > 0]
            results[regime] = {
                'win_rate': len(wins) / len(regime_trades) * 100,
                'trades': len(regime_trades),
                'avg_pnl': np.mean([t.pnl_pct for t in regime_trades])
            }
        else:
            results[regime] = {'win_rate': 0, 'trades': 0, 'avg_pnl': 0}
    return results

def analyze_regime_distribution(regime_history: List[dict]) -> dict:
    """Analyze regime distribution and flip frequency"""
    if not regime_history:
        return {}

    df = pd.DataFrame(regime_history)

    # Count days in each regime
    regime_counts = df['regime'].value_counts().to_dict()
    total_days = len(df)

    # Calculate flip frequency
    flips = df['switched'].sum()

    return {
        'total_days': total_days,
        'regime_distribution': {r: regime_counts.get(r, 0) / total_days * 100 for r in ['BULL', 'BEAR', 'NEUTRAL']},
        'flip_count': flips,
        'flip_frequency': flips / total_days * 100 if total_days > 0 else 0
    }

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 90)
    print("🔀 REGIME-BASED STRATEGY SWITCHING BACKTEST")
    print("=" * 90)

    # Download data
    etf_data, stock_data = download_data('1y')

    print("\n📊 Preparing market data...")
    market_data = prepare_market_data(etf_data)
    sector_metrics = calculate_sector_metrics(etf_data)

    # =========================================================================
    # Part 1: Regime Detection Comparison
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 1: REGIME DETECTION METHODS")
    print("=" * 90)

    rd_results = {}
    for rd_name in REGIME_DETECTORS.keys():
        trades, stats = run_regime_backtest(
            market_data, stock_data, sector_metrics,
            rd_name, 'SA-A_binary', 'TR-B_confirm_2d'
        )
        regime_dist = analyze_regime_distribution(stats['regime_history'])
        rd_results[rd_name] = {
            'metrics': calculate_metrics(trades),
            'regime_breakdown': calculate_regime_breakdown(trades),
            'distribution': regime_dist,
            'switch_count': stats['switch_count']
        }

    print(f"\n{'Method':<20} {'BULL%':>8} {'BEAR%':>8} {'NEUT%':>8} {'Flips':>8} {'Win%':>8} {'Trades':>8}")
    print("-" * 80)

    for name, data in sorted(rd_results.items(), key=lambda x: x[1]['metrics']['win_rate'], reverse=True):
        dist = data['distribution'].get('regime_distribution', {})
        m = data['metrics']
        print(f"{name:<20} {dist.get('BULL', 0):>7.1f}% {dist.get('BEAR', 0):>7.1f}% {dist.get('NEUTRAL', 0):>7.1f}% {data['switch_count']:>8} {m['win_rate']:>7.1f}% {m['trades']:>8}")

    # =========================================================================
    # Part 2: Strategy Assignment Comparison
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 2: STRATEGY ASSIGNMENT")
    print("=" * 90)

    # Use best regime detector
    best_rd = max(rd_results.items(), key=lambda x: x[1]['metrics']['win_rate'])[0]

    sa_results = {}
    for sa_name in STRATEGY_ASSIGNMENTS.keys():
        trades, stats = run_regime_backtest(
            market_data, stock_data, sector_metrics,
            best_rd, sa_name, 'TR-B_confirm_2d'
        )
        sa_results[sa_name] = {
            'metrics': calculate_metrics(trades),
            'regime_breakdown': calculate_regime_breakdown(trades)
        }

    print(f"\n{'Assignment':<20} {'Win%':>8} {'AvgP&L':>8} {'Sharpe':>8} {'Trades':>8} {'BULL%':>8} {'BEAR%':>8} {'NEUT%':>8}")
    print("-" * 100)

    for name, data in sorted(sa_results.items(), key=lambda x: x[1]['metrics']['win_rate'], reverse=True):
        m = data['metrics']
        rb = data['regime_breakdown']
        print(f"{name:<20} {m['win_rate']:>7.1f}% {m['avg_pnl']:>+7.2f}% {m['sharpe']:>8.2f} {m['trades']:>8} {rb['BULL']['win_rate']:>7.1f}% {rb['BEAR']['win_rate']:>7.1f}% {rb['NEUTRAL']['win_rate']:>7.1f}%")

    # =========================================================================
    # Part 3: Transition Rules Comparison
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 3: TRANSITION RULES")
    print("=" * 90)

    best_sa = max(sa_results.items(), key=lambda x: x[1]['metrics']['win_rate'])[0]

    tr_results = {}
    for tr_name in TRANSITION_RULES.keys():
        trades, stats = run_regime_backtest(
            market_data, stock_data, sector_metrics,
            best_rd, best_sa, tr_name
        )
        tr_results[tr_name] = {
            'metrics': calculate_metrics(trades),
            'switch_count': stats['switch_count']
        }

    print(f"\n{'Rule':<20} {'Win%':>8} {'AvgP&L':>8} {'Switches':>10} {'Trades':>8}")
    print("-" * 65)

    for name, data in sorted(tr_results.items(), key=lambda x: x[1]['metrics']['win_rate'], reverse=True):
        m = data['metrics']
        print(f"{name:<20} {m['win_rate']:>7.1f}% {m['avg_pnl']:>+7.2f}% {data['switch_count']:>10} {m['trades']:>8}")

    # =========================================================================
    # Part 4: Full System Comparison
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 4: FULL SYSTEM COMPARISON")
    print("=" * 90)

    # Best combination
    best_tr = max(tr_results.items(), key=lambda x: x[1]['metrics']['win_rate'])[0]

    # Run baselines
    print("\n  Running baselines...")

    # Dip-Bounce only (no regime switching)
    db_trades, _ = run_regime_backtest(
        market_data, stock_data, sector_metrics,
        best_rd, 'SA-E_db_only', 'TR-A_immediate'
    )
    db_metrics = calculate_metrics(db_trades)
    db_regime = calculate_regime_breakdown(db_trades)

    # Best regime switching
    best_trades, best_stats = run_regime_backtest(
        market_data, stock_data, sector_metrics,
        best_rd, best_sa, best_tr
    )
    best_metrics = calculate_metrics(best_trades)
    best_regime = calculate_regime_breakdown(best_trades)

    print(f"\n{'System':<35} {'Win%':>8} {'AvgP&L':>8} {'Sharpe':>8} {'MaxDD':>8} {'Trades':>8} {'PF':>8}")
    print("-" * 95)
    print(f"{'DB Only (baseline)':<35} {db_metrics['win_rate']:>7.1f}% {db_metrics['avg_pnl']:>+7.2f}% {db_metrics['sharpe']:>8.2f} {db_metrics['max_dd']:>7.1f}% {db_metrics['trades']:>8} {db_metrics['profit_factor']:>7.2f}")
    print(f"{f'{best_rd}+{best_sa}+{best_tr}':<35} {best_metrics['win_rate']:>7.1f}% {best_metrics['avg_pnl']:>+7.2f}% {best_metrics['sharpe']:>8.2f} {best_metrics['max_dd']:>7.1f}% {best_metrics['trades']:>8} {best_metrics['profit_factor']:>7.2f}")

    # =========================================================================
    # Part 5: By Regime Analysis
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 5: BY REGIME ANALYSIS")
    print("=" * 90)

    print(f"\n{'System':<35} {'BULL Win%':>12} {'BEAR Win%':>12} {'NEUTRAL Win%':>14}")
    print("-" * 80)
    print(f"{'DB Only':<35} {db_regime['BULL']['win_rate']:>11.1f}% {db_regime['BEAR']['win_rate']:>11.1f}% {db_regime['NEUTRAL']['win_rate']:>13.1f}%")
    print(f"{'Regime Switching':<35} {best_regime['BULL']['win_rate']:>11.1f}% {best_regime['BEAR']['win_rate']:>11.1f}% {best_regime['NEUTRAL']['win_rate']:>13.1f}%")

    # =========================================================================
    # ANSWERS
    # =========================================================================
    print("\n" + "=" * 90)
    print("❓ ANSWERS TO KEY QUESTIONS")
    print("=" * 90)

    # Success criteria
    win_rate_pass = best_metrics['win_rate'] > 58
    sharpe_pass = best_metrics['sharpe'] > 3.0
    max_dd_pass = best_metrics['max_dd'] < 20
    all_regime_pass = all(best_regime[r]['win_rate'] >= 50 for r in ['BULL', 'BEAR', 'NEUTRAL'] if best_regime[r]['trades'] > 0)

    print(f"""
Q1: Regime Detection ไหนดีสุด?
    Best: {best_rd}
    Win Rate: {rd_results[best_rd]['metrics']['win_rate']:.1f}%
    Flip Count: {rd_results[best_rd]['switch_count']}

Q2: Strategy Assignment ไหนดีสุด?
    Best: {best_sa}
    Win Rate: {sa_results[best_sa]['metrics']['win_rate']:.1f}%

Q3: Transition Rules สำคัญแค่ไหน?
    Best: {best_tr}
    Switches: {tr_results[best_tr]['switch_count']}
    Impact: {tr_results[best_tr]['metrics']['win_rate'] - min(tr_results.values(), key=lambda x: x['metrics']['win_rate'])['metrics']['win_rate']:+.1f}% win rate diff

Q4: Position Sizing by Regime ช่วยไหม?
    Not tested directly, but regime-specific strategies effectively do this.

Q5: Regime Switching ดีกว่า Single Strategy ไหม?
    DB Only Win Rate: {db_metrics['win_rate']:.1f}%
    Regime Switch Win Rate: {best_metrics['win_rate']:.1f}%
    Improvement: {best_metrics['win_rate'] - db_metrics['win_rate']:+.1f}%
""")

    # =========================================================================
    # SUCCESS CRITERIA CHECK
    # =========================================================================
    print("\n" + "=" * 90)
    print("✅ SUCCESS CRITERIA CHECK")
    print("=" * 90)

    print(f"""
1. Overall Win Rate > 58%: {'✅ PASS' if win_rate_pass else '❌ FAIL'} ({best_metrics['win_rate']:.1f}%)
2. Sharpe Ratio > 3.0: {'✅ PASS' if sharpe_pass else '❌ FAIL'} ({best_metrics['sharpe']:.2f})
3. Max Drawdown < 20%: {'✅ PASS' if max_dd_pass else '❌ FAIL'} ({best_metrics['max_dd']:.1f}%)
4. All Regimes Win% >= 50%: {'✅ PASS' if all_regime_pass else '❌ FAIL'}
   - BULL: {best_regime['BULL']['win_rate']:.1f}% ({best_regime['BULL']['trades']} trades)
   - BEAR: {best_regime['BEAR']['win_rate']:.1f}% ({best_regime['BEAR']['trades']} trades)
   - NEUTRAL: {best_regime['NEUTRAL']['win_rate']:.1f}% ({best_regime['NEUTRAL']['trades']} trades)
""")

    criteria_passed = sum([win_rate_pass, sharpe_pass, max_dd_pass, all_regime_pass])

    # =========================================================================
    # FINAL RECOMMENDATION
    # =========================================================================
    print("\n" + "=" * 90)
    print("✅ FINAL RECOMMENDATION")
    print("=" * 90)

    if criteria_passed >= 3 and best_metrics['win_rate'] > db_metrics['win_rate']:
        print(f"""
✅ REGIME SWITCHING RECOMMENDED

Best Configuration:
- Regime Detection: {best_rd}
- Strategy Assignment: {best_sa}
- Transition Rule: {best_tr}

Performance:
- Win Rate: {best_metrics['win_rate']:.1f}% (+{best_metrics['win_rate'] - db_metrics['win_rate']:.1f}% vs DB only)
- Sharpe: {best_metrics['sharpe']:.2f}
- Max DD: {best_metrics['max_dd']:.1f}%

Implementation:
```python
class RegimeBasedTrader:
    def detect_regime(self, market_data):
        # {best_rd}
        ...

    def get_strategy(self, regime):
        # {best_sa}
        if regime == "BULL":
            return "SECTOR_ROTATION"
        elif regime == "BEAR":
            return "DIP_BOUNCE"
        else:
            return ...

    def should_switch(self, new_regime):
        # {best_tr}
        ...
```
""")
    else:
        improvement = best_metrics['win_rate'] - db_metrics['win_rate']
        print(f"""
❌ REGIME SWITCHING NOT RECOMMENDED

Reason:
- Passed {criteria_passed}/4 criteria
- Improvement vs DB only: {improvement:+.1f}%
- Complexity not justified by improvement

Recommendation:
1. Keep using Dip-Bounce as primary strategy
2. Use Sector Rotation (SR-D + Stock-D) as complementary strategy
3. Don't add regime switching complexity

Simple Alternative:
```python
def get_strategy():
    # ใช้ทั้ง 2 strategies พร้อมกัน
    # ไม่ต้อง switch ตาม regime
    sr_signal = check_sector_rotation()  # SR-D
    db_signal = check_dip_bounce()

    # Priority: SR-D (higher win rate) > DB (more frequent)
    if sr_signal:
        return sr_signal
    return db_signal
```
""")

    print("\n" + "=" * 90)
    print("🏁 BACKTEST COMPLETE")
    print("=" * 90)

if __name__ == '__main__':
    main()
