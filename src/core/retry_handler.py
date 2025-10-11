"""
Retry Handler with Exponential Backoff
Provides intelligent retry logic for API calls and operations
"""
from typing import Callable, Optional, Type, Tuple, Any
from functools import wraps
import time
import random
from loguru import logger

from .exceptions import (
    APIRateLimitException,
    APITimeoutException,
    APIException,
    DataNotFoundException
)


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize retry configuration

        Args:
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay between retries (seconds)
            max_delay: Maximum delay between retries (seconds)
            exponential_base: Base for exponential backoff
            jitter: Add random jitter to prevent thundering herd
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt number

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff: delay = initial_delay * (exponential_base ^ attempt)
        delay = self.initial_delay * (self.exponential_base ** attempt)

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        # Add jitter (randomness) to prevent thundering herd
        if self.jitter:
            delay = delay * (0.5 + random.random())

        return delay


class RetryHandler:
    """Handles retry logic with exponential backoff"""

    # Default retry configurations for different scenarios
    DEFAULT_CONFIG = RetryConfig(
        max_retries=3,
        initial_delay=1.0,
        max_delay=30.0
    )

    API_RATE_LIMIT_CONFIG = RetryConfig(
        max_retries=5,
        initial_delay=5.0,
        max_delay=60.0,
        exponential_base=2.0
    )

    API_TIMEOUT_CONFIG = RetryConfig(
        max_retries=2,
        initial_delay=2.0,
        max_delay=10.0
    )

    NETWORK_ERROR_CONFIG = RetryConfig(
        max_retries=3,
        initial_delay=1.0,
        max_delay=15.0
    )

    @staticmethod
    def should_retry(exception: Exception) -> Tuple[bool, Optional[RetryConfig]]:
        """
        Determine if an exception should trigger a retry

        Args:
            exception: The exception that was raised

        Returns:
            (should_retry, retry_config)
        """
        # API Rate Limit - definitely retry with longer delays
        if isinstance(exception, APIRateLimitException):
            return True, RetryHandler.API_RATE_LIMIT_CONFIG

        # API Timeout - retry with shorter delays
        if isinstance(exception, APITimeoutException):
            return True, RetryHandler.API_TIMEOUT_CONFIG

        # Other API errors - retry with default config
        if isinstance(exception, APIException):
            return True, RetryHandler.NETWORK_ERROR_CONFIG

        # Network errors (connection issues)
        if isinstance(exception, (ConnectionError, TimeoutError)):
            return True, RetryHandler.NETWORK_ERROR_CONFIG

        # Data not found - don't retry (it won't appear)
        if isinstance(exception, DataNotFoundException):
            return False, None

        # Unknown errors - don't retry by default
        return False, None

    @staticmethod
    def retry_with_backoff(
        func: Callable,
        config: Optional[RetryConfig] = None,
        retry_on: Optional[Tuple[Type[Exception], ...]] = None
    ) -> Callable:
        """
        Decorator to add retry logic with exponential backoff

        Args:
            func: Function to retry
            config: Retry configuration (uses DEFAULT_CONFIG if None)
            retry_on: Tuple of exception types to retry on

        Returns:
            Wrapped function with retry logic

        Example:
            @retry_with_backoff(config=RetryConfig(max_retries=5))
            def fetch_stock_data(symbol):
                return api.get_data(symbol)
        """
        if config is None:
            config = RetryHandler.DEFAULT_CONFIG

        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    # Try to execute the function
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # Check if we should retry this exception
                    should_retry, specific_config = RetryHandler.should_retry(e)

                    # Use specific config if provided
                    if specific_config:
                        config_to_use = specific_config
                    else:
                        config_to_use = config

                    # If this is the last attempt, don't retry
                    if attempt >= config_to_use.max_retries:
                        logger.error(
                            f"Max retries ({config_to_use.max_retries}) exceeded for {func.__name__}",
                            extra={
                                'function': func.__name__,
                                'attempts': attempt + 1,
                                'error': str(e)
                            }
                        )
                        raise

                    # If we shouldn't retry this exception, raise immediately
                    if not should_retry:
                        if retry_on and not isinstance(e, retry_on):
                            # If retry_on is specified and this isn't one of those exceptions, raise
                            raise
                        elif not retry_on:
                            # If no retry_on specified, don't retry unknown exceptions
                            raise

                    # Calculate delay
                    delay = config_to_use.calculate_delay(attempt)

                    logger.warning(
                        f"Retry attempt {attempt + 1}/{config_to_use.max_retries} for {func.__name__} "
                        f"after {delay:.2f}s",
                        extra={
                            'function': func.__name__,
                            'attempt': attempt + 1,
                            'max_retries': config_to_use.max_retries,
                            'delay': delay,
                            'error': str(e),
                            'error_type': type(e).__name__
                        }
                    )

                    # Wait before retrying
                    time.sleep(delay)

            # If we get here, all retries failed
            if last_exception:
                raise last_exception

        return wrapper

    @staticmethod
    def retry_async(
        max_retries: int = 3,
        initial_delay: float = 1.0,
        exceptions: Tuple[Type[Exception], ...] = (Exception,)
    ):
        """
        Decorator for async functions with retry logic

        Args:
            max_retries: Maximum retry attempts
            initial_delay: Initial delay between retries
            exceptions: Exception types to retry on

        Example:
            @retry_async(max_retries=5)
            async def fetch_data(symbol):
                return await api.get_data(symbol)
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                config = RetryConfig(
                    max_retries=max_retries,
                    initial_delay=initial_delay
                )

                last_exception = None

                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)

                    except exceptions as e:
                        last_exception = e

                        if attempt >= max_retries:
                            logger.error(
                                f"Max retries ({max_retries}) exceeded for async {func.__name__}"
                            )
                            raise

                        should_retry, specific_config = RetryHandler.should_retry(e)
                        if not should_retry:
                            raise

                        config_to_use = specific_config or config
                        delay = config_to_use.calculate_delay(attempt)

                        logger.warning(
                            f"Async retry {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {delay:.2f}s"
                        )

                        # Async sleep
                        import asyncio
                        await asyncio.sleep(delay)

                if last_exception:
                    raise last_exception

            return wrapper
        return decorator


def with_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    retry_on: Optional[Tuple[Type[Exception], ...]] = None
):
    """
    Simple retry decorator with custom parameters

    Args:
        max_retries: Maximum retry attempts
        initial_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        retry_on: Exception types to retry on

    Example:
        @with_retry(max_retries=5, initial_delay=2.0)
        def risky_operation():
            return external_api_call()
    """
    config = RetryConfig(
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=max_delay
    )

    def decorator(func: Callable) -> Callable:
        return RetryHandler.retry_with_backoff(func, config, retry_on)

    return decorator


# Convenience decorators for common scenarios
def retry_on_api_error(func: Callable) -> Callable:
    """Retry on API-related errors"""
    return RetryHandler.retry_with_backoff(
        func,
        config=RetryHandler.API_RATE_LIMIT_CONFIG,
        retry_on=(APIException, ConnectionError, TimeoutError)
    )


def retry_on_timeout(func: Callable) -> Callable:
    """Retry on timeout errors"""
    return RetryHandler.retry_with_backoff(
        func,
        config=RetryHandler.API_TIMEOUT_CONFIG,
        retry_on=(APITimeoutException, TimeoutError)
    )


def retry_on_network_error(func: Callable) -> Callable:
    """Retry on network-related errors"""
    return RetryHandler.retry_with_backoff(
        func,
        config=RetryHandler.NETWORK_ERROR_CONFIG,
        retry_on=(ConnectionError, TimeoutError, APIException)
    )
