#!/usr/bin/env python3
"""
NEWS-BASED SECTOR PREDICTOR
ใช้ข่าวและเหตุการณ์โลกทำนายว่า sector ไหนจะดี

Philosophy:
- แต่ละเดือนดึงข่าว ดึงการเปลี่ยนแปลงของโลก
- ใช้ข้อมูลเหล่านั้นตัดสินใจว่าจะเทรด sector ไหน

News Sources:
1. Federal Reserve decisions → affects all sectors
2. Oil prices → Energy, Transportation
3. Tech news (AI, chips) → Tech, Semiconductors
4. Economic indicators → Finance, Consumer
5. Global events → Defense, Utilities
"""

import os
import json
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


class NewsSectorPredictor:
    """
    Predict which sector will perform best based on:
    1. Economic indicators (VIX, rates, oil)
    2. Sector momentum (recent performance)
    3. Market regime (bull/bear)
    """

    # Sector ETFs for quick sector analysis
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

    # Sector characteristics for different market conditions
    SECTOR_CONDITIONS = {
        'high_vix': {  # VIX > 25 - fear/uncertainty
            'best': ['Utilities', 'Consumer_Staples', 'Healthcare'],
            'worst': ['Technology', 'Semiconductors', 'Finance'],
        },
        'low_vix': {  # VIX < 15 - calm/confident
            'best': ['Technology', 'Semiconductors', 'Consumer'],
            'worst': ['Utilities', 'Consumer_Staples'],
        },
        'rising_rates': {  # Interest rates going up
            'best': ['Finance', 'Insurance'],
            'worst': ['Real_Estate', 'Utilities'],
        },
        'falling_rates': {  # Interest rates going down
            'best': ['Real_Estate', 'Utilities', 'Technology'],
            'worst': ['Finance'],
        },
        'rising_oil': {  # Oil prices going up
            'best': ['Energy'],
            'worst': ['Consumer', 'Transportation'],
        },
        'falling_oil': {  # Oil prices going down
            'best': ['Consumer', 'Transportation'],
            'worst': ['Energy'],
        },
        'bull_market': {  # SPY above MA50
            'best': ['Technology', 'Semiconductors', 'Consumer'],
            'worst': ['Utilities', 'Consumer_Staples'],
        },
        'bear_market': {  # SPY below MA50
            'best': ['Utilities', 'Consumer_Staples', 'Healthcare'],
            'worst': ['Technology', 'Semiconductors'],
        },
    }

    def __init__(self):
        self.data = {}
        self.conditions = {}

    def analyze_market_conditions(self) -> Dict:
        """Analyze current market conditions"""
        if yf is None:
            return {}

        conditions = {}

        # 1. VIX analysis
        try:
            vix = yf.download('^VIX', period='30d', progress=False)
            if isinstance(vix.columns, pd.MultiIndex):
                vix.columns = vix.columns.get_level_values(0)
            vix_current = float(vix['Close'].iloc[-1])
            vix_avg = float(vix['Close'].mean())

            if vix_current > 25:
                conditions['vix'] = 'high_vix'
            elif vix_current < 15:
                conditions['vix'] = 'low_vix'
            else:
                conditions['vix'] = 'normal_vix'

            conditions['vix_value'] = vix_current
            conditions['vix_trend'] = 'rising' if vix_current > vix_avg else 'falling'
        except:
            conditions['vix'] = 'unknown'

        # 2. SPY trend (market regime)
        try:
            spy = yf.download('SPY', period='100d', progress=False)
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)
            spy_price = float(spy['Close'].iloc[-1])
            spy_ma20 = float(spy['Close'].tail(20).mean())
            spy_ma50 = float(spy['Close'].tail(50).mean())

            if spy_price > spy_ma50:
                conditions['market'] = 'bull_market'
            else:
                conditions['market'] = 'bear_market'

            conditions['spy_above_ma20'] = spy_price > spy_ma20
            conditions['spy_above_ma50'] = spy_price > spy_ma50
        except:
            conditions['market'] = 'unknown'

        # 3. Oil price trend
        try:
            oil = yf.download('USO', period='30d', progress=False)
            if isinstance(oil.columns, pd.MultiIndex):
                oil.columns = oil.columns.get_level_values(0)
            oil_current = float(oil['Close'].iloc[-1])
            oil_prev = float(oil['Close'].iloc[0])
            oil_change = (oil_current / oil_prev - 1) * 100

            if oil_change > 5:
                conditions['oil'] = 'rising_oil'
            elif oil_change < -5:
                conditions['oil'] = 'falling_oil'
            else:
                conditions['oil'] = 'stable_oil'

            conditions['oil_change'] = oil_change
        except:
            conditions['oil'] = 'unknown'

        # 4. Interest rate proxy (TLT - bond prices inverse of rates)
        try:
            tlt = yf.download('TLT', period='30d', progress=False)
            if isinstance(tlt.columns, pd.MultiIndex):
                tlt.columns = tlt.columns.get_level_values(0)
            tlt_current = float(tlt['Close'].iloc[-1])
            tlt_prev = float(tlt['Close'].iloc[0])
            tlt_change = (tlt_current / tlt_prev - 1) * 100

            if tlt_change < -3:  # Bonds down = rates up
                conditions['rates'] = 'rising_rates'
            elif tlt_change > 3:  # Bonds up = rates down
                conditions['rates'] = 'falling_rates'
            else:
                conditions['rates'] = 'stable_rates'

            conditions['tlt_change'] = tlt_change
        except:
            conditions['rates'] = 'unknown'

        self.conditions = conditions
        return conditions

    def get_sector_momentum(self, lookback=20) -> Dict[str, float]:
        """Get momentum for each sector"""
        momentum = {}

        for sector, etf in self.SECTOR_ETFS.items():
            try:
                data = yf.download(etf, period='60d', progress=False)
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                closes = data['Close'].values
                if len(closes) >= lookback:
                    ret = (closes[-1] / closes[-lookback] - 1) * 100
                    momentum[sector] = ret
            except:
                continue

        return momentum

    def predict_best_sectors(self, n=3) -> List[Tuple[str, float]]:
        """Predict the best sectors based on conditions and momentum"""

        # Get current conditions
        conditions = self.analyze_market_conditions()
        momentum = self.get_sector_momentum()

        # Score each sector
        sector_scores = {sector: 0.0 for sector in self.SECTOR_ETFS.keys()}

        # Apply condition-based scoring
        for condition_key, condition_value in conditions.items():
            if condition_value in self.SECTOR_CONDITIONS:
                rules = self.SECTOR_CONDITIONS[condition_value]
                for sector in rules.get('best', []):
                    if sector in sector_scores:
                        sector_scores[sector] += 20
                for sector in rules.get('worst', []):
                    if sector in sector_scores:
                        sector_scores[sector] -= 15

        # Apply momentum scoring
        for sector, mom in momentum.items():
            if sector in sector_scores:
                # Momentum contributes to score but not too much
                sector_scores[sector] += mom * 2  # 1% momentum = 2 points

        # Sort and return top N
        ranked = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:n]

    def get_recommendations(self) -> Dict:
        """Get trading recommendations"""
        conditions = self.analyze_market_conditions()
        momentum = self.get_sector_momentum()
        best_sectors = self.predict_best_sectors(3)

        return {
            'timestamp': datetime.now().isoformat(),
            'conditions': conditions,
            'sector_momentum': momentum,
            'recommended_sectors': [
                {'sector': s, 'score': score} for s, score in best_sectors
            ],
            'reasoning': self._generate_reasoning(conditions, best_sectors),
        }

    def _generate_reasoning(self, conditions: Dict, best_sectors: List) -> str:
        """Generate human-readable reasoning"""
        reasons = []

        if conditions.get('vix') == 'high_vix':
            reasons.append(f"VIX is high ({conditions.get('vix_value', 0):.1f}) - favor defensive sectors")
        elif conditions.get('vix') == 'low_vix':
            reasons.append(f"VIX is low ({conditions.get('vix_value', 0):.1f}) - risk-on environment")

        if conditions.get('market') == 'bull_market':
            reasons.append("SPY is above MA50 - bull market favors growth sectors")
        else:
            reasons.append("SPY is below MA50 - bear market favors defensive sectors")

        if conditions.get('oil') == 'rising_oil':
            reasons.append(f"Oil prices rising ({conditions.get('oil_change', 0):+.1f}%) - energy may outperform")

        reasons.append(f"Top sectors: {', '.join([s for s, _ in best_sectors])}")

        return ' | '.join(reasons)


def main():
    """Main entry point"""
    print("="*70)
    print("NEWS-BASED SECTOR PREDICTOR")
    print("="*70)

    predictor = NewsSectorPredictor()
    recommendations = predictor.get_recommendations()

    print("\nCurrent Market Conditions:")
    conditions = recommendations['conditions']
    print(f"  VIX: {conditions.get('vix_value', 'N/A'):.1f} ({conditions.get('vix', 'N/A')})")
    print(f"  Market: {conditions.get('market', 'N/A')}")
    print(f"  Oil: {conditions.get('oil', 'N/A')} ({conditions.get('oil_change', 0):+.1f}%)")
    print(f"  Rates: {conditions.get('rates', 'N/A')}")

    print("\nSector Momentum (20-day):")
    momentum = recommendations['sector_momentum']
    for sector, mom in sorted(momentum.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int(abs(mom))
        sign = "+" if mom > 0 else ""
        print(f"  {sector:20s} {sign}{mom:5.1f}% {bar}")

    print("\nRecommended Sectors:")
    for i, rec in enumerate(recommendations['recommended_sectors'], 1):
        print(f"  {i}. {rec['sector']} (score: {rec['score']:.1f})")

    print(f"\nReasoning: {recommendations['reasoning']}")

    # Save recommendations
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'predictions')
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, 'sector_prediction.json')
    with open(output_file, 'w') as f:
        json.dump(recommendations, f, indent=2)

    print(f"\nSaved to: {output_file}")


if __name__ == '__main__':
    main()
