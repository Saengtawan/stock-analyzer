#!/usr/bin/env python3
"""
Position Manager - Single Source of Truth for Positions

This module provides unified position tracking for the entire trading system.
Both AutoTradingEngine and RapidPortfolioManager use the same PositionManager instance,
ensuring consistency and avoiding sync issues.

Design:
- Single Position dataclass with all fields needed by both Engine and Portfolio
- File-based persistence (rapid_portfolio.json)
- Atomic writes to prevent corruption
- Thread-safe operations

v6.7 - Initial version (R3 refactoring)
"""

import json
import os
import tempfile
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field
from threading import Lock
from loguru import logger


@dataclass
class Position:
    """
    Unified position representation

    Contains all fields needed by:
    - AutoTradingEngine (execution, order tracking)
    - RapidPortfolioManager (monitoring, analytics)
    """
    # Basic info
    symbol: str
    entry_date: str
    entry_price: float
    qty: int  # Also called 'shares' in some places
    cost_basis: float

    # Stop Loss / Take Profit
    initial_sl: float          # SL at entry (never changes)
    current_sl: float          # Current SL (can be trailed)
    take_profit: float         # TP price
    sl_pct: float              # SL percentage from entry
    tp_pct: float              # TP percentage from entry

    # Trailing stop state
    highest_price: float       # Peak price since entry
    trailing_active: bool = False  # Is trailing stop active?

    # ATR info (for per-position SL/TP calculation)
    atr_pct: float = 0.0       # ATR% at entry time

    # Engine-specific fields
    sl_order_id: Optional[str] = None      # Alpaca SL order ID
    entry_order_id: Optional[str] = None   # Alpaca entry order ID

    # Portfolio-specific fields
    initial_tp: float = 0.0    # TP at entry (for comparison)

    @property
    def shares(self) -> int:
        """Alias for qty (backward compatibility)"""
        return self.qty

    @property
    def initial_stop_loss(self) -> float:
        """Alias for initial_sl (backward compatibility)"""
        return self.initial_sl

    @property
    def current_stop_loss(self) -> float:
        """Alias for current_sl (backward compatibility)"""
        return self.current_sl

    @property
    def initial_take_profit(self) -> float:
        """Alias for initial_tp (backward compatibility)"""
        return self.initial_tp

    @property
    def position_value(self) -> float:
        """Position value at entry"""
        return self.qty * self.entry_price


class PositionManager:
    """
    Single source of truth for positions

    Used by both AutoTradingEngine and RapidPortfolioManager.
    Persists to rapid_portfolio.json for durability.

    Thread-safe: All operations use a lock to prevent race conditions.

    Usage:
        # Create shared instance
        pos_manager = PositionManager('rapid_portfolio.json')

        # Both components share the same instance
        engine = AutoTradingEngine(position_manager=pos_manager)
        portfolio = RapidPortfolioManager(position_manager=pos_manager)

        # Add position
        pos = Position(symbol='AAPL', entry_price=100, qty=10, ...)
        pos_manager.add(pos)

        # Both engine and portfolio see the same data immediately
        assert engine.get_position('AAPL') == portfolio.get_position('AAPL')
    """

    def __init__(self, portfolio_file: str = None):
        """
        Initialize Position Manager

        Args:
            portfolio_file: Path to portfolio JSON file (default: rapid_portfolio.json)
        """
        if portfolio_file is None:
            # v6.19: Default to active_positions.json (Auto Trading Engine state file)
            portfolio_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'data',
                'active_positions.json'
            )

        self.portfolio_file = os.path.abspath(portfolio_file)
        self.positions: Dict[str, Position] = {}
        self._lock = Lock()  # Thread safety

        # Load existing positions
        self.load()

        logger.info(f"PositionManager initialized: {self.portfolio_file}")
        logger.info(f"  Loaded {len(self.positions)} positions")

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def load(self) -> None:
        """Load positions from file"""
        with self._lock:
            if not os.path.exists(self.portfolio_file):
                logger.debug(f"Portfolio file not found: {self.portfolio_file}")
                return

            try:
                with open(self.portfolio_file, 'r') as f:
                    data = json.load(f)

                for symbol, pos_data in data.get('positions', {}).items():
                    # Handle backward compatibility - map old field names
                    if 'shares' in pos_data and 'qty' not in pos_data:
                        pos_data['qty'] = pos_data.pop('shares')

                    if 'initial_stop_loss' in pos_data and 'initial_sl' not in pos_data:
                        pos_data['initial_sl'] = pos_data.pop('initial_stop_loss')

                    if 'current_stop_loss' in pos_data and 'current_sl' not in pos_data:
                        pos_data['current_sl'] = pos_data.pop('current_stop_loss')

                    if 'initial_take_profit' in pos_data and 'initial_tp' not in pos_data:
                        pos_data['initial_tp'] = pos_data.pop('initial_take_profit', 0.0)

                    # Remove any old keys that don't map to Position fields
                    valid_keys = set(Position.__dataclass_fields__.keys())
                    filtered_data = {k: v for k, v in pos_data.items() if k in valid_keys}

                    self.positions[symbol] = Position(**filtered_data)

                logger.info(f"Loaded {len(self.positions)} positions from {self.portfolio_file}")

            except Exception as e:
                logger.error(f"Failed to load portfolio: {e}")

    def save(self) -> None:
        """
        Save positions to file (atomic write)

        Uses atomic write to prevent file corruption if process crashes mid-write.
        """
        with self._lock:
            try:
                data = {
                    'positions': {s: asdict(p) for s, p in self.positions.items()},
                    'last_updated': datetime.now().isoformat()
                }

                # Atomic write: write to temp file, then replace
                fd, tmp_path = tempfile.mkstemp(
                    dir=os.path.dirname(self.portfolio_file),
                    suffix='.tmp'
                )
                try:
                    with os.fdopen(fd, 'w') as f:
                        json.dump(data, f, indent=2, default=str)
                    os.replace(tmp_path, self.portfolio_file)
                except Exception:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise

                logger.debug(f"Saved {len(self.positions)} positions to {self.portfolio_file}")

            except Exception as e:
                logger.error(f"Failed to save portfolio: {e}")

    # =========================================================================
    # CRUD OPERATIONS
    # =========================================================================

    def add(self, position: Position) -> None:
        """
        Add new position

        Args:
            position: Position instance to add

        Raises:
            ValueError: If position already exists
        """
        with self._lock:
            if position.symbol in self.positions:
                raise ValueError(f"Position {position.symbol} already exists")

            self.positions[position.symbol] = position
            self.save()
            logger.info(f"Added position: {position.symbol}")

    def remove(self, symbol: str) -> Optional[Position]:
        """
        Remove position

        Args:
            symbol: Symbol to remove

        Returns:
            Removed Position or None if not found
        """
        with self._lock:
            pos = self.positions.pop(symbol, None)
            if pos:
                self.save()
                logger.info(f"Removed position: {symbol}")
            return pos

    def get(self, symbol: str) -> Optional[Position]:
        """
        Get position by symbol

        Args:
            symbol: Symbol to get

        Returns:
            Position or None if not found
        """
        return self.positions.get(symbol)

    def all(self) -> List[Position]:
        """
        Get all positions

        Returns:
            List of all Position instances
        """
        return list(self.positions.values())

    def symbols(self) -> List[str]:
        """
        Get all position symbols

        Returns:
            List of symbols
        """
        return list(self.positions.keys())

    def count(self) -> int:
        """
        Get number of positions

        Returns:
            Position count
        """
        return len(self.positions)

    def exists(self, symbol: str) -> bool:
        """
        Check if position exists

        Args:
            symbol: Symbol to check

        Returns:
            True if position exists
        """
        return symbol in self.positions

    # =========================================================================
    # UPDATE OPERATIONS
    # =========================================================================

    def update(self, symbol: str, **kwargs) -> bool:
        """
        Update position fields

        Args:
            symbol: Symbol to update
            **kwargs: Fields to update

        Returns:
            True if updated, False if position not found

        Example:
            manager.update('AAPL', current_sl=99.5, trailing_active=True)
        """
        with self._lock:
            if symbol not in self.positions:
                return False

            pos = self.positions[symbol]
            for key, value in kwargs.items():
                if hasattr(pos, key):
                    setattr(pos, key, value)

            self.save()
            logger.debug(f"Updated position {symbol}: {list(kwargs.keys())}")
            return True

    def update_stop_loss(self, symbol: str, new_sl: float) -> bool:
        """
        Update stop loss for position

        Args:
            symbol: Symbol to update
            new_sl: New stop loss price

        Returns:
            True if updated, False if position not found
        """
        return self.update(symbol, current_sl=new_sl)

    def update_trailing_stop(self, symbol: str, highest_price: float, trailing_active: bool = True) -> bool:
        """
        Update trailing stop state

        Args:
            symbol: Symbol to update
            highest_price: New highest price
            trailing_active: Whether trailing is active

        Returns:
            True if updated, False if position not found
        """
        return self.update(symbol, highest_price=highest_price, trailing_active=trailing_active)

    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================

    def clear(self) -> None:
        """Clear all positions (use with caution!)"""
        with self._lock:
            self.positions.clear()
            self.save()
            logger.warning("Cleared all positions")

    def get_positions_older_than(self, days: int) -> List[Position]:
        """
        Get positions older than N days

        Args:
            days: Days threshold

        Returns:
            List of positions older than threshold
        """
        from datetime import datetime, timedelta
        threshold = datetime.now() - timedelta(days=days)

        old_positions = []
        for pos in self.positions.values():
            entry_date = datetime.fromisoformat(pos.entry_date)
            if entry_date < threshold:
                old_positions.append(pos)

        return old_positions


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("PositionManager - Example Usage\n")

    # Create manager
    manager = PositionManager('/tmp/test_portfolio.json')

    # Example 1: Add position
    print("Example 1: Add position")
    pos = Position(
        symbol='AAPL',
        entry_date='2026-02-09',
        entry_price=100.0,
        qty=10,
        cost_basis=1000.0,
        initial_sl=98.0,
        current_sl=98.0,
        take_profit=104.0,
        sl_pct=2.0,
        tp_pct=4.0,
        highest_price=100.0,
        trailing_active=False,
        atr_pct=2.5
    )
    manager.add(pos)
    print(f"  Added: {pos.symbol} x{pos.qty} @ ${pos.entry_price}")

    # Example 2: Get position
    print("\nExample 2: Get position")
    retrieved = manager.get('AAPL')
    print(f"  {retrieved.symbol}: ${retrieved.entry_price} → SL ${retrieved.current_sl}, TP ${retrieved.take_profit}")

    # Example 3: Update position
    print("\nExample 3: Update trailing stop")
    manager.update_trailing_stop('AAPL', highest_price=102.0, trailing_active=True)
    updated = manager.get('AAPL')
    print(f"  Highest price: ${updated.highest_price}, Trailing: {updated.trailing_active}")

    # Example 4: List all
    print("\nExample 4: List all positions")
    for p in manager.all():
        print(f"  {p.symbol}: {p.qty} shares @ ${p.entry_price}")

    # Cleanup
    manager.remove('AAPL')
    print(f"\nRemoved position. Count: {manager.count()}")
