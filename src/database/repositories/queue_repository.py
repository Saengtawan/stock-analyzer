"""Queue Repository - Database-Backed"""

from datetime import datetime
from typing import List, Optional

from ..models.queued_signal import QueuedSignal
from ..manager import get_db_manager
from loguru import logger


class QueueRepository:
    """
    Repository for signal queue data access.

    Database-backed storage using signal_queue table.
    Provides unified API for queue management.
    """

    def __init__(self, db_name: str = 'trade_history'):
        """
        Initialize queue repository.

        Args:
            db_name: Database name (default: trade_history)
        """
        self.db = get_db_manager(db_name)

    def get_all(self, status: str = "waiting") -> List[QueuedSignal]:
        """
        Get all queued signals.

        Args:
            status: Filter by status (waiting, executing, removed)

        Returns:
            List of QueuedSignal objects ordered by score DESC, queued_at ASC
        """
        try:
            rows = self.db.fetch_all("""
                SELECT * FROM signal_queue
                WHERE status = ?
                ORDER BY score DESC, queued_at ASC
            """, (status,))

            return [QueuedSignal.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get queue: {e}")
            return []

    def get_by_symbol(self, symbol: str) -> Optional[QueuedSignal]:
        """
        Get queued signal by symbol.

        Args:
            symbol: Stock symbol

        Returns:
            QueuedSignal or None
        """
        try:
            row = self.db.fetch_one("""
                SELECT * FROM signal_queue
                WHERE symbol = ?
            """, (symbol,))

            if row:
                return QueuedSignal.from_row(dict(row))
            return None

        except Exception as e:
            logger.error(f"Failed to get queued signal {symbol}: {e}")
            return None

    def get_top(self, n: int = 1) -> List[QueuedSignal]:
        """
        Get top N signals by score.

        Args:
            n: Number of signals to retrieve

        Returns:
            List of top QueuedSignal objects
        """
        try:
            rows = self.db.fetch_all("""
                SELECT * FROM signal_queue
                WHERE status = 'waiting'
                ORDER BY score DESC, queued_at ASC
                LIMIT ?
            """, (n,))

            return [QueuedSignal.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get top signals: {e}")
            return []

    def add(self, signal: QueuedSignal) -> bool:
        """
        Add signal to queue (INSERT OR REPLACE).

        Args:
            signal: QueuedSignal object

        Returns:
            True if successful
        """
        try:
            signal.validate()

            # Import json for reasons serialization
            import json
            reasons_json = json.dumps(signal.reasons) if signal.reasons else None

            self.db.execute("""
                INSERT OR REPLACE INTO signal_queue (
                    symbol, signal_price, score,
                    stop_loss, take_profit, sl_pct, tp_pct,
                    queued_at, attempts, last_attempt_at,
                    atr_pct, reasons,
                    signal_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.symbol,
                signal.signal_price,
                signal.score,
                signal.stop_loss,
                signal.take_profit,
                signal.sl_pct,
                signal.tp_pct,
                signal.queued_at or datetime.now(),
                signal.attempts,
                signal.last_attempt_at,
                signal.atr_pct,
                reasons_json,
                signal.signal_id,
                signal.status
            ))

            return True

        except Exception as e:
            logger.error(f"Failed to add signal {signal.symbol} to queue: {e}")
            return False

    def remove(self, symbol: str) -> bool:
        """
        Remove signal from queue.

        Args:
            symbol: Stock symbol

        Returns:
            True if successful
        """
        try:
            self.db.execute("""
                DELETE FROM signal_queue
                WHERE symbol = ?
            """, (symbol,))

            return True

        except Exception as e:
            logger.error(f"Failed to remove signal {symbol} from queue: {e}")
            return False

    def clear(self) -> int:
        """
        Clear all waiting signals from queue.

        Returns:
            Number of signals removed
        """
        try:
            cursor = self.db.execute("""
                DELETE FROM signal_queue
                WHERE status = 'waiting'
            """)

            return cursor.rowcount

        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")
            return 0

    def increment_attempts(self, symbol: str) -> bool:
        """
        Increment execution attempts for signal.

        Args:
            symbol: Stock symbol

        Returns:
            True if successful
        """
        try:
            self.db.execute("""
                UPDATE signal_queue
                SET attempts = attempts + 1,
                    last_attempt_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE symbol = ?
            """, (datetime.now(), symbol))

            return True

        except Exception as e:
            logger.error(f"Failed to increment attempts for {symbol}: {e}")
            return False

    def update_status(self, symbol: str, status: str) -> bool:
        """
        Update signal status.

        Args:
            symbol: Stock symbol
            status: New status (waiting, executing, removed)

        Returns:
            True if successful
        """
        try:
            self.db.execute("""
                UPDATE signal_queue
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE symbol = ?
            """, (status, symbol))

            return True

        except Exception as e:
            logger.error(f"Failed to update status for {symbol}: {e}")
            return False

    def get_count(self, status: str = "waiting") -> int:
        """
        Get count of signals in queue.

        Args:
            status: Filter by status

        Returns:
            Number of signals
        """
        try:
            row = self.db.fetch_one("""
                SELECT COUNT(*) as count
                FROM signal_queue
                WHERE status = ?
            """, (status,))

            return row['count'] if row else 0

        except Exception as e:
            logger.error(f"Failed to get queue count: {e}")
            return 0

    def get_stats(self) -> dict:
        """
        Get queue statistics.

        Returns:
            Stats dictionary
        """
        try:
            row = self.db.fetch_one("""
                SELECT
                    COUNT(*) as total,
                    AVG(score) as avg_score,
                    MAX(score) as max_score,
                    MIN(score) as min_score,
                    MAX(queued_at) as last_added,
                    MIN(queued_at) as oldest
                FROM signal_queue
                WHERE status = 'waiting'
            """)

            return dict(row) if row else {}

        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {}

    def exists(self, symbol: str) -> bool:
        """
        Check if symbol exists in queue.

        Args:
            symbol: Stock symbol

        Returns:
            True if exists
        """
        return self.get_by_symbol(symbol) is not None
