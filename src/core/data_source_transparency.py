"""
Data Source Transparency Module
Provides full transparency on where financial data comes from
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List
from loguru import logger


@dataclass
class DataSourceMetadata:
    """Metadata for data source transparency"""
    source_name: str  # "Yahoo Finance", "SEC EDGAR", "Tiingo"
    data_type: str    # "financial_statement", "market_data", "insider_trading"
    period: str       # "Q1 2024", "TTM", "2023 Annual Report"
    as_of_date: datetime
    retrieval_date: datetime
    url: Optional[str] = None
    verified: bool = False
    confidence: float = 1.0  # 0.0-1.0, how confident we are in this data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'source': self.source_name,
            'type': self.data_type,
            'period': self.period,
            'as_of': self.as_of_date.isoformat() if isinstance(self.as_of_date, datetime) else str(self.as_of_date),
            'retrieved': self.retrieval_date.isoformat() if isinstance(self.retrieval_date, datetime) else str(self.retrieval_date),
            'url': self.url,
            'verified': self.verified,
            'confidence': self.confidence
        }


class TransparentFinancialData:
    """Financial data with full source transparency"""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.data: Dict[str, Any] = {}
        self.metadata: Dict[str, DataSourceMetadata] = {}

    def add_metric(self, metric_name: str, value: Any,
                   source_metadata: DataSourceMetadata):
        """Add metric with source metadata"""
        self.data[metric_name] = value
        self.metadata[metric_name] = source_metadata

        logger.debug(f"Added {metric_name} = {value} from {source_metadata.source_name}")

    def get_metric(self, metric_name: str, default: Any = None) -> Any:
        """Get metric value (backward compatible)"""
        return self.data.get(metric_name, default)

    def get_metric_with_source(self, metric_name: str) -> Dict[str, Any]:
        """Get metric with full source information"""
        metadata = self.metadata.get(metric_name)

        return {
            'value': self.data.get(metric_name),
            'source': metadata.to_dict() if metadata else None,
            'has_source': metadata is not None
        }

    def get_all_metrics_with_sources(self) -> Dict[str, Dict[str, Any]]:
        """Get all metrics with their sources"""
        result = {}
        for metric_name in self.data.keys():
            result[metric_name] = self.get_metric_with_source(metric_name)
        return result

    def generate_data_quality_report(self) -> Dict[str, Any]:
        """Generate report on data sources and quality"""
        sources = {}
        total_confidence = 0
        verified_count = 0

        for metric, metadata in self.metadata.items():
            source = metadata.source_name
            if source not in sources:
                sources[source] = {
                    'metrics': [],
                    'count': 0,
                    'verified': 0,
                    'avg_confidence': 0.0
                }

            sources[source]['metrics'].append(metric)
            sources[source]['count'] += 1
            total_confidence += metadata.confidence

            if metadata.verified:
                sources[source]['verified'] += 1
                verified_count += 1

        # Calculate average confidence per source
        for source_data in sources.values():
            if source_data['count'] > 0:
                source_metrics = source_data['metrics']
                source_confidence = sum(
                    self.metadata[m].confidence for m in source_metrics
                )
                source_data['avg_confidence'] = round(
                    source_confidence / source_data['count'], 2
                )

        overall_confidence = (total_confidence / len(self.metadata)) if self.metadata else 0.0

        return {
            'symbol': self.symbol,
            'total_metrics': len(self.data),
            'sources_used': sources,
            'verification_status': {
                'verified': verified_count,
                'unverified': len(self.metadata) - verified_count,
                'verification_rate': round(verified_count / len(self.metadata) * 100, 1) if self.metadata else 0
            },
            'overall_confidence': round(overall_confidence, 2),
            'data_quality_score': self._calculate_data_quality_score(
                overall_confidence,
                verified_count / len(self.metadata) if self.metadata else 0
            )
        }

    def _calculate_data_quality_score(self, confidence: float,
                                     verification_rate: float) -> Dict[str, Any]:
        """Calculate overall data quality score"""
        # Weight: 60% confidence, 40% verification
        score = (confidence * 0.6) + (verification_rate * 0.4)

        if score >= 0.9:
            grade = 'A'
            description = 'Excellent'
        elif score >= 0.8:
            grade = 'B'
            description = 'Good'
        elif score >= 0.7:
            grade = 'C'
            description = 'Fair'
        elif score >= 0.6:
            grade = 'D'
            description = 'Poor'
        else:
            grade = 'F'
            description = 'Very Poor'

        return {
            'score': round(score, 2),
            'grade': grade,
            'description': description
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (backward compatible)"""
        return self.data.copy()

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like get method for backward compatibility"""
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        """Dict-like access for backward compatibility"""
        return self.data[key]

    def __contains__(self, key: str) -> bool:
        """Dict-like 'in' operator"""
        return key in self.data


class DataSourceFactory:
    """Factory for creating data source metadata"""

    @staticmethod
    def create_yahoo_finance_metadata(
        data_type: str,
        period: str = "TTM",
        as_of_date: Optional[datetime] = None
    ) -> DataSourceMetadata:
        """Create metadata for Yahoo Finance data"""
        return DataSourceMetadata(
            source_name="Yahoo Finance",
            data_type=data_type,
            period=period,
            as_of_date=as_of_date or datetime.now(),
            retrieval_date=datetime.now(),
            url="https://finance.yahoo.com",
            verified=False,  # Yahoo Finance is generally reliable but not verified
            confidence=0.85
        )

    @staticmethod
    def create_sec_edgar_metadata(
        data_type: str,
        period: str,
        filing_url: Optional[str] = None,
        as_of_date: Optional[datetime] = None
    ) -> DataSourceMetadata:
        """Create metadata for SEC EDGAR data"""
        return DataSourceMetadata(
            source_name="SEC EDGAR",
            data_type=data_type,
            period=period,
            as_of_date=as_of_date or datetime.now(),
            retrieval_date=datetime.now(),
            url=filing_url or "https://www.sec.gov/edgar",
            verified=True,  # SEC data is official
            confidence=1.0
        )

    @staticmethod
    def create_tiingo_metadata(
        data_type: str,
        period: str = "Daily",
        as_of_date: Optional[datetime] = None
    ) -> DataSourceMetadata:
        """Create metadata for Tiingo data"""
        return DataSourceMetadata(
            source_name="Tiingo",
            data_type=data_type,
            period=period,
            as_of_date=as_of_date or datetime.now(),
            retrieval_date=datetime.now(),
            url="https://www.tiingo.com",
            verified=False,
            confidence=0.90
        )

    @staticmethod
    def create_calculated_metadata(
        calculation_method: str,
        input_sources: List[str],
        as_of_date: Optional[datetime] = None
    ) -> DataSourceMetadata:
        """Create metadata for calculated/derived metrics"""
        sources_str = ", ".join(input_sources)
        return DataSourceMetadata(
            source_name=f"Calculated ({calculation_method})",
            data_type="derived_metric",
            period="N/A",
            as_of_date=as_of_date or datetime.now(),
            retrieval_date=datetime.now(),
            url=None,
            verified=False,
            confidence=0.75  # Lower confidence for derived metrics
        )


# Example usage
if __name__ == "__main__":
    # Create transparent financial data
    data = TransparentFinancialData("AAPL")

    # Add metrics with sources
    data.add_metric(
        "pe_ratio",
        28.5,
        DataSourceFactory.create_yahoo_finance_metadata(
            data_type="valuation_ratio",
            period="TTM"
        )
    )

    data.add_metric(
        "revenue",
        394_328_000_000,
        DataSourceFactory.create_sec_edgar_metadata(
            data_type="financial_statement",
            period="FY 2023",
            filing_url="https://www.sec.gov/edgar/browse/?CIK=320193"
        )
    )

    data.add_metric(
        "roe",
        1.479,
        DataSourceFactory.create_calculated_metadata(
            calculation_method="Net Income / Shareholders Equity",
            input_sources=["SEC EDGAR FY2023"]
        )
    )

    # Get metric with source
    pe_with_source = data.get_metric_with_source("pe_ratio")
    print("\nP/E Ratio with source:")
    print(f"Value: {pe_with_source['value']}")
    print(f"Source: {pe_with_source['source']['source']}")
    print(f"Period: {pe_with_source['source']['period']}")
    print(f"Confidence: {pe_with_source['source']['confidence']}")

    # Generate quality report
    quality_report = data.generate_data_quality_report()
    print("\n" + "="*60)
    print("Data Quality Report:")
    print(f"Total Metrics: {quality_report['total_metrics']}")
    print(f"Sources Used: {list(quality_report['sources_used'].keys())}")
    print(f"Verification Rate: {quality_report['verification_status']['verification_rate']}%")
    print(f"Overall Confidence: {quality_report['overall_confidence']}")
    print(f"Quality Grade: {quality_report['data_quality_score']['grade']} ({quality_report['data_quality_score']['description']})")
