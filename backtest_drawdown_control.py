#!/usr/bin/env python3
"""
Drawdown Control Backtest
Test different methods to reduce Max DD while maintaining performance
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
# CONFIGURATION (reuse from previous)
# ============================================================================

SECTOR_ETFS = {
    'Technology': 'XLK', 'Healthcare': 'XLV', 'Financials': 'XLF',
    'Consumer Discretionary': 'XLY', 'Communication Services': 'XLC',
    'Industrials': 'XLI', 'Consumer Staples': 'XLP', 'Energy': 'XLE',
    'Utilities': 'XLU', 'Real Estate': 'XLRE', 'Materials': 'XLB'
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
    position_size: float = 1.0  # Multiplier

@dataclass
class PortfolioState:
    equity: float = 100.0
    peak_equity: float = 100.0
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    pnl_history: List[float] = field(default_factory=list)
    consecutive_losses: int = 0
    last_loss_date: Optional[str] = None
    days_stopped: int = 0
    open_positions: int = 0
    total_risk: float = 0.0

# ============================================================================
# DATA DOWNLOAD
# ============================================================================

def download_data(period='1y'):
    print("📥 Downloading data...")
    etf_symbols = list(SECTOR_ETFS.values()) + ['SPY', '^VIX']
    etf_data = yf.download(etf_symbols, period=period, progress=False)
    all_stocks = list(STOCK_TO_SECTOR.keys())
    stock_data = yf.download(all_stocks, period=period, progress=False)
    print(f"✅ ETF: {len(etf_data)} days, Stocks: {len(stock_data)} days")
    return etf_data, stock_data

def prepare_market_data(etf_data: pd.DataFrame) -> pd.DataFrame:
    spy_close = etf_data[('Close', 'SPY')]
    df = pd.DataFrame(index=spy_close.index)
    df['spy_close'] = spy_close
    df['spy_sma_50'] = spy_close.rolling(50).mean()
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
        df['vix_change_1d'] = df['vix'].pct_change() * 100
    except:
        df['vix'] = 20
        df['vix_change_1d'] = 0

    # ATR
    try:
        high = etf_data[('High', 'SPY')]
        low = etf_data[('Low', 'SPY')]
        df['spy_atr'] = (high - low).rolling(14).mean()
        df['spy_atr_pct'] = df['spy_atr'] / spy_close * 100
        df['spy_atr_avg_20d'] = df['spy_atr_pct'].rolling(20).mean()
    except:
        df['spy_atr_pct'] = 1.5
        df['spy_atr_avg_20d'] = 1.5

    return df

def calculate_sector_metrics(etf_data: pd.DataFrame) -> dict:
    metrics = {}
    for sector, etf in SECTOR_ETFS.items():
        try:
            close = etf_data[('Close', etf)]
            df = pd.DataFrame(index=close.index)
            df['close'] = close
            df['return_1d'] = close.pct_change() * 100
            df['return_20d'] = close.pct_change(20) * 100
            metrics[sector] = df
        except:
            pass

    try:
        spy_close = etf_data[('Close', 'SPY')]
        spy_df = pd.DataFrame(index=spy_close.index)
        spy_df['close'] = spy_close
        spy_df['return_20d'] = spy_close.pct_change(20) * 100
        metrics['SPY'] = spy_df
    except:
        pass

    return metrics

# ============================================================================
# POSITION SIZING METHODS
# ============================================================================

def ps_baseline(vix, regime, drawdown, atr_ratio) -> float:
    """No adjustment"""
    return 1.0

def ps_a_vix_based(vix, regime, drawdown, atr_ratio) -> float:
    """PS-A: VIX-Based Sizing"""
    if pd.isna(vix):
        return 1.0
    if vix < 15:
        return 1.2
    elif vix < 20:
        return 1.0
    elif vix < 25:
        return 0.7
    elif vix < 30:
        return 0.5
    else:
        return 0.3

def ps_b_atr_based(vix, regime, drawdown, atr_ratio) -> float:
    """PS-B: ATR-Based Sizing"""
    if pd.isna(atr_ratio):
        return 1.0
    if atr_ratio > 1.5:
        return 0.5
    elif atr_ratio > 1.2:
        return 0.7
    else:
        return 1.0

def ps_c_regime_based(vix, regime, drawdown, atr_ratio) -> float:
    """PS-C: Regime-Based Sizing"""
    if regime == Regime.BULL:
        return 1.0
    elif regime == Regime.NEUTRAL:
        return 0.7
    else:  # BEAR
        return 0.5

def ps_d_drawdown_based(vix, regime, drawdown, atr_ratio) -> float:
    """PS-D: Drawdown-Adjusted Sizing"""
    if drawdown < 5:
        return 1.0
    elif drawdown < 10:
        return 0.7
    elif drawdown < 15:
        return 0.5
    else:
        return 0.3

def ps_e_combined(vix, regime, drawdown, atr_ratio) -> float:
    """PS-E: Combined (VIX + Drawdown)"""
    vix_mult = ps_a_vix_based(vix, regime, drawdown, atr_ratio)
    dd_mult = ps_d_drawdown_based(vix, regime, drawdown, atr_ratio)
    return min(vix_mult, dd_mult)

POSITION_SIZING = {
    'PS-0_baseline': ps_baseline,
    'PS-A_vix': ps_a_vix_based,
    'PS-B_atr': ps_b_atr_based,
    'PS-C_regime': ps_c_regime_based,
    'PS-D_drawdown': ps_d_drawdown_based,
    'PS-E_combined': ps_e_combined,
}

# ============================================================================
# DAILY LIMITS
# ============================================================================

def dl_none(daily_pnl, pnl_history, consecutive_losses, regime, vix) -> Tuple[bool, str]:
    """No daily limit"""
    return True, ""

def dl_a_fixed(daily_pnl, pnl_history, consecutive_losses, regime, vix) -> Tuple[bool, str]:
    """DL-A: Fixed -2% daily limit"""
    if daily_pnl <= -2:
        return False, "DAILY_LIMIT"
    return True, ""

def dl_b_adaptive(daily_pnl, pnl_history, consecutive_losses, regime, vix) -> Tuple[bool, str]:
    """DL-B: Adaptive daily limit based on regime and VIX"""
    limit = -2.0
    if regime == Regime.BEAR:
        limit = -1.5
    if not pd.isna(vix) and vix > 25:
        limit = limit * 0.7
    if daily_pnl <= limit:
        return False, "ADAPTIVE_LIMIT"
    return True, ""

def dl_c_rolling(daily_pnl, pnl_history, consecutive_losses, regime, vix) -> Tuple[bool, str]:
    """DL-C: Rolling loss limit"""
    if len(pnl_history) >= 3 and sum(pnl_history[-3:]) <= -4:
        return False, "3DAY_LIMIT"
    if len(pnl_history) >= 5 and sum(pnl_history[-5:]) <= -6:
        return False, "5DAY_LIMIT"
    return True, ""

def dl_d_consecutive(daily_pnl, pnl_history, consecutive_losses, regime, vix) -> Tuple[bool, str]:
    """DL-D: Consecutive loss limit"""
    if consecutive_losses >= 3:
        return False, "CONSECUTIVE_LIMIT"
    return True, ""

DAILY_LIMITS = {
    'DL-0_none': dl_none,
    'DL-A_fixed': dl_a_fixed,
    'DL-B_adaptive': dl_b_adaptive,
    'DL-C_rolling': dl_c_rolling,
    'DL-D_consecutive': dl_d_consecutive,
}

# ============================================================================
# CIRCUIT BREAKERS
# ============================================================================

def cb_none(drawdown, vix, vix_change, spy_change) -> Tuple[str, float]:
    """No circuit breaker"""
    return "NORMAL", 1.0

def cb_a_drawdown(drawdown, vix, vix_change, spy_change) -> Tuple[str, float]:
    """CB-A: Drawdown-based"""
    if drawdown >= 15:
        return "STOP_ALL", 0.0
    elif drawdown >= 10:
        return "REDUCE_50", 0.5
    elif drawdown >= 7:
        return "REDUCE_30", 0.7
    return "NORMAL", 1.0

def cb_b_vix_spike(drawdown, vix, vix_change, spy_change) -> Tuple[str, float]:
    """CB-B: VIX spike"""
    if pd.isna(vix):
        return "NORMAL", 1.0
    if vix > 35:
        return "STOP_ALL", 0.0
    if vix > 30 or (not pd.isna(vix_change) and vix_change > 20):
        return "NO_NEW", 0.0
    if vix > 25:
        return "REDUCE_50", 0.5
    return "NORMAL", 1.0

def cb_c_spy_drop(drawdown, vix, vix_change, spy_change) -> Tuple[str, float]:
    """CB-C: SPY drop"""
    if pd.isna(spy_change):
        return "NORMAL", 1.0
    if spy_change <= -5:
        return "STOP_ALL", 0.0
    elif spy_change <= -3:
        return "NO_NEW", 0.0
    elif spy_change <= -2:
        return "REDUCE_50", 0.5
    return "NORMAL", 1.0

def cb_d_portfolio_heat(drawdown, vix, vix_change, spy_change, total_risk=0) -> Tuple[str, float]:
    """CB-D: Portfolio heat (simplified)"""
    max_heat = 6.0
    if total_risk >= max_heat:
        return "NO_NEW", 0.0
    elif total_risk >= max_heat * 0.8:
        return "REDUCE_30", 0.7
    return "NORMAL", 1.0

def cb_e_combined(drawdown, vix, vix_change, spy_change) -> Tuple[str, float]:
    """CB-E: Combined"""
    status_a, mult_a = cb_a_drawdown(drawdown, vix, vix_change, spy_change)
    status_b, mult_b = cb_b_vix_spike(drawdown, vix, vix_change, spy_change)
    status_c, mult_c = cb_c_spy_drop(drawdown, vix, vix_change, spy_change)

    # Use most restrictive
    min_mult = min(mult_a, mult_b, mult_c)
    if min_mult == 0:
        return "STOP_ALL", 0.0
    elif min_mult < 1:
        return "REDUCED", min_mult
    return "NORMAL", 1.0

CIRCUIT_BREAKERS = {
    'CB-0_none': cb_none,
    'CB-A_drawdown': cb_a_drawdown,
    'CB-B_vix_spike': cb_b_vix_spike,
    'CB-C_spy_drop': cb_c_spy_drop,
    'CB-E_combined': cb_e_combined,
}

# ============================================================================
# STOP LOSS METHODS
# ============================================================================

def sl_baseline(regime, vix, days_held, profit_pct) -> float:
    """Baseline: Fixed -2%"""
    return -2.0

def sl_a_regime_based(regime, vix, days_held, profit_pct) -> float:
    """SL-A: Regime-based"""
    if regime == Regime.BULL:
        return -2.5
    elif regime == Regime.NEUTRAL:
        return -2.0
    else:  # BEAR
        return -1.5

def sl_b_vix_based(regime, vix, days_held, profit_pct) -> float:
    """SL-B: VIX-based"""
    if pd.isna(vix):
        return -2.0
    if vix > 25:
        return -1.5
    elif vix > 20:
        return -1.8
    else:
        return -2.0

def sl_c_trailing(regime, vix, days_held, profit_pct) -> float:
    """SL-C: Trailing stop"""
    base_sl = -2.0
    if profit_pct >= 3:
        return max(base_sl, -1.0)  # Trail at 1%
    elif profit_pct >= 2:
        return max(base_sl, 0)  # Breakeven
    return base_sl

def sl_d_time_based(regime, vix, days_held, profit_pct) -> float:
    """SL-D: Time-based tightening"""
    if days_held >= 3:
        return -1.5  # Tighter after 3 days
    return -2.0

def sl_e_combined(regime, vix, days_held, profit_pct) -> float:
    """SL-E: Combined"""
    sl_regime = sl_a_regime_based(regime, vix, days_held, profit_pct)
    sl_vix = sl_b_vix_based(regime, vix, days_held, profit_pct)
    sl_trail = sl_c_trailing(regime, vix, days_held, profit_pct)
    return max(sl_regime, sl_vix, sl_trail)  # Tightest SL

STOP_LOSS_METHODS = {
    'SL-0_baseline': sl_baseline,
    'SL-A_regime': sl_a_regime_based,
    'SL-B_vix': sl_b_vix_based,
    'SL-C_trailing': sl_c_trailing,
    'SL-D_time': sl_d_time_based,
    'SL-E_combined': sl_e_combined,
}

# ============================================================================
# REGIME DETECTION (from previous - best: RD-E composite)
# ============================================================================

def detect_regime(row) -> Regime:
    """RD-E: Composite Score"""
    score = 0
    if not pd.isna(row.get('spy_sma_50')) and row['spy_close'] > row['spy_sma_50']:
        score += 1
    else:
        score -= 1
    if not pd.isna(row.get('spy_return_20d')) and row['spy_return_20d'] > 0:
        score += 1
    else:
        score -= 1
    if not pd.isna(row.get('vix')) and row['vix'] < 20:
        score += 1
    else:
        score -= 1
    if not pd.isna(row.get('spy_rsi')) and row['spy_rsi'] > 50:
        score += 1
    else:
        score -= 1

    if score >= 2:
        return Regime.BULL
    elif score <= -2:
        return Regime.BEAR
    else:
        return Regime.NEUTRAL

# ============================================================================
# SIGNAL GENERATION
# ============================================================================

def find_dip_bounce_signals(stock_data: pd.DataFrame, stock: str, date) -> Optional[float]:
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
        if not (rs_yesterday < 0 and rs_today > 0 and sector_1d > 0.5):
            return signals
        for stock in STOCK_UNIVERSE.get(sector, []):
            entry_price = find_dip_bounce_signals(stock_data, stock, date)
            if entry_price:
                signals.append((stock, entry_price))
        if not signals:
            for stock in STOCK_UNIVERSE.get(sector, [])[:2]:
                try:
                    entry_price = stock_data[('Close', stock)].loc[date]
                    signals.append((stock, entry_price))
                except:
                    continue
    except:
        pass
    return signals[:2]

# ============================================================================
# TRADE SIMULATION WITH DRAWDOWN CONTROLS
# ============================================================================

def simulate_trade_with_controls(stock_data: pd.DataFrame, stock: str, entry_date: str,
                                  entry_price: float, strategy: str, hold_days: int,
                                  regime: Regime, vix: float, sl_func) -> Optional[Trade]:
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
        max_hold = hold_days if strategy == 'DIP_BOUNCE' else hold_days + 2

        for day in range(1, max_hold + 1):
            if entry_idx + day >= len(closes):
                break
            current_price = closes.iloc[entry_idx + day]
            pnl_pct = (current_price / entry_price - 1) * 100

            # Dynamic SL
            sl = sl_func(regime, vix, day, pnl_pct)

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
                    symbol=stock, sector=sector, strategy=strategy,
                    entry_date=entry_date, entry_price=entry_price,
                    exit_date=dates[entry_idx + day].strftime('%Y-%m-%d'),
                    exit_price=current_price, pnl_pct=pnl_pct,
                    hold_days=day, exit_reason=exit_reason,
                    regime=regime.value
                )
        return None
    except:
        return None

# ============================================================================
# MAIN BACKTEST WITH DRAWDOWN CONTROLS
# ============================================================================

def run_controlled_backtest(market_data: pd.DataFrame, stock_data: pd.DataFrame,
                            sector_metrics: dict, ps_name: str, dl_name: str,
                            cb_name: str, sl_name: str) -> Tuple[List[Trade], dict]:

    trades = []
    state = PortfolioState()

    ps_func = POSITION_SIZING.get(ps_name, ps_baseline)
    dl_func = DAILY_LIMITS.get(dl_name, dl_none)
    cb_func = CIRCUIT_BREAKERS.get(cb_name, cb_none)
    sl_func = STOP_LOSS_METHODS.get(sl_name, sl_baseline)

    # Regime state
    current_regime = Regime.NEUTRAL
    pending_regime = None
    pending_days = 0

    dates = market_data.index[50:]
    daily_trades = defaultdict(list)
    days_stopped = 0
    times_cb_triggered = 0

    for date in dates:
        try:
            row = market_data.loc[date]
            date_str = date.strftime('%Y-%m-%d')

            # Detect regime (with 3-day confirmation)
            new_regime = detect_regime(row)
            if new_regime != current_regime:
                if pending_regime == new_regime:
                    pending_days += 1
                    if pending_days >= 3:
                        current_regime = new_regime
                        pending_regime = None
                        pending_days = 0
                else:
                    pending_regime = new_regime
                    pending_days = 1
            else:
                pending_regime = None
                pending_days = 0

            # Get market data
            vix = row.get('vix', 20)
            vix_change = row.get('vix_change_1d', 0)
            spy_change = row.get('spy_return_1d', 0)
            atr_ratio = row.get('spy_atr_pct', 1.5) / row.get('spy_atr_avg_20d', 1.5) if row.get('spy_atr_avg_20d', 1.5) > 0 else 1.0

            # Check circuit breaker
            cb_status, cb_mult = cb_func(state.current_drawdown, vix, vix_change, spy_change)
            if cb_mult == 0:
                times_cb_triggered += 1
                days_stopped += 1
                continue

            # Check daily limit
            can_trade, dl_reason = dl_func(
                state.daily_pnl, state.pnl_history,
                state.consecutive_losses, current_regime, vix
            )
            if not can_trade:
                days_stopped += 1
                continue

            # Get position size
            ps_mult = ps_func(vix, current_regime, state.current_drawdown, atr_ratio)
            final_mult = ps_mult * cb_mult

            # Generate signals based on regime
            strategies = []
            if current_regime == Regime.BULL:
                strategies = ['SECTOR_ROTATION']
            elif current_regime == Regime.BEAR:
                strategies = ['DIP_BOUNCE']
            else:  # NEUTRAL - aggressive
                strategies = ['SECTOR_ROTATION', 'DIP_BOUNCE']

            # Find and execute trades
            for strategy in strategies:
                if strategy == 'SECTOR_ROTATION':
                    for sector in SECTOR_ETFS.keys():
                        signals = find_sector_rotation_signals(sector_metrics, stock_data, sector, date)
                        for stock, entry_price in signals:
                            trade = simulate_trade_with_controls(
                                stock_data, stock, date_str, entry_price,
                                'SECTOR_ROTATION', 5, current_regime, vix, sl_func
                            )
                            if trade:
                                trade.position_size = final_mult
                                trades.append(trade)
                                daily_trades[date_str].append(trade)

                elif strategy == 'DIP_BOUNCE':
                    for stock in list(STOCK_TO_SECTOR.keys()):
                        entry_price = find_dip_bounce_signals(stock_data, stock, date)
                        if entry_price:
                            trade = simulate_trade_with_controls(
                                stock_data, stock, date_str, entry_price,
                                'DIP_BOUNCE', 3, current_regime, vix, sl_func
                            )
                            if trade:
                                trade.position_size = final_mult
                                trades.append(trade)
                                daily_trades[date_str].append(trade)

            # Update portfolio state
            day_pnl = sum(t.pnl_pct * t.position_size for t in daily_trades[date_str])
            state.daily_pnl = day_pnl
            state.pnl_history.append(day_pnl)

            if day_pnl < 0:
                state.consecutive_losses += 1
                state.last_loss_date = date_str
            else:
                state.consecutive_losses = 0

            # Update equity and drawdown
            state.equity += day_pnl
            state.peak_equity = max(state.peak_equity, state.equity)
            state.current_drawdown = (state.peak_equity - state.equity) / state.peak_equity * 100 if state.peak_equity > 0 else 0

        except Exception as e:
            continue

    stats = {
        'days_stopped': days_stopped,
        'times_cb_triggered': times_cb_triggered
    }

    return trades, stats

def calculate_metrics(trades: List[Trade]) -> dict:
    if not trades:
        return {'win_rate': 0, 'avg_pnl': 0, 'total_pnl': 0, 'sharpe': 0, 'max_dd': 0, 'trades': 0}

    # Apply position sizing to P&L
    pnls = [t.pnl_pct * t.position_size for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / len(pnls) * 100
    avg_pnl = np.mean(pnls)
    total_pnl = sum(pnls)
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 else 0

    # Max drawdown
    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0

    avg_size = np.mean([t.position_size for t in trades])

    return {
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'total_pnl': total_pnl,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'trades': len(trades),
        'avg_size': avg_size
    }

def calculate_regime_breakdown(trades: List[Trade]) -> dict:
    results = {}
    for regime in ['BULL', 'BEAR', 'NEUTRAL']:
        regime_trades = [t for t in trades if t.regime == regime]
        if regime_trades:
            wins = [t for t in regime_trades if t.pnl_pct > 0]
            results[regime] = len(wins) / len(regime_trades) * 100
        else:
            results[regime] = 0
    return results

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 90)
    print("🛡️ DRAWDOWN CONTROL BACKTEST")
    print("=" * 90)

    etf_data, stock_data = download_data('1y')
    market_data = prepare_market_data(etf_data)
    sector_metrics = calculate_sector_metrics(etf_data)

    # =========================================================================
    # Part 1: Position Sizing
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 1: POSITION SIZING METHODS")
    print("=" * 90)

    ps_results = {}
    for ps_name in POSITION_SIZING.keys():
        print(f"  Testing {ps_name}...")
        trades, stats = run_controlled_backtest(
            market_data, stock_data, sector_metrics,
            ps_name, 'DL-0_none', 'CB-0_none', 'SL-0_baseline'
        )
        ps_results[ps_name] = calculate_metrics(trades)

    print(f"\n{'Method':<20} {'MaxDD':>8} {'Win%':>8} {'Sharpe':>8} {'AvgSize':>8} {'Trades':>8}")
    print("-" * 70)
    for name, m in sorted(ps_results.items(), key=lambda x: x[1]['max_dd']):
        print(f"{name:<20} {m['max_dd']:>7.1f}% {m['win_rate']:>7.1f}% {m['sharpe']:>8.2f} {m['avg_size']:>7.2f}x {m['trades']:>8}")

    # =========================================================================
    # Part 2: Daily Limits
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 2: DAILY LIMITS")
    print("=" * 90)

    dl_results = {}
    for dl_name in DAILY_LIMITS.keys():
        print(f"  Testing {dl_name}...")
        trades, stats = run_controlled_backtest(
            market_data, stock_data, sector_metrics,
            'PS-0_baseline', dl_name, 'CB-0_none', 'SL-0_baseline'
        )
        dl_results[dl_name] = {**calculate_metrics(trades), 'days_stopped': stats['days_stopped']}

    print(f"\n{'Method':<20} {'MaxDD':>8} {'Win%':>8} {'DaysStopped':>12} {'Trades':>8}")
    print("-" * 65)
    for name, m in sorted(dl_results.items(), key=lambda x: x[1]['max_dd']):
        print(f"{name:<20} {m['max_dd']:>7.1f}% {m['win_rate']:>7.1f}% {m['days_stopped']:>12} {m['trades']:>8}")

    # =========================================================================
    # Part 3: Circuit Breakers
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 3: CIRCUIT BREAKERS")
    print("=" * 90)

    cb_results = {}
    for cb_name in CIRCUIT_BREAKERS.keys():
        print(f"  Testing {cb_name}...")
        trades, stats = run_controlled_backtest(
            market_data, stock_data, sector_metrics,
            'PS-0_baseline', 'DL-0_none', cb_name, 'SL-0_baseline'
        )
        cb_results[cb_name] = {**calculate_metrics(trades), 'triggered': stats['times_cb_triggered']}

    print(f"\n{'Method':<20} {'MaxDD':>8} {'Win%':>8} {'Triggered':>10} {'Trades':>8}")
    print("-" * 65)
    for name, m in sorted(cb_results.items(), key=lambda x: x[1]['max_dd']):
        print(f"{name:<20} {m['max_dd']:>7.1f}% {m['win_rate']:>7.1f}% {m['triggered']:>10} {m['trades']:>8}")

    # =========================================================================
    # Part 4: Stop Loss Methods
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 4: STOP LOSS METHODS")
    print("=" * 90)

    sl_results = {}
    for sl_name in STOP_LOSS_METHODS.keys():
        print(f"  Testing {sl_name}...")
        trades, stats = run_controlled_backtest(
            market_data, stock_data, sector_metrics,
            'PS-0_baseline', 'DL-0_none', 'CB-0_none', sl_name
        )
        sl_results[sl_name] = calculate_metrics(trades)

    print(f"\n{'Method':<20} {'MaxDD':>8} {'Win%':>8} {'AvgP&L':>8} {'Trades':>8}")
    print("-" * 60)
    for name, m in sorted(sl_results.items(), key=lambda x: x[1]['max_dd']):
        print(f"{name:<20} {m['max_dd']:>7.1f}% {m['win_rate']:>7.1f}% {m['avg_pnl']:>+7.2f}% {m['trades']:>8}")

    # =========================================================================
    # Part 5: Combination Strategies
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 5: COMBINATION STRATEGIES")
    print("=" * 90)

    combos = {
        'BASELINE': ('PS-0_baseline', 'DL-0_none', 'CB-0_none', 'SL-0_baseline'),
        'COMBO-A_conservative': ('PS-D_drawdown', 'DL-A_fixed', 'CB-A_drawdown', 'SL-A_regime'),
        'COMBO-B_aggressive': ('PS-E_combined', 'DL-C_rolling', 'CB-B_vix_spike', 'SL-C_trailing'),
        'COMBO-C_balanced': ('PS-A_vix', 'DL-B_adaptive', 'CB-A_drawdown', 'SL-B_vix'),
        'COMBO-D_minimal': ('PS-C_regime', 'DL-0_none', 'CB-A_drawdown', 'SL-0_baseline'),
        'COMBO-E_maximum': ('PS-E_combined', 'DL-C_rolling', 'CB-E_combined', 'SL-E_combined'),
    }

    combo_results = {}
    for combo_name, (ps, dl, cb, sl) in combos.items():
        print(f"  Testing {combo_name}...")
        trades, stats = run_controlled_backtest(
            market_data, stock_data, sector_metrics, ps, dl, cb, sl
        )
        metrics = calculate_metrics(trades)
        regime_breakdown = calculate_regime_breakdown(trades)
        combo_results[combo_name] = {**metrics, 'regime': regime_breakdown}

    print(f"\n{'Combo':<25} {'MaxDD':>8} {'Win%':>8} {'Sharpe':>8} {'Trades':>8} {'BULL%':>8} {'BEAR%':>8} {'NEUT%':>8}")
    print("-" * 105)
    for name, m in sorted(combo_results.items(), key=lambda x: x[1]['max_dd']):
        r = m['regime']
        print(f"{name:<25} {m['max_dd']:>7.1f}% {m['win_rate']:>7.1f}% {m['sharpe']:>8.2f} {m['trades']:>8} {r.get('BULL', 0):>7.1f}% {r.get('BEAR', 0):>7.1f}% {r.get('NEUTRAL', 0):>7.1f}%")

    # =========================================================================
    # SUCCESS CRITERIA
    # =========================================================================
    print("\n" + "=" * 90)
    print("✅ SUCCESS CRITERIA CHECK")
    print("=" * 90)

    baseline = combo_results['BASELINE']

    print(f"\nBaseline: MaxDD={baseline['max_dd']:.1f}%, Win%={baseline['win_rate']:.1f}%, Sharpe={baseline['sharpe']:.2f}")
    print("\nMethods that achieve MaxDD < 20%:")
    print("-" * 80)

    successful = []
    for name, m in combo_results.items():
        if m['max_dd'] < 20 and m['win_rate'] > 58 and m['sharpe'] > 3.0:
            successful.append((name, m))
            print(f"✅ {name}: MaxDD={m['max_dd']:.1f}%, Win%={m['win_rate']:.1f}%, Sharpe={m['sharpe']:.2f}")
        elif m['max_dd'] < 20:
            print(f"⚠️  {name}: MaxDD={m['max_dd']:.1f}% but Win%={m['win_rate']:.1f}%, Sharpe={m['sharpe']:.2f}")

    # =========================================================================
    # BEST METHOD
    # =========================================================================
    print("\n" + "=" * 90)
    print("🎯 BEST METHOD ANALYSIS")
    print("=" * 90)

    # Find best balance
    best_efficiency = None
    best_name = None

    for name, m in combo_results.items():
        if name == 'BASELINE':
            continue
        dd_reduction = baseline['max_dd'] - m['max_dd']
        win_rate_loss = baseline['win_rate'] - m['win_rate']

        # Efficiency = DD reduction per Win Rate loss
        efficiency = dd_reduction / max(win_rate_loss, 0.1) if win_rate_loss > 0 else dd_reduction * 10

        print(f"{name}: DD ->{m['max_dd']:.1f}% (Δ{-dd_reduction:+.1f}), Win% ->{m['win_rate']:.1f}% (Δ{-win_rate_loss:+.1f}), Eff={efficiency:.2f}")

        if best_efficiency is None or (efficiency > best_efficiency and m['max_dd'] < 20):
            best_efficiency = efficiency
            best_name = name

    # =========================================================================
    # ANSWERS
    # =========================================================================
    print("\n" + "=" * 90)
    print("❓ ANSWERS TO KEY QUESTIONS")
    print("=" * 90)

    methods_under_20 = [(n, m) for n, m in combo_results.items() if m['max_dd'] < 20]

    print(f"""
Q1: Method ไหนลด Max DD < 20% ได้?
    {len(methods_under_20)} methods: {', '.join([n for n, m in methods_under_20])}

Q2: Method ไหน cost ต่ำสุด?
    Best efficiency: {best_name}
    - DD reduction: {baseline['max_dd'] - combo_results[best_name]['max_dd']:.1f}%
    - Win Rate change: {combo_results[best_name]['win_rate'] - baseline['win_rate']:+.1f}%

Q3: Combination ไหนผ่านทุก criteria?
""")

    for name, m in successful:
        print(f"    ✅ {name}: MaxDD={m['max_dd']:.1f}%, Win%={m['win_rate']:.1f}%, Sharpe={m['sharpe']:.2f}")

    if not successful:
        print("    ❌ No combination passes all criteria")
        # Find closest
        closest = min(combo_results.items(), key=lambda x: x[1]['max_dd'])
        print(f"    Closest: {closest[0]} with MaxDD={closest[1]['max_dd']:.1f}%")

    # =========================================================================
    # FINAL RECOMMENDATION
    # =========================================================================
    print("\n" + "=" * 90)
    print("✅ FINAL RECOMMENDATION")
    print("=" * 90)

    if successful:
        best = min(successful, key=lambda x: x[1]['max_dd'])
        best_name, best_m = best

        print(f"""
✅ RECOMMENDED: {best_name}

Configuration:
- Position Sizing: {combos[best_name][0]}
- Daily Limit: {combos[best_name][1]}
- Circuit Breaker: {combos[best_name][2]}
- Stop Loss: {combos[best_name][3]}

Performance:
- Max DD: {best_m['max_dd']:.1f}% (Target: <20%) ✅
- Win Rate: {best_m['win_rate']:.1f}% (Target: >58%) ✅
- Sharpe: {best_m['sharpe']:.2f} (Target: >3.0) ✅
- Trades: {best_m['trades']}

Improvement vs Baseline:
- DD: {best_m['max_dd'] - baseline['max_dd']:+.1f}%
- Win Rate: {best_m['win_rate'] - baseline['win_rate']:+.1f}%
- Sharpe: {best_m['sharpe'] - baseline['sharpe']:+.2f}
""")
    else:
        # Find best trade-off
        best_dd = min(combo_results.items(), key=lambda x: x[1]['max_dd'] if x[0] != 'BASELINE' else 999)
        best_name, best_m = best_dd

        print(f"""
⚠️  NO COMBINATION PASSES ALL CRITERIA

Best available: {best_name}
- Max DD: {best_m['max_dd']:.1f}% (Target: <20%)
- Win Rate: {best_m['win_rate']:.1f}% (Target: >58%)
- Sharpe: {best_m['sharpe']:.2f} (Target: >3.0)

Options:
1. Accept slightly higher DD ({best_m['max_dd']:.1f}%) for better Win Rate
2. Use stricter controls but accept lower Win Rate
3. Reduce position size across the board
""")

    print("\n" + "=" * 90)
    print("🏁 BACKTEST COMPLETE")
    print("=" * 90)

if __name__ == '__main__':
    main()
