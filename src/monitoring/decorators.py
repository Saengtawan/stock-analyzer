"""
Monitoring Decorators - Phase 5D
=================================
Decorators for automatic performance tracking.
"""

import time
from functools import wraps
from typing import Callable
from loguru import logger

from .performance_monitor import get_performance_monitor


def track_performance(component: str, operation_type: str = 'query'):
    """
    Decorator to automatically track method performance.

    Args:
        component: Component name (e.g., 'PositionRepository')
        operation_type: Type of operation ('query', 'api', etc.)

    Usage:
        @track_performance('PositionRepository', 'query')
        def get_all(self):
            return self._load_from_database()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            monitor = get_performance_monitor()
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.time() - start_time) * 1000

                # Record performance
                if operation_type == 'query':
                    monitor.record_query_time(component, duration_ms, 'select')
                elif operation_type == 'api':
                    monitor.record_api_time(component, duration_ms, 200)

        return wrapper
    return decorator


def track_cache(component: str):
    """
    Decorator to automatically track cache hits/misses.

    The decorated function should return (result, cache_hit: bool).

    Usage:
        @track_cache('PositionRepository')
        def get_with_cache(self, use_cache=True):
            if use_cache and self._cache:
                return self._cache, True  # cache hit
            result = self._load()
            return result, False  # cache miss
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # Expect (data, cache_hit) tuple
            if isinstance(result, tuple) and len(result) == 2:
                data, cache_hit = result
                monitor = get_performance_monitor()
                monitor.record_cache_hit(component, cache_hit)
                return data
            else:
                return result

        return wrapper
    return decorator


def monitor_errors(component: str):
    """
    Decorator to monitor and log errors.

    Usage:
        @monitor_errors('PositionRepository')
        def risky_operation(self):
            # ... code that might fail
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"{component}.{func.__name__} error: {e}")

                # Create error alert
                try:
                    from database import AlertsRepository, Alert
                    from datetime import datetime

                    repo = AlertsRepository()
                    alert = Alert(
                        level='ERROR',
                        message=f"{component}.{func.__name__} failed: {str(e)}",
                        timestamp=datetime.now().isoformat(),
                        active=True,
                        metadata={'component': component, 'method': func.__name__}
                    )
                    repo.create(alert)
                except:
                    pass  # Don't fail if alert creation fails

                # Re-raise the exception
                raise

        return wrapper
    return decorator
