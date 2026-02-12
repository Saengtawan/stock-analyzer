"""
Automatic Monitoring Service - Phase 5D (Bonus)
================================================
Background monitoring service that automatically:
- Runs health checks periodically
- Tracks performance metrics
- Sends alerts on issues
- Logs monitoring data
"""

import time
import threading
from datetime import datetime
from typing import Optional, Callable
from loguru import logger

from .health_checker import HealthChecker, get_health_checker
from .performance_monitor import PerformanceMonitor, get_performance_monitor


class AutoMonitor:
    """
    Automatic monitoring service that runs in background.

    Features:
    - Periodic health checks (every 5 minutes)
    - Performance monitoring
    - Automatic alerting
    - Health score tracking
    """

    def __init__(self,
                 health_check_interval: int = 300,  # 5 minutes
                 alert_threshold: float = 70.0,      # Alert if health < 70
                 enabled: bool = True):
        """
        Initialize automatic monitoring.

        Args:
            health_check_interval: Seconds between health checks (default: 300)
            alert_threshold: Health score threshold for alerts (default: 70)
            enabled: Enable/disable monitoring (default: True)
        """
        self.health_check_interval = health_check_interval
        self.alert_threshold = alert_threshold
        self.enabled = enabled

        self._health_checker = get_health_checker()
        self._perf_monitor = get_performance_monitor()

        self._monitoring_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._alert_callbacks = []

        # Tracking
        self._last_health_status = None
        self._last_health_score = 100.0
        self._health_check_count = 0
        self._alert_count = 0

    # ========================================================================
    # Control Methods
    # ========================================================================

    def start(self):
        """Start automatic monitoring in background thread"""
        if not self.enabled:
            logger.info("AutoMonitor disabled, not starting")
            return

        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("AutoMonitor already running")
            return

        self._stop_event.clear()
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="AutoMonitor"
        )
        self._monitoring_thread.start()
        logger.info(f"AutoMonitor started (health checks every {self.health_check_interval}s)")

    def stop(self):
        """Stop automatic monitoring"""
        if not self._monitoring_thread:
            return

        logger.info("Stopping AutoMonitor...")
        self._stop_event.set()

        if self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5)

        logger.info("AutoMonitor stopped")

    def is_running(self) -> bool:
        """Check if monitoring is running"""
        return (self._monitoring_thread is not None and
                self._monitoring_thread.is_alive() and
                not self._stop_event.is_set())

    # ========================================================================
    # Alert Callbacks
    # ========================================================================

    def add_alert_callback(self, callback: Callable[[dict], None]):
        """
        Add callback function to be called on alerts.

        Args:
            callback: Function that takes alert dict as parameter
        """
        self._alert_callbacks.append(callback)

    def _trigger_alert(self, alert_type: str, message: str, details: dict = None):
        """Trigger alert to all registered callbacks"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'type': alert_type,
            'message': message,
            'details': details or {}
        }

        logger.warning(f"ALERT [{alert_type}]: {message}")
        self._alert_count += 1

        # Call all registered callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

        # Also create alert in AlertsRepository
        try:
            from database import AlertsRepository, Alert

            repo = AlertsRepository()
            db_alert = Alert(
                level='WARNING' if alert_type == 'health' else 'ERROR',
                message=message,
                timestamp=alert['timestamp'],
                active=True,
                metadata={'type': alert_type, 'details': details}
            )
            repo.create(db_alert)
        except Exception as e:
            logger.error(f"Failed to create alert in database: {e}")

    # ========================================================================
    # Monitoring Loop
    # ========================================================================

    def _monitoring_loop(self):
        """Main monitoring loop (runs in background thread)"""
        logger.info("AutoMonitor loop started")

        while not self._stop_event.is_set():
            try:
                self._run_health_check()
                self._check_performance()

            except Exception as e:
                logger.error(f"AutoMonitor error: {e}")

            # Wait for next interval (with ability to stop early)
            self._stop_event.wait(timeout=self.health_check_interval)

        logger.info("AutoMonitor loop stopped")

    def _run_health_check(self):
        """Run health check and alert if issues found"""
        try:
            # Run health check
            health_result = self._health_checker.check_all()

            self._health_check_count += 1
            current_status = health_result['status']

            # Log health check
            logger.debug(f"Health check #{self._health_check_count}: {current_status}")

            # Check for status changes
            if self._last_health_status != current_status:
                if current_status == 'error':
                    self._trigger_alert(
                        'health',
                        f"System health degraded to ERROR: {health_result['message']}",
                        {'summary': health_result['summary']}
                    )
                elif current_status == 'warning':
                    self._trigger_alert(
                        'health',
                        f"System health warning: {health_result['message']}",
                        {'summary': health_result['summary']}
                    )
                elif self._last_health_status in ('error', 'warning'):
                    # Recovered
                    logger.info(f"System health recovered to {current_status}")

                self._last_health_status = current_status

            # Log failed checks
            if health_result['summary']['error'] > 0:
                failed_checks = [
                    c['component'] for c in health_result['checks']
                    if c['status'] == 'error'
                ]
                logger.warning(f"Failed health checks: {', '.join(failed_checks)}")

        except Exception as e:
            logger.error(f"Health check failed: {e}")

    def _check_performance(self):
        """Check performance metrics and alert if degraded"""
        try:
            # Get performance summary
            summary = self._perf_monitor.get_summary()

            current_score = summary['health_score']

            # Check for score drop
            if current_score < self.alert_threshold:
                if self._last_health_score >= self.alert_threshold:
                    # Score just dropped below threshold
                    self._trigger_alert(
                        'performance',
                        f"Performance degraded: {current_score:.1f}/100",
                        {
                            'health_score': current_score,
                            'status': summary['status'],
                            'avg_query_ms': summary['avg_query_time_ms'],
                            'cache_hit_rate': summary['cache_hit_rate']
                        }
                    )

            # Check for slow queries
            if summary['avg_query_time_ms'] > 50:
                logger.warning(f"Slow queries detected: {summary['avg_query_time_ms']:.1f}ms avg")

            # Check for low cache hit rate
            if summary['cache_hit_rate'] < 50 and summary['total_queries'] > 10:
                logger.warning(f"Low cache hit rate: {summary['cache_hit_rate']:.1f}%")

            self._last_health_score = current_score

        except Exception as e:
            logger.error(f"Performance check failed: {e}")

    # ========================================================================
    # Statistics
    # ========================================================================

    def get_stats(self) -> dict:
        """Get monitoring statistics"""
        return {
            'running': self.is_running(),
            'health_checks_run': self._health_check_count,
            'alerts_triggered': self._alert_count,
            'last_health_status': self._last_health_status,
            'last_health_score': round(self._last_health_score, 1),
            'check_interval_seconds': self.health_check_interval,
            'alert_threshold': self.alert_threshold
        }


# ========================================================================
# Singleton Instance
# ========================================================================

_auto_monitor_instance = None

def get_auto_monitor() -> AutoMonitor:
    """Get or create the singleton AutoMonitor instance"""
    global _auto_monitor_instance
    if _auto_monitor_instance is None:
        _auto_monitor_instance = AutoMonitor()
    return _auto_monitor_instance


def start_auto_monitoring(health_check_interval: int = 300,
                          alert_threshold: float = 70.0):
    """
    Convenience function to start automatic monitoring.

    Args:
        health_check_interval: Seconds between health checks (default: 300)
        alert_threshold: Health score threshold for alerts (default: 70)
    """
    monitor = get_auto_monitor()
    monitor.health_check_interval = health_check_interval
    monitor.alert_threshold = alert_threshold
    monitor.start()
    return monitor


def stop_auto_monitoring():
    """Convenience function to stop automatic monitoring"""
    monitor = get_auto_monitor()
    monitor.stop()
