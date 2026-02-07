"""
Engine Risk Manager - Extracted from auto_trading_engine.py (Phase 6)
======================================================================

Utility functions for risk management:
- Daily loss limit checking
- Weekly loss limit checking
- Consecutive loss cooldown
- Position sizing calculations

These are standalone risk functions that support the engine.
"""

from typing import Tuple, Dict, Any, List
from datetime import datetime, date, timedelta
from loguru import logger


# Default risk limits
DEFAULT_DAILY_LOSS_LIMIT = -3.0      # Max daily loss %
DEFAULT_WEEKLY_LOSS_LIMIT = -5.0     # Max weekly loss %
DEFAULT_CONSECUTIVE_LOSSES = 3       # Max consecutive losses before cooldown
DEFAULT_COOLDOWN_HOURS = 4           # Hours to wait after consecutive losses


def check_daily_loss_limit(
    daily_pnl_pct: float,
    limit: float = DEFAULT_DAILY_LOSS_LIMIT,
) -> Tuple[bool, str]:
    """
    Check if daily loss limit has been exceeded.

    Args:
        daily_pnl_pct: Today's P&L as percentage
        limit: Maximum loss % (negative, default -3%)

    Returns:
        (can_trade: bool, reason: str)
    """
    if daily_pnl_pct <= limit:
        return False, f"Daily loss {daily_pnl_pct:.1f}% exceeds limit {limit}%"
    return True, f"Daily P&L {daily_pnl_pct:.1f}% within limit"


def check_weekly_loss_limit(
    weekly_pnl_pct: float,
    limit: float = DEFAULT_WEEKLY_LOSS_LIMIT,
) -> Tuple[bool, str]:
    """
    Check if weekly loss limit has been exceeded.

    Args:
        weekly_pnl_pct: This week's P&L as percentage
        limit: Maximum loss % (negative, default -5%)

    Returns:
        (can_trade: bool, reason: str)
    """
    if weekly_pnl_pct <= limit:
        return False, f"Weekly loss {weekly_pnl_pct:.1f}% exceeds limit {limit}%"
    return True, f"Weekly P&L {weekly_pnl_pct:.1f}% within limit"


def check_consecutive_loss_cooldown(
    consecutive_losses: int,
    last_loss_time: datetime = None,
    max_losses: int = DEFAULT_CONSECUTIVE_LOSSES,
    cooldown_hours: int = DEFAULT_COOLDOWN_HOURS,
) -> Tuple[bool, str]:
    """
    Check if in cooldown after consecutive losses.

    Args:
        consecutive_losses: Number of consecutive losing trades
        last_loss_time: Time of last losing trade
        max_losses: Number of losses before cooldown triggers
        cooldown_hours: Hours to wait

    Returns:
        (can_trade: bool, reason: str)
    """
    if consecutive_losses < max_losses:
        return True, f"{consecutive_losses} consecutive losses (< {max_losses})"

    if last_loss_time is None:
        return False, f"{consecutive_losses} consecutive losses - in cooldown"

    hours_since = (datetime.now() - last_loss_time).total_seconds() / 3600

    if hours_since < cooldown_hours:
        remaining = cooldown_hours - hours_since
        return False, f"Cooldown: {remaining:.1f}h remaining ({consecutive_losses} losses)"

    return True, f"Cooldown expired ({hours_since:.1f}h since last loss)"


def calculate_position_size(
    account_value: float,
    position_pct: float,
    entry_price: float,
    max_shares: int = 1000,
    min_shares: int = 1,
) -> Tuple[int, float]:
    """
    Calculate position size in shares.

    Args:
        account_value: Total account value
        position_pct: Target position size as % of account
        entry_price: Entry price per share
        max_shares: Maximum shares per position
        min_shares: Minimum shares per position

    Returns:
        (shares: int, dollar_amount: float)
    """
    dollar_amount = account_value * (position_pct / 100)
    shares = int(dollar_amount / entry_price)

    # Apply limits
    shares = max(min_shares, min(shares, max_shares))

    return shares, shares * entry_price


def calculate_risk_adjusted_size(
    base_size_pct: float,
    vix_factor: float = 1.0,
    mode_factor: float = 1.0,
    conviction_factor: float = 1.0,
) -> float:
    """
    Calculate risk-adjusted position size.

    Args:
        base_size_pct: Base position size %
        vix_factor: VIX adjustment (0.5-1.0)
        mode_factor: Mode adjustment (e.g., 0.5 for LOW_RISK)
        conviction_factor: Signal conviction (0.5-1.5)

    Returns:
        Adjusted position size %
    """
    adjusted = base_size_pct * vix_factor * mode_factor * conviction_factor
    return max(adjusted, base_size_pct * 0.25)  # Minimum 25% of base


def calculate_stop_loss(
    entry_price: float,
    atr_pct: float,
    atr_multiplier: float = 1.5,
    min_sl_pct: float = 2.0,
    max_sl_pct: float = 5.0,
) -> Tuple[float, float]:
    """
    Calculate ATR-based stop loss.

    Args:
        entry_price: Entry price
        atr_pct: ATR as % of price
        atr_multiplier: ATR multiplier for SL distance
        min_sl_pct: Minimum stop loss %
        max_sl_pct: Maximum stop loss %

    Returns:
        (stop_price: float, sl_pct: float)
    """
    sl_pct = atr_pct * atr_multiplier
    sl_pct = max(min_sl_pct, min(sl_pct, max_sl_pct))

    stop_price = entry_price * (1 - sl_pct / 100)
    return stop_price, sl_pct


def calculate_take_profit(
    entry_price: float,
    sl_pct: float,
    risk_reward_ratio: float = 2.0,
    min_tp_pct: float = 3.0,
    max_tp_pct: float = 10.0,
) -> Tuple[float, float]:
    """
    Calculate take profit based on risk/reward.

    Args:
        entry_price: Entry price
        sl_pct: Stop loss %
        risk_reward_ratio: Target R:R ratio
        min_tp_pct: Minimum take profit %
        max_tp_pct: Maximum take profit %

    Returns:
        (take_profit_price: float, tp_pct: float)
    """
    tp_pct = sl_pct * risk_reward_ratio
    tp_pct = max(min_tp_pct, min(tp_pct, max_tp_pct))

    take_profit_price = entry_price * (1 + tp_pct / 100)
    return take_profit_price, tp_pct


def check_max_drawdown(
    peak_value: float,
    current_value: float,
    max_drawdown_pct: float = 10.0,
) -> Tuple[bool, float, str]:
    """
    Check if maximum drawdown has been exceeded.

    Args:
        peak_value: Peak account value
        current_value: Current account value
        max_drawdown_pct: Maximum allowed drawdown %

    Returns:
        (ok: bool, drawdown_pct: float, reason: str)
    """
    if peak_value <= 0:
        return True, 0.0, "No peak value"

    drawdown_pct = ((peak_value - current_value) / peak_value) * 100

    if drawdown_pct >= max_drawdown_pct:
        return False, drawdown_pct, f"Drawdown {drawdown_pct:.1f}% >= {max_drawdown_pct}%"

    return True, drawdown_pct, f"Drawdown {drawdown_pct:.1f}% < {max_drawdown_pct}%"


def get_risk_summary(
    daily_pnl: float,
    weekly_pnl: float,
    consecutive_losses: int,
    vix: float,
    drawdown_pct: float,
) -> Dict[str, Any]:
    """
    Get summary of current risk status.

    Returns:
        Dict with risk metrics and overall status
    """
    daily_ok, _ = check_daily_loss_limit(daily_pnl)
    weekly_ok, _ = check_weekly_loss_limit(weekly_pnl)
    cooldown_ok, _ = check_consecutive_loss_cooldown(consecutive_losses)
    dd_ok, _, _ = check_max_drawdown(100, 100 - drawdown_pct)

    risk_level = 'LOW'
    if not all([daily_ok, weekly_ok, cooldown_ok, dd_ok]):
        risk_level = 'BLOCKED'
    elif vix > 25 or drawdown_pct > 5:
        risk_level = 'HIGH'
    elif vix > 20 or consecutive_losses > 0:
        risk_level = 'MEDIUM'

    return {
        'daily_pnl': daily_pnl,
        'weekly_pnl': weekly_pnl,
        'consecutive_losses': consecutive_losses,
        'vix': vix,
        'drawdown_pct': drawdown_pct,
        'risk_level': risk_level,
        'can_trade': all([daily_ok, weekly_ok, cooldown_ok, dd_ok]),
        'checks': {
            'daily': daily_ok,
            'weekly': weekly_ok,
            'cooldown': cooldown_ok,
            'drawdown': dd_ok,
        }
    }
