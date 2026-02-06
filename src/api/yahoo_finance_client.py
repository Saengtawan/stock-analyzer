"""
Yahoo Finance API Client - v6.10 with Robust Rate Limit Handling
"""
import yfinance as yf
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import time
import random
from loguru import logger

from .base_client import BaseAPIClient, DataCache, APIError


class YahooFinanceClient(BaseAPIClient):
    """
    Yahoo Finance data client with robust rate limit handling (v6.10)

    Implements:
    - Long cache (4 hours) to minimize API calls
    - Smart throttling with exponential backoff
    - Jittered delays to avoid request patterns
    - Session/crumb refresh on 401 errors
    """

    def __init__(self):
        # Yahoo Finance doesn't require API key
        # v7.0: Balanced rate limit (fast but safe)
        super().__init__(api_key="", rate_limit=30)  # 30 requests per minute
        self.rate_limiter.min_delay = 1.0  # 1 second minimum between calls
        self.cache = DataCache(ttl_minutes=240)  # 4 hour cache

        # Track recent errors for adaptive throttling
        self._error_count = 0
        self._last_error_time = 0
        self._cooldown_until = 0
        self._session_started = False  # Track if we've made any requests yet

    def _smart_throttle(self):
        """
        v7.0: Balanced throttling - fast but safe

        Features:
        - Initial 2s delay on first request
        - Base 1-1.5s delay between requests
        - Adaptive delay increase on errors
        - Cooldown after rate limit hits
        """
        current_time = time.time()

        # INITIAL DELAY: Wait 2s on first request
        if not self._session_started:
            self._session_started = True
            logger.info("🚀 Starting Yahoo Finance session...")
            time.sleep(2)
            return

        # If in cooldown period, wait
        if current_time < self._cooldown_until:
            wait_time = self._cooldown_until - current_time
            logger.info(f"⏳ Cooldown: waiting {wait_time:.1f}s")
            time.sleep(wait_time)

        # Base delay with jitter (1-1.5 seconds)
        base_delay = self.rate_limiter.min_delay
        jitter = random.uniform(1.0, 1.5)
        delay = base_delay * jitter

        # Increase delay if recent errors
        if self._error_count > 0:
            error_multiplier = min(self._error_count * 3, 10)  # Max 10x delay
            delay *= error_multiplier
            logger.debug(f"Error-based delay: {delay:.1f}s (errors: {self._error_count})")

        time.sleep(delay)

    def _handle_rate_limit_error(self, error_msg: str):
        """
        v6.10: Handle rate limit errors with cooldown
        """
        self._error_count += 1
        self._last_error_time = time.time()

        # Set cooldown period based on error count
        cooldown_seconds = min(30 * self._error_count, 300)  # Max 5 min cooldown
        self._cooldown_until = time.time() + cooldown_seconds

        logger.warning(f"⚠️ Rate limit hit (error #{self._error_count}). Cooldown: {cooldown_seconds}s")

        # Try to refresh yfinance session/crumb
        try:
            import yfinance.shared as yf_shared
            yf_shared._REQUESTS = None
            logger.info("Cleared yfinance session for refresh")
        except:
            pass

    def _record_success(self):
        """v6.10: Record successful request, decay error count"""
        if self._error_count > 0:
            self._error_count = max(0, self._error_count - 1)

    def get_price_data(self, symbol: str, period: str = "1y", interval: str = "1d",
                        data_type: str = 'price') -> pd.DataFrame:
        """
        Get historical price data from Yahoo Finance with robust rate limit handling (v6.10)

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            period: Time period ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
            interval: Data interval ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')
            data_type: Cache data type for TTL selection (default 'price', use 'sector_etf' for 5min TTL)

        Returns:
            DataFrame with OHLCV data
        """
        cache_key = f"{data_type}_{symbol}_{period}_{interval}"
        cached_data = self.cache.get(cache_key, data_type=data_type)
        if cached_data is not None:
            logger.debug(f"📦 Cache hit for {symbol}")
            return cached_data

        # v6.10: Retry logic with smart throttling and session refresh
        max_retries = 4
        for attempt in range(max_retries):
            try:
                # Smart throttle with adaptive delays
                self._smart_throttle()

                ticker = yf.Ticker(symbol)
                data = ticker.history(period=period, interval=interval)

                if data.empty:
                    raise APIError(f"No data found for symbol {symbol}")

                # Reset index to have date as column
                data = data.reset_index()

                # Standardize column names (after reset_index to handle 'Date' column)
                data.columns = data.columns.str.lower()

                # Add symbol column
                data['symbol'] = symbol

                # Ensure date column is datetime
                if 'date' in data.columns:
                    data['date'] = pd.to_datetime(data['date'])

                self.cache.set(cache_key, data, data_type=data_type)
                self._record_success()
                logger.debug(f"✅ Retrieved {len(data)} rows for {symbol}")

                return data

            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = any(x in error_str for x in ['rate', '429', '401', 'too many', 'unauthorized', 'crumb'])

                if is_rate_limit:
                    self._handle_rate_limit_error(str(e))

                    if attempt < max_retries - 1:
                        # Exponential backoff: 10s, 30s, 90s
                        wait_time = 10 * (3 ** attempt)
                        logger.warning(f"Rate limit on {symbol}, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue

                logger.error(f"Failed to get price data for {symbol}: {e}")
                raise APIError(f"Failed to get price data: {e}")

    def get_financial_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get financial statements data

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary containing financial data
        """
        cache_key = f"financial_{symbol}"
        cached_data = self.cache.get(cache_key, data_type='financial')
        if cached_data is not None:
            return cached_data

        try:
            ticker = yf.Ticker(symbol)

            # Get financial statements
            income_stmt = ticker.financials
            balance_sheet = ticker.balance_sheet
            cash_flow = ticker.cashflow

            # Get key metrics
            info = ticker.info

            financial_data = {
                'symbol': symbol,
                'last_updated': datetime.now().isoformat(),

                # Income Statement
                'revenue': self._get_latest_value(income_stmt, 'Total Revenue'),
                'gross_profit': self._get_latest_value(income_stmt, 'Gross Profit'),
                'operating_income': self._get_latest_value(income_stmt, 'Operating Income'),
                'net_income': self._get_latest_value(income_stmt, 'Net Income'),
                'ebitda': self._get_latest_value(income_stmt, 'EBITDA'),

                # Balance Sheet
                'total_assets': self._get_latest_value(balance_sheet, 'Total Assets'),
                'total_debt': self._get_latest_value(balance_sheet, 'Total Debt'),
                'shareholders_equity': self._get_latest_value(balance_sheet, 'Stockholders Equity'),
                'cash_and_equivalents': self._get_latest_value(balance_sheet, 'Cash And Cash Equivalents'),
                'current_assets': self._get_latest_value(balance_sheet, 'Current Assets'),
                'current_liabilities': self._get_latest_value(balance_sheet, 'Current Liabilities'),

                # Cash Flow
                'operating_cash_flow': self._get_latest_value(cash_flow, 'Operating Cash Flow'),
                'free_cash_flow': self._get_latest_value(cash_flow, 'Free Cash Flow'),
                'capital_expenditure': self._get_latest_value(cash_flow, 'Capital Expenditure'),

                # Key metrics from info
                'market_cap': info.get('marketCap'),
                'enterprise_value': info.get('enterpriseValue'),
                'shares_outstanding': info.get('sharesOutstanding'),
                'float_shares': info.get('floatShares'),
                'pe_ratio': info.get('trailingPE'),
                'forward_pe': info.get('forwardPE'),
                'peg_ratio': info.get('pegRatio'),
                'price_to_book': info.get('priceToBook'),
                'price_to_sales': info.get('priceToSalesTrailing12Months'),
                'dividend_yield': info.get('dividendYield'),
                'payout_ratio': info.get('payoutRatio'),
                'beta': info.get('beta'),
                'eps': info.get('trailingEps'),
                'forward_eps': info.get('forwardEps'),
                'book_value_per_share': info.get('bookValue'),
                'revenue_growth': info.get('revenueGrowth'),
                'earnings_growth': info.get('earningsGrowth'),
                'profit_margin': info.get('profitMargins'),
                'operating_margin': info.get('operatingMargins'),
                'gross_margin': info.get('grossMargins'),
                'return_on_equity': info.get('returnOnEquity'),
                'return_on_assets': info.get('returnOnAssets'),
                'debt_to_equity': info.get('debtToEquity'),
                'current_ratio': info.get('currentRatio'),
                'quick_ratio': info.get('quickRatio'),
                'interest_coverage': self._calculate_interest_coverage(income_stmt),

                # Industry data
                'sector': info.get('sector'),
                'industry': info.get('industry'),

                # Analyst Recommendations (NEW)
                'recommendation_key': info.get('recommendationKey'),
                'number_of_analyst_opinions': info.get('numberOfAnalystOpinions'),
                'target_mean_price': info.get('targetMeanPrice'),
                'target_high_price': info.get('targetHighPrice'),
                'target_low_price': info.get('targetLowPrice'),

                # Risk Assessment (NEW)
                'audit_risk': info.get('auditRisk'),
                'board_risk': info.get('boardRisk'),
                'compensation_risk': info.get('compensationRisk'),
                'shareholder_rights_risk': info.get('shareHolderRightsRisk'),
                'overall_risk': info.get('overallRisk'),

                # Trading & Price Levels (NEW)
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
                'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
                'fifty_day_average': info.get('fiftyDayAverage'),
                'two_hundred_day_average': info.get('twoHundredDayAverage'),

                # Ownership & Short Interest (NEW)
                'held_percent_insiders': info.get('heldPercentInsiders'),
                'held_percent_institutions': info.get('heldPercentInstitutions'),
                'shares_short': info.get('sharesShort'),
                'short_ratio': info.get('shortRatio'),
                'short_percent_of_float': info.get('shortPercentOfFloat'),

                # Enterprise Value Ratios (NEW)
                'enterprise_to_revenue': info.get('enterpriseToRevenue'),
                'enterprise_to_ebitda': info.get('enterpriseToEbitda'),
            }

            self.cache.set(cache_key, financial_data, data_type='financial')
            logger.info(f"Retrieved financial data for {symbol}")

            return financial_data

        except Exception as e:
            logger.error(f"Failed to get financial data for {symbol}: {e}")
            raise APIError(f"Failed to get financial data: {e}")

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get company information

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary containing company info
        """
        cache_key = f"company_{symbol}"
        cached_data = self.cache.get(cache_key, data_type='company')
        if cached_data is not None:
            return cached_data

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            company_data = {
                'symbol': symbol,
                'company_name': info.get('longName', info.get('shortName')),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'country': info.get('country'),
                'website': info.get('website'),
                'description': info.get('longBusinessSummary'),
                'employees': info.get('fullTimeEmployees'),
                'market_cap': info.get('marketCap'),
                'currency': info.get('currency'),
                'exchange': info.get('exchange'),
            }

            self.cache.set(cache_key, company_data, data_type='company')
            return company_data

        except Exception as e:
            logger.error(f"Failed to get company info for {symbol}: {e}")
            raise APIError(f"Failed to get company info: {e}")

    def get_real_time_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get real-time price data (NO CACHE - always fresh)

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary containing current price info
        """
        # NO CACHE for real-time data - always fetch fresh
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            price_data = {
                'symbol': symbol,
                'current_price': info.get('currentPrice', info.get('regularMarketPrice')),
                'previous_close': info.get('previousClose'),
                'open': info.get('open', info.get('regularMarketOpen')),
                'day_high': info.get('dayHigh', info.get('regularMarketDayHigh')),
                'day_low': info.get('dayLow', info.get('regularMarketDayLow')),
                'volume': info.get('volume', info.get('regularMarketVolume')),
                'average_volume': info.get('averageVolume'),
                'market_cap': info.get('marketCap'),
                'pe_ratio': info.get('trailingPE'),
                'change': info.get('regularMarketChange'),
                'change_percent': info.get('regularMarketChangePercent'),
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
                'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
                'timestamp': datetime.now().isoformat(),
            }

            # Do NOT cache realtime data
            return price_data

        except Exception as e:
            logger.error(f"Failed to get real-time price for {symbol}: {e}")
            raise APIError(f"Failed to get real-time price: {e}")

    def get_dividends(self, symbol: str) -> pd.DataFrame:
        """Get dividend history"""
        try:
            ticker = yf.Ticker(symbol)
            dividends = ticker.dividends

            if dividends.empty:
                return pd.DataFrame()

            df = dividends.reset_index()
            df.columns = ['date', 'dividend']
            df['symbol'] = symbol

            return df

        except Exception as e:
            logger.error(f"Failed to get dividends for {symbol}: {e}")
            return pd.DataFrame()

    def get_splits(self, symbol: str) -> pd.DataFrame:
        """Get stock split history"""
        try:
            ticker = yf.Ticker(symbol)
            splits = ticker.splits

            if splits.empty:
                return pd.DataFrame()

            df = splits.reset_index()
            df.columns = ['date', 'split_ratio']
            df['symbol'] = symbol

            return df

        except Exception as e:
            logger.error(f"Failed to get splits for {symbol}: {e}")
            return pd.DataFrame()

    def _get_latest_value(self, df: pd.DataFrame, column: str) -> Optional[float]:
        """Get the latest value from a financial statement DataFrame"""
        try:
            if column in df.index and not df.loc[column].empty:
                # Get the most recent value (first column)
                return float(df.loc[column].iloc[0])
        except (KeyError, IndexError, ValueError):
            pass
        return None

    def _calculate_interest_coverage(self, income_stmt: pd.DataFrame) -> Optional[float]:
        """Calculate interest coverage ratio"""
        try:
            ebit = self._get_latest_value(income_stmt, 'EBIT')
            interest_expense = self._get_latest_value(income_stmt, 'Interest Expense')

            if ebit and interest_expense and interest_expense != 0:
                return ebit / abs(interest_expense)
        except (TypeError, ZeroDivisionError):
            pass
        return None

    def is_market_open(self) -> Dict[str, Any]:
        """
        Check if US market is currently open and return market state

        Market states:
        - PRE: Pre-market (4:00-9:30 AM ET)
        - OPEN: Regular market hours (9:30 AM - 4:00 PM ET)
        - AFTER: After-hours (4:00-8:00 PM ET)
        - CLOSED: Market closed

        Returns:
            Dictionary with market_state and is_open boolean
        """
        import pytz
        from datetime import datetime

        try:
            # Get current time in US/Eastern
            eastern = pytz.timezone('US/Eastern')
            now = datetime.now(eastern)

            current_time = now.time()
            current_day = now.weekday()  # 0=Monday, 6=Sunday

            # Check if weekend
            if current_day >= 5:  # Saturday or Sunday
                return {
                    'market_state': 'CLOSED',
                    'is_open': False,
                    'reason': 'Weekend'
                }

            # Define market hours
            from datetime import time
            pre_market_start = time(4, 0)
            pre_market_end = time(9, 30)
            regular_open = time(9, 30)
            regular_close = time(16, 0)
            after_hours_close = time(20, 0)

            # Determine market state
            if pre_market_start <= current_time < pre_market_end:
                return {
                    'market_state': 'PRE',
                    'is_open': False,
                    'reason': 'Pre-market hours'
                }
            elif regular_open <= current_time < regular_close:
                return {
                    'market_state': 'OPEN',
                    'is_open': True,
                    'reason': 'Regular market hours'
                }
            elif regular_close <= current_time < after_hours_close:
                return {
                    'market_state': 'AFTER',
                    'is_open': False,
                    'reason': 'After-hours trading'
                }
            else:
                return {
                    'market_state': 'CLOSED',
                    'is_open': False,
                    'reason': 'Outside trading hours'
                }

        except Exception as e:
            logger.error(f"Failed to check market status: {e}")
            return {
                'market_state': 'UNKNOWN',
                'is_open': False,
                'reason': f'Error: {e}'
            }

    def get_intraday_data(self, symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
        """
        Get intraday price data

        Args:
            symbol: Stock symbol
            period: Time period (1d, 5d, 1mo, etc.)
            interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h)

        Returns:
            DataFrame with intraday OHLCV data
        """
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval=interval)

            if data.empty:
                logger.warning(f"No intraday data found for {symbol}")
                return pd.DataFrame()

            # Reset index and standardize columns
            data = data.reset_index()
            data.columns = data.columns.str.lower()

            logger.info(f"Retrieved {len(data)} rows of intraday data for {symbol} (interval={interval})")
            return data

        except Exception as e:
            logger.error(f"Failed to get intraday data for {symbol}: {e}")
            return pd.DataFrame()

    def get_average_volume(self, symbol: str, days: int = 20) -> float:
        """
        Get average daily volume over specified days

        Args:
            symbol: Stock symbol
            days: Number of days to average

        Returns:
            Average volume per 5-minute bar
        """
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=f"{days}d", interval="1d")

            if data.empty:
                return 0

            avg_daily_volume = data['Volume'].mean()

            # Convert to 5-minute bar average
            # Assuming 78 five-minute bars per day (6.5 hours * 12 bars/hour)
            avg_volume_5min = avg_daily_volume / 78 if avg_daily_volume > 0 else 0

            return avg_volume_5min

        except Exception as e:
            logger.error(f"Failed to get average volume for {symbol}: {e}")
            return 0

    def get_sector_top_companies(self, sector_key: str) -> pd.DataFrame:
        """
        Get top 50 companies for a yfinance sector (v5.2).

        Args:
            sector_key: yfinance sector key (e.g., 'technology', 'healthcare')

        Returns:
            DataFrame with columns: name, rating, market weight. Index: symbol.
            Empty DataFrame on failure.
        """
        cache_key = f"sector_companies_{sector_key}"
        cached = self.cache.get(cache_key, data_type='sector_companies')
        if cached is not None:
            return cached

        self._smart_throttle()

        try:
            sector = yf.Sector(sector_key)
            companies = sector.top_companies

            if companies is None or companies.empty:
                logger.warning(f"No companies found for sector '{sector_key}'")
                return pd.DataFrame()

            self.cache.set(cache_key, companies, data_type='sector_companies')
            self._record_success()
            logger.info(f"Retrieved {len(companies)} companies for sector '{sector_key}'")
            return companies

        except Exception as e:
            logger.error(f"Failed to get sector companies for '{sector_key}': {e}")
            return pd.DataFrame()

    def batch_download_prices(self, symbols: list, period: str = '5d',
                              interval: str = '1d',
                              data_type: str = 'sector_price') -> pd.DataFrame:
        """
        Batch download price data for multiple symbols in one yf.download() call (v5.2).

        Args:
            symbols: List of stock symbols
            period: Time period (default '5d')
            interval: Data interval (default '1d')
            data_type: Cache data_type key (default 'sector_price' for 20min TTL)

        Returns:
            DataFrame with MultiIndex columns (metric, symbol).
            Empty DataFrame on failure.
        """
        # Deterministic cache key from sorted first symbols + count
        key_symbols = '_'.join(sorted(symbols)[:5])
        cache_key = f"batch_{data_type}_{period}_{interval}_{key_symbols}_{len(symbols)}"
        cached = self.cache.get(cache_key, data_type=data_type)
        if cached is not None:
            logger.debug(f"Cache hit for batch download ({len(symbols)} symbols)")
            return cached

        self._smart_throttle()

        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                data = yf.download(symbols, period=period, interval=interval,
                                   progress=False, threads=True)

            if data.empty:
                logger.warning(f"Batch download returned empty ({len(symbols)} symbols)")
                return pd.DataFrame()

            self.cache.set(cache_key, data, data_type=data_type)
            self._record_success()
            logger.info(f"Batch downloaded {len(symbols)} symbols ({len(data)} rows)")
            return data

        except Exception as e:
            logger.error(f"Batch download failed: {e}")
            return pd.DataFrame()

    def get_premarket_data(self, symbol: str, interval: str = "5m") -> Dict[str, Any]:
        """
        Get pre-market data for gap analysis (4:00 AM - 9:30 AM ET)

        Args:
            symbol: Stock symbol
            interval: Data interval (default 5m)

        Returns:
            Dictionary containing:
            - has_premarket_data: Boolean
            - previous_close: Previous day's closing price
            - current_premarket_price: Latest pre-market price
            - premarket_high: Highest price in pre-market
            - premarket_low: Lowest price in pre-market
            - premarket_volume: Total pre-market volume
            - gap_percent: Gap % from previous close
            - gap_direction: 'up' or 'down'
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get intraday data (1 day with 5-minute intervals covers pre-market + regular hours)
            # IMPORTANT: prepost=True is required to get pre-market volume data
            data = ticker.history(period="1d", interval=interval, prepost=True)

            if data.empty:
                raise APIError(f"No data found for {symbol}")

            # Reset index and standardize columns
            data = data.reset_index()
            data.columns = data.columns.str.lower()

            # Convert datetime column to timezone-aware (US/Eastern)
            import pytz
            eastern = pytz.timezone('US/Eastern')

            # Handle both 'datetime' and 'date' column names
            datetime_col = 'datetime' if 'datetime' in data.columns else 'date'
            data[datetime_col] = pd.to_datetime(data[datetime_col])

            # Convert to Eastern time if timezone-aware
            if data[datetime_col].dt.tz is not None:
                data[datetime_col] = data[datetime_col].dt.tz_convert(eastern)
            else:
                data[datetime_col] = data[datetime_col].dt.tz_localize('UTC').dt.tz_convert(eastern)

            # Rename to datetime for consistency
            if datetime_col == 'date':
                data['datetime'] = data['date']

            # Get previous day's close
            # IMPORTANT: ticker.info['previousClose'] is often STALE (Yahoo Finance bug)
            # Use historical data instead for accurate previous close
            try:
                # Get last 5 trading days to find most recent close
                hist_data = ticker.history(period="5d", interval="1d", prepost=False)
                if not hist_data.empty and len(hist_data) >= 1:
                    # Get the most recent completed trading day close
                    # (last row in 5d data is the most recent close)
                    previous_close = float(hist_data['Close'].iloc[-1])
                    logger.debug(f"Got previous close from 5d history: ${previous_close:.2f}")
                else:
                    # Fallback to ticker.info if history fails
                    info = ticker.info
                    previous_close = info.get('previousClose', info.get('regularMarketPreviousClose'))
                    logger.warning(f"Using ticker.info previousClose (may be stale): ${previous_close}")
            except Exception as e:
                logger.warning(f"Failed to get history for previous close: {e}, falling back to ticker.info")
                info = ticker.info
                previous_close = info.get('previousClose', info.get('regularMarketPreviousClose'))

            # Final fallback: get from current data
            if previous_close is None or previous_close == 0:
                previous_day_data = data[data['datetime'].dt.hour < 4]
                if not previous_day_data.empty:
                    previous_close = previous_day_data['close'].iloc[-1]
                else:
                    previous_close = data['close'].iloc[0] if not data.empty else 0

            # Filter pre-market data (4:00 AM - 9:30 AM)
            premarket_data = data[
                ((data['datetime'].dt.hour >= 4) & (data['datetime'].dt.hour < 9)) |
                ((data['datetime'].dt.hour == 9) & (data['datetime'].dt.minute < 30))
            ]

            if premarket_data.empty:
                return {
                    'symbol': symbol,
                    'has_premarket_data': False,
                    'previous_close': previous_close,
                    'error': 'No pre-market data available'
                }

            # Calculate pre-market metrics
            current_premarket_price = premarket_data['close'].iloc[-1]
            premarket_high = premarket_data['high'].max()
            premarket_low = premarket_data['low'].min()
            premarket_volume = int(premarket_data['volume'].sum())

            # Calculate gap
            gap_amount = current_premarket_price - previous_close
            gap_percent = (gap_amount / previous_close * 100) if previous_close > 0 else 0
            gap_direction = 'up' if gap_amount > 0 else 'down'

            logger.info(f"Pre-market data for {symbol}: Gap {gap_percent:.2f}%, Volume {premarket_volume:,}")

            return {
                'symbol': symbol,
                'has_premarket_data': True,
                'premarket_bars': premarket_data,
                'previous_close': float(previous_close),
                'current_premarket_price': float(current_premarket_price),
                'premarket_high': float(premarket_high),
                'premarket_low': float(premarket_low),
                'premarket_volume': premarket_volume,
                'gap_amount': float(gap_amount),
                'gap_percent': float(gap_percent),
                'gap_direction': gap_direction,
            }

        except Exception as e:
            logger.error(f"Failed to get pre-market data for {symbol}: {e}")
            return {
                'symbol': symbol,
                'has_premarket_data': False,
                'error': str(e)
            }