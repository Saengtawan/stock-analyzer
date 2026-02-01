#!/usr/bin/env python3
"""
COMPLETE ANALYZER - 12-Step Analysis System

ครบทุกขั้นตอน:
1. Global Macro
2. Market Sentiment
3. Economic Cycle
4. Sector Rotation
5. Theme/Trend
6. Stock Filtering
7. Catalyst Check
8. Technical Analysis
9. Entry Timing
10. Position Sizing
11. Execution
12. Position Management
"""

import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'database', 'stocks.db')


@dataclass
class AnalysisResult:
    """Result of each analysis step"""
    step: int
    name: str
    passed: bool
    score: float
    signal: str
    details: Dict
    recommendation: str


class CompleteAnalyzer:
    """Complete 12-Step Analysis System"""

    def __init__(self, portfolio_value: float = 100000):
        self.portfolio_value = portfolio_value
        self.db_path = DB_PATH
        self.results = []

    def run_all_steps(self) -> Dict:
        """Run all 12 analysis steps"""
        print("="*70)
        print("🎯 COMPLETE 12-STEP ANALYSIS SYSTEM")
        print("="*70)
        print(f"Portfolio: ${self.portfolio_value:,.2f}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)

        self.results = []
        final_picks = []

        # Step 1: Global Macro
        step1 = self.step1_global_macro()
        self.results.append(step1)
        self._print_step_result(step1)

        if not step1.passed and step1.signal == 'RISK-OFF':
            return self._generate_final_report(final_picks)

        # Step 2: Market Sentiment
        step2 = self.step2_market_sentiment()
        self.results.append(step2)
        self._print_step_result(step2)

        if not step2.passed and step2.score < 30:
            return self._generate_final_report(final_picks)

        # Step 3: Economic Cycle
        step3 = self.step3_economic_cycle()
        self.results.append(step3)
        self._print_step_result(step3)

        # Step 4: Sector Rotation
        step4 = self.step4_sector_rotation(step3.details.get('recommended_sectors', []))
        self.results.append(step4)
        self._print_step_result(step4)

        if not step4.details.get('top_sectors'):
            return self._generate_final_report(final_picks)

        # Step 5: Theme/Trend
        step5 = self.step5_theme_identification()
        self.results.append(step5)
        self._print_step_result(step5)

        # Step 6: Stock Filtering
        step6 = self.step6_stock_filtering(step4.details['top_sectors'])
        self.results.append(step6)
        self._print_step_result(step6)

        if not step6.details.get('filtered_stocks'):
            return self._generate_final_report(final_picks)

        # Step 7: Catalyst Check
        step7 = self.step7_catalyst_check(step6.details['filtered_stocks'])
        self.results.append(step7)
        self._print_step_result(step7)

        # Step 8: Technical Analysis
        step8 = self.step8_technical_analysis(step7.details.get('stocks_with_catalysts', []))
        self.results.append(step8)
        self._print_step_result(step8)

        if not step8.details.get('technical_ready'):
            return self._generate_final_report(final_picks)

        # Step 9: Entry Timing
        step9 = self.step9_entry_timing(step8.details['technical_ready'])
        self.results.append(step9)
        self._print_step_result(step9)

        # Step 10: Position Sizing
        step10 = self.step10_position_sizing(step9.details.get('entry_ready', []))
        self.results.append(step10)
        self._print_step_result(step10)

        final_picks = step10.details.get('final_picks', [])

        # Steps 11 & 12 are execution and management (not analysis)
        step11 = self.step11_execution_prep(final_picks)
        self.results.append(step11)
        self._print_step_result(step11)

        step12 = self.step12_management_rules(final_picks)
        self.results.append(step12)
        self._print_step_result(step12)

        return self._generate_final_report(final_picks)

    def step1_global_macro(self) -> AnalysisResult:
        """Step 1: Analyze global macro conditions"""
        print("\n" + "="*60)
        print("📊 STEP 1: GLOBAL MACRO")
        print("="*60)

        indicators = {}
        score = 50  # Start neutral

        if yf:
            tickers = {
                '^VIX': 'vix',
                '^TNX': 'yield_10y',
                'DX-Y.NYB': 'dollar',
                'CL=F': 'oil',
                'GC=F': 'gold',
            }

            for ticker, name in tickers.items():
                try:
                    data = yf.Ticker(ticker)
                    hist = data.history(period='1mo')
                    if len(hist) > 0:
                        current = hist['Close'].iloc[-1]
                        prev = hist['Close'].iloc[-5] if len(hist) > 5 else current
                        change = (current / prev - 1) * 100
                        indicators[name] = {'value': current, 'change': change}
                except:
                    pass

        # Scoring
        vix = indicators.get('vix', {}).get('value', 20)
        if vix < 15:
            score += 20
            signal = 'RISK-ON'
        elif vix < 20:
            score += 10
            signal = 'NEUTRAL'
        elif vix < 25:
            score -= 10
            signal = 'CAUTIOUS'
        else:
            score -= 30
            signal = 'RISK-OFF'

        yield_10y = indicators.get('yield_10y', {}).get('value', 4)
        if yield_10y > 5:
            score -= 15
        elif yield_10y < 3.5:
            score += 10

        dollar = indicators.get('dollar', {}).get('value', 100)
        if dollar > 105:
            score -= 10
        elif dollar < 95:
            score += 5

        passed = score >= 40 and signal != 'RISK-OFF'

        return AnalysisResult(
            step=1,
            name="Global Macro",
            passed=passed,
            score=score,
            signal=signal,
            details=indicators,
            recommendation=f"VIX={vix:.1f}, Signal={signal}"
        )

    def step2_market_sentiment(self) -> AnalysisResult:
        """Step 2: Analyze market sentiment"""
        print("\n" + "="*60)
        print("📊 STEP 2: MARKET SENTIMENT")
        print("="*60)

        sentiment = {}
        score = 50

        if yf:
            # Get market breadth from major indices
            try:
                spy = yf.Ticker('SPY')
                spy_hist = spy.history(period='1mo')

                if len(spy_hist) > 0:
                    # Calculate momentum
                    closes = spy_hist['Close'].values
                    spy_mom_5d = (closes[-1] / closes[-5] - 1) * 100 if len(closes) > 5 else 0
                    spy_mom_20d = (closes[-1] / closes[-20] - 1) * 100 if len(closes) > 20 else 0

                    sentiment['spy_momentum_5d'] = spy_mom_5d
                    sentiment['spy_momentum_20d'] = spy_mom_20d

                    if spy_mom_5d > 2:
                        score += 15
                    elif spy_mom_5d > 0:
                        score += 5
                    elif spy_mom_5d < -2:
                        score -= 15

                    if spy_mom_20d > 5:
                        score += 10
                    elif spy_mom_20d < -5:
                        score -= 10

            except:
                pass

        # Determine sentiment level
        if score >= 70:
            signal = 'GREEDY'
            recommendation = 'ระวัง - อาจ over-extended'
        elif score >= 50:
            signal = 'HEALTHY'
            recommendation = 'ดี - สามารถซื้อได้'
        elif score >= 30:
            signal = 'CAUTIOUS'
            recommendation = 'ระวัง - ลดขนาด position'
        else:
            signal = 'FEARFUL'
            recommendation = 'ไม่ซื้อ - รอ sentiment ดีขึ้น'

        passed = score >= 40

        return AnalysisResult(
            step=2,
            name="Market Sentiment",
            passed=passed,
            score=score,
            signal=signal,
            details=sentiment,
            recommendation=recommendation
        )

    def step3_economic_cycle(self) -> AnalysisResult:
        """Step 3: Determine economic cycle phase"""
        print("\n" + "="*60)
        print("📊 STEP 3: ECONOMIC CYCLE")
        print("="*60)

        # Based on current indicators (simplified)
        # In production, would use PMI, GDP, unemployment, etc.

        cycle_indicators = {}

        if yf:
            try:
                # Use sector performance as proxy for cycle
                sector_etfs = {'XLF': 'financials', 'XLK': 'tech', 'XLE': 'energy', 'XLV': 'healthcare'}

                for etf, name in sector_etfs.items():
                    ticker = yf.Ticker(etf)
                    hist = ticker.history(period='3mo')
                    if len(hist) > 0:
                        mom = (hist['Close'].iloc[-1] / hist['Close'].iloc[0] - 1) * 100
                        cycle_indicators[name] = mom
            except:
                pass

        # Determine cycle based on sector leadership
        tech_mom = cycle_indicators.get('tech', 0)
        fin_mom = cycle_indicators.get('financials', 0)
        energy_mom = cycle_indicators.get('energy', 0)
        health_mom = cycle_indicators.get('healthcare', 0)

        if fin_mom > tech_mom and fin_mom > energy_mom:
            cycle = 'EARLY_EXPANSION'
            recommended_sectors = ['Financials', 'Technology', 'Consumer_Discretionary']
        elif tech_mom > energy_mom and tech_mom > health_mom:
            cycle = 'MID_EXPANSION'
            recommended_sectors = ['Technology', 'Semiconductors', 'Industrials']
        elif energy_mom > tech_mom and energy_mom > health_mom:
            cycle = 'LATE_EXPANSION'
            recommended_sectors = ['Energy', 'Materials', 'Industrials']
        else:
            cycle = 'MIXED'
            recommended_sectors = ['Healthcare', 'Utilities', 'Consumer_Staples']

        return AnalysisResult(
            step=3,
            name="Economic Cycle",
            passed=True,
            score=70,
            signal=cycle,
            details={'cycle_indicators': cycle_indicators, 'recommended_sectors': recommended_sectors},
            recommendation=f"Cycle: {cycle}, Focus: {', '.join(recommended_sectors[:2])}"
        )

    def step4_sector_rotation(self, cycle_sectors: List[str]) -> AnalysisResult:
        """Step 4: Identify best sectors"""
        print("\n" + "="*60)
        print("📊 STEP 4: SECTOR ROTATION")
        print("="*60)

        sector_etfs = {
            'Technology': 'XLK',
            'Healthcare': 'XLV',
            'Financials': 'XLF',
            'Consumer_Discretionary': 'XLY',
            'Consumer_Staples': 'XLP',
            'Energy': 'XLE',
            'Industrials': 'XLI',
            'Materials': 'XLB',
            'Utilities': 'XLU',
            'Semiconductors': 'SMH',
            'Banks': 'KBE',
        }

        sectors = []

        if yf:
            for sector, etf in sector_etfs.items():
                try:
                    ticker = yf.Ticker(etf)
                    hist = ticker.history(period='3mo')

                    if len(hist) >= 20:
                        closes = hist['Close'].values
                        mom_5d = (closes[-1] / closes[-5] - 1) * 100
                        mom_20d = (closes[-1] / closes[-20] - 1) * 100

                        # RSI
                        deltas = np.diff(closes[-15:])
                        gains = np.where(deltas > 0, deltas, 0)
                        losses = np.where(deltas < 0, -deltas, 0)
                        rsi = 100 - (100 / (1 + np.mean(gains) / np.mean(losses))) if np.mean(losses) > 0 else 50

                        # Score
                        score = 0
                        score += min(30, mom_5d * 5)
                        score += min(30, mom_20d * 2)
                        if sector in cycle_sectors:
                            score += 20

                        sectors.append({
                            'sector': sector,
                            'etf': etf,
                            'momentum_5d': mom_5d,
                            'momentum_20d': mom_20d,
                            'rsi': rsi,
                            'score': score,
                        })
                except:
                    pass

        sectors.sort(key=lambda x: x['score'], reverse=True)
        top_sectors = [s['sector'] for s in sectors[:3]]

        print(f"\nTop Sectors: {', '.join(top_sectors)}")

        return AnalysisResult(
            step=4,
            name="Sector Rotation",
            passed=len(top_sectors) > 0,
            score=sectors[0]['score'] if sectors else 0,
            signal=top_sectors[0] if top_sectors else 'NONE',
            details={'all_sectors': sectors, 'top_sectors': top_sectors},
            recommendation=f"Focus: {', '.join(top_sectors)}"
        )

    def step5_theme_identification(self) -> AnalysisResult:
        """Step 5: Identify hot themes"""
        print("\n" + "="*60)
        print("📊 STEP 5: THEME/TREND IDENTIFICATION")
        print("="*60)

        # Major themes and their proxy stocks
        themes = {
            'AI/ML': ['NVDA', 'AMD', 'MSFT', 'GOOGL'],
            'EV': ['TSLA', 'RIVN', 'LI'],
            'Cybersecurity': ['CRWD', 'PANW', 'ZS'],
            'Obesity_Drugs': ['LLY', 'NVO'],
            'Data_Centers': ['EQIX', 'DLR'],
        }

        theme_scores = {}

        if yf:
            for theme, stocks in themes.items():
                momentums = []
                for symbol in stocks[:2]:  # Sample 2 stocks per theme
                    try:
                        ticker = yf.Ticker(symbol)
                        hist = ticker.history(period='1mo')
                        if len(hist) > 5:
                            mom = (hist['Close'].iloc[-1] / hist['Close'].iloc[-20] - 1) * 100 if len(hist) > 20 else 0
                            momentums.append(mom)
                    except:
                        pass

                if momentums:
                    theme_scores[theme] = np.mean(momentums)

        # Rank themes
        hot_themes = sorted(theme_scores.items(), key=lambda x: x[1], reverse=True)[:3]

        print(f"Hot Themes: {', '.join([t[0] for t in hot_themes])}")

        return AnalysisResult(
            step=5,
            name="Theme Identification",
            passed=len(hot_themes) > 0,
            score=hot_themes[0][1] if hot_themes else 0,
            signal=hot_themes[0][0] if hot_themes else 'NONE',
            details={'theme_scores': dict(hot_themes)},
            recommendation=f"Hot: {hot_themes[0][0] if hot_themes else 'None'}"
        )

    def step6_stock_filtering(self, top_sectors: List[str]) -> AnalysisResult:
        """Step 6: Filter stock universe"""
        print("\n" + "="*60)
        print("📊 STEP 6: STOCK FILTERING")
        print("="*60)

        conn = sqlite3.connect(self.db_path)

        # Map top sectors to database sectors
        sector_mapping = {
            'Technology': ['Technology'],
            'Semiconductors': ['Semiconductors'],
            'Financials': ['Finance_Banks', 'Finance_Insurance', 'Finance_Diversified'],
            'Banks': ['Finance_Banks'],
            'Healthcare': ['Healthcare_Pharma', 'Healthcare_MedDevices'],
            'Energy': ['Energy_Oil', 'Energy_Midstream'],
            'Industrials': ['Industrial_Machinery', 'Industrial_Aerospace'],
            'Materials': ['Materials_Chemicals', 'Materials_Metals'],
            'Consumer_Staples': ['Consumer_Staples', 'Consumer_Food'],
            'Consumer_Discretionary': ['Consumer_Retail', 'Consumer_Auto'],
            'Utilities': ['Utilities_Electric', 'Utilities_Gas'],
        }

        db_sectors = []
        for sector in top_sectors:
            db_sectors.extend(sector_mapping.get(sector, [sector]))

        # Get stocks from these sectors
        placeholders = ','.join(['?' for _ in db_sectors])
        cursor = conn.execute(f"""
            SELECT DISTINCT symbol, sector FROM stock_prices
            WHERE sector IN ({placeholders})
        """, db_sectors)

        stocks = [(row[0], row[1]) for row in cursor.fetchall()]

        filtered = []

        for symbol, sector in stocks[:100]:  # Limit for speed
            try:
                df = pd.read_sql("""
                    SELECT date, close, high, low, volume FROM stock_prices
                    WHERE symbol = ?
                    ORDER BY date DESC
                    LIMIT 60
                """, conn, params=(symbol,))

                if len(df) < 30:
                    continue

                closes = df['close'].values[::-1]
                highs = df['high'].values[::-1]
                lows = df['low'].values[::-1]
                volumes = df['volume'].values[::-1]

                price = closes[-1]

                # Filters
                if price < 10:  # Min price
                    continue

                # Momentum
                mom_5d = (closes[-1] / closes[-5] - 1) * 100
                if mom_5d < 1 or mom_5d > 12:
                    continue

                # ATR%
                tr = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(-14, 0)]
                atr_pct = (np.mean(tr) / price) * 100
                if atr_pct > 3:
                    continue

                # MA20
                ma20 = np.mean(closes[-20:])
                if price < ma20:
                    continue

                # RSI
                deltas = np.diff(closes[-15:])
                rsi = 100 - (100 / (1 + np.mean(np.where(deltas > 0, deltas, 0)) / np.mean(np.where(deltas < 0, -deltas, 0)))) if np.mean(np.where(deltas < 0, -deltas, 0)) > 0 else 50
                if rsi > 70:
                    continue

                filtered.append({
                    'symbol': symbol,
                    'sector': sector,
                    'price': price,
                    'momentum_5d': mom_5d,
                    'atr_pct': atr_pct,
                    'rsi': rsi,
                })

            except:
                continue

        conn.close()

        print(f"Filtered: {len(filtered)} stocks from {len(stocks)} universe")

        return AnalysisResult(
            step=6,
            name="Stock Filtering",
            passed=len(filtered) > 0,
            score=len(filtered),
            signal=f"{len(filtered)} stocks",
            details={'filtered_stocks': filtered},
            recommendation=f"{len(filtered)} stocks passed filters"
        )

    def step7_catalyst_check(self, stocks: List[Dict]) -> AnalysisResult:
        """Step 7: Check for catalysts"""
        print("\n" + "="*60)
        print("📊 STEP 7: CATALYST CHECK")
        print("="*60)

        stocks_with_catalysts = []

        for stock in stocks[:30]:  # Limit for speed
            symbol = stock['symbol']
            catalysts = []
            catalyst_score = 0

            if yf:
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period='1mo')

                    if len(hist) > 5:
                        # Check for technical catalysts
                        closes = hist['Close'].values
                        volumes = hist['Volume'].values

                        # Volume surge
                        vol_avg = np.mean(volumes[-20:-1]) if len(volumes) > 20 else np.mean(volumes[:-1])
                        vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1
                        if vol_ratio > 1.5:
                            catalysts.append('VOLUME_SURGE')
                            catalyst_score += 10

                        # Gap up
                        gap = (hist['Open'].iloc[-1] / closes[-2] - 1) * 100 if len(closes) > 1 else 0
                        if gap > 2:
                            catalysts.append('GAP_UP')
                            catalyst_score += 10

                        # Breakout
                        recent_high = max(closes[-20:-1]) if len(closes) > 20 else max(closes[:-1])
                        if closes[-1] > recent_high:
                            catalysts.append('BREAKOUT')
                            catalyst_score += 15

                        # Near 52W high
                        high_52w = max(closes)
                        if closes[-1] / high_52w > 0.95:
                            catalysts.append('NEAR_52W_HIGH')
                            catalyst_score += 5

                except:
                    pass

            if catalysts:
                stock_copy = stock.copy()
                stock_copy['catalysts'] = catalysts
                stock_copy['catalyst_score'] = catalyst_score
                stocks_with_catalysts.append(stock_copy)

        stocks_with_catalysts.sort(key=lambda x: x['catalyst_score'], reverse=True)

        print(f"Stocks with catalysts: {len(stocks_with_catalysts)}")

        return AnalysisResult(
            step=7,
            name="Catalyst Check",
            passed=len(stocks_with_catalysts) > 0,
            score=stocks_with_catalysts[0]['catalyst_score'] if stocks_with_catalysts else 0,
            signal=f"{len(stocks_with_catalysts)} with catalysts",
            details={'stocks_with_catalysts': stocks_with_catalysts},
            recommendation=f"Top: {stocks_with_catalysts[0]['symbol'] if stocks_with_catalysts else 'None'}"
        )

    def step8_technical_analysis(self, stocks: List[Dict]) -> AnalysisResult:
        """Step 8: Technical analysis"""
        print("\n" + "="*60)
        print("📊 STEP 8: TECHNICAL ANALYSIS")
        print("="*60)

        technical_ready = []

        for stock in stocks[:20]:
            symbol = stock['symbol']
            tech_score = 0

            if yf:
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period='3mo')

                    if len(hist) >= 50:
                        closes = hist['Close'].values
                        volumes = hist['Volume'].values

                        price = closes[-1]
                        ma20 = np.mean(closes[-20:])
                        ma50 = np.mean(closes[-50:])

                        # Trend score
                        if price > ma20 > ma50:
                            tech_score += 30
                        elif price > ma20:
                            tech_score += 15

                        # RSI score
                        deltas = np.diff(closes[-15:])
                        rsi = 100 - (100 / (1 + np.mean(np.where(deltas > 0, deltas, 0)) / np.mean(np.where(deltas < 0, -deltas, 0)))) if np.mean(np.where(deltas < 0, -deltas, 0)) > 0 else 50
                        if 40 < rsi < 60:
                            tech_score += 20
                        elif 35 < rsi < 65:
                            tech_score += 10

                        # Volume score
                        vol_avg = np.mean(volumes[-20:])
                        if volumes[-1] > vol_avg:
                            tech_score += 15

                        if tech_score >= 40:
                            stock_copy = stock.copy()
                            stock_copy['tech_score'] = tech_score
                            stock_copy['rsi'] = rsi
                            stock_copy['above_ma20'] = (price / ma20 - 1) * 100
                            technical_ready.append(stock_copy)

                except:
                    pass

        technical_ready.sort(key=lambda x: x['tech_score'], reverse=True)

        print(f"Technical ready: {len(technical_ready)}")

        return AnalysisResult(
            step=8,
            name="Technical Analysis",
            passed=len(technical_ready) > 0,
            score=technical_ready[0]['tech_score'] if technical_ready else 0,
            signal=f"{len(technical_ready)} ready",
            details={'technical_ready': technical_ready},
            recommendation=f"Top: {technical_ready[0]['symbol'] if technical_ready else 'None'}"
        )

    def step9_entry_timing(self, stocks: List[Dict]) -> AnalysisResult:
        """Step 9: Determine entry timing"""
        print("\n" + "="*60)
        print("📊 STEP 9: ENTRY TIMING")
        print("="*60)

        entry_ready = []

        for stock in stocks[:10]:
            stock_copy = stock.copy()

            price = stock['price']

            # Determine entry strategy
            above_ma = stock.get('above_ma20', 0)

            if 0 < above_ma < 3:
                stock_copy['entry_strategy'] = 'BUY_NOW'
                stock_copy['entry_price'] = price
            elif above_ma >= 3:
                stock_copy['entry_strategy'] = 'WAIT_PULLBACK'
                stock_copy['entry_price'] = price * 0.98  # Wait for 2% pullback
            else:
                stock_copy['entry_strategy'] = 'WAIT_BREAKOUT'
                stock_copy['entry_price'] = price * 1.01  # Wait for 1% breakout

            stock_copy['stop_price'] = stock_copy['entry_price'] * 0.97  # -3%
            stock_copy['target_price'] = stock_copy['entry_price'] * 1.08  # +8%

            entry_ready.append(stock_copy)

        print(f"Entry ready: {len(entry_ready)}")

        return AnalysisResult(
            step=9,
            name="Entry Timing",
            passed=len(entry_ready) > 0,
            score=len(entry_ready),
            signal=entry_ready[0]['entry_strategy'] if entry_ready else 'NONE',
            details={'entry_ready': entry_ready},
            recommendation=f"Top: {entry_ready[0]['symbol']} @ {entry_ready[0]['entry_strategy']}" if entry_ready else 'None'
        )

    def step10_position_sizing(self, stocks: List[Dict]) -> AnalysisResult:
        """Step 10: Calculate position sizes"""
        print("\n" + "="*60)
        print("📊 STEP 10: POSITION SIZING")
        print("="*60)

        final_picks = []
        max_risk_per_trade = 0.015  # 1.5%
        max_position_pct = 0.15  # 15%

        for stock in stocks[:5]:
            stock_copy = stock.copy()

            entry_price = stock['entry_price']
            stop_price = stock['stop_price']

            # Risk per share
            risk_per_share = entry_price - stop_price

            # Position size based on risk
            max_risk_amount = self.portfolio_value * max_risk_per_trade
            shares_by_risk = int(max_risk_amount / risk_per_share) if risk_per_share > 0 else 0

            # Max position limit
            max_position_value = self.portfolio_value * max_position_pct
            shares_by_position = int(max_position_value / entry_price)

            # Take minimum
            shares = min(shares_by_risk, shares_by_position)

            if shares > 0:
                stock_copy['shares'] = shares
                stock_copy['position_value'] = shares * entry_price
                stock_copy['risk_amount'] = shares * risk_per_share
                stock_copy['position_pct'] = (shares * entry_price) / self.portfolio_value * 100

                final_picks.append(stock_copy)

        print(f"Final picks: {len(final_picks)}")

        return AnalysisResult(
            step=10,
            name="Position Sizing",
            passed=len(final_picks) > 0,
            score=len(final_picks),
            signal=f"{len(final_picks)} positions",
            details={'final_picks': final_picks},
            recommendation=f"{len(final_picks)} ready to execute"
        )

    def step11_execution_prep(self, picks: List[Dict]) -> AnalysisResult:
        """Step 11: Execution preparation"""
        print("\n" + "="*60)
        print("📊 STEP 11: EXECUTION PREP")
        print("="*60)

        orders = []

        for pick in picks:
            order = {
                'symbol': pick['symbol'],
                'action': 'BUY',
                'shares': pick['shares'],
                'order_type': 'LIMIT' if pick['entry_strategy'] == 'BUY_NOW' else 'STOP_LIMIT',
                'limit_price': pick['entry_price'],
                'stop_loss': pick['stop_price'],
                'target': pick['target_price'],
            }
            orders.append(order)

            print(f"  {order['symbol']}: {order['action']} {order['shares']} shares @ ${order['limit_price']:.2f}")

        return AnalysisResult(
            step=11,
            name="Execution Prep",
            passed=len(orders) > 0,
            score=len(orders),
            signal=f"{len(orders)} orders",
            details={'orders': orders},
            recommendation="Ready to execute"
        )

    def step12_management_rules(self, picks: List[Dict]) -> AnalysisResult:
        """Step 12: Position management rules"""
        print("\n" + "="*60)
        print("📊 STEP 12: MANAGEMENT RULES")
        print("="*60)

        rules = {
            'stop_loss': 'Exit if price hits stop (-3%)',
            'target': 'Take profit at target (+8%)',
            'trailing_stop': 'After +3% profit, trail stop at breakeven',
            'time_stop': 'Review if no movement after 5 days',
            'thesis_broken': 'Exit if catalyst fails or sector rotates',
        }

        for rule, description in rules.items():
            print(f"  • {rule}: {description}")

        return AnalysisResult(
            step=12,
            name="Management Rules",
            passed=True,
            score=100,
            signal="Rules Set",
            details={'rules': rules},
            recommendation="Follow the rules!"
        )

    def _print_step_result(self, result: AnalysisResult):
        """Print step result"""
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"\n{status} | Score: {result.score:.0f} | Signal: {result.signal}")
        print(f"Recommendation: {result.recommendation}")

    def _generate_final_report(self, picks: List[Dict]) -> Dict:
        """Generate final report"""
        print("\n" + "="*70)
        print("🏁 FINAL REPORT")
        print("="*70)

        steps_passed = sum(1 for r in self.results if r.passed)
        total_steps = len(self.results)

        print(f"\nSteps Passed: {steps_passed}/{total_steps}")

        if picks:
            print(f"\n📋 TOP PICKS:")
            print("-"*80)
            print(f"{'Symbol':<8} {'Entry':>10} {'Stop':>10} {'Target':>10} {'Shares':>8} {'Risk$':>10}")
            print("-"*80)

            for pick in picks:
                print(f"{pick['symbol']:<8} ${pick['entry_price']:>9.2f} ${pick['stop_price']:>9.2f} ${pick['target_price']:>9.2f} {pick['shares']:>8} ${pick['risk_amount']:>9.2f}")

            print("-"*80)
        else:
            print("\n⚠️ No picks - conditions not favorable")

        # Save report
        report = {
            'timestamp': datetime.now().isoformat(),
            'steps_passed': steps_passed,
            'total_steps': total_steps,
            'results': [{'step': r.step, 'name': r.name, 'passed': r.passed, 'score': r.score, 'signal': r.signal} for r in self.results],
            'picks': picks,
        }

        report_path = os.path.join(DATA_DIR, 'predictions', 'complete_analysis.json')
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        print(f"\n✅ Report saved to: {report_path}")

        return report


def main():
    """Main entry point"""
    analyzer = CompleteAnalyzer(portfolio_value=100000)
    report = analyzer.run_all_steps()


if __name__ == '__main__':
    main()
