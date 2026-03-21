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
  - Position size เล็ก (20% × $4,000 = $800)
  - Gap filter เข้ม (1%)
  - Worst case: -7% × $800 = -$56

v2.1 Changes:
- FIX: should_place_sl_order() now correctly returns False for NEW positions
- FIX: Use US Eastern Time for trading day calculation

PDT_RESERVE = 1: Keep last day trade for emergencies (SL only)

Author: Auto Trading System
Version: 2.2
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Tuple, Optional, Dict, TYPE_CHECKING
from enum import Enum
from loguru import logger
import os
import json
import tempfile
import pytz

if TYPE_CHECKING:
    from engine.broker_interface import BrokerInterface

# v2.4: PDT tracking database support
try:
    from database.repositories.pdt_repository import PDTRepository
    PDT_DB_AVAILABLE = True
except ImportError:
    PDT_DB_AVAILABLE = False
    logger.warning("PDTRepository not available, using JSON fallback")


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
    """
    PDT Smart Guard configuration

    ⚠️ **DEPRECATED in v6.10.1** ⚠️

    This class will be removed in v7.0 (est. March 2026).
    Use RapidRotationConfig directly instead.

    **Why deprecated:**
    - Unnecessary mapping layer (added complexity)
    - Duplicate config (violates single source of truth)
    - Harder to maintain (changes needed in 2 places)

    **Migration Example:**

    OLD (deprecated - will be removed):
    ```python
    from pdt_smart_guard import PDTConfig
    config = PDTConfig(
        max_day_trades=3,
        sl_threshold=-2.5,
        tp_threshold=4.0,
        reserve=1
    )
    guard = PDTSmartGuard(broker, config)
    ```

    NEW (recommended):
    ```python
    from config.strategy_config import RapidRotationConfig

    # Option 1: Load from YAML (best)
    config = RapidRotationConfig.from_yaml('config/trading.yaml')
    guard = PDTSmartGuard(broker, config)

    # Option 2: Create directly
    config = RapidRotationConfig(
        pdt_day_trade_limit=3,
        default_sl_pct=2.5,      # Positive value (not negative!)
        pdt_tp_threshold=4.0,
        pdt_reserve=1
    )
    guard = PDTSmartGuard(broker, config)
    ```

    **See:** docs/CONFIG_SCHEMA.md for full migration guide
    """
    max_day_trades: int = 3        # PDT limit
    sl_threshold: float = -2.5     # % loss to trigger SL
    tp_threshold: float = +4.0     # % profit worth using PDT (4% > 5% for faster lock)
    reserve: int = 1               # Keep N day trades for SL emergencies
    enforce_on_paper: bool = True  # Enforce even on paper trading
    # v2.2: Removed critical_threshold - ไม่ override PDT เด็ดขาด

    def __post_init__(self):
        """Emit deprecation warning when PDTConfig is instantiated"""
        import warnings
        warnings.warn(
            "\n"
            "=" * 70 + "\n"
            "⚠️  PDTConfig is DEPRECATED (v6.10.1)\n"
            "=" * 70 + "\n"
            "This class will be removed in v7.0 (March 2026).\n"
            "\n"
            "Use RapidRotationConfig directly instead:\n"
            "\n"
            "  # OLD (deprecated)\n"
            "  config = PDTConfig(max_day_trades=3, ...)\n"
            "\n"
            "  # NEW (recommended)\n"
            "  from config.strategy_config import RapidRotationConfig\n"
            "  config = RapidRotationConfig.from_yaml('config/trading.yaml')\n"
            "  guard = PDTSmartGuard(broker, config)\n"
            "\n"
            "See docs/CONFIG_SCHEMA.md for migration guide.\n"
            "=" * 70,
            DeprecationWarning,
            stacklevel=2
        )

    @classmethod
    def from_rapid_rotation_config(cls, config: 'RapidRotationConfig') -> 'PDTConfig':
        """
        ⚠️ DEPRECATED: Use RapidRotationConfig directly in PDTSmartGuard.__init__

        This factory method will be removed in v7.0.
        Pass RapidRotationConfig directly to PDTSmartGuard instead.

        Example:
            # OLD (deprecated)
            pdt_config = PDTConfig.from_rapid_rotation_config(config)
            guard = PDTSmartGuard(broker, pdt_config)

            # NEW (recommended)
            guard = PDTSmartGuard(broker, config)  # Pass RapidRotationConfig directly
        """
        import warnings
        warnings.warn(
            "PDTConfig.from_rapid_rotation_config() is deprecated. "
            "Pass RapidRotationConfig directly to PDTSmartGuard instead.",
            DeprecationWarning,
            stacklevel=2
        )

        from config.strategy_config import RapidRotationConfig  # Import for type checking

        return cls(
            max_day_trades=config.pdt_day_trade_limit,
            sl_threshold=config.default_sl_pct * -1,  # Convert to negative
            tp_threshold=config.pdt_tp_threshold,
            reserve=getattr(config, 'pdt_reserve', 1),  # Use config value or default
            enforce_on_paper=config.pdt_enforce_always
        )


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
    PDT Smart Guard v2.3 - Simplified Config

    v6.10.1 Changes: Uses RapidRotationConfig directly (no mapping needed)

    Intelligently manages day trade budget to:
    1. Protect capital (allow SL exits)
    2. Lock profits (allow TP exits when profitable enough)
    3. Save PDT budget (hold small gains overnight)
    4. Reserve last day trade for emergencies
    """

    def __init__(self, broker: 'BrokerInterface' = None, config = None, data_dir: str = None):
        """
        Initialize PDT Smart Guard

        Args:
            broker: Broker interface
            config: RapidRotationConfig (v6.10.1+) or PDTConfig (deprecated, backward compat)
                   If None, loads from default YAML path
            data_dir: Data directory for persistence

        v6.10.1: Simplified to use RapidRotationConfig directly (no mapping)
        """
        self.broker = broker

        # v6.10.1: Support both RapidRotationConfig and PDTConfig (backward compat)
        if config is None:
            # Load default config
            try:
                from config.strategy_config import RapidRotationConfig
                config_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'config', 'trading.yaml'
                )
                config = RapidRotationConfig.from_yaml(config_path)
                logger.debug(f"PDTSmartGuard: Loaded RapidRotationConfig from {config_path}")
            except Exception as e:
                logger.warning(f"PDTSmartGuard: Failed to load config, using defaults: {e}")
                from config.strategy_config import RapidRotationConfig
                config = RapidRotationConfig()

        # Check if old PDTConfig or new RapidRotationConfig
        if isinstance(config, PDTConfig):
            logger.warning("PDTConfig is deprecated. Please pass RapidRotationConfig directly.")
            self._use_legacy_config = True
        else:
            self._use_legacy_config = False

        self.config = config

        # Data directory for persistence
        if data_dir is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), '..', 'data'
            )
        self._data_dir = os.path.abspath(data_dir)
        os.makedirs(self._data_dir, exist_ok=True)
        self._entry_dates_file = os.path.join(self._data_dir, 'pdt_entry_dates.json')

        # v2.4: Initialize database repository
        self._pdt_repo = PDTRepository() if PDT_DB_AVAILABLE else None

        # Cache for entry dates (symbol -> date in US Eastern Time)
        self._entry_dates: Dict[str, date] = {}

        # US Eastern timezone for trading day calculations
        self._et_tz = pytz.timezone('US/Eastern')

        # Load persisted entry dates
        self._load_entry_dates()

        logger.info(f"PDT Smart Guard v2.4 initialized (DB-enabled, No Override Mode)")
        logger.info(f"  Storage: {'Database' if self._pdt_repo else 'JSON (fallback)'}")
        logger.info(f"  SL Threshold: -{self._get_sl_threshold()}%")
        logger.info(f"  TP Threshold: {self._get_tp_threshold()}%")
        logger.info(f"  Reserve: {self._get_reserve()} day trades")
        logger.info(f"  Budget = 0 → HOLD (ไม่ override PDT เด็ดขาด)")

    # v6.10.1: Helper properties for config access (backward compatible)
    def _get_max_day_trades(self) -> int:
        """Get max day trades (supports both config types)"""
        if self._use_legacy_config:
            return self.config.max_day_trades
        return self.config.pdt_day_trade_limit

    def _get_sl_threshold(self) -> float:
        """Get SL threshold as positive value (supports both config types)"""
        if self._use_legacy_config:
            return abs(self.config.sl_threshold)  # Convert -2.5 to 2.5
        return self.config.default_sl_pct  # Already positive

    def _get_tp_threshold(self) -> float:
        """Get TP threshold (supports both config types)"""
        if self._use_legacy_config:
            return self.config.tp_threshold
        return self.config.pdt_tp_threshold

    def _get_reserve(self) -> int:
        """Get reserve (supports both config types)"""
        if self._use_legacy_config:
            return self.config.reserve
        return getattr(self.config, 'pdt_reserve', 1)  # Default 1 if not in config yet

    def _get_enforce_on_paper(self) -> bool:
        """Get enforce on paper (supports both config types)"""
        if self._use_legacy_config:
            return self.config.enforce_on_paper
        return self.config.pdt_enforce_always

    def _get_et_date(self) -> date:
        """
        Get current date in US Eastern Time

        IMPORTANT: PDT rules use TRADING DAY, not calendar day
        Trading day = US Eastern Time date
        """
        return datetime.now(self._et_tz).date()

    def _save_entry_dates(self):
        """
        Persist entry dates to database (preferred) or JSON (fallback).

        v2.4: Database-first with JSON fallback
        """
        # Try database first
        if self._pdt_repo:
            try:
                # Sync all in-memory entries to database
                # Note: We only track active entries (no exit_date)
                # So we just upsert all current entries
                for symbol, entry_date in self._entry_dates.items():
                    self._pdt_repo.add_entry(symbol, entry_date.isoformat())
                return  # Success - no need for JSON
            except Exception as e:
                logger.warning(f"PDT Guard: DB save failed ({e}), falling back to JSON")

        # Fallback to JSON
        try:
            data = {sym: d.isoformat() for sym, d in self._entry_dates.items()}
            fd, tmp_path = tempfile.mkstemp(dir=self._data_dir, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp_path, self._entry_dates_file)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.error(f"PDT Guard: Failed to save entry dates: {e}")

    def _load_entry_dates(self):
        """
        Load persisted entry dates from database (preferred) or JSON (fallback).

        v2.4: Database-first with JSON fallback
        """
        # Try database first
        if self._pdt_repo:
            try:
                db_entries = self._pdt_repo.get_all_entries()
                for symbol, entry_date_str in db_entries.items():
                    self._entry_dates[symbol] = date.fromisoformat(entry_date_str)
                logger.info(f"PDT Guard: Loaded {len(self._entry_dates)} entry dates from database")
                return  # Success - no need for JSON
            except Exception as e:
                logger.warning(f"PDT Guard: DB load failed ({e}), falling back to JSON")

        # Fallback to JSON
        try:
            if not os.path.exists(self._entry_dates_file):
                return
            with open(self._entry_dates_file, 'r') as f:
                data = json.load(f)
            for sym, date_str in data.items():
                self._entry_dates[sym] = date.fromisoformat(date_str)
            logger.info(f"PDT Guard: Loaded {len(self._entry_dates)} entry dates from JSON")
        except Exception as e:
            logger.error(f"PDT Guard: Failed to load entry dates: {e}")

    def record_entry(self, symbol: str, entry_date: date = None):
        """
        Record entry date for a position

        If entry_date not provided, uses current US Eastern date
        """
        if entry_date is None:
            entry_date = self._get_et_date()
        self._entry_dates[symbol] = entry_date
        self._save_entry_dates()
        logger.debug(f"PDT Guard: Recorded entry for {symbol} on {self._entry_dates[symbol]} (ET)")

    def remove_entry(self, symbol: str):
        """Remove entry record when position closed"""
        if symbol in self._entry_dates:
            # v7.8: Record exit_date + same_day_exit in DB before removing from memory
            if self._pdt_repo:
                try:
                    self._pdt_repo.record_exit(symbol)
                except Exception as e:
                    logger.warning(f"PDT Guard: Failed to record exit for {symbol}: {e}")
            del self._entry_dates[symbol]
            self._save_entry_dates()

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
            return 0  # Unknown = assume Day 0 (cautious)

        # CRITICAL: Use US Eastern date, not local date!
        today_et = self._get_et_date()
        return (today_et - entry_date).days

    def get_pdt_status(self) -> PDTStatus:
        """
        Get current PDT status from Alpaca account (real-time).

        This uses Alpaca's official day trade count and PDT flag,
        which is THE authoritative source (not manually tracked).

        Returns:
            PDTStatus with:
                - day_trade_count: Official count from Alpaca (rolling 5 days)
                - remaining: Day trades left before hitting limit
                - is_flagged: True if account is flagged as Pattern Day Trader
                - can_day_trade: True if can execute day trades
                - reserve_active: True if at reserve limit

        Note:
            Alpaca's day_trade_count is THE single source of truth.
            It includes all day trades executed across all platforms/clients.
        """
        try:
            if not self.broker:
                logger.warning("PDT Guard: No broker connected, using fallback status")
                return PDTStatus(0, 3, False, True, False)

            # Get real-time account data from Alpaca
            account = self.broker.get_account()

            # Extract PDT info (Alpaca is the authoritative source)
            day_trade_count = int(getattr(account, 'day_trade_count', 0))
            is_flagged = bool(getattr(account, 'pattern_day_trader', False))
            equity = float(getattr(account, 'equity', 0))

            # Calculate remaining day trades
            max_trades = self._get_max_day_trades()
            remaining = max(0, max_trades - day_trade_count)

            # Check if at reserve limit
            reserve = self._get_reserve()
            reserve_active = remaining <= reserve

            # Log if status changed significantly
            if hasattr(self, '_last_day_trade_count'):
                if day_trade_count != self._last_day_trade_count:
                    logger.info(f"PDT Status Update: {day_trade_count} day trades used "
                               f"({remaining} remaining, equity=${equity:,.0f})")
            self._last_day_trade_count = day_trade_count

            return PDTStatus(
                day_trade_count=day_trade_count,
                remaining=remaining,
                is_flagged=is_flagged,
                can_day_trade=remaining > 0 and not is_flagged,
                reserve_active=reserve_active
            )
        except Exception as e:
            logger.error(f"Failed to get PDT status from Alpaca: {e}, using fallback")
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
        # pdt_enforce_always=false → bypass all PDT restrictions
        if not self._get_enforce_on_paper():
            return True, SellDecision.ALLOWED, "PDT not enforced (pdt_enforce_always=false)"

        days_held = self.get_days_held(symbol)

        # Day 1+: Always allowed (not a day trade)
        if days_held >= 1:
            return True, SellDecision.ALLOWED, f"Day {days_held} - not a day trade"

        # Day 0: Check PDT budget
        pdt_status = self.get_pdt_status()

        # v4.6: Use per-position thresholds if provided
        # v6.10.1: Use helper methods (handles both config types)
        sl_threshold = -abs(sl_override) if sl_override is not None else -self._get_sl_threshold()
        tp_threshold = tp_override if tp_override is not None else self._get_tp_threshold()

        # Already flagged as PDT
        if pdt_status.is_flagged:
            logger.warning(f"PDT Guard: Account flagged as PDT - sells restricted")
            return False, SellDecision.BLOCKED_NO_BUDGET, "Account flagged as PDT"

        # v2.3: STRICT MODE - NEVER use day trades (ติด flag แย่กว่าขาดทุน)
        # BLOCK ทุกกรณีเมื่อ Day 0 - แม้ SL/TP ก็ HOLD overnight
        logger.warning(f"PDT Guard: {symbol} BLOCKED - Day 0 position")
        logger.warning(f"  P&L: {pnl_pct:+.1f}% → HOLD overnight (wait for Day 1)")
        logger.warning(f"  PDT remaining: {pdt_status.remaining}/{self._get_max_day_trades()}")
        logger.warning(f"  v2.3 STRICT: ไม่ใช้ PDT เด็ดขาด (ติด flag = 90 วันห้ามเทรด)")

        if pnl_pct <= sl_threshold:
            logger.error(f"  ⚠️  SL hit ({pnl_pct:.2f}%) but HOLDING to avoid PDT flag!")
            return False, SellDecision.BLOCKED_NO_BUDGET, f"SL hit but HOLD (avoid PDT flag)"
        elif pnl_pct >= tp_threshold:
            logger.info(f"  💰 TP hit ({pnl_pct:.2f}%) but HOLDING to avoid PDT flag")
            return False, SellDecision.HOLD_OVERNIGHT, f"TP hit but HOLD (avoid PDT flag)"
        else:
            logger.info(f"  Hold overnight (save all PDT budget)")
            return False, SellDecision.HOLD_OVERNIGHT, f"Hold overnight (strict PDT mode)"

    def should_place_sl_order(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if SL order should be placed at Alpaca

        NEW position (no entry_date): NO SL order (Day 0)
        Day 0: NO SL order (we monitor manually to control PDT)
        Day 1+: Place SL order normally

        Returns:
            (should_place: bool, reason: str)
        """
        # pdt_enforce_always=false → always place SL orders (no PDT restriction)
        if not self._get_enforce_on_paper():
            return True, "PDT not enforced - SL order allowed"

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

    def should_place_eod_sl(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if EOD (end-of-day) SL should be placed for Day 0 positions.

        Day 0 positions normally have NO SL order (PDT control).
        But near market close (15:50 ET+), they become overnight holds,
        so we place SL to protect against overnight gaps.

        Returns:
            (should_place: bool, reason: str)
        """
        # pdt_enforce_always=false → no special EOD handling needed (SL already placed normally)
        if not self._get_enforce_on_paper():
            return False, "PDT not enforced - SL placed at entry, no EOD handling needed"

        entry_date = self._entry_dates.get(symbol)
        if not entry_date:
            return False, "No entry date recorded"

        days_held = self.get_days_held(symbol)
        if days_held != 0:
            return False, f"Day {days_held} - already has SL via should_place_sl_order()"

        # Day 0: Check if near market close
        now_et = datetime.now(self._et_tz)
        market_close_soon = now_et.hour == 15 and now_et.minute >= 50

        if market_close_soon:
            return True, "Day 0 near close (15:50+ ET) - place overnight SL"

        return False, "Day 0 before 15:50 ET - no SL (PDT control)"

    def get_guard_status(self) -> Dict:
        """Get full guard status for UI/API"""
        pdt_status = self.get_pdt_status()

        return {
            'enabled': True,
            'version': '2.3',
            'pdt': {
                'used': pdt_status.day_trade_count,
                'limit': self._get_max_day_trades(),
                'remaining': pdt_status.remaining,
                'is_flagged': pdt_status.is_flagged,
                'reserve_active': pdt_status.reserve_active
            },
            'config': {
                'sl_threshold': -self._get_sl_threshold(),  # Return as negative for consistency
                'tp_threshold': self._get_tp_threshold(),
                'reserve': self._get_reserve()
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


def init_pdt_guard(broker: 'BrokerInterface' = None, config: PDTConfig = None) -> PDTSmartGuard:
    """Initialize PDT Guard with broker"""
    global _guard
    _guard = PDTSmartGuard(broker, config)
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
