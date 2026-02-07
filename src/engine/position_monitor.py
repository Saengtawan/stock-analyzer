"""
Engine Position Monitor - Extracted from auto_trading_engine.py (Phase 8)
==========================================================================

Utility functions for position monitoring:
- Trailing stop calculations
- Take profit checking
- Days held tracking
- Position health checks

These are standalone monitoring utilities that support the engine.
"""

from typing import Tuple, Dict, Any, Optional, List
from datetime import datetime, timedelta
from loguru import logger


# Default trailing stop parameters
DEFAULT_TRAIL_ACTIVATION_PCT = 2.0   # Activate trailing at +2%
DEFAULT_TRAIL_LOCK_PCT = 60.0        # Lock 60% of gains


def update_peak_price(
    current_price: float,
    peak_price: float,
) -> Tuple[float, bool]:
    """
    Update peak price if current price is higher.

    Args:
        current_price: Current market price
        peak_price: Previous peak price

    Returns:
        (new_peak: float, was_updated: bool)
    """
    if current_price > peak_price:
        return current_price, True
    return peak_price, False


def update_trough_price(
    current_price: float,
    trough_price: float,
) -> Tuple[float, bool]:
    """
    Update trough (lowest) price if current is lower.

    Args:
        current_price: Current market price
        trough_price: Previous trough price

    Returns:
        (new_trough: float, was_updated: bool)
    """
    if trough_price <= 0 or current_price < trough_price:
        return current_price, True
    return trough_price, False


def calculate_trailing_stop(
    entry_price: float,
    peak_price: float,
    trail_activation_pct: float = DEFAULT_TRAIL_ACTIVATION_PCT,
    trail_lock_pct: float = DEFAULT_TRAIL_LOCK_PCT,
    min_sl_pct: float = 2.0,
) -> Tuple[float, bool, str]:
    """
    Calculate trailing stop price based on peak.

    Trailing activates when gain >= activation_pct.
    Locks in lock_pct of gains from peak.

    Args:
        entry_price: Original entry price
        peak_price: Highest price since entry
        trail_activation_pct: Gain % to activate trailing
        trail_lock_pct: % of gains to lock in
        min_sl_pct: Minimum stop loss %

    Returns:
        (stop_price: float, is_active: bool, reason: str)
    """
    gain_pct = ((peak_price - entry_price) / entry_price) * 100

    if gain_pct < trail_activation_pct:
        # Not activated yet, use minimum SL
        stop_price = entry_price * (1 - min_sl_pct / 100)
        return stop_price, False, f"Trailing not active (gain {gain_pct:.1f}% < {trail_activation_pct}%)"

    # Trailing active - lock in % of gains
    gain_amount = peak_price - entry_price
    locked_gain = gain_amount * (trail_lock_pct / 100)
    stop_price = entry_price + locked_gain

    # Ensure stop is at least at entry (breakeven)
    stop_price = max(stop_price, entry_price)

    locked_pct = ((stop_price - entry_price) / entry_price) * 100
    return stop_price, True, f"Trailing active: locking {locked_pct:.1f}% of {gain_pct:.1f}% gain"


def should_update_stop_order(
    current_stop: float,
    new_stop: float,
    min_update_pct: float = 0.1,
) -> Tuple[bool, str]:
    """
    Determine if stop order should be updated.

    Only update if new stop is significantly higher.

    Args:
        current_stop: Current stop price
        new_stop: Calculated new stop price
        min_update_pct: Minimum change % to update

    Returns:
        (should_update: bool, reason: str)
    """
    if current_stop <= 0:
        return True, "No current stop"

    change_pct = ((new_stop - current_stop) / current_stop) * 100

    if new_stop <= current_stop:
        return False, f"New stop {new_stop:.2f} <= current {current_stop:.2f}"

    if change_pct < min_update_pct:
        return False, f"Change {change_pct:.2f}% < {min_update_pct}%"

    return True, f"Update stop: {current_stop:.2f} -> {new_stop:.2f} (+{change_pct:.2f}%)"


def check_take_profit(
    current_price: float,
    entry_price: float,
    tp_price: float,
) -> Tuple[bool, float, str]:
    """
    Check if take profit has been hit.

    Args:
        current_price: Current market price
        entry_price: Entry price
        tp_price: Take profit price

    Returns:
        (hit: bool, gain_pct: float, reason: str)
    """
    gain_pct = ((current_price - entry_price) / entry_price) * 100

    if current_price >= tp_price:
        return True, gain_pct, f"TP hit at +{gain_pct:.1f}%"

    remaining_pct = ((tp_price - current_price) / current_price) * 100
    return False, gain_pct, f"TP not hit ({remaining_pct:.1f}% to go)"


def check_stop_loss(
    current_price: float,
    stop_price: float,
    entry_price: float,
) -> Tuple[bool, float, str]:
    """
    Check if stop loss has been hit.

    Args:
        current_price: Current market price
        stop_price: Stop loss price
        entry_price: Entry price

    Returns:
        (hit: bool, loss_pct: float, reason: str)
    """
    pnl_pct = ((current_price - entry_price) / entry_price) * 100

    if current_price <= stop_price:
        return True, pnl_pct, f"SL hit at {pnl_pct:.1f}%"

    buffer_pct = ((current_price - stop_price) / stop_price) * 100
    return False, pnl_pct, f"SL not hit ({buffer_pct:.1f}% buffer)"


def calculate_days_held(
    entry_time: datetime,
    current_time: datetime = None,
) -> int:
    """
    Calculate trading days held (simplified as calendar days).

    Args:
        entry_time: Position entry time
        current_time: Current time (default: now)

    Returns:
        Number of days held
    """
    current_time = current_time or datetime.now()
    delta = current_time.date() - entry_time.date()
    return delta.days


def check_pdt_day_trade(
    days_held: int,
    current_price: float,
    entry_price: float,
    pdt_tp_threshold: float = 4.0,
    pdt_budget: int = 0,
) -> Tuple[bool, str]:
    """
    Check if day trade (Day 0 sell) is allowed under PDT rules.

    Day 0 selling only allowed if:
    1. Gain >= threshold OR
    2. PDT budget > 0

    Args:
        days_held: Days since entry
        current_price: Current price
        entry_price: Entry price
        pdt_tp_threshold: Minimum gain % for Day 0 sell
        pdt_budget: Remaining PDT day trades

    Returns:
        (can_sell: bool, reason: str)
    """
    if days_held > 0:
        return True, "Not Day 0"

    gain_pct = ((current_price - entry_price) / entry_price) * 100

    if gain_pct >= pdt_tp_threshold:
        return True, f"Day 0 OK: gain {gain_pct:.1f}% >= {pdt_tp_threshold}%"

    if pdt_budget > 0:
        return True, f"Day 0 OK: PDT budget = {pdt_budget}"

    return False, f"Day 0 blocked: gain {gain_pct:.1f}% < {pdt_tp_threshold}% and PDT=0"


def get_position_health(
    current_price: float,
    entry_price: float,
    peak_price: float,
    stop_price: float,
    tp_price: float,
    days_held: int,
) -> Dict[str, Any]:
    """
    Get comprehensive position health status.

    Returns:
        Dict with health metrics
    """
    pnl_pct = ((current_price - entry_price) / entry_price) * 100
    from_peak_pct = ((current_price - peak_price) / peak_price) * 100 if peak_price > 0 else 0
    to_tp_pct = ((tp_price - current_price) / current_price) * 100 if tp_price > 0 else 0
    to_sl_pct = ((current_price - stop_price) / stop_price) * 100 if stop_price > 0 else 0

    # Determine health status
    if pnl_pct >= 3.0:
        status = 'excellent'
    elif pnl_pct >= 0:
        status = 'good'
    elif pnl_pct >= -2.0:
        status = 'caution'
    else:
        status = 'danger'

    return {
        'current_price': current_price,
        'entry_price': entry_price,
        'peak_price': peak_price,
        'pnl_pct': round(pnl_pct, 2),
        'from_peak_pct': round(from_peak_pct, 2),
        'to_tp_pct': round(to_tp_pct, 2),
        'to_sl_pct': round(to_sl_pct, 2),
        'days_held': days_held,
        'status': status,
    }


def should_close_position(
    position_health: Dict[str, Any],
    force_reasons: List[str] = None,
) -> Tuple[bool, str]:
    """
    Determine if position should be closed.

    Args:
        position_health: Health dict from get_position_health
        force_reasons: List of reasons that force close

    Returns:
        (should_close: bool, reason: str)
    """
    force_reasons = force_reasons or []

    # Check force reasons
    for reason in force_reasons:
        return True, reason

    # Check SL hit
    if position_health.get('to_sl_pct', float('inf')) <= 0:
        return True, "Stop loss hit"

    # Check TP hit
    if position_health.get('to_tp_pct', float('inf')) <= 0:
        return True, "Take profit hit"

    return False, "Hold position"
