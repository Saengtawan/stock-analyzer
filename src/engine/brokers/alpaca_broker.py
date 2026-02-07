"""
Alpaca Broker Implementation
=============================

Implements BrokerInterface for Alpaca Markets.
Wraps the existing alpaca_trader.py functionality.

Usage:
    from engine.brokers import AlpacaBroker

    broker = AlpacaBroker(api_key="...", secret_key="...", paper=True)
    account = broker.get_account()
"""

import os
import time
import functools
from datetime import datetime, timezone, timedelta
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
    OrderSide,
    OrderType,
    OrderStatus,
)

try:
    import alpaca_trade_api as tradeapi
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    logger.warning("alpaca-trade-api not installed")


def _retry_api(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 10.0):
    """Decorator for exponential backoff retry on API calls."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    err_str = str(e).lower()
                    status_code = getattr(e, 'status_code', None)

                    # Don't retry on client errors (4xx)
                    if status_code and 400 <= status_code < 500:
                        raise

                    # Don't retry on business logic errors
                    if any(kw in err_str for kw in ['insufficient', 'not found', 'forbidden', 'invalid']):
                        raise

                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(f"API retry {attempt + 1}/{max_retries}: {e} (wait {delay:.1f}s)")
                        time.sleep(delay)
                    else:
                        raise last_exc
        return wrapper
    return decorator


class AlpacaBroker(BrokerInterface):
    """
    Alpaca Markets broker implementation.

    Supports both paper and live trading.
    """

    # Constants
    PAPER_URL = "https://paper-api.alpaca.markets"
    LIVE_URL = "https://api.alpaca.markets"

    def __init__(
        self,
        api_key: str = None,
        secret_key: str = None,
        paper: bool = True,
    ):
        """
        Initialize Alpaca broker.

        Args:
            api_key: Alpaca API key (default: from env)
            secret_key: Alpaca secret key (default: from env)
            paper: Use paper trading (default: True)
        """
        if not ALPACA_AVAILABLE:
            raise ImportError("alpaca-trade-api package not installed")

        self._paper = paper
        self._api_key = api_key or os.getenv('ALPACA_API_KEY')
        self._secret_key = secret_key or os.getenv('ALPACA_SECRET_KEY')

        if not self._api_key or not self._secret_key:
            raise ValueError("Alpaca API key and secret key required")

        base_url = self.PAPER_URL if paper else self.LIVE_URL

        self.api = tradeapi.REST(
            key_id=self._api_key,
            secret_key=self._secret_key,
            base_url=base_url,
            api_version='v2'
        )

        logger.info(f"AlpacaBroker initialized ({'paper' if paper else 'LIVE'})")

    # =========================================================================
    # ACCOUNT
    # =========================================================================

    @_retry_api()
    def get_account(self) -> Account:
        """Get account information."""
        acct = self.api.get_account()

        return Account(
            equity=float(acct.equity),
            cash=float(acct.cash),
            buying_power=float(acct.buying_power),
            portfolio_value=float(acct.portfolio_value),
            currency=acct.currency,
            pattern_day_trader=acct.pattern_day_trader,
            day_trade_count=int(acct.daytrade_count),
            day_trades_remaining=max(0, 3 - int(acct.daytrade_count)),
            account_blocked=acct.account_blocked,
            trading_blocked=acct.trading_blocked,
            initial_margin=float(acct.initial_margin) if hasattr(acct, 'initial_margin') else 0,
            maintenance_margin=float(acct.maintenance_margin) if hasattr(acct, 'maintenance_margin') else 0,
        )

    # =========================================================================
    # POSITIONS
    # =========================================================================

    @_retry_api()
    def get_positions(self) -> List[Position]:
        """Get all open positions."""
        positions = self.api.list_positions()
        return [self._convert_position(p) for p in positions]

    @_retry_api()
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        try:
            pos = self.api.get_position(symbol)
            return self._convert_position(pos)
        except Exception as e:
            if 'position does not exist' in str(e).lower():
                return None
            raise

    def _convert_position(self, alpaca_pos) -> Position:
        """Convert Alpaca position to standard Position."""
        return Position(
            symbol=alpaca_pos.symbol,
            qty=float(alpaca_pos.qty),
            avg_entry_price=float(alpaca_pos.avg_entry_price),
            current_price=float(alpaca_pos.current_price),
            market_value=float(alpaca_pos.market_value),
            unrealized_pl=float(alpaca_pos.unrealized_pl),
            unrealized_plpc=float(alpaca_pos.unrealized_plpc),
            side="long" if float(alpaca_pos.qty) > 0 else "short",
            cost_basis=float(alpaca_pos.cost_basis),
        )

    # =========================================================================
    # ORDERS
    # =========================================================================

    @_retry_api()
    def get_orders(self, status: str = 'open') -> List[Order]:
        """Get orders with specified status."""
        orders = self.api.list_orders(status=status)
        return [self._convert_order(o) for o in orders]

    @_retry_api()
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get a specific order by ID."""
        try:
            order = self.api.get_order(order_id)
            return self._convert_order(order)
        except Exception as e:
            if 'not found' in str(e).lower():
                return None
            raise

    def _convert_order(self, alpaca_order) -> Order:
        """Convert Alpaca order to standard Order."""
        created_at = alpaca_order.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))

        return Order(
            id=alpaca_order.id,
            symbol=alpaca_order.symbol,
            side=alpaca_order.side,
            type=alpaca_order.type,
            qty=float(alpaca_order.qty),
            filled_qty=float(alpaca_order.filled_qty or 0),
            status=alpaca_order.status,
            created_at=created_at,
            filled_avg_price=float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else None,
            limit_price=float(alpaca_order.limit_price) if alpaca_order.limit_price else None,
            stop_price=float(alpaca_order.stop_price) if alpaca_order.stop_price else None,
            time_in_force=alpaca_order.time_in_force,
            extended_hours=getattr(alpaca_order, 'extended_hours', False),
        )

    @_retry_api()
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            self.api.cancel_order(order_id)
            return True
        except Exception as e:
            logger.warning(f"Failed to cancel order {order_id}: {e}")
            return False

    @_retry_api()
    def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        try:
            self.api.cancel_all_orders()
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False

    # =========================================================================
    # ORDER PLACEMENT
    # =========================================================================

    @_retry_api()
    def place_market_buy(self, symbol: str, qty: int) -> Order:
        """Place a market buy order."""
        order = self.api.submit_order(
            symbol=symbol,
            qty=qty,
            side='buy',
            type='market',
            time_in_force='day'
        )
        logger.info(f"Market BUY {qty} {symbol} → Order {order.id}")
        return self._convert_order(order)

    @_retry_api()
    def place_market_sell(self, symbol: str, qty: int) -> Order:
        """Place a market sell order."""
        order = self.api.submit_order(
            symbol=symbol,
            qty=qty,
            side='sell',
            type='market',
            time_in_force='day'
        )
        logger.info(f"Market SELL {qty} {symbol} → Order {order.id}")
        return self._convert_order(order)

    @_retry_api()
    def place_limit_buy(self, symbol: str, qty: int, limit_price: float) -> Order:
        """Place a limit buy order."""
        order = self.api.submit_order(
            symbol=symbol,
            qty=qty,
            side='buy',
            type='limit',
            limit_price=round(limit_price, 2),
            time_in_force='day'
        )
        logger.info(f"Limit BUY {qty} {symbol} @ ${limit_price:.2f} → Order {order.id}")
        return self._convert_order(order)

    @_retry_api()
    def place_limit_sell(self, symbol: str, qty: int, limit_price: float) -> Order:
        """Place a limit sell order."""
        order = self.api.submit_order(
            symbol=symbol,
            qty=qty,
            side='sell',
            type='limit',
            limit_price=round(limit_price, 2),
            time_in_force='day'
        )
        logger.info(f"Limit SELL {qty} {symbol} @ ${limit_price:.2f} → Order {order.id}")
        return self._convert_order(order)

    @_retry_api()
    def place_stop_loss(self, symbol: str, qty: int, stop_price: float) -> Order:
        """Place a stop loss order."""
        order = self.api.submit_order(
            symbol=symbol,
            qty=qty,
            side='sell',
            type='stop',
            stop_price=round(stop_price, 2),
            time_in_force='gtc'  # Good-til-canceled for stop loss
        )
        logger.info(f"Stop Loss {qty} {symbol} @ ${stop_price:.2f} → Order {order.id}")
        return self._convert_order(order)

    @_retry_api()
    def modify_stop_loss(self, order_id: str, new_stop_price: float) -> Order:
        """Modify an existing stop loss order."""
        # Alpaca requires cancel + replace
        old_order = self.get_order(order_id)
        if not old_order:
            raise ValueError(f"Order {order_id} not found")

        # Cancel old order
        self.cancel_order(order_id)
        time.sleep(0.5)  # Brief pause for order cancellation

        # Place new stop loss
        new_order = self.place_stop_loss(
            old_order.symbol,
            int(old_order.qty),
            new_stop_price
        )
        logger.info(f"Modified SL {old_order.symbol}: ${old_order.stop_price:.2f} → ${new_stop_price:.2f}")
        return new_order

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
        """Place a smart buy order with limit price slightly above ask."""
        quote = self.get_snapshot(symbol)
        if not quote or quote.ask <= 0:
            return self.place_market_buy(symbol, qty)

        limit_price = round(quote.ask * (1 + limit_offset_pct / 100), 2)
        order = self.place_limit_buy(symbol, qty, limit_price)

        if wait_for_fill:
            start = time.time()
            while time.time() - start < timeout_seconds:
                updated = self.get_order(order.id)
                if updated and updated.is_filled:
                    return updated
                time.sleep(0.5)

            # Timeout - cancel and use market order
            self.cancel_order(order.id)
            logger.warning(f"Limit order timeout for {symbol}, using market order")
            return self.place_market_buy(symbol, qty)

        return order

    def buy_with_stop_loss(
        self,
        symbol: str,
        qty: int,
        sl_pct: float = 2.5,
    ) -> Tuple[Order, Order]:
        """Buy shares and immediately place a stop loss order."""
        # Place buy order
        buy_order = self.place_market_buy(symbol, qty)

        # Wait for fill
        filled_price = None
        for _ in range(20):  # Wait up to 10 seconds
            updated = self.get_order(buy_order.id)
            if updated and updated.is_filled and updated.filled_avg_price:
                filled_price = updated.filled_avg_price
                buy_order = updated
                break
            time.sleep(0.5)

        if not filled_price:
            raise Exception(f"Buy order not filled: {buy_order.id}")

        # Calculate and place stop loss
        stop_price = round(filled_price * (1 - sl_pct / 100), 2)
        sl_order = self.place_stop_loss(symbol, qty, stop_price)

        return buy_order, sl_order

    # =========================================================================
    # MARKET DATA
    # =========================================================================

    @_retry_api()
    def get_clock(self) -> Clock:
        """Get market clock information."""
        clock = self.api.get_clock()
        return Clock(
            is_open=clock.is_open,
            next_open=clock.next_open,
            next_close=clock.next_close,
        )

    def is_market_open(self) -> bool:
        """Check if market is currently open."""
        return self.get_clock().is_open

    @_retry_api()
    def get_snapshot(self, symbol: str) -> Optional[Quote]:
        """Get current quote for a symbol."""
        try:
            snapshot = self.api.get_snapshot(symbol)
            if not snapshot:
                return None

            return Quote(
                symbol=symbol,
                bid=float(snapshot.latest_quote.bp) if snapshot.latest_quote else 0,
                ask=float(snapshot.latest_quote.ap) if snapshot.latest_quote else 0,
                last=float(snapshot.latest_trade.p) if snapshot.latest_trade else 0,
                volume=int(snapshot.daily_bar.v) if snapshot.daily_bar else 0,
                bid_size=int(snapshot.latest_quote.bs) if snapshot.latest_quote else 0,
                ask_size=int(snapshot.latest_quote.as_) if snapshot.latest_quote else 0,
                high=float(snapshot.daily_bar.h) if snapshot.daily_bar else 0,
                low=float(snapshot.daily_bar.l) if snapshot.daily_bar else 0,
                open=float(snapshot.daily_bar.o) if snapshot.daily_bar else 0,
                prev_close=float(snapshot.prev_daily_bar.c) if snapshot.prev_daily_bar else 0,
            )
        except Exception as e:
            logger.debug(f"Failed to get snapshot for {symbol}: {e}")
            return None

    @_retry_api()
    def get_snapshots(self, symbols: List[str]) -> Dict[str, Quote]:
        """Get quotes for multiple symbols."""
        result = {}
        try:
            snapshots = self.api.get_snapshots(symbols)
            for symbol, snapshot in snapshots.items():
                if snapshot:
                    result[symbol] = Quote(
                        symbol=symbol,
                        bid=float(snapshot.latest_quote.bp) if snapshot.latest_quote else 0,
                        ask=float(snapshot.latest_quote.ap) if snapshot.latest_quote else 0,
                        last=float(snapshot.latest_trade.p) if snapshot.latest_trade else 0,
                        volume=int(snapshot.daily_bar.v) if snapshot.daily_bar else 0,
                    )
        except Exception as e:
            logger.warning(f"Failed to get snapshots: {e}")

        return result

    @_retry_api()
    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: datetime = None,
        end: datetime = None,
        limit: int = 100,
    ) -> List[Bar]:
        """Get historical bars."""
        if end is None:
            end = datetime.now(timezone.utc)
        if start is None:
            start = end - timedelta(days=limit + 5)

        bars = self.api.get_bars(
            symbol,
            timeframe,
            start=start.strftime('%Y-%m-%d'),
            end=end.strftime('%Y-%m-%d'),
            limit=limit
        )

        result = []
        for bar in bars:
            result.append(Bar(
                timestamp=bar.t,
                open=float(bar.o),
                high=float(bar.h),
                low=float(bar.l),
                close=float(bar.c),
                volume=int(bar.v),
                vwap=float(bar.vw) if hasattr(bar, 'vw') else 0,
                trade_count=int(bar.n) if hasattr(bar, 'n') else 0,
            ))

        return result

    # =========================================================================
    # TRAILING STOP
    # =========================================================================

    def calculate_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        current_stop: float,
        trail_activation_pct: float = 2.0,
        trail_lock_pct: float = 70.0,
    ) -> Tuple[float, bool]:
        """Calculate trailing stop price."""
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
    def broker_name(self) -> str:
        return "Alpaca"

    @property
    def is_paper(self) -> bool:
        return self._paper
