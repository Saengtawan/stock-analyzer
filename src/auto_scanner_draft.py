#!/usr/bin/env python3
"""
🤖 AUTO SCANNER WITH DRAFT SYSTEM

ระบบอัตโนมัติที่:
1. สแกนหาหุ้นอัตโนมัติทุก 10 นาที
2. เก็บไว้ใน DRAFT (ยังไม่ซื้อ)
3. คุณเลือกเองว่าจะ Pick เข้า Portfolio ตัวไหน
4. ดูผ่าน Web UI: http://localhost:5000/drafts

Usage:
    # เริ่มระบบ
    python src/auto_scanner_draft.py

    # รันเป็น background
    nohup python src/auto_scanner_draft.py > logs/scanner.log 2>&1 &

    # ดู status
    python src/auto_scanner_draft.py --status
"""

import os
import sys
import json
import time
import signal
from datetime import datetime, timedelta
from typing import List, Dict
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(__file__))

from loguru import logger

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_DIR = os.path.join(DATA_DIR, 'logs')
DRAFTS_FILE = os.path.join(DATA_DIR, 'draft_stocks.json')
STATUS_FILE = os.path.join(LOG_DIR, 'scanner_status.json')

os.makedirs(LOG_DIR, exist_ok=True)

# Logging
log_file = os.path.join(LOG_DIR, f"scanner_{datetime.now().strftime('%Y%m%d')}.log")
logger.add(log_file, rotation="1 day", retention="7 days", level="INFO")


class AutoScannerDraft:
    """Auto Scanner that saves to Draft for manual review"""

    def __init__(self):
        self.running = True
        self.scan_interval = 10  # minutes
        self.drafts = self._load_drafts()

        self.stats = {
            'total_scans': 0,
            'opportunities_found': 0,
            'drafts_added': 0,
            'start_time': datetime.now().isoformat(),
            'last_scan': None,
        }

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info("="*60)
        logger.info("🤖 AUTO SCANNER (DRAFT MODE) STARTED")
        logger.info("="*60)
        logger.info(f"   Scan Interval: {self.scan_interval} minutes")
        logger.info(f"   Drafts File: {DRAFTS_FILE}")
        logger.info(f"   Web UI: http://localhost:5000/drafts")
        logger.info("="*60)

    def _shutdown(self, signum, frame):
        logger.info("🛑 Shutdown...")
        self.running = False
        self._save_all()

    def _load_drafts(self) -> List[Dict]:
        """Load draft stocks"""
        if os.path.exists(DRAFTS_FILE):
            try:
                with open(DRAFTS_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('drafts', [])
            except Exception:
                pass
        return []

    def _save_drafts(self):
        """Save draft stocks"""
        try:
            with open(DRAFTS_FILE, 'w') as f:
                json.dump({
                    'last_update': datetime.now().isoformat(),
                    'count': len(self.drafts),
                    'drafts': self.drafts,
                }, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving drafts: {e}")

    def _save_status(self):
        """Save scanner status"""
        try:
            with open(STATUS_FILE, 'w') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'running': self.running,
                    'stats': self.stats,
                    'draft_count': len(self.drafts),
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving status: {e}")

    def _save_all(self):
        self._save_drafts()
        self._save_status()
        logger.info("💾 All data saved")

    def is_market_hours(self) -> bool:
        """Check if market is open"""
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        hour = now.hour
        if hour < 9 or (hour == 9 and now.minute < 30):
            return False
        if hour >= 16:
            return False
        return True

    def scan_for_opportunities(self) -> List[Dict]:
        """Scan for pullback catalyst opportunities"""
        logger.info("🔍 Scanning for opportunities...")

        try:
            from screeners.pullback_catalyst_screener import PullbackCatalystScreener
            from main import StockAnalyzer

            analyzer = StockAnalyzer()
            screener = PullbackCatalystScreener(analyzer)

            opportunities = screener.screen_pullback_opportunities(
                min_price=20.0,
                max_price=500.0,
                min_volume_ratio=1.8,
                min_catalyst_score=45.0,
                max_rsi=76.0,
                max_stocks=30,
                lookback_days=5,
            )

            self.stats['total_scans'] += 1
            self.stats['opportunities_found'] += len(opportunities)
            self.stats['last_scan'] = datetime.now().isoformat()

            logger.info(f"✅ Found {len(opportunities)} opportunities")
            return opportunities

        except Exception as e:
            logger.error(f"Scan error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def add_to_drafts(self, opportunities: List[Dict]):
        """Add opportunities to draft list"""
        existing_symbols = {d['symbol'] for d in self.drafts}
        added = 0

        for opp in opportunities:
            symbol = opp['symbol']

            # Skip if already in drafts
            if symbol in existing_symbols:
                # Update existing draft with new data
                for draft in self.drafts:
                    if draft['symbol'] == symbol:
                        draft['last_seen'] = datetime.now().isoformat()
                        draft['current_price'] = opp.get('current_price', draft.get('current_price'))
                        draft['catalyst_score'] = opp.get('catalyst_score', draft.get('catalyst_score'))
                        draft['rsi'] = opp.get('rsi', draft.get('rsi'))
                        break
                continue

            # Add new draft
            draft = {
                'symbol': symbol,
                'company_name': opp.get('company_name', ''),
                'sector': opp.get('sector', ''),
                'added_date': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat(),
                'current_price': opp.get('current_price', 0),
                'entry_price': opp.get('entry_price', 0),
                'stop_loss': opp.get('stop_loss', 0),
                'target1': opp.get('target1', 0),
                'target2': opp.get('target2', 0),
                'target3': opp.get('target3', 0),
                'catalyst_score': opp.get('catalyst_score', 0),
                'rsi': opp.get('rsi', 0),
                'risk_reward': opp.get('risk_reward', 0),
                'recommendation': opp.get('recommendation', ''),
                'status': 'NEW',  # NEW, WATCHING, PICKED, EXPIRED
            }

            self.drafts.append(draft)
            existing_symbols.add(symbol)
            added += 1

            logger.info(f"📝 Added to DRAFT: {symbol} (Score: {draft['catalyst_score']:.0f})")

        if added > 0:
            self.stats['drafts_added'] += added
            logger.info(f"✅ Added {added} new stocks to DRAFT")

        # Clean old drafts (older than 7 days)
        cutoff = datetime.now() - timedelta(days=7)
        old_count = len(self.drafts)
        self.drafts = [
            d for d in self.drafts
            if datetime.fromisoformat(d['last_seen']) > cutoff
        ]
        removed = old_count - len(self.drafts)
        if removed > 0:
            logger.info(f"🗑️ Removed {removed} expired drafts")

        self._save_drafts()

    def run_cycle(self):
        """Run one scan cycle"""
        cycle_start = datetime.now()
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 SCAN CYCLE: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")

        if not self.is_market_hours():
            logger.info("📴 Market closed - skipping scan")
            self._save_status()
            return

        # Scan
        opportunities = self.scan_for_opportunities()

        # Add to drafts
        if opportunities:
            self.add_to_drafts(opportunities)

        # Report
        logger.info(f"\n📊 DRAFT STATUS:")
        logger.info(f"   Total Drafts: {len(self.drafts)}")
        logger.info(f"   New This Scan: {len([d for d in self.drafts if d['status'] == 'NEW'])}")
        logger.info(f"   High Conviction (Score >= 60): {len([d for d in self.drafts if d['catalyst_score'] >= 60])}")

        self._save_status()

    def run(self):
        """Main run loop"""
        logger.info("🚀 Starting Auto Scanner...")
        logger.info("   Press Ctrl+C to stop\n")

        while self.running:
            try:
                self.run_cycle()

                if not self.running:
                    break

                next_scan = datetime.now() + timedelta(minutes=self.scan_interval)
                logger.info(f"\n⏰ Next scan: {next_scan.strftime('%H:%M:%S')}")

                for _ in range(self.scan_interval * 60):
                    if not self.running:
                        break
                    time.sleep(1)

            except KeyboardInterrupt:
                logger.info("🛑 Interrupted")
                self.running = False
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(60)

        logger.info("👋 Scanner stopped")
        self._save_all()


def show_status():
    """Show current status"""
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'r') as f:
            status = json.load(f)

        print("\n" + "="*50)
        print("🤖 AUTO SCANNER STATUS")
        print("="*50)
        print(f"Last Update: {status.get('timestamp', 'N/A')}")
        print(f"Running: {status.get('running', False)}")
        print(f"Draft Count: {status.get('draft_count', 0)}")
        stats = status.get('stats', {})
        print(f"\nStats:")
        print(f"  Total Scans: {stats.get('total_scans', 0)}")
        print(f"  Opportunities Found: {stats.get('opportunities_found', 0)}")
        print(f"  Drafts Added: {stats.get('drafts_added', 0)}")
        print(f"  Last Scan: {stats.get('last_scan', 'N/A')}")
        print("="*50)

    # Show drafts
    if os.path.exists(DRAFTS_FILE):
        with open(DRAFTS_FILE, 'r') as f:
            data = json.load(f)

        drafts = data.get('drafts', [])
        if drafts:
            print(f"\n📋 TOP DRAFTS (by Catalyst Score):")
            print("-"*50)
            for d in sorted(drafts, key=lambda x: x['catalyst_score'], reverse=True)[:10]:
                score_emoji = "🔥" if d['catalyst_score'] >= 60 else "✅" if d['catalyst_score'] >= 50 else "📊"
                print(f"  {score_emoji} {d['symbol']:<6} Score: {d['catalyst_score']:.0f}  RSI: {d['rsi']:.1f}  ${d['current_price']:.2f}")
            print("-"*50)
    else:
        print("No drafts yet. Start the scanner first.")

    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Auto Scanner with Draft System')
    parser.add_argument('--status', action='store_true', help='Show status')
    parser.add_argument('--interval', type=int, default=10, help='Scan interval (minutes)')
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    scanner = AutoScannerDraft()
    scanner.scan_interval = args.interval
    scanner.run()


if __name__ == '__main__':
    main()
