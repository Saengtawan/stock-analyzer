#!/usr/bin/env python3
"""
SECTOR ANALYZER - วิเคราะห์และจัดอันดับ Sector

Layer 2 ของ Strategic Framework:
- Sector Momentum
- Sector Relative Strength
- Sector vs Economic Cycle
- Fund Flows (estimated)

เชื่อมโยงกับ Macro Regime เพื่อเลือก Sector ที่เหมาะสม
"""

import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'database', 'stocks.db')


# Sector ETFs mapping
SECTOR_ETFS = {
    'Technology': 'XLK',
    'Healthcare': 'XLV',
    'Financials': 'XLF',
    'Consumer_Discretionary': 'XLY',
    'Consumer_Staples': 'XLP',
    'Energy': 'XLE',
    'Industrials': 'XLI',
    'Materials': 'XLB',
    'Utilities': 'XLU',
    'Real_Estate': 'XLRE',
    'Communication': 'XLC',
    'Semiconductors': 'SMH',
    'Biotech': 'XBI',
    'Banks': 'KBE',
    'Regional_Banks': 'KRE',
}

# Economic cycle sector preferences
CYCLE_SECTORS = {
    'EARLY_EXPANSION': ['Financials', 'Technology', 'Consumer_Discretionary', 'Real_Estate'],
    'MID_EXPANSION': ['Industrials', 'Materials', 'Technology', 'Semiconductors'],
    'LATE_EXPANSION': ['Energy', 'Materials', 'Industrials'],
    'CONTRACTION': ['Healthcare', 'Utilities', 'Consumer_Staples'],
    'RECESSION': ['Utilities', 'Consumer_Staples', 'Healthcare'],
}


class SectorAnalyzer:
    """Analyze and rank sectors"""

    def __init__(self):
        self.db_path = DB_PATH
        self._init_tables()

    def _init_tables(self):
        """Initialize tables"""
        conn = sqlite3.connect(self.db_path)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sector_analysis (
                date TEXT,
                sector TEXT,
                momentum_5d REAL,
                momentum_20d REAL,
                momentum_60d REAL,
                relative_strength REAL,
                volume_change REAL,
                score REAL,
                rank INTEGER,
                PRIMARY KEY (date, sector)
            )
        """)

        conn.commit()
        conn.close()

    def get_sector_momentum(self) -> Dict:
        """Calculate momentum for each sector ETF"""
        if yf is None:
            return {}

        print("="*60)
        print("Calculating Sector Momentum")
        print("="*60)

        results = {}

        for sector, etf in SECTOR_ETFS.items():
            try:
                ticker = yf.Ticker(etf)
                hist = ticker.history(period='6mo')

                if len(hist) >= 60:
                    closes = hist['Close'].values
                    volumes = hist['Volume'].values

                    current = closes[-1]

                    # Momentum calculations
                    mom_5d = (closes[-1] / closes[-5] - 1) * 100
                    mom_20d = (closes[-1] / closes[-20] - 1) * 100
                    mom_60d = (closes[-1] / closes[-60] - 1) * 100

                    # Volume change
                    vol_recent = np.mean(volumes[-5:])
                    vol_prev = np.mean(volumes[-20:-5])
                    vol_change = (vol_recent / vol_prev - 1) * 100 if vol_prev > 0 else 0

                    # RSI
                    deltas = np.diff(closes[-15:])
                    gains = np.where(deltas > 0, deltas, 0)
                    losses = np.where(deltas < 0, -deltas, 0)
                    avg_gain = np.mean(gains)
                    avg_loss = np.mean(losses)
                    rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100

                    results[sector] = {
                        'etf': etf,
                        'price': current,
                        'momentum_5d': mom_5d,
                        'momentum_20d': mom_20d,
                        'momentum_60d': mom_60d,
                        'volume_change': vol_change,
                        'rsi': rsi,
                    }

                    print(f"  {sector:<25} {etf}: {mom_5d:+6.2f}% (5d) | {mom_20d:+6.2f}% (20d)")

            except Exception as e:
                print(f"  Error with {sector}: {e}")

        return results

    def get_relative_strength(self, sector_data: Dict) -> Dict:
        """Calculate relative strength vs SPY"""
        if yf is None:
            return sector_data

        try:
            spy = yf.Ticker('SPY')
            spy_hist = spy.history(period='6mo')

            if len(spy_hist) >= 60:
                spy_closes = spy_hist['Close'].values
                spy_mom_20d = (spy_closes[-1] / spy_closes[-20] - 1) * 100

                for sector, data in sector_data.items():
                    data['spy_mom_20d'] = spy_mom_20d
                    data['relative_strength'] = data['momentum_20d'] - spy_mom_20d

        except Exception as e:
            print(f"Error calculating relative strength: {e}")

        return sector_data

    def score_sectors(self, sector_data: Dict, regime: str = 'NEUTRAL') -> List[Tuple[str, float]]:
        """Score and rank sectors"""
        print("\n" + "="*60)
        print(f"Scoring Sectors (Regime: {regime})")
        print("="*60)

        scored = []

        # Get preferred sectors for current regime
        cycle_preference = CYCLE_SECTORS.get(regime, [])

        for sector, data in sector_data.items():
            score = 0

            # Momentum score (max 40)
            if data['momentum_5d'] > 3:
                score += 15
            elif data['momentum_5d'] > 1:
                score += 10
            elif data['momentum_5d'] > 0:
                score += 5

            if data['momentum_20d'] > 5:
                score += 15
            elif data['momentum_20d'] > 2:
                score += 10
            elif data['momentum_20d'] > 0:
                score += 5

            # Relative strength (max 20)
            rs = data.get('relative_strength', 0)
            if rs > 3:
                score += 20
            elif rs > 1:
                score += 15
            elif rs > 0:
                score += 10

            # Volume confirmation (max 15)
            vol = data.get('volume_change', 0)
            if vol > 20:
                score += 15
            elif vol > 10:
                score += 10
            elif vol > 0:
                score += 5

            # RSI - not overbought (max 15)
            rsi = data.get('rsi', 50)
            if 40 < rsi < 60:
                score += 15
            elif 35 < rsi < 65:
                score += 10
            elif rsi < 70:
                score += 5

            # Economic cycle bonus (max 10)
            if sector in cycle_preference:
                score += 10
                data['cycle_match'] = True
            else:
                data['cycle_match'] = False

            data['score'] = score
            scored.append((sector, score, data))

        # Sort by score
        scored.sort(key=lambda x: x[1], reverse=True)

        # Print rankings
        print(f"\n{'Rank':<5} {'Sector':<25} {'Score':>6} {'5d':>8} {'20d':>8} {'RS':>8} {'Cycle'}")
        print("-"*75)

        for i, (sector, score, data) in enumerate(scored[:10], 1):
            cycle_mark = "✅" if data.get('cycle_match') else ""
            print(f"{i:<5} {sector:<25} {score:>6.0f} {data['momentum_5d']:>+7.2f}% {data['momentum_20d']:>+7.2f}% {data.get('relative_strength', 0):>+7.2f}% {cycle_mark}")

        return scored

    def get_sector_stocks(self, sector: str, top_n: int = 10) -> List[Dict]:
        """Get top stocks in a sector from our database"""
        conn = sqlite3.connect(self.db_path)

        # Map sector name to database sectors
        sector_mapping = {
            'Financials': ['Finance_Banks', 'Finance_Insurance', 'Finance_Diversified', 'Finance_Exchanges', 'Finance_Payments'],
            'Banks': ['Finance_Banks'],
            'Technology': ['Technology'],
            'Semiconductors': ['Semiconductors'],
            'Healthcare': ['Healthcare_Pharma', 'Healthcare_MedDevices', 'Healthcare_Services'],
            'Energy': ['Energy_Oil', 'Energy_Midstream', 'Energy_Services'],
            'Consumer_Discretionary': ['Consumer_Retail', 'Consumer_Auto', 'Consumer_Travel'],
            'Consumer_Staples': ['Consumer_Staples', 'Consumer_Food'],
            'Industrials': ['Industrial_Machinery', 'Industrial_Aerospace', 'Industrial_Transport', 'Industrial_Conglomerate'],
            'Materials': ['Materials_Chemicals', 'Materials_Metals', 'Materials_Construction'],
            'Utilities': ['Utilities_Electric', 'Utilities_Gas'],
            'Real_Estate': ['Real_Estate_Retail', 'Real_Estate_Residential', 'Real_Estate_Industrial', 'Real_Estate_Healthcare', 'Real_Estate_Data'],
        }

        db_sectors = sector_mapping.get(sector, [sector])

        # Get symbols in this sector
        placeholders = ','.join(['?' for _ in db_sectors])
        cursor = conn.execute(f"""
            SELECT DISTINCT symbol, sector FROM stock_prices
            WHERE sector IN ({placeholders})
        """, db_sectors)

        symbols = [(row[0], row[1]) for row in cursor.fetchall()]

        stocks = []

        for symbol, sector_name in symbols[:30]:  # Limit to 30 per query
            df = pd.read_sql("""
                SELECT date, close, volume FROM stock_prices
                WHERE symbol = ?
                ORDER BY date DESC
                LIMIT 30
            """, conn, params=(symbol,))

            if len(df) >= 20:
                closes = df['close'].values[::-1]
                volumes = df['volume'].values[::-1]

                mom_5d = (closes[-1] / closes[-5] - 1) * 100 if closes[-5] > 0 else 0
                mom_20d = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 and closes[-20] > 0 else 0

                vol_avg = np.mean(volumes[-20:-1])
                vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

                # Score stock
                score = 0
                if 2 < mom_5d < 8:
                    score += 30
                if 5 < mom_20d < 15:
                    score += 20
                if vol_ratio > 1.2:
                    score += 10

                stocks.append({
                    'symbol': symbol,
                    'sector': sector_name,
                    'price': closes[-1],
                    'momentum_5d': mom_5d,
                    'momentum_20d': mom_20d,
                    'volume_ratio': vol_ratio,
                    'score': score,
                })

        conn.close()

        # Sort and return top N
        stocks.sort(key=lambda x: x['score'], reverse=True)

        return stocks[:top_n]

    def analyze(self, regime: str = 'NEUTRAL') -> Dict:
        """Full sector analysis"""
        print("\n" + "="*60)
        print("FULL SECTOR ANALYSIS")
        print("="*60)

        # 1. Get momentum
        sector_data = self.get_sector_momentum()

        # 2. Calculate relative strength
        sector_data = self.get_relative_strength(sector_data)

        # 3. Score and rank
        ranked = self.score_sectors(sector_data, regime)

        # 4. Get top sectors
        top_sectors = ranked[:3]

        # 5. Get stocks for top sectors
        print("\n" + "="*60)
        print("TOP STOCKS IN TOP SECTORS")
        print("="*60)

        recommendations = []

        for sector, score, data in top_sectors:
            print(f"\n📊 {sector} (Score: {score})")
            print("-"*50)

            stocks = self.get_sector_stocks(sector, top_n=5)

            for stock in stocks:
                print(f"  {stock['symbol']:<8} ${stock['price']:>8.2f} | 5d: {stock['momentum_5d']:+6.2f}% | 20d: {stock['momentum_20d']:+6.2f}%")

                recommendations.append({
                    'sector': sector,
                    'sector_score': score,
                    **stock
                })

        # Save analysis
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'regime': regime,
            'sector_rankings': [(s, sc, d) for s, sc, d in ranked],
            'top_sectors': [s for s, _, _ in top_sectors],
            'recommendations': recommendations[:15],
        }

        analysis_path = os.path.join(DATA_DIR, 'predictions', 'sector_analysis.json')
        with open(analysis_path, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)

        print(f"\n✅ Sector analysis saved to: {analysis_path}")

        return analysis


def main():
    """Main - run sector analysis"""
    analyzer = SectorAnalyzer()

    # Get regime from macro analysis
    regime = 'NEUTRAL'  # Default

    # Try to load macro regime
    macro_path = os.path.join(DATA_DIR, 'predictions', 'macro_summary.json')
    if os.path.exists(macro_path):
        with open(macro_path, 'r') as f:
            macro = json.load(f)
            regime = macro.get('regime', {}).get('regime', 'NEUTRAL')

    print(f"\nUsing regime: {regime}")

    # Run analysis
    analysis = analyzer.analyze(regime)

    print("\n" + "="*60)
    print("SECTOR ANALYSIS COMPLETE")
    print("="*60)
    print(f"Top Sectors: {', '.join(analysis['top_sectors'])}")
    print(f"Top Picks: {len(analysis['recommendations'])} stocks")


if __name__ == '__main__':
    main()
