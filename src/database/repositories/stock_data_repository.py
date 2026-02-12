"""Stock Data Repository"""

from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple
import pandas as pd

from ..manager import get_db_manager
from ..models.stock_price import StockPrice
from loguru import logger


class StockDataRepository:
    """
    Repository for stock price data access.
    
    Provides clean API for querying price data with caching and optimization.
    """
    
    def __init__(self):
        self.db = get_db_manager('stocks')
        self._cache = {}
    
    def get_latest_price(self, symbol: str) -> Optional[StockPrice]:
        """
        Get most recent price for symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            StockPrice object or None
        """
        row = self.db.fetch_one(
            "SELECT * FROM stock_prices WHERE symbol = ? ORDER BY date DESC LIMIT 1",
            (symbol,)
        )
        
        if row:
            return StockPrice.from_row(dict(row))
        return None
    
    def get_price_on_date(self, symbol: str, target_date: date) -> Optional[StockPrice]:
        """
        Get price for specific date.
        
        Args:
            symbol: Stock symbol
            target_date: Target date
            
        Returns:
            StockPrice object or None
        """
        row = self.db.fetch_one(
            "SELECT * FROM stock_prices WHERE symbol = ? AND date = ?",
            (symbol, target_date.isoformat())
        )
        
        if row:
            return StockPrice.from_row(dict(row))
        return None
    
    def get_prices(
        self,
        symbol: str,
        days: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 1000
    ) -> List[StockPrice]:
        """
        Get price history for symbol.
        
        Args:
            symbol: Stock symbol
            days: Number of days to look back (if provided)
            start_date: Start date (if provided)
            end_date: End date (if provided)
            limit: Maximum number of records
            
        Returns:
            List of StockPrice objects (newest first)
        """
        query = "SELECT * FROM stock_prices WHERE symbol = ?"
        params = [symbol]
        
        if days:
            cutoff = (date.today() - timedelta(days=days)).isoformat()
            query += " AND date >= ?"
            params.append(cutoff)
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())
        
        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        
        rows = self.db.fetch_all(query, tuple(params))
        
        return [StockPrice.from_row(dict(row)) for row in rows]
    
    def get_prices_dataframe(
        self,
        symbol: str,
        days: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Optional[pd.DataFrame]:
        """
        Get price history as pandas DataFrame.
        
        Args:
            symbol: Stock symbol
            days: Number of days to look back
            start_date: Start date
            end_date: End date
            
        Returns:
            DataFrame with OHLCV data, or None if no data
        """
        prices = self.get_prices(symbol, days, start_date, end_date, limit=5000)
        
        if not prices:
            return None
        
        # Convert to DataFrame
        data = [p.to_dict() for p in prices]
        df = pd.DataFrame(data)
        
        # Convert date to datetime and set as index
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df.set_index('date', inplace=True)
        
        return df
    
    def bulk_get_latest_prices(self, symbols: List[str]) -> dict:
        """
        Get latest prices for multiple symbols (optimized).
        
        Args:
            symbols: List of stock symbols
            
        Returns:
            Dict mapping symbol -> StockPrice
        """
        if not symbols:
            return {}
        
        # Build query with IN clause
        placeholders = ','.join('?' * len(symbols))
        query = f"""
            SELECT sp.*
            FROM stock_prices sp
            INNER JOIN (
                SELECT symbol, MAX(date) as max_date
                FROM stock_prices
                WHERE symbol IN ({placeholders})
                GROUP BY symbol
            ) latest ON sp.symbol = latest.symbol AND sp.date = latest.max_date
        """
        
        rows = self.db.fetch_all(query, tuple(symbols))
        
        result = {}
        for row in rows:
            price = StockPrice.from_row(dict(row))
            result[price.symbol] = price
        
        return result
    
    def get_symbols_list(self) -> List[str]:
        """
        Get list of all symbols in database.
        
        Returns:
            List of unique symbols
        """
        rows = self.db.fetch_all("SELECT DISTINCT symbol FROM stock_prices ORDER BY symbol")
        return [row['symbol'] for row in rows]
    
    def get_symbols_count(self) -> int:
        """
        Get total number of unique symbols.
        
        Returns:
            Symbol count
        """
        row = self.db.fetch_one("SELECT COUNT(DISTINCT symbol) as count FROM stock_prices")
        return row['count'] if row else 0
    
    def get_price_count(self, symbol: Optional[str] = None) -> int:
        """
        Get total number of price records.
        
        Args:
            symbol: Specific symbol, or None for all symbols
            
        Returns:
            Price record count
        """
        if symbol:
            row = self.db.fetch_one(
                "SELECT COUNT(*) as count FROM stock_prices WHERE symbol = ?",
                (symbol,)
            )
        else:
            row = self.db.fetch_one("SELECT COUNT(*) as count FROM stock_prices")
        
        return row['count'] if row else 0
    
    def get_date_range(self, symbol: str) -> Optional[Tuple[date, date]]:
        """
        Get date range for symbol's price data.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            (min_date, max_date) or None
        """
        row = self.db.fetch_one(
            "SELECT MIN(date) as min_date, MAX(date) as max_date FROM stock_prices WHERE symbol = ?",
            (symbol,)
        )
        
        if row and row['min_date'] and row['max_date']:
            return (
                date.fromisoformat(row['min_date']),
                date.fromisoformat(row['max_date'])
            )
        
        return None
    
    def create_or_update(self, price: StockPrice) -> bool:
        """
        Create or update price record.
        
        Args:
            price: StockPrice object
            
        Returns:
            True if successful
        """
        # Validate
        price.validate()
        
        # Check if exists
        existing = self.get_price_on_date(price.symbol, price.date)
        
        if existing:
            # Update
            self.db.execute(
                """
                UPDATE stock_prices SET
                    open = ?, high = ?, low = ?, close = ?, volume = ?,
                    adj_close = ?, sma_20 = ?, sma_50 = ?, sma_200 = ?,
                    rsi = ?, atr = ?, updated_at = ?
                WHERE symbol = ? AND date = ?
                """,
                (
                    price.open, price.high, price.low, price.close, price.volume,
                    price.adj_close, price.sma_20, price.sma_50, price.sma_200,
                    price.rsi, price.atr, datetime.now().isoformat(),
                    price.symbol, price.date.isoformat()
                )
            )
        else:
            # Insert
            self.db.execute(
                """
                INSERT INTO stock_prices (
                    symbol, date, open, high, low, close, volume,
                    adj_close, sma_20, sma_50, sma_200, rsi, atr,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    price.symbol, price.date.isoformat(),
                    price.open, price.high, price.low, price.close, price.volume,
                    price.adj_close, price.sma_20, price.sma_50, price.sma_200,
                    price.rsi, price.atr,
                    datetime.now().isoformat(), datetime.now().isoformat()
                )
            )
        
        return True
    
    def bulk_create_or_update(self, prices: List[StockPrice]) -> int:
        """
        Bulk create or update price records.
        
        Args:
            prices: List of StockPrice objects
            
        Returns:
            Number of records processed
        """
        count = 0
        
        for price in prices:
            try:
                self.create_or_update(price)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to save price for {price.symbol} on {price.date}: {e}")
        
        return count
    
    def delete_old_prices(self, days: int = 365) -> int:
        """
        Delete price records older than N days.
        
        Args:
            days: Retention period in days
            
        Returns:
            Number of records deleted
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        
        cursor = self.db.execute(
            "DELETE FROM stock_prices WHERE date < ?",
            (cutoff,)
        )
        
        return cursor.rowcount
    
    def vacuum_database(self) -> bool:
        """
        Vacuum database to reclaim space.
        
        Returns:
            True if successful
        """
        try:
            self.db.execute("VACUUM", commit=True)
            logger.info("Database vacuumed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to vacuum database: {e}")
            return False
