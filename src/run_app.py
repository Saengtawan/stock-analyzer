#!/usr/bin/env python3
"""
RAPID TRADING SYSTEM - Target 5-15% per month

Services:
1. Web Server (Flask) - http://localhost:5000
2. Rapid Portfolio Monitor - เช็ค portfolio ทุก 5 นาที (ตัดขาดทุนเร็ว!)
3. Rapid Rotation Scanner - หาหุ้นใหม่ทุก 15 นาที

Usage:
    python src/run_app.py
"""

import os
import sys
import time
import signal
import threading
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

import warnings
warnings.filterwarnings('ignore')

from loguru import logger

# Configure logging
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, f"app_{datetime.now().strftime('%Y%m%d')}.log")
logger.add(log_file, rotation="1 day", retention="7 days", level="INFO")


class ServiceManager:
    """Manage all services"""

    def __init__(self):
        self.running = True
        self.services = {}

        # Health check state
        self.health_status = {}
        self.last_portfolio_check = None
        self.last_scanner_run = None

        # Handle shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        print("\n")
        logger.info("=" * 60)
        logger.info("SHUTTING DOWN ALL SERVICES...")
        logger.info("=" * 60)
        self.running = False

    def start_web_server(self):
        """Start Flask web server"""
        try:
            logger.info("Starting Web Server...")

            from web.app import app

            # Run in thread
            def run_flask():
                app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)

            flask_thread = threading.Thread(target=run_flask, daemon=True)
            flask_thread.start()

            self.services['web'] = flask_thread
            logger.info("Web Server started at http://localhost:5000")

            return True

        except Exception as e:
            logger.error(f"Web Server failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start_rapid_portfolio_monitor(self):
        """Start rapid portfolio monitor - เช็คทุก 5 นาที เตือนถ้าต้องขาย"""
        try:
            logger.info("Starting Rapid Portfolio Monitor...")

            from rapid_portfolio_manager import RapidPortfolioManager, ExitSignal

            self.rapid_portfolio = RapidPortfolioManager()

            def run_monitor():
                check_interval = 5 * 60  # 5 minutes

                while self.running:
                    try:
                        if self.rapid_portfolio.positions:
                            statuses = self.rapid_portfolio.check_all_positions()
                            self.last_portfolio_check = datetime.now()

                            # Check for critical alerts
                            for status in statuses:
                                if status.signal == ExitSignal.CRITICAL:
                                    logger.warning(f"🔴 CRITICAL: {status.symbol} - {status.action}")
                                    print(f"\n🔴 ALERT: {status.symbol} ลง {status.pnl_pct:.1f}% - ขายทันที!\n")
                                elif status.signal == ExitSignal.WARNING:
                                    logger.warning(f"🟠 WARNING: {status.symbol} - {status.action}")
                                elif status.signal == ExitSignal.TAKE_PROFIT:
                                    logger.info(f"🎯 TAKE PROFIT: {status.symbol} +{status.pnl_pct:.1f}%")
                                    print(f"\n🎯 {status.symbol} ถึงเป้า +{status.pnl_pct:.1f}% - ขายเอากำไร!\n")

                        if not self.rapid_portfolio.positions:
                            self.last_portfolio_check = datetime.now()

                        if not self.running:
                            break

                        # Wait for next check
                        for _ in range(check_interval):
                            if not self.running:
                                break
                            time.sleep(1)

                    except Exception as e:
                        logger.error(f"Portfolio monitor error: {e}")
                        time.sleep(60)

            monitor_thread = threading.Thread(target=run_monitor, daemon=True)
            monitor_thread.start()

            self.services['rapid_monitor'] = monitor_thread
            logger.info("Rapid Portfolio Monitor started (check every 5 minutes)")

            return True

        except Exception as e:
            logger.error(f"Rapid Portfolio Monitor failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start_rapid_rotation_scanner(self):
        """Start rapid rotation scanner - หาหุ้นใหม่ทุก 15 นาที"""
        try:
            logger.info("Starting Rapid Rotation Scanner...")

            from screeners.rapid_rotation_screener import RapidRotationScreener

            self.rapid_screener = RapidRotationScreener()

            # Store latest signals
            self.latest_rapid_signals = []

            def run_rapid_scanner():
                scan_interval = 15 * 60  # 15 minutes

                while self.running:
                    try:
                        logger.info("Rapid Rotation: Scanning...")
                        self.rapid_screener.load_data()
                        signals = self.rapid_screener.screen(top_n=5)

                        self.latest_rapid_signals = signals
                        self.last_scanner_run = datetime.now()

                        if signals:
                            logger.info(f"Rapid Rotation: Found {len(signals)} signals")
                            top = signals[0]
                            logger.info(f"  Top pick: {top.symbol} @ ${top.entry_price:.2f} (Score: {top.score})")
                        else:
                            logger.info("Rapid Rotation: No signals")

                        if not self.running:
                            break

                        # Wait for next scan
                        for _ in range(scan_interval):
                            if not self.running:
                                break
                            time.sleep(1)

                    except Exception as e:
                        logger.error(f"Rapid scanner error: {e}")
                        time.sleep(60)

            scanner_thread = threading.Thread(target=run_rapid_scanner, daemon=True)
            scanner_thread.start()

            self.services['rapid_scanner'] = scanner_thread
            logger.info("Rapid Rotation Scanner started (scan every 15 minutes)")

            return True

        except Exception as e:
            logger.error(f"Rapid Rotation Scanner failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start_health_checker(self):
        """Start health checker - เช็คระบบทุก 5 นาที"""
        def run_health():
            check_interval = 5 * 60  # 5 minutes

            while self.running:
                try:
                    status = self._check_health()
                    self.health_status = status

                    if not status['healthy']:
                        logger.warning("=" * 40)
                        logger.warning("HEALTH CHECK FAILED")
                        for issue in status['issues']:
                            logger.warning(f"  HEALTH: {issue}")
                        logger.warning("=" * 40)
                    else:
                        logger.debug("Health check: All OK")

                except Exception as e:
                    logger.error(f"Health checker error: {e}")
                    self.health_status = {
                        'healthy': False,
                        'timestamp': datetime.now().isoformat(),
                        'checks': {},
                        'issues': [f'Health checker error: {e}']
                    }

                # Wait for next check (breakable)
                for _ in range(check_interval):
                    if not self.running:
                        break
                    time.sleep(1)

        thread = threading.Thread(target=run_health, daemon=True)
        thread.start()
        self.services['health'] = thread
        logger.info("Health Checker started (check every 5 minutes)")

    def _check_health(self):
        """Run all health checks and return status dict"""
        checks = {}
        issues = []
        now = datetime.now()

        # 1. Alpaca API
        try:
            from alpaca_trader import AlpacaTrader
            trader = AlpacaTrader(paper=True)
            account = trader.get_account()
            checks['alpaca_api'] = {
                'ok': True,
                'detail': f"Connected, ${account['portfolio_value']:,.0f}"
            }
        except Exception as e:
            checks['alpaca_api'] = {'ok': False, 'detail': str(e)}
            issues.append(f"Alpaca API down: {e}")

        # 2. Market clock
        try:
            clock = trader.get_clock()
            market_status = "Open" if clock['is_open'] else "Closed"
            checks['market_clock'] = {
                'ok': True,
                'detail': market_status
            }
        except Exception as e:
            checks['market_clock'] = {'ok': False, 'detail': str(e)}
            issues.append(f"Market clock error: {e}")

        # 3. Thread liveness
        alive_count = 0
        total_count = 0
        dead_threads = []
        for name, thread in self.services.items():
            if name == 'health':
                continue  # Don't check self
            total_count += 1
            if thread.is_alive():
                alive_count += 1
            else:
                dead_threads.append(name)

        if dead_threads:
            checks['threads'] = {
                'ok': False,
                'detail': f"{alive_count}/{total_count} alive, dead: {', '.join(dead_threads)}"
            }
            issues.append(f"Dead threads: {', '.join(dead_threads)}")
        else:
            checks['threads'] = {
                'ok': True,
                'detail': f"{alive_count}/{total_count} alive"
            }

        # 4. Portfolio monitor freshness
        if self.last_portfolio_check:
            age_sec = (now - self.last_portfolio_check).total_seconds()
            age_min = age_sec / 60
            if age_sec > 600:  # > 10 minutes
                checks['portfolio_monitor'] = {
                    'ok': False,
                    'detail': f"Stale: last check {age_min:.0f}m ago"
                }
                issues.append(f"Portfolio monitor stale ({age_min:.0f}m)")
            else:
                checks['portfolio_monitor'] = {
                    'ok': True,
                    'detail': f"Last check {age_min:.0f}m ago"
                }
        else:
            checks['portfolio_monitor'] = {
                'ok': True,
                'detail': 'Not started yet'
            }

        # 5. Scanner freshness
        if self.last_scanner_run:
            age_sec = (now - self.last_scanner_run).total_seconds()
            age_min = age_sec / 60
            if age_sec > 1800:  # > 30 minutes
                checks['scanner'] = {
                    'ok': False,
                    'detail': f"Stale: last scan {age_min:.0f}m ago"
                }
                issues.append(f"Scanner stale ({age_min:.0f}m)")
            else:
                checks['scanner'] = {
                    'ok': True,
                    'detail': f"Last scan {age_min:.0f}m ago"
                }
        else:
            checks['scanner'] = {
                'ok': True,
                'detail': 'Not started yet'
            }

        # 6. Positions sync (Alpaca vs in-memory)
        try:
            if hasattr(self, 'rapid_portfolio'):
                alpaca_positions = trader.get_positions()
                memory_count = len(self.rapid_portfolio.positions) if self.rapid_portfolio.positions else 0
                alpaca_count = len(alpaca_positions)

                if memory_count != alpaca_count:
                    checks['positions_sync'] = {
                        'ok': False,
                        'detail': f"Mismatch: memory={memory_count}, Alpaca={alpaca_count}"
                    }
                    issues.append(f"Position mismatch: memory={memory_count}, Alpaca={alpaca_count}")
                else:
                    checks['positions_sync'] = {
                        'ok': True,
                        'detail': f"{alpaca_count} position(s), in sync"
                    }
            else:
                checks['positions_sync'] = {
                    'ok': True,
                    'detail': 'Portfolio manager not loaded'
                }
        except Exception as e:
            checks['positions_sync'] = {'ok': False, 'detail': str(e)}
            issues.append(f"Position sync check error: {e}")

        return {
            'healthy': len(issues) == 0,
            'timestamp': now.isoformat(),
            'checks': checks,
            'issues': issues
        }

    def run(self):
        """Run all services"""
        print()
        print("=" * 60)
        print("  🚀 RAPID TRADING SYSTEM")
        print("  Target: 5-15% per month")
        print("=" * 60)
        print()

        # Start services
        web_ok = self.start_web_server()
        time.sleep(2)

        rapid_monitor_ok = self.start_rapid_portfolio_monitor()
        time.sleep(1)

        rapid_scanner_ok = self.start_rapid_rotation_scanner()

        self.start_health_checker()

        print()
        print("=" * 60)
        print("  SERVICES STATUS")
        print("=" * 60)
        print(f"   Web Server:        {'✅ Running' if web_ok else '❌ Failed'}")
        print(f"   Portfolio Monitor: {'✅ Running' if rapid_monitor_ok else '❌ Failed'}")
        print(f"   Rapid Scanner:     {'✅ Running' if rapid_scanner_ok else '❌ Failed'}")
        print()
        print("=" * 60)
        print("  WEB UI")
        print("=" * 60)
        print("   🚀 Rapid Trader:  http://localhost:5000/rapid")
        print("   📊 Portfolio:     http://localhost:5000/portfolio")
        print("   🔍 Screen:        http://localhost:5000/screen")
        print()
        print("=" * 60)
        print("  RAPID TRADER v3.0 - FULLY INTEGRATED")
        print("=" * 60)
        print("   🤖 AI Universe: 680+ stocks (DeepSeek)")
        print("   📊 Market Regime: Bull/Bear/Sideways")
        print("   🔥 Sector Regime: Hot sectors")
        print("   📰 Alt Data: Insider, Sentiment, Short")
        print()
        print("=" * 60)
        print("  TRADING RULES")
        print("=" * 60)
        print("   📈 Buy:  TRUE DIP only (Mom1d < 0)")
        print("   🔴 Stop Loss:  1.5-2.5% (ATR-based)")
        print("   🎯 Take Profit: +4-6%")
        print("   ⏰ Max Hold: 4 days")
        print()
        print("=" * 60)
        print("  MONITORS")
        print("=" * 60)
        print("   Portfolio: เช็คทุก 5 นาที")
        print("   Scanner:   หาหุ้นใหม่ทุก 15 นาที")
        print()
        print("=" * 60)
        print("   Press Ctrl+C to stop")
        print("=" * 60)
        print()

        # Keep running
        while self.running:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break

        print()
        logger.info("All services stopped")
        print("=" * 60)
        print("  Goodbye!")
        print("=" * 60)


def main():
    manager = ServiceManager()
    manager.run()


if __name__ == '__main__':
    main()
