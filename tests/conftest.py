"""
Pytest configuration and fixtures for stock analyzer tests
"""
import pytest
import os
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def mock_price_data():
    """Fixture providing mock price data"""
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5),
        'open': [180.0, 181.0, 179.0, 182.0, 183.0],
        'high': [185.0, 186.0, 184.0, 187.0, 188.0],
        'low': [178.0, 179.0, 177.0, 180.0, 181.0],
        'close': [182.0, 183.0, 181.0, 184.0, 185.0],
        'volume': [1000000, 1200000, 900000, 1100000, 1300000],
        'symbol': ['AAPL'] * 5
    })


@pytest.fixture
def mock_financial_data():
    """Fixture providing mock financial data"""
    return {
        'symbol': 'AAPL',
        'last_updated': datetime.now().isoformat(),
        'market_cap': 3000000000000,
        'pe_ratio': 25.5,
        'peg_ratio': 1.2,
        'price_to_book': 8.5,
        'revenue': 350000000000,
        'net_income': 85000000000,
        'total_assets': 400000000000,
        'shareholders_equity': 80000000000,
        'debt_to_equity': 0.3,
        'current_ratio': 1.5,
        'roe': 0.285,
        'roa': 0.21,
        'profit_margin': 0.24,
        'operating_margin': 0.28,
        'sector': 'Technology',
        'industry': 'Consumer Electronics'
    }


@pytest.fixture
def mock_real_time_data():
    """Fixture providing mock real-time data"""
    return {
        'symbol': 'AAPL',
        'current_price': 185.50,
        'previous_close': 183.00,
        'open': 184.00,
        'day_high': 186.00,
        'day_low': 183.50,
        'volume': 50000000,
        'market_cap': 3000000000000,
        'pe_ratio': 25.5,
        'change': 2.50,
        'change_percent': 1.37,
        'timestamp': datetime.now().isoformat()
    }


@pytest.fixture
def mock_company_info():
    """Fixture providing mock company information"""
    return {
        'symbol': 'AAPL',
        'company_name': 'Apple Inc.',
        'sector': 'Technology',
        'industry': 'Consumer Electronics',
        'country': 'United States',
        'website': 'https://www.apple.com',
        'description': 'Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.',
        'employees': 164000,
        'market_cap': 3000000000000,
        'currency': 'USD',
        'exchange': 'NASDAQ'
    }


@pytest.fixture
def mock_fmp_response():
    """Fixture providing mock FMP API responses"""
    return {
        'price_data': {
            'historical': [
                {
                    'date': '2024-01-01',
                    'open': 180.0,
                    'high': 185.0,
                    'low': 178.0,
                    'close': 182.0,
                    'volume': 1000000
                }
            ]
        },
        'key_metrics': [
            {
                'marketCap': 3000000000000,
                'peRatio': 25.5,
                'pegRatio': 1.2,
                'priceToBookRatio': 8.5
            }
        ],
        'ratios': [
            {
                'currentRatio': 1.5,
                'debtEquityRatio': 0.3,
                'returnOnEquity': 0.285,
                'returnOnAssets': 0.21
            }
        ],
        'income_statement': [
            {
                'revenue': 350000000000,
                'netIncome': 85000000000,
                'eps': 5.89
            }
        ],
        'profile': [
            {
                'companyName': 'Apple Inc.',
                'sector': 'Technology',
                'industry': 'Consumer Electronics'
            }
        ]
    }


@pytest.fixture
def mock_tiingo_response():
    """Fixture providing mock Tiingo API responses"""
    return {
        'price_data': [
            {
                'date': '2024-01-01T00:00:00.000Z',
                'open': 180.0,
                'high': 185.0,
                'low': 178.0,
                'close': 182.0,
                'volume': 1000000
            }
        ],
        'intraday_data': [
            {
                'date': '2024-01-01T09:30:00.000Z',
                'open': 180.0,
                'high': 181.0,
                'low': 179.5,
                'close': 180.5,
                'volume': 100000
            }
        ],
        'company_info': {
            'name': 'Apple Inc.',
            'ticker': 'AAPL',
            'description': 'Apple Inc. designs, manufactures, and markets smartphones...',
            'exchangeCode': 'NASDAQ'
        }
    }


@pytest.fixture
def sample_symbols():
    """Fixture providing sample stock symbols for testing"""
    return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']


@pytest.fixture
def test_config():
    """Fixture providing test configuration"""
    return {
        'primary_source': 'yahoo',
        'backup_source': 'fmp',
        'price_backup': 'tiingo',
        'rate_limits': {
            'fmp': 300,
            'tiingo': 500,
            'yfinance': 2000
        },
        'cache': {
            'price_data_ttl': 300,
            'fundamental_ttl': 3600,
            'technical_ttl': 900
        }
    }


@pytest.fixture
def mock_api_error():
    """Fixture providing mock API error"""
    from api.base_client import APIError
    return APIError("Mock API error for testing")


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Automatically setup test environment for all tests"""
    # Set test environment variables
    test_env = {
        'FMP_API_KEY': 'test_fmp_key',
        'TIINGO_API_KEY': 'test_tiingo_key',
        'LOG_LEVEL': 'WARNING',  # Reduce logging noise during tests
        'TEST_MODE': 'true'
    }

    original_env = {}
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    # Restore original environment
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def mock_cache():
    """Fixture providing mock cache for testing"""
    cache_data = {}

    class MockCache:
        def get(self, key):
            return cache_data.get(key)

        def set(self, key, value):
            cache_data[key] = value

        def clear(self):
            cache_data.clear()

    return MockCache()


@pytest.fixture
def date_range_last_year():
    """Fixture providing date range for last year"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    return start_date, end_date


@pytest.fixture
def mock_technical_indicators():
    """Fixture providing mock technical indicator data"""
    return {
        'rsi': 65.0,
        'macd': 0.5,
        'macd_signal': 0.3,
        'macd_histogram': 0.2,
        'sma_20': 180.0,
        'sma_50': 175.0,
        'sma_200': 170.0,
        'ema_12': 182.0,
        'ema_26': 178.0,
        'bollinger_upper': 190.0,
        'bollinger_middle': 180.0,
        'bollinger_lower': 170.0,
        'atr': 3.5,
        'volume_sma': 1000000
    }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "api_key_required: mark test as requiring real API keys"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names"""
    for item in items:
        # Mark integration tests
        if "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.integration)

        # Mark slow tests
        if "slow" in item.nodeid.lower() or "real_api" in item.nodeid.lower():
            item.add_marker(pytest.mark.slow)

        # Mark tests requiring API keys
        if "real_api" in item.nodeid.lower():
            item.add_marker(pytest.mark.api_key_required)


# Custom assertion helpers
def assert_valid_price_data(df):
    """Assert that a DataFrame contains valid price data"""
    required_columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'symbol']

    # Check columns exist
    for col in required_columns:
        assert col in df.columns, f"Missing required column: {col}"

    if len(df) > 0:
        # Check data types
        assert pd.api.types.is_datetime64_any_dtype(df['date'])
        assert pd.api.types.is_numeric_dtype(df['open'])
        assert pd.api.types.is_numeric_dtype(df['close'])

        # Check logical constraints
        assert (df['high'] >= df['low']).all()
        assert (df['volume'] >= 0).all()


def assert_valid_financial_data(data):
    """Assert that a dictionary contains valid financial data"""
    required_fields = ['symbol']

    for field in required_fields:
        assert field in data, f"Missing required field: {field}"

    # Check numeric fields are valid when present
    numeric_fields = ['market_cap', 'pe_ratio', 'revenue', 'net_income']
    for field in numeric_fields:
        if field in data and data[field] is not None:
            assert isinstance(data[field], (int, float)), f"{field} should be numeric"


# Export assertion helpers to be available in tests
pytest.assert_valid_price_data = assert_valid_price_data
pytest.assert_valid_financial_data = assert_valid_financial_data