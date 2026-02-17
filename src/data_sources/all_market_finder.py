#!/usr/bin/env python3
"""
ALL MARKET FINDER - หาหุ้นได้ทุกสภาวะตลาด

"แม้วันที่แย่ที่สุดมันต้องมีหุ้นที่ราคาขึ้นบ้าง
 เพราะไม่งั้นมันคงพังกันทั้งระบบ"

ระบบนี้หาหุ้นที่ดีได้ทุกสภาวะ:
- ตลาดขึ้น: หา momentum stocks
- ตลาดลง: หา defensive stocks, หุ้นที่สวนตลาด
- ตลาดผันผวน: หา low volatility stocks

ทำงานอัตโนมัติ 24/7
"""

import os
import sys
import json
import time
import signal
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None


@dataclass
class StockPick:
    """หุ้นที่ถูกเลือก"""
    symbol: str
    sector: str
    strategy: str  # MOMENTUM, DEFENSIVE, CONTRARIAN, LOW_VOL
    price: float
    score: float
    reasons: List[str]
    metrics: Dict


class AllMarketFinder:
    """
    หาหุ้นได้ทุกสภาวะตลาด

    Strategies:
    1. MOMENTUM - ตลาดขาขึ้น, หุ้นแข็งแรง
    2. DEFENSIVE - ตลาดขาลง, หุ้นปลอดภัย
    3. CONTRARIAN - หุ้นที่สวนตลาด
    4. LOW_VOL - หุ้นผันผวนต่ำ ปลอดภัย
    """

    # ===== COMPLETE UNIVERSE =====
    UNIVERSE = {
        # GROWTH (for bull markets)
        'Growth': [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
            'AMD', 'CRM', 'ADBE', 'NFLX', 'SQ', 'SHOP', 'SNOW',
        ],
        # DEFENSIVE (for bear markets)
        'Defensive': [
            'JNJ', 'PG', 'KO', 'PEP', 'WMT', 'COST',
            'VZ', 'T', 'D', 'SO', 'DUK',
            'MCD', 'CL', 'K', 'GIS',
        ],
        # VALUE (for all markets)
        'Value': [
            'JPM', 'BAC', 'WFC', 'BRK-B',
            'XOM', 'CVX', 'MRK', 'PFE',
            'CAT', 'HON', 'MMM', 'UPS',
        ],
        # DIVIDEND (for income)
        'Dividend': [
            'O', 'VZ', 'T', 'MO', 'PM', 'IBM',
            'XOM', 'CVX', 'JNJ', 'PG', 'KO',
        ],
        # SEMICONDUCTORS
        'Semiconductors': [
            'NVDA', 'AMD', 'INTC', 'QCOM', 'AVGO',
            'MU', 'AMAT', 'LRCX', 'TSM', 'ASML',
        ],
        # FINANCIALS
        'Financials': [
            'JPM', 'BAC', 'WFC', 'GS', 'MS',
            'V', 'MA', 'AXP', 'BLK', 'SCHW',
        ],
        # HEALTHCARE
        'Healthcare': [
            'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY',
            'AMGN', 'GILD', 'BMY', 'CVS',
        ],
        # CONSUMER
        'Consumer': [
            'HD', 'LOW', 'COST', 'WMT', 'TGT',
            'MCD', 'SBUX', 'NKE', 'DIS',
        ],
        # INDUSTRIAL
        'Industrial': [
            'CAT', 'DE', 'HON', 'GE', 'BA',
            'UNP', 'UPS', 'FDX', 'LMT', 'RTX',
        ],
        # ENERGY
        'Energy': [
            'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'OXY',
        ],
    }

    def __init__(self):
        """Initialize"""
        self.output_dir = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'all_market'
        )
        os.makedirs(self.output_dir, exist_ok=True)

        self.running = False
        self.market_state = None
        self.picks: List[StockPick] = []

    def run(self, max_cycles: int = None):
        """Run continuously"""
        self.running = True
        cycle = 0

        # v6.21: Use safe_signal to prevent errors in background threads
        from utils.safe_signal import safe_signal_install
        safe_signal_install(signal.SIGINT, lambda s, f: setattr(self, 'running', False))

        print("=" * 70)
        print("ALL MARKET FINDER - WORKS IN ANY MARKET CONDITION")
        print("=" * 70)

        while self.running:
            cycle += 1
            print(f"\n{'='*50}")
            print(f"CYCLE {cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            print(f"{'='*50}")

            try:
                self.run_once()

                if max_cycles and cycle >= max_cycles:
                    break

                if self.running:
                    print("\nNext scan in 10 minutes...")
                    time.sleep(600)

            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)

        print("\nStopped.")

    def run_once(self):
        """Run one complete scan"""
        # 1. Detect market state
        print("\n1. Detecting market state...")
        self.market_state = self._detect_market_state()
        print(f"   State: {self.market_state['state']}")
        print(f"   SPY: {self.market_state['spy_trend']}")
        print(f"   VIX: {self.market_state['vix']:.1f}")

        # 2. Choose strategy based on market state
        print("\n2. Selecting strategy...")
        strategy = self._choose_strategy()
        print(f"   Strategy: {strategy}")

        # 3. Find stocks
        print("\n3. Finding stocks...")
        if strategy == 'MOMENTUM':
            self.picks = self._find_momentum_stocks()
        elif strategy == 'DEFENSIVE':
            self.picks = self._find_defensive_stocks()
        elif strategy == 'CONTRARIAN':
            self.picks = self._find_contrarian_stocks()
        elif strategy == 'LOW_VOL':
            self.picks = self._find_low_vol_stocks()
        else:
            self.picks = self._find_all_weather_stocks()

        # 4. Save and display
        print("\n4. Saving results...")
        self._save_results()
        self._print_picks()

    def _detect_market_state(self) -> Dict:
        """Detect current market state"""
        state = {
            'state': 'UNKNOWN',
            'spy_price': None,
            'spy_trend': 'UNKNOWN',
            'spy_vs_ma20': 0,
            'spy_vs_ma50': 0,
            'vix': 20,
            'sector_leaders': [],
            'sector_laggards': [],
        }

        if yf is None:
            return state

        try:
            # SPY analysis
            spy = yf.download('SPY', period='60d', progress=False)
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)

            price = float(spy['Close'].iloc[-1])
            ma20 = float(spy['Close'].tail(20).mean())
            ma50 = float(spy['Close'].tail(50).mean())

            state['spy_price'] = price
            state['spy_vs_ma20'] = ((price - ma20) / ma20) * 100
            state['spy_vs_ma50'] = ((price - ma50) / ma50) * 100

            if price > ma20 and price > ma50:
                state['spy_trend'] = 'STRONG_UP'
            elif price > ma20:
                state['spy_trend'] = 'UP'
            elif price < ma20 and price < ma50:
                state['spy_trend'] = 'STRONG_DOWN'
            else:
                state['spy_trend'] = 'DOWN'

            # VIX analysis
            vix = yf.download('^VIX', period='5d', progress=False)
            if isinstance(vix.columns, pd.MultiIndex):
                vix.columns = vix.columns.get_level_values(0)
            state['vix'] = float(vix['Close'].iloc[-1])

            # Determine overall state
            if state['spy_trend'] in ['STRONG_UP', 'UP'] and state['vix'] < 20:
                state['state'] = 'BULL'
            elif state['spy_trend'] in ['STRONG_DOWN', 'DOWN'] and state['vix'] > 25:
                state['state'] = 'BEAR'
            elif state['vix'] > 30:
                state['state'] = 'PANIC'
            else:
                state['state'] = 'NEUTRAL'

            # Sector analysis
            sector_etfs = {
                'XLK': 'Tech', 'XLF': 'Finance', 'XLV': 'Healthcare',
                'XLY': 'Consumer', 'XLI': 'Industrial', 'XLE': 'Energy',
                'XLP': 'Staples', 'XLU': 'Utilities',
            }

            sector_perf = {}
            for etf, name in sector_etfs.items():
                try:
                    data = yf.download(etf, period='20d', progress=False)
                    if not data.empty:
                        if isinstance(data.columns, pd.MultiIndex):
                            data.columns = data.columns.get_level_values(0)
                        ret = (float(data['Close'].iloc[-1]) / float(data['Close'].iloc[0]) - 1) * 100
                        sector_perf[name] = ret
                    time.sleep(0.5)
                except:
                    pass

            if sector_perf:
                sorted_sectors = sorted(sector_perf.items(), key=lambda x: x[1], reverse=True)
                state['sector_leaders'] = [s[0] for s in sorted_sectors[:3]]
                state['sector_laggards'] = [s[0] for s in sorted_sectors[-3:]]

        except Exception as e:
            state['error'] = str(e)

        return state

    def _choose_strategy(self) -> str:
        """Choose strategy based on market state"""
        state = self.market_state['state']
        vix = self.market_state['vix']

        if state == 'BULL':
            return 'MOMENTUM'
        elif state == 'BEAR':
            return 'DEFENSIVE'
        elif state == 'PANIC':
            return 'LOW_VOL'
        elif vix > 25:
            return 'LOW_VOL'
        else:
            return 'ALL_WEATHER'

    def _find_momentum_stocks(self) -> List[StockPick]:
        """Find momentum stocks for bull market"""
        print("   Looking for momentum stocks...")
        picks = []
        seen_symbols = set()  # Track seen symbols to avoid duplicates

        # Focus on growth sectors
        focus_sectors = ['Growth', 'Semiconductors', 'Consumer']
        symbols = []
        for sector in focus_sectors:
            if sector in self.UNIVERSE:
                symbols.extend([(s, sector) for s in self.UNIVERSE[sector]])

        for symbol, sector in symbols:
            if symbol in seen_symbols:
                continue  # Skip duplicates
            seen_symbols.add(symbol)

            pick = self._analyze_momentum(symbol, sector)
            if pick:
                picks.append(pick)
            time.sleep(1)

        return sorted(picks, key=lambda x: x.score, reverse=True)[:15]

    def _find_defensive_stocks(self) -> List[StockPick]:
        """Find defensive stocks for bear market"""
        print("   Looking for defensive stocks...")
        picks = []

        # Focus on defensive sectors
        focus_sectors = ['Defensive', 'Dividend', 'Healthcare']
        symbols = []
        for sector in focus_sectors:
            if sector in self.UNIVERSE:
                symbols.extend([(s, sector) for s in self.UNIVERSE[sector]])

        for symbol, sector in symbols:
            pick = self._analyze_defensive(symbol, sector)
            if pick:
                picks.append(pick)
            time.sleep(1)

        return sorted(picks, key=lambda x: x.score, reverse=True)[:15]

    def _find_contrarian_stocks(self) -> List[StockPick]:
        """Find stocks bucking the trend"""
        print("   Looking for contrarian plays...")
        picks = []

        # Look at all sectors for stocks moving opposite to market
        all_symbols = []
        for sector, symbols in self.UNIVERSE.items():
            all_symbols.extend([(s, sector) for s in symbols])

        for symbol, sector in all_symbols:
            pick = self._analyze_contrarian(symbol, sector)
            if pick:
                picks.append(pick)
            time.sleep(1)

        return sorted(picks, key=lambda x: x.score, reverse=True)[:15]

    def _find_low_vol_stocks(self) -> List[StockPick]:
        """Find low volatility stocks for uncertain markets"""
        print("   Looking for low volatility stocks...")
        picks = []

        # Focus on stable sectors
        focus_sectors = ['Defensive', 'Dividend', 'Value']
        symbols = []
        for sector in focus_sectors:
            if sector in self.UNIVERSE:
                symbols.extend([(s, sector) for s in self.UNIVERSE[sector]])

        for symbol, sector in symbols:
            pick = self._analyze_low_vol(symbol, sector)
            if pick:
                picks.append(pick)
            time.sleep(1)

        return sorted(picks, key=lambda x: x.score, reverse=True)[:15]

    def _find_all_weather_stocks(self) -> List[StockPick]:
        """Find stocks that work in any market"""
        print("   Looking for all-weather stocks...")
        picks = []

        # Quality stocks from all sectors
        quality_symbols = [
            ('AAPL', 'Growth'), ('MSFT', 'Growth'), ('GOOGL', 'Growth'),
            ('JNJ', 'Defensive'), ('PG', 'Defensive'), ('KO', 'Defensive'),
            ('JPM', 'Financials'), ('V', 'Financials'),
            ('UNH', 'Healthcare'), ('LLY', 'Healthcare'),
            ('HD', 'Consumer'), ('COST', 'Consumer'),
            ('CAT', 'Industrial'), ('HON', 'Industrial'),
        ]

        for symbol, sector in quality_symbols:
            pick = self._analyze_quality(symbol, sector)
            if pick:
                picks.append(pick)
            time.sleep(1)

        return sorted(picks, key=lambda x: x.score, reverse=True)[:15]

    # ===== ANALYSIS METHODS =====

    def _analyze_momentum(self, symbol: str, sector: str) -> Optional[StockPick]:
        """Analyze for momentum strategy"""
        if yf is None:
            return None

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='60d')
            if hist.empty or len(hist) < 50:
                return None

            closes = hist['Close'].values.flatten()
            volumes = hist['Volume'].values.flatten()
            price = float(closes[-1])

            ma20 = float(np.mean(closes[-20:]))
            ma50 = float(np.mean(closes[-50:]))
            rsi = self._calc_rsi(closes)
            accum = self._calc_accumulation(closes, volumes)

            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            # Momentum criteria
            if not (accum > 1.2 and 30 < rsi < 60 and above_ma20 > 0 and above_ma50 > 0):
                return None

            score = accum * 20 + (60 - rsi) + above_ma20 * 2

            reasons = []
            if accum > 1.5:
                reasons.append(f"Strong accumulation ({accum:.2f})")
            if rsi < 50:
                reasons.append(f"Not overbought (RSI {rsi:.0f})")
            if above_ma20 > 2:
                reasons.append(f"Above MA20 by {above_ma20:.1f}%")

            return StockPick(
                symbol=symbol, sector=sector, strategy='MOMENTUM',
                price=price, score=score, reasons=reasons,
                metrics={'rsi': rsi, 'accum': accum, 'above_ma20': above_ma20}
            )

        except:
            return None

    def _analyze_defensive(self, symbol: str, sector: str) -> Optional[StockPick]:
        """Analyze for defensive strategy"""
        if yf is None:
            return None

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='60d')
            if hist.empty or len(hist) < 50:
                return None

            closes = hist['Close'].values.flatten()
            highs = hist['High'].values.flatten()
            lows = hist['Low'].values.flatten()
            price = float(closes[-1])

            atr_pct = self._calc_atr_pct(closes, highs, lows)
            beta = self._calc_beta(closes)

            # Defensive criteria: low volatility, low beta
            if atr_pct > 2.5 or (beta and beta > 1.0):
                return None

            # Check dividend
            info = ticker.info
            div_yield = info.get('dividendYield', 0) or 0

            score = (3 - atr_pct) * 30 + div_yield * 1000 + (1 - (beta or 0)) * 20

            reasons = []
            if atr_pct < 2:
                reasons.append(f"Low volatility ({atr_pct:.1f}%)")
            if beta and beta < 0.8:
                reasons.append(f"Low beta ({beta:.2f})")
            if div_yield > 0.02:
                reasons.append(f"Dividend {div_yield*100:.1f}%")

            return StockPick(
                symbol=symbol, sector=sector, strategy='DEFENSIVE',
                price=price, score=score, reasons=reasons,
                metrics={'atr_pct': atr_pct, 'beta': beta, 'div_yield': div_yield}
            )

        except:
            return None

    def _analyze_contrarian(self, symbol: str, sector: str) -> Optional[StockPick]:
        """Analyze for contrarian strategy - stocks going UP when market is DOWN"""
        if yf is None:
            return None

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='20d')
            if hist.empty or len(hist) < 15:
                return None

            closes = hist['Close'].values.flatten()
            price = float(closes[-1])
            ret_5d = (closes[-1] / closes[-5] - 1) * 100

            # If market is down but stock is up, it's contrarian
            spy_trend = self.market_state.get('spy_vs_ma20', 0)

            # Contrarian: stock up when market down
            if spy_trend < 0 and ret_5d > 0:
                score = ret_5d * 10 + abs(spy_trend) * 5

                reasons = [
                    f"Up {ret_5d:.1f}% while market down",
                    "Bucking the trend",
                ]

                return StockPick(
                    symbol=symbol, sector=sector, strategy='CONTRARIAN',
                    price=price, score=score, reasons=reasons,
                    metrics={'5d_return': ret_5d, 'market_trend': spy_trend}
                )

        except:
            pass

        return None

    def _analyze_low_vol(self, symbol: str, sector: str) -> Optional[StockPick]:
        """Analyze for low volatility strategy"""
        if yf is None:
            return None

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='60d')
            if hist.empty or len(hist) < 50:
                return None

            closes = hist['Close'].values.flatten()
            highs = hist['High'].values.flatten()
            lows = hist['Low'].values.flatten()
            price = float(closes[-1])

            atr_pct = self._calc_atr_pct(closes, highs, lows)

            # Very low volatility
            if atr_pct > 1.5:
                return None

            score = (2 - atr_pct) * 50

            reasons = [f"Very low volatility ({atr_pct:.2f}%)"]

            return StockPick(
                symbol=symbol, sector=sector, strategy='LOW_VOL',
                price=price, score=score, reasons=reasons,
                metrics={'atr_pct': atr_pct}
            )

        except:
            return None

    def _analyze_quality(self, symbol: str, sector: str) -> Optional[StockPick]:
        """Analyze for quality all-weather stocks"""
        if yf is None:
            return None

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='60d')
            info = ticker.info

            if hist.empty or len(hist) < 50:
                return None

            closes = hist['Close'].values.flatten()
            volumes = hist['Volume'].values.flatten()
            highs = hist['High'].values.flatten()
            lows = hist['Low'].values.flatten()
            price = float(closes[-1])

            # Quality metrics
            atr_pct = self._calc_atr_pct(closes, highs, lows)
            rsi = self._calc_rsi(closes)
            accum = self._calc_accumulation(closes, volumes)

            profit_margin = info.get('profitMargins', 0) or 0
            roe = info.get('returnOnEquity', 0) or 0

            # Quality: profitable, stable, not overbought
            if profit_margin > 0.1 and atr_pct < 2.5 and rsi < 65:
                score = profit_margin * 100 + (roe or 0) * 100 + (3 - atr_pct) * 10

                reasons = []
                if profit_margin > 0.15:
                    reasons.append(f"High margin ({profit_margin*100:.0f}%)")
                if roe and roe > 0.15:
                    reasons.append(f"Strong ROE ({roe*100:.0f}%)")
                if atr_pct < 2:
                    reasons.append(f"Stable ({atr_pct:.1f}% vol)")
                if accum > 1.2:
                    reasons.append("Accumulation")

                return StockPick(
                    symbol=symbol, sector=sector, strategy='ALL_WEATHER',
                    price=price, score=score, reasons=reasons or ["Quality stock"],
                    metrics={'margin': profit_margin, 'roe': roe, 'atr': atr_pct}
                )

        except:
            pass

        return None

    # ===== CALCULATION HELPERS =====

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

    def _calc_beta(self, closes) -> Optional[float]:
        """Calculate beta vs SPY"""
        try:
            spy = yf.download('SPY', period='60d', progress=False)
            if spy.empty:
                return None
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)

            spy_ret = np.diff(spy['Close'].values) / spy['Close'].values[:-1]
            stock_ret = np.diff(closes) / closes[:-1]

            min_len = min(len(spy_ret), len(stock_ret))
            cov = np.cov(stock_ret[-min_len:], spy_ret[-min_len:])
            beta = cov[0, 1] / cov[1, 1] if cov[1, 1] != 0 else 1

            return round(beta, 2)
        except:
            return None

    def _save_results(self):
        """Save results"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Main results file
        results = {
            'timestamp': datetime.now().isoformat(),
            'market_state': self.market_state,
            'picks_count': len(self.picks),
            'picks': [
                {
                    'symbol': p.symbol,
                    'sector': p.sector,
                    'strategy': p.strategy,
                    'price': p.price,
                    'score': round(p.score, 1),
                    'reasons': p.reasons,
                    'metrics': p.metrics,
                }
                for p in self.picks
            ]
        }

        # Save latest
        latest_file = os.path.join(self.output_dir, 'LATEST_PICKS.json')
        with open(latest_file, 'w') as f:
            json.dump(results, f, indent=2)

        # Save history
        history_file = os.path.join(self.output_dir, f'picks_{timestamp}.json')
        with open(history_file, 'w') as f:
            json.dump(results, f, indent=2)

        # Save simple text file
        text_file = os.path.join(self.output_dir, 'PICKS.txt')
        with open(text_file, 'w') as f:
            f.write(f"STOCK PICKS - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Market State: {self.market_state['state']}\n")
            f.write(f"SPY Trend: {self.market_state['spy_trend']}\n")
            f.write(f"VIX: {self.market_state['vix']:.1f}\n\n")

            if self.picks:
                f.write(f"{'#':<3} {'Symbol':<8} {'Strategy':<12} {'Score':<7} {'Price':<10}\n")
                f.write("-" * 50 + "\n")
                for i, p in enumerate(self.picks, 1):
                    f.write(f"{i:<3} {p.symbol:<8} {p.strategy:<12} {p.score:<7.1f} ${p.price:<9.2f}\n")
                    for reason in p.reasons:
                        f.write(f"    - {reason}\n")
            else:
                f.write("No picks today\n")

        print(f"   Saved to: {self.output_dir}")

    def _print_picks(self):
        """Print picks to console"""
        print("\n" + "=" * 60)
        print(f"PICKS ({self.market_state['state']} market)")
        print("=" * 60)

        if self.picks:
            print(f"\n{'#':<3} {'Symbol':<8} {'Strategy':<12} {'Score':<7} {'Price':<10}")
            print("-" * 50)

            for i, p in enumerate(self.picks[:10], 1):
                print(f"{i:<3} {p.symbol:<8} {p.strategy:<12} {p.score:<7.1f} ${p.price:<9.2f}")
                for reason in p.reasons[:2]:
                    print(f"    - {reason}")
        else:
            print("\nNo picks meet criteria.")

        print(f"\nFull results: {os.path.join(self.output_dir, 'PICKS.txt')}")


def main():
    """Entry point"""
    print("""
============================================================
   ALL MARKET FINDER
============================================================

   Works in ANY market condition:
   - Bull market: Momentum stocks
   - Bear market: Defensive stocks
   - Panic mode: Low volatility stocks
   - Neutral: Quality all-weather stocks

   Even in the worst days, some stocks go UP.
   We find them for you.

============================================================
""")

    finder = AllMarketFinder()
    finder.run(max_cycles=1)


if __name__ == '__main__':
    main()
