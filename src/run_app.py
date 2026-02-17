#!/usr/bin/env python3
"""
RAPID TRADING SYSTEM - Target 5-15% per month

Services:
1. Web Server (Flask) - http://localhost:5000
2. Rapid Portfolio Monitor - เช็ค portfolio ทุก 5 นาที (ตัดขาดทุนเร็ว!)
3. Rapid Rotation Scanner - หาหุ้นใหม่ทุก 5 นาที
4. Universe Maintenance - เคลียร์หุ้น delisted ทุกวัน 2:00 AM

v6.25 CRITICAL FIX - Auto-Sell Implementation:
- Portfolio monitor now EXECUTES sells when CRITICAL or TAKE_PROFIT signals detected
- Previously: Only logged warnings, no protection (caused $130 loss)
- Now: Executes market sell, cancels SL/TP orders, removes position
- Protection: Double-checks broker position exists before selling

Usage:
    python src/run_app.py
"""

import os
import sys
import time
import json
import signal
import tempfile
import threading
from datetime import datetime
from dataclasses import asdict

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

# Load environment variables from .env file (v4.7)
from dotenv import load_dotenv
load_dotenv('.env')

import warnings
warnings.filterwarnings('ignore')

from loguru import logger
logger.info(f"Environment loaded - Alpaca API configured: {bool(os.getenv('ALPACA_API_KEY'))}")

# Initialize monitoring (Production)
from monitoring.startup import initialize_monitoring

# Configure logging with optimized rotation (Phase 1: Log Management)
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Remove default handler to avoid duplicate logs
logger.remove()

# Add console handler (minimal output)
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO",
    colorize=True
)

# Add file handler with rotation + compression
log_file = os.path.join(LOG_DIR, f"app_{datetime.now().strftime('%Y-%m-%d')}.log")
logger.add(
    log_file,
    rotation="10 MB",      # Rotate at 10MB (prevents giant files)
    retention="7 days",    # Keep last 7 days
    compression="zip",     # Compress rotated files (saves 70-80% space)
    enqueue=True,         # Thread-safe async logging
    backtrace=True,       # Enable detailed error traces
    diagnose=True,        # Enable variable inspection
    level="INFO"
)

# Production Grade v6.21: Add JSON structured logging (using loguru's serialize)
json_log_file = os.path.join(LOG_DIR, f"app_{datetime.now().strftime('%Y-%m-%d')}.json")
logger.add(
    json_log_file,
    serialize=True,      # Loguru's built-in JSON serialization
    rotation="10 MB",
    retention="7 days",
    compression="zip",
    enqueue=True,
    level="INFO"
)

# Signal cache file (shared between background scanner and Flask)
SIGNALS_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'cache')
SIGNALS_CACHE_FILE = os.path.join(SIGNALS_CACHE_DIR, 'rapid_signals.json')
os.makedirs(SIGNALS_CACHE_DIR, exist_ok=True)


class ServiceManager:
    """Manage all services"""

    def __init__(self):
        self.running = True
        self.services = {}

        # Health check state
        self.health_status = {}
        self.last_portfolio_check = None
        self.last_scanner_run = None
        self._scan_progress = {}

        # v5.1: Real-time streaming
        self.streamer = None
        self.rapid_portfolio = None

        # Handle shutdown
        # Auto-monitoring
        self.monitor = initialize_monitoring(auto_start=True, health_check_interval=300)

        # v6.21: Install signal handlers only in main thread (fix: "signal only works in main thread")
        try:
            import threading
            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGINT, self._shutdown)
                signal.signal(signal.SIGTERM, self._shutdown)
                logger.info("✅ Signal handlers installed in main thread")
            else:
                logger.warning("⚠️ Skipping signal handlers (not in main thread)")
        except Exception as e:
            logger.warning(f"⚠️ Could not install signal handlers: {e}")

    def _shutdown(self, signum, frame):
        """
        Graceful shutdown handler (v6.21 Production Grade - Phase 2 Item 1)

        Ensures clean shutdown:
        1. Stop accepting new signals
        2. Wait for pending orders (max 30s)
        3. Save portfolio state
        4. Stop streamer
        5. Close database connections
        """
        print("\n")
        logger.info("=" * 60)
        logger.info("🛑 GRACEFUL SHUTDOWN INITIATED")
        logger.info("=" * 60)
        self.running = False

        # Step 1: Stop accepting new signals
        logger.info("1. Stopping signal processing...")
        if hasattr(self, 'rapid_portfolio') and self.rapid_portfolio:
            try:
                # Signal engine to stop accepting new signals
                if hasattr(self.rapid_portfolio, 'engine'):
                    self.rapid_portfolio.engine.running = False
                    logger.info("   ✅ Engine stopped accepting new signals")
            except Exception as e:
                logger.error(f"   ❌ Error stopping engine: {e}")

        # Step 2: Wait for pending orders (max 30s)
        logger.info("2. Waiting for pending orders...")
        if hasattr(self, 'rapid_portfolio') and self.rapid_portfolio:
            try:
                from engine.brokers.alpaca_broker import AlpacaBroker
                if hasattr(self.rapid_portfolio, 'engine') and hasattr(self.rapid_portfolio.engine, 'broker'):
                    broker = self.rapid_portfolio.engine.broker
                    pending_orders = broker.get_orders(status='open')

                    if pending_orders:
                        logger.info(f"   Found {len(pending_orders)} pending orders")
                        timeout = 30
                        start = time.time()

                        while pending_orders and (time.time() - start) < timeout:
                            time.sleep(1)
                            pending_orders = broker.get_orders(status='open')
                            if len(pending_orders) > 0:
                                logger.debug(f"   Still waiting... {len(pending_orders)} orders pending")

                        if pending_orders:
                            logger.warning(
                                f"   ⚠️ {len(pending_orders)} orders still pending after {timeout}s. "
                                f"Orders: {[o.symbol for o in pending_orders]}"
                            )
                            # Note: We don't cancel them - let them complete naturally
                        else:
                            logger.info("   ✅ All orders completed")
                    else:
                        logger.info("   ✅ No pending orders")
            except Exception as e:
                logger.error(f"   ❌ Error checking pending orders: {e}")

        # Step 3: Save portfolio state
        logger.info("3. Saving portfolio state...")
        if hasattr(self, 'rapid_portfolio') and self.rapid_portfolio:
            try:
                if hasattr(self.rapid_portfolio, 'save_portfolio'):
                    self.rapid_portfolio.save_portfolio()
                    logger.info("   ✅ Portfolio state saved")
                elif hasattr(self.rapid_portfolio, 'engine') and hasattr(self.rapid_portfolio.engine, '_save_positions_state'):
                    self.rapid_portfolio.engine._save_positions_state()
                    logger.info("   ✅ Position state saved")
            except Exception as e:
                logger.error(f"   ❌ Failed to save portfolio state: {e}")

        # Step 4: Stop price streamer
        logger.info("4. Stopping price streamer...")
        if self.streamer:
            try:
                self.streamer.stop()
                logger.info("   ✅ Streamer stopped")
            except Exception as e:
                logger.error(f"   ❌ Error stopping streamer: {e}")

        # Step 5: Close database connections
        logger.info("5. Closing database connections...")
        try:
            from database import close_all_connections
            close_all_connections()
            logger.info("   ✅ Database connections closed")
        except Exception as e:
            logger.error(f"   ❌ Error closing database: {e}")

        logger.info("=" * 60)
        logger.info("✅ SHUTDOWN COMPLETE")
        logger.info("=" * 60)

        import sys
        sys.exit(0)

    def _update_cron_status(self, job_name, status):
        """Update cron job status in data/cron_status.json"""
        try:
            status_file = os.path.join(os.getcwd(), 'data', 'cron_status.json')

            # Load existing status
            if os.path.exists(status_file):
                with open(status_file, 'r') as f:
                    all_status = json.load(f)
            else:
                all_status = {}

            # Update this job's status
            all_status[job_name] = {
                'status': status,
                'last_run': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }

            # Write back
            os.makedirs(os.path.dirname(status_file), exist_ok=True)
            with open(status_file, 'w') as f:
                json.dump(all_status, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to update cron status for {job_name}: {e}")

    # v6.1: _save_signals_cache REMOVED - engine now writes cache directly

    def start_web_server(self):
        """Start Flask web server"""
        try:
            logger.info("Starting Web Server...")

            from web.app import app

            # Store reference to ServiceManager so web endpoints can access scan progress
            app.config['service_manager'] = self

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

    def _execute_emergency_sell(self, symbol: str, status, reason: str):
        """
        Execute emergency sell when CRITICAL or TAKE_PROFIT signal detected
        v6.25: Implements auto-sell to protect capital

        Args:
            symbol: Stock symbol to sell
            status: PositionStatus object with trade details
            reason: Sell reason (CRITICAL_SL or TAKE_PROFIT)
        """
        try:
            # Get position details
            if symbol not in self.rapid_portfolio.positions:
                logger.warning(f"❌ {symbol} not in portfolio - cannot sell")
                return

            position = self.rapid_portfolio.positions[symbol]

            # Double-check: Verify position exists at broker
            if not self.rapid_portfolio.broker:
                logger.error(f"❌ No broker connection - cannot auto-sell {symbol}")
                return

            broker_position = self.rapid_portfolio.broker.get_position(symbol)
            if not broker_position:
                logger.warning(f"❌ {symbol} position not found at broker - already closed?")
                # Remove from portfolio
                del self.rapid_portfolio.positions[symbol]
                self.rapid_portfolio.save_positions()
                return

            qty = broker_position.qty

            # Guard: market must be open for market sell
            if not self.rapid_portfolio.broker.is_market_open():
                logger.info(f"{symbol}: Market closed — will retry emergency sell when market opens (reason: {reason})")
                return

            # Execute market sell
            logger.info(f"🔴 AUTO-SELL: {symbol} {qty} shares @ ${status.current_price:.2f} | Reason: {reason} | P&L: {status.pnl_pct:+.2f}%")
            print(f"\n{'='*60}")
            print(f"🔴 AUTO-SELL EXECUTED")
            print(f"Symbol: {symbol}")
            print(f"Qty: {qty} shares")
            print(f"Price: ${status.current_price:.2f}")
            print(f"P&L: {status.pnl_pct:+.2f}% (${status.pnl_usd:+.2f})")
            print(f"Reason: {reason}")
            print(f"{'='*60}\n")

            order = self.rapid_portfolio.broker.place_market_sell(symbol, qty)

            if order and order.status in ['filled', 'new', 'accepted']:
                logger.info(f"✅ Sell order placed: {order.id} | Status: {order.status}")

                # Cancel any existing SL/TP orders
                if position.sl_order_id:
                    try:
                        self.rapid_portfolio.broker.cancel_order(position.sl_order_id)
                        logger.info(f"✅ Cancelled SL order: {position.sl_order_id}")
                    except Exception as e:
                        logger.debug(f"SL order cancel failed (may already be filled): {e}")

                if position.tp_order_id:
                    try:
                        self.rapid_portfolio.broker.cancel_order(position.tp_order_id)
                        logger.info(f"✅ Cancelled TP order: {position.tp_order_id}")
                    except Exception as e:
                        logger.debug(f"TP order cancel failed (may already be filled): {e}")

                # Remove from portfolio
                del self.rapid_portfolio.positions[symbol]
                self.rapid_portfolio.save_positions()

                logger.info(f"✅ {symbol} position closed and removed from portfolio")
            else:
                logger.error(f"❌ Sell order failed: {order}")

        except Exception as e:
            logger.error(f"❌ Emergency sell failed for {symbol}: {e}")
            import traceback
            traceback.print_exc()

    def start_rapid_portfolio_monitor(self):
        """Start rapid portfolio monitor - เช็คทุก 5 นาที เตือนถ้าต้องขาย"""
        try:
            logger.info("Starting Rapid Portfolio Monitor...")

            from rapid_portfolio_manager import RapidPortfolioManager, ExitSignal
            from engine.brokers.alpaca_broker import AlpacaBroker

            # v6.25: Initialize with broker for auto-sell capability
            broker = AlpacaBroker(paper=True)
            self.rapid_portfolio = RapidPortfolioManager(broker=broker)

            def run_monitor():
                check_interval = 5 * 60  # 5 minutes

                while self.running:
                    try:
                        if self.rapid_portfolio.positions:
                            statuses = self.rapid_portfolio.check_all_positions()
                            self.last_portfolio_check = datetime.now()

                            # Check for critical alerts and execute sells
                            for status in statuses:
                                if status.signal == ExitSignal.CRITICAL:
                                    logger.warning(f"🔴 CRITICAL: {status.symbol} - {status.action}")
                                    print(f"\n🔴 ALERT: {status.symbol} ลง {status.pnl_pct:.1f}% - ขายทันที!\n")

                                    # v6.25: AUTO-SELL when CRITICAL signal detected
                                    self._execute_emergency_sell(status.symbol, status, "CRITICAL_SL")

                                elif status.signal == ExitSignal.WARNING:
                                    logger.warning(f"🟠 WARNING: {status.symbol} - {status.action}")
                                elif status.signal == ExitSignal.TAKE_PROFIT:
                                    logger.info(f"🎯 TAKE PROFIT: {status.symbol} +{status.pnl_pct:.1f}%")
                                    print(f"\n🎯 {status.symbol} ถึงเป้า +{status.pnl_pct:.1f}% - ขายเอากำไร!\n")

                                    # v6.25: AUTO-SELL when TAKE_PROFIT signal detected
                                    self._execute_emergency_sell(status.symbol, status, "TAKE_PROFIT")

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

    def start_realtime_price_streamer(self):
        """
        Start real-time price streamer (v5.1)

        Connects AlpacaStreamer to Portfolio Monitor for instant peak tracking.
        No more 5-minute gaps - catches every price movement!
        """
        try:
            logger.info("Starting Real-time Price Streamer...")

            # v6.17: Stop old streamer BEFORE creating new one (prevents connection leak)
            if self.streamer:
                try:
                    logger.info("Stopping old streamer before creating new one...")
                    self.streamer.stop()
                except Exception as e:
                    logger.error(f"Error stopping old streamer: {e}")
                self.streamer = None

            # Import streamer
            from alpaca_streamer import AlpacaStreamer

            # Get Alpaca credentials
            api_key = os.getenv('ALPACA_API_KEY')
            secret_key = os.getenv('ALPACA_SECRET_KEY')

            if not api_key or not secret_key:
                logger.warning("Alpaca credentials not found - skipping real-time streaming")
                return False

            # Initialize streamer
            self.streamer = AlpacaStreamer(
                api_key=api_key,
                secret_key=secret_key,
                socketio=None,  # Don't need socketio for portfolio updates
                paper=True
            )

            # Register callback to update portfolio on price changes
            def on_price_update(symbol: str, price: float, data_type: str):
                """Called on EVERY price update from WebSocket!"""
                if self.rapid_portfolio and symbol in self.rapid_portfolio.positions:
                    self.rapid_portfolio.handle_realtime_price(symbol, price, data_type)

            self.streamer.on_price_update = on_price_update

            # Subscribe to all position symbols
            if self.rapid_portfolio and self.rapid_portfolio.positions:
                symbols = list(self.rapid_portfolio.positions.keys())
                self.streamer.subscribe(symbols, trades=True, bars=True, quotes=False)
                logger.info(f"📡 Subscribed to real-time prices: {symbols}")
            else:
                logger.warning("No positions to subscribe - will subscribe when positions are added")

            # Start streaming
            self.streamer.start()
            self.services['price_streamer'] = self.streamer

            logger.info("✅ Real-time Price Streamer started (WebSocket active!)")
            return True

        except Exception as e:
            error_msg = str(e).lower()
            if 'connection limit' in error_msg or '429' in error_msg:
                logger.warning("⚠️  Alpaca WebSocket connection limit reached")
                logger.warning("   Falling back to polling mode (checks every 5 minutes)")
                logger.warning("   Real-time streaming will resume when connections are available")
            else:
                logger.error(f"Real-time Price Streamer failed: {e}")
                import traceback
                traceback.print_exc()
            return False

    def subscribe_new_position(self, symbol: str):
        """Subscribe to real-time prices when new position is added"""
        if self.streamer and self.streamer.running:
            self.streamer.subscribe([symbol], trades=True, bars=True)
            logger.info(f"📡 Subscribed to real-time prices: {symbol}")

    def unsubscribe_closed_position(self, symbol: str):
        """Unsubscribe from real-time prices when position is closed"""
        if self.streamer and self.streamer.running:
            self.streamer.unsubscribe([symbol])
            logger.info(f"📡 Unsubscribed from: {symbol}")

    def _on_scan_progress(self, **kwargs):
        """Broadcast scan progress via Socket.IO for live UI"""
        progress = {
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        self._scan_progress = progress
        try:
            from web.app import socketio
            socketio.emit('scan_progress', progress)
        except Exception:
            pass  # Socket.IO not available yet

    # v6.1: _get_scanner_bear_sectors REMOVED - scanner moved to engine

    # v6.1: Scanner REMOVED - Engine is now single source of truth
    # UI reads from rapid_signals.json written by auto_trading_engine.py
    # This reduces API calls by 50%+ and ensures UI/Engine are always in sync

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

                        # Send alert via AlertManager
                        try:
                            from alert_manager import get_alert_manager
                            get_alert_manager().alert_health_check_fail(status['issues'])
                        except Exception:
                            pass
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

    def start_universe_maintenance_scheduler(self):
        """Start universe maintenance scheduler - รันทุกวัน 2:00 AM"""
        def run_maintenance():
            import subprocess

            while self.running:
                try:
                    now = datetime.now()

                    # Check if it's 2:00 AM (±5 minutes window)
                    if now.hour == 2 and now.minute < 5:
                        logger.info("="*60)
                        logger.info("UNIVERSE MAINTENANCE: Starting daily cleanup...")
                        logger.info("="*60)

                        # Update status: running
                        self._update_cron_status('universe_maintenance', 'running')

                        # Run maintenance script
                        script_path = os.path.join(os.getcwd(), 'scripts', 'maintain_universe_1000.py')
                        python_path = sys.executable

                        try:
                            result = subprocess.run(
                                [python_path, script_path],
                                capture_output=True,
                                text=True,
                                timeout=600  # 10 minute timeout
                            )

                            if result.returncode == 0:
                                logger.info("✅ Universe maintenance completed successfully")
                                logger.info(f"Output: {result.stdout[:500]}")
                                self._update_cron_status('universe_maintenance', 'ok')
                            else:
                                logger.error(f"❌ Universe maintenance failed: {result.stderr}")
                                self._update_cron_status('universe_maintenance', 'error')

                        except subprocess.TimeoutExpired:
                            logger.error("❌ Universe maintenance timed out (>10 min)")
                            self._update_cron_status('universe_maintenance', 'error')
                        except Exception as e:
                            logger.error(f"❌ Universe maintenance error: {e}")
                            self._update_cron_status('universe_maintenance', 'error')

                        # Sleep for 1 hour to avoid running multiple times in the same hour
                        if self.running:
                            time.sleep(3600)

                    # Check every minute
                    if not self.running:
                        break
                    time.sleep(60)

                except Exception as e:
                    logger.error(f"Universe maintenance scheduler error: {e}")
                    time.sleep(60)

        thread = threading.Thread(target=run_maintenance, daemon=True)
        thread.start()
        self.services['universe_maintenance'] = thread
        logger.info("Universe Maintenance Scheduler started (daily at 2:00 AM)")

    def _check_and_restart_threads(self):
        """Check if critical service threads are alive and restart if dead"""
        for name, thread in list(self.services.items()):
            if name == 'health':
                continue

            # Check if thread is alive (handle special cases)
            is_alive = False
            if name == 'price_streamer':
                # AlpacaStreamer is not a Thread, check if it's running
                # v6.17: Fixed - check correct attributes (running, thread)
                is_alive = (self.streamer and
                           self.streamer.running and
                           self.streamer.thread and
                           self.streamer.thread.is_alive())
            else:
                # Regular thread
                is_alive = thread.is_alive()

            if not is_alive:
                logger.warning(f"Thread '{name}' died — restarting...")
                try:
                    if name == 'web':
                        self.start_web_server()
                    elif name == 'rapid_monitor':
                        self.start_rapid_portfolio_monitor()
                    elif name == 'price_streamer':
                        # v6.17: Stop old streamer BEFORE creating new one (prevents connection leak)
                        if self.streamer:
                            try:
                                self.streamer.stop()
                            except Exception as e:
                                logger.error(f"Error stopping old streamer: {e}")
                        self.start_realtime_price_streamer()
                    # v6.1: rapid_scanner removed - engine is single source of truth
                    logger.info(f"Thread '{name}' restarted successfully")
                except Exception as e:
                    logger.error(f"Failed to restart thread '{name}': {e}")

    def _check_health(self):
        """Run all health checks and return status dict"""
        checks = {}
        issues = []
        now = datetime.now()
        broker = None  # Initialize to None

        # 1. Alpaca API (using broker abstraction layer)
        try:
            from engine.brokers import AlpacaBroker
            broker = AlpacaBroker(paper=True)
            account = broker.get_account()
            checks['alpaca_api'] = {
                'ok': True,
                'detail': f"Connected, ${account.portfolio_value:,.0f}"
            }
        except Exception as e:
            checks['alpaca_api'] = {'ok': False, 'detail': str(e)}
            issues.append(f"Alpaca API down: {e}")
            broker = None

        # 2. Market clock
        if broker:
            try:
                clock = broker.get_clock()
                market_status = "Open" if clock.is_open else "Closed"
                checks['market_clock'] = {
                    'ok': True,
                    'detail': market_status
                }
            except Exception as e:
                checks['market_clock'] = {'ok': False, 'detail': str(e)}
                issues.append(f"Market clock error: {e}")
        else:
            checks['market_clock'] = {'ok': False, 'detail': 'Trader not initialized'}
            issues.append('Market clock: trader not available')

        # 3. Thread liveness (web uses HTTP check instead of thread.is_alive)
        alive_count = 0
        total_count = 0
        dead_threads = []
        for name, thread in self.services.items():
            if name == 'health':
                continue  # Don't check self
            total_count += 1
            if name == 'web':
                # Flask thread may exit but server still serves via internal threads
                # Use HTTP check instead of thread.is_alive()
                try:
                    import urllib.request
                    resp = urllib.request.urlopen('http://localhost:5000/api/auto/status', timeout=5)
                    if resp.status == 200:
                        alive_count += 1
                    else:
                        dead_threads.append(name)
                except Exception:
                    dead_threads.append(name)
            elif name == 'price_streamer':
                # AlpacaStreamer is not a Thread, check if streamer object exists and is running
                # v6.17: Fixed - check correct attributes (running, thread)
                if self.streamer and self.streamer.running and self.streamer.thread and self.streamer.thread.is_alive():
                    alive_count += 1
                else:
                    dead_threads.append(name)
            elif thread.is_alive():
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

        # 5. Scanner freshness (v6.1: read from engine's cache file)
        try:
            if os.path.exists(SIGNALS_CACHE_FILE):
                with open(SIGNALS_CACHE_FILE, 'r') as f:
                    cache_data = json.load(f)
                cache_ts = datetime.fromisoformat(cache_data['timestamp'])
                age_sec = (now - cache_ts).total_seconds()
                age_min = age_sec / 60
                mode = cache_data.get('mode', 'unknown')

                if mode == 'closed':
                    checks['scanner'] = {
                        'ok': True,
                        'detail': f"Market closed (last scan {age_min:.0f}m ago)"
                    }
                elif age_sec > 1800:  # > 30 minutes during market hours
                    checks['scanner'] = {
                        'ok': False,
                        'detail': f"Stale: last scan {age_min:.0f}m ago"
                    }
                    issues.append(f"Scanner stale ({age_min:.0f}m)")
                else:
                    checks['scanner'] = {
                        'ok': True,
                        'detail': f"Last scan {age_min:.0f}m ago ({cache_data.get('count', 0)} signals)"
                    }
            else:
                checks['scanner'] = {
                    'ok': True,
                    'detail': 'Waiting for first engine scan'
                }
        except Exception as e:
            checks['scanner'] = {
                'ok': False,
                'detail': f"Cache read error: {e}"
            }

        # 6. Positions sync (Alpaca vs engine in-memory)
        # Use engine positions (source of truth) not rapid_portfolio (may have stale cache)
        if broker:
            try:
                if hasattr(self, 'rapid_portfolio'):
                    alpaca_positions = broker.get_positions()
                    # Prefer engine.positions (auto-synced with Alpaca) over rapid_portfolio cache
                    engine = getattr(self.rapid_portfolio, 'engine', None)
                    if engine and hasattr(engine, 'positions'):
                        memory_count = len(engine.positions)
                    else:
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
        else:
            checks['positions_sync'] = {'ok': False, 'detail': 'Trader not initialized'}

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

        # v5.1: Start real-time price streaming
        streamer_ok = self.start_realtime_price_streamer()
        time.sleep(1)

        # v6.1: Scanner removed - Engine is single source of truth
        # UI reads from rapid_signals.json written by auto_trading_engine.py

        self.start_health_checker()
        self.start_universe_maintenance_scheduler()  # v6.12: Auto cleanup at 2 AM

        print()
        print("=" * 60)
        print("  SERVICES STATUS")
        print("=" * 60)
        print(f"   Web Server:        {'✅ Running' if web_ok else '❌ Failed'}")
        print(f"   Portfolio Monitor: {'✅ Running' if rapid_monitor_ok else '❌ Failed'}")
        print(f"   Price Streamer:    {'✅ Real-time WebSocket' if streamer_ok else '⚠️  Fallback to polling'}")
        print(f"   Signal Scanner:    ✅ Via Trading Engine (single source)")
        print(f"   Universe Cleanup:  ✅ Daily at 2:00 AM")
        print()
        print("=" * 60)
        print("  WEB UI")
        print("=" * 60)
        print("   🚀 Rapid Trader:  http://localhost:5000/rapid")
        print("   📊 Portfolio:     http://localhost:5000/portfolio")
        print("   🔍 Screen:        http://localhost:5000/screen")
        print()
        print("=" * 60)
        print("  RAPID TRADER v5.1.0 - FULLY INTEGRATED")
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
        thread_check_counter = 0
        while self.running:
            try:
                time.sleep(1)
                thread_check_counter += 1
                if thread_check_counter >= 60:
                    thread_check_counter = 0
                    self._check_and_restart_threads()
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
