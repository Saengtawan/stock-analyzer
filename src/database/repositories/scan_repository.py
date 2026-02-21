"""Scan Repository - Database-Backed"""

from datetime import datetime, date
from typing import List, Optional

from ..models.scan_session import ScanSession
from ..manager import get_db_manager
from loguru import logger


class ScanRepository:
    """
    Repository for scan session data access.

    Database-backed storage using scan_sessions table.
    Provides unified API for scan tracking.
    """

    def __init__(self, db_name: str = 'trade_history'):
        """
        Initialize scan repository.

        Args:
            db_name: Database name (default: trade_history)
        """
        self.db = get_db_manager(db_name)

    def create(self, session: ScanSession) -> Optional[int]:
        """
        Create new scan session.

        Args:
            session: ScanSession object

        Returns:
            Session ID if successful, None otherwise
        """
        try:
            session.validate()

            cursor = self.db.execute("""
                INSERT INTO scan_sessions (
                    session_type, scan_time, scan_time_et,
                    mode, is_market_open, market_regime,
                    signal_count, waiting_count, pool_size, scan_duration_seconds,
                    positions_current, positions_max, positions_full,
                    next_scan_et, next_scan_timestamp, next_open, next_close,
                    status, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_type,
                session.scan_time or datetime.now(),
                session.scan_time_et,
                session.mode,
                1 if session.is_market_open else 0,
                session.market_regime,
                session.signal_count,
                session.waiting_count,
                session.pool_size,
                session.scan_duration_seconds,
                session.positions_current,
                session.positions_max,
                1 if session.positions_full else 0,
                session.next_scan_et,
                session.next_scan_timestamp,
                session.next_open,
                session.next_close,
                session.status,
                session.metadata
            ))

            return cursor.lastrowid

        except Exception as e:
            logger.error(f"Failed to create scan session: {e}")
            return None

    def get_latest(self, session_type: Optional[str] = None) -> Optional[ScanSession]:
        """
        Get most recent scan session.

        Args:
            session_type: Optional filter by session type

        Returns:
            ScanSession or None
        """
        try:
            if session_type:
                row = self.db.fetch_one("""
                    SELECT * FROM scan_sessions
                    WHERE session_type = ?
                    ORDER BY scan_time DESC
                    LIMIT 1
                """, (session_type,))
            else:
                row = self.db.fetch_one("""
                    SELECT * FROM scan_sessions
                    ORDER BY scan_time DESC
                    LIMIT 1
                """)

            if row:
                return ScanSession.from_row(dict(row))
            return None

        except Exception as e:
            logger.error(f"Failed to get latest scan session: {e}")
            return None

    def get_by_id(self, session_id: int) -> Optional[ScanSession]:
        """
        Get scan session by ID.

        Args:
            session_id: Session ID

        Returns:
            ScanSession or None
        """
        try:
            row = self.db.fetch_one("""
                SELECT * FROM scan_sessions
                WHERE id = ?
            """, (session_id,))

            if row:
                return ScanSession.from_row(dict(row))
            return None

        except Exception as e:
            logger.error(f"Failed to get scan session {session_id}: {e}")
            return None

    def get_by_type(self, session_type: str, days: int = 7) -> List[ScanSession]:
        """
        Get scan sessions by type.

        Args:
            session_type: Session type (morning, midday, afternoon, etc.)
            days: Number of days to look back

        Returns:
            List of ScanSession objects
        """
        try:
            rows = self.db.fetch_all("""
                SELECT * FROM scan_sessions
                WHERE session_type = ?
                  AND scan_time >= datetime('now', ? || ' days')
                ORDER BY scan_time DESC
            """, (session_type, f'-{days}'))

            return [ScanSession.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get scan sessions for {session_type}: {e}")
            return []

    def get_daily_sessions(self, target_date: Optional[date] = None) -> List[ScanSession]:
        """
        Get all scan sessions for a specific day.

        Args:
            target_date: Target date (default: today)

        Returns:
            List of ScanSession objects
        """
        try:
            target_date = target_date or date.today()
            date_str = target_date.isoformat()

            rows = self.db.fetch_all("""
                SELECT * FROM scan_sessions
                WHERE DATE(scan_time) = ?
                ORDER BY scan_time ASC
            """, (date_str,))

            return [ScanSession.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get daily sessions: {e}")
            return []

    def get_stats(self, days: int = 7) -> dict:
        """
        Get scan statistics for time period.

        Args:
            days: Number of days to analyze

        Returns:
            Stats dictionary
        """
        try:
            row = self.db.fetch_one("""
                SELECT
                    COUNT(*) as total_scans,
                    SUM(signal_count) as total_signals,
                    SUM(waiting_count) as total_waiting,
                    AVG(signal_count) as avg_signals_per_scan,
                    AVG(scan_duration_seconds) as avg_duration,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_scans
                FROM scan_sessions
                WHERE scan_time >= datetime('now', ? || ' days')
            """, (f'-{days}',))

            return dict(row) if row else {}

        except Exception as e:
            logger.error(f"Failed to get scan stats: {e}")
            return {}

    def get_regime_performance(self, days: int = 30) -> List[dict]:
        """
        Get signal performance by market regime.

        Args:
            days: Number of days to analyze

        Returns:
            List of {market_regime, scans, signals, avg_score} dictionaries
        """
        try:
            rows = self.db.fetch_all("""
                SELECT
                    market_regime,
                    COUNT(*) as scans,
                    SUM(signal_count) as total_signals,
                    ROUND(AVG(signal_count), 2) as avg_signals
                FROM scan_sessions
                WHERE scan_time >= datetime('now', ? || ' days')
                  AND market_regime IS NOT NULL
                GROUP BY market_regime
                ORDER BY total_signals DESC
            """, (f'-{days}',))

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get regime performance: {e}")
            return []

    def update_status(self, session_id: int, status: str) -> bool:
        """
        Update scan session status.

        Args:
            session_id: Session ID
            status: New status (running, completed, failed)

        Returns:
            True if successful
        """
        try:
            self.db.execute("""
                UPDATE scan_sessions
                SET status = ?
                WHERE id = ?
            """, (status, session_id))

            return True

        except Exception as e:
            logger.error(f"Failed to update scan session {session_id}: {e}")
            return False

    def delete_old(self, days: int = 90) -> int:
        """
        Delete scan sessions older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of sessions deleted
        """
        try:
            cursor = self.db.execute("""
                DELETE FROM scan_sessions
                WHERE scan_time < datetime('now', ? || ' days')
            """, (f'-{days}',))

            return cursor.rowcount

        except Exception as e:
            logger.error(f"Failed to delete old scan sessions: {e}")
            return 0
