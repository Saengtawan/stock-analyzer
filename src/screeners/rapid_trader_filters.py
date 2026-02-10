#!/usr/bin/env python3
"""
RAPID TRADER FILTERS v4.0 - Single Source of Truth

This module contains ALL filter logic for Rapid Trader strategy.
Both production screener and backtest should use these functions.

IMPORTANT:
- Any filter changes must be made HERE
- Both rapid_rotation_screener.py and STANDARD_BACKTEST.py should import from here
- This ensures consistency between production and backtest

Filter History:
- v3.3: Bounce confirmation filters
- v3.4: Dynamic SL/TP calculation
- v3.5: Added SMA20 filter (92% of losers were below SMA20)
- v4.0: Market Regime Filter (SPY > SMA20 = Bull → Trade)
        Backtest: +5.5%/mo, DD 8.9%, WR 49%
"""

from typing import Dict, Optional, Tuple
import pandas as pd
import numpy as np
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from config.strategy_config import RapidRotationConfig
except ImportError:
    # Fallback for tests or standalone usage
    RapidRotationConfig = None


# ============================================================================
# CONFIGURATION
# ============================================================================
class FilterConfig:
    """
    Filter configuration - Single Source of Truth (v6.7)

    Now loads from RapidRotationConfig instead of hardcoded values.
    Backward compatible: can still be used without config (uses defaults).
    """

    def __init__(self, config: 'RapidRotationConfig' = None):
        """
        Initialize FilterConfig

        Args:
            config: Optional RapidRotationConfig instance. If None, uses defaults.
        """
        if config is None and RapidRotationConfig is not None:
            # Try to load from default YAML
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'config', 'trading.yaml'
            )
            if os.path.exists(config_path):
                try:
                    config = RapidRotationConfig.from_yaml(config_path)
                except Exception:
                    pass  # Fall back to defaults

        self.config = config

        # Minimum requirements
        self.MIN_SCORE = config.min_score if config else 85
        self.MIN_ATR_PCT = config.min_atr_pct if config else 2.5
        self.MIN_PRICE = 10  # Not in config yet
        self.MAX_PRICE = 2000  # Not in config yet

        # Dynamic SL/TP
        self.ATR_SL_MULTIPLIER = config.atr_sl_multiplier if config else 1.5
        self.ATR_TP_MULTIPLIER = config.atr_tp_multiplier if config else 3.0
        self.MIN_SL_PCT = config.min_sl_pct if config else 2.0
        self.MAX_SL_PCT = config.max_sl_pct if config else 4.0
        self.MIN_TP_PCT = config.min_tp_pct if config else 4.0
        self.MAX_TP_PCT = config.max_tp_pct if config else 8.0

        # Base SL/TP for simplified calculation
        self.BASE_SL_PCT = config.default_sl_pct if config else 2.5
        self.BASE_TP_PCT = config.default_tp_pct if config else 5.0


# Legacy class-level constants for backward compatibility
# These are deprecated and will be removed in future versions
FilterConfig.MIN_SCORE = 85
FilterConfig.MIN_ATR_PCT = 2.5
FilterConfig.MIN_PRICE = 10
FilterConfig.MAX_PRICE = 2000
FilterConfig.ATR_SL_MULTIPLIER = 1.5
FilterConfig.ATR_TP_MULTIPLIER = 3.0
FilterConfig.MIN_SL_PCT = 2.0
FilterConfig.MAX_SL_PCT = 4.0
FilterConfig.MIN_TP_PCT = 4.0
FilterConfig.MAX_TP_PCT = 8.0
FilterConfig.BASE_SL_PCT = 2.5
FilterConfig.BASE_TP_PCT = 6.0


# ============================================================================
# INDICATOR CALCULATIONS
# ============================================================================
def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """Calculate RSI for given price series"""
    if len(prices) < period + 1:
        return 50.0
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    if loss.iloc[-1] == 0:
        return 100.0
    rs = gain.iloc[-1] / loss.iloc[-1]
    return 100 - (100 / (1 + rs))


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """Calculate ATR for given OHLC data"""
    if len(close) < period + 1:
        return 0.0
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]


# ============================================================================
# BOUNCE CONFIRMATION FILTERS (v3.3)
# ============================================================================
def check_bounce_confirmation(
    yesterday_move: float,
    mom_1d: float,
    today_is_green: bool,
    gap_pct: float,
    current_price: float,
    sma5: float,
    atr_pct: float,
) -> Tuple[bool, str]:
    """
    Check bounce confirmation filters

    Returns:
        Tuple of (passed, rejection_reason)
    """
    # FILTER 1: Yesterday MUST be down (the dip day)
    if yesterday_move > -1.0:
        return False, "Yesterday not down enough"

    # FILTER 2: Today should show recovery (not falling further)
    if mom_1d < -1.0:
        return False, "Still falling hard"

    # FILTER 3: Strong preference for green candle (bounce signal)
    if not today_is_green and mom_1d < 0.5:
        return False, "No clear bounce signal"

    # FILTER 4: Skip big gap ups (exhaustion risk)
    if gap_pct > 2.0:
        return False, "Gap up too large (exhaustion risk)"

    # FILTER 5: Still in oversold zone (room to recover)
    if current_price > sma5 * 1.02:
        return False, "Too extended above SMA5"

    # FILTER 6: Minimum volatility
    if atr_pct < FilterConfig.MIN_ATR_PCT:
        return False, f"Volatility too low ({atr_pct:.1f}% < {FilterConfig.MIN_ATR_PCT}%)"

    return True, ""


# ============================================================================
# SMA20 FILTER (v3.5 - ROOT CAUSE FIX)
# ============================================================================
def check_sma20_filter(current_price: float, sma20: float) -> Tuple[bool, str]:
    """
    Check SMA20 trend filter (v6.17 - Reverted to strict > 0%)

    Based on root cause analysis: 92% of stop loss trades were below SMA20

    Reverted: Require strictly above SMA20 (no pullbacks allowed).
    This prevents catching stocks in downtrends.

    Returns:
        Tuple of (passed, rejection_reason)
    """
    # Calculate distance from SMA20
    sma20_distance_pct = ((current_price - sma20) / sma20) * 100

    # v6.17: Strict filter - must be above SMA20
    if sma20_distance_pct < 0:
        return False, f"Below SMA20 ({sma20_distance_pct:.1f}%)"

    return True, ""


# ============================================================================
# PRICE FILTERS
# ============================================================================
def check_price_filters(current_price: float) -> Tuple[bool, str]:
    """
    Check basic price filters

    Returns:
        Tuple of (passed, rejection_reason)
    """
    if current_price < FilterConfig.MIN_PRICE:
        return False, f"Price too low (${current_price:.2f} < ${FilterConfig.MIN_PRICE})"

    if current_price > FilterConfig.MAX_PRICE:
        return False, f"Price too high (${current_price:.2f} > ${FilterConfig.MAX_PRICE})"

    return True, ""


# ============================================================================
# SCORING LOGIC (v3.3)
# ============================================================================
def calculate_score(
    today_is_green: bool,
    mom_1d: float,
    mom_5d: float,
    yesterday_move: float,
    rsi: float,
    current_price: float,
    sma20: float,
    sma50: float,
    atr_pct: float,
    dist_from_high: float,
    volume_ratio: float,
) -> Tuple[int, list]:
    """
    Calculate screening score

    Returns:
        Tuple of (score, reasons)
    """
    score = 0
    reasons = []

    # 1. BOUNCE CONFIRMATION (max 40 pts)
    if today_is_green and mom_1d > 0.5:
        score += 40
        reasons.append("Strong bounce")
    elif today_is_green or mom_1d > 0.3:
        score += 25
        reasons.append("Bounce confirmed")

    # 2. Prior dip magnitude (max 40 pts)
    if -12 <= mom_5d <= -5:
        score += 40
        reasons.append(f"Deep dip {mom_5d:.1f}%")
    elif -5 < mom_5d <= -3:
        score += 30
        reasons.append(f"Good dip {mom_5d:.1f}%")
    elif -3 < mom_5d < 0:
        score += 15
        reasons.append(f"Mild dip {mom_5d:.1f}%")

    # 3. Yesterday's dip (max 30 pts)
    if yesterday_move <= -3:
        score += 30
        reasons.append(f"Big dip yesterday {yesterday_move:.1f}%")
    elif yesterday_move <= -1.5:
        score += 20
        reasons.append(f"Dip yesterday {yesterday_move:.1f}%")
    elif yesterday_move <= -1:
        score += 10

    # 4. RSI scoring (max 35 pts)
    if 25 <= rsi <= 40:
        score += 35
        reasons.append(f"Very oversold RSI={rsi:.0f}")
    elif 40 < rsi <= 50:
        score += 20
        reasons.append(f"Low RSI={rsi:.0f}")

    # 5. Trend context (max 25 pts)
    if current_price > sma50 and current_price > sma20 * 0.98:
        score += 25
        reasons.append("Strong uptrend")
    elif current_price > sma20:
        score += 15
        reasons.append("Above SMA20")

    # 6. Volatility bonus (max 20 pts)
    if atr_pct > 5:
        score += 20
        reasons.append(f"Very volatile {atr_pct:.1f}%")
    elif atr_pct > 4:
        score += 15
        reasons.append(f"High vol {atr_pct:.1f}%")
    elif atr_pct > 3:
        score += 10

    # 7. Room to recover (max 20 pts)
    if 10 <= dist_from_high <= 25:
        score += 20
        reasons.append(f"Great room {dist_from_high:.0f}%")
    elif 6 <= dist_from_high < 10:
        score += 10
        reasons.append(f"Some room {dist_from_high:.0f}%")

    # 8. Volume confirmation (max 15 pts)
    if volume_ratio > 1.5:
        score += 15
        reasons.append("High vol bounce")
    elif volume_ratio > 1.2:
        score += 5

    return score, reasons


# ============================================================================
# DYNAMIC SL/TP CALCULATION (v3.4)
# ============================================================================
def calculate_dynamic_sl_tp(
    current_price: float,
    atr: float,
    swing_low_5d: float,
    ema5: float,
    high_20d: float,
    high_52w: float,
) -> Dict:
    """
    Calculate dynamic SL/TP based on market structure

    Returns:
        Dict with sl, tp, sl_pct, tp_pct, sl_method, tp_method
    """
    # --- DYNAMIC STOP LOSS ---
    # Method 1: ATR-based
    atr_based_sl = current_price - (atr * FilterConfig.ATR_SL_MULTIPLIER)

    # Method 2: Swing Low based
    swing_low_sl = swing_low_5d * 0.995  # 0.5% below swing low

    # Method 3: EMA based
    ema_based_sl = ema5 * 0.99  # 1% below EMA5

    # Choose HIGHEST SL = best protection
    sl_options = {
        'ATR': atr_based_sl,
        'SwingLow': swing_low_sl,
        'EMA5': ema_based_sl
    }
    sl_method = max(sl_options, key=sl_options.get)
    stop_loss = sl_options[sl_method]

    # Apply safety caps
    sl_pct_raw = (current_price - stop_loss) / current_price * 100
    sl_pct = max(FilterConfig.MIN_SL_PCT, min(sl_pct_raw, FilterConfig.MAX_SL_PCT))
    stop_loss = current_price * (1 - sl_pct / 100)

    # --- DYNAMIC TAKE PROFIT ---
    # Method 1: ATR-based
    atr_based_tp = current_price + (atr * FilterConfig.ATR_TP_MULTIPLIER)

    # Method 2: Resistance based
    resistance_tp = high_20d * 0.995  # Just below resistance

    # Method 3: 52-week high consideration
    high_52w_tp = high_52w * 0.98  # 2% below 52w high

    # Choose LOWEST TP = most realistic target
    tp_options = {
        'ATR': atr_based_tp,
        'Resistance': resistance_tp,
        '52wHigh': high_52w_tp
    }
    tp_method = min(tp_options, key=tp_options.get)
    take_profit = tp_options[tp_method]

    # Apply safety caps
    tp_pct_raw = (take_profit - current_price) / current_price * 100
    tp_pct = max(FilterConfig.MIN_TP_PCT, min(tp_pct_raw, FilterConfig.MAX_TP_PCT))
    take_profit = current_price * (1 + tp_pct / 100)

    return {
        'stop_loss': round(stop_loss, 2),
        'take_profit': round(take_profit, 2),
        'sl_pct': round(sl_pct, 2),
        'tp_pct': round(tp_pct, 2),
        'sl_method': sl_method,
        'tp_method': tp_method,
        'risk_reward': round(tp_pct / sl_pct, 2),
    }


def calculate_simple_sl_tp(current_price: float, atr_pct: float, support: float) -> Dict:
    """
    Calculate simple SL/TP (for backtest compatibility)

    This is a simplified version that doesn't require all the data
    """
    # TP multiplier based on volatility
    tp_multiplier = min(1.5, max(1.0, atr_pct / 3))
    tp_pct = FilterConfig.BASE_TP_PCT * tp_multiplier

    # SL based on volatility
    if atr_pct > 5:
        sl_pct = 4.0
    elif atr_pct > 4:
        sl_pct = 3.75
    else:
        sl_pct = FilterConfig.BASE_SL_PCT

    # Consider support level
    sl_from_support = ((current_price - support * 0.995) / current_price) * 100
    sl_pct = max(sl_pct, min(sl_from_support * 0.8, 4.5))

    stop_loss = current_price * (1 - sl_pct / 100)
    take_profit = current_price * (1 + tp_pct / 100)

    return {
        'stop_loss': round(stop_loss, 2),
        'take_profit': round(take_profit, 2),
        'sl_pct': round(sl_pct, 2),
        'tp_pct': round(tp_pct, 2),
    }


# ============================================================================
# COMPLETE FILTER CHECK
# ============================================================================
def apply_all_filters(
    current_price: float,
    yesterday_move: float,
    mom_1d: float,
    today_is_green: bool,
    gap_pct: float,
    sma5: float,
    sma20: float,
    atr_pct: float,
) -> Tuple[bool, str]:
    """
    Apply all filters in sequence

    Returns:
        Tuple of (passed, rejection_reason)
    """
    # 1. Price filters
    passed, reason = check_price_filters(current_price)
    if not passed:
        return False, reason

    # 2. Bounce confirmation filters
    passed, reason = check_bounce_confirmation(
        yesterday_move, mom_1d, today_is_green, gap_pct,
        current_price, sma5, atr_pct
    )
    if not passed:
        return False, reason

    # 3. SMA20 filter (v3.5)
    passed, reason = check_sma20_filter(current_price, sma20)
    if not passed:
        return False, reason

    return True, ""


# ============================================================================
# TEST
# ============================================================================
if __name__ == "__main__":
    print("Rapid Trader Filters v3.5")
    print("=" * 50)
    print("\nFilters:")
    print("1. Price filter: $10 - $2000")
    print("2. Bounce confirmation (v3.3)")
    print("3. SMA20 filter (v3.5 - root cause fix)")
    print("\nConfiguration:")
    print(f"  MIN_SCORE: {FilterConfig.MIN_SCORE}")
    print(f"  MIN_ATR_PCT: {FilterConfig.MIN_ATR_PCT}%")
    print(f"  SL range: {FilterConfig.MIN_SL_PCT}% - {FilterConfig.MAX_SL_PCT}%")
    print(f"  TP range: {FilterConfig.MIN_TP_PCT}% - {FilterConfig.MAX_TP_PCT}%")

    # Test SMA20 filter
    print("\n" + "=" * 50)
    print("Testing SMA20 Filter:")

    # Should fail
    result, reason = check_sma20_filter(95, 100)
    print(f"  Price $95, SMA20 $100: {'PASS' if result else 'FAIL'} - {reason or 'OK'}")

    # Should pass
    result, reason = check_sma20_filter(105, 100)
    print(f"  Price $105, SMA20 $100: {'PASS' if result else 'FAIL'} - {reason or 'OK'}")
