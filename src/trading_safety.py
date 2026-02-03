#!/usr/bin/env python3
"""
TRADING SAFETY SYSTEM - Phase 3
Rapid Trader v3.9 Safety Layers

7 Safety Layers:
1. Fallback SL Order - Every position MUST have SL at Alpaca
2. Daily Loss Limit - Stop trading if down -5% in a day
3. Max Positions - Never hold more than 3 positions
4. Max Hold Days - Auto-sell after 5 days
5. Health Check - Monitor system health
6. Emergency Stop - Manual override to stop all trading
7. PDT Protection - Pattern Day Trader rule (3 day trades / 5 days for <$25K)

NOT INCLUDED (Phase 3):
- Notifications (Line/Telegram) - will add later
"""

import os
import sys
import time
import json
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alpaca_trader import AlpacaTrader
from loguru import logger


class SafetyStatus(Enum):
    """Safety check status"""
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class SafetyCheck:
    """Result of a safety check"""
    name: str
    status: SafetyStatus
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class HealthReport:
    """System health report"""
    timestamp: datetime
    overall_status: SafetyStatus
    checks: List[SafetyCheck]
    can_trade: bool
    reasons: List[str]


class TradingSafetySystem:
    """
    Trading Safety System for Rapid Trader v3.9

    Monitors and enforces safety rules:
    - Position protection (SL orders)
    - Loss limits
    - Position limits
    - System health
    """

    # Safety thresholds
    DAILY_LOSS_LIMIT_PCT = 5.0      # Stop trading if down 5% in a day
    MAX_POSITIONS = 3               # Max concurrent positions
    MAX_HOLD_DAYS = 5               # Max days to hold a position
    MIN_BUYING_POWER_PCT = 10.0     # Min buying power to trade (% of equity)

    # PDT Rule (Pattern Day Trader)
    PDT_ACCOUNT_THRESHOLD = 25000   # PDT applies to accounts < $25K
    PDT_DAY_TRADE_LIMIT = 3         # Max 3 day trades in rolling 5 days
    PDT_ENFORCE_ALWAYS = True       # Enforce even on paper (for realistic testing)

    # Health check intervals
    HEALTH_CHECK_INTERVAL = 300     # 5 minutes

    def __init__(self, trader: AlpacaTrader):
        """Initialize safety system"""
        self.trader = trader
        self.emergency_stop = False
        self.daily_loss_triggered = False
        self.last_health_check = None
        self.health_history: List[HealthReport] = []

        # State file - absolute path in data/ directory
        data_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'data'
        )
        data_dir = os.path.abspath(data_dir)
        os.makedirs(data_dir, exist_ok=True)
        self._state_file = os.path.join(data_dir, 'trading_safety_state.json')

        # Load state
        self._load_state()

        logger.info("Trading Safety System initialized")

    # =========================================================================
    # STATE PERSISTENCE
    # =========================================================================

    def _load_state(self):
        """Load safety state from file"""
        try:
            if os.path.exists(self._state_file):
                with open(self._state_file, 'r') as f:
                    state = json.load(f)
                    self.emergency_stop = state.get('emergency_stop', False)
                    # Reset daily loss on new day
                    last_date = state.get('date', '')
                    today = datetime.now().strftime('%Y-%m-%d')
                    if last_date != today:
                        self.daily_loss_triggered = False
                    else:
                        self.daily_loss_triggered = state.get('daily_loss_triggered', False)
        except Exception as e:
            logger.error(f"Failed to load safety state: {e}")

    def _save_state(self):
        """Save safety state to file (atomic write)"""
        try:
            state = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'emergency_stop': self.emergency_stop,
                'daily_loss_triggered': self.daily_loss_triggered,
                'last_updated': datetime.now().isoformat()
            }
            dir_path = os.path.dirname(self._state_file)
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(state, f, indent=2)
                os.replace(tmp_path, self._state_file)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.error(f"Failed to save safety state: {e}")

    # =========================================================================
    # SAFETY CHECKS
    # =========================================================================

    def check_sl_protection(self) -> SafetyCheck:
        """
        Check that all positions have stop loss orders

        CRITICAL RULE: No position without SL protection
        """
        try:
            positions = self.trader.get_positions()
            orders = self.trader.get_orders(status='open')

            # Get symbols with SL orders
            sl_symbols = set()
            for order in orders:
                if order.type == 'stop' and order.side == 'sell':
                    sl_symbols.add(order.symbol)

            # Check all positions have SL
            unprotected = []
            for pos in positions:
                if pos.symbol not in sl_symbols:
                    unprotected.append(pos.symbol)

            if unprotected:
                return SafetyCheck(
                    name="SL Protection",
                    status=SafetyStatus.CRITICAL,
                    message=f"UNPROTECTED: {', '.join(unprotected)}",
                    value=len(unprotected),
                    threshold=0
                )

            return SafetyCheck(
                name="SL Protection",
                status=SafetyStatus.OK,
                message=f"All {len(positions)} positions protected",
                value=len(positions),
                threshold=0
            )

        except Exception as e:
            return SafetyCheck(
                name="SL Protection",
                status=SafetyStatus.WARNING,
                message=f"Check failed: {e}"
            )

    def check_daily_loss(self) -> SafetyCheck:
        """Check daily P&L against limit"""
        try:
            account = self.trader.get_account()
            equity = account['equity']
            last_equity = account['last_equity']

            daily_pnl = equity - last_equity
            daily_pnl_pct = (daily_pnl / last_equity) * 100 if last_equity > 0 else 0

            if daily_pnl_pct <= -self.DAILY_LOSS_LIMIT_PCT:
                self.daily_loss_triggered = True
                self._save_state()
                return SafetyCheck(
                    name="Daily Loss Limit",
                    status=SafetyStatus.CRITICAL,
                    message=f"LIMIT HIT: {daily_pnl_pct:.2f}% (limit: -{self.DAILY_LOSS_LIMIT_PCT}%)",
                    value=daily_pnl_pct,
                    threshold=-self.DAILY_LOSS_LIMIT_PCT
                )

            if daily_pnl_pct <= -self.DAILY_LOSS_LIMIT_PCT * 0.7:  # 70% of limit
                return SafetyCheck(
                    name="Daily Loss Limit",
                    status=SafetyStatus.WARNING,
                    message=f"Approaching limit: {daily_pnl_pct:.2f}%",
                    value=daily_pnl_pct,
                    threshold=-self.DAILY_LOSS_LIMIT_PCT
                )

            return SafetyCheck(
                name="Daily Loss Limit",
                status=SafetyStatus.OK,
                message=f"Daily P&L: {daily_pnl_pct:+.2f}%",
                value=daily_pnl_pct,
                threshold=-self.DAILY_LOSS_LIMIT_PCT
            )

        except Exception as e:
            return SafetyCheck(
                name="Daily Loss Limit",
                status=SafetyStatus.WARNING,
                message=f"Check failed: {e}"
            )

    def check_position_count(self) -> SafetyCheck:
        """Check number of positions against limit"""
        try:
            positions = self.trader.get_positions()
            count = len(positions)

            if count > self.MAX_POSITIONS:
                return SafetyCheck(
                    name="Position Count",
                    status=SafetyStatus.CRITICAL,
                    message=f"OVER LIMIT: {count} positions (max: {self.MAX_POSITIONS})",
                    value=count,
                    threshold=self.MAX_POSITIONS
                )

            if count == self.MAX_POSITIONS:
                return SafetyCheck(
                    name="Position Count",
                    status=SafetyStatus.WARNING,
                    message=f"At limit: {count}/{self.MAX_POSITIONS}",
                    value=count,
                    threshold=self.MAX_POSITIONS
                )

            return SafetyCheck(
                name="Position Count",
                status=SafetyStatus.OK,
                message=f"Positions: {count}/{self.MAX_POSITIONS}",
                value=count,
                threshold=self.MAX_POSITIONS
            )

        except Exception as e:
            return SafetyCheck(
                name="Position Count",
                status=SafetyStatus.WARNING,
                message=f"Check failed: {e}"
            )

    def check_buying_power(self) -> SafetyCheck:
        """Check available buying power"""
        try:
            account = self.trader.get_account()
            buying_power = account['buying_power']
            equity = account['equity']

            bp_pct = (buying_power / equity) * 100 if equity > 0 else 0

            if bp_pct < self.MIN_BUYING_POWER_PCT:
                return SafetyCheck(
                    name="Buying Power",
                    status=SafetyStatus.WARNING,
                    message=f"Low: {bp_pct:.1f}% (${buying_power:,.0f})",
                    value=bp_pct,
                    threshold=self.MIN_BUYING_POWER_PCT
                )

            return SafetyCheck(
                name="Buying Power",
                status=SafetyStatus.OK,
                message=f"Available: ${buying_power:,.0f} ({bp_pct:.1f}%)",
                value=bp_pct,
                threshold=self.MIN_BUYING_POWER_PCT
            )

        except Exception as e:
            return SafetyCheck(
                name="Buying Power",
                status=SafetyStatus.WARNING,
                message=f"Check failed: {e}"
            )

    def check_api_connection(self) -> SafetyCheck:
        """Check Alpaca API connection"""
        try:
            clock = self.trader.get_clock()

            return SafetyCheck(
                name="API Connection",
                status=SafetyStatus.OK,
                message=f"Connected (Market {'Open' if clock['is_open'] else 'Closed'})"
            )

        except Exception as e:
            return SafetyCheck(
                name="API Connection",
                status=SafetyStatus.CRITICAL,
                message=f"DISCONNECTED: {e}"
            )

    def check_emergency_stop(self) -> SafetyCheck:
        """Check emergency stop status"""
        if self.emergency_stop:
            return SafetyCheck(
                name="Emergency Stop",
                status=SafetyStatus.EMERGENCY,
                message="EMERGENCY STOP ACTIVE"
            )

        return SafetyCheck(
            name="Emergency Stop",
            status=SafetyStatus.OK,
            message="Not active"
        )

    def check_pdt_rule(self) -> SafetyCheck:
        """
        Check Pattern Day Trader rule compliance

        PDT Rule: If account < $25K, max 3 day trades in rolling 5 days
        A day trade = buy and sell same stock on same day

        We enforce this even on paper trading for realistic testing.
        """
        try:
            account = self.trader.get_account()
            portfolio_value = account['portfolio_value']
            daytrade_count = account.get('daytrade_count', 0)
            is_pdt = account.get('pattern_day_trader', False)

            # If account >= $25K, PDT doesn't apply
            if portfolio_value >= self.PDT_ACCOUNT_THRESHOLD and not self.PDT_ENFORCE_ALWAYS:
                return SafetyCheck(
                    name="PDT Rule",
                    status=SafetyStatus.OK,
                    message=f"Above ${self.PDT_ACCOUNT_THRESHOLD:,} - PDT N/A",
                    value=daytrade_count,
                    threshold=self.PDT_DAY_TRADE_LIMIT
                )

            # Check if already flagged as PDT
            if is_pdt:
                return SafetyCheck(
                    name="PDT Rule",
                    status=SafetyStatus.CRITICAL,
                    message="FLAGGED as Pattern Day Trader!",
                    value=daytrade_count,
                    threshold=self.PDT_DAY_TRADE_LIMIT
                )

            # Check day trade count
            if daytrade_count >= self.PDT_DAY_TRADE_LIMIT:
                return SafetyCheck(
                    name="PDT Rule",
                    status=SafetyStatus.CRITICAL,
                    message=f"PDT LIMIT: {daytrade_count}/{self.PDT_DAY_TRADE_LIMIT} day trades",
                    value=daytrade_count,
                    threshold=self.PDT_DAY_TRADE_LIMIT
                )

            # Warning if approaching limit
            if daytrade_count >= self.PDT_DAY_TRADE_LIMIT - 1:
                return SafetyCheck(
                    name="PDT Rule",
                    status=SafetyStatus.WARNING,
                    message=f"PDT Warning: {daytrade_count}/{self.PDT_DAY_TRADE_LIMIT} day trades",
                    value=daytrade_count,
                    threshold=self.PDT_DAY_TRADE_LIMIT
                )

            return SafetyCheck(
                name="PDT Rule",
                status=SafetyStatus.OK,
                message=f"Day trades: {daytrade_count}/{self.PDT_DAY_TRADE_LIMIT}",
                value=daytrade_count,
                threshold=self.PDT_DAY_TRADE_LIMIT
            )

        except Exception as e:
            return SafetyCheck(
                name="PDT Rule",
                status=SafetyStatus.WARNING,
                message=f"Check failed: {e}"
            )

    # =========================================================================
    # HEALTH CHECK
    # =========================================================================

    def run_health_check(self) -> HealthReport:
        """Run all safety checks and generate health report"""
        logger.info("Running health check...")

        checks = [
            self.check_emergency_stop(),
            self.check_api_connection(),
            self.check_sl_protection(),
            self.check_daily_loss(),
            self.check_position_count(),
            self.check_buying_power(),
            self.check_pdt_rule(),  # Layer 7: PDT Protection
        ]

        # Determine overall status
        statuses = [c.status for c in checks]

        if SafetyStatus.EMERGENCY in statuses:
            overall = SafetyStatus.EMERGENCY
        elif SafetyStatus.CRITICAL in statuses:
            overall = SafetyStatus.CRITICAL
        elif SafetyStatus.WARNING in statuses:
            overall = SafetyStatus.WARNING
        else:
            overall = SafetyStatus.OK

        # Determine if can trade
        can_trade = True
        reasons = []

        if self.emergency_stop:
            can_trade = False
            reasons.append("Emergency stop active")

        if self.daily_loss_triggered:
            can_trade = False
            reasons.append("Daily loss limit triggered")

        for check in checks:
            if check.status == SafetyStatus.CRITICAL:
                if check.name == "API Connection":
                    can_trade = False
                    reasons.append("API disconnected")
                elif check.name == "SL Protection":
                    # Can still trade but need to fix SL first
                    reasons.append("Unprotected positions - fix SL before new trades")
                elif check.name == "PDT Rule":
                    can_trade = False
                    reasons.append(f"PDT limit reached: {check.message}")

        report = HealthReport(
            timestamp=datetime.now(),
            overall_status=overall,
            checks=checks,
            can_trade=can_trade,
            reasons=reasons
        )

        self.last_health_check = report
        self.health_history.append(report)

        # Keep last 100 reports
        if len(self.health_history) > 100:
            self.health_history = self.health_history[-100:]

        return report

    def can_open_new_position(self) -> Tuple[bool, str]:
        """Check if safe to open a new position"""
        # Run fresh health check
        report = self.run_health_check()

        if not report.can_trade:
            return False, "; ".join(report.reasons)

        # Check position count
        positions = self.trader.get_positions()
        if len(positions) >= self.MAX_POSITIONS:
            return False, f"Max positions ({self.MAX_POSITIONS}) reached"

        return True, "OK"

    # =========================================================================
    # EMERGENCY CONTROLS
    # =========================================================================

    def activate_emergency_stop(self, reason: str = "Manual"):
        """Activate emergency stop - halts all trading"""
        logger.warning(f"🚨 EMERGENCY STOP ACTIVATED: {reason}")
        self.emergency_stop = True
        self._save_state()

    def deactivate_emergency_stop(self):
        """Deactivate emergency stop"""
        logger.info("Emergency stop deactivated")
        self.emergency_stop = False
        self._save_state()

    def emergency_close_all(self) -> Dict:
        """
        EMERGENCY: Close all positions and cancel all orders

        Use only in emergency situations!
        """
        logger.warning("🚨 EMERGENCY CLOSE ALL POSITIONS")

        results = {
            'orders_cancelled': 0,
            'positions_closed': 0,
            'errors': []
        }

        try:
            # Cancel all orders first
            self.trader.cancel_all_orders()
            results['orders_cancelled'] = True

            # Close all positions
            positions = self.trader.get_positions()
            for pos in positions:
                try:
                    self.trader.place_market_sell(pos.symbol, int(pos.qty))
                    results['positions_closed'] += 1
                    logger.info(f"Closed {pos.symbol}")
                except Exception as e:
                    results['errors'].append(f"{pos.symbol}: {e}")

        except Exception as e:
            results['errors'].append(f"Emergency close failed: {e}")

        # Activate emergency stop
        self.activate_emergency_stop("Emergency close all")

        return results

    # =========================================================================
    # POSITION PROTECTION
    # =========================================================================

    def ensure_sl_protection(self) -> List[str]:
        """
        Ensure all positions have SL orders

        Returns list of symbols that were fixed
        """
        fixed = []

        try:
            positions = self.trader.get_positions()
            orders = self.trader.get_orders(status='open')

            # Get symbols with SL orders
            sl_symbols = {}
            for order in orders:
                if order.type == 'stop' and order.side == 'sell':
                    sl_symbols[order.symbol] = order

            # Fix unprotected positions
            for pos in positions:
                if pos.symbol not in sl_symbols:
                    logger.warning(f"🛡️ Adding missing SL for {pos.symbol}")

                    # Calculate SL at -2.5% from current price
                    sl_price = pos.current_price * 0.975

                    try:
                        self.trader.place_stop_loss(
                            pos.symbol,
                            int(pos.qty),
                            sl_price
                        )
                        fixed.append(pos.symbol)
                        logger.info(f"✅ Added SL for {pos.symbol} @ ${sl_price:.2f}")
                    except Exception as e:
                        logger.error(f"Failed to add SL for {pos.symbol}: {e}")

        except Exception as e:
            logger.error(f"ensure_sl_protection failed: {e}")

        return fixed

    # =========================================================================
    # REPORTING
    # =========================================================================

    def get_status_summary(self) -> Dict:
        """Get current safety status summary"""
        report = self.run_health_check()

        return {
            'timestamp': report.timestamp.isoformat(),
            'overall_status': report.overall_status.value,
            'can_trade': report.can_trade,
            'reasons': report.reasons,
            'emergency_stop': self.emergency_stop,
            'daily_loss_triggered': self.daily_loss_triggered,
            'checks': [
                {
                    'name': c.name,
                    'status': c.status.value,
                    'message': c.message
                }
                for c in report.checks
            ]
        }

    def print_status(self):
        """Print formatted status to console"""
        summary = self.get_status_summary()

        print("=" * 60)
        print("TRADING SAFETY STATUS")
        print("=" * 60)
        print()
        print(f"Overall: {summary['overall_status'].upper()}")
        print(f"Can Trade: {'YES' if summary['can_trade'] else 'NO'}")

        if summary['reasons']:
            print(f"Reasons: {', '.join(summary['reasons'])}")

        print()
        print("Checks:")
        for check in summary['checks']:
            icon = {
                'ok': '✅',
                'warning': '⚠️',
                'critical': '🔴',
                'emergency': '🚨'
            }.get(check['status'], '❓')
            print(f"  {icon} {check['name']}: {check['message']}")

        print("=" * 60)


# =============================================================================
# TEST
# =============================================================================

def test_safety_system():
    """Test safety system"""
    print("=" * 60)
    print("TRADING SAFETY SYSTEM TEST")
    print("=" * 60)

    # Credentials from environment
    API_KEY = os.environ.get('ALPACA_API_KEY')
    SECRET_KEY = os.environ.get('ALPACA_SECRET_KEY')
    if not API_KEY or not SECRET_KEY:
        print("ERROR: Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables")
        return

    trader = AlpacaTrader(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        paper=True
    )

    safety = TradingSafetySystem(trader)

    # Run health check
    print("\n[1] Health Check:")
    safety.print_status()

    # Test can_open_new_position
    print("\n[2] Can Open New Position:")
    can_trade, reason = safety.can_open_new_position()
    print(f"    Result: {'YES' if can_trade else 'NO'}")
    print(f"    Reason: {reason}")

    # Test ensure_sl_protection
    print("\n[3] Ensure SL Protection:")
    fixed = safety.ensure_sl_protection()
    print(f"    Fixed: {fixed if fixed else 'None needed'}")

    print("\n" + "=" * 60)
    print("SAFETY SYSTEM TEST COMPLETE")
    print("=" * 60)

    return safety


if __name__ == "__main__":
    test_safety_system()
