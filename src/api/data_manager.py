"""
Data Manager - Coordinates multiple data sources
"""
import os
import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from .yahoo_finance_client import YahooFinanceClient
from .fmp_client import FMPClient
from .tiingo_client import TiingoClient
from .base_client import APIError, DataCache


class DataManager:
    """
    Manages data from multiple sources with fallback capabilities
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.cache = DataCache(ttl_minutes=60)

        # Initialize clients
        self.yahoo_client = YahooFinanceClient()

        # FMP client (optional, requires API key)
        # DISABLED: Quota too low (250/day), replaced by Tiingo (1000/hr)
        fmp_key = os.getenv('FMP_API_KEY')
        self.fmp_client = None
        # if fmp_key:
        #     self.fmp_client = FMPClient(fmp_key)

        # Tiingo client (optional, requires API key)
        tiingo_key = os.getenv('TIINGO_API_KEY')
        self.tiingo_client = None
        if tiingo_key:
            self.tiingo_client = TiingoClient(tiingo_key)

        # Set primary and backup sources
        # v6.10: Use Tiingo as primary to avoid Yahoo rate limits (1000 req/hr vs Yahoo's rate limit issues)
        self.primary_source = self.config.get('primary_source', 'tiingo' if self.tiingo_client else 'yahoo')
        self.backup_source = self.config.get('backup_source', 'yahoo')  # Yahoo as backup
        self.price_backup = self.config.get('price_backup', 'fmp')  # FMP as last resort only

        logger.info(f"DataManager initialized with primary: {self.primary_source}, backup: {self.backup_source}, price_backup: {self.price_backup}")

    def get_price_data(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Get price data with fallback to backup source

        Args:
            symbol: Stock symbol
            period: Time period
            interval: Data interval

        Returns:
            DataFrame with price data
        """
        # Try primary source first
        try:
            if self.primary_source == 'yahoo':
                return self.yahoo_client.get_price_data(symbol, period, interval)
            elif self.primary_source == 'fmp' and self.fmp_client:
                return self.fmp_client.get_price_data(symbol, period, interval)
            elif self.primary_source == 'tiingo' and self.tiingo_client:
                return self.tiingo_client.get_price_data(symbol, period, interval)
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source}) failed for {symbol}: {e}")

        # Try backup source
        try:
            if self.backup_source == 'yahoo' and self.primary_source != 'yahoo':
                return self.yahoo_client.get_price_data(symbol, period, interval)
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