"""
Market Hours Constants - Single Source of Truth
================================================

This module provides market hours constants and helper functions.
All components should import from here instead of hardcoding values.

Usage:
    from src.utils.market_hours import MARKET_OPEN_HOUR, MARKET_CLOSE_HOUR
    from src.utils.market_hours import is_market_open, get_market_status
"""

import pytz
from datetime import datetime, time

# =============================================================================
# MARKET HOURS CONSTANTS (US/Eastern)
# =============================================================================

MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
PRE_CLOSE_HOUR = 15
PRE_CLOSE_MINUTE = 50

# Derived constants
MARKET_OPEN_TIME = time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)  # 09:30
MARKET_CLOSE_TIME = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)  # 16:00
PRE_CLOSE_TIME = time(PRE_CLOSE_HOUR, PRE_CLOSE_MINUTE)  # 15:50

# Minutes from midnight (for session timeline)
MARKET_OPEN_MINUTES = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE  # 570
MARKET_CLOSE_MINUTES = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE  # 960
PRE_CLOSE_MINUTES = PRE_CLOSE_HOUR * 60 + PRE_CLOSE_MINUTE  # 950

# Timezone
MARKET_TIMEZONE = pytz.timezone('US/Eastern')


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_et_time() -> datetime:
    """Get current time in US/Eastern timezone."""
    return datetime.now(MARKET_TIMEZONE)


def is_market_hours(dt: datetime = None) -> bool:
    """
    Check if given time is during market hours (09:30 - 16:00 ET).

    Args:
        dt: Datetime to check (default: now in ET)

    Returns:
        True if during market hours, False otherwise
    """
    if dt is None:
        dt = get_et_time()

    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = MARKET_TIMEZONE.localize(dt)
    else:
        dt = dt.astimezone(MARKET_TIMEZONE)

    current_time = dt.time()
    return MARKET_OPEN_TIME <= current_time < MARKET_CLOSE_TIME


def is_pre_close(dt: datetime = None) -> bool:
    """
    Check if given time is in pre-close period (15:50 - 16:00 ET).

    Args:
        dt: Datetime to check (default: now in ET)

    Returns:
        True if in pre-close period, False otherwise
    """
    if dt is None:
        dt = get_et_time()

    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = MARKET_TIMEZONE.localize(dt)
    else:
        dt = dt.astimezone(MARKET_TIMEZONE)

    current_time = dt.time()
    return PRE_CLOSE_TIME <= current_time < MARKET_CLOSE_TIME


def minutes_to_market_open(dt: datetime = None) -> int:
    """
    Get minutes until market opens.

    Args:
        dt: Datetime to check (default: now in ET)

    Returns:
        Minutes until market open (negative if market already open)
    """
    if dt is None:
        dt = get_et_time()

    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = MARKET_TIMEZONE.localize(dt)
    else:
        dt = dt.astimezone(MARKET_TIMEZONE)

    current_minutes = dt.hour * 60 + dt.minute
    return MARKET_OPEN_MINUTES - current_minutes


def minutes_to_market_close(dt: datetime = None) -> int:
    """
    Get minutes until market closes.

    Args:
        dt: Datetime to check (default: now in ET)

    Returns:
        Minutes until market close (negative if market already closed)
    """
    if dt is None:
        dt = get_et_time()

    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = MARKET_TIMEZONE.localize(dt)
    else:
        dt = dt.astimezone(MARKET_TIMEZONE)

    current_minutes = dt.hour * 60 + dt.minute
    return MARKET_CLOSE_MINUTES - current_minutes


def get_market_status(dt: datetime = None) -> dict:
    """
    Get comprehensive market status.

    Args:
        dt: Datetime to check (default: now in ET)

    Returns:
        Dict with: is_open, is_pre_close, minutes_to_open, minutes_to_close
    """
    if dt is None:
        dt = get_et_time()

    return {
        'is_open': is_market_hours(dt),
        'is_pre_close': is_pre_close(dt),
        'minutes_to_open': minutes_to_market_open(dt),
        'minutes_to_close': minutes_to_market_close(dt),
        'current_time': dt,
    }


# =============================================================================
# STRING FORMATTING
# =============================================================================

def format_market_time(hour: int, minute: int) -> str:
    """Format market time as HH:MM string."""
    return f"{hour:02d}:{minute:02d}"


MARKET_OPEN_STR = format_market_time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)  # "09:30"
MARKET_CLOSE_STR = format_market_time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)  # "16:00"
PRE_CLOSE_STR = format_market_time(PRE_CLOSE_HOUR, PRE_CLOSE_MINUTE)  # "15:50"


# =============================================================================
# ALPACA INTEGRATION - Dynamic Market Hours
# =============================================================================

# Cache for market hours (key: date string, value: market hours dict)
_market_hours_cache = {}

def get_market_hours_from_broker(date: datetime = None, force_refresh: bool = False) -> dict:
    """
    Get actual market hours from Alpaca broker for given date.

    This supports:
    - Early close days (e.g., day before Christmas closes at 13:00)
    - Late open days (rare but possible)
    - Market holidays

    Args:
        date: Date to get hours for (default: today)
        force_refresh: Force refresh from API (ignore cache)

    Returns:
        Dict with:
            - open: Market open time string (e.g., "09:30")
            - close: Market close time string (e.g., "16:00" or "13:00")
            - date: Date string (YYYY-MM-DD)
            - is_early_close: True if market closes early
            - source: "alpaca" or "fallback"

    Example:
        >>> hours = get_market_hours_from_broker()
        >>> print(hours['close'])  # "13:00" on early close day
        >>> if hours['is_early_close']:
        >>>     print("Market closes early today!")
    """
    if date is None:
        date = get_et_time()

    date_str = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)

    # Check cache first
    if not force_refresh and date_str in _market_hours_cache:
        return _market_hours_cache[date_str]

    # Try to get from Alpaca
    try:
        from engine.brokers import AlpacaBroker

        broker = AlpacaBroker(paper=True)
        calendar = broker.get_calendar(start=date_str, end=date_str)

        if not calendar or len(calendar) == 0:
            # Not a trading day
            raise ValueError(f"No market hours for {date_str} (holiday or weekend)")

        day = calendar[0]

        # Parse market hours from Alpaca
        result = {
            'open': day['open'],
            'close': day['close'],
            'date': day['date'],
            'is_early_close': day['close'] != '16:00',  # Standard close is 16:00
            'source': 'alpaca'
        }

        # Cache it
        _market_hours_cache[date_str] = result
        return result

    except Exception as e:
        # Fallback to constants
        from loguru import logger
        logger.debug(f"Failed to get market hours from Alpaca: {e}, using fallback")

        result = {
            'open': MARKET_OPEN_STR,
            'close': MARKET_CLOSE_STR,
            'date': date_str,
            'is_early_close': False,
            'source': 'fallback'
        }

        # Don't cache fallback (try API again next time)
        return result


def get_actual_market_close_time(date: datetime = None) -> time:
    """
    Get actual market close time for given date (supports early close).

    Args:
        date: Date to check (default: today)

    Returns:
        time object for market close (e.g., time(16, 0) or time(13, 0))

    Example:
        >>> close_time = get_actual_market_close_time()
        >>> if datetime.now().time() >= close_time:
        >>>     print("Market is closed")
    """
    hours = get_market_hours_from_broker(date)
    close_str = hours['close']

    # Parse "HH:MM" to time object
    hour, minute = map(int, close_str.split(':'))
    return time(hour, minute)


def is_early_close_today() -> bool:
    """
    Check if today is an early close day.

    Returns:
        True if market closes early today (e.g., 13:00 instead of 16:00)

    Example:
        >>> if is_early_close_today():
        >>>     print("Warning: Market closes early today!")
    """
    hours = get_market_hours_from_broker()
    return hours['is_early_close']


def clear_market_hours_cache():
    """Clear market hours cache (useful for testing or forcing refresh)"""
    global _market_hours_cache
    _market_hours_cache = {}
