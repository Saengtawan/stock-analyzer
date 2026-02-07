"""
Engine Order Executor - Extracted from auto_trading_engine.py (Phase 9)
========================================================================

Utility functions for order execution:
- Order parameter calculation
- Position size calculation
- Order validation
- Execution helpers

These are standalone utilities for order-related operations.
The actual order execution remains in the engine with the Alpaca client.
"""

from typing import Tuple, Dict, Any, Optional, List
from datetime import datetime
from loguru import logger


# Default order parameters
DEFAULT_POSITION_SIZE_PCT = 35.0     # Base position size as % of account
DEFAULT_MIN_POSITION_SIZE = 100.0    # Minimum position $ amount
DEFAULT_MAX_POSITION_SIZE = 10000.0  # Maximum position $ amount


def calculate_order_qty(
    account_value: float,
    entry_price: float,
    position_size_pct: float = DEFAULT_POSITION_SIZE_PCT,
    min_amount: float = DEFAULT_MIN_POSITION_SIZE,
    max_amount: float = DEFAULT_MAX_POSITION_SIZE,
) -> Tuple[int, float, str]:
    """
    Calculate order quantity based on account size and position %.

    Args:
        account_value: Total account value
        entry_price: Entry price per share
        position_size_pct: Target position as % of account
        min_amount: Minimum dollar amount
        max_amount: Maximum dollar amount

    Returns:
        (qty: int, dollar_amount: float, reason: str)
    """
    if entry_price <= 0:
        return 0, 0.0, "Invalid entry price"

    # Calculate base amount
    base_amount = account_value * (position_size_pct / 100)

    # Apply limits
    dollar_amount = max(min_amount, min(base_amount, max_amount))

    # Calculate shares
    qty = int(dollar_amount / entry_price)

    if qty < 1:
        return 0, 0.0, f"Qty < 1 (${dollar_amount:.0f} / ${entry_price:.2f})"

    actual_amount = qty * entry_price
    return qty, actual_amount, f"{qty} shares @ ${entry_price:.2f} = ${actual_amount:.0f}"


def validate_order_params(
    symbol: str,
    qty: int,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
) -> Tuple[bool, List[str]]:
    """
    Validate order parameters before submission.

    Args:
        symbol: Stock symbol
        qty: Order quantity
        entry_price: Entry price
        stop_loss: Stop loss price
        take_profit: Take profit price

    Returns:
        (valid: bool, errors: List[str])
    """
    errors = []

    if not symbol or len(symbol) > 10:
        errors.append(f"Invalid symbol: {symbol}")

    if qty < 1:
        errors.append(f"Invalid qty: {qty}")

    if entry_price <= 0:
        errors.append(f"Invalid entry price: {entry_price}")

    if stop_loss <= 0 or stop_loss >= entry_price:
        errors.append(f"Invalid stop loss: {stop_loss} (must be < {entry_price})")

    if take_profit <= entry_price:
        errors.append(f"Invalid take profit: {take_profit} (must be > {entry_price})")

    return len(errors) == 0, errors


def calculate_sl_tp_prices(
    entry_price: float,
    atr_pct: float,
    sl_multiplier: float = 1.5,
    tp_multiplier: float = 2.0,
    min_sl_pct: float = 2.0,
    max_sl_pct: float = 5.0,
    min_tp_pct: float = 3.0,
    max_tp_pct: float = 10.0,
) -> Dict[str, float]:
    """
    Calculate stop loss and take profit prices based on ATR.

    Args:
        entry_price: Entry price
        atr_pct: ATR as % of price
        sl_multiplier: ATR multiplier for SL
        tp_multiplier: Risk/reward multiplier for TP
        min_sl_pct: Minimum SL %
        max_sl_pct: Maximum SL %
        min_tp_pct: Minimum TP %
        max_tp_pct: Maximum TP %

    Returns:
        Dict with sl_price, sl_pct, tp_price, tp_pct
    """
    # Calculate SL %
    sl_pct = atr_pct * sl_multiplier
    sl_pct = max(min_sl_pct, min(sl_pct, max_sl_pct))
    sl_price = entry_price * (1 - sl_pct / 100)

    # Calculate TP % (based on R:R)
    tp_pct = sl_pct * tp_multiplier
    tp_pct = max(min_tp_pct, min(tp_pct, max_tp_pct))
    tp_price = entry_price * (1 + tp_pct / 100)

    return {
        'sl_price': round(sl_price, 2),
        'sl_pct': round(sl_pct, 2),
        'tp_price': round(tp_price, 2),
        'tp_pct': round(tp_pct, 2),
    }


def calculate_conviction_size(
    base_size_pct: float,
    signal_score: float,
    mode: str = 'NORMAL',
    vix: float = 20.0,
) -> Tuple[float, str]:
    """
    Calculate conviction-adjusted position size.

    Higher score = larger position (within limits)
    LOW_RISK mode = smaller position
    High VIX = smaller position

    Args:
        base_size_pct: Base position size %
        signal_score: Signal score (0-100)
        mode: Trading mode ('NORMAL', 'LOW_RISK', 'BEAR')
        vix: Current VIX value

    Returns:
        (adjusted_size_pct: float, reason: str)
    """
    # Score factor (90-100 score = 1.0-1.2, below 90 = 0.8-1.0)
    if signal_score >= 95:
        score_factor = 1.2
    elif signal_score >= 90:
        score_factor = 1.0
    elif signal_score >= 85:
        score_factor = 0.9
    else:
        score_factor = 0.8

    # Mode factor
    mode_factors = {
        'NORMAL': 1.0,
        'LOW_RISK': 0.5,
        'BEAR': 0.6,
        'BEAR+LOW_RISK': 0.4,
    }
    mode_factor = mode_factors.get(mode, 1.0)

    # VIX factor
    if vix < 15:
        vix_factor = 1.0
    elif vix < 20:
        vix_factor = 0.9
    elif vix < 25:
        vix_factor = 0.75
    else:
        vix_factor = 0.6

    adjusted = base_size_pct * score_factor * mode_factor * vix_factor

    reason = f"score {score_factor:.1f}x, mode {mode_factor:.1f}x, vix {vix_factor:.1f}x"
    return round(adjusted, 1), reason


def format_order_summary(
    symbol: str,
    action: str,
    qty: int,
    price: float,
    stop_loss: float = None,
    take_profit: float = None,
    reason: str = None,
) -> str:
    """
    Format order summary for logging.

    Returns:
        Formatted string
    """
    sl_str = f" SL ${stop_loss:.2f}" if stop_loss else ""
    tp_str = f" TP ${take_profit:.2f}" if take_profit else ""
    reason_str = f" ({reason})" if reason else ""

    return f"{action} {qty} {symbol} @ ${price:.2f}{sl_str}{tp_str}{reason_str}"


def should_use_day_trade(
    days_held: int,
    current_price: float,
    entry_price: float,
    pdt_budget: int,
    pdt_tp_threshold: float = 4.0,
) -> Tuple[bool, str]:
    """
    Determine if day trade (Day 0 exit) should be used.

    Day trade allowed if:
    1. days_held == 0 AND
    2. (gain >= threshold OR pdt_budget > 0)

    Args:
        days_held: Days since entry
        current_price: Current price
        entry_price: Entry price
        pdt_budget: Remaining PDT budget
        pdt_tp_threshold: Gain % threshold for Day 0 exit

    Returns:
        (use_day_trade: bool, reason: str)
    """
    if days_held > 0:
        return False, "Not Day 0"

    gain_pct = ((current_price - entry_price) / entry_price) * 100

    if gain_pct >= pdt_tp_threshold:
        return True, f"Day 0 exit: gain {gain_pct:.1f}% >= {pdt_tp_threshold}%"

    if pdt_budget > 0:
        return True, f"Day 0 exit: PDT budget = {pdt_budget}"

    return False, f"Day 0 blocked: gain {gain_pct:.1f}% < {pdt_tp_threshold}% and PDT=0"


def prepare_bracket_order(
    symbol: str,
    qty: int,
    entry_price: float,
    sl_price: float,
    tp_price: float,
) -> Dict[str, Any]:
    """
    Prepare bracket order parameters.

    Bracket order = Entry + SL + TP in one order.

    Returns:
        Dict with order parameters
    """
    return {
        'symbol': symbol,
        'side': 'buy',
        'type': 'limit',
        'limit_price': round(entry_price, 2),
        'qty': qty,
        'time_in_force': 'day',
        'order_class': 'bracket',
        'stop_loss': {
            'stop_price': round(sl_price, 2),
        },
        'take_profit': {
            'limit_price': round(tp_price, 2),
        },
    }


def prepare_trailing_stop_order(
    symbol: str,
    qty: int,
    trail_percent: float,
) -> Dict[str, Any]:
    """
    Prepare trailing stop order parameters.

    Returns:
        Dict with order parameters
    """
    return {
        'symbol': symbol,
        'side': 'sell',
        'type': 'trailing_stop',
        'trail_percent': round(trail_percent, 2),
        'qty': qty,
        'time_in_force': 'gtc',
    }
