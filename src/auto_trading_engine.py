#!/usr/bin/env python3
"""
AUTO TRADING ENGINE - Phase 2
Rapid Trader v4.5 - Low Risk Mode Edition

Integrates:
- Alpaca Module (Phase 1) for order execution
- Rapid Rotation Screener for signal generation
- Trailing stop logic (v3.11: +3% activation, 80% lock)
- Market Regime Filter (SPY > SMA20 = Bull → Trade)
- Signal Queue (v4.1) - queue signals when positions full
- Regime Cache (v4.2) - cache regime check for 5 min
- Gap Filter (v4.3) - skip stocks that gap up/down too much
- Earnings Filter (v4.4) - skip stocks with earnings within 5 days
- Late Start Protection (v4.4) - skip scan if > 15 min after open
- Low Risk Mode (v4.5) - stricter criteria when PDT budget = 0

v4.5 Changes:
- Low Risk Mode: เมื่อ PDT budget = 0 → ยังซื้อได้ แต่เข้มขึ้น
  - Gap filter เข้มขึ้น: 1% (ปกติ 2%)
  - Score สูงขึ้น: 90 (ปกติ 85)
  - Position size เล็กลง: 25% (ปกติ 45%)
  - ATR limit: < 4% (ไม่ซื้อหุ้นผันผวนมาก)
  เหตุผล: ต้อง hold ข้ามคืนอยู่แล้ว → เลือกเฉพาะหุ้นปลอดภัยสุด

v4.4 Changes:
- Earnings Filter: Skip stocks with earnings within 5 days
  เหตุผล: เสี่ยง gap ±10-20% หลัง earnings
- Late Start Protection: Skip scan if started > 15 min after market open
  เหตุผล: ราคาอาจขึ้นไปแล้ว ไม่ใช่ dip bounce
- TAKE_PROFIT_PCT: 6% → 5% (เกิดบ่อยกว่า, trailing จับ upside)
- PDT_TP_THRESHOLD: 6% → 4% (Day 0 sell, +4% เกิดบ่อยกว่า)

v4.3 Changes:
- Gap Filter: Skip stocks with gap > +2% or < -5% from prev close
  เหตุผล: Gap up แรง = ไม่ใช่ dip bounce แล้ว
  AMD case: gap +3.6% > +2% → SKIP

v4.2 Changes:
- Regime cache to avoid repeated yfinance calls (5 min cache)

v4.1 Changes:
- Signal Queue: Queue signals when positions full
- ATR-based deviation check for queued signals
- Freshness priority (< 30 min signals first)

v4.0 Changes:
- Added Market Regime Filter: Only trade when SPY > SMA20
  Result: WR 49%, +5.5%/mo, DD 8.9% (meets both targets!)
- Updated position sizing for optimal returns

Daily Flow:
- 06:00 ET: System wake up, health check
- 09:00 ET: Pre-market scan + Regime check
- 09:30 ET: Market open → Check late start → Execute signals
- 09:31-15:59 ET: Monitor loop (every 1 min)
- 15:50 ET: Pre-close check
- 16:00 ET: Daily summary
- 16:01+ ET: Sleep mode
"""

import os
import sys
import time
import json
import tempfile
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import pytz
import pandas as pd

# Add src to path
src_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, src_dir)
sys.path.insert(0, os.path.dirname(src_dir))  # Add parent for 'src' imports

from alpaca_trader import AlpacaTrader, Position, Order
from trading_safety import TradingSafetySystem, SafetyStatus
from pdt_smart_guard import PDTSmartGuard, PDTConfig, SellDecision, init_pdt_guard
from trade_logger import get_trade_logger, TradeLogger
from loguru import logger

# For Market Regime Filter
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not available - regime filter disabled")

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
    STOPPED = "stopped"


@dataclass
class ManagedPosition:
    """Position with trailing stop management (v4.6: ATR-based SL/TP)"""
    symbol: str
    qty: int
    entry_price: float
    entry_time: datetime
    sl_order_id: str
    current_sl_price: float
    peak_price: float
    trailing_active: bool = False
    days_held: int = 0
    # v4.6: ATR-based per-position SL/TP
    sl_pct: float = 2.5          # Actual SL% for this position
    tp_price: float = 0.0        # Target TP price
    tp_pct: float = 5.0          # Actual TP% for this position
    atr_pct: float = 0.0         # ATR% at entry
    # v4.7: Sector diversification
    sector: str = ""             # Stock sector (e.g. "Technology")
    # v4.8: Price action tracking
    trough_price: float = 0.0   # Lowest price during hold


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
    regime_status: str = "UNKNOWN"  # v4.0: Track market regime
    regime_skipped: bool = False    # v4.0: True if skipped due to bear market
    queue_added: int = 0            # v4.1: Signals added to queue
    queue_executed: int = 0         # v4.1: Signals executed from queue
    queue_expired: int = 0          # v4.1: Signals expired (price moved too much)
    queue_rescans: int = 0          # v4.1: Times rescanned after queue empty
    gap_rejected: int = 0           # v4.3: Signals rejected by gap filter
    earnings_rejected: int = 0      # v4.4: Signals rejected by earnings filter
    late_start_skipped: bool = False  # v4.4: True if scan skipped due to late start
    low_risk_trades: int = 0        # v4.5: Trades executed in low risk mode
    sector_rejected: int = 0        # v4.7: Signals rejected by sector filter


@dataclass
class QueuedSignal:
    """
    Signal Queue Entry - v4.1 Final

    When positions are full at market open, good signals are queued.
    When a slot opens, queued signals are checked and executed if price is still good.

    Priority: Freshness (< 30 min) > Score
    """
    symbol: str
    signal_price: float         # Price when signal was generated
    score: float                # Signal score
    stop_loss: float            # Original SL price
    take_profit: float          # Original TP price
    queued_at: datetime         # When added to queue
    reasons: List[str]          # Signal reasons
    atr_pct: float = 5.0        # ATR% for deviation calculation
    sl_pct: float = 0.0         # SL percentage from entry (for recalculation)
    tp_pct: float = 0.0         # TP percentage from entry (for recalculation)

    def get_max_deviation(self, atr_mult: float, min_dev: float, max_dev: float) -> float:
        """
        Calculate max acceptable deviation based on ATR

        Formula: min(max(ATR% * mult, min_dev), max_dev)
        Example: ATR 6% * 0.5 = 3% → capped to 1.5%
        """
        atr_based = self.atr_pct * atr_mult
        return min(max(atr_based, min_dev), max_dev)

    def is_price_acceptable(self, current_price: float, atr_mult: float, min_dev: float, max_dev: float) -> Tuple[bool, float, float]:
        """
        Check if current price is still acceptable for entry

        Returns:
            (acceptable: bool, deviation_pct: float, max_allowed: float)
        """
        deviation_pct = ((current_price - self.signal_price) / self.signal_price) * 100
        max_allowed = self.get_max_deviation(atr_mult, min_dev, max_dev)
        acceptable = deviation_pct <= max_allowed
        return acceptable, deviation_pct, max_allowed

    def minutes_since_queued(self) -> float:
        """Get minutes since signal was queued"""
        return (datetime.now() - self.queued_at).total_seconds() / 60

    def is_fresh(self, freshness_window_minutes: float) -> bool:
        """Check if signal is still fresh (within window)"""
        return self.minutes_since_queued() <= freshness_window_minutes


class AutoTradingEngine:
    """
    Full-Auto Trading Engine for Rapid Trader v3.9

    Features:
    - Automatic signal detection and execution
    - Trailing stop management
    - Position monitoring every minute
    - Safety limits (max positions, daily loss limit)
    """

    # Trading parameters (v4.6 - ATR-based SL/TP)
    MAX_POSITIONS = 3           # v4.0: 2 → 3
    POSITION_SIZE_PCT = 30      # Fallback: fixed 30% (used when risk-parity disabled)
    # v4.9: Risk-parity position sizing
    RISK_PARITY_ENABLED = True
    RISK_BUDGET_PCT = 1.0       # Max risk per position = 1% of account
    MAX_POSITION_PCT = 40       # Cap: never exceed 40% in one position

    # v4.6: ATR-based SL/TP (replaces fixed SL/TP)
    SL_ATR_MULTIPLIER = 1.5     # SL = 1.5 × ATR%
    SL_MIN_PCT = 2.0            # Floor: at least 2% SL
    SL_MAX_PCT = 4.0            # Cap: max 4% SL
    TP_ATR_MULTIPLIER = 3.0     # TP = 3 × ATR%
    TP_MIN_PCT = 4.0            # Floor: at least 4% TP
    TP_MAX_PCT = 8.0            # Cap: max 8% TP
    TARGET_RR = 2.0             # v4.9: Target R:R ratio (TP = SL * TARGET_RR)
    # PDT TP = SL% (dynamic, R:R 1:1 minimum for Day 0)

    # Fallback fixed values (when ATR not available)
    STOP_LOSS_PCT = 2.5         # Fallback if no ATR data
    TAKE_PROFIT_PCT = 5.0       # Fallback if no ATR data
    PDT_TP_THRESHOLD = 4.0      # Fallback PDT TP (overridden per-position in v4.6)

    TRAIL_ACTIVATION_PCT = 3.0  # v4.0: 2 → 3 (match backtest)
    TRAIL_LOCK_PCT = 80         # v3.11: 70 → 80
    MAX_HOLD_DAYS = 5
    DAILY_LOSS_LIMIT_PCT = 5.0  # Stop trading if down 5% in a day
    MIN_SCORE = 95              # v4.7: 85 → 95 (score 95+ = WR ~55%, ลด grey zone)

    # Weekly Loss Limit (v4.7 NEW!)
    # หยุดเทรดถ้าขาดทุนสะสม -5% ในสัปดาห์ ป้องกัน sector rotation / prolonged downturn
    WEEKLY_LOSS_LIMIT_PCT = 5.0     # % - หยุดซื้อใหม่ถ้าขาดทุน -5%/สัปดาห์

    # Consecutive Loss Stop (v4.7 NEW!)
    # แพ้ติดกัน 3 ครั้ง → หยุด 1 วัน (strategy อาจไม่เข้ากับ market condition)
    MAX_CONSECUTIVE_LOSSES = 3

    # Signal Queue (v4.1 Final)
    # When positions full → queue signals → execute when slot opens (if price still good)
    # Priority: Freshness (< 30 min) > Score
    # R:R analysis: +1.5% deviation → R:R ~1:1 (acceptable limit)
    QUEUE_ENABLED = True
    QUEUE_ATR_MULT = 0.5              # ATR multiplier for deviation
    QUEUE_MIN_DEVIATION = 0.5         # % - minimum deviation allowed
    QUEUE_MAX_DEVIATION = 1.5         # % - cap at R:R ~1:1
    QUEUE_MAX_SIZE = 3                # Max signals in queue (= MAX_POSITIONS)

    # Sector Diversification (v4.7 NEW!)
    # ป้องกันถือหุ้น sector เดียวกันเยอะเกิน (correlated risk)
    # เช่น AMD + NVDA + INTC = 3 ตัว Tech → ลงพร้อมกัน
    SECTOR_FILTER_ENABLED = True
    MAX_PER_SECTOR = 2              # ไม่เกิน 2 ตัว/sector

    # Consecutive Sector Loss (v4.7 NEW!)
    # sector แพ้ติดกัน → cooldown sector นั้น
    # ป้องกัน dip-buying falling knife ซ้ำๆ ใน sector ที่กำลัง rotate out
    SECTOR_LOSS_TRACKING_ENABLED = True
    MAX_SECTOR_CONSECUTIVE_LOSS = 2     # แพ้ 2 ครั้งติดใน sector → cooldown
    SECTOR_COOLDOWN_DAYS = 2            # หยุดซื้อ sector นั้น 2 วัน
    QUEUE_FRESHNESS_WINDOW = 30       # Minutes - fresh signals get priority
    QUEUE_RESCAN_ON_EMPTY = True      # Rescan if queue empty/expired

    # Smart Order Execution - Strategy 4 (v4.8 NEW!)
    # Limit @ Ask + Market Fallback → ลด slippage ~0.1-0.2%
    SMART_ORDER_ENABLED = True
    SMART_ORDER_MAX_SPREAD_PCT = 0.5   # Skip ถ้า spread > 0.5%
    SMART_ORDER_WAIT_SECONDS = 30      # รอ limit fill 30 วินาที

    # Gap Filter (v4.3 NEW!)
    # ไม่ซื้อหุ้นที่ gap up/down แรงเกินไป
    # เหตุผล: Gap up แรง = ไม่ใช่ dip bounce แล้ว
    # AMD case: gap +3.6% > +2% → SKIP
    GAP_FILTER_ENABLED = True
    GAP_MAX_UP = 2.0        # % - ไม่ซื้อหุ้น gap up เกิน (default 2%)
    GAP_MAX_DOWN = -5.0     # % - ไม่ซื้อหุ้น gap down แรงเกิน (อาจมีปัญหา)

    # Earnings Filter (v4.4 NEW!)
    # ไม่ซื้อหุ้นที่มี earnings ใกล้ๆ (เสี่ยง gap ±10-20%)
    EARNINGS_FILTER_ENABLED = True
    EARNINGS_SKIP_DAYS_BEFORE = 5   # Skip ถ้า earnings ภายใน 5 วัน
    EARNINGS_SKIP_DAYS_AFTER = 0    # ไม่ skip หลัง earnings (อาจมี momentum)

    # Low Risk Mode (v4.5 NEW!)
    # เมื่อ PDT budget = 0: ยังซื้อได้ แต่เข้มขึ้น + size เล็กลง
    # เหตุผล: ต้อง hold ข้ามคืนอยู่แล้ว → เลือกเฉพาะหุ้นปลอดภัยสุด
    LOW_RISK_MODE_ENABLED = True
    LOW_RISK_GAP_MAX_UP = 1.0       # % - เข้มขึ้น (ปกติ 2%)
    LOW_RISK_MIN_SCORE = 98         # v4.7: เข้มขึ้น (ปกติ 95) แต่ไม่ถึง 100 ให้ยังเทรดได้บ้าง
    LOW_RISK_POSITION_SIZE_PCT = 20 # % - เล็กลง (ปกติ 30%) = ~$800
    LOW_RISK_MAX_ATR_PCT = 4.0      # % - หุ้นไม่ผันผวนมาก
    EARNINGS_NO_DATA_ACTION = 'warn'  # 'allow', 'skip', 'warn'

    # Late Start Protection (v4.4 NEW!)
    # ถ้าเริ่มหลัง market open ไปนาน → skip scan (ราคาอาจขึ้นไปแล้ว)
    LATE_START_PROTECTION = True
    MARKET_OPEN_SCAN_DELAY = 5      # รอ 5 นาทีหลังตลาดเปิดก่อน scan (09:35 ET)
    MARKET_OPEN_SCAN_WINDOW = 20    # นาที - ถ้าเริ่มหลัง 09:50 ET → skip scan

    # Afternoon Scan (v4.9.1 — replaces Mid-day 11:00)
    # 14:00 ET = หลัง lunch dip, ราคา settle แล้ว, pattern ชัดกว่า
    # ใช้เกณฑ์เข้มกว่า morning scan เพราะเวลาเหลือน้อย (2 ชม.)
    AFTERNOON_SCAN_ENABLED = True
    AFTERNOON_SCAN_HOUR = 14        # 14:00 ET
    AFTERNOON_SCAN_MINUTE = 0
    AFTERNOON_MIN_SCORE = 96        # เข้มกว่าเช้า (95)
    AFTERNOON_GAP_MAX_UP = 1.5      # เข้มกว่าเช้า (2.0)
    AFTERNOON_GAP_MAX_DOWN = -3.0   # เข้มกว่าเช้า (-5.0)

    # Earnings Auto-Sell (v4.9 NEW!)
    # ถ้าถือหุ้นที่มี earnings วันนี้/พรุ่งนี้ → ขายก่อน close อัตโนมัติ
    EARNINGS_AUTO_SELL = True
    EARNINGS_AUTO_SELL_BUFFER_MIN = 30  # ขายอย่างน้อย 30 นาทีก่อนปิด

    # Market Regime Filter (v4.0 NEW!)
    # Rule: SPY > SMA20 = Bull → Trade, SPY < SMA20 = Bear → Skip
    REGIME_FILTER_ENABLED = True
    REGIME_SMA_PERIOD = 20
    # v4.9: Enhanced regime checks
    REGIME_RSI_MIN = 40          # SPY RSI > 40 required
    REGIME_RETURN_5D_MIN = -2.0  # SPY 5-day return > -2%
    REGIME_VIX_MAX = 30.0        # VIX < 30 required
    # Backtest results: This single filter achieves target!
    # - WR: 48% → 49%
    # - DD: 12.6% → 8.9% ✅
    # - Return: +5.5%/mo ✅

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
    MONITOR_INTERVAL_SECONDS = 15  # Check every 15 seconds (was 60)

    # v4.7 Fix #13: Circuit breaker
    CIRCUIT_BREAKER_MAX_ERRORS = 5

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

        # PDT Smart Guard v2.2 (No Override Mode)
        self.pdt_guard = init_pdt_guard(
            trader=self.trader,
            config=PDTConfig(
                max_day_trades=3,
                sl_threshold=-self.STOP_LOSS_PCT,  # -2.5%
                tp_threshold=self.PDT_TP_THRESHOLD,  # v4.4: +4.0% (เกิดบ่อยกว่า +6%)
                reserve=1  # Keep 1 day trade for SL emergencies
                # v2.2: ไม่มี critical_threshold → ไม่ override PDT เด็ดขาด
            )
        )
        logger.info("PDT Smart Guard v2.2 initialized (No Override - ไม่มีทางโดน PDT flag)")

        # Trade Logger v1.0
        self.trade_logger = get_trade_logger()
        logger.info("Trade Logger v1.0 initialized")

        # Alert Manager v1.0
        from alert_manager import get_alert_manager
        self.alerts = get_alert_manager()
        logger.info("Alert Manager v1.0 initialized")

        # v4.9: Load config from YAML (overrides class constants)
        try:
            from trading_config import apply_config
            apply_config(self)
        except Exception as e:
            logger.warning(f"Config load skipped: {e}")

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
        self._positions_lock = threading.RLock()  # v4.9: Reentrant lock for positions dict
        self._close_locks: Dict[str, threading.Lock] = {}  # v4.9: Per-symbol close mutex
        self._close_locks_lock = threading.Lock()  # Protects _close_locks dict
        self._close_all_lock = threading.Lock()  # Prevent concurrent close-all
        self.daily_stats = DailyStats(date=datetime.now().strftime('%Y-%m-%d'))
        self.running = False
        self.monitor_thread = None

        # v4.7: Loss protection tracking (thread-safe via _stats_lock)
        self._stats_lock = threading.Lock()
        self.consecutive_losses = 0         # นับแพ้ติดกัน (reset เมื่อชนะ)
        self.cooldown_until = None          # หยุดเทรดถึงวันที่นี้
        self.weekly_realized_pnl = 0.0      # P&L สะสมในสัปดาห์ (reset ทุกจันทร์)
        self.weekly_reset_date = None       # วันที่ reset ล่าสุด

        # v4.7: Sector loss tracking {sector: {losses: int, cooldown_until: date}}
        self.sector_loss_tracker: Dict[str, Dict] = {}

        # Signal Queue (v4.1)
        self.signal_queue: List[QueuedSignal] = []

        # Regime cache (v4.2) - avoid repeated yfinance calls
        self._regime_cache: Optional[Tuple[bool, str, datetime]] = None
        self._regime_cache_seconds = 300  # 5 minutes

        # Timezone
        self.et_tz = pytz.timezone('US/Eastern')

        # Position state file (persists peak_price, trailing_active, SL/TP etc.)
        self._state_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        os.makedirs(self._state_dir, exist_ok=True)
        self._state_file = os.path.join(self._state_dir, 'active_positions.json')
        self._queue_file = os.path.join(self._state_dir, 'signal_queue.json')

        # Load existing positions from Alpaca + persisted state
        self._sync_positions()

        # Load persisted signal queue
        self._load_queue_state()

        # Load persisted loss counters
        self._load_loss_counters()

        logger.info(f"AutoTradingEngine initialized (paper={paper})")

        if auto_start:
            self.start()

    # =========================================================================
    # POSITION STATE PERSISTENCE
    # =========================================================================

    def _save_positions_state(self):
        """
        Persist all ManagedPosition state to JSON file (atomic write).

        Saves: peak_price, trough_price, trailing_active, sl_pct, tp_pct,
        atr_pct, current_sl_price, tp_price, entry_time, sector — all fields
        that would be lost on crash/restart.

        NOTE: Caller must hold _positions_lock OR this method takes a snapshot under lock.
        """
        try:
            # Snapshot positions under lock (safe against concurrent modification)
            with self._positions_lock:
                positions_snapshot = dict(self.positions)

            state = {}
            for symbol, pos in positions_snapshot.items():
                state[symbol] = {
                    'symbol': pos.symbol,
                    'qty': pos.qty,
                    'entry_price': pos.entry_price,
                    'entry_time': pos.entry_time.isoformat(),
                    'sl_order_id': pos.sl_order_id,
                    'current_sl_price': pos.current_sl_price,
                    'peak_price': pos.peak_price,
                    'trailing_active': pos.trailing_active,
                    'days_held': pos.days_held,
                    'sl_pct': pos.sl_pct,
                    'tp_price': pos.tp_price,
                    'tp_pct': pos.tp_pct,
                    'atr_pct': pos.atr_pct,
                    'sector': pos.sector,
                    'trough_price': pos.trough_price,
                }

            data = {
                'saved_at': datetime.now().isoformat(),
                'count': len(state),
                'positions': state,
            }

            # Atomic write: temp file + rename
            fd, tmp_path = tempfile.mkstemp(dir=self._state_dir, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                os.replace(tmp_path, self._state_file)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            logger.debug(f"Position state saved: {len(state)} positions")

        except Exception as e:
            logger.error(f"Failed to save position state: {e}")

    def _load_positions_state(self) -> Dict[str, dict]:
        """
        Load persisted position state from JSON file.

        Returns:
            Dict mapping symbol → position state dict
        """
        try:
            if not os.path.exists(self._state_file):
                return {}

            with open(self._state_file, 'r') as f:
                data = json.load(f)

            positions = data.get('positions', {})
            saved_at = data.get('saved_at', 'unknown')
            logger.info(f"Loaded persisted state: {len(positions)} positions (saved at {saved_at})")
            return positions

        except Exception as e:
            logger.error(f"Failed to load position state: {e}")
            return {}

    # =========================================================================
    # QUEUE STATE PERSISTENCE
    # =========================================================================

    def _save_queue_state(self):
        """Persist signal queue to JSON file (atomic write)."""
        try:
            entries = []
            for q in self.signal_queue:
                entries.append({
                    'symbol': q.symbol,
                    'signal_price': q.signal_price,
                    'score': q.score,
                    'stop_loss': q.stop_loss,
                    'take_profit': q.take_profit,
                    'queued_at': q.queued_at.isoformat(),
                    'reasons': q.reasons,
                    'atr_pct': q.atr_pct,
                    'sl_pct': q.sl_pct,
                    'tp_pct': q.tp_pct,
                })

            data = {
                'saved_at': datetime.now().isoformat(),
                'count': len(entries),
                'queue': entries,
            }

            fd, tmp_path = tempfile.mkstemp(dir=self._state_dir, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                os.replace(tmp_path, self._queue_file)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            logger.debug(f"Queue state saved: {len(entries)} signals")

        except Exception as e:
            logger.error(f"Failed to save queue state: {e}")

    def _load_queue_state(self):
        """Load persisted signal queue from JSON file on startup."""
        try:
            if not os.path.exists(self._queue_file):
                return

            with open(self._queue_file, 'r') as f:
                data = json.load(f)

            entries = data.get('queue', [])
            loaded = 0
            for entry in entries:
                try:
                    queued = QueuedSignal(
                        symbol=entry['symbol'],
                        signal_price=entry['signal_price'],
                        score=entry['score'],
                        stop_loss=entry['stop_loss'],
                        take_profit=entry['take_profit'],
                        queued_at=datetime.fromisoformat(entry['queued_at']),
                        reasons=entry.get('reasons', []),
                        atr_pct=entry.get('atr_pct', 5.0),
                        sl_pct=entry.get('sl_pct', 0.0),
                        tp_pct=entry.get('tp_pct', 0.0),
                    )
                    # Skip if already holding this symbol
                    if queued.symbol not in self.positions:
                        self.signal_queue.append(queued)
                        loaded += 1
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping invalid queue entry: {e}")

            if loaded:
                logger.info(f"Loaded persisted queue: {loaded} signals (saved at {data.get('saved_at', 'unknown')})")

        except Exception as e:
            logger.error(f"Failed to load queue state: {e}")

    # =========================================================================
    # POSITION SYNC
    # =========================================================================

    def _sync_positions(self):
        """
        Sync positions from Alpaca + merge persisted state.

        Alpaca = source of truth for: symbol exists, qty, current_price
        Persisted state = source of truth for: peak_price, trough_price,
        trailing_active, sl_pct, tp_pct, atr_pct, entry_time, sector
        """
        try:
            alpaca_positions = self.trader.get_positions()
            alpaca_orders = self.trader.get_orders(status='open')

            # Load persisted state (peak_price, trailing_active, etc.)
            persisted = self._load_positions_state()

            # Try to load entry dates from rapid_portfolio.json
            portfolio_entry_dates = {}
            try:
                portfolio_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rapid_portfolio.json")
                if os.path.exists(portfolio_file):
                    with open(portfolio_file, 'r') as f:
                        portfolio_data = json.load(f)
                    for symbol, pos_data in portfolio_data.get('positions', {}).items():
                        if 'entry_date' in pos_data:
                            portfolio_entry_dates[symbol] = datetime.strptime(pos_data['entry_date'], '%Y-%m-%d').date()
            except Exception as e:
                logger.warning(f"Could not load portfolio entry dates: {e}")

            for pos in alpaca_positions:
                # Find SL order for this position
                sl_order = None
                for order in alpaca_orders:
                    if order.symbol == pos.symbol and order.type == 'stop':
                        sl_order = order
                        break

                # Get entry date from portfolio file or use today
                entry_date = portfolio_entry_dates.get(pos.symbol, datetime.now().date())
                entry_time = datetime.combine(entry_date, datetime.min.time())

                if pos.symbol not in self.positions:
                    saved = persisted.get(pos.symbol, {})

                    # Restore entry_time from persisted state if available
                    if saved.get('entry_time'):
                        try:
                            entry_time = datetime.fromisoformat(saved['entry_time'])
                        except (ValueError, TypeError):
                            pass  # Fall back to portfolio_entry_dates

                    self.positions[pos.symbol] = ManagedPosition(
                        symbol=pos.symbol,
                        qty=int(pos.qty),
                        entry_price=pos.avg_entry_price,
                        entry_time=entry_time,
                        sl_order_id=sl_order.id if sl_order else saved.get('sl_order_id', ''),
                        current_sl_price=sl_order.stop_price if sl_order else saved.get('current_sl_price', pos.avg_entry_price * 0.975),
                        # Restore dynamic state from persisted data
                        peak_price=saved.get('peak_price', pos.current_price),
                        trailing_active=saved.get('trailing_active', False),
                        sl_pct=saved.get('sl_pct', self.STOP_LOSS_PCT),
                        tp_price=saved.get('tp_price', 0.0),
                        tp_pct=saved.get('tp_pct', self.TAKE_PROFIT_PCT),
                        atr_pct=saved.get('atr_pct', 0.0),
                        sector=saved.get('sector', ''),
                        trough_price=saved.get('trough_price', 0.0),
                    )

                    if saved:
                        logger.info(f"Restored position: {pos.symbol} (peak=${saved.get('peak_price', 0):.2f}, trail={'ON' if saved.get('trailing_active') else 'OFF'})")
                    else:
                        logger.info(f"Synced position: {pos.symbol} (no persisted state)")

                # PDT Guard: Record entry date
                self.pdt_guard.record_entry(pos.symbol, entry_date)

            # Clean up persisted state for positions no longer at Alpaca
            alpaca_symbols = {pos.symbol for pos in alpaca_positions}
            stale = [s for s in persisted if s not in alpaca_symbols]
            if stale:
                logger.info(f"Stale persisted positions removed: {', '.join(stale)}")

            logger.info(f"Synced {len(self.positions)} positions")
            self.pdt_guard.log_status()

            # Save clean state
            if self.positions:
                self._save_positions_state()

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
    # MARKET REGIME FILTER (v4.0 NEW!)
    # =========================================================================

    def _get_spy_data_from_alpaca(self, days: int = 60) -> Optional[pd.DataFrame]:
        """
        v4.7 Fix #8: Get SPY historical data from Alpaca bars API.
        Returns a DataFrame with 'Close' column, or None on failure.
        """
        try:
            from datetime import timezone
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=days + 5)  # Extra buffer for weekends

            bars = self.trader.api.get_bars(
                'SPY',
                '1Day',
                start=start.strftime('%Y-%m-%d'),
                end=end.strftime('%Y-%m-%d'),
                limit=days + 5
            )
            if not bars:
                return None

            data = []
            for bar in bars:
                data.append({
                    'Close': bar.c,
                    'High': bar.h,
                    'Low': bar.l,
                    'Open': bar.o,
                    'Volume': bar.v,
                })
            df = pd.DataFrame(data)
            if len(df) >= 20:
                logger.debug(f"SPY data from Alpaca: {len(df)} bars")
                return df
            return None
        except Exception as e:
            logger.debug(f"Alpaca SPY data failed: {e}")
            return None

    def _check_market_regime(self, force_refresh: bool = False) -> Tuple[bool, str]:
        """
        Check if market is in Bull regime (OK to trade)

        v4.9 Enhanced Regime Filter — must pass ALL:
          1. SPY > SMA20 (trend)
          2. SPY RSI(14) > 40 (momentum not oversold crash)
          3. SPY Return 5d > -2% (no recent crash)
          4. VIX < 30 (fear gauge)

        Returns:
            (is_bull, reason)
        """
        if not self.REGIME_FILTER_ENABLED:
            return True, "Regime filter disabled"

        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance not available — blocking trades (fail-closed)")
            return False, "yfinance not available — data unavailable"

        # v4.2: Use cache to avoid repeated yfinance calls
        if not force_refresh and self._regime_cache:
            is_bull, reason, cached_at = self._regime_cache
            age_seconds = (datetime.now() - cached_at).total_seconds()
            if age_seconds < self._regime_cache_seconds:
                return is_bull, reason

        try:
            # v4.7 Fix #8: Try Alpaca bars first, fall back to yfinance
            spy = self._get_spy_data_from_alpaca(60)
            if spy is None or spy.empty:
                spy = yf.download('SPY', period='60d', progress=False)

            if spy.empty or len(spy) < self.REGIME_SMA_PERIOD:
                logger.warning("Not enough SPY data for regime check — blocking trades (fail-closed)")
                return False, "Insufficient SPY data — data unavailable"

            # Get close prices (handle multi-index from yfinance)
            close = spy['Close']
            if hasattr(close, 'iloc'):
                current_price = float(close.iloc[-1])
                sma = float(close.iloc[-self.REGIME_SMA_PERIOD:].mean())
            else:
                current_price = float(close[-1])
                sma = float(close[-self.REGIME_SMA_PERIOD:].mean())

            # --- Check 1: SPY > SMA20 ---
            pct_above = ((current_price / sma) - 1) * 100
            sma_ok = current_price > sma

            # --- Check 2: RSI(14) > 40 ---
            rsi_val = self._calc_rsi(close, period=14)

            # --- Check 3: Return 5d > -2% ---
            if len(close) >= 6:
                price_5d_ago = float(close.iloc[-6]) if hasattr(close, 'iloc') else float(close[-6])
                return_5d = ((current_price / price_5d_ago) - 1) * 100
            else:
                return_5d = 0.0

            # --- Check 4: VIX < 30 ---
            vix_val = self._get_vix()

            # Evaluate
            rsi_ok = rsi_val > self.REGIME_RSI_MIN
            ret5d_ok = return_5d > self.REGIME_RETURN_5D_MIN
            vix_ok = vix_val < self.REGIME_VIX_MAX

            is_bull = sma_ok and rsi_ok and ret5d_ok and vix_ok

            # Build detailed reason
            checks = []
            checks.append(f"SMA{self.REGIME_SMA_PERIOD}={'OK' if sma_ok else 'FAIL'}({pct_above:+.1f}%)")
            checks.append(f"RSI={'OK' if rsi_ok else 'FAIL'}({rsi_val:.0f})")
            checks.append(f"Ret5d={'OK' if ret5d_ok else 'FAIL'}({return_5d:+.1f}%)")
            checks.append(f"VIX={'OK' if vix_ok else 'FAIL'}({vix_val:.1f})")
            check_str = " | ".join(checks)

            if is_bull:
                reason = f"BULL: {check_str}"
                logger.info(f"✅ Market Regime: {reason}")
            else:
                failed = []
                if not sma_ok:
                    failed.append(f"SPY < SMA{self.REGIME_SMA_PERIOD}")
                if not rsi_ok:
                    failed.append(f"RSI {rsi_val:.0f} < {self.REGIME_RSI_MIN}")
                if not ret5d_ok:
                    failed.append(f"Ret5d {return_5d:+.1f}% < {self.REGIME_RETURN_5D_MIN}%")
                if not vix_ok:
                    failed.append(f"VIX {vix_val:.1f} > {self.REGIME_VIX_MAX}")
                reason = f"BEAR: {', '.join(failed)} [{check_str}]"
                logger.warning(f"⚠️ Market Regime: {reason} - SKIPPING NEW TRADES")

            # v4.2: Cache result
            self._regime_cache = (is_bull, reason, datetime.now())
            return is_bull, reason

        except Exception as e:
            logger.error(f"Regime check failed: {e} — blocking trades (fail-closed)")
            return False, f"Data unavailable: {e}"

    @staticmethod
    def _calc_rsi(close_series, period: int = 14) -> float:
        """Calculate RSI from a pandas Series of close prices."""
        try:
            if hasattr(close_series, 'iloc'):
                deltas = close_series.diff()
            else:
                deltas = pd.Series(close_series).diff()

            gains = deltas.clip(lower=0)
            losses = (-deltas).clip(lower=0)

            avg_gain = gains.rolling(window=period, min_periods=period).mean().iloc[-1]
            avg_loss = losses.rolling(window=period, min_periods=period).mean().iloc[-1]

            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))
        except Exception:
            return 50.0  # default neutral

    def _get_vix(self) -> float:
        """Fetch current VIX value. Returns 20.0 on error (neutral)."""
        try:
            vix = yf.download('^VIX', period='5d', progress=False)
            if vix.empty:
                return 20.0
            close = vix['Close']
            return float(close.iloc[-1]) if hasattr(close, 'iloc') else float(close[-1])
        except Exception:
            return 20.0

    # =========================================================================
    # LOW RISK MODE (v4.5 NEW!)
    # =========================================================================

    def _is_low_risk_mode(self) -> Tuple[bool, str]:
        """
        Check if we should use Low Risk Mode

        Low Risk Mode activates when PDT budget = 0
        ซื้อได้ แต่เข้มขึ้น + size เล็กลง

        Returns:
            (is_low_risk, reason)
        """
        if not self.LOW_RISK_MODE_ENABLED:
            return False, "Low risk mode disabled"

        pdt_status = self.pdt_guard.get_pdt_status()

        if pdt_status.remaining <= 0:
            return True, f"PDT budget = 0 → Low Risk Mode"

        if pdt_status.remaining <= self.pdt_guard.config.reserve:
            return True, f"PDT budget = {pdt_status.remaining} (≤ reserve {self.pdt_guard.config.reserve}) → Low Risk Mode"

        return False, f"PDT budget OK ({pdt_status.remaining}/{self.pdt_guard.config.max_day_trades})"

    def _get_effective_params(self) -> Dict:
        """
        Get effective trading parameters based on mode

        Returns parameters adjusted for normal or low-risk mode
        """
        is_low_risk, reason = self._is_low_risk_mode()

        if is_low_risk:
            logger.info(f"⚠️ LOW RISK MODE: {reason}")
            return {
                'gap_max_up': self.LOW_RISK_GAP_MAX_UP,
                'min_score': self.LOW_RISK_MIN_SCORE,
                'position_size_pct': self.LOW_RISK_POSITION_SIZE_PCT,
                'max_atr_pct': self.LOW_RISK_MAX_ATR_PCT,
                'mode': 'LOW_RISK'
            }
        else:
            return {
                'gap_max_up': self.GAP_MAX_UP,
                'min_score': self.MIN_SCORE,
                'position_size_pct': self.POSITION_SIZE_PCT,
                'max_atr_pct': None,  # No ATR limit in normal mode
                'mode': 'NORMAL'
            }

    # =========================================================================
    # GAP FILTER (v4.3 NEW!)
    # =========================================================================

    def _check_gap_filter(self, symbol: str, current_price: float, max_up_override: float = None) -> Tuple[bool, float, str]:
        """
        Check if stock has gapped too much from previous close

        Gap up แรง = ไม่ใช่ dip bounce แล้ว → SKIP
        Gap down แรง = อาจมีปัญหา (bad news) → SKIP

        Args:
            max_up_override: Override GAP_MAX_UP (for low-risk mode)

        Returns:
            (is_acceptable, gap_pct, reason)
        """
        if not self.GAP_FILTER_ENABLED:
            return True, 0.0, "Gap filter disabled"

        # v4.5: Use override if provided (low-risk mode)
        gap_max_up = max_up_override if max_up_override is not None else self.GAP_MAX_UP

        try:
            # Get previous close (yesterday's close)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='5d')  # Get 5 days to be safe

            if hist.empty or len(hist) < 1:
                logger.warning(f"{symbol}: Not enough data for gap check — blocking (fail-closed)")
                return False, 0.0, "Data unavailable — insufficient data"

            # iloc[-1] = most recent close (yesterday if during market hours)
            prev_close = float(hist['Close'].iloc[-1])
            gap_pct = ((current_price - prev_close) / prev_close) * 100

            # Check gap limits
            if gap_pct > gap_max_up:
                reason = f"GAP UP TOO HIGH: {gap_pct:+.1f}% > {gap_max_up:+.1f}% (prev close ${prev_close:.2f})"
                logger.warning(f"❌ {symbol}: {reason}")
                return False, gap_pct, reason

            if gap_pct < self.GAP_MAX_DOWN:
                reason = f"GAP DOWN TOO HIGH: {gap_pct:+.1f}% < {self.GAP_MAX_DOWN:+.1f}% (prev close ${prev_close:.2f})"
                logger.warning(f"❌ {symbol}: {reason}")
                return False, gap_pct, reason

            reason = f"Gap OK: {gap_pct:+.1f}% (prev close ${prev_close:.2f})"
            logger.info(f"✅ {symbol}: {reason}")
            return True, gap_pct, reason

        except Exception as e:
            logger.error(f"{symbol}: Gap check failed: {e} — blocking (fail-closed)")
            return False, 0.0, f"Data unavailable: {e}"

    # =========================================================================
    # EARNINGS FILTER (v4.4 NEW!)
    # =========================================================================

    def _check_earnings_filter(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if stock has earnings announcement coming soon

        ไม่ซื้อหุ้นที่มี earnings ใกล้ๆ เพราะเสี่ยง gap ±10-20%

        Returns:
            (is_acceptable, reason)
        """
        if not self.EARNINGS_FILTER_ENABLED:
            return True, "Earnings filter disabled"

        try:
            ticker = yf.Ticker(symbol)
            now = datetime.now()

            # Method 1: calendar (returns dict in newer yfinance)
            try:
                calendar = ticker.calendar
                if calendar is not None:
                    # Handle dict format (newer yfinance)
                    if isinstance(calendar, dict):
                        earnings_date = calendar.get('Earnings Date')
                        if earnings_date:
                            # Could be list of dates
                            if isinstance(earnings_date, list) and len(earnings_date) > 0:
                                earnings_date = earnings_date[0]
                            if earnings_date:
                                # Convert to date object
                                from datetime import date as date_type
                                if isinstance(earnings_date, str):
                                    earnings_date = pd.to_datetime(earnings_date).date()
                                elif isinstance(earnings_date, datetime):
                                    earnings_date = earnings_date.date()
                                elif not isinstance(earnings_date, date_type):
                                    # Try to convert
                                    earnings_date = pd.to_datetime(earnings_date).date()
                                # earnings_date is now a date object
                                days_until = (earnings_date - now.date()).days

                                if 0 <= days_until <= self.EARNINGS_SKIP_DAYS_BEFORE:
                                    reason = f"EARNINGS in {days_until} days ({earnings_date.strftime('%Y-%m-%d')})"
                                    logger.warning(f"❌ {symbol}: {reason}")
                                    return False, reason

                                if self.EARNINGS_SKIP_DAYS_AFTER > 0 and -self.EARNINGS_SKIP_DAYS_AFTER <= days_until < 0:
                                    reason = f"EARNINGS was {-days_until} days ago"
                                    logger.warning(f"❌ {symbol}: {reason}")
                                    return False, reason

                                return True, f"Earnings OK ({days_until} days away)"

                    # Handle DataFrame format (older yfinance)
                    elif hasattr(calendar, 'empty') and not calendar.empty:
                        if 'Earnings Date' in calendar.index:
                            earnings_date = calendar.loc['Earnings Date']
                            if hasattr(earnings_date, 'iloc'):
                                earnings_date = earnings_date.iloc[0]
                            if pd.notna(earnings_date):
                                if isinstance(earnings_date, str):
                                    earnings_date = pd.to_datetime(earnings_date)
                                days_until = (earnings_date.date() - now.date()).days

                                if 0 <= days_until <= self.EARNINGS_SKIP_DAYS_BEFORE:
                                    reason = f"EARNINGS in {days_until} days ({earnings_date.strftime('%Y-%m-%d')})"
                                    logger.warning(f"❌ {symbol}: {reason}")
                                    return False, reason

                                return True, f"Earnings OK ({days_until} days away)"
            except Exception as e:
                logger.debug(f"{symbol}: Calendar method failed: {e}")

            # Method 2: info (has earningsDate field)
            try:
                info = ticker.info
                if info:
                    # earningsTimestamp or earningsDate
                    earnings_ts = info.get('earningsTimestamp') or info.get('earningsTimestampStart')
                    if earnings_ts:
                        earnings_date = datetime.fromtimestamp(earnings_ts)
                        days_until = (earnings_date.date() - now.date()).days

                        if 0 <= days_until <= self.EARNINGS_SKIP_DAYS_BEFORE:
                            reason = f"EARNINGS in {days_until} days ({earnings_date.strftime('%Y-%m-%d')})"
                            logger.warning(f"❌ {symbol}: {reason}")
                            return False, reason

                        return True, f"Earnings OK ({days_until} days away)"
            except Exception as e:
                logger.debug(f"{symbol}: Info method failed: {e}")

            # No earnings data found
            if self.EARNINGS_NO_DATA_ACTION == 'skip':
                return False, "No earnings data - skipping (conservative)"
            elif self.EARNINGS_NO_DATA_ACTION == 'warn':
                logger.warning(f"⚠️ {symbol}: No earnings data available")
                return True, "No earnings data (warned)"
            else:  # 'allow'
                return True, "No earnings data (allowed)"

        except Exception as e:
            logger.error(f"{symbol}: Earnings check failed: {e} — blocking (fail-closed)")
            return False, f"Data unavailable: {e}"

    # =========================================================================
    # SECTOR DIVERSIFICATION (v4.7 NEW!)
    # =========================================================================

    def _check_sector_filter(self, sector: str) -> Tuple[bool, str]:
        """
        Check if adding this sector would exceed MAX_PER_SECTOR

        ป้องกันถือหุ้น sector เดียวกันเยอะเกิน (correlated risk)
        เช่น AMD + NVDA + INTC = 3 ตัว Tech → ลงพร้อมกัน
        """
        if not self.SECTOR_FILTER_ENABLED or not sector:
            return True, "Sector filter disabled or no sector data"

        # Count current positions in same sector
        same_sector_count = sum(
            1 for pos in self.positions.values()
            if pos.sector and pos.sector.lower() == sector.lower()
        )

        if same_sector_count >= self.MAX_PER_SECTOR:
            existing = [s for s, p in self.positions.items() if p.sector and p.sector.lower() == sector.lower()]
            return False, f"Already {same_sector_count} positions in {sector}: {existing} (max {self.MAX_PER_SECTOR})"

        return True, f"{sector}: {same_sector_count}/{self.MAX_PER_SECTOR} positions"

    def _check_sector_cooldown(self, sector: str) -> Tuple[bool, str]:
        """
        Check if sector is in cooldown from consecutive losses.
        Tech แพ้ 2 ครั้งติด → skip Tech 2 วัน
        """
        if not self.SECTOR_LOSS_TRACKING_ENABLED or not sector:
            return True, "Sector loss tracking disabled"

        sector_key = sector.lower()
        tracker = self.sector_loss_tracker.get(sector_key)
        if not tracker:
            return True, f"{sector}: no loss history"

        # Check cooldown
        if tracker.get('cooldown_until'):
            today = datetime.now(self.et_tz).date()
            if today <= tracker['cooldown_until']:
                return False, f"{sector} cooldown until {tracker['cooldown_until']} ({tracker['losses']} consecutive losses)"
            else:
                # Cooldown expired, reset
                self.sector_loss_tracker[sector_key] = {'losses': 0, 'cooldown_until': None}
                return True, f"{sector}: cooldown ended"

        return True, f"{sector}: {tracker.get('losses', 0)}/{self.MAX_SECTOR_CONSECUTIVE_LOSS} losses"

    def _record_sector_trade_result(self, sector: str, pnl_pct: float):
        """Record trade result per sector for consecutive loss tracking. Thread-safe."""
        if not self.SECTOR_LOSS_TRACKING_ENABLED or not sector:
            return

        with self._stats_lock:
            sector_key = sector.lower()
            if sector_key not in self.sector_loss_tracker:
                self.sector_loss_tracker[sector_key] = {'losses': 0, 'cooldown_until': None}

            tracker = self.sector_loss_tracker[sector_key]

            if pnl_pct > 0:
                tracker['losses'] = 0  # Reset on win
            else:
                tracker['losses'] += 1
                logger.info(f"📉 {sector} consecutive losses: {tracker['losses']}/{self.MAX_SECTOR_CONSECUTIVE_LOSS}")

                if tracker['losses'] >= self.MAX_SECTOR_CONSECUTIVE_LOSS:
                    tracker['cooldown_until'] = datetime.now(self.et_tz).date() + timedelta(days=self.SECTOR_COOLDOWN_DAYS)
                    logger.warning(f"🧊 {sector} cooldown {self.SECTOR_COOLDOWN_DAYS} days → until {tracker['cooldown_until']}")

        self._save_loss_counters()

    # =========================================================================
    # LOSS COUNTER PERSISTENCE (v4.9 NEW!)
    # =========================================================================

    def _save_loss_counters(self):
        """Persist loss tracking counters (atomic write)"""
        try:
            state = {
                'consecutive_losses': self.consecutive_losses,
                'weekly_realized_pnl': self.weekly_realized_pnl,
                'cooldown_until': self.cooldown_until.isoformat() if self.cooldown_until else None,
                'weekly_reset_date': self.weekly_reset_date.isoformat() if self.weekly_reset_date else None,
                'sector_loss_tracker': {
                    k: {'losses': v['losses'], 'cooldown_until': v['cooldown_until'].isoformat() if v.get('cooldown_until') else None}
                    for k, v in self.sector_loss_tracker.items()
                },
                'saved_at': datetime.now().isoformat(),
            }
            loss_file = os.path.join(self._state_dir, 'loss_counters.json')
            fd, tmp_path = tempfile.mkstemp(dir=self._state_dir, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(state, f, indent=2)
                os.replace(tmp_path, loss_file)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.error(f"Failed to save loss counters: {e}")

    def _load_loss_counters(self):
        """Load persisted loss tracking counters"""
        try:
            loss_file = os.path.join(self._state_dir, 'loss_counters.json')
            if not os.path.exists(loss_file):
                return
            with open(loss_file, 'r') as f:
                state = json.load(f)
            self.consecutive_losses = state.get('consecutive_losses', 0)
            self.weekly_realized_pnl = state.get('weekly_realized_pnl', 0.0)
            if state.get('cooldown_until'):
                from datetime import date as date_type
                self.cooldown_until = date_type.fromisoformat(state['cooldown_until'])
            if state.get('weekly_reset_date'):
                from datetime import date as date_type
                self.weekly_reset_date = date_type.fromisoformat(state['weekly_reset_date'])
            # Restore sector loss tracker
            for k, v in state.get('sector_loss_tracker', {}).items():
                from datetime import date as date_type
                self.sector_loss_tracker[k] = {
                    'losses': v['losses'],
                    'cooldown_until': date_type.fromisoformat(v['cooldown_until']) if v.get('cooldown_until') else None
                }
            logger.info(f"Loaded loss counters: consecutive={self.consecutive_losses}, weekly_pnl=${self.weekly_realized_pnl:.2f}")
        except Exception as e:
            logger.error(f"Failed to load loss counters: {e}")

    # =========================================================================
    # LATE START PROTECTION (v4.4 NEW!)
    # =========================================================================

    def _is_late_start(self) -> Tuple[bool, str]:
        """
        Check if we started too late after market open

        ถ้าเริ่มหลัง 09:30 + MARKET_OPEN_SCAN_WINDOW → skip scan

        Returns:
            (is_late, reason)
        """
        if not self.LATE_START_PROTECTION:
            return False, "Late start protection disabled"

        now = self._get_et_time()
        market_open = now.replace(
            hour=self.MARKET_OPEN_HOUR,
            minute=self.MARKET_OPEN_MINUTE,
            second=0,
            microsecond=0
        )
        cutoff = market_open + timedelta(minutes=self.MARKET_OPEN_SCAN_WINDOW)

        if now > cutoff:
            minutes_late = (now - market_open).total_seconds() / 60
            reason = f"Late start: {minutes_late:.0f} min after open (cutoff: {self.MARKET_OPEN_SCAN_WINDOW} min)"
            logger.warning(f"⚠️ {reason}")
            return True, reason

        return False, f"On time ({(now - market_open).total_seconds() / 60:.0f} min after open)"

    # =========================================================================
    # ATR-BASED SL/TP CALCULATION (v4.6)
    # =========================================================================

    def _calculate_atr_sl_tp(self, symbol: str, entry_price: float, signal_atr_pct: float = None) -> Dict:
        """
        Calculate ATR-based SL/TP for a position (v4.6)

        SL = 1.5 × ATR%, clamped [2%, 4%]
        TP = 3 × ATR%, clamped [4%, 8%]
        PDT TP = SL% (R:R 1:1 minimum for Day 0)

        Returns:
            Dict with sl_pct, tp_pct, sl_price, tp_price, pdt_tp_pct, atr_pct
        """
        # Get ATR% - prefer signal's ATR, fallback to yfinance
        atr_pct = signal_atr_pct
        if atr_pct is None or atr_pct <= 0:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="1mo")
                if len(hist) >= 14:
                    high = hist['High']
                    low = hist['Low']
                    close = hist['Close']
                    tr = pd.concat([
                        high - low,
                        abs(high - close.shift(1)),
                        abs(low - close.shift(1))
                    ], axis=1).max(axis=1)
                    atr = tr.rolling(14).mean().iloc[-1]
                    atr_pct = (atr / close.iloc[-1]) * 100
            except Exception as e:
                logger.debug(f"ATR calculation error for {symbol}: {e}")

        # Fallback to fixed values if ATR not available
        if atr_pct is None or atr_pct <= 0:
            logger.warning(f"{symbol}: No ATR data, using fixed SL/TP")
            sl_pct = self.STOP_LOSS_PCT
            tp_pct = self.TAKE_PROFIT_PCT
        else:
            # Calculate SL and clamp
            sl_pct = self.SL_ATR_MULTIPLIER * atr_pct
            sl_pct = max(self.SL_MIN_PCT, min(sl_pct, self.SL_MAX_PCT))

            # v4.9: TP = SL * TARGET_RR (maintains R:R at all volatility levels)
            # Then clamp within [TP_MIN, TP_MAX]
            tp_pct = sl_pct * self.TARGET_RR
            tp_pct = max(self.TP_MIN_PCT, min(tp_pct, self.TP_MAX_PCT))

        # Round
        sl_pct = round(sl_pct, 2)
        tp_pct = round(tp_pct, 2)

        # Calculate prices
        sl_price = round(entry_price * (1 - sl_pct / 100), 2)
        tp_price = round(entry_price * (1 + tp_pct / 100), 2)

        # PDT TP = SL% (R:R 1:1 minimum for Day 0 sells)
        pdt_tp_pct = sl_pct

        logger.info(f"📊 {symbol} ATR-based SL/TP (ATR: {atr_pct:.1f}%)")
        logger.info(f"   SL: -{sl_pct}% (${sl_price:.2f})")
        logger.info(f"   TP: +{tp_pct}% (${tp_price:.2f})")
        logger.info(f"   PDT TP: +{pdt_tp_pct}% (Day 0 threshold)")
        logger.info(f"   R:R = 1:{tp_pct/sl_pct:.1f}")

        return {
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'pdt_tp_pct': pdt_tp_pct,
            'atr_pct': round(atr_pct, 2) if atr_pct else 0
        }

    # =========================================================================
    # ANALYSIS DATA (for logging - not for filtering)
    # =========================================================================

    def _get_analysis_data(self, symbol: str) -> Dict:
        """
        Get analysis data for logging purposes (future filter decisions)

        Returns dict with:
        - dist_from_52w_high: % below 52-week high
        - return_5d: 5-day return
        - return_20d: 20-day return
        - market_cap: Market cap in billions
        - market_cap_tier: MEGA/LARGE/MID/SMALL
        - beta: Stock beta
        - volume_ratio: Today volume / avg volume
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            hist = ticker.history(period="1mo")

            if hist.empty:
                return {}

            current_price = hist['Close'].iloc[-1]

            # 52-week high distance
            high_52w = info.get('fiftyTwoWeekHigh', 0)
            dist_from_high = ((high_52w - current_price) / high_52w * 100) if high_52w > 0 else None

            # Returns
            return_5d = None
            return_20d = None
            if len(hist) >= 5:
                return_5d = ((current_price / hist['Close'].iloc[-5]) - 1) * 100
            if len(hist) >= 20:
                return_20d = ((current_price / hist['Close'].iloc[-20]) - 1) * 100

            # Market cap
            market_cap = info.get('marketCap', 0)
            market_cap_b = market_cap / 1e9 if market_cap else None

            # Market cap tier
            if market_cap >= 200e9:
                tier = "MEGA"
            elif market_cap >= 10e9:
                tier = "LARGE"
            elif market_cap >= 2e9:
                tier = "MID"
            else:
                tier = "SMALL"

            # Beta
            beta = info.get('beta')

            # Volume ratio
            avg_vol = info.get('averageVolume', 0)
            today_vol = hist['Volume'].iloc[-1] if 'Volume' in hist.columns else 0
            volume_ratio = (today_vol / avg_vol) if avg_vol > 0 else None

            return {
                'dist_from_52w_high': round(dist_from_high, 1) if dist_from_high else None,
                'return_5d': round(return_5d, 2) if return_5d else None,
                'return_20d': round(return_20d, 2) if return_20d else None,
                'market_cap': round(market_cap_b, 1) if market_cap_b else None,
                'market_cap_tier': tier,
                'beta': round(beta, 2) if beta else None,
                'volume_ratio': round(volume_ratio, 2) if volume_ratio else None
            }

        except Exception as e:
            logger.debug(f"Analysis data error for {symbol}: {e}")
            return {}

    def _get_config_snapshot(self) -> Dict:
        """Get current config values for trade logging"""
        return {
            'version': 'v4.8',
            'min_score': self.MIN_SCORE,
            'position_size_pct': self.POSITION_SIZE_PCT,
            'sl_atr_mult': self.SL_ATR_MULTIPLIER,
            'tp_atr_mult': self.TP_ATR_MULTIPLIER,
            'trail_activation_pct': self.TRAIL_ACTIVATION_PCT,
            'trail_lock_pct': self.TRAIL_LOCK_PCT,
            'max_hold_days': self.MAX_HOLD_DAYS,
            'max_per_sector': self.MAX_PER_SECTOR,
            'gap_max_up_pct': self.GAP_MAX_UP,
            'daily_loss_limit_pct': self.DAILY_LOSS_LIMIT_PCT,
            'weekly_loss_limit_pct': self.WEEKLY_LOSS_LIMIT_PCT,
            'max_consecutive_losses': self.MAX_CONSECUTIVE_LOSSES,
            'smart_order_enabled': self.SMART_ORDER_ENABLED,
        }

    # =========================================================================
    # SCANNING
    # =========================================================================

    def scan_for_signals(self) -> List[Dict]:
        """Run screener to find signals (with regime filter)"""
        if not self.screener:
            logger.warning("Screener not available")
            return []

        try:
            self.state = TradingState.SCANNING

            # v4.0: Check market regime FIRST
            is_bull, regime_reason = self._check_market_regime()
            if not is_bull:
                logger.warning(f"Skipping scan - {regime_reason}")
                self.daily_stats.signals_found = 0
                return []

            logger.info("Scanning for signals...")

            # Load fresh data
            self.screener.load_data()

            # Get signals (excluding current positions)
            existing = list(self.positions.keys())
            signals = self.screener.get_portfolio_signals(
                max_positions=self.MAX_POSITIONS,
                existing_positions=existing
            )

            # v4.0: Filter by MIN_SCORE if screener doesn't do it
            if hasattr(self, 'MIN_SCORE'):
                signals = [s for s in signals if getattr(s, 'score', 0) >= self.MIN_SCORE]

            self.daily_stats.signals_found = len(signals)
            logger.info(f"Found {len(signals)} signals (regime: BULL)")

            return signals

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            return []

    # =========================================================================
    # SIGNAL QUEUE (v4.1)
    # =========================================================================

    def _add_to_queue(self, signal) -> bool:
        """
        Add signal to queue when positions are full

        Returns:
            True if added successfully
        """
        if not self.QUEUE_ENABLED:
            return False

        symbol = signal.symbol

        # Don't queue if already in queue
        if any(q.symbol == symbol for q in self.signal_queue):
            logger.debug(f"Queue: {symbol} already in queue")
            return False

        # Don't queue if already have position
        if symbol in self.positions:
            return False

        # Check queue size limit
        if len(self.signal_queue) >= self.QUEUE_MAX_SIZE:
            # Remove lowest score signal if new one is better
            lowest = min(self.signal_queue, key=lambda q: q.score)
            new_score = getattr(signal, 'score', 0)
            if new_score > lowest.score:
                self.signal_queue.remove(lowest)
                logger.debug(f"Queue: Removed {lowest.symbol} (score {lowest.score:.0f}) for {symbol} (score {new_score:.0f})")
            else:
                logger.debug(f"Queue: Full, {symbol} not better than worst")
                return False

        sig_price = getattr(signal, 'entry_price', getattr(signal, 'close', 0))
        sig_sl = getattr(signal, 'stop_loss', 0)
        sig_tp = getattr(signal, 'take_profit', 0)

        # Calculate SL/TP as percentages for recalculation when executed later
        sl_pct = ((sig_price - sig_sl) / sig_price * 100) if sig_price and sig_sl else self.STOP_LOSS_PCT
        tp_pct = ((sig_tp - sig_price) / sig_price * 100) if sig_price and sig_tp else self.TAKE_PROFIT_PCT

        queued = QueuedSignal(
            symbol=symbol,
            signal_price=sig_price,
            score=getattr(signal, 'score', 0),
            stop_loss=sig_sl,
            take_profit=sig_tp,
            queued_at=datetime.now(),
            reasons=getattr(signal, 'reasons', []),
            atr_pct=getattr(signal, 'atr_pct', 5.0),  # Default 5% if not available
            sl_pct=sl_pct,
            tp_pct=tp_pct,
        )

        self.signal_queue.append(queued)
        self.daily_stats.queue_added += 1
        self._save_queue_state()

        logger.info(f"📋 Queue: Added {symbol} @ ${queued.signal_price:.2f} (score: {queued.score:.0f}, ATR: {queued.atr_pct:.1f}%)")
        return True

    def _check_queue_for_execution(self) -> Optional[QueuedSignal]:
        """
        Check queue for executable signals when slot opens

        Priority: Freshness (< 30 min) > Score
        Deviation: ATR-based with min/max caps

        Returns:
            QueuedSignal if found acceptable one, None otherwise
        """
        if not self.QUEUE_ENABLED or not self.signal_queue:
            return None

        # Sort queue: Fresh signals first (< QUEUE_FRESHNESS_WINDOW), then by score
        def sort_key(q):
            is_fresh = q.is_fresh(self.QUEUE_FRESHNESS_WINDOW)
            return (0 if is_fresh else 1, -q.score)  # Fresh first, then highest score

        sorted_queue = sorted(self.signal_queue, key=sort_key)

        # Check each queued signal in priority order
        for queued in sorted_queue:
            symbol = queued.symbol
            age_min = queued.minutes_since_queued()

            # Skip if already have position now
            if symbol in self.positions:
                self.signal_queue.remove(queued)
                self._save_queue_state()
                continue

            # Get current price
            try:
                pos = self.trader.get_position(symbol)
                if pos:
                    current_price = pos.current_price
                else:
                    # Fetch from Yahoo
                    import yfinance as yf
                    ticker = yf.Ticker(symbol)
                    current_price = ticker.info.get('regularMarketPrice', 0)

                if current_price <= 0:
                    logger.warning(f"Queue: Could not get price for {symbol}")
                    continue

                # Check price deviation with ATR-based limits
                acceptable, deviation, max_allowed = queued.is_price_acceptable(
                    current_price,
                    self.QUEUE_ATR_MULT,
                    self.QUEUE_MIN_DEVIATION,
                    self.QUEUE_MAX_DEVIATION
                )

                fresh_tag = "🆕" if queued.is_fresh(self.QUEUE_FRESHNESS_WINDOW) else "⏰"

                if acceptable:
                    logger.info(f"✅ Queue: {fresh_tag} {symbol} price OK - ${queued.signal_price:.2f} → ${current_price:.2f} ({deviation:+.1f}% <= {max_allowed:.1f}%) [age: {age_min:.0f}min]")
                    self.signal_queue.remove(queued)
                    self._save_queue_state()
                    return queued
                else:
                    logger.warning(f"❌ Queue: {fresh_tag} {symbol} price moved - ${queued.signal_price:.2f} → ${current_price:.2f} ({deviation:+.1f}% > {max_allowed:.1f}%) [age: {age_min:.0f}min]")
                    self.signal_queue.remove(queued)
                    self._save_queue_state()
                    self.daily_stats.queue_expired += 1

            except Exception as e:
                logger.error(f"Queue: Error checking {symbol}: {e}")

        return None

    def _execute_from_queue(self, queued: QueuedSignal) -> bool:
        """
        Execute a queued signal with recalculated SL/TP based on current price.

        Args:
            queued: QueuedSignal to execute

        Returns:
            True if executed successfully
        """
        try:
            symbol = queued.symbol

            # Get current price for fresh SL/TP calculation
            current_price = queued.signal_price  # fallback
            try:
                alpaca_pos = self.trader.get_position(symbol)
                if alpaca_pos:
                    # Already have position somehow — skip
                    logger.warning(f"Queue: {symbol} already has position at Alpaca")
                    return False
                snapshot = self.trader.get_snapshot(symbol) if hasattr(self.trader, 'get_snapshot') else None
                if snapshot and snapshot.get('last_price'):
                    current_price = snapshot['last_price']
            except Exception:
                pass  # Use original signal_price as fallback

            # Recalculate SL/TP from stored percentages + current price
            sl_pct = queued.sl_pct if queued.sl_pct > 0 else self.STOP_LOSS_PCT
            tp_pct = queued.tp_pct if queued.tp_pct > 0 else self.TAKE_PROFIT_PCT
            fresh_sl = round(current_price * (1 - sl_pct / 100), 2)
            fresh_tp = round(current_price * (1 + tp_pct / 100), 2)

            # Create a mock signal object for execute_signal
            class MockSignal:
                pass

            signal = MockSignal()
            signal.symbol = symbol
            signal.entry_price = current_price
            signal.stop_loss = fresh_sl
            signal.take_profit = fresh_tp
            signal.score = queued.score
            signal.reasons = queued.reasons

            logger.info(f"📋 Queue: {symbol} SL/TP recalculated: SL ${fresh_sl:.2f} ({sl_pct:.1f}%), TP ${fresh_tp:.2f} ({tp_pct:.1f}%) @ ${current_price:.2f}")

            # Execute
            success = self.execute_signal(signal)

            if success:
                self.daily_stats.queue_executed += 1
                logger.info(f"✅ Queue: Executed {symbol} from queue")

            return success

        except Exception as e:
            logger.error(f"Queue: Error executing {queued.symbol}: {e}")
            return False

    def _clear_queue_end_of_day(self):
        """Clear queue at end of day"""
        if self.signal_queue:
            expired_count = len(self.signal_queue)
            symbols = [q.symbol for q in self.signal_queue]
            self.signal_queue.clear()
            self._save_queue_state()
            self.daily_stats.queue_expired += expired_count
            logger.info(f"📋 Queue: Cleared {expired_count} signals at EOD: {symbols}")

    def get_queue_status(self) -> List[Dict]:
        """Get current queue status for UI"""
        return [
            {
                'symbol': q.symbol,
                'signal_price': q.signal_price,
                'score': q.score,
                'atr_pct': q.atr_pct,
                'max_deviation': q.get_max_deviation(
                    self.QUEUE_ATR_MULT,
                    self.QUEUE_MIN_DEVIATION,
                    self.QUEUE_MAX_DEVIATION
                ),
                'queued_at': q.queued_at.isoformat(),
                'age_minutes': round(q.minutes_since_queued(), 1),
                'is_fresh': q.is_fresh(self.QUEUE_FRESHNESS_WINDOW),
                'reasons': q.reasons
            }
            for q in self.signal_queue
        ]

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

            # v4.5: Get effective parameters (normal vs low-risk mode)
            params = self._get_effective_params()
            mode = params['mode']

            if mode == 'LOW_RISK':
                logger.info(f"🛡️ {symbol}: Using LOW RISK parameters")

            # Safety check first
            can_trade, reason = self.safety.can_open_new_position()
            if not can_trade:
                logger.warning(f"Safety block: {reason}")
                return False

            # v4.7 Fix #5: PDT pre-buy budget check
            # If SL triggers on Day 0, we need PDT budget to sell.
            # Skip buy in NORMAL mode if no PDT budget remaining for emergency exit.
            if mode != 'LOW_RISK':
                pdt_pre_check = self.pdt_guard.get_pdt_status()
                if pdt_pre_check.remaining <= self.pdt_guard.config.reserve:
                    logger.warning(f"❌ PDT pre-buy block: remaining={pdt_pre_check.remaining}, "
                                   f"reserve={self.pdt_guard.config.reserve} → skip {symbol} in NORMAL mode")
                    return False

            # Check if already have position
            if symbol in self.positions:
                logger.warning(f"Already have position in {symbol}")
                return False

            # v4.7 Fix #9: Reconcile with Alpaca before buying
            # Catches positions that engine doesn't know about
            try:
                alpaca_existing = self.trader.get_position(symbol)
                if alpaca_existing:
                    logger.warning(f"⚠️ RECONCILIATION: Alpaca already holds {symbol} "
                                   f"(qty={alpaca_existing.qty}, current=${alpaca_existing.current_price:.2f}) "
                                   f"but engine unaware — skipping buy")
                    return False
            except Exception:
                pass  # get_position returns None for non-existent, exceptions are safe to ignore

            # Check max positions
            if len(self.positions) >= self.MAX_POSITIONS:
                logger.warning(f"Max positions ({self.MAX_POSITIONS}) reached")
                return False

            # v4.5: Check score against effective min_score
            signal_score = getattr(signal, 'score', 0)
            if signal_score < params['min_score']:
                logger.warning(f"❌ Score Filter REJECT {symbol}: {signal_score} < {params['min_score']} (mode: {mode})")
                # Trade Log: Log SKIP (score)
                try:
                    current_price = getattr(signal, 'entry_price', None) or getattr(signal, 'close', 0)
                    self.trade_logger.log_skip(
                        symbol=symbol,
                        price=current_price,
                        reason="SCORE_REJECT",
                        skip_detail=f"Score {signal_score} < {params['min_score']} ({mode})",
                        filters={"score": {"passed": False, "detail": f"{signal_score} < {params['min_score']}"}},
                        signal_score=signal_score
                    )
                except Exception as log_err:
                    logger.warning(f"Trade log error: {log_err}")
                return False

            # Calculate position size (v4.5: use effective size)
            # Use simulated capital as a cap, but never exceed real buying power
            account = self.trader.get_account()
            real_buying_power = float(account.get('buying_power', 0))
            if self.SIMULATED_CAPITAL:
                capital = min(self.SIMULATED_CAPITAL, real_buying_power)
                logger.info(f"Using simulated capital: ${self.SIMULATED_CAPITAL:,.0f} (buying power: ${real_buying_power:,.0f}, effective: ${capital:,.0f})")
            else:
                capital = account['portfolio_value']
            position_value = capital * (params['position_size_pct'] / 100)

            if mode == 'LOW_RISK':
                logger.info(f"🛡️ Position size: ${position_value:,.0f} (LOW RISK: {params['position_size_pct']}%)")

            # Get current price
            pos_check = self.trader.get_position(symbol)
            if pos_check:
                current_price = pos_check.current_price
            else:
                # Use signal's entry price as estimate
                current_price = getattr(signal, 'entry_price', None) or getattr(signal, 'close', 100)

            # v4.5: Check ATR in low risk mode
            if mode == 'LOW_RISK' and params['max_atr_pct'] is not None:
                signal_atr = getattr(signal, 'atr_pct', None)
                if signal_atr and signal_atr > params['max_atr_pct']:
                    logger.warning(f"❌ ATR Filter REJECT {symbol}: ATR {signal_atr:.1f}% > {params['max_atr_pct']}% (LOW RISK)")
                    # Trade Log: Log SKIP (ATR)
                    try:
                        self.trade_logger.log_skip(
                            symbol=symbol,
                            price=current_price,
                            reason="ATR_REJECT",
                            skip_detail=f"ATR {signal_atr:.1f}% > {params['max_atr_pct']}% (LOW RISK)",
                            filters={"atr": {"passed": False, "detail": f"{signal_atr:.1f}% > {params['max_atr_pct']}%"}},
                            signal_score=signal_score
                        )
                    except Exception as log_err:
                        logger.warning(f"Trade log error: {log_err}")
                    return False

            # v4.3: Gap Filter - ไม่ซื้อหุ้นที่ gap up/down แรงเกินไป
            # v4.5: Use effective gap_max_up
            gap_ok, gap_pct, gap_reason = self._check_gap_filter(symbol, current_price, max_up_override=params['gap_max_up'])
            if not gap_ok:
                logger.warning(f"❌ Gap Filter REJECT {symbol}: {gap_reason}")
                self.daily_stats.gap_rejected += 1
                # Trade Log: Log SKIP (gap)
                try:
                    self.trade_logger.log_skip(
                        symbol=symbol,
                        price=current_price,
                        reason="GAP_REJECT",
                        skip_detail=gap_reason,
                        filters={"gap": {"passed": False, "detail": gap_reason}},
                        signal_score=signal_score,
                        gap_pct=gap_pct
                    )
                except Exception as log_err:
                    logger.warning(f"Trade log error: {log_err}")
                return False

            # v4.4: Earnings Filter - ไม่ซื้อหุ้นที่มี earnings ใกล้ๆ
            earnings_ok, earnings_reason = self._check_earnings_filter(symbol)
            if not earnings_ok:
                logger.warning(f"❌ Earnings Filter REJECT {symbol}: {earnings_reason}")
                self.daily_stats.earnings_rejected += 1
                # Trade Log: Log SKIP (earnings)
                try:
                    self.trade_logger.log_skip(
                        symbol=symbol,
                        price=current_price,
                        reason="EARNINGS_REJECT",
                        skip_detail=earnings_reason,
                        filters={"earnings": {"passed": False, "detail": earnings_reason}},
                        signal_score=signal_score,
                        gap_pct=gap_pct
                    )
                except Exception as log_err:
                    logger.warning(f"Trade log error: {log_err}")
                return False

            # v4.7: Sector Diversification - ไม่ซื้อหุ้น sector เดียวกันเกิน MAX_PER_SECTOR
            signal_sector = getattr(signal, 'sector', '') or ''
            sector_ok, sector_reason = self._check_sector_filter(signal_sector)
            if not sector_ok:
                logger.warning(f"❌ Sector Filter REJECT {symbol}: {sector_reason}")
                self.daily_stats.sector_rejected += 1
                try:
                    self.trade_logger.log_skip(
                        symbol=symbol,
                        price=current_price,
                        reason="SECTOR_REJECT",
                        skip_detail=sector_reason,
                        filters={"sector": {"passed": False, "detail": sector_reason}},
                        signal_score=signal_score,
                        sector=signal_sector
                    )
                except Exception as log_err:
                    logger.warning(f"Trade log error: {log_err}")
                return False

            # v4.7: Sector Cooldown - sector แพ้ติดกัน → cooldown
            sector_cd_ok, sector_cd_reason = self._check_sector_cooldown(signal_sector)
            if not sector_cd_ok:
                logger.warning(f"🧊 Sector Cooldown REJECT {symbol}: {sector_cd_reason}")
                self.daily_stats.sector_rejected += 1
                try:
                    self.trade_logger.log_skip(
                        symbol=symbol,
                        price=current_price,
                        reason="SECTOR_COOLDOWN",
                        skip_detail=sector_cd_reason,
                        filters={"sector_cooldown": {"passed": False, "detail": sector_cd_reason}},
                        signal_score=signal_score,
                        sector=signal_sector
                    )
                except Exception as log_err:
                    logger.warning(f"Trade log error: {log_err}")
                return False

            # v4.6: Calculate ATR-based SL/TP (must happen before qty for risk-parity)
            signal_atr = getattr(signal, 'atr_pct', None)
            atr_sl_tp = self._calculate_atr_sl_tp(symbol, current_price, signal_atr)
            sl_pct = atr_sl_tp['sl_pct']
            tp_pct = atr_sl_tp['tp_pct']
            sl_price = atr_sl_tp['sl_price']
            tp_price = atr_sl_tp['tp_price']

            # v4.9: Risk-parity position sizing
            if self.RISK_PARITY_ENABLED and sl_pct > 0:
                # position_value = capital * (risk_budget / sl_pct)
                # If risk_budget=1% and sl=2%, position = 50% of capital
                # If risk_budget=1% and sl=4%, position = 25% of capital
                risk_parity_pct = (self.RISK_BUDGET_PCT / sl_pct) * 100
                risk_parity_pct = min(risk_parity_pct, self.MAX_POSITION_PCT)
                position_value = capital * (risk_parity_pct / 100)
                logger.info(f"Risk-Parity: SL {sl_pct}% → size {risk_parity_pct:.0f}% (${position_value:,.0f})")
            # else: uses fixed position_value from params['position_size_pct']

            qty = int(position_value / current_price)
            if qty <= 0:
                logger.warning(f"Position size too small for {symbol}")
                return False

            logger.info(f"Executing: BUY {symbol} x{qty} @ ~${current_price:.2f}")

            # PDT Smart Guard v2.0: Check if we should place SL order
            # Day 0: NO SL order (we monitor manually to control PDT)
            # Day 1+: Place SL order normally
            should_place_sl, sl_reason = self.pdt_guard.should_place_sl_order(symbol)

            if should_place_sl:
                # Normal flow: Buy with stop loss (use ATR-based SL%)
                buy_order, sl_order = self.trader.buy_with_stop_loss(symbol, qty, sl_pct=sl_pct)
                if not buy_order:
                    logger.error(f"Failed to execute {symbol} (spread too wide or order failed)")
                    return False
                sl_order_id = sl_order.id if sl_order else None
                if sl_order:
                    sl_price = sl_order.stop_price  # Use actual order price
            else:
                # PDT Guard: Buy WITHOUT stop loss (Day 0)
                # v4.8: Use smart buy (limit @ ask + market fallback)
                logger.info(f"PDT Guard: {sl_reason} - buying without SL order")
                buy_order = self.trader.place_smart_buy(symbol, qty)
                if not buy_order:
                    logger.warning(f"Smart buy SKIP {symbol}: spread too wide")
                    return False
                # Wait for fill if not already filled
                if buy_order.status != 'filled':
                    time.sleep(2)
                    buy_order = self.trader.get_order(buy_order.id)
                sl_order_id = None

            if not buy_order or buy_order.status != 'filled':
                logger.error(f"Buy order not filled for {symbol}")
                return False

            # Create managed position with ATR-based SL/TP
            entry_price = buy_order.filled_avg_price

            # v4.7 Fix #1: Use actual filled qty from trader
            actual_qty = getattr(self.trader, '_last_filled_qty', qty)
            if actual_qty and actual_qty != qty:
                logger.warning(f"Using actual filled qty {actual_qty} (requested {qty})")
                qty = actual_qty

            # Recalculate SL/TP with actual fill price
            sl_price = round(entry_price * (1 - sl_pct / 100), 2)
            tp_price = round(entry_price * (1 + tp_pct / 100), 2)

            with self._positions_lock:
                self.positions[symbol] = ManagedPosition(
                    symbol=symbol,
                    qty=qty,
                    entry_price=entry_price,
                    entry_time=datetime.now(),
                    sl_order_id=sl_order_id,
                    current_sl_price=sl_price,
                    peak_price=entry_price,
                    trailing_active=False,
                    sl_pct=sl_pct,
                    tp_price=tp_price,
                    tp_pct=tp_pct,
                    atr_pct=atr_sl_tp['atr_pct'],
                    sector=signal_sector,
                    trough_price=entry_price,
                )
                self._save_positions_state()

            # PDT Guard: Record entry date
            self.pdt_guard.record_entry(symbol)

            self.daily_stats.trades_executed += 1
            self.daily_stats.signals_executed += 1

            # v4.5: Track low risk trades
            if mode == 'LOW_RISK':
                self.daily_stats.low_risk_trades += 1
                logger.info(f"✅ Bought {symbol} x{qty} @ ${entry_price:.2f} [LOW RISK MODE]")
            else:
                logger.info(f"✅ Bought {symbol} x{qty} @ ${entry_price:.2f}")
            logger.info(f"   SL: ${sl_price:.2f} (-{sl_pct}%) | TP: ${tp_price:.2f} (+{tp_pct}%) | ATR: {atr_sl_tp['atr_pct']}%")

            # Alert: BUY executed
            self.alerts.alert_trade_executed(symbol, 'BUY', entry_price, qty)

            # Trade Log: Log BUY
            try:
                pdt_status = self.pdt_guard.get_pdt_status()
                regime_ok, regime_reason = self._check_market_regime()

                # Get analysis data for future filter decisions
                analysis = self._get_analysis_data(symbol)

                # Get execution metadata from smart buy
                exec_meta = getattr(self.trader, 'last_execution_meta', {})
                signal_price_val = getattr(signal, 'entry_price', None) or getattr(signal, 'close', None)
                slippage = None
                if signal_price_val and entry_price and signal_price_val > 0:
                    slippage = round(((entry_price - signal_price_val) / signal_price_val) * 100, 3)

                self.trade_logger.log_buy(
                    symbol=symbol,
                    qty=qty,
                    price=entry_price,
                    reason="SIGNAL",
                    filters={
                        "regime": {"passed": regime_ok, "detail": regime_reason},
                        "gap": {"passed": True, "detail": f"{gap_pct:+.1f}%"},
                        "earnings": {"passed": True, "detail": earnings_reason},
                        "score": {"passed": True, "detail": f"{signal_score}"}
                    },
                    pdt_remaining=pdt_status.remaining,
                    mode=mode,
                    regime="BULL" if regime_ok else "BEAR",
                    gap_pct=gap_pct,
                    signal_score=signal_score,
                    atr_pct=getattr(signal, 'atr_pct', None),
                    sector=getattr(signal, 'sector', None),
                    order_id=buy_order.id if buy_order else None,
                    # Analysis data
                    dist_from_52w_high=analysis.get('dist_from_52w_high'),
                    return_5d=analysis.get('return_5d'),
                    return_20d=analysis.get('return_20d'),
                    market_cap=analysis.get('market_cap'),
                    market_cap_tier=analysis.get('market_cap_tier'),
                    beta=analysis.get('beta'),
                    volume_ratio=analysis.get('volume_ratio'),
                    # Execution data (v4.8)
                    order_type=exec_meta.get('order_type'),
                    signal_price=signal_price_val,
                    limit_price=exec_meta.get('limit_price'),
                    fill_price=entry_price,
                    slippage_pct=slippage,
                    bid_ask_spread_pct=exec_meta.get('bid_ask_spread_pct'),
                    fill_time_sec=exec_meta.get('fill_time_sec'),
                    fill_status=exec_meta.get('fill_status'),
                    # Config snapshot (v4.8)
                    config_snapshot=self._get_config_snapshot(),
                )
            except Exception as log_err:
                logger.warning(f"Trade log error: {log_err}")

            return True

        except Exception as e:
            logger.error(f"Execute failed for {signal}: {e}")
            return False

    # =========================================================================
    # MONITORING & TRAILING
    # =========================================================================

    def _check_overnight_gap(self, symbol: str, managed_pos):
        """
        v4.7 Fix #11: Check for overnight gap risk at market open.
        Only runs within first 5 min of market open, for Day 1+ positions.
        """
        et_now = self._get_et_time()
        minutes_since_open = (et_now.hour - self.MARKET_OPEN_HOUR) * 60 + (et_now.minute - self.MARKET_OPEN_MINUTE)
        if minutes_since_open < 0 or minutes_since_open > 5:
            return  # Only check in first 5 minutes after open

        days_held = self.pdt_guard.get_days_held(symbol)
        if days_held < 1:
            return  # Only for positions held overnight

        try:
            snapshot = self.trader.get_snapshot(symbol)
            if not snapshot or not snapshot.get('prev_close'):
                return

            prev_close = snapshot['prev_close']
            current_price = snapshot.get('latest_price', 0)
            if prev_close <= 0 or current_price <= 0:
                return

            gap_pct = ((current_price - prev_close) / prev_close) * 100
            sl_pct = managed_pos.sl_pct or self.STOP_LOSS_PCT

            if gap_pct < -(3 * sl_pct):
                # Catastrophic gap: auto-close
                logger.error(f"🚨 CATASTROPHIC GAP {symbol}: {gap_pct:+.1f}% (> 3x SL of {sl_pct}%) → AUTO CLOSE")
                self.alerts.alert_gap_risk(symbol, gap_pct, 'CATASTROPHIC')
                self._close_position(symbol, managed_pos, "GAP_CATASTROPHIC")
            elif gap_pct < -(2 * sl_pct):
                # Severe gap: alert
                logger.warning(f"⚠️ SEVERE GAP {symbol}: {gap_pct:+.1f}% (> 2x SL of {sl_pct}%)")
                self.alerts.alert_gap_risk(symbol, gap_pct, 'SEVERE')
        except Exception as e:
            logger.debug(f"Gap check error for {symbol}: {e}")

    def _get_earnings_days_until(self, symbol: str) -> Optional[int]:
        """
        Return number of days until earnings for symbol, or None if unknown.
        Cached per symbol with TTL: successful lookups cached for the day,
        failed lookups retry after 5 minutes.
        """
        now = time.time()

        if not hasattr(self, '_earnings_cache'):
            self._earnings_cache = {}  # symbol → (days_until, expiry_timestamp)

        cached = self._earnings_cache.get(symbol)
        if cached is not None:
            days_until, expiry = cached
            if now < expiry:
                return days_until

        today = datetime.now().date()
        days_until = None
        cache_ttl = 300  # 5 min retry on failure
        try:
            ticker = yf.Ticker(symbol)
            calendar = ticker.calendar
            if calendar is not None and isinstance(calendar, dict):
                earnings_date = calendar.get('Earnings Date')
                if earnings_date:
                    if isinstance(earnings_date, list) and len(earnings_date) > 0:
                        earnings_date = earnings_date[0]
                    if earnings_date:
                        from datetime import date as date_type
                        if isinstance(earnings_date, str):
                            earnings_date = pd.to_datetime(earnings_date).date()
                        elif isinstance(earnings_date, datetime):
                            earnings_date = earnings_date.date()
                        elif not isinstance(earnings_date, date_type):
                            earnings_date = pd.to_datetime(earnings_date).date()
                        days_until = (earnings_date - today).days
            # Success: cache until end of day (6 hours)
            cache_ttl = 21600
        except Exception as e:
            logger.debug(f"Earnings lookup error for {symbol}: {e}")

        self._earnings_cache[symbol] = (days_until, now + cache_ttl)
        return days_until

    def _check_overnight_earnings(self):
        """
        v4.9: Check if any held position has earnings TODAY or TOMORROW.
        Alert user to consider exiting before close.
        Dedup: only alert once per symbol per day.
        """
        if not self.positions:
            return

        # Cooldown-based dedup: alert at most once per 1 minute per symbol
        ALERT_COOLDOWN_SEC = 60  # 1 minute
        if not hasattr(self, '_earnings_alert_times'):
            self._earnings_alert_times = {}  # symbol → last alert timestamp

        now_ts = time.time()

        for symbol in list(self.positions.keys()):
            last_alert = self._earnings_alert_times.get(symbol, 0)
            if now_ts - last_alert < ALERT_COOLDOWN_SEC:
                continue  # Still in cooldown

            try:
                days_until = self._get_earnings_days_until(symbol)
                if days_until is not None and 0 <= days_until <= 1:
                    reason = f"EARNINGS {'TODAY' if days_until == 0 else 'TOMORROW'}"
                    logger.warning(f"EARNINGS ALERT: {symbol} — {reason} — consider exiting before close")
                    self.alerts.alert_earnings_warning(symbol, reason)
                    self._earnings_alert_times[symbol] = now_ts
            except Exception as e:
                logger.debug(f"Earnings check error for {symbol}: {e}")

    def _detect_stock_split(self, symbol: str, alpaca_pos, managed_pos: ManagedPosition) -> Optional[float]:
        """
        Detect stock split by comparing Alpaca position with managed position.
        Returns split ratio if detected (e.g., 2.0 for 2:1 split), None otherwise.
        """
        alpaca_qty = float(alpaca_pos.qty)
        alpaca_price = alpaca_pos.avg_entry_price
        managed_qty = managed_pos.qty
        managed_price = managed_pos.entry_price

        if managed_qty <= 0 or managed_price <= 0:
            return None

        qty_ratio = alpaca_qty / managed_qty
        price_ratio = managed_price / alpaca_price if alpaca_price > 0 else 0

        # Split detected if qty doubled+ AND price halved (or vice versa for reverse)
        # Allow 5% tolerance for rounding
        if qty_ratio > 1.5 and abs(qty_ratio - price_ratio) / qty_ratio < 0.05:
            return qty_ratio
        if qty_ratio < 0.67 and price_ratio > 0 and abs(1/qty_ratio - 1/price_ratio) / (1/qty_ratio) < 0.05:
            return qty_ratio  # Reverse split

        return None

    def monitor_positions(self):
        """Monitor all positions and update trailing stops"""
        if not self.positions:
            return

        # v4.9: Detect stock splits and adjust tracking
        for symbol, managed_pos in list(self.positions.items()):
            try:
                alpaca_pos = self.trader.get_position(symbol)
                if alpaca_pos:
                    split_ratio = self._detect_stock_split(symbol, alpaca_pos, managed_pos)
                    if split_ratio:
                        logger.critical(f"STOCK SPLIT DETECTED: {symbol} ratio={split_ratio:.1f}x")
                        logger.critical(f"  Old: qty={managed_pos.qty}, entry=${managed_pos.entry_price:.2f}, SL=${managed_pos.current_sl_price:.2f}")
                        # Adjust all position tracking
                        managed_pos.qty = int(alpaca_pos.qty)
                        managed_pos.entry_price = alpaca_pos.avg_entry_price
                        managed_pos.current_sl_price = round(managed_pos.current_sl_price / split_ratio, 2)
                        managed_pos.peak_price = round(managed_pos.peak_price / split_ratio, 2)
                        if managed_pos.tp_price > 0:
                            managed_pos.tp_price = round(managed_pos.tp_price / split_ratio, 2)
                        if managed_pos.trough_price > 0:
                            managed_pos.trough_price = round(managed_pos.trough_price / split_ratio, 2)
                        logger.critical(f"  New: qty={managed_pos.qty}, entry=${managed_pos.entry_price:.2f}, SL=${managed_pos.current_sl_price:.2f}")
                        try:
                            self.alerts.add('CRITICAL', f'Stock Split: {symbol}',
                                            f'{symbol} split detected (ratio {split_ratio:.1f}x) — position adjusted',
                                            category='risk', symbol=symbol)
                        except Exception:
                            pass
                        self._save_positions_state()
                        # Update SL order at Alpaca
                        if managed_pos.sl_order_id:
                            self.trader.modify_stop_loss(managed_pos.sl_order_id, managed_pos.current_sl_price)
            except Exception as e:
                logger.debug(f"Split check error for {symbol}: {e}")

        # v4.7 Fix #11: Check overnight gap and earnings risk
        for symbol, managed_pos in list(self.positions.items()):
            self._check_overnight_gap(symbol, managed_pos)
        self._check_overnight_earnings()

        # Ensure all positions have SL protection
        self.safety.ensure_sl_protection()

        logger.debug(f"Monitoring {len(self.positions)} positions...")

        for symbol, managed_pos in list(self.positions.items()):
            try:
                self._check_position(symbol, managed_pos)
            except Exception as e:
                logger.error(f"Error monitoring {symbol}: {e}")

        # Detect orphan positions (at Alpaca but not tracked by engine)
        try:
            alpaca_positions = self.trader.get_positions()
            alpaca_symbols = {p.symbol for p in alpaca_positions}
            engine_symbols = set(self.positions.keys())

            orphans = alpaca_symbols - engine_symbols
            if orphans:
                logger.warning(f"⚠️ ORPHAN POSITIONS at Alpaca not tracked by engine: {', '.join(sorted(orphans))}")
                self.alerts.alert_orphan_positions(sorted(orphans))
        except Exception as e:
            logger.debug(f"Orphan check error: {e}")

    def _check_position(self, symbol: str, managed_pos: ManagedPosition):
        """
        Check single position and update trailing if needed

        PDT Smart Guard v2.0 integration:
        - Day 0: No SL order at Alpaca, monitor manually
        - Day 1+: Place/update SL order normally
        """

        # Get current position from Alpaca
        try:
            alpaca_pos = self.trader.get_position(symbol)
        except Exception as e:
            err_str = str(e).lower()
            # v4.9 Fix #34: Handle Alpaca maintenance / API outage
            if any(kw in err_str for kw in ['maintenance', '503', '502', 'service unavailable']):
                logger.warning(f"{symbol}: Alpaca API unavailable (maintenance?) — skipping check")
                return
            # v4.9 Fix #32: Handle trading halt
            if 'halted' in err_str or 'halt' in err_str:
                logger.warning(f"{symbol}: Trading HALTED — keeping position, skipping check")
                return
            raise  # Re-raise other errors

        if not alpaca_pos:
            # Position closed externally (SL triggered at Alpaca)
            logger.warning(f"{symbol} position not found - SL likely triggered at Alpaca")
            # Record SL exit for stats tracking
            try:
                sl_price = managed_pos.current_sl_price
                pnl_pct = ((sl_price - managed_pos.entry_price) / managed_pos.entry_price) * 100
                pnl_usd = (sl_price - managed_pos.entry_price) * managed_pos.qty
                logger.info(f"SL fill detected for {symbol}: {pnl_pct:+.2f}% (${pnl_usd:+.2f})")
                # Update stats
                self.daily_stats.realized_pnl += pnl_usd
                with self._stats_lock:
                    self.weekly_realized_pnl += pnl_usd
                if pnl_pct > 0:
                    self.daily_stats.trades_won += 1
                else:
                    self.daily_stats.trades_lost += 1
                self._record_trade_result(pnl_pct)
                self._record_sector_trade_result(managed_pos.sector, pnl_pct)
                # Log the SL trade
                try:
                    days_held = self.pdt_guard.get_days_held(symbol)
                    hold_delta = datetime.now() - managed_pos.entry_time
                    hold_hours = int(hold_delta.total_seconds() / 3600)
                    hold_minutes = int((hold_delta.total_seconds() % 3600) / 60)
                    hold_duration = f"{hold_hours}h {hold_minutes}m" if hold_hours > 0 else f"{hold_minutes}m"
                    self.trade_logger.log_sell(
                        symbol=symbol, qty=managed_pos.qty, price=sl_price,
                        reason="SL_FILLED_AT_ALPACA", entry_price=managed_pos.entry_price,
                        pnl_usd=pnl_usd, pnl_pct=pnl_pct, hold_duration=hold_duration,
                        day_held=days_held, sl_price=sl_price,
                        trail_active=managed_pos.trailing_active, peak_price=managed_pos.peak_price,
                    )
                except Exception as log_err:
                    logger.warning(f"Trade log error for SL fill: {log_err}")
            except Exception as e:
                logger.warning(f"Failed to track SL fill for {symbol}: {e}")
            with self._positions_lock:
                if symbol in self.positions:
                    del self.positions[symbol]
                    self._save_positions_state()
            self.pdt_guard.remove_entry(symbol)
            return

        current_price = alpaca_pos.current_price
        entry_price = managed_pos.entry_price

        # v4.7 Fix #7: Use intraday high from Alpaca snapshot for peak_price
        # Prevents missing peaks between monitor intervals
        intraday_high = current_price
        try:
            snapshot = self.trader.get_snapshot(symbol)
            if snapshot and snapshot.get('daily_high'):
                intraday_high = max(current_price, snapshot['daily_high'])
        except Exception:
            pass  # Fallback to current_price

        # Update peak and trough
        _state_changed = False
        if intraday_high > managed_pos.peak_price:
            managed_pos.peak_price = intraday_high
            _state_changed = True
        if managed_pos.trough_price == 0 or current_price < managed_pos.trough_price:
            managed_pos.trough_price = current_price
            _state_changed = True

        # Calculate P&L
        pnl_pct = ((current_price - entry_price) / entry_price) * 100

        # Get PDT guard status for this position
        days_held = self.pdt_guard.get_days_held(symbol)
        is_day0 = days_held == 0

        # v4.6: Use per-position SL/TP
        pos_sl_pct = managed_pos.sl_pct or self.STOP_LOSS_PCT
        pos_tp_pct = managed_pos.tp_pct or self.TAKE_PROFIT_PCT
        pos_tp_price = managed_pos.tp_price or (entry_price * (1 + pos_tp_pct / 100))

        # ==== PDT Smart Guard v2.0: Day 0 Handling ====
        if is_day0:
            # Day 0: Manual SL monitoring (no SL order at Alpaca)
            if pnl_pct <= -pos_sl_pct:
                logger.warning(f"🛑 {symbol} Day 0 SL hit at {pnl_pct:.2f}% (SL: -{pos_sl_pct}%)")
                self._close_position(symbol, managed_pos, "DAY0_SL")
                return

            # Day 0: Check TP (v4.6: use per-position TP)
            if pnl_pct >= pos_tp_pct:
                logger.info(f"🎯 {symbol} Day 0 TP at {pnl_pct:+.2f}% (TP: +{pos_tp_pct}%)")
                self._close_position(symbol, managed_pos, "DAY0_TP")
                return

            # Day 0: Log status
            logger.debug(f"PDT Guard: {symbol} Day 0 - P&L {pnl_pct:+.2f}% (SL: -{pos_sl_pct}%, TP: +{pos_tp_pct}%)")

        else:
            # ==== Day 1+: Normal operation ====

            # Place SL order if not exists (transition from Day 0)
            if not managed_pos.sl_order_id:
                logger.info(f"PDT Guard: {symbol} Day {days_held} - placing SL order now")
                sl_price = managed_pos.current_sl_price  # v4.6: use stored SL price
                sl_order = self.trader.place_stop_loss(symbol, managed_pos.qty, sl_price)
                if sl_order:
                    managed_pos.sl_order_id = sl_order.id
                    managed_pos.current_sl_price = sl_order.stop_price
                    _state_changed = True
                    logger.info(f"✅ {symbol} SL order placed @ ${sl_order.stop_price:.2f}")

            # Check take profit (v4.6: use per-position TP)
            if pnl_pct >= pos_tp_pct:
                logger.info(f"🎯 {symbol} hit TP at {pnl_pct:+.2f}% (TP: +{pos_tp_pct}%)")
                self._close_position(symbol, managed_pos, "TAKE_PROFIT")
                return

            # Check trailing activation
            if not managed_pos.trailing_active and pnl_pct >= self.TRAIL_ACTIVATION_PCT:
                managed_pos.trailing_active = True
                _state_changed = True
                logger.info(f"📈 {symbol} trailing activated at {pnl_pct:+.2f}%")
                self.alerts.alert_trailing_activated(symbol, current_price, managed_pos.peak_price)

            # Update trailing stop (only if SL order exists)
            if managed_pos.trailing_active and managed_pos.sl_order_id:
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
                        managed_pos.current_sl_price = new_order.stop_price
                        _state_changed = True
                        if new_order.stop_price != new_sl:
                            logger.warning(f"{symbol} SL fallback to ${new_order.stop_price:.2f}")
                    else:
                        # CRITICAL: No SL protection - close position immediately
                        logger.error(f"CRITICAL: {symbol} has no SL - closing position for safety")
                        self._close_position(symbol, managed_pos, "NO_SL_PROTECTION")

        # Check days held (update for display)
        managed_pos.days_held = days_held

        # Time exit (only for Day 1+)
        if days_held >= self.MAX_HOLD_DAYS and pnl_pct < 1:
            logger.info(f"⏰ {symbol} held {days_held} days with {pnl_pct:+.2f}% - time exit")
            self._close_position(symbol, managed_pos, "TIME_EXIT")
            return

        # v4.9.1: Earnings auto-sell — sell ASAP on Day 1+ if earnings today/tomorrow
        if self.EARNINGS_AUTO_SELL and days_held >= 1:
            try:
                days_until = self._get_earnings_days_until(symbol)
                if days_until is not None and 0 <= days_until <= 1:
                    logger.warning(f"🚨 EARNINGS AUTO-SELL: {symbol} — earnings in {days_until} day(s), P&L {pnl_pct:+.2f}%")
                    self._close_position(symbol, managed_pos, f"EARNINGS_AUTO_SELL")
                    return
            except Exception as e:
                logger.debug(f"Earnings auto-sell check error for {symbol}: {e}")

        # Persist state if anything changed
        if _state_changed:
            self._save_positions_state()

        # Log status
        logger.debug(
            f"{symbol}: ${current_price:.2f} ({pnl_pct:+.2f}%), "
            f"SL=${managed_pos.current_sl_price:.2f}, "
            f"Peak=${managed_pos.peak_price:.2f}, "
            f"Trailing={'ON' if managed_pos.trailing_active else 'OFF'}"
        )

    def _close_position(self, symbol: str, managed_pos: ManagedPosition, reason: str, force: bool = False):
        """
        Close a position with PDT Smart Guard v2.0 protection

        Args:
            symbol: Stock symbol
            managed_pos: Managed position object
            reason: Reason for closing (TAKE_PROFIT, TIME_EXIT, etc.)
            force: If True, bypass PDT check (for manual sells)
        """
        # Per-symbol close mutex — prevents concurrent close for same symbol
        with self._close_locks_lock:
            if symbol not in self._close_locks:
                self._close_locks[symbol] = threading.Lock()
            close_lock = self._close_locks[symbol]

        if not close_lock.acquire(blocking=False):
            logger.warning(f"{symbol} close already in progress — skipping duplicate")
            return

        try:
            # Double-check: symbol still in positions after acquiring lock
            with self._positions_lock:
                if symbol not in self.positions:
                    logger.info(f"{symbol} already removed from positions — skipping close")
                    return

            # CRITICAL: Check if position still exists before selling
            # This prevents double-sell if SL was already triggered
            alpaca_pos = self.trader.get_position(symbol)
            if not alpaca_pos:
                logger.info(f"{symbol} position already closed (SL may have triggered)")
                with self._positions_lock:
                    if symbol in self.positions:
                        del self.positions[symbol]
                        self._save_positions_state()
                self.pdt_guard.remove_entry(symbol)
                return

            # Calculate current P&L for PDT check
            current_price = alpaca_pos.current_price
            pnl_pct = ((current_price - managed_pos.entry_price) / managed_pos.entry_price) * 100

            # PDT Smart Guard v2.0: Check if sell is allowed
            # v4.6: Pass per-position SL/TP to PDT guard (PDT TP = SL for R:R 1:1)
            if not force:
                pos_sl_pct = managed_pos.sl_pct or self.STOP_LOSS_PCT
                can_sell, decision, pdt_reason = self.pdt_guard.can_sell(
                    symbol, pnl_pct,
                    sl_override=pos_sl_pct,
                    tp_override=pos_sl_pct  # PDT TP = SL% (R:R 1:1 minimum)
                )

                if not can_sell:
                    logger.warning(f"PDT Guard BLOCKED: {symbol} {reason} - {pdt_reason}")
                    logger.warning(f"  Decision: {decision.value}, P&L: {pnl_pct:+.2f}%")
                    return  # Do NOT sell

                logger.info(f"PDT Guard ALLOWED: {symbol} - {pdt_reason}")

            # Cancel SL order first (if exists)
            if managed_pos.sl_order_id:
                self.trader.cancel_order(managed_pos.sl_order_id)

            # v4.9: Check for existing pending sell orders (prevent duplication)
            try:
                open_orders = self.trader.get_orders(status='open')
                pending_sells = [o for o in open_orders if o.symbol == symbol and o.side == 'sell' and o.type == 'market']
                if pending_sells:
                    logger.warning(f"{symbol}: Already has {len(pending_sells)} pending sell order(s) — skipping duplicate")
                    return
            except Exception as e:
                logger.warning(f"{symbol}: Could not check pending orders: {e}")

            # Sell using actual qty from Alpaca (not managed_pos.qty)
            # In case of partial fills or discrepancies
            actual_qty = int(alpaca_pos.qty)
            sell_order = self.trader.place_market_sell(symbol, actual_qty)

            # Wait for fill with retry (max 10 seconds)
            order = None
            for _wait in range(10):
                time.sleep(1)
                order = self.trader.get_order(sell_order.id)
                if order.status == 'filled':
                    break

            if not order or order.status != 'filled':
                # CRITICAL: Sell order NOT filled — keep position in tracking
                logger.error(f"CRITICAL: {symbol} sell NOT filled (status={order.status if order else 'unknown'}), keeping in tracking")
                logger.error(f"  Sell order {sell_order.id} may still be pending at Alpaca — will retry next monitor cycle")
                self.alerts.alert_sell_failed(symbol, f"Status: {order.status if order else 'unknown'}, order {sell_order.id}")
                return

            exit_price = order.filled_avg_price
            pnl_pct = ((exit_price - managed_pos.entry_price) / managed_pos.entry_price) * 100
            pnl_usd = (exit_price - managed_pos.entry_price) * actual_qty

            logger.info(f"✅ Closed {symbol}: {pnl_pct:+.2f}% (${pnl_usd:+.2f}) - {reason}")

            # Alert: trade closed
            if 'stop loss' in reason.lower() or 'sl' in reason.lower():
                self.alerts.alert_sl_hit(symbol, exit_price, managed_pos.current_sl_price, pnl_pct)
            elif 'take profit' in reason.lower() or 'tp' in reason.lower():
                self.alerts.alert_tp_hit(symbol, exit_price, managed_pos.tp_price, pnl_pct)
            elif 'max hold' in reason.lower():
                self.alerts.alert_max_hold_exit(symbol, managed_pos.days_held, pnl_pct)
            else:
                self.alerts.alert_trade_executed(symbol, 'SELL', exit_price, actual_qty)

            # Update stats
            self.daily_stats.realized_pnl += pnl_usd
            with self._stats_lock:
                self.weekly_realized_pnl += pnl_usd  # v4.7: Weekly tracking
            if pnl_pct > 0:
                self.daily_stats.trades_won += 1
            else:
                self.daily_stats.trades_lost += 1

            # v4.7: Track consecutive losses + cooldown
            self._record_trade_result(pnl_pct)
            self._record_sector_trade_result(managed_pos.sector, pnl_pct)

            # Trade Log: Log SELL
            try:
                days_held = self.pdt_guard.get_days_held(symbol)
                pdt_status = self.pdt_guard.get_pdt_status()
                pdt_used = days_held == 0  # Day 0 sell = PDT used

                # Calculate hold duration
                entry_time = managed_pos.entry_time
                hold_delta = datetime.now() - entry_time
                hold_hours = int(hold_delta.total_seconds() / 3600)
                hold_minutes = int((hold_delta.total_seconds() % 3600) / 60)
                hold_duration = f"{hold_hours}h {hold_minutes}m" if hold_hours > 0 else f"{hold_minutes}m"

                # Calculate price action metrics
                max_gain = ((managed_pos.peak_price - managed_pos.entry_price) / managed_pos.entry_price) * 100 if managed_pos.peak_price > managed_pos.entry_price else 0
                max_dd = ((managed_pos.trough_price - managed_pos.entry_price) / managed_pos.entry_price) * 100 if managed_pos.trough_price > 0 and managed_pos.trough_price < managed_pos.entry_price else 0
                exit_eff = round(pnl_pct / max_gain * 100, 1) if max_gain > 0 else (0 if pnl_pct <= 0 else 100)

                self.trade_logger.log_sell(
                    symbol=symbol,
                    qty=actual_qty,
                    price=exit_price,
                    reason=reason,
                    entry_price=managed_pos.entry_price,
                    pnl_usd=pnl_usd,
                    pnl_pct=pnl_pct,
                    hold_duration=hold_duration,
                    pdt_used=pdt_used,
                    pdt_remaining=pdt_status.remaining - (1 if pdt_used else 0),
                    day_held=days_held,
                    sl_price=managed_pos.current_sl_price,
                    trail_active=managed_pos.trailing_active,
                    peak_price=managed_pos.peak_price,
                    order_id=order.id,
                    # Price action (v4.8)
                    trough_price=managed_pos.trough_price if managed_pos.trough_price > 0 else None,
                    max_gain_pct=round(max_gain, 2),
                    max_drawdown_pct=round(max_dd, 2),
                    exit_efficiency=exit_eff,
                )
            except Exception as log_err:
                logger.warning(f"Trade log error: {log_err}")

            # Remove from managed positions and PDT guard (only after confirmed fill)
            with self._positions_lock:
                if symbol in self.positions:
                    del self.positions[symbol]
                    self._save_positions_state()
            self.pdt_guard.remove_entry(symbol)

            # Re-verify position is actually gone from Alpaca before opening new
            try:
                verify_pos = self.trader.get_position(symbol)
                if verify_pos:
                    logger.warning(f"{symbol}: Still exists at Alpaca after sell — NOT opening new position")
                    return
            except Exception:
                pass  # Position not found = good, it's closed

            # v4.1 Final: Check queue → Rescan if empty
            if len(self.positions) < self.MAX_POSITIONS:
                executed = False

                # Step 1: Check queue first
                if self.signal_queue:
                    queued = self._check_queue_for_execution()
                    if queued:
                        logger.info(f"📋 Queue: Slot opened, executing {queued.symbol}")
                        executed = self._execute_from_queue(queued)

                # Step 2: If queue empty/expired and rescan enabled, scan fresh
                if not executed and self.QUEUE_RESCAN_ON_EMPTY:
                    logger.info(f"📋 Queue: Empty/expired, rescanning...")
                    self.daily_stats.queue_rescans += 1
                    signals = self.scan_for_signals()
                    if signals:
                        # Execute first signal (best one)
                        signal = signals[0]
                        logger.info(f"🔄 Rescan: Found {signal.symbol}, executing...")
                        self.execute_signal(signal)

                        # Queue remaining signals
                        for remaining in signals[1:]:
                            self._add_to_queue(remaining)

        except Exception as e:
            logger.error(f"Failed to close {symbol}: {e}")
        finally:
            close_lock.release()

    # =========================================================================
    # DAILY CHECKS
    # =========================================================================

    def check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit exceeded"""
        account = self.trader.get_account()
        last_equity = account['last_equity']
        if last_equity <= 0:
            return False
        daily_pnl_pct = ((account['equity'] - last_equity) / last_equity) * 100

        if daily_pnl_pct <= -self.DAILY_LOSS_LIMIT_PCT:
            logger.warning(f"Daily loss limit hit: {daily_pnl_pct:.2f}%")
            return True
        return False

    # =========================================================================
    # WEEKLY LOSS LIMIT (v4.7 NEW!)
    # =========================================================================

    def check_weekly_loss_limit(self) -> bool:
        """
        Check if weekly loss limit exceeded.
        Reset ทุกวันจันทร์ (start of trading week). Thread-safe.
        """
        today = datetime.now(self.et_tz).date()

        with self._stats_lock:
            # Reset on Monday
            if today.weekday() == 0 and self.weekly_reset_date != today:
                self.weekly_realized_pnl = 0.0
                self.weekly_reset_date = today
                logger.info("Weekly P&L reset (Monday)")
                self._save_loss_counters()

            weekly_pnl = self.weekly_realized_pnl

        account = self.trader.get_account()
        capital = float(account.get('portfolio_value', self.SIMULATED_CAPITAL or 4000))
        weekly_pnl_pct = (weekly_pnl / capital) * 100

        if weekly_pnl_pct <= -self.WEEKLY_LOSS_LIMIT_PCT:
            logger.warning(f"🚨 Weekly loss limit hit: {weekly_pnl_pct:.2f}% (${weekly_pnl:.2f})")
            return True
        return False

    # =========================================================================
    # CONSECUTIVE LOSS STOP (v4.7 NEW!)
    # =========================================================================

    def check_consecutive_loss_cooldown(self) -> bool:
        """
        Check if in cooldown from consecutive losses.
        แพ้ 3 ครั้งติด → หยุด 1 วัน. Thread-safe.
        """
        with self._stats_lock:
            if self.cooldown_until:
                today = datetime.now(self.et_tz).date()
                if today <= self.cooldown_until:
                    logger.warning(f"🧊 Cooldown active: {self.consecutive_losses} consecutive losses (until {self.cooldown_until})")
                    return True
                else:
                    # Cooldown expired
                    logger.info(f"✅ Cooldown ended, resuming trading")
                    self.cooldown_until = None
                    self.consecutive_losses = 0
        return False

    def _record_trade_result(self, pnl_pct: float):
        """
        Record trade result for consecutive loss tracking + weekly P&L.
        Called after every closed trade. Thread-safe.
        """
        with self._stats_lock:
            if pnl_pct >= 0:
                self.consecutive_losses = 0  # Reset on win or breakeven
            else:
                self.consecutive_losses += 1
                logger.info(f"📉 Consecutive losses: {self.consecutive_losses}/{self.MAX_CONSECUTIVE_LOSSES}")

                if self.consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
                    self.cooldown_until = datetime.now(self.et_tz).date() + timedelta(days=1)
                    logger.warning(f"🧊 {self.consecutive_losses} consecutive losses → cooldown until {self.cooldown_until}")

        self._save_loss_counters()

    def pre_close_check(self):
        """Pre-close check - handle max hold days and Day 0 SL"""
        logger.info("Pre-close check...")

        for symbol, managed_pos in list(self.positions.items()):
            if managed_pos.days_held >= self.MAX_HOLD_DAYS:
                logger.info(f"Closing {symbol} - held {managed_pos.days_held} days")
                self._close_position(symbol, managed_pos, "MAX_HOLD_DAYS")

        # v4.9.1: Earnings auto-sell (safety net — primary check is in _check_position)
        if self.EARNINGS_AUTO_SELL:
            for symbol, managed_pos in list(self.positions.items()):
                try:
                    days_until = self._get_earnings_days_until(symbol)
                    if days_until is not None and 0 <= days_until <= 1:
                        days_held = self.pdt_guard.get_days_held(symbol)
                        if days_held >= 1:
                            logger.warning(f"EARNINGS AUTO-SELL (pre-close): {symbol} — earnings in {days_until} day(s)")
                            self._close_position(symbol, managed_pos, "EARNINGS_AUTO_SELL")
                        else:
                            logger.warning(f"EARNINGS: {symbol} Day 0, cannot sell (PDT) — place tight SL instead")
                except Exception as e:
                    logger.debug(f"Earnings auto-sell check error for {symbol}: {e}")

        # v4.9: Place overnight SL for Day 0 positions near close
        for symbol, managed_pos in list(self.positions.items()):
            try:
                should_place, reason = self.pdt_guard.should_place_eod_sl(symbol)
                if should_place:
                    # Calculate SL price using position's SL%
                    sl_pct = managed_pos.sl_pct or self.STOP_LOSS_PCT
                    sl_price = round(managed_pos.entry_price * (1 - sl_pct / 100), 2)
                    logger.info(f"Placing EOD SL for {symbol} (Day 0): ${sl_price:.2f} (-{sl_pct}%)")
                    sl_order = self.trader.place_stop_loss(symbol, managed_pos.qty, sl_price)
                    if sl_order:
                        managed_pos.sl_order_id = sl_order.id
                        managed_pos.current_sl_price = sl_order.stop_price
                        self._save_positions_state()
                        logger.info(f"EOD SL placed for {symbol}: ${sl_order.stop_price:.2f}")
            except Exception as e:
                logger.error(f"EOD SL error for {symbol}: {e}")

    def daily_summary(self) -> Dict:
        """Generate daily summary"""
        account = self.trader.get_account()

        summary = {
            'date': self.daily_stats.date,
            'regime_status': self.daily_stats.regime_status,  # v4.0
            'regime_skipped': self.daily_stats.regime_skipped,  # v4.0
            'signals_found': self.daily_stats.signals_found,
            'signals_executed': self.daily_stats.signals_executed,
            'trades_won': self.daily_stats.trades_won,
            'trades_lost': self.daily_stats.trades_lost,
            'realized_pnl': self.daily_stats.realized_pnl,
            'account_value': account['portfolio_value'],
            'positions_held': len(self.positions),
            # v4.1: Queue stats
            'queue_added': self.daily_stats.queue_added,
            'queue_executed': self.daily_stats.queue_executed,
            'queue_expired': self.daily_stats.queue_expired,
            # v4.5: Low risk mode stats
            'low_risk_trades': self.daily_stats.low_risk_trades,
        }

        logger.info("=" * 50)
        logger.info("DAILY SUMMARY (v4.5 Low Risk Mode)")
        logger.info("=" * 50)
        logger.info(f"  Market Regime: {self.daily_stats.regime_status}")
        if self.daily_stats.regime_skipped:
            logger.info("  ⚠️ Skipped trading due to BEAR market")
        for k, v in summary.items():
            if k not in ['regime_status', 'regime_skipped']:
                logger.info(f"  {k}: {v}")

        # v4.1: Queue summary
        if self.daily_stats.queue_added > 0:
            logger.info(f"  📋 Queue: {self.daily_stats.queue_added} added, {self.daily_stats.queue_executed} executed, {self.daily_stats.queue_expired} expired")

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
        # Persist final state before shutdown
        if self.positions:
            self._save_positions_state()
            logger.info(f"Saved {len(self.positions)} position(s) state on shutdown")
        logger.info("Trading engine stopped")

    def _run_loop(self):
        """Main trading loop"""
        logger.info("Trading loop started")

        last_scan_date = None
        consecutive_errors = 0  # v4.7 Fix #13: Circuit breaker counter

        while self.running:
            try:
                now = self._get_et_time()

                # Skip weekends
                if self._is_weekend():
                    self.state = TradingState.SLEEPING
                    time.sleep(60)
                    continue

                # Check market status
                try:
                    clock = self.trader.get_clock()
                except Exception as clock_err:
                    # v4.9 Fix #34: Handle Alpaca maintenance
                    err_str = str(clock_err).lower()
                    if any(kw in err_str for kw in ['maintenance', '503', '502', 'service unavailable']):
                        logger.warning(f"Alpaca API maintenance detected — waiting 60s")
                        time.sleep(60)
                        continue
                    raise

                if not clock['is_open']:
                    self.state = TradingState.SLEEPING
                    time.sleep(60)
                    continue

                # Market is open
                self.state = TradingState.TRADING

                # Pre-market scan (once per day at open)
                today = now.strftime('%Y-%m-%d')
                if last_scan_date != today:
                    # v4.7: Wait for market to settle before scanning
                    # 09:30-09:35 = spread กว้าง, volatile, slippage สูง
                    # 09:35+ = spread แคบ, ราคานิ่งขึ้น, ได้ราคาดีกว่า
                    et_now = self._get_et_time()
                    market_open = et_now.replace(
                        hour=self.MARKET_OPEN_HOUR,
                        minute=self.MARKET_OPEN_MINUTE,
                        second=0, microsecond=0
                    )
                    scan_time = market_open + timedelta(minutes=self.MARKET_OPEN_SCAN_DELAY)
                    if et_now < scan_time:
                        wait_secs = (scan_time - et_now).total_seconds()
                        logger.info(f"⏳ Waiting {wait_secs:.0f}s for market to settle (scan at {scan_time.strftime('%H:%M')} ET)")
                        time.sleep(wait_secs)

                    # v4.4: Late start protection — skip morning scan if starting
                    # too late (> 20 min after open). Afternoon scan still runs at 14:00 ET.
                    is_late, late_reason = self._is_late_start()
                    if is_late:
                        logger.warning(f"⏰ {late_reason} - skipping morning scan, afternoon scan at {self.AFTERNOON_SCAN_HOUR}:{self.AFTERNOON_SCAN_MINUTE:02d} ET")
                        self.daily_stats.late_start_skipped = True
                        last_scan_date = today
                        continue

                    # v4.0: Check market regime first
                    is_bull, regime_reason = self._check_market_regime()
                    self.daily_stats.regime_status = "BULL" if is_bull else "BEAR"

                    if not is_bull:
                        logger.warning(f"📉 BEAR market - skipping all new trades today")
                        self.daily_stats.regime_skipped = True
                    elif self.check_daily_loss_limit():
                        logger.warning("Daily loss limit - no new trades today")
                    elif self.check_weekly_loss_limit():
                        logger.warning("Weekly loss limit - no new trades this week")
                    elif self.check_consecutive_loss_cooldown():
                        logger.warning("Consecutive loss cooldown - no new trades today")
                    else:
                        # v4.1: Clear queue from previous day
                        self._clear_queue_end_of_day()

                        # Scan and execute (regime is BULL)
                        signals = self.scan_for_signals()
                        for signal in signals:
                            if len(self.positions) < self.MAX_POSITIONS:
                                self.execute_signal(signal)
                            else:
                                # v4.1: Queue remaining signals instead of breaking
                                self._add_to_queue(signal)

                    last_scan_date = today

                # v4.9.1: Afternoon scan — fill empty slots after lunch dip
                if self.AFTERNOON_SCAN_ENABLED and last_scan_date == today:
                    et_now = self._get_et_time()
                    afternoon_time = et_now.replace(
                        hour=self.AFTERNOON_SCAN_HOUR,
                        minute=self.AFTERNOON_SCAN_MINUTE,
                        second=0, microsecond=0
                    )
                    if not hasattr(self, '_afternoon_scan_done') or self._afternoon_scan_done != today:
                        if et_now >= afternoon_time and len(self.positions) < self.MAX_POSITIONS:
                            logger.info(f"☀️ Afternoon scan: {len(self.positions)}/{self.MAX_POSITIONS} positions, scanning for more...")
                            self._afternoon_scan_done = today
                            is_bull, _ = self._check_market_regime()
                            if is_bull and not self.check_daily_loss_limit() and not self.check_weekly_loss_limit():
                                # Use stricter params for afternoon
                                saved_min_score = self.MIN_SCORE
                                saved_gap_up = self.GAP_MAX_UP
                                saved_gap_down = self.GAP_MAX_DOWN
                                self.MIN_SCORE = max(self.MIN_SCORE, self.AFTERNOON_MIN_SCORE)
                                self.GAP_MAX_UP = self.AFTERNOON_GAP_MAX_UP
                                self.GAP_MAX_DOWN = self.AFTERNOON_GAP_MAX_DOWN
                                try:
                                    signals = self.scan_for_signals()
                                    for signal in signals:
                                        if len(self.positions) < self.MAX_POSITIONS:
                                            self.execute_signal(signal)
                                finally:
                                    self.MIN_SCORE = saved_min_score
                                    self.GAP_MAX_UP = saved_gap_up
                                    self.GAP_MAX_DOWN = saved_gap_down

                # Pre-close check
                if self._is_pre_close():
                    self.state = TradingState.CLOSING
                    self.pre_close_check()

                # Monitor positions
                self.state = TradingState.MONITORING
                self.monitor_positions()

                # v4.7 Fix #15: Write heartbeat
                self._write_heartbeat()

                # Wait for next interval
                time.sleep(self.MONITOR_INTERVAL_SECONDS)

                # v4.7: Reset error counter on successful cycle
                consecutive_errors = 0

            except Exception as e:
                logger.error(f"Loop error: {e}")
                self.state = TradingState.ERROR
                consecutive_errors += 1

                # v4.7 Fix #13: Circuit breaker
                if consecutive_errors >= self.CIRCUIT_BREAKER_MAX_ERRORS:
                    logger.critical(f"🚨 CIRCUIT BREAKER: {consecutive_errors} consecutive errors — EMERGENCY STOP")
                    self.alerts.alert_circuit_breaker(consecutive_errors)
                    self.running = False
                    self.state = TradingState.STOPPED
                    break

                time.sleep(30)

        # Generate daily summary on stop
        self.daily_summary()

    # =========================================================================
    # STATUS & INFO
    # =========================================================================

    def _write_heartbeat(self):
        """v4.7 Fix #15: Write heartbeat file for external watchdog monitoring"""
        try:
            heartbeat_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'data', 'heartbeat.json'
            )
            os.makedirs(os.path.dirname(heartbeat_path), exist_ok=True)

            heartbeat = {
                'timestamp': datetime.now().isoformat(),
                'state': self.state.value,
                'positions': len(self.positions),
                'running': self.running,
            }
            # Atomic write
            tmp_path = heartbeat_path + '.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(heartbeat, f)
            os.replace(tmp_path, heartbeat_path)
        except Exception as e:
            logger.debug(f"Heartbeat write error: {e}")

    def get_status(self) -> Dict:
        """Get current engine status"""
        # Snapshot shared state under lock
        with self._positions_lock:
            positions_count = len(self.positions)
            queue_size = len(self.signal_queue)
            position_items = list(self.positions.items())

        with self._stats_lock:
            consecutive_losses = self.consecutive_losses
            weekly_pnl = self.weekly_realized_pnl

        account = self.trader.get_account()
        safety_status = self.safety.get_status_summary()

        # v4.0: Get current regime
        is_bull, regime_reason = self._check_market_regime()

        # v4.5: Get low risk mode status
        is_low_risk, low_risk_reason = self._is_low_risk_mode()

        # v4.7 Fix #12: Sector exposure breakdown
        sector_counts = {}
        for sym, pos in position_items:
            sect = getattr(pos, 'sector', 'Unknown') or 'Unknown'
            sector_counts[sect] = sector_counts.get(sect, 0) + 1
        total_pos = positions_count or 1
        sector_exposure = {
            sect: {'count': cnt, 'pct': round(cnt / total_pos * 100, 1)}
            for sect, cnt in sector_counts.items()
        }

        return {
            'state': self.state.value,
            'running': self.running,
            'market_open': self.trader.is_market_open(),
            'market_regime': 'BULL' if is_bull else 'BEAR',  # v4.0
            'regime_detail': regime_reason,  # v4.0
            'low_risk_mode': is_low_risk,  # v4.5
            'low_risk_reason': low_risk_reason,  # v4.5
            'positions': positions_count,
            'account_value': account['portfolio_value'],
            'cash': account['cash'],
            'daily_stats': asdict(self.daily_stats),
            'safety': safety_status,
            'version': 'v4.9 Thread-Safe',
            # v4.1: Queue status
            'queue_size': queue_size,
            'queue': self.get_queue_status(),
            # v4.7: Sector exposure
            'sector_exposure': sector_exposure,
            # v4.9: Loss protection snapshot
            'consecutive_losses': consecutive_losses,
            'weekly_pnl': weekly_pnl,
        }

    def get_positions_status(self) -> List[Dict]:
        """Get detailed positions status"""
        status = []

        for symbol, managed_pos in list(self.positions.items()):  # copy to avoid iteration error
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
    """Test trading engine v4.0"""
    print("=" * 60)
    print("AUTO TRADING ENGINE v4.0 - Smart Regime Edition")
    print("=" * 60)

    # Credentials from environment
    API_KEY = os.environ.get('ALPACA_API_KEY')
    SECRET_KEY = os.environ.get('ALPACA_SECRET_KEY')
    if not API_KEY or not SECRET_KEY:
        print("ERROR: Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables")
        return

    engine = AutoTradingEngine(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        paper=True,
        auto_start=False  # Don't auto-start for testing
    )

    # v4.0: Show config
    print("\n[0] v4.0 Configuration:")
    print(f"    MAX_POSITIONS: {engine.MAX_POSITIONS}")
    print(f"    POSITION_SIZE_PCT: {engine.POSITION_SIZE_PCT}%")
    print(f"    MIN_SCORE: {engine.MIN_SCORE}")
    print(f"    TRAIL_ACTIVATION: {engine.TRAIL_ACTIVATION_PCT}%")
    print(f"    TRAIL_LOCK: {engine.TRAIL_LOCK_PCT}%")
    print(f"    REGIME_FILTER: {'ENABLED' if engine.REGIME_FILTER_ENABLED else 'DISABLED'}")
    print(f"    REGIME_SMA: SMA{engine.REGIME_SMA_PERIOD}")

    # v4.0: Test Market Regime Filter
    print("\n[1] Market Regime Check:")
    is_bull, regime_reason = engine._check_market_regime()
    print(f"    Status: {'🟢 BULL - OK to trade' if is_bull else '🔴 BEAR - Skip new trades'}")
    print(f"    Detail: {regime_reason}")

    # Get status
    print("\n[2] Engine Status:")
    status = engine.get_status()
    for k, v in status.items():
        if k != 'daily_stats':
            print(f"    {k}: {v}")

    # Check market
    print("\n[3] Market Status:")
    clock = engine.trader.get_clock()
    print(f"    Open: {clock['is_open']}")
    print(f"    Next Open: {clock['next_open']}")

    # Test scan (if screener available)
    if engine.screener:
        print("\n[4] Testing Scan (with Regime Filter):")
        signals = engine.scan_for_signals()
        if not is_bull:
            print("    ⚠️ Scan skipped due to BEAR market")
        else:
            print(f"    Found {len(signals)} signals (Score >= {engine.MIN_SCORE})")
            if signals:
                for i, s in enumerate(signals[:3]):
                    print(f"    [{i+1}] {s.symbol}: Score={s.score}")
    else:
        print("\n[4] Screener not available for testing")

    # Test position monitoring (if any positions)
    print("\n[5] Position Monitoring:")
    positions = engine.get_positions_status()
    if positions:
        for p in positions:
            print(f"    {p['symbol']}: ${p['current_price']:.2f} ({p['pnl_pct']:+.2f}%)")
    else:
        print("    No positions")

    print("\n" + "=" * 60)
    print("v4.0 ENGINE TEST COMPLETE")
    print("Expected: +5.5%/mo, DD 8.9%, WR 49%")
    print("=" * 60)

    return engine


if __name__ == "__main__":
    test_engine()
