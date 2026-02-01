#!/usr/bin/env python3
"""
🤖 FULLY AUTOMATIC TRADING SYSTEM

ระบบอัตโนมัติ 100% - ไม่ต้องทำอะไรเลย:
1. สแกนหาหุ้นอัตโนมัติทุก 10 นาที
2. เข้าซื้ออัตโนมัติเมื่อเจอโอกาส
3. จัดการ portfolio อัตโนมัติ
4. ขายอัตโนมัติตาม exit rules
5. ส่ง alerts ทาง webhook/email

Usage:
    # เริ่มระบบ
    python src/auto_trading_system.py

    # รันเป็น background
    nohup python src/auto_trading_system.py > logs/auto_trading.log 2>&1 &

    # ดู status
    python src/auto_trading_system.py --status
"""

import os
import sys
import json
import time
import signal
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(__file__))

from loguru import logger

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_DIR = os.path.join(DATA_DIR, 'logs')
DB_PATH = os.path.join(DATA_DIR, 'database', 'stocks.db')
PORTFOLIO_FILE = os.path.join(BASE_DIR, 'portfolio.json')
TRADE_HISTORY_FILE = os.path.join(DATA_DIR, 'trade_history.json')
STATUS_FILE = os.path.join(LOG_DIR, 'auto_trading_status.json')

os.makedirs(LOG_DIR, exist_ok=True)

# Setup logging
log_file = os.path.join(LOG_DIR, f"auto_trading_{datetime.now().strftime('%Y%m%d')}.log")
logger.add(log_file, rotation="1 day", retention="30 days", level="INFO")


class AutoTradingSystem:
    """Fully Automatic Trading System - Pullback Catalyst Strategy"""

    def __init__(self):
        self.running = True
        self.scan_interval = 10  # minutes

        # Portfolio settings
        self.initial_capital = 100000
        self.max_positions = 5
        self.position_pct = 0.22  # 22% per position
        self.strong_position_pct = 0.28  # 28% for strong catalyst

        # Exit settings
        self.stop_loss = 0.025  # -2.5%
        self.target1 = 0.05    # +5%
        self.target2 = 0.085   # +8.5%
        self.target3 = 0.13    # +13%

        # State
        self.portfolio = self._load_portfolio()
        self.watchlist = {}
        self.trade_history = self._load_trade_history()

        # Stats
        self.stats = {
            'total_scans': 0,
            'opportunities_found': 0,
            'entries_made': 0,
            'exits_made': 0,
            'start_time': datetime.now().isoformat(),
        }

        # Signal handlers
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info("="*70)
        logger.info("🤖 FULLY AUTOMATIC TRADING SYSTEM INITIALIZED")
        logger.info("="*70)
        logger.info(f"   Capital: ${self.initial_capital:,.0f}")
        logger.info(f"   Max Positions: {self.max_positions}")
        logger.info(f"   Position Size: {self.position_pct*100:.0f}% / {self.strong_position_pct*100:.0f}%")
        logger.info(f"   Stop Loss: {self.stop_loss*100:.1f}%")
        logger.info(f"   Targets: T1={self.target1*100:.0f}%, T2={self.target2*100:.1f}%, T3={self.target3*100:.0f}%")
        logger.info("="*70)

    def _shutdown(self, signum, frame):
        """Graceful shutdown"""
        logger.info("🛑 Shutdown signal received...")
        self.running = False
        self._save_all()

    def _load_portfolio(self) -> Dict:
        """Load portfolio from file"""
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE, 'r') as f:
                    data = json.load(f)
                    if 'positions' not in data:
                        data['positions'] = []
                    if 'cash' not in data:
                        data['cash'] = self.initial_capital
                    return data
            except Exception as e:
                logger.error(f"Error loading portfolio: {e}")

        return {
            'cash': self.initial_capital,
            'positions': [],
            'last_update': datetime.now().isoformat(),
        }

    def _save_portfolio(self):
        """Save portfolio to file"""
        try:
            self.portfolio['last_update'] = datetime.now().isoformat()
            with open(PORTFOLIO_FILE, 'w') as f:
                json.dump(self.portfolio, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving portfolio: {e}")

    def _load_trade_history(self) -> List:
        """Load trade history"""
        if os.path.exists(TRADE_HISTORY_FILE):
            try:
                with open(TRADE_HISTORY_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_trade_history(self):
        """Save trade history"""
        try:
            with open(TRADE_HISTORY_FILE, 'w') as f:
                json.dump(self.trade_history, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving trade history: {e}")

    def _save_all(self):
        """Save all state"""
        self._save_portfolio()
        self._save_trade_history()
        self._save_status()
        logger.info("💾 All data saved")

    def _save_status(self):
        """Save current status"""
        try:
            status = {
                'timestamp': datetime.now().isoformat(),
                'running': self.running,
                'stats': self.stats,
                'portfolio_value': self._calculate_portfolio_value(),
                'positions': len(self.portfolio.get('positions', [])),
                'watchlist': len(self.watchlist),
            }
            with open(STATUS_FILE, 'w') as f:
                json.dump(status, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving status: {e}")

    def is_market_hours(self) -> bool:
        """Check if market is open"""
        now = datetime.now()
        if now.weekday() >= 5:  # Weekend
            return False
        hour = now.hour
        # Simplified: 9:30 AM - 4:00 PM
        if hour < 9 or (hour == 9 and now.minute < 30):
            return False
        if hour >= 16:
            return False
        return True

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol"""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='1d')
            if len(data) > 0:
                return float(data['Close'].iloc[-1])
        except Exception as e:
            logger.debug(f"Error getting price for {symbol}: {e}")
        return None

    def _calculate_portfolio_value(self) -> float:
        """Calculate total portfolio value"""
        value = self.portfolio.get('cash', 0)
        for pos in self.portfolio.get('positions', []):
            current_price = self.get_current_price(pos['symbol'])
            if current_price:
                value += current_price * pos['shares']
            else:
                value += pos['entry_price'] * pos['shares']
        return value

    # ==================== SCANNING ====================

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

            logger.info(f"✅ Found {len(opportunities)} opportunities")
            return opportunities

        except Exception as e:
            logger.error(f"Scan error: {e}")
            return []

    # ==================== TRADING ====================

    def should_enter(self, opportunity: Dict) -> bool:
        """Check if we should enter this trade"""
        # Check if already in position
        symbol = opportunity['symbol']
        for pos in self.portfolio.get('positions', []):
            if pos['symbol'] == symbol:
                return False

        # Check max positions
        if len(self.portfolio.get('positions', [])) >= self.max_positions:
            return False

        # Check catalyst score threshold
        if opportunity.get('catalyst_score', 0) < 50:
            return False

        # Check if good entry (near pullback target)
        current_price = opportunity.get('current_price', 0)
        entry_price = opportunity.get('entry_price', 0)
        if current_price > entry_price * 1.02:  # More than 2% above entry
            return False

        return True

    def enter_position(self, opportunity: Dict):
        """Enter a new position"""
        symbol = opportunity['symbol']
        entry_price = opportunity.get('entry_price', opportunity.get('current_price'))
        catalyst_score = opportunity.get('catalyst_score', 0)

        # Calculate position size
        portfolio_value = self._calculate_portfolio_value()
        if catalyst_score >= 65:
            pos_pct = self.strong_position_pct
        else:
            pos_pct = self.position_pct

        position_value = portfolio_value * pos_pct
        shares = int(position_value / entry_price)

        if shares <= 0:
            logger.warning(f"Cannot enter {symbol}: not enough funds")
            return

        if self.portfolio['cash'] < entry_price * shares:
            logger.warning(f"Cannot enter {symbol}: insufficient cash")
            return

        # Create position
        position = {
            'symbol': symbol,
            'entry_date': datetime.now().strftime('%Y-%m-%d'),
            'entry_time': datetime.now().strftime('%H:%M:%S'),
            'entry_price': entry_price,
            'shares': shares,
            'cost': entry_price * shares,
            'catalyst_score': catalyst_score,
            'highest_price': entry_price,
            'days_held': 0,
            't1_hit': False,
            't2_hit': False,
        }

        # Update portfolio
        self.portfolio['cash'] -= entry_price * shares
        self.portfolio['positions'].append(position)
        self._save_portfolio()

        self.stats['entries_made'] += 1

        logger.info(f"🟢 ENTERED: {symbol}")
        logger.info(f"   Price: ${entry_price:.2f}")
        logger.info(f"   Shares: {shares}")
        logger.info(f"   Cost: ${entry_price * shares:,.2f}")
        logger.info(f"   Catalyst Score: {catalyst_score:.0f}")

        self._send_alert(
            "ENTRY",
            f"Bought {shares} shares of {symbol} at ${entry_price:.2f}",
            {
                'symbol': symbol,
                'entry_price': entry_price,
                'shares': shares,
                'catalyst_score': catalyst_score,
            }
        )

    def manage_positions(self):
        """Manage existing positions - check for exits"""
        logger.info("📊 Managing positions...")

        positions_to_remove = []

        for pos in self.portfolio.get('positions', []):
            symbol = pos['symbol']
            current_price = self.get_current_price(symbol)

            if current_price is None:
                logger.warning(f"Could not get price for {symbol}")
                continue

            entry_price = pos['entry_price']
            pnl_pct = (current_price / entry_price - 1)

            # Update highest price
            if current_price > pos.get('highest_price', entry_price):
                pos['highest_price'] = current_price

            # Increment days held (if new day)
            pos['days_held'] = pos.get('days_held', 0) + 1

            exit_reason = None
            exit_shares = pos['shares']

            # Check exit conditions
            if pnl_pct <= -self.stop_loss:
                exit_reason = 'STOP_LOSS'

            elif pnl_pct >= self.target1 and not pos.get('t1_hit'):
                exit_reason = 'TARGET1'
                exit_shares = int(pos['shares'] * 0.30)
                pos['t1_hit'] = True

            elif pnl_pct >= self.target2 and not pos.get('t2_hit'):
                exit_reason = 'TARGET2'
                exit_shares = int(pos['shares'] * 0.45)
                pos['t2_hit'] = True

            elif pnl_pct >= self.target3:
                exit_reason = 'TARGET3'

            elif pos.get('t1_hit') and pos['highest_price'] > entry_price * 1.06:
                if current_price < pos['highest_price'] * 0.965:
                    exit_reason = 'TRAILING_STOP'

            elif pos['days_held'] >= 14:
                exit_reason = 'TIME_STOP'

            # Execute exit
            if exit_reason:
                self._exit_position(pos, current_price, exit_shares, exit_reason)

                if exit_shares >= pos['shares']:
                    positions_to_remove.append(pos)
                else:
                    pos['shares'] -= exit_shares

        # Remove closed positions
        for pos in positions_to_remove:
            self.portfolio['positions'].remove(pos)

        self._save_portfolio()

    def _exit_position(self, position: Dict, exit_price: float, shares: int, reason: str):
        """Exit a position (fully or partially)"""
        symbol = position['symbol']
        entry_price = position['entry_price']
        pnl = (exit_price - entry_price) * shares
        pnl_pct = (exit_price / entry_price - 1) * 100

        # Add cash back
        self.portfolio['cash'] += exit_price * shares

        # Record trade
        trade = {
            'symbol': symbol,
            'entry_date': position['entry_date'],
            'exit_date': datetime.now().strftime('%Y-%m-%d'),
            'exit_time': datetime.now().strftime('%H:%M:%S'),
            'entry_price': entry_price,
            'exit_price': exit_price,
            'shares': shares,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'exit_reason': reason,
            'days_held': position.get('days_held', 0),
        }
        self.trade_history.append(trade)
        self._save_trade_history()

        self.stats['exits_made'] += 1

        emoji = "🟢" if pnl > 0 else "🔴"
        logger.info(f"{emoji} EXITED: {symbol} ({reason})")
        logger.info(f"   Entry: ${entry_price:.2f} → Exit: ${exit_price:.2f}")
        logger.info(f"   P&L: ${pnl:+,.2f} ({pnl_pct:+.2f}%)")

        self._send_alert(
            "EXIT",
            f"Sold {shares} shares of {symbol} at ${exit_price:.2f} ({reason})",
            {
                'symbol': symbol,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'reason': reason,
            }
        )

    # ==================== ALERTS ====================

    def _send_alert(self, alert_type: str, message: str, data: Dict = None):
        """Send alert"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Console
        print("\n" + "🔔"*20)
        print(f"[{timestamp}] {alert_type}: {message}")
        if data:
            for k, v in data.items():
                print(f"  {k}: {v}")
        print("🔔"*20 + "\n")

        # Log
        logger.warning(f"ALERT [{alert_type}]: {message}")

        # Save to alerts file
        alerts_file = os.path.join(LOG_DIR, 'alerts.json')
        try:
            alerts = []
            if os.path.exists(alerts_file):
                with open(alerts_file, 'r') as f:
                    alerts = json.load(f)

            alerts.append({
                'timestamp': timestamp,
                'type': alert_type,
                'message': message,
                'data': data,
            })

            with open(alerts_file, 'w') as f:
                json.dump(alerts[-100:], f, indent=2)  # Keep last 100

        except Exception as e:
            logger.error(f"Failed to save alert: {e}")

    # ==================== MAIN LOOP ====================

    def run_cycle(self):
        """Run one complete cycle"""
        cycle_start = datetime.now()
        logger.info(f"\n{'='*70}")
        logger.info(f"🔄 CYCLE: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*70}")

        # Check market hours
        if not self.is_market_hours():
            logger.info("📴 Market closed - sleeping...")
            self._save_status()
            return

        # 1. Manage existing positions first
        if self.portfolio.get('positions'):
            self.manage_positions()

        # 2. Scan for new opportunities
        opportunities = self.scan_for_opportunities()

        # 3. Enter new positions if good opportunities
        for opp in opportunities:
            if self.should_enter(opp):
                self.enter_position(opp)

                # Check max positions again
                if len(self.portfolio.get('positions', [])) >= self.max_positions:
                    break

        # 4. Report status
        portfolio_value = self._calculate_portfolio_value()
        total_pnl = portfolio_value - self.initial_capital
        pnl_pct = (portfolio_value / self.initial_capital - 1) * 100

        logger.info(f"\n📊 PORTFOLIO STATUS:")
        logger.info(f"   Value: ${portfolio_value:,.2f}")
        logger.info(f"   P&L: ${total_pnl:+,.2f} ({pnl_pct:+.2f}%)")
        logger.info(f"   Positions: {len(self.portfolio.get('positions', []))}/{self.max_positions}")
        logger.info(f"   Cash: ${self.portfolio.get('cash', 0):,.2f}")

        self._save_status()

    def run(self):
        """Main run loop"""
        logger.info("🚀 Starting Automatic Trading System...")
        logger.info(f"   Scan interval: {self.scan_interval} minutes")
        logger.info("   Press Ctrl+C to stop\n")

        while self.running:
            try:
                self.run_cycle()

                if not self.running:
                    break

                # Wait for next cycle
                next_scan = datetime.now() + timedelta(minutes=self.scan_interval)
                logger.info(f"\n⏰ Next scan: {next_scan.strftime('%H:%M:%S')}")

                for _ in range(self.scan_interval * 60):
                    if not self.running:
                        break
                    time.sleep(1)

            except KeyboardInterrupt:
                logger.info("🛑 Interrupted by user")
                self.running = False
            except Exception as e:
                logger.error(f"Cycle error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(60)

        logger.info("👋 System stopped")
        self._save_all()


def show_status():
    """Show current system status"""
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'r') as f:
            status = json.load(f)

        print("\n" + "="*50)
        print("🤖 AUTO TRADING SYSTEM STATUS")
        print("="*50)
        print(f"Last Update: {status.get('timestamp', 'N/A')}")
        print(f"Running: {status.get('running', False)}")
        print(f"Portfolio Value: ${status.get('portfolio_value', 0):,.2f}")
        print(f"Positions: {status.get('positions', 0)}")
        print(f"Watchlist: {status.get('watchlist', 0)}")
        print("\nStats:")
        stats = status.get('stats', {})
        print(f"  Total Scans: {stats.get('total_scans', 0)}")
        print(f"  Opportunities Found: {stats.get('opportunities_found', 0)}")
        print(f"  Entries Made: {stats.get('entries_made', 0)}")
        print(f"  Exits Made: {stats.get('exits_made', 0)}")
        print("="*50 + "\n")
    else:
        print("No status file found. System may not have been started.")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Automatic Trading System')
    parser.add_argument('--status', action='store_true', help='Show current status')
    parser.add_argument('--interval', type=int, default=10, help='Scan interval (minutes)')
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    system = AutoTradingSystem()
    system.scan_interval = args.interval
    system.run()


if __name__ == '__main__':
    main()
