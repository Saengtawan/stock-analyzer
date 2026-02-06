#!/usr/bin/env python3
"""
COMPREHENSIVE STRATEGY VALIDATION
==================================
ยืนยันว่า Self-Recheck (R5+R9) ดีกว่า 3 ทางเลือกก่อนหน้าจริงไหม
ด้วยการ test ทุกมุมมอง ทุก market condition
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# CONSTANTS
# =============================================================================

LOOKBACK_PERIOD = "3y"  # Use 3 years for better BEAR coverage
MAX_HOLD_DAYS = 30

# Sector ETF mapping
SECTOR_ETFS = {
    'Technology': 'XLK',
    'Healthcare': 'XLV',
    'Financial': 'XLF',
    'Consumer Cyclical': 'XLY',
    'Consumer Defensive': 'XLP',
    'Energy': 'XLE',
    'Industrials': 'XLI',
    'Basic Materials': 'XLB',
    'Utilities': 'XLU',
    'Real Estate': 'XLRE',
    'Communication Services': 'XLC'
}

# =============================================================================
# STRATEGY CONFIGURATIONS
# =============================================================================

STRATEGIES = {
    'v5.6_Baseline': {
        'name': 'v5.6 Baseline',
        'tp_mult': 5.0,
        'sl_mult': 1.5,
        'max_hold': 30,
        'trailing': None,
        'recheck': None,
        'entry_days': None,  # All days
    },
    'TIME_BASED': {
        'name': 'TIME-BASED (Mon/Tue)',
        'tp_mult': 2.5,
        'sl_mult': 1.5,
        'max_hold': 5,
        'trailing': None,
        'recheck': None,
        'entry_days': [0, 1],  # Monday, Tuesday
    },
    'HYBRID': {
        'name': 'HYBRID',
        'tp_mult': 5.0,  # Default
        'sl_mult': 1.5,
        'max_hold': 30,  # Default
        'trailing': None,
        'recheck': None,
        'entry_days': None,
        'hybrid_rules': {
            'mon_tue': {'tp_mult': 2.5, 'max_hold': 5},
            'wed_fri': {'tp_mult': 5.0, 'max_hold': 14},
        }
    },
    'Self_Recheck': {
        'name': 'Self-Recheck (R5+R9)',
        'tp_mult': 5.0,
        'sl_mult': 1.5,
        'max_hold': 30,
        'trailing': None,
        'recheck': {
            'R5_sector_weak': True,
            'R5_min_profit': 2.0,
            'R9_momentum_fade': True,
        },
        'trailing_params': {
            'sector': (2.0, 50),
            'momentum': (1.5, 60),
        },
        'entry_days': None,
    },
}

# =============================================================================
# DATA LOADING
# =============================================================================

def load_market_data() -> Tuple[pd.Series, pd.DataFrame, Dict]:
    """Load VIX, SPY, and sector ETF data"""
    print("Loading market data...")

    vix = yf.download("^VIX", period=LOOKBACK_PERIOD, progress=False)['Close']
    spy = yf.download("SPY", period=LOOKBACK_PERIOD, progress=False)

    etf_data = {}
    symbols = list(set(SECTOR_ETFS.values()))
    data = yf.download(symbols, period=LOOKBACK_PERIOD, progress=False, group_by='ticker')
    for symbol in symbols:
        try:
            if len(symbols) > 1:
                etf_data[symbol] = data[symbol]['Close']
            else:
                etf_data[symbol] = data['Close']
        except:
            pass

    return vix, spy, etf_data

def get_stock_sector(symbol: str) -> str:
    """Get sector for a stock"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return info.get('sector', 'Unknown')
    except:
        return 'Unknown'

# =============================================================================
# REGIME DETECTION
# =============================================================================

def calculate_regime(spy_data: pd.DataFrame, date: pd.Timestamp) -> str:
    """Calculate market regime for a given date"""
    try:
        hist = spy_data.loc[:date]
        if len(hist) < 50:
            return "NEUTRAL"

        close = hist['Close']
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()

        current_price = float(close.iloc[-1])
        current_sma20 = float(sma20.iloc[-1])
        current_sma50 = float(sma50.iloc[-1])

        if pd.isna(current_sma20) or pd.isna(current_sma50):
            return "NEUTRAL"

        if current_price > current_sma20 and current_sma20 > current_sma50:
            return "BULL"
        elif current_price < current_sma20 and current_sma20 < current_sma50:
            return "BEAR"
        else:
            return "SIDEWAYS"
    except Exception as e:
        return "NEUTRAL"

def analyze_test_period(spy_data: pd.DataFrame, vix_data: pd.Series) -> Dict:
    """Analyze test period for market conditions"""

    start_date = spy_data.index[50]  # Need 50 days for SMA
    end_date = spy_data.index[-1]
    total_days = len(spy_data) - 50

    # Count regime days
    regimes = {'BULL': 0, 'BEAR': 0, 'SIDEWAYS': 0, 'NEUTRAL': 0}
    regime_dates = {'BULL': [], 'BEAR': [], 'SIDEWAYS': []}

    for i in range(50, len(spy_data)):
        date = spy_data.index[i]
        regime = calculate_regime(spy_data, date)
        regimes[regime] += 1
        if regime in regime_dates:
            regime_dates[regime].append(date)

    # VIX analysis
    vix_high_25 = 0
    vix_high_30 = 0
    vix_spike_dates = []

    for i in range(1, len(vix_data)):
        date = vix_data.index[i]
        vix_val = float(vix_data.iloc[i])
        if vix_val >= 25:
            vix_high_25 += 1
        if vix_val >= 30:
            vix_high_30 += 1
            vix_spike_dates.append((date, vix_val))

    # Find regime flips
    regime_flips = []
    prev_regime = None
    for i in range(50, len(spy_data)):
        date = spy_data.index[i]
        regime = calculate_regime(spy_data, date)
        if prev_regime == "BULL" and regime == "BEAR":
            regime_flips.append(date)
        prev_regime = regime

    # Find crash periods (SPY drops > 10% in 20 days)
    crash_periods = []
    close = spy_data['Close']
    for i in range(70, len(spy_data)):
        ret_20d = float((close.iloc[i] / close.iloc[i-20] - 1) * 100)
        if ret_20d < -10:
            crash_periods.append((spy_data.index[i], ret_20d))

    return {
        'start_date': start_date,
        'end_date': end_date,
        'total_days': total_days,
        'bull_pct': regimes['BULL'] / total_days * 100,
        'bear_pct': regimes['BEAR'] / total_days * 100,
        'sideways_pct': regimes['SIDEWAYS'] / total_days * 100,
        'vix_25_pct': vix_high_25 / len(vix_data) * 100,
        'vix_30_pct': vix_high_30 / len(vix_data) * 100,
        'regime_flips': regime_flips,
        'crash_periods': crash_periods[:5],  # First 5
        'vix_spike_dates': vix_spike_dates[:10],  # First 10
        'bear_dates': regime_dates['BEAR'][:10] if regime_dates['BEAR'] else [],
    }

# =============================================================================
# INDICATOR CALCULATIONS
# =============================================================================

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR"""
    high = df['High']
    low = df['Low']
    close = df['Close']

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    return atr

def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """Calculate RSI"""
    if len(prices) < period + 1:
        return 50.0

    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()

    rs = gain / loss.replace(0, 0.0001)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

def calculate_momentum(prices: pd.Series, period: int = 3) -> float:
    """Calculate price momentum (% change over period)"""
    if len(prices) < period + 1:
        return 0.0
    return float((prices.iloc[-1] / prices.iloc[-period] - 1) * 100)

def calculate_sector_strength(sector: str, etf_data: Dict, date: pd.Timestamp) -> float:
    """Calculate sector strength (0-100)"""
    try:
        etf_symbol = SECTOR_ETFS.get(sector)
        if not etf_symbol or etf_symbol not in etf_data:
            return 50.0

        prices = etf_data[etf_symbol]
        hist = prices.loc[:date]
        if len(hist) < 20:
            return 50.0

        ret_5d = (float(hist.iloc[-1]) / float(hist.iloc[-5]) - 1) * 100 if len(hist) >= 5 else 0
        ret_20d = (float(hist.iloc[-1]) / float(hist.iloc[-20]) - 1) * 100 if len(hist) >= 20 else 0

        strength = 50 + (ret_5d * 5) + (ret_20d * 2)
        return max(0, min(100, strength))
    except:
        return 50.0

# =============================================================================
# SIGNAL COLLECTION
# =============================================================================

def collect_signals(start_date: str, end_date: str) -> List[Dict]:
    """Collect dip-bounce signals"""
    stocks = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'NFLX', 'CRM',
        'ORCL', 'ADBE', 'INTC', 'CSCO', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT', 'LRCX',
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'SCHW', 'BLK',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'TMO', 'ABT', 'LLY', 'BMY', 'AMGN',
        'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'MPC', 'VLO', 'PSX', 'OXY', 'HAL',
        'DIS', 'CMCSA', 'T', 'VZ', 'TMUS', 'CHTR', 'EA', 'TTWO', 'WBD', 'PARA',
        'HD', 'LOW', 'TGT', 'COST', 'WMT', 'TJX', 'ROST', 'DG', 'DLTR', 'BBY',
        'PG', 'KO', 'PEP', 'PM', 'MO', 'CL', 'EL', 'KMB', 'GIS', 'K',
        'CAT', 'DE', 'MMM', 'HON', 'UPS', 'FDX', 'BA', 'LMT', 'RTX', 'GE',
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'XEL', 'ES', 'EXC', 'SRE', 'ED'
    ]

    signals = []
    print("Downloading stock data...")
    all_data = yf.download(stocks, start=start_date, end=end_date, progress=False, group_by='ticker')

    for symbol in stocks:
        try:
            if len(stocks) > 1:
                df = all_data[symbol].dropna()
            else:
                df = all_data.dropna()

            if len(df) < 50:
                continue

            df['return'] = df['Close'].pct_change() * 100
            df['prev_return'] = df['return'].shift(1)
            df['ATR'] = calculate_atr(df)

            for i in range(2, len(df) - MAX_HOLD_DAYS):
                yesterday_ret = df['prev_return'].iloc[i]
                today_ret = df['return'].iloc[i]

                if yesterday_ret <= -2.0 and today_ret >= 1.0:
                    entry_date = df.index[i]
                    entry_price = float(df['Close'].iloc[i])
                    atr = float(df['ATR'].iloc[i])

                    if pd.isna(atr) or atr <= 0:
                        continue

                    signals.append({
                        'symbol': symbol,
                        'entry_date': entry_date,
                        'entry_price': entry_price,
                        'atr': atr,
                        'sector': get_stock_sector(symbol),
                        'weekday': entry_date.weekday(),
                        'future_data': df.iloc[i:i+MAX_HOLD_DAYS+1].copy()
                    })
        except Exception as e:
            continue

    return signals

# =============================================================================
# STRATEGY EXECUTION
# =============================================================================

def run_strategy(signals: List[Dict], strategy: Dict,
                 spy_data: pd.DataFrame, vix_data: pd.Series,
                 etf_data: Dict, regime_filter: str = None) -> Dict:
    """Run a single strategy on signals"""

    results = []
    exit_reasons = {}

    for signal in signals:
        entry_date = signal['entry_date']
        entry_price = signal['entry_price']
        atr = signal['atr']
        sector = signal['sector']
        weekday = signal['weekday']
        future_data = signal['future_data']

        # Check entry day filter
        entry_days = strategy.get('entry_days')
        if entry_days is not None and weekday not in entry_days:
            continue

        # Check regime filter
        if regime_filter:
            current_regime = calculate_regime(spy_data, entry_date)
            if current_regime != regime_filter:
                continue

        # Get strategy parameters
        tp_mult = strategy['tp_mult']
        sl_mult = strategy['sl_mult']
        max_hold = strategy['max_hold']

        # HYBRID adjustments
        if strategy.get('hybrid_rules'):
            if weekday in [0, 1]:  # Mon, Tue
                tp_mult = strategy['hybrid_rules']['mon_tue']['tp_mult']
                max_hold = strategy['hybrid_rules']['mon_tue']['max_hold']
            else:
                tp_mult = strategy['hybrid_rules']['wed_fri']['tp_mult']
                max_hold = strategy['hybrid_rules']['wed_fri']['max_hold']

        sl_price = entry_price - (atr * sl_mult)
        tp_price = entry_price + (atr * tp_mult)

        # Self-recheck state
        recheck_config = strategy.get('recheck')
        trailing_params = strategy.get('trailing_params', {})
        trailing_active = False
        trailing_floor = 0
        trailing_lock_pct = 0

        # Entry sector strength for comparison
        entry_sector_strength = calculate_sector_strength(sector, etf_data, entry_date)

        exit_price = None
        exit_reason = None
        exit_day = None
        peak_price = entry_price

        for day in range(1, min(len(future_data), max_hold + 1)):
            current_date = future_data.index[day]
            current_price = float(future_data['Close'].iloc[day])
            high_price = float(future_data['High'].iloc[day])
            low_price = float(future_data['Low'].iloc[day])

            current_pnl = (current_price / entry_price - 1) * 100

            if current_price > peak_price:
                peak_price = current_price

            # Stop Loss
            if low_price <= sl_price:
                exit_price = sl_price
                exit_reason = "STOP_LOSS"
                exit_day = day
                break

            # Take Profit
            if high_price >= tp_price:
                exit_price = tp_price
                exit_reason = "TAKE_PROFIT"
                exit_day = day
                break

            # Trailing Stop (if active)
            if trailing_active and low_price <= trailing_floor:
                exit_price = trailing_floor
                exit_reason = "TRAIL_STOP"
                exit_day = day
                break

            # Update trailing floor
            if trailing_active and current_price > peak_price:
                profit_from_entry = (current_price / entry_price - 1) * 100
                trailing_floor = entry_price * (1 + (profit_from_entry / 100) * (trailing_lock_pct / 100))

            # Self-Recheck Logic
            if recheck_config and not trailing_active:
                hist_data = future_data.iloc[:day+1]

                # R5: Sector weak + profit > 2%
                if recheck_config.get('R5_sector_weak'):
                    current_sector_strength = calculate_sector_strength(sector, etf_data, current_date)
                    sector_change = current_sector_strength - entry_sector_strength
                    min_profit = recheck_config.get('R5_min_profit', 2.0)

                    if sector_change < -15 and current_pnl > min_profit:
                        activation_pct, lock_pct = trailing_params.get('sector', (2.0, 50))
                        if current_pnl >= activation_pct:
                            trailing_active = True
                            trailing_lock_pct = lock_pct
                            trailing_floor = entry_price * (1 + (current_pnl / 100) * (lock_pct / 100))

                # R9: Momentum fade + profit
                if recheck_config.get('R9_momentum_fade') and not trailing_active:
                    momentum_3d = calculate_momentum(hist_data['Close'], min(3, day))
                    if momentum_3d < -2.0 and current_pnl > 0:
                        activation_pct, lock_pct = trailing_params.get('momentum', (1.5, 60))
                        if current_pnl >= activation_pct:
                            trailing_active = True
                            trailing_lock_pct = lock_pct
                            trailing_floor = entry_price * (1 + (current_pnl / 100) * (lock_pct / 100))

            # Max Hold Exit
            if day >= max_hold:
                exit_price = current_price
                exit_reason = "MAX_HOLD"
                exit_day = day
                break

        if exit_price is None:
            exit_price = float(future_data['Close'].iloc[-1])
            exit_reason = "MAX_HOLD"
            exit_day = len(future_data) - 1

        pnl = (exit_price / entry_price - 1) * 100

        results.append({
            'symbol': signal['symbol'],
            'entry_date': entry_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl': pnl,
            'exit_reason': exit_reason,
            'days_held': exit_day,
            'regime': calculate_regime(spy_data, entry_date),
        })

        exit_reasons[exit_reason] = exit_reasons.get(exit_reason, 0) + 1

    return calculate_metrics(results, exit_reasons, strategy['name'])

def calculate_metrics(results: List[Dict], exit_reasons: Dict, name: str) -> Dict:
    """Calculate performance metrics"""
    if len(results) == 0:
        return {'name': name, 'trades': 0}

    df = pd.DataFrame(results)

    wins = df[df['pnl'] > 0]
    losses = df[df['pnl'] <= 0]

    win_rate = len(wins) / len(df) * 100
    avg_win = float(wins['pnl'].mean()) if len(wins) > 0 else 0
    avg_loss = abs(float(losses['pnl'].mean())) if len(losses) > 0 else 0

    expectancy = (win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * avg_loss)

    # Worst case analysis
    worst_trade = float(df['pnl'].min())
    best_trade = float(df['pnl'].max())

    # Calculate worst week (rolling 5 trades)
    if len(df) >= 5:
        rolling_pnl = df['pnl'].rolling(5).sum()
        worst_week = float(rolling_pnl.min()) if not rolling_pnl.isna().all() else worst_trade
    else:
        worst_week = worst_trade

    # Calculate losing streak
    losing_streak = 0
    max_losing_streak = 0
    for pnl in df['pnl']:
        if pnl <= 0:
            losing_streak += 1
            max_losing_streak = max(max_losing_streak, losing_streak)
        else:
            losing_streak = 0

    # Big losses (< -5%)
    big_losses = len(df[df['pnl'] < -5])

    # Capital days
    capital_days = float(df['days_held'].sum())
    total_return = float(df['pnl'].sum())
    return_per_capital_day = total_return / capital_days if capital_days > 0 else 0

    # Annual return estimate (assuming ~250 trading days, avg hold)
    avg_hold = float(df['days_held'].mean())
    trades_per_year = 250 / avg_hold if avg_hold > 0 else 0
    annual_return = expectancy * trades_per_year

    return {
        'name': name,
        'trades': len(df),
        'expectancy': expectancy,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'avg_hold': avg_hold,
        'annual_return': annual_return,
        'worst_trade': worst_trade,
        'best_trade': best_trade,
        'worst_week': worst_week,
        'max_losing_streak': max_losing_streak,
        'big_losses': big_losses,
        'big_loss_pct': big_losses / len(df) * 100,
        'capital_days': capital_days,
        'return_per_capital_day': return_per_capital_day,
        'exit_distribution': exit_reasons,
        'results_df': df,
    }

# =============================================================================
# STRESS TESTS
# =============================================================================

def run_regime_specific_tests(signals: List[Dict], spy_data: pd.DataFrame,
                               vix_data: pd.Series, etf_data: Dict) -> Dict:
    """Run tests for each regime"""

    regime_results = {}

    for regime in ['BULL', 'BEAR', 'SIDEWAYS']:
        regime_results[regime] = {}
        for strat_key, strategy in STRATEGIES.items():
            result = run_strategy(signals, strategy, spy_data, vix_data, etf_data, regime_filter=regime)
            regime_results[regime][strat_key] = result

    return regime_results

def analyze_vix_performance(signals: List[Dict], vix_data: pd.Series,
                            spy_data: pd.DataFrame, etf_data: Dict) -> Dict:
    """Analyze performance in high VIX conditions"""

    vix_results = {'HIGH_VIX': {}, 'LOW_VIX': {}}

    for strat_key, strategy in STRATEGIES.items():
        # Filter signals by VIX level
        high_vix_signals = []
        low_vix_signals = []

        for signal in signals:
            try:
                entry_date = signal['entry_date']
                vix_slice = vix_data.loc[:entry_date]
                if len(vix_slice) > 0:
                    vix_val = float(vix_slice.iloc[-1])
                    if vix_val >= 25:
                        high_vix_signals.append(signal)
                    else:
                        low_vix_signals.append(signal)
            except:
                low_vix_signals.append(signal)

        if len(high_vix_signals) > 0:
            vix_results['HIGH_VIX'][strat_key] = run_strategy(
                high_vix_signals, strategy, spy_data, vix_data, etf_data
            )
        else:
            vix_results['HIGH_VIX'][strat_key] = {'name': strategy['name'], 'trades': 0}

        if len(low_vix_signals) > 0:
            vix_results['LOW_VIX'][strat_key] = run_strategy(
                low_vix_signals, strategy, spy_data, vix_data, etf_data
            )
        else:
            vix_results['LOW_VIX'][strat_key] = {'name': strategy['name'], 'trades': 0}

    return vix_results

def calculate_protection_value(baseline_results: Dict, recheck_results: Dict) -> Dict:
    """Calculate value of protection from recheck rules"""

    if baseline_results['trades'] == 0 or recheck_results['trades'] == 0:
        return {'r5_saves': 0, 'r9_saves': 0, 'total_protection': 0}

    baseline_df = baseline_results['results_df']
    recheck_df = recheck_results['results_df']

    # Compare trades that had different outcomes
    baseline_big_losses = len(baseline_df[baseline_df['pnl'] < -5])
    recheck_big_losses = len(recheck_df[recheck_df['pnl'] < -5])

    big_loss_reduction = baseline_big_losses - recheck_big_losses

    # Calculate average loss reduction
    baseline_avg_loss = abs(float(baseline_df[baseline_df['pnl'] < 0]['pnl'].mean())) if len(baseline_df[baseline_df['pnl'] < 0]) > 0 else 0
    recheck_avg_loss = abs(float(recheck_df[recheck_df['pnl'] < 0]['pnl'].mean())) if len(recheck_df[recheck_df['pnl'] < 0]) > 0 else 0

    loss_reduction = baseline_avg_loss - recheck_avg_loss

    # E[R] cost
    er_cost = baseline_results['expectancy'] - recheck_results['expectancy']

    # Net benefit calculation
    # Protection value = (big losses avoided * avg loss avoided)
    protection_value = big_loss_reduction * baseline_avg_loss / 100 if baseline_big_losses > 0 else 0

    return {
        'baseline_big_losses': baseline_big_losses,
        'recheck_big_losses': recheck_big_losses,
        'big_loss_reduction': big_loss_reduction,
        'baseline_avg_loss': baseline_avg_loss,
        'recheck_avg_loss': recheck_avg_loss,
        'loss_reduction': loss_reduction,
        'er_cost': er_cost,
        'protection_value': protection_value,
        'net_benefit': protection_value - er_cost,
    }

# =============================================================================
# YEAR SIMULATION
# =============================================================================

def simulate_year(results_df: pd.DataFrame, starting_capital: float = 100000) -> Dict:
    """Simulate a year of trading with position sizing"""

    if len(results_df) == 0:
        return {
            'final_capital': starting_capital,
            'max_drawdown': 0,
            'peak_capital': starting_capital,
        }

    capital = starting_capital
    peak_capital = starting_capital
    max_drawdown = 0

    # Position size: 10% of capital per trade
    position_size_pct = 0.10

    capital_history = [capital]

    for _, trade in results_df.iterrows():
        position_size = capital * position_size_pct
        trade_pnl = position_size * (trade['pnl'] / 100)
        capital += trade_pnl

        capital_history.append(capital)

        if capital > peak_capital:
            peak_capital = capital

        drawdown = (peak_capital - capital) / peak_capital * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return {
        'final_capital': capital,
        'max_drawdown': max_drawdown,
        'peak_capital': peak_capital,
        'total_return_pct': (capital / starting_capital - 1) * 100,
        'capital_history': capital_history,
    }

# =============================================================================
# DECISION MATRIX
# =============================================================================

def calculate_decision_matrix(all_results: Dict, regime_results: Dict,
                              vix_results: Dict, year_sims: Dict) -> Dict:
    """Calculate decision matrix scores"""

    weights = {
        'expectancy': 0.20,
        'annual_return': 0.20,
        'protection': 0.20,
        'avg_hold': 0.15,
        'simplicity': 0.10,
        'bear_performance': 0.10,
        'capital_efficiency': 0.05,
    }

    # Get max values for normalization
    max_er = max([r['expectancy'] for r in all_results.values() if r['trades'] > 0] or [1])
    max_annual = max([r['annual_return'] for r in all_results.values() if r['trades'] > 0] or [1])
    min_dd = min([year_sims[k]['max_drawdown'] for k in year_sims] or [1])
    max_dd = max([year_sims[k]['max_drawdown'] for k in year_sims] or [1])
    min_hold = min([r['avg_hold'] for r in all_results.values() if r['trades'] > 0] or [1])
    max_hold = max([r['avg_hold'] for r in all_results.values() if r['trades'] > 0] or [1])

    scores = {}

    for strat_key, result in all_results.items():
        if result['trades'] == 0:
            scores[strat_key] = {'total': 0}
            continue

        # E[R] score (0-10)
        er_score = (result['expectancy'] / max_er) * 10 if max_er > 0 else 5

        # Annual return score (0-10)
        annual_score = (result['annual_return'] / max_annual) * 10 if max_annual > 0 else 5

        # Protection score (lower DD = better)
        dd = year_sims[strat_key]['max_drawdown']
        protection_score = 10 - ((dd - min_dd) / (max_dd - min_dd + 0.01) * 10) if max_dd > min_dd else 10

        # Avg hold score (lower = better)
        hold = result['avg_hold']
        hold_score = 10 - ((hold - min_hold) / (max_hold - min_hold + 0.01) * 10) if max_hold > min_hold else 10

        # Simplicity score
        simplicity = {
            'v5.6_Baseline': 10,
            'TIME_BASED': 8,
            'HYBRID': 6,
            'Self_Recheck': 4,
        }
        simplicity_score = simplicity.get(strat_key, 5)

        # BEAR performance score
        bear_result = regime_results.get('BEAR', {}).get(strat_key, {})
        if bear_result.get('trades', 0) > 0:
            bear_er = bear_result.get('expectancy', 0)
            bear_score = 5 + (bear_er / 2)  # Normalize around 5
            bear_score = max(0, min(10, bear_score))
        else:
            bear_score = 5  # Neutral if no BEAR trades

        # Capital efficiency score
        cap_eff = result.get('return_per_capital_day', 0)
        max_cap_eff = max([r.get('return_per_capital_day', 0) for r in all_results.values() if r['trades'] > 0] or [1])
        cap_eff_score = (cap_eff / max_cap_eff) * 10 if max_cap_eff > 0 else 5

        # Calculate weighted total
        total = (
            er_score * weights['expectancy'] +
            annual_score * weights['annual_return'] +
            protection_score * weights['protection'] +
            hold_score * weights['avg_hold'] +
            simplicity_score * weights['simplicity'] +
            bear_score * weights['bear_performance'] +
            cap_eff_score * weights['capital_efficiency']
        ) * 10  # Scale to 100

        scores[strat_key] = {
            'expectancy': er_score,
            'annual_return': annual_score,
            'protection': protection_score,
            'avg_hold': hold_score,
            'simplicity': simplicity_score,
            'bear_performance': bear_score,
            'capital_efficiency': cap_eff_score,
            'total': total,
        }

    return scores

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 90)
    print("COMPREHENSIVE STRATEGY VALIDATION")
    print("=" * 90)
    print()

    # Load data
    vix_data, spy_data, etf_data = load_market_data()
    print(f"VIX data: {len(vix_data)} days")
    print(f"SPY data: {len(spy_data)} days")
    print()

    # =================================
    # A. TEST PERIOD ANALYSIS
    # =================================
    print("=" * 90)
    print("A. TEST PERIOD ANALYSIS")
    print("=" * 90)
    print()

    period_analysis = analyze_test_period(spy_data, vix_data)

    print(f"Start Date: {period_analysis['start_date'].strftime('%Y-%m-%d')}")
    print(f"End Date: {period_analysis['end_date'].strftime('%Y-%m-%d')}")
    print(f"Total Days: {period_analysis['total_days']}")
    print()
    print("Market Conditions:")
    print(f"  BULL days: {period_analysis['bull_pct']:.1f}%")
    print(f"  BEAR days: {period_analysis['bear_pct']:.1f}%")
    print(f"  SIDEWAYS days: {period_analysis['sideways_pct']:.1f}%")
    print(f"  VIX ≥ 25 days: {period_analysis['vix_25_pct']:.1f}%")
    print(f"  VIX ≥ 30 days: {period_analysis['vix_30_pct']:.1f}%")
    print()

    if period_analysis['regime_flips']:
        print(f"Regime Flips (BULL→BEAR): {len(period_analysis['regime_flips'])}")
        for flip in period_analysis['regime_flips'][:3]:
            print(f"  - {flip.strftime('%Y-%m-%d')}")
    else:
        print("Regime Flips (BULL→BEAR): 0")
    print()

    if period_analysis['crash_periods']:
        print(f"Crash Periods (>10% drop in 20d): {len(period_analysis['crash_periods'])}")
        for date, ret in period_analysis['crash_periods'][:3]:
            print(f"  - {date.strftime('%Y-%m-%d')}: {ret:.1f}%")
    else:
        print("Crash Periods: 0")
    print()

    # Collect signals
    start_date = (datetime.now() - timedelta(days=1095)).strftime('%Y-%m-%d')  # 3 years
    end_date = datetime.now().strftime('%Y-%m-%d')

    print("Collecting signals...")
    signals = collect_signals(start_date, end_date)
    print(f"Total signals: {len(signals)}")
    print()

    # =================================
    # B. NORMAL CONDITIONS TEST
    # =================================
    print("=" * 90)
    print("B. NORMAL CONDITIONS TEST (All 4 Strategies)")
    print("=" * 90)
    print()

    all_results = {}
    for strat_key, strategy in STRATEGIES.items():
        print(f"Testing: {strategy['name']}...")
        result = run_strategy(signals, strategy, spy_data, vix_data, etf_data)
        all_results[strat_key] = result

    print()
    print(f"{'Strategy':<25} {'Trades':>7} {'E[R]':>8} {'Win%':>7} {'Hold':>6} {'Annual':>10} {'BigL%':>7}")
    print("-" * 90)

    for strat_key, result in all_results.items():
        if result['trades'] > 0:
            print(f"{result['name']:<25} {result['trades']:>7} {result['expectancy']:>+7.3f}% {result['win_rate']:>6.1f}% {result['avg_hold']:>5.1f}d {result['annual_return']:>+9.1f}% {result['big_loss_pct']:>6.1f}%")

    print()

    # =================================
    # C. REGIME-SPECIFIC TESTS
    # =================================
    print("=" * 90)
    print("C. REGIME-SPECIFIC PERFORMANCE")
    print("=" * 90)
    print()

    regime_results = run_regime_specific_tests(signals, spy_data, vix_data, etf_data)

    for regime in ['BULL', 'BEAR', 'SIDEWAYS']:
        print(f"\n{regime} Market:")
        print(f"{'Strategy':<25} {'Trades':>7} {'E[R]':>8} {'Win%':>7} {'BigL%':>7}")
        print("-" * 60)

        for strat_key, result in regime_results[regime].items():
            if result['trades'] > 0:
                print(f"{result['name']:<25} {result['trades']:>7} {result['expectancy']:>+7.3f}% {result['win_rate']:>6.1f}% {result.get('big_loss_pct', 0):>6.1f}%")
            else:
                print(f"{result['name']:<25} {'N/A':>7}")

    print()

    # =================================
    # D. VIX PERFORMANCE
    # =================================
    print("=" * 90)
    print("D. VIX-BASED PERFORMANCE")
    print("=" * 90)
    print()

    vix_results = analyze_vix_performance(signals, vix_data, spy_data, etf_data)

    for vix_level in ['HIGH_VIX', 'LOW_VIX']:
        label = "VIX ≥ 25" if vix_level == 'HIGH_VIX' else "VIX < 25"
        print(f"\n{label}:")
        print(f"{'Strategy':<25} {'Trades':>7} {'E[R]':>8} {'Win%':>7}")
        print("-" * 50)

        for strat_key, result in vix_results[vix_level].items():
            if result['trades'] > 0:
                print(f"{result['name']:<25} {result['trades']:>7} {result['expectancy']:>+7.3f}% {result['win_rate']:>6.1f}%")
            else:
                print(f"{result['name']:<25} {'N/A':>7}")

    print()

    # =================================
    # E. WORST CASE ANALYSIS
    # =================================
    print("=" * 90)
    print("E. WORST CASE ANALYSIS")
    print("=" * 90)
    print()

    print(f"{'Metric':<20} {'v5.6':>12} {'TIME':>12} {'HYBRID':>12} {'Recheck':>12}")
    print("-" * 70)

    metrics = ['worst_trade', 'worst_week', 'max_losing_streak', 'big_losses']
    labels = ['Worst Trade', 'Worst Week', 'Losing Streak', 'Big Losses']

    for metric, label in zip(metrics, labels):
        values = []
        for strat_key in ['v5.6_Baseline', 'TIME_BASED', 'HYBRID', 'Self_Recheck']:
            val = all_results[strat_key].get(metric, 0)
            if metric in ['worst_trade', 'worst_week']:
                values.append(f"{val:+.1f}%")
            else:
                values.append(str(int(val)))
        print(f"{label:<20} {values[0]:>12} {values[1]:>12} {values[2]:>12} {values[3]:>12}")

    print()

    # =================================
    # F. CAPITAL EFFICIENCY
    # =================================
    print("=" * 90)
    print("F. CAPITAL EFFICIENCY")
    print("=" * 90)
    print()

    print(f"{'Strategy':<25} {'Trades':>7} {'AvgHold':>8} {'CapDays':>10} {'Ret/CapDay':>12}")
    print("-" * 70)

    for strat_key, result in all_results.items():
        if result['trades'] > 0:
            print(f"{result['name']:<25} {result['trades']:>7} {result['avg_hold']:>7.1f}d {result['capital_days']:>9.0f} {result['return_per_capital_day']:>+11.4f}%")

    print()

    # =================================
    # G. PROTECTION VALUE
    # =================================
    print("=" * 90)
    print("G. PROTECTION VALUE ANALYSIS")
    print("=" * 90)
    print()

    protection = calculate_protection_value(
        all_results['v5.6_Baseline'],
        all_results['Self_Recheck']
    )

    print("Self-Recheck (R5+R9) Protection Analysis:")
    print(f"  Baseline big losses (< -5%): {protection['baseline_big_losses']}")
    print(f"  Recheck big losses: {protection['recheck_big_losses']}")
    print(f"  Big losses avoided: {protection['big_loss_reduction']}")
    print()
    print(f"  Baseline avg loss: -{protection['baseline_avg_loss']:.2f}%")
    print(f"  Recheck avg loss: -{protection['recheck_avg_loss']:.2f}%")
    print(f"  Loss reduction: {protection['loss_reduction']:.2f}%")
    print()
    print(f"  E[R] cost: {protection['er_cost']:+.3f}%")
    print(f"  Protection value: {protection['protection_value']:.3f}%")
    print(f"  Net benefit: {protection['net_benefit']:+.3f}%")
    print()

    # =================================
    # H. YEAR SIMULATION
    # =================================
    print("=" * 90)
    print("H. YEAR SIMULATION ($100,000 starting capital)")
    print("=" * 90)
    print()

    year_sims = {}
    for strat_key, result in all_results.items():
        if result['trades'] > 0:
            year_sims[strat_key] = simulate_year(result['results_df'])
        else:
            year_sims[strat_key] = {
                'final_capital': 100000,
                'max_drawdown': 0,
                'total_return_pct': 0,
            }

    print(f"{'Strategy':<25} {'Final Capital':>15} {'Return':>10} {'Max DD':>10}")
    print("-" * 70)

    for strat_key in ['v5.6_Baseline', 'TIME_BASED', 'HYBRID', 'Self_Recheck']:
        sim = year_sims[strat_key]
        print(f"{all_results[strat_key]['name']:<25} ${sim['final_capital']:>13,.0f} {sim['total_return_pct']:>+9.1f}% {sim['max_drawdown']:>9.1f}%")

    print()

    # =================================
    # I. DECISION MATRIX
    # =================================
    print("=" * 90)
    print("I. DECISION MATRIX")
    print("=" * 90)
    print()

    scores = calculate_decision_matrix(all_results, regime_results, vix_results, year_sims)

    print(f"{'Criteria':<20} {'Weight':>7} {'v5.6':>8} {'TIME':>8} {'HYBRID':>8} {'Recheck':>8}")
    print("-" * 70)

    criteria = ['expectancy', 'annual_return', 'protection', 'avg_hold', 'simplicity', 'bear_performance', 'capital_efficiency']
    weights_pct = [20, 20, 20, 15, 10, 10, 5]
    labels = ['E[R]', 'Annual Return', 'Protection', 'Avg Hold', 'Simplicity', 'BEAR Perf', 'Cap Efficiency']

    for crit, weight, label in zip(criteria, weights_pct, labels):
        values = []
        for strat_key in ['v5.6_Baseline', 'TIME_BASED', 'HYBRID', 'Self_Recheck']:
            val = scores[strat_key].get(crit, 0)
            values.append(f"{val:.1f}")
        print(f"{label:<20} {weight:>6}% {values[0]:>8} {values[1]:>8} {values[2]:>8} {values[3]:>8}")

    print("-" * 70)
    totals = [scores[k]['total'] for k in ['v5.6_Baseline', 'TIME_BASED', 'HYBRID', 'Self_Recheck']]
    print(f"{'TOTAL':<20} {'100%':>7} {totals[0]:>7.1f} {totals[1]:>7.1f} {totals[2]:>7.1f} {totals[3]:>7.1f}")

    print()

    # =================================
    # J. SUCCESS CRITERIA CHECK
    # =================================
    print("=" * 90)
    print("J. SUCCESS CRITERIA CHECK")
    print("=" * 90)
    print()

    baseline = all_results['v5.6_Baseline']
    recheck = all_results['Self_Recheck']

    criteria_checks = [
        (
            "E[R] ≥ 90% of v5.6",
            recheck['expectancy'] >= baseline['expectancy'] * 0.90,
            f"{recheck['expectancy']:+.3f}% vs {baseline['expectancy'] * 0.90:+.3f}%"
        ),
        (
            "Max DD < v5.6",
            year_sims['Self_Recheck']['max_drawdown'] <= year_sims['v5.6_Baseline']['max_drawdown'],
            f"{year_sims['Self_Recheck']['max_drawdown']:.1f}% vs {year_sims['v5.6_Baseline']['max_drawdown']:.1f}%"
        ),
        (
            "Big Losses < v5.6",
            recheck['big_losses'] <= baseline['big_losses'],
            f"{recheck['big_losses']} vs {baseline['big_losses']}"
        ),
        (
            "BEAR E[R] ≥ 0",
            regime_results['BEAR']['Self_Recheck'].get('expectancy', 0) >= 0 if regime_results['BEAR']['Self_Recheck']['trades'] > 0 else True,
            f"{regime_results['BEAR']['Self_Recheck'].get('expectancy', 0):+.3f}%" if regime_results['BEAR']['Self_Recheck']['trades'] > 0 else "N/A"
        ),
        (
            "Protection Value > E[R] Cost",
            protection['net_benefit'] >= 0,
            f"{protection['net_benefit']:+.3f}%"
        ),
        (
            "Total Score > All Others",
            scores['Self_Recheck']['total'] >= max([scores[k]['total'] for k in scores if k != 'Self_Recheck']),
            f"{scores['Self_Recheck']['total']:.1f} vs max {max([scores[k]['total'] for k in scores if k != 'Self_Recheck']):.1f}"
        ),
    ]

    passed = 0
    for desc, met, value in criteria_checks:
        status = "✅" if met else "❌"
        print(f"  {status} {desc}: {value}")
        if met:
            passed += 1

    print(f"\nPassed: {passed}/{len(criteria_checks)}")
    print()

    # =================================
    # K. FINAL RECOMMENDATION
    # =================================
    print("=" * 90)
    print("K. FINAL RECOMMENDATION")
    print("=" * 90)
    print()

    # Determine winner
    winner_key = max(scores, key=lambda k: scores[k]['total'])
    winner_name = all_results[winner_key]['name']
    winner_score = scores[winner_key]['total']

    # Determine confidence
    score_gap = winner_score - sorted([scores[k]['total'] for k in scores])[-2]
    if score_gap > 10:
        confidence = 90
    elif score_gap > 5:
        confidence = 75
    else:
        confidence = 60

    # Build reasoning
    reasoning = []

    # Best E[R]
    best_er_key = max(all_results, key=lambda k: all_results[k]['expectancy'] if all_results[k]['trades'] > 0 else -999)
    reasoning.append(f"Best E[R]: {all_results[best_er_key]['name']} ({all_results[best_er_key]['expectancy']:+.3f}%)")

    # Best Annual
    best_annual_key = max(all_results, key=lambda k: all_results[k]['annual_return'] if all_results[k]['trades'] > 0 else -999)
    reasoning.append(f"Best Annual: {all_results[best_annual_key]['name']} ({all_results[best_annual_key]['annual_return']:+.1f}%)")

    # Best Protection
    best_dd_key = min(year_sims, key=lambda k: year_sims[k]['max_drawdown'])
    reasoning.append(f"Best Protection: {all_results[best_dd_key]['name']} (DD: {year_sims[best_dd_key]['max_drawdown']:.1f}%)")

    # Print final box
    has_bear = period_analysis['bear_pct'] > 5

    print("┌" + "─" * 70 + "┐")
    print("│  COMPREHENSIVE VALIDATION RESULTS" + " " * 35 + "│")
    print("├" + "─" * 70 + "┤")
    print("│" + " " * 70 + "│")

    period_str = f"{period_analysis['start_date'].strftime('%Y-%m-%d')} to {period_analysis['end_date'].strftime('%Y-%m-%d')}"
    bull_bear = "Yes" if has_bear else "No (Limited)"
    print(f"│  TEST PERIOD: {period_str} (BEAR: {bull_bear})" + " " * (70 - 16 - len(period_str) - 8 - len(bull_bear)) + "│")
    print("│" + " " * 70 + "│")

    print("│  NORMAL CONDITIONS:" + " " * 49 + "│")
    for r in reasoning:
        padding = 70 - 6 - len(r)
        print(f"│  ├── {r}" + " " * padding + "│")
    print("│" + " " * 70 + "│")

    print("│  OVERALL SCORES:" + " " * 52 + "│")
    for strat_key in ['v5.6_Baseline', 'TIME_BASED', 'HYBRID', 'Self_Recheck']:
        name = all_results[strat_key]['name']
        score = scores[strat_key]['total']
        marker = " ← WINNER" if strat_key == winner_key else ""
        line = f"├── {name}: {score:.1f}/100{marker}"
        padding = 70 - 6 - len(line) + 4
        print(f"│  {line}" + " " * padding + "│")
    print("│" + " " * 70 + "│")

    winner_line = f"WINNER: {winner_name}"
    padding = 70 - 4 - len(winner_line)
    print(f"│  {winner_line}" + " " * padding + "│")
    print("│" + " " * 70 + "│")

    # Recommendation
    if winner_key == 'v5.6_Baseline':
        rec = "KEEP v5.6 Baseline - Simplicity + Best E[R]"
    elif winner_key == 'Self_Recheck':
        rec = "IMPLEMENT Self-Recheck (R5+R9) - Better Protection"
    elif winner_key == 'TIME_BASED':
        rec = "CONSIDER TIME-BASED - Faster Exits"
    else:
        rec = "CONSIDER HYBRID - Balanced Approach"

    rec_line = f"RECOMMENDATION: {rec}"
    if len(rec_line) > 66:
        rec_line = rec_line[:63] + "..."
    padding = 70 - 4 - len(rec_line)
    print(f"│  {rec_line}" + " " * padding + "│")
    print("│" + " " * 70 + "│")

    conf_line = f"CONFIDENCE: {confidence}%"
    padding = 70 - 4 - len(conf_line)
    print(f"│  {conf_line}" + " " * padding + "│")
    print("└" + "─" * 70 + "┘")

    print()

    # =================================
    # L. QUESTIONS ANSWERED
    # =================================
    print("=" * 90)
    print("L. KEY QUESTIONS ANSWERED")
    print("=" * 90)
    print()

    # Q1: Self-Recheck ดีกว่า v5.6 ใน BEAR market ไหม?
    bear_base = regime_results['BEAR']['v5.6_Baseline']
    bear_recheck = regime_results['BEAR']['Self_Recheck']
    if bear_base['trades'] > 0 and bear_recheck['trades'] > 0:
        q1 = f"BEAR: Recheck E[R] {bear_recheck['expectancy']:+.3f}% vs v5.6 {bear_base['expectancy']:+.3f}%"
        q1_answer = "Yes" if bear_recheck['expectancy'] > bear_base['expectancy'] else "No"
    else:
        q1 = "BEAR: Insufficient data"
        q1_answer = "N/A"
    print(f"1. Self-Recheck ดีกว่า v5.6 ใน BEAR? {q1_answer}")
    print(f"   {q1}")
    print()

    # Q2: Protection value คุ้มกับ E[R] ที่เสียไป?
    print(f"2. Protection value คุ้มกับ E[R] cost?")
    if protection['net_benefit'] >= 0:
        print(f"   YES - Net benefit: {protection['net_benefit']:+.3f}%")
    else:
        print(f"   NO - Net cost: {protection['net_benefit']:+.3f}%")
    print()

    # Q3: ถ้าเกิด market crash, strategy ไหน survive ดีสุด?
    print(f"3. Market crash survival (by Max DD):")
    best_crash = min(year_sims, key=lambda k: year_sims[k]['max_drawdown'])
    print(f"   BEST: {all_results[best_crash]['name']} (DD: {year_sims[best_crash]['max_drawdown']:.1f}%)")
    print()

    # Q4: Capital efficiency
    print(f"4. Capital efficiency (Return per Capital Day):")
    best_cap = max(all_results, key=lambda k: all_results[k].get('return_per_capital_day', 0) if all_results[k]['trades'] > 0 else -999)
    print(f"   BEST: {all_results[best_cap]['name']} ({all_results[best_cap]['return_per_capital_day']:+.4f}%/day)")
    print()

    # Q5: ทางไหน robust ที่สุด
    print(f"5. Most robust across all conditions:")
    print(f"   WINNER: {winner_name} (Score: {winner_score:.1f}/100)")
    print()


if __name__ == "__main__":
    main()
