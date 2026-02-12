"""Trade Repository"""

from datetime import datetime, date, timedelta
from typing import List, Optional

from ..manager import get_db_manager
from ..models.trade import Trade


class TradeRepository:
    """
    Repository for trade data access.
    
    Provides clean API for CRUD operations on trades.
    """
    
    def __init__(self):
        self.db = get_db_manager('trade_history')
    
    def get_by_id(self, trade_id: int) -> Optional[Trade]:
        """
        Get trade by ID.
        
        Args:
            trade_id: Trade ID
            
        Returns:
            Trade object or None
        """
        row = self.db.fetch_one(
            "SELECT * FROM trades WHERE id = ?",
            (trade_id,)
        )
        
        if row:
            return Trade.from_row(dict(row))
        return None
    
    def get_all(self, limit: int = 1000) -> List[Trade]:
        """
        Get all trades (limited).

        Args:
            limit: Maximum number of trades

        Returns:
            List of Trade objects
        """
        rows = self.db.fetch_all(
            "SELECT * FROM trades ORDER BY date DESC LIMIT ?",
            (limit,)
        )

        return [Trade.from_row(dict(row)) for row in rows]
    
    def get_open_trades(self) -> List[Trade]:
        """
        Get all open trades (BUY action without corresponding SELL).

        Returns:
            List of Trade objects
        """
        rows = self.db.fetch_all(
            "SELECT * FROM trades WHERE action = 'BUY' AND pnl_usd IS NULL ORDER BY date DESC"
        )

        return [Trade.from_row(dict(row)) for row in rows]
    
    def get_closed_trades(
        self,
        strategy: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 1000
    ) -> List[Trade]:
        """
        Get closed trades with filters.

        Args:
            strategy: Filter by strategy name
            start_date: Filter by date >= start_date
            end_date: Filter by date <= end_date
            limit: Maximum number of trades

        Returns:
            List of Trade objects
        """
        query = "SELECT * FROM trades WHERE action = 'SELL' AND pnl_usd IS NOT NULL"
        params = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)

        rows = self.db.fetch_all(query, tuple(params))

        return [Trade.from_row(dict(row)) for row in rows]
    
    def get_by_symbol(self, symbol: str, limit: int = 100) -> List[Trade]:
        """
        Get trades for a specific symbol.

        Args:
            symbol: Stock symbol
            limit: Maximum number of trades

        Returns:
            List of Trade objects
        """
        rows = self.db.fetch_all(
            "SELECT * FROM trades WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, limit)
        )

        return [Trade.from_row(dict(row)) for row in rows]

    def get_recent_trades(self, days: int = 30, limit: int = 500) -> List[Trade]:
        """
        Get recent trades within N days.

        Args:
            days: Number of days to look back
            limit: Maximum number of trades

        Returns:
            List of Trade objects
        """
        cutoff_date = (date.today() - timedelta(days=days)).isoformat()

        rows = self.db.fetch_all(
            "SELECT * FROM trades WHERE date >= ? ORDER BY date DESC LIMIT ?",
            (cutoff_date, limit)
        )

        return [Trade.from_row(dict(row)) for row in rows]
    
    def create(self, trade: Trade) -> int:
        """
        Create new trade.
        
        Args:
            trade: Trade object
            
        Returns:
            Trade ID
        """
        # Validate
        trade.validate()
        
        # Insert
        cursor = self.db.execute(
            """
            INSERT INTO trades (
                symbol, action, qty, price, timestamp,
                entry_date, entry_price, exit_date, exit_price,
                pnl, pnl_pct, strategy, signal_score,
                stop_loss, take_profit, spy_price, vix, regime, sector,
                rsi, atr_pct, gap_pct, momentum_5d,
                exit_reason, pdt_used, day_held, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.symbol, trade.action, trade.qty, trade.price,
                trade.timestamp.isoformat() if trade.timestamp else None,
                trade.entry_date.isoformat() if trade.entry_date else None,
                trade.entry_price,
                trade.exit_date.isoformat() if trade.exit_date else None,
                trade.exit_price,
                trade.pnl, trade.pnl_pct, trade.strategy, trade.signal_score,
                trade.stop_loss, trade.take_profit,
                trade.spy_price, trade.vix, trade.regime, trade.sector,
                trade.rsi, trade.atr_pct, trade.gap_pct, trade.momentum_5d,
                trade.exit_reason, trade.pdt_used, trade.day_held, trade.metadata
            )
        )
        
        return cursor.lastrowid
    
    def update(self, trade: Trade) -> bool:
        """
        Update existing trade.
        
        Args:
            trade: Trade object with ID
            
        Returns:
            True if successful
        """
        if not trade.id:
            raise ValueError("Trade ID is required for update")
        
        # Validate
        trade.validate()
        
        # Update
        self.db.execute(
            """
            UPDATE trades SET
                symbol = ?, action = ?, qty = ?, price = ?,
                exit_date = ?, exit_price = ?,
                pnl = ?, pnl_pct = ?,
                stop_loss = ?, take_profit = ?,
                exit_reason = ?, pdt_used = ?, day_held = ?,
                metadata = ?
            WHERE id = ?
            """,
            (
                trade.symbol, trade.action, trade.qty, trade.price,
                trade.exit_date.isoformat() if trade.exit_date else None,
                trade.exit_price,
                trade.pnl, trade.pnl_pct,
                trade.stop_loss, trade.take_profit,
                trade.exit_reason, trade.pdt_used, trade.day_held,
                trade.metadata,
                trade.id
            )
        )
        
        return True
    
    def delete(self, trade_id: int) -> bool:
        """
        Delete trade by ID.
        
        Args:
            trade_id: Trade ID
            
        Returns:
            True if successful
        """
        self.db.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        return True
    
    def get_statistics(
        self,
        strategy: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> dict:
        """
        Get trade statistics.

        Args:
            strategy: Filter by strategy
            start_date: Filter by date >= start_date
            end_date: Filter by date <= end_date

        Returns:
            Dictionary with statistics
        """
        query = """
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN pnl_usd < 0 THEN 1 ELSE 0 END) as losing_trades,
                AVG(pnl_usd) as avg_pnl,
                AVG(pnl_pct) as avg_pnl_pct,
                SUM(pnl_usd) as total_pnl,
                MAX(pnl_usd) as max_win,
                MIN(pnl_usd) as max_loss,
                AVG(day_held) as avg_hold_days
            FROM trades
            WHERE action = 'SELL' AND pnl_usd IS NOT NULL
        """
        params = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())

        row = self.db.fetch_one(query, tuple(params))

        if row:
            stats = dict(row)
            # Calculate win rate
            if stats['total_trades'] > 0:
                stats['win_rate'] = (stats['winning_trades'] / stats['total_trades']) * 100
            else:
                stats['win_rate'] = 0.0
            return stats

        return {}
