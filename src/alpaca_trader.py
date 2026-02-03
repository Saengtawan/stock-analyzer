#!/usr/bin/env python3
"""
ALPACA TRADER MODULE - Phase 1
Rapid Trader v3.9 Auto-Trading Integration

Handles all Alpaca API interactions:
- Account info
- Position management
- Order placement (buy, sell, stop loss)
- Stop loss modification (for trailing)

CRITICAL RULE: Every position MUST have a stop loss order at Alpaca.
If SL order fails after buy, immediately sell the position.
"""

import os
import time
import functools
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import alpaca_trade_api as tradeapi
from loguru import logger


def _retry_api(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 10.0):
    """
    Decorator: exponential backoff retry for Alpaca API calls.
    Retries on connection errors, rate limits, and 5xx server errors.
    Does NOT retry on 4xx client errors (bad request, insufficient funds, etc.).
    """
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

                    # Don't retry on client errors (4xx) — they won't succeed
                    if status_code and 400 <= status_code < 500:
                        raise

                    # Don't retry if it's clearly a business logic error
                    if any(kw in err_str for kw in ['insufficient', 'not found', 'forbidden', 'invalid']):
                        raise

                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(f"API retry {attempt + 1}/{max_retries} for {func.__name__}: {e} (wait {delay:.1f}s)")
                        time.sleep(delay)
                    else:
                        logger.error(f"API failed after {max_retries} retries: {func.__name__}: {e}")
                        raise last_exc
        return wrapper
    return decorator


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


@dataclass
class Position:
    """Represents an open position"""
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float  # percentage


@dataclass
class Order:
    """Represents an order"""
    id: str
    symbol: str
    side: str
    type: str
    qty: float
    filled_qty: float
    status: str
    filled_avg_price: Optional[float]
    stop_price: Optional[float]
    created_at: datetime


class AlpacaTrader:
    """
    Alpaca Trading Client for Rapid Trader v3.9

    Paper Trading endpoint: https://paper-api.alpaca.markets
    Live Trading endpoint: https://api.alpaca.markets
    """

    # v3.9 Exit Strategy Parameters
    STOP_LOSS_PCT = 2.5      # -2.5% initial stop loss
    TRAIL_ACTIVATION_PCT = 2.0  # Start trailing at +2%
    TRAIL_LOCK_PCT = 70      # Lock 70% of gains

    def __init__(
        self,
        api_key: str = None,
        secret_key: str = None,
        base_url: str = None,
        paper: bool = True
    ):
        """
        Initialize Alpaca client

        Args:
            api_key: Alpaca API key (or set ALPACA_API_KEY env var)
            secret_key: Alpaca secret key (or set ALPACA_SECRET_KEY env var)
            base_url: API endpoint (defaults to paper trading)
            paper: If True, use paper trading endpoint
        """
        self.api_key = api_key or os.environ.get('ALPACA_API_KEY')
        self.secret_key = secret_key or os.environ.get('ALPACA_SECRET_KEY')

        if paper:
            self.base_url = base_url or 'https://paper-api.alpaca.markets'
        else:
            self.base_url = base_url or 'https://api.alpaca.markets'

        if not self.api_key or not self.secret_key:
            raise ValueError("API key and secret key are required")

        self.api = tradeapi.REST(
            self.api_key,
            self.secret_key,
            self.base_url,
            api_version='v2'
        )

        logger.info(f"Alpaca client initialized: {self.base_url}")

    # =========================================================================
    # ACCOUNT & POSITIONS
    # =========================================================================

    @_retry_api(max_retries=3, base_delay=1.0)
    def get_account(self) -> Dict:
        """Get account information"""
        try:
            account = self.api.get_account()
            return {
                'id': account.id,
                'status': account.status,
                'currency': account.currency,
                'cash': float(account.cash),
                'portfolio_value': float(account.portfolio_value),
                'buying_power': float(account.buying_power),
                'equity': float(account.equity),
                'last_equity': float(account.last_equity),
                'daytrade_count': account.daytrade_count,
                'pattern_day_trader': account.pattern_day_trader,
            }
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            raise

    @_retry_api(max_retries=3, base_delay=1.0)
    def get_positions(self) -> List[Position]:
        """Get all open positions"""
        try:
            positions = self.api.list_positions()
            return [
                Position(
                    symbol=p.symbol,
                    qty=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    market_value=float(p.market_value),
                    unrealized_pl=float(p.unrealized_pl),
                    unrealized_plpc=float(p.unrealized_plpc) * 100,  # Convert to %
                )
                for p in positions
            ]
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol"""
        try:
            p = self.api.get_position(symbol)
            return Position(
                symbol=p.symbol,
                qty=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                market_value=float(p.market_value),
                unrealized_pl=float(p.unrealized_pl),
                unrealized_plpc=float(p.unrealized_plpc) * 100,
            )
        except tradeapi.rest.APIError as e:
            if 'position does not exist' in str(e).lower():
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to get position {symbol}: {e}")
            raise

    # =========================================================================
    # ORDERS
    # =========================================================================

    def get_orders(self, status: str = 'open') -> List[Order]:
        """
        Get orders

        Args:
            status: 'open', 'closed', 'all'
        """
        try:
            orders = self.api.list_orders(status=status)
            return [
                Order(
                    id=o.id,
                    symbol=o.symbol,
                    side=o.side,
                    type=o.type,
                    qty=float(o.qty),
                    filled_qty=float(o.filled_qty) if o.filled_qty else 0,
                    status=o.status,
                    filled_avg_price=float(o.filled_avg_price) if o.filled_avg_price else None,
                    stop_price=float(o.stop_price) if o.stop_price else None,
                    created_at=o.created_at,
                )
                for o in orders
            ]
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            raise

    @_retry_api(max_retries=3, base_delay=0.5)
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get a specific order by ID"""
        try:
            o = self.api.get_order(order_id)
            return Order(
                id=o.id,
                symbol=o.symbol,
                side=o.side,
                type=o.type,
                qty=float(o.qty),
                filled_qty=float(o.filled_qty) if o.filled_qty else 0,
                status=o.status,
                filled_avg_price=float(o.filled_avg_price) if o.filled_avg_price else None,
                stop_price=float(o.stop_price) if o.stop_price else None,
                created_at=o.created_at,
            )
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            raise

    @_retry_api(max_retries=2, base_delay=1.0)
    def place_market_buy(self, symbol: str, qty: int) -> Order:
        """
        Place a market buy order

        Args:
            symbol: Stock symbol
            qty: Number of shares

        Returns:
            Order object
        """
        try:
            logger.info(f"Placing market buy: {symbol} x{qty}")
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side='buy',
                type='market',
                time_in_force='day'
            )
            logger.info(f"Buy order placed: {order.id}")
            return Order(
                id=order.id,
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                qty=float(order.qty),
                filled_qty=float(order.filled_qty) if order.filled_qty else 0,
                status=order.status,
                filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
                stop_price=None,
                created_at=order.created_at,
            )
        except Exception as e:
            logger.error(f"Failed to place buy order: {e}")
            raise

    def place_smart_buy(
        self,
        symbol: str,
        qty: int,
        max_spread_pct: float = 0.5,
        wait_seconds: int = 30
    ) -> Optional[Order]:
        """
        Strategy 4: Smart Limit Buy + Market Fallback

        Flow:
        1. Get bid/ask from snapshot
        2. Check spread (> max_spread_pct → skip)
        3. Place limit order @ ask price
        4. Wait up to wait_seconds for fill
        5. Not filled → cancel + market order (fallback)

        Returns:
            Order if filled, None if spread too wide (caller should skip)

        Side effect:
            Sets self.last_execution_meta dict with execution details
        """
        import time

        # Initialize execution metadata
        self.last_execution_meta = {
            'order_type': 'market',
            'limit_price': None,
            'bid_ask_spread_pct': None,
            'fill_time_sec': None,
            'fill_status': None,
        }
        start_time = time.time()

        # Step 1: Get bid/ask
        snapshot = self.get_snapshot(symbol)
        if not snapshot or not snapshot.get('bid') or not snapshot.get('ask'):
            logger.warning(f"Smart buy: No bid/ask for {symbol}, falling back to market")
            result = self.place_market_buy(symbol, qty)
            self.last_execution_meta['fill_time_sec'] = round(time.time() - start_time, 1)
            self.last_execution_meta['fill_status'] = 'filled' if result else 'failed'
            return result

        bid = snapshot['bid']
        ask = snapshot['ask']

        if bid <= 0 or ask <= 0:
            logger.warning(f"Smart buy: Invalid bid/ask for {symbol}, falling back to market")
            result = self.place_market_buy(symbol, qty)
            self.last_execution_meta['fill_time_sec'] = round(time.time() - start_time, 1)
            self.last_execution_meta['fill_status'] = 'filled' if result else 'failed'
            return result

        spread_pct = ((ask - bid) / bid) * 100
        self.last_execution_meta['bid_ask_spread_pct'] = round(spread_pct, 3)

        logger.info(f"Smart buy: {symbol} Bid=${bid:.2f} Ask=${ask:.2f} Spread={spread_pct:.2f}%")

        # Step 2: Spread check
        if spread_pct > max_spread_pct:
            logger.warning(f"Smart buy: {symbol} spread {spread_pct:.2f}% > {max_spread_pct}% - SKIP")
            self.last_execution_meta['fill_status'] = 'spread_reject'
            return None

        # Step 3: Place limit @ ask
        try:
            limit_price = round(ask, 2)
            self.last_execution_meta['order_type'] = 'limit'
            self.last_execution_meta['limit_price'] = limit_price
            logger.info(f"Smart buy: Limit order {symbol} x{qty} @ ${limit_price:.2f}")
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side='buy',
                type='limit',
                limit_price=limit_price,
                time_in_force='day'
            )
            order_id = order.id
            logger.info(f"Smart buy: Limit order placed: {order_id}")

            # Step 4: Wait for fill
            for i in range(wait_seconds):
                time.sleep(1)
                check = self.get_order(order_id)
                if check.status == 'filled':
                    saved = limit_price - check.filled_avg_price if check.filled_avg_price else 0
                    logger.info(
                        f"Smart buy: LIMIT FILLED {symbol} @ ${check.filled_avg_price:.2f} "
                        f"(limit was ${limit_price:.2f}, saved ${saved:.2f})"
                    )
                    self.last_execution_meta['fill_time_sec'] = round(time.time() - start_time, 1)
                    self.last_execution_meta['fill_status'] = 'filled'
                    return check
                if check.status in ('cancelled', 'expired', 'rejected'):
                    logger.warning(f"Smart buy: Order {check.status} for {symbol}")
                    break

            # Step 5: Not filled → cancel + market fallback
            check = self.get_order(order_id)
            if check.status == 'filled':
                self.last_execution_meta['fill_time_sec'] = round(time.time() - start_time, 1)
                self.last_execution_meta['fill_status'] = 'filled'
                return check

            logger.info(f"Smart buy: Limit not filled in {wait_seconds}s, falling back to MARKET")
            self.cancel_order(order_id)
            time.sleep(0.5)  # Wait for cancel to process

            # Verify cancel went through before market order
            check = self.get_order(order_id)
            if check.status == 'filled':
                logger.info(f"Smart buy: Filled during cancel! {symbol} @ ${check.filled_avg_price:.2f}")
                self.last_execution_meta['fill_time_sec'] = round(time.time() - start_time, 1)
                self.last_execution_meta['fill_status'] = 'filled'
                return check

            self.last_execution_meta['order_type'] = 'market_fallback'
            result = self.place_market_buy(symbol, qty)
            self.last_execution_meta['fill_time_sec'] = round(time.time() - start_time, 1)
            self.last_execution_meta['fill_status'] = 'filled' if result else 'failed'
            return result

        except Exception as e:
            logger.error(f"Smart buy limit failed: {e}, falling back to market")
            self.last_execution_meta['order_type'] = 'market_fallback'
            result = self.place_market_buy(symbol, qty)
            self.last_execution_meta['fill_time_sec'] = round(time.time() - start_time, 1)
            self.last_execution_meta['fill_status'] = 'filled' if result else 'failed'
            return result

    @_retry_api(max_retries=2, base_delay=1.0)
    def place_market_sell(self, symbol: str, qty: int) -> Order:
        """Place a market sell order"""
        try:
            logger.info(f"Placing market sell: {symbol} x{qty}")
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side='sell',
                type='market',
                time_in_force='day'
            )
            logger.info(f"Sell order placed: {order.id}")
            return Order(
                id=order.id,
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                qty=float(order.qty),
                filled_qty=float(order.filled_qty) if order.filled_qty else 0,
                status=order.status,
                filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
                stop_price=None,
                created_at=order.created_at,
            )
        except Exception as e:
            logger.error(f"Failed to place sell order: {e}")
            raise

    def place_stop_loss(self, symbol: str, qty: int, stop_price: float) -> Order:
        """
        Place a stop loss order

        Args:
            symbol: Stock symbol
            qty: Number of shares
            stop_price: Price at which to trigger the stop

        Returns:
            Order object
        """
        try:
            logger.info(f"Placing stop loss: {symbol} x{qty} @ ${stop_price:.2f}")
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side='sell',
                type='stop',
                stop_price=round(stop_price, 2),
                time_in_force='gtc'  # Good til cancelled
            )
            logger.info(f"Stop loss order placed: {order.id}")
            return Order(
                id=order.id,
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                qty=float(order.qty),
                filled_qty=float(order.filled_qty) if order.filled_qty else 0,
                status=order.status,
                filled_avg_price=None,
                stop_price=float(order.stop_price) if order.stop_price else stop_price,
                created_at=order.created_at,
            )
        except Exception as e:
            logger.error(f"Failed to place stop loss: {e}")
            raise

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        try:
            logger.info(f"Cancelling order: {order_id}")
            self.api.cancel_order(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders"""
        try:
            logger.warning("Cancelling ALL open orders")
            self.api.cancel_all_orders()
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False

    # =========================================================================
    # STOP LOSS MODIFICATION (FOR TRAILING)
    # =========================================================================

    def modify_stop_loss(
        self,
        order_id: str,
        new_stop_price: float,
        max_retries: int = 3
    ) -> Optional[Order]:
        """
        Modify an existing stop loss order (for trailing)

        Alpaca doesn't support direct order modification,
        so we cancel and replace.

        CRITICAL: If cancel succeeds but place fails, we retry up to max_retries.
        If all retries fail, the old SL price is still valid (order wasn't cancelled yet).

        Args:
            order_id: Existing stop loss order ID
            new_stop_price: New stop price
            max_retries: Max retry attempts for placing new SL

        Returns:
            New Order object or None if failed
        """
        import time

        try:
            # Get existing order details
            old_order = self.get_order(order_id)
            if not old_order:
                logger.error(f"Order {order_id} not found")
                return None

            if old_order.status != 'accepted' and old_order.status != 'new':
                logger.warning(f"Order {order_id} status is {old_order.status}, cannot modify")
                return None

            symbol = old_order.symbol
            qty = int(old_order.qty)
            old_stop_price = old_order.stop_price

            logger.info(f"Modifying SL for {symbol}: ${old_stop_price:.2f} → ${new_stop_price:.2f}")

            # Cancel old order
            if not self.cancel_order(order_id):
                logger.error("Failed to cancel old SL order")
                return None

            # Place new stop loss with retry logic
            new_order = None
            for attempt in range(max_retries):
                try:
                    new_order = self.place_stop_loss(symbol, qty, new_stop_price)
                    if new_order:
                        break
                except Exception as e:
                    logger.warning(f"Retry {attempt + 1}/{max_retries} placing SL for {symbol}: {e}")
                    time.sleep(1)

            if new_order:
                logger.info(f"SL modified: {order_id} → {new_order.id}")
                return new_order
            else:
                # CRITICAL: All retries failed - try to restore old SL
                logger.error(f"CRITICAL: Failed to place new SL for {symbol}, attempting to restore old SL at ${old_stop_price:.2f}")
                try:
                    fallback_order = self.place_stop_loss(symbol, qty, old_stop_price)
                    if fallback_order:
                        logger.warning(f"Restored original SL for {symbol} at ${old_stop_price:.2f}")
                        return fallback_order
                except Exception:
                    pass
                logger.error(f"CRITICAL: {symbol} has NO STOP LOSS - manual intervention required!")
                return None

        except Exception as e:
            logger.error(f"Failed to modify stop loss: {e}")
            return None

    # =========================================================================
    # HIGH-LEVEL TRADING OPERATIONS (v3.9)
    # =========================================================================

    def buy_with_stop_loss(
        self,
        symbol: str,
        qty: int,
        sl_pct: float = None
    ) -> Tuple[Optional[Order], Optional[Order]]:
        """
        Buy stock and immediately place stop loss

        CRITICAL RULE: If SL fails, sell the position immediately

        Args:
            symbol: Stock symbol
            qty: Number of shares
            sl_pct: Stop loss percentage (default 2.5%)

        Returns:
            Tuple of (buy_order, sl_order) or (None, None) if failed
        """
        sl_pct = sl_pct or self.STOP_LOSS_PCT

        try:
            # 1. Smart buy (limit @ ask + market fallback)
            buy_order = self.place_smart_buy(symbol, qty)
            if not buy_order:
                # Spread too wide → skip
                logger.warning(f"buy_with_stop_loss: Smart buy returned None (spread too wide)")
                return None, None

            # 2. Wait for fill if not already filled
            import time
            if buy_order.status != 'filled':
                max_wait = 30
                for _ in range(max_wait):
                    order = self.get_order(buy_order.id)
                    if order.status == 'filled':
                        buy_order = order
                        break
                    time.sleep(1)

            if buy_order.status != 'filled':
                logger.warning(f"Buy order not filled after wait, cancelling")
                self.cancel_order(buy_order.id)
                time.sleep(0.5)
                # Re-check: order may have filled between status check and cancel
                final_check = self.get_order(buy_order.id)
                if final_check.status == 'filled':
                    logger.info(f"Order filled during cancel — proceeding with SL")
                    buy_order = final_check
                else:
                    return None, None

            fill_price = buy_order.filled_avg_price
            logger.info(f"Buy filled: {symbol} x{qty} @ ${fill_price:.2f}")

            # 3. Calculate stop loss price
            sl_price = fill_price * (1 - sl_pct / 100)

            # 4. Place stop loss order
            try:
                sl_order = self.place_stop_loss(symbol, qty, sl_price)
                logger.info(f"SL placed: {symbol} @ ${sl_price:.2f} (-{sl_pct}%)")
                return buy_order, sl_order

            except Exception as e:
                # CRITICAL: SL failed - must sell immediately
                logger.error(f"SL FAILED - selling position immediately: {e}")
                emergency_sell = self.place_market_sell(symbol, qty)
                # Verify emergency sell fills
                if emergency_sell:
                    for _retry in range(5):
                        time.sleep(1)
                        check = self.get_order(emergency_sell.id)
                        if check.status == 'filled':
                            logger.info(f"Emergency sell filled for {symbol}")
                            break
                    else:
                        logger.error(f"CRITICAL: Emergency sell NOT filled for {symbol} — manual intervention needed!")
                return buy_order, None

        except Exception as e:
            logger.error(f"buy_with_stop_loss failed: {e}")
            return None, None

    def calculate_trailing_stop(
        self,
        entry_price: float,
        peak_price: float,
        activation_pct: float = None,
        lock_pct: float = None
    ) -> Tuple[float, bool]:
        """
        Calculate trailing stop price

        Args:
            entry_price: Original entry price
            peak_price: Highest price since entry
            activation_pct: Profit % to activate trailing (default 2%)
            lock_pct: % of gains to lock (default 70%)

        Returns:
            Tuple of (stop_price, is_trailing_active)
        """
        activation_pct = activation_pct or self.TRAIL_ACTIVATION_PCT
        lock_pct = lock_pct or self.TRAIL_LOCK_PCT

        pnl_pct = ((peak_price - entry_price) / entry_price) * 100

        if pnl_pct < activation_pct:
            # Not yet at trailing activation - use fixed SL
            return entry_price * (1 - self.STOP_LOSS_PCT / 100), False

        # Trailing active - lock percentage of gains
        gain = peak_price - entry_price
        locked_gain = gain * (lock_pct / 100)
        trail_stop = entry_price + locked_gain

        return trail_stop, True

    # =========================================================================
    # UTILITY
    # =========================================================================

    @_retry_api(max_retries=3, base_delay=1.0)
    def get_clock(self) -> Dict:
        """Get market clock"""
        try:
            clock = self.api.get_clock()
            return {
                'is_open': clock.is_open,
                'timestamp': clock.timestamp,
                'next_open': clock.next_open,
                'next_close': clock.next_close,
            }
        except Exception as e:
            logger.error(f"Failed to get clock: {e}")
            raise

    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        clock = self.get_clock()
        return clock['is_open']

    def get_snapshot(self, symbol: str) -> Optional[Dict]:
        """
        Get market snapshot for a symbol (includes extended hours data).
        Returns latest trade, quote, daily bar, and prev daily bar.
        """
        try:
            snap = self.api.get_snapshot(symbol)
            return {
                'latest_trade_price': snap.latest_trade.p,
                'latest_trade_time': str(snap.latest_trade.t),
                'bid': snap.latest_quote.bp,
                'ask': snap.latest_quote.ap,
                'daily_open': snap.daily_bar.o,
                'daily_close': snap.daily_bar.c,
                'daily_high': snap.daily_bar.h,
                'daily_low': snap.daily_bar.l,
                'daily_volume': snap.daily_bar.v,
                'prev_close': snap.prev_daily_bar.c,
            }
        except Exception as e:
            logger.debug(f"Snapshot error for {symbol}: {e}")
            return None

    def get_snapshots(self, symbols: list) -> Dict:
        """Get snapshots for multiple symbols in one API call"""
        results = {}
        try:
            snaps = self.api.get_snapshots(symbols)
            for symbol, snap in snaps.items():
                results[symbol] = {
                    'latest_trade_price': snap.latest_trade.p,
                    'latest_trade_time': str(snap.latest_trade.t),
                    'daily_close': snap.daily_bar.c,
                    'prev_close': snap.prev_daily_bar.c,
                }
        except Exception as e:
            logger.debug(f"Snapshots error: {e}")
        return results


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

def test_connection():
    """Test Alpaca API connection"""
    print("=" * 60)
    print("ALPACA CONNECTION TEST")
    print("=" * 60)

    # Credentials (Paper Trading)
    API_KEY = "PK45CDQEE2WO7I7N4BH762VSMK"
    SECRET_KEY = "DFDhSeYmnsxS2YpyAZLX1MLm9ndfmYr9XaUEiyn78SH1"

    try:
        trader = AlpacaTrader(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            paper=True
        )

        # Test 1: Get Account
        print("\n[1] Account Info:")
        account = trader.get_account()
        print(f"    Status: {account['status']}")
        print(f"    Cash: ${account['cash']:,.2f}")
        print(f"    Portfolio Value: ${account['portfolio_value']:,.2f}")
        print(f"    Buying Power: ${account['buying_power']:,.2f}")

        # Test 2: Market Clock
        print("\n[2] Market Clock:")
        clock = trader.get_clock()
        print(f"    Market Open: {clock['is_open']}")
        print(f"    Next Open: {clock['next_open']}")
        print(f"    Next Close: {clock['next_close']}")

        # Test 3: Positions
        print("\n[3] Current Positions:")
        positions = trader.get_positions()
        if positions:
            for p in positions:
                print(f"    {p.symbol}: {p.qty} shares @ ${p.avg_entry_price:.2f}")
                print(f"           P&L: ${p.unrealized_pl:+.2f} ({p.unrealized_plpc:+.2f}%)")
        else:
            print("    No open positions")

        # Test 4: Open Orders
        print("\n[4] Open Orders:")
        orders = trader.get_orders(status='open')
        if orders:
            for o in orders:
                print(f"    {o.id[:8]}... {o.side.upper()} {o.symbol} x{o.qty}")
                print(f"           Type: {o.type}, Status: {o.status}")
                if o.stop_price:
                    print(f"           Stop: ${o.stop_price:.2f}")
        else:
            print("    No open orders")

        print("\n" + "=" * 60)
        print("CONNECTION TEST: PASSED")
        print("=" * 60)

        return trader

    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nCONNECTION TEST: FAILED")
        return None


if __name__ == "__main__":
    test_connection()
