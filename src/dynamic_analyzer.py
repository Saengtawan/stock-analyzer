#!/usr/bin/env python3
"""
DYNAMIC ANALYZER - วิเคราะห์ลึกซึ้ง แต่ละหุ้น/sector มี pattern ต่างกัน

"ระบบแบบนี้มันต้อง dynamic เพราะทุกอย่างไม่ได้ตายตัว
 หุ้นแต่ละตัว แต่ละ sector มีรูปแบบของตัวมันเอง"

ระบบนี้:
1. เรียนรู้ pattern ของแต่ละ sector
2. ปรับ criteria ตาม sector
3. รู้ว่า sector ไหนดีในสภาวะตลาดแบบไหน
4. ปรับ position size ตาม confidence
5. Track performance แยกตาม sector
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None


@dataclass
class SectorProfile:
    """Profile ของแต่ละ sector"""
    name: str
    symbols: List[str]

    # Optimal parameters (learned from backtest)
    optimal_accum: float
    optimal_rsi_max: float
    optimal_atr_max: float

    # Performance metrics
    avg_return: float
    win_rate: float
    best_market_condition: str  # BULL, NEUTRAL, BEAR

    # Correlations
    spy_correlation: float
    vix_sensitivity: float


class DynamicAnalyzer:
    """
    Dynamic Stock Analyzer

    เรียนรู้และปรับตัวตาม:
    - Sector patterns
    - Market conditions
    - Historical performance
    """

    # Default sector profiles (จะถูก update จาก backtest)
    SECTOR_DEFAULTS = {
        'Industrial': {
            'symbols': ['CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT', 'MMM', 'UPS'],
            'optimal_accum': 1.3,
            'optimal_rsi_max': 55,
            'optimal_atr_max': 2.5,
            'best_market': 'BULL',
        },
        'Consumer': {
            'symbols': ['HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'DIS'],
            'optimal_accum': 1.2,
            'optimal_rsi_max': 58,
            'optimal_atr_max': 2.0,
            'best_market': 'BULL',
        },
        'Finance': {
            'symbols': ['JPM', 'BAC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BLK', 'SCHW'],
            'optimal_accum': 1.2,
            'optimal_rsi_max': 55,
            'optimal_atr_max': 2.5,
            'best_market': 'BULL',
        },
        'Healthcare': {
            'symbols': ['JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'AMGN', 'GILD'],
            'optimal_accum': 1.1,
            'optimal_rsi_max': 60,
            'optimal_atr_max': 2.0,
            'best_market': 'NEUTRAL',
        },
        'Tech': {
            'symbols': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD', 'CRM', 'ADBE'],
            'optimal_accum': 1.2,
            'optimal_rsi_max': 55,
            'optimal_atr_max': 3.0,
            'best_market': 'BULL',
        },
        'Semiconductor': {
            'symbols': ['NVDA', 'AMD', 'AVGO', 'MU', 'AMAT', 'LRCX'],
            'optimal_accum': 1.3,
            'optimal_rsi_max': 50,
            'optimal_atr_max': 3.5,
            'best_market': 'BULL',
        },
        'Defensive': {
            'symbols': ['JNJ', 'PG', 'KO', 'PEP', 'WMT', 'COST'],
            'optimal_accum': 1.1,
            'optimal_rsi_max': 60,
            'optimal_atr_max': 1.5,
            'best_market': 'BEAR',
        },
    }

    def __init__(self, data_dir: str = None):
        """Initialize"""
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(__file__), '..', 'data', 'dynamic'
        )
        os.makedirs(self.data_dir, exist_ok=True)

        self.profiles: Dict[str, SectorProfile] = {}
        self.performance_history: Dict[str, List] = {}
        self.market_state = None

        self._load_profiles()

    def _load_profiles(self):
        """Load or create sector profiles"""
        profile_file = os.path.join(self.data_dir, 'sector_profiles.json')

        if os.path.exists(profile_file):
            with open(profile_file, 'r') as f:
                data = json.load(f)
                for name, p in data.items():
                    self.profiles[name] = SectorProfile(**p)
        else:
            # Create default profiles
            for name, defaults in self.SECTOR_DEFAULTS.items():
                self.profiles[name] = SectorProfile(
                    name=name,
                    symbols=defaults['symbols'],
                    optimal_accum=defaults['optimal_accum'],
                    optimal_rsi_max=defaults['optimal_rsi_max'],
                    optimal_atr_max=defaults['optimal_atr_max'],
                    avg_return=0,
                    win_rate=50,
                    best_market_condition=defaults['best_market'],
                    spy_correlation=0.7,
                    vix_sensitivity=0.5,
                )

    def _save_profiles(self):
        """Save sector profiles"""
        profile_file = os.path.join(self.data_dir, 'sector_profiles.json')
        with open(profile_file, 'w') as f:
            json.dump({name: asdict(p) for name, p in self.profiles.items()}, f, indent=2)

    def learn_sector_patterns(self):
        """เรียนรู้ patterns ของแต่ละ sector จาก historical data"""
        print("=" * 70)
        print("LEARNING SECTOR PATTERNS")
        print("=" * 70)

        if yf is None:
            print("yfinance not available")
            return

        # Download market data
        print("\n1. Downloading market data...")
        end = datetime.now()
        start = end - timedelta(days=365)

        spy = yf.download('SPY', start=start, end=end, progress=False)
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = spy.columns.get_level_values(0)

        vix = yf.download('^VIX', start=start, end=end, progress=False)
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)

        # Learn each sector
        print("\n2. Learning sector patterns...")

        for sector_name, profile in self.profiles.items():
            print(f"\n   {sector_name}:")

            sector_returns = []
            sector_spy_corr = []

            for symbol in profile.symbols[:5]:  # Sample 5 stocks
                try:
                    df = yf.download(symbol, start=start, end=end, progress=False)
                    if df.empty:
                        continue
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)

                    # Calculate returns
                    returns = df['Close'].pct_change().dropna()
                    sector_returns.extend(returns.values)

                    # Calculate correlation with SPY
                    spy_returns = spy['Close'].pct_change().dropna()
                    min_len = min(len(returns), len(spy_returns))
                    if min_len > 20:
                        corr = np.corrcoef(returns[-min_len:], spy_returns[-min_len:])[0, 1]
                        sector_spy_corr.append(corr)

                except:
                    continue

            # Update profile
            if sector_returns:
                avg_ret = np.mean(sector_returns) * 252 * 100  # Annualized
                profile.avg_return = round(avg_ret, 2)

            if sector_spy_corr:
                profile.spy_correlation = round(np.mean(sector_spy_corr), 2)

            print(f"     Avg Annual Return: {profile.avg_return:.1f}%")
            print(f"     SPY Correlation: {profile.spy_correlation:.2f}")

        self._save_profiles()
        print("\n3. Profiles saved!")

    def get_current_market_state(self) -> Dict:
        """Get current market state"""
        state = {
            'condition': 'NEUTRAL',
            'spy_trend': 'FLAT',
            'vix_level': 'NORMAL',
            'recommended_sectors': [],
        }

        if yf is None:
            return state

        try:
            spy = yf.download('SPY', period='30d', progress=False)
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)

            price = float(spy['Close'].iloc[-1])
            ma20 = float(spy['Close'].tail(20).mean())

            if price > ma20 * 1.02:
                state['spy_trend'] = 'STRONG_UP'
                state['condition'] = 'BULL'
            elif price > ma20:
                state['spy_trend'] = 'UP'
                state['condition'] = 'BULL'
            elif price < ma20 * 0.98:
                state['spy_trend'] = 'STRONG_DOWN'
                state['condition'] = 'BEAR'
            else:
                state['spy_trend'] = 'DOWN'
                state['condition'] = 'NEUTRAL'

            vix = yf.download('^VIX', period='5d', progress=False)
            if isinstance(vix.columns, pd.MultiIndex):
                vix.columns = vix.columns.get_level_values(0)
            vix_val = float(vix['Close'].iloc[-1])

            if vix_val < 15:
                state['vix_level'] = 'LOW'
            elif vix_val < 20:
                state['vix_level'] = 'NORMAL'
            elif vix_val < 30:
                state['vix_level'] = 'HIGH'
                if state['condition'] == 'BULL':
                    state['condition'] = 'NEUTRAL'
            else:
                state['vix_level'] = 'EXTREME'
                state['condition'] = 'BEAR'

            # Recommend sectors based on condition
            for name, profile in self.profiles.items():
                if profile.best_market_condition == state['condition']:
                    state['recommended_sectors'].append(name)
                elif state['condition'] == 'NEUTRAL':
                    state['recommended_sectors'].append(name)

        except Exception as e:
            state['error'] = str(e)

        self.market_state = state
        return state

    def analyze_with_sector_rules(self, symbol: str, sector: str) -> Optional[Dict]:
        """วิเคราะห์หุ้นด้วย sector-specific rules"""
        if yf is None or sector not in self.profiles:
            return None

        profile = self.profiles[sector]

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='60d')

            if hist.empty or len(hist) < 55:
                return None

            closes = hist['Close'].values.flatten()
            volumes = hist['Volume'].values.flatten()
            highs = hist['High'].values.flatten()
            lows = hist['Low'].values.flatten()

            price = float(closes[-1])
            ma20 = float(np.mean(closes[-20:]))
            ma50 = float(np.mean(closes[-50:]))

            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100
            rsi = self._calc_rsi(closes)
            accum = self._calc_accumulation(closes, volumes)
            atr_pct = self._calc_atr_pct(closes, highs, lows)

            # Use SECTOR-SPECIFIC criteria
            if accum <= profile.optimal_accum:
                return None
            if rsi >= profile.optimal_rsi_max:
                return None
            if above_ma20 <= 0 or above_ma50 <= 0:
                return None
            if atr_pct > profile.optimal_atr_max:
                return None

            # Score based on how much it exceeds criteria
            score = 0
            reasons = []

            accum_excess = accum - profile.optimal_accum
            if accum_excess > 0.5:
                score += 30
                reasons.append(f"Strong accumulation ({accum:.2f})")
            elif accum_excess > 0.2:
                score += 20
                reasons.append(f"Good accumulation ({accum:.2f})")
            else:
                score += 10

            rsi_margin = profile.optimal_rsi_max - rsi
            if rsi_margin > 15:
                score += 25
                reasons.append(f"Ideal RSI ({rsi:.0f})")
            elif rsi_margin > 5:
                score += 15
            else:
                score += 5

            if atr_pct < profile.optimal_atr_max * 0.7:
                score += 20
                reasons.append(f"Low volatility ({atr_pct:.2f}%)")
            else:
                score += 10

            if above_ma20 > 5:
                score += 15
                reasons.append(f"Strong uptrend (+{above_ma20:.1f}%)")
            else:
                score += 5

            # Sector bonus
            if self.market_state and sector in self.market_state.get('recommended_sectors', []):
                score += 10
                reasons.append(f"Favored sector ({sector})")

            confidence = min(100, int(score * 1.1))

            return {
                'symbol': symbol,
                'sector': sector,
                'price': price,
                'confidence': confidence,
                'score': score,
                'reasons': reasons,
                'metrics': {
                    'rsi': round(rsi, 1),
                    'accum': round(accum, 2),
                    'atr_pct': round(atr_pct, 2),
                    'above_ma20': round(above_ma20, 2),
                },
                'sector_criteria': {
                    'optimal_accum': profile.optimal_accum,
                    'optimal_rsi': profile.optimal_rsi_max,
                    'optimal_atr': profile.optimal_atr_max,
                }
            }

        except:
            return None

    def find_best_stocks(self) -> List[Dict]:
        """Find best stocks using dynamic sector rules"""
        print("=" * 70)
        print("DYNAMIC STOCK FINDER")
        print("=" * 70)

        # Get market state
        print("\n1. Checking market state...")
        market = self.get_current_market_state()
        print(f"   Condition: {market['condition']}")
        print(f"   SPY Trend: {market['spy_trend']}")
        print(f"   VIX Level: {market['vix_level']}")
        print(f"   Recommended Sectors: {', '.join(market['recommended_sectors'])}")

        # Scan stocks
        print("\n2. Scanning stocks with sector-specific rules...")
        finds = []

        for sector_name in market['recommended_sectors']:
            if sector_name not in self.profiles:
                continue

            profile = self.profiles[sector_name]

            for symbol in profile.symbols:
                result = self.analyze_with_sector_rules(symbol, sector_name)
                if result and result['confidence'] >= 60:
                    finds.append(result)

        # Sort by confidence
        finds.sort(key=lambda x: x['confidence'], reverse=True)

        print(f"\n3. Found {len(finds)} stocks:")
        for f in finds[:10]:
            print(f"   {f['symbol']} ({f['sector']}): {f['confidence']}%")
            for r in f['reasons'][:2]:
                print(f"     + {r}")

        # Save results
        self._save_results(finds)

        return finds

    def _save_results(self, finds: List[Dict]):
        """Save results"""
        results_file = os.path.join(self.data_dir, 'dynamic_picks.json')
        with open(results_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'market_state': self.market_state,
                'picks': finds,
            }, f, indent=2)

        # Readable version
        txt_file = os.path.join(self.data_dir, 'DYNAMIC_PICKS.txt')
        with open(txt_file, 'w') as f:
            f.write(f"DYNAMIC STOCK PICKS - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Market: {self.market_state['condition']}\n")
            f.write(f"Recommended: {', '.join(self.market_state['recommended_sectors'])}\n\n")

            for i, pick in enumerate(finds[:20], 1):
                f.write(f"{i}. {pick['symbol']} ({pick['sector']}) - {pick['confidence']}%\n")
                for r in pick['reasons']:
                    f.write(f"   + {r}\n")
                f.write("\n")

    # Calculation helpers
    def _calc_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calc_accumulation(self, closes, volumes, period=20):
        if len(closes) < period:
            return 1.0
        up_vol, down_vol = 0.0, 0.0
        for i in range(-period+1, 0):
            if closes[i] > closes[i-1]:
                up_vol += volumes[i]
            elif closes[i] < closes[i-1]:
                down_vol += volumes[i]
        return up_vol / down_vol if down_vol > 0 else 3.0

    def _calc_atr_pct(self, closes, highs, lows, period=14):
        if len(closes) < period + 1:
            return 5.0
        tr = []
        for i in range(-period, 0):
            tr.append(max(
                float(highs[i]) - float(lows[i]),
                abs(float(highs[i]) - float(closes[i-1])),
                abs(float(lows[i]) - float(closes[i-1]))
            ))
        atr = np.mean(tr)
        price = float(closes[-1])
        return (atr / price) * 100 if price > 0 else 5.0


def main():
    """Main entry point"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                   DYNAMIC ANALYZER                           ║
║   วิเคราะห์ลึกซึ้ง แต่ละ sector มี pattern ต่างกัน          ║
╚══════════════════════════════════════════════════════════════╝
""")

    analyzer = DynamicAnalyzer()

    # Learn patterns first
    # analyzer.learn_sector_patterns()

    # Find best stocks
    picks = analyzer.find_best_stocks()

    if picks:
        print(f"\nResults saved to: {analyzer.data_dir}")


if __name__ == '__main__':
    main()
