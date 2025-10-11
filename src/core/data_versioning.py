"""
Data Versioning and Metadata Tracking System
Ensures reproducibility and auditability of analyses
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from enum import Enum
import hashlib
import json


class DataSourceType(Enum):
    """Types of data sources"""
    YAHOO_FINANCE = "yahoo_finance"
    SEC_EDGAR = "sec_edgar"
    AI_GENERATED = "ai_generated"
    CACHED = "cached"
    MANUAL = "manual"


@dataclass
class DataSourceMetadata:
    """Metadata for a data source"""
    source_type: DataSourceType
    last_updated: datetime
    data_points: int
    quality_score: float  # 0-1
    is_real_time: bool = False
    is_verified: bool = False
    provider: Optional[str] = None
    api_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'source_type': self.source_type.value,
            'last_updated': self.last_updated.isoformat(),
            'data_points': self.data_points,
            'quality_score': self.quality_score,
            'is_real_time': self.is_real_time,
            'is_verified': self.is_verified,
            'provider': self.provider,
            'api_version': self.api_version
        }


@dataclass
class DataVersion:
    """Version information for dataset"""
    version_id: str  # Unique identifier (hash)
    created_at: datetime
    symbol: str
    data_type: str  # 'price', 'fundamental', 'technical', etc.
    source_metadata: DataSourceMetadata
    data_hash: str  # Hash of actual data
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'version_id': self.version_id,
            'created_at': self.created_at.isoformat(),
            'symbol': self.symbol,
            'data_type': self.data_type,
            'source_metadata': self.source_metadata.to_dict(),
            'data_hash': self.data_hash,
            'metadata': self.metadata
        }

    @staticmethod
    def generate_version_id(symbol: str, data_type: str, timestamp: datetime) -> str:
        """Generate unique version ID"""
        content = f"{symbol}:{data_type}:{timestamp.isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class AnalysisVersion:
    """Version information for complete analysis"""
    analysis_id: str
    created_at: datetime
    symbol: str
    time_horizon: str
    account_value: float
    data_versions: Dict[str, DataVersion]  # data_type -> DataVersion
    analysis_version: str  # Version of analysis code/logic
    api_version: str = "2.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'analysis_id': self.analysis_id,
            'created_at': self.created_at.isoformat(),
            'symbol': self.symbol,
            'time_horizon': self.time_horizon,
            'account_value': self.account_value,
            'data_versions': {
                k: v.to_dict() for k, v in self.data_versions.items()
            },
            'analysis_version': self.analysis_version,
            'api_version': self.api_version,
            'metadata': self.metadata,
            'reproducibility_score': self.calculate_reproducibility_score()
        }

    def calculate_reproducibility_score(self) -> float:
        """
        Calculate how reproducible this analysis is

        Returns:
            Score from 0 (not reproducible) to 1 (fully reproducible)
        """
        if not self.data_versions:
            return 0.0

        scores = []

        for data_version in self.data_versions.values():
            metadata = data_version.source_metadata

            # Real-time verified data is most reproducible
            if metadata.is_verified and metadata.is_real_time:
                scores.append(1.0)
            # Verified but not real-time
            elif metadata.is_verified:
                scores.append(0.9)
            # Real-time but not verified
            elif metadata.is_real_time:
                scores.append(0.8)
            # Cached data with good quality
            elif metadata.quality_score >= 0.8:
                scores.append(0.7)
            # AI-generated data is least reproducible
            elif metadata.source_type == DataSourceType.AI_GENERATED:
                scores.append(0.3)
            else:
                scores.append(0.5)

        return sum(scores) / len(scores) if scores else 0.0

    @staticmethod
    def generate_analysis_id(symbol: str, timestamp: datetime) -> str:
        """Generate unique analysis ID"""
        content = f"analysis:{symbol}:{timestamp.isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:20]


class DataVersionManager:
    """Manages data versioning and metadata"""

    def __init__(self, analysis_version: str = "2.0.0"):
        """
        Initialize data version manager

        Args:
            analysis_version: Version of the analysis logic
        """
        self.analysis_version = analysis_version
        self.current_versions: Dict[str, AnalysisVersion] = {}

    def create_data_version(
        self,
        symbol: str,
        data_type: str,
        data: Any,
        source_type: DataSourceType,
        last_updated: datetime,
        data_points: int,
        quality_score: float,
        is_real_time: bool = False,
        is_verified: bool = False,
        provider: Optional[str] = None
    ) -> DataVersion:
        """
        Create a data version record

        Args:
            symbol: Stock symbol
            data_type: Type of data (price, fundamental, etc.)
            data: Actual data (used for hashing)
            source_type: Type of data source
            last_updated: When data was last updated
            data_points: Number of data points
            quality_score: Quality score (0-1)
            is_real_time: Is this real-time data?
            is_verified: Is this verified/validated?
            provider: Data provider name

        Returns:
            DataVersion object
        """
        now = datetime.now(timezone.utc)

        # Create data hash
        data_str = json.dumps(data, sort_keys=True, default=str)
        data_hash = hashlib.sha256(data_str.encode()).hexdigest()[:16]

        # Create source metadata
        source_metadata = DataSourceMetadata(
            source_type=source_type,
            last_updated=last_updated,
            data_points=data_points,
            quality_score=quality_score,
            is_real_time=is_real_time,
            is_verified=is_verified,
            provider=provider,
            api_version=self.analysis_version
        )

        # Generate version ID
        version_id = DataVersion.generate_version_id(symbol, data_type, now)

        return DataVersion(
            version_id=version_id,
            created_at=now,
            symbol=symbol,
            data_type=data_type,
            source_metadata=source_metadata,
            data_hash=data_hash
        )

    def create_analysis_version(
        self,
        symbol: str,
        time_horizon: str,
        account_value: float,
        data_versions: Dict[str, DataVersion],
        metadata: Optional[Dict[str, Any]] = None
    ) -> AnalysisVersion:
        """
        Create an analysis version record

        Args:
            symbol: Stock symbol
            time_horizon: Investment time horizon
            account_value: Account value
            data_versions: Dictionary of data versions used
            metadata: Additional metadata

        Returns:
            AnalysisVersion object
        """
        now = datetime.now(timezone.utc)
        analysis_id = AnalysisVersion.generate_analysis_id(symbol, now)

        analysis_version = AnalysisVersion(
            analysis_id=analysis_id,
            created_at=now,
            symbol=symbol,
            time_horizon=time_horizon,
            account_value=account_value,
            data_versions=data_versions,
            analysis_version=self.analysis_version,
            metadata=metadata or {}
        )

        # Store current version
        self.current_versions[symbol] = analysis_version

        return analysis_version

    def get_version_summary(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get summary of current version for a symbol

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary with version summary or None
        """
        if symbol not in self.current_versions:
            return None

        version = self.current_versions[symbol]
        return version.to_dict()

    def compare_versions(
        self,
        version1: AnalysisVersion,
        version2: AnalysisVersion
    ) -> Dict[str, Any]:
        """
        Compare two analysis versions

        Args:
            version1: First version
            version2: Second version

        Returns:
            Dictionary with comparison details
        """
        differences = {
            'same_symbol': version1.symbol == version2.symbol,
            'same_time_horizon': version1.time_horizon == version2.time_horizon,
            'time_difference': abs((version1.created_at - version2.created_at).total_seconds()),
            'data_differences': []
        }

        # Compare data versions
        all_data_types = set(version1.data_versions.keys()) | set(version2.data_versions.keys())

        for data_type in all_data_types:
            v1_data = version1.data_versions.get(data_type)
            v2_data = version2.data_versions.get(data_type)

            if v1_data and v2_data:
                if v1_data.data_hash != v2_data.data_hash:
                    differences['data_differences'].append({
                        'data_type': data_type,
                        'hash_match': False,
                        'v1_last_updated': v1_data.source_metadata.last_updated.isoformat(),
                        'v2_last_updated': v2_data.source_metadata.last_updated.isoformat()
                    })
            elif v1_data:
                differences['data_differences'].append({
                    'data_type': data_type,
                    'status': 'only_in_version1'
                })
            else:
                differences['data_differences'].append({
                    'data_type': data_type,
                    'status': 'only_in_version2'
                })

        differences['is_reproducible'] = (
            differences['same_symbol'] and
            len(differences['data_differences']) == 0
        )

        return differences

    def get_data_freshness_report(self, analysis_version: AnalysisVersion) -> Dict[str, Any]:
        """
        Generate data freshness report

        Args:
            analysis_version: Analysis version to check

        Returns:
            Dictionary with freshness information
        """
        now = datetime.now(timezone.utc)
        report = {
            'analysis_date': analysis_version.created_at.isoformat(),
            'data_sources': []
        }

        for data_type, data_version in analysis_version.data_versions.items():
            last_updated = data_version.source_metadata.last_updated
            age_seconds = (now - last_updated).total_seconds()
            age_hours = age_seconds / 3600
            age_days = age_seconds / 86400

            freshness = 'excellent'
            if age_hours > 24:
                freshness = 'good'
            if age_days > 7:
                freshness = 'fair'
            if age_days > 30:
                freshness = 'stale'

            report['data_sources'].append({
                'data_type': data_type,
                'last_updated': last_updated.isoformat(),
                'age_hours': round(age_hours, 1),
                'age_days': round(age_days, 1),
                'freshness': freshness,
                'quality_score': data_version.source_metadata.quality_score,
                'is_real_time': data_version.source_metadata.is_real_time
            })

        return report

    def export_version(self, analysis_version: AnalysisVersion) -> str:
        """
        Export analysis version as JSON string

        Args:
            analysis_version: Version to export

        Returns:
            JSON string
        """
        return json.dumps(analysis_version.to_dict(), indent=2, default=str)

    @staticmethod
    def import_version(json_str: str) -> Dict[str, Any]:
        """
        Import analysis version from JSON

        Args:
            json_str: JSON string

        Returns:
            Dictionary with version data
        """
        return json.loads(json_str)
