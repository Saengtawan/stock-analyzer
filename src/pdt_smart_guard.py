#!/usr/bin/env python3
"""
PDT SMART GUARD v2.2
====================
Intelligent Pattern Day Trader protection for accounts < $25K

Design Philosophy:
- Day 1+: Sell freely (not a day trade)
- Day 0 + Budget > 0: Check PDT budget before sell
  - SL hit (-2.5%): Use PDT to cut loss
  - TP hit (+4%): Use PDT to lock profit
  - Small gain (<4%): Hold overnight (save PDT)
- Day 0 + Budget = 0: HOLD ทุกกรณี (รอ Day 1)
  - ไม่ override PDT เด็ดขาด → ไม่มีทางโดน flag

v2.2 Changes:
- REMOVED Critical Override: ไม่ยอมโดน PDT flag ไม่ว่ากรณีใด
- Budget = 0 → HOLD ทุกกรณี (แม้ขาดทุนหนัก)
- Low Risk Mode ป้องกัน worst case:
  - Position size เล็ก ($1,000)
  - Gap filter เข้ม (1%)
  - Worst case: -7% × $1,000 = -$70

v2.1 Changes:
- FIX: should_place_sl_order() now correctly returns False for NEW positions
- FIX: Use US Eastern Time for trading day calculation

PDT_RESERVE = 1: Keep last day trade for emergencies (SL only)

Author: Auto Trading System
Version: 2.2
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Tuple, Optional, Dict
from enum import Enum
from loguru import logger
import os
import pytz


class SellDecision(Enum):
    """Sell decision types"""
    ALLOWED = "ALLOWED"                    # Day 1+ or budget available
    SL_EMERGENCY = "SL_EMERGENCY"          # Day 0 SL - use PDT
    TP_PROFITABLE = "TP_PROFITABLE"        # Day 0 TP - use PDT
    BLOCKED_NO_BUDGET = "BLOCKED_NO_BUDGET"  # No PDT budget left - HOLD (v2.2: no override)
    BLOCKED_RESERVE = "BLOCKED_RESERVE"    # Reserve for SL only
    HOLD_OVERNIGHT = "HOLD_OVERNIGHT"      # Small gain - save PDT


@dataclass
class PDTConfig:
    """PDT Smart Guard configuration"""
    max_day_trades: int = 3        # PDT limit
    sl_threshold: float = -2.5     # % loss to trigger SL
    tp_threshold: float = +4.0     # % profit worth using PDT (4% > 5% for faster lock)
    reserve: int = 1               # Keep N day trades for SL emergencies
    enforce_on_paper: bool = True  # Enforce even on paper trading
    # v2.2: Removed critical_threshold - ไม่ override PDT เด็ดขาด


@dataclass
class PDTStatus:
    """Current PDT status"""
    day_trade_count: int
    remaining: int
    is_flagged: bool
    can_day_trade: bool
    reserve_active: bool


class PDTSmartGuard:
    """
    PDT Smart Guard v2.0

    Intelligently manages day trade budget to:
    1. Protect capital (allow SL exits)
    2. Lock profits (allow TP exits when profitable enough)
    3. Save PDT budget (hold small gains overnight)
    4. Reserve last day trade for emergencies
    """

    def __init__(self, trader=None, config: PDTConfig = None):
        self.trader = trader
        self.config = config or PDTConfig()

        # Cache for entry dates (symbol -> date in US Eastern Time)
        self._entry_dates: Dict[str, date] = {}

        # US Eastern timezone for trading day calculations
        self._et_tz = pytz.timezone('US/Eastern')

        logger.info(f"PDT Smart Guard v2.2 initialized (No Override Mode)")
        logger.info(f"  SL Threshold: {self.config.sl_threshold}%")
        logger.info(f"  TP Threshold: {self.config.tp_threshold}%")
        logger.info(f"  Reserve: {self.config.reserve} day trades")
        logger.info(f"  Budget = 0 → HOLD (ไม่ override PDT เด็ดขาด)")

    def set_trader(self, trader):
        """Set trader instance"""
        self.trader = trader

    def _get_et_date(self) -> date:
        """
        Get current date in US Eastern Time

        IMPORTANT: PDT rules use TRADING DAY, not calendar day
        Trading day = US Eastern Time date
        """
        return datetime.now(self._et_tz).date()

    def record_entry(self, symbol: str, entry_date: date = None):
        """
        Record entry date for a position

        If entry_date not provided, uses current US Eastern date
        """
        if entry_date is None:
            entry_date = self._get_et_date()
        self._entry_dates[symbol] = entry_date
        logger.debug(f"PDT Guard: Recorded entry for {symbol} on {self._entry_dates[symbol]} (ET)")

    def remove_entry(self, symbol: str):
        """Remove entry record when position closed"""
        if symbol in self._entry_dates:
            del self._entry_dates[symbol]

    def get_entry_date(self, symbol: str) -> Optional[date]:
        """Get entry date for a symbol"""
        return self._entry_dates.get(symbol)

    def get_days_held(self, symbol: str) -> int:
        """
        Get number of TRADING DAYS position has been held

        Uses US Eastern Time for date comparison
        Day 0 = bought today (same ET date) = Day Trade if sold
        Day 1+ = bought on previous ET date = NOT a Day Trade
        """
        entry_date = self._entry_dates.get(symbol)
        if not entry_date:
            return 999  # Unknown = assume safe

        # CRITICAL: Use US Eastern date, not local date!
        today_et = self._get_et_date()
        return (today_et - entry_date).days

    def get_pdt_status(self) -> PDTStatus:
        """Get current PDT status from Alpaca"""
        try:
            if not self.trader:
                return PDTStatus(0, 3, False, True, False)

            account = self.trader.get_account()
            day_trade_count = account.get('daytrade_count', 0)
            is_flagged = account.get('pattern_day_trader', False)
            remaining = max(0, self.config.max_day_trades - day_trade_count)

            return PDTStatus(
                day_trade_count=day_trade_count,
                remaining=remaining,
                is_flagged=is_flagged,
                can_day_trade=remaining > 0 and not is_flagged,
                reserve_active=remaining <= self.config.reserve
            )
        except Exception as e:
            logger.error(f"PDT status error: {e}")
            return PDTStatus(0, 3, False, True, False)

    def is_day_trade(self, symbol: str) -> bool:
        """Check if selling this symbol today would be a day trade"""
        days_held = self.get_days_held(symbol)
        return days_held == 0

    def can_sell(self, symbol: str, pnl_pct: float, sl_override: float = None, tp_override: float = None) -> Tuple[bool, SellDecision, str]:
        """
        Check if selling is allowed under PDT rules

        v4.6: sl_override/tp_override for per-position ATR-based thresholds
        - sl_override: SL% for this position (e.g., -4% for AMD)
        - tp_override: PDT TP% for this position (= SL% for R:R 1:1)

        Returns:
            (allowed: bool, decision: SellDecision, reason: str)
        """
        days_held = self.get_days_held(symbol)

        # Day 1+: Always allowed (not a day trade)
        if days_held >= 1:
            return True, SellDecision.ALLOWED, f"Day {days_held} - not a day trade"

        # Day 0: Check PDT budget
        pdt_status = self.get_pdt_status()

        # v4.6: Use per-position thresholds if provided
        sl_threshold = -abs(sl_override) if sl_override is not None else self.config.sl_threshold
        tp_threshold = tp_override if tp_override is not None else self.config.tp_threshold

        # Already flagged as PDT
        if pdt_status.is_flagged:
            logger.warning(f"PDT Guard: Account flagged as PDT - sells restricted")
            return False, SellDecision.BLOCKED_NO_BUDGET, "Account flagged as PDT"

        # No budget left - v2.2: HOLD ทุกกรณี (ไม่ override PDT เด็ดขาด)
        if pdt_status.remaining <= 0:
            logger.warning(f"PDT Guard: {symbol} BLOCKED - no day trades remaining")
            logger.warning(f"  P&L: {pnl_pct:+.1f}% → HOLD overnight (wait for Day 1)")
            logger.warning(f"  v2.2: ไม่ override PDT → ไม่มีทางโดน flag")
            return False, SellDecision.BLOCKED_NO_BUDGET, f"No PDT budget (0/{self.config.max_day_trades}) - HOLD overnight"

        # SL triggered: Allow even with reserve (emergency exit)
        if pnl_pct <= sl_threshold:
            logger.info(f"PDT Guard: {symbol} SL EMERGENCY at {pnl_pct:.2f}% - using day trade")
            return True, SellDecision.SL_EMERGENCY, f"SL emergency ({pnl_pct:.2f}% <= {sl_threshold}%)"

        # TP triggered: Check if worth using PDT (v4.6: dynamic threshold)
        if pnl_pct >= tp_threshold:
            # Check reserve
            if pdt_status.reserve_active:
                logger.info(f"PDT Guard: {symbol} TP at {pnl_pct:.2f}% - BLOCKED (reserve for SL)")
                return False, SellDecision.BLOCKED_RESERVE, f"Reserve active - save for SL"

            logger.info(f"PDT Guard: {symbol} TP PROFITABLE at {pnl_pct:.2f}% - using day trade")
            return True, SellDecision.TP_PROFITABLE, f"TP profitable ({pnl_pct:.2f}% >= {tp_threshold}%)"

        # Small gain: Hold overnight to save PDT
        logger.info(f"PDT Guard: {symbol} HOLD overnight ({pnl_pct:.2f}% < {tp_threshold}%)")
        return False, SellDecision.HOLD_OVERNIGHT, f"Hold overnight (gain {pnl_pct:.2f}% not worth PDT)"

    def should_place_sl_order(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if SL order should be placed at Alpaca

        NEW position (no entry_date): NO SL order (Day 0)
        Day 0: NO SL order (we monitor manually to control PDT)
        Day 1+: Place SL order normally

        Returns:
            (should_place: bool, reason: str)
        """
        # v2.1 FIX: Check if entry_date exists FIRST
        # If no entry_date → NEW position being bought NOW → Day 0
        entry_date = self._entry_dates.get(symbol)
        if not entry_date:
            # NEW position = Day 0 = don't place SL order
            # This is called BEFORE record_entry() in execute_signal()
            return False, "New position (Day 0) - no SL order"

        days_held = self.get_days_held(symbol)

        if days_held == 0:
            return False, "Day 0 - PDT Guard active (no SL order)"

        return True, f"Day {days_held} - SL order allowed"

    def get_guard_status(self) -> Dict:
        """Get full guard status for UI/API"""
        pdt_status = self.get_pdt_status()

        return {
            'enabled': True,
            'version': '2.0',
            'pdt': {
                'used': pdt_status.day_trade_count,
                'limit': self.config.max_day_trades,
                'remaining': pdt_status.remaining,
                'is_flagged': pdt_status.is_flagged,
                'reserve_active': pdt_status.reserve_active
            },
            'config': {
                'sl_threshold': self.config.sl_threshold,
                'tp_threshold': self.config.tp_threshold,
                'reserve': self.config.reserve
            },
            'positions': {
                symbol: {
                    'entry_date': str(entry_date),
                    'days_held': (self._get_et_date() - entry_date).days,
                    'is_day_trade': (self._get_et_date() - entry_date).days == 0
                }
                for symbol, entry_date in list(self._entry_dates.items())  # copy to avoid iteration error
            },
            'current_et_date': str(self._get_et_date())  # For debugging
        }

    def log_status(self):
        """Log current PDT status"""
        status = self.get_guard_status()
        pdt = status['pdt']

        logger.info("=" * 50)
        logger.info("PDT SMART GUARD STATUS")
        logger.info("=" * 50)
        logger.info(f"Day Trades: {pdt['used']}/{pdt['limit']} (remaining: {pdt['remaining']})")
        logger.info(f"Reserve Active: {pdt['reserve_active']}")
        logger.info(f"Flagged: {pdt['is_flagged']}")

        if status['positions']:
            logger.info("Positions:")
            for symbol, pos in status['positions'].items():
                day_trade_warning = " ⚠️ DAY TRADE" if pos['is_day_trade'] else ""
                logger.info(f"  {symbol}: Day {pos['days_held']}{day_trade_warning}")

        logger.info("=" * 50)


# Singleton instance
_guard: Optional[PDTSmartGuard] = None


def get_pdt_guard() -> PDTSmartGuard:
    """Get singleton PDT Guard instance"""
    global _guard
    if _guard is None:
        _guard = PDTSmartGuard()
    return _guard


def init_pdt_guard(trader=None, config: PDTConfig = None) -> PDTSmartGuard:
    """Initialize PDT Guard with trader"""
    global _guard
    _guard = PDTSmartGuard(trader, config)
    return _guard


# =============================================================================
# TEST
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("PDT SMART GUARD v2.0 - TEST")
    print("=" * 60)

    # Create guard without trader (for testing)
    guard = PDTSmartGuard(config=PDTConfig(
        max_day_trades=3,
        sl_threshold=-2.5,
        tp_threshold=5.0,
        reserve=1
    ))

    # Mock entry dates
    guard.record_entry("AMD", date.today())  # Day 0
    guard.record_entry("AAPL", date(2026, 2, 1))  # Day 1+

    print("\n--- Test Cases ---\n")

    # Test Day 0 scenarios
    test_cases = [
        ("AMD", -3.0, "Day 0, SL hit"),
        ("AMD", -1.0, "Day 0, small loss"),
        ("AMD", +2.0, "Day 0, small gain"),
        ("AMD", +6.0, "Day 0, TP hit"),
        ("AAPL", -3.0, "Day 1+, SL hit"),
        ("AAPL", +2.0, "Day 1+, any gain"),
    ]

    for symbol, pnl, desc in test_cases:
        allowed, decision, reason = guard.can_sell(symbol, pnl)
        status = "✅ SELL" if allowed else "❌ HOLD"
        print(f"{desc:25} | {status} | {decision.value} | {reason}")

    print("\n--- Guard Status ---\n")
    guard.log_status()
