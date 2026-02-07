"""
Engine Core - Placeholder for main trading loop (Phase 10)
===========================================================

This module will eventually contain the core trading loop logic.
Currently a placeholder - the main loop remains in auto_trading_engine.py.

Future refactoring will move:
- _run_loop()
- start() / stop()
- Main state machine
- Scanner schedule management

For now, this module provides some utility functions for loop management.
"""

from typing import Callable, Optional, Dict, Any
from datetime import datetime, timedelta
from loguru import logger
import time


def create_loop_schedule(
    market_open_hour: int = 9,
    market_open_minute: int = 30,
    market_close_hour: int = 16,
    market_close_minute: int = 0,
    scan_interval_minutes: int = 5,
    volatile_interval_minutes: int = 3,
    volatile_end_hour: int = 11,
) -> Dict[str, Any]:
    """
    Create schedule configuration for main loop.

    Args:
        market_open_hour: Market open hour (ET)
        market_open_minute: Market open minute
        market_close_hour: Market close hour
        market_close_minute: Market close minute
        scan_interval_minutes: Normal scan interval
        volatile_interval_minutes: Scan interval during volatile period
        volatile_end_hour: Hour when volatile period ends

    Returns:
        Schedule configuration dict
    """
    return {
        'market_open': f"{market_open_hour:02d}:{market_open_minute:02d}",
        'market_close': f"{market_close_hour:02d}:{market_close_minute:02d}",
        'scan_interval': scan_interval_minutes,
        'volatile_interval': volatile_interval_minutes,
        'volatile_end': volatile_end_hour,
        'pre_close_minute': 50,  # Pre-close starts at 15:50
    }


def calculate_next_scan_time(
    current_time: datetime,
    schedule: Dict[str, Any],
) -> Optional[datetime]:
    """
    Calculate next scan time based on schedule.

    Args:
        current_time: Current time (in ET)
        schedule: Schedule from create_loop_schedule

    Returns:
        Next scan time or None if market closed
    """
    hour = current_time.hour

    # Determine interval based on volatility period
    volatile_end = schedule.get('volatile_end', 11)
    if hour < volatile_end:
        interval = schedule.get('volatile_interval', 3)
    else:
        interval = schedule.get('scan_interval', 5)

    next_scan = current_time + timedelta(minutes=interval)

    # Check if past pre-close
    pre_close = current_time.replace(hour=15, minute=schedule.get('pre_close_minute', 50), second=0, microsecond=0)
    if next_scan >= pre_close:
        return None

    return next_scan


def sleep_until(
    target_time: datetime,
    check_interval_seconds: float = 1.0,
    stop_flag: Callable[[], bool] = None,
) -> bool:
    """
    Sleep until target time, checking stop flag periodically.

    Args:
        target_time: Time to wake up
        check_interval_seconds: How often to check stop flag
        stop_flag: Callable that returns True to stop early

    Returns:
        True if reached target, False if stopped early
    """
    while datetime.now() < target_time:
        if stop_flag and stop_flag():
            return False
        time.sleep(check_interval_seconds)
    return True


def format_loop_status(
    state: str,
    positions_count: int,
    queue_count: int,
    last_scan: Optional[datetime],
    next_scan: Optional[datetime],
) -> str:
    """
    Format current loop status for display.

    Returns:
        Formatted status string
    """
    last_str = last_scan.strftime('%H:%M:%S') if last_scan else 'Never'
    next_str = next_scan.strftime('%H:%M:%S') if next_scan else 'N/A'

    return (
        f"State: {state} | "
        f"Positions: {positions_count} | "
        f"Queue: {queue_count} | "
        f"Last scan: {last_str} | "
        f"Next scan: {next_str}"
    )


class LoopTimer:
    """
    Timer for managing loop iterations.

    Usage:
        timer = LoopTimer(interval_seconds=60)
        while running:
            timer.start()
            # do work
            timer.wait()  # waits remaining time
    """

    def __init__(self, interval_seconds: float):
        self.interval = interval_seconds
        self.start_time = None

    def start(self):
        """Mark start of iteration"""
        self.start_time = time.time()

    def elapsed(self) -> float:
        """Get elapsed time since start"""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time

    def remaining(self) -> float:
        """Get remaining time in interval"""
        return max(0, self.interval - self.elapsed())

    def wait(self, stop_flag: Callable[[], bool] = None) -> bool:
        """
        Wait for remaining time in interval.

        Returns:
            True if completed, False if stopped early
        """
        remaining = self.remaining()
        if remaining <= 0:
            return True

        if stop_flag is None:
            time.sleep(remaining)
            return True

        # Check stop flag periodically
        check_interval = min(1.0, remaining)
        while remaining > 0:
            if stop_flag():
                return False
            sleep_time = min(check_interval, remaining)
            time.sleep(sleep_time)
            remaining = self.remaining()

        return True


def safe_call(
    func: Callable,
    error_prefix: str = "Error",
    default: Any = None,
) -> Any:
    """
    Call function with exception handling.

    Args:
        func: Function to call (no args)
        error_prefix: Prefix for error logging
        default: Default return value on error

    Returns:
        Function result or default
    """
    try:
        return func()
    except Exception as e:
        logger.error(f"{error_prefix}: {e}")
        return default
