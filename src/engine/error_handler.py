"""
Unified Error Handling (Production Grade v6.21)

Provides standardized error codes, responses, and centralized error handling.

Features:
- Standard error codes (E1001-E9999)
- Error categorization (recoverable/non-recoverable)
- Consistent error response format
- Error tracking and statistics
- Integration with DLQ and monitoring

Usage:
    from engine.error_handler import TradingError, ErrorHandler, ErrorCode

    # Raise typed error
    raise TradingError(
        code=ErrorCode.ORDER_SUBMISSION_FAILED,
        message="Failed to submit order",
        context={'symbol': 'AAPL', 'qty': 10},
        recoverable=True
    )

    # Handle error centrally
    handler = ErrorHandler()
    try:
        broker.place_order(...)
    except Exception as e:
        handler.handle_error(e, context={'operation': 'place_order'})
"""

from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import traceback
from loguru import logger


class ErrorCode(Enum):
    """Standard error codes"""

    # Order errors (E1xxx)
    ORDER_VALIDATION_FAILED = "E1001"
    ORDER_SUBMISSION_FAILED = "E1002"
    ORDER_FILL_TIMEOUT = "E1003"
    ORDER_REJECTED = "E1004"
    INSUFFICIENT_BUYING_POWER = "E1005"
    POSITION_NOT_FOUND = "E1006"

    # Position errors (E2xxx)
    POSITION_SYNC_FAILED = "E2001"
    POSITION_SL_MISSING = "E2002"
    POSITION_SL_CREATION_FAILED = "E2003"
    POSITION_QUANTITY_MISMATCH = "E2004"

    # API errors (E3xxx)
    API_TIMEOUT = "E3001"
    API_RATE_LIMIT = "E3002"
    API_AUTH_FAILED = "E3003"
    API_CONNECTION_FAILED = "E3004"
    API_INVALID_RESPONSE = "E3005"

    # Data errors (E4xxx)
    DATA_FETCH_FAILED = "E4001"
    DATA_PARSE_FAILED = "E4002"
    DATA_VALIDATION_FAILED = "E4003"
    DATA_CACHE_MISS = "E4004"

    # System errors (E5xxx)
    SYSTEM_INITIALIZATION_FAILED = "E5001"
    SYSTEM_SHUTDOWN_FAILED = "E5002"
    SYSTEM_CONFIG_INVALID = "E5003"
    SYSTEM_STATE_CORRUPT = "E5004"

    # Broker errors (E6xxx)
    BROKER_UNAVAILABLE = "E6001"
    BROKER_ACCOUNT_SUSPENDED = "E6002"
    BROKER_MARKET_CLOSED = "E6003"

    # Strategy errors (E7xxx)
    STRATEGY_SIGNAL_INVALID = "E7001"
    STRATEGY_EXECUTION_FAILED = "E7002"
    STRATEGY_CONFIG_INVALID = "E7003"

    # Unknown/Generic errors (E9xxx)
    UNKNOWN_ERROR = "E9999"


@dataclass
class ErrorResponse:
    """Standard error response format"""
    code: str                    # Error code (e.g., "E1001")
    message: str                 # Human-readable error message
    recoverable: bool            # Whether error is recoverable
    context: Dict[str, Any]      # Error context (symbol, qty, etc.)
    timestamp: str               # Error timestamp
    traceback: Optional[str] = None  # Stack trace (if available)
    suggestions: Optional[list] = None  # Recovery suggestions


class TradingError(Exception):
    """
    Base exception for all trading errors

    Attributes:
        code: Error code (ErrorCode enum)
        message: Error message
        context: Additional context
        recoverable: Whether error is recoverable
        original_error: Original exception (if wrapped)
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        original_error: Optional[Exception] = None
    ):
        self.code = code
        self.message = message
        self.context = context or {}
        self.recoverable = recoverable
        self.original_error = original_error

        super().__init__(f"[{code.value}] {message}")

    def to_response(self, include_traceback: bool = False) -> ErrorResponse:
        """Convert to standard error response"""
        tb = None
        if include_traceback and self.original_error:
            tb = ''.join(traceback.format_exception(
                type(self.original_error),
                self.original_error,
                self.original_error.__traceback__
            ))

        return ErrorResponse(
            code=self.code.value,
            message=self.message,
            recoverable=self.recoverable,
            context=self.context,
            timestamp=datetime.now().isoformat(),
            traceback=tb,
            suggestions=self._get_suggestions()
        )

    def _get_suggestions(self) -> Optional[list]:
        """Get recovery suggestions based on error code"""
        suggestions = {
            ErrorCode.ORDER_VALIDATION_FAILED: [
                "Check order parameters (symbol, qty, price)",
                "Verify market hours",
                "Check buying power"
            ],
            ErrorCode.API_RATE_LIMIT: [
                "Wait 60 seconds before retrying",
                "Reduce API call frequency",
                "Check rate limiter configuration"
            ],
            ErrorCode.POSITION_SL_MISSING: [
                "Check if SL order exists in broker",
                "Manually create SL order via Alpaca UI",
                "Check auto-recovery logs"
            ],
            ErrorCode.API_TIMEOUT: [
                "Retry the operation",
                "Check network connection",
                "Verify Alpaca API status"
            ],
        }

        return suggestions.get(self.code)


class ErrorHandler:
    """
    Centralized error handler

    Features:
    - Logs all errors
    - Categorizes errors (recoverable/non-recoverable)
    - Sends to DLQ if needed
    - Tracks error statistics
    - Integrates with monitoring
    """

    def __init__(self):
        """Initialize error handler"""
        self.error_counts: Dict[str, int] = {}

        logger.info("ErrorHandler initialized")

    def handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        add_to_dlq: bool = True,
        record_metric: bool = True
    ) -> ErrorResponse:
        """
        Handle error centrally

        Args:
            error: Exception to handle
            context: Additional context
            add_to_dlq: Whether to add to DLQ (for TradingErrors with recoverable=True)
            record_metric: Whether to record in monitoring metrics

        Returns:
            ErrorResponse
        """
        # Convert to TradingError if needed
        if isinstance(error, TradingError):
            trading_error = error
        else:
            trading_error = self._convert_to_trading_error(error, context)

        # Update error counts
        self.error_counts[trading_error.code.value] = \
            self.error_counts.get(trading_error.code.value, 0) + 1

        # Log error
        log_level = logger.error if not trading_error.recoverable else logger.warning
        log_level(
            f"[{trading_error.code.value}] {trading_error.message} "
            f"(recoverable={trading_error.recoverable}, context={trading_error.context})"
        )

        # Add to DLQ if recoverable
        if add_to_dlq and trading_error.recoverable:
            try:
                from engine.dead_letter_queue import get_dlq
                dlq = get_dlq()
                dlq.add(
                    operation_type=f"error_{trading_error.code.value}",
                    operation_data=trading_error.context,
                    error=trading_error.message,
                    context={
                        'code': trading_error.code.value,
                        'recoverable': trading_error.recoverable
                    }
                )
            except Exception as e:
                logger.error(f"Failed to add error to DLQ: {e}")

        # Record in monitoring metrics
        if record_metric:
            try:
                from engine.monitoring_metrics import get_metrics_tracker
                tracker = get_metrics_tracker()

                # Record as order failure if it's an order-related error
                if trading_error.code.value.startswith('E1'):  # Order errors
                    symbol = trading_error.context.get('symbol', 'UNKNOWN')
                    tracker.record_order_attempt(
                        symbol=symbol,
                        success=False,
                        error=trading_error.message
                    )
            except Exception as e:
                logger.debug(f"Failed to record error metric: {e}")

        # Generate error response
        response = trading_error.to_response(include_traceback=True)

        return response

    def _convert_to_trading_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> TradingError:
        """
        Convert generic exception to TradingError

        Args:
            error: Original exception
            context: Additional context

        Returns:
            TradingError
        """
        error_str = str(error).lower()
        error_type = type(error).__name__

        # Map common errors to error codes
        if 'timeout' in error_str:
            code = ErrorCode.API_TIMEOUT
            recoverable = True
        elif 'rate limit' in error_str or '429' in error_str:
            code = ErrorCode.API_RATE_LIMIT
            recoverable = True
        elif 'auth' in error_str or 'unauthorized' in error_str or '401' in error_str:
            code = ErrorCode.API_AUTH_FAILED
            recoverable = False
        elif 'connection' in error_str or 'network' in error_str:
            code = ErrorCode.API_CONNECTION_FAILED
            recoverable = True
        elif 'insufficient' in error_str:
            code = ErrorCode.INSUFFICIENT_BUYING_POWER
            recoverable = False
        elif 'not found' in error_str:
            code = ErrorCode.POSITION_NOT_FOUND
            recoverable = True
        elif 'validation' in error_str or 'invalid' in error_str:
            code = ErrorCode.ORDER_VALIDATION_FAILED
            recoverable = False
        else:
            code = ErrorCode.UNKNOWN_ERROR
            recoverable = True

        return TradingError(
            code=code,
            message=str(error),
            context=context or {'error_type': error_type},
            recoverable=recoverable,
            original_error=error
        )

    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get error statistics

        Returns:
            Statistics dictionary
        """
        total_errors = sum(self.error_counts.values())

        return {
            'total_errors': total_errors,
            'error_counts': self.error_counts,
            'most_common': sorted(
                self.error_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]  # Top 10 most common errors
        }

    def reset_statistics(self):
        """Reset error statistics"""
        self.error_counts = {}
        logger.info("Error statistics reset")


# =========================================================================
# GLOBAL ERROR HANDLER
# =========================================================================

_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """Get global error handler instance"""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler()
    return _error_handler


# =========================================================================
# CONVENIENCE DECORATORS
# =========================================================================

def handle_errors(operation_name: str = "operation", add_to_dlq: bool = True):
    """
    Decorator to handle errors in functions

    Usage:
        @handle_errors(operation_name="place_order")
        def place_order(symbol, qty):
            # ... code that might raise errors ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handler = get_error_handler()
                context = {
                    'operation': operation_name,
                    'function': func.__name__,
                    'args': str(args),
                    'kwargs': str(kwargs)
                }
                error_response = handler.handle_error(e, context, add_to_dlq)

                # Re-raise if non-recoverable
                if not error_response.recoverable:
                    raise

                # Return None if recoverable
                logger.warning(f"Recoverable error handled, returning None")
                return None

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


# =========================================================================
# EXAMPLE USAGE
# =========================================================================

if __name__ == '__main__':
    print("🧪 Testing Unified Error Handling...")

    # Test 1: Trading error
    print("\n1. TradingError:")
    try:
        raise TradingError(
            code=ErrorCode.ORDER_SUBMISSION_FAILED,
            message="Failed to submit order - API timeout",
            context={'symbol': 'AAPL', 'qty': 10},
            recoverable=True
        )
    except TradingError as e:
        print(f"   Code: {e.code.value}")
        print(f"   Message: {e.message}")
        print(f"   Recoverable: {e.recoverable}")
        response = e.to_response()
        print(f"   Suggestions: {response.suggestions}")

    # Test 2: Error handler
    print("\n2. Error handler:")
    handler = ErrorHandler()

    try:
        # Simulate API error
        raise TimeoutError("API request timed out after 30s")
    except Exception as e:
        response = handler.handle_error(
            e,
            context={'operation': 'get_account', 'broker': 'alpaca'},
            add_to_dlq=False  # Skip DLQ for test
        )
        print(f"   Handled: {response.code} - {response.message}")
        print(f"   Recoverable: {response.recoverable}")
        print(f"   Suggestions: {response.suggestions}")

    # Test 3: Error statistics
    print("\n3. Error statistics:")
    stats = handler.get_error_statistics()
    print(f"   Total errors: {stats['total_errors']}")
    print(f"   Error counts: {stats['error_counts']}")

    # Test 4: Error decorator
    print("\n4. Error decorator:")

    @handle_errors(operation_name="test_operation")
    def risky_function():
        raise ValueError("Invalid input")

    result = risky_function()  # Will handle error and return None
    print(f"   Result: {result}")

    print("\n✅ Tests complete!")
