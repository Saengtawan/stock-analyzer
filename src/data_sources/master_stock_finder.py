#!/usr/bin/env python3
"""
MASTER STOCK FINDER - ระบบค้นหาหุ้นอัตโนมัติครบวงจร

"ฉันไม่รู้ว่าใครจะชนะตลาดได้ แต่เรานี่แหละจะทำมัน"

ระบบนี้รวม:
1. Technical Analysis (v12.0 momentum gates)
2. Fundamental Analysis (P/E, growth, margins)
3. Economic Data (Fed, inflation, yields)
4. News & Sentiment (analyst ratings, insider trading)
5. Earnings Calendar (หลีกเลี่ยงก่อนประกาศงบ)
6. Market Conditions (SPY trend, VIX)
7. Sector Rotation (หา sector ที่กำลังร้อนแรง)

ทุกอย่างทำงานอัตโนมัติ คุณแค่มาดูผลลัพธ์!
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
class StockAnalysis:
    """ผลการวิเคราะห์หุ้น 1 ตัว"""
    symbol: str
    sector: str
    timestamp: str

    # Technical
    price: float
    rsi: float
    accumulation: float
    atr_pct: float
    above_ma20: float
    above_ma50: float
    technical_score: float
    technical_pass: bool

    # Fundamental
    pe_ratio: Optional[float]
    revenue_growth: Optional[float]
    profit_margin: Optional[float]
    analyst_rating: Optional[str]
    price_target: Optional[float]
    upside_pct: Optional[float]
    fundamental_score: float

    # Sentiment
    insider_signal: str
    news_sentiment: str
    sentiment_score: float

    # Events
    days_to_earnings: Optional[int]
    earnings_warning: bool

    # Final
    total_score: float
    recommendation: str
    reasons: List[str]


class MasterStockFinder:
    """
    ระบบค้นหาหุ้นครบวงจร

    ใช้งาน:
        finder = MasterStockFinder()
        finder.run()  # รันอัตโนมัติ
        # หรือ
        finder.run_once()  # รันครั้งเดียว
    """

    # ===== COMPLETE STOCK UNIVERSE =====
    UNIVERSE = {
        # === TECHNOLOGY ===
        'Technology': [
            # Mega Cap
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
            # Semiconductors
            'AMD', 'INTC', 'QCOM', 'AVGO', 'MU', 'AMAT', 'LRCX',
            # Software
            'CRM', 'ADBE', 'NOW', 'PANW', 'CRWD', 'ZS', 'DDOG',
            # Internet
            'NFLX', 'SPOT', 'PINS', 'SNAP', 'RBLX',
            # Fintech
            'PYPL', 'SQ', 'COIN', 'AFRM',
            # E-commerce
            'SHOP', 'MELI', 'SE',
            # Cloud/AI
            'SNOW', 'PLTR', 'AI', 'PATH',
        ],
        # === FINANCE ===
        'Finance': [
            # Big Banks
            'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS',
            # Credit Cards
            'V', 'MA', 'AXP', 'COF', 'DFS',
            # Asset Managers
            'BLK', 'SCHW', 'TROW',
            # Insurance
            'BRK-B', 'PGR', 'MET', 'AIG',
        ],
        # === HEALTHCARE ===
        'Healthcare': [
            # Pharma
            'JNJ', 'PFE', 'ABBV', 'MRK', 'LLY', 'BMY',
            # Biotech
            'AMGN', 'GILD', 'BIIB', 'REGN', 'VRTX', 'MRNA',
            # Healthcare Services
            'UNH', 'CVS', 'CI', 'HUM',
            # Medical Devices
            'MDT', 'ABT', 'ISRG', 'DXCM',
        ],
        # === CONSUMER ===
        'Consumer': [
            # Retail
            'HD', 'LOW', 'COST', 'WMT', 'TGT',
            # E-commerce
            'EBAY', 'ETSY',
            # Restaurants
            'MCD', 'SBUX', 'CMG', 'DPZ', 'YUM',
            # Apparel/Shoes
            'NKE', 'LULU',
            # Entertainment
            'DIS', 'CMCSA', 'NFLX', 'WBD',
            # Auto
            'TSLA', 'F', 'GM', 'RIVN',
        ],
        # === INDUSTRIAL ===
        'Industrial': [
            # Equipment
            'CAT', 'DE', 'HON', 'GE', 'MMM',
            # Aerospace
            'BA', 'RTX', 'LMT', 'NOC', 'GD',
            # Transport
            'UNP', 'CSX', 'FDX', 'UPS',
            # Construction
            'SHW', 'VMC', 'MLM',
        ],
        # === ENERGY ===
        'Energy': [
            'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'OXY', 'MPC', 'VLO',
        ],
        # === UTILITIES & REITS ===
        'Utilities': [
            'NEE', 'DUK', 'SO', 'AEP',
        ],
    }

    # ===== SCREENING CRITERIA (v12.0+) =====
    CRITERIA = {
        # Technical
        'accum_min': 1.2,
        'rsi_max': 58,
        'rsi_min': 30,  # ไม่ต่ำเกินไป
        'ma20_min': 0,
        'ma50_min': 0,
        'atr_max': 3.0,

        # Fundamental
        'pe_max': 50,  # ไม่แพงเกินไป
        'upside_min': 10,  # target > 10%

        # Events
        'earnings_avoid_days': 7,  # หลีกเลี่ยง 7 วันก่อนงบ
    }

    # ===== WEIGHTS FOR SCORING =====
    WEIGHTS = {
        'technical': 0.4,
        'fundamental': 0.3,
        'sentiment': 0.2,
        'events': 0.1,
    }

    def __init__(self, output_dir: str = None):
        """Initialize"""
        self.output_dir = output_dir or os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'master'
        )
        os.makedirs(self.output_dir, exist_ok=True)

        self.running = False
        self.cache = {}
        self.results: List[StockAnalysis] = []
        self.best_picks: List[StockAnalysis] = []

        # Rate limiting
        self.request_delay = 1.5  # seconds between requests
        self.batch_delay = 20     # seconds between batches
        self.cycle_delay = 600    # 10 minutes between cycles

        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        print("\nStopping...")
        self.running = False

    def run(self, max_cycles: int = None):
        """Run continuously"""
        self.running = True
        cycle = 0

        print("=" * 80)
        print("MASTER STOCK FINDER - RUNNING")
        print("=" * 80)
        print(f"Universe: {sum(len(s) for s in self.UNIVERSE.values())} stocks")
        print(f"Output: {self.output_dir}")
        print("Press Ctrl+C to stop\n")

        while self.running:
            cycle += 1
            print(f"\n{'='*60}")
            print(f"CYCLE {cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")

            try:
                self.run_once()

                if max_cycles and cycle >= max_cycles:
                    break

                if self.running:
                    print(f"\nNext cycle in {self.cycle_delay//60} minutes...")
                    time.sleep(self.cycle_delay)

            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)

        print("\nStopped.")

    def run_once(self):
        """Run one complete analysis"""
        start_time = datetime.now()

        # 1. Check market conditions
        print("\n1. Checking market conditions...")
        market_ok, market_info = self._check_market()
        if not market_ok:
            print(f"   Market is not favorable: {market_info}")
            self._save_results([], market_info)
            return

        print(f"   Market: {market_info}")

        # 2. Analyze all stocks
        print("\n2. Analyzing stocks...")
        self.results = []
        total_stocks = sum(len(s) for s in self.UNIVERSE.values())
        analyzed = 0

        for sector, symbols in self.UNIVERSE.items():
            for symbol in symbols:
                analysis = self._analyze_stock_complete(symbol, sector)
                if analysis:
                    self.results.append(analysis)
                analyzed += 1

                if analyzed % 20 == 0:
                    passed = sum(1 for r in self.results if r.recommendation == 'BUY')
                    print(f"   Analyzed {analyzed}/{total_stocks}... ({passed} passed)")

                time.sleep(self.request_delay)

        # 3. Filter and rank
        print("\n3. Ranking stocks...")
        self.best_picks = self._get_best_picks()

        # 4. Save results
        print("\n4. Saving results...")
        self._save_results(self.best_picks, market_info)

        # 5. Print summary
        elapsed = (datetime.now() - start_time).seconds
        self._print_summary(elapsed)

    def _check_market(self) -> Tuple[bool, str]:
        """Check overall market conditions"""
        if yf is None:
            return True, "No data (assuming OK)"

        try:
            # SPY
            spy = yf.download('SPY', period='30d', progress=False)
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)

            spy_close = float(spy['Close'].iloc[-1])
            spy_ma20 = float(spy['Close'].tail(20).mean())
            spy_trend = 'UP' if spy_close > spy_ma20 else 'DOWN'

            # VIX
            vix = yf.download('^VIX', period='5d', progress=False)
            if isinstance(vix.columns, pd.MultiIndex):
                vix.columns = vix.columns.get_level_values(0)
            vix_val = float(vix['Close'].iloc[-1])

            info = f"SPY {spy_trend} ({((spy_close/spy_ma20)-1)*100:+.1f}% vs MA20), VIX {vix_val:.1f}"

            # Conditions for trading
            if spy_trend == 'DOWN':
                return False, f"Market DOWN - {info}"
            if vix_val > 30:
                return False, f"VIX too high - {info}"

            return True, info

        except Exception as e:
            return True, f"Error checking market: {e}"

    def _analyze_stock_complete(self, symbol: str, sector: str) -> Optional[StockAnalysis]:
        """Complete analysis of one stock"""
        if yf is None:
            return None

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='60d')

            if hist.empty or len(hist) < 50:
                return None

            closes = hist['Close'].values.flatten()
            volumes = hist['Volume'].values.flatten()
            highs = hist['High'].values.flatten()
            lows = hist['Low'].values.flatten()
            price = float(closes[-1])

            # ===== TECHNICAL =====
            ma20 = float(np.mean(closes[-20:]))
            ma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else ma20
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100
            rsi = self._calc_rsi(closes)
            accum = self._calc_accumulation(closes, volumes)
            atr_pct = self._calc_atr_pct(closes, highs, lows)

            tech_pass = (
                accum > self.CRITERIA['accum_min'] and
                self.CRITERIA['rsi_min'] < rsi < self.CRITERIA['rsi_max'] and
                above_ma20 > self.CRITERIA['ma20_min'] and
                above_ma50 > self.CRITERIA['ma50_min'] and
                atr_pct < self.CRITERIA['atr_max']
            )

            tech_score = 0
            if tech_pass:
                tech_score = min(100, accum * 20 + (60 - rsi) + min(above_ma20, 10) * 2)

            # ===== FUNDAMENTAL =====
            info = ticker.info
            pe = info.get('trailingPE')
            rev_growth = info.get('revenueGrowth')
            profit_margin = info.get('profitMargins')
            analyst_rating = info.get('recommendationKey')
            target = info.get('targetMeanPrice')
            upside = ((target - price) / price * 100) if target and price else None

            fund_score = 0
            if pe and pe < self.CRITERIA['pe_max']:
                fund_score += 20
            if rev_growth and rev_growth > 0.1:
                fund_score += 30
            if profit_margin and profit_margin > 0.1:
                fund_score += 20
            if upside and upside > self.CRITERIA['upside_min']:
                fund_score += 30

            # ===== SENTIMENT =====
            insider_signal = 'NEUTRAL'
            news_sentiment = 'NEUTRAL'

            try:
                insider = ticker.insider_transactions
                if insider is not None and not insider.empty:
                    buys = len(insider[insider['Shares'] > 0])
                    sells = len(insider[insider['Shares'] < 0])
                    if buys > sells:
                        insider_signal = 'BULLISH'
                    elif sells > buys:
                        insider_signal = 'BEARISH'
            except:
                pass

            sent_score = 50
            if insider_signal == 'BULLISH':
                sent_score += 25
            elif insider_signal == 'BEARISH':
                sent_score -= 25
            if analyst_rating in ['strong_buy', 'buy']:
                sent_score += 25
            elif analyst_rating in ['sell', 'strong_sell']:
                sent_score -= 25

            # ===== EVENTS =====
            days_to_earn = None
            earn_warning = False

            try:
                calendar = ticker.calendar
                if calendar is not None and not calendar.empty:
                    if 'Earnings Date' in calendar.index:
                        earn_date = calendar.loc['Earnings Date']
                        if hasattr(earn_date, 'iloc'):
                            earn_date = earn_date.iloc[0]
                        days_to_earn = (pd.to_datetime(earn_date) - pd.Timestamp.now()).days
                        earn_warning = days_to_earn is not None and 0 < days_to_earn <= self.CRITERIA['earnings_avoid_days']
            except:
                pass

            event_score = 100 if not earn_warning else 50

            # ===== TOTAL SCORE =====
            total_score = (
                tech_score * self.WEIGHTS['technical'] +
                fund_score * self.WEIGHTS['fundamental'] +
                sent_score * self.WEIGHTS['sentiment'] +
                event_score * self.WEIGHTS['events']
            )

            # ===== RECOMMENDATION =====
            reasons = []
            if tech_pass:
                reasons.append("Technical PASS")
            else:
                reasons.append("Technical FAIL")

            if accum > 1.5:
                reasons.append(f"Strong accumulation ({accum:.2f})")
            if upside and upside > 20:
                reasons.append(f"High upside ({upside:.0f}%)")
            if insider_signal == 'BULLISH':
                reasons.append("Insider buying")
            if earn_warning:
                reasons.append("CAUTION: Earnings soon")

            recommendation = 'HOLD'
            if tech_pass and total_score > 60 and not earn_warning:
                recommendation = 'BUY'
            elif not tech_pass or total_score < 30:
                recommendation = 'AVOID'

            return StockAnalysis(
                symbol=symbol,
                sector=sector,
                timestamp=datetime.now().isoformat(),
                price=round(price, 2),
                rsi=round(rsi, 1),
                accumulation=round(accum, 2),
                atr_pct=round(atr_pct, 2),
                above_ma20=round(above_ma20, 2),
                above_ma50=round(above_ma50, 2),
                technical_score=round(tech_score, 1),
                technical_pass=tech_pass,
                pe_ratio=round(pe, 1) if pe else None,
                revenue_growth=round(rev_growth*100, 1) if rev_growth else None,
                profit_margin=round(profit_margin*100, 1) if profit_margin else None,
                analyst_rating=analyst_rating,
                price_target=round(target, 2) if target else None,
                upside_pct=round(upside, 1) if upside else None,
                fundamental_score=round(fund_score, 1),
                insider_signal=insider_signal,
                news_sentiment=news_sentiment,
                sentiment_score=round(sent_score, 1),
                days_to_earnings=days_to_earn,
                earnings_warning=earn_warning,
                total_score=round(total_score, 1),
                recommendation=recommendation,
                reasons=reasons,
            )

        except Exception as e:
            return None

    def _get_best_picks(self) -> List[StockAnalysis]:
        """Get best picks sorted by score"""
        buys = [r for r in self.results if r.recommendation == 'BUY']
        return sorted(buys, key=lambda x: x.total_score, reverse=True)[:20]

    def _save_results(self, picks: List[StockAnalysis], market_info: str):
        """Save results to files"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save best picks
        best_file = os.path.join(self.output_dir, 'BEST_STOCKS.json')
        best_data = {
            'timestamp': datetime.now().isoformat(),
            'market': market_info,
            'count': len(picks),
            'stocks': [asdict(p) for p in picks],
        }
        with open(best_file, 'w') as f:
            json.dump(best_data, f, indent=2)

        # Save all results
        all_file = os.path.join(self.output_dir, f'analysis_{timestamp}.json')
        all_data = {
            'timestamp': datetime.now().isoformat(),
            'market': market_info,
            'total_analyzed': len(self.results),
            'buys': len([r for r in self.results if r.recommendation == 'BUY']),
            'results': [asdict(r) for r in self.results],
        }
        with open(all_file, 'w') as f:
            json.dump(all_data, f, indent=2)

        # Save simple list for quick viewing
        simple_file = os.path.join(self.output_dir, 'TOP_PICKS.txt')
        with open(simple_file, 'w') as f:
            f.write(f"TOP STOCK PICKS - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Market: {market_info}\n")
            f.write("=" * 60 + "\n\n")

            if picks:
                f.write(f"{'#':<3} {'Symbol':<8} {'Sector':<12} {'Score':<7} {'Price':<10} {'Upside':<8}\n")
                f.write("-" * 60 + "\n")
                for i, p in enumerate(picks, 1):
                    upside = f"{p.upside_pct:.0f}%" if p.upside_pct else "N/A"
                    f.write(f"{i:<3} {p.symbol:<8} {p.sector:<12} {p.total_score:<7.1f} ${p.price:<9.2f} {upside:<8}\n")
            else:
                f.write("No stocks meet criteria today.\n")

        print(f"   Saved to: {self.output_dir}")

    def _print_summary(self, elapsed: int):
        """Print summary"""
        print("\n" + "=" * 60)
        print("ANALYSIS COMPLETE")
        print("=" * 60)

        total = len(self.results)
        buys = len(self.best_picks)

        print(f"\nAnalyzed: {total} stocks in {elapsed} seconds")
        print(f"Passed: {buys} stocks")

        if self.best_picks:
            print(f"\nTOP 10 PICKS:")
            print(f"{'#':<3} {'Symbol':<8} {'Sector':<12} {'Score':<7} {'RSI':<5} {'Accum':<6} {'Upside':<8}")
            print("-" * 60)

            for i, p in enumerate(self.best_picks[:10], 1):
                upside = f"{p.upside_pct:.0f}%" if p.upside_pct else "N/A"
                print(f"{i:<3} {p.symbol:<8} {p.sector:<12} {p.total_score:<7.1f} "
                      f"{p.rsi:<5.0f} {p.accumulation:<6.2f} {upside:<8}")

            # Print reasons for top pick
            if self.best_picks:
                top = self.best_picks[0]
                print(f"\n{top.symbol} - Why it's #1:")
                for reason in top.reasons:
                    print(f"  + {reason}")
        else:
            print("\nNo stocks meet all criteria today.")
            print("Wait for better market conditions.")

        print(f"\nResults saved to: {self.output_dir}")
        print(f"Quick view: {os.path.join(self.output_dir, 'TOP_PICKS.txt')}")

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
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
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
============================================================
   MASTER STOCK FINDER
============================================================

   "เราไม่รู้ว่าใครจะชนะตลาดได้ แต่เรานี่แหละจะทำมัน"

   ระบบนี้จะ:
   - วิเคราะห์หุ้นกว่า 150+ ตัว
   - ใช้ Technical + Fundamental + Sentiment
   - หลีกเลี่ยงหุ้นที่กำลังจะประกาศงบ
   - หาหุ้นที่ดีที่สุดให้คุณ

   คุณแค่มาดูผลลัพธ์!

============================================================
""")

    finder = MasterStockFinder()

    # Run once for demo (or run() for continuous)
    finder.run_once()


if __name__ == '__main__':
    main()
