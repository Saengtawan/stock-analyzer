"""
Yahoo Finance API Client
"""
import yfinance as yf
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

from .base_client import BaseAPIClient, DataCache, APIError


class YahooFinanceClient(BaseAPIClient):
    """Yahoo Finance data client"""

    def __init__(self):
        # Yahoo Finance doesn't require API key
        super().__init__(api_key="", rate_limit=120)  # 2 requests per second
        self.cache = DataCache(ttl_minutes=5)  # Short cache for real-time data

    def get_price_data(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Get historical price data from Yahoo Finance

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            period: Time period ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
            interval: Data interval ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')

        Returns:
            DataFrame with OHLCV data
        """
        cache_key = f"price_{symbol}_{period}_{interval}"
        cached_data = self.cache.get(cache_key, data_type='price')
        if cached_data is not None:
            return cached_data

        try:
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

            self.cache.set(cache_key, data, data_type='price')
            logger.info(f"Retrieved {len(data)} rows of price data for {symbol}")

            return data

        except Exception as e:
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