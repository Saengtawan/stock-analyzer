#!/usr/bin/env python3
"""
AUTO PORTFOLIO - ระบบค้นหาและเก็บหุ้นอัตโนมัติ

ระบบนี้:
1. รันตลอดเวลา ค้นหาหุ้นที่ดี
2. พอเจอหุ้นที่ผ่านเกณฑ์ทั้งหมด → เก็บเข้า Draft Portfolio
3. คุณแค่มาดูว่ามีอะไรบ้าง แล้ว pick เข้า Portfolio จริง

Confidence Score:
- 90-100: HIGH CONFIDENCE (ผ่านทุกเกณฑ์ + score สูงมาก)
- 70-89: GOOD (ผ่านทุกเกณฑ์ + score ดี)
- 50-69: OK (ผ่านเกณฑ์พื้นฐาน)

Draft Portfolio จะเก็บ:
- symbol
- entry_price (ราคาตอนเจอ)
- found_at (วันเวลาที่เจอ)
- confidence
- reasons
"""

import os
import sys
import json
import time
import signal
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
class DraftStock:
    """หุ้นใน Draft Portfolio"""
    symbol: str
    sector: str
    entry_price: float
    found_at: str
    confidence: int  # 0-100
    score: float
    reasons: List[str]
    metrics: Dict
    status: str  # 'draft', 'picked', 'passed'


class AutoPortfolio:
    """
    ระบบ Auto Portfolio

    ใช้งาน:
        auto = AutoPortfolio()
        auto.run()  # รันอัตโนมัติ

    ดู draft:
        auto.show_drafts()

    Pick หุ้น:
        auto.pick_stock('AAPL')  # ย้ายจาก draft ไป portfolio
    """

    # Universe
    UNIVERSE = {
        'Industrial': ['CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT', 'MMM', 'UPS'],
        'Consumer': ['HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'DIS'],
        'Finance': ['JPM', 'BAC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BLK', 'SCHW'],
        'Healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'AMGN', 'GILD'],
        'Tech': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD', 'CRM', 'ADBE', 'INTC', 'QCOM'],
        'Semiconductor': ['NVDA', 'AMD', 'AVGO', 'MU', 'AMAT', 'LRCX', 'TSM'],
    }

    # Confidence thresholds
    HIGH_CONFIDENCE_SCORE = 80
    GOOD_SCORE = 60

    def __init__(self, data_dir: str = None):
        """Initialize"""
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(__file__), '..', 'data', 'portfolio'
        )
        os.makedirs(self.data_dir, exist_ok=True)

        self.draft_file = os.path.join(self.data_dir, 'draft_portfolio.json')
        self.portfolio_file = os.path.join(self.data_dir, 'portfolio.json')
        self.history_file = os.path.join(self.data_dir, 'history.json')

        self.drafts: List[DraftStock] = []
        self.portfolio: List[DraftStock] = []
        self.running = False

        self._load_data()

        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        print("\nSaving and stopping...")
        self.running = False
        self._save_data()

    def _load_data(self):
        """Load saved data"""
        if os.path.exists(self.draft_file):
            with open(self.draft_file, 'r') as f:
                data = json.load(f)
                self.drafts = [DraftStock(**d) for d in data.get('drafts', [])]

        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file, 'r') as f:
                data = json.load(f)
                self.portfolio = [DraftStock(**d) for d in data.get('stocks', [])]

    def _save_data(self):
        """Save data"""
        with open(self.draft_file, 'w') as f:
            json.dump({
                'updated_at': datetime.now().isoformat(),
                'count': len(self.drafts),
                'drafts': [asdict(d) for d in self.drafts],
            }, f, indent=2)

        with open(self.portfolio_file, 'w') as f:
            json.dump({
                'updated_at': datetime.now().isoformat(),
                'count': len(self.portfolio),
                'stocks': [asdict(d) for d in self.portfolio],
            }, f, indent=2)

        # Save readable summary
        summary_file = os.path.join(self.data_dir, 'DRAFTS.txt')
        with open(summary_file, 'w') as f:
            f.write(f"DRAFT PORTFOLIO - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write("=" * 70 + "\n\n")

            if self.drafts:
                f.write(f"Found {len(self.drafts)} stocks:\n\n")
                for d in sorted(self.drafts, key=lambda x: x.confidence, reverse=True):
                    conf_label = "HIGH" if d.confidence >= 90 else ("GOOD" if d.confidence >= 70 else "OK")
                    f.write(f"{d.symbol} ({d.sector})\n")
                    f.write(f"  Price: ${d.entry_price:.2f}\n")
                    f.write(f"  Confidence: {d.confidence}% ({conf_label})\n")
                    f.write(f"  Found: {d.found_at}\n")
                    for reason in d.reasons[:3]:
                        f.write(f"  + {reason}\n")
                    f.write("\n")
            else:
                f.write("No stocks in draft yet.\n")

    def run(self, interval_minutes: int = 10):
        """Run continuously"""
        self.running = True

        print("=" * 70)
        print("AUTO PORTFOLIO - Running")
        print("=" * 70)
        print(f"Draft file: {self.draft_file}")
        print(f"Check interval: {interval_minutes} minutes")
        print("Press Ctrl+C to stop\n")

        while self.running:
            try:
                # Check market first
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking market...")
                market_ok, market_info = self._check_market()

                if not market_ok:
                    print(f"  Market not favorable: {market_info}")
                    print(f"  Waiting {interval_minutes} minutes...")
                    time.sleep(interval_minutes * 60)
                    continue

                print(f"  Market: {market_info}")

                # Scan for stocks
                print("  Scanning stocks...")
                new_finds = self._scan_stocks()

                if new_finds:
                    print(f"  Found {len(new_finds)} new stocks!")
                    for stock in new_finds:
                        self._add_to_draft(stock)
                        conf = "HIGH" if stock.confidence >= 90 else "GOOD"
                        print(f"    + {stock.symbol} ({conf} {stock.confidence}%)")
                else:
                    print("  No new stocks matching criteria")

                # Show current drafts
                self.show_drafts(brief=True)

                # Save
                self._save_data()

                # Wait
                print(f"\nWaiting {interval_minutes} minutes...")
                time.sleep(interval_minutes * 60)

            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)

        print("\nStopped.")
        self._save_data()

    def run_once(self):
        """Run one scan"""
        print("=" * 70)
        print("AUTO PORTFOLIO - Single Scan")
        print("=" * 70)

        market_ok, market_info = self._check_market()
        print(f"Market: {market_info}")

        if not market_ok:
            print("Market not favorable. No scan.")
            return

        print("\nScanning stocks...")
        new_finds = self._scan_stocks()

        if new_finds:
            print(f"\nFound {len(new_finds)} stocks:")
            for stock in new_finds:
                self._add_to_draft(stock)
                conf = "HIGH" if stock.confidence >= 90 else "GOOD"
                print(f"  {stock.symbol}: {conf} confidence ({stock.confidence}%)")
                for r in stock.reasons[:2]:
                    print(f"    + {r}")

        self._save_data()
        self.show_drafts()

    def _check_market(self):
        """Check market conditions"""
        if yf is None:
            return True, "No data"

        try:
            spy = yf.download('SPY', period='30d', progress=False)
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)

            price = float(spy['Close'].iloc[-1])
            ma20 = float(spy['Close'].tail(20).mean())
            trend = 'UP' if price > ma20 else 'DOWN'

            vix = yf.download('^VIX', period='5d', progress=False)
            if isinstance(vix.columns, pd.MultiIndex):
                vix.columns = vix.columns.get_level_values(0)
            vix_val = float(vix['Close'].iloc[-1])

            info = f"SPY {trend} ({((price/ma20)-1)*100:+.1f}%), VIX {vix_val:.1f}"

            # Avoid October, November
            if datetime.now().month in [10, 11]:
                return False, f"Bad month (Oct/Nov) - {info}"

            if trend == 'DOWN':
                return False, f"Market downtrend - {info}"

            if vix_val > 25:
                return False, f"VIX too high - {info}"

            return True, info

        except Exception as e:
            return True, f"Error: {e}"

    def _scan_stocks(self) -> List[DraftStock]:
        """Scan for stocks"""
        finds = []
        seen = set(d.symbol for d in self.drafts)  # Don't add duplicates

        for sector, symbols in self.UNIVERSE.items():
            for symbol in symbols:
                if symbol in seen:
                    continue

                result = self._analyze_stock(symbol, sector)
                if result:
                    finds.append(result)
                    seen.add(symbol)

                time.sleep(1)  # Rate limit

        return finds

    def _analyze_stock(self, symbol: str, sector: str) -> Optional[DraftStock]:
        """Analyze a stock"""
        if yf is None:
            return None

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

            # CRITERIA CHECK
            reasons = []
            score = 0

            # Gate 1: Accumulation
            if accum <= 1.2:
                return None
            if accum >= 1.5:
                reasons.append(f"Strong accumulation ({accum:.2f})")
                score += 25
            else:
                reasons.append(f"Accumulation OK ({accum:.2f})")
                score += 15

            # Gate 2: RSI
            if rsi >= 58 or rsi <= 30:
                return None
            if 40 <= rsi <= 50:
                reasons.append(f"Ideal RSI ({rsi:.0f})")
                score += 20
            else:
                reasons.append(f"RSI OK ({rsi:.0f})")
                score += 10

            # Gate 3: Above MAs
            if above_ma20 <= 0 or above_ma50 <= 0:
                return None
            if above_ma20 > 2:
                reasons.append(f"Above MA20 by {above_ma20:.1f}%")
                score += 15
            else:
                score += 5

            # Gate 4: ATR
            if atr_pct > 3.0:
                return None
            if atr_pct < 2.0:
                reasons.append(f"Low volatility ({atr_pct:.2f}%)")
                score += 20
            else:
                score += 10

            # Bonus: Sector
            if sector in ['Finance', 'Industrial']:
                reasons.append(f"Strong sector ({sector})")
                score += 10

            # Calculate confidence
            confidence = min(100, int(score * 1.2))

            if confidence < 50:
                return None

            return DraftStock(
                symbol=symbol,
                sector=sector,
                entry_price=price,
                found_at=datetime.now().isoformat(),
                confidence=confidence,
                score=score,
                reasons=reasons,
                metrics={
                    'rsi': round(rsi, 1),
                    'accum': round(accum, 2),
                    'atr_pct': round(atr_pct, 2),
                    'above_ma20': round(above_ma20, 2),
                },
                status='draft'
            )

        except:
            return None

    def _add_to_draft(self, stock: DraftStock):
        """Add stock to draft"""
        # Remove if already exists
        self.drafts = [d for d in self.drafts if d.symbol != stock.symbol]
        self.drafts.append(stock)

    def pick_stock(self, symbol: str):
        """Move stock from draft to portfolio"""
        for i, draft in enumerate(self.drafts):
            if draft.symbol == symbol:
                draft.status = 'picked'
                self.portfolio.append(draft)
                del self.drafts[i]
                self._save_data()
                print(f"Picked {symbol} into portfolio!")
                return

        print(f"{symbol} not found in drafts")

    def pass_stock(self, symbol: str):
        """Mark stock as passed (don't want)"""
        for draft in self.drafts:
            if draft.symbol == symbol:
                draft.status = 'passed'
                self._save_data()
                print(f"Passed on {symbol}")
                return

        print(f"{symbol} not found in drafts")

    def show_drafts(self, brief: bool = False):
        """Show draft portfolio"""
        if brief:
            if self.drafts:
                symbols = [f"{d.symbol}({d.confidence}%)" for d in
                          sorted(self.drafts, key=lambda x: x.confidence, reverse=True)[:5]]
                print(f"  Drafts: {', '.join(symbols)}")
            return

        print("\n" + "=" * 70)
        print("DRAFT PORTFOLIO")
        print("=" * 70)

        if not self.drafts:
            print("No stocks in draft.")
            return

        drafts = sorted(self.drafts, key=lambda x: x.confidence, reverse=True)

        print(f"\n{'Symbol':<8} {'Sector':<12} {'Conf':<6} {'Price':<10} {'Found'}")
        print("-" * 60)

        for d in drafts:
            found = d.found_at[:16] if d.found_at else "?"
            print(f"{d.symbol:<8} {d.sector:<12} {d.confidence}%    ${d.entry_price:<9.2f} {found}")

        print(f"\nTotal: {len(drafts)} stocks")
        print(f"\nTo pick: auto.pick_stock('SYMBOL')")
        print(f"To pass: auto.pass_stock('SYMBOL')")

    def show_portfolio(self):
        """Show picked portfolio"""
        print("\n" + "=" * 70)
        print("PORTFOLIO (Picked)")
        print("=" * 70)

        if not self.portfolio:
            print("Empty portfolio.")
            return

        for p in self.portfolio:
            print(f"\n{p.symbol} ({p.sector})")
            print(f"  Entry: ${p.entry_price:.2f}")
            print(f"  Picked: {p.found_at[:10]}")

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


def main():
    """Entry point"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    AUTO PORTFOLIO                            ║
║   ระบบค้นหาและเก็บหุ้นอัตโนมัติ                              ║
╚══════════════════════════════════════════════════════════════╝

Usage:
  python auto_portfolio.py              # Run once
  python auto_portfolio.py --continuous # Run continuously

The system will:
1. Check market conditions
2. Scan all stocks in universe
3. Find stocks matching criteria
4. Save to draft portfolio

You just come back and check what's been found!
""")

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--continuous', '-c', action='store_true')
    args = parser.parse_args()

    auto = AutoPortfolio()

    if args.continuous:
        auto.run()
    else:
        auto.run_once()


if __name__ == '__main__':
    main()
