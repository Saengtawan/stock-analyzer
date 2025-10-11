"""
Core Module
Provides foundational functionality for the stock analyzer
"""

# Exceptions
from .exceptions import (
    StockAnalyzerException,
    DataException,
    DataNotFoundException,
    DataValidationException,
    DataQualityException,
    APIException,
    APIRateLimitException,
    APITimeoutException,
    APIAuthenticationException,
    APIQuotaExceededException,
    AnalysisException,
    InsufficientDataException,
    AnalysisTimeoutException,
    AIException,
    AIHallucinationDetectedException,
    AIModelException,
    ConfigurationException,
    MissingConfigException,
    InvalidConfigException
)

# Retry handling
from .retry_handler import (
    RetryConfig,
    RetryHandler,
    with_retry,
    retry_on_api_error,
    retry_on_timeout,
    retry_on_network_error
)

# Data quality and validation
from .data_quality import (
    DataQuality,
    DataSource,
    ValidationResult,
    DataQualityScore,
    DataValidator,
    DataQualityChecker
)

# Async processing
from .async_processor import (
    ConcurrentProcessor,
    AsyncProcessor,
    BatchProcessor,
    concurrent
)

# Data versioning
from .data_versioning import (
    DataSourceType,
    DataSourceMetadata,
    DataVersion,
    AnalysisVersion,
    DataVersionManager
)

# Synchronized data
from .synchronized_data import (
    SynchronizedDataset,
    SynchronizedDataManager
)

# AI confidence
from .ai_confidence import (
    ConfidenceLevel,
    ConfidenceBreakdown,
    AIConfidenceCalculator
)

# AI hallucination detection
from .ai_hallucination import (
    HallucinationDetection,
    AIHallucinationDetector
)

# Score calculation
from .score_calculator import (
    ScoreComponent,
    TransparentScoreCalculator
)

# Time horizon configuration
from .time_horizon_config import (
    TimeHorizonConfig,
    TimeHorizonManager
)

# Data source transparency
from .data_source_transparency import (
    DataSourceMetadata,
    TransparentFinancialData,
    DataSourceFactory
)

__all__ = [
    # Exceptions
    'StockAnalyzerException',
    'DataException',
    'DataNotFoundException',
    'DataValidationException',
    'DataQualityException',
    'APIException',
    'APIRateLimitException',
    'APITimeoutException',
    'APIAuthenticationException',
    'APIQuotaExceededException',
    'AnalysisException',
    'InsufficientDataException',
    'AnalysisTimeoutException',
    'AIException',
    'AIHallucinationDetectedException',
    'AIModelException',
    'ConfigurationException',
    'MissingConfigException',
    'InvalidConfigException',

    # Retry
    'RetryConfig',
    'RetryHandler',
    'with_retry',
    'retry_on_api_error',
    'retry_on_timeout',
    'retry_on_network_error',

    # Data Quality
    'DataQuality',
    'DataSource',
    'ValidationResult',
    'DataQualityScore',
    'DataValidator',
    'DataQualityChecker',

    # Async
    'ConcurrentProcessor',
    'AsyncProcessor',
    'BatchProcessor',
    'concurrent',

    # Versioning
    'DataSourceType',
    'DataSourceMetadata',
    'DataVersion',
    'AnalysisVersion',
    'DataVersionManager',

    # Synchronized Data
    'SynchronizedDataset',
    'SynchronizedDataManager',

    # AI Confidence
    'ConfidenceLevel',
    'ConfidenceBreakdown',
    'AIConfidenceCalculator',

    # AI Hallucination
    'HallucinationDetection',
    'AIHallucinationDetector',

    # Score Calculation
    'ScoreComponent',
    'TransparentScoreCalculator',

    # Time Horizon
    'TimeHorizonConfig',
    'TimeHorizonManager',

    # Data Source Transparency
    'DataSourceMetadata',
    'TransparentFinancialData',
    'DataSourceFactory'
]
