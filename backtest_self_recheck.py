#!/usr/bin/env python3
"""
QUANT RESEARCH — Self-Recheck Exit System
==========================================
ใช้ 30 Layers ที่มีอยู่แล้ว recheck position ทุกวัน
แทนที่จะถือ 30 วันโดยไม่ดูอะไรเลย
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

SL_MULTIPLIER = 1.5
TP_MULTIPLIER = 5.0
MAX_HOLD_DAYS = 30
LOOKBACK_PERIOD = "2y"

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
# DATA LOADING
# =============================================================================

def load_vix_data() -> pd.DataFrame:
    """Load VIX data"""
    vix = yf.download("^VIX", period=LOOKBACK_PERIOD, progress=False)
    return vix['Close']

def load_spy_data() -> pd.DataFrame:
    """Load SPY data for regime detection"""
    spy = yf.download("SPY", period=LOOKBACK_PERIOD, progress=False)
    return spy

def load_sector_etf_data() -> Dict[str, pd.DataFrame]:
    """Load all sector ETF data"""
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
    return etf_data

def get_stock_sector(symbol: str) -> str:
    """Get sector for a stock"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return info.get('sector', 'Unknown')
    except:
        return 'Unknown'

# =============================================================================
# REGIME & INDICATOR CALCULATIONS
# =============================================================================

def calculate_regime(spy_data: pd.DataFrame, date: pd.Timestamp) -> str:
    """Calculate market regime for a given date"""
    try:
        # Get data up to date
        hist = spy_data.loc[:date]
        if len(hist) < 50:
            return "NEUTRAL"

        close = hist['Close']
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()

        current_price = close.iloc[-1]
        current_sma20 = sma20.iloc[-1]
        current_sma50 = sma50.iloc[-1]

        if current_price > current_sma20 > current_sma50:
            return "BULL"
        elif current_price < current_sma20 < current_sma50:
            return "BEAR"
        else:
            return "SIDEWAYS"
    except:
        return "NEUTRAL"

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

        # Calculate momentum score
        ret_5d = (hist.iloc[-1] / hist.iloc[-5] - 1) * 100 if len(hist) >= 5 else 0
        ret_20d = (hist.iloc[-1] / hist.iloc[-20] - 1) * 100 if len(hist) >= 20 else 0

        # Normalize to 0-100
        strength = 50 + (ret_5d * 5) + (ret_20d * 2)
        return max(0, min(100, strength))
    except:
        return 50.0

def get_sector_regime(sector: str, etf_data: Dict, date: pd.Timestamp) -> str:
    """Get sector regime"""
    strength = calculate_sector_strength(sector, etf_data, date)
    if strength >= 60:
        return "STRONG"
    elif strength <= 40:
        return "WEAK"
    else:
        return "NEUTRAL"

def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """Calculate RSI"""
    if len(prices) < period + 1:
        return 50.0

    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()

    rs = gain / loss.replace(0, 0.0001)
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0

def calculate_momentum(prices: pd.Series, period: int = 5) -> float:
    """Calculate price momentum (% change over period)"""
    if len(prices) < period + 1:
        return 0.0
    return (prices.iloc[-1] / prices.iloc[-period] - 1) * 100

def calculate_score(stock_data: pd.DataFrame, date: pd.Timestamp,
                   spy_data: pd.DataFrame, vix_data: pd.Series,
                   sector: str, etf_data: Dict) -> float:
    """
    Calculate comprehensive score (simplified version of 30 Layers)
    Components:
    - RSI (oversold = good for bounce)
    - Momentum
    - Volume
    - Sector strength
    - VIX level
    """
    try:
        hist = stock_data.loc[:date]
        if len(hist) < 20:
            return 50.0

        close = hist['Close']
        volume = hist['Volume']

        # 1. RSI Score (oversold = higher score)
        rsi = calculate_rsi(close)
        if rsi <= 30:
            rsi_score = 100
        elif rsi <= 40:
            rsi_score = 80
        elif rsi >= 70:
            rsi_score = 30
        else:
            rsi_score = 60

        # 2. Momentum Score (recent bounce = higher score)
        mom_1d = calculate_momentum(close, 1)
        mom_5d = calculate_momentum(close, 5)

        if mom_1d > 1.5:  # Strong bounce today
            mom_score = 90
        elif mom_1d > 0.5:
            mom_score = 75
        elif mom_1d < -2:
            mom_score = 40
        else:
            mom_score = 60

        # 3. Volume Score
        avg_vol = volume.rolling(20).mean().iloc[-1]
        current_vol = volume.iloc[-1]
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0

        if vol_ratio > 1.5:
            vol_score = 80
        elif vol_ratio > 1.0:
            vol_score = 65
        else:
            vol_score = 50

        # 4. Sector Score
        sector_strength = calculate_sector_strength(sector, etf_data, date)
        sector_score = sector_strength

        # 5. VIX Score (higher VIX during entry = opportunity)
        try:
            current_vix = vix_data.loc[:date].iloc[-1]
            if current_vix >= 25:
                vix_score = 80  # High fear = opportunity
            elif current_vix >= 20:
                vix_score = 70
            elif current_vix <= 15:
                vix_score = 50  # Low VIX = complacency
            else:
                vix_score = 60
        except:
            vix_score = 60

        # Weighted average
        total_score = (
            rsi_score * 0.25 +
            mom_score * 0.25 +
            vol_score * 0.15 +
            sector_score * 0.20 +
            vix_score * 0.15
        )

        return total_score
    except:
        return 50.0

def is_signal_still_valid(stock_data: pd.DataFrame, date: pd.Timestamp) -> bool:
    """
    Check if the original entry signal is still valid
    (Stock-D filter: price < SMA20, RSI < 40, etc.)
    """
    try:
        hist = stock_data.loc[:date]
        if len(hist) < 20:
            return True

        close = hist['Close']
        sma20 = close.rolling(20).mean()
        rsi = calculate_rsi(close)

        # Original signal was dip-bounce
        # If stock is now in strong uptrend (RSI > 60, price > SMA20)
        # then the original dip signal has played out

        current_price = close.iloc[-1]
        current_sma20 = sma20.iloc[-1]

        # Signal is "no longer valid" if stock has fully recovered
        if current_price > current_sma20 * 1.05 and rsi > 60:
            return False  # Recovery complete

        return True  # Still in dip/recovery phase
    except:
        return True

# =============================================================================
# SELF-RECHECK EXIT SYSTEM
# =============================================================================

class SelfRecheckSystem:
    """Self-recheck exit system using 30 Layers logic"""

    def __init__(self, config: Dict):
        self.config = config
        self.name = config.get('name', 'SelfRecheck')

    def recheck_position(self, position: Dict, current_conditions: Dict) -> Tuple[str, str]:
        """
        Daily recheck of position
        Returns: (action, reason)
        Action: SELL, TRAILING, HOLD
        """
        profit_pct = position['current_pnl']
        entry_score = position['entry_score']
        entry_regime = position['entry_regime']
        entry_sector_strength = position['entry_sector_strength']
        entry_vix = position['entry_vix']
        days_held = position['days_held']

        current_score = current_conditions['score']
        current_regime = current_conditions['regime']
        current_sector_strength = current_conditions['sector_strength']
        current_vix = current_conditions['vix']
        current_rsi = current_conditions['rsi']
        momentum_3d = current_conditions['momentum_3d']
        signal_valid = current_conditions['signal_valid']

        # Calculate changes
        score_change = current_score - entry_score
        vix_change = current_vix - entry_vix
        sector_change = current_sector_strength - entry_sector_strength

        rules = self.config.get('rules', {})

        # =========================================
        # RULE PRIORITY (from most urgent to least)
        # =========================================

        # R1: Score dropped significantly + has profit → SELL
        if rules.get('R1_score_low', False):
            threshold = rules.get('R1_threshold', 70)
            if current_score < threshold and profit_pct > 0:
                return "SELL", f"R1_score_low_{current_score:.0f}"

        # R2: Score dropped > X points → TRAILING
        if rules.get('R2_score_drop', False):
            drop_threshold = rules.get('R2_drop_threshold', 20)
            if score_change < -drop_threshold:
                return "TRAILING", f"R2_score_drop_{score_change:.0f}"

        # R3: Regime BULL→BEAR → TRAILING
        if rules.get('R3_regime_flip', False):
            if entry_regime == "BULL" and current_regime == "BEAR":
                return "TRAILING", "R3_regime_bear"

        # R4: Regime BULL→BEAR + profit → SELL
        if rules.get('R4_regime_flip_sell', False):
            if entry_regime == "BULL" and current_regime == "BEAR" and profit_pct > 0:
                return "SELL", "R4_regime_flip_profit"

        # R5: Sector weakened + profit > X% → TRAILING
        if rules.get('R5_sector_weak', False):
            min_profit = rules.get('R5_min_profit', 2.0)
            if sector_change < -15 and profit_pct > min_profit:
                return "TRAILING", f"R5_sector_weak_{sector_change:.0f}"

        # R6: VIX spike + profit → TRAILING
        if rules.get('R6_vix_spike', False):
            vix_threshold = rules.get('R6_vix_threshold', 5)
            if vix_change > vix_threshold and profit_pct > 0:
                return "TRAILING", f"R6_vix_spike_{vix_change:.1f}"

        # R7: Signal no longer valid + profit → SELL
        if rules.get('R7_signal_invalid', False):
            if not signal_valid and profit_pct > 0:
                return "SELL", "R7_signal_invalid"

        # R8: RSI overbought + profit > X% → SELL
        if rules.get('R8_rsi_high', False):
            rsi_threshold = rules.get('R8_rsi_threshold', 70)
            min_profit = rules.get('R8_min_profit', 2.0)
            if current_rsi > rsi_threshold and profit_pct > min_profit:
                return "SELL", f"R8_rsi_{current_rsi:.0f}"

        # R9: Momentum negative X days + profit → TRAILING
        if rules.get('R9_momentum_fade', False):
            if momentum_3d < -2.0 and profit_pct > 0:
                return "TRAILING", f"R9_momentum_{momentum_3d:.1f}"

        # R10: Score improving → HOLD longer
        if rules.get('R10_score_improving', False):
            if score_change > 10:
                return "HOLD", "R10_score_improving"

        # Default: HOLD
        return "HOLD", "conditions_stable"


# =============================================================================
# TRAILING STOP HANDLER
# =============================================================================

class TrailingStopHandler:
    """Handle trailing stop after activation"""

    def __init__(self, config: Dict):
        self.config = config

    def get_trailing_params(self, trigger_reason: str) -> Tuple[float, float]:
        """
        Get trailing parameters based on trigger reason
        Returns: (activation_pct, lock_pct)
        """
        params = self.config.get('trailing_params', {})

        if 'regime' in trigger_reason:
            return params.get('regime', (2.0, 60))
        elif 'sector' in trigger_reason:
            return params.get('sector', (2.0, 50))
        elif 'vix' in trigger_reason:
            return params.get('vix', (1.5, 70))
        elif 'score' in trigger_reason:
            return params.get('score', (2.0, 50))
        elif 'momentum' in trigger_reason:
            return params.get('momentum', (1.5, 60))
        else:
            return (2.0, 50)  # Default


# =============================================================================
# BACKTESTER
# =============================================================================

def collect_signals(start_date: str, end_date: str) -> List[Dict]:
    """Collect dip-bounce signals"""
    # Use same stocks as main system
    stocks = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'NFLX', 'CRM',
        'ORCL', 'ADBE', 'INTC', 'CSCO', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT', 'LRCX',
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'SCHW', 'BLK',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'TMO', 'ABT', 'LLY', 'BMY', 'AMGN',
        'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PXD', 'MPC', 'VLO', 'PSX', 'OXY',
        'DIS', 'CMCSA', 'T', 'VZ', 'TMUS', 'CHTR', 'NFLX', 'EA', 'TTWO', 'WBD',
        'HD', 'LOW', 'TGT', 'COST', 'WMT', 'TJX', 'ROST', 'DG', 'DLTR', 'BBY',
        'PG', 'KO', 'PEP', 'PM', 'MO', 'CL', 'EL', 'KMB', 'GIS', 'K',
        'CAT', 'DE', 'MMM', 'HON', 'UPS', 'FDX', 'BA', 'LMT', 'RTX', 'GE',
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'XEL', 'ES', 'EXC', 'SRE', 'ED'
    ]

    signals = []

    # Download all data at once
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

            # Calculate indicators
            df['return'] = df['Close'].pct_change() * 100
            df['prev_return'] = df['return'].shift(1)
            df['ATR'] = calculate_atr(df)

            # Dip-bounce signal: yesterday dip >= 2%, today bounce >= 1%
            for i in range(2, len(df) - MAX_HOLD_DAYS):
                yesterday_ret = df['prev_return'].iloc[i]
                today_ret = df['return'].iloc[i]

                if yesterday_ret <= -2.0 and today_ret >= 1.0:
                    entry_date = df.index[i]
                    entry_price = df['Close'].iloc[i]
                    atr = df['ATR'].iloc[i]

                    if pd.isna(atr) or atr <= 0:
                        continue

                    signals.append({
                        'symbol': symbol,
                        'entry_date': entry_date,
                        'entry_price': entry_price,
                        'atr': atr,
                        'sl_price': entry_price - (atr * SL_MULTIPLIER),
                        'tp_price': entry_price + (atr * TP_MULTIPLIER),
                        'sector': get_stock_sector(symbol),
                        'future_data': df.iloc[i:i+MAX_HOLD_DAYS+1].copy()
                    })
        except Exception as e:
            continue

    return signals

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

def run_backtest_with_recheck(signals: List[Dict], config: Dict,
                              spy_data: pd.DataFrame, vix_data: pd.Series,
                              etf_data: Dict) -> Dict:
    """Run backtest with self-recheck system"""

    recheck_system = SelfRecheckSystem(config)
    trailing_handler = TrailingStopHandler(config)

    results = []
    exit_reasons = {}

    for signal in signals:
        symbol = signal['symbol']
        entry_date = signal['entry_date']
        entry_price = signal['entry_price']
        sl_price = signal['sl_price']
        tp_price = signal['tp_price']
        sector = signal['sector']
        future_data = signal['future_data']

        if len(future_data) < 2:
            continue

        # Calculate entry conditions
        entry_regime = calculate_regime(spy_data, entry_date)
        entry_sector_strength = calculate_sector_strength(sector, etf_data, entry_date)
        try:
            vix_slice = vix_data.loc[:entry_date]
            if len(vix_slice) > 0:
                entry_vix = float(vix_slice.iloc[-1])
            else:
                entry_vix = 20.0
        except:
            entry_vix = 20.0
        entry_score = calculate_score(future_data, entry_date, spy_data, vix_data, sector, etf_data)

        # Track position
        position = {
            'entry_score': entry_score,
            'entry_regime': entry_regime,
            'entry_sector_strength': entry_sector_strength,
            'entry_vix': entry_vix,
            'peak_price': entry_price,
            'trailing_active': False,
            'trailing_activation_pct': 0,
            'trailing_lock_pct': 0,
            'trailing_floor': 0,
            'days_held': 0,
            'current_pnl': 0
        }

        exit_price = None
        exit_reason = None
        exit_day = None

        for day in range(1, len(future_data)):
            current_date = future_data.index[day]
            current_price = future_data['Close'].iloc[day]
            high_price = future_data['High'].iloc[day]
            low_price = future_data['Low'].iloc[day]

            position['days_held'] = day
            position['current_pnl'] = (current_price / entry_price - 1) * 100

            # Update peak price
            if current_price > position['peak_price']:
                position['peak_price'] = current_price

            # Check basic exits first
            # 1. Stop Loss
            if low_price <= sl_price:
                exit_price = sl_price
                exit_reason = "STOP_LOSS"
                exit_day = day
                break

            # 2. Take Profit
            if high_price >= tp_price:
                exit_price = tp_price
                exit_reason = "TAKE_PROFIT"
                exit_day = day
                break

            # 3. Trailing Stop (if active)
            if position['trailing_active']:
                floor_price = position['trailing_floor']
                if low_price <= floor_price:
                    exit_price = floor_price
                    exit_reason = "TRAIL_STOP"
                    exit_day = day
                    break

                # Update floor based on new peak
                if current_price > position['peak_price']:
                    lock_pct = position['trailing_lock_pct']
                    profit_from_entry = (current_price / entry_price - 1) * 100
                    # e.g., profit 15%, lock 60% => floor = entry * (1 + 0.15 * 0.60) = entry * 1.09
                    position['trailing_floor'] = entry_price * (1 + (profit_from_entry / 100) * (lock_pct / 100))

            # 4. Self-Recheck Logic
            if not position['trailing_active'] and config.get('enable_recheck', True):
                # Get current conditions
                hist_data = future_data.iloc[:day+1]
                current_rsi = calculate_rsi(hist_data['Close'])
                momentum_3d = calculate_momentum(hist_data['Close'], min(3, day))

                # Get current VIX safely
                try:
                    vix_slice = vix_data.loc[:current_date]
                    if len(vix_slice) > 0:
                        current_vix_val = float(vix_slice.iloc[-1])
                    else:
                        current_vix_val = float(entry_vix)
                except:
                    current_vix_val = float(entry_vix) if isinstance(entry_vix, (int, float)) else 20.0

                current_conditions = {
                    'score': calculate_score(future_data, current_date, spy_data, vix_data, sector, etf_data),
                    'regime': calculate_regime(spy_data, current_date),
                    'sector_strength': calculate_sector_strength(sector, etf_data, current_date),
                    'vix': current_vix_val,
                    'rsi': current_rsi,
                    'momentum_3d': momentum_3d,
                    'signal_valid': is_signal_still_valid(future_data, current_date)
                }

                action, reason = recheck_system.recheck_position(position, current_conditions)

                if action == "SELL":
                    exit_price = current_price
                    exit_reason = reason
                    exit_day = day
                    break

                elif action == "TRAILING":
                    # Activate trailing stop
                    activation_pct, lock_pct = trailing_handler.get_trailing_params(reason)
                    profit_pct = position['current_pnl']

                    if profit_pct >= activation_pct:
                        position['trailing_active'] = True
                        position['trailing_activation_pct'] = activation_pct
                        position['trailing_lock_pct'] = lock_pct
                        # Lock in lock_pct% of current profit
                        # e.g., if profit is 10% and lock is 60%, floor = entry * (1 + 0.10 * 0.60) = entry * 1.06
                        position['trailing_floor'] = entry_price * (1 + (profit_pct / 100) * (lock_pct / 100))
                        position['trailing_reason'] = reason
                    # If not enough profit, continue holding

            # 5. Max Hold Exit
            if day >= MAX_HOLD_DAYS:
                exit_price = current_price
                exit_reason = "MAX_HOLD"
                exit_day = day
                break

        if exit_price is None:
            # Use last available price
            exit_price = future_data['Close'].iloc[-1]
            exit_reason = "MAX_HOLD"
            exit_day = len(future_data) - 1

        pnl = (exit_price / entry_price - 1) * 100

        results.append({
            'symbol': symbol,
            'entry_date': entry_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl': pnl,
            'exit_reason': exit_reason,
            'days_held': exit_day
        })

        exit_reasons[exit_reason] = exit_reasons.get(exit_reason, 0) + 1

    # Calculate metrics
    if len(results) == 0:
        return {'trades': 0}

    df = pd.DataFrame(results)

    wins = df[df['pnl'] > 0]
    losses = df[df['pnl'] <= 0]

    win_rate = len(wins) / len(df) * 100
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses['pnl'].mean()) if len(losses) > 0 else 0

    expectancy = (win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * avg_loss)

    return {
        'name': config.get('name', 'Unknown'),
        'trades': len(df),
        'expectancy': expectancy,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'avg_hold': df['days_held'].mean(),
        'exit_distribution': exit_reasons,
        'max_drawdown': df['pnl'].min(),
        'big_losses': len(df[df['pnl'] < -5]),
        'results_df': df
    }


# =============================================================================
# RECHECK CONFIGURATIONS
# =============================================================================

def get_recheck_configs() -> List[Dict]:
    """Define recheck configurations to test"""

    configs = []

    # Config 0: Baseline (no recheck)
    configs.append({
        'name': 'Baseline (no recheck)',
        'enable_recheck': False,
        'rules': {}
    })

    # Config 1: Score-based only
    configs.append({
        'name': 'R1: Score < 70 + profit → SELL',
        'enable_recheck': True,
        'rules': {
            'R1_score_low': True,
            'R1_threshold': 70
        }
    })

    # Config 2: Score drop → Trailing
    configs.append({
        'name': 'R2: Score drop > 20 → TRAILING',
        'enable_recheck': True,
        'rules': {
            'R2_score_drop': True,
            'R2_drop_threshold': 20
        },
        'trailing_params': {
            'score': (2.0, 50)
        }
    })

    # Config 3: Regime flip → Trailing
    configs.append({
        'name': 'R3: Regime BULL→BEAR → TRAILING',
        'enable_recheck': True,
        'rules': {
            'R3_regime_flip': True
        },
        'trailing_params': {
            'regime': (2.0, 60)
        }
    })

    # Config 4: Regime flip + profit → Sell
    configs.append({
        'name': 'R4: Regime flip + profit → SELL',
        'enable_recheck': True,
        'rules': {
            'R4_regime_flip_sell': True
        }
    })

    # Config 5: Sector weak → Trailing
    configs.append({
        'name': 'R5: Sector weak + profit > 2% → TRAILING',
        'enable_recheck': True,
        'rules': {
            'R5_sector_weak': True,
            'R5_min_profit': 2.0
        },
        'trailing_params': {
            'sector': (2.0, 50)
        }
    })

    # Config 6: VIX spike → Trailing
    configs.append({
        'name': 'R6: VIX spike > +5 + profit → TRAILING',
        'enable_recheck': True,
        'rules': {
            'R6_vix_spike': True,
            'R6_vix_threshold': 5
        },
        'trailing_params': {
            'vix': (1.5, 70)
        }
    })

    # Config 7: Signal invalid → Sell
    configs.append({
        'name': 'R7: Signal invalid + profit → SELL',
        'enable_recheck': True,
        'rules': {
            'R7_signal_invalid': True
        }
    })

    # Config 8: RSI high → Sell
    configs.append({
        'name': 'R8: RSI > 70 + profit > 2% → SELL',
        'enable_recheck': True,
        'rules': {
            'R8_rsi_high': True,
            'R8_rsi_threshold': 70,
            'R8_min_profit': 2.0
        }
    })

    # Config 9: Momentum fade → Trailing
    configs.append({
        'name': 'R9: Momentum < -2% + profit → TRAILING',
        'enable_recheck': True,
        'rules': {
            'R9_momentum_fade': True
        },
        'trailing_params': {
            'momentum': (1.5, 60)
        }
    })

    # Config 10: Combined - Conservative
    configs.append({
        'name': 'Combined: Conservative (R3+R5+R8)',
        'enable_recheck': True,
        'rules': {
            'R3_regime_flip': True,
            'R5_sector_weak': True,
            'R5_min_profit': 2.0,
            'R8_rsi_high': True,
            'R8_rsi_threshold': 70,
            'R8_min_profit': 2.0
        },
        'trailing_params': {
            'regime': (2.0, 60),
            'sector': (2.0, 50)
        }
    })

    # Config 11: Combined - Aggressive
    configs.append({
        'name': 'Combined: Aggressive (R1+R4+R7+R8)',
        'enable_recheck': True,
        'rules': {
            'R1_score_low': True,
            'R1_threshold': 70,
            'R4_regime_flip_sell': True,
            'R7_signal_invalid': True,
            'R8_rsi_high': True,
            'R8_rsi_threshold': 65,
            'R8_min_profit': 1.5
        }
    })

    # Config 12: Combined - Balanced
    configs.append({
        'name': 'Combined: Balanced (R2+R3+R6+R9)',
        'enable_recheck': True,
        'rules': {
            'R2_score_drop': True,
            'R2_drop_threshold': 20,
            'R3_regime_flip': True,
            'R6_vix_spike': True,
            'R6_vix_threshold': 5,
            'R9_momentum_fade': True
        },
        'trailing_params': {
            'score': (2.0, 50),
            'regime': (2.0, 60),
            'vix': (1.5, 70),
            'momentum': (1.5, 60)
        }
    })

    # Config 13: Smart Exit (all profit-protecting rules)
    configs.append({
        'name': 'Smart Exit: All Profit Protection',
        'enable_recheck': True,
        'rules': {
            'R1_score_low': True,
            'R1_threshold': 65,
            'R3_regime_flip': True,
            'R5_sector_weak': True,
            'R5_min_profit': 1.5,
            'R6_vix_spike': True,
            'R6_vix_threshold': 5,
            'R8_rsi_high': True,
            'R8_rsi_threshold': 65,
            'R8_min_profit': 1.5,
            'R9_momentum_fade': True
        },
        'trailing_params': {
            'regime': (1.5, 65),
            'sector': (1.5, 55),
            'vix': (1.0, 75),
            'momentum': (1.0, 65)
        }
    })

    return configs


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 90)
    print("SELF-RECHECK EXIT SYSTEM BACKTEST")
    print("=" * 90)
    print("Concept: ใช้ 30 Layers recheck position ทุกวัน")
    print()

    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)  # 2 years

    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print()

    # Load market data
    print("Loading market data...")
    vix_data = load_vix_data()
    spy_data = load_spy_data()
    etf_data = load_sector_etf_data()
    print(f"VIX data: {len(vix_data)} days")
    print(f"SPY data: {len(spy_data)} days")
    print(f"Sector ETFs: {len(etf_data)} loaded")
    print()

    # Collect signals
    print("Collecting dip-bounce signals...")
    signals = collect_signals(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d')
    )
    print(f"Total signals: {len(signals)}")
    print()

    # Get configurations
    configs = get_recheck_configs()

    # Run backtests
    results = []

    for config in configs:
        print(f"Testing: {config['name']}...")
        result = run_backtest_with_recheck(signals, config, spy_data, vix_data, etf_data)
        results.append(result)

    print()
    print("=" * 90)
    print("INDIVIDUAL RULE RESULTS")
    print("=" * 90)
    print()

    print(f"{'Config':<45} {'E[R]':>8} {'Hold':>7} {'Win%':>7} {'MaxH%':>7} {'BigL':>6}")
    print("-" * 90)

    baseline = results[0]

    for r in results:
        if r['trades'] == 0:
            continue

        maxh_pct = r['exit_distribution'].get('MAX_HOLD', 0) / r['trades'] * 100

        print(f"{r['name']:<45} {r['expectancy']:>+7.3f}% {r['avg_hold']:>6.1f}d {r['win_rate']:>6.1f}% {maxh_pct:>6.1f}% {r['big_losses']:>5}")

    print()
    print("=" * 90)
    print("EXIT DISTRIBUTION ANALYSIS")
    print("=" * 90)
    print()

    for r in results[:3]:  # Show first 3 configs
        if r['trades'] == 0:
            continue
        print(f"{r['name']}:")
        for reason, count in sorted(r['exit_distribution'].items(), key=lambda x: -x[1]):
            pct = count / r['trades'] * 100
            print(f"  {reason}: {count} ({pct:.1f}%)")
        print()

    print("=" * 90)
    print("COMBINED STRATEGIES COMPARISON")
    print("=" * 90)
    print()

    # Find best strategies
    combined_results = [r for r in results if 'Combined' in r['name'] or 'Smart' in r['name']]

    print(f"{'Strategy':<45} {'E[R]':>8} {'Hold':>7} {'Win%':>7} {'MaxH%':>7}")
    print("-" * 90)

    for r in combined_results:
        if r['trades'] == 0:
            continue
        maxh_pct = r['exit_distribution'].get('MAX_HOLD', 0) / r['trades'] * 100
        print(f"{r['name']:<45} {r['expectancy']:>+7.3f}% {r['avg_hold']:>6.1f}d {r['win_rate']:>6.1f}% {maxh_pct:>6.1f}%")

    print()
    print("=" * 90)
    print("PROTECTION ANALYSIS")
    print("=" * 90)
    print()

    # Compare big losses across configs
    print(f"{'Config':<45} {'Big Losses (< -5%)':<20} {'Max DD':>10}")
    print("-" * 90)

    for r in results:
        if r['trades'] == 0:
            continue
        big_loss_pct = r['big_losses'] / r['trades'] * 100
        print(f"{r['name']:<45} {r['big_losses']:>3} ({big_loss_pct:>5.1f}%) {r['max_drawdown']:>+9.1f}%")

    print()
    print("=" * 90)
    print("SUCCESS CRITERIA CHECK")
    print("=" * 90)
    print()

    # Find best config
    valid_results = [r for r in results if r['trades'] > 0 and r['expectancy'] > 0]

    if len(valid_results) > 0:
        # Score = E[R] * (1 - hold_penalty) * protection_bonus
        for r in valid_results:
            hold_penalty = max(0, (r['avg_hold'] - 7) / 30)  # Penalty for hold > 7d
            maxh_pct = r['exit_distribution'].get('MAX_HOLD', 0) / r['trades'] * 100
            protection_bonus = 1 + (100 - maxh_pct) / 200  # Bonus for low max hold exits
            r['score'] = r['expectancy'] * (1 - hold_penalty * 0.3) * protection_bonus

        best = max(valid_results, key=lambda x: x['score'])

        print(f"Best Config: {best['name']}")
        print()

        # Check criteria
        criteria = [
            (f"Avg Hold ≤ 10 days", best['avg_hold'] <= 10, f"{best['avg_hold']:.1f} days"),
            (f"E[R] ≥ +1.2%", best['expectancy'] >= 1.2, f"{best['expectancy']:+.3f}%"),
            (f"Max Hold Exit ≤ 15%", best['exit_distribution'].get('MAX_HOLD', 0) / best['trades'] * 100 <= 15,
             f"{best['exit_distribution'].get('MAX_HOLD', 0) / best['trades'] * 100:.1f}%"),
            (f"Win Rate ≥ 40%", best['win_rate'] >= 40, f"{best['win_rate']:.1f}%"),
            (f"Big Losses < Baseline", best['big_losses'] <= baseline['big_losses'],
             f"{best['big_losses']} vs {baseline['big_losses']}")
        ]

        passed = 0
        for desc, met, value in criteria:
            status = "✅" if met else "❌"
            print(f"  {status} {desc}: {value}")
            if met:
                passed += 1

        print(f"\nPassed: {passed}/{len(criteria)}")

    print()
    print("=" * 90)
    print("FINAL RECOMMENDATION")
    print("=" * 90)
    print()

    # Determine recommendation
    if len(valid_results) > 0:
        best = max(valid_results, key=lambda x: x['score'])
        best_maxh = best['exit_distribution'].get('MAX_HOLD', 0) / best['trades'] * 100
        baseline_maxh = baseline['exit_distribution'].get('MAX_HOLD', 0) / baseline['trades'] * 100

        # Decision logic
        if best['expectancy'] >= baseline['expectancy'] * 0.95:  # Within 5% of baseline
            if best['avg_hold'] < baseline['avg_hold'] * 0.8:  # 20%+ hold reduction
                recommendation = "IMPLEMENT SELF-RECHECK"
                confidence = 85
            elif best_maxh < baseline_maxh * 0.7:  # 30%+ reduction in max hold exits
                recommendation = "IMPLEMENT SELF-RECHECK"
                confidence = 75
            else:
                recommendation = "KEEP BASELINE v5.6"
                confidence = 70
        else:
            recommendation = "KEEP BASELINE v5.6"
            confidence = 80

        print("┌" + "─" * 70 + "┐")
        print("│  SELF-RECHECK EXIT SYSTEM RESULTS" + " " * 35 + "│")
        print("├" + "─" * 70 + "┤")
        print("│" + " " * 70 + "│")
        print(f"│  BEST RECHECK SYSTEM: {best['name'][:45]:<45} │")
        print("│" + " " * 70 + "│")
        print("│  PERFORMANCE vs BASELINE:                                           │")
        e_cmp = f"{best['expectancy']:+.3f}% vs {baseline['expectancy']:+.3f}%"
        print(f"│  ├── E[R]: {e_cmp:<56} │")
        h_cmp = f"{best['avg_hold']:.1f}d vs {baseline['avg_hold']:.1f}d"
        print(f"│  ├── Avg Hold: {h_cmp:<51} │")
        m_cmp = f"{best_maxh:.1f}% vs {baseline_maxh:.1f}%"
        print(f"│  ├── Max Hold Exits: {m_cmp:<45} │")
        w_cmp = f"{best['win_rate']:.1f}% vs {baseline['win_rate']:.1f}%"
        print(f"│  └── Win Rate: {w_cmp:<51} │")
        print("│" + " " * 70 + "│")
        print("│  PROTECTION ANALYSIS:                                               │")
        bl_cmp = f"{best['big_losses']} vs {baseline['big_losses']}"
        print(f"│  ├── Big Losses (< -5%): {bl_cmp:<41} │")
        dd_cmp = f"{best['max_drawdown']:+.1f}% vs {baseline['max_drawdown']:+.1f}%"
        print(f"│  └── Max Drawdown: {dd_cmp:<47} │")
        print("│" + " " * 70 + "│")
        print(f"│  RECOMMENDATION: {recommendation:<49} │")
        print(f"│  CONFIDENCE: {confidence}%{' ' * 55}│")
        print("└" + "─" * 70 + "┘")

    print()

    # Save detailed results
    output_file = "backtest_results/self_recheck_results.csv"
    try:
        import os
        os.makedirs("backtest_results", exist_ok=True)

        summary_data = []
        for r in results:
            if r['trades'] == 0:
                continue
            maxh_pct = r['exit_distribution'].get('MAX_HOLD', 0) / r['trades'] * 100
            summary_data.append({
                'Config': r['name'],
                'E[R]': r['expectancy'],
                'Win Rate': r['win_rate'],
                'Avg Hold': r['avg_hold'],
                'Max Hold %': maxh_pct,
                'Big Losses': r['big_losses'],
                'Trades': r['trades']
            })

        pd.DataFrame(summary_data).to_csv(output_file, index=False)
        print(f"Results saved to: {output_file}")
    except Exception as e:
        print(f"Could not save results: {e}")


if __name__ == "__main__":
    main()
