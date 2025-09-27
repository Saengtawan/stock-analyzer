"""
Test suite for API clients (FMP and Tiingo)
"""
import pytest
import os
import pandas as pd
from unittest.mock import Mock, patch
from datetime import datetime

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from api.fmp_client import FMPClient
from api.tiingo_client import TiingoClient
from api.data_manager import DataManager
from api.base_client import APIError


class TestFMPClient:
    """Test Financial Modeling Prep client"""

    def setup_method(self):
        """Setup test environment"""
        self.api_key = os.getenv('FMP_API_KEY', 'test_key')
        self.client = FMPClient(self.api_key)

    def test_client_initialization(self):
        """Test client initialization"""
        assert self.client.api_key == self.api_key
        assert self.client.rate_limit == 300
        assert self.client.base_url == "https://financialmodelingprep.com/api/v3"

    @patch('api.fmp_client.FMPClient._make_request')
    def test_get_price_data_success(self, mock_request):
        """Test successful price data retrieval"""
        mock_data = [
            {
                'date': '2024-01-01',
                'open': 180.0,
                'high': 185.0,
                'low': 178.0,
                'close': 182.0,
                'volume': 1000000
            },
            {
                'date': '2024-01-02',
                'open': 182.0,
                'high': 187.0,
                'low': 181.0,
                'close': 185.0,
                'volume': 1200000
            }
        ]

        mock_request.return_value = {'historical': mock_data}

        result = self.client.get_price_data('AAPL', period='5d')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert 'date' in result.columns
        assert 'open' in result.columns
        assert 'close' in result.columns
        assert 'symbol' in result.columns
        assert result['symbol'].iloc[0] == 'AAPL'

    @patch('api.fmp_client.FMPClient._make_request')
    def test_get_financial_data_success(self, mock_request):
        """Test successful financial data retrieval"""
        # Mock responses for different endpoints
        mock_responses = {
            'key-metrics': [{'marketCap': 3000000000000, 'peRatio': 25.5}],
            'ratios': [{'currentRatio': 1.5, 'debtEquityRatio': 0.3}],
            'income-statement': [{'revenue': 350000000000, 'netIncome': 85000000000}],
            'balance-sheet-statement': [{'totalAssets': 400000000000}],
            'cash-flow-statement': [{'netCashProvidedByOperatingActivities': 90000000000}],
            'profile': [{'companyName': 'Apple Inc.', 'sector': 'Technology'}]
        }

        def side_effect(url, params):
            for endpoint, response in mock_responses.items():
                if endpoint in url:
                    return response
            return {}

        mock_request.side_effect = side_effect

        result = self.client.get_financial_data('AAPL')

        assert isinstance(result, dict)
        assert 'symbol' in result
        assert 'market_cap' in result
        assert result['symbol'] == 'AAPL'

    @patch('api.fmp_client.FMPClient._make_request')
    def test_get_real_time_price_success(self, mock_request):
        """Test successful real-time price retrieval"""
        mock_data = [{
            'price': 185.50,
            'previousClose': 183.00,
            'open': 184.00,
            'dayHigh': 186.00,
            'dayLow': 183.50,
            'volume': 50000000
        }]

        mock_request.return_value = mock_data

        result = self.client.get_real_time_price('AAPL')

        assert isinstance(result, dict)
        assert 'current_price' in result
        assert 'symbol' in result
        assert result['symbol'] == 'AAPL'
        assert result['current_price'] == 185.50

    @patch('api.fmp_client.FMPClient._make_request')
    def test_api_error_handling(self, mock_request):
        """Test API error handling"""
        mock_request.return_value = {'Error Message': 'Invalid API key'}

        with pytest.raises(APIError):
            self.client.get_price_data('AAPL')

    def test_invalid_interval(self):
        """Test invalid interval handling"""
        with pytest.raises(APIError):
            self.client.get_price_data('AAPL', interval='invalid')


class TestTiingoClient:
    """Test Tiingo client"""

    def setup_method(self):
        """Setup test environment"""
        self.api_key = os.getenv('TIINGO_API_KEY', 'test_key')
        self.client = TiingoClient(self.api_key)

    def test_client_initialization(self):
        """Test client initialization"""
        assert self.client.api_key == self.api_key
        assert self.client.rate_limit == 500
        assert self.client.base_url == "https://api.tiingo.com/tiingo"

    @patch('api.tiingo_client.TiingoClient._make_request')
    def test_get_price_data_success(self, mock_request):
        """Test successful price data retrieval"""
        mock_data = [
            {
                'date': '2024-01-01T00:00:00.000Z',
                'open': 180.0,
                'high': 185.0,
                'low': 178.0,
                'close': 182.0,
                'volume': 1000000,
                'adjOpen': 180.0,
                'adjHigh': 185.0,
                'adjLow': 178.0,
                'adjClose': 182.0,
                'adjVolume': 1000000
            }
        ]

        mock_request.return_value = mock_data

        result = self.client.get_price_data('AAPL', period='5d')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        assert 'date' in result.columns
        assert 'open' in result.columns
        assert 'close' in result.columns
        assert 'symbol' in result.columns
        assert result['symbol'].iloc[0] == 'AAPL'

    @patch('api.tiingo_client.TiingoClient._make_request')
    def test_get_real_time_price_success(self, mock_request):
        """Test successful real-time price retrieval"""
        mock_data = [
            {
                'date': '2024-01-01T16:00:00.000Z',
                'close': 185.50,
                'prevClose': 183.00,
                'open': 184.00,
                'high': 186.00,
                'low': 183.50,
                'volume': 50000000
            }
        ]

        mock_request.return_value = mock_data

        result = self.client.get_real_time_price('AAPL')

        assert isinstance(result, dict)
        assert 'current_price' in result
        assert 'symbol' in result
        assert result['symbol'] == 'AAPL'
        assert result['current_price'] == 185.50

    @patch('api.tiingo_client.TiingoClient._make_request')
    def test_get_intraday_data_success(self, mock_request):
        """Test successful intraday data retrieval"""
        mock_data = [
            {
                'date': '2024-01-01T09:30:00.000Z',
                'open': 180.0,
                'high': 181.0,
                'low': 179.5,
                'close': 180.5,
                'volume': 100000
            }
        ]

        mock_request.return_value = mock_data

        result = self.client.get_intraday_data('AAPL', interval='5min')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        assert 'date' in result.columns
        assert 'symbol' in result.columns

    def test_financial_data_not_supported(self):
        """Test that Tiingo doesn't provide fundamental data"""
        result = self.client.get_financial_data('AAPL')

        assert isinstance(result, dict)
        assert 'note' in result
        assert 'Tiingo API does not provide fundamental financial data' in result['note']

    @patch('api.tiingo_client.TiingoClient._make_request')
    def test_crypto_data_success(self, mock_request):
        """Test successful crypto data retrieval"""
        mock_data = [
            {
                'ticker': 'btcusd',
                'priceData': [
                    {
                        'date': '2024-01-01T00:00:00.000Z',
                        'open': 45000.0,
                        'high': 46000.0,
                        'low': 44500.0,
                        'close': 45500.0,
                        'volume': 1000
                    }
                ]
            }
        ]

        mock_request.return_value = mock_data

        result = self.client.get_crypto_data('btcusd')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        assert 'date' in result.columns
        assert 'symbol' in result.columns


class TestDataManager:
    """Test DataManager with new API clients"""

    def setup_method(self):
        """Setup test environment"""
        self.config = {
            'primary_source': 'yahoo',
            'backup_source': 'fmp',
            'price_backup': 'tiingo'
        }

        # Mock environment variables
        with patch.dict(os.environ, {
            'FMP_API_KEY': 'test_fmp_key',
            'TIINGO_API_KEY': 'test_tiingo_key'
        }):
            self.data_manager = DataManager(self.config)

    def test_data_manager_initialization(self):
        """Test DataManager initialization with new clients"""
        assert self.data_manager.primary_source == 'yahoo'
        assert self.data_manager.backup_source == 'fmp'
        assert self.data_manager.price_backup == 'tiingo'
        assert self.data_manager.yahoo_client is not None
        assert self.data_manager.fmp_client is not None
        assert self.data_manager.tiingo_client is not None

    @patch('api.yahoo_finance_client.YahooFinanceClient.get_price_data')
    def test_price_data_primary_success(self, mock_yahoo):
        """Test successful price data retrieval from primary source"""
        mock_data = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02'],
            'open': [180.0, 182.0],
            'close': [182.0, 185.0],
            'symbol': ['AAPL', 'AAPL']
        })
        mock_yahoo.return_value = mock_data

        result = self.data_manager.get_price_data('AAPL')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        mock_yahoo.assert_called_once()

    @patch('api.yahoo_finance_client.YahooFinanceClient.get_price_data')
    @patch('api.fmp_client.FMPClient.get_price_data')
    def test_price_data_fallback_to_fmp(self, mock_fmp, mock_yahoo):
        """Test fallback to FMP when Yahoo fails"""
        mock_yahoo.side_effect = APIError("Yahoo failed")
        mock_data = pd.DataFrame({
            'date': ['2024-01-01'],
            'open': [180.0],
            'close': [182.0],
            'symbol': ['AAPL']
        })
        mock_fmp.return_value = mock_data

        result = self.data_manager.get_price_data('AAPL')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        mock_yahoo.assert_called_once()
        mock_fmp.assert_called_once()

    @patch('api.yahoo_finance_client.YahooFinanceClient.get_price_data')
    @patch('api.fmp_client.FMPClient.get_price_data')
    @patch('api.tiingo_client.TiingoClient.get_price_data')
    def test_price_data_fallback_to_tiingo(self, mock_tiingo, mock_fmp, mock_yahoo):
        """Test fallback to Tiingo when both Yahoo and FMP fail"""
        mock_yahoo.side_effect = APIError("Yahoo failed")
        mock_fmp.side_effect = APIError("FMP failed")
        mock_data = pd.DataFrame({
            'date': ['2024-01-01'],
            'open': [180.0],
            'close': [182.0],
            'symbol': ['AAPL']
        })
        mock_tiingo.return_value = mock_data

        result = self.data_manager.get_price_data('AAPL')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        mock_yahoo.assert_called_once()
        mock_fmp.assert_called_once()
        mock_tiingo.assert_called_once()

    @patch('api.yahoo_finance_client.YahooFinanceClient.get_financial_data')
    @patch('api.fmp_client.FMPClient.get_financial_data')
    def test_financial_data_fallback_to_fmp(self, mock_fmp, mock_yahoo):
        """Test fallback to FMP for financial data when Yahoo fails"""
        mock_yahoo.side_effect = APIError("Yahoo failed")
        mock_data = {
            'symbol': 'AAPL',
            'pe_ratio': 25.5,
            'market_cap': 3000000000000
        }
        mock_fmp.return_value = mock_data

        result = self.data_manager.get_financial_data('AAPL')

        assert isinstance(result, dict)
        assert result['symbol'] == 'AAPL'
        mock_yahoo.assert_called_once()
        mock_fmp.assert_called_once()

    def test_multiple_symbols_processing(self):
        """Test processing multiple symbols"""
        with patch.object(self.data_manager, 'get_price_data') as mock_get_price:
            mock_get_price.return_value = pd.DataFrame({
                'date': ['2024-01-01'],
                'close': [100.0],
                'symbol': ['TEST']
            })

            result = self.data_manager.get_multiple_symbols(
                ['AAPL', 'MSFT'],
                data_type='price'
            )

            assert 'data' in result
            assert 'errors' in result
            assert 'success_count' in result
            assert result['success_count'] == 2

    def test_cache_functionality(self):
        """Test caching functionality"""
        # Test that cache is working
        assert hasattr(self.data_manager, 'cache')
        assert hasattr(self.data_manager, 'clear_cache')

        # Test cache clearing
        self.data_manager.clear_cache()  # Should not raise any errors


class TestIntegration:
    """Integration tests for the complete API system"""

    @pytest.mark.skipif(
        not (os.getenv('FMP_API_KEY') and os.getenv('TIINGO_API_KEY')),
        reason="API keys not available"
    )
    def test_real_api_integration(self):
        """Test real API integration (requires actual API keys)"""
        config = {
            'primary_source': 'yahoo',
            'backup_source': 'fmp',
            'price_backup': 'tiingo'
        }

        dm = DataManager(config)

        # Test price data
        try:
            price_data = dm.get_price_data('AAPL', period='5d')
            assert isinstance(price_data, pd.DataFrame)
            assert not price_data.empty
            assert 'close' in price_data.columns
        except APIError:
            pytest.skip("API unavailable")

        # Test financial data
        try:
            financial_data = dm.get_financial_data('AAPL')
            assert isinstance(financial_data, dict)
            assert 'symbol' in financial_data
        except APIError:
            pytest.skip("API unavailable")

    def test_error_propagation(self):
        """Test that errors are properly propagated through the system"""
        config = {'primary_source': 'yahoo', 'backup_source': 'fmp'}

        with patch.dict(os.environ, {}, clear=True):
            dm = DataManager(config)

            # Should still work with Yahoo Finance
            with patch.object(dm.yahoo_client, 'get_price_data') as mock_yahoo:
                mock_yahoo.side_effect = APIError("All sources failed")

                with pytest.raises(APIError):
                    dm.get_price_data('INVALID_SYMBOL')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])