"""Position Repository - Database-Backed"""

from datetime import datetime, date
from typing import List, Optional

from ..models.position import Position
from ..manager import get_db_manager
from loguru import logger


class PositionRepository:
    """
    Repository for active position data access.

    Database-backed storage using active_positions table.
    Provides unified API for position management.
    """

    def __init__(self, db_name: str = 'trade_history'):
        """
        Initialize position repository.

        Args:
            db_name: Database name (default: trade_history)
        """
        self.db = get_db_manager(db_name)
        self._use_database = True  # Always use database (no JSON fallback)
        self._cache = None
        self._cache_time = None

    def _load_from_database(self) -> List[Position]:
        """
        Load positions from database (Phase 4).

        Returns:
            List of Position objects
        """
        try:
            rows = self.db.fetch_all("SELECT * FROM active_positions")

            positions = []
            for row in rows:
                try:
                    row_dict = dict(row)
                    position = Position.from_row(row_dict)
                    positions.append(position)
                except Exception as e:
                    logger.warning(f"Failed to load position {row['symbol']}: {e}")

            return positions

        except Exception as e:
            logger.error(f"Failed to load positions from database: {e}")
            return []


    def _save_to_database(self, positions: List[Position]) -> bool:
        """
        Save positions to database (Phase 4).

        Args:
            positions: List of Position objects

        Returns:
            True if successful
        """
        try:
            # Clear existing positions
            self.db.execute("DELETE FROM active_positions")

            # Insert new positions
            for position in positions:
                self.db.execute("""
                    INSERT INTO active_positions (
                        symbol, entry_date, entry_price, qty,
                        stop_loss, take_profit, peak_price, trough_price,
                        trailing_stop, day_held,
                        sl_pct, tp_pct, entry_atr_pct,
                        sl_order_id, tp_order_id, entry_order_id,
                        sector, source, signal_score,
                        mode, regime, entry_rsi, momentum_5d,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    position.symbol,
                    position.entry_date,
                    position.entry_price,
                    position.qty,
                    position.stop_loss,
                    position.take_profit,
                    position.peak_price,
                    position.trough_price,
                    1 if position.trailing_stop else 0,
                    position.day_held,
                    position.sl_pct,
                    position.tp_pct,
                    position.entry_atr_pct,
                    position.sl_order_id,
                    position.tp_order_id,
                    position.entry_order_id,
                    position.sector,
                    position.source,
                    position.signal_score,
                    position.mode,
                    position.regime,
                    position.entry_rsi,
                    position.momentum_5d,
                    datetime.now().isoformat()
                ))

            # Clear cache
            self._cache = None

            return True

        except Exception as e:
            logger.error(f"Failed to save positions to database: {e}")
            return False


    def get_all(self, use_cache: bool = True) -> List[Position]:
        """
        Get all active positions.

        Args:
            use_cache: Use cached positions if available

        Returns:
            List of Position objects
        """
        # Check cache (5 second TTL)
        if use_cache and self._cache is not None and self._cache_time:
            if (datetime.now() - self._cache_time).total_seconds() < 5:
                return self._cache

        # Load from database
        positions = self._load_from_database()

        # Update cache
        self._cache = positions
        self._cache_time = datetime.now()

        return positions
    
    def get_by_symbol(self, symbol: str) -> Optional[Position]:
        """
        Get position for specific symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Position object or None
        """
        try:
            row = self.db.fetch_one(
                "SELECT * FROM active_positions WHERE symbol = ?",
                (symbol,)
            )
            if row:
                return Position.from_row(dict(row))
            return None
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            return None
    
    def get_by_strategy(self, strategy: str) -> List[Position]:
        """
        Get positions for specific strategy.
        
        Args:
            strategy: Strategy name
            
        Returns:
            List of Position objects
        """
        positions = self.get_all()
        
        return [p for p in positions if p.strategy == strategy]
    
    def exists(self, symbol: str) -> bool:
        """
        Check if position exists for symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            True if position exists
        """
        return self.get_by_symbol(symbol) is not None
    
    def create(self, position: Position) -> bool:
        """
        Create new position.

        Args:
            position: Position object

        Returns:
            True if successful
        """
        # Validate
        position.validate()

        # Check if already exists
        if self.exists(position.symbol):
            raise ValueError(f"Position for {position.symbol} already exists")

        # Load current positions
        positions = self.get_all(use_cache=False)

        # Add new position
        positions.append(position)

        # Save to database
        return self._save_to_database(positions)
    
    def update(self, position: Position) -> bool:
        """
        Update existing position.

        Args:
            position: Position object

        Returns:
            True if successful
        """
        # Validate
        position.validate()

        # Load current positions
        positions = self.get_all(use_cache=False)

        # Find and update
        updated = False
        for i, pos in enumerate(positions):
            if pos.symbol == position.symbol:
                positions[i] = position
                updated = True
                break

        if not updated:
            raise ValueError(f"Position for {position.symbol} not found")

        # Save to database
        return self._save_to_database(positions)
    
    def delete(self, symbol: str) -> bool:
        """
        Delete position by symbol.

        Args:
            symbol: Stock symbol

        Returns:
            True if successful
        """
        # Load current positions
        positions = self.get_all(use_cache=False)

        # Filter out the position
        new_positions = [p for p in positions if p.symbol != symbol]

        if len(new_positions) == len(positions):
            raise ValueError(f"Position for {symbol} not found")

        # Save to database
        return self._save_to_database(new_positions)
    
    def count(self) -> int:
        """
        Get total number of positions.
        
        Returns:
            Position count
        """
        return len(self.get_all())
    
    def get_total_exposure(self) -> float:
        """
        Calculate total position exposure (sum of position values).
        
        Returns:
            Total exposure in USD
        """
        positions = self.get_all()
        return sum(p.entry_price * p.qty for p in positions)
    
    def get_symbols(self) -> List[str]:
        """
        Get list of all position symbols.
        
        Returns:
            List of symbols
        """
        positions = self.get_all()
        return [p.symbol for p in positions]
    
    def update_peak_price(self, symbol: str, current_price: float) -> bool:
        """
        Update peak price for trailing stop.
        
        Args:
            symbol: Stock symbol
            current_price: Current market price
            
        Returns:
            True if updated
        """
        position = self.get_by_symbol(symbol)
        
        if not position:
            return False
        
        # Update peak if higher
        if position.peak_price is None or current_price > position.peak_price:
            position.peak_price = current_price
            return self.update(position)
        
        return False
    
    def increment_days_held(self, symbol: Optional[str] = None) -> bool:
        """
        Increment days_held counter.
        
        Args:
            symbol: Specific symbol, or None for all positions
            
        Returns:
            True if successful
        """
        positions = self.get_all(use_cache=False)
        
        updated = False
        for position in positions:
            if symbol is None or position.symbol == symbol:
                position.day_held += 1
                updated = True
        
        if updated:
            return self._save_positions(positions)
        
        return False
    
    def get_positions_by_hold_time(self, min_days: int) -> List[Position]:
        """
        Get positions held for at least N days.
        
        Args:
            min_days: Minimum holding period
            
        Returns:
            List of Position objects
        """
        positions = self.get_all()
        return [p for p in positions if p.day_held >= min_days]
    
    def clear_all(self) -> bool:
        """
        Clear all positions (use with caution!).
        
        Returns:
            True if successful
        """
        logger.warning("Clearing all positions!")
        return self._save_positions([])
