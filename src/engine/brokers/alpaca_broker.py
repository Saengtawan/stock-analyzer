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
            last_equity=float(acct.last_equity) if hasattr(acct, 'last_equity') else float(acct.equity),
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

        # Use IEX feed for free/paper accounts to avoid SIP subscription errors
        bars = self.api.get_bars(
            symbol,
            timeframe,
            start=start.strftime('%Y-%m-%d'),
            end=end.strftime('%Y-%m-%d'),
            limit=limit,
            feed='iex'  # Free tier compatible
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
        peak_price: float,  # v4.9: Renamed from current_price for clarity
        current_stop: float,
        trail_activation_pct: float = 3.0,  # v4.9: Updated default from 2.0
        trail_lock_pct: float = 80.0,       # v4.9: Updated default from 70.0
    ) -> Tuple[float, bool]:
        """
        Calculate trailing stop price to lock in profits.

        Args:
            entry_price: Original entry price
            peak_price: Highest price reached (NOT current price!)
            current_stop: Current stop loss price
            trail_activation_pct: Gain % to activate trailing (default 3%)
            trail_lock_pct: % of gain to lock (default 80%)

        Returns:
            Tuple of (new_stop_price, updated)

        Example:
            Entry: $100, Peak: $110 (+10%)
            → Lock 80% of $10 = $8
            → New SL: $108 (lock $8 profit)
        """
        gain_pct = ((peak_price - entry_price) / entry_price) * 100

        if gain_pct < trail_activation_pct:
            return current_stop, False

        # Calculate new stop to lock in gains from peak
        gain_amount = peak_price - entry_price
        locked_gain = gain_amount * (trail_lock_pct / 100)
        new_stop = entry_price + locked_gain

        # Only raise stop, never lower
        if new_stop > current_stop:
            return round(new_stop, 2), True

        return current_stop, False

    # =========================================================================
    # PORTFOLIO HISTORY & ANALYTICS
    # =========================================================================

    @_retry_api()
    def get_portfolio_history(
        self,
        period: str = '1M',
        timeframe: str = '1D',
        extended_hours: bool = False
    ) -> Dict:
        """
        Get portfolio equity history from Alpaca.

        Args:
            period: Time period ('1D', '1W', '1M', '3M', '1A', 'all')
            timeframe: Bar timeframe ('1Min', '5Min', '15Min', '1H', '1D')
            extended_hours: Include extended hours

        Returns:
            Dict with:
            - equity: List[float] - Equity values
            - profit_loss: List[float] - P&L in dollars
            - profit_loss_pct: List[float] - P&L in percent
            - base_value: float - Starting equity
            - timeframe: str - Timeframe used
            - timestamp: List[int] - Unix timestamps

        Example:
            history = broker.get_portfolio_history(period='1M', timeframe='1D')
            equity_curve = history['equity']
            daily_returns = history['profit_loss_pct']
        """
        history = self.api.get_portfolio_history(
            period=period,
            timeframe=timeframe,
            extended_hours=extended_hours
        )

        return {
            'equity': history.equity,
            'profit_loss': history.profit_loss,
            'profit_loss_pct': history.profit_loss_pct,
            'base_value': history.base_value,
            'timeframe': history.timeframe,
            'timestamp': history.timestamp,
        }

    def calculate_performance_metrics(self, history: Dict) -> Dict:
        """
        Calculate performance metrics from portfolio history.

        Args:
            history: Output from get_portfolio_history()

        Returns:
            Dict with metrics:
            - total_return_pct: Total return %
            - total_return_usd: Total return $
            - max_drawdown_pct: Maximum drawdown %
            - max_drawdown_date: Date of max drawdown
            - sharpe_ratio: Sharpe ratio (annualized)
            - win_days: Number of profitable days
            - loss_days: Number of losing days
            - win_rate: Win rate %
            - avg_daily_return: Average daily return %
            - volatility: Daily volatility (std dev)
        """
        import numpy as np
        from datetime import datetime as dt

        equity = history['equity']
        profit_loss_pct = history['profit_loss_pct']
        timestamps = history['timestamp']

        if not equity or len(equity) < 2:
            return {
                'total_return_pct': 0,
                'total_return_usd': 0,
                'max_drawdown_pct': 0,
                'max_drawdown_date': None,
                'sharpe_ratio': 0,
                'win_days': 0,
                'loss_days': 0,
                'win_rate': 0,
                'avg_daily_return': 0,
                'volatility': 0,
            }

        # Total return
        total_return_pct = ((equity[-1] - equity[0]) / equity[0]) * 100
        total_return_usd = equity[-1] - equity[0]

        # Max drawdown
        peak = equity[0]
        max_dd = 0
        max_dd_date = None

        for i, eq in enumerate(equity):
            if eq > peak:
                peak = eq
            dd = ((eq - peak) / peak) * 100
            if dd < max_dd:
                max_dd = dd
                max_dd_date = dt.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d') if timestamps else None

        # Daily returns analysis
        daily_returns = []
        for i in range(1, len(profit_loss_pct)):
            daily_return = profit_loss_pct[i] - profit_loss_pct[i-1]
            daily_returns.append(daily_return)

        win_days = sum(1 for r in daily_returns if r > 0)
        loss_days = sum(1 for r in daily_returns if r <= 0)
        win_rate = (win_days / len(daily_returns) * 100) if daily_returns else 0

        # Sharpe ratio (annualized, assume risk-free rate = 0)
        if daily_returns:
            avg_return = np.mean(daily_returns)
            std_return = np.std(daily_returns)
            sharpe = (avg_return / std_return * np.sqrt(252)) if std_return > 0 else 0
        else:
            avg_return = 0
            std_return = 0
            sharpe = 0

        return {
            'total_return_pct': round(total_return_pct, 2),
            'total_return_usd': round(total_return_usd, 2),
            'max_drawdown_pct': round(max_dd, 2),
            'max_drawdown_date': max_dd_date,
            'sharpe_ratio': round(sharpe, 2),
            'win_days': win_days,
            'loss_days': loss_days,
            'win_rate': round(win_rate, 1),
            'avg_daily_return': round(avg_return, 3),
            'volatility': round(std_return, 3),
        }

    # =========================================================================
    # TRADE HISTORY & ACTIVITIES
    # =========================================================================

    @_retry_api()
    def get_activities(
        self,
        activity_types: str = 'FILL',
        days: int = 30,
        direction: str = 'desc',
        page_size: int = 100
    ) -> List[Dict]:
        """
        Get account activities (fills, dividends, etc).

        Args:
            activity_types: 'FILL', 'DIV', 'CSD', etc (comma-separated)
            days: Number of days to look back
            direction: 'asc' or 'desc'
            page_size: Max results per page

        Returns:
            List of activities with details:
            - symbol: Stock symbol
            - side: 'buy' or 'sell'
            - qty: Quantity
            - price: Fill price
            - transaction_time: Timestamp
            - order_id: Related order ID

        Example:
            fills = broker.get_activities(activity_types='FILL', days=7)
            for fill in fills:
                print(f"{fill['symbol']}: {fill['qty']} @ ${fill['price']}")
        """
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        activities = self.api.get_activities(
            activity_types=activity_types,
            date=start_date,
            direction=direction,
            page_size=page_size
        )

        result = []
        for activity in activities:
            # Convert to dict
            act_dict = {
                'id': activity.id,
                'activity_type': activity.activity_type,
                'transaction_time': activity.transaction_time.isoformat() if hasattr(activity.transaction_time, 'isoformat') else str(activity.transaction_time),
            }

            # FILL-specific fields
            if activity.activity_type == 'FILL':
                act_dict.update({
                    'symbol': activity.symbol,
                    'side': activity.side,
                    'qty': float(activity.qty),
                    'price': float(activity.price),
                    'order_id': activity.order_id,
                })

            # DIV-specific fields
            elif activity.activity_type == 'DIV':
                act_dict.update({
                    'symbol': activity.symbol,
                    'qty': float(activity.qty) if hasattr(activity, 'qty') else 0,
                    'amount': float(activity.net_amount) if hasattr(activity, 'net_amount') else 0,
                })

            result.append(act_dict)

        return result

    def analyze_slippage(self, fills: List[Dict], orders: List[Order]) -> Dict:
        """
        Analyze slippage from fills vs expected prices.

        Args:
            fills: List from get_activities(activity_types='FILL')
            orders: List from get_orders(status='filled')

        Returns:
            Dict with slippage analysis:
            - total_fills: Number of fills
            - avg_slippage_usd: Average slippage per share
            - avg_slippage_pct: Average slippage %
            - total_slippage_cost: Total slippage cost
            - positive_slippage_count: Favorable fills
            - negative_slippage_count: Unfavorable fills
        """
        if not fills or not orders:
            return {
                'total_fills': 0,
                'avg_slippage_usd': 0,
                'avg_slippage_pct': 0,
                'total_slippage_cost': 0,
                'positive_slippage_count': 0,
                'negative_slippage_count': 0,
            }

        # Create order lookup
        order_map = {o.id: o for o in orders}

        slippages = []
        total_cost = 0
        positive = 0
        negative = 0

        for fill in fills:
            if fill['activity_type'] != 'FILL':
                continue

            order_id = fill.get('order_id')
            if not order_id or order_id not in order_map:
                continue

            order = order_map[order_id]
            fill_price = fill['price']

            # Determine expected price (limit price or snapshot at order time)
            expected_price = order.limit_price if order.limit_price else fill_price

            # Calculate slippage
            if fill['side'] == 'buy':
                slippage = fill_price - expected_price  # Negative = better
            else:
                slippage = expected_price - fill_price  # Negative = worse

            slippages.append(slippage)
            total_cost += slippage * fill['qty']

            if slippage < 0:
                positive += 1
            else:
                negative += 1

        avg_slippage = sum(slippages) / len(slippages) if slippages else 0
        avg_pct = (avg_slippage / sum(f['price'] for f in fills if f['activity_type'] == 'FILL') * len(slippages)) * 100 if slippages else 0

        return {
            'total_fills': len(slippages),
            'avg_slippage_usd': round(avg_slippage, 4),
            'avg_slippage_pct': round(avg_pct, 4),
            'total_slippage_cost': round(total_cost, 2),
            'positive_slippage_count': positive,
            'negative_slippage_count': negative,
        }

    # =========================================================================
    # MARKET CALENDAR
    # =========================================================================

    @_retry_api()
    def get_calendar(
        self,
        start: str = None,
        end: str = None
    ) -> List[Dict]:
        """
        Get market calendar (trading days).

        Args:
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)

        Returns:
            List of trading days with:
            - date: Trading date
            - open: Market open time
            - close: Market close time

        Example:
            calendar = broker.get_calendar(
                start='2026-02-01',
                end='2026-02-28'
            )
        """
        if not start:
            start = datetime.now().strftime('%Y-%m-%d')
        if not end:
            end = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

        calendar = self.api.get_calendar(start=start, end=end)

        result = []
        for day in calendar:
            result.append({
                'date': day.date.strftime('%Y-%m-%d') if hasattr(day.date, 'strftime') else str(day.date),
                'open': day.open.strftime('%H:%M') if hasattr(day.open, 'strftime') else str(day.open),
                'close': day.close.strftime('%H:%M') if hasattr(day.close, 'strftime') else str(day.close),
            })

        return result

    def is_market_open_tomorrow(self) -> bool:
        """
        Check if market will be open tomorrow.

        Returns:
            True if market opens tomorrow, False otherwise

        Example:
            if not broker.is_market_open_tomorrow():
                logger.warning("Tomorrow is holiday - skip new positions")
        """
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        calendar = self.get_calendar(start=tomorrow, end=tomorrow)
        return len(calendar) > 0

    def get_next_market_day(self) -> Optional[str]:
        """
        Get next trading day date.

        Returns:
            Date string (YYYY-MM-DD) or None
        """
        today = datetime.now()
        for i in range(1, 10):  # Check next 10 days
            check_date = (today + timedelta(days=i)).strftime('%Y-%m-%d')
            calendar = self.get_calendar(start=check_date, end=check_date)
            if calendar:
                return check_date
        return None

    def get_upcoming_holidays(self, days: int = 30) -> List[Dict]:
        """
        Get upcoming market holidays.

        Args:
            days: Number of days to look ahead

        Returns:
            List of holidays with:
            - date: Holiday date
            - days_away: Days until holiday

        Example:
            holidays = broker.get_upcoming_holidays(days=30)
            for h in holidays:
                print(f"Holiday on {h['date']} ({h['days_away']} days away)")
        """
        start = datetime.now()
        end = start + timedelta(days=days)

        # Get all calendar days in range
        all_days = []
        current = start
        while current <= end:
            all_days.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)

        # Get trading days
        calendar = self.get_calendar(
            start=start.strftime('%Y-%m-%d'),
            end=end.strftime('%Y-%m-%d')
        )
        trading_days = set(day['date'] for day in calendar)

        # Find holidays (weekdays that are not trading days)
        holidays = []
        for day_str in all_days:
            day = datetime.strptime(day_str, '%Y-%m-%d')
            # Skip weekends
            if day.weekday() >= 5:
                continue
            # If weekday but not trading day = holiday
            if day_str not in trading_days:
                days_away = (day - start).days
                holidays.append({
                    'date': day_str,
                    'days_away': days_away,
                    'day_of_week': day.strftime('%A'),
                })

        return holidays

    # =========================================================================
    # UTILITY
    # =========================================================================

    @property
    def broker_name(self) -> str:
        return "Alpaca"

    @property
    def is_paper(self) -> bool:
        return self._paper
