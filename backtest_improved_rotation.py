#!/usr/bin/env python3
"""
Improved Strategy Rotation Backtest
Increase trades while maintaining quality
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
    is_fallback: bool = False

@dataclass
class PortfolioState:
    equity: float = 100.0
    peak_equity: float = 100.0
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    sr_daily_pnl: float = 0.0
    db_daily_pnl: float = 0.0
    recent_win_rate: float = 50.0
    recent_sr_win_rate: float = 50.0
    recent_db_win_rate: float = 50.0

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
    except:
        df['vix'] = 20

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

def calculate_regime_score(row) -> int:
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
    return score

# ============================================================================
# REGIME THRESHOLD METHODS
# ============================================================================

def rt_a_original(score, vix) -> Regime:
    """RT-A: Original ±2"""
    if score >= 2: return Regime.BULL
    elif score <= -2: return Regime.BEAR
    return Regime.NEUTRAL

def rt_b_wider(score, vix) -> Regime:
    """RT-B: Wider NEUTRAL ±3"""
    if score >= 3: return Regime.BULL
    elif score <= -3: return Regime.BEAR
    return Regime.NEUTRAL

def rt_c_even_wider(score, vix) -> Regime:
    """RT-C: Even Wider NEUTRAL (4/-3)"""
    if score == 4: return Regime.BULL
    elif score <= -3: return Regime.BEAR
    return Regime.NEUTRAL

def rt_d_asymmetric(score, vix) -> Regime:
    """RT-D: Asymmetric (Easier BEAR)"""
    if score >= 3: return Regime.BULL
    elif score <= -1: return Regime.BEAR
    return Regime.NEUTRAL

def rt_e_vix_adjusted(score, vix) -> Regime:
    """RT-E: VIX-Adjusted Threshold"""
    if not pd.isna(vix) and vix > 25:
        if score >= 3: return Regime.BULL
        elif score <= -1: return Regime.BEAR
    else:
        if score >= 2: return Regime.BULL
        elif score <= -2: return Regime.BEAR
    return Regime.NEUTRAL

REGIME_THRESHOLDS = {
    'RT-A_original': rt_a_original,
    'RT-B_wider': rt_b_wider,
    'RT-C_even_wider': rt_c_even_wider,
    'RT-D_asymmetric': rt_d_asymmetric,
    'RT-E_vix_adjusted': rt_e_vix_adjusted,
}

# ============================================================================
# STRATEGY SELECTION METHODS
# ============================================================================

def ss_a_exclusive(regime, sr_available, db_available) -> List[Tuple[str, int, bool]]:
    """SS-A: Original Exclusive"""
    if regime == Regime.BULL:
        return [("SECTOR_ROTATION", 1, False)] if sr_available else []
    elif regime == Regime.BEAR:
        return [("DIP_BOUNCE", 1, False)] if db_available else []
    else:
        result = []
        if sr_available: result.append(("SECTOR_ROTATION", 1, False))
        if db_available: result.append(("DIP_BOUNCE", 1, False))
        return result

def ss_b_fallback(regime, sr_available, db_available) -> List[Tuple[str, int, bool]]:
    """SS-B: Primary + Fallback"""
    if regime == Regime.BULL:
        if sr_available: return [("SECTOR_ROTATION", 1, False)]
        elif db_available: return [("DIP_BOUNCE", 2, True)]  # Fallback
    elif regime == Regime.BEAR:
        if db_available: return [("DIP_BOUNCE", 1, False)]
        elif sr_available: return [("SECTOR_ROTATION", 2, True)]  # Fallback
    else:
        result = []
        if sr_available: result.append(("SECTOR_ROTATION", 1, False))
        if db_available: result.append(("DIP_BOUNCE", 1, False))
        return result
    return []

def ss_c_always_both(regime, sr_available, db_available) -> List[Tuple[str, int, bool]]:
    """SS-C: Always Both with Priority"""
    result = []
    if regime == Regime.BULL:
        if sr_available: result.append(("SECTOR_ROTATION", 1, False))
        if db_available: result.append(("DIP_BOUNCE", 2, False))
    elif regime == Regime.BEAR:
        if db_available: result.append(("DIP_BOUNCE", 1, False))
        if sr_available: result.append(("SECTOR_ROTATION", 2, False))
    else:
        if sr_available: result.append(("SECTOR_ROTATION", 1, False))
        if db_available: result.append(("DIP_BOUNCE", 1, False))
    return result

def ss_d_signal_strength(regime, sr_available, db_available, sr_score=70, db_score=70) -> List[Tuple[str, int, bool]]:
    """SS-D: Signal Strength Based"""
    result = []
    if regime == Regime.BULL:
        if sr_available and sr_score >= 75: result.append(("SECTOR_ROTATION", 1, False))
        elif db_available and db_score >= 80: result.append(("DIP_BOUNCE", 2, True))
        elif sr_available: result.append(("SECTOR_ROTATION", 1, False))
    elif regime == Regime.BEAR:
        if db_available and db_score >= 70: result.append(("DIP_BOUNCE", 1, False))
        elif sr_available and sr_score >= 85: result.append(("SECTOR_ROTATION", 2, True))
        elif db_available: result.append(("DIP_BOUNCE", 1, False))
    else:
        if sr_available: result.append(("SECTOR_ROTATION", 1, False))
        if db_available: result.append(("DIP_BOUNCE", 1, False))
    return result

STRATEGY_SELECTIONS = {
    'SS-A_exclusive': ss_a_exclusive,
    'SS-B_fallback': ss_b_fallback,
    'SS-C_always_both': ss_c_always_both,
}

# ============================================================================
# DD CONTROL BY STRATEGY
# ============================================================================

def dc_a_regime_only(strategy, regime, recent_wr) -> float:
    """DC-A: Regime-Based Only"""
    return {"BULL": -4.0, "NEUTRAL": -3.0, "BEAR": -2.0}.get(regime.value, -3.0)

def dc_b_strategy_specific(strategy, regime, recent_wr) -> float:
    """DC-B: Strategy-Specific DD Control"""
    if strategy == "SECTOR_ROTATION":
        base = {"BULL": -5.0, "NEUTRAL": -4.0, "BEAR": -3.0}
    else:
        base = {"BULL": -3.5, "NEUTRAL": -3.0, "BEAR": -2.5}
    return base.get(regime.value, -3.0)

def dc_c_win_rate_adjusted(strategy, regime, recent_wr) -> float:
    """DC-C: Win Rate Adjusted"""
    base = dc_b_strategy_specific(strategy, regime, recent_wr)
    if recent_wr > 65: return base * 1.3
    elif recent_wr < 45: return base * 0.7
    return base

def dc_d_separate_limits(strategy, regime, recent_wr) -> float:
    """DC-D: Separate Limits - looser for both"""
    if strategy == "SECTOR_ROTATION":
        return {"BULL": -5.0, "NEUTRAL": -4.5, "BEAR": -4.0}.get(regime.value, -4.0)
    else:
        return {"BULL": -4.0, "NEUTRAL": -3.5, "BEAR": -3.0}.get(regime.value, -3.0)

def dc_e_balanced(strategy, regime, recent_wr) -> float:
    """DC-E: Balanced - moderate limits"""
    if strategy == "SECTOR_ROTATION":
        base = {"BULL": -4.5, "NEUTRAL": -4.0, "BEAR": -3.5}
    else:
        base = {"BULL": -3.5, "NEUTRAL": -3.0, "BEAR": -2.5}

    # Small win rate adjustment
    result = base.get(regime.value, -3.5)
    if recent_wr > 60: result *= 1.15
    elif recent_wr < 50: result *= 0.85
    return result

DD_CONTROLS = {
    'DC-A_regime': dc_a_regime_only,
    'DC-B_strategy': dc_b_strategy_specific,
    'DC-C_winrate': dc_c_win_rate_adjusted,
    'DC-D_separate': dc_d_separate_limits,
    'DC-E_balanced': dc_e_balanced,
}

# ============================================================================
# SIGNAL GENERATION
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
                signals.append((stock, entry_price, score + 10))

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

def check_signals_available(sector_metrics: dict, stock_data: pd.DataFrame, date) -> Tuple[bool, bool, int, int]:
    """Check if SR and DB signals are available"""
    sr_available = False
    sr_score = 0
    db_available = False
    db_score = 0

    # Check SR signals
    for sector in SECTOR_ETFS.keys():
        signals = find_sector_rotation_signals(sector_metrics, stock_data, sector, date)
        if signals:
            sr_available = True
            sr_score = max(sr_score, max(s[2] for s in signals))

    # Check DB signals
    for stock in list(STOCK_TO_SECTOR.keys())[:30]:  # Sample for speed
        result = find_dip_bounce_signals(stock_data, stock, date)
        if result:
            db_available = True
            db_score = max(db_score, result[1])

    return sr_available, db_available, sr_score, db_score

# ============================================================================
# TRADE SIMULATION
# ============================================================================

def simulate_trade(stock_data: pd.DataFrame, stock: str, entry_date: str,
                   entry_price: float, strategy: str, hold_days: int,
                   regime: Regime) -> Optional[Trade]:
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
        sl = -2.0 if strategy == 'DIP_BOUNCE' else -2.5
        max_hold = hold_days if strategy == 'DIP_BOUNCE' else hold_days + 2

        for day in range(1, max_hold + 1):
            if entry_idx + day >= len(closes): break
            current_price = closes.iloc[entry_idx + day]
            pnl_pct = (current_price / entry_price - 1) * 100

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

def run_improved_backtest(market_data: pd.DataFrame, stock_data: pd.DataFrame,
                          sector_metrics: dict, rt_name: str, ss_name: str,
                          dc_name: str) -> Tuple[List[Trade], dict]:

    trades = []
    state = PortfolioState()

    rt_func = REGIME_THRESHOLDS.get(rt_name, rt_a_original)
    ss_func = STRATEGY_SELECTIONS.get(ss_name, ss_a_exclusive)
    dc_func = DD_CONTROLS.get(dc_name, dc_a_regime_only)

    current_regime = Regime.NEUTRAL
    pending_regime = None
    pending_days = 0

    dates = market_data.index[50:]
    regime_counts = defaultdict(int)
    fallback_count = 0
    sr_trades = []
    db_trades = []

    for date in dates:
        try:
            row = market_data.loc[date]
            date_str = date.strftime('%Y-%m-%d')

            # Calculate regime score
            score = calculate_regime_score(row)
            vix = row.get('vix', 20)

            # Detect regime with threshold
            new_regime = rt_func(score, vix)

            # 3-day confirmation
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

            regime_counts[current_regime.value] += 1

            # Check available signals
            sr_available, db_available, sr_score, db_score = check_signals_available(
                sector_metrics, stock_data, date
            )

            # Get strategies based on selection method
            strategies = ss_func(current_regime, sr_available, db_available)

            for strategy, priority, is_fallback in strategies:
                # Get DD limit for this strategy
                recent_wr = state.recent_sr_win_rate if strategy == "SECTOR_ROTATION" else state.recent_db_win_rate
                daily_limit = dc_func(strategy, current_regime, recent_wr)

                # Check daily limit
                strategy_daily_pnl = state.sr_daily_pnl if strategy == "SECTOR_ROTATION" else state.db_daily_pnl
                if strategy_daily_pnl <= daily_limit:
                    continue

                # Execute trades
                day_trades = []

                if strategy == 'SECTOR_ROTATION':
                    for sector in SECTOR_ETFS.keys():
                        signals = find_sector_rotation_signals(sector_metrics, stock_data, sector, date)
                        for stock, entry_price, signal_score in signals:
                            trade = simulate_trade(
                                stock_data, stock, date_str, entry_price,
                                'SECTOR_ROTATION', 5, current_regime
                            )
                            if trade:
                                trade.is_fallback = is_fallback
                                if is_fallback: fallback_count += 1
                                trades.append(trade)
                                sr_trades.append(trade)
                                day_trades.append(trade)

                elif strategy == 'DIP_BOUNCE':
                    for stock in list(STOCK_TO_SECTOR.keys()):
                        result = find_dip_bounce_signals(stock_data, stock, date)
                        if result:
                            entry_price, signal_score = result
                            trade = simulate_trade(
                                stock_data, stock, date_str, entry_price,
                                'DIP_BOUNCE', 3, current_regime
                            )
                            if trade:
                                trade.is_fallback = is_fallback
                                if is_fallback: fallback_count += 1
                                trades.append(trade)
                                db_trades.append(trade)
                                day_trades.append(trade)

                # Update strategy-specific daily P&L
                for t in day_trades:
                    if t.strategy == "SECTOR_ROTATION":
                        state.sr_daily_pnl += t.pnl_pct
                    else:
                        state.db_daily_pnl += t.pnl_pct

            # Update state at end of day
            state.daily_pnl = state.sr_daily_pnl + state.db_daily_pnl
            state.equity += state.daily_pnl
            state.peak_equity = max(state.peak_equity, state.equity)
            state.current_drawdown = (state.peak_equity - state.equity) / state.peak_equity * 100 if state.peak_equity > 0 else 0

            # Reset daily P&L
            state.sr_daily_pnl = 0
            state.db_daily_pnl = 0

            # Update win rates
            recent_sr = sr_trades[-20:] if len(sr_trades) >= 20 else sr_trades
            recent_db = db_trades[-20:] if len(db_trades) >= 20 else db_trades
            if recent_sr:
                state.recent_sr_win_rate = len([t for t in recent_sr if t.pnl_pct > 0]) / len(recent_sr) * 100
            if recent_db:
                state.recent_db_win_rate = len([t for t in recent_db if t.pnl_pct > 0]) / len(recent_db) * 100

        except Exception as e:
            continue

    total_days = sum(regime_counts.values())
    stats = {
        'regime_distribution': {k: v / total_days * 100 for k, v in regime_counts.items()},
        'fallback_count': fallback_count,
        'sr_trades': len(sr_trades),
        'db_trades': len(db_trades)
    }

    return trades, stats

def calculate_metrics(trades: List[Trade]) -> dict:
    if not trades:
        return {'win_rate': 0, 'avg_pnl': 0, 'total_pnl': 0, 'sharpe': 0, 'max_dd': 0, 'trades': 0}

    pnls = [t.pnl_pct for t in trades]
    wins = [p for p in pnls if p > 0]
    win_rate = len(wins) / len(pnls) * 100
    avg_pnl = np.mean(pnls)
    total_pnl = sum(pnls)
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 else 0

    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0

    return {
        'win_rate': win_rate, 'avg_pnl': avg_pnl, 'total_pnl': total_pnl,
        'sharpe': sharpe, 'max_dd': max_dd, 'trades': len(trades)
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

def calculate_strategy_breakdown(trades: List[Trade]) -> dict:
    results = {}
    for strategy in ['SECTOR_ROTATION', 'DIP_BOUNCE']:
        strat_trades = [t for t in trades if t.strategy == strategy]
        if strat_trades:
            wins = [t for t in strat_trades if t.pnl_pct > 0]
            results[strategy] = {'win_rate': len(wins) / len(strat_trades) * 100, 'trades': len(strat_trades)}
        else:
            results[strategy] = {'win_rate': 0, 'trades': 0}
    return results

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 90)
    print("🔄 IMPROVED STRATEGY ROTATION BACKTEST")
    print("=" * 90)

    etf_data, stock_data = download_data('1y')
    market_data = prepare_market_data(etf_data)
    sector_metrics = calculate_sector_metrics(etf_data)

    # =========================================================================
    # Part 1: Regime Thresholds
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 1: REGIME THRESHOLD IMPACT")
    print("=" * 90)

    rt_results = {}
    for rt_name in REGIME_THRESHOLDS.keys():
        print(f"  Testing {rt_name}...")
        trades, stats = run_improved_backtest(
            market_data, stock_data, sector_metrics,
            rt_name, 'SS-A_exclusive', 'DC-A_regime'
        )
        metrics = calculate_metrics(trades)
        regime_bd = calculate_regime_breakdown(trades)
        rt_results[rt_name] = {**metrics, 'regime_dist': stats['regime_distribution'], 'regime_bd': regime_bd}

    print(f"\n{'Config':<20} {'BULL%':>8} {'BEAR%':>8} {'NEUT%':>8} {'Trades':>8} {'Win%':>8} {'MaxDD':>8}")
    print("-" * 85)
    for name, m in sorted(rt_results.items(), key=lambda x: -x[1]['trades']):
        rd = m['regime_dist']
        print(f"{name:<20} {rd.get('BULL', 0):>7.1f}% {rd.get('BEAR', 0):>7.1f}% {rd.get('NEUTRAL', 0):>7.1f}% {m['trades']:>8} {m['win_rate']:>7.1f}% {m['max_dd']:>7.1f}%")

    # =========================================================================
    # Part 2: Strategy Selection
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 2: STRATEGY SELECTION IMPACT")
    print("=" * 90)

    # Use best RT
    best_rt = max(rt_results.items(), key=lambda x: x[1]['trades'])[0]

    ss_results = {}
    for ss_name in STRATEGY_SELECTIONS.keys():
        print(f"  Testing {ss_name} with {best_rt}...")
        trades, stats = run_improved_backtest(
            market_data, stock_data, sector_metrics,
            best_rt, ss_name, 'DC-A_regime'
        )
        metrics = calculate_metrics(trades)
        strat_bd = calculate_strategy_breakdown(trades)
        regime_bd = calculate_regime_breakdown(trades)
        ss_results[ss_name] = {**metrics, 'strat_bd': strat_bd, 'regime_bd': regime_bd,
                               'fallback': stats['fallback_count'], 'sr': stats['sr_trades'], 'db': stats['db_trades']}

    print(f"\n{'Config':<20} {'SR Trades':>10} {'DB Trades':>10} {'Total':>8} {'Win%':>8} {'Fallback':>10}")
    print("-" * 80)
    for name, m in sorted(ss_results.items(), key=lambda x: -x[1]['trades']):
        print(f"{name:<20} {m['sr']:>10} {m['db']:>10} {m['trades']:>8} {m['win_rate']:>7.1f}% {m['fallback']:>10}")

    # =========================================================================
    # Part 3: DD Control by Strategy
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 3: DD CONTROL BY STRATEGY")
    print("=" * 90)

    best_ss = max(ss_results.items(), key=lambda x: x[1]['trades'])[0]

    dc_results = {}
    for dc_name in DD_CONTROLS.keys():
        print(f"  Testing {dc_name}...")
        trades, stats = run_improved_backtest(
            market_data, stock_data, sector_metrics,
            best_rt, best_ss, dc_name
        )
        metrics = calculate_metrics(trades)
        strat_bd = calculate_strategy_breakdown(trades)
        regime_bd = calculate_regime_breakdown(trades)
        dc_results[dc_name] = {**metrics, 'strat_bd': strat_bd, 'regime_bd': regime_bd,
                               'sr': stats['sr_trades'], 'db': stats['db_trades']}

    print(f"\n{'Config':<20} {'SR Trades':>10} {'SR Win%':>10} {'DB Trades':>10} {'DB Win%':>10} {'MaxDD':>8}")
    print("-" * 85)
    for name, m in sorted(dc_results.items(), key=lambda x: -x[1]['trades']):
        sr = m['strat_bd'].get('SECTOR_ROTATION', {})
        db = m['strat_bd'].get('DIP_BOUNCE', {})
        print(f"{name:<20} {sr.get('trades', 0):>10} {sr.get('win_rate', 0):>9.1f}% {db.get('trades', 0):>10} {db.get('win_rate', 0):>9.1f}% {m['max_dd']:>7.1f}%")

    # =========================================================================
    # Part 4: Hybrid Combinations
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 4: HYBRID COMBINATIONS")
    print("=" * 90)

    hybrids = {
        'BASELINE': ('RT-A_original', 'SS-A_exclusive', 'DC-A_regime'),
        'HY-A_wide_fallback_strat': ('RT-B_wider', 'SS-B_fallback', 'DC-B_strategy'),
        'HY-B_vix_both_winrate': ('RT-E_vix_adjusted', 'SS-C_always_both', 'DC-C_winrate'),
        'HY-C_wider_both_separate': ('RT-B_wider', 'SS-C_always_both', 'DC-D_separate'),
        'HY-D_asym_fallback_balanced': ('RT-D_asymmetric', 'SS-B_fallback', 'DC-E_balanced'),
        'HY-E_wider_both_balanced': ('RT-B_wider', 'SS-C_always_both', 'DC-E_balanced'),
        'HY-F_evenwide_both_separate': ('RT-C_even_wider', 'SS-C_always_both', 'DC-D_separate'),
    }

    hybrid_results = {}
    for hy_name, (rt, ss, dc) in hybrids.items():
        print(f"  Testing {hy_name}...")
        trades, stats = run_improved_backtest(
            market_data, stock_data, sector_metrics, rt, ss, dc
        )
        metrics = calculate_metrics(trades)
        regime_bd = calculate_regime_breakdown(trades)
        strat_bd = calculate_strategy_breakdown(trades)
        hybrid_results[hy_name] = {**metrics, 'regime_bd': regime_bd, 'strat_bd': strat_bd,
                                    'sr': stats['sr_trades'], 'db': stats['db_trades'],
                                    'fallback': stats['fallback_count']}

    print(f"\n{'Hybrid':<30} {'Trades':>8} {'Win%':>8} {'Sharpe':>8} {'MaxDD':>8} {'BULL%':>8} {'BEAR%':>8} {'NEUT%':>8}")
    print("-" * 115)
    for name, m in sorted(hybrid_results.items(), key=lambda x: (-x[1]['trades'], x[1]['max_dd'])):
        rb = m['regime_bd']
        print(f"{name:<30} {m['trades']:>8} {m['win_rate']:>7.1f}% {m['sharpe']:>8.2f} {m['max_dd']:>7.1f}% {rb['BULL']['win_rate']:>7.1f}% {rb['BEAR']['win_rate']:>7.1f}% {rb['NEUTRAL']['win_rate']:>7.1f}%")

    # =========================================================================
    # SUCCESS CRITERIA
    # =========================================================================
    print("\n" + "=" * 90)
    print("✅ SUCCESS CRITERIA CHECK")
    print("=" * 90)

    print(f"\nTarget: MaxDD<15%, Win%>60%, Sharpe>5.0, Trades>100, BEAR%>60%")
    print("-" * 80)

    successful = []
    for name, m in hybrid_results.items():
        passes_dd = m['max_dd'] < 15
        passes_wr = m['win_rate'] > 60
        passes_sharpe = m['sharpe'] > 5.0
        passes_trades = m['trades'] > 100
        passes_bear = m['regime_bd']['BEAR']['win_rate'] > 60

        score = sum([passes_dd, passes_wr, passes_sharpe, passes_trades, passes_bear])

        if score >= 4:
            successful.append((name, m, score))
            status = "✅" if score == 5 else "⚠️"
            print(f"{status} {name}: Trades={m['trades']}, Win={m['win_rate']:.1f}%, DD={m['max_dd']:.1f}%, BEAR={m['regime_bd']['BEAR']['win_rate']:.1f}% ({score}/5)")

    # =========================================================================
    # ANSWERS
    # =========================================================================
    print("\n" + "=" * 90)
    print("❓ ANSWERS TO KEY QUESTIONS")
    print("=" * 90)

    baseline = hybrid_results['BASELINE']
    best_hy = max(hybrid_results.items(), key=lambda x: (x[1]['trades'] if x[1]['max_dd'] < 20 else 0, -x[1]['max_dd']))[0]
    best_m = hybrid_results[best_hy]

    print(f"""
Q1: NEUTRAL กว้างแค่ไหนดี?
    RT-A (±2): {rt_results['RT-A_original']['regime_dist'].get('NEUTRAL', 0):.1f}% NEUTRAL, {rt_results['RT-A_original']['trades']} trades
    RT-B (±3): {rt_results['RT-B_wider']['regime_dist'].get('NEUTRAL', 0):.1f}% NEUTRAL, {rt_results['RT-B_wider']['trades']} trades
    RT-C (4/-3): {rt_results['RT-C_even_wider']['regime_dist'].get('NEUTRAL', 0):.1f}% NEUTRAL, {rt_results['RT-C_even_wider']['trades']} trades
    Best: {'RT-B or RT-C - more NEUTRAL time = more Both strategies' if rt_results['RT-B_wider']['trades'] > rt_results['RT-A_original']['trades'] else 'RT-A'}

Q2: Fallback strategy ช่วยได้เท่าไหร่?
    SS-A (Exclusive): {ss_results['SS-A_exclusive']['trades']} trades
    SS-B (Fallback): {ss_results['SS-B_fallback']['trades']} trades (+{ss_results['SS-B_fallback']['trades'] - ss_results['SS-A_exclusive']['trades']})
    SS-C (Always Both): {ss_results['SS-C_always_both']['trades']} trades (+{ss_results['SS-C_always_both']['trades'] - ss_results['SS-A_exclusive']['trades']})
    Fallback trades used: {ss_results['SS-B_fallback']['fallback']}

Q3: ทำไม BEAR win% ลดลง?
    Baseline BEAR Win%: {baseline['regime_bd']['BEAR']['win_rate']:.1f}%
    Best Hybrid BEAR Win%: {best_m['regime_bd']['BEAR']['win_rate']:.1f}%
    DD Control blocks low-quality trades in BEAR mode

Q4: Strategy-specific DD control คุ้มไหม?
    DC-A (Regime): {dc_results['DC-A_regime']['trades']} trades, {dc_results['DC-A_regime']['max_dd']:.1f}% DD
    DC-B (Strategy): {dc_results['DC-B_strategy']['trades']} trades, {dc_results['DC-B_strategy']['max_dd']:.1f}% DD
    DC-D (Separate): {dc_results['DC-D_separate']['trades']} trades, {dc_results['DC-D_separate']['max_dd']:.1f}% DD

Q5: Best combination?
    {best_hy}: {best_m['trades']} trades, {best_m['win_rate']:.1f}% win, {best_m['max_dd']:.1f}% DD
""")

    # =========================================================================
    # FINAL RECOMMENDATION
    # =========================================================================
    print("\n" + "=" * 90)
    print("✅ FINAL RECOMMENDATION")
    print("=" * 90)

    config = hybrids[best_hy]

    print(f"""
🏆 BEST CONFIGURATION: {best_hy}

Components:
- Regime Threshold: {config[0]}
- Strategy Selection: {config[1]}
- DD Control: {config[2]}

Performance:
- Trades/Year: {best_m['trades']} {'✅' if best_m['trades'] > 100 else '⚠️'}
- Win Rate: {best_m['win_rate']:.1f}% {'✅' if best_m['win_rate'] > 60 else '⚠️'}
- Sharpe: {best_m['sharpe']:.2f} {'✅' if best_m['sharpe'] > 5.0 else '⚠️'}
- Max DD: {best_m['max_dd']:.1f}% {'✅' if best_m['max_dd'] < 15 else '⚠️'}
- BEAR Win%: {best_m['regime_bd']['BEAR']['win_rate']:.1f}% {'✅' if best_m['regime_bd']['BEAR']['win_rate'] > 60 else '⚠️'}

By Regime:
- BULL: {best_m['regime_bd']['BULL']['win_rate']:.1f}% ({best_m['regime_bd']['BULL']['trades']} trades)
- BEAR: {best_m['regime_bd']['BEAR']['win_rate']:.1f}% ({best_m['regime_bd']['BEAR']['trades']} trades)
- NEUTRAL: {best_m['regime_bd']['NEUTRAL']['win_rate']:.1f}% ({best_m['regime_bd']['NEUTRAL']['trades']} trades)

By Strategy:
- SECTOR_ROTATION: {best_m['strat_bd'].get('SECTOR_ROTATION', {}).get('win_rate', 0):.1f}% ({best_m['sr']} trades)
- DIP_BOUNCE: {best_m['strat_bd'].get('DIP_BOUNCE', {}).get('win_rate', 0):.1f}% ({best_m['db']} trades)

vs Baseline:
- Trades: {best_m['trades'] - baseline['trades']:+d}
- Win Rate: {best_m['win_rate'] - baseline['win_rate']:+.1f}%
- Max DD: {best_m['max_dd'] - baseline['max_dd']:+.1f}%
""")

    print("\n" + "=" * 90)
    print("🏁 BACKTEST COMPLETE")
    print("=" * 90)

if __name__ == '__main__':
    main()
