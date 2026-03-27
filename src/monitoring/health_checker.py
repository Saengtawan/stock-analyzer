"""
Health Checker - Phase 5A
==========================
Comprehensive system health checks for production monitoring.

Checks:
- Database connectivity and integrity
- Repository health (PositionRepository, AlertsRepository, TradeRepository)
- File system (disk space, file access)
- System resources (memory, CPU)
- Data integrity
"""

import os
import psutil
from database.orm.base import get_session; from sqlalchemy import text
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger


@dataclass
class HealthStatus:
    """Health check result"""
    component: str
    status: str  # 'ok', 'warning', 'error'
    message: str
    details: Optional[Dict] = None
    checked_at: str = ''

    def __post_init__(self):
        if not self.checked_at:
            self.checked_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            'component': self.component,
            'status': self.status,
            'message': self.message,
            'details': self.details,
            'checked_at': self.checked_at
        }


class HealthChecker:
    """
    System health checker for production monitoring.

    Performs comprehensive health checks on all critical components.
    """

    # Health check thresholds
    DISK_SPACE_WARNING_GB = 5.0
    DISK_SPACE_CRITICAL_GB = 1.0
    MEMORY_WARNING_PCT = 85
    MEMORY_CRITICAL_PCT = 95
    DB_SIZE_WARNING_MB = 500
    DB_SIZE_CRITICAL_MB = 1000

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize health checker.

        Args:
            data_dir: Data directory path (default: ../data)
        """
        if data_dir is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                '..', 'data'
            )
        self.data_dir = Path(data_dir).resolve()

    # ========================================================================
    # Main Health Check Methods
    # ========================================================================

    def check_all(self) -> Dict:
        """
        Run all health checks and return comprehensive status.

        Returns:
            Dict with overall status and individual check results
        """
        checks = []

        # Database checks
        checks.append(self.check_database_connectivity())
        checks.append(self.check_database_integrity())

        # Repository checks
        checks.append(self.check_position_repository())
        checks.append(self.check_alert_repository())
        checks.append(self.check_trade_repository())

        # System checks
        checks.append(self.check_disk_space())
        checks.append(self.check_memory())
        checks.append(self.check_file_permissions())

        # Determine overall status
        error_count = sum(1 for c in checks if c.status == 'error')
        warning_count = sum(1 for c in checks if c.status == 'warning')

        if error_count > 0:
            overall_status = 'error'
            overall_message = f'{error_count} critical issue(s) detected'
        elif warning_count > 0:
            overall_status = 'warning'
            overall_message = f'{warning_count} warning(s) detected'
        else:
            overall_status = 'ok'
            overall_message = 'All systems operational'

        return {
            'status': overall_status,
            'message': overall_message,
            'timestamp': datetime.now().isoformat(),
            'checks': [c.to_dict() for c in checks],
            'summary': {
                'total': len(checks),
                'ok': sum(1 for c in checks if c.status == 'ok'),
                'warning': warning_count,
                'error': error_count
            }
        }

    # ========================================================================
    # Database Health Checks
    # ========================================================================

    def check_database_connectivity(self) -> HealthStatus:
        """Check database connectivity and basic operations"""
        try:
            from database.manager import get_db_manager

            db = get_db_manager('trade_history')

            # Try a simple query
            result = db.fetch_one("SELECT 1 as test")

            if result and result['test'] == 1:
                return HealthStatus(
                    component='database_connectivity',
                    status='ok',
                    message='Database connection healthy',
                    details={'database': 'trade_history'}
                )
            else:
                return HealthStatus(
                    component='database_connectivity',
                    status='error',
                    message='Database query returned unexpected result'
                )

        except Exception as e:
            return HealthStatus(
                component='database_connectivity',
                status='error',
                message=f'Database connection failed: {str(e)}'
            )

    def check_database_integrity(self) -> HealthStatus:
        """Check database integrity and size"""
        try:
            db_path = self.data_dir / 'trade_history.db'

            if not db_path.exists():
                return HealthStatus(
                    component='database_integrity',
                    status='error',
                    message='Database file not found'
                )

            # Check database size
            size_mb = db_path.stat().st_size / (1024 * 1024)

            # Check integrity
            conn = get_session().__enter__()
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchone()[0]
            conn.close()

            # Determine status based on size
            if size_mb > self.DB_SIZE_CRITICAL_MB:
                status = 'warning'
                message = f'Database size critical: {size_mb:.1f} MB'
            elif size_mb > self.DB_SIZE_WARNING_MB:
                status = 'warning'
                message = f'Database size high: {size_mb:.1f} MB'
            else:
                status = 'ok'
                message = 'Database integrity healthy'

            # Check integrity result
            if integrity_result != 'ok':
                status = 'error'
                message = f'Database integrity check failed: {integrity_result}'

            return HealthStatus(
                component='database_integrity',
                status=status,
                message=message,
                details={
                    'size_mb': round(size_mb, 2),
                    'integrity': integrity_result
                }
            )

        except Exception as e:
            return HealthStatus(
                component='database_integrity',
                status='error',
                message=f'Database integrity check failed: {str(e)}'
            )

    # ========================================================================
    # Repository Health Checks
    # ========================================================================

    def check_position_repository(self) -> HealthStatus:
        """Check PositionRepository health"""
        try:
            from database import PositionRepository

            repo = PositionRepository()

            # Try to get all positions
            positions = repo.get_all()
            count = len(positions)

            # Check if using database
            using_db = repo._use_database

            return HealthStatus(
                component='position_repository',
                status='ok',
                message=f'Position repository healthy ({count} positions)',
                details={
                    'count': count,
                    'using_database': using_db,
                    'backend': 'database' if using_db else 'json'
                }
            )

        except Exception as e:
            return HealthStatus(
                component='position_repository',
                status='error',
                message=f'Position repository check failed: {str(e)}'
            )

    def check_alert_repository(self) -> HealthStatus:
        """Check AlertsRepository health"""
        try:
            from database import AlertsRepository

            repo = AlertsRepository()

            # Get alert counts
            total = repo.count(active_only=False)
            active = repo.count(active_only=True)

            # Check statistics
            stats = repo.get_statistics(hours=24)

            return HealthStatus(
                component='alert_repository',
                status='ok',
                message=f'Alert repository healthy ({total} total, {active} active)',
                details={
                    'total': total,
                    'active': active,
                    'last_24h': stats['total']
                }
            )

        except Exception as e:
            return HealthStatus(
                component='alert_repository',
                status='error',
                message=f'Alert repository check failed: {str(e)}'
            )

    def check_trade_repository(self) -> HealthStatus:
        """Check TradeRepository health"""
        try:
            from database import TradeRepository

            repo = TradeRepository()

            # Try to query trades table to verify connectivity
            # Use get_all with limit
            trades = repo.get_all(limit=10)

            return HealthStatus(
                component='trade_repository',
                status='ok',
                message=f'Trade repository healthy ({len(trades)} recent trades)',
                details={
                    'recent_count': len(trades)
                }
            )

        except Exception as e:
            return HealthStatus(
                component='trade_repository',
                status='error',
                message=f'Trade repository check failed: {str(e)}'
            )

    # ========================================================================
    # System Resource Checks
    # ========================================================================

    def check_disk_space(self) -> HealthStatus:
        """Check available disk space"""
        try:
            disk = psutil.disk_usage(str(self.data_dir))
            free_gb = disk.free / (1024 ** 3)
            used_pct = disk.percent

            if free_gb < self.DISK_SPACE_CRITICAL_GB:
                status = 'error'
                message = f'Critical: Only {free_gb:.1f} GB free'
            elif free_gb < self.DISK_SPACE_WARNING_GB:
                status = 'warning'
                message = f'Warning: {free_gb:.1f} GB free'
            else:
                status = 'ok'
                message = f'Disk space healthy ({free_gb:.1f} GB free)'

            return HealthStatus(
                component='disk_space',
                status=status,
                message=message,
                details={
                    'free_gb': round(free_gb, 2),
                    'used_pct': round(used_pct, 1),
                    'total_gb': round(disk.total / (1024 ** 3), 2)
                }
            )

        except Exception as e:
            return HealthStatus(
                component='disk_space',
                status='error',
                message=f'Disk space check failed: {str(e)}'
            )

    def check_memory(self) -> HealthStatus:
        """Check system memory usage"""
        try:
            memory = psutil.virtual_memory()
            used_pct = memory.percent
            available_gb = memory.available / (1024 ** 3)

            if used_pct > self.MEMORY_CRITICAL_PCT:
                status = 'error'
                message = f'Critical: {used_pct:.1f}% memory used'
            elif used_pct > self.MEMORY_WARNING_PCT:
                status = 'warning'
                message = f'Warning: {used_pct:.1f}% memory used'
            else:
                status = 'ok'
                message = f'Memory healthy ({used_pct:.1f}% used)'

            return HealthStatus(
                component='memory',
                status=status,
                message=message,
                details={
                    'used_pct': round(used_pct, 1),
                    'available_gb': round(available_gb, 2),
                    'total_gb': round(memory.total / (1024 ** 3), 2)
                }
            )

        except Exception as e:
            return HealthStatus(
                component='memory',
                status='error',
                message=f'Memory check failed: {str(e)}'
            )

    def check_file_permissions(self) -> HealthStatus:
        """Check file system permissions"""
        try:
            # Check if data directory is writable
            test_file = self.data_dir / '.health_check_test'

            try:
                test_file.write_text('test')
                test_file.unlink()
                writable = True
            except:
                writable = False

            # Check if critical files exist
            critical_files = [
                'trade_history.db',
            ]

            missing_files = []
            for file in critical_files:
                if not (self.data_dir / file).exists():
                    missing_files.append(file)

            if not writable:
                return HealthStatus(
                    component='file_permissions',
                    status='error',
                    message='Data directory not writable'
                )
            elif missing_files:
                return HealthStatus(
                    component='file_permissions',
                    status='warning',
                    message=f'Missing files: {", ".join(missing_files)}'
                )
            else:
                return HealthStatus(
                    component='file_permissions',
                    status='ok',
                    message='File permissions healthy',
                    details={'data_dir': str(self.data_dir)}
                )

        except Exception as e:
            return HealthStatus(
                component='file_permissions',
                status='error',
                message=f'File permission check failed: {str(e)}'
            )

    # ========================================================================
    # Quick Health Check
    # ========================================================================

    def check_quick(self) -> Dict:
        """
        Quick health check (database + repositories only).

        Returns:
            Dict with basic health status
        """
        checks = [
            self.check_database_connectivity(),
            self.check_position_repository(),
            self.check_alert_repository(),
        ]

        error_count = sum(1 for c in checks if c.status == 'error')

        if error_count > 0:
            overall_status = 'error'
        else:
            overall_status = 'ok'

        return {
            'status': overall_status,
            'timestamp': datetime.now().isoformat(),
            'checks': [c.to_dict() for c in checks]
        }


# ========================================================================
# Singleton Instance
# ========================================================================

_health_checker_instance = None

def get_health_checker() -> HealthChecker:
    """Get or create the singleton HealthChecker instance"""
    global _health_checker_instance
    if _health_checker_instance is None:
        _health_checker_instance = HealthChecker()
    return _health_checker_instance
