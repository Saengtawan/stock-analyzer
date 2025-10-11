"""
Custom Exceptions for Stock Analyzer
Provides granular error handling
"""
from typing import Optional, Dict, Any


class StockAnalyzerException(Exception):
    """Base exception for all stock analyzer errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'details': self.details
        }


# Data-related exceptions
class DataException(StockAnalyzerException):
    """Base exception for data-related errors"""
    pass


class DataNotFoundException(DataException):
    """Raised when required data is not found"""

    def __init__(self, symbol: str, data_type: str = "data"):
        message = f"No {data_type} available for symbol: {symbol}"
        super().__init__(message, {'symbol': symbol, 'data_type': data_type})
        self.symbol = symbol
        self.data_type = data_type


class DataValidationException(DataException):
    """Raised when data validation fails"""

    def __init__(self, message: str, field: str, value: Any):
        super().__init__(message, {'field': field, 'value': value})
        self.field = field
        self.value = value


class DataQualityException(DataException):
    """Raised when data quality is too poor"""

    def __init__(self, message: str, quality_score: float, threshold: float):
        super().__init__(
            message,
            {'quality_score': quality_score, 'threshold': threshold}
        )
        self.quality_score = quality_score
        self.threshold = threshold


# API-related exceptions
class APIException(StockAnalyzerException):
    """Base exception for API-related errors"""
    pass


class APIRateLimitException(APIException):
    """Raised when API rate limit is exceeded"""

    def __init__(self, service: str, retry_after: Optional[int] = None):
        message = f"API rate limit exceeded for {service}"
        if retry_after:
            message += f". Retry after {retry_after} seconds"

        super().__init__(message, {
            'service': service,
            'retry_after': retry_after,
            'action': 'Please wait and try again later'
        })
        self.service = service
        self.retry_after = retry_after


class APITimeoutException(APIException):
    """Raised when API request times out"""

    def __init__(self, service: str, timeout: int):
        message = f"API request timed out for {service} after {timeout} seconds"
        super().__init__(message, {
            'service': service,
            'timeout': timeout,
            'action': 'Try again or check your connection'
        })
        self.service = service
        self.timeout = timeout


class APIAuthenticationException(APIException):
    """Raised when API authentication fails"""

    def __init__(self, service: str):
        message = f"Authentication failed for {service}"
        super().__init__(message, {
            'service': service,
            'action': 'Check API credentials in configuration'
        })
        self.service = service


class APIQuotaExceededException(APIException):
    """Raised when API quota is exceeded"""

    def __init__(self, service: str, reset_time: Optional[str] = None):
        message = f"API quota exceeded for {service}"
        if reset_time:
            message += f". Quota resets at {reset_time}"

        super().__init__(message, {
            'service': service,
            'reset_time': reset_time,
            'action': 'Wait for quota reset or upgrade plan'
        })
        self.service = service
        self.reset_time = reset_time


# Analysis-related exceptions
class AnalysisException(StockAnalyzerException):
    """Base exception for analysis-related errors"""
    pass


class InsufficientDataException(AnalysisException):
    """Raised when there's insufficient data for analysis"""

    def __init__(self, symbol: str, required_points: int, available_points: int):
        message = f"Insufficient data for {symbol}. Required: {required_points}, Available: {available_points}"
        super().__init__(message, {
            'symbol': symbol,
            'required_points': required_points,
            'available_points': available_points
        })
        self.symbol = symbol
        self.required_points = required_points
        self.available_points = available_points


class AnalysisTimeoutException(AnalysisException):
    """Raised when analysis takes too long"""

    def __init__(self, symbol: str, timeout: int):
        message = f"Analysis timeout for {symbol} after {timeout} seconds"
        super().__init__(message, {
            'symbol': symbol,
            'timeout': timeout,
            'action': 'Try again or simplify analysis parameters'
        })
        self.symbol = symbol
        self.timeout = timeout


# AI-related exceptions
class AIException(StockAnalyzerException):
    """Base exception for AI-related errors"""
    pass


class AIHallucinationDetectedException(AIException):
    """Raised when AI hallucination is detected"""

    def __init__(self, field: str, ai_value: Any, real_value: Any, confidence: float):
        message = f"AI hallucination detected for {field}"
        super().__init__(message, {
            'field': field,
            'ai_value': ai_value,
            'real_value': real_value,
            'confidence': confidence,
            'action': 'Using real data instead of AI-generated data'
        })
        self.field = field
        self.ai_value = ai_value
        self.real_value = real_value
        self.confidence = confidence


class AIModelException(AIException):
    """Raised when AI model encounters an error"""

    def __init__(self, model_name: str, error_message: str):
        message = f"AI model error ({model_name}): {error_message}"
        super().__init__(message, {
            'model': model_name,
            'error': error_message
        })
        self.model_name = model_name
        self.error_message = error_message


# Configuration exceptions
class ConfigurationException(StockAnalyzerException):
    """Base exception for configuration errors"""
    pass


class MissingConfigException(ConfigurationException):
    """Raised when required configuration is missing"""

    def __init__(self, config_key: str):
        message = f"Missing required configuration: {config_key}"
        super().__init__(message, {
            'config_key': config_key,
            'action': 'Check .env file or environment variables'
        })
        self.config_key = config_key


class InvalidConfigException(ConfigurationException):
    """Raised when configuration value is invalid"""

    def __init__(self, config_key: str, value: Any, reason: str):
        message = f"Invalid configuration for {config_key}: {reason}"
        super().__init__(message, {
            'config_key': config_key,
            'value': value,
            'reason': reason
        })
        self.config_key = config_key
        self.value = value
        self.reason = reason
