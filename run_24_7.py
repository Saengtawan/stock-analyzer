#!/usr/bin/env python3
"""
24/7 STOCK FINDER - รันตลอดเวลา

ระบบนี้:
1. รัน 24/7 ไม่หยุด
2. ดึงข้อมูลจากทุกแหล่งฟรี
3. เคารพ rate limits (ไม่โดน block)
4. เจอหุ้นดี → เก็บ draft
5. เขียน log ทุกอย่าง

Rate Limits ที่ต้องระวัง:
- Yahoo Finance: ~2000 requests/hour (safe: 1 req/2 sec)
- No API key needed

Schedule:
- ทุก 15 นาที: Scan หุ้นทั้งหมด
- ทุก 1 ชั่วโมง: Update market data
- ทุก 6 ชั่วโมง: Full analysis + report
"""

import os
import sys
import json
import time
import signal
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

# Setup logging
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, f'stock_finder_{datetime.now().strftime("%Y%m%d")}.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

try:
    import pandas as pd
    import numpy as np
    import yfinance as yf
except ImportError as e:
    logger.error(f"Missing dependency: {e}")
    logger.error("Run: pip install yfinance pandas numpy")
    exit(1)


class StockFinder24_7:
    """24/7 Stock Finder"""

    # Universe
    UNIVERSE = {
        'Industrial': ['CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT', 'MMM', 'UPS', 'FDX'],
        'Consumer': ['HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'DIS', 'LULU'],
        'Finance': ['JPM', 'BAC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BLK', 'SCHW', 'COF'],
        'Healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'AMGN', 'GILD', 'BIIB'],
        'Tech': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD', 'CRM', 'ADBE', 'INTC', 'QCOM', 'AVGO'],
        'Semiconductor': ['NVDA', 'AMD', 'AVGO', 'MU', 'AMAT', 'LRCX', 'TSM', 'ASML'],
    }

    # Rate limits (in seconds)
    RATE_LIMITS = {
        'yahoo_request': 2,      # 2 sec between requests
        'batch_pause': 30,       # 30 sec every 20 stocks
        'scan_interval': 900,    # 15 min between scans
        'market_update': 3600,   # 1 hour market data refresh
        'full_report': 21600,    # 6 hours full report
    }

    def __init__(self):
        """Initialize"""
        self.data_dir = os.path.join(os.path.dirname(__file__), 'data', 'finder_24_7')
        os.makedirs(self.data_dir, exist_ok=True)

        self.running = False
        self.scan_count = 0
        self.stocks_found = 0

        # Cache
        self.cache = {
            'spy': None,
            'vix': None,
            'last_update': None,
        }

        # Results
        self.drafts = []
        self.all_scans = []

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received")
        self.running = False

    def run(self):
        """Run 24/7"""
        self.running = True
        logger.info("=" * 60)
        logger.info("24/7 STOCK FINDER STARTING")
        logger.info("=" * 60)
        logger.info(f"Universe: {sum(len(s) for s in self.UNIVERSE.values())} stocks")
        logger.info(f"Data dir: {self.data_dir}")
        logger.info(f"Scan interval: {self.RATE_LIMITS['scan_interval']//60} minutes")
        logger.info("Press Ctrl+C to stop")

        last_full_report = 0

        while self.running:
            try:
                self.scan_count += 1
                logger.info(f"\n{'='*50}")
                logger.info(f"SCAN #{self.scan_count}")
                logger.info(f"{'='*50}")

                # Run scan
                finds = self._run_scan()

                if finds:
                    self.stocks_found += len(finds)
                    logger.info(f"Found {len(finds)} stocks!")
                    for f in finds:
                        logger.info(f"  + {f['symbol']} ({f['confidence']}%)")

                # Save results
                self._save_results()

                # Full report every 6 hours
                now = time.time()
                if now - last_full_report > self.RATE_LIMITS['full_report']:
                    self._generate_report()
                    last_full_report = now

                # Wait for next scan
                if self.running:
                    wait = self.RATE_LIMITS['scan_interval']
                    logger.info(f"Next scan in {wait//60} minutes...")
                    time.sleep(wait)

            except Exception as e:
                logger.error(f"Error in scan: {e}")
                time.sleep(60)

        logger.info("Finder stopped")
        self._save_results()

    def _run_scan(self) -> List[Dict]:
        """Run one scan"""
        # Update market data
        self._update_market()

        # Check market conditions
        market_ok, market_info = self._check_market()
        logger.info(f"Market: {market_info}")

        if not market_ok:
            logger.info("Market not favorable, skipping scan")
            return []

        # Scan stocks
        finds = []
        seen = set(d['symbol'] for d in self.drafts)
        batch_count = 0

        for sector, symbols in self.UNIVERSE.items():
            for symbol in symbols:
                if symbol in seen:
                    continue

                result = self._analyze_stock(symbol, sector)
                if result and result['confidence'] >= 60:
                    finds.append(result)
                    seen.add(symbol)

                time.sleep(self.RATE_LIMITS['yahoo_request'])
                batch_count += 1

                if batch_count % 20 == 0:
                    logger.debug(f"Processed {batch_count} stocks, pausing...")
                    time.sleep(self.RATE_LIMITS['batch_pause'])

        # Add to drafts
        for f in finds:
            self._add_to_drafts(f)

        return finds

    def _update_market(self):
        """Update market data"""
        now = time.time()
        if self.cache['last_update'] and now - self.cache['last_update'] < self.RATE_LIMITS['market_update']:
            return

        try:
            logger.debug("Updating market data...")

            spy = yf.download('SPY', period='30d', progress=False)
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)
            self.cache['spy'] = spy

            time.sleep(self.RATE_LIMITS['yahoo_request'])

            vix = yf.download('^VIX', period='5d', progress=False)
            if isinstance(vix.columns, pd.MultiIndex):
                vix.columns = vix.columns.get_level_values(0)
            self.cache['vix'] = vix

            self.cache['last_update'] = now
            logger.debug("Market data updated")

        except Exception as e:
            logger.error(f"Error updating market: {e}")

    def _check_market(self):
        """Check market conditions"""
        spy = self.cache.get('spy')
        vix = self.cache.get('vix')

        if spy is None or spy.empty:
            return True, "No market data"

        price = float(spy['Close'].iloc[-1])
        ma20 = float(spy['Close'].tail(20).mean())
        trend = 'UP' if price > ma20 else 'DOWN'

        vix_val = 20
        if vix is not None and not vix.empty:
            vix_val = float(vix['Close'].iloc[-1])

        info = f"SPY {trend} ({((price/ma20)-1)*100:+.1f}%), VIX {vix_val:.1f}"

        # Conditions
        month = datetime.now().month
        if month in [10, 11]:
            return False, f"Bad month - {info}"
        if trend == 'DOWN':
            return False, f"Downtrend - {info}"
        if vix_val > 25:
            return False, f"High VIX - {info}"

        return True, info

    def _analyze_stock(self, symbol: str, sector: str) -> Optional[Dict]:
        """Analyze a stock"""
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

            # Criteria
            if accum <= 1.2:
                return None
            if rsi >= 58 or rsi <= 30:
                return None
            if above_ma20 <= 0 or above_ma50 <= 0:
                return None
            if atr_pct > 3.0:
                return None

            # Score & confidence
            score = 0
            reasons = []

            if accum >= 1.5:
                score += 25
                reasons.append(f"Strong accumulation ({accum:.2f})")
            else:
                score += 15
                reasons.append(f"Accumulation OK ({accum:.2f})")

            if 40 <= rsi <= 50:
                score += 20
                reasons.append(f"Ideal RSI ({rsi:.0f})")
            else:
                score += 10

            if above_ma20 > 2:
                score += 15
                reasons.append(f"Above MA20 by {above_ma20:.1f}%")
            else:
                score += 5

            if atr_pct < 2.0:
                score += 20
                reasons.append(f"Low volatility ({atr_pct:.2f}%)")
            else:
                score += 10

            if sector in ['Finance', 'Industrial']:
                score += 10
                reasons.append(f"Strong sector ({sector})")

            confidence = min(100, int(score * 1.2))

            return {
                'symbol': symbol,
                'sector': sector,
                'price': price,
                'confidence': confidence,
                'score': score,
                'reasons': reasons,
                'found_at': datetime.now().isoformat(),
                'metrics': {
                    'rsi': round(rsi, 1),
                    'accum': round(accum, 2),
                    'atr_pct': round(atr_pct, 2),
                    'above_ma20': round(above_ma20, 2),
                }
            }

        except:
            return None

    def _add_to_drafts(self, stock: Dict):
        """Add to drafts"""
        self.drafts = [d for d in self.drafts if d['symbol'] != stock['symbol']]
        self.drafts.append(stock)
        self.drafts.sort(key=lambda x: x['confidence'], reverse=True)

    def _save_results(self):
        """Save results"""
        # Save drafts
        drafts_file = os.path.join(self.data_dir, 'drafts.json')
        with open(drafts_file, 'w') as f:
            json.dump({
                'updated_at': datetime.now().isoformat(),
                'scan_count': self.scan_count,
                'stocks_found': self.stocks_found,
                'drafts': self.drafts,
            }, f, indent=2)

        # Save readable version
        txt_file = os.path.join(self.data_dir, 'DRAFTS.txt')
        with open(txt_file, 'w') as f:
            f.write(f"DRAFT STOCKS - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Scans completed: {self.scan_count}\n")
            f.write(f"Total finds: {self.stocks_found}\n\n")

            if self.drafts:
                f.write(f"{'Symbol':<8} {'Sector':<12} {'Conf':<6} {'Price':<10}\n")
                f.write("-" * 40 + "\n")
                for d in self.drafts[:20]:
                    f.write(f"{d['symbol']:<8} {d['sector']:<12} {d['confidence']}%    ${d['price']:.2f}\n")
                    for r in d['reasons'][:2]:
                        f.write(f"  + {r}\n")
            else:
                f.write("No stocks found yet.\n")

    def _generate_report(self):
        """Generate 6-hour report"""
        logger.info("\n" + "=" * 60)
        logger.info("6-HOUR REPORT")
        logger.info("=" * 60)

        logger.info(f"Scans completed: {self.scan_count}")
        logger.info(f"Total stocks found: {self.stocks_found}")

        if self.drafts:
            logger.info(f"\nTop picks:")
            for d in self.drafts[:5]:
                logger.info(f"  {d['symbol']} ({d['confidence']}%) - {d['sector']}")

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
    """Entry point"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                   24/7 STOCK FINDER                          ║
║   รันตลอดเวลา ค้นหาหุ้นที่ดีที่สุดให้คุณ                    ║
╚══════════════════════════════════════════════════════════════╝

Schedule:
- Every 15 min: Scan all stocks
- Every 1 hour: Update market data
- Every 6 hours: Generate report

Respects rate limits. Safe to run 24/7.

Press Ctrl+C to stop.
""")

    finder = StockFinder24_7()
    finder.run()


if __name__ == '__main__':
    main()
