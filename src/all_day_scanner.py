#!/usr/bin/env python3
"""
ALL-DAY SCANNER - ระบบสแกนหุ้นตลอดทั้งวัน

รันตลอด 24 ชั่วโมง (หรือเฉพาะ market hours) เพื่อ:
1. หาหุ้น Pullback Catalyst
2. Monitor portfolio
3. ส่ง alerts เมื่อเจอโอกาส

Usage:
    # รันแบบ basic (console output)
    python src/all_day_scanner.py

    # รันเป็น daemon
    nohup python src/all_day_scanner.py > logs/scanner.log 2>&1 &

    # รันด้วย screen
    screen -S scanner python src/all_day_scanner.py
"""

import os
import sys
import json
import time
import signal
from datetime import datetime, timedelta
from typing import Optional
import warnings
warnings.filterwarnings('ignore')

# Add parent to path
sys.path.insert(0, os.path.dirname(__file__))

from loguru import logger

# Configure logging
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

log_file = os.path.join(LOG_DIR, f"scanner_{datetime.now().strftime('%Y%m%d')}.log")
logger.add(log_file, rotation="1 day", retention="7 days", level="INFO")


class AllDayScanner:
    """All-day stock scanner with Pullback Catalyst strategy"""

    def __init__(self):
        self.running = True
        self.scan_interval = 10  # minutes between scans
        self.last_scan = None
        self.opportunities = []
        self.alerts_sent = set()

        # Results file
        self.results_file = os.path.join(LOG_DIR, 'latest_opportunities.json')

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        logger.info("="*60)
        logger.info("🚀 ALL-DAY SCANNER INITIALIZED")
        logger.info("="*60)

    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown"""
        logger.info("🛑 Shutdown signal received, saving state...")
        self.running = False
        self._save_results()

    def is_market_hours(self) -> bool:
        """Check if within US market hours (simplified)"""
        # Note: This is simplified - doesn't account for holidays
        now = datetime.now()

        # Weekday check (0=Monday, 6=Sunday)
        if now.weekday() >= 5:
            return False

        # Market hours: 9:30 AM - 4:00 PM ET
        # Simplified: assume local time is ET or close enough
        hour = now.hour
        minute = now.minute

        # Pre-market starts at 4 AM, regular at 9:30 AM, closes at 4 PM
        if hour < 9 or (hour == 9 and minute < 30):
            return False  # Before market open
        if hour >= 16:
            return False  # After market close

        return True

    def run_pullback_scan(self) -> list:
        """Run pullback catalyst scan"""
        logger.info("🔍 Running Pullback Catalyst scan...")

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
                max_stocks=20,
                lookback_days=5,
            )

            logger.info(f"✅ Found {len(opportunities)} pullback opportunities")
            return opportunities

        except Exception as e:
            logger.error(f"❌ Pullback scan error: {e}")
            return []

    def run_portfolio_check(self) -> dict:
        """Check portfolio for exit signals"""
        logger.info("📊 Checking portfolio...")

        try:
            from portfolio_manager_v3 import PortfolioManagerV3

            pm = PortfolioManagerV3()
            current_date = datetime.now().strftime('%Y-%m-%d')
            updates = pm.update_positions(current_date)

            exit_positions = updates.get('exit_positions', [])
            holding = updates.get('holding', [])

            if exit_positions:
                logger.warning(f"⚠️ {len(exit_positions)} positions need exit!")
                for pos in exit_positions:
                    logger.warning(f"   - {pos['symbol']}: {pos['exit_reason']}")

            logger.info(f"✅ Portfolio: {len(holding)} positions, {len(exit_positions)} exit signals")

            return {
                'holding': len(holding),
                'exit_signals': exit_positions,
            }

        except Exception as e:
            logger.error(f"❌ Portfolio check error: {e}")
            return {'holding': 0, 'exit_signals': []}

    def send_alert(self, alert_type: str, message: str, data: dict = None):
        """Send alert (console + file for now)"""
        alert_id = f"{alert_type}_{datetime.now().strftime('%Y%m%d_%H%M')}"

        if alert_id in self.alerts_sent:
            return  # Don't repeat same alert

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Console alert
        print("\n" + "="*60)
        print(f"🔔 ALERT: {alert_type}")
        print(f"⏰ Time: {timestamp}")
        print(f"📝 {message}")
        if data:
            for k, v in data.items():
                print(f"   {k}: {v}")
        print("="*60 + "\n")

        # Log alert
        logger.warning(f"ALERT [{alert_type}]: {message}")

        # Save to file
        alerts_file = os.path.join(LOG_DIR, 'alerts.json')
        try:
            if os.path.exists(alerts_file):
                with open(alerts_file, 'r') as f:
                    alerts = json.load(f)
            else:
                alerts = []

            alerts.append({
                'timestamp': timestamp,
                'type': alert_type,
                'message': message,
                'data': data,
            })

            # Keep last 100 alerts
            alerts = alerts[-100:]

            with open(alerts_file, 'w') as f:
                json.dump(alerts, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save alert: {e}")

        self.alerts_sent.add(alert_id)

    def _save_results(self):
        """Save current opportunities to file"""
        try:
            with open(self.results_file, 'w') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'opportunities': self.opportunities,
                    'count': len(self.opportunities),
                }, f, indent=2, default=str)
            logger.info(f"💾 Saved {len(self.opportunities)} opportunities to {self.results_file}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")

    def run_scan_cycle(self):
        """Run one complete scan cycle"""
        cycle_start = datetime.now()
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 SCAN CYCLE START: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")

        # 1. Check if market is open
        if not self.is_market_hours():
            logger.info("📴 Market closed - skipping full scan")
            logger.info("   Next scan will run during market hours")
            return

        # 2. Run pullback catalyst scan
        self.opportunities = self.run_pullback_scan()

        # Alert if high-conviction opportunities found
        high_conviction = [o for o in self.opportunities if o.get('catalyst_score', 0) >= 60]
        if high_conviction:
            for opp in high_conviction[:3]:  # Top 3
                self.send_alert(
                    "PULLBACK_OPPORTUNITY",
                    f"{opp['symbol']} - Catalyst Score: {opp['catalyst_score']:.0f}",
                    {
                        'Entry': f"${opp.get('entry_price', 0):.2f}",
                        'Stop': f"${opp.get('stop_loss', 0):.2f}",
                        'Target': f"${opp.get('target2', 0):.2f}",
                        'RSI': f"{opp.get('rsi', 0):.1f}",
                        'Recommendation': opp.get('recommendation', 'MONITOR'),
                    }
                )

        # 3. Check portfolio
        portfolio_status = self.run_portfolio_check()

        # Alert if exit signals
        if portfolio_status['exit_signals']:
            for exit_sig in portfolio_status['exit_signals']:
                self.send_alert(
                    "EXIT_SIGNAL",
                    f"{exit_sig['symbol']} - {exit_sig['exit_reason']}",
                    exit_sig
                )

        # 4. Save results
        self._save_results()

        # 5. Log cycle summary
        cycle_end = datetime.now()
        duration = (cycle_end - cycle_start).total_seconds()

        logger.info(f"\n📋 CYCLE SUMMARY:")
        logger.info(f"   Duration: {duration:.1f} seconds")
        logger.info(f"   Opportunities: {len(self.opportunities)}")
        logger.info(f"   High Conviction: {len(high_conviction)}")
        logger.info(f"   Portfolio Positions: {portfolio_status['holding']}")
        logger.info(f"   Exit Signals: {len(portfolio_status['exit_signals'])}")

        self.last_scan = cycle_end

    def run(self, continuous: bool = True):
        """Run the scanner"""
        logger.info(f"🚀 Starting All-Day Scanner")
        logger.info(f"   Scan Interval: {self.scan_interval} minutes")
        logger.info(f"   Mode: {'Continuous' if continuous else 'Single scan'}")
        logger.info(f"   Results: {self.results_file}")

        if not continuous:
            # Single scan mode
            self.run_scan_cycle()
            return

        # Continuous mode
        logger.info("\n⏳ Starting continuous scanning...")
        logger.info("   Press Ctrl+C to stop\n")

        while self.running:
            try:
                self.run_scan_cycle()

                if not self.running:
                    break

                # Wait for next scan
                next_scan = datetime.now() + timedelta(minutes=self.scan_interval)
                logger.info(f"\n⏰ Next scan at: {next_scan.strftime('%H:%M:%S')}")
                logger.info(f"   (Sleeping {self.scan_interval} minutes...)\n")

                # Sleep in small chunks to allow graceful shutdown
                for _ in range(self.scan_interval * 60):
                    if not self.running:
                        break
                    time.sleep(1)

            except KeyboardInterrupt:
                logger.info("🛑 Interrupted by user")
                self.running = False
            except Exception as e:
                logger.error(f"❌ Scan cycle error: {e}")
                # Wait a bit before retrying
                time.sleep(60)

        logger.info("👋 Scanner stopped")
        self._save_results()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='All-Day Stock Scanner')
    parser.add_argument('--once', action='store_true', help='Run single scan only')
    parser.add_argument('--interval', type=int, default=10, help='Scan interval in minutes')
    args = parser.parse_args()

    scanner = AllDayScanner()
    scanner.scan_interval = args.interval

    if args.once:
        scanner.run(continuous=False)
    else:
        scanner.run(continuous=True)


if __name__ == '__main__':
    main()
