"""Signal Repository - Database-Backed"""

from datetime import datetime
from typing import List, Optional

from ..models.trading_signal import TradingSignal
from ..manager import get_db_manager
from loguru import logger


class SignalRepository:
    """
    Repository for trading signal data access.

    Database-backed storage using trading_signals table.
    Provides unified API for signal management.
    """

    def __init__(self, db_name: str = 'trade_history'):
        """
        Initialize signal repository.

        Args:
            db_name: Database name (default: trade_history)
        """
        self.db = get_db_manager(db_name)
        self._cache = None
        self._cache_time = None

    def _load_from_database(self, where_clause: str = "", params: tuple = ()) -> List[TradingSignal]:
        """
        Load signals from database.

        Args:
            where_clause: Optional WHERE clause (without WHERE keyword)
            params: Query parameters

        Returns:
            List of TradingSignal objects
        """
        try:
            query = "SELECT * FROM trading_signals"
            if where_clause:
                query += f" WHERE {where_clause}"
            query += " ORDER BY signal_time DESC"

            rows = self.db.fetch_all(query, params)

            signals = []
            for row in rows:
                try:
                    row_dict = dict(row)
                    signal = TradingSignal.from_row(row_dict)
                    signals.append(signal)
                except Exception as e:
                    logger.warning(f"Failed to load signal {row.get('symbol', 'UNKNOWN')}: {e}")

            return signals

        except Exception as e:
            logger.error(f"Failed to load signals from database: {e}")
            return []

    def get_all(self, status: Optional[str] = None, limit: int = 1000) -> List[TradingSignal]:
        """
        Get all trading signals.

        Args:
            status: Filter by status (active, waiting, executed, expired)
            limit: Maximum number of signals to return

        Returns:
            List of TradingSignal objects
        """
        if status:
            where_clause = "status = ?"
            params = (status,)
        else:
            where_clause = ""
            params = ()

        query = "SELECT * FROM trading_signals"
        if where_clause:
            query += f" WHERE {where_clause}"
        query += f" ORDER BY signal_time DESC LIMIT {limit}"

        return self._load_from_database(where_clause, params) if where_clause else \
               [TradingSignal.from_row(dict(row)) for row in self.db.fetch_all(query)]

    def get_active(self) -> List[TradingSignal]:
        """
        Get all active signals.

        Returns:
            List of active TradingSignal objects
        """
        return self._load_from_database("status = ?", ("active",))

    def get_waiting(self) -> List[TradingSignal]:
        """
        Get all waiting signals.

        Returns:
            List of waiting TradingSignal objects
        """
        return self._load_from_database("status = ?", ("waiting",))

    def get_by_symbol(self, symbol: str, status: Optional[str] = None) -> List[TradingSignal]:
        """
        Get signals for specific symbol.

        Args:
            symbol: Stock symbol
            status: Optional status filter

        Returns:
            List of TradingSignal objects
        """
        if status:
            where_clause = "symbol = ? AND status = ?"
            params = (symbol, status)
        else:
            where_clause = "symbol = ?"
            params = (symbol,)

        return self._load_from_database(where_clause, params)

    def get_by_session(self, scan_session_id: int) -> List[TradingSignal]:
        """
        Get signals from specific scan session.

        Args:
            scan_session_id: Scan session ID

        Returns:
            List of TradingSignal objects
        """
        return self._load_from_database("scan_session_id = ?", (scan_session_id,))

    def get_by_regime(self, market_regime: str, days: int = 7) -> List[TradingSignal]:
        """
        Get signals by market regime within time period.

        Args:
            market_regime: Market regime (BULL, BEAR, NORMAL)
            days: Number of days to look back

        Returns:
            List of TradingSignal objects
        """
        return self._load_from_database(
            "market_regime = ? AND signal_time >= datetime('now', ? || ' days')",
            (market_regime, f'-{days}')
        )

    def create(self, signal: TradingSignal) -> Optional[int]:
        """
        Create new signal.

        Args:
            signal: TradingSignal object

        Returns:
            Signal ID if successful, None otherwise
        """
        try:
            signal.validate()

            # Import json for reasons serialization
            import json
            reasons_json = json.dumps(signal.reasons) if signal.reasons else None

            cursor = self.db.execute("""
                INSERT INTO trading_signals (
                    symbol, score, signal_price, signal_time,
                    stop_loss, take_profit, sl_pct, tp_pct, risk_reward, expected_gain, max_loss,
                    atr_pct, rsi, momentum_5d, momentum_20d, distance_from_high,
                    swing_low, resistance, volume_ratio, vwap,
                    sector, market_regime, sector_score, alt_data_score,
                    sl_method, tp_method,
                    status, wait_reason,
                    scan_session_id, session_type, scan_time_et,
                    executed_at, execution_result,
                    reasons, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.symbol, signal.score, signal.signal_price,
                signal.signal_time or datetime.now(),
                signal.stop_loss, signal.take_profit, signal.sl_pct, signal.tp_pct,
                signal.risk_reward, signal.expected_gain, signal.max_loss,
                signal.atr_pct, signal.rsi, signal.momentum_5d, signal.momentum_20d,
                signal.distance_from_high, signal.swing_low, signal.resistance,
                signal.volume_ratio, signal.vwap,
                signal.sector, signal.market_regime, signal.sector_score, signal.alt_data_score,
                signal.sl_method, signal.tp_method,
                signal.status, signal.wait_reason,
                signal.scan_session_id, signal.session_type, signal.scan_time_et,
                signal.executed_at, signal.execution_result,
                reasons_json, signal.metadata
            ))

            # Clear cache
            self._cache = None

            return cursor.lastrowid

        except Exception as e:
            logger.error(f"Failed to create signal {signal.symbol}: {e}")
            return None

    def create_batch(self, signals: List[TradingSignal], scan_session_id: Optional[int] = None) -> int:
        """
        Create multiple signals efficiently.

        Args:
            signals: List of TradingSignal objects
            scan_session_id: Optional scan session ID to assign to all signals

        Returns:
            Number of signals created
        """
        count = 0
        for signal in signals:
            if scan_session_id:
                signal.scan_session_id = scan_session_id

            if self.create(signal):
                count += 1

        return count

    def update_status(self, signal_id: int, status: str, execution_result: Optional[str] = None) -> bool:
        """
        Update signal status and execution result.

        Args:
            signal_id: Signal ID
            status: New status (active, waiting, executed, expired)
            execution_result: Execution result (BOUGHT, SKIPPED_FILTER, etc.)

        Returns:
            True if successful
        """
        try:
            executed_at = datetime.now() if status == 'executed' else None

            self.db.execute("""
                UPDATE trading_signals
                SET status = ?,
                    execution_result = ?,
                    executed_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, execution_result, executed_at, signal_id))

            # Clear cache
            self._cache = None

            return True

        except Exception as e:
            logger.error(f"Failed to update signal {signal_id}: {e}")
            return False

    def update_status_by_symbol(self, symbol: str, status: str, execution_result: Optional[str] = None) -> bool:
        """
        Update status for all active/waiting signals of a symbol.

        Args:
            symbol: Stock symbol
            status: New status
            execution_result: Execution result

        Returns:
            True if successful
        """
        try:
            executed_at = datetime.now() if status == 'executed' else None

            self.db.execute("""
                UPDATE trading_signals
                SET status = ?,
                    execution_result = ?,
                    executed_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE symbol = ?
                  AND status IN ('active', 'waiting')
            """, (status, execution_result, executed_at, symbol))

            # Clear cache
            self._cache = None

            return True

        except Exception as e:
            logger.error(f"Failed to update signals for {symbol}: {e}")
            return False

    def expire_old_signals(self, hours: int = 24) -> int:
        """
        Mark old active/waiting signals as expired.

        Args:
            hours: Age threshold in hours

        Returns:
            Number of signals expired
        """
        try:
            cursor = self.db.execute("""
                UPDATE trading_signals
                SET status = 'expired',
                    updated_at = CURRENT_TIMESTAMP
                WHERE status IN ('active', 'waiting')
                  AND signal_time < datetime('now', ? || ' hours')
            """, (f'-{hours}',))

            # Clear cache
            self._cache = None

            return cursor.rowcount

        except Exception as e:
            logger.error(f"Failed to expire old signals: {e}")
            return 0

    def get_stats(self, days: int = 7) -> dict:
        """
        Get signal statistics for time period.

        Args:
            days: Number of days to analyze

        Returns:
            Stats dictionary
        """
        try:
            row = self.db.fetch_one("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN status = 'waiting' THEN 1 ELSE 0 END) as waiting,
                    SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END) as executed,
                    SUM(CASE WHEN execution_result = 'BOUGHT' THEN 1 ELSE 0 END) as bought,
                    AVG(score) as avg_score
                FROM trading_signals
                WHERE signal_time >= datetime('now', ? || ' days')
            """, (f'-{days}',))

            return dict(row) if row else {}

        except Exception as e:
            logger.error(f"Failed to get signal stats: {e}")
            return {}

    def delete_old(self, days: int = 90) -> int:
        """
        Delete signals older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of signals deleted
        """
        try:
            cursor = self.db.execute("""
                DELETE FROM trading_signals
                WHERE signal_time < datetime('now', ? || ' days')
            """, (f'-{days}',))

            # Clear cache
            self._cache = None

            return cursor.rowcount

        except Exception as e:
            logger.error(f"Failed to delete old signals: {e}")
            return 0
