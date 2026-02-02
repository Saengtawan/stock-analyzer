#!/usr/bin/env python3
"""
AUTO TRADING ENGINE - Phase 2
Rapid Trader v3.9 Full-Auto Trading

Integrates:
- Alpaca Module (Phase 1) for order execution
- Rapid Rotation Screener for signal generation
- Trailing stop logic (v3.9: +2% activation, 70% lock)

Daily Flow:
- 06:00 ET: System wake up, health check
- 09:00 ET: Pre-market scan
- 09:30 ET: Market open → Execute signals
- 09:31-15:59 ET: Monitor loop (every 1 min)
- 15:50 ET: Pre-close check
- 16:00 ET: Daily summary
- 16:01+ ET: Sleep mode
"""

import os
import sys
import time
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import pytz

# Add src to path
src_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, src_dir)
sys.path.insert(0, os.path.dirname(src_dir))  # Add parent for 'src' imports

from alpaca_trader import AlpacaTrader, Position, Order
from trading_safety import TradingSafetySystem, SafetyStatus
from loguru import logger

# Try to import screener
try:
    from screeners.rapid_rotation_screener import RapidRotationScreener
    SCREENER_AVAILABLE = True
except ImportError as e:
    try:
        # Try alternative import
        from src.screeners.rapid_rotation_screener import RapidRotationScreener
        SCREENER_AVAILABLE = True
    except ImportError:
        SCREENER_AVAILABLE = False
        logger.warning(f"RapidRotationScreener not available: {e}")


class TradingState(Enum):
    """Trading engine states"""
    SLEEPING = "sleeping"
    STARTING = "starting"
    SCANNING = "scanning"
    TRADING = "trading"
    MONITORING = "monitoring"
    CLOSING = "closing"
    ERROR = "error"


@dataclass
class ManagedPosition:
    """Position with trailing stop management"""
    symbol: str
    qty: int
    entry_price: float
    entry_time: datetime
    sl_order_id: str
    current_sl_price: float
    peak_price: float
    trailing_active: bool = False
    days_held: int = 0


@dataclass
class DailyStats:
    """Daily trading statistics"""
    date: str
    trades_executed: int = 0
    trades_won: int = 0
    trades_lost: int = 0
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    signals_found: int = 0
    signals_executed: int = 0


class AutoTradingEngine:
    """
    Full-Auto Trading Engine for Rapid Trader v3.9

    Features:
    - Automatic signal detection and execution
    - Trailing stop management
    - Position monitoring every minute
    - Safety limits (max positions, daily loss limit)
    """

    # Trading parameters (v3.11 - Lock 80% upgrade)
    MAX_POSITIONS = 2
    POSITION_SIZE_PCT = 40  # 40% per position
    STOP_LOSS_PCT = 2.5
    TAKE_PROFIT_PCT = 6.0
    TRAIL_ACTIVATION_PCT = 2.0
    TRAIL_LOCK_PCT = 80  # v3.11: 70 → 80 (+8.9% return improvement)
    MAX_HOLD_DAYS = 5
    DAILY_LOSS_LIMIT_PCT = 5.0  # Stop trading if down 5% in a day

    # Simulated capital for realistic testing
    # Set to match real capital you'll use in live trading
    # None = use actual Alpaca account value
    SIMULATED_CAPITAL = 4000  # ~$4,000 = ~125,000 THB

    # Timing (ET timezone)
    MARKET_OPEN_HOUR = 9
    MARKET_OPEN_MINUTE = 30
    MARKET_CLOSE_HOUR = 16
    MARKET_CLOSE_MINUTE = 0
    PRE_CLOSE_MINUTE = 50  # 15:50 ET

    # Monitor interval
    MONITOR_INTERVAL_SECONDS = 60  # Check every 1 minute

    def __init__(
        self,
        api_key: str = None,
        secret_key: str = None,
        paper: bool = True,
        auto_start: bool = False
    ):
        """Initialize trading engine"""

        # Alpaca client
        self.trader = AlpacaTrader(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper
        )

        # Safety system
        self.safety = TradingSafetySystem(self.trader)

        # Screener
        self.screener = None
        if SCREENER_AVAILABLE:
            try:
                self.screener = RapidRotationScreener()
                logger.info("Screener initialized")
            except Exception as e:
                logger.error(f"Failed to init screener: {e}")

        # State
        self.state = TradingState.SLEEPING
        self.positions: Dict[str, ManagedPosition] = {}
        self.daily_stats = DailyStats(date=datetime.now().strftime('%Y-%m-%d'))
        self.running = False
        self.monitor_thread = None

        # Timezone
        self.et_tz = pytz.timezone('US/Eastern')

        # Load existing positions from Alpaca
        self._sync_positions()

        logger.info(f"AutoTradingEngine initialized (paper={paper})")

        if auto_start:
            self.start()

    # =========================================================================
    # POSITION SYNC
    # =========================================================================

    def _sync_positions(self):
        """Sync positions from Alpaca"""
        try:
            alpaca_positions = self.trader.get_positions()
            alpaca_orders = self.trader.get_orders(status='open')

            for pos in alpaca_positions:
                # Find SL order for this position
                sl_order = None
                for order in alpaca_orders:
                    if order.symbol == pos.symbol and order.type == 'stop':
                        sl_order = order
                        break

                if pos.symbol not in self.positions:
                    self.positions[pos.symbol] = ManagedPosition(
                        symbol=pos.symbol,
                        qty=int(pos.qty),
                        entry_price=pos.avg_entry_price,
                        entry_time=datetime.now(),  # Unknown actual entry
                        sl_order_id=sl_order.id if sl_order else "",
                        current_sl_price=sl_order.stop_price if sl_order else pos.avg_entry_price * 0.975,
                        peak_price=pos.current_price,
                        trailing_active=False
                    )
                    logger.info(f"Synced position: {pos.symbol}")

            logger.info(f"Synced {len(self.positions)} positions")

        except Exception as e:
            logger.error(f"Failed to sync positions: {e}")

    # =========================================================================
    # TIME HELPERS
    # =========================================================================

    def _get_et_time(self) -> datetime:
        """Get current time in ET"""
        return datetime.now(self.et_tz)

    def _is_market_hours(self) -> bool:
        """Check if within market hours"""
        now = self._get_et_time()
        market_open = now.replace(
            hour=self.MARKET_OPEN_HOUR,
            minute=self.MARKET_OPEN_MINUTE,
            second=0
        )
        market_close = now.replace(
            hour=self.MARKET_CLOSE_HOUR,
            minute=self.MARKET_CLOSE_MINUTE,
            second=0
        )
        return market_open <= now <= market_close

    def _is_pre_close(self) -> bool:
        """Check if in pre-close period (15:50-16:00 ET)"""
        now = self._get_et_time()
        pre_close = now.replace(
            hour=15,
            minute=self.PRE_CLOSE_MINUTE,
            second=0
        )
        market_close = now.replace(
            hour=self.MARKET_CLOSE_HOUR,
            minute=self.MARKET_CLOSE_MINUTE,
            second=0
        )
        return pre_close <= now <= market_close

    def _is_weekend(self) -> bool:
        """Check if weekend"""
        return self._get_et_time().weekday() >= 5

    # =========================================================================
    # SCANNING
    # =========================================================================

    def scan_for_signals(self) -> List[Dict]:
        """Run screener to find signals"""
        if not self.screener:
            logger.warning("Screener not available")
            return []

        try:
            self.state = TradingState.SCANNING
            logger.info("Scanning for signals...")

            # Load fresh data
            self.screener.load_data()

            # Get signals (excluding current positions)
            existing = list(self.positions.keys())
            signals = self.screener.get_portfolio_signals(
                max_positions=self.MAX_POSITIONS,
                existing_positions=existing
            )

            self.daily_stats.signals_found = len(signals)
            logger.info(f"Found {len(signals)} signals")

            return signals

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            return []

    # =========================================================================
    # EXECUTION
    # =========================================================================

    def execute_signal(self, signal) -> bool:
        """
        Execute a trading signal

        Args:
            signal: Signal object from screener

        Returns:
            True if executed successfully
        """
        try:
            symbol = signal.symbol

            # Safety check first
            can_trade, reason = self.safety.can_open_new_position()
            if not can_trade:
                logger.warning(f"Safety block: {reason}")
                return False

            # Check if already have position
            if symbol in self.positions:
                logger.warning(f"Already have position in {symbol}")
                return False

            # Check max positions
            if len(self.positions) >= self.MAX_POSITIONS:
                logger.warning(f"Max positions ({self.MAX_POSITIONS}) reached")
                return False

            # Calculate position size
            # Use simulated capital if set, otherwise use actual account value
            if self.SIMULATED_CAPITAL:
                capital = self.SIMULATED_CAPITAL
                logger.info(f"Using simulated capital: ${capital:,.0f}")
            else:
                account = self.trader.get_account()
                capital = account['portfolio_value']
            position_value = capital * (self.POSITION_SIZE_PCT / 100)

            # Get current price
            pos_check = self.trader.get_position(symbol)
            if pos_check:
                current_price = pos_check.current_price
            else:
                # Use signal's entry price as estimate
                current_price = getattr(signal, 'entry_price', None) or getattr(signal, 'close', 100)

            qty = int(position_value / current_price)
            if qty <= 0:
                logger.warning(f"Position size too small for {symbol}")
                return False

            logger.info(f"Executing: BUY {symbol} x{qty} @ ~${current_price:.2f}")

            # Buy with stop loss
            buy_order, sl_order = self.trader.buy_with_stop_loss(symbol, qty)

            if not buy_order or not sl_order:
                logger.error(f"Failed to execute {symbol}")
                return False

            # Create managed position
            entry_price = buy_order.filled_avg_price
            sl_price = sl_order.stop_price

            self.positions[symbol] = ManagedPosition(
                symbol=symbol,
                qty=qty,
                entry_price=entry_price,
                entry_time=datetime.now(),
                sl_order_id=sl_order.id,
                current_sl_price=sl_price,
                peak_price=entry_price,
                trailing_active=False
            )

            self.daily_stats.trades_executed += 1
            self.daily_stats.signals_executed += 1

            logger.info(f"✅ Bought {symbol} x{qty} @ ${entry_price:.2f}, SL @ ${sl_price:.2f}")

            return True

        except Exception as e:
            logger.error(f"Execute failed for {signal}: {e}")
            return False

    # =========================================================================
    # MONITORING & TRAILING
    # =========================================================================

    def monitor_positions(self):
        """Monitor all positions and update trailing stops"""
        if not self.positions:
            return

        # Ensure all positions have SL protection
        self.safety.ensure_sl_protection()

        logger.debug(f"Monitoring {len(self.positions)} positions...")

        for symbol, managed_pos in list(self.positions.items()):
            try:
                self._check_position(symbol, managed_pos)
            except Exception as e:
                logger.error(f"Error monitoring {symbol}: {e}")

    def _check_position(self, symbol: str, managed_pos: ManagedPosition):
        """Check single position and update trailing if needed"""

        # Get current position from Alpaca
        alpaca_pos = self.trader.get_position(symbol)
        if not alpaca_pos:
            # Position closed externally
            logger.warning(f"{symbol} position not found - may have been closed")
            del self.positions[symbol]
            return

        current_price = alpaca_pos.current_price
        entry_price = managed_pos.entry_price

        # Update peak
        if current_price > managed_pos.peak_price:
            managed_pos.peak_price = current_price

        # Calculate P&L
        pnl_pct = ((current_price - entry_price) / entry_price) * 100

        # Check take profit
        if pnl_pct >= self.TAKE_PROFIT_PCT:
            logger.info(f"🎯 {symbol} hit TP at {pnl_pct:+.2f}%")
            self._close_position(symbol, managed_pos, "TAKE_PROFIT")
            return

        # Check trailing activation
        if not managed_pos.trailing_active and pnl_pct >= self.TRAIL_ACTIVATION_PCT:
            managed_pos.trailing_active = True
            logger.info(f"📈 {symbol} trailing activated at {pnl_pct:+.2f}%")

        # Update trailing stop
        if managed_pos.trailing_active:
            new_sl, _ = self.trader.calculate_trailing_stop(
                entry_price,
                managed_pos.peak_price,
                self.TRAIL_ACTIVATION_PCT,
                self.TRAIL_LOCK_PCT
            )

            # Only move SL up, never down
            if new_sl > managed_pos.current_sl_price:
                logger.info(f"📈 {symbol} updating SL: ${managed_pos.current_sl_price:.2f} → ${new_sl:.2f}")

                # Modify SL order at Alpaca (has retry + fallback logic)
                new_order = self.trader.modify_stop_loss(
                    managed_pos.sl_order_id,
                    new_sl
                )

                if new_order:
                    managed_pos.sl_order_id = new_order.id
                    # Use the order's actual stop_price (may be fallback to old price)
                    managed_pos.current_sl_price = new_order.stop_price
                    if new_order.stop_price != new_sl:
                        logger.warning(f"{symbol} SL fallback to ${new_order.stop_price:.2f}")
                else:
                    # CRITICAL: No SL protection - close position immediately
                    logger.error(f"CRITICAL: {symbol} has no SL - closing position for safety")
                    self._close_position(symbol, managed_pos, "NO_SL_PROTECTION")

        # Check days held
        days_held = (datetime.now() - managed_pos.entry_time).days
        managed_pos.days_held = days_held

        if days_held >= self.MAX_HOLD_DAYS and pnl_pct < 1:
            logger.info(f"⏰ {symbol} held {days_held} days with {pnl_pct:+.2f}% - time exit")
            self._close_position(symbol, managed_pos, "TIME_EXIT")
            return

        # Log status
        logger.debug(
            f"{symbol}: ${current_price:.2f} ({pnl_pct:+.2f}%), "
            f"SL=${managed_pos.current_sl_price:.2f}, "
            f"Peak=${managed_pos.peak_price:.2f}, "
            f"Trailing={'ON' if managed_pos.trailing_active else 'OFF'}"
        )

    def _close_position(self, symbol: str, managed_pos: ManagedPosition, reason: str):
        """Close a position"""
        try:
            # CRITICAL: Check if position still exists before selling
            # This prevents double-sell if SL was already triggered
            alpaca_pos = self.trader.get_position(symbol)
            if not alpaca_pos:
                logger.info(f"{symbol} position already closed (SL may have triggered)")
                del self.positions[symbol]
                return

            # Cancel SL order first
            if managed_pos.sl_order_id:
                self.trader.cancel_order(managed_pos.sl_order_id)

            # Sell using actual qty from Alpaca (not managed_pos.qty)
            # In case of partial fills or discrepancies
            actual_qty = int(alpaca_pos.qty)
            sell_order = self.trader.place_market_sell(symbol, actual_qty)

            # Wait for fill
            time.sleep(2)
            order = self.trader.get_order(sell_order.id)

            if order.status == 'filled':
                exit_price = order.filled_avg_price
                pnl_pct = ((exit_price - managed_pos.entry_price) / managed_pos.entry_price) * 100
                pnl_usd = (exit_price - managed_pos.entry_price) * managed_pos.qty

                logger.info(f"✅ Closed {symbol}: {pnl_pct:+.2f}% (${pnl_usd:+.2f}) - {reason}")

                # Update stats
                self.daily_stats.realized_pnl += pnl_usd
                if pnl_pct > 0:
                    self.daily_stats.trades_won += 1
                else:
                    self.daily_stats.trades_lost += 1

            # Remove from managed positions
            del self.positions[symbol]

        except Exception as e:
            logger.error(f"Failed to close {symbol}: {e}")

    # =========================================================================
    # DAILY CHECKS
    # =========================================================================

    def check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit exceeded"""
        account = self.trader.get_account()
        daily_pnl_pct = ((account['equity'] - account['last_equity']) / account['last_equity']) * 100

        if daily_pnl_pct <= -self.DAILY_LOSS_LIMIT_PCT:
            logger.warning(f"🚨 Daily loss limit hit: {daily_pnl_pct:.2f}%")
            return True
        return False

    def pre_close_check(self):
        """Pre-close check - handle max hold days"""
        logger.info("Pre-close check...")

        for symbol, managed_pos in list(self.positions.items()):
            if managed_pos.days_held >= self.MAX_HOLD_DAYS:
                logger.info(f"Closing {symbol} - held {managed_pos.days_held} days")
                self._close_position(symbol, managed_pos, "MAX_HOLD_DAYS")

    def daily_summary(self) -> Dict:
        """Generate daily summary"""
        account = self.trader.get_account()

        summary = {
            'date': self.daily_stats.date,
            'signals_found': self.daily_stats.signals_found,
            'signals_executed': self.daily_stats.signals_executed,
            'trades_won': self.daily_stats.trades_won,
            'trades_lost': self.daily_stats.trades_lost,
            'realized_pnl': self.daily_stats.realized_pnl,
            'account_value': account['portfolio_value'],
            'positions_held': len(self.positions),
        }

        logger.info("=" * 50)
        logger.info("DAILY SUMMARY")
        logger.info("=" * 50)
        for k, v in summary.items():
            logger.info(f"  {k}: {v}")

        return summary

    # =========================================================================
    # MAIN LOOP
    # =========================================================================

    def start(self):
        """Start the trading engine"""
        if self.running:
            logger.warning("Engine already running")
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Trading engine started")

    def stop(self):
        """Stop the trading engine"""
        self.running = False
        logger.info("Trading engine stopped")

    def _run_loop(self):
        """Main trading loop"""
        logger.info("Trading loop started")

        last_scan_date = None

        while self.running:
            try:
                now = self._get_et_time()

                # Skip weekends
                if self._is_weekend():
                    self.state = TradingState.SLEEPING
                    time.sleep(60)
                    continue

                # Check market status
                clock = self.trader.get_clock()

                if not clock['is_open']:
                    self.state = TradingState.SLEEPING
                    time.sleep(60)
                    continue

                # Market is open
                self.state = TradingState.TRADING

                # Pre-market scan (once per day at open)
                today = now.strftime('%Y-%m-%d')
                if last_scan_date != today:
                    # Check daily loss limit
                    if self.check_daily_loss_limit():
                        logger.warning("Daily loss limit - no new trades today")
                    else:
                        # Scan and execute
                        signals = self.scan_for_signals()
                        for signal in signals:
                            if len(self.positions) < self.MAX_POSITIONS:
                                self.execute_signal(signal)
                            else:
                                break

                    last_scan_date = today

                # Pre-close check
                if self._is_pre_close():
                    self.state = TradingState.CLOSING
                    self.pre_close_check()

                # Monitor positions
                self.state = TradingState.MONITORING
                self.monitor_positions()

                # Wait for next interval
                time.sleep(self.MONITOR_INTERVAL_SECONDS)

            except Exception as e:
                logger.error(f"Loop error: {e}")
                self.state = TradingState.ERROR
                time.sleep(30)

        # Generate daily summary on stop
        self.daily_summary()

    # =========================================================================
    # STATUS & INFO
    # =========================================================================

    def get_status(self) -> Dict:
        """Get current engine status"""
        account = self.trader.get_account()
        safety_status = self.safety.get_status_summary()

        return {
            'state': self.state.value,
            'running': self.running,
            'market_open': self.trader.is_market_open(),
            'positions': len(self.positions),
            'account_value': account['portfolio_value'],
            'cash': account['cash'],
            'daily_stats': asdict(self.daily_stats),
            'safety': safety_status,
        }

    def get_positions_status(self) -> List[Dict]:
        """Get detailed positions status"""
        status = []

        for symbol, managed_pos in self.positions.items():
            alpaca_pos = self.trader.get_position(symbol)
            if alpaca_pos:
                pnl_pct = ((alpaca_pos.current_price - managed_pos.entry_price) / managed_pos.entry_price) * 100
                status.append({
                    'symbol': symbol,
                    'qty': managed_pos.qty,
                    'entry_price': managed_pos.entry_price,
                    'current_price': alpaca_pos.current_price,
                    'pnl_pct': pnl_pct,
                    'pnl_usd': alpaca_pos.unrealized_pl,
                    'sl_price': managed_pos.current_sl_price,
                    'peak_price': managed_pos.peak_price,
                    'trailing_active': managed_pos.trailing_active,
                    'days_held': managed_pos.days_held,
                })

        return status


# =============================================================================
# TEST / DEMO
# =============================================================================

def test_engine():
    """Test trading engine"""
    print("=" * 60)
    print("AUTO TRADING ENGINE TEST")
    print("=" * 60)

    # Credentials
    API_KEY = "PK45CDQEE2WO7I7N4BH762VSMK"
    SECRET_KEY = "DFDhSeYmnsxS2YpyAZLX1MLm9ndfmYr9XaUEiyn78SH1"

    engine = AutoTradingEngine(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        paper=True,
        auto_start=False  # Don't auto-start for testing
    )

    # Get status
    print("\n[1] Engine Status:")
    status = engine.get_status()
    for k, v in status.items():
        print(f"    {k}: {v}")

    # Check market
    print("\n[2] Market Status:")
    clock = engine.trader.get_clock()
    print(f"    Open: {clock['is_open']}")
    print(f"    Next Open: {clock['next_open']}")

    # Test scan (if screener available)
    if engine.screener:
        print("\n[3] Testing Scan:")
        signals = engine.scan_for_signals()
        print(f"    Found {len(signals)} signals")
        if signals:
            for i, s in enumerate(signals[:3]):
                print(f"    [{i+1}] {s.symbol}: Score={s.score}")
    else:
        print("\n[3] Screener not available for testing")

    # Test position monitoring (if any positions)
    print("\n[4] Position Monitoring:")
    positions = engine.get_positions_status()
    if positions:
        for p in positions:
            print(f"    {p['symbol']}: ${p['current_price']:.2f} ({p['pnl_pct']:+.2f}%)")
    else:
        print("    No positions")

    print("\n" + "=" * 60)
    print("ENGINE TEST COMPLETE")
    print("=" * 60)

    return engine


if __name__ == "__main__":
    test_engine()
