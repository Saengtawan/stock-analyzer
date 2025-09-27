"""
Base API Client for all data providers
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import requests
import time
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger


class RateLimiter:
    """Rate limiting for API calls"""

    def __init__(self, calls_per_minute: int):
        self.calls_per_minute = calls_per_minute
        self.calls = []

    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        now = time.time()
        # Remove calls older than 1 minute
        self.calls = [call_time for call_time in self.calls if now - call_time < 60]

        if len(self.calls) >= self.calls_per_minute:
            sleep_time = 60 - (now - self.calls[0])
            if sleep_time > 0:
                logger.info(f"Rate limit reached, sleeping for {sleep_time:.1f} seconds")
                time.sleep(sleep_time)

        self.calls.append(now)


class BaseAPIClient(ABC):
    """Abstract base class for all API clients"""

    def __init__(self, api_key: str, rate_limit: int = 60):
        self.api_key = api_key
        self.rate_limiter = RateLimiter(rate_limit)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'StockAnalyzer/1.0'
        })

    def _make_request(self, url: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make rate-limited API request"""
        self.rate_limiter.wait_if_needed()

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise

    @abstractmethod
    def get_price_data(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """Get historical price data"""
        pass

    @abstractmethod
    def get_financial_data(self, symbol: str) -> Dict[str, Any]:
        """Get financial statements data"""
        pass

    @abstractmethod
    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """Get company information"""
        pass

    def validate_symbol(self, symbol: str) -> bool:
        """Validate if symbol exists"""
        try:
            data = self.get_company_info(symbol)
            return bool(data)
        except Exception:
            return False


class DataCache:
    """Simple in-memory cache for API responses"""

    def __init__(self, ttl_minutes: int = 60):
        self.cache = {}
        self.ttl = timedelta(minutes=ttl_minutes)

    def get(self, key: str) -> Optional[Any]:
        """Get cached data if not expired"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                return data
            else:
                del self.cache[key]
        return None

    def set(self, key: str, data: Any):
        """Cache data with timestamp"""
        self.cache[key] = (data, datetime.now())

    def clear(self):
        """Clear all cached data"""
        self.cache.clear()


class APIError(Exception):
    """Custom exception for API errors"""
    pass


class RateLimitExceeded(APIError):
    """Exception for rate limit exceeded"""
    pass


class InvalidSymbol(APIError):
    """Exception for invalid stock symbol"""
    pass