"""
Monitoring Metrics (Production Grade v6.21)

Tracks critical metrics for production monitoring:
- Order success/failure rate
- Position sync success rate
- API latency (p50, p95, p99)
- DLQ accumulation rate
- Rate limiter usage

Usage:
    from engine.monitoring_metrics import get_metrics_tracker

    tracker = get_metrics_tracker()

    # Track order
    tracker.record_order_attempt('AAPL', success=True, latency_ms=150)

    # Track position sync
    tracker.record_position_sync(success=True, positions_count=5)

    # Get metrics
    metrics = tracker.get_metrics()
    print(f"Order success rate: {metrics['order_success_rate']:.1%}")
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque
from threading import Lock
from loguru import logger


@dataclass
class MetricWindow:
    """Rolling window for metrics"""
    window_seconds: int = 3600  # 1 hour
    values: deque = field(default_factory=deque)  # (timestamp, value) tuples

    def add(self, value: Any, timestamp: float = None):
        """Add value to window"""
        if timestamp is None:
            timestamp = time.time()
        self.values.append((timestamp, value))
        self._cleanup(timestamp)

    def _cleanup(self, now: float):
        """Remove values outside window"""
        cutoff = now - self.window_seconds
        while self.values and self.values[0][0] < cutoff:
            self.values.popleft()

    def get_count(self) -> int:
        """Get count of values in window"""
        self._cleanup(time.time())
        return len(self.values)

    def get_values(self) -> List[Any]:
        """Get all values in window"""
        self._cleanup(time.time())
        return [v for _, v in self.values]

    def get_rate_per_minute(self) -> float:
        """Get rate per minute"""
        self._cleanup(time.time())
        if not self.values:
            return 0.0

        # Calculate actual time span
        if len(self.values) == 1:
            return 1.0  # Only 1 value, assume 1/min

        time_span = self.values[-1][0] - self.values[0][0]
        if time_span == 0:
            return len(self.values)  # All at same time

        return (len(self.values) / time_span) * 60


class MonitoringMetrics:
    """
    Production monitoring metrics tracker

    Tracks metrics in rolling windows (1 hour by default):
    - Order attempts (success/failure)
    - Position sync attempts
    - API call latencies
    - DLQ accumulation
    - Rate limiter usage
    """

    def __init__(self, window_seconds: int = 3600):
        """
        Initialize metrics tracker

        Args:
            window_seconds: Rolling window size in seconds (default: 1 hour)
        """
        self.window_seconds = window_seconds
        self.lock = Lock()

        # Order metrics
        self.order_attempts = MetricWindow(window_seconds)
        self.order_successes = MetricWindow(window_seconds)
        self.order_failures = MetricWindow(window_seconds)

        # Position sync metrics
        self.position_sync_attempts = MetricWindow(window_seconds)
        self.position_sync_successes = MetricWindow(window_seconds)

        # API latency metrics
        self.api_latencies = MetricWindow(window_seconds)

        # DLQ metrics
        self.dlq_additions = MetricWindow(window_seconds)

        # Rate limiter metrics
        self.rate_limit_waits = MetricWindow(window_seconds)

        # Alert thresholds
        self.thresholds = {
            'order_failure_rate': 0.10,      # Alert if >10% orders fail
            'position_sync_failure_rate': 0.05,  # Alert if >5% syncs fail
            'api_latency_p99_ms': 5000,      # Alert if p99 latency >5s
            'dlq_accumulation_rate': 10,     # Alert if >10 DLQ items/min
            'rate_limit_wait_rate': 5,       # Alert if >5 waits/min
        }

        logger.info(f"MonitoringMetrics initialized (window: {window_seconds}s)")

    def record_order_attempt(
        self,
        symbol: str,
        success: bool,
        latency_ms: float = None,
        error: str = None
    ):
        """
        Record order attempt

        Args:
            symbol: Stock symbol
            success: Whether order succeeded
            latency_ms: API latency in milliseconds
            error: Error message if failed
        """
        with self.lock:
            now = time.time()
            self.order_attempts.add(symbol, now)

            if success:
                self.order_successes.add(symbol, now)
            else:
                self.order_failures.add({'symbol': symbol, 'error': error}, now)

            if latency_ms is not None:
                self.api_latencies.add(latency_ms, now)

    def record_position_sync(self, success: bool, positions_count: int = 0):
        """
        Record position sync attempt

        Args:
            success: Whether sync succeeded
            positions_count: Number of positions synced
        """
        with self.lock:
            now = time.time()
            self.position_sync_attempts.add(success, now)

            if success:
                self.position_sync_successes.add(positions_count, now)

    def record_api_latency(self, latency_ms: float):
        """Record API call latency"""
        with self.lock:
            self.api_latencies.add(latency_ms, time.time())

    def record_dlq_addition(self, operation_type: str):
        """Record DLQ item addition"""
        with self.lock:
            self.dlq_additions.add(operation_type, time.time())

    def record_rate_limit_wait(self, wait_seconds: float):
        """Record rate limiter wait"""
        with self.lock:
            self.rate_limit_waits.add(wait_seconds, time.time())

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics

        Returns:
            Dictionary with all metrics
        """
        with self.lock:
            # Order metrics
            order_attempts = self.order_attempts.get_count()
            order_successes = self.order_successes.get_count()
            order_failures = self.order_failures.get_count()

            order_success_rate = (
                order_successes / order_attempts if order_attempts > 0 else 1.0
            )
            order_failure_rate = (
                order_failures / order_attempts if order_attempts > 0 else 0.0
            )

            # Position sync metrics
            sync_attempts = self.position_sync_attempts.get_count()
            sync_successes = self.position_sync_successes.get_count()

            sync_success_rate = (
                sync_successes / sync_attempts if sync_attempts > 0 else 1.0
            )

            # API latency metrics
            latencies = self.api_latencies.get_values()
            if latencies:
                sorted_latencies = sorted(latencies)
                p50_idx = int(len(sorted_latencies) * 0.50)
                p95_idx = int(len(sorted_latencies) * 0.95)
                p99_idx = int(len(sorted_latencies) * 0.99)

                latency_p50 = sorted_latencies[p50_idx] if p50_idx < len(sorted_latencies) else 0
                latency_p95 = sorted_latencies[p95_idx] if p95_idx < len(sorted_latencies) else 0
                latency_p99 = sorted_latencies[p99_idx] if p99_idx < len(sorted_latencies) else 0
                latency_avg = sum(latencies) / len(latencies)
            else:
                latency_p50 = latency_p95 = latency_p99 = latency_avg = 0

            # DLQ metrics
            dlq_count = self.dlq_additions.get_count()
            dlq_rate_per_min = self.dlq_additions.get_rate_per_minute()

            # Rate limiter metrics
            rate_limit_waits = self.rate_limit_waits.get_count()
            rate_limit_wait_rate = self.rate_limit_waits.get_rate_per_minute()

            return {
                # Order metrics
                'order_attempts': order_attempts,
                'order_successes': order_successes,
                'order_failures': order_failures,
                'order_success_rate': order_success_rate,
                'order_failure_rate': order_failure_rate,

                # Position sync metrics
                'position_sync_attempts': sync_attempts,
                'position_sync_successes': sync_successes,
                'position_sync_success_rate': sync_success_rate,

                # API latency metrics (in milliseconds)
                'api_latency_p50_ms': latency_p50,
                'api_latency_p95_ms': latency_p95,
                'api_latency_p99_ms': latency_p99,
                'api_latency_avg_ms': latency_avg,
                'api_call_count': len(latencies),

                # DLQ metrics
                'dlq_additions_count': dlq_count,
                'dlq_additions_per_min': dlq_rate_per_min,

                # Rate limiter metrics
                'rate_limit_waits_count': rate_limit_waits,
                'rate_limit_waits_per_min': rate_limit_wait_rate,

                # Window info
                'window_seconds': self.window_seconds,
                'timestamp': datetime.now().isoformat(),
            }

    def check_alerts(self) -> List[Dict[str, Any]]:
        """
        Check if any metrics exceed alert thresholds

        Returns:
            List of alerts (empty if all metrics healthy)
        """
        metrics = self.get_metrics()
        alerts = []

        # Check order failure rate
        if metrics['order_failure_rate'] > self.thresholds['order_failure_rate']:
            alerts.append({
                'type': 'order_failure_rate',
                'severity': 'WARNING',
                'message': f"Order failure rate {metrics['order_failure_rate']:.1%} exceeds threshold {self.thresholds['order_failure_rate']:.1%}",
                'value': metrics['order_failure_rate'],
                'threshold': self.thresholds['order_failure_rate']
            })

        # Check position sync failure rate
        if metrics['position_sync_success_rate'] < (1 - self.thresholds['position_sync_failure_rate']):
            alerts.append({
                'type': 'position_sync_failure_rate',
                'severity': 'CRITICAL',
                'message': f"Position sync success rate {metrics['position_sync_success_rate']:.1%} too low",
                'value': metrics['position_sync_success_rate'],
                'threshold': 1 - self.thresholds['position_sync_failure_rate']
            })

        # Check API latency p99
        if metrics['api_latency_p99_ms'] > self.thresholds['api_latency_p99_ms']:
            alerts.append({
                'type': 'api_latency_p99',
                'severity': 'WARNING',
                'message': f"API p99 latency {metrics['api_latency_p99_ms']:.0f}ms exceeds threshold {self.thresholds['api_latency_p99_ms']}ms",
                'value': metrics['api_latency_p99_ms'],
                'threshold': self.thresholds['api_latency_p99_ms']
            })

        # Check DLQ accumulation
        if metrics['dlq_additions_per_min'] > self.thresholds['dlq_accumulation_rate']:
            alerts.append({
                'type': 'dlq_accumulation',
                'severity': 'WARNING',
                'message': f"DLQ additions {metrics['dlq_additions_per_min']:.1f}/min exceeds threshold {self.thresholds['dlq_accumulation_rate']}/min",
                'value': metrics['dlq_additions_per_min'],
                'threshold': self.thresholds['dlq_accumulation_rate']
            })

        # Check rate limiter waits
        if metrics['rate_limit_waits_per_min'] > self.thresholds['rate_limit_wait_rate']:
            alerts.append({
                'type': 'rate_limit_waits',
                'severity': 'INFO',
                'message': f"Rate limit waits {metrics['rate_limit_waits_per_min']:.1f}/min exceeds threshold {self.thresholds['rate_limit_wait_rate']}/min",
                'value': metrics['rate_limit_waits_per_min'],
                'threshold': self.thresholds['rate_limit_wait_rate']
            })

        return alerts

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get overall health status

        Returns:
            Health status dictionary
        """
        alerts = self.check_alerts()

        # Determine overall health
        if any(a['severity'] == 'CRITICAL' for a in alerts):
            health = 'CRITICAL'
        elif any(a['severity'] == 'WARNING' for a in alerts):
            health = 'WARNING'
        elif any(a['severity'] == 'INFO' for a in alerts):
            health = 'INFO'
        else:
            health = 'HEALTHY'

        metrics = self.get_metrics()

        return {
            'status': health,
            'alerts': alerts,
            'alert_count': len(alerts),
            'metrics_summary': {
                'order_success_rate': f"{metrics['order_success_rate']:.1%}",
                'position_sync_success_rate': f"{metrics['position_sync_success_rate']:.1%}",
                'api_latency_p99_ms': f"{metrics['api_latency_p99_ms']:.0f}ms",
                'dlq_additions_per_min': f"{metrics['dlq_additions_per_min']:.1f}/min",
            },
            'timestamp': datetime.now().isoformat()
        }


# =========================================================================
# GLOBAL METRICS TRACKER
# =========================================================================

_metrics_tracker: Optional[MonitoringMetrics] = None


def get_metrics_tracker() -> MonitoringMetrics:
    """Get global metrics tracker instance"""
    global _metrics_tracker
    if _metrics_tracker is None:
        _metrics_tracker = MonitoringMetrics()
    return _metrics_tracker


# =========================================================================
# EXAMPLE USAGE
# =========================================================================

if __name__ == '__main__':
    print("🧪 Testing Monitoring Metrics...")

    # Create tracker
    tracker = MonitoringMetrics(window_seconds=60)  # 1-minute window for testing

    # Test 1: Record order attempts
    print("\n1. Recording order attempts:")
    for i in range(100):
        success = i % 10 != 0  # 90% success rate
        tracker.record_order_attempt(
            symbol='AAPL',
            success=success,
            latency_ms=100 + (i % 50),  # 100-150ms latency
            error='Timeout' if not success else None
        )

    # Test 2: Record position syncs
    print("\n2. Recording position syncs:")
    for i in range(10):
        tracker.record_position_sync(success=True, positions_count=5)

    # Test 3: Get metrics
    print("\n3. Current metrics:")
    metrics = tracker.get_metrics()
    print(f"   Order success rate: {metrics['order_success_rate']:.1%}")
    print(f"   Order failure rate: {metrics['order_failure_rate']:.1%}")
    print(f"   API latency p50: {metrics['api_latency_p50_ms']:.0f}ms")
    print(f"   API latency p99: {metrics['api_latency_p99_ms']:.0f}ms")

    # Test 4: Check alerts
    print("\n4. Checking alerts:")
    alerts = tracker.check_alerts()
    if alerts:
        for alert in alerts:
            print(f"   [{alert['severity']}] {alert['message']}")
    else:
        print("   ✅ No alerts - all metrics healthy")

    # Test 5: Health status
    print("\n5. Health status:")
    health = tracker.get_health_status()
    print(f"   Status: {health['status']}")
    print(f"   Alerts: {health['alert_count']}")
    print(f"   Summary: {health['metrics_summary']}")

    print("\n✅ Tests complete!")
