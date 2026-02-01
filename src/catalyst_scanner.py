#!/usr/bin/env python3
"""
CATALYST SCANNER - หา Catalyst ที่จะทำให้หุ้นขึ้น

Layer 3 ของ Strategic Framework:
- Earnings Calendar (ประกาศงบ)
- Analyst Ratings (upgrade/downgrade)
- Insider Trading (ผู้บริหารซื้อ/ขาย)
- News Sentiment (ข่าวดี/ร้าย)

หุ้นที่มี Catalyst = มีเหตุผลที่จะขึ้น
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


class CatalystScanner:
    """Scan for stock catalysts"""

    def __init__(self):
        self.db_path = DB_PATH
        self._init_tables()

    def _init_tables(self):
        """Initialize tables"""
        conn = sqlite3.connect(self.db_path)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_catalysts (
                symbol TEXT,
                date TEXT,
                catalyst_type TEXT,
                description TEXT,
                impact TEXT,
                score REAL,
                source TEXT,
                updated_at TEXT,
                PRIMARY KEY (symbol, date, catalyst_type)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS earnings_calendar (
                symbol TEXT,
                earnings_date TEXT,
                estimate_eps REAL,
                actual_eps REAL,
                surprise_pct REAL,
                updated_at TEXT,
                PRIMARY KEY (symbol, earnings_date)
            )
        """)

        conn.commit()
        conn.close()

    def get_earnings_calendar(self, symbols: List[str]) -> List[Dict]:
        """Get upcoming earnings for symbols"""
        if yf is None:
            return []

        print("="*60)
        print("Scanning Earnings Calendar")
        print("="*60)

        upcoming_earnings = []

        for symbol in symbols[:50]:  # Limit to avoid rate limits
            try:
                ticker = yf.Ticker(symbol)
                cal = ticker.calendar

                if cal is not None and not cal.empty:
                    # Try to get earnings date
                    earnings_date = None

                    if isinstance(cal, pd.DataFrame):
                        if 'Earnings Date' in cal.columns:
                            earnings_date = cal['Earnings Date'].iloc[0]
                    elif isinstance(cal, dict):
                        earnings_date = cal.get('Earnings Date')

                    if earnings_date is not None:
                        # Check if upcoming (within 30 days)
                        if isinstance(earnings_date, (list, tuple)):
                            earnings_date = earnings_date[0]

                        if hasattr(earnings_date, 'strftime'):
                            date_str = earnings_date.strftime('%Y-%m-%d')
                        else:
                            date_str = str(earnings_date)[:10]

                        today = datetime.now().strftime('%Y-%m-%d')
                        future_30d = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

                        if today <= date_str <= future_30d:
                            days_until = (datetime.strptime(date_str, '%Y-%m-%d') - datetime.now()).days

                            upcoming_earnings.append({
                                'symbol': symbol,
                                'earnings_date': date_str,
                                'days_until': days_until,
                                'catalyst_type': 'EARNINGS',
                            })

            except Exception as e:
                continue

        # Sort by date
        upcoming_earnings.sort(key=lambda x: x['earnings_date'])

        print(f"Found {len(upcoming_earnings)} upcoming earnings")
        for earn in upcoming_earnings[:10]:
            print(f"  {earn['symbol']:<8} {earn['earnings_date']} ({earn['days_until']:+d} days)")

        return upcoming_earnings

    def get_analyst_ratings(self, symbol: str) -> Dict:
        """Get analyst ratings for a symbol"""
        if yf is None:
            return {}

        try:
            ticker = yf.Ticker(symbol)
            recommendations = ticker.recommendations

            if recommendations is not None and len(recommendations) > 0:
                recent = recommendations.tail(10)

                # Count recommendations
                buy_count = len(recent[recent['To Grade'].str.contains('Buy|Outperform|Overweight', case=False, na=False)])
                sell_count = len(recent[recent['To Grade'].str.contains('Sell|Underperform|Underweight', case=False, na=False)])
                hold_count = len(recent) - buy_count - sell_count

                # Check for recent upgrades
                if len(recent) > 0:
                    latest = recent.iloc[-1]
                    action = latest.get('Action', '')

                    if 'up' in str(action).lower():
                        catalyst = 'UPGRADE'
                    elif 'down' in str(action).lower():
                        catalyst = 'DOWNGRADE'
                    else:
                        catalyst = 'MAINTAIN'

                    return {
                        'symbol': symbol,
                        'buy_count': buy_count,
                        'hold_count': hold_count,
                        'sell_count': sell_count,
                        'latest_action': catalyst,
                        'bullish_pct': buy_count / len(recent) * 100 if len(recent) > 0 else 50,
                    }

        except Exception as e:
            pass

        return {}

    def get_insider_activity(self, symbol: str) -> Dict:
        """Get insider trading activity"""
        if yf is None:
            return {}

        try:
            ticker = yf.Ticker(symbol)
            insiders = ticker.insider_transactions

            if insiders is not None and len(insiders) > 0:
                # Recent transactions (last 90 days)
                recent = insiders.head(20)

                buy_value = 0
                sell_value = 0

                for _, row in recent.iterrows():
                    shares = abs(row.get('Shares', 0))
                    value = row.get('Value', 0)

                    if 'Purchase' in str(row.get('Transaction', '')):
                        buy_value += value if value else 0
                    elif 'Sale' in str(row.get('Transaction', '')):
                        sell_value += value if value else 0

                net_value = buy_value - sell_value

                return {
                    'symbol': symbol,
                    'buy_value': buy_value,
                    'sell_value': sell_value,
                    'net_value': net_value,
                    'insider_signal': 'BUYING' if net_value > 100000 else 'SELLING' if net_value < -100000 else 'NEUTRAL',
                }

        except Exception as e:
            pass

        return {}

    def get_price_momentum_catalyst(self, symbol: str) -> Dict:
        """Check for price momentum catalysts (breakout, gap up, etc.)"""
        if yf is None:
            return {}

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='3mo')

            if len(hist) >= 60:
                closes = hist['Close'].values
                highs = hist['High'].values
                volumes = hist['Volume'].values

                current = closes[-1]
                prev_close = closes[-2]

                # Gap detection
                gap_pct = (hist['Open'].iloc[-1] / prev_close - 1) * 100

                # 52-week high
                high_52w = max(highs)
                pct_from_high = (current / high_52w - 1) * 100

                # Breakout detection (above recent high)
                recent_high = max(closes[-20:-1])
                is_breakout = current > recent_high * 1.01

                # Volume surge
                vol_avg = np.mean(volumes[-20:-1])
                vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

                catalysts = []

                if gap_pct > 3:
                    catalysts.append('GAP_UP')
                if is_breakout:
                    catalysts.append('BREAKOUT')
                if vol_ratio > 2:
                    catalysts.append('VOLUME_SURGE')
                if pct_from_high > -5:
                    catalysts.append('NEAR_52W_HIGH')

                return {
                    'symbol': symbol,
                    'gap_pct': gap_pct,
                    'pct_from_high': pct_from_high,
                    'is_breakout': is_breakout,
                    'volume_ratio': vol_ratio,
                    'catalysts': catalysts,
                }

        except Exception as e:
            pass

        return {}

    def scan_symbols(self, symbols: List[str]) -> List[Dict]:
        """Scan all symbols for catalysts"""
        print("\n" + "="*60)
        print("SCANNING FOR CATALYSTS")
        print("="*60)

        results = []

        # Get earnings calendar
        earnings = self.get_earnings_calendar(symbols)
        earnings_map = {e['symbol']: e for e in earnings}

        for i, symbol in enumerate(symbols):
            if i % 10 == 0:
                print(f"  Scanning... {i}/{len(symbols)}")

            catalysts = []
            score = 0

            # 1. Check earnings
            if symbol in earnings_map:
                earn = earnings_map[symbol]
                catalysts.append(f"EARNINGS in {earn['days_until']} days")
                score += 20 if earn['days_until'] <= 14 else 10

            # 2. Check analyst ratings
            ratings = self.get_analyst_ratings(symbol)
            if ratings:
                if ratings.get('latest_action') == 'UPGRADE':
                    catalysts.append('ANALYST_UPGRADE')
                    score += 15
                elif ratings.get('bullish_pct', 50) > 70:
                    catalysts.append('ANALYST_BULLISH')
                    score += 10

            # 3. Check insider activity
            insider = self.get_insider_activity(symbol)
            if insider:
                if insider.get('insider_signal') == 'BUYING':
                    catalysts.append('INSIDER_BUYING')
                    score += 20

            # 4. Check price momentum
            momentum = self.get_price_momentum_catalyst(symbol)
            if momentum:
                for cat in momentum.get('catalysts', []):
                    catalysts.append(cat)
                    score += 10

            if catalysts:
                results.append({
                    'symbol': symbol,
                    'catalysts': catalysts,
                    'catalyst_count': len(catalysts),
                    'score': score,
                    'details': {
                        'earnings': earnings_map.get(symbol),
                        'ratings': ratings,
                        'insider': insider,
                        'momentum': momentum,
                    }
                })

        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)

        print(f"\n✅ Found {len(results)} stocks with catalysts")

        # Save results
        catalyst_path = os.path.join(DATA_DIR, 'predictions', 'catalyst_scan.json')
        with open(catalyst_path, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'count': len(results),
                'results': results[:50],  # Top 50
            }, f, indent=2, default=str)

        return results

    def get_top_catalysts(self, top_n: int = 10) -> List[Dict]:
        """Get top stocks by catalyst score"""
        # Load from database
        conn = sqlite3.connect(self.db_path)

        # Get all symbols from our universe
        cursor = conn.execute("""
            SELECT DISTINCT symbol FROM stock_prices
            WHERE sector NOT LIKE '%_ETF' AND sector != 'INDICATOR'
        """)
        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Scan for catalysts
        results = self.scan_symbols(symbols[:100])  # Limit for speed

        # Print top picks
        print("\n" + "="*60)
        print("TOP CATALYST PICKS")
        print("="*60)

        for stock in results[:top_n]:
            print(f"\n{stock['symbol']} (Score: {stock['score']})")
            for cat in stock['catalysts']:
                print(f"  • {cat}")

        return results[:top_n]


def main():
    """Main - run catalyst scan"""
    scanner = CatalystScanner()

    # Get symbols from sector analysis (top sectors)
    sector_path = os.path.join(DATA_DIR, 'predictions', 'sector_analysis.json')

    if os.path.exists(sector_path):
        with open(sector_path, 'r') as f:
            sector_data = json.load(f)
            symbols = [r['symbol'] for r in sector_data.get('recommendations', [])]
    else:
        # Use all symbols
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute("""
            SELECT DISTINCT symbol FROM stock_prices
            WHERE sector NOT LIKE '%_ETF' AND sector != 'INDICATOR'
            LIMIT 100
        """)
        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()

    print(f"\nScanning {len(symbols)} symbols for catalysts...")

    # Scan
    results = scanner.scan_symbols(symbols)

    print("\n" + "="*60)
    print("CATALYST SCAN COMPLETE")
    print("="*60)
    print(f"Stocks with catalysts: {len(results)}")

    if results:
        print("\nTop 5 by catalyst score:")
        for stock in results[:5]:
            print(f"  {stock['symbol']}: {', '.join(stock['catalysts'])} (Score: {stock['score']})")


if __name__ == '__main__':
    main()
