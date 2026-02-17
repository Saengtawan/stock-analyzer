"""
Data Manager - Coordinates multiple data sources

v6.7 - UNIFIED DATA LAYER:
- Added broker integration for realtime data
- Single abstraction for ALL READ operations
- Fallback logic: broker → API sources → cached data
"""
import os
import json
import pandas as pd
import yfinance as yf
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from loguru import logger

from .yahoo_finance_client import YahooFinanceClient
from .fmp_client import FMPClient
from .tiingo_client import TiingoClient
from .base_client import APIError, DataCache

# v6.x: Import market utilities (Single Source of Truth)
try:
    from utils.market_hours import MARKET_OPEN_STR, MARKET_CLOSE_STR
except ImportError:
    MARKET_OPEN_STR = '09:30'
    MARKET_CLOSE_STR = '16:00'


class DataManager:
    """
    Unified data layer for historical + realtime data (v6.7)

    Manages data from multiple sources with fallback capabilities:
    - Broker (Alpaca) - realtime prices, positions, orders, account
    - Yahoo Finance - historical data, fallback prices
    - Tiingo/FMP - backup sources
    - Local cache/JSON - offline fallback

    Design: READ operations only (WRITE stays direct to broker)
    """

    def __init__(self, config: Dict[str, Any] = None, broker=None):
        """
        Initialize DataManager with optional broker integration

        Args:
            config: Configuration dict
            broker: Optional BrokerInterface for realtime data (e.g., AlpacaBroker)
        """
        self.config = config or {}
        self.cache = DataCache(ttl_minutes=60)
        self.broker = broker  # v6.7: Optional broker for realtime data

        # Initialize clients
        self.yahoo_client = YahooFinanceClient()

        # FMP client (optional, requires API key)
        fmp_key = os.getenv('FMP_API_KEY')
        self.fmp_client = None
        # if fmp_key:
        #     self.fmp_client = FMPClient(fmp_key)

        # Tiingo client (optional — backup only, free tier rate limit too low for primary)
        tiingo_key = os.getenv('TIINGO_API_KEY')
        self.tiingo_client = None
        if tiingo_key:
            self.tiingo_client = TiingoClient(tiingo_key)

        # v4.9.4: Yahoo primary (no hard rate limit, supports fundamentals + real-time)
        # Tiingo demoted to backup (free tier ~50/hr, price-only, 429 issues)
        self.primary_source = self.config.get('primary_source', 'yahoo')
        self.backup_source = self.config.get('backup_source', 'tiingo' if self.tiingo_client else 'yahoo')
        self.price_backup = self.config.get('price_backup', 'tiingo' if self.tiingo_client else 'yahoo')

        # v6.7: Cache paths for offline fallback
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.account_cache_file = os.path.join(self.project_root, 'data', 'account_cache.json')

        logger.info(f"DataManager initialized with primary: {self.primary_source}, backup: {self.backup_source}, "
                   f"price_backup: {self.price_backup}, broker: {'Yes' if broker else 'No'}")

    def get_price_data(self, symbol: str, period: str = "1y", interval: str = "1d",
                        data_type: str = 'price') -> pd.DataFrame:
        """
        Get price data with fallback to backup source

        Args:
            symbol: Stock symbol
            period: Time period
            interval: Data interval
            data_type: Cache data type for TTL selection (default 'price', use 'sector_etf' for 5min TTL)

        Returns:
            DataFrame with price data
        """
        # Try primary source first
        try:
            if self.primary_source == 'yahoo':
                return self.yahoo_client.get_price_data(symbol, period, interval, data_type=data_type)
            elif self.primary_source == 'fmp' and self.fmp_client:
                return self.fmp_client.get_price_data(symbol, period, interval)
            elif self.primary_source == 'tiingo' and self.tiingo_client:
                return self.tiingo_client.get_price_data(symbol, period, interval)
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source}) failed for {symbol}: {e}")

        # Try backup source
        try:
            if self.backup_source == 'yahoo' and self.primary_source != 'yahoo':
                return self.yahoo_client.get_price_data(symbol, period, interval, data_type=data_type)
            elif self.backup_source == 'fmp' and self.fmp_client and self.primary_source != 'fmp':
                return self.fmp_client.get_price_data(symbol, period, interval)
            elif self.backup_source == 'tiingo' and self.tiingo_client and self.primary_source != 'tiingo':
                return self.tiingo_client.get_price_data(symbol, period, interval)
        except Exception as e:
            logger.warning(f"Backup source ({self.backup_source}) also failed for {symbol}: {e}")

        # Try price backup source (Tiingo is good for price data)
        try:
            if self.price_backup == 'tiingo' and self.tiingo_client and self.primary_source != 'tiingo' and self.backup_source != 'tiingo':
                return self.tiingo_client.get_price_data(symbol, period, interval)
            elif self.price_backup == 'fmp' and self.fmp_client and self.primary_source != 'fmp' and self.backup_source != 'fmp':
                return self.fmp_client.get_price_data(symbol, period, interval)
        except Exception as e:
            logger.error(f"Price backup source ({self.price_backup}) also failed for {symbol}: {e}")

        raise APIError(f"Failed to get price data for {symbol} from all sources")

    def get_financial_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get financial data with fallback

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary with financial data
        """
        # Try primary source first
        try:
            if self.primary_source == 'yahoo':
                return self.yahoo_client.get_financial_data(symbol)
            elif self.primary_source == 'fmp' and self.fmp_client:
                return self.fmp_client.get_financial_data(symbol)
            elif self.primary_source == 'tiingo' and self.tiingo_client:
                # Tiingo doesn't provide financial data, fall through to backup
                raise APIError("Tiingo doesn't provide financial data")
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source}) failed for financial data {symbol}: {e}")

        # Try backup source (prefer FMP for financial data)
        try:
            if self.backup_source == 'fmp' and self.fmp_client and self.primary_source != 'fmp':
                return self.fmp_client.get_financial_data(symbol)
            elif self.backup_source == 'yahoo' and self.primary_source != 'yahoo':
                return self.yahoo_client.get_financial_data(symbol)
        except Exception as e:
            logger.error(f"Backup source ({self.backup_source}) also failed for financial data {symbol}: {e}")

        raise APIError(f"Failed to get financial data for {symbol} from all sources")

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """Get company information"""
        try:
            if self.primary_source == 'yahoo':
                return self.yahoo_client.get_company_info(symbol)
            elif self.primary_source == 'fmp' and self.fmp_client:
                return self.fmp_client.get_company_info(symbol)
            elif self.primary_source == 'tiingo' and self.tiingo_client:
                return self.tiingo_client.get_company_info(symbol)
        except Exception as e:
            logger.warning(f"Primary source failed for company info {symbol}: {e}")

        # Try backup
        try:
            if self.backup_source == 'fmp' and self.fmp_client and self.primary_source != 'fmp':
                return self.fmp_client.get_company_info(symbol)
            elif self.backup_source == 'yahoo' and self.primary_source != 'yahoo':
                return self.yahoo_client.get_company_info(symbol)
            elif self.backup_source == 'tiingo' and self.tiingo_client and self.primary_source != 'tiingo':
                return self.tiingo_client.get_company_info(symbol)
        except Exception as e:
            logger.error(f"Backup source also failed for company info {symbol}: {e}")

        raise APIError(f"Failed to get company info for {symbol}")

    def get_real_time_price(self, symbol: str) -> Dict[str, Any]:
        """Get real-time price with fallback"""
        # Try Yahoo first (usually most reliable for real-time)
        try:
            return self.yahoo_client.get_real_time_price(symbol)
        except Exception as e:
            logger.warning(f"Yahoo failed for real-time price {symbol}: {e}")

        # Try FMP
        if self.fmp_client:
            try:
                return self.fmp_client.get_real_time_price(symbol)
            except Exception as e:
                logger.warning(f"FMP failed for real-time price {symbol}: {e}")

        # Try Tiingo
        if self.tiingo_client:
            try:
                return self.tiingo_client.get_real_time_price(symbol)
            except Exception as e:
                logger.error(f"Tiingo also failed for real-time price {symbol}: {e}")

        raise APIError(f"Failed to get real-time price for {symbol} from all sources")

    def get_multiple_symbols(self, symbols: List[str], data_type: str = "price", **kwargs) -> Dict[str, Any]:
        """
        Get data for multiple symbols efficiently

        Args:
            symbols: List of stock symbols
            data_type: Type of data ('price', 'financial', 'company')
            **kwargs: Additional parameters for data retrieval

        Returns:
            Dictionary mapping symbols to their data
        """
        results = {}
        errors = {}

        for symbol in symbols:
            try:
                if data_type == "price":
                    results[symbol] = self.get_price_data(symbol, **kwargs)
                elif data_type == "financial":
                    results[symbol] = self.get_financial_data(symbol)
                elif data_type == "company":
                    results[symbol] = self.get_company_info(symbol)
                elif data_type == "realtime":
                    results[symbol] = self.get_real_time_price(symbol)
                else:
                    raise ValueError(f"Unknown data type: {data_type}")

            except Exception as e:
                errors[symbol] = str(e)
                logger.error(f"Failed to get {data_type} data for {symbol}: {e}")

        if errors:
            logger.warning(f"Errors occurred for symbols: {errors}")

        return {
            'data': results,
            'errors': errors,
            'success_count': len(results),
            'error_count': len(errors),
            'total_requested': len(symbols)
        }

    def validate_symbols(self, symbols: List[str]) -> Dict[str, bool]:
        """
        Validate multiple symbols

        Args:
            symbols: List of symbols to validate

        Returns:
            Dictionary mapping symbols to their validity
        """
        results = {}

        for symbol in symbols:
            try:
                # Try to get company info as validation
                self.get_company_info(symbol)
                results[symbol] = True
            except Exception:
                results[symbol] = False

        return results

    def get_market_data(self, symbols: List[str] = None) -> Dict[str, Any]:
        """
        Get market overview data

        Args:
            symbols: Optional list of symbols, defaults to major indices

        Returns:
            Dictionary with market data
        """
        if symbols is None:
            symbols = ['SPY', 'QQQ', 'IWM', 'VTI', 'DIA']  # Major ETFs

        market_data = {}

        for symbol in symbols:
            try:
                data = self.get_real_time_price(symbol)
                market_data[symbol] = data
            except Exception as e:
                logger.error(f"Failed to get market data for {symbol}: {e}")

        return market_data

    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        if hasattr(self.yahoo_client, 'cache'):
            self.yahoo_client.cache.clear()
        if self.fmp_client and hasattr(self.fmp_client, 'cache'):
            self.fmp_client.cache.clear()
        if self.tiingo_client and hasattr(self.tiingo_client, 'cache'):
            self.tiingo_client.cache.clear()

        logger.info("All caches cleared")

    def get_data_freshness(self, symbol: str) -> Dict[str, Any]:
        """
        Check data freshness for a symbol

        Returns:
            Dictionary with cache status and last update times
        """
        cache_status = {}

        # Check price data cache
        price_key = f"price_{symbol}_1y_1d"
        price_cached = self.yahoo_client.cache.get(price_key) is not None
        cache_status['price_cached'] = price_cached

        # Check financial data cache
        financial_key = f"financial_{symbol}"
        financial_cached = self.yahoo_client.cache.get(financial_key) is not None
        cache_status['financial_cached'] = financial_cached

        return {
            'symbol': symbol,
            'cache_status': cache_status,
            'timestamp': datetime.now().isoformat()
        }

    def get_sector_top_companies(self, sector_key: str) -> 'pd.DataFrame':
        """Get top 50 companies for a sector via Yahoo Finance (v5.2)."""
        return self.yahoo_client.get_sector_top_companies(sector_key)

    def batch_download_prices(self, symbols: list, period: str = '5d',
                              interval: str = '1d',
                              data_type: str = 'sector_price') -> 'pd.DataFrame':
        """Batch download prices for multiple symbols (v5.2)."""
        return self.yahoo_client.batch_download_prices(symbols, period, interval, data_type)

    # =========================================================================
    # v6.7: REALTIME PRICES (broker → yfinance fallback)
    # =========================================================================

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current realtime price with fallback (v6.7)

        Priority:
        1. Broker (Alpaca realtime) if available
        2. yfinance (15-min delayed for free tier)

        Returns:
            Current price as float, or None if all sources fail
        """
        # Try broker first (realtime)
        if self.broker:
            try:
                quote = self.broker.get_snapshot(symbol)
                if quote and quote.last > 0:
                    logger.debug(f"Price from broker: {symbol} = ${quote.last:.2f}")
                    return float(quote.last)
            except Exception as e:
                logger.warning(f"Broker price fetch failed for {symbol}: {e}")

        # Fallback to yfinance
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='1d')
            if len(data) > 0:
                price = float(data['Close'].iloc[-1])
                logger.debug(f"Price from yfinance: {symbol} = ${price:.2f}")
                return price
        except Exception as e:
            logger.warning(f"yfinance price fetch failed for {symbol}: {e}")

        logger.error(f"Failed to get current price for {symbol} from all sources")
        return None

    def get_batch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Batch fetch current prices with fallback (v6.7)

        Priority:
        1. Broker batch snapshots (1 API call for all symbols)
        2. yfinance parallel fetch

        Returns:
            Dict mapping symbol → current price
        """
        prices = {}

        # Try broker batch fetch first (fast!)
        if self.broker:
            try:
                quotes = self.broker.get_snapshots(symbols)
                for symbol, quote in quotes.items():
                    if quote and quote.last > 0:
                        prices[symbol] = float(quote.last)

                if prices:
                    logger.info(f"Batch prices from broker: {len(prices)}/{len(symbols)} symbols")

                    # Fill missing symbols with yfinance
                    missing = set(symbols) - set(prices.keys())
                    if missing:
                        logger.warning(f"Broker missing {len(missing)} symbols, using yfinance fallback")
                        for symbol in missing:
                            price = self.get_current_price(symbol)
                            if price:
                                prices[symbol] = price

                    return prices
            except Exception as e:
                logger.warning(f"Broker batch fetch failed: {e}, falling back to yfinance")

        # Fallback: yfinance parallel fetch
        logger.info(f"Batch prices from yfinance: {len(symbols)} symbols")
        for symbol in symbols:
            price = self.get_current_price(symbol)
            if price:
                prices[symbol] = price

        return prices

    def get_bars(self, symbol: str, timeframe: str = '1Day',
                 start: datetime = None, end: datetime = None,
                 limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Get historical bars with fallback (v6.7)

        Priority:
        1. Broker get_bars() if available
        2. yfinance historical data

        Args:
            symbol: Stock symbol
            timeframe: '1Day', '1Hour', '5Min', etc.
            start: Start datetime
            end: End datetime
            limit: Max bars to fetch

        Returns:
            DataFrame with OHLCV data
        """
        # Try broker first
        if self.broker:
            try:
                bars = self.broker.get_bars(symbol, timeframe, start, end, limit)
                if bars:
                    # Convert to DataFrame
                    data = []
                    for bar in bars:
                        data.append({
                            'timestamp': bar.timestamp,
                            'open': bar.open,
                            'high': bar.high,
                            'low': bar.low,
                            'close': bar.close,
                            'volume': bar.volume
                        })
                    df = pd.DataFrame(data)
                    df.set_index('timestamp', inplace=True)
                    logger.debug(f"Bars from broker: {symbol} ({len(df)} bars)")
                    return df
            except Exception as e:
                logger.warning(f"Broker bars fetch failed for {symbol}: {e}")

        # Fallback to yfinance
        try:
            # Map timeframe to yfinance interval
            interval_map = {
                '1Day': '1d',
                '1Hour': '1h',
                '5Min': '5m',
                '15Min': '15m',
                '1Min': '1m'
            }
            interval = interval_map.get(timeframe, '1d')

            # Calculate period from limit
            if limit <= 7:
                period = '7d'
            elif limit <= 30:
                period = '1mo'
            elif limit <= 90:
                period = '3mo'
            else:
                period = '1y'

            df = self.get_price_data(symbol, period=period, interval=interval)
            if not df.empty:
                logger.debug(f"Bars from yfinance: {symbol} ({len(df)} bars)")
                return df.tail(limit)
        except Exception as e:
            logger.error(f"yfinance bars fetch failed for {symbol}: {e}")

        return None

    # =========================================================================
    # v6.7: ACCOUNT & POSITIONS (broker → cached JSON fallback)
    # =========================================================================

    def get_account(self) -> Optional[Any]:
        """
        Get account information with fallback (v6.7)

        Priority:
        1. Broker get_account() if available
        2. Cached account data (last known state)

        Returns:
            Account object with equity, cash, buying_power, etc.
        """
        # Try broker first
        if self.broker:
            try:
                account = self.broker.get_account()

                # Cache account data for offline fallback
                try:
                    os.makedirs(os.path.dirname(self.account_cache_file), exist_ok=True)
                    cache_data = {
                        'equity': float(account.equity),
                        'cash': float(account.cash),
                        'buying_power': float(account.buying_power),
                        'portfolio_value': float(account.portfolio_value),
                        'pattern_day_trader': account.pattern_day_trader,
                        'day_trade_count': account.day_trade_count,
                        'cached_at': datetime.now().isoformat()
                    }
                    with open(self.account_cache_file, 'w') as f:
                        json.dump(cache_data, f, indent=2)
                except Exception as e:
                    logger.debug(f"Failed to cache account data: {e}")

                return account
            except Exception as e:
                logger.warning(f"Broker get_account failed: {e}, trying cached data")

        # Fallback to cached account data
        try:
            if os.path.exists(self.account_cache_file):
                with open(self.account_cache_file) as f:
                    cached = json.load(f)

                cached_time = datetime.fromisoformat(cached['cached_at'])
                age_hours = (datetime.now() - cached_time).total_seconds() / 3600

                if age_hours < 24:
                    logger.info(f"Using cached account data (age: {age_hours:.1f}h)")
                    # Create mock Account object
                    from ..engine.broker_interface import Account
                    return Account(
                        equity=cached['equity'],
                        cash=cached['cash'],
                        buying_power=cached['buying_power'],
                        portfolio_value=cached['portfolio_value'],
                        pattern_day_trader=cached.get('pattern_day_trader', False),
                        day_trade_count=cached.get('day_trade_count', 0)
                    )
                else:
                    logger.warning(f"Cached account data is stale ({age_hours:.1f}h old)")
        except Exception as e:
            logger.error(f"Failed to load cached account data: {e}")

        return None

    def get_positions(self) -> List[Any]:
        """
        Get all positions with fallback (v6.7)

        Priority:
        1. Broker get_positions() if available
        2. Local portfolio.json (managed positions)

        Returns:
            List of Position objects
        """
        # Try broker first
        if self.broker:
            try:
                positions = self.broker.get_positions()
                logger.debug(f"Positions from broker: {len(positions)} positions")
                return positions
            except Exception as e:
                logger.warning(f"Broker get_positions failed: {e}, trying local portfolio")

        # Fallback to DB (single source of truth)
        try:
            from database import PositionRepository
            from ..engine.broker_interface import Position
            repo = PositionRepository()
            db_positions = repo.get_all()
            positions = []
            for db_pos in db_positions:
                qty = db_pos.qty or 0
                price = db_pos.entry_price or 0.0
                positions.append(Position(
                    symbol=db_pos.symbol,
                    qty=qty,
                    avg_entry_price=price,
                    current_price=price,
                    market_value=qty * price,
                    unrealized_pl=0,
                    unrealized_plpc=0,
                    side='long',
                    cost_basis=qty * price,
                ))
            logger.info(f"Positions from DB: {len(positions)} positions")
            return positions
        except Exception as e:
            logger.error(f"Failed to load positions from DB: {e}")

        return []

    def get_position(self, symbol: str) -> Optional[Any]:
        """
        Get position for specific symbol with fallback (v6.7)

        Priority:
        1. Broker get_position() if available
        2. Local portfolio.json

        Returns:
            Position object or None
        """
        # Try broker first
        if self.broker:
            try:
                position = self.broker.get_position(symbol)
                if position:
                    return position
            except Exception as e:
                logger.debug(f"Broker get_position failed for {symbol}: {e}")

        # Fallback to DB (single source of truth)
        try:
            from database import PositionRepository
            from ..engine.broker_interface import Position
            repo = PositionRepository()
            db_pos = repo.get_by_symbol(symbol)
            if db_pos:
                qty = db_pos.qty or 0
                price = db_pos.entry_price or 0.0
                return Position(
                    symbol=db_pos.symbol,
                    qty=qty,
                    avg_entry_price=price,
                    current_price=price,
                    market_value=qty * price,
                    unrealized_pl=0,
                    unrealized_plpc=0,
                    side='long',
                    cost_basis=qty * price,
                )
        except Exception as e:
            logger.debug(f"Failed to load position from DB: {e}")

        return None

    # =========================================================================
    # v6.7: ORDERS (broker → empty fallback)
    # =========================================================================

    def get_orders(self, status: str = 'open') -> List[Any]:
        """
        Get orders with fallback (v6.7)

        Priority:
        1. Broker get_orders() if available
        2. Empty list (no offline fallback for orders)

        Returns:
            List of Order objects
        """
        if self.broker:
            try:
                orders = self.broker.get_orders(status=status)
                logger.debug(f"Orders from broker: {len(orders)} orders")
                return orders
            except Exception as e:
                logger.warning(f"Broker get_orders failed: {e}")

        # No fallback for orders (must be live)
        return []

    def get_order(self, order_id: str) -> Optional[Any]:
        """
        Get specific order with fallback (v6.7)

        Priority:
        1. Broker get_order() if available
        2. None (no offline fallback)

        Returns:
            Order object or None
        """
        if self.broker:
            try:
                order = self.broker.get_order(order_id)
                return order
            except Exception as e:
                logger.debug(f"Broker get_order failed for {order_id}: {e}")

        return None

    # =========================================================================
    # v6.7: MARKET INFO (broker → standard hours fallback)
    # =========================================================================

    def get_clock(self) -> Optional[Any]:
        """
        Get market clock with fallback (v6.7)

        Priority:
        1. Broker get_clock() if available
        2. Standard market hours (9:30-16:00 ET, Mon-Fri)

        Returns:
            Clock object with is_open, next_open, next_close
        """
        if self.broker:
            try:
                clock = self.broker.get_clock()
                return clock
            except Exception as e:
                logger.warning(f"Broker get_clock failed: {e}, using standard hours")

        # Fallback: standard market hours
        from ..engine.broker_interface import Clock
        now = datetime.now()

        # Check if market day (Mon-Fri, not holiday)
        is_market_day = now.weekday() < 5

        # Standard hours: 9:30-16:00 ET
        market_open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)

        is_open = is_market_day and market_open_time <= now <= market_close_time

        # Calculate next open/close
        if now < market_open_time and is_market_day:
            next_open = market_open_time
        else:
            # Next trading day
            days_ahead = 1 if now.weekday() < 4 else (7 - now.weekday())
            next_open = (now + timedelta(days=days_ahead)).replace(hour=9, minute=30, second=0)

        if is_open:
            next_close = market_close_time
        else:
            next_close = next_open.replace(hour=16, minute=0)

        return Clock(
            is_open=is_open,
            next_open=next_open,
            next_close=next_close
        )

    def is_market_open(self) -> bool:
        """Check if market is currently open (v6.7)"""
        clock = self.get_clock()
        return clock.is_open if clock else False

    def get_calendar(self, start: str = None, end: str = None) -> List[Dict]:
        """
        Get market calendar with fallback (v6.7)

        Priority:
        1. Broker get_calendar() if available
        2. Standard trading days (Mon-Fri, no holidays)

        Returns:
            List of trading days with date, open, close times
        """
        if self.broker:
            try:
                calendar = self.broker.get_calendar(start=start, end=end)
                return calendar
            except Exception as e:
                logger.warning(f"Broker get_calendar failed: {e}, using standard calendar")

        # Fallback: generate standard trading days
        if not start:
            start = datetime.now().strftime('%Y-%m-%d')
        if not end:
            end = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

        start_date = datetime.strptime(start, '%Y-%m-%d')
        end_date = datetime.strptime(end, '%Y-%m-%d')

        calendar = []
        current = start_date
        while current <= end_date:
            # Include Mon-Fri only
            if current.weekday() < 5:
                calendar.append({
                    'date': current.strftime('%Y-%m-%d'),
                    'open': MARKET_OPEN_STR,
                    'close': MARKET_CLOSE_STR
                })
            current += timedelta(days=1)

        return calendar