"""
Market Calendar Utility - Single Source of Truth
=================================================

This module provides trading day detection and market calendar functions.
All components should use these functions instead of duplicating logic.

Usage:
    from src.utils.market_calendar import is_trading_day_today, get_market_calendar_status
"""

import pytz
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any

from .market_hours import MARKET_TIMEZONE, get_et_time


# =============================================================================
# TRADING DAY DETECTION
# =============================================================================

def is_trading_day_today(
    next_open: Optional[datetime] = None,
    is_market_open: bool = False,
    current_date: Optional[date] = None
) -> bool:
    """
    Determine if today is/was a trading day.

    Logic:
    - If market is open NOW → yes, today is a trading day
    - If next open is TODAY → yes, today is a trading day (premarket)
    - If next open is TOMORROW and today is WEEKDAY → yes, today was a trading day (after close)
    - Otherwise → no (weekend or holiday)

    Args:
        next_open: Next market open datetime (from Alpaca API)
        is_market_open: Whether market is currently open
        current_date: Date to check (default: today in ET)

    Returns:
        True if today is/was a trading day, False otherwise

    Examples:
        Monday 10:00 (market open):
            is_market_open=True → True

        Monday 17:00 (after close):
            next_open=Tuesday 09:30, is_weekday=True → True

        Friday 17:00 (after close):
            next_open=Monday 09:30, is_weekday=True → True

        Saturday:
            next_open=Monday 09:30, is_weekday=False → False

        Holiday (e.g., New Year):
            next_open=Next trading day, is_weekday=True but days_until > 1 → False
    """
    if current_date is None:
        et_now = get_et_time()
        current_date = et_now.date()
    else:
        et_now = get_et_time()

    # If market is open now, definitely a trading day
    if is_market_open:
        return True

    # If next_open not provided, can't determine - default to weekday check
    if next_open is None:
        is_weekday = et_now.weekday() < 5
        return is_weekday

    # Get next open date
    next_open_date = next_open.date() if hasattr(next_open, 'date') else next_open

    # If next open is today, it's a trading day (premarket)
    if next_open_date == current_date:
        return True

    # After-hours detection: if current ET time >= 16:00 and it's a weekday,
    # market has already closed today → today WAS a trading day (show CLOSED not HOLIDAY).
    # This fixes the false-positive holiday label after market close.
    # Note: does NOT apply to early-close days (e.g. Dec 24 13:00 close) since
    # those have next_open farther than 1 day away and time < 16:00.
    from datetime import time as _time
    MARKET_CLOSE = _time(16, 0)
    if et_now.time() >= MARKET_CLOSE and et_now.weekday() < 5:
        return True

    # If we got here, market is not open and next open is not today and we're
    # not in after-hours of a regular trading day → holiday or weekend.
    return False


def is_holiday_today(
    next_open: Optional[datetime] = None,
    current_date: Optional[date] = None
) -> bool:
    """
    Determine if today is a market holiday.

    A holiday is a weekday that is NOT a trading day.

    Args:
        next_open: Next market open datetime
        current_date: Date to check (default: today in ET)

    Returns:
        True if today is a holiday, False otherwise
    """
    if current_date is None:
        et_now = get_et_time()
        current_date = et_now.date()
    else:
        et_now = get_et_time()

    is_weekday = et_now.weekday() < 5

    # If weekend, not a holiday (it's a weekend)
    if not is_weekday:
        return False

    # If weekday but not a trading day → holiday
    is_trading = is_trading_day_today(next_open, False, current_date)
    return is_weekday and not is_trading


# =============================================================================
# MARKET CALENDAR STATUS
# =============================================================================

def get_market_calendar_status(
    next_open: Optional[datetime] = None,
    next_close: Optional[datetime] = None,
    is_market_open: bool = False
) -> Dict[str, Any]:
    """
    Get comprehensive market calendar status.

    This function provides all information needed for UI header display.

    Args:
        next_open: Next market open datetime (from Alpaca clock)
        next_close: Next market close datetime (from Alpaca clock)
        is_market_open: Whether market is currently open

    Returns:
        Dict with:
            - is_trading_day: bool - Is today a trading day?
            - is_holiday: bool - Is today a holiday?
            - is_weekend: bool - Is today a weekend?
            - is_open: bool - Is market currently open?
            - next_open: datetime - Next market open
            - next_close: datetime - Next market close
            - status: str - Human-readable status (OPEN, CLOSED, HOLIDAY, WEEKEND)
    """
    et_now = get_et_time()
    current_date = et_now.date()
    is_weekday = et_now.weekday() < 5

    # Determine if today is a trading day
    is_trading = is_trading_day_today(next_open, is_market_open, current_date)

    # Determine if today is a holiday (weekday but not trading day)
    is_holiday = is_weekday and not is_trading

    # Determine status string
    if is_market_open:
        status = 'OPEN'
    elif is_holiday:
        status = 'HOLIDAY'
    elif not is_weekday:
        status = 'WEEKEND'
    else:
        status = 'CLOSED'

    return {
        'is_trading_day': is_trading,
        'is_holiday': is_holiday,
        'is_weekend': not is_weekday,
        'is_open': is_market_open,
        'next_open': next_open,
        'next_close': next_close,
        'status': status,
        'current_time': et_now,
    }


# =============================================================================
# NEXT TRADING DAY
# =============================================================================

def get_next_trading_day(
    current_date: Optional[date] = None,
    calendar: Optional[list] = None
) -> date:
    """
    Get next trading day from current date.

    Args:
        current_date: Starting date (default: today in ET)
        calendar: List of trading days from Alpaca API (optional)

    Returns:
        Next trading day (date object)
    """
    if current_date is None:
        current_date = get_et_time().date()

    # If calendar provided, use it
    if calendar:
        for trading_day in calendar:
            if isinstance(trading_day, str):
                trading_day = datetime.strptime(trading_day, '%Y-%m-%d').date()
            if trading_day > current_date:
                return trading_day

    # Fallback: simple weekday calculation (doesn't account for holidays)
    next_day = current_date + timedelta(days=1)
    while next_day.weekday() >= 5:  # Skip weekends
        next_day += timedelta(days=1)

    return next_day


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_next_open_display(next_open: Optional[datetime]) -> str:
    """
    Format next open time for display.

    Args:
        next_open: Next market open datetime

    Returns:
        Formatted string like "Mon 09:30" or "Tomorrow 09:30"
    """
    if next_open is None:
        return "Unknown"

    et_now = get_et_time()
    next_open_date = next_open.date() if hasattr(next_open, 'date') else next_open

    # Calculate days difference
    days_diff = (next_open_date - et_now.date()).days

    if days_diff == 0:
        day_str = "Today"
    elif days_diff == 1:
        day_str = "Tomorrow"
    elif days_diff == 3 and et_now.weekday() == 4:  # Friday → Monday
        day_str = "Mon"
    else:
        day_str = next_open.strftime('%a')

    time_str = next_open.strftime('%H:%M') if hasattr(next_open, 'strftime') else "09:30"

    return f"{day_str} {time_str}"
