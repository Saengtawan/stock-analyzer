#!/usr/bin/env python3
"""
DATA COLLECTOR - เก็บข้อมูลทุกอย่างไว้เป็นฐานข้อมูล

เป้าหมาย: ให้ระบบทำงานได้ถูกต้อง หาหุ้นที่ดีเข้าพอร์ตได้ถูกต้อง

Data to collect:
1. Stock prices (500+ stocks)
2. Sector ETFs (11 sectors)
3. Market indicators (VIX, SPY)
4. Economic data (rates, oil, bonds)
5. Sector momentum history
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sqlite3
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    print("Need yfinance: pip install yfinance")
    yf = None

# Base directory for data
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'database')
os.makedirs(DATA_DIR, exist_ok=True)


class DataCollector:
    """Collect and store all data needed for the system"""

    # Universe of stocks by sector
    UNIVERSE = {
        'Technology': ['AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'CRM', 'ORCL', 'ADBE', 'INTC', 'CSCO', 'IBM', 'NOW', 'INTU', 'PANW'],
        'Semiconductors': ['NVDA', 'AMD', 'AVGO', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'ADI', 'MCHP', 'NXPI'],
        'Finance': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'V', 'MA', 'AXP', 'BLK', 'SCHW', 'CME', 'ICE'],
        'Industrial': ['CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT', 'NOC', 'GD', 'MMM', 'EMR', 'ETN', 'ITW'],
        'Healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY', 'AMGN', 'GILD', 'CI'],
        'Consumer': ['HD', 'LOW', 'NKE', 'MCD', 'SBUX', 'WMT', 'COST', 'TGT', 'TJX', 'ROST', 'ORLY', 'AZO'],
        'Consumer_Staples': ['PG', 'KO', 'PEP', 'PM', 'MO', 'CL', 'EL', 'KMB', 'GIS', 'HSY', 'MDLZ'],
        'Energy': ['XOM', 'CVX', 'COP', 'EOG', 'SLB', 'MPC', 'VLO', 'PSX', 'OXY', 'DVN', 'HAL'],
        'Utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'PEG', 'WEC'],
        'Real_Estate': ['PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'O', 'SPG', 'WELL', 'DLR', 'AVB'],
        'Materials': ['LIN', 'APD', 'SHW', 'ECL', 'FCX', 'NEM', 'NUE', 'DOW', 'DD', 'PPG'],
    }

    # Sector ETFs
    SECTOR_ETFS = {
        'Technology': 'XLK',
        'Finance': 'XLF',
        'Healthcare': 'XLV',
        'Consumer': 'XLY',
        'Consumer_Staples': 'XLP',
        'Energy': 'XLE',
        'Utilities': 'XLU',
        'Industrial': 'XLI',
        'Materials': 'XLB',
        'Real_Estate': 'XLRE',
        'Semiconductors': 'SMH',
    }

    # Market indicators
    MARKET_INDICATORS = {
        'SPY': 'S&P 500',
        '^VIX': 'Volatility Index',
        'TLT': 'Bonds',
        'USO': 'Oil',
        'GLD': 'Gold',
        'UUP': 'Dollar Index',
    }

    def __init__(self, db_path=None):
        self.db_path = db_path or os.path.join(DATA_DIR, 'stocks.db')
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Stock prices table
        c.execute('''
            CREATE TABLE IF NOT EXISTS stock_prices (
                symbol TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                sector TEXT,
                PRIMARY KEY (symbol, date)
            )
        ''')

        # Sector momentum table
        c.execute('''
            CREATE TABLE IF NOT EXISTS sector_momentum (
                sector TEXT,
                date TEXT,
                momentum_5d REAL,
                momentum_10d REAL,
                momentum_20d REAL,
                is_best_sector INTEGER,
                PRIMARY KEY (sector, date)
            )
        ''')

        # Market conditions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS market_conditions (
                date TEXT PRIMARY KEY,
                spy_price REAL,
                spy_ma20 REAL,
                spy_ma50 REAL,
                vix REAL,
                market_regime TEXT,
                oil_change REAL,
                tlt_change REAL
            )
        ''')

        # Trading signals table
        c.execute('''
            CREATE TABLE IF NOT EXISTS trading_signals (
                date TEXT,
                symbol TEXT,
                sector TEXT,
                signal_type TEXT,
                score REAL,
                entry_price REAL,
                stop_price REAL,
                target_price REAL,
                PRIMARY KEY (date, symbol)
            )
        ''')

        # Trade history table
        c.execute('''
            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT,
                exit_date TEXT,
                symbol TEXT,
                sector TEXT,
                entry_price REAL,
                exit_price REAL,
                return_pct REAL,
                exit_reason TEXT
            )
        ''')

        conn.commit()
        conn.close()
        print(f"Database initialized: {self.db_path}")

    def collect_stock_prices(self, period='2y'):
        """Collect stock prices for all stocks"""
        if yf is None:
            print("yfinance not available")
            return

        print("\n" + "="*60)
        print("COLLECTING STOCK PRICES")
        print("="*60)

        conn = sqlite3.connect(self.db_path)

        total_stocks = sum(len(symbols) for symbols in self.UNIVERSE.values())
        collected = 0

        for sector, symbols in self.UNIVERSE.items():
            print(f"\n{sector}: {len(symbols)} stocks")

            for symbol in symbols:
                try:
                    data = yf.download(symbol, period=period, progress=False)
                    if isinstance(data.columns, pd.MultiIndex):
                        data.columns = data.columns.get_level_values(0)

                    for idx, row in data.iterrows():
                        date_str = idx.strftime('%Y-%m-%d')
                        conn.execute('''
                            INSERT OR REPLACE INTO stock_prices
                            (symbol, date, open, high, low, close, volume, sector)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            symbol, date_str,
                            float(row['Open']), float(row['High']),
                            float(row['Low']), float(row['Close']),
                            int(row['Volume']), sector
                        ))

                    collected += 1
                    print(f"  ✓ {symbol} ({len(data)} days)")

                except Exception as e:
                    print(f"  ✗ {symbol}: {e}")

        conn.commit()
        conn.close()

        print(f"\nCollected: {collected}/{total_stocks} stocks")

    def collect_sector_etfs(self, period='2y'):
        """Collect sector ETF prices"""
        if yf is None:
            return

        print("\n" + "="*60)
        print("COLLECTING SECTOR ETFs")
        print("="*60)

        conn = sqlite3.connect(self.db_path)

        for sector, etf in self.SECTOR_ETFS.items():
            try:
                data = yf.download(etf, period=period, progress=False)
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)

                for idx, row in data.iterrows():
                    date_str = idx.strftime('%Y-%m-%d')
                    conn.execute('''
                        INSERT OR REPLACE INTO stock_prices
                        (symbol, date, open, high, low, close, volume, sector)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        etf, date_str,
                        float(row['Open']), float(row['High']),
                        float(row['Low']), float(row['Close']),
                        int(row['Volume']), f'{sector}_ETF'
                    ))

                print(f"  ✓ {sector}: {etf} ({len(data)} days)")

            except Exception as e:
                print(f"  ✗ {sector}: {e}")

        conn.commit()
        conn.close()

    def collect_market_indicators(self, period='2y'):
        """Collect market indicators"""
        if yf is None:
            return

        print("\n" + "="*60)
        print("COLLECTING MARKET INDICATORS")
        print("="*60)

        conn = sqlite3.connect(self.db_path)

        for symbol, name in self.MARKET_INDICATORS.items():
            try:
                data = yf.download(symbol, period=period, progress=False)
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)

                for idx, row in data.iterrows():
                    date_str = idx.strftime('%Y-%m-%d')
                    conn.execute('''
                        INSERT OR REPLACE INTO stock_prices
                        (symbol, date, open, high, low, close, volume, sector)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        symbol, date_str,
                        float(row['Open']), float(row['High']),
                        float(row['Low']), float(row['Close']),
                        int(row['Volume']), 'INDICATOR'
                    ))

                print(f"  ✓ {name}: {symbol} ({len(data)} days)")

            except Exception as e:
                print(f"  ✗ {name}: {e}")

        conn.commit()
        conn.close()

    def calculate_sector_momentum(self):
        """Calculate sector momentum and store"""
        print("\n" + "="*60)
        print("CALCULATING SECTOR MOMENTUM")
        print("="*60)

        conn = sqlite3.connect(self.db_path)

        for sector, etf in self.SECTOR_ETFS.items():
            df = pd.read_sql(f'''
                SELECT date, close FROM stock_prices
                WHERE symbol = '{etf}'
                ORDER BY date
            ''', conn)

            if len(df) < 20:
                continue

            df['momentum_5d'] = df['close'].pct_change(5) * 100
            df['momentum_10d'] = df['close'].pct_change(10) * 100
            df['momentum_20d'] = df['close'].pct_change(20) * 100

            for idx, row in df.iterrows():
                if pd.notna(row['momentum_5d']):
                    conn.execute('''
                        INSERT OR REPLACE INTO sector_momentum
                        (sector, date, momentum_5d, momentum_10d, momentum_20d, is_best_sector)
                        VALUES (?, ?, ?, ?, ?, 0)
                    ''', (
                        sector, row['date'],
                        row['momentum_5d'], row['momentum_10d'], row['momentum_20d']
                    ))

            print(f"  ✓ {sector}: {len(df)} days")

        conn.commit()
        conn.close()

    def calculate_market_conditions(self):
        """Calculate market conditions"""
        print("\n" + "="*60)
        print("CALCULATING MARKET CONDITIONS")
        print("="*60)

        conn = sqlite3.connect(self.db_path)

        # Get SPY data
        spy = pd.read_sql('''
            SELECT date, close FROM stock_prices
            WHERE symbol = 'SPY'
            ORDER BY date
        ''', conn)

        # Get VIX data
        vix = pd.read_sql('''
            SELECT date, close as vix FROM stock_prices
            WHERE symbol = '^VIX'
            ORDER BY date
        ''', conn)

        # Merge
        df = spy.merge(vix, on='date', how='left')
        df['spy_ma20'] = df['close'].rolling(20).mean()
        df['spy_ma50'] = df['close'].rolling(50).mean()

        for idx, row in df.iterrows():
            if pd.notna(row['spy_ma50']):
                regime = 'bull' if row['close'] > row['spy_ma50'] else 'bear'
                conn.execute('''
                    INSERT OR REPLACE INTO market_conditions
                    (date, spy_price, spy_ma20, spy_ma50, vix, market_regime)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    row['date'], row['close'], row['spy_ma20'],
                    row['spy_ma50'], row['vix'], regime
                ))

        conn.commit()
        conn.close()
        print(f"  ✓ Market conditions: {len(df)} days")

    def get_summary(self):
        """Get database summary"""
        conn = sqlite3.connect(self.db_path)

        summary = {}

        # Stock prices
        cursor = conn.execute('SELECT COUNT(DISTINCT symbol), COUNT(*), MIN(date), MAX(date) FROM stock_prices')
        row = cursor.fetchone()
        summary['stock_prices'] = {
            'symbols': row[0],
            'records': row[1],
            'date_range': f"{row[2]} to {row[3]}"
        }

        # Sector momentum
        cursor = conn.execute('SELECT COUNT(DISTINCT sector), COUNT(*) FROM sector_momentum')
        row = cursor.fetchone()
        summary['sector_momentum'] = {
            'sectors': row[0],
            'records': row[1]
        }

        # Market conditions
        cursor = conn.execute('SELECT COUNT(*) FROM market_conditions')
        row = cursor.fetchone()
        summary['market_conditions'] = {
            'records': row[0]
        }

        conn.close()
        return summary

    def collect_all(self, period='2y'):
        """Collect all data"""
        print("\n" + "="*70)
        print("DATA COLLECTION - Building Database")
        print("="*70)

        self.collect_stock_prices(period)
        self.collect_sector_etfs(period)
        self.collect_market_indicators(period)
        self.calculate_sector_momentum()
        self.calculate_market_conditions()

        summary = self.get_summary()

        print("\n" + "="*60)
        print("DATABASE SUMMARY")
        print("="*60)
        print(f"\nStock Prices:")
        print(f"  Symbols: {summary['stock_prices']['symbols']}")
        print(f"  Records: {summary['stock_prices']['records']:,}")
        print(f"  Range: {summary['stock_prices']['date_range']}")

        print(f"\nSector Momentum:")
        print(f"  Sectors: {summary['sector_momentum']['sectors']}")
        print(f"  Records: {summary['sector_momentum']['records']:,}")

        print(f"\nMarket Conditions:")
        print(f"  Records: {summary['market_conditions']['records']:,}")

        print(f"\nDatabase saved: {self.db_path}")


def main():
    """Main entry point"""
    collector = DataCollector()
    collector.collect_all(period='2y')


if __name__ == '__main__':
    main()
