"""
Timeout utilities (Production Grade v6.21 - Phase 2 Item 2)

Provides timeout decorators and context managers for preventing
hanging operations.

Usage:
    from utils.timeout import timeout

    @timeout(seconds=30)
    def long_running_task():
        # ... task code ...

    # Or as context manager:
    with timeout(seconds=30):
        # ... code that might hang ...
"""

import signal
import functools
from contextlib import contextmanager
from typing import Callable, Any
from loguru import logger


class TimeoutError(Exception):
    """Raised when operation exceeds timeout"""
    pass


def timeout(seconds: int = 300):
    """
    Decorator to add timeout to function (Unix only)

    Args:
        seconds: Timeout in seconds (default: 300 = 5 minutes)

    Example:
        @timeout(seconds=60)
        def scan_stocks():
            # This will timeout after 60 seconds
            ...

    Note: Only works on Unix systems (uses SIGALRM)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Check if we can use signal (Unix only)
            if not hasattr(signal, 'SIGALRM'):
                logger.warning(f"Timeout decorator not supported on this platform (function: {func.__name__})")
                return func(*args, **kwargs)

            def timeout_handler(signum, frame):
                raise TimeoutError(f"Function '{func.__name__}' exceeded timeout of {seconds}s")

            # Set signal handler (v6.21: Skip if not in main thread)
            try:
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(seconds)
                use_timeout = True
            except ValueError as e:
                # "signal only works in main thread" - skip timeout
                logger.debug(f"Timeout skipped for {func.__name__} (not in main thread)")
                use_timeout = False

            try:
                result = func(*args, **kwargs)
            finally:
                # Restore old handler and cancel alarm
                if use_timeout:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)

            return result

        return wrapper
    return decorator


@contextmanager
def timeout_context(seconds: int = 300):
    """
    Context manager for timeout (Unix only)

    Args:
        seconds: Timeout in seconds

    Example:
        with timeout_context(seconds=60):
            # This code will timeout after 60 seconds
            result = expensive_operation()

    Note: Only works on Unix systems (uses SIGALRM)
    """
    if not hasattr(signal, 'SIGALRM'):
        logger.warning("Timeout context not supported on this platform")
        yield
        return

    def timeout_handler(signum, frame):
        raise TimeoutError(f"Operation exceeded timeout of {seconds}s")

    # v6.21: Handle "signal only works in main thread" gracefully
    try:
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(seconds)
        use_timeout = True
    except ValueError:
        logger.debug("Timeout context skipped (not in main thread)")
        use_timeout = False

    try:
        yield
    finally:
        if use_timeout:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


# =========================================================================
# THREAD-SAFE TIMEOUT (works on all platforms)
# =========================================================================

import threading


class ThreadTimeout:
    """
    Thread-based timeout (works on all platforms, but less efficient)

    Note: This creates a timer thread. For critical operations,
    prefer signal-based timeout on Unix systems.
    """

    def __init__(self, seconds: int):
        self.seconds = seconds
        self.timer: Optional[threading.Timer] = None
        self.timed_out = False

    def _timeout_callback(self):
        """Called when timeout expires"""
        self.timed_out = True
        logger.error(f"Operation timed out after {self.seconds}s")

    def __enter__(self):
        self.timer = threading.Timer(self.seconds, self._timeout_callback)
        self.timer.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.timer:
            self.timer.cancel()

        if self.timed_out:
            raise TimeoutError(f"Operation exceeded timeout of {self.seconds}s")


# =========================================================================
# CONVENIENCE FUNCTIONS
# =========================================================================

def run_with_timeout(func: Callable, args=(), kwargs=None, timeout_seconds: int = 300) -> Any:
    """
    Run function with timeout (thread-safe, works on all platforms)

    Args:
        func: Function to run
        args: Positional arguments
        kwargs: Keyword arguments
        timeout_seconds: Timeout in seconds

    Returns:
        Function result

    Raises:
        TimeoutError: If function exceeds timeout

    Example:
        result = run_with_timeout(scan_stocks, timeout_seconds=60)
    """
    kwargs = kwargs or {}

    with ThreadTimeout(timeout_seconds):
        return func(*args, **kwargs)


# =========================================================================
# EXAMPLE USAGE
# =========================================================================

if __name__ == '__main__':
    import time

    print("🧪 Testing timeout utilities...")

    # Test 1: Successful completion
    print("\n1. Function completes within timeout:")
    @timeout(seconds=5)
    def quick_task():
        time.sleep(1)
        return "done"

    result = quick_task()
    print(f"   ✅ Result: {result}")

    # Test 2: Timeout
    print("\n2. Function exceeds timeout:")
    @timeout(seconds=2)
    def slow_task():
        time.sleep(10)
        return "done"

    try:
        slow_task()
    except TimeoutError as e:
        print(f"   ✅ Caught timeout: {e}")

    # Test 3: Context manager
    print("\n3. Context manager timeout:")
    try:
        with timeout_context(seconds=2):
            time.sleep(5)
    except TimeoutError as e:
        print(f"   ✅ Caught timeout: {e}")

    print("\n✅ Tests complete!")
