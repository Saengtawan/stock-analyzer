"""
Data Quality and Validation Layer
Provides comprehensive data quality checks and validation
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from loguru import logger
import re


class DataQuality(Enum):
    """Data quality levels"""
    EXCELLENT = "excellent"  # Real-time, verified data
    GOOD = "good"           # Recent data, minor gaps
    FAIR = "fair"           # Some data gaps or delays
    POOR = "poor"           # Significant gaps or stale
    UNKNOWN = "unknown"     # Cannot determine quality


class DataSource(Enum):
    """Data source types"""
    YAHOO_FINANCE = "yahoo_finance"
    SEC_EDGAR = "sec_edgar"
    AI_GENERATED = "ai_generated"
    CACHED = "cached"
    UNKNOWN = "unknown"


@dataclass
class ValidationResult:
    """Result of data validation"""
    is_valid: bool
    quality: DataQuality
    errors: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'is_valid': self.is_valid,
            'quality': self.quality.value,
            'errors': self.errors,
            'warnings': self.warnings,
            'metadata': self.metadata
        }


@dataclass
class DataQualityScore:
    """Data quality score breakdown"""
    overall_score: float  # 0-1
    completeness: float   # 0-1
    freshness: float      # 0-1
    accuracy: float       # 0-1
    consistency: float    # 0-1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'overall_score': round(self.overall_score, 2),
            'completeness': round(self.completeness, 2),
            'freshness': round(self.freshness, 2),
            'accuracy': round(self.accuracy, 2),
            'consistency': round(self.consistency, 2),
            'quality_level': self._get_quality_level()
        }

    def _get_quality_level(self) -> str:
        if self.overall_score >= 0.8:
            return DataQuality.EXCELLENT.value
        elif self.overall_score >= 0.6:
            return DataQuality.GOOD.value
        elif self.overall_score >= 0.4:
            return DataQuality.FAIR.value
        else:
            return DataQuality.POOR.value


class DataValidator:
    """Validates input data and parameters"""

    # Symbol validation regex
    SYMBOL_PATTERN = re.compile(r'^[A-Z]{1,5}$')

    # Valid time horizons
    VALID_TIME_HORIZONS = ['short', 'medium', 'long']

    # Account value limits
    MIN_ACCOUNT_VALUE = 1000
    MAX_ACCOUNT_VALUE = 100_000_000

    @classmethod
    def validate_symbol(cls, symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Validate stock symbol

        Returns:
            (is_valid, error_message)
        """
        if not symbol:
            return False, "Symbol is required"

        symbol = symbol.upper().strip()

        if not cls.SYMBOL_PATTERN.match(symbol):
            return False, f"Invalid symbol format: {symbol}. Must be 1-5 uppercase letters"

        return True, None

    @classmethod
    def validate_time_horizon(cls, time_horizon: str) -> Tuple[bool, Optional[str]]:
        """Validate time horizon"""
        if not time_horizon:
            return False, "Time horizon is required"

        if time_horizon not in cls.VALID_TIME_HORIZONS:
            return False, f"Invalid time horizon: {time_horizon}. Must be one of {cls.VALID_TIME_HORIZONS}"

        return True, None

    @classmethod
    def validate_account_value(cls, value: float) -> Tuple[bool, Optional[str]]:
        """Validate account value"""
        if not isinstance(value, (int, float)):
            return False, "Account value must be a number"

        if value < cls.MIN_ACCOUNT_VALUE:
            return False, f"Account value must be at least ${cls.MIN_ACCOUNT_VALUE:,.0f}"

        if value > cls.MAX_ACCOUNT_VALUE:
            return False, f"Account value cannot exceed ${cls.MAX_ACCOUNT_VALUE:,.0f}"

        return True, None

    @classmethod
    def validate_analysis_request(cls, data: Dict[str, Any]) -> ValidationResult:
        """
        Validate complete analysis request

        Args:
            data: Request data containing symbol, time_horizon, account_value

        Returns:
            ValidationResult with validation details
        """
        errors = []
        warnings = []

        # Validate symbol
        symbol = data.get('symbol', '').upper()
        is_valid, error = cls.validate_symbol(symbol)
        if not is_valid:
            errors.append(error)

        # Validate time horizon
        time_horizon = data.get('time_horizon', 'medium')
        is_valid, error = cls.validate_time_horizon(time_horizon)
        if not is_valid:
            errors.append(error)

        # Validate account value
        account_value = data.get('account_value', 100000)
        is_valid, error = cls.validate_account_value(account_value)
        if not is_valid:
            errors.append(error)

        # Check for warnings
        if account_value < 10000:
            warnings.append("Small account size may limit diversification")

        return ValidationResult(
            is_valid=len(errors) == 0,
            quality=DataQuality.GOOD if len(errors) == 0 else DataQuality.POOR,
            errors=errors,
            warnings=warnings,
            metadata={
                'validated_at': datetime.now().isoformat(),
                'symbol': symbol,
                'time_horizon': time_horizon,
                'account_value': account_value
            }
        )


class DataQualityChecker:
    """Checks quality of market data"""

    @staticmethod
    def check_price_data_quality(
        price_data: Any,
        symbol: str,
        expected_points: int = 252
    ) -> DataQualityScore:
        """
        Check quality of price data

        Args:
            price_data: DataFrame with price data
            symbol: Stock symbol
            expected_points: Expected number of data points (default 252 = 1 year)

        Returns:
            DataQualityScore with quality metrics
        """
        if price_data is None or len(price_data) == 0:
            return DataQualityScore(
                overall_score=0.0,
                completeness=0.0,
                freshness=0.0,
                accuracy=0.0,
                consistency=0.0
            )

        # 1. Completeness: Do we have enough data points?
        actual_points = len(price_data)
        completeness = min(actual_points / expected_points, 1.0)

        # 2. Freshness: How recent is the data?
        try:
            last_date = price_data.index[-1]
            if hasattr(last_date, 'date'):
                last_date = last_date.date()

            days_old = (datetime.now().date() - last_date).days

            if days_old == 0:
                freshness = 1.0
            elif days_old <= 1:
                freshness = 0.95
            elif days_old <= 3:
                freshness = 0.8
            elif days_old <= 7:
                freshness = 0.6
            else:
                freshness = max(0.0, 0.6 - (days_old - 7) * 0.05)
        except Exception as e:
            logger.warning(f"Could not determine data freshness: {e}")
            freshness = 0.5

        # 3. Accuracy: Check for data anomalies
        accuracy = 1.0
        try:
            # Check for missing values
            close_col = None
            for col in ['Close', 'close', 'Adj Close']:
                if col in price_data.columns:
                    close_col = col
                    break

            if close_col:
                missing_pct = price_data[close_col].isna().sum() / len(price_data)
                accuracy -= missing_pct * 0.5

                # Check for zero or negative prices
                invalid_prices = (price_data[close_col] <= 0).sum()
                if invalid_prices > 0:
                    accuracy -= invalid_prices / len(price_data) * 0.3
        except Exception as e:
            logger.warning(f"Could not check price data accuracy: {e}")
            accuracy = 0.7

        # 4. Consistency: Check for data gaps
        consistency = 1.0
        try:
            # Simple check: are dates roughly consecutive?
            date_diffs = price_data.index.to_series().diff()
            # Allow up to 5 days gap (weekends + holiday)
            large_gaps = (date_diffs > timedelta(days=5)).sum()
            if large_gaps > 0:
                consistency -= large_gaps / len(price_data) * 0.3
        except Exception as e:
            logger.warning(f"Could not check data consistency: {e}")
            consistency = 0.8

        # Calculate overall score (weighted average)
        overall_score = (
            completeness * 0.3 +
            freshness * 0.3 +
            accuracy * 0.3 +
            consistency * 0.1
        )

        return DataQualityScore(
            overall_score=overall_score,
            completeness=completeness,
            freshness=freshness,
            accuracy=accuracy,
            consistency=consistency
        )

    @staticmethod
    def check_fundamental_data_quality(
        fundamental_data: Dict[str, Any],
        symbol: str
    ) -> DataQualityScore:
        """
        Check quality of fundamental data

        Args:
            fundamental_data: Dictionary with fundamental metrics
            symbol: Stock symbol

        Returns:
            DataQualityScore with quality metrics
        """
        if not fundamental_data:
            return DataQualityScore(
                overall_score=0.0,
                completeness=0.0,
                freshness=0.0,
                accuracy=0.0,
                consistency=0.0
            )

        # Key fundamental fields
        key_fields = [
            'market_cap', 'pe_ratio', 'pb_ratio', 'roe', 'roa',
            'debt_to_equity', 'revenue', 'earnings', 'profit_margin'
        ]

        # 1. Completeness: How many key fields are present?
        present_fields = sum(1 for field in key_fields if fundamental_data.get(field) is not None)
        completeness = present_fields / len(key_fields)

        # 2. Freshness: Check data timestamp
        freshness = 0.8  # Default for fundamental data (usually quarterly)
        if 'last_updated' in fundamental_data:
            try:
                last_updated = datetime.fromisoformat(str(fundamental_data['last_updated']))
                days_old = (datetime.now() - last_updated).days

                if days_old <= 90:  # Within last quarter
                    freshness = 1.0
                elif days_old <= 180:  # Within last 2 quarters
                    freshness = 0.8
                else:
                    freshness = 0.6
            except Exception:
                pass

        # 3. Accuracy: Check for reasonable values
        accuracy = 1.0

        # Check PE ratio reasonableness
        if fundamental_data.get('pe_ratio'):
            pe = fundamental_data['pe_ratio']
            if pe < 0 or pe > 1000:  # Unreasonable PE
                accuracy -= 0.2

        # Check ROE reasonableness
        if fundamental_data.get('roe'):
            roe = fundamental_data['roe']
            if roe < -100 or roe > 200:  # Unreasonable ROE
                accuracy -= 0.2

        # 4. Consistency: Check related metrics
        consistency = 1.0

        # Check if profit margin and ROE are consistent
        if fundamental_data.get('profit_margin') and fundamental_data.get('roe'):
            # These should generally have same sign
            if (fundamental_data['profit_margin'] > 0) != (fundamental_data['roe'] > 0):
                consistency -= 0.3

        overall_score = (
            completeness * 0.4 +
            freshness * 0.2 +
            accuracy * 0.3 +
            consistency * 0.1
        )

        return DataQualityScore(
            overall_score=overall_score,
            completeness=completeness,
            freshness=freshness,
            accuracy=accuracy,
            consistency=consistency
        )

    @staticmethod
    def check_overall_data_quality(
        price_quality: DataQualityScore,
        fundamental_quality: DataQualityScore,
        weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Calculate overall data quality from multiple sources

        Args:
            price_quality: Quality score for price data
            fundamental_quality: Quality score for fundamental data
            weights: Optional weights for each data type

        Returns:
            Dictionary with overall quality metrics
        """
        if weights is None:
            weights = {'price': 0.5, 'fundamental': 0.5}

        overall_score = (
            price_quality.overall_score * weights['price'] +
            fundamental_quality.overall_score * weights['fundamental']
        )

        # Determine overall quality level
        if overall_score >= 0.8:
            quality_level = DataQuality.EXCELLENT
        elif overall_score >= 0.6:
            quality_level = DataQuality.GOOD
        elif overall_score >= 0.4:
            quality_level = DataQuality.FAIR
        else:
            quality_level = DataQuality.POOR

        return {
            'overall_score': round(overall_score, 2),
            'quality_level': quality_level.value,
            'price_data': price_quality.to_dict(),
            'fundamental_data': fundamental_quality.to_dict(),
            'recommendation': DataQualityChecker._get_quality_recommendation(quality_level)
        }

    @staticmethod
    def _get_quality_recommendation(quality: DataQuality) -> str:
        """Get recommendation based on quality level"""
        recommendations = {
            DataQuality.EXCELLENT: "Data quality is excellent. Analysis results are highly reliable.",
            DataQuality.GOOD: "Data quality is good. Analysis results are generally reliable.",
            DataQuality.FAIR: "Data quality is fair. Some gaps present. Use results with caution.",
            DataQuality.POOR: "Data quality is poor. Analysis results may be unreliable.",
            DataQuality.UNKNOWN: "Data quality cannot be determined."
        }
        return recommendations.get(quality, "Unknown data quality")
