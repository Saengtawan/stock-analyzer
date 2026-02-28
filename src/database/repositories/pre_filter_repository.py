"""Pre-filter Repository - Database-Backed"""

from datetime import datetime, date
from typing import List, Optional

from ..models.pre_filter_session import PreFilterSession
from ..models.filtered_stock import FilteredStock
from ..manager import get_db_manager
from loguru import logger


class PreFilterRepository:
    """
    Repository for pre-filter data access.

    Database-backed storage using pre_filter_sessions and filtered_stocks tables.
    Provides unified API for pre-filter tracking.
    """

    def __init__(self, db_name: str = 'trade_history', _db=None):
        """
        Initialize pre-filter repository.

        Args:
            db_name: Database name (default: trade_history)
            _db: Optional DatabaseManager for testing (bypasses get_db_manager)
        """
        self.db = _db if _db is not None else get_db_manager(db_name)

    # =========================================================================
    # Pre-filter Sessions
    # =========================================================================

    def create_session(self, session: PreFilterSession) -> Optional[int]:
        """
        Create new pre-filter session.

        Args:
            session: PreFilterSession object

        Returns:
            Session ID if successful, None otherwise
        """
        try:
            session.validate()

            cursor = self.db.execute("""
                INSERT INTO pre_filter_sessions (
                    scan_type, scan_time, pool_size, total_scanned,
                    status, is_ready, duration_seconds, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.scan_type,
                session.scan_time or datetime.now(),
                session.pool_size,
                session.total_scanned,
                session.status,
                1 if session.is_ready else 0,
                session.duration_seconds,
                session.error_message
            ))

            return cursor.lastrowid

        except Exception as e:
            logger.error(f"Failed to create pre-filter session: {e}")
            return None

    def get_latest_session(self, scan_type: Optional[str] = None) -> Optional[PreFilterSession]:
        """
        Get most recent pre-filter session.

        Args:
            scan_type: Optional filter by scan type ('evening' or 'pre_open')

        Returns:
            PreFilterSession or None
        """
        try:
            if scan_type:
                row = self.db.fetch_one("""
                    SELECT * FROM pre_filter_sessions
                    WHERE scan_type = ?
                    ORDER BY scan_time DESC
                    LIMIT 1
                """, (scan_type,))
            else:
                row = self.db.fetch_one("""
                    SELECT * FROM pre_filter_sessions
                    ORDER BY scan_time DESC
                    LIMIT 1
                """)

            if row:
                return PreFilterSession.from_row(dict(row))
            return None

        except Exception as e:
            logger.error(f"Failed to get latest session: {e}")
            return None

    def get_session_by_id(self, session_id: int) -> Optional[PreFilterSession]:
        """Get session by ID."""
        try:
            row = self.db.fetch_one("""
                SELECT * FROM pre_filter_sessions WHERE id = ?
            """, (session_id,))

            if row:
                return PreFilterSession.from_row(dict(row))
            return None

        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None

    def update_session_status(self, session_id: int, status: str = None,
                             pool_size: Optional[int] = None,
                             total_scanned: Optional[int] = None,
                             duration: Optional[float] = None,
                             error_message: Optional[str] = None) -> bool:
        """
        Update session status.

        Args:
            session_id: Session ID
            status: Optional new status ('running', 'completed', 'failed')
            pool_size: Optional pool size
            total_scanned: Optional total stocks scanned
            duration: Optional duration in seconds
            error_message: Optional error message

        Returns:
            True if successful
        """
        try:
            params = []
            query_parts = []

            if status is not None:
                query_parts.append("status = ?")
                params.append(status)

            if pool_size is not None:
                query_parts.append("pool_size = ?")
                params.append(pool_size)

            if total_scanned is not None:
                query_parts.append("total_scanned = ?")
                params.append(total_scanned)

            if duration is not None:
                query_parts.append("duration_seconds = ?")
                params.append(duration)

            if error_message is not None:
                query_parts.append("error_message = ?")
                params.append(error_message)

            if status == 'completed':
                query_parts.append("is_ready = 1")

            # Nothing to update
            if not query_parts:
                return True

            params.append(session_id)

            self.db.execute(f"""
                UPDATE pre_filter_sessions
                SET {', '.join(query_parts)}
                WHERE id = ?
            """, tuple(params))

            return True

        except Exception as e:
            logger.error(f"Failed to update session status: {e}")
            return False

    # =========================================================================
    # Filtered Stocks
    # =========================================================================

    def add_stock(self, stock: FilteredStock) -> Optional[int]:
        """
        Add filtered stock to pool.

        Args:
            stock: FilteredStock object

        Returns:
            Stock ID if successful, None otherwise
        """
        try:
            stock.validate()

            cursor = self.db.execute("""
                INSERT INTO filtered_stocks (
                    session_id, symbol, sector, score,
                    close_price, volume_avg_20d, atr_pct, rsi,
                    filter_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                stock.session_id,
                stock.symbol,
                stock.sector,
                stock.score,
                stock.close_price,
                stock.volume_avg_20d,
                stock.atr_pct,
                stock.rsi,
                stock.filter_reason
            ))

            return cursor.lastrowid

        except Exception as e:
            logger.error(f"Failed to add filtered stock: {e}")
            return None

    def add_stocks_bulk(self, stocks: List[FilteredStock]) -> int:
        """
        Add multiple filtered stocks in bulk.

        Args:
            stocks: List of FilteredStock objects

        Returns:
            Number of stocks added
        """
        if not stocks:
            return 0

        try:
            params_list = []
            for stock in stocks:
                stock.validate()
                params_list.append((
                    stock.session_id,
                    stock.symbol,
                    stock.sector,
                    stock.score,
                    stock.close_price,
                    stock.volume_avg_20d,
                    stock.atr_pct,
                    stock.rsi,
                    stock.filter_reason
                ))

            self.db.execute_many("""
                INSERT INTO filtered_stocks (
                    session_id, symbol, sector, score,
                    close_price, volume_avg_20d, atr_pct, rsi,
                    filter_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, params_list)

            return len(stocks)

        except Exception as e:
            logger.error(f"Failed to bulk add stocks: {e}")
            return 0

    def get_filtered_pool(self, session_id: Optional[int] = None) -> List[FilteredStock]:
        """
        Get filtered stock pool.

        Args:
            session_id: Optional session ID (defaults to latest)

        Returns:
            List of FilteredStock objects
        """
        try:
            if session_id is None:
                # Get latest session
                latest = self.get_latest_session()
                if not latest:
                    return []
                session_id = latest.id

            rows = self.db.fetch_all("""
                SELECT * FROM filtered_stocks
                WHERE session_id = ?
                ORDER BY score DESC
            """, (session_id,))

            return [FilteredStock.from_row(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get filtered pool: {e}")
            return []

    def get_stock_symbols(self, session_id: Optional[int] = None) -> List[str]:
        """
        Get list of symbols in filtered pool.

        Args:
            session_id: Optional session ID (defaults to latest)

        Returns:
            List of symbols
        """
        try:
            if session_id is None:
                latest = self.get_latest_session()
                if not latest:
                    return []
                session_id = latest.id

            rows = self.db.fetch_all("""
                SELECT symbol FROM filtered_stocks
                WHERE session_id = ?
                ORDER BY symbol
            """, (session_id,))

            return [row['symbol'] for row in rows]

        except Exception as e:
            logger.error(f"Failed to get stock symbols: {e}")
            return []

    # =========================================================================
    # Analytics & Maintenance
    # =========================================================================

    def get_pool_size_history(self, days: int = 7) -> List[dict]:
        """
        Get pool size history.

        Args:
            days: Number of days to look back

        Returns:
            List of {scan_time, scan_type, pool_size}
        """
        try:
            rows = self.db.fetch_all("""
                SELECT scan_time, scan_type, pool_size
                FROM pre_filter_sessions
                WHERE scan_time >= datetime('now', ? || ' days')
                ORDER BY scan_time DESC
            """, (f'-{days}',))

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get pool size history: {e}")
            return []

    def cleanup_old_sessions(self, days: int = 30) -> int:
        """
        Delete old sessions (cascades to filtered_stocks).

        Args:
            days: Keep sessions from last N days

        Returns:
            Number of sessions deleted
        """
        try:
            cursor = self.db.execute("""
                DELETE FROM pre_filter_sessions
                WHERE scan_time < datetime('now', ? || ' days')
            """, (f'-{days}',))

            deleted = cursor.rowcount
            logger.info(f"Cleaned up {deleted} old pre-filter sessions (>{days} days)")
            return deleted

        except Exception as e:
            logger.error(f"Failed to cleanup old sessions: {e}")
            return 0
