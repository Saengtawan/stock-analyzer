"""
Engine Time Utilities - Extracted from auto_trading_engine.py (Phase 2)
========================================================================

Functions for market hours, timezone, and time-based checks.
These are standalone functions to avoid tight coupling with engine instance.
"""

from datetime import datetime
from typing import Optional
import pytz

# Default market hours (ET)
DEFAULT_MARKET_OPEN_HOUR = 9
DEFAULT_MARKET_OPEN_MINUTE = 30
DEFAULT_MARKET_CLOSE_HOUR = 16
DEFAULT_MARKET_CLOSE_MINUTE = 0
DEFAULT_PRE_CLOSE_MINUTE = 50

# Timezone
ET_TZ = pytz.timezone('America/New_York')


def get_et_time() -> datetime:
    """Get current time in Eastern Time"""
    return datetime.now(ET_TZ)


def is_market_hours(
    open_hour: int = DEFAULT_MARKET_OPEN_HOUR,
    open_minute: int = DEFAULT_MARKET_OPEN_MINUTE,
    close_hour: int = DEFAULT_MARKET_CLOSE_HOUR,
    close_minute: int = DEFAULT_MARKET_CLOSE_MINUTE,
) -> bool:
    """
    Check if current time is within market hours.

    Args:
        open_hour: Market open hour (default 9)
        open_minute: Market open minute (default 30)
        close_hour: Market close hour (default 16)
        close_minute: Market close minute (default 0)

    Returns:
        True if within market hours
    """
    now = get_et_time()
    market_open = now.replace(hour=open_hour, minute=open_minute, second=0, microsecond=0)
    market_close = now.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)
    return market_open <= now <= market_close


def is_pre_close(
    pre_close_minute: int = DEFAULT_PRE_CLOSE_MINUTE,
    close_hour: int = DEFAULT_MARKET_CLOSE_HOUR,
    close_minute: int = DEFAULT_MARKET_CLOSE_MINUTE,
) -> bool:
    """
    Check if in pre-close period (default 15:50-16:00 ET).

    Args:
        pre_close_minute: Minute to start pre-close (default 50)
        close_hour: Market close hour (default 16)
        close_minute: Market close minute (default 0)

    Returns:
        True if in pre-close period
    """
    now = get_et_time()
    pre_close = now.replace(hour=15, minute=pre_close_minute, second=0, microsecond=0)
    market_close = now.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)
    return pre_close <= now <= market_close


def is_weekend() -> bool:
    """Check if today is a weekend (Saturday=5, Sunday=6)"""
    return get_et_time().weekday() >= 5


def get_market_open_time() -> datetime:
    """Get today's market open time in ET"""
    now = get_et_time()
    return now.replace(
        hour=DEFAULT_MARKET_OPEN_HOUR,
        minute=DEFAULT_MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0
    )


def get_market_close_time() -> datetime:
    """Get today's market close time in ET"""
    now = get_et_time()
    return now.replace(
        hour=DEFAULT_MARKET_CLOSE_HOUR,
        minute=DEFAULT_MARKET_CLOSE_MINUTE,
        second=0,
        microsecond=0
    )


def minutes_since_market_open() -> float:
    """Get minutes since market open (negative if before open)"""
    now = get_et_time()
    market_open = get_market_open_time()
    delta = now - market_open
    return delta.total_seconds() / 60


def minutes_until_market_close() -> float:
    """Get minutes until market close (negative if after close)"""
    now = get_et_time()
    market_close = get_market_close_time()
    delta = market_close - now
    return delta.total_seconds() / 60


def is_late_start(max_minutes_after_open: int = 15) -> bool:
    """
    Check if current time is too late after market open.

    Args:
        max_minutes_after_open: Maximum minutes after open to consider "on time"

    Returns:
        True if late start (past the window)
    """
    minutes = minutes_since_market_open()
    return minutes > max_minutes_after_open


def format_et_time(dt: Optional[datetime] = None, fmt: str = "%H:%M:%S") -> str:
    """Format datetime in ET timezone"""
    if dt is None:
        dt = get_et_time()
    elif dt.tzinfo is None:
        dt = ET_TZ.localize(dt)
    return dt.strftime(fmt)
