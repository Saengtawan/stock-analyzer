"""
Broker Interface - Abstract base class for all broker implementations
======================================================================

This module defines the standard interface that all broker implementations
must follow. This allows the trading engine to work with any broker
(Alpaca, Interactive Brokers, etc.) without code changes.

Usage:
    from engine.broker_interface import BrokerInterface, Position, Order

    class MyBroker(BrokerInterface):
        def get_account(self) -> Account:
            ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any


# =============================================================================
# ENUMS
# =============================================================================

class OrderSide(Enum):
    """Order side (buy or sell)"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(Enum):
    """Order status"""
    NEW = "new"
    PENDING = "pending"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


# =============================================================================
# DATA MODELS - Standard format for all brokers
# =============================================================================

@dataclass
class Position:
    """
    Standard position representation.

    All broker implementations must convert their position format to this.
    """
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float  # percentage as decimal (0.05 = 5%)

    # Optional fields
    side: str = "long"  # "long" or "short"
    qty_available: float = 0.0  # Available shares (not locked by orders)
    cost_basis: float = 0.0

    def __post_init__(self):
        if self.cost_basis == 0.0:
            self.cost_basis = self.qty * self.avg_entry_price


@dataclass
class Order:
    """
    Standard order representation.

    All broker implementations must convert their order format to this.
    """
    id: str
    symbol: str
    side: str  # "buy" or "sell"
    type: str  # "market", "limit", "stop", "stop_limit"
    qty: float
    filled_qty: float
    status: str
    created_at: datetime

    # Optional fields
    filled_avg_price: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "day"
    extended_hours: bool = False

    @property
    def is_filled(self) -> bool:
        return self.status.lower() == "filled"

    @property
    def is_open(self) -> bool:
        return self.status.lower() in ("new", "pending", "accepted", "partially_filled")

    @property
    def is_canceled(self) -> bool:
        return self.status.lower() in ("canceled", "cancelled")


@dataclass
class Account:
    """
    Standard account representation.

    All broker implementations must convert their account format to this.
    """
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float

    # Optional fields
    currency: str = "USD"
    pattern_day_trader: bool = False
    day_trade_count: int = 0
    day_trades_remaining: int = 3
    account_blocked: bool = False
    trading_blocked: bool = False

    # Last equity for daily P&L calculation
    last_equity: float = 0.0

    # Margin info (optional)
    initial_margin: float = 0.0
    maintenance_margin: float = 0.0
    last_maintenance_margin: float = 0.0

    @property
    def is_paper(self) -> bool:
        """Override in implementation if needed"""
        return False


@dataclass
class Quote:
    """
    Standard quote/snapshot representation.

    All broker implementations must convert their quote format to this.
    """
    symbol: str
    bid: float
    ask: float
    last: float
    volume: int
    timestamp: datetime = field(default_factory=datetime.now)

    # Optional fields
    bid_size: int = 0
    ask_size: int = 0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0
    prev_close: float = 0.0
    vwap: float = 0.0  # v6.20: Volume-weighted average price (daily)

    @property
    def mid(self) -> float:
        """Mid price between bid and ask"""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last

    @property
    def spread(self) -> float:
        """Bid-ask spread"""
        if self.bid > 0 and self.ask > 0:
            return self.ask - self.bid
        return 0.0

    @property
    def spread_pct(self) -> float:
        """Spread as percentage of mid price"""
        if self.mid > 0:
            return (self.spread / self.mid) * 100
        return 0.0


@dataclass
class Clock:
    """
    Standard market clock representation.
    """
    is_open: bool
    next_open: Optional[datetime]
    next_close: Optional[datetime]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Bar:
    """
    Standard OHLCV bar representation.
    """
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    # Optional
    vwap: float = 0.0
    trade_count: int = 0


# =============================================================================
# BROKER INTERFACE - Abstract Base Class
# =============================================================================

class BrokerInterface(ABC):
    """
    Abstract base class for all broker implementations.

    All broker implementations (Alpaca, IB, etc.) must implement these methods.
    The trading engine uses only this interface, never broker-specific code.

    Example implementation:
        class AlpacaBroker(BrokerInterface):
            def get_account(self) -> Account:
                alpaca_account = self.api.get_account()
                return Account(
                    equity=float(alpaca_account.equity),
                    cash=float(alpaca_account.cash),
                    ...
                )
    """

    # =========================================================================
    # ACCOUNT
    # =========================================================================

    @abstractmethod
    def get_account(self) -> Account:
        """
        Get account information.

        Returns:
            Account object with equity, cash, buying_power, etc.
        """
        pass

    # =========================================================================
    # POSITIONS
    # =========================================================================

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """
        Get all open positions.

        Returns:
            List of Position objects
        """
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a specific symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Position object or None if no position
        """
        pass

    # =========================================================================
    # ORDERS
    # =========================================================================

    @abstractmethod
    def get_orders(self, status: str = 'open') -> List[Order]:
        """
        Get orders with specified status.

        Args:
            status: 'open', 'closed', 'all'

        Returns:
            List of Order objects
        """
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get a specific order by ID.

        Args:
            order_id: Order ID

        Returns:
            Order object or None if not found
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if canceled successfully
        """
        pass

    @abstractmethod
    def cancel_all_orders(self) -> bool:
        """
        Cancel all open orders.

        Returns:
            True if all orders canceled
        """
        pass

    # =========================================================================
    # ORDER PLACEMENT
    # =========================================================================

    @abstractmethod
    def place_market_buy(self, symbol: str, qty: int) -> Order:
        """
        Place a market buy order.

        Args:
            symbol: Stock symbol
            qty: Number of shares

        Returns:
            Order object
        """
        pass

    @abstractmethod
    def place_market_sell(self, symbol: str, qty: int) -> Order:
        """
        Place a market sell order.

        Args:
            symbol: Stock symbol
            qty: Number of shares

        Returns:
            Order object
        """
        pass

    @abstractmethod
    def place_limit_buy(self, symbol: str, qty: int, limit_price: float) -> Order:
        """
        Place a limit buy order.

        Args:
            symbol: Stock symbol
            qty: Number of shares
            limit_price: Limit price

        Returns:
            Order object
        """
        pass

    @abstractmethod
    def place_limit_sell(self, symbol: str, qty: int, limit_price: float) -> Order:
        """
        Place a limit sell order.

        Args:
            symbol: Stock symbol
            qty: Number of shares
            limit_price: Limit price

        Returns:
            Order object
        """
        pass

    @abstractmethod
    def place_stop_loss(self, symbol: str, qty: int, stop_price: float) -> Order:
        """
        Place a stop loss order.

        Args:
            symbol: Stock symbol
            qty: Number of shares
            stop_price: Stop price

        Returns:
            Order object
        """
        pass

    @abstractmethod
    def modify_stop_loss(self, order_id: str, new_stop_price: float) -> Order:
        """
        Modify an existing stop loss order.

        Args:
            order_id: Order ID to modify
            new_stop_price: New stop price

        Returns:
            New Order object
        """
        pass

    # =========================================================================
    # COMPOSITE ORDERS
    # =========================================================================

    def place_smart_buy(
        self,
        symbol: str,
        qty: int,
        limit_offset_pct: float = 0.1,
        wait_for_fill: bool = True,
        timeout_seconds: int = 30,
    ) -> Order:
        """
        Place a smart buy order (limit order slightly above ask).

        Default implementation uses limit order. Override for broker-specific logic.

        Args:
            symbol: Stock symbol
            qty: Number of shares
            limit_offset_pct: Offset above ask price
            wait_for_fill: Wait for fill
            timeout_seconds: Timeout in seconds

        Returns:
            Order object
        """
        quote = self.get_snapshot(symbol)
        if quote:
            limit_price = quote.ask * (1 + limit_offset_pct / 100)
            return self.place_limit_buy(symbol, qty, round(limit_price, 2))
        else:
            return self.place_market_buy(symbol, qty)

    def buy_with_stop_loss(
        self,
        symbol: str,
        qty: int,
        sl_pct: float = 2.5,
    ) -> Tuple[Order, Order]:
        """
        Buy shares and immediately place a stop loss order.

        Default implementation places market buy then stop loss.
        Override for broker-specific bracket orders.

        Args:
            symbol: Stock symbol
            qty: Number of shares
            sl_pct: Stop loss percentage

        Returns:
            Tuple of (buy_order, stop_loss_order)
        """
        # Place buy order
        buy_order = self.place_market_buy(symbol, qty)

        # Wait for fill and get fill price
        filled_price = buy_order.filled_avg_price
        if not filled_price:
            # Fetch updated order
            updated = self.get_order(buy_order.id)
            if updated:
                filled_price = updated.filled_avg_price

        if not filled_price:
            raise Exception(f"Buy order not filled: {buy_order.id}")

        # Calculate stop price
        stop_price = round(filled_price * (1 - sl_pct / 100), 2)

        # Place stop loss
        sl_order = self.place_stop_loss(symbol, qty, stop_price)

        return buy_order, sl_order

    # =========================================================================
    # MARKET DATA
    # =========================================================================

    @abstractmethod
    def get_clock(self) -> Clock:
        """
        Get market clock information.

        Returns:
            Clock object with is_open, next_open, next_close
        """
        pass

    @abstractmethod
    def is_market_open(self) -> bool:
        """
        Check if market is currently open.

        Returns:
            True if market is open
        """
        pass

    @abstractmethod
    def get_snapshot(self, symbol: str) -> Optional[Quote]:
        """
        Get current quote/snapshot for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Quote object or None
        """
        pass

    @abstractmethod
    def get_snapshots(self, symbols: List[str]) -> Dict[str, Quote]:
        """
        Get quotes for multiple symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dict mapping symbol to Quote
        """
        pass

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: datetime = None,
        end: datetime = None,
        limit: int = 100,
    ) -> List[Bar]:
        """
        Get historical bars/candles.

        Args:
            symbol: Stock symbol
            timeframe: "1Min", "5Min", "15Min", "1Hour", "1Day"
            start: Start datetime
            end: End datetime
            limit: Maximum bars to return

        Returns:
            List of Bar objects
        """
        pass

    # =========================================================================
    # TRAILING STOP CALCULATION
    # =========================================================================

    def calculate_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        current_stop: float,
        trail_activation_pct: float = 2.0,
        trail_lock_pct: float = 70.0,
    ) -> Tuple[float, bool]:
        """
        Calculate trailing stop price.

        Default implementation uses simple percentage-based trailing.
        Override for broker-specific trailing stop logic.

        Args:
            entry_price: Original entry price
            current_price: Current market price
            current_stop: Current stop price
            trail_activation_pct: Gain % to activate trailing
            trail_lock_pct: % of gains to lock in

        Returns:
            Tuple of (new_stop_price, should_update)
        """
        gain_pct = ((current_price - entry_price) / entry_price) * 100

        if gain_pct < trail_activation_pct:
            return current_stop, False

        # Calculate new stop to lock in gains
        gain_amount = current_price - entry_price
        locked_gain = gain_amount * (trail_lock_pct / 100)
        new_stop = entry_price + locked_gain

        # Only raise stop, never lower
        if new_stop > current_stop:
            return round(new_stop, 2), True

        return current_stop, False

    # =========================================================================
    # UTILITY
    # =========================================================================

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Return broker name for logging"""
        pass

    @property
    def is_paper(self) -> bool:
        """Return True if paper trading"""
        return False
