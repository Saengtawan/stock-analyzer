"""
Rate Limiter for API calls (Production Grade v6.21)

Implements sliding window rate limiting to prevent exceeding API quotas.

Alpaca limits:
- 200 requests/minute
- 10,000 requests/day

Conservative limits (with 25% buffer):
- 150 requests/minute
- 7,500 requests/day

Usage:
    from engine.rate_limiter import RateLimiter

    limiter = RateLimiter(max_requests=150, window_seconds=60)

    # Before API call
    limiter.wait_if_needed(endpoint="get_snapshot:AAPL")

    # Or check without blocking
    if limiter.acquire(endpoint="get_account"):
        # Make API call
        ...
    else:
        # Rate limited - skip or retry later
        ...
"""

import time
from collections import deque
from threading import Lock
from typing import Optional, Tuple
from loguru import logger


class RateLimiter:
    """
    Thread-safe rate limiter with sliding window algorithm

    Features:
    - Sliding window (more accurate than fixed window)
    - Thread-safe (multiple threads can share one limiter)
    - Per-endpoint tracking (for debugging)
    - Configurable limits and windows
    """

    def __init__(
        self,
        max_requests: int = 150,
        window_seconds: int = 60,
        name: str = "RateLimiter"
    ):
        """
        Initialize rate limiter

        Args:
            max_requests: Maximum requests allowed in window (default: 150)
            window_seconds: Time window in seconds (default: 60)
            name: Name for logging (default: "RateLimiter")
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name

        # Sliding window: deque of (timestamp, endpoint) tuples
        self.requests = deque()  # type: deque[Tuple[float, str]]

        # Thread safety
        self.lock = Lock()

        # Statistics
        self.total_requests = 0
        self.total_waits = 0
        self.total_wait_time = 0.0

        logger.info(
            f"{self.name} initialized: {max_requests} req/{window_seconds}s "
            f"({max_requests * 60 / window_seconds:.0f} req/min)"
        )

    def _cleanup_old_requests(self, now: float):
        """Remove requests outside the current window (internal, not thread-safe)"""
        cutoff = now - self.window_seconds

        while self.requests and self.requests[0][0] < cutoff:
            self.requests.popleft()

    def acquire(self, endpoint: str = "unknown") -> bool:
        """
        Try to acquire permission to make API call (non-blocking)

        Args:
            endpoint: Endpoint name for tracking (e.g., "get_snapshot:AAPL")

        Returns:
            True if allowed, False if rate limited
        """
        with self.lock:
            now = time.time()

            # Remove old requests
            self._cleanup_old_requests(now)

            # Check if within limit
            if len(self.requests) >= self.max_requests:
                # Rate limited
                oldest = self.requests[0][0]
                wait_time = self.window_seconds - (now - oldest)

                logger.warning(
                    f"⚠️ {self.name}: Rate limit reached "
                    f"({len(self.requests)}/{self.max_requests} in {self.window_seconds}s). "
                    f"Must wait {wait_time:.1f}s"
                )
                return False

            # Within limit - record this request
            self.requests.append((now, endpoint))
            self.total_requests += 1

            return True

    def wait_if_needed(
        self,
        endpoint: str = "unknown",
        max_wait: float = 60.0
    ):
        """
        Block until rate limit allows request (with timeout)

        Args:
            endpoint: Endpoint name for tracking
            max_wait: Maximum wait time in seconds (default: 60)

        Raises:
            TimeoutError: If wait exceeds max_wait

        Example:
            limiter.wait_if_needed(endpoint="get_snapshot:AAPL")
            # ... make API call ...
        """
        waited = 0.0
        wait_start = time.time()

        while not self.acquire(endpoint):
            if waited >= max_wait:
                raise TimeoutError(
                    f"{self.name}: Rate limit wait exceeded {max_wait}s "
                    f"({len(self.requests)}/{self.max_requests} requests in window)"
                )

            # Sleep 1 second and try again
            time.sleep(1)
            waited = time.time() - wait_start
            self.total_waits += 1
            self.total_wait_time += 1.0

    def get_current_usage(self) -> Tuple[int, int, float]:
        """
        Get current rate limit usage

        Returns:
            (current_requests, max_requests, usage_pct)

        Example:
            current, max_req, pct = limiter.get_current_usage()
            print(f"Usage: {current}/{max_req} ({pct:.1f}%)")
        """
        with self.lock:
            now = time.time()
            self._cleanup_old_requests(now)

            current = len(self.requests)
            usage_pct = (current / self.max_requests) * 100 if self.max_requests > 0 else 0

            return current, self.max_requests, usage_pct

    def get_statistics(self) -> dict:
        """
        Get rate limiter statistics

        Returns:
            Dictionary with statistics
        """
        current, max_req, usage_pct = self.get_current_usage()

        return {
            'name': self.name,
            'current_requests': current,
            'max_requests': max_req,
            'window_seconds': self.window_seconds,
            'usage_pct': usage_pct,
            'total_requests': self.total_requests,
            'total_waits': self.total_waits,
            'total_wait_time': self.total_wait_time,
        }

    def reset(self):
        """Reset rate limiter (clear all requests)"""
        with self.lock:
            self.requests.clear()
            logger.info(f"{self.name}: Reset")

    def __repr__(self) -> str:
        current, max_req, usage_pct = self.get_current_usage()
        return (
            f"RateLimiter(name='{self.name}', "
            f"current={current}/{max_req}, "
            f"usage={usage_pct:.1f}%)"
        )


# =========================================================================
# CONVENIENCE FUNCTIONS
# =========================================================================

def create_alpaca_limiter() -> RateLimiter:
    """
    Create rate limiter for Alpaca API

    Alpaca limits: 200 req/min
    Conservative limit: 150 req/min (25% buffer)

    Returns:
        Configured RateLimiter instance
    """
    return RateLimiter(
        max_requests=150,
        window_seconds=60,
        name="AlpacaAPI"
    )


# =========================================================================
# EXAMPLE USAGE
# =========================================================================

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)

    print("🧪 Testing Rate Limiter...")

    # Create limiter: 5 requests per 10 seconds
    limiter = RateLimiter(max_requests=5, window_seconds=10, name="Test")

    # Test 1: Normal usage
    print("\n1. Normal usage (should allow 5 requests):")
    for i in range(5):
        if limiter.acquire(endpoint=f"request_{i+1}"):
            print(f"   ✅ Request {i+1} allowed")
        else:
            print(f"   ❌ Request {i+1} blocked")

    # Test 2: Rate limit hit
    print("\n2. 6th request (should be blocked):")
    if limiter.acquire(endpoint="request_6"):
        print("   ✅ Request 6 allowed")
    else:
        print("   ❌ Request 6 blocked (rate limited)")

    # Test 3: Statistics
    print("\n3. Statistics:")
    stats = limiter.get_statistics()
    print(f"   Current: {stats['current_requests']}/{stats['max_requests']}")
    print(f"   Usage: {stats['usage_pct']:.1f}%")
    print(f"   Total requests: {stats['total_requests']}")

    # Test 4: Wait for capacity
    print("\n4. Wait for rate limit to allow...")
    print("   (Sleeping 11 seconds to clear window...)")
    time.sleep(11)

    if limiter.acquire(endpoint="request_7"):
        print("   ✅ Request 7 allowed (after window expired)")

    print(f"\n✅ Tests complete! Final: {limiter}")
