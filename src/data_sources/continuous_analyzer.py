#!/usr/bin/env python3
"""
Continuous Stock Analyzer - ระบบวิเคราะห์หุ้นอัตโนมัติที่รันตลอดเวลา

ระบบนี้จะ:
1. ดึงข้อมูลจากทุกแหล่ง (ไม่เกิน rate limit)
2. วิเคราะห์หุ้นทุกตัวในจักรวาล
3. หาหุ้นที่ผ่านเกณฑ์ทั้งหมด
4. เก็บผลลัพธ์ไว้ในไฟล์
5. ทำซ้ำไปเรื่อยๆ

การจัดการ Rate Limit:
- Yahoo Finance: 2000 requests/hour = ~1 request/2 seconds
- FRED: 500 requests/day
- ใช้ cache เพื่อลดการ request ซ้ำ
"""

import os
import sys
import json
import time
import signal
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import yfinance as yf
except ImportError:
    yf = None

import numpy as np


class ContinuousAnalyzer:
    """
    ระบบวิเคราะห์หุ้นอัตโนมัติที่รันตลอดเวลา

    ใช้งาน:
        analyzer = ContinuousAnalyzer()
        analyzer.run()  # จะรันไปเรื่อยๆ จนกว่าจะ stop
    """

    # ===== UNIVERSE OF STOCKS =====
    STOCK_UNIVERSE = {
        'Technology': [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
            'AMD', 'INTC', 'QCOM', 'CRM', 'ADBE', 'NFLX', 'PYPL',
            'SQ', 'SHOP', 'SNOW', 'UBER', 'ABNB', 'COIN'
        ],
        'Finance': [
            'JPM', 'BAC', 'GS', 'MS', 'WFC', 'C',
            'V', 'MA', 'AXP', 'COF', 'BLK', 'SCHW'
        ],
        'Healthcare': [
            'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY',
            'BMY', 'GILD', 'AMGN', 'BIIB', 'REGN', 'VRTX'
        ],
        'Consumer': [
            'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX',
            'NKE', 'LULU', 'DIS', 'CMCSA', 'CHTR'
        ],
        'Industrial': [
            'CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT',
            'MMM', 'UPS', 'FDX'
        ],
        'Energy': [
            'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'OXY'
        ],
    }

    # ===== v12.0 SCREENING CRITERIA =====
    SCREENING_CONFIG = {
        'accum_min': 1.2,      # Accumulation > 1.2
        'rsi_max': 58,         # RSI < 58
        'ma20_min': 0,         # Price > MA20
        'ma50_min': 0,         # Price > MA50
        'atr_max': 3.0,        # ATR < 3%
    }

    # ===== RATE LIMIT CONFIG =====
    RATE_LIMITS = {
        'yahoo_delay': 2.0,    # 2 seconds between Yahoo requests
        'batch_size': 10,      # Process 10 stocks per batch
        'batch_delay': 30,     # 30 seconds between batches
        'cycle_delay': 300,    # 5 minutes between full cycles
    }

    def __init__(self, output_dir: str = None):
        """Initialize the analyzer"""
        self.output_dir = output_dir or os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'analysis'
        )
        os.makedirs(self.output_dir, exist_ok=True)

        self.running = False
        self.cycle_count = 0
        self.last_results = None

        # Cache for market data
        self.cache = {
            'spy': None,
            'spy_updated': None,
            'vix': None,
            'vix_updated': None,
        }

        # Results storage
        self.best_stocks = []
        self.all_analysis = {}

        # Signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print("\nReceived shutdown signal. Saving results...")
        self.running = False

    def run(self, max_cycles: int = None):
        """
        Run the analyzer continuously

        Args:
            max_cycles: Maximum number of cycles (None = run forever)
        """
        self.running = True
        print("=" * 80)
        print("CONTINUOUS STOCK ANALYZER - STARTING")
        print("=" * 80)
        print(f"Output directory: {self.output_dir}")
        print(f"Universe: {sum(len(s) for s in self.STOCK_UNIVERSE.values())} stocks")
        print(f"Press Ctrl+C to stop\n")

        while self.running:
            self.cycle_count += 1
            print(f"\n{'='*60}")
            print(f"CYCLE {self.cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")

            try:
                # Run one full analysis cycle
                self._run_cycle()

                # Save results
                self._save_results()

                # Check max cycles
                if max_cycles and self.cycle_count >= max_cycles:
                    print(f"\nReached max cycles ({max_cycles}). Stopping.")
                    break

                # Wait before next cycle
                if self.running:
                    print(f"\nWaiting {self.RATE_LIMITS['cycle_delay']}s before next cycle...")
                    time.sleep(self.RATE_LIMITS['cycle_delay'])

            except Exception as e:
                print(f"Error in cycle: {e}")
                time.sleep(60)  # Wait 1 minute on error

        print("\nAnalyzer stopped.")
        self._save_results()

    def _run_cycle(self):
        """Run one full analysis cycle"""
        # Step 1: Update market data
        print("\n1. Updating market data...")
        self._update_market_data()

        # Step 2: Check market trend
        market_ok = self._check_market_trend()
        if not market_ok:
            print("   Market is DOWN (SPY < MA20). Waiting for better conditions.")
            return

        # Step 3: Analyze all stocks
        print("\n2. Analyzing stocks...")
        all_stocks = []
        for sector, symbols in self.STOCK_UNIVERSE.items():
            all_stocks.extend([(sym, sector) for sym in symbols])

        passed_stocks = []
        failed_stocks = []

        # Process in batches to respect rate limits
        for i in range(0, len(all_stocks), self.RATE_LIMITS['batch_size']):
            batch = all_stocks[i:i + self.RATE_LIMITS['batch_size']]

            for symbol, sector in batch:
                result = self._analyze_stock(symbol, sector)

                if result['passed']:
                    passed_stocks.append(result)
                else:
                    failed_stocks.append(result)

                # Rate limit delay
                time.sleep(self.RATE_LIMITS['yahoo_delay'])

            # Batch delay
            if i + self.RATE_LIMITS['batch_size'] < len(all_stocks):
                remaining = len(all_stocks) - i - self.RATE_LIMITS['batch_size']
                print(f"   Processed {i + len(batch)}/{len(all_stocks)}. "
                      f"{len(passed_stocks)} passed. Waiting...")
                time.sleep(self.RATE_LIMITS['batch_delay'])

        # Step 4: Rank passed stocks
        print(f"\n3. Ranking {len(passed_stocks)} stocks that passed screening...")
        self.best_stocks = self._rank_stocks(passed_stocks)

        # Step 5: Store results
        self.all_analysis = {
            'timestamp': datetime.now().isoformat(),
            'cycle': self.cycle_count,
            'market_trend': 'UP' if market_ok else 'DOWN',
            'total_analyzed': len(all_stocks),
            'passed': len(passed_stocks),
            'failed': len(failed_stocks),
            'best_stocks': self.best_stocks,
        }

        # Print summary
        self._print_summary()

    def _update_market_data(self):
        """Update cached market data"""
        if yf is None:
            return

        now = datetime.now()

        # Update SPY every 5 minutes
        if (self.cache['spy_updated'] is None or
            (now - self.cache['spy_updated']).seconds > 300):
            try:
                spy = yf.download('SPY', period='60d', progress=False)
                if isinstance(spy.columns, pd.MultiIndex):
                    spy.columns = spy.columns.get_level_values(0)
                self.cache['spy'] = spy
                self.cache['spy_updated'] = now
                print("   SPY data updated")
            except Exception as e:
                print(f"   Error updating SPY: {e}")

            time.sleep(self.RATE_LIMITS['yahoo_delay'])

        # Update VIX
        if (self.cache['vix_updated'] is None or
            (now - self.cache['vix_updated']).seconds > 300):
            try:
                vix = yf.download('^VIX', period='5d', progress=False)
                if isinstance(vix.columns, pd.MultiIndex):
                    vix.columns = vix.columns.get_level_values(0)
                self.cache['vix'] = vix
                self.cache['vix_updated'] = now
                print("   VIX data updated")
            except Exception as e:
                print(f"   Error updating VIX: {e}")

            time.sleep(self.RATE_LIMITS['yahoo_delay'])

    def _check_market_trend(self) -> bool:
        """Check if market is in uptrend (SPY > MA20)"""
        if self.cache['spy'] is None:
            return True  # Assume OK if no data

        spy = self.cache['spy']
        if spy.empty:
            return True

        spy_close = float(spy['Close'].iloc[-1])
        spy_ma20 = float(spy['Close'].tail(20).mean())

        is_up = spy_close > spy_ma20
        pct = ((spy_close - spy_ma20) / spy_ma20) * 100

        print(f"   SPY: ${spy_close:.2f} ({pct:+.1f}% vs MA20)")
        print(f"   Market Trend: {'UP' if is_up else 'DOWN'}")

        # Also check VIX
        if self.cache['vix'] is not None and not self.cache['vix'].empty:
            vix = float(self.cache['vix']['Close'].iloc[-1])
            print(f"   VIX: {vix:.1f}")
            if vix > 25:
                print("   Warning: VIX is high (>25)")

        return is_up

    def _analyze_stock(self, symbol: str, sector: str) -> Dict:
        """Analyze a single stock"""
        result = {
            'symbol': symbol,
            'sector': sector,
            'passed': False,
            'fail_reason': None,
            'score': 0,
            'metrics': {},
        }

        if yf is None:
            result['fail_reason'] = 'yfinance not available'
            return result

        try:
            # Download data
            df = yf.download(symbol, period='60d', progress=False)
            if df.empty or len(df) < 50:
                result['fail_reason'] = 'Insufficient data'
                return result

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            closes = df['Close'].values.flatten()
            volumes = df['Volume'].values.flatten()
            highs = df['High'].values.flatten()
            lows = df['Low'].values.flatten()

            price = float(closes[-1])

            # Calculate metrics
            ma20 = float(np.mean(closes[-20:]))
            ma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else ma20

            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            rsi = self._calculate_rsi(closes)
            accum = self._calculate_accumulation(closes, volumes)
            atr_pct = self._calculate_atr_pct(closes, highs, lows)

            result['metrics'] = {
                'price': price,
                'above_ma20': round(above_ma20, 2),
                'above_ma50': round(above_ma50, 2),
                'rsi': round(rsi, 1),
                'accumulation': round(accum, 2),
                'atr_pct': round(atr_pct, 2),
            }

            # Apply screening gates (v12.0)
            config = self.SCREENING_CONFIG

            if accum <= config['accum_min']:
                result['fail_reason'] = f'Accumulation {accum:.2f} <= {config["accum_min"]}'
                return result

            if rsi >= config['rsi_max']:
                result['fail_reason'] = f'RSI {rsi:.0f} >= {config["rsi_max"]}'
                return result

            if above_ma20 <= config['ma20_min']:
                result['fail_reason'] = f'Below MA20 ({above_ma20:.1f}%)'
                return result

            if above_ma50 <= config['ma50_min']:
                result['fail_reason'] = f'Below MA50 ({above_ma50:.1f}%)'
                return result

            if atr_pct > config['atr_max']:
                result['fail_reason'] = f'ATR {atr_pct:.2f}% > {config["atr_max"]}%'
                return result

            # PASSED! Calculate score
            result['passed'] = True
            result['score'] = self._calculate_score(result['metrics'])

        except Exception as e:
            result['fail_reason'] = str(e)

        return result

    def _calculate_score(self, metrics: Dict) -> float:
        """Calculate a ranking score for a stock"""
        score = 0

        # Accumulation (higher is better)
        accum = metrics.get('accumulation', 1)
        score += min(accum, 3) * 20  # Max 60 points

        # RSI (lower is better, but not too low)
        rsi = metrics.get('rsi', 50)
        if 40 <= rsi <= 55:
            score += 30
        elif 35 <= rsi <= 60:
            score += 20
        else:
            score += 10

        # Trend strength (above MA20/50)
        above_ma20 = metrics.get('above_ma20', 0)
        above_ma50 = metrics.get('above_ma50', 0)
        if above_ma20 > 0 and above_ma50 > 0:
            score += min(above_ma20, 5) * 3  # Max 15 points
            score += min(above_ma50, 5) * 3  # Max 15 points

        # Low volatility (lower ATR is better)
        atr = metrics.get('atr_pct', 3)
        if atr < 2:
            score += 20
        elif atr < 2.5:
            score += 10

        return round(score, 2)

    def _rank_stocks(self, stocks: List[Dict]) -> List[Dict]:
        """Rank stocks by score"""
        ranked = sorted(stocks, key=lambda x: x['score'], reverse=True)
        return ranked[:20]  # Top 20

    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI"""
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

    def _calculate_accumulation(self, closes, volumes, period=20):
        """Calculate accumulation ratio"""
        if len(closes) < period:
            return 1.0
        up_vol, down_vol = 0.0, 0.0
        for i in range(-period+1, 0):
            if closes[i] > closes[i-1]:
                up_vol += volumes[i]
            elif closes[i] < closes[i-1]:
                down_vol += volumes[i]
        return up_vol / down_vol if down_vol > 0 else 3.0

    def _calculate_atr_pct(self, closes, highs, lows, period=14):
        """Calculate ATR as percentage"""
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

    def _print_summary(self):
        """Print analysis summary"""
        print("\n" + "=" * 60)
        print("ANALYSIS SUMMARY")
        print("=" * 60)

        if self.all_analysis:
            print(f"\nTimestamp: {self.all_analysis['timestamp']}")
            print(f"Market Trend: {self.all_analysis['market_trend']}")
            print(f"Stocks Analyzed: {self.all_analysis['total_analyzed']}")
            print(f"Passed Screening: {self.all_analysis['passed']}")

        if self.best_stocks:
            print(f"\nTOP {len(self.best_stocks)} STOCKS:")
            print(f"{'Rank':<5} {'Symbol':<8} {'Sector':<12} {'Score':<8} {'RSI':<6} {'Accum':<6}")
            print("-" * 50)

            for i, stock in enumerate(self.best_stocks, 1):
                metrics = stock.get('metrics', {})
                print(f"{i:<5} {stock['symbol']:<8} {stock['sector']:<12} "
                      f"{stock['score']:<8.1f} {metrics.get('rsi', 0):<6.0f} "
                      f"{metrics.get('accumulation', 0):<6.2f}")
        else:
            print("\nNo stocks passed screening criteria.")

    def _save_results(self):
        """Save results to file"""
        if not self.all_analysis:
            return

        # Save latest results
        latest_file = os.path.join(self.output_dir, 'latest_analysis.json')
        with open(latest_file, 'w') as f:
            json.dump(self.all_analysis, f, indent=2, default=str)

        # Save historical results
        date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        history_file = os.path.join(self.output_dir, f'analysis_{date_str}.json')
        with open(history_file, 'w') as f:
            json.dump(self.all_analysis, f, indent=2, default=str)

        # Save best stocks as simple list
        best_file = os.path.join(self.output_dir, 'best_stocks.json')
        best_list = [
            {
                'symbol': s['symbol'],
                'sector': s['sector'],
                'score': s['score'],
                **s.get('metrics', {})
            }
            for s in self.best_stocks
        ]
        with open(best_file, 'w') as f:
            json.dump(best_list, f, indent=2)

        print(f"\nResults saved to {self.output_dir}")

    def get_best_stocks(self) -> List[Dict]:
        """Get current best stocks"""
        return self.best_stocks


def main():
    """Main entry point"""
    print("""
CONTINUOUS STOCK ANALYZER
=========================

This program will:
1. Analyze all stocks in the universe
2. Apply v12.0 screening criteria
3. Find and rank the best stocks
4. Save results continuously
5. Repeat every 5 minutes

The analyzer respects rate limits:
- Yahoo Finance: 1 request every 2 seconds
- 10 stocks per batch with 30 second pauses

Press Ctrl+C to stop.
""")

    analyzer = ContinuousAnalyzer()

    # Run 1 cycle for demo (or remove max_cycles for continuous)
    analyzer.run(max_cycles=1)


if __name__ == '__main__':
    main()
