"""
Real-time Price Fetcher

Hybrid approach for getting current prices:
- Use 1-minute intraday bars for today's price
- Fallback to daily bars if market closed
- Cache for 60 seconds to avoid rate limits
"""

from typing import Optional, Tuple
import yfinance as yf
import pandas as pd
from datetime import datetime, time as dt_time
import pytz
from loguru import logger

# v6.x: Import market hours (Single Source of Truth)
try:
    from utils.market_hours import MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE
except ImportError:
    MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE = 9, 30
    MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE = 16, 0


class RealtimePriceFetcher:
    """
    Fetch real-time prices using hybrid approach

    Strategy:
    1. During market hours: Use 1-minute bars (last 60 minutes)
    2. Market closed: Use daily bars (yesterday's close)
    3. Cache results for 60 seconds to minimize API calls
    """

    def __init__(self, cache_ttl_seconds: int = 60):
        """
        Initialize real-time price fetcher

        Args:
            cache_ttl_seconds: Cache TTL (default 60s)
        """
        self.cache_ttl = cache_ttl_seconds
        self._cache = {}  # {symbol: (price, timestamp, is_realtime)}

        # Market hours (US Eastern Time) - loaded from utils.market_hours
        self.market_open = dt_time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)
        self.market_close = dt_time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
        self.eastern = pytz.timezone('US/Eastern')

    def is_market_open(self) -> bool:
        """Check if US market is currently open"""
        now_et = datetime.now(self.eastern)
        current_time = now_et.time()

        # Check if weekday (Monday=0, Friday=4)
        if now_et.weekday() >= 5:  # Saturday or Sunday
            return False

        # Check if within market hours
        return self.market_open <= current_time <= self.market_close

    def get_price(
        self,
        symbol: str,
        fallback_daily_data: Optional[pd.DataFrame] = None
    ) -> Tuple[float, bool, str]:
        """
        Get current price for a symbol

        Args:
            symbol: Stock symbol
            fallback_daily_data: Optional daily bars DataFrame to use as fallback

        Returns:
            Tuple of (price, is_realtime, source)
            - price: Current price
            - is_realtime: True if from intraday data, False if from daily bars
            - source: Description of data source
        """
        # Check cache first
        if symbol in self._cache:
            cached_price, cached_time, is_realtime = self._cache[symbol]
            age = (datetime.now().timestamp() - cached_time)
            if age < self.cache_ttl:
                logger.debug(f"{symbol}: Using cached price ${cached_price:.2f} "
                           f"(age: {age:.1f}s, realtime: {is_realtime})")
                return cached_price, is_realtime, f"cache ({age:.0f}s old)"

        # Determine fetch strategy based on market hours
        market_open = self.is_market_open()

        if market_open:
            # Try intraday data first
            price, success = self._fetch_intraday_price(symbol)
            if success:
                self._cache[symbol] = (price, datetime.now().timestamp(), True)
                return price, True, "intraday (1m bars)"

            logger.warning(f"{symbol}: Failed to fetch intraday price, falling back to daily")

        # Fallback to daily bars
        if fallback_daily_data is not None and not fallback_daily_data.empty:
            price = fallback_daily_data['close'].iloc[-1]
            self._cache[symbol] = (price, datetime.now().timestamp(), False)
            return price, False, "daily bars (fallback)"

        # Last resort: fetch daily bars
        price, success = self._fetch_daily_price(symbol)
        if success:
            self._cache[symbol] = (price, datetime.now().timestamp(), False)
            return price, False, "daily bars (fetched)"

        # Complete failure
        logger.error(f"{symbol}: Failed to fetch any price data!")
        return 0.0, False, "failed"

    def _fetch_intraday_price(self, symbol: str) -> Tuple[float, bool]:
        """
        Fetch price from 1-minute intraday bars

        Returns:
            Tuple of (price, success)
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get today's 1-minute bars (last hour to be safe)
            intraday = ticker.history(period="1d", interval="1m")

            if intraday.empty:
                logger.debug(f"{symbol}: No intraday data available")
                return 0.0, False

            # Get last close price
            last_price = intraday['Close'].iloc[-1]
            last_time = intraday.index[-1]

            logger.debug(f"{symbol}: Intraday price ${last_price:.2f} at {last_time}")
            return last_price, True

        except Exception as e:
            logger.debug(f"{symbol}: Intraday fetch failed: {e}")
            return 0.0, False

    def _fetch_daily_price(self, symbol: str) -> Tuple[float, bool]:
        """
        Fetch price from daily bars

        Returns:
            Tuple of (price, success)
        """
        try:
            ticker = yf.Ticker(symbol)
            daily = ticker.history(period="2d")  # Get last 2 days

            if daily.empty:
                return 0.0, False

            price = daily['Close'].iloc[-1]
            return price, True

        except Exception as e:
            logger.debug(f"{symbol}: Daily fetch failed: {e}")
            return 0.0, False

    def clear_cache(self):
        """Clear price cache"""
        self._cache.clear()
        logger.debug("Real-time price cache cleared")


# Global instance
_realtime_fetcher = None


def get_realtime_fetcher() -> RealtimePriceFetcher:
    """Get global real-time price fetcher instance"""
    global _realtime_fetcher
    if _realtime_fetcher is None:
        _realtime_fetcher = RealtimePriceFetcher()
    return _realtime_fetcher


def get_current_price(
    symbol: str,
    fallback_daily_data: Optional[pd.DataFrame] = None
) -> Tuple[float, bool, str]:
    """
    Convenience function to get current price

    Args:
        symbol: Stock symbol
        fallback_daily_data: Optional daily bars to use as fallback

    Returns:
        Tuple of (price, is_realtime, source)
    """
    fetcher = get_realtime_fetcher()
    return fetcher.get_price(symbol, fallback_daily_data)


def clear_price_cache():
    """Clear the global price cache"""
    fetcher = get_realtime_fetcher()
    fetcher.clear_cache()
