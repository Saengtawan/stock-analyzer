#!/usr/bin/env python3
"""
DATA MANAGER - จัดการข้อมูลทั้งหมดอย่างเป็นระบบ

โครงสร้างข้อมูล:
1. SQLite: Raw data (prices, volume) - สำหรับ historical queries
2. Numpy Arrays: Pre-calculated features - สำหรับ fast analysis
3. JSON: Config, metadata, reference data
4. Cache: In-memory cache สำหรับข้อมูลที่ใช้บ่อย

Free API Sources:
1. yfinance - Stock prices, fundamentals (FREE, no key)
2. Alpha Vantage - News, economic data (FREE with key, 5 calls/min)
3. FRED - Economic indicators (FREE with key)
4. Finnhub - News, sentiment (FREE with key)
5. Quandl - Economic data (FREE with key)
"""

import os
import json
import sqlite3
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from functools import lru_cache
import hashlib
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

# Database layer integration
from database import StockDataRepository


class DataManager:
    """
    Centralized data management system

    Structure:
    data/
    ├── database/
    │   ├── stocks.db          # SQLite: raw prices, volume
    │   ├── features.pkl       # Pickle: pre-calculated features
    │   └── cache.json         # JSON: cached computations
    ├── features/
    │   ├── price_matrix.npy   # Numpy: price matrix [symbols x dates]
    │   ├── volume_matrix.npy  # Numpy: volume matrix
    │   ├── returns_matrix.npy # Numpy: returns matrix
    │   └── indicators.npz     # Numpy: technical indicators
    ├── reference/
    │   ├── symbols.json       # JSON: symbol list by sector
    │   ├── config.json        # JSON: system configuration
    │   └── events.json        # JSON: calendar events
    └── predictions/
        └── sector_prediction.json  # JSON: current predictions
    """

    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.join(
            os.path.dirname(__file__), '..', 'data'
        )

        # Create directory structure
        self.dirs = {
            'database': os.path.join(self.base_dir, 'database'),
            'features': os.path.join(self.base_dir, 'features'),
            'reference': os.path.join(self.base_dir, 'reference'),
            'predictions': os.path.join(self.base_dir, 'predictions'),
            'cache': os.path.join(self.base_dir, 'cache'),
        }

        for dir_path in self.dirs.values():
            os.makedirs(dir_path, exist_ok=True)

        # Database path
        self.db_path = os.path.join(self.dirs['database'], 'stocks.db')

        # Phase 3: Initialize database layer
        self.use_db_layer = True  # Always use database layer
        if self.use_db_layer:
            try:
                self.stock_repo = StockDataRepository()
            except Exception:
                self.use_db_layer = False
                self.stock_repo = None
        else:
            self.stock_repo = None

        # In-memory cache
        self._cache = {}
        self._cache_expiry = {}

    # ==================== SQLite Methods ====================

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        return sqlite3.connect(self.db_path)

    def get_prices(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """Get price data for a symbol (Phase 3: uses StockDataRepository)"""
        cache_key = f"prices_{symbol}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Phase 3: Use StockDataRepository if available
        if self.use_db_layer and self.stock_repo:
            try:
                # Calculate days for repository query
                if start_date:
                    start_dt = pd.to_datetime(start_date)
                    days = (datetime.now() - start_dt).days + 10  # Add buffer
                else:
                    days = 365  # Default to 1 year

                df = self.stock_repo.get_prices_dataframe(
                    symbol=symbol,
                    days=days
                )

                # Apply date filters if needed
                if start_date:
                    df = df[df.index >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df.index <= pd.to_datetime(end_date)]

                self._cache[cache_key] = df
                return df

            except Exception:
                # Fall through to SQLite fallback
                pass

        # Fallback: Direct SQLite access
        conn = self.get_connection()
        query = "SELECT date, open, high, low, close, volume FROM stock_prices WHERE symbol = ?"
        params = [symbol]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date"

        df = pd.read_sql(query, conn, params=params)
        conn.close()

        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)

        self._cache[cache_key] = df
        return df

    def get_sector_symbols(self, sector: str) -> List[str]:
        """Get all symbols in a sector (Phase 3: uses StockDataRepository)"""
        # Phase 3: Use StockDataRepository if available
        if self.use_db_layer and self.stock_repo:
            try:
                # Get all symbols and filter by sector
                # Note: Repository doesn't have sector filter yet, so we do it manually
                # This is still better than direct SQL for consistency
                all_symbols = self.stock_repo.get_symbols_list()

                # Filter by sector using metadata query
                # For now, fall back to direct SQL for sector queries
                # (Can be improved with a get_symbols_by_sector method in repository)
                pass  # Fall through to SQLite
            except Exception:
                pass  # Fall through to SQLite

        # Fallback: Direct SQLite access (sector queries need specialized method)
        conn = self.get_connection()
        cursor = conn.execute(
            "SELECT DISTINCT symbol FROM stock_prices WHERE sector = ?",
            (sector,)
        )
        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()
        return symbols

    def get_all_sectors(self) -> List[str]:
        """Get all sectors (Phase 3: uses StockDataRepository)"""
        # Phase 3: Note - Repository doesn't have sector aggregation methods yet
        # This requires a specialized query, so we keep using direct SQL
        # Can be improved with a get_all_sectors() method in StockDataRepository

        # Direct SQLite access (specialized query)
        conn = self.get_connection()
        cursor = conn.execute(
            "SELECT DISTINCT sector FROM stock_prices WHERE sector NOT LIKE '%_ETF' AND sector != 'INDICATOR'"
        )
        sectors = [row[0] for row in cursor.fetchall()]
        conn.close()
        return sectors

    # ==================== Matrix/Array Methods ====================

    def create_price_matrix(self, symbols: List[str] = None, lookback: int = 252) -> Tuple[np.ndarray, List[str], List[str]]:
        """
        Create price matrix [symbols x dates]

        Returns:
            matrix: numpy array of shape (n_symbols, n_dates)
            symbols: list of symbols (row labels)
            dates: list of dates (column labels)
        """
        if symbols is None:
            symbols = self.get_all_symbols()

        conn = self.get_connection()

        # Get date range
        cursor = conn.execute("SELECT DISTINCT date FROM stock_prices ORDER BY date DESC LIMIT ?", (lookback,))
        dates = [row[0] for row in cursor.fetchall()][::-1]

        if not dates:
            return np.array([]), [], []

        # Create matrix
        matrix = np.full((len(symbols), len(dates)), np.nan)

        for i, symbol in enumerate(symbols):
            df = pd.read_sql(
                f"SELECT date, close FROM stock_prices WHERE symbol = ? AND date >= ? ORDER BY date",
                conn, params=(symbol, dates[0])
            )
            for _, row in df.iterrows():
                if row['date'] in dates:
                    j = dates.index(row['date'])
                    matrix[i, j] = row['close']

        conn.close()
        return matrix, symbols, dates

    def create_returns_matrix(self, price_matrix: np.ndarray = None, period: int = 1) -> np.ndarray:
        """Create returns matrix from price matrix"""
        if price_matrix is None:
            price_matrix, _, _ = self.create_price_matrix()

        if price_matrix.size == 0:
            return np.array([])

        # Calculate returns
        returns = np.zeros_like(price_matrix)
        returns[:, period:] = (price_matrix[:, period:] / price_matrix[:, :-period] - 1) * 100
        returns[:, :period] = np.nan

        return returns

    def create_indicator_matrix(self, symbols: List[str] = None) -> Dict[str, np.ndarray]:
        """
        Create matrices for technical indicators

        Returns dict with:
            - rsi: RSI matrix [symbols x dates]
            - atr_pct: ATR% matrix
            - ma20: MA20 matrix
            - momentum: 20-day momentum matrix
        """
        if symbols is None:
            symbols = self.get_all_symbols()[:100]  # Limit for speed

        conn = self.get_connection()

        indicators = {
            'rsi': [],
            'atr_pct': [],
            'ma20': [],
            'momentum': [],
        }

        for symbol in symbols:
            df = self.get_prices(symbol)
            if len(df) < 30:
                for key in indicators:
                    indicators[key].append([])
                continue

            closes = df['close'].values
            highs = df['high'].values
            lows = df['low'].values

            # RSI
            rsi = self._calc_rsi(closes)
            indicators['rsi'].append(rsi)

            # ATR %
            atr_pct = self._calc_atr_pct(closes, highs, lows)
            indicators['atr_pct'].append(atr_pct)

            # MA20
            ma20 = pd.Series(closes).rolling(20).mean().values
            indicators['ma20'].append(ma20)

            # Momentum
            momentum = np.zeros_like(closes)
            momentum[20:] = (closes[20:] / closes[:-20] - 1) * 100
            indicators['momentum'].append(momentum)

        conn.close()

        # Convert to numpy arrays (padded)
        max_len = max(len(x) for x in indicators['rsi']) if indicators['rsi'] else 0

        for key in indicators:
            padded = []
            for arr in indicators[key]:
                if len(arr) < max_len:
                    padded.append(np.pad(arr, (0, max_len - len(arr)), constant_values=np.nan))
                else:
                    padded.append(arr[:max_len])
            indicators[key] = np.array(padded) if padded else np.array([])

        return indicators

    def save_features(self, features: Dict[str, np.ndarray], name: str):
        """Save feature matrices"""
        path = os.path.join(self.dirs['features'], f'{name}.npz')
        np.savez_compressed(path, **features)
        print(f"Saved features to: {path}")

    def load_features(self, name: str) -> Dict[str, np.ndarray]:
        """Load feature matrices"""
        path = os.path.join(self.dirs['features'], f'{name}.npz')
        if os.path.exists(path):
            return dict(np.load(path))
        return {}

    # ==================== Reference Data Methods ====================

    def save_reference(self, data: Dict, name: str):
        """Save reference data as JSON"""
        path = os.path.join(self.dirs['reference'], f'{name}.json')
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"Saved reference: {path}")

    def load_reference(self, name: str) -> Dict:
        """Load reference data"""
        path = os.path.join(self.dirs['reference'], f'{name}.json')
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        return {}

    # ==================== Cache Methods ====================

    def cache_set(self, key: str, value: Any, ttl: int = 3600):
        """Set cache value with TTL (seconds)"""
        self._cache[key] = value
        self._cache_expiry[key] = datetime.now() + timedelta(seconds=ttl)

    def cache_get(self, key: str) -> Optional[Any]:
        """Get cache value (returns None if expired)"""
        if key not in self._cache:
            return None
        if datetime.now() > self._cache_expiry.get(key, datetime.min):
            del self._cache[key]
            del self._cache_expiry[key]
            return None
        return self._cache[key]

    def clear_cache(self):
        """Clear all cache"""
        self._cache.clear()
        self._cache_expiry.clear()

    # ==================== Utility Methods ====================

    def get_all_symbols(self) -> List[str]:
        """Get all stock symbols"""
        conn = self.get_connection()
        cursor = conn.execute(
            "SELECT DISTINCT symbol FROM stock_prices WHERE sector NOT LIKE '%_ETF' AND sector != 'INDICATOR'"
        )
        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()
        return symbols

    def get_latest_date(self) -> str:
        """Get latest date in database"""
        conn = self.get_connection()
        cursor = conn.execute("SELECT MAX(date) FROM stock_prices")
        result = cursor.fetchone()[0]
        conn.close()
        return result

    def get_summary(self) -> Dict:
        """Get database summary"""
        conn = self.get_connection()

        summary = {}

        # Symbols
        cursor = conn.execute("SELECT COUNT(DISTINCT symbol) FROM stock_prices")
        summary['total_symbols'] = cursor.fetchone()[0]

        # Records
        cursor = conn.execute("SELECT COUNT(*) FROM stock_prices")
        summary['total_records'] = cursor.fetchone()[0]

        # Date range
        cursor = conn.execute("SELECT MIN(date), MAX(date) FROM stock_prices")
        row = cursor.fetchone()
        summary['date_range'] = {'start': row[0], 'end': row[1]}

        # By sector
        cursor = conn.execute(
            "SELECT sector, COUNT(DISTINCT symbol), COUNT(*) FROM stock_prices GROUP BY sector"
        )
        summary['sectors'] = {
            row[0]: {'symbols': row[1], 'records': row[2]}
            for row in cursor.fetchall()
        }

        conn.close()
        return summary

    # ==================== Calculation Helpers ====================

    def _calc_rsi(self, prices: np.ndarray, period: int = 14) -> np.ndarray:
        """Calculate RSI"""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        rsi = np.zeros(len(prices))
        for i in range(period, len(prices)):
            avg_gain = np.mean(gains[i-period:i])
            avg_loss = np.mean(losses[i-period:i])
            if avg_loss == 0:
                rsi[i] = 100
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100 - (100 / (1 + rs))

        return rsi

    def _calc_atr_pct(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, period: int = 14) -> np.ndarray:
        """Calculate ATR as percentage"""
        tr = np.zeros(len(closes))
        for i in range(1, len(closes)):
            tr[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )

        atr = np.zeros(len(closes))
        for i in range(period, len(closes)):
            atr[i] = np.mean(tr[i-period:i])

        atr_pct = np.zeros(len(closes))
        atr_pct[period:] = (atr[period:] / closes[period:]) * 100

        return atr_pct


def main():
    """Test data manager"""
    print("="*60)
    print("DATA MANAGER TEST")
    print("="*60)

    dm = DataManager()

    # Show summary
    summary = dm.get_summary()
    print(f"\nDatabase Summary:")
    print(f"  Symbols: {summary['total_symbols']}")
    print(f"  Records: {summary['total_records']:,}")
    print(f"  Date Range: {summary['date_range']['start']} to {summary['date_range']['end']}")

    # Test price matrix
    print("\nCreating price matrix...")
    symbols = dm.get_all_symbols()[:50]  # First 50 symbols
    matrix, syms, dates = dm.create_price_matrix(symbols, lookback=60)
    print(f"  Price matrix shape: {matrix.shape}")

    # Test returns matrix
    returns = dm.create_returns_matrix(matrix)
    print(f"  Returns matrix shape: {returns.shape}")

    # Test indicators
    print("\nCalculating indicators...")
    indicators = dm.create_indicator_matrix(symbols[:20])
    for name, arr in indicators.items():
        print(f"  {name}: shape {arr.shape}")

    # Save features
    dm.save_features({
        'price_matrix': matrix,
        'returns_matrix': returns,
        'symbols': np.array(syms),
        'dates': np.array(dates),
    }, 'test_features')

    print("\nData manager test complete!")


if __name__ == '__main__':
    main()
