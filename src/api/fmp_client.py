"""
Financial Modeling Prep API Client
"""
import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from loguru import logger

from .base_client import BaseAPIClient, DataCache, APIError


class FMPClient(BaseAPIClient):
    """Financial Modeling Prep API client"""

    def __init__(self, api_key: str):
        super().__init__(api_key, rate_limit=300)  # 300 calls per day free tier
        self.base_url = "https://financialmodelingprep.com/api/v3"
        self.cache = DataCache(ttl_minutes=60)  # 1 hour cache

    def get_price_data(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Get historical price data from FMP

        Args:
            symbol: Stock symbol
            period: Time period
            interval: Data interval (1d, 1h, 5m, etc.)

        Returns:
            DataFrame with OHLCV data
        """
        cache_key = f"fmp_price_{symbol}_{period}_{interval}"
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            # Map period to date range
            end_date = datetime.now()
            start_date = self._get_start_date(period, end_date)

            # Choose endpoint based on interval
            if interval in ['1m', '5m', '15m', '30m', '1h']:
                endpoint = f"{self.base_url}/historical-chart/{interval}/{symbol}"
                params = {
                    'from': start_date.strftime('%Y-%m-%d'),
                    'to': end_date.strftime('%Y-%m-%d'),
                    'apikey': self.api_key
                }
            else:
                endpoint = f"{self.base_url}/historical-price-full/{symbol}"
                params = {
                    'from': start_date.strftime('%Y-%m-%d'),
                    'to': end_date.strftime('%Y-%m-%d'),
                    'apikey': self.api_key
                }

            response = self._make_request(endpoint, params)

            if 'Error Message' in response:
                raise APIError(f"FMP error: {response['Error Message']}")

            # Extract data based on endpoint
            if interval in ['1m', '5m', '15m', '30m', '1h']:
                data = response
            else:
                if 'historical' not in response:
                    raise APIError("No historical data found")
                data = response['historical']

            if not data:
                raise APIError(f"No data found for symbol {symbol}")

            # Convert to DataFrame
            df = pd.DataFrame(data)

            # Standardize columns and data types
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            elif 'datetime' in df.columns:
                df['date'] = pd.to_datetime(df['datetime'])
                df = df.drop('datetime', axis=1)

            # Ensure standard column names
            column_mapping = {
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume'
            }

            for old_col, new_col in column_mapping.items():
                if old_col in df.columns:
                    df[new_col] = pd.to_numeric(df[old_col], errors='coerce')

            # Add symbol column
            df['symbol'] = symbol

            # Sort by date
            df = df.sort_values('date').reset_index(drop=True)

            self.cache.set(cache_key, df)
            logger.info(f"Retrieved {len(df)} rows of price data for {symbol} from FMP")

            return df

        except Exception as e:
            logger.error(f"Failed to get price data for {symbol}: {e}")
            raise APIError(f"Failed to get price data: {e}")

    def get_financial_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get comprehensive financial data from FMP

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary containing financial data
        """
        cache_key = f"fmp_financial_{symbol}"
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            # Get key metrics
            key_metrics = self._get_key_metrics(symbol)

            # Get financial ratios
            ratios = self._get_financial_ratios(symbol)

            # Get income statement
            income_stmt = self._get_income_statement(symbol)

            # Get balance sheet
            balance_sheet = self._get_balance_sheet(symbol)

            # Get cash flow
            cash_flow = self._get_cash_flow(symbol)

            # Get company profile
            profile = self._get_company_profile(symbol)

            # Combine all data
            financial_data = {
                'symbol': symbol,
                'last_updated': datetime.now().isoformat(),

                # From key metrics
                **key_metrics,

                # From ratios
                **ratios,

                # From income statement
                **income_stmt,

                # From balance sheet
                **balance_sheet,

                # From cash flow
                **cash_flow,

                # From profile
                **profile,
            }

            self.cache.set(cache_key, financial_data)
            logger.info(f"Retrieved financial data for {symbol} from FMP")

            return financial_data

        except Exception as e:
            logger.error(f"Failed to get financial data for {symbol}: {e}")
            raise APIError(f"Failed to get financial data: {e}")

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get company information from FMP

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary containing company info
        """
        try:
            profile = self._get_company_profile(symbol)

            return {
                'symbol': symbol,
                'company_name': profile.get('companyName'),
                'sector': profile.get('sector'),
                'industry': profile.get('industry'),
                'country': profile.get('country'),
                'website': profile.get('website'),
                'description': profile.get('description'),
                'employees': profile.get('fullTimeEmployees'),
                'market_cap': profile.get('mktCap'),
                'currency': profile.get('currency'),
                'exchange': profile.get('exchangeShortName'),
            }

        except Exception as e:
            logger.error(f"Failed to get company info for {symbol}: {e}")
            raise APIError(f"Failed to get company info: {e}")

    def get_real_time_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get real-time price data from FMP

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary containing current price info
        """
        try:
            endpoint = f"{self.base_url}/quote/{symbol}"
            params = {'apikey': self.api_key}

            response = self._make_request(endpoint, params)

            if not response:
                raise APIError(f"No price data found for {symbol}")

            data = response[0] if isinstance(response, list) else response

            return {
                'symbol': symbol,
                'current_price': data.get('price'),
                'previous_close': data.get('previousClose'),
                'open': data.get('open'),
                'day_high': data.get('dayHigh'),
                'day_low': data.get('dayLow'),
                'volume': data.get('volume'),
                'average_volume': data.get('avgVolume'),
                'market_cap': data.get('marketCap'),
                'pe_ratio': data.get('pe'),
                'change': data.get('change'),
                'change_percent': data.get('changesPercentage'),
                'timestamp': datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get real-time price for {symbol}: {e}")
            raise APIError(f"Failed to get real-time price: {e}")

    def get_dividends(self, symbol: str) -> pd.DataFrame:
        """Get dividend history from FMP"""
        try:
            endpoint = f"{self.base_url}/historical-price-full/stock_dividend/{symbol}"
            params = {'apikey': self.api_key}

            response = self._make_request(endpoint, params)

            if 'historical' not in response or not response['historical']:
                return pd.DataFrame()

            df = pd.DataFrame(response['historical'])
            df['date'] = pd.to_datetime(df['date'])
            df = df.rename(columns={'dividend': 'dividend'})
            df['symbol'] = symbol

            return df[['date', 'dividend', 'symbol']].sort_values('date')

        except Exception as e:
            logger.error(f"Failed to get dividends for {symbol}: {e}")
            return pd.DataFrame()

    def get_splits(self, symbol: str) -> pd.DataFrame:
        """Get stock split history from FMP"""
        try:
            endpoint = f"{self.base_url}/historical-price-full/stock_split/{symbol}"
            params = {'apikey': self.api_key}

            response = self._make_request(endpoint, params)

            if 'historical' not in response or not response['historical']:
                return pd.DataFrame()

            df = pd.DataFrame(response['historical'])
            df['date'] = pd.to_datetime(df['date'])
            df = df.rename(columns={'numerator': 'split_numerator', 'denominator': 'split_denominator'})
            df['split_ratio'] = df['split_numerator'] / df['split_denominator']
            df['symbol'] = symbol

            return df[['date', 'split_ratio', 'symbol']].sort_values('date')

        except Exception as e:
            logger.error(f"Failed to get splits for {symbol}: {e}")
            return pd.DataFrame()

    def _get_key_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get key metrics from FMP"""
        endpoint = f"{self.base_url}/key-metrics/{symbol}"
        params = {'apikey': self.api_key, 'limit': 1}

        response = self._make_request(endpoint, params)

        if not response:
            return {}

        data = response[0] if isinstance(response, list) else response

        return {
            'market_cap': data.get('marketCap'),
            'enterprise_value': data.get('enterpriseValue'),
            'pe_ratio': data.get('peRatio'),
            'peg_ratio': data.get('pegRatio'),
            'price_to_book': data.get('priceToBookRatio'),
            'price_to_sales': data.get('priceToSalesRatio'),
            'enterprise_value_multiple': data.get('enterpriseValueMultiple'),
            'price_to_free_cash_flows': data.get('priceToFreeCashFlowsRatio'),
        }

    def _get_financial_ratios(self, symbol: str) -> Dict[str, Any]:
        """Get financial ratios from FMP"""
        endpoint = f"{self.base_url}/ratios/{symbol}"
        params = {'apikey': self.api_key, 'limit': 1}

        response = self._make_request(endpoint, params)

        if not response:
            return {}

        data = response[0] if isinstance(response, list) else response

        return {
            'current_ratio': data.get('currentRatio'),
            'quick_ratio': data.get('quickRatio'),
            'debt_to_equity': data.get('debtEquityRatio'),
            'return_on_equity': data.get('returnOnEquity'),
            'return_on_assets': data.get('returnOnAssets'),
            'profit_margin': data.get('netProfitMargin'),
            'operating_margin': data.get('operatingProfitMargin'),
            'dividend_yield': data.get('dividendYield'),
            'payout_ratio': data.get('payoutRatio'),
        }

    def _get_income_statement(self, symbol: str) -> Dict[str, Any]:
        """Get income statement data from FMP"""
        endpoint = f"{self.base_url}/income-statement/{symbol}"
        params = {'apikey': self.api_key, 'limit': 1}

        response = self._make_request(endpoint, params)

        if not response:
            return {}

        data = response[0] if isinstance(response, list) else response

        return {
            'revenue': data.get('revenue'),
            'gross_profit': data.get('grossProfit'),
            'operating_income': data.get('operatingIncome'),
            'net_income': data.get('netIncome'),
            'ebitda': data.get('ebitda'),
            'eps': data.get('eps'),
        }

    def _get_balance_sheet(self, symbol: str) -> Dict[str, Any]:
        """Get balance sheet data from FMP"""
        endpoint = f"{self.base_url}/balance-sheet-statement/{symbol}"
        params = {'apikey': self.api_key, 'limit': 1}

        response = self._make_request(endpoint, params)

        if not response:
            return {}

        data = response[0] if isinstance(response, list) else response

        return {
            'total_assets': data.get('totalAssets'),
            'total_debt': data.get('totalDebt'),
            'shareholders_equity': data.get('totalStockholdersEquity'),
            'cash_and_equivalents': data.get('cashAndCashEquivalents'),
            'current_assets': data.get('totalCurrentAssets'),
            'current_liabilities': data.get('totalCurrentLiabilities'),
        }

    def _get_cash_flow(self, symbol: str) -> Dict[str, Any]:
        """Get cash flow data from FMP"""
        endpoint = f"{self.base_url}/cash-flow-statement/{symbol}"
        params = {'apikey': self.api_key, 'limit': 1}

        response = self._make_request(endpoint, params)

        if not response:
            return {}

        data = response[0] if isinstance(response, list) else response

        return {
            'operating_cash_flow': data.get('netCashProvidedByOperatingActivities'),
            'free_cash_flow': data.get('freeCashFlow'),
            'capital_expenditure': data.get('capitalExpenditure'),
        }

    def _get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Get company profile from FMP"""
        endpoint = f"{self.base_url}/profile/{symbol}"
        params = {'apikey': self.api_key}

        response = self._make_request(endpoint, params)

        if not response:
            return {}

        data = response[0] if isinstance(response, list) else response

        return {
            'companyName': data.get('companyName'),
            'sector': data.get('sector'),
            'industry': data.get('industry'),
            'country': data.get('country'),
            'website': data.get('website'),
            'description': data.get('description'),
            'fullTimeEmployees': data.get('fullTimeEmployees'),
            'mktCap': data.get('mktCap'),
            'currency': data.get('currency'),
            'exchangeShortName': data.get('exchangeShortName'),
            'beta': data.get('beta'),
        }

    def _get_start_date(self, period: str, end_date: datetime) -> datetime:
        """Convert period string to start date"""
        period_mapping = {
            '1d': timedelta(days=1),
            '5d': timedelta(days=5),
            '1mo': timedelta(days=30),
            '3mo': timedelta(days=90),
            '6mo': timedelta(days=180),
            '1y': timedelta(days=365),
            '2y': timedelta(days=730),
            '5y': timedelta(days=1825),
            '10y': timedelta(days=3650),
            'ytd': timedelta(days=(end_date - datetime(end_date.year, 1, 1)).days),
            'max': timedelta(days=7300),  # 20 years
        }

        delta = period_mapping.get(period, timedelta(days=365))
        return end_date - delta