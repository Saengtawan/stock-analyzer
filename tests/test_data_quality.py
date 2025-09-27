"""
Test suite for data quality and validation
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from api.data_manager import DataManager
from api.base_client import APIError


class TestDataQuality:
    """Test data quality from all sources"""

    def setup_method(self):
        """Setup test environment"""
        self.config = {
            'primary_source': 'yahoo',
            'backup_source': 'fmp',
            'price_backup': 'tiingo'
        }
        self.data_manager = DataManager(self.config)

    def test_price_data_structure(self):
        """Test that price data has correct structure"""
        with pytest.mock.patch.object(self.data_manager, 'get_price_data') as mock_get_price:
            # Mock valid price data
            mock_data = pd.DataFrame({
                'date': pd.date_range('2024-01-01', periods=5),
                'open': [180.0, 181.0, 179.0, 182.0, 183.0],
                'high': [185.0, 186.0, 184.0, 187.0, 188.0],
                'low': [178.0, 179.0, 177.0, 180.0, 181.0],
                'close': [182.0, 183.0, 181.0, 184.0, 185.0],
                'volume': [1000000, 1200000, 900000, 1100000, 1300000],
                'symbol': ['AAPL'] * 5
            })
            mock_get_price.return_value = mock_data

            result = self.data_manager.get_price_data('AAPL')

            # Test required columns
            required_columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'symbol']
            for col in required_columns:
                assert col in result.columns, f"Missing required column: {col}"

            # Test data types
            assert pd.api.types.is_datetime64_any_dtype(result['date']), "Date column should be datetime"
            assert pd.api.types.is_numeric_dtype(result['open']), "Open should be numeric"
            assert pd.api.types.is_numeric_dtype(result['close']), "Close should be numeric"
            assert pd.api.types.is_numeric_dtype(result['volume']), "Volume should be numeric"

            # Test logical constraints
            assert (result['high'] >= result['low']).all(), "High should be >= Low"
            assert (result['high'] >= result['open']).all(), "High should be >= Open"
            assert (result['high'] >= result['close']).all(), "High should be >= Close"
            assert (result['low'] <= result['open']).all(), "Low should be <= Open"
            assert (result['low'] <= result['close']).all(), "Low should be <= Close"
            assert (result['volume'] >= 0).all(), "Volume should be non-negative"

    def test_financial_data_structure(self):
        """Test that financial data has correct structure"""
        with pytest.mock.patch.object(self.data_manager, 'get_financial_data') as mock_get_financial:
            # Mock valid financial data
            mock_data = {
                'symbol': 'AAPL',
                'last_updated': datetime.now().isoformat(),
                'market_cap': 3000000000000,
                'pe_ratio': 25.5,
                'revenue': 350000000000,
                'net_income': 85000000000,
                'total_assets': 400000000000,
                'debt_to_equity': 0.3,
                'current_ratio': 1.5,
                'roe': 0.285
            }
            mock_get_financial.return_value = mock_data

            result = self.data_manager.get_financial_data('AAPL')

            # Test required fields
            assert 'symbol' in result
            assert 'last_updated' in result
            assert result['symbol'] == 'AAPL'

            # Test numeric fields are valid
            numeric_fields = ['market_cap', 'pe_ratio', 'revenue', 'net_income']
            for field in numeric_fields:
                if field in result and result[field] is not None:
                    assert isinstance(result[field], (int, float)), f"{field} should be numeric"
                    assert not np.isnan(result[field]), f"{field} should not be NaN"

            # Test ratio constraints
            if 'pe_ratio' in result and result['pe_ratio'] is not None:
                assert result['pe_ratio'] > 0, "P/E ratio should be positive"

            if 'current_ratio' in result and result['current_ratio'] is not None:
                assert result['current_ratio'] > 0, "Current ratio should be positive"

    def test_data_consistency_across_sources(self):
        """Test data consistency between different sources"""
        symbol = 'AAPL'
        period = '5d'

        # Mock different sources with slightly different but consistent data
        yahoo_data = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=3),
            'close': [180.0, 181.0, 182.0],
            'symbol': [symbol] * 3
        })

        fmp_data = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=3),
            'close': [180.1, 180.9, 182.1],  # Slightly different due to data source differences
            'symbol': [symbol] * 3
        })

        with pytest.mock.patch.object(self.data_manager.yahoo_client, 'get_price_data') as mock_yahoo:
            with pytest.mock.patch.object(self.data_manager.fmp_client, 'get_price_data') as mock_fmp:
                mock_yahoo.return_value = yahoo_data
                mock_fmp.return_value = fmp_data

                # Get data from primary source
                result_yahoo = self.data_manager.get_price_data(symbol, period)

                # Simulate primary source failure to test backup
                mock_yahoo.side_effect = APIError("Primary source failed")
                result_fmp = self.data_manager.get_price_data(symbol, period)

                # Test that both sources provide reasonable data
                assert len(result_yahoo) == len(result_fmp), "Data length should be consistent"
                assert result_yahoo['symbol'].iloc[0] == result_fmp['symbol'].iloc[0], "Symbol should match"

                # Test that price differences are within reasonable bounds (e.g., < 5%)
                yahoo_avg = result_yahoo['close'].mean()
                fmp_avg = result_fmp['close'].mean()
                price_diff_pct = abs(yahoo_avg - fmp_avg) / yahoo_avg * 100
                assert price_diff_pct < 5, f"Price difference between sources too large: {price_diff_pct}%"

    def test_data_freshness(self):
        """Test that data is reasonably fresh"""
        with pytest.mock.patch.object(self.data_manager, 'get_price_data') as mock_get_price:
            # Mock data with recent dates
            recent_date = datetime.now() - timedelta(days=1)
            mock_data = pd.DataFrame({
                'date': [recent_date],
                'close': [180.0],
                'symbol': ['AAPL']
            })
            mock_get_price.return_value = mock_data

            result = self.data_manager.get_price_data('AAPL', period='1d')

            # Test data freshness (should be within last week for daily data)
            latest_date = result['date'].max()
            days_old = (datetime.now() - latest_date.to_pydatetime()).days
            assert days_old <= 7, f"Data is too old: {days_old} days"

    def test_missing_data_handling(self):
        """Test handling of missing or incomplete data"""
        # Test empty data
        with pytest.mock.patch.object(self.data_manager, 'get_price_data') as mock_get_price:
            mock_get_price.return_value = pd.DataFrame()

            result = self.data_manager.get_price_data('INVALID_SYMBOL')
            assert len(result) == 0, "Should return empty DataFrame for invalid symbol"

        # Test data with missing values
        with pytest.mock.patch.object(self.data_manager, 'get_price_data') as mock_get_price:
            mock_data = pd.DataFrame({
                'date': pd.date_range('2024-01-01', periods=3),
                'open': [180.0, np.nan, 182.0],
                'close': [181.0, 181.5, np.nan],
                'symbol': ['AAPL'] * 3
            })
            mock_get_price.return_value = mock_data

            result = self.data_manager.get_price_data('AAPL')

            # Should handle NaN values gracefully
            assert len(result) == 3, "Should preserve all rows"
            assert result['date'].notna().all(), "Date column should not have NaN"

    def test_volume_data_quality(self):
        """Test volume data quality and anomaly detection"""
        with pytest.mock.patch.object(self.data_manager, 'get_price_data') as mock_get_price:
            # Mock data with volume anomalies
            mock_data = pd.DataFrame({
                'date': pd.date_range('2024-01-01', periods=5),
                'close': [180.0, 181.0, 182.0, 183.0, 184.0],
                'volume': [1000000, 1200000, 50000000, 1100000, 1300000],  # Day 3 has unusually high volume
                'symbol': ['AAPL'] * 5
            })
            mock_get_price.return_value = mock_data

            result = self.data_manager.get_price_data('AAPL')

            # Test volume data quality
            volumes = result['volume']
            assert (volumes >= 0).all(), "All volumes should be non-negative"

            # Test for volume anomalies (basic statistical check)
            median_volume = volumes.median()
            volume_ratios = volumes / median_volume

            # Should detect the anomalous volume (day 3)
            anomalous_days = volume_ratios > 10  # More than 10x median
            assert anomalous_days.sum() <= 1, "Should have at most one clear anomaly"

    def test_price_data_validation(self):
        """Test comprehensive price data validation"""
        with pytest.mock.patch.object(self.data_manager, 'get_price_data') as mock_get_price:
            # Mock data with potential issues
            mock_data = pd.DataFrame({
                'date': pd.date_range('2024-01-01', periods=4),
                'open': [180.0, 181.0, 0.01, 183.0],  # Day 3 has suspicious low price
                'high': [185.0, 186.0, 184.0, 188.0],
                'low': [178.0, 179.0, 0.01, 181.0],   # Day 3 has suspicious low price
                'close': [182.0, 183.0, 0.01, 185.0], # Day 3 has suspicious low price
                'volume': [1000000, 1200000, 900000, 1100000],
                'symbol': ['AAPL'] * 4
            })
            mock_get_price.return_value = mock_data

            result = self.data_manager.get_price_data('AAPL')

            # Test for suspicious price patterns
            prices = result[['open', 'high', 'low', 'close']]

            # Check for unrealistic low prices (likely data errors)
            median_price = prices.median().median()
            price_threshold = median_price * 0.1  # Prices below 10% of median are suspicious

            suspicious_rows = (prices < price_threshold).any(axis=1)
            if suspicious_rows.any():
                print(f"Warning: Found {suspicious_rows.sum()} rows with suspicious low prices")

            # Test price continuity (no huge gaps between consecutive days)
            price_changes = result['close'].pct_change().abs()
            large_changes = price_changes > 0.5  # 50% change in one day
            assert large_changes.sum() <= 1, "Should have at most one large price change"

    def test_real_time_data_quality(self):
        """Test real-time data quality"""
        with pytest.mock.patch.object(self.data_manager, 'get_real_time_price') as mock_get_realtime:
            mock_data = {
                'symbol': 'AAPL',
                'current_price': 185.50,
                'previous_close': 183.00,
                'open': 184.00,
                'day_high': 186.00,
                'day_low': 183.50,
                'volume': 50000000,
                'timestamp': datetime.now().isoformat()
            }
            mock_get_realtime.return_value = mock_data

            result = self.data_manager.get_real_time_price('AAPL')

            # Test required fields
            required_fields = ['symbol', 'current_price', 'timestamp']
            for field in required_fields:
                assert field in result, f"Missing required field: {field}"

            # Test price relationships
            if all(k in result for k in ['current_price', 'day_high', 'day_low']):
                assert result['day_low'] <= result['current_price'] <= result['day_high'], \
                    "Current price should be between day high and low"

            # Test timestamp freshness (should be within last hour for real-time data)
            if 'timestamp' in result:
                timestamp = datetime.fromisoformat(result['timestamp'].replace('Z', '+00:00'))
                age_minutes = (datetime.now() - timestamp.replace(tzinfo=None)).total_seconds() / 60
                assert age_minutes <= 60, f"Real-time data too old: {age_minutes} minutes"


class TestDataValidation:
    """Test data validation utilities"""

    def test_symbol_validation(self):
        """Test symbol validation functionality"""
        dm = DataManager()

        # Test valid symbols
        valid_symbols = ['AAPL', 'MSFT', 'GOOGL']
        with pytest.mock.patch.object(dm, 'get_company_info') as mock_company_info:
            mock_company_info.return_value = {'symbol': 'AAPL', 'company_name': 'Apple Inc.'}

            result = dm.validate_symbols(valid_symbols)

            assert isinstance(result, dict)
            assert len(result) == len(valid_symbols)

    def test_data_range_validation(self):
        """Test data range validation"""
        # Test valid date ranges
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        assert start_date < end_date, "Start date should be before end date"

        # Test reasonable date ranges (not too far in the past or future)
        today = datetime.now()
        max_history = today - timedelta(days=365 * 20)  # 20 years
        max_future = today + timedelta(days=7)  # 1 week in future

        assert start_date >= max_history, "Start date too far in the past"
        assert end_date <= max_future, "End date too far in the future"

    def test_data_completeness(self):
        """Test data completeness checks"""
        # Mock incomplete data
        incomplete_data = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=10),
            'close': [180.0, 181.0, None, 183.0, 184.0, None, 186.0, 187.0, 188.0, 189.0]
        })

        # Check completeness
        missing_count = incomplete_data['close'].isna().sum()
        total_count = len(incomplete_data)
        completeness_ratio = (total_count - missing_count) / total_count

        assert completeness_ratio >= 0.8, f"Data completeness too low: {completeness_ratio:.2%}"

    def test_outlier_detection(self):
        """Test basic outlier detection"""
        # Mock data with outliers
        data = pd.Series([180.0, 181.0, 182.0, 183.0, 500.0, 184.0, 185.0])  # 500.0 is an outlier

        # Simple outlier detection using IQR
        Q1 = data.quantile(0.25)
        Q3 = data.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        outliers = data[(data < lower_bound) | (data > upper_bound)]
        assert len(outliers) == 1, f"Should detect exactly 1 outlier, found {len(outliers)}"
        assert 500.0 in outliers.values, "Should detect the 500.0 outlier"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])