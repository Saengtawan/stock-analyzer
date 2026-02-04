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
    """Rate limiting for API calls with adaptive delay"""

    def __init__(self, calls_per_minute: int, min_delay: float = 0.5):
        self.calls_per_minute = calls_per_minute
        self.min_delay = min_delay  # Minimum delay between calls
        self.calls = []
        self.last_call = 0
        self.consecutive_errors = 0

    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        now = time.time()

        # Always enforce minimum delay between calls
        time_since_last = now - self.last_call
        if time_since_last < self.min_delay:
            sleep_time = self.min_delay - time_since_last
            time.sleep(sleep_time)
            now = time.time()

        # Remove calls older than 1 minute
        self.calls = [call_time for call_time in self.calls if now - call_time < 60]

        if len(self.calls) >= self.calls_per_minute:
            sleep_time = 60 - (now - self.calls[0])
            if sleep_time > 0:
                logger.info(f"Rate limit reached, sleeping for {sleep_time:.1f} seconds")
                time.sleep(sleep_time)

        # Add extra delay if we've seen errors
        if self.consecutive_errors > 0:
            extra_delay = min(self.consecutive_errors * 2, 30)  # Max 30s extra
            logger.info(f"Adding {extra_delay}s delay due to {self.consecutive_errors} recent errors")
            time.sleep(extra_delay)

        self.calls.append(now)
        self.last_call = now

    def record_error(self):
        """Record that an error occurred"""
        self.consecutive_errors += 1

    def record_success(self):
        """Record that a call succeeded"""
        self.consecutive_errors = max(0, self.consecutive_errors - 1)


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
        """Make rate-limited API request with 429 retry"""
        max_retries = 3
        last_error = None
        for attempt in range(max_retries):
            self.rate_limiter.wait_if_needed()
            try:
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 429:
                    self.rate_limiter.record_error()
                    if attempt < max_retries - 1:
                        wait = min(30, (attempt + 1) * 10)
                        logger.warning(f"429 rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})")
                        time.sleep(wait)
                        continue
                    # Last attempt — raise so fallback can kick in
                    response.raise_for_status()
                response.raise_for_status()
                self.rate_limiter.record_success()
                return response.json()
            except requests.exceptions.RequestException as e:
                self.rate_limiter.record_error()
                last_error = e
                if attempt < max_retries - 1 and '429' in str(e):
                    wait = min(30, (attempt + 1) * 10)
                    logger.warning(f"Rate limit error, retrying in {wait}s")
                    time.sleep(wait)
                    continue
                logger.error(f"API request failed: {e}")
                raise
        # Should not reach here, but raise if it does
        raise requests.exceptions.RequestException(f"Max retries exceeded: {last_error}")

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
    """
    v6.10: Persistent cache with disk storage to avoid rate limits

    Features:
    - Memory cache for fast access
    - Disk cache for persistence across restarts
    - Long TTLs (24h for price data) to minimize API calls
    """

    def __init__(self, ttl_minutes: int = 60, cache_dir: str = None):
        import os
        import pickle

        self.cache = {}
        self.default_ttl = timedelta(minutes=ttl_minutes)

        # Disk cache directory
        self.cache_dir = cache_dir or os.path.expanduser('~/.stock_analyzer_cache')
        os.makedirs(self.cache_dir, exist_ok=True)

        # v6.10: SMART CACHE - Different TTLs based on data freshness needs
        #
        # ⏳ LONG CACHE (historical data - OK to be older):
        #    - Historical prices for momentum calculation
        #    - Company info (sector, industry)
        #    - Financial fundamentals
        #
        # 🔄 SHORT CACHE (need fresher data):
        #    - Sector regime (market conditions change)
        #    - Insider activity
        #
        # ❌ NO CACHE (always fresh):
        #    - Real-time prices (handled separately)
        #    - Pre-market data
        #
        self.ttl_by_type = {
            # LONG CACHE - historical data
            'price': timedelta(hours=4),           # Historical prices: 4h (for 20-90 day momentum)
            'company': timedelta(hours=24),        # Company info: 24h (sector/industry rarely change)
            'financial': timedelta(hours=12),      # Financial data: 12h (quarterly reports)
            'universe': timedelta(hours=6),        # Stock universe: 6h

            # SHORT CACHE - need fresher data
            'sector_regime': timedelta(minutes=20),  # Sector regime: 20min (v4.9.3 — matches SECTOR_REGIME_TTL_MINUTES)
            'insider': timedelta(hours=4),         # Insider activity: 4h
            'sec_edgar': timedelta(hours=6),       # SEC filings: 6h

            # DEFAULT
            'default': self.default_ttl
        }

        # Load existing disk cache
        self._load_disk_cache()

        # v4.9.3: Auto cleanup old/large disk cache
        self.DISK_CLEANUP_DAYS = 14   # ไม่ลบ cache ที่ยังใช้ (conservative)
        self.DISK_CLEANUP_MAX_MB = 100
        self._cleanup_disk_cache()

    def _get_disk_path(self, key: str) -> str:
        """Get disk cache path for key"""
        import hashlib
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return f"{self.cache_dir}/{safe_key}.pkl"

    def _load_disk_cache(self):
        """Load all cached data from disk"""
        import os
        import pickle

        try:
            count = 0
            for f in os.listdir(self.cache_dir):
                if f.endswith('.pkl'):
                    try:
                        path = f"{self.cache_dir}/{f}"
                        with open(path, 'rb') as fp:
                            key, data, timestamp, data_type = pickle.load(fp)

                            # Check if still valid
                            ttl = self.ttl_by_type.get(data_type, self.default_ttl)
                            if datetime.now() - timestamp < ttl:
                                self.cache[key] = (data, timestamp, data_type)
                                count += 1
                    except:
                        pass
            if count > 0:
                logger.info(f"📦 Loaded {count} cached items from disk")
        except Exception as e:
            logger.debug(f"Could not load disk cache: {e}")

    def _cleanup_disk_cache(self, max_age_days: int = None, max_size_mb: int = None):
        """v4.9.3: Remove expired/oversized pickle files from disk cache"""
        import os
        import time as _time

        try:
            now = _time.time()
            max_age_days = max_age_days or self.DISK_CLEANUP_DAYS
            max_size_mb = max_size_mb or self.DISK_CLEANUP_MAX_MB
            max_age_seconds = max_age_days * 86400
            max_size_bytes = max_size_mb * 1024 * 1024

            files = []
            total_size = 0
            for f in os.listdir(self.cache_dir):
                if not f.endswith('.pkl'):
                    continue
                path = os.path.join(self.cache_dir, f)
                try:
                    stat = os.stat(path)
                    files.append((path, stat.st_mtime, stat.st_size))
                    total_size += stat.st_size
                except OSError:
                    continue

            removed = 0

            # 1. Remove files older than max_age_days
            for path, mtime, size in files:
                if now - mtime > max_age_seconds:
                    try:
                        os.unlink(path)
                        total_size -= size
                        removed += 1
                    except OSError:
                        pass

            # 2. If still over max_size, remove oldest first
            if total_size > max_size_bytes:
                remaining = [(p, m, s) for p, m, s in files if os.path.exists(p)]
                remaining.sort(key=lambda x: x[1])  # oldest first
                for path, mtime, size in remaining:
                    if total_size <= max_size_bytes:
                        break
                    try:
                        os.unlink(path)
                        total_size -= size
                        removed += 1
                    except OSError:
                        pass

            if removed > 0:
                logger.info(f"🧹 Disk cache cleanup: removed {removed} files, {total_size / 1024 / 1024:.1f}MB remaining")
        except Exception as e:
            logger.debug(f"Disk cache cleanup error: {e}")

    def get(self, key: str, data_type: str = 'default') -> Optional[Any]:
        """Get cached data if not expired"""
        if key in self.cache:
            data, timestamp, cached_type = self.cache[key]
            ttl = self.ttl_by_type.get(cached_type, self.default_ttl)
            if datetime.now() - timestamp < ttl:
                return data
            else:
                del self.cache[key]
        return None

    def set(self, key: str, data: Any, data_type: str = 'default'):
        """Cache data with timestamp and type, also save to disk"""
        import pickle

        self.cache[key] = (data, datetime.now(), data_type)

        # Also save to disk for persistence
        try:
            path = self._get_disk_path(key)
            with open(path, 'wb') as fp:
                pickle.dump((key, data, datetime.now(), data_type), fp)
        except Exception as e:
            logger.debug(f"Could not save to disk cache: {e}")

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