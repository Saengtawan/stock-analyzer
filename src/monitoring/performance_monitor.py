"""
Performance Monitor - Phase 5B
===============================
Track and analyze system performance metrics.

Metrics:
- Query execution times
- Database size and growth
- API response times
- Cache hit rates
- Repository performance
"""

import os
import time
from database.orm.base import get_session; from sqlalchemy import text
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from contextlib import contextmanager
from loguru import logger


@dataclass
class PerformanceMetric:
    """Single performance metric"""
    metric_type: str  # query, api, cache, db_size
    component: str    # repository name, endpoint, etc.
    value: float      # metric value (ms, MB, %, etc.)
    unit: str         # ms, MB, pct, count
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return {
            'metric_type': self.metric_type,
            'component': self.component,
            'value': self.value,
            'unit': self.unit,
            'timestamp': self.timestamp,
            'metadata': self.metadata
        }


class PerformanceMonitor:
    """
    Performance monitoring and metrics collection.

    Tracks:
    - Query execution times
    - Database size and growth
    - API response times
    - Repository performance
    """

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize performance monitor.

        Args:
            data_dir: Data directory path (default: ../data)
        """
        if data_dir is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                '..', 'data'
            )
        self.data_dir = Path(data_dir).resolve()
        self._metrics_cache = []
        self._cache_size_limit = 1000

    # ========================================================================
    # Metric Collection
    # ========================================================================

    def record_query_time(self, component: str, duration_ms: float, query_type: str = 'select'):
        """
        Record database query execution time.

        Args:
            component: Component name (e.g., 'PositionRepository')
            duration_ms: Query duration in milliseconds
            query_type: Type of query (select, insert, update, delete)
        """
        metric = PerformanceMetric(
            metric_type='query',
            component=component,
            value=duration_ms,
            unit='ms',
            metadata={'query_type': query_type}
        )
        self._add_metric(metric)

    def record_api_time(self, endpoint: str, duration_ms: float, status_code: int):
        """
        Record API endpoint response time.

        Args:
            endpoint: API endpoint path
            duration_ms: Response time in milliseconds
            status_code: HTTP status code
        """
        metric = PerformanceMetric(
            metric_type='api',
            component=endpoint,
            value=duration_ms,
            unit='ms',
            metadata={'status_code': status_code}
        )
        self._add_metric(metric)

    def record_cache_hit(self, component: str, hit: bool):
        """
        Record cache hit/miss.

        Args:
            component: Component name
            hit: True if cache hit, False if miss
        """
        metric = PerformanceMetric(
            metric_type='cache',
            component=component,
            value=1.0 if hit else 0.0,
            unit='hit',
            metadata={'hit': hit}
        )
        self._add_metric(metric)

    def record_db_size(self, database: str, size_mb: float):
        """
        Record database size.

        Args:
            database: Database name
            size_mb: Size in megabytes
        """
        metric = PerformanceMetric(
            metric_type='db_size',
            component=database,
            value=size_mb,
            unit='MB'
        )
        self._add_metric(metric)

    def _add_metric(self, metric: PerformanceMetric):
        """Add metric to cache"""
        self._metrics_cache.append(metric)

        # Trim cache if too large
        if len(self._metrics_cache) > self._cache_size_limit:
            self._metrics_cache = self._metrics_cache[-self._cache_size_limit:]

    # ========================================================================
    # Context Managers for Automatic Timing
    # ========================================================================

    @contextmanager
    def measure_query(self, component: str, query_type: str = 'select'):
        """
        Context manager to measure query execution time.

        Usage:
            with monitor.measure_query('PositionRepository', 'select'):
                positions = repo.get_all()
        """
        start_time = time.time()
        try:
            yield
        finally:
            duration_ms = (time.time() - start_time) * 1000
            self.record_query_time(component, duration_ms, query_type)

    @contextmanager
    def measure_api(self, endpoint: str):
        """
        Context manager to measure API response time.

        Usage:
            with monitor.measure_api('/api/rapid/alerts'):
                result = get_alerts()
        """
        start_time = time.time()
        status_code = 200
        try:
            yield lambda code: setattr(self, '_temp_status', code)
        finally:
            duration_ms = (time.time() - start_time) * 1000
            status = getattr(self, '_temp_status', 200)
            self.record_api_time(endpoint, duration_ms, status)

    # ========================================================================
    # Metrics Retrieval
    # ========================================================================

    def get_query_stats(self, component: Optional[str] = None, hours: int = 24) -> Dict:
        """
        Get query performance statistics.

        Args:
            component: Filter by component (optional)
            hours: Time window in hours

        Returns:
            Dict with query statistics
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        # Filter metrics
        metrics = [
            m for m in self._metrics_cache
            if m.metric_type == 'query'
            and m.timestamp >= cutoff
            and (component is None or m.component == component)
        ]

        if not metrics:
            return {
                'count': 0,
                'avg_ms': 0,
                'min_ms': 0,
                'max_ms': 0,
                'p50_ms': 0,
                'p95_ms': 0,
                'p99_ms': 0
            }

        values = sorted([m.value for m in metrics])
        count = len(values)

        return {
            'count': count,
            'avg_ms': round(sum(values) / count, 2),
            'min_ms': round(min(values), 2),
            'max_ms': round(max(values), 2),
            'p50_ms': round(values[int(count * 0.5)], 2),
            'p95_ms': round(values[int(count * 0.95)], 2) if count > 20 else round(max(values), 2),
            'p99_ms': round(values[int(count * 0.99)], 2) if count > 100 else round(max(values), 2)
        }

    def get_api_stats(self, endpoint: Optional[str] = None, hours: int = 24) -> Dict:
        """
        Get API performance statistics.

        Args:
            endpoint: Filter by endpoint (optional)
            hours: Time window in hours

        Returns:
            Dict with API statistics
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        # Filter metrics
        metrics = [
            m for m in self._metrics_cache
            if m.metric_type == 'api'
            and m.timestamp >= cutoff
            and (endpoint is None or m.component == endpoint)
        ]

        if not metrics:
            return {
                'count': 0,
                'avg_ms': 0,
                'min_ms': 0,
                'max_ms': 0,
                'p95_ms': 0,
                'success_rate': 0
            }

        values = sorted([m.value for m in metrics])
        count = len(values)

        # Calculate success rate (2xx and 3xx status codes)
        success_count = sum(
            1 for m in metrics
            if m.metadata and 200 <= m.metadata.get('status_code', 500) < 400
        )

        return {
            'count': count,
            'avg_ms': round(sum(values) / count, 2),
            'min_ms': round(min(values), 2),
            'max_ms': round(max(values), 2),
            'p95_ms': round(values[int(count * 0.95)], 2) if count > 20 else round(max(values), 2),
            'success_rate': round((success_count / count) * 100, 1) if count > 0 else 0
        }

    def get_cache_stats(self, component: Optional[str] = None, hours: int = 24) -> Dict:
        """
        Get cache performance statistics.

        Args:
            component: Filter by component (optional)
            hours: Time window in hours

        Returns:
            Dict with cache statistics
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        # Filter metrics
        metrics = [
            m for m in self._metrics_cache
            if m.metric_type == 'cache'
            and m.timestamp >= cutoff
            and (component is None or m.component == component)
        ]

        if not metrics:
            return {
                'total': 0,
                'hits': 0,
                'misses': 0,
                'hit_rate': 0
            }

        hits = sum(1 for m in metrics if m.value == 1.0)
        misses = len(metrics) - hits

        return {
            'total': len(metrics),
            'hits': hits,
            'misses': misses,
            'hit_rate': round((hits / len(metrics)) * 100, 1) if metrics else 0
        }

    def get_database_stats(self) -> Dict:
        """
        Get current database statistics.

        Returns:
            Dict with database statistics
        """
        stats = {}

        # Check trade_history.db
        trade_db = self.data_dir / 'trade_history.db'
        if trade_db.exists():
            size_mb = trade_db.stat().st_size / (1024 * 1024)
            stats['trade_history'] = {
                'size_mb': round(size_mb, 2),
                'exists': True
            }

            # Get table counts
            try:
                conn = get_session().__enter__()
                cursor = conn.cursor()

                # Count positions
                cursor.execute("SELECT COUNT(*) FROM active_positions")
                positions_count = cursor.fetchone()[0]

                # Count alerts
                cursor.execute("SELECT COUNT(*) FROM alerts")
                alerts_count = cursor.fetchone()[0]

                # Count trades
                cursor.execute("SELECT COUNT(*) FROM trades")
                trades_count = cursor.fetchone()[0]

                conn.close()

                stats['trade_history'].update({
                    'positions': positions_count,
                    'alerts': alerts_count,
                    'trades': trades_count
                })

            except Exception as e:
                logger.warning(f"Failed to get table counts: {e}")

        # Check stocks.db
        stocks_db = self.data_dir / 'stocks.db'
        if stocks_db.exists():
            size_mb = stocks_db.stat().st_size / (1024 * 1024)
            stats['stocks'] = {
                'size_mb': round(size_mb, 2),
                'exists': True
            }

        return stats

    def get_all_stats(self, hours: int = 24) -> Dict:
        """
        Get all performance statistics.

        Args:
            hours: Time window in hours

        Returns:
            Dict with all statistics
        """
        return {
            'timestamp': datetime.now().isoformat(),
            'window_hours': hours,
            'queries': self.get_query_stats(hours=hours),
            'api': self.get_api_stats(hours=hours),
            'cache': self.get_cache_stats(hours=hours),
            'database': self.get_database_stats()
        }

    # ========================================================================
    # Repository-Specific Stats
    # ========================================================================

    def get_repository_stats(self, hours: int = 24) -> Dict:
        """
        Get performance statistics by repository.

        Returns:
            Dict with stats for each repository
        """
        repositories = ['PositionRepository', 'AlertsRepository', 'TradeRepository']
        stats = {}

        for repo in repositories:
            stats[repo] = self.get_query_stats(component=repo, hours=hours)

        return stats

    # ========================================================================
    # Metrics Summary
    # ========================================================================

    def get_summary(self) -> Dict:
        """
        Get performance summary for the last 24 hours.

        Returns:
            Dict with summary statistics
        """
        all_stats = self.get_all_stats(hours=24)

        # Calculate overall health score (0-100)
        health_score = 100

        # Deduct points for slow queries
        avg_query_ms = all_stats['queries'].get('avg_ms', 0)
        if avg_query_ms > 10:
            health_score -= min(20, (avg_query_ms - 10) / 2)

        # Deduct points for slow API
        avg_api_ms = all_stats['api'].get('avg_ms', 0)
        if avg_api_ms > 100:
            health_score -= min(20, (avg_api_ms - 100) / 10)

        # Deduct points for low cache hit rate
        cache_hit_rate = all_stats['cache'].get('hit_rate', 100)
        if cache_hit_rate < 80:
            health_score -= (80 - cache_hit_rate) / 4

        # Deduct points for low API success rate
        api_success_rate = all_stats['api'].get('success_rate', 100)
        if api_success_rate < 95:
            health_score -= (95 - api_success_rate)

        health_score = max(0, round(health_score, 1))

        return {
            'health_score': health_score,
            'status': 'excellent' if health_score >= 90 else 'good' if health_score >= 70 else 'fair' if health_score >= 50 else 'poor',
            'total_queries': all_stats['queries']['count'],
            'total_api_requests': all_stats['api']['count'],
            'avg_query_time_ms': all_stats['queries']['avg_ms'],
            'avg_api_time_ms': all_stats['api']['avg_ms'],
            'cache_hit_rate': all_stats['cache']['hit_rate'],
            'api_success_rate': all_stats['api']['success_rate'],
            'timestamp': datetime.now().isoformat()
        }


# ========================================================================
# Singleton Instance
# ========================================================================

_performance_monitor_instance = None

def get_performance_monitor() -> PerformanceMonitor:
    """Get or create the singleton PerformanceMonitor instance"""
    global _performance_monitor_instance
    if _performance_monitor_instance is None:
        _performance_monitor_instance = PerformanceMonitor()
    return _performance_monitor_instance
