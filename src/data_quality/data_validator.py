"""
Data Quality Validation and Enhancement Module
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger
import warnings
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest


class DataQualityValidator:
    """Comprehensive data quality validation and enhancement"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.quality_thresholds = {
            'completeness_threshold': 0.95,  # 95% data completeness required
            'price_change_threshold': 0.50,  # 50% max daily price change
            'volume_anomaly_threshold': 10.0,  # 10x median volume
            'price_variance_threshold': 3.0,  # 3 standard deviations
            'outlier_contamination': 0.05,  # 5% outlier tolerance
            'min_trading_days': 20,  # Minimum trading days for analysis
            'zero_volume_threshold': 0.01  # 1% zero volume tolerance
        }
        self.quality_metrics = {}

    def validate_price_data(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """
        Comprehensive price data validation

        Args:
            df: Price data DataFrame
            symbol: Stock symbol

        Returns:
            Validation results and quality metrics
        """
        logger.info(f"Validating price data for {symbol}")

        validation_results = {
            'symbol': symbol,
            'total_records': len(df),
            'validation_passed': True,
            'warnings': [],
            'errors': [],
            'quality_score': 100.0,
            'metrics': {}
        }

        if df.empty:
            validation_results['errors'].append("Empty dataset")
            validation_results['validation_passed'] = False
            validation_results['quality_score'] = 0.0
            return validation_results

        # 1. Data Structure Validation
        structure_result = self._validate_structure(df)
        validation_results['metrics']['structure'] = structure_result
        if not structure_result['valid']:
            validation_results['errors'].extend(structure_result['errors'])
            validation_results['validation_passed'] = False

        # 2. Data Completeness Check
        completeness_result = self._check_completeness(df)
        validation_results['metrics']['completeness'] = completeness_result
        if completeness_result['score'] < self.quality_thresholds['completeness_threshold']:
            validation_results['warnings'].append(
                f"Data completeness below threshold: {completeness_result['score']:.2%}"
            )
            validation_results['quality_score'] -= 20

        # 3. Price Logic Validation
        price_logic_result = self._validate_price_logic(df)
        validation_results['metrics']['price_logic'] = price_logic_result
        if not price_logic_result['valid']:
            validation_results['errors'].extend(price_logic_result['errors'])
            validation_results['validation_passed'] = False

        # 4. Anomaly Detection
        anomaly_result = self._detect_anomalies(df)
        validation_results['metrics']['anomalies'] = anomaly_result
        if anomaly_result['anomaly_count'] > 0:
            validation_results['warnings'].append(
                f"Found {anomaly_result['anomaly_count']} potential anomalies"
            )

        # 5. Time Series Continuity
        continuity_result = self._check_continuity(df)
        validation_results['metrics']['continuity'] = continuity_result
        if continuity_result['gaps'] > 0:
            validation_results['warnings'].append(
                f"Found {continuity_result['gaps']} data gaps"
            )

        # 6. Volume Analysis
        volume_result = self._validate_volume_data(df)
        validation_results['metrics']['volume'] = volume_result
        if not volume_result['valid']:
            validation_results['warnings'].extend(volume_result['warnings'])

        # Calculate final quality score
        validation_results['quality_score'] = self._calculate_quality_score(validation_results)

        logger.info(f"Validation complete for {symbol}: Quality Score = {validation_results['quality_score']:.1f}")
        return validation_results

    def clean_price_data(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Clean and enhance price data quality

        Args:
            df: Raw price data
            symbol: Stock symbol

        Returns:
            Cleaned DataFrame
        """
        logger.info(f"Cleaning price data for {symbol}")

        if df.empty:
            return df

        cleaned_df = df.copy()

        # 1. Remove duplicates
        cleaned_df = cleaned_df.drop_duplicates(subset=['date'], keep='last')

        # 2. Sort by date
        cleaned_df = cleaned_df.sort_values('date').reset_index(drop=True)

        # 3. Handle missing values
        cleaned_df = self._handle_missing_values(cleaned_df)

        # 4. Fix price anomalies
        cleaned_df = self._fix_price_anomalies(cleaned_df)

        # 5. Validate and fix OHLC relationships
        cleaned_df = self._fix_ohlc_relationships(cleaned_df)

        # 6. Handle volume anomalies
        cleaned_df = self._clean_volume_data(cleaned_df)

        # 7. Add data quality flags
        cleaned_df = self._add_quality_flags(cleaned_df, df)

        logger.info(f"Data cleaning complete for {symbol}: {len(df)} -> {len(cleaned_df)} records")
        return cleaned_df

    def validate_fundamental_data(self, data: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """
        Validate fundamental data quality

        Args:
            data: Fundamental data dictionary
            symbol: Stock symbol

        Returns:
            Validation results
        """
        validation_results = {
            'symbol': symbol,
            'validation_passed': True,
            'warnings': [],
            'errors': [],
            'quality_score': 100.0,
            'metrics': {}
        }

        # 1. Required fields check
        required_fields = ['revenue', 'net_income', 'total_assets', 'market_cap']
        missing_fields = [field for field in required_fields if field not in data or data[field] is None]

        if missing_fields:
            validation_results['warnings'].append(f"Missing fundamental fields: {missing_fields}")
            validation_results['quality_score'] -= len(missing_fields) * 10

        # 2. Logical consistency checks
        logical_checks = self._check_fundamental_logic(data)
        validation_results['metrics']['logical_consistency'] = logical_checks

        if not logical_checks['valid']:
            validation_results['warnings'].extend(logical_checks['warnings'])
            validation_results['quality_score'] -= 15

        # 3. Ratio validation
        ratio_checks = self._validate_financial_ratios(data)
        validation_results['metrics']['ratios'] = ratio_checks

        if not ratio_checks['valid']:
            validation_results['warnings'].extend(ratio_checks['warnings'])
            validation_results['quality_score'] -= 10

        return validation_results

    def cross_validate_sources(self, primary_data: pd.DataFrame,
                              backup_data: pd.DataFrame,
                              symbol: str) -> Dict[str, Any]:
        """
        Cross-validate data between different sources

        Args:
            primary_data: Data from primary source
            backup_data: Data from backup source
            symbol: Stock symbol

        Returns:
            Cross-validation results
        """
        logger.info(f"Cross-validating data sources for {symbol}")

        results = {
            'symbol': symbol,
            'correlation': 0.0,
            'price_difference_pct': 0.0,
            'data_agreement': 'unknown',
            'recommendation': 'use_primary',
            'warnings': []
        }

        if primary_data.empty or backup_data.empty:
            results['warnings'].append("One or both data sources are empty")
            return results

        # Align data by date
        merged = pd.merge(primary_data, backup_data, on='date', suffixes=('_primary', '_backup'))

        if merged.empty:
            results['warnings'].append("No overlapping dates between sources")
            return results

        # Calculate correlation
        if 'close_primary' in merged.columns and 'close_backup' in merged.columns:
            correlation = merged['close_primary'].corr(merged['close_backup'])
            results['correlation'] = correlation if not np.isnan(correlation) else 0.0

        # Calculate price differences
        if 'close_primary' in merged.columns and 'close_backup' in merged.columns:
            price_diff = abs(merged['close_primary'] - merged['close_backup'])
            avg_price = (merged['close_primary'] + merged['close_backup']) / 2
            price_diff_pct = (price_diff / avg_price * 100).mean()
            results['price_difference_pct'] = price_diff_pct

        # Determine data agreement level
        if results['correlation'] > 0.95 and results['price_difference_pct'] < 2.0:
            results['data_agreement'] = 'excellent'
        elif results['correlation'] > 0.90 and results['price_difference_pct'] < 5.0:
            results['data_agreement'] = 'good'
        elif results['correlation'] > 0.80 and results['price_difference_pct'] < 10.0:
            results['data_agreement'] = 'fair'
        else:
            results['data_agreement'] = 'poor'
            results['recommendation'] = 'investigate'
            results['warnings'].append("Significant disagreement between data sources")

        return results

    def _validate_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate DataFrame structure"""
        required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]

        result = {
            'valid': len(missing_columns) == 0,
            'missing_columns': missing_columns,
            'errors': []
        }

        if missing_columns:
            result['errors'].append(f"Missing required columns: {missing_columns}")

        # Check data types
        if 'date' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['date']):
            result['errors'].append("Date column is not datetime type")
            result['valid'] = False

        return result

    def _check_completeness(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Check data completeness"""
        total_records = len(df)
        if total_records == 0:
            return {'score': 0.0, 'missing_count': 0, 'total_count': 0}

        # Count missing values in critical columns
        critical_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_count = 0

        for col in critical_columns:
            if col in df.columns:
                missing_count += df[col].isna().sum()

        total_values = total_records * len(critical_columns)
        completeness_score = (total_values - missing_count) / total_values if total_values > 0 else 0.0

        return {
            'score': completeness_score,
            'missing_count': missing_count,
            'total_count': total_values
        }

    def _validate_price_logic(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate price logic (High >= Low, etc.)"""
        result = {'valid': True, 'errors': []}

        if len(df) == 0:
            return result

        # Check OHLC relationships
        if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
            invalid_high_low = (df['high'] < df['low']).sum()
            if invalid_high_low > 0:
                result['errors'].append(f"{invalid_high_low} records where High < Low")
                result['valid'] = False

            invalid_high_open = (df['high'] < df['open']).sum()
            invalid_high_close = (df['high'] < df['close']).sum()
            invalid_low_open = (df['low'] > df['open']).sum()
            invalid_low_close = (df['low'] > df['close']).sum()

            total_violations = invalid_high_open + invalid_high_close + invalid_low_open + invalid_low_close
            if total_violations > 0:
                result['errors'].append(f"{total_violations} OHLC relationship violations")
                result['valid'] = False

        # Check for negative prices
        price_columns = ['open', 'high', 'low', 'close']
        for col in price_columns:
            if col in df.columns:
                negative_prices = (df[col] <= 0).sum()
                if negative_prices > 0:
                    result['errors'].append(f"{negative_prices} negative/zero prices in {col}")
                    result['valid'] = False

        return result

    def _detect_anomalies(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect price and volume anomalies"""
        result = {
            'anomaly_count': 0,
            'price_anomalies': 0,
            'volume_anomalies': 0,
            'anomaly_indices': []
        }

        if len(df) < 10:  # Need sufficient data for anomaly detection
            return result

        # Price anomaly detection using Isolation Forest
        if 'close' in df.columns:
            price_data = df[['close']].ffill()
            if len(price_data.dropna()) > 5:
                iso_forest = IsolationForest(contamination=self.quality_thresholds['outlier_contamination'])
                anomalies = iso_forest.fit_predict(price_data.fillna(price_data.mean()))
                price_anomaly_indices = np.where(anomalies == -1)[0]
                result['price_anomalies'] = len(price_anomaly_indices)
                result['anomaly_indices'].extend(price_anomaly_indices.tolist())

        # Volume anomaly detection
        if 'volume' in df.columns:
            volumes = df['volume'].fillna(0)
            if len(volumes) > 5:
                median_volume = volumes.median()
                if median_volume > 0:
                    volume_ratios = volumes / median_volume
                    volume_anomalies = volume_ratios > self.quality_thresholds['volume_anomaly_threshold']
                    result['volume_anomalies'] = volume_anomalies.sum()

        result['anomaly_count'] = result['price_anomalies'] + result['volume_anomalies']
        return result

    def _check_continuity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Check time series continuity"""
        result = {'gaps': 0, 'gap_dates': []}

        if len(df) < 2 or 'date' not in df.columns:
            return result

        df_sorted = df.sort_values('date')
        dates = pd.to_datetime(df_sorted['date'])

        # Check for gaps (more than 3 days for daily data)
        date_diffs = dates.diff().dt.days
        gaps = date_diffs > 3  # More than 3 days gap

        result['gaps'] = gaps.sum()
        if result['gaps'] > 0:
            gap_indices = np.where(gaps)[0]
            result['gap_dates'] = dates.iloc[gap_indices].dt.strftime('%Y-%m-%d').tolist()

        return result

    def _validate_volume_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate volume data"""
        result = {'valid': True, 'warnings': []}

        if 'volume' not in df.columns:
            result['warnings'].append("No volume data available")
            return result

        volumes = df['volume'].fillna(0)

        # Check for negative volumes
        negative_volumes = (volumes < 0).sum()
        if negative_volumes > 0:
            result['warnings'].append(f"{negative_volumes} negative volume records")
            result['valid'] = False

        # Check for excessive zero volumes
        zero_volumes = (volumes == 0).sum()
        zero_volume_ratio = zero_volumes / len(volumes) if len(volumes) > 0 else 0

        if zero_volume_ratio > self.quality_thresholds['zero_volume_threshold']:
            result['warnings'].append(f"High zero volume ratio: {zero_volume_ratio:.2%}")

        return result

    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """Handle missing values in price data"""
        if df.empty:
            return df

        # Forward fill for price data (use last known price)
        price_columns = ['open', 'high', 'low', 'close']
        for col in price_columns:
            if col in df.columns:
                df[col] = df[col].ffill()

        # Volume: fill with 0 or median
        if 'volume' in df.columns:
            median_volume = df['volume'].median()
            df['volume'] = df['volume'].fillna(median_volume if not np.isnan(median_volume) else 0)

        return df

    def _fix_price_anomalies(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fix obvious price anomalies"""
        if df.empty:
            return df

        # Remove records with impossible price relationships
        price_columns = ['open', 'high', 'low', 'close']
        if all(col in df.columns for col in price_columns):
            # Fix high < low
            invalid_mask = df['high'] < df['low']
            if invalid_mask.any():
                logger.warning(f"Fixing {invalid_mask.sum()} records where high < low")
                # Swap high and low values
                df.loc[invalid_mask, ['high', 'low']] = df.loc[invalid_mask, ['low', 'high']].values

        return df

    def _fix_ohlc_relationships(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure OHLC relationships are logical"""
        if df.empty:
            return df

        price_columns = ['open', 'high', 'low', 'close']
        if all(col in df.columns for col in price_columns):
            # Ensure high is the maximum and low is the minimum
            df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
            df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)

        return df

    def _clean_volume_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean volume data"""
        if 'volume' not in df.columns:
            return df

        # Set negative volumes to 0
        df.loc[df['volume'] < 0, 'volume'] = 0

        # Cap extremely high volumes (potential data errors)
        if len(df) > 10:
            median_volume = df['volume'].median()
            max_reasonable_volume = median_volume * 50  # 50x median is maximum reasonable
            df.loc[df['volume'] > max_reasonable_volume, 'volume'] = max_reasonable_volume

        return df

    def _add_quality_flags(self, cleaned_df: pd.DataFrame, original_df: pd.DataFrame) -> pd.DataFrame:
        """Add data quality flags"""
        cleaned_df['data_quality_flag'] = 'clean'

        # Mark interpolated records
        for col in ['open', 'high', 'low', 'close']:
            if col in original_df.columns and col in cleaned_df.columns:
                interpolated_mask = original_df[col].isna() & cleaned_df[col].notna()
                cleaned_df.loc[interpolated_mask, 'data_quality_flag'] = 'interpolated'

        return cleaned_df

    def _check_fundamental_logic(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Check fundamental data logical consistency"""
        result = {'valid': True, 'warnings': []}

        # Revenue should be positive
        if 'revenue' in data and data['revenue'] is not None:
            if data['revenue'] < 0:
                result['warnings'].append("Negative revenue")
                result['valid'] = False

        # Assets should be greater than equity
        if all(k in data and data[k] is not None for k in ['total_assets', 'shareholders_equity']):
            if data['total_assets'] < data['shareholders_equity']:
                result['warnings'].append("Total assets less than shareholders equity")
                result['valid'] = False

        # Market cap should be reasonable
        if 'market_cap' in data and data['market_cap'] is not None:
            if data['market_cap'] <= 0:
                result['warnings'].append("Invalid market cap")
                result['valid'] = False

        return result

    def _validate_financial_ratios(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate financial ratios for reasonableness"""
        result = {'valid': True, 'warnings': []}

        # P/E ratio should be reasonable
        if 'pe_ratio' in data and data['pe_ratio'] is not None:
            if data['pe_ratio'] < 0 or data['pe_ratio'] > 1000:
                result['warnings'].append(f"Unusual P/E ratio: {data['pe_ratio']}")

        # Current ratio should be positive
        if 'current_ratio' in data and data['current_ratio'] is not None:
            if data['current_ratio'] < 0:
                result['warnings'].append("Negative current ratio")
                result['valid'] = False

        # ROE should be between -100% and 100%
        if 'roe' in data and data['roe'] is not None:
            if abs(data['roe']) > 1.0:
                result['warnings'].append(f"Unusual ROE: {data['roe']:.2%}")

        return result

    def _calculate_quality_score(self, validation_results: Dict[str, Any]) -> float:
        """Calculate overall data quality score"""
        base_score = validation_results['quality_score']

        # Deduct points for errors and warnings
        error_penalty = len(validation_results['errors']) * 15
        warning_penalty = len(validation_results['warnings']) * 5

        final_score = max(0.0, base_score - error_penalty - warning_penalty)
        return final_score

    def generate_quality_report(self, validation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate comprehensive data quality report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_symbols': len(validation_results),
            'overall_quality_score': 0.0,
            'symbols_passed': 0,
            'symbols_failed': 0,
            'common_issues': {},
            'recommendations': []
        }

        if not validation_results:
            return report

        # Calculate overall metrics
        total_score = sum(r['quality_score'] for r in validation_results)
        report['overall_quality_score'] = total_score / len(validation_results)

        report['symbols_passed'] = sum(1 for r in validation_results if r['validation_passed'])
        report['symbols_failed'] = len(validation_results) - report['symbols_passed']

        # Identify common issues
        all_warnings = []
        all_errors = []

        for result in validation_results:
            all_warnings.extend(result['warnings'])
            all_errors.extend(result['errors'])

        # Count issue frequencies
        from collections import Counter
        warning_counts = Counter(all_warnings)
        error_counts = Counter(all_errors)

        report['common_issues'] = {
            'frequent_warnings': dict(warning_counts.most_common(5)),
            'frequent_errors': dict(error_counts.most_common(5))
        }

        # Generate recommendations
        if report['overall_quality_score'] < 80:
            report['recommendations'].append("Overall data quality is below recommended threshold")

        if report['symbols_failed'] > 0:
            report['recommendations'].append(f"Review {report['symbols_failed']} failed symbols")

        if 'Missing fundamental fields' in str(warning_counts):
            report['recommendations'].append("Consider additional data sources for fundamental data")

        return report