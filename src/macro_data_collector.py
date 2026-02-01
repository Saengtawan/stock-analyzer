#!/usr/bin/env python3
"""
MACRO DATA COLLECTOR - เก็บข้อมูลเศรษฐกิจโลก

Layer 1 ของ Strategic Framework:
- Fed Rate
- CPI/Inflation
- VIX (Fear Index)
- Treasury Yields
- Dollar Index
- Oil & Gold

Free APIs:
- FRED (Federal Reserve Economic Data) - Free with API key
- Yahoo Finance - Free
- Alpha Vantage - Free tier available
"""

import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'database', 'stocks.db')

# Free API Keys (get your own at fred.stlouisfed.org)
FRED_API_KEY = os.environ.get('FRED_API_KEY', '')


class MacroDataCollector:
    """Collect macroeconomic data"""

    def __init__(self):
        self.db_path = DB_PATH
        self._init_tables()

    def _init_tables(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)

        # Macro indicators table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS macro_indicators (
                date TEXT,
                indicator TEXT,
                value REAL,
                source TEXT,
                updated_at TEXT,
                PRIMARY KEY (date, indicator)
            )
        """)

        # Economic events table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS economic_events (
                date TEXT,
                event TEXT,
                description TEXT,
                impact TEXT,
                actual TEXT,
                forecast TEXT,
                previous TEXT,
                PRIMARY KEY (date, event)
            )
        """)

        # Market regime table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_regime (
                date TEXT PRIMARY KEY,
                regime TEXT,
                vix REAL,
                trend TEXT,
                risk_level TEXT,
                notes TEXT
            )
        """)

        conn.commit()
        conn.close()

    def collect_from_yahoo(self) -> Dict:
        """Collect macro data from Yahoo Finance (FREE)"""
        if yf is None:
            print("yfinance not available")
            return {}

        print("="*60)
        print("Collecting Macro Data from Yahoo Finance")
        print("="*60)

        indicators = {}

        # Key market indicators
        tickers = {
            '^VIX': 'VIX',           # Fear Index
            '^TNX': '10Y_YIELD',     # 10-Year Treasury Yield
            '^TYX': '30Y_YIELD',     # 30-Year Treasury Yield
            'DX-Y.NYB': 'DOLLAR_INDEX',  # Dollar Index
            'CL=F': 'OIL_WTI',       # Oil WTI
            'GC=F': 'GOLD',          # Gold
            '^GSPC': 'SP500',        # S&P 500
            '^DJI': 'DOW',           # Dow Jones
            '^IXIC': 'NASDAQ',       # Nasdaq
        }

        for ticker, name in tickers.items():
            try:
                data = yf.Ticker(ticker)
                hist = data.history(period='6mo')

                if len(hist) > 0:
                    current = hist['Close'].iloc[-1]
                    prev_day = hist['Close'].iloc[-2] if len(hist) > 1 else current
                    prev_week = hist['Close'].iloc[-5] if len(hist) > 5 else current
                    prev_month = hist['Close'].iloc[-21] if len(hist) > 21 else current

                    indicators[name] = {
                        'current': current,
                        'change_1d': (current / prev_day - 1) * 100,
                        'change_1w': (current / prev_week - 1) * 100,
                        'change_1m': (current / prev_month - 1) * 100,
                        'high_52w': hist['Close'].max(),
                        'low_52w': hist['Close'].min(),
                    }
                    print(f"  {name}: {current:.2f} ({indicators[name]['change_1d']:+.2f}%)")

            except Exception as e:
                print(f"  Error fetching {name}: {e}")

        # Save to database
        self._save_indicators(indicators)

        return indicators

    def collect_from_fred(self) -> Dict:
        """Collect economic data from FRED (requires API key)"""
        if not FRED_API_KEY:
            print("FRED API key not set. Set FRED_API_KEY environment variable.")
            print("Get free key at: https://fred.stlouisfed.org/docs/api/api_key.html")
            return {}

        print("\n" + "="*60)
        print("Collecting Economic Data from FRED")
        print("="*60)

        indicators = {}

        # Key economic series
        series = {
            'FEDFUNDS': 'FED_RATE',           # Federal Funds Rate
            'CPIAUCSL': 'CPI',                # Consumer Price Index
            'UNRATE': 'UNEMPLOYMENT',         # Unemployment Rate
            'GDP': 'GDP',                     # Real GDP
            'T10Y2Y': 'YIELD_CURVE',          # 10Y-2Y Yield Spread
            'UMCSENT': 'CONSUMER_SENTIMENT',  # Consumer Sentiment
            'HOUST': 'HOUSING_STARTS',        # Housing Starts
            'INDPRO': 'INDUSTRIAL_PRODUCTION', # Industrial Production
        }

        base_url = "https://api.stlouisfed.org/fred/series/observations"

        for series_id, name in series.items():
            try:
                params = {
                    'series_id': series_id,
                    'api_key': FRED_API_KEY,
                    'file_type': 'json',
                    'sort_order': 'desc',
                    'limit': 12,  # Last 12 observations
                }

                response = requests.get(base_url, params=params)
                data = response.json()

                if 'observations' in data and len(data['observations']) > 0:
                    obs = data['observations']
                    current = float(obs[0]['value']) if obs[0]['value'] != '.' else None

                    if current is not None:
                        prev = float(obs[1]['value']) if len(obs) > 1 and obs[1]['value'] != '.' else current

                        indicators[name] = {
                            'current': current,
                            'previous': prev,
                            'change': current - prev,
                            'date': obs[0]['date'],
                        }
                        print(f"  {name}: {current:.2f} (prev: {prev:.2f})")

            except Exception as e:
                print(f"  Error fetching {name}: {e}")

        return indicators

    def _save_indicators(self, indicators: Dict):
        """Save indicators to database"""
        conn = sqlite3.connect(self.db_path)
        today = datetime.now().strftime('%Y-%m-%d')
        updated_at = datetime.now().isoformat()

        for name, data in indicators.items():
            conn.execute("""
                INSERT OR REPLACE INTO macro_indicators
                (date, indicator, value, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (today, name, data['current'], 'yahoo', updated_at))

        conn.commit()
        conn.close()

    def analyze_regime(self) -> Dict:
        """Analyze current market regime"""
        print("\n" + "="*60)
        print("Analyzing Market Regime")
        print("="*60)

        # Get latest indicators
        conn = sqlite3.connect(self.db_path)
        today = datetime.now().strftime('%Y-%m-%d')

        cursor = conn.execute("""
            SELECT indicator, value FROM macro_indicators
            WHERE date = ?
        """, (today,))

        indicators = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        if not indicators:
            print("No data for today. Collecting first...")
            indicators_data = self.collect_from_yahoo()
            indicators = {k: v['current'] for k, v in indicators_data.items()}

        # Analyze regime
        regime = {
            'date': today,
            'regime': 'NEUTRAL',
            'risk_level': 'MEDIUM',
            'signals': [],
        }

        # VIX analysis
        vix = indicators.get('VIX', 20)
        if vix > 30:
            regime['signals'].append('⚠️ VIX > 30: HIGH FEAR - Consider waiting')
            regime['risk_level'] = 'HIGH'
        elif vix > 25:
            regime['signals'].append('⚠️ VIX > 25: ELEVATED FEAR - Reduce size')
            regime['risk_level'] = 'MEDIUM-HIGH'
        elif vix < 15:
            regime['signals'].append('✅ VIX < 15: LOW FEAR - RISK-ON')
            regime['risk_level'] = 'LOW'
        else:
            regime['signals'].append('📊 VIX normal: NEUTRAL')

        # 10Y Yield analysis
        yield_10y = indicators.get('10Y_YIELD', 4.0)
        if yield_10y > 5:
            regime['signals'].append('⚠️ 10Y > 5%: HIGH RATES - Bonds attractive')
        elif yield_10y < 3:
            regime['signals'].append('✅ 10Y < 3%: LOW RATES - Stocks attractive')

        # Dollar analysis
        dxy = indicators.get('DOLLAR_INDEX', 100)
        if dxy > 105:
            regime['signals'].append('⚠️ Dollar STRONG: Headwind for multinationals')
        elif dxy < 95:
            regime['signals'].append('✅ Dollar WEAK: Tailwind for multinationals')

        # Oil analysis
        oil = indicators.get('OIL_WTI', 70)
        if oil > 90:
            regime['signals'].append('⚠️ Oil > $90: Inflation pressure')
        elif oil < 60:
            regime['signals'].append('✅ Oil < $60: Low inflation')

        # Determine overall regime
        high_risk_signals = sum(1 for s in regime['signals'] if '⚠️' in s)
        low_risk_signals = sum(1 for s in regime['signals'] if '✅' in s)

        if high_risk_signals >= 3:
            regime['regime'] = 'RISK-OFF'
            regime['recommendation'] = 'ไม่ซื้อ หรือ ลดขนาด position'
        elif low_risk_signals >= 3:
            regime['regime'] = 'RISK-ON'
            regime['recommendation'] = 'สามารถซื้อได้ตาม signal'
        else:
            regime['regime'] = 'NEUTRAL'
            regime['recommendation'] = 'ระวัง เลือกเฉพาะหุ้นที่มีเหตุผลชัดเจน'

        # Print summary
        print(f"\n📊 MARKET REGIME: {regime['regime']}")
        print(f"🎯 Risk Level: {regime['risk_level']}")
        print(f"💡 Recommendation: {regime['recommendation']}")
        print("\nSignals:")
        for signal in regime['signals']:
            print(f"  {signal}")

        # Save to database
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO market_regime
            (date, regime, vix, trend, risk_level, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (today, regime['regime'], vix, 'NEUTRAL',
              regime['risk_level'], json.dumps(regime['signals'])))
        conn.commit()
        conn.close()

        return regime

    def get_economic_calendar(self) -> List[Dict]:
        """Get upcoming economic events (using free sources)"""
        print("\n" + "="*60)
        print("Economic Calendar (Hardcoded Key Events)")
        print("="*60)

        # Key events for 2025 (hardcoded - update periodically)
        events = [
            # Fed Meetings 2025
            {'date': '2025-01-29', 'event': 'FOMC Meeting', 'impact': 'HIGH'},
            {'date': '2025-03-19', 'event': 'FOMC Meeting', 'impact': 'HIGH'},
            {'date': '2025-05-07', 'event': 'FOMC Meeting', 'impact': 'HIGH'},
            {'date': '2025-06-18', 'event': 'FOMC Meeting', 'impact': 'HIGH'},
            {'date': '2025-07-30', 'event': 'FOMC Meeting', 'impact': 'HIGH'},
            {'date': '2025-09-17', 'event': 'FOMC Meeting', 'impact': 'HIGH'},
            {'date': '2025-11-05', 'event': 'FOMC Meeting', 'impact': 'HIGH'},
            {'date': '2025-12-17', 'event': 'FOMC Meeting', 'impact': 'HIGH'},

            # Jobs Reports (first Friday each month)
            {'date': '2025-02-07', 'event': 'Jobs Report', 'impact': 'HIGH'},
            {'date': '2025-03-07', 'event': 'Jobs Report', 'impact': 'HIGH'},
            {'date': '2025-04-04', 'event': 'Jobs Report', 'impact': 'HIGH'},

            # CPI Reports (usually mid-month)
            {'date': '2025-02-12', 'event': 'CPI Report', 'impact': 'HIGH'},
            {'date': '2025-03-12', 'event': 'CPI Report', 'impact': 'HIGH'},
            {'date': '2025-04-10', 'event': 'CPI Report', 'impact': 'HIGH'},
        ]

        # Filter upcoming events
        today = datetime.now().strftime('%Y-%m-%d')
        upcoming = [e for e in events if e['date'] >= today]
        upcoming.sort(key=lambda x: x['date'])

        print(f"\nUpcoming High-Impact Events:")
        for event in upcoming[:10]:
            days_until = (datetime.strptime(event['date'], '%Y-%m-%d') - datetime.now()).days
            print(f"  {event['date']} ({days_until:+d}d): {event['event']}")

        return upcoming[:10]

    def get_summary(self) -> Dict:
        """Get complete macro summary"""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'indicators': self.collect_from_yahoo(),
            'regime': self.analyze_regime(),
            'upcoming_events': self.get_economic_calendar(),
        }

        # Save summary
        summary_path = os.path.join(DATA_DIR, 'predictions', 'macro_summary.json')
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"\n✅ Macro summary saved to: {summary_path}")

        return summary


def main():
    """Main - collect and analyze macro data"""
    collector = MacroDataCollector()

    # Collect all data
    summary = collector.get_summary()

    print("\n" + "="*60)
    print("MACRO ANALYSIS COMPLETE")
    print("="*60)
    print(f"Regime: {summary['regime']['regime']}")
    print(f"Risk Level: {summary['regime']['risk_level']}")
    print(f"Recommendation: {summary['regime']['recommendation']}")


if __name__ == '__main__':
    main()
