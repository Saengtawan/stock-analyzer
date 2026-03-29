"""
Dead Letter Queue Repository - DB-backed DLQ storage (v6.72)

Replaces data/dlq/dead_letter_queue.json with a dead_letter_queue table.
Stores failed operations with full retry/resolution metadata.
"""

import json
from datetime import datetime, date, timedelta
from typing import List

from ..manager import get_db_manager
from loguru import logger


def _json_serial(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


class DLQRepository:
    """Repository for dead letter queue items (replaces DLQ JSON file)."""

    def __init__(self, db_name: str = 'trade_history', _db=None):
        self.db = _db if _db is not None else get_db_manager(db_name)
        self._ensure_table()

    def _ensure_table(self):
        """Create dead_letter_queue table if it doesn't exist."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id TEXT PRIMARY KEY,
                operation_type TEXT NOT NULL,
                operation_data TEXT NOT NULL,
                error TEXT NOT NULL,
                context TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                last_retry_at TEXT,
                resolved_at TEXT,
                resolution_note TEXT,
                next_retry_at TEXT
            )
        """)

    def add(self, item) -> bool:
        """
        Insert a new DLQ item (INSERT OR IGNORE — no duplicate IDs).

        Args:
            item: DLQItem dataclass instance

        Returns:
            True if inserted
        """
        try:
            self.db.execute("""
                INSERT OR IGNORE INTO dead_letter_queue
                    (id, operation_type, operation_data, error, context,
                     status, created_at, retry_count, last_retry_at,
                     resolved_at, resolution_note, next_retry_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.id,
                item.operation_type,
                json.dumps(item.operation_data, default=_json_serial),
                item.error,
                json.dumps(item.context, default=_json_serial) if item.context else None,
                item.status,
                item.created_at,
                item.retry_count,
                item.last_retry_at,
                item.resolved_at,
                item.resolution_note,
                item.next_retry_at,
            ))
            return True
        except Exception as e:
            logger.error(f"DLQRepository.add failed: {e}")
            return False

    def update(self, item) -> bool:
        """
        Update all mutable fields for an existing DLQ item.

        Args:
            item: DLQItem dataclass instance (id must match existing row)

        Returns:
            True if successful
        """
        try:
            self.db.execute("""
                UPDATE dead_letter_queue SET
                    operation_type = ?,
                    operation_data = ?,
                    error = ?,
                    context = ?,
                    status = ?,
                    retry_count = ?,
                    last_retry_at = ?,
                    resolved_at = ?,
                    resolution_note = ?,
                    next_retry_at = ?
                WHERE id = ?
            """, (
                item.operation_type,
                json.dumps(item.operation_data, default=_json_serial),
                item.error,
                json.dumps(item.context, default=_json_serial) if item.context else None,
                item.status,
                item.retry_count,
                item.last_retry_at,
                item.resolved_at,
                item.resolution_note,
                item.next_retry_at,
                item.id,
            ))
            return True
        except Exception as e:
            logger.error(f"DLQRepository.update failed: {e}")
            return False

    def get_all(self) -> List[dict]:
        """
        Fetch all DLQ rows as raw dicts.

        Returns:
            List of row dicts (caller reconstructs DLQItem)
        """
        try:
            rows = self.db.fetch_all("SELECT * FROM dead_letter_queue")
            result = []
            for row in rows:
                d = dict(row)
                d['operation_data'] = json.loads(d['operation_data'])
                d['context'] = json.loads(d['context']) if d['context'] else {}
                result.append(d)
            return result
        except Exception as e:
            logger.error(f"DLQRepository.get_all failed: {e}")
            return []

    def delete_old(self, days: int) -> int:
        """
        Delete resolved/ignored items older than N days.

        Args:
            days: Cutoff in days

        Returns:
            Number of rows deleted
        """
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            cursor = self.db.execute("""
                DELETE FROM dead_letter_queue
                WHERE status IN ('resolved', 'ignored')
                  AND resolved_at < ?
            """, (cutoff,))
            return cursor.rowcount
        except Exception as e:
            logger.error(f"DLQRepository.delete_old failed: {e}")
            return 0

    def get_statistics(self) -> dict:
        """
        Return count per status.

        Returns:
            Dict mapping status -> count
        """
        try:
            rows = self.db.fetch_all("""
                SELECT status, COUNT(*) as cnt
                FROM dead_letter_queue
                GROUP BY status
            """)
            return {row['status']: row['cnt'] for row in rows}
        except Exception as e:
            logger.error(f"DLQRepository.get_statistics failed: {e}")
            return {}
