"""
Synchronized Data Manager
Ensures all data sources use consistent timestamps and are properly synchronized
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, date, timezone
from dataclasses import dataclass
from loguru import logger

from .data_versioning import DataVersionManager, DataSourceType, DataVersion
from .data_quality import DataQualityChecker, DataQualityScore


@dataclass
class SynchronizedDataset:
    """Container for synchronized data from multiple sources"""
    symbol: str
    as_of_date: datetime
    price_data: Optional[Any] = None
    fundamental_data: Optional[Dict[str, Any]] = None
    technical_data: Optional[Dict[str, Any]] = None
    news_data: Optional[List[Dict[str, Any]]] = None
    insider_data: Optional[Dict[str, Any]] = None

    # Quality metrics
    price_quality: Optional[DataQualityScore] = None
    fundamental_quality: Optional[DataQualityScore] = None

    # Versioning
    data_versions: Dict[str, DataVersion] = None

    # Synchronization metadata
    sync_warnings: List[str] = None

    def __post_init__(self):
        if self.sync_warnings is None:
            self.sync_warnings = []
        if self.data_versions is None:
            self.data_versions = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'symbol': self.symbol,
            'as_of_date': self.as_of_date.isoformat(),
            'has_price_data': self.price_data is not None,
            'has_fundamental_data': self.fundamental_data is not None,
            'has_technical_data': self.technical_data is not None,
            'has_news_data': self.news_data is not None and len(self.news_data) > 0,
            'has_insider_data': self.insider_data is not None,
            'price_quality': self.price_quality.to_dict() if self.price_quality else None,
            'fundamental_quality': self.fundamental_quality.to_dict() if self.fundamental_quality else None,
            'sync_warnings': self.sync_warnings,
            'data_versions': {k: v.to_dict() for k, v in self.data_versions.items()}
        }


class SynchronizedDataManager:
    """
    Manages synchronized data collection from multiple sources
    Ensures all data is from the same time period
    """

    def __init__(self, version_manager: Optional[DataVersionManager] = None):
        """
        Initialize synchronized data manager

        Args:
            version_manager: Data version manager instance
        """
        self.version_manager = version_manager or DataVersionManager()
        self.quality_checker = DataQualityChecker()

    def fetch_synchronized_data(
        self,
        symbol: str,
        data_manager: Any,  # Your existing data manager
        as_of_date: Optional[datetime] = None,
        max_staleness_days: int = 3
    ) -> SynchronizedDataset:
        """
        Fetch all data sources synchronized to the same date

        Args:
            symbol: Stock symbol
            data_manager: Existing data manager to fetch from
            as_of_date: Target date (default: now)
            max_staleness_days: Maximum days old for data to be acceptable

        Returns:
            SynchronizedDataset with all data sources
        """
        if as_of_date is None:
            as_of_date = datetime.now(timezone.utc)

        logger.info(f"Fetching synchronized data for {symbol} as of {as_of_date}")

        dataset = SynchronizedDataset(
            symbol=symbol,
            as_of_date=as_of_date
        )

        # 1. Fetch price data
        try:
            price_data = data_manager.get_price_data(symbol, period='1y')

            if price_data is not None and len(price_data) > 0:
                # Check data freshness
                last_date = price_data.index[-1]
                if hasattr(last_date, 'date'):
                    last_date = last_date.date()

                staleness_days = (as_of_date.date() - last_date).days

                if staleness_days > max_staleness_days:
                    dataset.sync_warnings.append(
                        f"Price data is {staleness_days} days old (max: {max_staleness_days})"
                    )

                dataset.price_data = price_data

                # Check quality
                dataset.price_quality = self.quality_checker.check_price_data_quality(
                    price_data, symbol
                )

                # Create data version
                price_version = self.version_manager.create_data_version(
                    symbol=symbol,
                    data_type='price',
                    data=price_data.to_dict() if hasattr(price_data, 'to_dict') else {},
                    source_type=DataSourceType.YAHOO_FINANCE,
                    last_updated=datetime.combine(last_date, datetime.min.time()),
                    data_points=len(price_data),
                    quality_score=dataset.price_quality.overall_score,
                    is_real_time=(staleness_days == 0),
                    is_verified=True,
                    provider='yahoo_finance'
                )
                dataset.data_versions['price'] = price_version

        except Exception as e:
            logger.error(f"Error fetching price data for {symbol}: {e}")
            dataset.sync_warnings.append(f"Price data unavailable: {str(e)}")

        # 2. Fetch fundamental data
        try:
            fundamental_data = data_manager.get_fundamental_data(symbol)

            if fundamental_data:
                dataset.fundamental_data = fundamental_data

                # Check quality
                dataset.fundamental_quality = self.quality_checker.check_fundamental_data_quality(
                    fundamental_data, symbol
                )

                # Create data version
                fund_version = self.version_manager.create_data_version(
                    symbol=symbol,
                    data_type='fundamental',
                    data=fundamental_data,
                    source_type=DataSourceType.YAHOO_FINANCE,
                    last_updated=fundamental_data.get('last_updated', as_of_date),
                    data_points=len(fundamental_data),
                    quality_score=dataset.fundamental_quality.overall_score,
                    is_verified=True,
                    provider='yahoo_finance'
                )
                dataset.data_versions['fundamental'] = fund_version

        except Exception as e:
            logger.error(f"Error fetching fundamental data for {symbol}: {e}")
            dataset.sync_warnings.append(f"Fundamental data unavailable: {str(e)}")

        # 3. Check overall synchronization
        self._check_synchronization(dataset, max_staleness_days)

        return dataset

    def _check_synchronization(self, dataset: SynchronizedDataset, max_staleness_days: int):
        """
        Check if all data sources are properly synchronized

        Args:
            dataset: SynchronizedDataset to check
            max_staleness_days: Maximum acceptable staleness
        """
        if not dataset.data_versions:
            dataset.sync_warnings.append("No data versions available")
            return

        # Get all data timestamps
        timestamps = []
        for data_type, version in dataset.data_versions.items():
            timestamps.append((data_type, version.source_metadata.last_updated))

        # Check if timestamps are close together
        if len(timestamps) > 1:
            timestamps_sorted = sorted(timestamps, key=lambda x: x[1])
            oldest = timestamps_sorted[0]
            newest = timestamps_sorted[-1]

            time_spread = (newest[1] - oldest[1]).days

            if time_spread > max_staleness_days:
                dataset.sync_warnings.append(
                    f"Data sources not synchronized: {time_spread} days between "
                    f"{oldest[0]} and {newest[0]}"
                )

    def merge_data_sources(
        self,
        dataset: SynchronizedDataset,
        prefer_source: str = 'real'
    ) -> Dict[str, Any]:
        """
        Merge data from multiple sources with conflict resolution

        Args:
            dataset: SynchronizedDataset with multiple sources
            prefer_source: Preferred source for conflicts ('real', 'ai', 'newest')

        Returns:
            Merged data dictionary
        """
        merged = {
            'symbol': dataset.symbol,
            'as_of_date': dataset.as_of_date.isoformat(),
            'data_quality': {
                'price': dataset.price_quality.to_dict() if dataset.price_quality else None,
                'fundamental': dataset.fundamental_quality.to_dict() if dataset.fundamental_quality else None
            },
            'sync_warnings': dataset.sync_warnings
        }

        # Add price data
        if dataset.price_data is not None:
            merged['price_data_points'] = len(dataset.price_data)
            merged['latest_price'] = float(dataset.price_data.iloc[-1].get('Close', 0))

        # Add fundamental data
        if dataset.fundamental_data:
            merged['fundamental'] = dataset.fundamental_data

        return merged

    def get_data_synchronization_report(
        self,
        dataset: SynchronizedDataset
    ) -> Dict[str, Any]:
        """
        Generate synchronization quality report

        Args:
            dataset: SynchronizedDataset to analyze

        Returns:
            Report dictionary
        """
        report = {
            'symbol': dataset.symbol,
            'as_of_date': dataset.as_of_date.isoformat(),
            'data_sources_available': len(dataset.data_versions),
            'data_sources': [],
            'synchronization_quality': 'unknown',
            'warnings': dataset.sync_warnings
        }

        # Analyze each data source
        for data_type, version in dataset.data_versions.items():
            metadata = version.source_metadata

            age_days = (dataset.as_of_date - metadata.last_updated).days

            report['data_sources'].append({
                'type': data_type,
                'source': metadata.source_type.value,
                'last_updated': metadata.last_updated.isoformat(),
                'age_days': age_days,
                'quality_score': metadata.quality_score,
                'is_real_time': metadata.is_real_time,
                'is_verified': metadata.is_verified,
                'data_points': metadata.data_points
            })

        # Determine overall synchronization quality
        if len(dataset.sync_warnings) == 0:
            report['synchronization_quality'] = 'excellent'
        elif len(dataset.sync_warnings) <= 2:
            report['synchronization_quality'] = 'good'
        else:
            report['synchronization_quality'] = 'poor'

        return report
