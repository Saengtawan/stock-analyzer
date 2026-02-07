"""
Mock Broker Implementation
===========================

Implements BrokerInterface with fake data for testing.
No real API calls are made.

Usage:
    from engine.brokers import MockBroker

    broker = MockBroker(starting_cash=100000)
    account = broker.get_account()  # Returns mock data
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from loguru import logger

from engine.broker_interface import (
    BrokerInterface,
    Account,
    Position,
    Order,
    Quote,
    Clock,
    Bar,
)


class MockBroker(BrokerInterface):
    """
    Mock broker for testing.

    Simulates order fills, position tracking, and market data.
    """

    def __init__(
        self,
        starting_cash: float = 100000.0,
        is_market_open: bool = True,
    ):
        """
        Initialize mock broker.

        Args:
            starting_cash: Starting cash amount
            is_market_open: Whether market is open
        """
        self._cash = starting_cash
        self._positions: Dict[str, Position] = {}
        self._orders: Dict[str, Order] = {}
        self._market_open = is_market_open

        # Mock price data
        self._prices: Dict[str, float] = {
            'AAPL': 175.50,
            'GOOGL': 140.25,
            'MSFT': 375.00,
            'AMZN': 178.50,
            'NVDA': 875.00,
            'TSLA': 245.00,
            'META': 485.00,
            'SPY': 495.00,
        }

        logger.info(f"MockBroker initialized with ${starting_cash:,.0f}")

    # =========================================================================
    # ACCOUNT
    # =========================================================================

    def get_account(self) -> Account:
        """Get mock account information."""
        equity = self._cash + sum(p.market_value for p in self._positions.values())
        return Account(
            equity=equity,
            cash=self._cash,
            buying_power=self._cash * 2,  # Simulate 2x margin
            portfolio_value=equity,
            currency="USD",
            pattern_day_trader=False,
            day_trade_count=0,
            day_trades_remaining=3,
            account_blocked=False,
            trading_blocked=False,
        )

    # =========================================================================
    # POSITIONS
    # =========================================================================

    def get_positions(self) -> List[Position]:
        """Get all mock positions."""
        return list(self._positions.values())

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get mock position for a symbol."""
        return self._positions.get(symbol)

    def _update_position_price(self, symbol: str):
        """Update position with current price."""
        if symbol in self._positions:
            pos = self._positions[symbol]
            current_price = self._get_price(symbol)
            market_value = pos.qty * current_price
            unrealized_pl = market_value - pos.cost_basis
            unrealized_plpc = unrealized_pl / pos.cost_basis if pos.cost_basis > 0 else 0

            self._positions[symbol] = Position(
                symbol=pos.symbol,
                qty=pos.qty,
                avg_entry_price=pos.avg_entry_price,
                current_price=current_price,
                market_value=market_value,
                unrealized_pl=unrealized_pl,
                unrealized_plpc=unrealized_plpc,
                side=pos.side,
                cost_basis=pos.cost_basis,
            )

    # =========================================================================
    # ORDERS
    # =========================================================================

    def get_orders(self, status: str = 'open') -> List[Order]:
        """Get mock orders with specified status."""
        if status == 'all':
            return list(self._orders.values())
        return [o for o in self._orders.values() if self._matches_status(o, status)]

    def _matches_status(self, order: Order, status: str) -> bool:
        if status == 'open':
            return order.is_open
        elif status == 'closed':
            return not order.is_open
        return True

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get a specific mock order."""
        return self._orders.get(order_id)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a mock order."""
        if order_id in self._orders:
            order = self._orders[order_id]
            self._orders[order_id] = Order(
                id=order.id,
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                qty=order.qty,
                filled_qty=order.filled_qty,
                status="canceled",
                created_at=order.created_at,
                filled_avg_price=order.filled_avg_price,
                limit_price=order.limit_price,
                stop_price=order.stop_price,
            )
            return True
        return False

    def cancel_all_orders(self) -> bool:
        """Cancel all mock orders."""
        for order_id in list(self._orders.keys()):
            self.cancel_order(order_id)
        return True

    # =========================================================================
    # ORDER PLACEMENT
    # =========================================================================

    def _create_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str,
        limit_price: float = None,
        stop_price: float = None,
    ) -> Order:
        """Create a mock order."""
        order_id = str(uuid.uuid4())[:8]
        price = self._get_price(symbol)

        # Simulate instant fill for market orders
        if order_type == "market":
            filled_price = price
            filled_qty = qty
            status = "filled"

            # Update positions and cash
            if side == "buy":
                self._add_position(symbol, qty, filled_price)
                self._cash -= qty * filled_price
            else:
                self._remove_position(symbol, qty)
                self._cash += qty * filled_price
        else:
            filled_price = None
            filled_qty = 0
            status = "new"

        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            type=order_type,
            qty=qty,
            filled_qty=filled_qty,
            status=status,
            created_at=datetime.now(),
            filled_avg_price=filled_price,
            limit_price=limit_price,
            stop_price=stop_price,
        )

        self._orders[order_id] = order
        return order

    def _add_position(self, symbol: str, qty: int, price: float):
        """Add to position."""
        if symbol in self._positions:
            pos = self._positions[symbol]
            total_qty = pos.qty + qty
            total_cost = pos.cost_basis + (qty * price)
            avg_price = total_cost / total_qty

            self._positions[symbol] = Position(
                symbol=symbol,
                qty=total_qty,
                avg_entry_price=avg_price,
                current_price=price,
                market_value=total_qty * price,
                unrealized_pl=0,
                unrealized_plpc=0,
                cost_basis=total_cost,
            )
        else:
            self._positions[symbol] = Position(
                symbol=symbol,
                qty=qty,
                avg_entry_price=price,
                current_price=price,
                market_value=qty * price,
                unrealized_pl=0,
                unrealized_plpc=0,
                cost_basis=qty * price,
            )

    def _remove_position(self, symbol: str, qty: int):
        """Remove from position."""
        if symbol in self._positions:
            pos = self._positions[symbol]
            new_qty = pos.qty - qty
            if new_qty <= 0:
                del self._positions[symbol]
            else:
                self._positions[symbol] = Position(
                    symbol=symbol,
                    qty=new_qty,
                    avg_entry_price=pos.avg_entry_price,
                    current_price=pos.current_price,
                    market_value=new_qty * pos.current_price,
                    unrealized_pl=0,
                    unrealized_plpc=0,
                    cost_basis=new_qty * pos.avg_entry_price,
                )

    def place_market_buy(self, symbol: str, qty: int) -> Order:
        """Place a mock market buy order."""
        return self._create_order(symbol, qty, "buy", "market")

    def place_market_sell(self, symbol: str, qty: int) -> Order:
        """Place a mock market sell order."""
        return self._create_order(symbol, qty, "sell", "market")

    def place_limit_buy(self, symbol: str, qty: int, limit_price: float) -> Order:
        """Place a mock limit buy order."""
        return self._create_order(symbol, qty, "buy", "limit", limit_price=limit_price)

    def place_limit_sell(self, symbol: str, qty: int, limit_price: float) -> Order:
        """Place a mock limit sell order."""
        return self._create_order(symbol, qty, "sell", "limit", limit_price=limit_price)

    def place_stop_loss(self, symbol: str, qty: int, stop_price: float) -> Order:
        """Place a mock stop loss order."""
        return self._create_order(symbol, qty, "sell", "stop", stop_price=stop_price)

    def modify_stop_loss(self, order_id: str, new_stop_price: float) -> Order:
        """Modify a mock stop loss order."""
        old_order = self._orders.get(order_id)
        if not old_order:
            raise ValueError(f"Order {order_id} not found")

        # Cancel old and create new
        self.cancel_order(order_id)
        return self.place_stop_loss(old_order.symbol, int(old_order.qty), new_stop_price)

    # =========================================================================
    # MARKET DATA
    # =========================================================================

    def _get_price(self, symbol: str) -> float:
        """Get mock price for a symbol."""
        return self._prices.get(symbol, 100.0)

    def set_price(self, symbol: str, price: float):
        """Set mock price for testing."""
        self._prices[symbol] = price
        self._update_position_price(symbol)

    def get_clock(self) -> Clock:
        """Get mock market clock."""
        now = datetime.now()
        return Clock(
            is_open=self._market_open,
            next_open=now.replace(hour=9, minute=30) + timedelta(days=1),
            next_close=now.replace(hour=16, minute=0),
        )

    def is_market_open(self) -> bool:
        """Check if mock market is open."""
        return self._market_open

    def set_market_open(self, is_open: bool):
        """Set mock market open status."""
        self._market_open = is_open

    def get_snapshot(self, symbol: str) -> Optional[Quote]:
        """Get mock quote for a symbol."""
        price = self._get_price(symbol)
        spread = price * 0.001  # 0.1% spread

        return Quote(
            symbol=symbol,
            bid=round(price - spread / 2, 2),
            ask=round(price + spread / 2, 2),
            last=price,
            volume=1000000,
            bid_size=100,
            ask_size=100,
            high=round(price * 1.02, 2),
            low=round(price * 0.98, 2),
            open=round(price * 0.995, 2),
            prev_close=round(price * 0.99, 2),
        )

    def get_snapshots(self, symbols: List[str]) -> Dict[str, Quote]:
        """Get mock quotes for multiple symbols."""
        return {s: self.get_snapshot(s) for s in symbols if self.get_snapshot(s)}

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: datetime = None,
        end: datetime = None,
        limit: int = 100,
    ) -> List[Bar]:
        """Get mock historical bars."""
        price = self._get_price(symbol)
        bars = []

        for i in range(limit):
            day = datetime.now() - timedelta(days=limit - i)
            # Simulate random daily movement
            daily_change = (hash(f"{symbol}{i}") % 1000 - 500) / 10000
            close = price * (1 + daily_change)

            bars.append(Bar(
                timestamp=day,
                open=round(close * 0.999, 2),
                high=round(close * 1.02, 2),
                low=round(close * 0.98, 2),
                close=round(close, 2),
                volume=1000000 + (hash(f"{symbol}{i}") % 500000),
            ))

        return bars

    # =========================================================================
    # UTILITY
    # =========================================================================

    @property
    def broker_name(self) -> str:
        return "Mock"

    @property
    def is_paper(self) -> bool:
        return True
