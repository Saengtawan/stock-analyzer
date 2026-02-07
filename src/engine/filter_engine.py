"""
Engine Filter Engine - Extracted from auto_trading_engine.py (Phase 5)
=======================================================================

Utility functions for trade filtering:
- Gap filter
- Earnings filter
- Late start filter
- Stock-D filter (dip-bounce validation)

These are standalone filter functions that can be used by the engine.
"""

from typing import Tuple, Dict, Any, Optional, List
from datetime import datetime, timedelta
from loguru import logger


# Default filter thresholds
DEFAULT_GAP_UP_MAX = 2.0      # Max gap up % allowed
DEFAULT_GAP_DOWN_MAX = -5.0   # Max gap down % allowed
DEFAULT_EARNINGS_DAYS = 5     # Block if earnings within N days
DEFAULT_LATE_START_MINUTES = 15  # Max minutes after open


def check_gap_filter(
    current_price: float,
    prev_close: float,
    max_up: float = DEFAULT_GAP_UP_MAX,
    max_down: float = DEFAULT_GAP_DOWN_MAX,
) -> Tuple[bool, float, str]:
    """
    Check if price gap from previous close is acceptable.

    Dip-bounce strategy requires entering on dips, not gaps up.
    Large gaps down may indicate serious problems.

    Args:
        current_price: Current/open price
        prev_close: Previous day's close
        max_up: Maximum gap up % (default 2%)
        max_down: Maximum gap down % (default -5%)

    Returns:
        (allowed: bool, gap_pct: float, reason: str)
    """
    if prev_close <= 0:
        return True, 0.0, "No previous close"

    gap_pct = ((current_price - prev_close) / prev_close) * 100

    if gap_pct > max_up:
        return False, gap_pct, f"Gap up {gap_pct:.1f}% > {max_up}%"
    elif gap_pct < max_down:
        return False, gap_pct, f"Gap down {gap_pct:.1f}% < {max_down}%"
    else:
        return True, gap_pct, f"Gap {gap_pct:.1f}% within limits"


def check_earnings_filter(
    earnings_date: Optional[datetime],
    current_date: datetime = None,
    min_days: int = DEFAULT_EARNINGS_DAYS,
) -> Tuple[bool, Optional[int], str]:
    """
    Check if stock has upcoming earnings that should block entry.

    Earnings can cause 10-20% gaps, too risky for dip-bounce.

    Args:
        earnings_date: Next earnings date (None if unknown)
        current_date: Current date (default: now)
        min_days: Minimum days until earnings to allow trade

    Returns:
        (allowed: bool, days_until: Optional[int], reason: str)
    """
    if earnings_date is None:
        return True, None, "No earnings date known"

    current_date = current_date or datetime.now()

    if isinstance(earnings_date, str):
        earnings_date = datetime.fromisoformat(earnings_date)

    days_until = (earnings_date.date() - current_date.date()).days

    if days_until < 0:
        return True, days_until, "Earnings already passed"
    elif days_until <= min_days:
        return False, days_until, f"Earnings in {days_until} days (min {min_days})"
    else:
        return True, days_until, f"Earnings in {days_until} days (OK)"


def check_late_start_filter(
    minutes_since_open: float,
    max_minutes: int = DEFAULT_LATE_START_MINUTES,
) -> Tuple[bool, str]:
    """
    Check if we're past the optimal entry window after market open.

    Dip-bounce works best at open when dips occur.
    Late entries may catch stocks that already bounced.

    Args:
        minutes_since_open: Minutes since market open
        max_minutes: Maximum minutes after open

    Returns:
        (allowed: bool, reason: str)
    """
    if minutes_since_open < 0:
        return False, "Market not open yet"
    elif minutes_since_open <= max_minutes:
        return True, f"{minutes_since_open:.0f} min since open (OK)"
    else:
        return False, f"{minutes_since_open:.0f} min since open > {max_minutes} (late)"


def check_stock_d_filter(
    dip_5d: float,
    bounce_today: float,
    rsi: float,
    min_dip: float = -5.0,
    min_bounce: float = 0.5,
    max_rsi: float = 50.0,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check Stock-D filter for dip-bounce pattern.

    A valid dip-bounce requires:
    1. Prior dip (negative 5-day momentum)
    2. Today's bounce (positive intraday)
    3. Oversold RSI (not overbought)

    Args:
        dip_5d: 5-day price change %
        bounce_today: Today's price change %
        rsi: Current RSI
        min_dip: Minimum 5d dip required (default -5%)
        min_bounce: Minimum today's bounce (default 0.5%)
        max_rsi: Maximum RSI (default 50)

    Returns:
        (allowed: bool, reason: str, details: Dict)
    """
    details = {
        'dip_5d': dip_5d,
        'bounce_today': bounce_today,
        'rsi': rsi,
        'checks': {}
    }

    # Check 1: Prior dip
    has_dip = dip_5d <= min_dip
    details['checks']['dip'] = has_dip

    # Check 2: Today's bounce
    has_bounce = bounce_today >= min_bounce
    details['checks']['bounce'] = has_bounce

    # Check 3: RSI not overbought
    rsi_ok = rsi <= max_rsi
    details['checks']['rsi'] = rsi_ok

    if has_dip and has_bounce and rsi_ok:
        return True, "Valid dip-bounce pattern", details

    reasons = []
    if not has_dip:
        reasons.append(f"5d {dip_5d:.1f}% > {min_dip}%")
    if not has_bounce:
        reasons.append(f"bounce {bounce_today:.1f}% < {min_bounce}%")
    if not rsi_ok:
        reasons.append(f"RSI {rsi:.0f} > {max_rsi}")

    return False, f"No dip-bounce: {', '.join(reasons)}", details


def check_atr_volatility(
    atr_pct: float,
    max_atr: float = 8.0,
    min_atr: float = 1.0,
) -> Tuple[bool, str]:
    """
    Check if ATR volatility is within acceptable range.

    Too high ATR = too volatile
    Too low ATR = no movement potential

    Args:
        atr_pct: ATR as % of price
        max_atr: Maximum ATR % (default 8%)
        min_atr: Minimum ATR % (default 1%)

    Returns:
        (allowed: bool, reason: str)
    """
    if atr_pct > max_atr:
        return False, f"ATR {atr_pct:.1f}% > {max_atr}% (too volatile)"
    elif atr_pct < min_atr:
        return False, f"ATR {atr_pct:.1f}% < {min_atr}% (no movement)"
    else:
        return True, f"ATR {atr_pct:.1f}% within range"


def check_price_range(
    price: float,
    min_price: float = 5.0,
    max_price: float = 500.0,
) -> Tuple[bool, str]:
    """
    Check if price is within acceptable range.

    Args:
        price: Stock price
        min_price: Minimum price (default $5)
        max_price: Maximum price (default $500)

    Returns:
        (allowed: bool, reason: str)
    """
    if price < min_price:
        return False, f"${price:.2f} < ${min_price} (too cheap)"
    elif price > max_price:
        return False, f"${price:.2f} > ${max_price} (too expensive)"
    else:
        return True, f"${price:.2f} within range"


def apply_all_filters(
    signal: Dict[str, Any],
    filters: Dict[str, bool],
    filter_params: Dict[str, Any] = None,
) -> Tuple[bool, List[str]]:
    """
    Apply all enabled filters to a signal.

    Args:
        signal: Signal dict with price, earnings, etc.
        filters: Dict of filter_name -> enabled
        filter_params: Optional filter parameters

    Returns:
        (allowed: bool, rejection_reasons: List[str])
    """
    filter_params = filter_params or {}
    rejections = []

    # Gap filter
    if filters.get('gap', True):
        allowed, gap, reason = check_gap_filter(
            signal.get('entry_price', 0),
            signal.get('prev_close', 0),
            filter_params.get('gap_up_max', DEFAULT_GAP_UP_MAX),
            filter_params.get('gap_down_max', DEFAULT_GAP_DOWN_MAX),
        )
        if not allowed:
            rejections.append(f"[GAP] {reason}")

    # Earnings filter
    if filters.get('earnings', True):
        allowed, days, reason = check_earnings_filter(
            signal.get('earnings_date'),
            min_days=filter_params.get('earnings_days', DEFAULT_EARNINGS_DAYS),
        )
        if not allowed:
            rejections.append(f"[EARNINGS] {reason}")

    # ATR filter
    if filters.get('atr', True):
        allowed, reason = check_atr_volatility(
            signal.get('atr_pct', 5.0),
            filter_params.get('max_atr', 8.0),
            filter_params.get('min_atr', 1.0),
        )
        if not allowed:
            rejections.append(f"[ATR] {reason}")

    # Price range filter
    if filters.get('price_range', True):
        allowed, reason = check_price_range(
            signal.get('entry_price', 0),
            filter_params.get('min_price', 5.0),
            filter_params.get('max_price', 500.0),
        )
        if not allowed:
            rejections.append(f"[PRICE] {reason}")

    return len(rejections) == 0, rejections
