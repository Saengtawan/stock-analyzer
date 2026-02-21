"""Execution Repository - Database-Backed"""

from datetime import datetime, date
from typing import List, Optional

from ..models.execution_record import ExecutionRecord
from ..manager import get_db_manager
from loguru import logger


class ExecutionRepository:
    """
    Repository for execution record data access.

    Database-backed storage using execution_history table.
    Provides unified API for execution tracking.
    """

    def __init__(self, db_name: str = 'trade_history'):
        """
        Initialize execution repository.

        Args:
            db_name: Database name (default: trade_history)
        """
        self.db = get_db_manager(db_name)

    def create(self, record: ExecutionRecord) -> Optional[int]:
        """
        Create new execution record.

        Args:
            record: ExecutionRecord object

        Returns:
            Record ID if successful, None otherwise
        """
        try:
            record.validate()

            cursor = self.db.execute("""
                INSERT INTO execution_history (
                    symbol, action, timestamp, skip_reason,
                    signal_id, signal_score, signal_price,
                    scan_session_id, session_type, market_regime,
                    entry_price, qty, stop_loss, take_profit,
                    metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.symbol,
                record.action,
                record.timestamp or datetime.now(),
                record.skip_reason,
                record.signal_id,
                record.signal_score,
                record.signal_price,
                record.scan_session_id,
                record.session_type,
                record.market_regime,
                record.entry_price,
                record.qty,
                record.stop_loss,
                record.take_profit,
                record.metadata
            ))

            return cursor.lastrowid

        except Exception as e:
            logger.error(f"Failed to create execution record for {record.symbol}: {e}")
            return None

    def create_batch(self, records: List[ExecutionRecord], scan_session_id: Optional[int] = None) -> int:
        """
        Create multiple execution records efficiently.

        Args:
            records: List of ExecutionRecord objects
            scan_session_id: Optional scan session ID to assign

        Returns:
            Number of records created
        """
        count = 0
        for record in records:
            if scan_session_id:
                record.scan_session_id = scan_session_id

            if self.create(record):
                count += 1

        return count

    def get_by_symbol(self, symbol: str, limit: int = 100) -> List[ExecutionRecord]:
        """
        Get execution records for specific symbol.

        Args:
            symbol: Stock symbol
            limit: Maximum number of records

        Returns:
            List of ExecutionRecord objects
        """
        try:
            rows = self.db.fetch_all("""
                SELECT * FROM execution_history
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (symbol, limit))

            return [ExecutionRecord.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get execution records for {symbol}: {e}")
            return []

    def get_last_action(self, symbol: str) -> Optional[ExecutionRecord]:
        """
        Get most recent execution record for symbol.

        Args:
            symbol: Stock symbol

        Returns:
            ExecutionRecord or None
        """
        try:
            row = self.db.fetch_one("""
                SELECT * FROM execution_history
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (symbol,))

            if row:
                return ExecutionRecord.from_row(dict(row))
            return None

        except Exception as e:
            logger.error(f"Failed to get last action for {symbol}: {e}")
            return None

    def get_by_action(self, action: str, days: int = 7) -> List[ExecutionRecord]:
        """
        Get execution records by action type.

        Args:
            action: Action type (BOUGHT, SKIPPED_FILTER, etc.)
            days: Number of days to look back

        Returns:
            List of ExecutionRecord objects
        """
        try:
            rows = self.db.fetch_all("""
                SELECT * FROM execution_history
                WHERE action = ?
                  AND timestamp >= datetime('now', ? || ' days')
                ORDER BY timestamp DESC
            """, (action, f'-{days}'))

            return [ExecutionRecord.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get execution records for action {action}: {e}")
            return []

    def get_daily_summary(self, target_date: Optional[date] = None) -> dict:
        """
        Get daily execution summary.

        Args:
            target_date: Target date (default: today)

        Returns:
            Summary dictionary with counts by action
        """
        try:
            target_date = target_date or date.today()
            date_str = target_date.isoformat()

            rows = self.db.fetch_all("""
                SELECT
                    action,
                    COUNT(*) as count,
                    COUNT(DISTINCT symbol) as unique_symbols
                FROM execution_history
                WHERE DATE(timestamp) = ?
                GROUP BY action
            """, (date_str,))

            summary = {row['action']: {
                'count': row['count'],
                'unique_symbols': row['unique_symbols']
            } for row in rows}

            # Add totals
            total_count = sum(s['count'] for s in summary.values())
            total_symbols = len(set(
                row['symbol'] for row in self.db.fetch_all(
                    "SELECT DISTINCT symbol FROM execution_history WHERE DATE(timestamp) = ?",
                    (date_str,)
                )
            ))

            summary['TOTAL'] = {
                'count': total_count,
                'unique_symbols': total_symbols
            }

            return summary

        except Exception as e:
            logger.error(f"Failed to get daily summary: {e}")
            return {}

    def get_skip_reasons(self, days: int = 30, limit: int = 10) -> List[dict]:
        """
        Get top skip reasons for SKIPPED_FILTER actions.

        Args:
            days: Number of days to analyze
            limit: Maximum number of reasons to return

        Returns:
            List of {skip_reason, count, pct} dictionaries
        """
        try:
            rows = self.db.fetch_all("""
                SELECT
                    skip_reason,
                    COUNT(*) as count,
                    ROUND(100.0 * COUNT(*) / (
                        SELECT COUNT(*) FROM execution_history
                        WHERE action = 'SKIPPED_FILTER'
                          AND timestamp >= datetime('now', ? || ' days')
                    ), 2) as pct
                FROM execution_history
                WHERE action = 'SKIPPED_FILTER'
                  AND skip_reason IS NOT NULL
                  AND timestamp >= datetime('now', ? || ' days')
                GROUP BY skip_reason
                ORDER BY count DESC
                LIMIT ?
            """, (f'-{days}', f'-{days}', limit))

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get skip reasons: {e}")
            return []

    def get_conversion_rate(self, days: int = 7) -> List[dict]:
        """
        Get signal conversion rate by day.

        Args:
            days: Number of days to analyze

        Returns:
            List of {date, total, bought, conversion_rate} dictionaries
        """
        try:
            rows = self.db.fetch_all("""
                SELECT
                    DATE(timestamp) as date,
                    COUNT(*) as total,
                    SUM(CASE WHEN action = 'BOUGHT' THEN 1 ELSE 0 END) as bought,
                    ROUND(100.0 * SUM(CASE WHEN action = 'BOUGHT' THEN 1 ELSE 0 END) / COUNT(*), 2) as conversion_rate
                FROM execution_history
                WHERE timestamp >= datetime('now', ? || ' days')
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
            """, (f'-{days}',))

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get conversion rate: {e}")
            return []

    def delete_old(self, days: int = 180) -> int:
        """
        Delete execution records older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of records deleted
        """
        try:
            cursor = self.db.execute("""
                DELETE FROM execution_history
                WHERE timestamp < datetime('now', ? || ' days')
            """, (f'-{days}',))

            return cursor.rowcount

        except Exception as e:
            logger.error(f"Failed to delete old execution records: {e}")
            return 0
