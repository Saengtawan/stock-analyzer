"""Alerts Repository - Phase 4B"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict
from dataclasses import dataclass

from ..manager import get_db_manager
from loguru import logger


@dataclass
class Alert:
    """Alert model"""
    id: Optional[int] = None
    level: str = 'INFO'  # INFO, WARNING, ERROR, CRITICAL
    message: str = ''
    timestamp: str = ''
    active: bool = True
    resolved_at: Optional[str] = None
    metadata: Optional[Dict] = None
    created_at: Optional[str] = None

    def validate(self):
        """Validate alert data"""
        if not self.message:
            raise ValueError("Alert message is required")

        if self.level not in ('INFO', 'WARNING', 'ERROR', 'CRITICAL'):
            raise ValueError(f"Invalid alert level: {self.level}")

        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'level': self.level,
            'message': self.message,
            'timestamp': self.timestamp,
            'active': self.active,
            'resolved_at': self.resolved_at,
            'metadata': self.metadata,
            'created_at': self.created_at
        }

    @classmethod
    def from_row(cls, row: Dict) -> 'Alert':
        """Create Alert from database row"""
        import json

        # Parse metadata JSON if present
        metadata = None
        if row.get('metadata'):
            try:
                metadata = json.loads(row['metadata'])
            except:
                metadata = None

        return cls(
            id=row.get('id'),
            level=row.get('level', 'INFO'),
            message=row.get('message', ''),
            timestamp=row.get('timestamp', ''),
            active=bool(row.get('active', 1)),
            resolved_at=row.get('resolved_at'),
            metadata=metadata,
            created_at=row.get('created_at')
        )


class AlertsRepository:
    """
    Repository for alerts data access.

    Phase 4B: Database-backed alert management
    Provides unified API for alert tracking and management.
    """

    def __init__(self, db_name: str = 'trade_history'):
        """
        Initialize alerts repository.

        Args:
            db_name: Database name (default: trade_history)
        """
        self.db = get_db_manager(db_name)

        # Verify table exists
        try:
            self.db.fetch_one("SELECT COUNT(*) FROM alerts")
        except Exception as e:
            raise RuntimeError(f"alerts table not found: {e}")

    def get_all(self, limit: int = 1000) -> List[Alert]:
        """
        Get all alerts.

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of Alert objects
        """
        try:
            rows = self.db.fetch_all(
                "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )

            return [Alert.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get all alerts: {e}")
            return []

    def get_active(self, limit: int = 100) -> List[Alert]:
        """
        Get all active alerts.

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of active Alert objects
        """
        try:
            rows = self.db.fetch_all(
                "SELECT * FROM alerts WHERE active = 1 ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )

            return [Alert.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get active alerts: {e}")
            return []

    def get_by_level(self, level: str, limit: int = 100) -> List[Alert]:
        """
        Get alerts by severity level.

        Args:
            level: Alert level (INFO, WARNING, ERROR, CRITICAL)
            limit: Maximum number of alerts to return

        Returns:
            List of Alert objects
        """
        try:
            rows = self.db.fetch_all(
                "SELECT * FROM alerts WHERE level = ? ORDER BY timestamp DESC LIMIT ?",
                (level, limit)
            )

            return [Alert.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get alerts by level: {e}")
            return []

    def get_recent(self, hours: int = 24, limit: int = 100) -> List[Alert]:
        """
        Get recent alerts within specified hours.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of alerts to return

        Returns:
            List of Alert objects
        """
        try:
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

            rows = self.db.fetch_all(
                "SELECT * FROM alerts WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                (cutoff, limit)
            )

            return [Alert.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get recent alerts: {e}")
            return []

    def get_by_id(self, alert_id: int) -> Optional[Alert]:
        """
        Get alert by ID.

        Args:
            alert_id: Alert ID

        Returns:
            Alert object or None
        """
        try:
            row = self.db.fetch_one(
                "SELECT * FROM alerts WHERE id = ?",
                (alert_id,)
            )

            if row:
                return Alert.from_row(dict(row))

            return None

        except Exception as e:
            logger.error(f"Failed to get alert by ID: {e}")
            return None

    def create(self, alert: Alert) -> Optional[int]:
        """
        Create new alert.

        Args:
            alert: Alert object

        Returns:
            Alert ID if successful, None otherwise
        """
        import json

        # Validate
        alert.validate()

        try:
            # Prepare metadata
            metadata_json = None
            if alert.metadata:
                metadata_json = json.dumps(alert.metadata)

            # Insert alert
            cursor = self.db.execute("""
                INSERT INTO alerts (
                    level, message, timestamp, active,
                    resolved_at, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                alert.level,
                alert.message,
                alert.timestamp,
                1 if alert.active else 0,
                alert.resolved_at,
                metadata_json,
                datetime.now().isoformat()
            ))

            # Get the inserted ID
            alert_id = cursor.lastrowid

            logger.info(f"Alert created: [{alert.level}] {alert.message}")

            return alert_id

        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
            return None

    def resolve(self, alert_id: int) -> bool:
        """
        Mark alert as resolved.

        Args:
            alert_id: Alert ID

        Returns:
            True if successful
        """
        try:
            self.db.execute("""
                UPDATE alerts
                SET active = 0, resolved_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), alert_id))

            logger.info(f"Alert {alert_id} resolved")

            return True

        except Exception as e:
            logger.error(f"Failed to resolve alert: {e}")
            return False

    def resolve_all(self, level: Optional[str] = None) -> int:
        """
        Resolve all active alerts, optionally filtered by level.

        Args:
            level: Alert level to filter (optional)

        Returns:
            Number of alerts resolved
        """
        try:
            if level:
                cursor = self.db.execute("""
                    UPDATE alerts
                    SET active = 0, resolved_at = ?
                    WHERE active = 1 AND level = ?
                """, (datetime.now().isoformat(), level))
            else:
                cursor = self.db.execute("""
                    UPDATE alerts
                    SET active = 0, resolved_at = ?
                    WHERE active = 1
                """, (datetime.now().isoformat(),))

            count = cursor.rowcount

            logger.info(f"Resolved {count} alerts" + (f" (level: {level})" if level else ""))

            return count

        except Exception as e:
            logger.error(f"Failed to resolve all alerts: {e}")
            return 0

    def delete_old(self, days: int = 30) -> int:
        """
        Delete old resolved alerts.

        Args:
            days: Delete alerts older than this many days

        Returns:
            Number of alerts deleted
        """
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

            cursor = self.db.execute("""
                DELETE FROM alerts
                WHERE active = 0 AND resolved_at < ?
            """, (cutoff,))

            count = cursor.rowcount

            logger.info(f"Deleted {count} old alerts (older than {days} days)")

            return count

        except Exception as e:
            logger.error(f"Failed to delete old alerts: {e}")
            return 0

    def get_statistics(self, hours: int = 24) -> Dict:
        """
        Get alert statistics for the specified time period.

        Args:
            hours: Number of hours to analyze

        Returns:
            Dictionary with alert statistics
        """
        try:
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

            # Get counts by level
            rows = self.db.fetch_all("""
                SELECT level, COUNT(*) as count
                FROM alerts
                WHERE timestamp >= ?
                GROUP BY level
            """, (cutoff,))

            by_level = {row['level']: row['count'] for row in rows}

            # Get active count
            active_row = self.db.fetch_one("""
                SELECT COUNT(*) as count
                FROM alerts
                WHERE active = 1
            """)

            active_count = active_row['count'] if active_row else 0

            # Get total count
            total_row = self.db.fetch_one("""
                SELECT COUNT(*) as count
                FROM alerts
                WHERE timestamp >= ?
            """, (cutoff,))

            total_count = total_row['count'] if total_row else 0

            return {
                'period_hours': hours,
                'total': total_count,
                'active': active_count,
                'by_level': by_level,
                'info': by_level.get('INFO', 0),
                'warning': by_level.get('WARNING', 0),
                'error': by_level.get('ERROR', 0),
                'critical': by_level.get('CRITICAL', 0)
            }

        except Exception as e:
            logger.error(f"Failed to get alert statistics: {e}")
            return {
                'period_hours': hours,
                'total': 0,
                'active': 0,
                'by_level': {},
                'info': 0,
                'warning': 0,
                'error': 0,
                'critical': 0
            }

    def count(self, active_only: bool = False) -> int:
        """
        Get total number of alerts.

        Args:
            active_only: Count only active alerts

        Returns:
            Alert count
        """
        try:
            if active_only:
                row = self.db.fetch_one("SELECT COUNT(*) as count FROM alerts WHERE active = 1")
            else:
                row = self.db.fetch_one("SELECT COUNT(*) as count FROM alerts")

            return row['count'] if row else 0

        except Exception as e:
            logger.error(f"Failed to count alerts: {e}")
            return 0
