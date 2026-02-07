"""
Engine Regime Checker - Extracted from auto_trading_engine.py (Phase 4)
========================================================================

Utilities for market regime detection:
- VIX checking
- Bear/Bull mode detection
- Sector regime filtering

These are utility functions that support the engine's regime checking.
The actual regime methods remain in the engine due to tight coupling.
"""

from typing import Tuple, Optional, Dict, List
from datetime import datetime, timedelta
from loguru import logger


# VIX thresholds
DEFAULT_VIX_MAX = 30.0       # Block trades when VIX >= 30
DEFAULT_VIX_CAUTION = 25.0   # Reduce position size when VIX > 25
DEFAULT_VIX_EXTREME = 40.0   # Emergency mode when VIX > 40


def check_vix_threshold(vix_value: float, max_vix: float = DEFAULT_VIX_MAX) -> Tuple[bool, str]:
    """
    Check if VIX is below threshold for trading.

    Args:
        vix_value: Current VIX value
        max_vix: Maximum VIX for trading (default 30)

    Returns:
        (allowed: bool, reason: str)
    """
    if vix_value >= max_vix:
        return False, f"VIX {vix_value:.1f} >= {max_vix} (blocked)"
    return True, f"VIX {vix_value:.1f} < {max_vix} (OK)"


def get_vix_risk_level(vix_value: float) -> str:
    """
    Get risk level based on VIX.

    Returns:
        'low', 'medium', 'high', or 'extreme'
    """
    if vix_value < 15:
        return 'low'
    elif vix_value < DEFAULT_VIX_CAUTION:
        return 'medium'
    elif vix_value < DEFAULT_VIX_EXTREME:
        return 'high'
    else:
        return 'extreme'


def calculate_vix_position_factor(vix_value: float) -> float:
    """
    Calculate position size factor based on VIX.

    Lower VIX = larger positions (up to 1.0)
    Higher VIX = smaller positions

    Returns:
        Factor between 0.5 and 1.0
    """
    if vix_value <= 15:
        return 1.0
    elif vix_value <= 20:
        return 0.9
    elif vix_value <= 25:
        return 0.75
    elif vix_value < 30:
        return 0.6
    else:
        return 0.5  # Minimum factor


def is_bear_mode(
    spy_price: float,
    spy_sma20: float,
    spy_sma50: Optional[float] = None,
) -> Tuple[bool, str]:
    """
    Determine if market is in bear mode.

    Bear mode triggers when SPY < SMA20.

    Args:
        spy_price: Current SPY price
        spy_sma20: SPY 20-day SMA
        spy_sma50: Optional SPY 50-day SMA

    Returns:
        (is_bear: bool, reason: str)
    """
    if spy_price < spy_sma20:
        pct_below = ((spy_sma20 - spy_price) / spy_sma20) * 100
        return True, f"SPY ${spy_price:.2f} < SMA20 ${spy_sma20:.2f} ({pct_below:.1f}% below)"

    return False, f"SPY ${spy_price:.2f} > SMA20 ${spy_sma20:.2f} (BULL)"


def filter_sectors_by_regime(
    sector_regimes: Dict[str, str],
    is_bear: bool,
    bear_allowed: List[str] = None,
    bull_blocked: List[str] = None,
) -> Dict[str, bool]:
    """
    Filter sectors based on market regime.

    In BEAR mode: Only allow specific sectors (defensive)
    In BULL mode: Block certain sectors (if configured)

    Args:
        sector_regimes: Dict mapping sector -> regime ('BULL', 'BEAR', etc.)
        is_bear: True if market is in bear mode
        bear_allowed: Sectors allowed in bear mode
        bull_blocked: Sectors blocked in bull mode

    Returns:
        Dict mapping sector -> allowed (bool)
    """
    bear_allowed = bear_allowed or ['Consumer Defensive', 'Healthcare', 'Utilities']
    bull_blocked = bull_blocked or []

    result = {}
    for sector, regime in sector_regimes.items():
        if is_bear:
            result[sector] = sector in bear_allowed
        else:
            result[sector] = sector not in bull_blocked

    return result


def calculate_regime_score(
    return_1d: float,
    return_5d: float,
    return_20d: float,
    weight_1d: float = 0.45,
    weight_5d: float = 0.35,
    weight_20d: float = 0.20,
) -> float:
    """
    Calculate composite regime score.

    v6.0: Weighted average of returns at different timeframes.

    Args:
        return_1d: 1-day return %
        return_5d: 5-day return %
        return_20d: 20-day return %
        weight_1d: Weight for 1d (default 0.45)
        weight_5d: Weight for 5d (default 0.35)
        weight_20d: Weight for 20d (default 0.20)

    Returns:
        Composite score
    """
    return (return_1d * weight_1d) + (return_5d * weight_5d) + (return_20d * weight_20d)


def determine_regime_from_score(score: float) -> str:
    """
    Determine regime category from composite score.

    Thresholds:
        > 4.0: STRONG BULL
        > 1.5: BULL
        > -2.0: SIDEWAYS
        > -4.0: BEAR
        <= -4.0: STRONG BEAR

    Args:
        score: Composite regime score

    Returns:
        Regime string
    """
    if score > 4.0:
        return 'STRONG BULL'
    elif score > 1.5:
        return 'BULL'
    elif score > -2.0:
        return 'SIDEWAYS'
    elif score > -4.0:
        return 'BEAR'
    else:
        return 'STRONG BEAR'


def is_regime_allowed(regime: str, allow_sideways: bool = True) -> bool:
    """
    Check if regime allows trading.

    Args:
        regime: Regime string from determine_regime_from_score
        allow_sideways: Whether to allow trading in SIDEWAYS

    Returns:
        True if trading allowed
    """
    allowed_regimes = ['STRONG BULL', 'BULL']
    if allow_sideways:
        allowed_regimes.append('SIDEWAYS')

    return regime in allowed_regimes
