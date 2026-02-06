#!/usr/bin/env python3
"""
Sector Rotation Strategy Backtest
Compare sector rotation vs dip-bounce vs dual strategy
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
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

DEFENSIVE_SECTORS = ['Healthcare', 'Utilities', 'Consumer Staples']

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

@dataclass
class Trade:
    symbol: str
    sector: str
    strategy: str  # 'sector_rotation', 'dip_bounce', 'dual'
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl_pct: float
    hold_days: int
    exit_reason: str
    market_regime: str
    sector_1d: float = 0
    sector_5d: float = 0
    sector_20d: float = 0

@dataclass
class SectorSignal:
    sector: str
    date: str
    strategy_variant: str  # SR-A, SR-B, etc.
    sector_1d: float
    sector_5d: float
    sector_20d: float
    spy_1d: float
    spy_5d: float
    spy_20d: float
    regime: str

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

def calculate_sector_metrics(etf_data: pd.DataFrame) -> pd.DataFrame:
    """Calculate daily metrics for each sector"""
    metrics = {}

    for sector, etf in SECTOR_ETFS.items():
        try:
            close = etf_data[('Close', etf)]
            volume = etf_data[('Volume', etf)]

            df = pd.DataFrame(index=close.index)
            df['close'] = close
            df['volume'] = volume
            df['return_1d'] = close.pct_change() * 100
            df['return_5d'] = close.pct_change(5) * 100
            df['return_20d'] = close.pct_change(20) * 100
            df['return_3d'] = close.pct_change(3) * 100
            df['volume_avg_20d'] = volume.rolling(20).mean()
            df['volume_ratio'] = volume / df['volume_avg_20d']

            # ATR (simplified)
            high = etf_data[('High', etf)]
            low = etf_data[('Low', etf)]
            df['atr'] = (high - low).rolling(14).mean()
            df['atr_pct'] = df['atr'] / close * 100

            metrics[sector] = df
        except Exception as e:
            print(f"Error processing {sector}: {e}")

    # SPY metrics
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

    # VIX
    try:
        vix = etf_data[('Close', '^VIX')]
        metrics['VIX'] = pd.DataFrame({'vix': vix}, index=vix.index)
    except:
        pass

    return metrics

def get_market_regime(spy_20d: float, vix: float) -> str:
    if spy_20d > 5 and vix < 20:
        return 'BULL'
    elif spy_20d < -5 or vix > 25:
        return 'BEAR'
    else:
        return 'NEUTRAL'

# ============================================================================
# SECTOR ROTATION STRATEGIES
# ============================================================================

def sr_a_simple_rotation(sector_metrics: dict, date, sector: str) -> bool:
    """SR-A: 1d Breakout - Sector outperform SPY by 2%+"""
    try:
        sector_1d = sector_metrics[sector].loc[date, 'return_1d']
        spy_1d = sector_metrics['SPY'].loc[date, 'return_1d']

        return sector_1d > spy_1d + 2 and sector_1d > 1
    except:
        return False

def sr_b_momentum_rotation(sector_metrics: dict, date, sector: str) -> bool:
    """SR-B: 5d Momentum - Sector uptrend + today green + beat SPY"""
    try:
        s = sector_metrics[sector].loc[date]
        spy = sector_metrics['SPY'].loc[date]

        return s['return_5d'] > 3 and s['return_1d'] > 0 and s['return_5d'] > spy['return_5d']
    except:
        return False

def sr_c_reversal_rotation(sector_metrics: dict, date, sector: str) -> bool:
    """SR-C: Reversal - Sector down 5d but bouncing today"""
    try:
        s = sector_metrics[sector].loc[date]

        return s['return_5d'] < -3 and s['return_1d'] > 1.5
    except:
        return False

def sr_d_relative_strength_breakout(sector_metrics: dict, date, sector: str) -> bool:
    """SR-D: RS Breakout - Sector crosses above SPY in 20d performance"""
    try:
        s = sector_metrics[sector]
        spy = sector_metrics['SPY']

        idx = s.index.get_loc(date)
        if idx < 1:
            return False

        rs_today = s.iloc[idx]['return_20d'] - spy.iloc[idx]['return_20d']
        rs_yesterday = s.iloc[idx-1]['return_20d'] - spy.iloc[idx-1]['return_20d']
        sector_1d = s.iloc[idx]['return_1d']

        return rs_yesterday < 0 and rs_today > 0 and sector_1d > 0.5
    except:
        return False

def sr_e_money_flow(sector_metrics: dict, date, sector: str) -> bool:
    """SR-E: Money Flow - Volume spike + up + beat SPY"""
    try:
        s = sector_metrics[sector].loc[date]
        spy_1d = sector_metrics['SPY'].loc[date, 'return_1d']

        return s['volume_ratio'] > 1.5 and s['return_1d'] > 1 and s['return_1d'] > spy_1d
    except:
        return False

def sr_f_defensive_rotation(sector_metrics: dict, date, sector: str, regime: str) -> bool:
    """SR-F: Defensive Rotation - In BEAR, defensive sectors that are green"""
    try:
        if regime != 'BEAR':
            return False
        if sector not in DEFENSIVE_SECTORS:
            return False

        sector_1d = sector_metrics[sector].loc[date, 'return_1d']
        return sector_1d > 0
    except:
        return False

SR_STRATEGIES = {
    'SR-A_1d_breakout': sr_a_simple_rotation,
    'SR-B_5d_momentum': sr_b_momentum_rotation,
    'SR-C_reversal': sr_c_reversal_rotation,
    'SR-D_rs_breakout': sr_d_relative_strength_breakout,
    'SR-E_money_flow': sr_e_money_flow,
}

# ============================================================================
# STOCK SELECTION METHODS
# ============================================================================

def select_volume_leaders(stock_data: pd.DataFrame, sector: str, date, top_n: int = 3) -> List[str]:
    """Stock-A: Top stocks by volume ratio"""
    stocks = STOCK_UNIVERSE.get(sector, [])
    candidates = []

    for stock in stocks:
        try:
            vol = stock_data[('Volume', stock)]
            vol_avg = vol.rolling(20).mean()

            idx = vol.index.get_loc(date)
            if idx < 20:
                continue

            vol_ratio = vol.iloc[idx] / vol_avg.iloc[idx]
            if vol_ratio > 1.5:
                candidates.append((stock, vol_ratio))
        except:
            continue

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in candidates[:top_n]]

def select_price_leaders(stock_data: pd.DataFrame, sector: str, date, sector_1d: float, top_n: int = 3) -> List[str]:
    """Stock-B: Stocks that lead sector performance"""
    stocks = STOCK_UNIVERSE.get(sector, [])
    candidates = []

    for stock in stocks:
        try:
            close = stock_data[('Close', stock)]
            idx = close.index.get_loc(date)
            if idx < 1:
                continue

            stock_1d = (close.iloc[idx] / close.iloc[idx-1] - 1) * 100
            if stock_1d > sector_1d:
                candidates.append((stock, stock_1d))
        except:
            continue

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in candidates[:top_n]]

def select_rsi_sweet_spot(stock_data: pd.DataFrame, sector: str, date, top_n: int = 3) -> List[str]:
    """Stock-C: Stocks with RSI between 40-60"""
    stocks = STOCK_UNIVERSE.get(sector, [])
    candidates = []

    for stock in stocks:
        try:
            close = stock_data[('Close', stock)]

            # Calculate RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            idx = rsi.index.get_loc(date)
            stock_rsi = rsi.iloc[idx]

            if 40 <= stock_rsi <= 60:
                vol = stock_data[('Volume', stock)].iloc[idx]
                candidates.append((stock, vol, stock_rsi))
        except:
            continue

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in candidates[:top_n]]

def select_bounce_combo(stock_data: pd.DataFrame, sector: str, date, top_n: int = 3) -> List[str]:
    """Stock-D: Dip yesterday + bounce today"""
    stocks = STOCK_UNIVERSE.get(sector, [])
    candidates = []

    for stock in stocks:
        try:
            close = stock_data[('Close', stock)]
            idx = close.index.get_loc(date)
            if idx < 2:
                continue

            yesterday_return = (close.iloc[idx-1] / close.iloc[idx-2] - 1) * 100
            today_return = (close.iloc[idx] / close.iloc[idx-1] - 1) * 100

            if yesterday_return < -1 and today_return > 0.5:
                score = today_return - yesterday_return
                candidates.append((stock, score))
        except:
            continue

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in candidates[:top_n]]

STOCK_SELECTION = {
    'Stock-A_volume': select_volume_leaders,
    'Stock-B_price_lead': select_price_leaders,
    'Stock-C_rsi_sweet': select_rsi_sweet_spot,
    'Stock-D_bounce': select_bounce_combo,
}

# ============================================================================
# EXIT STRATEGIES
# ============================================================================

def exit_fixed_days(entry_idx: int, current_idx: int, hold_days: int, pnl_pct: float, **kwargs) -> Tuple[bool, str]:
    """Exit-A: Fixed holding period"""
    if current_idx - entry_idx >= hold_days:
        return True, f'HOLD_{hold_days}D'
    return False, ''

def exit_atr_tpsl(entry_idx: int, current_idx: int, pnl_pct: float, atr_pct: float, **kwargs) -> Tuple[bool, str]:
    """Exit-B: ATR-based TP/SL"""
    tp = atr_pct * 2.5
    sl = -atr_pct * 1.5

    if pnl_pct >= tp:
        return True, 'TP'
    if pnl_pct <= sl:
        return True, 'SL'
    return False, ''

def exit_sector_weakness(entry_idx: int, current_idx: int, sector_1d: float, **kwargs) -> Tuple[bool, str]:
    """Exit-C: Exit when sector turns weak"""
    if sector_1d < -1.5:
        return True, 'SECTOR_WEAK'
    return False, ''

def exit_trailing_sector(entry_idx: int, current_idx: int, sector_1d: float, sector_3d_avg: float, **kwargs) -> Tuple[bool, str]:
    """Exit-D: Exit when sector momentum fades"""
    if sector_1d < sector_3d_avg - 1:
        return True, 'MOMENTUM_FADE'
    return False, ''

# ============================================================================
# DIP-BOUNCE BASELINE
# ============================================================================

def find_dip_bounce_signals(stock_data: pd.DataFrame, stock: str) -> List[Tuple[str, float]]:
    """Find dip-bounce signals"""
    signals = []

    try:
        closes = stock_data[('Close', stock)].dropna()

        for i in range(2, len(closes)):
            date = closes.index[i]
            today_close = closes.iloc[i]
            yesterday_close = closes.iloc[i-1]
            day_before_close = closes.iloc[i-2]

            yesterday_return = (yesterday_close / day_before_close - 1) * 100
            today_return = (today_close / yesterday_close - 1) * 100

            if yesterday_return <= -2 and today_return >= 1:
                signals.append((date.strftime('%Y-%m-%d'), today_close))
    except:
        pass

    return signals

# ============================================================================
# TRADE SIMULATION
# ============================================================================

def simulate_trade(stock_data: pd.DataFrame, stock: str, entry_date: str, entry_price: float,
                   exit_strategy: str, hold_days: int, sector_metrics: dict, sector: str) -> Optional[Trade]:
    """Simulate a single trade"""
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

        max_hold = min(hold_days + 5, 15)  # Safety limit

        for day in range(1, max_hold + 1):
            if entry_idx + day >= len(closes):
                break

            current_price = closes.iloc[entry_idx + day]
            pnl_pct = (current_price / entry_price - 1) * 100
            current_date = dates[entry_idx + day]

            # Get sector metrics for exit decision
            try:
                s_metrics = sector_metrics[sector].loc[current_date]
                sector_1d = s_metrics['return_1d']
                sector_3d = s_metrics.get('return_3d', 0)
                atr_pct = s_metrics.get('atr_pct', 2)
            except:
                sector_1d = 0
                sector_3d = 0
                atr_pct = 2

            should_exit = False
            exit_reason = ''

            # Check exit conditions
            if exit_strategy == 'fixed':
                if day >= hold_days:
                    should_exit = True
                    exit_reason = f'HOLD_{hold_days}D'
            elif exit_strategy == 'atr':
                tp = atr_pct * 2.5
                sl = -atr_pct * 1.5
                if pnl_pct >= tp:
                    should_exit, exit_reason = True, 'TP'
                elif pnl_pct <= sl:
                    should_exit, exit_reason = True, 'SL'
                elif day >= hold_days:
                    should_exit, exit_reason = True, f'HOLD_{hold_days}D'
            elif exit_strategy == 'sector':
                if sector_1d < -1.5:
                    should_exit, exit_reason = True, 'SECTOR_WEAK'
                elif day >= hold_days:
                    should_exit, exit_reason = True, f'HOLD_{hold_days}D'
            else:  # default: fixed with TP/SL
                if pnl_pct >= 3:
                    should_exit, exit_reason = True, 'TP'
                elif pnl_pct <= -2:
                    should_exit, exit_reason = True, 'SL'
                elif day >= hold_days:
                    should_exit, exit_reason = True, f'HOLD_{hold_days}D'

            if should_exit:
                return Trade(
                    symbol=stock,
                    sector=sector,
                    strategy='',
                    entry_date=entry_date,
                    entry_price=entry_price,
                    exit_date=current_date.strftime('%Y-%m-%d'),
                    exit_price=current_price,
                    pnl_pct=pnl_pct,
                    hold_days=day,
                    exit_reason=exit_reason,
                    market_regime='',
                    sector_1d=sector_1d
                )

        return None
    except Exception as e:
        return None

# ============================================================================
# MAIN BACKTEST
# ============================================================================

def run_sector_rotation_backtest(sector_metrics: dict, stock_data: pd.DataFrame,
                                  strategy_name: str, strategy_func,
                                  stock_selection: str, exit_strategy: str,
                                  hold_days: int) -> List[Trade]:
    """Run backtest for a sector rotation strategy variant"""
    trades = []

    # Get common dates
    spy_dates = sector_metrics['SPY'].index[25:]  # Skip first 25 days for calculations

    for date in spy_dates:
        try:
            # Get regime
            spy_20d = sector_metrics['SPY'].loc[date, 'return_20d']
            vix = sector_metrics.get('VIX', pd.DataFrame()).get('vix', pd.Series()).get(date, 20)
            if pd.isna(vix):
                vix = 20
            regime = get_market_regime(spy_20d, vix)

            # Check each sector for signals
            for sector in SECTOR_ETFS.keys():
                # Special handling for SR-F (defensive rotation)
                if strategy_name == 'SR-F_defensive':
                    if not sr_f_defensive_rotation(sector_metrics, date, sector, regime):
                        continue
                else:
                    if not strategy_func(sector_metrics, date, sector):
                        continue

                # Sector signal triggered - select stocks
                sector_1d = sector_metrics[sector].loc[date, 'return_1d']

                if stock_selection == 'Stock-A_volume':
                    stocks = select_volume_leaders(stock_data, sector, date)
                elif stock_selection == 'Stock-B_price_lead':
                    stocks = select_price_leaders(stock_data, sector, date, sector_1d)
                elif stock_selection == 'Stock-C_rsi_sweet':
                    stocks = select_rsi_sweet_spot(stock_data, sector, date)
                elif stock_selection == 'Stock-D_bounce':
                    stocks = select_bounce_combo(stock_data, sector, date)
                else:
                    stocks = select_volume_leaders(stock_data, sector, date)

                # Simulate trades for selected stocks
                for stock in stocks[:2]:  # Max 2 stocks per signal
                    try:
                        entry_price = stock_data[('Close', stock)].loc[date]
                        entry_date = date.strftime('%Y-%m-%d')

                        trade = simulate_trade(
                            stock_data, stock, entry_date, entry_price,
                            exit_strategy, hold_days, sector_metrics, sector
                        )

                        if trade:
                            trade.strategy = strategy_name
                            trade.market_regime = regime
                            trade.sector_1d = sector_1d
                            trade.sector_5d = sector_metrics[sector].loc[date, 'return_5d']
                            trade.sector_20d = sector_metrics[sector].loc[date, 'return_20d']
                            trades.append(trade)
                    except:
                        continue
        except Exception as e:
            continue

    return trades

def run_dip_bounce_backtest(stock_data: pd.DataFrame, sector_metrics: dict,
                            hold_days: int = 3) -> List[Trade]:
    """Run dip-bounce baseline backtest"""
    trades = []

    for stock, sector in STOCK_TO_SECTOR.items():
        signals = find_dip_bounce_signals(stock_data, stock)

        for entry_date, entry_price in signals:
            try:
                date = pd.Timestamp(entry_date)

                # Get regime
                spy_20d = sector_metrics['SPY'].loc[date, 'return_20d']
                vix = sector_metrics.get('VIX', pd.DataFrame()).get('vix', pd.Series()).get(date, 20)
                if pd.isna(vix):
                    vix = 20
                regime = get_market_regime(spy_20d, vix)

                trade = simulate_trade(
                    stock_data, stock, entry_date, entry_price,
                    'default', hold_days, sector_metrics, sector
                )

                if trade:
                    trade.strategy = 'DIP_BOUNCE'
                    trade.market_regime = regime
                    try:
                        trade.sector_1d = sector_metrics[sector].loc[date, 'return_1d']
                        trade.sector_5d = sector_metrics[sector].loc[date, 'return_5d']
                        trade.sector_20d = sector_metrics[sector].loc[date, 'return_20d']
                    except:
                        pass
                    trades.append(trade)
            except:
                continue

    return trades

def calculate_metrics(trades: List[Trade]) -> dict:
    """Calculate performance metrics"""
    if not trades:
        return {
            'win_rate': 0, 'avg_pnl': 0, 'total_pnl': 0,
            'sharpe': 0, 'max_dd': 0, 'avg_hold': 0,
            'trades': 0, 'profit_factor': 0
        }

    pnls = [t.pnl_pct for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / len(pnls) * 100
    avg_pnl = np.mean(pnls)
    total_pnl = sum(pnls)

    # Sharpe
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 else 0

    # Max drawdown
    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0

    # Avg hold days
    avg_hold = np.mean([t.hold_days for t in trades])

    # Profit factor
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    return {
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'total_pnl': total_pnl,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'avg_hold': avg_hold,
        'trades': len(trades),
        'profit_factor': profit_factor
    }

def calculate_metrics_by_regime(trades: List[Trade]) -> dict:
    """Calculate metrics by market regime"""
    results = {}
    for regime in ['BULL', 'BEAR', 'NEUTRAL']:
        regime_trades = [t for t in trades if t.market_regime == regime]
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
    print("🔄 SECTOR ROTATION STRATEGY BACKTEST")
    print("=" * 90)

    # Download data
    etf_data, stock_data = download_data('1y')

    # Calculate metrics
    print("\n📊 Calculating sector metrics...")
    sector_metrics = calculate_sector_metrics(etf_data)

    # =========================================================================
    # Part 1: Sector Rotation Strategy Variants
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 1: SECTOR ROTATION STRATEGY VARIANTS")
    print("=" * 90)

    sr_results = {}

    for sr_name, sr_func in SR_STRATEGIES.items():
        print(f"\n  Testing {sr_name}...")
        trades = run_sector_rotation_backtest(
            sector_metrics, stock_data,
            sr_name, sr_func,
            'Stock-A_volume', 'default', 5
        )
        sr_results[sr_name] = {
            'trades': trades,
            'metrics': calculate_metrics(trades),
            'by_regime': calculate_metrics_by_regime(trades)
        }

    # Add SR-F (defensive) - special case
    print(f"\n  Testing SR-F_defensive...")
    sr_f_trades = run_sector_rotation_backtest(
        sector_metrics, stock_data,
        'SR-F_defensive', None,
        'Stock-A_volume', 'default', 5
    )
    sr_results['SR-F_defensive'] = {
        'trades': sr_f_trades,
        'metrics': calculate_metrics(sr_f_trades),
        'by_regime': calculate_metrics_by_regime(sr_f_trades)
    }

    # Print results
    print(f"\n{'Strategy':<25} {'Win%':>8} {'AvgP&L':>8} {'Sharpe':>8} {'MaxDD':>8} {'AvgHold':>8} {'Trades':>8} {'PF':>8}")
    print("-" * 95)

    sorted_sr = sorted(sr_results.items(), key=lambda x: x[1]['metrics']['win_rate'], reverse=True)
    for name, data in sorted_sr:
        m = data['metrics']
        print(f"{name:<25} {m['win_rate']:>7.1f}% {m['avg_pnl']:>+7.2f}% {m['sharpe']:>8.2f} {m['max_dd']:>7.1f}% {m['avg_hold']:>7.1f}d {m['trades']:>8} {m['profit_factor']:>7.2f}")

    # =========================================================================
    # Part 2: Stock Selection Methods (using best SR strategy)
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 2: STOCK SELECTION METHODS")
    print("=" * 90)

    best_sr = sorted_sr[0][0] if sorted_sr else 'SR-A_1d_breakout'
    best_sr_func = SR_STRATEGIES.get(best_sr, sr_a_simple_rotation)

    stock_results = {}
    for sel_name in STOCK_SELECTION.keys():
        print(f"\n  Testing {sel_name} with {best_sr}...")
        trades = run_sector_rotation_backtest(
            sector_metrics, stock_data,
            best_sr, best_sr_func,
            sel_name, 'default', 5
        )
        stock_results[sel_name] = calculate_metrics(trades)

    print(f"\n{'Selection':<25} {'Win%':>8} {'AvgP&L':>8} {'Trades':>8}")
    print("-" * 55)
    for name, m in sorted(stock_results.items(), key=lambda x: x[1]['win_rate'], reverse=True):
        print(f"{name:<25} {m['win_rate']:>7.1f}% {m['avg_pnl']:>+7.2f}% {m['trades']:>8}")

    # =========================================================================
    # Part 3: Exit Strategy Comparison
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 3: EXIT STRATEGY COMPARISON")
    print("=" * 90)

    exit_results = {}
    for exit_type, hold in [('fixed', 3), ('fixed', 5), ('fixed', 7), ('atr', 5), ('sector', 5)]:
        label = f"Exit_{exit_type}_{hold}d"
        print(f"\n  Testing {label}...")
        trades = run_sector_rotation_backtest(
            sector_metrics, stock_data,
            best_sr, best_sr_func,
            'Stock-A_volume', exit_type, hold
        )
        exit_results[label] = calculate_metrics(trades)

    print(f"\n{'Exit Strategy':<25} {'Win%':>8} {'AvgP&L':>8} {'AvgHold':>8} {'Trades':>8}")
    print("-" * 65)
    for name, m in sorted(exit_results.items(), key=lambda x: x[1]['win_rate'], reverse=True):
        print(f"{name:<25} {m['win_rate']:>7.1f}% {m['avg_pnl']:>+7.2f}% {m['avg_hold']:>7.1f}d {m['trades']:>8}")

    # =========================================================================
    # Part 4: Dip-Bounce vs Sector Rotation
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 4: DIP-BOUNCE vs SECTOR ROTATION")
    print("=" * 90)

    print("\n  Running Dip-Bounce baseline...")
    db_trades = run_dip_bounce_backtest(stock_data, sector_metrics, 3)
    db_metrics = calculate_metrics(db_trades)
    db_regime = calculate_metrics_by_regime(db_trades)

    # Best SR results
    best_sr_data = sr_results[sorted_sr[0][0]]

    print(f"\n{'Strategy':<25} {'Win%':>8} {'AvgP&L':>8} {'Sharpe':>8} {'Trades':>8} {'PF':>8}")
    print("-" * 75)
    print(f"{'DIP_BOUNCE':<25} {db_metrics['win_rate']:>7.1f}% {db_metrics['avg_pnl']:>+7.2f}% {db_metrics['sharpe']:>8.2f} {db_metrics['trades']:>8} {db_metrics['profit_factor']:>7.2f}")
    print(f"{sorted_sr[0][0]:<25} {best_sr_data['metrics']['win_rate']:>7.1f}% {best_sr_data['metrics']['avg_pnl']:>+7.2f}% {best_sr_data['metrics']['sharpe']:>8.2f} {best_sr_data['metrics']['trades']:>8} {best_sr_data['metrics']['profit_factor']:>7.2f}")

    # =========================================================================
    # Part 5: By Market Regime
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PART 5: BY MARKET REGIME")
    print("=" * 90)

    print(f"\n{'Strategy':<25} {'BULL Win%':>12} {'BEAR Win%':>12} {'NEUTRAL Win%':>14}")
    print("-" * 70)
    print(f"{'DIP_BOUNCE':<25} {db_regime.get('BULL', 0):>11.1f}% {db_regime.get('BEAR', 0):>11.1f}% {db_regime.get('NEUTRAL', 0):>13.1f}%")

    for name, data in sorted_sr[:3]:
        r = data['by_regime']
        print(f"{name:<25} {r.get('BULL', 0):>11.1f}% {r.get('BEAR', 0):>11.1f}% {r.get('NEUTRAL', 0):>13.1f}%")

    # =========================================================================
    # ANSWERS
    # =========================================================================
    print("\n" + "=" * 90)
    print("❓ ANSWERS TO KEY QUESTIONS")
    print("=" * 90)

    best_sr_metrics = best_sr_data['metrics']

    viable = best_sr_metrics['win_rate'] > 55 and best_sr_metrics['sharpe'] > 1.0
    better_than_db = best_sr_metrics['win_rate'] > db_metrics['win_rate']

    print(f"""
Q1: Sector Rotation เป็น strategy ที่ viable ไหม?
    Best SR Win Rate: {best_sr_metrics['win_rate']:.1f}% (need >55%)
    Best SR Sharpe: {best_sr_metrics['sharpe']:.2f} (need >1.0)
    Answer: {'✅ YES - Viable' if viable else '❌ NO - Not viable'}

Q2: ดีกว่า Dip-Bounce ไหม?
    SR Win Rate: {best_sr_metrics['win_rate']:.1f}%
    DB Win Rate: {db_metrics['win_rate']:.1f}%
    Difference: {best_sr_metrics['win_rate'] - db_metrics['win_rate']:+.1f}%
    Answer: {'✅ YES' if better_than_db else '❌ NO'}

Q3: Best combination?
    Entry: {sorted_sr[0][0]}
    Stock Selection: {max(stock_results.items(), key=lambda x: x[1]['win_rate'])[0]}
    Exit: {max(exit_results.items(), key=lambda x: x[1]['win_rate'])[0]}

Q4: When to use what?
    BULL: {'Dip-Bounce' if db_regime.get('BULL', 0) > best_sr_data['by_regime'].get('BULL', 0) else sorted_sr[0][0]} ({max(db_regime.get('BULL', 0), best_sr_data['by_regime'].get('BULL', 0)):.1f}%)
    BEAR: {'Dip-Bounce' if db_regime.get('BEAR', 0) > best_sr_data['by_regime'].get('BEAR', 0) else sorted_sr[0][0]} ({max(db_regime.get('BEAR', 0), best_sr_data['by_regime'].get('BEAR', 0)):.1f}%)
    NEUTRAL: {'Dip-Bounce' if db_regime.get('NEUTRAL', 0) > best_sr_data['by_regime'].get('NEUTRAL', 0) else sorted_sr[0][0]} ({max(db_regime.get('NEUTRAL', 0), best_sr_data['by_regime'].get('NEUTRAL', 0)):.1f}%)

Q5: Resource allocation ($100K, max 2 positions)?
""")

    if viable and better_than_db:
        print("""    Recommendation: DUAL STRATEGY
    - 60% capital for Sector Rotation (better win rate)
    - 40% capital for Dip-Bounce (more frequent signals)
    - Priority: SR signal > DB signal when both trigger""")
    elif viable:
        print("""    Recommendation: SITUATION-BASED
    - Use Dip-Bounce as primary (higher frequency)
    - Use Sector Rotation in specific regimes where it performs better""")
    else:
        print("""    Recommendation: DIP-BOUNCE FOCUS
    - Sector Rotation ไม่ viable พอสำหรับ standalone strategy
    - Focus 100% on Dip-Bounce
    - ใช้ sector เป็น scoring bonus เท่านั้น (ไม่ใช่ separate strategy)""")

    # =========================================================================
    # FINAL RECOMMENDATION
    # =========================================================================
    print("\n" + "=" * 90)
    print("✅ FINAL RECOMMENDATION")
    print("=" * 90)

    if not viable:
        print("""
❌ SECTOR ROTATION ไม่ VIABLE เป็น STANDALONE STRATEGY

เหตุผล:
- Win Rate ไม่ถึง 55% threshold
- Sharpe ไม่ถึง 1.0 threshold
- ไม่ดีกว่า Dip-Bounce อย่างมีนัยสำคัญ

แนะนำ:
1. Focus Dip-Bounce เป็น primary strategy
2. ใช้ Sector เป็น scoring bonus (+3 to +5 points) ไม่ใช่ filter
3. ไม่ต้อง implement Sector Rotation แยก

Code สำหรับ scoring bonus:
```python
def get_sector_bonus(sector_5d: float) -> int:
    if sector_5d > 3:
        return 5
    elif sector_5d > 0:
        return 3
    elif sector_5d > -3:
        return 0
    else:
        return -3
```
""")
    else:
        print(f"""
✅ SECTOR ROTATION VIABLE

Best Configuration:
- Strategy: {sorted_sr[0][0]}
- Stock Selection: Volume Leaders
- Exit: Fixed 5 days with TP/SL
- Expected Win Rate: {best_sr_metrics['win_rate']:.1f}%

Dual Strategy Implementation:
```python
def get_trading_signal():
    sr_signal = check_sector_rotation()
    db_signal = check_dip_bounce()

    if sr_signal and sr_signal.confidence > 0.7:
        return sr_signal  # Priority to high-confidence SR
    elif db_signal:
        return db_signal
    elif sr_signal:
        return sr_signal
    return None
```
""")

    print("\n" + "=" * 90)
    print("🏁 BACKTEST COMPLETE")
    print("=" * 90)

if __name__ == '__main__':
    main()
