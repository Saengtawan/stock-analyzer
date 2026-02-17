"""
Safe Signal Handler Utilities
Prevents "signal only works in main thread" errors
"""
import signal
import threading
import logging

logger = logging.getLogger(__name__)


def safe_signal_install(signum, handler):
    """
    Safely install signal handler only if in main thread.

    Args:
        signum: Signal number (signal.SIGINT, signal.SIGTERM, etc.)
        handler: Signal handler function

    Returns:
        bool: True if handler was installed, False if skipped

    Example:
        >>> from utils.safe_signal import safe_signal_install
        >>> safe_signal_install(signal.SIGINT, my_handler)
    """
    try:
        if threading.current_thread() is threading.main_thread():
            signal.signal(signum, handler)
            logger.debug(f"✅ Signal handler installed for {signum}")
            return True
        else:
            logger.debug(f"⚠️ Skipping signal handler for {signum} (not in main thread)")
            return False
    except Exception as e:
        logger.warning(f"⚠️ Could not install signal handler for {signum}: {e}")
        return False


def safe_signal_install_multiple(handlers):
    """
    Install multiple signal handlers safely.

    Args:
        handlers: Dict of {signal_num: handler_func} or list of (signal_num, handler_func)

    Returns:
        dict: {signal_num: success_bool}

    Example:
        >>> handlers = {
        ...     signal.SIGINT: shutdown_handler,
        ...     signal.SIGTERM: shutdown_handler
        ... }
        >>> results = safe_signal_install_multiple(handlers)
    """
    if isinstance(handlers, dict):
        handlers = handlers.items()

    results = {}
    for signum, handler in handlers:
        results[signum] = safe_signal_install(signum, handler)

    return results


def is_main_thread():
    """
    Check if currently in main thread.

    Returns:
        bool: True if in main thread, False otherwise
    """
    return threading.current_thread() is threading.main_thread()
