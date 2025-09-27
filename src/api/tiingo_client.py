"""
Tiingo API Client
"""
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

from .base_client import BaseAPIClient, DataCache, APIError


class TiingoClient(BaseAPIClient):
    """Tiingo API client"""

    def __init__(self, api_key: str):
        super().__init__(api_key, rate_limit=500)  # 500 requests per hour
        self.base_url = "https://api.tiingo.com/tiingo"
        self.cache = DataCache(ttl_minutes=15)  # 15 minutes cache for price data

    def get_price_data(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Get historical price data from Tiingo

        Args:
            symbol: Stock symbol
            period: Time period
            interval: Data interval (daily, weekly, monthly)

        Returns:
            DataFrame with OHLCV data
        """
        cache_key = f"tiingo_price_{symbol}_{period}_{interval}"
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = self._get_start_date(period, end_date)

            # Choose endpoint based on interval
            if interval in ['1d', 'daily']:
                endpoint = f"{self.base_url}/daily/{symbol}/prices"
                params = {
                    'startDate': start_date.strftime('%Y-%m-%d'),
                    'endDate': end_date.strftime('%Y-%m-%d'),
                    'token': self.api_key
                }
            elif interval in ['1w', 'weekly']:
                endpoint = f"{self.base_url}/daily/{symbol}/prices"
                params = {
                    'startDate': start_date.strftime('%Y-%m-%d'),
                    'endDate': end_date.strftime('%Y-%m-%d'),
                    'resampleFreq': 'weekly',
                    'token': self.api_key
                }
            elif interval in ['1mo', 'monthly']:
                endpoint = f"{self.base_url}/daily/{symbol}/prices"
                params = {
                    'startDate': start_date.strftime('%Y-%m-%d'),
                    'endDate': end_date.strftime('%Y-%m-%d'),
                    'resampleFreq': 'monthly',
                    'token': self.api_key
                }
            else:
                raise APIError(f"Unsupported interval: {interval}")

            response = self._make_request(endpoint, params)

            if 'detail' in response:
                raise APIError(f"Tiingo error: {response['detail']}")

            if not response:
                raise APIError(f"No data found for symbol {symbol}")

            # Convert to DataFrame
            df = pd.DataFrame(response)

            if df.empty:
                raise APIError(f"No data found for symbol {symbol}")

            # Standardize columns
            df['date'] = pd.to_datetime(df['date'])
            df = df.rename(columns={
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume',
                'adjOpen': 'adj_open',
                'adjHigh': 'adj_high',
                'adjLow': 'adj_low',
                'adjClose': 'adj_close',
                'adjVolume': 'adj_volume'
            })

            # Ensure numeric types
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # Add symbol column
            df['symbol'] = symbol

            # Sort by date
            df = df.sort_values('date').reset_index(drop=True)

            self.cache.set(cache_key, df)
            logger.info(f"Retrieved {len(df)} rows of price data for {symbol} from Tiingo")

            return df

        except Exception as e:
            logger.error(f"Failed to get price data for {symbol}: {e}")
            raise APIError(f"Failed to get price data: {e}")

    def get_real_time_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get real-time price data from Tiingo

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary containing current price info
        """
        try:
            endpoint = f"{self.base_url}/daily/{symbol}/prices"
            params = {
                'token': self.api_key,
                'sort': 'date',
                'format': 'json'
            }

            response = self._make_request(endpoint, params)

            if 'detail' in response:
                raise APIError(f"Tiingo error: {response['detail']}")

            if not response:
                raise APIError(f"No price data found for {symbol}")

            # Get the most recent data point
            latest_data = response[-1] if isinstance(response, list) else response

            return {
                'symbol': symbol,
                'current_price': latest_data.get('close'),
                'previous_close': latest_data.get('prevClose'),
                'open': latest_data.get('open'),
                'day_high': latest_data.get('high'),
                'day_low': latest_data.get('low'),
                'volume': latest_data.get('volume'),
                'adj_close': latest_data.get('adjClose'),
                'change': latest_data.get('close', 0) - latest_data.get('prevClose', 0) if latest_data.get('close') and latest_data.get('prevClose') else None,
                'change_percent': ((latest_data.get('close', 0) - latest_data.get('prevClose', 0)) / latest_data.get('prevClose', 1) * 100) if latest_data.get('close') and latest_data.get('prevClose') else None,
                'timestamp': latest_data.get('date'),
            }

        except Exception as e:
            logger.error(f"Failed to get real-time price for {symbol}: {e}")
            raise APIError(f"Failed to get real-time price: {e}")

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get company information from Tiingo

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary containing company info
        """
        try:
            endpoint = f"{self.base_url}/daily/{symbol}"
            params = {'token': self.api_key}

            response = self._make_request(endpoint, params)

            if 'detail' in response:
                raise APIError(f"Tiingo error: {response['detail']}")

            return {
                'symbol': symbol,
                'company_name': response.get('name'),
                'description': response.get('description'),
                'exchange': response.get('exchangeCode'),
                'start_date': response.get('startDate'),
                'end_date': response.get('endDate'),
                'ticker': response.get('ticker'),
            }

        except Exception as e:
            logger.error(f"Failed to get company info for {symbol}: {e}")
            raise APIError(f"Failed to get company info: {e}")

    def get_intraday_data(self, symbol: str, interval: str = "5min") -> pd.DataFrame:
        """
        Get intraday price data from Tiingo

        Args:
            symbol: Stock symbol
            interval: Intraday interval (1min, 5min, 15min, 30min, 1hour)

        Returns:
            DataFrame with intraday OHLCV data
        """
        cache_key = f"tiingo_intraday_{symbol}_{interval}"
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            # Map interval to Tiingo format
            interval_mapping = {
                '1m': '1min',
                '5m': '5min',
                '15m': '15min',
                '30m': '30min',
                '1h': '1hour'
            }

            tiingo_interval = interval_mapping.get(interval, interval)

            endpoint = f"{self.base_url}/iex/{symbol}/prices"
            params = {
                'resampleFreq': tiingo_interval,
                'token': self.api_key
            }

            response = self._make_request(endpoint, params)

            if 'detail' in response:
                raise APIError(f"Tiingo error: {response['detail']}")

            if not response:
                raise APIError(f"No intraday data found for symbol {symbol}")

            # Convert to DataFrame
            df = pd.DataFrame(response)

            if df.empty:
                return df

            # Standardize columns
            df['date'] = pd.to_datetime(df['date'])
            df = df.rename(columns={
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume'
            })

            # Ensure numeric types
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # Add symbol column
            df['symbol'] = symbol

            # Sort by date
            df = df.sort_values('date').reset_index(drop=True)

            self.cache.set(cache_key, df)
            logger.info(f"Retrieved {len(df)} rows of intraday data for {symbol} from Tiingo")

            return df

        except Exception as e:
            logger.error(f"Failed to get intraday data for {symbol}: {e}")
            raise APIError(f"Failed to get intraday data: {e}")

    def get_crypto_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """
        Get cryptocurrency data from Tiingo

        Args:
            symbol: Crypto symbol (e.g., 'btcusd')
            period: Time period

        Returns:
            DataFrame with crypto OHLCV data
        """
        cache_key = f"tiingo_crypto_{symbol}_{period}"
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = self._get_start_date(period, end_date)

            endpoint = f"https://api.tiingo.com/tiingo/crypto/prices"
            params = {
                'tickers': symbol,
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'token': self.api_key
            }

            response = self._make_request(endpoint, params)

            if 'detail' in response:
                raise APIError(f"Tiingo error: {response['detail']}")

            if not response:
                raise APIError(f"No crypto data found for symbol {symbol}")

            # Extract price data from nested structure
            price_data = []
            for item in response:
                if 'priceData' in item:
                    for price in item['priceData']:
                        price['ticker'] = item.get('ticker', symbol)
                        price_data.append(price)

            if not price_data:
                raise APIError(f"No price data found for symbol {symbol}")

            # Convert to DataFrame
            df = pd.DataFrame(price_data)

            # Standardize columns
            df['date'] = pd.to_datetime(df['date'])
            df = df.rename(columns={'ticker': 'symbol'})

            # Ensure numeric types
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # Sort by date
            df = df.sort_values('date').reset_index(drop=True)

            self.cache.set(cache_key, df)
            logger.info(f"Retrieved {len(df)} rows of crypto data for {symbol} from Tiingo")

            return df

        except Exception as e:
            logger.error(f"Failed to get crypto data for {symbol}: {e}")
            raise APIError(f"Failed to get crypto data: {e}")

    def get_financial_data(self, symbol: str) -> Dict[str, Any]:
        """
        Tiingo doesn't provide fundamental data, return empty dict

        Args:
            symbol: Stock symbol

        Returns:
            Empty dictionary
        """
        logger.warning(f"Tiingo doesn't provide fundamental data for {symbol}")
        return {
            'symbol': symbol,
            'last_updated': datetime.now().isoformat(),
            'note': 'Tiingo API does not provide fundamental financial data'
        }

    def get_dividends(self, symbol: str) -> pd.DataFrame:
        """
        Tiingo doesn't provide dividend data, return empty DataFrame

        Args:
            symbol: Stock symbol

        Returns:
            Empty DataFrame
        """
        logger.warning(f"Tiingo doesn't provide dividend data for {symbol}")
        return pd.DataFrame()

    def get_splits(self, symbol: str) -> pd.DataFrame:
        """
        Tiingo doesn't provide split data, return empty DataFrame

        Args:
            symbol: Stock symbol

        Returns:
            Empty DataFrame
        """
        logger.warning(f"Tiingo doesn't provide split data for {symbol}")
        return pd.DataFrame()

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