#!/usr/bin/env python3
"""
Yahoo Finance Rate Limiter
--------------------------
Shared rate limiter and ticker cache to prevent rate limiting

Features:
1. Cache yfinance Ticker objects (reuse across data sources)
2. Rate limiting with delay between requests
3. Retry logic with exponential backoff
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import logging

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)


class YFinanceRateLimiter:
    """
    Singleton rate limiter for Yahoo Finance API

    Usage:
        limiter = get_rate_limiter()
        ticker = limiter.get_ticker('AAPL')
        info = ticker.info
    """

    _instance = None
    _lock = threading.Lock()

    # Configuration
    MIN_DELAY_SECONDS = 0.5      # Minimum delay between requests
    MAX_RETRIES = 3              # Max retries on rate limit
    BACKOFF_FACTOR = 2           # Exponential backoff multiplier
    TICKER_CACHE_TTL = 300       # Cache tickers for 5 minutes
    INFO_CACHE_TTL = 3600        # Cache info for 1 hour

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._ticker_cache: Dict[str, tuple] = {}  # symbol -> (ticker, timestamp)
        self._info_cache: Dict[str, tuple] = {}    # symbol -> (info, timestamp)
        self._last_request_time = 0
        self._request_lock = threading.Lock()
        self._initialized = True

        logger.info("YFinance Rate Limiter initialized")
        logger.info(f"  Min delay: {self.MIN_DELAY_SECONDS}s")
        logger.info(f"  Info cache TTL: {self.INFO_CACHE_TTL}s")

    def _wait_for_rate_limit(self):
        """Wait if needed to avoid rate limiting"""
        with self._request_lock:
            now = time.time()
            elapsed = now - self._last_request_time

            if elapsed < self.MIN_DELAY_SECONDS:
                sleep_time = self.MIN_DELAY_SECONDS - elapsed
                time.sleep(sleep_time)

            self._last_request_time = time.time()

    def get_ticker(self, symbol: str) -> Optional[Any]:
        """
        Get yfinance Ticker with rate limiting

        Returns cached ticker if available and fresh
        """
        if yf is None:
            logger.warning("yfinance not installed")
            return None

        # Check cache
        if symbol in self._ticker_cache:
            ticker, cached_time = self._ticker_cache[symbol]
            if datetime.now() - cached_time < timedelta(seconds=self.TICKER_CACHE_TTL):
                return ticker

        # Rate limit
        self._wait_for_rate_limit()

        # Create new ticker
        ticker = yf.Ticker(symbol)
        self._ticker_cache[symbol] = (ticker, datetime.now())

        return ticker

    def get_info(self, symbol: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Get ticker.info with caching and retry logic

        This is the most rate-limited call, so we cache it aggressively
        """
        if yf is None:
            return None

        # Check cache
        if not force_refresh and symbol in self._info_cache:
            info, cached_time = self._info_cache[symbol]
            if datetime.now() - cached_time < timedelta(seconds=self.INFO_CACHE_TTL):
                logger.debug(f"{symbol}: Using cached info")
                return info

        # Get ticker
        ticker = self.get_ticker(symbol)
        if not ticker:
            return None

        # Retry logic with exponential backoff
        for attempt in range(self.MAX_RETRIES):
            try:
                self._wait_for_rate_limit()
                info = ticker.info

                # Cache the result
                self._info_cache[symbol] = (info, datetime.now())
                return info

            except Exception as e:
                error_msg = str(e).lower()

                if 'rate' in error_msg or 'limit' in error_msg or '429' in error_msg:
                    # Rate limited - exponential backoff
                    wait_time = self.MIN_DELAY_SECONDS * (self.BACKOFF_FACTOR ** attempt)
                    logger.warning(f"{symbol}: Rate limited, waiting {wait_time:.1f}s (attempt {attempt + 1}/{self.MAX_RETRIES})")
                    time.sleep(wait_time)
                else:
                    # Other error
                    logger.error(f"{symbol}: Error getting info: {e}")
                    return None

        logger.error(f"{symbol}: Failed after {self.MAX_RETRIES} retries")
        return None

    def get_history(self, symbol: str, period: str = '1y') -> Optional[Any]:
        """Get ticker.history with rate limiting"""
        ticker = self.get_ticker(symbol)
        if not ticker:
            return None

        for attempt in range(self.MAX_RETRIES):
            try:
                self._wait_for_rate_limit()
                return ticker.history(period=period)

            except Exception as e:
                error_msg = str(e).lower()

                if 'rate' in error_msg or 'limit' in error_msg or '429' in error_msg:
                    wait_time = self.MIN_DELAY_SECONDS * (self.BACKOFF_FACTOR ** attempt)
                    logger.warning(f"{symbol}: Rate limited on history, waiting {wait_time:.1f}s")
                    time.sleep(wait_time)
                else:
                    logger.error(f"{symbol}: Error getting history: {e}")
                    return None

        return None

    def clear_cache(self, symbol: str = None):
        """Clear cache for a symbol or all symbols"""
        if symbol:
            self._ticker_cache.pop(symbol, None)
            self._info_cache.pop(symbol, None)
        else:
            self._ticker_cache.clear()
            self._info_cache.clear()

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            'ticker_cache_size': len(self._ticker_cache),
            'info_cache_size': len(self._info_cache),
            'min_delay': self.MIN_DELAY_SECONDS,
            'info_cache_ttl': self.INFO_CACHE_TTL
        }


# Singleton getter
_rate_limiter: Optional[YFinanceRateLimiter] = None


def get_rate_limiter() -> YFinanceRateLimiter:
    """Get singleton rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = YFinanceRateLimiter()
    return _rate_limiter


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)

    print("=" * 60)
    print("YFINANCE RATE LIMITER TEST")
    print("=" * 60)

    limiter = get_rate_limiter()

    symbols = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD']

    for symbol in symbols:
        print(f"\nFetching {symbol}...")
        start = time.time()
        info = limiter.get_info(symbol)
        elapsed = time.time() - start

        if info:
            price = info.get('currentPrice', info.get('regularMarketPrice', 'N/A'))
            print(f"  {symbol}: ${price} ({elapsed:.2f}s)")
        else:
            print(f"  {symbol}: Failed")

    print(f"\nCache stats: {limiter.get_cache_stats()}")
