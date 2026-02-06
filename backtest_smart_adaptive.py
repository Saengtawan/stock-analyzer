#!/usr/bin/env python3
"""
Smart Adaptive Drawdown Control - Full Integration Test
Combines all confirmed systems with adaptive DD control
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
    position_size: float = 1.0

@dataclass
class PortfolioState:
    equity: float = 100.0
    peak_equity: float = 100.0
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    pnl_history: List[float] = field(default_factory=list)
    consecutive_losses: int = 0
    recent_win_rate: float = 50.0
    days_since_peak: int = 0

# ============================================================================
# DATA FUNCTIONS
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
    df['spy_return_20d'] = spy_close.pct_change(20) * 100

    delta = spy_close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['spy_rsi'] = 100 - (100 / (1 + rs))

    try:
        df['vix'] = etf_data[('Close', '^VIX')]
        df['vix_change_1d'] = df['vix'].pct_change() * 100
    except:
        df['vix'] = 20
        df['vix_change_1d'] = 0

    try:
        high = etf_data[('High', 'SPY')]
        low = etf_data[('Low', 'SPY')]
        df['spy_atr'] = (high - low).rolling(14).mean()
        df['spy_atr_pct'] = df['spy_atr'] / spy_close * 100
    except:
        df['spy_atr_pct'] = 1.5

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
# REGIME DETECTION (RD-E Composite - CONFIRMED)
# ============================================================================

def detect_regime(row) -> Regime:
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
# ADAPTIVE DAILY LIMITS
# ============================================================================

def adl_none(regime, vix, drawdown, recent_wr) -> float:
    return -100.0  # No limit

def adl_fixed(regime, vix, drawdown, recent_wr) -> float:
    return -2.0  # Fixed -2%

def adl_a_regime(regime, vix, drawdown, recent_wr) -> float:
    """ADL-A: Regime-Based"""
    return {"BULL": -4.0, "NEUTRAL": -3.0, "BEAR": -2.0}.get(regime.value, -3.0)

def adl_b_vix(regime, vix, drawdown, recent_wr) -> float:
    """ADL-B: VIX-Based"""
    if pd.isna(vix): return -3.0
    if vix < 15: return -5.0
    elif vix < 20: return -4.0
    elif vix < 25: return -3.0
    elif vix < 30: return -2.0
    else: return -1.5

def adl_c_regime_vix(regime, vix, drawdown, recent_wr) -> float:
    """ADL-C: Regime + VIX Combined"""
    base = {"BULL": -4.0, "NEUTRAL": -3.0, "BEAR": -2.0}.get(regime.value, -3.0)
    if pd.isna(vix): return base
    if vix > 30: return base * 0.5
    elif vix > 25: return base * 0.7
    elif vix < 15: return base * 1.3
    return base

def adl_d_dd_aware(regime, vix, drawdown, recent_wr) -> float:
    """ADL-D: Drawdown-Aware"""
    base = {"BULL": -4.0, "NEUTRAL": -3.0, "BEAR": -2.0}.get(regime.value, -3.0)
    if drawdown > 15: return base * 0.5
    elif drawdown > 10: return base * 0.7
    elif drawdown > 5: return base * 0.85
    return base

def adl_e_full(regime, vix, drawdown, recent_wr) -> float:
    """ADL-E: Full Adaptive"""
    base = {"BULL": -4.0, "NEUTRAL": -3.0, "BEAR": -2.0}.get(regime.value, -3.0)
    vix_factor = 1.3 if (not pd.isna(vix) and vix < 15) else (0.5 if (not pd.isna(vix) and vix > 30) else 1.0)
    dd_factor = max(0.5, 1.0 - drawdown * 0.03)
    wr_factor = 0.8 if recent_wr < 50 else (1.2 if recent_wr > 65 else 1.0)
    return base * vix_factor * dd_factor * wr_factor

DAILY_LIMITS = {
    'ADL-0_none': adl_none,
    'ADL-X_fixed': adl_fixed,
    'ADL-A_regime': adl_a_regime,
    'ADL-B_vix': adl_b_vix,
    'ADL-C_regime_vix': adl_c_regime_vix,
    'ADL-D_dd_aware': adl_d_dd_aware,
    'ADL-E_full': adl_e_full,
}

# ============================================================================
# ADAPTIVE POSITION SIZING
# ============================================================================

def aps_baseline(regime, vix, drawdown, strategy, signal_score) -> float:
    return 1.0

def aps_a_regime(regime, vix, drawdown, strategy, signal_score) -> float:
    """APS-A: Regime-Based"""
    return {"BULL": 1.0, "NEUTRAL": 0.8, "BEAR": 0.6}.get(regime.value, 0.8)

def aps_b_vix(regime, vix, drawdown, strategy, signal_score) -> float:
    """APS-B: VIX-Based"""
    if pd.isna(vix): return 1.0
    if vix < 15: return 1.2
    elif vix < 20: return 1.0
    elif vix < 25: return 0.7
    elif vix < 30: return 0.5
    else: return 0.3

def aps_c_drawdown(regime, vix, drawdown, strategy, signal_score) -> float:
    """APS-C: Drawdown-Based"""
    if drawdown < 5: return 1.0
    elif drawdown < 10: return 0.7
    elif drawdown < 15: return 0.5
    else: return 0.3

def aps_d_strategy(regime, vix, drawdown, strategy, signal_score) -> float:
    """APS-D: Strategy-Based"""
    base = 1.0 if strategy == "SECTOR_ROTATION" else 0.85
    if signal_score > 80: return base * 1.2
    elif signal_score < 60: return base * 0.8
    return base

def aps_e_full(regime, vix, drawdown, strategy, signal_score) -> float:
    """APS-E: Full Adaptive"""
    regime_mult = {"BULL": 1.0, "NEUTRAL": 0.85, "BEAR": 0.7}.get(regime.value, 0.85)
    vix_mult = max(0.3, min(1.2, 1.5 - (vix if not pd.isna(vix) else 20) * 0.03))
    dd_mult = max(0.3, 1.0 - drawdown * 0.04)
    strat_mult = 1.0 if strategy == "SECTOR_ROTATION" else 0.85
    signal_mult = 0.8 + (signal_score - 50) * 0.008
    return regime_mult * vix_mult * dd_mult * strat_mult * signal_mult

POSITION_SIZING = {
    'APS-0_baseline': aps_baseline,
    'APS-A_regime': aps_a_regime,
    'APS-B_vix': aps_b_vix,
    'APS-C_drawdown': aps_c_drawdown,
    'APS-D_strategy': aps_d_strategy,
    'APS-E_full': aps_e_full,
}

# ============================================================================
# ADAPTIVE CIRCUIT BREAKERS
# ============================================================================

def acb_none(regime, vix, vix_change, drawdown, spy_1d, consec_losses) -> Tuple[str, float]:
    return "NORMAL", 1.0

def acb_a_regime(regime, vix, vix_change, drawdown, spy_1d, consec_losses) -> Tuple[str, float]:
    """ACB-A: Regime-Aware"""
    thresholds = {
        "BULL": {"warn": 12, "reduce": 18, "stop": 25},
        "NEUTRAL": {"warn": 10, "reduce": 15, "stop": 20},
        "BEAR": {"warn": 7, "reduce": 12, "stop": 15}
    }
    t = thresholds.get(regime.value, thresholds["NEUTRAL"])
    if drawdown >= t["stop"]: return "STOP_ALL", 0.0
    elif drawdown >= t["reduce"]: return "REDUCE_50", 0.5
    elif drawdown >= t["warn"]: return "REDUCE_30", 0.7
    return "NORMAL", 1.0

def acb_b_vix(regime, vix, vix_change, drawdown, spy_1d, consec_losses) -> Tuple[str, float]:
    """ACB-B: VIX-Aware"""
    if not pd.isna(vix):
        if vix > 35 or (not pd.isna(vix_change) and vix_change > 30):
            return "STOP_ALL", 0.0
        if vix > 30 or (not pd.isna(vix_change) and vix_change > 20):
            return "REDUCE_70", 0.3

    dd_threshold = 20 if (pd.isna(vix) or vix < 20) else (15 if vix < 25 else 10)
    if drawdown >= dd_threshold: return "STOP_ALL", 0.0
    elif drawdown >= dd_threshold * 0.75: return "REDUCE_50", 0.5
    return "NORMAL", 1.0

def acb_c_recovery(regime, vix, vix_change, drawdown, spy_1d, consec_losses) -> Tuple[str, float]:
    """ACB-C: Recovery-Aware"""
    if drawdown >= 15:
        if not pd.isna(spy_1d) and spy_1d > 2:
            return "RECOVERY_MODE", 0.7
        return "STOP_ALL", 0.0
    if drawdown >= 10:
        if not pd.isna(spy_1d) and spy_1d > 1:
            return "CAUTIOUS", 0.8
        return "REDUCE_50", 0.5
    return "NORMAL", 1.0

def acb_d_multi(regime, vix, vix_change, drawdown, spy_1d, consec_losses) -> Tuple[str, float]:
    """ACB-D: Multi-Factor"""
    risk_score = 0
    risk_score += {"BULL": 0, "NEUTRAL": 1, "BEAR": 2}.get(regime.value, 1)

    if not pd.isna(vix):
        if vix > 30: risk_score += 3
        elif vix > 25: risk_score += 2
        elif vix > 20: risk_score += 1

    risk_score += int(drawdown / 5)
    risk_score += min(consec_losses, 3)

    if not pd.isna(spy_1d) and spy_1d > 1:
        risk_score -= 1

    if risk_score >= 8: return "STOP_ALL", 0.0
    elif risk_score >= 6: return "REDUCE_70", 0.3
    elif risk_score >= 4: return "REDUCE_50", 0.5
    elif risk_score >= 2: return "REDUCE_20", 0.8
    return "NORMAL", 1.0

CIRCUIT_BREAKERS = {
    'ACB-0_none': acb_none,
    'ACB-A_regime': acb_a_regime,
    'ACB-B_vix': acb_b_vix,
    'ACB-C_recovery': acb_c_recovery,
    'ACB-D_multi': acb_d_multi,
}

# ============================================================================
# ADAPTIVE STOP LOSS
# ============================================================================

def asl_baseline(strategy, regime, vix, profit_pct, days_held) -> float:
    return -2.0

def asl_a_regime_vix(strategy, regime, vix, profit_pct, days_held) -> float:
    """ASL-A: Regime + VIX"""
    base = {"BULL": -2.5, "NEUTRAL": -2.0, "BEAR": -1.5}.get(regime.value, -2.0)
    if not pd.isna(vix):
        if vix > 30: return base * 0.6
        elif vix > 25: return base * 0.8
        elif vix < 15: return base * 1.2
    return base

def asl_b_strategy(strategy, regime, vix, profit_pct, days_held) -> float:
    """ASL-B: Strategy-Based"""
    base = -3.0 if strategy == "SECTOR_ROTATION" else -2.0
    regime_mult = {"BULL": 1.2, "NEUTRAL": 1.0, "BEAR": 0.8}.get(regime.value, 1.0)
    return base * regime_mult

def asl_c_atr(strategy, regime, vix, profit_pct, days_held) -> float:
    """ASL-C: ATR-Based (simplified)"""
    base_mult = {"BULL": 2.0, "NEUTRAL": 1.5, "BEAR": 1.0}.get(regime.value, 1.5)
    if not pd.isna(vix) and vix > 25:
        base_mult *= 0.8
    return -1.5 * base_mult  # Simplified: assume 1.5% ATR

def asl_d_trailing(strategy, regime, vix, profit_pct, days_held) -> float:
    """ASL-D: Trailing with Regime"""
    base_sl = -2.0
    trail_trigger = {"BULL": 3.0, "NEUTRAL": 2.5, "BEAR": 2.0}.get(regime.value, 2.5)

    if profit_pct >= trail_trigger + 1.5:
        return -1.0  # Tight trail
    elif profit_pct >= trail_trigger:
        return 0.0  # Breakeven
    return base_sl

STOP_LOSS_METHODS = {
    'ASL-0_baseline': asl_baseline,
    'ASL-A_regime_vix': asl_a_regime_vix,
    'ASL-B_strategy': asl_b_strategy,
    'ASL-C_atr': asl_c_atr,
    'ASL-D_trailing': asl_d_trailing,
}

# ============================================================================
# SIGNAL GENERATION (CONFIRMED STRATEGIES)
# ============================================================================

def find_dip_bounce_signals(stock_data: pd.DataFrame, stock: str, date) -> Optional[Tuple[float, int]]:
    try:
        closes = stock_data[('Close', stock)]
        idx = closes.index.get_loc(date)
        if idx < 2: return None
        yesterday_return = (closes.iloc[idx-1] / closes.iloc[idx-2] - 1) * 100
        today_return = (closes.iloc[idx] / closes.iloc[idx-1] - 1) * 100
        if yesterday_return <= -2 and today_return >= 1:
            score = 70 + min(abs(yesterday_return), 3) * 5 + min(today_return, 3) * 5
            return closes.iloc[idx], int(score)
        return None
    except:
        return None

def find_sector_rotation_signals(sector_metrics: dict, stock_data: pd.DataFrame,
                                  sector: str, date) -> List[Tuple[str, float, int]]:
    signals = []
    try:
        s = sector_metrics[sector]
        spy = sector_metrics['SPY']
        idx = s.index.get_loc(date)
        if idx < 1: return signals

        rs_today = s.iloc[idx]['return_20d'] - spy.iloc[idx]['return_20d']
        rs_yesterday = s.iloc[idx-1]['return_20d'] - spy.iloc[idx-1]['return_20d']
        sector_1d = s.iloc[idx]['return_1d']

        if not (rs_yesterday < 0 and rs_today > 0 and sector_1d > 0.5):
            return signals

        for stock in STOCK_UNIVERSE.get(sector, []):
            result = find_dip_bounce_signals(stock_data, stock, date)
            if result:
                entry_price, score = result
                signals.append((stock, entry_price, score + 10))  # Bonus for SR

        if not signals:
            for stock in STOCK_UNIVERSE.get(sector, [])[:2]:
                try:
                    entry_price = stock_data[('Close', stock)].loc[date]
                    signals.append((stock, entry_price, 75))
                except:
                    continue
    except:
        pass
    return signals[:2]

# ============================================================================
# TRADE SIMULATION
# ============================================================================

def simulate_trade(stock_data: pd.DataFrame, stock: str, entry_date: str,
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
        if entry_idx is None: return None

        tp = 3.0 if strategy == 'DIP_BOUNCE' else 4.0
        max_hold = hold_days if strategy == 'DIP_BOUNCE' else hold_days + 2

        for day in range(1, max_hold + 1):
            if entry_idx + day >= len(closes): break
            current_price = closes.iloc[entry_idx + day]
            pnl_pct = (current_price / entry_price - 1) * 100

            sl = sl_func(strategy, regime, vix, pnl_pct, day)

            exit_reason = ''
            if pnl_pct >= tp: exit_reason = 'TP'
            elif pnl_pct <= sl: exit_reason = 'SL'
            elif day >= max_hold: exit_reason = f'HOLD_{max_hold}D'

            if exit_reason:
                return Trade(
                    symbol=stock, sector=STOCK_TO_SECTOR.get(stock, 'Unknown'),
                    strategy=strategy, entry_date=entry_date, entry_price=entry_price,
                    exit_date=dates[entry_idx + day].strftime('%Y-%m-%d'),
                    exit_price=current_price, pnl_pct=pnl_pct, hold_days=day,
                    exit_reason=exit_reason, regime=regime.value
                )
        return None
    except:
        return None

# ============================================================================
# MAIN BACKTEST
# ============================================================================

def run_smart_backtest(market_data: pd.DataFrame, stock_data: pd.DataFrame,
                       sector_metrics: dict, adl_name: str, aps_name: str,
                       acb_name: str, asl_name: str) -> Tuple[List[Trade], dict]:

    trades = []
    state = PortfolioState()

    adl_func = DAILY_LIMITS.get(adl_name, adl_none)
    aps_func = POSITION_SIZING.get(aps_name, aps_baseline)
    acb_func = CIRCUIT_BREAKERS.get(acb_name, acb_none)
    asl_func = STOP_LOSS_METHODS.get(asl_name, asl_baseline)

    current_regime = Regime.NEUTRAL
    pending_regime = None
    pending_days = 0

    dates = market_data.index[50:]
    daily_trades = defaultdict(list)
    days_stopped = 0
    cb_triggered = 0

    for date in dates:
        try:
            row = market_data.loc[date]
            date_str = date.strftime('%Y-%m-%d')

            # Regime detection with 3-day confirmation
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

            vix = row.get('vix', 20)
            vix_change = row.get('vix_change_1d', 0)
            spy_1d = row.get('spy_return_1d', 0)

            # Circuit breaker check
            cb_status, cb_mult = acb_func(
                current_regime, vix, vix_change,
                state.current_drawdown, spy_1d, state.consecutive_losses
            )
            if cb_mult == 0:
                cb_triggered += 1
                days_stopped += 1
                continue

            # Daily limit check
            daily_limit = adl_func(current_regime, vix, state.current_drawdown, state.recent_win_rate)
            if state.daily_pnl <= daily_limit:
                days_stopped += 1
                continue

            # Strategy selection (SA-C Aggressive)
            strategies = []
            if current_regime == Regime.BULL:
                strategies = ['SECTOR_ROTATION']
            elif current_regime == Regime.BEAR:
                strategies = ['DIP_BOUNCE']
            else:
                strategies = ['SECTOR_ROTATION', 'DIP_BOUNCE']

            day_trades = []

            for strategy in strategies:
                if strategy == 'SECTOR_ROTATION':
                    for sector in SECTOR_ETFS.keys():
                        signals = find_sector_rotation_signals(sector_metrics, stock_data, sector, date)
                        for stock, entry_price, signal_score in signals:
                            ps_mult = aps_func(current_regime, vix, state.current_drawdown, strategy, signal_score)
                            final_mult = ps_mult * cb_mult

                            trade = simulate_trade(
                                stock_data, stock, date_str, entry_price,
                                'SECTOR_ROTATION', 5, current_regime, vix, asl_func
                            )
                            if trade:
                                trade.position_size = final_mult
                                trades.append(trade)
                                day_trades.append(trade)

                elif strategy == 'DIP_BOUNCE':
                    for stock in list(STOCK_TO_SECTOR.keys()):
                        result = find_dip_bounce_signals(stock_data, stock, date)
                        if result:
                            entry_price, signal_score = result
                            ps_mult = aps_func(current_regime, vix, state.current_drawdown, strategy, signal_score)
                            final_mult = ps_mult * cb_mult

                            trade = simulate_trade(
                                stock_data, stock, date_str, entry_price,
                                'DIP_BOUNCE', 3, current_regime, vix, asl_func
                            )
                            if trade:
                                trade.position_size = final_mult
                                trades.append(trade)
                                day_trades.append(trade)

            # Update state
            day_pnl = sum(t.pnl_pct * t.position_size for t in day_trades)
            state.daily_pnl = day_pnl
            state.pnl_history.append(day_pnl)

            if day_pnl < 0:
                state.consecutive_losses += 1
            else:
                state.consecutive_losses = 0

            state.equity += day_pnl
            state.peak_equity = max(state.peak_equity, state.equity)
            state.current_drawdown = (state.peak_equity - state.equity) / state.peak_equity * 100 if state.peak_equity > 0 else 0

            if state.current_drawdown > 0:
                state.days_since_peak += 1
            else:
                state.days_since_peak = 0

            # Update recent win rate
            recent_trades = trades[-20:] if len(trades) >= 20 else trades
            if recent_trades:
                wins = [t for t in recent_trades if t.pnl_pct > 0]
                state.recent_win_rate = len(wins) / len(recent_trades) * 100

        except Exception as e:
            continue

    stats = {
        'days_stopped': days_stopped,
        'cb_triggered': cb_triggered
    }

    return trades, stats

def calculate_metrics(trades: List[Trade]) -> dict:
    if not trades:
        return {'win_rate': 0, 'avg_pnl': 0, 'total_pnl': 0, 'sharpe': 0, 'max_dd': 0, 'trades': 0, 'avg_size': 0}

    pnls = [t.pnl_pct * t.position_size for t in trades]
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

    avg_size = np.mean([t.position_size for t in trades])

    return {
        'win_rate': win_rate, 'avg_pnl': avg_pnl, 'total_pnl': total_pnl,
        'sharpe': sharpe, 'max_dd': max_dd, 'trades': len(trades), 'avg_size': avg_size
    }

def calculate_regime_breakdown(trades: List[Trade]) -> dict:
    results = {}
    for regime in ['BULL', 'BEAR', 'NEUTRAL']:
        regime_trades = [t for t in trades if t.regime == regime]
        if regime_trades:
            wins = [t for t in regime_trades if t.pnl_pct > 0]
            results[regime] = {'win_rate': len(wins) / len(regime_trades) * 100, 'trades': len(regime_trades)}
        else:
            results[regime] = {'win_rate': 0, 'trades': 0}
    return results

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 90)
    print("🧠 SMART ADAPTIVE DRAWDOWN CONTROL - FULL INTEGRATION TEST")
    print("=" * 90)

    etf_data, stock_data = download_data('1y')
    market_data = prepare_market_data(etf_data)
    sector_metrics = calculate_sector_metrics(etf_data)

    # =========================================================================
    # Part 1: Daily Limits
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 1: ADAPTIVE DAILY LIMITS")
    print("=" * 90)

    adl_results = {}
    for adl_name in DAILY_LIMITS.keys():
        print(f"  Testing {adl_name}...")
        trades, stats = run_smart_backtest(
            market_data, stock_data, sector_metrics,
            adl_name, 'APS-0_baseline', 'ACB-0_none', 'ASL-0_baseline'
        )
        metrics = calculate_metrics(trades)
        adl_results[adl_name] = {**metrics, 'days_stopped': stats['days_stopped']}

    print(f"\n{'Method':<20} {'MaxDD':>8} {'Win%':>8} {'Trades':>8} {'Stopped':>8} {'Sharpe':>8}")
    print("-" * 70)
    for name, m in sorted(adl_results.items(), key=lambda x: -x[1]['trades']):
        print(f"{name:<20} {m['max_dd']:>7.1f}% {m['win_rate']:>7.1f}% {m['trades']:>8} {m['days_stopped']:>8} {m['sharpe']:>8.2f}")

    # =========================================================================
    # Part 2: Position Sizing
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 2: ADAPTIVE POSITION SIZING")
    print("=" * 90)

    aps_results = {}
    for aps_name in POSITION_SIZING.keys():
        print(f"  Testing {aps_name}...")
        trades, stats = run_smart_backtest(
            market_data, stock_data, sector_metrics,
            'ADL-0_none', aps_name, 'ACB-0_none', 'ASL-0_baseline'
        )
        aps_results[aps_name] = calculate_metrics(trades)

    print(f"\n{'Method':<20} {'MaxDD':>8} {'Win%':>8} {'AvgSize':>8} {'Sharpe':>8} {'Trades':>8}")
    print("-" * 70)
    for name, m in sorted(aps_results.items(), key=lambda x: x[1]['max_dd']):
        print(f"{name:<20} {m['max_dd']:>7.1f}% {m['win_rate']:>7.1f}% {m['avg_size']:>7.2f}x {m['sharpe']:>8.2f} {m['trades']:>8}")

    # =========================================================================
    # Part 3: Circuit Breakers
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 3: ADAPTIVE CIRCUIT BREAKERS")
    print("=" * 90)

    acb_results = {}
    for acb_name in CIRCUIT_BREAKERS.keys():
        print(f"  Testing {acb_name}...")
        trades, stats = run_smart_backtest(
            market_data, stock_data, sector_metrics,
            'ADL-0_none', 'APS-0_baseline', acb_name, 'ASL-0_baseline'
        )
        acb_results[acb_name] = {**calculate_metrics(trades), 'triggered': stats['cb_triggered']}

    print(f"\n{'Method':<20} {'MaxDD':>8} {'Win%':>8} {'Triggered':>10} {'Trades':>8}")
    print("-" * 65)
    for name, m in sorted(acb_results.items(), key=lambda x: x[1]['max_dd']):
        print(f"{name:<20} {m['max_dd']:>7.1f}% {m['win_rate']:>7.1f}% {m['triggered']:>10} {m['trades']:>8}")

    # =========================================================================
    # Part 4: Stop Loss
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 4: ADAPTIVE STOP LOSS")
    print("=" * 90)

    asl_results = {}
    for asl_name in STOP_LOSS_METHODS.keys():
        print(f"  Testing {asl_name}...")
        trades, stats = run_smart_backtest(
            market_data, stock_data, sector_metrics,
            'ADL-0_none', 'APS-0_baseline', 'ACB-0_none', asl_name
        )
        asl_results[asl_name] = calculate_metrics(trades)

    print(f"\n{'Method':<20} {'MaxDD':>8} {'Win%':>8} {'AvgP&L':>8} {'Trades':>8}")
    print("-" * 60)
    for name, m in sorted(asl_results.items(), key=lambda x: x[1]['max_dd']):
        print(f"{name:<20} {m['max_dd']:>7.1f}% {m['win_rate']:>7.1f}% {m['avg_pnl']:>+7.2f}% {m['trades']:>8}")

    # =========================================================================
    # Part 5: Smart Combinations
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 5: SMART ADAPTIVE COMBINATIONS")
    print("=" * 90)

    combos = {
        'BASELINE': ('ADL-0_none', 'APS-0_baseline', 'ACB-0_none', 'ASL-0_baseline'),
        'SMART-A_conservative': ('ADL-C_regime_vix', 'APS-C_drawdown', 'ACB-A_regime', 'ASL-A_regime_vix'),
        'SMART-B_balanced': ('ADL-D_dd_aware', 'APS-E_full', 'ACB-C_recovery', 'ASL-B_strategy'),
        'SMART-C_aggressive': ('ADL-A_regime', 'APS-D_strategy', 'ACB-D_multi', 'ASL-D_trailing'),
        'SMART-D_vix_focused': ('ADL-B_vix', 'APS-B_vix', 'ACB-B_vix', 'ASL-A_regime_vix'),
        'SMART-E_full': ('ADL-E_full', 'APS-E_full', 'ACB-D_multi', 'ASL-D_trailing'),
        'OPTIMAL': ('ADL-A_regime', 'APS-C_drawdown', 'ACB-A_regime', 'ASL-D_trailing'),
    }

    combo_results = {}
    for combo_name, (adl, aps, acb, asl) in combos.items():
        print(f"  Testing {combo_name}...")
        trades, stats = run_smart_backtest(
            market_data, stock_data, sector_metrics, adl, aps, acb, asl
        )
        metrics = calculate_metrics(trades)
        regime = calculate_regime_breakdown(trades)
        combo_results[combo_name] = {**metrics, 'regime': regime, 'stopped': stats['days_stopped']}

    print(f"\n{'Combo':<25} {'MaxDD':>8} {'Win%':>8} {'Sharpe':>8} {'Trades':>8} {'BULL%':>8} {'BEAR%':>8} {'NEUT%':>8}")
    print("-" * 105)
    for name, m in sorted(combo_results.items(), key=lambda x: (-x[1]['trades'], x[1]['max_dd'])):
        r = m['regime']
        print(f"{name:<25} {m['max_dd']:>7.1f}% {m['win_rate']:>7.1f}% {m['sharpe']:>8.2f} {m['trades']:>8} {r['BULL']['win_rate']:>7.1f}% {r['BEAR']['win_rate']:>7.1f}% {r['NEUTRAL']['win_rate']:>7.1f}%")

    # =========================================================================
    # SUCCESS CRITERIA
    # =========================================================================
    print("\n" + "=" * 90)
    print("✅ SUCCESS CRITERIA CHECK")
    print("=" * 90)

    print(f"\nTarget: MaxDD<20%, Win%>58%, Sharpe>3.0, Trades>100")
    print("-" * 80)

    successful = []
    for name, m in combo_results.items():
        passes_dd = m['max_dd'] < 20
        passes_wr = m['win_rate'] > 58
        passes_sharpe = m['sharpe'] > 3.0
        passes_trades = m['trades'] > 100
        passes_all_regime = all(m['regime'][r]['win_rate'] >= 50 for r in ['BULL', 'BEAR', 'NEUTRAL'] if m['regime'][r]['trades'] > 5)

        score = sum([passes_dd, passes_wr, passes_sharpe, passes_trades])

        if passes_dd and passes_wr and passes_sharpe and passes_trades:
            successful.append((name, m))
            print(f"✅ {name}: DD={m['max_dd']:.1f}%, Win={m['win_rate']:.1f}%, Sharpe={m['sharpe']:.2f}, Trades={m['trades']}")
        elif score >= 3:
            print(f"⚠️  {name}: DD={m['max_dd']:.1f}%, Win={m['win_rate']:.1f}%, Sharpe={m['sharpe']:.2f}, Trades={m['trades']} ({score}/4 criteria)")

    # =========================================================================
    # ANSWERS
    # =========================================================================
    print("\n" + "=" * 90)
    print("❓ ANSWERS TO KEY QUESTIONS")
    print("=" * 90)

    baseline = combo_results['BASELINE']

    # Q1: Adaptive vs Fixed
    fixed_dl = adl_results.get('ADL-X_fixed', {})
    regime_dl = adl_results.get('ADL-A_regime', {})

    print(f"""
Q1: Adaptive ดีกว่า Fixed ไหม?
    Fixed -2%: Trades={fixed_dl.get('trades', 0)}, Win={fixed_dl.get('win_rate', 0):.1f}%
    ADL-A Regime: Trades={regime_dl.get('trades', 0)}, Win={regime_dl.get('win_rate', 0):.1f}%
    Answer: {'✅ YES - More trades!' if regime_dl.get('trades', 0) > fixed_dl.get('trades', 0) else '❌ NO'}

Q2: Component ไหนสำคัญสุด?
    Daily Limit impact: {baseline['max_dd'] - min(m['max_dd'] for m in adl_results.values()):.1f}% DD reduction
    Position Sizing impact: {baseline['max_dd'] - min(m['max_dd'] for m in aps_results.values()):.1f}% DD reduction
    Circuit Breaker impact: {baseline['max_dd'] - min(m['max_dd'] for m in acb_results.values()):.1f}% DD reduction
    Stop Loss impact: {baseline['max_dd'] - min(m['max_dd'] for m in asl_results.values()):.1f}% DD reduction
""")

    # Find best
    if successful:
        best = max(successful, key=lambda x: (x[1]['trades'], -x[1]['max_dd']))
        best_name, best_m = best
    else:
        # Find closest
        best_name = max(combo_results.items(), key=lambda x: (x[1]['trades'], -x[1]['max_dd']) if x[0] != 'BASELINE' else (0, 0))[0]
        best_m = combo_results[best_name]

    print(f"""
Q3: Combination ไหนดีสุด?
    Best: {best_name}
    - Max DD: {best_m['max_dd']:.1f}%
    - Win Rate: {best_m['win_rate']:.1f}%
    - Sharpe: {best_m['sharpe']:.2f}
    - Trades: {best_m['trades']}

Q4: Recovery-Aware ช่วยไหม?
    ACB-C Recovery: DD={acb_results['ACB-C_recovery']['max_dd']:.1f}%, Trades={acb_results['ACB-C_recovery']['trades']}
    ACB-A Regime: DD={acb_results['ACB-A_regime']['max_dd']:.1f}%, Trades={acb_results['ACB-A_regime']['trades']}
    Answer: {'✅ Yes - Better balance' if acb_results['ACB-C_recovery']['trades'] > acb_results['ACB-A_regime']['trades'] else 'Similar'}

Q5: Strategy-specific DD control ช่วยไหม?
    APS-D Strategy: DD={aps_results['APS-D_strategy']['max_dd']:.1f}%, Win={aps_results['APS-D_strategy']['win_rate']:.1f}%
    APS-0 Baseline: DD={aps_results['APS-0_baseline']['max_dd']:.1f}%, Win={aps_results['APS-0_baseline']['win_rate']:.1f}%
""")

    # =========================================================================
    # FINAL RECOMMENDATION
    # =========================================================================
    print("\n" + "=" * 90)
    print("✅ FINAL RECOMMENDATION")
    print("=" * 90)

    best_config = combos[best_name]

    print(f"""
🏆 BEST CONFIGURATION: {best_name}

Components:
- Daily Limit: {best_config[0]}
- Position Sizing: {best_config[1]}
- Circuit Breaker: {best_config[2]}
- Stop Loss: {best_config[3]}

Performance:
- Max DD: {best_m['max_dd']:.1f}% {'✅' if best_m['max_dd'] < 20 else '⚠️'}
- Win Rate: {best_m['win_rate']:.1f}% {'✅' if best_m['win_rate'] > 58 else '⚠️'}
- Sharpe: {best_m['sharpe']:.2f} {'✅' if best_m['sharpe'] > 3.0 else '⚠️'}
- Trades/Year: {best_m['trades']} {'✅' if best_m['trades'] > 100 else '⚠️'}

By Regime:
- BULL: {best_m['regime']['BULL']['win_rate']:.1f}% ({best_m['regime']['BULL']['trades']} trades)
- BEAR: {best_m['regime']['BEAR']['win_rate']:.1f}% ({best_m['regime']['BEAR']['trades']} trades)
- NEUTRAL: {best_m['regime']['NEUTRAL']['win_rate']:.1f}% ({best_m['regime']['NEUTRAL']['trades']} trades)

vs Baseline:
- DD: {best_m['max_dd'] - baseline['max_dd']:+.1f}%
- Win Rate: {best_m['win_rate'] - baseline['win_rate']:+.1f}%
- Trades: {best_m['trades'] - baseline['trades']:+d}
""")

    criteria_passed = sum([
        best_m['max_dd'] < 20,
        best_m['win_rate'] > 58,
        best_m['sharpe'] > 3.0,
        best_m['trades'] > 100
    ])

    if criteria_passed == 4:
        print("🎉 ALL CRITERIA PASSED! Ready for implementation.")
    else:
        print(f"⚠️  {criteria_passed}/4 criteria passed. Consider trade-offs.")

    print("\n" + "=" * 90)
    print("🏁 BACKTEST COMPLETE")
    print("=" * 90)

if __name__ == '__main__':
    main()
