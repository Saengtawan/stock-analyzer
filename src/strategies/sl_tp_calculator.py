#!/usr/bin/env python3
"""
SL/TP Calculator - Single Source of Truth

This module is the ONLY place where Stop Loss and Take Profit calculations happen.
All other code (screener, portfolio manager, engine) MUST use this calculator.

Design:
- Uses RapidRotationConfig for parameters (min/max bounds, ATR multipliers)
- Implements multiple SL/TP strategies (ATR-based, swing-based, fixed)
- Returns structured result with all metadata for debugging

v6.7 - Initial version extracted from rapid_trader_filters.py
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import sys
import os

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from config.strategy_config import RapidRotationConfig
except ImportError:
    RapidRotationConfig = None


@dataclass
class SLTPResult:
    """
    Result from SL/TP calculation

    Contains all information needed for:
    - Order placement (stop_loss, take_profit prices)
    - Risk management (sl_pct, tp_pct, risk_reward)
    - Logging/debugging (sl_method, tp_method)
    """
    # Prices
    stop_loss: float           # Actual SL price
    take_profit: float         # Actual TP price

    # Percentages
    sl_pct: float              # SL as % from entry
    tp_pct: float              # TP as % from entry

    # Metadata
    sl_method: str             # How SL was calculated ("ATR", "swing_low", "fixed")
    tp_method: str             # How TP was calculated ("ATR", "resistance", "fixed")
    risk_reward: float         # R:R ratio (tp_pct / sl_pct)

    # Optional debug info
    atr_value: Optional[float] = None
    swing_low: Optional[float] = None
    resistance: Optional[float] = None


class SLTPCalculator:
    """
    Single source of truth for SL/TP calculation

    Strategy (from rapid_trader_filters.py):
    - SL: 1.5×ATR (clamped 2%-4%) - primary method
    - SL: MAX(ATR-based, swing_low, EMA5) - use best available
    - TP: 3×ATR (clamped 4%-8%) - primary method
    - TP: MIN(ATR-based, resistance levels) - avoid overreach

    Usage:
        config = RapidRotationConfig.from_yaml('config/trading.yaml')
        calculator = SLTPCalculator(config)

        result = calculator.calculate(
            entry_price=100.0,
            atr=2.5,
            swing_low=98.0,
            ema5=99.5,
            high_20d=105.0,
            high_52w=110.0
        )

        print(f"SL: ${result.stop_loss} (-{result.sl_pct}%)")
        print(f"TP: ${result.take_profit} (+{result.tp_pct}%)")
        print(f"R:R: {result.risk_reward:.2f}")
    """

    def __init__(self, config: 'RapidRotationConfig' = None):
        """
        Initialize calculator with configuration

        Args:
            config: RapidRotationConfig instance. If None, loads from default YAML.
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

        # Store config or use defaults
        self.atr_sl_multiplier = config.atr_sl_multiplier if config else 1.5
        self.atr_tp_multiplier = config.atr_tp_multiplier if config else 3.0
        self.min_sl_pct = config.min_sl_pct if config else 2.0
        self.max_sl_pct = config.max_sl_pct if config else 4.0
        self.min_tp_pct = config.min_tp_pct if config else 4.0
        self.max_tp_pct = config.max_tp_pct if config else 8.0
        self.default_sl_pct = config.default_sl_pct if config else 2.5
        self.default_tp_pct = config.default_tp_pct if config else 5.0

    def calculate(
        self,
        entry_price: float,
        atr: float = None,
        swing_low: float = None,
        ema5: float = None,
        high_20d: float = None,
        high_52w: float = None
    ) -> SLTPResult:
        """
        Calculate dynamic SL/TP based on available indicators

        This is the ONLY method that should be used for SL/TP calculation.
        All other code must call this method.

        Args:
            entry_price: Entry price for the position
            atr: Average True Range (absolute value, not %)
            swing_low: Recent swing low (5-day low)
            ema5: 5-day EMA
            high_20d: 20-day high
            high_52w: 52-week high

        Returns:
            SLTPResult with all SL/TP information
        """
        # =====================================================================
        # STOP LOSS CALCULATION
        # =====================================================================
        sl_candidates = []
        sl_method = "fixed"

        # Method 1: ATR-based SL (primary)
        if atr and atr > 0:
            atr_based_sl = entry_price - (atr * self.atr_sl_multiplier)
            sl_candidates.append(('ATR', atr_based_sl))

        # Method 2: Swing low (support level)
        if swing_low and swing_low < entry_price:
            # Place SL slightly below swing low (0.5% buffer)
            swing_sl = swing_low * 0.995
            sl_candidates.append(('swing_low', swing_sl))

        # Method 3: EMA5-based SL
        if ema5 and ema5 < entry_price:
            # Place SL slightly below EMA5 (0.5% buffer)
            ema_sl = ema5 * 0.995
            sl_candidates.append(('EMA5', ema_sl))

        # Choose the HIGHEST SL (most conservative)
        if sl_candidates:
            sl_method, stop_loss = max(sl_candidates, key=lambda x: x[1])
        else:
            # Fallback to fixed SL
            stop_loss = entry_price * (1 - self.default_sl_pct / 100)
            sl_method = "fixed"

        # Calculate SL percentage
        sl_pct_raw = ((entry_price - stop_loss) / entry_price) * 100

        # Clamp SL to min/max bounds (safety caps)
        sl_pct = max(self.min_sl_pct, min(sl_pct_raw, self.max_sl_pct))
        stop_loss = entry_price * (1 - sl_pct / 100)

        # =====================================================================
        # TAKE PROFIT CALCULATION
        # =====================================================================
        tp_candidates = []
        tp_method = "fixed"

        # Method 1: ATR-based TP (primary)
        if atr and atr > 0:
            atr_based_tp = entry_price + (atr * self.atr_tp_multiplier)
            tp_candidates.append(('ATR', atr_based_tp))

        # Method 2: Resistance levels
        if high_20d and high_20d > entry_price:
            # Take profit at 20-day high (90% of distance to avoid overshoot)
            resistance_tp = entry_price + (high_20d - entry_price) * 0.9
            tp_candidates.append(('resistance_20d', resistance_tp))

        if high_52w and high_52w > entry_price:
            # Take profit at 52-week high (80% of distance)
            resistance_52w_tp = entry_price + (high_52w - entry_price) * 0.8
            tp_candidates.append(('resistance_52w', resistance_52w_tp))

        # Choose the LOWEST TP (most conservative, easier to hit)
        if tp_candidates:
            tp_method, take_profit = min(tp_candidates, key=lambda x: x[1])
        else:
            # Fallback to fixed TP
            take_profit = entry_price * (1 + self.default_tp_pct / 100)
            tp_method = "fixed"

        # Calculate TP percentage
        tp_pct_raw = ((take_profit - entry_price) / entry_price) * 100

        # Clamp TP to min/max bounds (safety caps)
        tp_pct = max(self.min_tp_pct, min(tp_pct_raw, self.max_tp_pct))
        take_profit = entry_price * (1 + tp_pct / 100)

        # =====================================================================
        # RISK:REWARD CALCULATION
        # =====================================================================
        risk_reward = tp_pct / sl_pct if sl_pct > 0 else 0.0

        # =====================================================================
        # RETURN RESULT
        # =====================================================================
        return SLTPResult(
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            sl_pct=round(sl_pct, 2),
            tp_pct=round(tp_pct, 2),
            sl_method=sl_method,
            tp_method=tp_method,
            risk_reward=round(risk_reward, 2),
            atr_value=atr,
            swing_low=swing_low,
            resistance=high_20d or high_52w
        )

    def calculate_simple(
        self,
        entry_price: float,
        sl_pct: float = None,
        tp_pct: float = None
    ) -> SLTPResult:
        """
        Calculate simple fixed-percentage SL/TP

        Useful for quick calculations or when indicators are not available.

        Args:
            entry_price: Entry price
            sl_pct: Stop loss percentage (default from config)
            tp_pct: Take profit percentage (default from config)

        Returns:
            SLTPResult with fixed SL/TP
        """
        sl_pct = sl_pct or self.default_sl_pct
        tp_pct = tp_pct or self.default_tp_pct

        # Clamp to bounds
        sl_pct = max(self.min_sl_pct, min(sl_pct, self.max_sl_pct))
        tp_pct = max(self.min_tp_pct, min(tp_pct, self.max_tp_pct))

        stop_loss = entry_price * (1 - sl_pct / 100)
        take_profit = entry_price * (1 + tp_pct / 100)
        risk_reward = tp_pct / sl_pct if sl_pct > 0 else 0.0

        return SLTPResult(
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            sl_pct=round(sl_pct, 2),
            tp_pct=round(tp_pct, 2),
            sl_method="fixed",
            tp_method="fixed",
            risk_reward=round(risk_reward, 2)
        )


# ============================================================================
# CONVENIENCE FUNCTIONS (for backward compatibility)
# ============================================================================

def calculate_sl_tp(
    entry_price: float,
    atr: float = None,
    config: 'RapidRotationConfig' = None,
    **kwargs
) -> Tuple[float, float, float, float]:
    """
    Convenience function for backward compatibility

    Returns:
        Tuple of (stop_loss, take_profit, sl_pct, tp_pct)
    """
    calculator = SLTPCalculator(config)
    result = calculator.calculate(entry_price=entry_price, atr=atr, **kwargs)
    return result.stop_loss, result.take_profit, result.sl_pct, result.tp_pct


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("SL/TP Calculator - Example Usage\n")

    # Example 1: With default config
    print("Example 1: Default config")
    calculator = SLTPCalculator()
    result = calculator.calculate(
        entry_price=100.0,
        atr=2.5,
        swing_low=98.0,
        ema5=99.5,
        high_20d=105.0
    )
    print(f"  Entry: $100.00")
    print(f"  SL: ${result.stop_loss} (-{result.sl_pct}%) via {result.sl_method}")
    print(f"  TP: ${result.take_profit} (+{result.tp_pct}%) via {result.tp_method}")
    print(f"  R:R: {result.risk_reward:.2f}")

    # Example 2: Simple fixed SL/TP
    print("\nExample 2: Simple fixed SL/TP")
    result2 = calculator.calculate_simple(entry_price=50.0, sl_pct=3.0, tp_pct=6.0)
    print(f"  Entry: $50.00")
    print(f"  SL: ${result2.stop_loss} (-{result2.sl_pct}%)")
    print(f"  TP: ${result2.take_profit} (+{result2.tp_pct}%)")
    print(f"  R:R: {result2.risk_reward:.2f}")
