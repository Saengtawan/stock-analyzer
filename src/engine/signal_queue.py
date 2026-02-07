"""
Engine Signal Queue - Extracted from auto_trading_engine.py (Phase 7)
======================================================================

Utility functions for signal queue management:
- Queue prioritization
- Price deviation checking
- Signal freshness validation
- Queue operations

These are standalone queue utilities that support the engine.
"""

from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger


# Default queue parameters
DEFAULT_FRESHNESS_MINUTES = 30       # Consider signals fresh if < 30 min old
DEFAULT_ATR_MULT = 0.5               # ATR multiplier for price deviation
DEFAULT_MIN_DEVIATION = 0.5          # Minimum acceptable deviation %
DEFAULT_MAX_DEVIATION = 1.5          # Maximum acceptable deviation %
DEFAULT_QUEUE_MAX_SIZE = 10          # Maximum queue size


def check_price_deviation(
    current_price: float,
    signal_price: float,
    atr_pct: float = 5.0,
    atr_mult: float = DEFAULT_ATR_MULT,
    min_dev: float = DEFAULT_MIN_DEVIATION,
    max_dev: float = DEFAULT_MAX_DEVIATION,
) -> Tuple[bool, float, float]:
    """
    Check if current price is still acceptable vs signal price.

    Uses ATR-based deviation calculation with min/max bounds.

    Args:
        current_price: Current market price
        signal_price: Price when signal was generated
        atr_pct: ATR as % of price
        atr_mult: Multiplier for ATR-based deviation
        min_dev: Minimum deviation threshold %
        max_dev: Maximum deviation threshold %

    Returns:
        (acceptable: bool, deviation_pct: float, max_allowed: float)
    """
    if signal_price <= 0:
        return False, 0.0, 0.0

    deviation_pct = ((current_price - signal_price) / signal_price) * 100
    atr_based_dev = atr_pct * atr_mult
    max_allowed = min(max(atr_based_dev, min_dev), max_dev)

    acceptable = deviation_pct <= max_allowed
    return acceptable, deviation_pct, max_allowed


def is_signal_fresh(
    queued_at: datetime,
    freshness_minutes: float = DEFAULT_FRESHNESS_MINUTES,
) -> Tuple[bool, float]:
    """
    Check if signal is still fresh (within time window).

    Args:
        queued_at: Time when signal was queued
        freshness_minutes: Maximum age in minutes

    Returns:
        (is_fresh: bool, minutes_old: float)
    """
    minutes_old = (datetime.now() - queued_at).total_seconds() / 60
    is_fresh = minutes_old <= freshness_minutes
    return is_fresh, minutes_old


def prioritize_queue(
    queue: List[Dict[str, Any]],
    freshness_minutes: float = DEFAULT_FRESHNESS_MINUTES,
) -> List[Dict[str, Any]]:
    """
    Sort queue by priority (fresh signals first, then by score).

    Priority order:
    1. Fresh signals (< freshness_minutes) by score descending
    2. Older signals by score descending

    Args:
        queue: List of queued signals
        freshness_minutes: Threshold for "fresh" signals

    Returns:
        Sorted queue
    """
    now = datetime.now()

    def sort_key(signal):
        queued_at = signal.get('queued_at')
        if isinstance(queued_at, str):
            queued_at = datetime.fromisoformat(queued_at)

        minutes_old = (now - queued_at).total_seconds() / 60 if queued_at else float('inf')
        is_fresh = minutes_old <= freshness_minutes
        score = signal.get('score', 0)

        # Fresh signals first (is_fresh=True -> 0), then by score descending
        return (0 if is_fresh else 1, -score)

    return sorted(queue, key=sort_key)


def filter_expired_signals(
    queue: List[Dict[str, Any]],
    max_age_minutes: float = 60.0,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Separate expired signals from valid ones.

    Args:
        queue: List of queued signals
        max_age_minutes: Maximum signal age

    Returns:
        (valid_signals: List, expired_signals: List)
    """
    valid = []
    expired = []
    now = datetime.now()

    for signal in queue:
        queued_at = signal.get('queued_at')
        if isinstance(queued_at, str):
            queued_at = datetime.fromisoformat(queued_at)

        if queued_at:
            age_minutes = (now - queued_at).total_seconds() / 60
            if age_minutes <= max_age_minutes:
                valid.append(signal)
            else:
                expired.append(signal)
        else:
            expired.append(signal)

    return valid, expired


def should_add_to_queue(
    signal: Dict[str, Any],
    current_queue: List[Dict[str, Any]],
    held_symbols: List[str],
    max_queue_size: int = DEFAULT_QUEUE_MAX_SIZE,
    min_score: float = 85.0,
) -> Tuple[bool, str]:
    """
    Determine if a signal should be added to the queue.

    Args:
        signal: Signal to potentially queue
        current_queue: Current queue
        held_symbols: Symbols currently held
        max_queue_size: Maximum queue size
        min_score: Minimum score to queue

    Returns:
        (should_add: bool, reason: str)
    """
    symbol = signal.get('symbol', '')
    score = signal.get('score', 0)

    # Check if already holding
    if symbol in held_symbols:
        return False, f"Already holding {symbol}"

    # Check if already in queue
    queued_symbols = [s.get('symbol') for s in current_queue]
    if symbol in queued_symbols:
        return False, f"{symbol} already in queue"

    # Check score threshold
    if score < min_score:
        return False, f"Score {score} < {min_score}"

    # Check queue size
    if len(current_queue) >= max_queue_size:
        # Check if this signal is better than worst in queue
        if current_queue:
            min_queued_score = min(s.get('score', 0) for s in current_queue)
            if score > min_queued_score:
                return True, f"Score {score} > worst in queue ({min_queued_score})"
        return False, f"Queue full ({len(current_queue)}/{max_queue_size})"

    return True, "Added to queue"


def select_best_from_queue(
    queue: List[Dict[str, Any]],
    current_prices: Dict[str, float],
    freshness_minutes: float = DEFAULT_FRESHNESS_MINUTES,
    atr_mult: float = DEFAULT_ATR_MULT,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Select the best executable signal from queue.

    Checks price deviation and freshness to find best candidate.

    Args:
        queue: Prioritized queue of signals
        current_prices: Dict mapping symbol -> current price
        freshness_minutes: Freshness threshold
        atr_mult: ATR multiplier for deviation check

    Returns:
        (best_signal: Optional[Dict], reason: str)
    """
    for signal in queue:
        symbol = signal.get('symbol', '')
        current_price = current_prices.get(symbol)

        if current_price is None:
            continue

        # Check price deviation
        acceptable, dev_pct, max_dev = check_price_deviation(
            current_price,
            signal.get('signal_price', 0),
            signal.get('atr_pct', 5.0),
            atr_mult,
        )

        if not acceptable:
            logger.debug(f"Queue {symbol}: price deviation {dev_pct:.1f}% > {max_dev:.1f}%")
            continue

        # Check freshness (prefer fresh but accept older)
        is_fresh, minutes_old = is_signal_fresh(
            signal.get('queued_at', datetime.now()),
            freshness_minutes,
        )

        freshness_note = "fresh" if is_fresh else f"aged {minutes_old:.0f}min"
        return signal, f"Selected {symbol} (dev {dev_pct:.1f}%, {freshness_note})"

    return None, "No executable signals in queue"


def get_queue_summary(queue: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Get summary statistics for the queue.

    Returns:
        Dict with queue stats
    """
    if not queue:
        return {
            'count': 0,
            'symbols': [],
            'avg_score': 0,
            'oldest_minutes': 0,
            'freshest_minutes': 0,
        }

    now = datetime.now()
    scores = [s.get('score', 0) for s in queue]

    ages = []
    for s in queue:
        queued_at = s.get('queued_at')
        if isinstance(queued_at, str):
            queued_at = datetime.fromisoformat(queued_at)
        if queued_at:
            ages.append((now - queued_at).total_seconds() / 60)

    return {
        'count': len(queue),
        'symbols': [s.get('symbol', '') for s in queue],
        'avg_score': sum(scores) / len(scores) if scores else 0,
        'oldest_minutes': max(ages) if ages else 0,
        'freshest_minutes': min(ages) if ages else 0,
    }
