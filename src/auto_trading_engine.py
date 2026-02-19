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

from trading_safety import TradingSafetySystem, SafetyStatus

# Broker abstraction layer
from engine.broker_interface import BrokerInterface, Position, Order
from engine.brokers import AlpacaBroker
from pdt_smart_guard import PDTSmartGuard, SellDecision, init_pdt_guard  # v6.10.1: PDTConfig deprecated
from trade_logger import get_trade_logger, TradeLogger
from loguru import logger

# v6.7: Import unified configuration
try:
    from config.strategy_config import RapidRotationConfig
except ImportError:
    RapidRotationConfig = None

# v6.8: Import SL/TP calculator
try:
    from strategies import SLTPCalculator, SLTPResult
except ImportError:
    SLTPCalculator = None

# v6.x: Import market utilities (Single Source of Truth)
try:
    from utils.market_hours import (
        MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
        MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
        PRE_CLOSE_MINUTE, PRE_CLOSE_HOUR,
        is_market_hours, is_pre_close, get_et_time
    )
    from utils.market_calendar import is_trading_day_today, get_market_calendar_status
    from utils.timeout import timeout  # Production Grade v6.21
    MARKET_UTILS_AVAILABLE = True
except ImportError:
    MARKET_UTILS_AVAILABLE = False
    # Fallback constants if utils not available
    MARKET_OPEN_HOUR = 9
    MARKET_OPEN_MINUTE = 30
    MARKET_CLOSE_HOUR = 16
    MARKET_CLOSE_MINUTE = 0
    PRE_CLOSE_HOUR = 15
    PRE_CLOSE_MINUTE = 50
    SLTPResult = None

# For Market Regime Filter
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not available - regime filter disabled")

# v6.9: Centralized data management (performance + caching)
try:
    from api.data_manager import DataManager
    DATA_MANAGER_AVAILABLE = True
except ImportError:
    DATA_MANAGER_AVAILABLE = False
    logger.warning("DataManager not available - using direct yfinance")

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

# VIX Adaptive Strategy v3.0
try:
    from strategies.vix_adaptive.engine_integration import VIXAdaptiveIntegration
    from strategies.vix_adaptive.data_enricher import add_vix_indicators_to_cache
    VIX_ADAPTIVE_AVAILABLE = True
except ImportError as e:
    VIX_ADAPTIVE_AVAILABLE = False
    logger.warning(f"VIX Adaptive Strategy not available: {e}")


# Phase 1 Refactor: Import models from engine module
from engine.models import (
    TradingState,
    SignalSource,
    ManagedPosition,
    DailyStats,
    QueuedSignal,
)

# Re-export for backwards compatibility (other files import from here)
__all__ = [
    'AutoTradingEngine',
    'TradingState',
    'SignalSource',
    'ManagedPosition',
    'DailyStats',
    'QueuedSignal',
]


class AutoTradingEngine:
    """
    Full-Auto Trading Engine for Rapid Trader v3.9

    Features:
    - Automatic signal detection and execution
    - Trailing stop management
    - Position monitoring every minute
    - Safety limits (max positions, daily loss limit)

    ⚠️  v6.1 CONFIG ARCHITECTURE:
        - ALL trading parameters come from config/trading.yaml (SINGLE SOURCE OF TRUTH)
        - Class attributes below are INITIALIZED FROM YAML at __init__
        - Only static/structural constants remain as class-level defaults
        - If YAML is missing → ConfigurationError (fail loud, not silent)
    """

    # =========================================================================
    # STATIC CONSTANTS — These are NOT configurable (structural/fixed)
    # =========================================================================

    # Market hours (ET timezone) — imported from utils.market_hours (Single Source of Truth)
    # MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, MARKET_CLOSE_HOUR, etc. are now imported at module level

    # Sector ETF mapping — structural, not trading param
    BEAR_SECTORS = {
        'Consumer Defensive': 'XLP',
        'Utilities': 'XLU',
        'Healthcare': 'XLV',
        'Energy': 'XLE',
        'Basic Materials': 'XLB',
        'Industrials': 'XLI',
    }
    BEAR_SECTOR_THRESHOLD = 3  # return_20d > 3% = sector is rising

    # System defaults (rarely changed)
    CIRCUIT_BREAKER_MAX_ERRORS = 5
    TARGET_RR = 2.0  # Target Risk:Reward ratio

    # =========================================================================
    # TRADING PARAMETERS — Loaded from YAML at __init__
    # These are declared here for type hints and IDE support only.
    # Actual values come from config/trading.yaml
    # =========================================================================

    # Position Management
    MAX_POSITIONS: int
    POSITION_SIZE_PCT: float
    MAX_POSITION_PCT: float
    RISK_PARITY_ENABLED: bool
    RISK_BUDGET_PCT: float

    # ATR-based SL/TP
    SL_ATR_MULTIPLIER: float
    SL_MIN_PCT: float
    SL_MAX_PCT: float
    TP_ATR_MULTIPLIER: float
    TP_MIN_PCT: float
    TP_MAX_PCT: float

    # Fallback fixed values
    STOP_LOSS_PCT: float
    TAKE_PROFIT_PCT: float
    PDT_TP_THRESHOLD: float

    # Trailing Stop
    TRAIL_ENABLED: bool
    TRAIL_ACTIVATION_PCT: float
    TRAIL_LOCK_PCT: float
    MAX_HOLD_DAYS: int

    # Risk Limits
    DAILY_LOSS_LIMIT_PCT: float
    WEEKLY_LOSS_LIMIT_PCT: float
    MAX_CONSECUTIVE_LOSSES: int
    MIN_SCORE: int

    # Signal Queue
    QUEUE_ENABLED: bool
    QUEUE_ATR_MULT: float
    QUEUE_MIN_DEVIATION: float
    QUEUE_MAX_DEVIATION: float
    QUEUE_MAX_SIZE: int
    QUEUE_FRESHNESS_WINDOW: int
    QUEUE_RESCAN_ON_EMPTY: bool

    # Sector Management
    SECTOR_FILTER_ENABLED: bool
    MAX_PER_SECTOR: int
    SECTOR_LOSS_TRACKING_ENABLED: bool
    MAX_SECTOR_CONSECUTIVE_LOSS: int
    SECTOR_COOLDOWN_DAYS: int

    # Smart Order
    SMART_ORDER_ENABLED: bool
    SMART_ORDER_MAX_SPREAD_PCT: float
    SMART_ORDER_WAIT_SECONDS: int

    # Gap Filter
    GAP_FILTER_ENABLED: bool
    GAP_MAX_UP: float
    GAP_MAX_DOWN: float

    # Earnings Filter
    EARNINGS_FILTER_ENABLED: bool
    EARNINGS_SKIP_DAYS_BEFORE: int
    EARNINGS_SKIP_DAYS_AFTER: int
    EARNINGS_NO_DATA_ACTION: str
    EARNINGS_AUTO_SELL: bool
    EARNINGS_AUTO_SELL_BUFFER_MIN: int

    # Low Risk Mode
    LOW_RISK_MODE_ENABLED: bool
    LOW_RISK_GAP_MAX_UP: float
    LOW_RISK_MIN_SCORE: int
    LOW_RISK_POSITION_SIZE_PCT: float
    LOW_RISK_MAX_ATR_PCT: float

    # Late Start Protection
    LATE_START_PROTECTION: bool
    MARKET_OPEN_SCAN_DELAY: int
    MARKET_OPEN_SCAN_WINDOW: int

    # Afternoon Scan
    AFTERNOON_SCAN_ENABLED: bool
    AFTERNOON_SCAN_HOUR: int
    AFTERNOON_SCAN_MINUTE: int
    AFTERNOON_MIN_SCORE: int
    AFTERNOON_GAP_MAX_UP: float
    AFTERNOON_GAP_MAX_DOWN: float

    # Continuous Scan (v6.3)
    CONTINUOUS_SCAN_ENABLED: bool
    CONTINUOUS_SCAN_INTERVAL_MINUTES: int      # Slow interval (11:00-16:00)
    CONTINUOUS_SCAN_VOLATILE_INTERVAL: int     # Volatile interval (09:35-11:00)
    CONTINUOUS_SCAN_VOLATILE_END_HOUR: int     # Volatile period ends at this hour
    CONTINUOUS_SCAN_MIDDAY_HOUR: int

    # BEAR Mode
    BEAR_MODE_ENABLED: bool
    BEAR_MAX_POSITIONS: int
    BEAR_MIN_SCORE: int
    BEAR_GAP_MAX_UP: float
    BEAR_GAP_MAX_DOWN: float
    BEAR_POSITION_SIZE_PCT: float
    BEAR_MAX_ATR_PCT: float

    # BULL Sector Filter
    BULL_SECTOR_FILTER_ENABLED: bool
    BULL_SECTOR_MIN_RETURN: float

    # Quant Research Findings
    STOCK_D_FILTER_ENABLED: bool
    BEAR_DD_CONTROL_EXEMPT: bool

    # Stock Quality Filters (v6.2)
    MAX_RSI_ENTRY: float = None  # Optional: block RSI > this value
    AVOID_MOM_RANGE: list = None  # Optional: [min, max] momentum range to skip

    # Conviction Sizing
    CONVICTION_SIZING_ENABLED: bool
    CONVICTION_A_PLUS_PCT: float
    CONVICTION_A_PCT: float
    CONVICTION_B_PCT: float

    # Smart Day Trade
    SMART_DAY_TRADE_ENABLED: bool
    DAY_TRADE_GAP_THRESHOLD: float
    DAY_TRADE_MOMENTUM_THRESHOLD: float
    DAY_TRADE_EMERGENCY_ENABLED: bool

    # Overnight Gap Scanner
    OVERNIGHT_GAP_ENABLED: bool
    OVERNIGHT_GAP_SCAN_HOUR: int
    OVERNIGHT_GAP_SCAN_MINUTE: int
    OVERNIGHT_GAP_MIN_SCORE: int
    OVERNIGHT_GAP_POSITION_PCT: float
    OVERNIGHT_GAP_TARGET_PCT: float
    OVERNIGHT_GAP_SL_PCT: float

    # Breakout Scanner
    BREAKOUT_SCAN_ENABLED: bool
    BREAKOUT_MIN_VOLUME_MULT: float
    BREAKOUT_MIN_SCORE: int
    BREAKOUT_TARGET_PCT: float
    BREAKOUT_SL_PCT: float

    # Post-Earnings Momentum (PEM)
    PEM_ENABLED: bool
    PEM_GAP_THRESHOLD_PCT: float
    PEM_VOLUME_EARLY_RATIO_MIN: float
    PEM_SCAN_HOUR: int
    PEM_SCAN_MINUTE: int
    PEM_MAX_POSITIONS: int
    PEM_POSITION_SIZE_PCT: float
    PEM_SL_PCT: float

    # Market Regime Filter
    REGIME_FILTER_ENABLED: bool
    REGIME_SMA_PERIOD: int
    REGIME_RSI_MIN: float
    REGIME_RETURN_5D_MIN: float
    REGIME_VIX_MAX: float

    # Simulated capital
    SIMULATED_CAPITAL: float

    # Monitor interval
    MONITOR_INTERVAL_SECONDS: int

    def __init__(
        self,
        api_key: str = None,
        secret_key: str = None,
        paper: bool = True,
        auto_start: bool = False,
        config: 'RapidRotationConfig' = None
    ):
        """
        Initialize trading engine

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            paper: Use paper trading account
            auto_start: Start engine automatically
            config: Optional RapidRotationConfig for core strategy parameters (v6.7)
        """

        # =====================================================================
        # v6.7: LOAD UNIFIED CONFIG FIRST (for core parameters)
        # Then load extended parameters from YAML
        # =====================================================================
        self._core_config = config
        if self._core_config is None and RapidRotationConfig is not None:
            # Try to load from default YAML
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'config', 'trading.yaml'
            )
            if os.path.exists(config_path):
                try:
                    self._core_config = RapidRotationConfig.from_yaml(config_path)
                except Exception as e:
                    logger.warning(f"Failed to load RapidRotationConfig: {e}")

        # Load all parameters from YAML (including extended ones)
        self._load_config_from_yaml()

        # Broker abstraction layer (Phase 3: supports Alpaca, Mock, future brokers)
        self.broker: BrokerInterface = AlpacaBroker(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper
        )

        # v6.9: Centralized data manager (performance + caching)
        if DATA_MANAGER_AVAILABLE:
            self.data_manager = DataManager(broker=self.broker)
            logger.info("DataManager initialized with broker integration")
        else:
            self.data_manager = None
            logger.warning("DataManager unavailable - using direct yfinance calls")

        # Safety system — v6.17: Pass RapidRotationConfig directly (not dict!)
        # This ensures ALL config values (including PDT_ENFORCE_ALWAYS) are loaded
        self.safety = TradingSafetySystem(self.broker, config=self._core_config)

        # PDT Smart Guard v2.3 (v6.10.1: Simplified - uses RapidRotationConfig directly)
        self.pdt_guard = init_pdt_guard(
            broker=self.broker,
            config=self._core_config  # v6.10.1: Pass RapidRotationConfig directly (no mapping!)
        )
        logger.info("PDT Smart Guard v2.3 initialized (No Override - uses RapidRotationConfig)")

        # Trade Logger v1.0
        self.trade_logger = get_trade_logger()
        logger.info("Trade Logger v1.0 initialized")

        # Alert Manager v1.0
        from alert_manager import get_alert_manager
        self.alerts = get_alert_manager()
        logger.info("Alert Manager v1.0 initialized")

        # v6.17: Entry Protection Filter (3-layer entry protection)
        try:
            from filters import EntryProtectionFilter
            self.entry_protection = EntryProtectionFilter(config=self._core_config)
            logger.info("✅ Entry Protection Filter v6.17 initialized")
        except Exception as e:
            logger.warning(f"Entry Protection Filter init failed: {e}")
            self.entry_protection = None

        # Screener
        self.screener = None
        if SCREENER_AVAILABLE:
            try:
                self.screener = RapidRotationScreener()
                logger.info("Screener initialized")
            except Exception as e:
                logger.error(f"Failed to init screener: {e}")

        # v4.9.4: Additional scanners (overnight gap + breakout)
        self.overnight_scanner = None
        self.breakout_scanner = None
        self.premarket_gap_scanner = None  # v6.11: Pre-market gap scanner

        if self.OVERNIGHT_GAP_ENABLED:
            try:
                from screeners.overnight_gap_scanner import OvernightGapScanner
                self.overnight_scanner = OvernightGapScanner()
                logger.info("OvernightGapScanner initialized")
            except Exception as e:
                logger.warning(f"OvernightGapScanner init failed: {e}")
        if self.BREAKOUT_SCAN_ENABLED:
            try:
                from screeners.breakout_scanner import BreakoutScanner
                self.breakout_scanner = BreakoutScanner()
                logger.info("BreakoutScanner initialized")
            except Exception as e:
                logger.warning(f"BreakoutScanner init failed: {e}")

        # v6.11: Pre-Market Gap Scanner (100% win rate, 6AM-9:30AM)
        try:
            from screeners.premarket_gap_scanner import PreMarketGapScanner
            self.premarket_gap_scanner = PreMarketGapScanner()
            logger.info("✅ PreMarketGapScanner initialized (v6.11)")
        except Exception as e:
            logger.warning(f"PreMarketGapScanner init failed: {e}")

        # v6.29: Post-Earnings Momentum (PEM) Scanner
        self.pem_screener = None
        if self.PEM_ENABLED:
            try:
                from screeners.pem_screener import PEMScreener
                pem_config = {
                    'pem_gap_threshold_pct': self.PEM_GAP_THRESHOLD_PCT,
                    'pem_volume_early_ratio_min': self.PEM_VOLUME_EARLY_RATIO_MIN,
                }
                self.pem_screener = PEMScreener(broker=self.broker, config=pem_config)
                logger.info("✅ PEMScreener initialized (v6.29)")
            except Exception as e:
                logger.warning(f"PEMScreener init failed: {e}")

        # VIX Adaptive Strategy v3.0
        self.vix_adaptive = None
        if VIX_ADAPTIVE_AVAILABLE and self.VIX_ADAPTIVE_ENABLED:
            try:
                self.vix_adaptive = VIXAdaptiveIntegration(
                    config_path='config/vix_adaptive.yaml',
                    enabled=True
                )
                logger.info(f"✅ VIX Adaptive Strategy initialized: {self.vix_adaptive}")
            except Exception as e:
                logger.warning(f"VIX Adaptive init failed: {e}")

        # v6.8: SL/TP Calculator (unified calculation logic)
        if SLTPCalculator is not None:
            self.sltp_calculator = SLTPCalculator(config=self._core_config)
            logger.info("SLTPCalculator initialized")
        else:
            self.sltp_calculator = None

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

        # v5.3: Track last skip reason for UI display
        self._last_skip_reason: str = ""

        # Regime cache (v4.2) - avoid repeated yfinance calls
        self._regime_cache: Optional[Tuple[bool, str, datetime, Dict]] = None
        # v5.0: Scan log lock (prevent concurrent writes from losing data)
        self._scan_log_lock = threading.Lock()
        # v6.3: Scan mutex (prevent concurrent scans from refresh spam)
        self._scan_lock = threading.Lock()
        self._regime_cache_seconds = 120  # v6.21: Increase to 120s to reduce API calls
        # v6.21: Cache bear sectors to prevent redundant checks
        self._bear_sectors_cache: Optional[Tuple[List[str], datetime]] = None
        self._bear_sectors_cache_seconds = 120

        # Timezone
        self.et_tz = pytz.timezone('US/Eastern')

        # State directory for queue and other JSON state files
        self._state_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        os.makedirs(self._state_dir, exist_ok=True)
        self._queue_file = os.path.join(self._state_dir, 'signal_queue.json')

        # v5.1 P1-9: Track Alpaca position count for max_positions enforcement
        self._alpaca_position_count = 0

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
    # v6.1: CONFIG LOADER — YAML as Single Source of Truth
    # =========================================================================

    def _load_config_from_yaml(self):
        """
        Load trading parameters from RapidRotationConfig.
    
        v6.10 Architecture (FULL MIGRATION):
        - ALL parameters from RapidRotationConfig (single source of truth)
        - No more trading_config.py dependency
        - Backward compatible with YAML loading via RapidRotationConfig.from_yaml()
    
        Raises:
            ValueError: If RapidRotationConfig not available or invalid
        """
        # Ensure we have config (load from YAML if not provided)
        if self._core_config is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'trading.yaml'
            )
            
            if not os.path.exists(config_path):
                raise ValueError(f"Config file not found: {config_path}")
            
            try:
                from config.strategy_config import RapidRotationConfig
                self._core_config = RapidRotationConfig.from_yaml(config_path)
                logger.info(f"Loaded RapidRotationConfig from {config_path}")
            except Exception as e:
                logger.critical(f"Failed to load RapidRotationConfig: {e}")
                raise ValueError(f"Cannot load configuration: {e}")
        
        # Shorthand
        cfg = self._core_config
        
        # =====================================================================
        # CORE PARAMETERS
        # =====================================================================
        # SL/TP
        self.SL_ATR_MULTIPLIER = cfg.atr_sl_multiplier
        self.SL_MIN_PCT = cfg.min_sl_pct
        self.SL_MAX_PCT = cfg.max_sl_pct
        self.TP_ATR_MULTIPLIER = cfg.atr_tp_multiplier
        self.TP_MIN_PCT = cfg.min_tp_pct
        self.TP_MAX_PCT = cfg.max_tp_pct
        self.STOP_LOSS_PCT = cfg.default_sl_pct
        self.TAKE_PROFIT_PCT = cfg.default_tp_pct
        self.TRAIL_ACTIVATION_PCT = cfg.trail_activation_pct
        self.TRAIL_LOCK_PCT = cfg.trail_lock_pct
        
        # Position Management
        self.MAX_HOLD_DAYS = cfg.max_hold_days
        self.MAX_POSITIONS = cfg.max_positions
        self.POSITION_SIZE_PCT = cfg.position_size_pct
        self.MAX_POSITION_PCT = cfg.max_position_pct
        self.RISK_PARITY_ENABLED = cfg.risk_parity_enabled
        self.RISK_BUDGET_PCT = cfg.risk_budget_pct
        self.SIMULATED_CAPITAL = cfg.simulated_capital
        self.PDT_TP_THRESHOLD = cfg.pdt_tp_threshold
        self.TRAIL_ENABLED = cfg.trail_enabled
        
        # Risk Limits
        self.DAILY_LOSS_LIMIT_PCT = cfg.daily_loss_limit_pct
        self.WEEKLY_LOSS_LIMIT_PCT = cfg.weekly_loss_limit_pct
        self.MAX_CONSECUTIVE_LOSSES = cfg.max_consecutive_losses
        
        # Scoring
        self.MIN_SCORE = cfg.min_score
        self.MAX_RSI_ENTRY = cfg.max_rsi_entry
        self.AVOID_MOM_RANGE = cfg.avoid_mom_range
        
        # Market Hours
        self.MARKET_OPEN_HOUR = cfg.market_open_hour
        self.MARKET_OPEN_MINUTE = cfg.market_open_minute
        self.MARKET_CLOSE_HOUR = cfg.market_close_hour
        self.MARKET_CLOSE_MINUTE = cfg.market_close_minute
        self.PRE_CLOSE_MINUTE = cfg.pre_close_minute
        
        # =====================================================================
        # REGIME FILTERING
        # =====================================================================
        self.REGIME_FILTER_ENABLED = cfg.regime_filter_enabled
        self.REGIME_SMA_PERIOD = cfg.regime_sma_period
        self.REGIME_RSI_MIN = cfg.regime_rsi_min
        self.REGIME_RETURN_5D_MIN = cfg.regime_return_5d_min
        self.REGIME_VIX_MAX = cfg.regime_vix_max
        self.VIX_SKIP_ZONE_ENABLED = cfg.vix_skip_zone_enabled
        self.VIX_SKIP_ZONE_LOW = cfg.vix_skip_zone_low
        self.VIX_SKIP_ZONE_HIGH = cfg.vix_skip_zone_high
        self.OPENING_WINDOW_LIMIT_ENABLED = cfg.opening_window_limit_enabled
        self.OPENING_WINDOW_MINUTES = cfg.opening_window_minutes
        self.OPENING_WINDOW_MAX_BUYS = cfg.opening_window_max_buys
        self._opening_window_buys = 0       # resets each trading day
        self._opening_window_date = None    # tracks which date the counter is for
        self.SPY_INTRADAY_FILTER_ENABLED = cfg.spy_intraday_filter_enabled
        self.SPY_INTRADAY_FILTER_PCT = cfg.spy_intraday_filter_pct
        self.VIX_SPIKE_PROTECTION_ENABLED = cfg.vix_spike_protection_enabled
        self.VIX_SPIKE_PCT = cfg.vix_spike_pct
        self.VIX_SPIKE_SL_TIGHTEN_PCT = cfg.vix_spike_sl_tighten_pct
        
        # =====================================================================
        # SIGNAL QUEUE
        # =====================================================================
        self.QUEUE_ENABLED = cfg.queue_enabled
        self.QUEUE_ATR_MULT = cfg.queue_atr_mult
        self.QUEUE_MIN_DEVIATION = cfg.queue_min_deviation
        self.QUEUE_MAX_DEVIATION = cfg.queue_max_deviation
        self.QUEUE_MAX_SIZE = cfg.queue_max_size
        self.QUEUE_FRESHNESS_WINDOW = cfg.queue_freshness_window
        self.QUEUE_RESCAN_ON_EMPTY = cfg.queue_rescan_on_empty
        
        # =====================================================================
        # SECTOR MANAGEMENT
        # =====================================================================
        self.SECTOR_FILTER_ENABLED = cfg.sector_filter_enabled
        self.MAX_PER_SECTOR = cfg.max_per_sector
        self.SECTOR_LOSS_TRACKING_ENABLED = cfg.sector_loss_tracking_enabled
        self.MAX_SECTOR_CONSECUTIVE_LOSS = cfg.max_sector_consecutive_loss
        self.SECTOR_COOLDOWN_DAYS = cfg.sector_cooldown_days
        # Dynamic Sector Gate (VIX-based quota)
        self.DYNAMIC_SECTOR_GATE_ENABLED = cfg.dynamic_sector_gate_enabled
        self.SECTOR_GATE_NORMAL_MAX = cfg.sector_gate_normal_max
        self.SECTOR_GATE_SKIP_MAX = cfg.sector_gate_skip_max
        self.SECTOR_GATE_HIGH_MAX = cfg.sector_gate_high_max
        self.SECTOR_GATE_EXTREME_MAX = cfg.sector_gate_extreme_max
        
        # =====================================================================
        # SMART ORDER
        # =====================================================================
        self.SMART_ORDER_ENABLED = cfg.smart_order_enabled
        self.SMART_ORDER_MAX_SPREAD_PCT = cfg.smart_order_max_spread_pct
        self.SMART_ORDER_WAIT_SECONDS = cfg.smart_order_wait_seconds
        
        # =====================================================================
        # GAP FILTER
        # =====================================================================
        self.GAP_FILTER_ENABLED = cfg.gap_filter_enabled
        self.GAP_MAX_UP = cfg.gap_max_up
        self.GAP_MAX_DOWN = cfg.gap_max_down
        
        # =====================================================================
        # EARNINGS FILTER
        # =====================================================================
        self.EARNINGS_FILTER_ENABLED = cfg.earnings_filter_enabled
        self.EARNINGS_SKIP_DAYS_BEFORE = cfg.earnings_skip_days_before
        self.EARNINGS_SKIP_DAYS_AFTER = cfg.earnings_skip_days_after
        self.EARNINGS_NO_DATA_ACTION = cfg.earnings_no_data_action
        self.EARNINGS_AUTO_SELL = cfg.earnings_auto_sell
        self.EARNINGS_AUTO_SELL_BUFFER_MIN = cfg.earnings_auto_sell_buffer_min
        
        # =====================================================================
        # LOW RISK MODE
        # =====================================================================
        self.LOW_RISK_MODE_ENABLED = cfg.low_risk_mode_enabled
        self.LOW_RISK_GAP_MAX_UP = cfg.low_risk_gap_max_up
        self.LOW_RISK_MIN_SCORE = cfg.low_risk_min_score
        self.LOW_RISK_POSITION_SIZE_PCT = cfg.low_risk_position_size_pct
        self.LOW_RISK_MAX_ATR_PCT = cfg.low_risk_max_atr_pct
        
        # =====================================================================
        # LATE START PROTECTION
        # =====================================================================
        self.LATE_START_PROTECTION = cfg.late_start_protection
        self.MARKET_OPEN_SCAN_DELAY = cfg.market_open_scan_delay
        self.MARKET_OPEN_SCAN_WINDOW = cfg.market_open_scan_window
        
        # =====================================================================
        # AFTERNOON SCAN
        # =====================================================================
        self.AFTERNOON_SCAN_ENABLED = cfg.afternoon_scan_enabled
        self.AFTERNOON_SCAN_HOUR = cfg.afternoon_scan_hour
        self.AFTERNOON_SCAN_MINUTE = cfg.afternoon_scan_minute
        self.AFTERNOON_MIN_SCORE = cfg.afternoon_min_score
        self.AFTERNOON_GAP_MAX_UP = cfg.afternoon_gap_max_up
        self.AFTERNOON_GAP_MAX_DOWN = cfg.afternoon_gap_max_down

        # =====================================================================
        # INTRADAY PRE-FILTER REFRESH (v6.27)
        # =====================================================================
        self.PRE_FILTER_INTRADAY_ENABLED = getattr(cfg, 'pre_filter_intraday_enabled', True)
        self.PRE_FILTER_INTRADAY_SCHEDULE = getattr(cfg, 'pre_filter_intraday_schedule', [10, 13, 15])
        self.PRE_FILTER_INTRADAY_MINUTE = getattr(cfg, 'pre_filter_intraday_minute', 45)

        # =====================================================================
        # CONTINUOUS SCAN
        # =====================================================================
        self.CONTINUOUS_SCAN_ENABLED = cfg.continuous_scan_enabled
        self.CONTINUOUS_SCAN_INTERVAL_MINUTES = cfg.continuous_scan_interval_minutes
        self.CONTINUOUS_SCAN_VOLATILE_INTERVAL = cfg.continuous_scan_volatile_interval
        self.CONTINUOUS_SCAN_VOLATILE_END_HOUR = cfg.continuous_scan_volatile_end_hour
        self.CONTINUOUS_SCAN_MIDDAY_HOUR = cfg.continuous_scan_midday_hour

        # Dynamic scan (v6.18) - VIX-based interval
        self.CONTINUOUS_SCAN_DYNAMIC_ENABLED = getattr(cfg, 'continuous_scan_dynamic_enabled', False)
        self.CONTINUOUS_SCAN_VIX_THRESHOLD = getattr(cfg, 'continuous_scan_vix_threshold', 20.0)
        self.CONTINUOUS_SCAN_DYNAMIC_VOLATILE_INTERVAL = getattr(cfg, 'continuous_scan_dynamic_volatile_interval', 5)
        self.CONTINUOUS_SCAN_DYNAMIC_CALM_INTERVAL = getattr(cfg, 'continuous_scan_dynamic_calm_interval', 10)
        
        # =====================================================================
        # BEAR MODE
        # =====================================================================
        self.BEAR_MODE_ENABLED = cfg.bear_mode_enabled
        self.BEAR_MAX_POSITIONS = cfg.bear_max_positions
        self.BEAR_MIN_SCORE = cfg.bear_min_score
        self.BEAR_GAP_MAX_UP = cfg.bear_gap_max_up
        self.BEAR_GAP_MAX_DOWN = cfg.bear_gap_max_down
        self.BEAR_POSITION_SIZE_PCT = cfg.bear_position_size_pct
        self.BEAR_MAX_ATR_PCT = cfg.bear_max_atr_pct
        
        # =====================================================================
        # BULL SECTOR FILTER
        # =====================================================================
        self.BULL_SECTOR_FILTER_ENABLED = cfg.bull_sector_filter_enabled
        self.BULL_SECTOR_MIN_RETURN = cfg.bull_sector_min_return
        self.SECTOR_WEAK_RELATIVE_N = getattr(cfg, 'sector_weak_relative_n', 2)
        
        # =====================================================================
        # QUANT RESEARCH
        # =====================================================================
        self.STOCK_D_FILTER_ENABLED = cfg.stock_d_filter_enabled
        self.BEAR_DD_CONTROL_EXEMPT = cfg.bear_dd_control_exempt
        
        # =====================================================================
        # CONVICTION SIZING
        # =====================================================================
        self.CONVICTION_SIZING_ENABLED = cfg.conviction_sizing_enabled
        self.CONVICTION_A_PLUS_PCT = cfg.conviction_a_plus_pct
        self.CONVICTION_A_PCT = cfg.conviction_a_pct
        self.CONVICTION_B_PCT = cfg.conviction_b_pct
        
        # =====================================================================
        # SMART DAY TRADE
        # =====================================================================
        self.SMART_DAY_TRADE_ENABLED = cfg.smart_day_trade_enabled
        self.DAY_TRADE_GAP_THRESHOLD = cfg.day_trade_gap_threshold
        self.DAY_TRADE_MOMENTUM_THRESHOLD = cfg.day_trade_momentum_threshold
        self.DAY_TRADE_EMERGENCY_ENABLED = cfg.day_trade_emergency_enabled
        
        # =====================================================================
        # OVERNIGHT GAP SCANNER
        # =====================================================================
        self.OVERNIGHT_GAP_ENABLED = cfg.overnight_gap_enabled
        self.OVERNIGHT_GAP_SCAN_HOUR = cfg.overnight_gap_scan_hour
        self.OVERNIGHT_GAP_SCAN_MINUTE = cfg.overnight_gap_scan_minute
        self.OVERNIGHT_GAP_MIN_SCORE = cfg.overnight_gap_min_score
        self.OVERNIGHT_GAP_POSITION_PCT = cfg.overnight_gap_position_pct
        self.OVERNIGHT_GAP_TARGET_PCT = cfg.overnight_gap_target_pct
        self.OVERNIGHT_GAP_SL_PCT = cfg.overnight_gap_sl_pct
        
        # =====================================================================
        # BREAKOUT SCANNER
        # =====================================================================
        self.BREAKOUT_SCAN_ENABLED = cfg.breakout_scan_enabled
        self.BREAKOUT_MIN_VOLUME_MULT = cfg.breakout_min_volume_mult
        self.BREAKOUT_MIN_SCORE = cfg.breakout_min_score
        self.BREAKOUT_TARGET_PCT = cfg.breakout_target_pct
        self.BREAKOUT_SL_PCT = cfg.breakout_sl_pct

        # =====================================================================
        # POST-EARNINGS MOMENTUM (PEM) STRATEGY (v6.29)
        # =====================================================================
        self.PEM_ENABLED = getattr(cfg, 'pem_enabled', False)
        self.PEM_GAP_THRESHOLD_PCT = getattr(cfg, 'pem_gap_threshold_pct', 8.0)
        self.PEM_VOLUME_EARLY_RATIO_MIN = getattr(cfg, 'pem_volume_early_ratio_min', 0.15)
        self.PEM_SCAN_HOUR = getattr(cfg, 'pem_scan_hour', 9)
        self.PEM_SCAN_MINUTE = getattr(cfg, 'pem_scan_minute', 35)
        self.PEM_MAX_POSITIONS = getattr(cfg, 'pem_max_positions', 1)
        self.PEM_POSITION_SIZE_PCT = getattr(cfg, 'pem_position_size_pct', 33.0)
        self.PEM_SL_PCT = getattr(cfg, 'pem_sl_pct', 5.0)

        # =====================================================================
        # VIX ADAPTIVE STRATEGY v3.0
        # =====================================================================
        self.VIX_ADAPTIVE_ENABLED = cfg.vix_adaptive_enabled

        # =====================================================================
        # MONITOR
        # =====================================================================
        self.MONITOR_INTERVAL_SECONDS = cfg.monitor_interval_seconds
        
        logger.info("✅ Loaded ALL parameters from RapidRotationConfig (v6.10)")
        logger.info(f"   SL range: {self.SL_MIN_PCT}%-{self.SL_MAX_PCT}%")
        logger.info(f"   Max positions: {self.MAX_POSITIONS}")
        logger.info(f"   Regime filter: {'ENABLED' if self.REGIME_FILTER_ENABLED else 'DISABLED'}")
    
    
    def _save_positions_state(self):
        """Persist all ManagedPosition state to DB (single source of truth)."""
        self._sync_active_positions_db()

    # Engine sources that this engine owns (do NOT touch rapid_trader positions)
    _ENGINE_SOURCES = ('dip_bounce', 'vix_adaptive', 'mean_reversion', 'rapid_rotation')

    def _sync_active_positions_db(self):
        """Sync in-memory positions to DB via PositionRepository.
        Called after every _save_positions_state(). Non-critical: errors logged only.

        Scoped to engine-owned sources only — rapid_trader positions are NOT touched.
        """
        try:
            from database import PositionRepository
            from database.models.position import Position as DBPosition
            from datetime import datetime as _dt

            repo = PositionRepository()

            with self._positions_lock:
                positions_snapshot = dict(self.positions)

            current_symbols = list(positions_snapshot.keys())
            engine_sources = self._ENGINE_SOURCES
            src_placeholders = ','.join('?' * len(engine_sources))

            # Remove stale engine-owned positions (scoped — do NOT delete rapid_trader rows)
            if current_symbols:
                sym_placeholders = ','.join('?' * len(current_symbols))
                repo.db.execute(
                    f"DELETE FROM active_positions WHERE source IN ({src_placeholders}) AND symbol NOT IN ({sym_placeholders})",
                    list(engine_sources) + current_symbols
                )
            else:
                repo.db.execute(
                    f"DELETE FROM active_positions WHERE source IN ({src_placeholders})",
                    list(engine_sources)
                )

            # Upsert current engine positions
            for sym, pos in positions_snapshot.items():
                repo.db.execute("""
                    INSERT OR REPLACE INTO active_positions
                    (symbol, entry_date, entry_price, qty, stop_loss, take_profit,
                     peak_price, trough_price, trailing_stop, day_held, sl_pct, tp_pct,
                     entry_atr_pct, sl_order_id, sector, source, signal_score, mode,
                     regime, entry_rsi, momentum_5d, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    sym,
                    pos.entry_time.isoformat() if hasattr(pos.entry_time, 'isoformat') else pos.entry_time,
                    pos.entry_price, pos.qty,
                    pos.current_sl_price,
                    getattr(pos, 'tp_price', 0.0),
                    pos.peak_price,
                    getattr(pos, 'trough_price', 0.0),
                    1 if pos.trailing_active else 0,
                    pos.days_held,
                    pos.sl_pct,
                    getattr(pos, 'tp_pct', 5.0),
                    getattr(pos, 'atr_pct', 0.0),
                    pos.sl_order_id,
                    getattr(pos, 'sector', ''),
                    getattr(pos, 'source', 'dip_bounce'),
                    getattr(pos, 'signal_score', 0),
                    getattr(pos, 'entry_mode', 'NORMAL'),
                    getattr(pos, 'entry_regime', 'BULL'),
                    getattr(pos, 'entry_rsi', 0.0),
                    getattr(pos, 'momentum_5d', 0.0),
                    _dt.now().isoformat()
                ))

            logger.debug(f"✅ DB synced: {len(positions_snapshot)} positions via PositionRepository")
        except Exception as e:
            logger.warning(f"DB active_positions sync failed (non-critical): {e}")

    def _load_positions_state(self) -> Dict[str, dict]:
        """Load persisted position state from DB (single source of truth)."""
        try:
            from database import PositionRepository
            repo = PositionRepository()
            db_positions = repo.get_all(use_cache=False)
            positions = {}
            for db_pos in db_positions:
                positions[db_pos.symbol] = {
                    'entry_time': db_pos.entry_date.isoformat() if db_pos.entry_date else None,
                    'sl_order_id': db_pos.sl_order_id,
                    'current_sl_price': db_pos.stop_loss,
                    'peak_price': db_pos.peak_price,
                    'trailing_active': bool(db_pos.trailing_stop),
                    'sl_pct': db_pos.sl_pct,
                    'tp_price': db_pos.take_profit,
                    'tp_pct': db_pos.tp_pct,
                    'atr_pct': db_pos.entry_atr_pct,
                    'sector': db_pos.sector,
                    'trough_price': db_pos.trough_price,
                    'source': db_pos.source,
                    'signal_score': db_pos.signal_score,
                    'entry_mode': db_pos.mode,
                    'entry_regime': db_pos.regime,
                    'entry_rsi': db_pos.entry_rsi,
                    'momentum_5d': db_pos.momentum_5d,
                    'days_held': db_pos.day_held or 0,
                }
            if positions:
                logger.info(f"Loaded persisted state: {len(positions)} positions from DB")
            return positions
        except Exception as e:
            logger.warning(f"Failed to load persisted state from DB: {e}")
            return {}

    # =========================================================================
    # QUEUE STATE PERSISTENCE
    # =========================================================================

    def _save_queue_state(self):
        """Persist signal queue to JSON file (atomic write)."""
        from engine.state_manager import serialize_queued_signal, atomic_write_json
        try:
            entries = [serialize_queued_signal(q) for q in self.signal_queue]
            data = {'saved_at': datetime.now().isoformat(), 'count': len(entries), 'queue': entries}
            if atomic_write_json(self._queue_file, data):
                logger.debug(f"Queue state saved: {len(entries)} signals")
        except Exception as e:
            logger.error(f"Failed to save queue state: {e}")

    def _load_queue_state(self):
        """Load persisted signal queue from JSON file on startup."""
        from engine.state_manager import safe_read_json, deserialize_queued_signal
        data = safe_read_json(self._queue_file, {})
        entries = data.get('queue', [])
        loaded = 0
        expired = 0
        now = datetime.now()

        for entry in entries:
            try:
                queued = deserialize_queued_signal(entry, QueuedSignal)

                # Skip if already have position
                if queued.symbol in self.positions:
                    expired += 1
                    continue

                # Clear signals older than 24 hours (stale from previous day)
                age_hours = (now - queued.queued_at).total_seconds() / 3600
                if age_hours > 24:
                    expired += 1
                    logger.debug(f"Skipping stale queue entry: {queued.symbol} (age: {age_hours:.1f}h)")
                    continue

                self.signal_queue.append(queued)
                loaded += 1
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping invalid queue entry: {e}")

        if loaded:
            logger.info(f"Loaded persisted queue: {loaded} signals (saved at {data.get('saved_at', 'unknown')})")
        if expired:
            logger.info(f"Cleared {expired} stale/duplicate signals from queue")
            self._save_queue_state()  # Save cleaned queue

    # =========================================================================
    # SIGNALS CACHE (v6.1 - Single Source of Truth for UI)
    # =========================================================================

    def _save_signals_cache(self, signals: list, scan_type: str, scan_duration: float = 0,
                             waiting_signals: list = None, positions_status: dict = None):
        """
        Write signals to JSON cache file for UI consumption.

        This is the SINGLE SOURCE OF TRUTH for Buy Signals in the UI.
        UI reads from this cache instead of running its own scanner.

        v6.4: Added waiting_signals and positions_status for UI to show
              signals that are waiting for position slots to open.
        """
        import tempfile
        from dataclasses import asdict

        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, 'rapid_signals.json')

        try:
            # Convert signals to dict
            signals_data = []
            for s in signals:
                try:
                    d = asdict(s)
                    # @property fields not included by asdict
                    d['expected_gain'] = getattr(s, 'expected_gain', 0)
                    d['max_loss'] = getattr(s, 'max_loss', 0)
                    signals_data.append(d)
                except Exception:
                    # Fallback for non-dataclass signals
                    signals_data.append({
                        'symbol': getattr(s, 'symbol', ''),
                        'entry_price': getattr(s, 'entry_price', 0),
                        'score': getattr(s, 'score', 0),
                        'sector': getattr(s, 'sector', ''),
                        'stop_loss': getattr(s, 'stop_loss', 0),
                        'take_profit': getattr(s, 'take_profit', 0),
                    })

            # v6.4: Convert waiting signals to dict for UI display
            waiting_data = []
            if waiting_signals:
                for s in waiting_signals[:5]:  # Limit to 5 waiting signals
                    try:
                        d = asdict(s)
                        d['expected_gain'] = getattr(s, 'expected_gain', 0)
                        d['max_loss'] = getattr(s, 'max_loss', 0)
                        d['reason'] = 'positions_full'
                        waiting_data.append(d)
                    except Exception:
                        waiting_data.append({
                            'symbol': getattr(s, 'symbol', ''),
                            'entry_price': getattr(s, 'entry_price', 0),
                            'score': getattr(s, 'score', 0),
                            'sector': getattr(s, 'sector', ''),
                            'stop_loss': getattr(s, 'stop_loss', 0),
                            'take_profit': getattr(s, 'take_profit', 0),
                            'reason': 'positions_full',
                        })

            # Get market status
            is_market_open = False
            next_open = None
            next_close = None
            try:
                clock = self.broker.get_clock()
                is_market_open = clock.is_open
                next_open = clock.next_open
                next_close = clock.next_close
            except Exception:
                pass

            # Determine session
            et_now = self._get_et_time()
            if et_now.hour < 12:
                session = "Morning"
            elif et_now.hour < 14:
                session = "Midday"
            else:
                session = "Afternoon"

            # Calculate next scan time (with timestamp for UI countdown)
            next_scan = None
            next_scan_timestamp = None
            if is_market_open:
                # v6.3: Calculate next continuous scan time
                if self.CONTINUOUS_SCAN_ENABLED:
                    # Determine interval based on time (volatile vs normal)
                    is_volatile = et_now.hour < self.CONTINUOUS_SCAN_VOLATILE_END_HOUR
                    interval_min = self.CONTINUOUS_SCAN_VOLATILE_INTERVAL if is_volatile else self.CONTINUOUS_SCAN_INTERVAL_MINUTES
                    next_cont_scan = et_now + timedelta(minutes=interval_min)
                    # Don't scan past 15:45 (pre-close)
                    pre_close_cutoff = et_now.replace(hour=15, minute=45, second=0, microsecond=0)
                    if next_cont_scan < pre_close_cutoff:
                        next_scan = f"{next_cont_scan.strftime('%H:%M')} ET ({interval_min}min)"
                        next_scan_timestamp = next_cont_scan.isoformat()
                    else:
                        next_scan = "Tomorrow 09:35 ET"
                        next_scan_timestamp = None
                else:
                    # Legacy: fixed scan times
                    if et_now.hour < 14:
                        next_scan = "14:00 ET"
                        next_scan_timestamp = et_now.replace(hour=14, minute=0, second=0, microsecond=0).isoformat()
                    elif et_now.hour < 15 or (et_now.hour == 15 and et_now.minute < 30):
                        next_scan = "15:30 ET"
                        next_scan_timestamp = et_now.replace(hour=15, minute=30, second=0, microsecond=0).isoformat()
                    else:
                        next_scan = "Tomorrow 09:35 ET"
                        next_scan_timestamp = None
            else:
                next_scan = f"{next_open.strftime('%Y-%m-%d %H:%M ET')}" if next_open else "Next Market Open"
                next_scan_timestamp = next_open.isoformat() if next_open else None

            # v6.10: Get actual scanned universe size from screener
            pool_size = 0
            if self.screener and hasattr(self.screener, 'data_cache'):
                pool_size = len(self.screener.data_cache)

            cache_data = {
                'mode': 'market' if is_market_open else 'closed',
                'is_market_open': is_market_open,
                'timestamp': datetime.now().isoformat(),
                'scan_time': et_now.strftime('%Y-%m-%d %H:%M:%S ET'),
                'session': session,
                'scan_type': scan_type,
                'next_scan': next_scan,
                'next_scan_timestamp': next_scan_timestamp,  # v6.3: For UI countdown
                'next_open': next_open.isoformat() if next_open else None,
                'next_close': next_close.isoformat() if next_close else None,
                'count': len(signals_data),
                'signals': signals_data,
                'scan_duration_seconds': round(scan_duration, 1),
                'regime': self.daily_stats.regime_status if hasattr(self, 'daily_stats') else 'UNKNOWN',
                # v6.4: Waiting signals for UI display when positions full
                'waiting_signals': waiting_data,
                'positions_status': positions_status or {'current': len(self.positions), 'max': self.MAX_POSITIONS, 'is_full': len(self.positions) >= self.MAX_POSITIONS},
                # v6.10: Actual scanned universe size (not pre-filter pool)
                'pool_size': pool_size,
            }

            # Atomic write
            fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(cache_data, f, indent=2, default=str)
                os.replace(tmp_path, cache_file)
                waiting_info = f", {len(waiting_data)} waiting" if waiting_data else ""
                logger.info(f"📤 Signals cache: {len(signals_data)} signals{waiting_info} ({scan_type}, mode={cache_data['mode']})")
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

        except Exception as e:
            logger.warning(f"Failed to write signals cache: {e}")

    def _save_market_closed_cache(self):
        """Write market closed status to cache for UI."""
        from engine.state_manager import safe_read_json, atomic_write_json
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, 'rapid_signals.json')

        try:
            next_open = None
            try:
                next_open = self.broker.get_clock().next_open
            except Exception:
                pass

            old_data = safe_read_json(cache_file, {})
            cache_data = {
                'mode': 'closed', 'is_market_open': False, 'timestamp': datetime.now().isoformat(),
                'scan_time': old_data.get('scan_time'), 'session': 'Closed', 'scan_type': 'market_closed',
                'next_scan': f"{next_open.strftime('%Y-%m-%d %H:%M ET')}" if next_open else "Next Market Open",
                'next_open': next_open.isoformat() if next_open else None,
                'count': len(old_data.get('signals', [])), 'signals': old_data.get('signals', []),
                'scan_duration_seconds': 0, 'regime': 'CLOSED',
            }
            atomic_write_json(cache_file, cache_data)
        except Exception as e:
            logger.warning(f"Failed to write market closed cache: {e}")

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
            alpaca_positions = self.broker.get_positions()
            alpaca_orders = self.broker.get_orders(status='open')

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
                            entry_date = entry_time.date()  # v6.10: Update entry_date to match restored entry_time
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
                        days_held=saved.get('days_held', 0),
                        sl_pct=saved.get('sl_pct', self.STOP_LOSS_PCT),
                        tp_price=saved.get('tp_price', 0.0),
                        tp_pct=saved.get('tp_pct', self.TAKE_PROFIT_PCT),
                        atr_pct=saved.get('atr_pct', 0.0),
                        sector=saved.get('sector', ''),
                        trough_price=saved.get('trough_price', 0.0),
                        source=saved.get('source', 'dip_bounce'),  # v4.9.5: Restore signal source
                        signal_score=saved.get('signal_score', 0.0),  # v4.9.8: Restore for analytics
                        # v4.9.9: Restore entry context for analytics
                        entry_mode=saved.get('entry_mode', 'NORMAL'),
                        entry_regime=saved.get('entry_regime', 'BULL'),
                        entry_rsi=saved.get('entry_rsi', saved.get('rsi', 0.0)),  # v5.1 P3-23: backward compat
                        momentum_5d=saved.get('momentum_5d', 0.0),
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
                # Log exit trade for positions closed while engine was offline
                for sym in stale:
                    saved = persisted.get(sym, {})
                    try:
                        if self.trade_logger.has_sell_logged(sym, since_hours=72):
                            logger.debug(f"{sym}: SELL already in DB — skipping offline exit log")
                            continue
                        # Try to get actual fill price from Alpaca closed orders
                        exit_price = saved.get('current_sl_price', 0.0)
                        try:
                            closed_orders = self.broker.get_orders(status='closed')
                            fill = next(
                                (o for o in closed_orders
                                 if o.symbol == sym and o.side == 'sell' and o.status == 'filled'),
                                None
                            )
                            if fill and fill.filled_avg_price:
                                exit_price = fill.filled_avg_price
                        except Exception:
                            pass  # Use SL price as fallback
                        entry_price = saved.get('entry_price', 0.0)
                        qty = saved.get('qty', 0)
                        if entry_price and qty and exit_price:
                            pnl_pct = (exit_price - entry_price) / entry_price * 100
                            pnl_usd = (exit_price - entry_price) * qty
                            self.trade_logger.log_sell(
                                symbol=sym, qty=qty, price=exit_price,
                                reason="SL_FILLED_WHILE_OFFLINE",
                                entry_price=entry_price, pnl_usd=pnl_usd, pnl_pct=pnl_pct,
                                day_held=0, sl_price=saved.get('current_sl_price', exit_price),
                                trail_active=saved.get('trailing_active', False),
                                peak_price=saved.get('peak_price', entry_price),
                                signal_score=saved.get('signal_score', 0),
                                sector=saved.get('sector', ''),
                                atr_pct=saved.get('atr_pct', 0),
                                signal_source=saved.get('source', 'dip_bounce'),
                                mode=saved.get('entry_mode', 'NORMAL'),
                                regime=saved.get('entry_regime', 'BULL'),
                                entry_rsi=saved.get('entry_rsi', 0),
                                momentum_5d=saved.get('momentum_5d', 0),
                            )
                            logger.warning(
                                f"⚠️ Offline exit logged for {sym}: {pnl_pct:+.2f}% (${pnl_usd:+.2f}) "
                                f"@ ${exit_price:.2f} (SL_FILLED_WHILE_OFFLINE)"
                            )
                    except Exception as e:
                        logger.warning(f"Could not log offline exit for {sym}: {e}")

            # ===================================================================
            # v6.21 PRODUCTION GRADE: Position Sync Recovery (Phase 1 Item 2)
            # ===================================================================
            # Check for missing SL orders and create them
            positions_without_sl = []
            for symbol, managed_pos in self.positions.items():
                if not managed_pos.sl_order_id:
                    positions_without_sl.append(symbol)
                    logger.error(
                        f"⚠️ CRITICAL: Position {symbol} has no SL order! "
                        f"Qty: {managed_pos.qty}, Entry: ${managed_pos.entry_price:.2f}"
                    )

                    # AUTO-RECOVERY: Create SL order immediately
                    try:
                        sl_price = managed_pos.current_sl_price or (managed_pos.entry_price * 0.975)
                        logger.info(f"🔧 AUTO-RECOVERY: Creating SL order for {symbol} @ ${sl_price:.2f}")

                        sl_order = self.broker.place_stop_loss(
                            symbol=symbol,
                            qty=managed_pos.qty,
                            stop_price=sl_price
                        )

                        managed_pos.sl_order_id = sl_order.id
                        logger.info(f"✅ AUTO-RECOVERY: SL order created for {symbol} (Order ID: {sl_order.id})")

                        # Send alert
                        self.alerts.alert_position_sync(
                            symbol=symbol,
                            issue="missing_sl_order",
                            action="created_sl_order",
                            details=f"SL @ ${sl_price:.2f}"
                        )

                    except Exception as e:
                        logger.error(f"❌ AUTO-RECOVERY FAILED for {symbol}: {e}")

                        # v6.21: Add to DLQ for manual review
                        try:
                            from engine.dead_letter_queue import get_dlq
                            dlq = get_dlq()
                            dlq.add(
                                operation_type="position_sync_sl_creation",
                                operation_data={
                                    'symbol': symbol,
                                    'qty': managed_pos.qty,
                                    'entry_price': managed_pos.entry_price,
                                    'sl_price': sl_price
                                },
                                error=str(e),
                                context={
                                    'position': asdict(managed_pos),
                                    'recovery_attempt': 'auto'
                                }
                            )
                        except Exception as dlq_error:
                            logger.error(f"Failed to add to DLQ: {dlq_error}")

                        # Send critical alert
                        self.alerts.alert_position_sync(
                            symbol=symbol,
                            issue="missing_sl_order_recovery_failed",
                            action="manual_intervention_required",
                            details=str(e)
                        )

            # Check for quantity mismatches
            for pos in alpaca_positions:
                if pos.symbol in self.positions:
                    local_qty = self.positions[pos.symbol].qty
                    alpaca_qty = int(pos.qty)

                    if local_qty != alpaca_qty:
                        logger.warning(
                            f"⚠️ Quantity mismatch for {pos.symbol}: "
                            f"Local={local_qty}, Alpaca={alpaca_qty} → Syncing to Alpaca (source of truth)"
                        )
                        self.positions[pos.symbol].qty = alpaca_qty

                        # Send alert for significant mismatches (> 10%)
                        if abs(local_qty - alpaca_qty) / alpaca_qty > 0.1:
                            self.alerts.alert_position_sync(
                                symbol=pos.symbol,
                                issue="quantity_mismatch",
                                action="synced_to_broker",
                                details=f"Local {local_qty} → Alpaca {alpaca_qty}"
                            )

            # Update position count cache
            self._alpaca_position_count = len(alpaca_positions)

            # Log sync summary
            logger.info(f"✅ Synced {len(self.positions)} positions")
            if positions_without_sl:
                logger.warning(
                    f"⚠️ Position sync recovery: {len(positions_without_sl)} positions had missing SL orders. "
                    f"Auto-recovery attempted for: {', '.join(positions_without_sl)}"
                )

            self.pdt_guard.log_status()

            # Save clean state
            if self.positions:
                self._save_positions_state()

        except Exception as e:
            logger.error(f"❌ Failed to sync positions: {e}")
            # Send critical alert if sync fails
            try:
                self.alerts.alert_position_sync(
                    symbol="ALL",
                    issue="sync_failed",
                    action="retry_on_next_cycle",
                    details=str(e)
                )
            except:
                pass  # Don't fail on alert failure

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

    def _get_spy_data_from_broker(self, days: int = 60) -> Optional[pd.DataFrame]:
        """
        v4.7 Fix #8: Get SPY historical data from broker.
        Returns a DataFrame with 'Close' column, or None on failure.
        Uses BrokerInterface.get_bars() for broker-agnostic access.
        """
        try:
            from datetime import timezone
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=days + 5)  # Extra buffer for weekends

            # Use broker interface method (returns List[Bar] with standard attributes)
            bars = self.broker.get_bars(
                symbol='SPY',
                timeframe='1Day',
                start=start,
                end=end,
                limit=days + 5
            )
            if not bars:
                return None

            # Bar dataclass uses standard attributes: close, high, low, open, volume
            data = []
            for bar in bars:
                data.append({
                    'Close': bar.close,
                    'High': bar.high,
                    'Low': bar.low,
                    'Open': bar.open,
                    'Volume': bar.volume,
                })
            df = pd.DataFrame(data)
            if len(df) >= 20:
                logger.debug(f"SPY data from broker: {len(df)} bars")
                return df
            return None
        except Exception as e:
            logger.debug(f"Broker SPY data failed: {e}")
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
        # v5.1: Shorter TTL (60s) when VIX was a fallback value
        if not force_refresh and self._regime_cache:
            is_bull, reason, cached_at = self._regime_cache[0], self._regime_cache[1], self._regime_cache[2]
            details = self._regime_cache[3] if len(self._regime_cache) > 3 else {}
            cache_ttl = 45 if details.get('vix_is_fallback') else self._regime_cache_seconds  # v6.11: 60s→45s for faster VIX recovery
            age_seconds = (datetime.now() - cached_at).total_seconds()
            if age_seconds < cache_ttl:
                return is_bull, reason

        try:
            # v4.7 Fix #8: Try Alpaca bars first, fall back to yfinance
            spy = self._get_spy_data_from_broker(60)
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
            vix_val, vix_is_fallback = self._get_vix()

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

            # v4.2: Cache result (v4.9.5: add SPY details for UI)
            # v5.1: Track VIX fallback — use shorter cache TTL if VIX was unreliable
            self._regime_cache = (is_bull, reason, datetime.now(), {
                'spy_price': round(current_price, 2),
                'spy_sma20': round(sma, 2),
                'pct_above_sma': round(pct_above, 2),
                'rsi': round(rsi_val, 1),
                'return_5d': round(return_5d, 2),
                'vix': round(vix_val, 1),
                'vix_is_fallback': vix_is_fallback,
                'sma_ok': sma_ok,
                'rsi_ok': rsi_ok,
                'ret5d_ok': ret5d_ok,
                'vix_ok': vix_ok,
            })
            if vix_is_fallback:
                logger.warning(f"VIX={vix_val:.1f} is FALLBACK — cache TTL shortened to 60s")
            return is_bull, reason

        except Exception as e:
            logger.error(f"Regime check failed: {e} — blocking trades (fail-closed)")
            return False, f"Data unavailable: {e}"

    def _should_skip_before_holiday(self) -> Tuple[bool, str]:
        """
        Check if should skip new positions due to upcoming holiday (v4.7).

        Returns:
            (should_skip, reason)

        Examples:
            - Friday before 3-day weekend → skip
            - Day before holiday → skip
            - Normal day → don't skip
        """
        # Check if feature is enabled in config (v6.10: use RapidRotationConfig)
        if not (self._core_config.skip_before_holiday if self._core_config else True):
            return False, "Holiday check disabled in config"

        if not hasattr(self.broker, 'get_calendar'):
            return False, "Calendar check not available"

        try:
            # Check if tomorrow is a trading day
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            calendar = self.broker.get_calendar(start=tomorrow, end=tomorrow)

            if not calendar:
                # Tomorrow is not a trading day
                day_name = datetime.now().strftime('%A')

                # Check if it's Friday (weekend is expected)
                if datetime.now().weekday() == 4:  # Friday
                    # Check if Monday is also holiday (3-day weekend)
                    monday = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
                    monday_cal = self.broker.get_calendar(start=monday, end=monday)
                    if not monday_cal:
                        return True, f"⚠️ 3-day weekend ahead (Fri→Mon closed) - skipping new positions"
                    else:
                        return False, f"Regular weekend (normal Friday)"
                else:
                    # Weekday before holiday
                    return True, f"⚠️ Tomorrow is holiday ({day_name}) - skipping new positions"

            return False, "Tomorrow is trading day"

        except Exception as e:
            logger.warning(f"Calendar check failed: {e} - proceeding with trades")
            return False, f"Calendar check failed: {e}"

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

            # Guard against NaN from insufficient data
            import math
            if math.isnan(avg_gain) or math.isnan(avg_loss):
                return 50.0
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            return 50.0 if math.isnan(rsi) else rsi
        except Exception:
            return 50.0  # default neutral

    def _get_vix(self) -> Tuple[float, bool]:
        """Fetch current VIX value with retry. Returns (value, is_fallback).
        Returns (50.0, True) on error (fail-safe → BEAR)."""
        for attempt in range(2):
            try:
                vix = yf.download('^VIX', period='5d', progress=False)
                if vix.empty:
                    if attempt == 0:
                        logger.warning("VIX data empty — retrying in 3s...")
                        time.sleep(3)
                        continue
                    logger.warning("VIX data empty after retry — fail-safe: 50.0")
                    return 50.0, True
                close = vix['Close']
                # Handle yfinance MultiIndex columns: ('Close', '^VIX')
                if hasattr(close, 'columns'):
                    close = close.iloc[:, 0]
                val = float(close.iloc[-1]) if hasattr(close, 'iloc') else float(close[-1])
                # Sanity check: VIX should be 5-100, not a stock price
                if val > 100 or val < 5:
                    logger.warning(f"VIX value {val} looks invalid — fail-safe: 25.0")
                    return 25.0, True
                return val, False
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"VIX fetch failed ({e}) — retrying in 3s...")
                    time.sleep(3)
                else:
                    logger.warning(f"VIX fetch failed after retry ({e}) — fail-safe: 50.0")
                    return 50.0, True
        return 50.0, True

    def _check_vix_fresh_before_entry(self) -> Tuple[bool, float]:
        """
        P1 FIX: Fresh VIX check BEFORE placing any trade (bypasses cache).

        VIX can spike fast (120s cache may miss it). This ensures we never
        enter a trade when VIX >= REGIME_VIX_MAX (30).

        Also blocks VIX skip zone (20-24 by default): uncertainty zone where
        dip-bounce win rate drops to ~41% — too low to trade profitably.

        Returns:
            (can_trade, vix_value): True if VIX OK, False if blocked
        """
        vix_val, is_fallback = self._get_vix()

        if vix_val >= self.REGIME_VIX_MAX:
            logger.warning(f"⛔ VIX ENTRY BLOCK: VIX {vix_val:.1f} >= {self.REGIME_VIX_MAX} "
                          f"(fallback={is_fallback}) — trade blocked for safety")
            return False, vix_val

        # VIX Skip Zone (20-24): block only when VIX is RISING (fear increasing)
        # Backtest: VIX 20-24 + rising  → 28.1% win, -0.66% avg ❌
        #           VIX 20-24 + falling → 46.8% win, +0.85% avg ✅ (better than NORMAL!)
        if self.VIX_SKIP_ZONE_ENABLED:
            if self.VIX_SKIP_ZONE_LOW <= vix_val < self.VIX_SKIP_ZONE_HIGH:
                vix_change = self._get_vix_change_pct()
                vix_rising = (vix_change is not None and vix_change > 0)
                vix_falling = (vix_change is not None and vix_change < 0)
                if vix_rising:
                    logger.warning(
                        f"⛔ VIX SKIP ZONE (RISING): VIX {vix_val:.1f} in [{self.VIX_SKIP_ZONE_LOW}-{self.VIX_SKIP_ZONE_HIGH}) "
                        f"and rising {vix_change:+.1f}% — fear increasing, win rate 28%, blocking"
                    )
                    return False, vix_val
                elif vix_falling:
                    logger.info(
                        f"✅ VIX {vix_val:.1f} in skip zone but FALLING {vix_change:+.1f}% — "
                        f"fear subsiding, allowing (backtest: 46.8% win, +0.85%)"
                    )
                else:
                    # Unknown direction (fallback) → block to be safe
                    logger.warning(f"⛔ VIX SKIP ZONE: VIX {vix_val:.1f}, direction unknown — blocking")
                    return False, vix_val

        # Log VIX check for audit trail
        logger.info(f"✅ VIX entry check OK: {vix_val:.1f} (skip_zone={self.VIX_SKIP_ZONE_LOW}-{self.VIX_SKIP_ZONE_HIGH}, max={self.REGIME_VIX_MAX})")
        return True, vix_val

    def _get_spy_intraday_return(self) -> float:
        """Get SPY % return from today's open price. Cached 5 min to reduce API calls.
        Returns 0.0 on data error (fail-open — don't block on missing data)."""
        cache = getattr(self, '_spy_intraday_cache', None)
        if cache and (datetime.now() - cache[1]).total_seconds() < 300:
            return cache[0]
        try:
            spy = yf.download('SPY', period='1d', interval='5m', progress=False)
            if spy.empty:
                return 0.0
            open_col = spy['Open']
            close_col = spy['Close']
            if hasattr(open_col, 'columns'):
                open_col = open_col.iloc[:, 0]
            if hasattr(close_col, 'columns'):
                close_col = close_col.iloc[:, 0]
            open_price = float(open_col.iloc[0])
            current = float(close_col.iloc[-1])
            pct = (current - open_price) / open_price * 100
            self._spy_intraday_cache = (pct, datetime.now())
            logger.debug(f"SPY intraday: open={open_price:.2f} current={current:.2f} ret={pct:+.2f}%")
            return pct
        except Exception as e:
            logger.debug(f"SPY intraday check failed: {e}")
            return 0.0

    def _get_intraday_pct(self, ticker: str, cache_attr: str) -> float:
        """Get % return from today's open for any ticker. Cached 5 min.
        Returns None on error (so caller can distinguish from 0.0)."""
        cache = getattr(self, cache_attr, None)
        if cache and (datetime.now() - cache[1]).total_seconds() < 300:
            return cache[0]
        try:
            data = yf.download(ticker, period='1d', interval='5m', progress=False)
            if data.empty:
                return None
            open_col = data['Open']
            close_col = data['Close']
            if hasattr(open_col, 'columns'):
                open_col = open_col.iloc[:, 0]
            if hasattr(close_col, 'columns'):
                close_col = close_col.iloc[:, 0]
            open_price = float(open_col.iloc[0])
            current = float(close_col.iloc[-1])
            if open_price == 0:
                return None
            pct = round((current - open_price) / open_price * 100, 3)
            setattr(self, cache_attr, (pct, datetime.now()))
            return pct
        except Exception as e:
            logger.debug(f"{ticker} intraday fetch failed: {e}")
            return None

    def _get_vix_change_pct(self) -> float:
        """Get VIX % change vs yesterday's close. Cached 5 min.
        Uses daily data (already fetched via _get_vix). Returns None on error."""
        cache = getattr(self, '_vix_change_cache', None)
        if cache and (datetime.now() - cache[1]).total_seconds() < 300:
            return cache[0]
        try:
            vix = yf.download('^VIX', period='5d', progress=False)
            if vix.empty or len(vix) < 2:
                return None
            close_col = vix['Close']
            if hasattr(close_col, 'columns'):
                close_col = close_col.iloc[:, 0]
            prev_close = float(close_col.iloc[-2])
            current = float(close_col.iloc[-1])
            if prev_close == 0:
                return None
            pct = round((current - prev_close) / prev_close * 100, 3)
            self._vix_change_cache = (pct, datetime.now())
            return pct
        except Exception as e:
            logger.debug(f"VIX change pct fetch failed: {e}")
            return None

    def _get_entry_market_context(self) -> dict:
        """Collect VIX spike detection indicators at time of entry.
        Returns dict with entry_vix, entry_spy_intraday_pct, entry_vix_change_pct,
        entry_uvxy_pct, entry_qqq_spy_spread. All values can be None on error."""
        spy_pct = self._get_intraday_pct('SPY', '_spy_intraday_cache')
        uvxy_pct = self._get_intraday_pct('UVXY', '_uvxy_intraday_cache')
        qqq_pct = self._get_intraday_pct('QQQ', '_qqq_intraday_cache')
        qqq_spy_spread = None
        if qqq_pct is not None and spy_pct is not None:
            qqq_spy_spread = round(qqq_pct - spy_pct, 3)
        vix_val, _ = self._get_vix()
        vix_change = self._get_vix_change_pct()
        return {
            'entry_spy_intraday_pct': spy_pct,
            'entry_vix': round(vix_val, 2) if vix_val else None,
            'entry_vix_change_pct': vix_change,
            'entry_uvxy_pct': uvxy_pct,
            'entry_qqq_spy_spread': qqq_spy_spread,
        }

    def _check_vix_spike_protection(self):
        """Tighten SLs on all positions when VIX spikes >VIX_SPIKE_PCT% vs yesterday.
        Only triggers once per trading session."""
        if not self.VIX_SPIKE_PROTECTION_ENABLED:
            return
        import pytz
        et_tz = pytz.timezone('US/Eastern')
        today_et = datetime.now(et_tz).date()
        if getattr(self, '_vix_spike_triggered_today', None) == today_et:
            return
        try:
            vix_data = yf.download('^VIX', period='5d', progress=False)
            if len(vix_data) < 2:
                return
            close = vix_data['Close']
            if hasattr(close, 'columns'):
                close = close.iloc[:, 0]
            vix_prev = float(close.iloc[-2])
            vix_curr = float(close.iloc[-1])
            vix_change_pct = (vix_curr - vix_prev) / vix_prev * 100
            if vix_change_pct < self.VIX_SPIKE_PCT:
                return

            logger.warning(f"🚨 VIX SPIKE PROTECTION: {vix_prev:.1f}→{vix_curr:.1f} "
                          f"(+{vix_change_pct:.1f}% ≥ {self.VIX_SPIKE_PCT}%) — tightening all SLs")

            for symbol, managed_pos in list(self.positions.items()):
                try:
                    snapshot = self.broker.get_snapshot(symbol)
                    if not snapshot:
                        continue
                    current_price = snapshot.price
                    new_sl = round(current_price * (1 - self.VIX_SPIKE_SL_TIGHTEN_PCT / 100), 2)
                    if new_sl <= managed_pos.current_sl_price:
                        logger.debug(f"  {symbol}: SL already tight (${managed_pos.current_sl_price:.2f}), skipping")
                        continue
                    days_held = self.pdt_guard.get_days_held(symbol)
                    if days_held >= 1 and managed_pos.sl_order_id:
                        new_order = self.broker.modify_stop_loss(managed_pos.sl_order_id, new_sl)
                        if new_order:
                            managed_pos.sl_order_id = new_order.id
                    managed_pos.current_sl_price = new_sl
                    logger.warning(f"  {symbol}: SL tightened ${managed_pos.current_sl_price:.2f} → ${new_sl:.2f} "
                                  f"({self.VIX_SPIKE_SL_TIGHTEN_PCT:.1f}% below ${current_price:.2f})")
                except Exception as e:
                    logger.error(f"VIX spike SL tighten failed for {symbol}: {e}")

            self._vix_spike_triggered_today = today_et
        except Exception as e:
            logger.warning(f"VIX spike protection check failed: {e}")

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

        if not self.pdt_guard._get_enforce_on_paper():
            return False, "PDT not enforced - Low Risk Mode skipped"

        pdt_status = self.pdt_guard.get_pdt_status()

        if pdt_status.remaining <= 0:
            return True, f"PDT budget = 0 → Low Risk Mode"

        if pdt_status.remaining <= self.pdt_guard._get_reserve():
            return True, f"PDT budget = {pdt_status.remaining} (≤ reserve {self.pdt_guard._get_reserve()}) → Low Risk Mode"

        return False, f"PDT budget OK ({pdt_status.remaining}/{self.pdt_guard._get_max_day_trades()})"

    # =========================================================================
    # SMART BEAR MODE (v4.9.2 NEW!)
    # =========================================================================

    def _is_bear_mode(self) -> Tuple[bool, str]:
        """
        Check if Smart Bear Mode should activate.

        Precedence: REGIME_FILTER gates everything → BEAR_MODE decides defensive trading.
        If REGIME_FILTER disabled: always BULL → bear mode never activates.
        If REGIME_FILTER enabled + SPY BEAR + BEAR_MODE_ENABLED: trade defensive sectors only.

        Returns:
            (is_bear, reason)
        """
        if not self.BEAR_MODE_ENABLED:
            return False, "Bear mode disabled"

        is_bull, reason = self._check_market_regime()
        if is_bull:
            return False, "Market is BULL"

        return True, f"BEAR MODE: {reason}"

    def _get_bear_allowed_sectors(self) -> List[str]:
        """
        Get dynamic list of sectors allowed in Bear Mode

        v4.9.6: Use sector REGIME (not return_20d threshold)
        - STRONG BULL, BULL, SIDEWAYS → ALLOWED (conviction sizing handles risk)
        - BEAR, STRONG BEAR → BLOCKED

        v6.21: Add caching to reduce redundant checks and API calls

        ตรงกับ scanner ใน run_app.py — ทั้งสองระบบใช้ logic เดียวกัน

        Returns:
            List of sector names allowed for trading
        """
        # v6.21: Use cache to avoid repeated checks
        if self._bear_sectors_cache:
            allowed, cached_at = self._bear_sectors_cache
            age_seconds = (datetime.now() - cached_at).total_seconds()
            if age_seconds < self._bear_sectors_cache_seconds:
                return allowed

        allowed = []

        if self.screener and hasattr(self.screener, 'sector_regime') and self.screener.sector_regime:
            sr = self.screener.sector_regime
            for etf, sector_name in sr.SECTOR_ETFS.items():
                try:
                    regime = sr.sector_regimes.get(etf, 'UNKNOWN')
                    # v5.1: Allowlist (not blocklist) — UNKNOWN is BLOCKED for safety
                    if regime in ('BULL', 'STRONG BULL', 'SIDEWAYS'):
                        allowed.append(sector_name)
                        logger.info(f"🐻 {sector_name} ({etf}) regime={regime} → ALLOWED")
                    else:
                        logger.info(f"🐻 {sector_name} ({etf}) regime={regime} → BLOCKED")
                except Exception as e:
                    logger.warning(f"Error checking sector {etf}: {e} — BLOCKED (fail-closed)")

        logger.info(f"🐻 Bear allowed sectors ({len(allowed)}/11): {allowed}")

        # v6.21: Cache the result
        self._bear_sectors_cache = (allowed, datetime.now())

        return allowed

    def _get_bull_blocked_sectors(self) -> List[str]:
        """
        Dynamic sector exclusion — 2 conditions (v6.28):

        1. Absolute: return_20d < BULL_SECTOR_MIN_RETURN (-3%) → sector actively declining
        2. Relative: bottom SECTOR_WEAK_RELATIVE_N sectors by return_20d → always exclude worst performers

        Both conditions applied — union of both sets.
        Dynamic: Materials blocked today if -4%, NOT blocked if +10% (as now).
        """
        if not self.BULL_SECTOR_FILTER_ENABLED:
            return []

        ALIASES = {'Financial', 'Financials', 'Consumer Discretionary',
                   'Consumer Staples', 'Materials', 'Communications',
                   'Telecommunication Services'}

        blocked = set()
        sector_returns = {}  # {sector_name: return_20d} for canonical sectors

        if self.screener and hasattr(self.screener, 'sector_regime') and self.screener.sector_regime:
            sector_to_etf = self.screener.sector_regime.SECTOR_TO_ETF
            for sector_name, etf in sector_to_etf.items():
                if sector_name in ALIASES:
                    continue
                try:
                    metrics = self.screener.sector_regime.sector_metrics.get(etf)
                    if metrics:
                        sector_returns[sector_name] = metrics.get('return_20d', 0)
                except Exception as e:
                    logger.warning(f"Error checking sector {sector_name}: {e}")

            # Condition 1: Absolute — return_20d below threshold
            abs_threshold = self.BULL_SECTOR_MIN_RETURN
            for sector, ret in sector_returns.items():
                if ret < abs_threshold:
                    blocked.add(sector)
                    logger.info(f"🔴 {sector} return_20d={ret:+.1f}% < {abs_threshold}% → BLOCKED (absolute)")

            # Condition 2: Relative — bottom N sectors always blocked
            n = self.SECTOR_WEAK_RELATIVE_N
            if n > 0 and sector_returns:
                sorted_sectors = sorted(sector_returns.items(), key=lambda x: x[1])
                for sector, ret in sorted_sectors[:n]:
                    if sector not in blocked:
                        blocked.add(sector)
                        logger.info(f"🔴 {sector} return_20d={ret:+.1f}% (bottom {n}) → BLOCKED (relative)")

        if blocked:
            logger.info(f"⛔ Weak sectors blocked: {sorted(blocked)}")
        return list(blocked)

    def _get_conviction_size(self, signal, params) -> Tuple[float, str]:
        """
        v4.9.4: Conviction-based position sizing

        A+ (45%): STRONG BULL sector + (insider buying OR score 85+)
        A  (40%): BULL sector + score 80+
        B  (30%): SIDEWAYS/UNKNOWN sector + score 80+
        SKIP:     BEAR sector -> return 0
        """
        if not self.CONVICTION_SIZING_ENABLED:
            return params['position_size_pct'], 'DEFAULT'

        sector = getattr(signal, 'sector', '')
        score = getattr(signal, 'score', 0)
        alt_score = getattr(signal, 'alt_data_score', 0)
        has_insider = alt_score >= 5  # insider buying gives +5

        # Get sector regime
        regime = 'UNKNOWN'
        if self.screener and hasattr(self.screener, 'sector_regime') and self.screener.sector_regime:
            try:
                regime = self.screener.sector_regime.get_sector_regime(sector)
            except Exception:
                regime = 'UNKNOWN'

        # BEAR sector -> skip
        if regime in ('BEAR', 'STRONG BEAR'):
            return 0, 'SKIP_BEAR'

        # A+: STRONG BULL + insider/high score
        if regime == 'STRONG BULL' and (has_insider or score >= 85):
            return self.CONVICTION_A_PLUS_PCT, 'A+'

        # A: BULL + score 80+
        if regime in ('BULL', 'STRONG BULL') and score >= 80:
            return self.CONVICTION_A_PCT, 'A'

        # B: SIDEWAYS/UNKNOWN
        return self.CONVICTION_B_PCT, 'B'

    def _should_use_day_trade(self, symbol: str, managed_pos: 'ManagedPosition', current_price: float) -> Tuple[bool, str]:
        """
        v4.9.4: Decide if we should use a day trade to close this position.
        Only for Day 0 positions (same-day round trip).

        Returns: (should_day_trade, reason)
        """
        if not self.SMART_DAY_TRADE_ENABLED:
            return False, "disabled"

        # Only relevant for Day 0
        days_held = self.pdt_guard.get_days_held(symbol)
        if days_held > 0:
            return False, "not day 0"

        # Check PDT budget
        pdt_status = self.pdt_guard.get_pdt_status()
        if pdt_status.remaining <= self.pdt_guard._get_reserve():
            return False, "no PDT budget"

        pnl_pct = ((current_price - managed_pos.entry_price) / managed_pos.entry_price) * 100

        # Case 1: Gap profit > threshold
        if pnl_pct >= self.DAY_TRADE_GAP_THRESHOLD:
            return True, f"GAP_PROFIT: +{pnl_pct:.1f}% >= {self.DAY_TRADE_GAP_THRESHOLD}%"

        # Case 2: Intraday momentum > threshold
        if pnl_pct >= self.DAY_TRADE_MOMENTUM_THRESHOLD:
            return True, f"MOMENTUM: +{pnl_pct:.1f}% >= {self.DAY_TRADE_MOMENTUM_THRESHOLD}%"

        # Case 3: Emergency SL (losing badly)
        if self.DAY_TRADE_EMERGENCY_ENABLED:
            sl_pct = managed_pos.sl_pct or self.STOP_LOSS_PCT
            if pnl_pct <= -(sl_pct * 1.5):  # 1.5x SL = emergency
                return True, f"EMERGENCY: {pnl_pct:.1f}% <= -{sl_pct * 1.5:.1f}%"

        return False, "no trigger"

    def _get_effective_params(self) -> Dict:
        """
        Get effective trading parameters based on mode

        Priority: BEAR > LOW_RISK > NORMAL
        If BEAR + LOW_RISK → use the stricter of both

        Returns parameters adjusted for current mode
        """
        is_bear, bear_reason = self._is_bear_mode()
        is_low_risk, lr_reason = self._is_low_risk_mode()

        if is_bear:
            allowed_sectors = self._get_bear_allowed_sectors()

            if is_low_risk:
                # BEAR + LOW_RISK: use stricter of both
                logger.info(f"🐻🛡️ BEAR+LOW_RISK MODE: {bear_reason} | {lr_reason}")
                return {
                    'gap_max_up': min(self.BEAR_GAP_MAX_UP, self.LOW_RISK_GAP_MAX_UP),
                    'gap_max_down': self.BEAR_GAP_MAX_DOWN,
                    'min_score': max(self.BEAR_MIN_SCORE, self.LOW_RISK_MIN_SCORE),
                    'position_size_pct': min(self.BEAR_POSITION_SIZE_PCT, self.LOW_RISK_POSITION_SIZE_PCT),
                    'max_atr_pct': min(self.BEAR_MAX_ATR_PCT, self.LOW_RISK_MAX_ATR_PCT),
                    'max_positions': self.BEAR_MAX_POSITIONS,
                    'allowed_sectors': allowed_sectors,
                    'mode': 'BEAR+LOW_RISK'
                }
            else:
                logger.info(f"🐻 BEAR MODE: {bear_reason}")
                return {
                    'gap_max_up': self.BEAR_GAP_MAX_UP,
                    'gap_max_down': self.BEAR_GAP_MAX_DOWN,
                    'min_score': self.BEAR_MIN_SCORE,
                    'position_size_pct': self.BEAR_POSITION_SIZE_PCT,
                    'max_atr_pct': self.BEAR_MAX_ATR_PCT,
                    'max_positions': self.BEAR_MAX_POSITIONS,
                    'allowed_sectors': allowed_sectors,
                    'mode': 'BEAR'
                }
        elif is_low_risk:
            blocked = self._get_bull_blocked_sectors()
            logger.info(f"⚠️ LOW RISK MODE: {lr_reason}")
            return {
                'gap_max_up': self.LOW_RISK_GAP_MAX_UP,
                'min_score': self.LOW_RISK_MIN_SCORE,
                'position_size_pct': self.LOW_RISK_POSITION_SIZE_PCT,
                'max_atr_pct': self.LOW_RISK_MAX_ATR_PCT,
                'max_positions': None,
                'allowed_sectors': None,
                'blocked_sectors': blocked,
                'mode': 'LOW_RISK'
            }
        else:
            blocked = self._get_bull_blocked_sectors()
            return {
                'gap_max_up': self.GAP_MAX_UP,
                'min_score': self.MIN_SCORE,
                'position_size_pct': self.POSITION_SIZE_PCT,
                'max_atr_pct': None,  # No ATR limit in normal mode
                'max_positions': None,
                'allowed_sectors': None,
                'blocked_sectors': blocked,
                'mode': 'NORMAL'
            }

    # =========================================================================
    # GAP FILTER (v4.3 NEW!)
    # =========================================================================

    def _check_gap_filter(self, symbol: str, current_price: float, max_up_override: float = None, max_down_override: float = None) -> Tuple[bool, float, str]:
        """
        Check if stock has gapped too much from previous close

        Gap up แรง = ไม่ใช่ dip bounce แล้ว → SKIP
        Gap down แรง = อาจมีปัญหา (bad news) → SKIP

        Args:
            max_up_override: Override GAP_MAX_UP (for low-risk/bear mode)
            max_down_override: Override GAP_MAX_DOWN (for bear mode)

        Returns:
            (is_acceptable, gap_pct, reason)
        """
        if not self.GAP_FILTER_ENABLED:
            return True, 0.0, "Gap filter disabled"

        # v4.5: Use override if provided (low-risk/bear mode)
        gap_max_up = max_up_override if max_up_override is not None else self.GAP_MAX_UP

        try:
            # Get previous close (yesterday's close)
            # v6.9: Use DataManager with 5-min cache (historical data OK to cache)
            if self.data_manager:
                hist = self.data_manager.get_price_data(symbol, period='5d', interval='1d')
            else:
                # Fallback to direct yfinance
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='5d')  # Get 5 days to be safe

            if hist.empty or len(hist) < 1:
                logger.warning(f"{symbol}: Not enough data for gap check — blocking (fail-closed)")
                return False, 0.0, "Data unavailable — insufficient data"

            # iloc[-1] = most recent close (yesterday if during market hours)
            # v6.12: Handle both uppercase and lowercase column names
            close_col = 'Close' if 'Close' in hist.columns else 'close'
            prev_close = float(hist[close_col].iloc[-1])
            gap_pct = ((current_price - prev_close) / prev_close) * 100

            # Check gap limits
            if gap_pct > gap_max_up:
                reason = f"GAP UP TOO HIGH: {gap_pct:+.1f}% > {gap_max_up:+.1f}% (prev close ${prev_close:.2f})"
                logger.warning(f"❌ {symbol}: {reason}")
                return False, gap_pct, reason

            gap_max_down = max_down_override if max_down_override is not None else self.GAP_MAX_DOWN
            if gap_pct < gap_max_down:
                reason = f"GAP DOWN TOO HIGH: {gap_pct:+.1f}% < {gap_max_down:+.1f}% (prev close ${prev_close:.2f})"
                logger.warning(f"❌ {symbol}: {reason}")
                return False, gap_pct, reason

            reason = f"Gap OK: {gap_pct:+.1f}% (prev close ${prev_close:.2f})"
            logger.info(f"✅ {symbol}: {reason}")
            return True, gap_pct, reason

        except Exception as e:
            logger.error(f"{symbol}: Gap check failed: {e} — blocking (fail-closed)")
            return False, 0.0, f"Data unavailable: {e}"

    # =========================================================================
    # STOCK-D FILTER (v5.3 NEW! - Quant Research Finding)
    # =========================================================================

    def _check_stock_d_filter(self, symbol: str) -> Tuple[bool, str, Dict]:
        """
        Check if stock shows dip-bounce pattern (Stock-D filter).

        v5.3 Quant Research Finding:
        - Requiring dip-bounce pattern improves expectancy by +1.466%
        - Pattern: Yesterday dip >= 2%, Today bounce >= 1%
        - Filters out low-quality entries (620 → 110 trades, higher quality)

        Returns:
            (is_dip_bounce, reason, data)
        """
        if not self.STOCK_D_FILTER_ENABLED:
            return True, "Stock-D filter disabled", {}

        data = {}
        try:
            # v6.9: Use DataManager with 5-min cache (dip-bounce pattern from historical data)
            if self.data_manager:
                hist = self.data_manager.get_price_data(symbol, period='5d', interval='1d')
            else:
                # Fallback to direct yfinance
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='5d')

            if hist.empty or len(hist) < 3:
                logger.warning(f"{symbol}: Not enough data for Stock-D check — blocking (fail-closed)")
                return False, "Data unavailable — insufficient data", data

            # Get prices for pattern detection
            # hist.iloc[-1] = today (most recent), hist.iloc[-2] = yesterday, hist.iloc[-3] = 2 days ago
            # v6.12: Handle both uppercase and lowercase column names
            close_col = 'Close' if 'Close' in hist.columns else 'close'
            today_close = float(hist[close_col].iloc[-1])
            yesterday_close = float(hist[close_col].iloc[-2])
            day_before_close = float(hist[close_col].iloc[-3])

            # Calculate returns
            yesterday_return = ((yesterday_close - day_before_close) / day_before_close) * 100
            today_return = ((today_close - yesterday_close) / yesterday_close) * 100

            data = {
                'yesterday_return': round(yesterday_return, 2),
                'today_return': round(today_return, 2),
                'today_close': round(today_close, 2),
                'yesterday_close': round(yesterday_close, 2),
            }

            # Dip-bounce pattern: Yesterday dip >= 2%, Today bounce >= 1%
            is_dip = yesterday_return <= -2.0
            is_bounce = today_return >= 1.0

            if is_dip and is_bounce:
                reason = f"Stock-D OK: Yesterday {yesterday_return:+.1f}% (dip), Today {today_return:+.1f}% (bounce)"
                logger.info(f"✅ {symbol}: {reason}")
                return True, reason, data
            elif not is_dip:
                reason = f"Stock-D REJECT: Yesterday {yesterday_return:+.1f}% (need <= -2%)"
                logger.info(f"❌ {symbol}: {reason}")
                return False, reason, data
            else:  # dip but no bounce
                reason = f"Stock-D REJECT: Today {today_return:+.1f}% (need >= 1%)"
                logger.info(f"❌ {symbol}: {reason}")
                return False, reason, data

        except Exception as e:
            logger.error(f"{symbol}: Stock-D check failed: {e} — blocking (fail-closed)")
            return False, f"Data unavailable: {e}", data

    # =========================================================================
    # EARNINGS FILTER (v4.4 NEW!)
    # =========================================================================

    def _enrich_earnings_data(self, ticker, earnings_data: Dict):
        """v5.0: Fetch analyst/fundamental data from ticker.info for earnings context"""
        try:
            info = ticker.info
            if info:
                earnings_data['analyst_recommendation'] = info.get('recommendationMean')
                earnings_data['analyst_count'] = info.get('numberOfAnalystOpinions')
                earnings_data['target_mean_price'] = info.get('targetMeanPrice')
                earnings_data['earnings_quarterly_growth'] = info.get('earningsQuarterlyGrowth')
                earnings_data['revenue_growth'] = info.get('revenueGrowth')
                earnings_data['short_percent_of_float'] = info.get('shortPercentOfFloat')
        except Exception as e:
            logger.debug(f"Earnings enrichment error: {e}")

    def _check_earnings_filter(self, symbol: str) -> Tuple[bool, str, Dict]:
        """
        Check if stock has earnings announcement coming soon

        ไม่ซื้อหุ้นที่มี earnings ใกล้ๆ เพราะเสี่ยง gap ±10-20%

        Returns:
            (is_acceptable, reason, earnings_data)
            earnings_data: dict with 12 fields for EARNINGS_REJECT logging
        """
        earnings_data = {}

        if not self.EARNINGS_FILTER_ENABLED:
            return True, "Earnings filter disabled", earnings_data

        try:
            ticker = yf.Ticker(symbol)
            now = datetime.now()

            # Method 1: calendar (returns dict in newer yfinance)
            try:
                calendar = ticker.calendar
                if calendar is not None:
                    # Handle dict format (newer yfinance)
                    if isinstance(calendar, dict):
                        # v5.0: Extract estimates from calendar (free — already fetched)
                        earnings_data['eps_estimate'] = calendar.get('Earnings Average')
                        earnings_data['eps_estimate_high'] = calendar.get('Earnings High')
                        earnings_data['eps_estimate_low'] = calendar.get('Earnings Low')
                        earnings_data['revenue_estimate'] = calendar.get('Revenue Average')

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

                                # v5.0: Store date/days in earnings_data
                                earnings_data['earnings_date'] = earnings_date.strftime('%Y-%m-%d')
                                earnings_data['days_until_earnings'] = days_until

                                if 0 <= days_until <= self.EARNINGS_SKIP_DAYS_BEFORE:
                                    reason = f"EARNINGS in {days_until} days ({earnings_date.strftime('%Y-%m-%d')})"
                                    logger.warning(f"❌ {symbol}: {reason}")
                                    # v5.0: Fetch extra info fields on REJECT only
                                    self._enrich_earnings_data(ticker, earnings_data)
                                    return False, reason, earnings_data

                                if self.EARNINGS_SKIP_DAYS_AFTER > 0 and -self.EARNINGS_SKIP_DAYS_AFTER <= days_until < 0:
                                    reason = f"EARNINGS was {-days_until} days ago"
                                    logger.warning(f"❌ {symbol}: {reason}")
                                    self._enrich_earnings_data(ticker, earnings_data)
                                    return False, reason, earnings_data

                                return True, f"Earnings OK ({days_until} days away)", earnings_data

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

                                earnings_data['earnings_date'] = earnings_date.strftime('%Y-%m-%d')
                                earnings_data['days_until_earnings'] = days_until

                                if 0 <= days_until <= self.EARNINGS_SKIP_DAYS_BEFORE:
                                    reason = f"EARNINGS in {days_until} days ({earnings_date.strftime('%Y-%m-%d')})"
                                    logger.warning(f"❌ {symbol}: {reason}")
                                    self._enrich_earnings_data(ticker, earnings_data)
                                    return False, reason, earnings_data

                                return True, f"Earnings OK ({days_until} days away)", earnings_data
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

                        earnings_data['earnings_date'] = earnings_date.strftime('%Y-%m-%d')
                        earnings_data['days_until_earnings'] = days_until

                        if 0 <= days_until <= self.EARNINGS_SKIP_DAYS_BEFORE:
                            reason = f"EARNINGS in {days_until} days ({earnings_date.strftime('%Y-%m-%d')})"
                            logger.warning(f"❌ {symbol}: {reason}")
                            # info already fetched — enrich directly
                            earnings_data['analyst_recommendation'] = info.get('recommendationMean')
                            earnings_data['analyst_count'] = info.get('numberOfAnalystOpinions')
                            earnings_data['target_mean_price'] = info.get('targetMeanPrice')
                            earnings_data['earnings_quarterly_growth'] = info.get('earningsQuarterlyGrowth')
                            earnings_data['revenue_growth'] = info.get('revenueGrowth')
                            earnings_data['short_percent_of_float'] = info.get('shortPercentOfFloat')
                            return False, reason, earnings_data

                        return True, f"Earnings OK ({days_until} days away)", earnings_data
            except Exception as e:
                logger.debug(f"{symbol}: Info method failed: {e}")

            # No earnings data found
            if self.EARNINGS_NO_DATA_ACTION == 'skip':
                return False, "No earnings data - skipping (conservative)", earnings_data
            elif self.EARNINGS_NO_DATA_ACTION == 'warn':
                logger.warning(f"⚠️ {symbol}: No earnings data available")
                return True, "No earnings data (warned)", earnings_data
            else:  # 'allow'
                return True, "No earnings data (allowed)", earnings_data

        except Exception as e:
            logger.error(f"{symbol}: Earnings check failed: {e} — blocking (fail-closed)")
            return False, f"Data unavailable: {e}", earnings_data

    # =========================================================================
    # SECTOR DIVERSIFICATION (v4.7 NEW!)
    # =========================================================================

    def _get_effective_sector_max(self) -> int:
        """
        Get effective max_per_sector based on current VIX tier (Dynamic Sector Gate).

        VIX NORMAL (<20):  max = sector_gate_normal_max (2)  — calm market, allow pairs
        VIX SKIP (20-24):  max = sector_gate_skip_max (1)   — uncertainty, force diversify
        VIX HIGH (24-38):  max = sector_gate_high_max (1)   — volatile, very tight
        VIX EXTREME (>38): max = sector_gate_extreme_max (0) — no new positions

        Falls back to MAX_PER_SECTOR if dynamic gate disabled or VIX unavailable.
        """
        if not self.DYNAMIC_SECTOR_GATE_ENABLED:
            return self.MAX_PER_SECTOR

        try:
            if self.vix_adaptive and self.vix_adaptive.enabled:
                tier = self.vix_adaptive.strategy.current_tier
                if tier == 'normal':
                    return self.SECTOR_GATE_NORMAL_MAX
                elif tier in ('skip', 'high'):
                    return self.SECTOR_GATE_SKIP_MAX
                elif tier == 'extreme':
                    return self.SECTOR_GATE_EXTREME_MAX
        except Exception:
            pass

        return self.MAX_PER_SECTOR

    def _check_sector_filter(self, sector: str) -> Tuple[bool, str]:
        """
        Check if adding this sector would exceed effective max_per_sector.

        ป้องกันถือหุ้น sector เดียวกันเยอะเกิน (correlated risk)
        เช่น AMD + NVDA + INTC = 3 ตัว Tech → ลงพร้อมกัน
        Dynamic Sector Gate ปรับ limit อัตโนมัติตาม VIX tier.
        """
        if not self.SECTOR_FILTER_ENABLED or not sector:
            return True, "Sector filter disabled or no sector data"

        # Get effective max (static or VIX-adjusted)
        effective_max = self._get_effective_sector_max()

        # Count current positions in same sector
        same_sector_count = sum(
            1 for pos in self.positions.values()
            if pos.sector and pos.sector.lower() == sector.lower()
        )

        if same_sector_count >= effective_max:
            existing = [s for s, p in self.positions.items() if p.sector and p.sector.lower() == sector.lower()]
            return False, f"Already {same_sector_count} positions in {sector}: {existing} (max {effective_max})"

        return True, f"{sector}: {same_sector_count}/{effective_max} positions"

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
        from engine.state_manager import atomic_write_json
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
            atomic_write_json(os.path.join(self._state_dir, 'loss_counters.json'), state)
        except Exception as e:
            logger.error(f"Failed to save loss counters: {e}")

    def _load_loss_counters(self):
        """Load persisted loss tracking counters"""
        from engine.state_manager import safe_read_json
        from datetime import date as date_type
        state = safe_read_json(os.path.join(self._state_dir, 'loss_counters.json'), {})
        if not state:
            return
        self.consecutive_losses = state.get('consecutive_losses', 0)
        self.weekly_realized_pnl = state.get('weekly_realized_pnl', 0.0)
        if state.get('cooldown_until'):
            self.cooldown_until = date_type.fromisoformat(state['cooldown_until'])
        if state.get('weekly_reset_date'):
            self.weekly_reset_date = date_type.fromisoformat(state['weekly_reset_date'])
        for k, v in state.get('sector_loss_tracker', {}).items():
            self.sector_loss_tracker[k] = {
                'losses': v['losses'],
                'cooldown_until': date_type.fromisoformat(v['cooldown_until']) if v.get('cooldown_until') else None
            }
        logger.info(f"Loaded loss counters: consecutive={self.consecutive_losses}, weekly_pnl=${self.weekly_realized_pnl:.2f}")

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
        Calculate ATR-based SL/TP for a position (v4.6, v6.8+ uses SLTPCalculator with advanced features)

        v6.8+: Uses SLTPCalculator with full features:
        - SL: MAX(ATR-based, swing_low, EMA5) - most conservative
        - TP: MIN(ATR-based, resistance) - avoid overreach

        Returns:
            Dict with sl_pct, tp_pct, sl_price, tp_price, pdt_tp_pct, atr_pct
        """
        # Fetch historical data for advanced SL/TP calculation
        atr_pct = signal_atr_pct
        swing_low = None
        ema5 = None
        high_20d = None
        high_52w = None

        try:
            # v6.9: Use DataManager with 5-min cache (historical data for indicators)
            if self.data_manager:
                hist = self.data_manager.get_price_data(symbol, period="1y", interval="1d")
            else:
                # Fallback to direct yfinance
                ticker = yf.Ticker(symbol)
                # Fetch 1 year of data for all indicators
                hist = ticker.history(period="1y")

            if len(hist) >= 14:
                # v6.12: Handle both uppercase and lowercase column names
                high = hist['High'] if 'High' in hist.columns else hist['high']
                low = hist['Low'] if 'Low' in hist.columns else hist['low']
                close = hist['Close'] if 'Close' in hist.columns else hist['close']

                # Calculate ATR if not provided
                if atr_pct is None or atr_pct <= 0:
                    tr = pd.concat([
                        high - low,
                        abs(high - close.shift(1)),
                        abs(low - close.shift(1))
                    ], axis=1).max(axis=1)
                    atr = tr.rolling(14).mean().iloc[-1]
                    atr_pct = (atr / close.iloc[-1]) * 100

                # v6.8+: Calculate advanced indicators for SLTPCalculator
                if len(hist) >= 5:
                    swing_low = low.tail(5).min()  # 5-day low (support)
                    ema5 = close.ewm(span=5, adjust=False).mean().iloc[-1]  # 5-day EMA (trend)

                if len(hist) >= 20:
                    high_20d = high.tail(20).max()  # 20-day high (resistance)

                if len(hist) >= 252:  # ~1 year
                    high_52w = high.tail(252).max()  # 52-week high (resistance)

                logger.debug(f"{symbol} indicators: swing_low={swing_low:.2f if swing_low else None}, "
                           f"ema5={ema5:.2f if ema5 else None}, "
                           f"high_20d={high_20d:.2f if high_20d else None}, "
                           f"high_52w={high_52w:.2f if high_52w else None}")

        except Exception as e:
            logger.debug(f"Indicator calculation error for {symbol}: {e}")

        # v6.8+: Use SLTPCalculator with FULL features if available
        if self.sltp_calculator is not None:
            # Convert ATR% to absolute ATR value for calculator
            atr_value = None
            if atr_pct and atr_pct > 0:
                atr_value = entry_price * (atr_pct / 100)

            # Use calculator with ALL available indicators
            result = self.sltp_calculator.calculate(
                entry_price=entry_price,
                atr=atr_value,
                swing_low=swing_low,
                ema5=ema5,
                high_20d=high_20d,
                high_52w=high_52w
            )

            sl_pct = result.sl_pct
            tp_pct = result.tp_pct
            sl_price = result.stop_loss
            tp_price = result.take_profit
            pdt_tp_pct = sl_pct  # R:R 1:1 for Day 0

            # Log which method was used
            logger.info(f"📊 {symbol} SL/TP: Method={result.sl_method}/{result.tp_method}, R:R={result.risk_reward:.1f}")

        else:
            # v4.6: Fallback to manual calculation (backward compatible)
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

        # v6.8+: Enhanced logging
        if self.sltp_calculator is not None and hasattr(result, 'sl_method'):
            logger.info(f"📊 {symbol} Advanced SL/TP:")
            logger.info(f"   Method: {result.sl_method} → {result.tp_method}")
            logger.info(f"   SL: -{sl_pct}% (${sl_price:.2f})")
            logger.info(f"   TP: +{tp_pct}% (${tp_price:.2f})")
            logger.info(f"   R:R = 1:{result.risk_reward:.1f}")
            if swing_low:
                logger.info(f"   Support: ${swing_low:.2f}")
            if high_20d or high_52w:
                resistance = high_20d or high_52w
                logger.info(f"   Resistance: ${resistance:.2f}")
        else:
            # Legacy logging
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
            # v6.9: Use DataManager with caching (1h for company info, 5min for historical)
            if self.data_manager:
                info = self.data_manager.get_company_info(symbol)
                hist = self.data_manager.get_price_data(symbol, period="1mo", interval="1d")
            else:
                # Fallback to direct yfinance
                ticker = yf.Ticker(symbol)
                info = ticker.info
                hist = ticker.history(period="1mo")

            if hist.empty:
                return {}

            # v6.12: Handle both uppercase and lowercase column names
            close_col = 'Close' if 'Close' in hist.columns else 'close'
            current_price = hist[close_col].iloc[-1]

            # 52-week high distance
            high_52w = info.get('fiftyTwoWeekHigh', 0)
            dist_from_high = ((high_52w - current_price) / high_52w * 100) if high_52w > 0 else None

            # Returns
            return_5d = None
            return_20d = None
            if len(hist) >= 5:
                return_5d = ((current_price / hist[close_col].iloc[-5]) - 1) * 100
            if len(hist) >= 20:
                return_20d = ((current_price / hist[close_col].iloc[-20]) - 1) * 100

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
    # v5.0: DATA COLLECTION HELPERS
    # =========================================================================

    def _get_exit_context(self, symbol: str, current_price: float) -> Dict:
        """Fetch current market indicators at sell time (best-effort, never blocks sell)."""
        ctx = {}
        try:
            # 1. Snapshot: bid/ask/volume/prev_close (single Alpaca API call)
            snapshot = self.broker.get_snapshot(symbol)
            if snapshot:
                bid = snapshot.get('bid', 0)
                ask = snapshot.get('ask', 0)
                prev_close = snapshot.get('prev_close', 0)
                daily_vol = snapshot.get('daily_volume', 0)

                if bid and ask and bid > 0:
                    ctx['exit_bid_ask_spread'] = round(((ask - bid) / bid) * 100, 3)
                if prev_close and prev_close > 0:
                    ctx['exit_momentum_1d'] = round(((current_price - prev_close) / prev_close) * 100, 2)

                # Volume ratio (daily vs avg from yfinance)
                try:
                    # v6.9: Use DataManager with caching (1h for company info, 5min for historical)
                    if self.data_manager:
                        info = self.data_manager.get_company_info(symbol)
                        avg_vol = info.get('averageVolume', 0)
                        if avg_vol and daily_vol:
                            ctx['exit_volume_ratio'] = round(daily_vol / avg_vol, 2)

                        # RSI from recent history
                        hist = self.data_manager.get_price_data(symbol, period='1mo', interval='1d')
                    else:
                        # Fallback to direct yfinance
                        import yfinance as yf
                        ticker = yf.Ticker(symbol)
                        info = ticker.fast_info if hasattr(ticker, 'fast_info') else ticker.info
                        avg_vol = getattr(info, 'average_volume', None) or (info.get('averageVolume', 0) if isinstance(info, dict) else 0)
                        if avg_vol and daily_vol:
                            ctx['exit_volume_ratio'] = round(daily_vol / avg_vol, 2)

                        # RSI from recent history
                        hist = ticker.history(period='1mo')
                    if hist is not None and len(hist) >= 15:
                        # v6.12: Handle both uppercase and lowercase column names
                        close_col = 'Close' if 'Close' in hist.columns else 'close'
                        rsi_val = self._calc_rsi(hist[close_col])
                        import math
                        if not math.isnan(rsi_val):
                            ctx['exit_rsi'] = round(rsi_val, 1)
                except Exception as e:
                    logger.debug(f"Exit RSI context error: {e}")

            # 2. SPY change from regime cache (no API call)
            if hasattr(self, '_regime_cache') and self._regime_cache and len(self._regime_cache) >= 4:
                details = self._regime_cache[3]
                if isinstance(details, dict):
                    ctx['exit_spy_change'] = details.get('return_5d')

        except Exception as e:
            logger.debug(f"Exit context fetch error for {symbol}: {e}")
        return ctx

    def _process_scan_signals(self, signals, scan_type: str, max_positions: int = None):
        """Process all signals from a scan: execute/queue + log ALL signals."""
        effective_max = max_positions or self.MAX_POSITIONS
        positions_status = {
            'current': len(self.positions),
            'max': effective_max,
            'is_full': len(self.positions) >= effective_max
        }

        # v6.3: Always save cache even if no signals (so UI knows scan happened)
        if not signals:
            try:
                self._save_signals_cache([], scan_type, positions_status=positions_status)
            except Exception as e:
                logger.warning(f"Signals cache error (empty): {e}")
            return

        params = self._get_effective_params()
        mode = params.get('mode', 'NORMAL')

        # v5.1 P2-22: Generate scan_id before processing so execute_signal can link BUY→scan
        self._current_scan_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{scan_type}"

        scan_results = []
        # v6.4: Track actionable vs waiting signals for UI
        actionable_signals = []
        waiting_signals = []

        for rank, signal in enumerate(signals):
            action = "SKIPPED_FILTER"
            skip_reason = ""
            self._last_skip_reason = ""  # v5.3: Reset before execute
            if len(self.positions) < effective_max:
                result = self.execute_signal(signal)
                action = "BOUGHT" if result else "SKIPPED_FILTER"
                skip_reason = self._last_skip_reason if not result else ""
                actionable_signals.append(signal)  # v6.4: Signals we tried to process
            else:
                queued = self._add_to_queue(signal)
                action = "QUEUED" if queued else "QUEUE_FULL"
                skip_reason = "positions_full"
                waiting_signals.append(signal)  # v6.4: Signals waiting for slot

            scan_results.append({
                "signal_rank": rank + 1,
                "action_taken": action,
                "skip_reason": skip_reason,  # v5.3: Include skip reason
                "symbol": getattr(signal, 'symbol', ''),
                "scan_price": getattr(signal, 'entry_price', 0),
                "score": getattr(signal, 'score', 0),
                "rsi": getattr(signal, 'rsi', None),
                "momentum_5d": getattr(signal, 'momentum_5d', None),
                "atr_pct": getattr(signal, 'atr_pct', None),
                "sector": getattr(signal, 'sector', ''),
                "signal_source": self._derive_signal_source(signal, scan_type),
                "volume_ratio": getattr(signal, 'volume_ratio', None),
                "stop_loss": getattr(signal, 'stop_loss', None),
                "take_profit": getattr(signal, 'take_profit', None),
            })

        # Summary counts for monitoring
        from collections import Counter
        action_counts = Counter(r['action_taken'] for r in scan_results)
        bought = action_counts.get('BOUGHT', 0)
        skipped = action_counts.get('SKIPPED_FILTER', 0)
        queued = action_counts.get('QUEUED', 0)
        queue_full = action_counts.get('QUEUE_FULL', 0)
        logger.info(
            f"📊 Scan [{scan_type}] {len(scan_results)} signals: "
            f"{bought} bought, {skipped} skipped, {queued} queued, {queue_full} queue_full"
        )

        # Log entire scan batch (failure must not affect trading)
        try:
            scan_id = self._current_scan_id
            self._save_scan_log(scan_id, scan_type, mode, scan_results)
        except Exception as e:
            logger.warning(f"Scan log save error (non-fatal): {e}")

        # v5.1: Write execution status cache for UI signal status display
        try:
            self._save_execution_status(scan_results)
        except Exception as e:
            logger.warning(f"Execution status cache error: {e}")

        # v6.1: Write signals cache for UI (Single Source of Truth)
        # v6.4: Include waiting signals and positions status for UI display
        try:
            self._save_signals_cache(
                actionable_signals,
                scan_type,
                waiting_signals=waiting_signals,
                positions_status=positions_status
            )
        except Exception as e:
            logger.warning(f"Signals cache error: {e}")

    def _derive_signal_source(self, signal, scan_type: str = '') -> str:
        """Derive signal source from scan_type (primary) or signal attributes (fallback).
        v5.1 P2-10: Uses SignalSource constants to prevent typo bugs.
        """
        # Primary: scan_type is authoritative (set by the scan loop)
        if scan_type == 'overnight_gap':
            return SignalSource.OVERNIGHT_GAP
        if scan_type == 'pem':
            return SignalSource.PEM
        # sl_method / source attribute from screener output (secondary)
        sl_method = getattr(signal, 'sl_method', '')
        source_attr = signal.__dict__.get('source', '') if hasattr(signal, '__dict__') else ''
        if source_attr == 'pem' or 'pem' in sl_method:
            return SignalSource.PEM
        elif 'overnight_gap' in sl_method:
            return SignalSource.OVERNIGHT_GAP
        elif 'breakout' in sl_method:
            return SignalSource.BREAKOUT
        # Default for morning/afternoon/late_start scans
        return SignalSource.DIP_BOUNCE

    def _save_scan_log(self, scan_id: str, scan_type: str, mode: str, results: list):
        """Append scan batch to today's scan log file (thread-safe atomic write)."""
        from engine.state_manager import safe_read_json, atomic_write_json, cleanup_old_files
        scan_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scan_logs')
        os.makedirs(scan_dir, exist_ok=True)
        filepath = os.path.join(scan_dir, f'scan_{datetime.now().strftime("%Y-%m-%d")}.json')

        entry = {
            "scan_id": scan_id, "scan_timestamp": datetime.now().isoformat(),
            "scan_type": scan_type, "regime": self._regime_cache[1] if hasattr(self, '_regime_cache') and self._regime_cache else "UNKNOWN",
            "mode": mode, "total_signals": len(results), "signals": results,
        }

        with self._scan_log_lock:
            existing = safe_read_json(filepath, [])
            existing.append(entry)
            atomic_write_json(filepath, existing)

        # Daily cleanup (once per day)
        if not hasattr(self, '_last_scan_log_cleanup') or self._last_scan_log_cleanup != datetime.now().date():
            self._last_scan_log_cleanup = datetime.now().date()
            cleanup_old_files(scan_dir, max_age_days=90, pattern='scan_*.json')

    def _save_execution_status(self, scan_results):
        """Write latest execution results to cache for UI signal status display."""
        from engine.state_manager import safe_read_json, atomic_write_json
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        filepath = os.path.join(cache_dir, 'execution_status.json')

        status_map = {r.get('symbol', ''): {'action': r.get('action_taken', 'UNKNOWN'), 'skip_reason': r.get('skip_reason', ''), 'timestamp': datetime.now().isoformat()}
                      for r in scan_results if r.get('symbol', '')}

        existing = safe_read_json(filepath, {})
        existing.update(status_map)
        atomic_write_json(filepath, existing)

    # =========================================================================
    # SCANNING
    # =========================================================================

    @timeout(seconds=300)  # Production Grade v6.21: 5-minute timeout
    def scan_for_signals(self) -> List[Dict]:
        """Run screener to find signals (with regime filter)"""
        if not self.screener:
            logger.warning("Screener not available")
            return []

        # v6.3: Prevent concurrent scans (refresh spam protection)
        if not self._scan_lock.acquire(blocking=False):
            logger.warning("⚠️ Scan lock held - another scan in progress, skipping")
            return []

        self._scan_lock_acquired_at = datetime.now()  # v6.24: track for watchdog

        try:
            self.state = TradingState.SCANNING

            # v4.0: Check market regime FIRST
            is_bull, regime_reason = self._check_market_regime()

            # v4.9.2: Bear mode pass-through
            allowed_sectors = None
            if not is_bull:
                if self.BEAR_MODE_ENABLED:
                    allowed_sectors = self._get_bear_allowed_sectors()
                    logger.info(f"🐻 Bear mode scan — {len(allowed_sectors)} sectors allowed: {allowed_sectors}")
                else:
                    logger.warning(f"Skipping scan - {regime_reason}")
                    self.daily_stats.signals_found = 0
                    return []

            # v4.9.3: Get effective params (includes blocked_sectors for BULL)
            params = self._get_effective_params()
            blocked_sectors = params.get('blocked_sectors') or []

            regime_label = "BEAR_MODE" if allowed_sectors else "BULL"
            if blocked_sectors:
                logger.info(f"Scanning for signals (regime: {regime_label}, blocked: {blocked_sectors})...")
            else:
                logger.info(f"Scanning for signals (regime: {regime_label})...")

            # Load fresh data
            self.screener.load_data()

            # Get signals (excluding current positions)
            existing = list(self.positions.keys())
            effective_max = params.get('max_positions') or self.MAX_POSITIONS
            signals = self.screener.get_portfolio_signals(
                max_positions=effective_max,
                existing_positions=existing,
                allowed_sectors=allowed_sectors,
                blocked_sectors=blocked_sectors,
                min_score=params['min_score'],
                gap_max_up=params['gap_max_up'],
                bear_mode_enabled=self.BEAR_MODE_ENABLED,  # v6.21: Pass BEAR mode flag
            )

            self.daily_stats.signals_found = len(signals)
            logger.info(f"Found {len(signals)} signals (regime: {regime_label})")

            # VIX Adaptive Strategy v3.0: Add VIX-based signals
            if self.vix_adaptive and self.vix_adaptive.enabled:
                try:
                    # Enrich screener data_cache with VIX indicators
                    if self.screener and hasattr(self.screener, 'data_cache'):
                        add_vix_indicators_to_cache(self.screener.data_cache)

                        # Pass enriched cache to VIX Adaptive
                        vix_signals = self.vix_adaptive.scan_signals(
                            date=datetime.now().date(),
                            stock_data=self.screener.data_cache,
                            active_positions=list(self.positions.values())
                        )

                        if vix_signals:
                            signals.extend(vix_signals)
                            logger.info(f"VIX Adaptive: Added {len(vix_signals)} signals (Total: {len(signals)})")
                    else:
                        logger.warning("VIX Adaptive: Screener data_cache not available")

                except Exception as e:
                    logger.error(f"VIX Adaptive scan failed: {e}")

            return signals

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            return []
        finally:
            # v6.3: Always release scan lock
            self._scan_lock.release()

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
                pos = self.broker.get_position(symbol)
                if pos:
                    current_price = pos.current_price
                else:
                    # v6.9: Use DataManager for current price (broker → yfinance fallback)
                    if self.data_manager:
                        current_price = self.data_manager.get_current_price(symbol) or 0
                    else:
                        # Fallback to direct yfinance
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
                alpaca_pos = self.broker.get_position(symbol)
                if alpaca_pos:
                    # Already have position somehow — skip
                    logger.warning(f"Queue: {symbol} already has position at Alpaca")
                    return False
                snapshot = self.broker.get_snapshot(symbol) if hasattr(self.broker, 'get_snapshot') else None
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

    def _reconcile_positions(self):
        """Check for position mismatches between engine and Alpaca (once per day).

        v5.1 P1-9: Also stores Alpaca position count so max_positions check
        accounts for manual/external trades not tracked by engine.
        """
        today = datetime.now().date()
        if hasattr(self, '_last_reconcile') and self._last_reconcile == today:
            return  # Already reconciled today
        self._last_reconcile = today

        try:
            alpaca_positions = self.broker.get_positions()
            if alpaca_positions is None:
                return

            # v5.1 P1-9: Store Alpaca count for max_positions enforcement
            self._alpaca_position_count = len(alpaca_positions)

            alpaca_symbols = {p.symbol for p in alpaca_positions}
            engine_symbols = set(self.positions.keys())

            # Symbols in Alpaca but not in engine (ghost fills / manual trades)
            ghost = alpaca_symbols - engine_symbols
            # Symbols in engine but not in Alpaca (stale positions)
            stale = engine_symbols - alpaca_symbols

            if ghost:
                logger.warning(f"⚠️ RECONCILE: {len(ghost)} Alpaca position(s) not tracked by engine: {ghost}")
                for sym in ghost:
                    pos = next((p for p in alpaca_positions if p.symbol == sym), None)
                    if pos:
                        logger.warning(f"  {sym}: qty={pos.qty} avg_entry=${float(pos.avg_entry_price):.2f} market_value=${float(pos.market_value):.2f}")
                logger.warning(f"⚠️ RECONCILE: max_positions will use Alpaca count ({self._alpaca_position_count}) to prevent over-leverage")

            if stale:
                logger.warning(f"⚠️ RECONCILE: Stale positions in engine not in Alpaca: {stale}")
                for sym in stale:
                    logger.warning(f"  Removing stale engine position: {sym}")
                with self._positions_lock:
                    for sym in stale:
                        self.positions.pop(sym, None)

            if not ghost and not stale:
                logger.info(f"✅ RECONCILE: OK ({len(engine_symbols)} positions match)")

        except Exception as e:
            logger.warning(f"Position reconciliation error: {e}")

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

    def _log_filter_rejection(self, symbol, price, reason, skip_detail, filters,
                                signal_score, signal_sector, signal_source, signal, mode,
                                gap_pct=None, **extra_kwargs):
        """Helper to log filter rejections (DRY: shared by all filter SKIP paths)."""
        try:
            self.trade_logger.log_skip(
                symbol=symbol,
                price=price,
                reason=reason,
                skip_detail=skip_detail,
                filters=filters,
                signal_score=signal_score,
                gap_pct=gap_pct,
                sector=signal_sector, signal_source=signal_source,
                atr_pct=getattr(signal, 'atr_pct', None),
                entry_rsi=getattr(signal, 'rsi', None),
                momentum_5d=getattr(signal, 'momentum_5d', None),
                mode=mode,
                **extra_kwargs,
            )
        except Exception as log_err:
            logger.warning(f"Trade log error: {log_err}")

    # =========================================================================
    # EXECUTE_SIGNAL HELPER METHODS (v6.5 Refactor)
    # =========================================================================

    def _exec_preflight_checks(self, symbol: str, params: Dict) -> Tuple[bool, str]:
        """
        Block 1: Pre-flight checks before trade execution.
        Returns (passed, skip_reason).
        """
        mode = params['mode']

        # Safety check
        can_trade, reason = self.safety.can_open_new_position(mode=mode)
        if not can_trade:
            logger.warning(f"Safety block: {reason}")
            return False, f"Safety: {reason}"

        # PDT pre-buy budget check (skip in LOW_RISK mode or when PDT not enforced)
        if 'LOW_RISK' not in mode and self.pdt_guard._get_enforce_on_paper():
            pdt_status = self.pdt_guard.get_pdt_status()
            if pdt_status.remaining <= self.pdt_guard._get_reserve():
                logger.warning(f"❌ PDT pre-buy block: remaining={pdt_status.remaining}")
                return False, "PDT Full"

        # Check duplicate position
        if symbol in self.positions:
            logger.warning(f"Already have position in {symbol}")
            return False, "Duplicate"

        # Reconcile with Alpaca
        try:
            alpaca_existing = self.broker.get_position(symbol)
            if alpaca_existing:
                logger.warning(f"⚠️ RECONCILIATION: Alpaca already holds {symbol}")
                return False, "Already Held"
        except Exception:
            pass

        # Check max positions under lock
        with self._positions_lock:
            effective_max = params.get('max_positions') or self.MAX_POSITIONS
            actual_count = max(len(self.positions), getattr(self, '_alpaca_position_count', 0))
            if actual_count >= effective_max:
                logger.warning(f"Max positions ({effective_max}) reached")
                return False, "Max Pos"

        # Fresh VIX check
        vix_ok, vix_val = self._check_vix_fresh_before_entry()
        if not vix_ok:
            return False, f"VIX {vix_val:.0f}"

        # Opening window stagger: must wait OPENING_STAGGER_MIN between buys in first 30 min
        # Backtest: max-1 loses 44% of trades (45.5% win) leaving +200% P&L on table.
        # Stagger-15min allows 2 positions in 30min, retains 87% of baseline profit.
        if self.OPENING_WINDOW_LIMIT_ENABLED:
            et_now = self._get_et_time()
            today = et_now.date()
            # Reset stagger tracker on new trading day
            if self._opening_window_date != today:
                self._opening_window_buys = 0
                self._opening_window_date = today
                self._opening_last_buy_time = None
            # Check if we're in the opening window (9:30 to 9:30+window_minutes)
            market_open_et = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
            window_end_et = market_open_et + timedelta(minutes=self.OPENING_WINDOW_MINUTES)
            if market_open_et <= et_now < window_end_et:
                last_buy = getattr(self, '_opening_last_buy_time', None)
                if last_buy is not None:
                    elapsed = (et_now - last_buy).total_seconds() / 60
                    stagger = self.OPENING_WINDOW_MAX_BUYS  # reuse field as stagger minutes
                    if elapsed < stagger:
                        wait_min = stagger - elapsed
                        logger.warning(
                            f"⛔ OPENING STAGGER: Must wait {wait_min:.0f}min more before next buy "
                            f"(last buy {elapsed:.0f}min ago, stagger={stagger}min in first {self.OPENING_WINDOW_MINUTES}min)"
                        )
                        return False, f"Opening stagger ({stagger}min)"

        # SPY intraday filter: block new entries when SPY already selling off from open
        if self.SPY_INTRADAY_FILTER_ENABLED:
            spy_ret = self._get_spy_intraday_return()
            if spy_ret <= self.SPY_INTRADAY_FILTER_PCT:
                logger.warning(f"⛔ SPY INTRADAY BLOCK: SPY {spy_ret:+.2f}% from open "
                               f"(threshold {self.SPY_INTRADAY_FILTER_PCT}%)")
                return False, f"SPY intraday {spy_ret:.1f}%"

        return True, ""

    def _exec_quality_filters(self, signal, params: Dict, current_price: float) -> Tuple[bool, str]:
        """
        Block 2: Score, RSI, and momentum quality filters.
        Returns (passed, skip_reason).
        """
        symbol = signal.symbol
        mode = params['mode']
        signal_score = getattr(signal, 'score', 0)
        signal_sector = getattr(signal, 'sector', '') or ''
        signal_source = self._derive_signal_source(signal)

        # Score filter: use strategy-specific threshold for breakout/overnight/pem (different scale than dip-bounce)
        sl_method = getattr(signal, 'sl_method', '')
        if 'breakout' in sl_method:
            effective_min_score = self.BREAKOUT_MIN_SCORE
        elif 'overnight_gap' in sl_method:
            effective_min_score = self.OVERNIGHT_GAP_MIN_SCORE
        elif signal_source == SignalSource.PEM or 'pem' in sl_method:
            effective_min_score = 50   # PEM score is based on gap size, not dip-bounce formula
        else:
            effective_min_score = params['min_score']

        if signal_score < effective_min_score:
            logger.warning(f"❌ Score Filter REJECT {symbol}: {signal_score} < {effective_min_score}")
            self._log_filter_rejection(
                symbol, current_price, "SCORE_REJECT",
                f"Score {signal_score} < {effective_min_score}",
                {"score": {"passed": False}},
                signal_score, signal_sector, signal_source, signal, mode,
            )
            return False, f"Score {signal_score}"

        # RSI filter (v6.2)
        signal_rsi = getattr(signal, 'rsi', None)
        max_rsi = getattr(self, 'MAX_RSI_ENTRY', None)
        if max_rsi and signal_rsi and signal_rsi > max_rsi:
            logger.warning(f"❌ RSI Filter REJECT {symbol}: RSI {signal_rsi:.0f} > {max_rsi}")
            self._log_filter_rejection(
                symbol, current_price, "RSI_REJECT",
                f"RSI {signal_rsi:.0f} > {max_rsi}",
                {"rsi": {"passed": False}},
                signal_score, signal_sector, signal_source, signal, mode,
            )
            return False, f"RSI {signal_rsi:.0f}"

        # Momentum range filter (v6.2)
        signal_mom = getattr(signal, 'momentum', None) or getattr(signal, 'mom_score', None)
        avoid_range = getattr(self, 'AVOID_MOM_RANGE', None)
        if avoid_range and signal_mom and len(avoid_range) == 2:
            mom_min, mom_max = avoid_range
            if mom_min <= signal_mom <= mom_max:
                logger.warning(f"❌ Momentum Filter REJECT {symbol}: {signal_mom:.1f}%")
                self._log_filter_rejection(
                    symbol, current_price, "MOM_REJECT",
                    f"Momentum {signal_mom:.1f}% in avoid range",
                    {"momentum": {"passed": False}},
                    signal_score, signal_sector, signal_source, signal, mode,
                )
                return False, f"Mom {signal_mom:.1f}%"

        return True, ""

    def _exec_calculate_position(self, signal, params: Dict, current_price: float) -> Tuple[bool, str, float, float, str]:
        """
        Block 3: Calculate position size and conviction.
        Returns (passed, skip_reason, position_value, capital, conviction).
        """
        mode = params['mode']

        # Get account info
        account = self.broker.get_account()
        if isinstance(account, dict):
            real_buying_power = float(account.get('buying_power', 0))
            portfolio_value = account.get('portfolio_value', 0)
        else:
            real_buying_power = float(getattr(account, 'buying_power', 0))
            portfolio_value = getattr(account, 'portfolio_value', 0)

        if self.SIMULATED_CAPITAL:
            capital = min(self.SIMULATED_CAPITAL, real_buying_power)
        else:
            capital = portfolio_value

        # Conviction-based sizing
        conviction_pct, conviction = self._get_conviction_size(signal, params)
        if conviction == 'SKIP_BEAR':
            logger.warning(f"Conviction SKIP: {signal.symbol} in BEAR sector")
            return False, "BEAR Sector", 0, 0, ""

        position_value = capital * (conviction_pct / 100)
        logger.info(f"Conviction {conviction}: {signal.symbol} -> {conviction_pct}% (${position_value:,.0f})")

        # ATR check in low risk mode
        if 'LOW_RISK' in mode and params['max_atr_pct'] is not None:
            signal_atr = getattr(signal, 'atr_pct', None)
            if signal_atr and signal_atr > params['max_atr_pct']:
                logger.warning(f"❌ ATR Filter REJECT {signal.symbol}: {signal_atr:.1f}%")
                return False, f"ATR {signal_atr:.1f}%", 0, 0, ""

        return True, "", position_value, capital, conviction

    def _exec_pretrade_filters(self, signal, params: Dict, current_price: float) -> Tuple[bool, str, float]:
        """
        Block 4: Pre-trade filters (gap, stock-d, earnings, sector).
        Returns (passed, skip_reason, gap_pct).
        """
        symbol = signal.symbol
        mode = params['mode']
        signal_score = getattr(signal, 'score', 0)
        signal_sector = getattr(signal, 'sector', '') or ''
        signal_source = self._derive_signal_source(signal)

        # Gap filter (skip for breakout and PEM — these legitimately gap up)
        sl_method = getattr(signal, 'sl_method', '')
        if 'breakout' in sl_method or signal_source == 'pem':
            gap_ok, gap_pct = True, getattr(signal, 'gap_pct', 0.0) or 0.0
        else:
            gap_ok, gap_pct, gap_reason = self._check_gap_filter(
                symbol, current_price,
                max_up_override=params['gap_max_up'],
                max_down_override=params.get('gap_max_down')
            )
        if not gap_ok:
            logger.warning(f"❌ Gap Filter REJECT {symbol}: {gap_reason}")
            self.daily_stats.gap_rejected += 1
            self._log_filter_rejection(
                symbol, current_price, "GAP_REJECT", gap_reason,
                {"gap": {"passed": False}},
                signal_score, signal_sector, signal_source, signal, mode,
                gap_pct=gap_pct,
            )
            return False, f"Gap {gap_pct:+.1f}%", gap_pct

        # Stock-D filter (skip for PEM — earnings gap stocks don't need dip-bounce pattern)
        if signal_source == 'pem':
            stock_d_ok, stock_d_reason, stock_d_data = True, "PEM skip", {}
        else:
            stock_d_ok, stock_d_reason, stock_d_data = self._check_stock_d_filter(symbol)
        if not stock_d_ok:
            logger.warning(f"❌ Stock-D Filter REJECT {symbol}: {stock_d_reason}")
            if not hasattr(self.daily_stats, 'stock_d_rejected'):
                self.daily_stats.stock_d_rejected = 0
            self.daily_stats.stock_d_rejected += 1
            self._log_filter_rejection(
                symbol, current_price, "STOCK_D_REJECT", stock_d_reason,
                {"stock_d": {"passed": False}},
                signal_score, signal_sector, signal_source, signal, mode,
                gap_pct=gap_pct,
            )
            return False, "Stock-D ❌", gap_pct

        # Earnings filter (skip for PEM — PEM IS the earnings play, we want to trade it)
        _skip_earnings = signal.__dict__.get('skip_earnings_filter', False) if hasattr(signal, '__dict__') else False
        if _skip_earnings or signal_source == 'pem':
            earnings_ok, earnings_reason, earnings_data = True, "PEM skip", {}
        else:
            earnings_ok, earnings_reason, earnings_data = self._check_earnings_filter(symbol)
        if not earnings_ok:
            logger.warning(f"❌ Earnings Filter REJECT {symbol}: {earnings_reason}")
            self.daily_stats.earnings_rejected += 1
            self._log_filter_rejection(
                symbol, current_price, "EARNINGS_REJECT", earnings_reason,
                {"earnings": {"passed": False}},
                signal_score, signal_sector, signal_source, signal, mode,
                gap_pct=gap_pct, **earnings_data,
            )
            return False, "Earnings", gap_pct

        # Sector diversification filter
        sector_ok, sector_reason = self._check_sector_filter(signal_sector)
        if not sector_ok:
            logger.warning(f"❌ Sector Filter REJECT {symbol}: {sector_reason}")
            self.daily_stats.sector_rejected += 1
            self._log_filter_rejection(
                symbol, current_price, "SECTOR_REJECT", sector_reason,
                {"sector": {"passed": False}},
                signal_score, signal_sector, signal_source, signal, mode,
            )
            return False, "Sector Full", gap_pct

        # Sector cooldown
        sector_cd_ok, sector_cd_reason = self._check_sector_cooldown(signal_sector)
        if not sector_cd_ok:
            logger.warning(f"🧊 Sector Cooldown REJECT {symbol}: {sector_cd_reason}")
            self.daily_stats.sector_rejected += 1
            self._log_filter_rejection(
                symbol, current_price, "SECTOR_COOLDOWN", sector_cd_reason,
                {"sector_cooldown": {"passed": False}},
                signal_score, signal_sector, signal_source, signal, mode,
            )
            return False, "Sector CD", gap_pct

        # Bear mode sector filter
        allowed_sectors = params.get('allowed_sectors')
        if allowed_sectors and signal_sector and signal_sector not in allowed_sectors:
            logger.warning(f"❌ BEAR Sector Filter REJECT {symbol}")
            self._log_filter_rejection(
                symbol, current_price, "BEAR_SECTOR_REJECT",
                f"Sector '{signal_sector}' not allowed in BEAR",
                {"bear_sector": {"passed": False}},
                signal_score, signal_sector, signal_source, signal, mode,
            )
            return False, "BEAR Sector", gap_pct

        # Bull sector filter
        blocked_sectors = params.get('blocked_sectors') or []
        if blocked_sectors and signal_sector and signal_sector in blocked_sectors:
            logger.warning(f"⛔ BULL Sector Filter REJECT {symbol}")
            self.daily_stats.sector_rejected += 1
            self._log_filter_rejection(
                symbol, current_price, "BULL_SECTOR_REJECT",
                f"Sector '{signal_sector}' ETF declining",
                {"bull_sector": {"passed": False}},
                signal_score, signal_sector, signal_source, signal, mode,
            )
            return False, "BULL Sector", gap_pct

        return True, "", gap_pct

    def _exec_place_order(self, symbol: str, qty: int, sl_pct: float, current_price: float, limit_price: float = None) -> Tuple[bool, Optional[Order], Optional[str], float]:
        """
        Block 6: Place buy order with optional stop loss.

        Args:
            symbol: Stock symbol
            qty: Quantity to buy
            sl_pct: Stop loss percentage
            current_price: Current market price (estimate)
            limit_price: Optional limit price from entry protection (v6.17)

        Returns (success, buy_order, sl_order_id, actual_entry_price).
        """
        if limit_price:
            logger.info(f"Executing: BUY {symbol} x{qty} @ LIMIT ${limit_price:.2f} (market ~${current_price:.2f})")
        else:
            logger.info(f"Executing: BUY {symbol} x{qty} @ ~${current_price:.2f}")

        # Check if we should place SL order (PDT Smart Guard)
        should_place_sl, sl_reason = self.pdt_guard.should_place_sl_order(symbol)

        if should_place_sl:
            # v6.17: Use limit price if provided
            buy_order, sl_order = self.broker.buy_with_stop_loss(
                symbol, qty, sl_pct=sl_pct, limit_price=limit_price
            )
            if not buy_order:
                logger.error(f"Failed to execute {symbol}")
                return False, None, None, 0
            sl_order_id = sl_order.id if sl_order else None
        else:
            logger.info(f"PDT Guard: {sl_reason} - buying without SL order")
            # v6.17: Use limit price if provided, otherwise use smart buy
            if limit_price:
                buy_order = self.broker.place_limit_buy(symbol, qty, limit_price)
                # v6.31: Wait up to 30s for fill (prevent ghost positions)
                if buy_order and buy_order.status != 'filled':
                    for _ in range(15):  # 15 x 2s = 30s max
                        time.sleep(2)
                        buy_order = self.broker.get_order(buy_order.id)
                        if buy_order and buy_order.status == 'filled':
                            break
            else:
                buy_order = self.broker.place_smart_buy(symbol, qty)
            if not buy_order:
                logger.warning(f"Buy order failed for {symbol}")
                return False, None, None, 0
            # v6.31: Wait up to 30s for fill (market orders usually fill fast)
            if buy_order.status != 'filled':
                for _ in range(15):  # 15 x 2s = 30s max
                    time.sleep(2)
                    buy_order = self.broker.get_order(buy_order.id)
                    if buy_order and buy_order.status == 'filled':
                        break
            sl_order_id = None

        if not buy_order or buy_order.status != 'filled':
            order_status = getattr(buy_order, 'status', 'None')
            logger.error(f"Buy order not filled for {symbol} (status={order_status})")
            try:
                if buy_order and hasattr(buy_order, 'id'):
                    self.broker.cancel_order(buy_order.id)
            except Exception:
                pass
            return False, None, None, 0

        entry_price = buy_order.filled_avg_price
        actual_qty = getattr(self.broker, '_last_filled_qty', qty)
        if actual_qty and actual_qty != qty:
            logger.warning(f"Using actual filled qty {actual_qty} (requested {qty})")

        return True, buy_order, sl_order_id, entry_price

    def _exec_create_position(self, signal, entry_price: float, qty: int,
                               sl_order_id: Optional[str], sl_pct: float, tp_pct: float,
                               atr_pct: float, params: Dict) -> bool:
        """
        Block 7: Create ManagedPosition under lock.
        Returns success.
        """
        symbol = signal.symbol
        mode = params['mode']
        signal_sector = getattr(signal, 'sector', '') or ''
        signal_source = self._derive_signal_source(signal)
        signal_score = getattr(signal, 'score', 0)

        sl_price = round(entry_price * (1 - sl_pct / 100), 2)
        tp_price = round(entry_price * (1 + tp_pct / 100), 2)

        with self._positions_lock:
            # Re-check max positions under lock
            effective_max = params.get('max_positions') or self.MAX_POSITIONS
            actual_count = max(len(self.positions), getattr(self, '_alpaca_position_count', 0))
            if actual_count >= effective_max:
                logger.warning(f"⚠️ Max positions reached under lock — cancelling {symbol}")
                return False

            regime_ok, regime_reason = self._check_market_regime()

            managed_pos = ManagedPosition(
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
                atr_pct=atr_pct,
                sector=signal_sector,
                trough_price=entry_price,
                source=signal_source,
                signal_score=signal_score,
                entry_mode=mode,
                entry_regime="BULL" if regime_ok else "BEAR",
                entry_rsi=getattr(signal, 'rsi', 0.0) or 0.0,
                momentum_5d=getattr(signal, 'momentum_5d', 0.0) or 0.0,
            )

            # v6.11: Add gap trade metadata if this is from pre-market gap scanner
            if hasattr(signal, '__dict__'):
                if signal.__dict__.get('gap_trade'):
                    managed_pos.gap_trade = True
                    managed_pos.gap_confidence = signal.__dict__.get('gap_confidence', 0)
                    managed_pos.gap_pct = signal.__dict__.get('gap_pct', 0)
                    logger.info(f"  📊 Gap Trade: {managed_pos.gap_pct:+.1f}% gap, "
                               f"{managed_pos.gap_confidence}% confidence (exit at EOD)")

            self.positions[symbol] = managed_pos
            self._save_positions_state()

        return True

    def _exec_post_trade_logging(self, signal, buy_order, entry_price: float, qty: int,
                                   gap_pct: float, sl_pct: float, tp_pct: float,
                                   atr_pct: float, params: Dict):
        """
        Block 8: Post-trade logging and stats update.
        """
        symbol = signal.symbol
        mode = params['mode']
        signal_score = getattr(signal, 'score', 0)
        signal_sector = getattr(signal, 'sector', '') or ''
        signal_source = self._derive_signal_source(signal)

        sl_price = round(entry_price * (1 - sl_pct / 100), 2)
        tp_price = round(entry_price * (1 + tp_pct / 100), 2)

        # PDT record
        self.pdt_guard.record_entry(symbol)

        # Opening window stagger: record last buy time
        if self.OPENING_WINDOW_LIMIT_ENABLED:
            et_now = self._get_et_time()
            market_open_et = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
            window_end_et = market_open_et + timedelta(minutes=self.OPENING_WINDOW_MINUTES)
            if market_open_et <= et_now < window_end_et:
                self._opening_last_buy_time = et_now
                self._opening_window_buys += 1
                logger.info(f"📊 Opening stagger: buy #{self._opening_window_buys} at {et_now.strftime('%H:%M')} ET, next allowed after {(et_now + timedelta(minutes=self.OPENING_WINDOW_MAX_BUYS)).strftime('%H:%M')} ET")

        # Update stats
        self.daily_stats.trades_executed += 1
        self.daily_stats.signals_executed += 1
        if 'LOW_RISK' in mode:
            self.daily_stats.low_risk_trades += 1
            logger.info(f"✅ Bought {symbol} x{qty} @ ${entry_price:.2f} [LOW RISK MODE]")
        else:
            logger.info(f"✅ Bought {symbol} x{qty} @ ${entry_price:.2f}")
        logger.info(f"   SL: ${sl_price:.2f} (-{sl_pct}%) | TP: ${tp_price:.2f} (+{tp_pct}%) | ATR: {atr_pct}%")

        # Alert
        self.alerts.alert_trade_executed(symbol, 'BUY', entry_price, qty)

        # Trade log
        try:
            pdt_status = self.pdt_guard.get_pdt_status()
            regime_ok, regime_reason = self._check_market_regime()
            analysis = self._get_analysis_data(symbol)
            exec_meta = getattr(self.broker, 'last_execution_meta', {})
            signal_price_val = getattr(signal, 'entry_price', None) or getattr(signal, 'close', None)
            slippage = None
            if signal_price_val and entry_price and signal_price_val > 0:
                slippage = round(((entry_price - signal_price_val) / signal_price_val) * 100, 3)

            # Entry timing context
            et_now = self._get_et_time()
            market_open = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
            entry_mins = int((et_now - market_open).total_seconds() / 60) if et_now >= market_open else None

            # SPY % above SMA20 (from regime check data)
            spy_pct_above_sma = None
            try:
                spy_data = yf.download('SPY', period='60d', progress=False)
                if not spy_data.empty:
                    close_col = spy_data['Close']
                    if hasattr(close_col, 'columns'):
                        close_col = close_col.iloc[:, 0]
                    spy_sma20 = float(close_col.rolling(20).mean().iloc[-1])
                    spy_current = float(close_col.iloc[-1])
                    if spy_sma20 > 0:
                        spy_pct_above_sma = round((spy_current - spy_sma20) / spy_sma20 * 100, 3)
            except Exception:
                pass

            # VIX spike detection context (v6.24)
            mkt_ctx = self._get_entry_market_context()

            self.trade_logger.log_buy(
                symbol=symbol, qty=qty, price=entry_price, reason="SIGNAL",
                filters={
                    "regime": {"passed": regime_ok, "detail": regime_reason},
                    "gap": {"passed": True, "detail": f"{gap_pct:+.1f}%"},
                    "score": {"passed": True, "detail": f"{signal_score}"}
                },
                pdt_remaining=pdt_status.remaining,
                mode=mode,
                regime="BULL" if regime_ok else "BEAR",
                gap_pct=gap_pct,
                signal_score=signal_score,
                atr_pct=getattr(signal, 'atr_pct', None),
                entry_rsi=getattr(signal, 'rsi', None),
                momentum_5d=getattr(signal, 'momentum_5d', None),
                sector=signal_sector,
                signal_source=signal_source,
                order_id=buy_order.id if buy_order else None,
                dist_from_52w_high=analysis.get('dist_from_52w_high'),
                return_5d=analysis.get('return_5d'),
                return_20d=analysis.get('return_20d'),
                order_type=exec_meta.get('order_type'),
                signal_price=signal_price_val,
                fill_price=entry_price,
                slippage_pct=slippage,
                config_snapshot=self._get_config_snapshot(),
                # Entry timing context
                entry_minutes_after_open=entry_mins,
                entry_spy_pct_above_sma=spy_pct_above_sma,
                # VIX spike detection context (v6.24)
                entry_vix=mkt_ctx['entry_vix'],
                entry_spy_intraday_pct=mkt_ctx['entry_spy_intraday_pct'],
                entry_vix_change_pct=mkt_ctx['entry_vix_change_pct'],
                entry_uvxy_pct=mkt_ctx['entry_uvxy_pct'],
                entry_qqq_spy_spread=mkt_ctx['entry_qqq_spy_spread'],
            )
        except Exception as log_err:
            logger.warning(f"Trade log error: {log_err}")

    def _get_realtime_data(self, symbol: str, fallback_price: float) -> Tuple[float, Optional[float]]:
        """
        Get real-time price and VWAP from Alpaca snapshot (v6.20 Refactor #3)

        Fetches live market data during market hours to ensure accurate entry validation.
        Falls back to signal price if market closed or snapshot unavailable.

        Args:
            symbol: Stock symbol
            fallback_price: Price to use if real-time data unavailable (typically signal.entry_price)

        Returns:
            (current_price, vwap) - VWAP is None if unavailable

        Production Grade: Data quality checks (v6.21)
        - VWAP sanity: Must be within ±50% of current price
        - Reject suspicious VWAP to prevent bad entry validation
        """
        # Only fetch during market hours with broker support
        if not self.broker.is_market_open() or not hasattr(self.broker, 'get_snapshot'):
            return fallback_price, None

        try:
            snapshot = self.broker.get_snapshot(symbol)
            if snapshot:
                # Extract price (use fallback if invalid)
                price = snapshot.last if snapshot.last > 0 else fallback_price
                # Extract VWAP (None if invalid)
                vwap = snapshot.vwap if snapshot.vwap > 0 else None

                # PRODUCTION GRADE: VWAP sanity check (v6.21)
                if vwap is not None and price > 0:
                    vwap_deviation_pct = abs((vwap - price) / price) * 100
                    if vwap_deviation_pct > 50:
                        logger.error(
                            f"❌ {symbol}: VWAP sanity check failed! "
                            f"Price=${price:.2f}, VWAP=${vwap:.2f} ({vwap_deviation_pct:+.1f}% deviation) "
                            f"- rejecting VWAP (expected ±50%)"
                        )
                        vwap = None  # Reject bad VWAP

                # Log real-time data
                if snapshot.last > 0:
                    logger.debug(f"📊 {symbol}: Real-time price ${price:.2f} (snapshot)")
                if vwap:
                    logger.debug(f"📊 {symbol}: Real-time VWAP ${vwap:.2f} (snapshot)")

                return price, vwap

        except Exception as e:
            logger.debug(f"Could not get snapshot for {symbol}: {e}")

        return fallback_price, None

    def execute_signal(self, signal) -> bool:
        """
        Execute a trading signal.

        v6.5 Refactored: Split into 8 helper methods for maintainability.
        Flow: preflight → quality → sizing → pretrade → sltp → order → position → logging

        Args:
            signal: Signal object from screener

        Returns:
            True if executed successfully
        """
        try:
            symbol = signal.symbol

            # Get effective parameters (normal vs low-risk mode)
            params = self._get_effective_params()
            mode = params['mode']

            if 'LOW_RISK' in mode:
                logger.info(f"🛡️ {symbol}: Using LOW RISK parameters")

            # BLOCK 1: Pre-flight checks (safety, PDT, duplicate, max positions, VIX)
            preflight_ok, skip_reason = self._exec_preflight_checks(symbol, params)
            if not preflight_ok:
                self._last_skip_reason = skip_reason
                return False

            # Get current price estimate (fallback)
            pos_check = self.broker.get_position(symbol)
            fallback_price = pos_check.current_price if pos_check else (
                getattr(signal, 'entry_price', None) or getattr(signal, 'close', 100)
            )

            # v6.20 Refactor #3: Get real-time price + VWAP (extracted to method for clarity)
            current_price, realtime_vwap = self._get_realtime_data(symbol, fallback_price)

            # v6.23: BLOCK 1.5: Entry Protection Filter (4-layer protection with adaptive timing)
            # v6.29: PEM signals bypass entry protection (momentum strategy, not mean-reversion)
            entry_limit_price = None  # Will be set by entry protection filter
            _skip_entry_protection = signal.__dict__.get('skip_entry_protection', False) if hasattr(signal, '__dict__') else False
            if self.entry_protection and self.entry_protection.enabled and not _skip_entry_protection:
                signal_price = getattr(signal, 'entry_price', current_price)
                # v6.23: Use signal.metadata for market_data (contains gap_pct for adaptive timing)
                market_data = getattr(signal, 'metadata', None) or {}

                # v6.20: Add real-time VWAP if available (priority: snapshot > signal)
                if realtime_vwap:
                    market_data['vwap'] = realtime_vwap
                elif not market_data.get('vwap'):
                    market_data['vwap'] = getattr(signal, 'vwap', None)

                allowed, reason, limit_price = self.entry_protection.check_entry(
                    symbol=symbol,
                    signal_price=signal_price,
                    current_price=current_price,
                    market_data=market_data
                )

                if not allowed:
                    logger.info(f"🛡️ {symbol}: {reason}")
                    signal_score = getattr(signal, 'score', 0)
                    signal_sector = getattr(signal, 'sector', '') or ''
                    signal_source = self._derive_signal_source(signal)
                    self._log_filter_rejection(
                        symbol, current_price, "ENTRY_PROTECTION", reason,
                        {"entry_protection": {"passed": False, "reason": reason}},
                        signal_score, signal_sector, signal_source, signal, mode,
                    )
                    self._last_skip_reason = reason
                    return False

                # Save limit price for order execution
                if limit_price:
                    entry_limit_price = limit_price
                    logger.info(f"💰 {symbol}: Using limit price ${limit_price:.2f} (signal ${signal_price:.2f})")

            # BLOCK 2: Quality filters (score, RSI, momentum)
            quality_ok, skip_reason = self._exec_quality_filters(signal, params, current_price)
            if not quality_ok:
                self._last_skip_reason = skip_reason
                return False

            # BLOCK 3: Calculate position size and conviction
            sizing_ok, skip_reason, position_value, capital, conviction = self._exec_calculate_position(
                signal, params, current_price
            )
            if not sizing_ok:
                self._last_skip_reason = skip_reason
                return False

            # BLOCK 4: Pre-trade filters (gap, stock-d, earnings, sector)
            pretrade_ok, skip_reason, gap_pct = self._exec_pretrade_filters(signal, params, current_price)
            if not pretrade_ok:
                self._last_skip_reason = skip_reason
                return False

            # BLOCK 5: Calculate ATR-based SL/TP + risk-parity sizing
            signal_atr = getattr(signal, 'atr_pct', None)
            atr_sl_tp = self._calculate_atr_sl_tp(symbol, current_price, signal_atr)
            sl_pct = atr_sl_tp['sl_pct']
            tp_pct = atr_sl_tp['tp_pct']

            # Risk-parity position sizing
            if self.RISK_PARITY_ENABLED and sl_pct > 0:
                risk_parity_pct = (self.RISK_BUDGET_PCT / sl_pct) * 100
                risk_parity_pct = min(risk_parity_pct, self.MAX_POSITION_PCT)
                position_value = capital * (risk_parity_pct / 100)
                logger.info(f"Risk-Parity: SL {sl_pct}% → size {risk_parity_pct:.0f}% (${position_value:,.0f})")

            qty = int(position_value / current_price)
            if qty <= 0:
                logger.warning(f"Position size too small for {symbol}")
                self._last_skip_reason = "Qty=0"
                return False

            # BLOCK 6: Place order (v6.17: Pass limit price from entry protection)
            order_ok, buy_order, sl_order_id, entry_price = self._exec_place_order(
                symbol, qty, sl_pct, current_price, limit_price=entry_limit_price
            )
            if not order_ok:
                signal_score = getattr(signal, 'score', 0)
                signal_sector = getattr(signal, 'sector', '') or ''
                signal_source = self._derive_signal_source(signal)
                self._log_filter_rejection(
                    symbol, current_price, "ORDER_NOT_FILLED", "Order failed",
                    {"order_fill": {"passed": False}},
                    signal_score, signal_sector, signal_source, signal, mode,
                )
                return False

            # Update qty if actual filled qty differs
            actual_qty = getattr(self.broker, '_last_filled_qty', qty)
            if actual_qty and actual_qty != qty:
                logger.warning(f"Using actual filled qty {actual_qty} (requested {qty})")
                qty = actual_qty

            # BLOCK 7: Create ManagedPosition
            position_ok = self._exec_create_position(
                signal, entry_price, qty, sl_order_id, sl_pct, tp_pct,
                atr_sl_tp['atr_pct'], params
            )
            if not position_ok:
                try:
                    self.broker.cancel_order(buy_order.id)
                except Exception:
                    pass
                return False

            # BLOCK 8: Post-trade logging
            self._exec_post_trade_logging(
                signal, buy_order, entry_price, qty, gap_pct,
                sl_pct, tp_pct, atr_sl_tp['atr_pct'], params
            )

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
            snapshot = self.broker.get_snapshot(symbol)
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
            # Success: cache 30 min (v5.0: reduced from 6h for faster rescheduled earnings detection)
            cache_ttl = 1800
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

    def _check_naked_positions(self):
        """Re-place SL orders for positions missing them (recovery from SL placement failure)."""
        for symbol, pos in list(self.positions.items()):
            if not pos.sl_order_id:
                logger.warning(f"⚠️ NAKED POSITION: {symbol} has no SL order — attempting to place")
                try:
                    sl_price = pos.stop_loss if hasattr(pos, 'stop_loss') else pos.current_sl_price
                    qty = pos.qty
                    sl_order = self.broker.place_stop_loss(symbol, qty, sl_price)
                    if sl_order:
                        pos.sl_order_id = sl_order.id
                        logger.info(f"✅ SL recovered for {symbol} @ ${sl_price:.2f}")
                    else:
                        logger.critical(f"SL recovery returned None for {symbol}")
                except Exception as e:
                    logger.critical(f"SL recovery FAILED for {symbol}: {e}")

    def monitor_positions(self):
        """Monitor all positions and update trailing stops

        # TODO P3-20: This method is ~500+ lines. Future refactoring candidate.
        # Key sections: SL recovery → split detection → SL fill check →
        # trailing stop update → TP check → max hold check → close execution
        """
        if not self.positions:
            return

        # v5.1: Check for and recover naked positions (no SL order)
        self._check_naked_positions()

        # VIX spike protection: tighten SLs if VIX jumped sharply today
        self._check_vix_spike_protection()

        # v4.9: Detect stock splits and adjust tracking
        for symbol, managed_pos in list(self.positions.items()):
            try:
                alpaca_pos = self.broker.get_position(symbol)
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
                        except Exception as e:
                            logger.warning(f"Failed to add split alert for {symbol}: {e}")
                        self._save_positions_state()
                        # Update SL order at Alpaca
                        if managed_pos.sl_order_id:
                            self.broker.modify_stop_loss(managed_pos.sl_order_id, managed_pos.current_sl_price)
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
            alpaca_positions = self.broker.get_positions()
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
            alpaca_pos = self.broker.get_position(symbol)
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
                    # v5.0: Fetch exit context (best-effort, never blocks sell)
                    exit_ctx = self._get_exit_context(symbol, sl_price)
                    self.trade_logger.log_sell(
                        symbol=symbol, qty=managed_pos.qty, price=sl_price,
                        reason="SL_FILLED_AT_ALPACA", entry_price=managed_pos.entry_price,
                        pnl_usd=pnl_usd, pnl_pct=pnl_pct, hold_duration=hold_duration,
                        day_held=days_held, sl_price=sl_price,
                        trail_active=managed_pos.trailing_active, peak_price=managed_pos.peak_price,
                        # v4.9.8: Carry entry context to SELL for analytics
                        signal_score=managed_pos.signal_score,
                        sector=managed_pos.sector,
                        atr_pct=managed_pos.atr_pct,
                        # v4.9.9: Signal source, mode, regime, rsi, momentum
                        signal_source=managed_pos.source,
                        mode=managed_pos.entry_mode,
                        regime=managed_pos.entry_regime,
                        entry_rsi=managed_pos.entry_rsi,
                        momentum_5d=managed_pos.momentum_5d,
                        # v5.0: Exit-time indicators
                        **exit_ctx,
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
            snapshot = self.broker.get_snapshot(symbol)
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
            # v4.9.4: Smart Day Trade — check before normal SL/TP
            should_dt, dt_reason = self._should_use_day_trade(symbol, managed_pos, current_price)
            if should_dt:
                logger.info(f"SMART DAY TRADE: {symbol} -- {dt_reason}")
                self._close_position(symbol, managed_pos, f"SMART_DAY_TRADE:{dt_reason}")
                return

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

            # Day 0: Trailing stop (v6.10: internal tracking only, no broker order)
            if self.TRAIL_ENABLED and not managed_pos.trailing_active and pnl_pct >= self.TRAIL_ACTIVATION_PCT:
                managed_pos.trailing_active = True
                _state_changed = True
                logger.info(f"📈 {symbol} Day 0 trailing activated at {pnl_pct:+.2f}%")
                self.alerts.alert_trailing_activated(symbol, current_price, managed_pos.peak_price)

            # Day 0: Check trailing stop trigger (manual close if drops from peak)
            if managed_pos.trailing_active and pnl_pct >= self.TRAIL_ACTIVATION_PCT:
                # Calculate what the trailing SL should be
                trailing_sl, _ = self.broker.calculate_trailing_stop(
                    entry_price,
                    managed_pos.peak_price,
                    managed_pos.current_sl_price,  # v6.10: Pass current_stop parameter
                    self.TRAIL_ACTIVATION_PCT,
                    self.TRAIL_LOCK_PCT
                )

                # If current price drops below trailing SL, close position
                if current_price < trailing_sl:
                    locked_pct = ((trailing_sl - entry_price) / entry_price) * 100
                    logger.info(f"🔒 {symbol} Day 0 trailing stop triggered: ${current_price:.2f} < ${trailing_sl:.2f} (lock {locked_pct:+.2f}%)")
                    self._close_position(symbol, managed_pos, f"DAY0_TRAILING_STOP")
                    return

                # Store what the SL should be for Day 1 transition
                managed_pos.current_sl_price = trailing_sl
                if trailing_sl > entry_price * (1 - pos_sl_pct/100):  # Only if better than original
                    _state_changed = True

            # Day 0: Log status
            logger.debug(f"PDT Guard: {symbol} Day 0 - P&L {pnl_pct:+.2f}% (SL: -{pos_sl_pct}%, TP: +{pos_tp_pct}%), Trail={'ON' if managed_pos.trailing_active else 'OFF'}")

        else:
            # ==== Day 1+: Normal operation ====

            # Place SL order if not exists (transition from Day 0)
            if not managed_pos.sl_order_id:
                logger.info(f"PDT Guard: {symbol} Day {days_held} - placing SL order now")
                sl_price = managed_pos.current_sl_price  # v4.6: use stored SL price
                sl_order = self.broker.place_stop_loss(symbol, managed_pos.qty, sl_price)
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

            # Check trailing activation (v5.6: can be disabled)
            if self.TRAIL_ENABLED and not managed_pos.trailing_active and pnl_pct >= self.TRAIL_ACTIVATION_PCT:
                managed_pos.trailing_active = True
                _state_changed = True
                logger.info(f"📈 {symbol} trailing activated at {pnl_pct:+.2f}%")
                self.alerts.alert_trailing_activated(symbol, current_price, managed_pos.peak_price)

            # Update trailing stop (only if SL order exists and trailing enabled)
            if managed_pos.trailing_active and managed_pos.sl_order_id:
                new_sl, _ = self.broker.calculate_trailing_stop(
                    entry_price,
                    managed_pos.peak_price,
                    managed_pos.current_sl_price,  # v6.10: Pass current_stop parameter
                    self.TRAIL_ACTIVATION_PCT,
                    self.TRAIL_LOCK_PCT
                )

                # v6.17: Only update if new SL is meaningfully higher (prevents order spam)
                # Minimum threshold: $0.50 OR 0.1% of current price, whichever is larger
                min_threshold = max(0.50, current_price * 0.001)
                sl_diff = new_sl - managed_pos.current_sl_price

                # Only move SL up, never down, and only if difference is significant
                if sl_diff > min_threshold:
                    logger.info(f"📈 {symbol} updating SL: ${managed_pos.current_sl_price:.2f} → ${new_sl:.2f} (+${sl_diff:.2f})")

                    # Modify SL order at Alpaca (has retry + fallback logic)
                    new_order = self.broker.modify_stop_loss(
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

        # v4.9.4: Overnight gap position — sell at open next day (9:31-10:00 ET)
        if getattr(managed_pos, 'source', '') == SignalSource.OVERNIGHT_GAP and days_held >= 1:
            et_now = self._get_et_time()
            if (et_now.hour == 9 and et_now.minute >= 31) or (et_now.hour == 10 and et_now.minute < 1):
                logger.info(f"OVERNIGHT_GAP_EXIT: {symbol} Day {days_held}, P&L {pnl_pct:+.2f}%")
                self._close_position(symbol, managed_pos, "OVERNIGHT_GAP_EXIT")
                return

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
            alpaca_pos = self.broker.get_position(symbol)
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
                self.broker.cancel_order(managed_pos.sl_order_id)

            # v4.9: Check for existing pending sell orders (prevent duplication)
            try:
                open_orders = self.broker.get_orders(status='open')
                pending_sells = [o for o in open_orders if o.symbol == symbol and o.side == 'sell' and o.type == 'market']
                if pending_sells:
                    logger.warning(f"{symbol}: Already has {len(pending_sells)} pending sell order(s) — skipping duplicate")
                    return
            except Exception as e:
                logger.warning(f"{symbol}: Could not check pending orders: {e}")

            # Guard: market must be open for market sell (prevents DLQ flood on holidays)
            if not self.broker.is_market_open():
                logger.info(f"{symbol}: Market closed — will retry close when market opens (reason: {reason})")
                return

            # Sell using actual qty from Alpaca (not managed_pos.qty)
            # In case of partial fills or discrepancies
            actual_qty = int(alpaca_pos.qty)
            sell_order = self.broker.place_market_sell(symbol, actual_qty)

            # Wait for fill with retry (max 10 seconds)
            order = None
            for _wait in range(10):
                time.sleep(1)
                order = self.broker.get_order(sell_order.id)
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

                # v5.0: Fetch exit context (best-effort, never blocks sell)
                exit_ctx = self._get_exit_context(symbol, exit_price)

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
                    # v4.9.8: Carry entry context to SELL for analytics
                    signal_score=managed_pos.signal_score,
                    sector=managed_pos.sector,
                    atr_pct=managed_pos.atr_pct,
                    # v4.9.9: Signal source, mode, regime, rsi, momentum
                    signal_source=managed_pos.source,
                    mode=managed_pos.entry_mode,
                    regime=managed_pos.entry_regime,
                    entry_rsi=managed_pos.entry_rsi,
                    momentum_5d=managed_pos.momentum_5d,
                    # v5.0: Exit-time indicators
                    **exit_ctx,
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
                verify_pos = self.broker.get_position(symbol)
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

    def check_daily_loss_limit(self, mode: str = None) -> bool:
        """
        Check if daily loss limit exceeded.

        v5.3: BEAR regime exempt from DD controls (Quant Research finding)
        Mean-reversion strategy needs room to work; DD controls destroy edge.

        Args:
            mode: Trading mode ('BEAR', 'BEAR+LOW_RISK', 'LOW_RISK', 'NORMAL')
        """
        # v5.3: BEAR DD Control Exemption
        if self.BEAR_DD_CONTROL_EXEMPT and mode and 'BEAR' in mode:
            logger.debug(f"Daily loss limit check SKIPPED (BEAR DD exempt, mode={mode})")
            return False

        account = self.broker.get_account()
        last_equity = account.last_equity
        if last_equity <= 0:
            return False
        daily_pnl_pct = ((account.equity - last_equity) / last_equity) * 100

        if daily_pnl_pct <= -self.DAILY_LOSS_LIMIT_PCT:
            logger.warning(f"Daily loss limit hit: {daily_pnl_pct:.2f}%")
            return True
        return False

    # =========================================================================
    # WEEKLY LOSS LIMIT (v4.7 NEW!)
    # =========================================================================

    def check_weekly_loss_limit(self, mode: str = None) -> bool:
        """
        Check if weekly loss limit exceeded.
        Reset ทุกวันจันทร์ (start of trading week). Thread-safe.

        v5.3: BEAR regime exempt from DD controls (Quant Research finding)

        Args:
            mode: Trading mode ('BEAR', 'BEAR+LOW_RISK', 'LOW_RISK', 'NORMAL')
        """
        # v5.3: BEAR DD Control Exemption
        if self.BEAR_DD_CONTROL_EXEMPT and mode and 'BEAR' in mode:
            logger.debug(f"Weekly loss limit check SKIPPED (BEAR DD exempt, mode={mode})")
            return False

        today = datetime.now(self.et_tz).date()

        with self._stats_lock:
            # Reset on Monday
            if today.weekday() == 0 and self.weekly_reset_date != today:
                self.weekly_realized_pnl = 0.0
                self.weekly_reset_date = today
                logger.info("Weekly P&L reset (Monday)")
                self._save_loss_counters()

            weekly_pnl = self.weekly_realized_pnl

        account = self.broker.get_account()
        capital = float(getattr(account, 'portfolio_value', self.SIMULATED_CAPITAL or 4000))
        weekly_pnl_pct = (weekly_pnl / capital) * 100

        if weekly_pnl_pct <= -self.WEEKLY_LOSS_LIMIT_PCT:
            logger.warning(f"🚨 Weekly loss limit hit: {weekly_pnl_pct:.2f}% (${weekly_pnl:.2f})")
            return True
        return False

    # =========================================================================
    # CONSECUTIVE LOSS STOP (v4.7 NEW!)
    # =========================================================================

    def check_consecutive_loss_cooldown(self, mode: str = None) -> bool:
        """
        Check if in cooldown from consecutive losses.
        แพ้ 3 ครั้งติด → หยุด 1 วัน. Thread-safe.

        v5.3: BEAR regime exempt from DD controls (Quant Research finding)

        Args:
            mode: Trading mode ('BEAR', 'BEAR+LOW_RISK', 'LOW_RISK', 'NORMAL')
        """
        # v5.3: BEAR DD Control Exemption
        if self.BEAR_DD_CONTROL_EXEMPT and mode and 'BEAR' in mode:
            logger.debug(f"Consecutive loss cooldown check SKIPPED (BEAR DD exempt, mode={mode})")
            return False

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
        """Pre-close check - handle max hold days, gap trades, and Day 0 SL"""
        logger.info("Pre-close check...")

        # v6.11: Close gap trades at market close (same day exit)
        for symbol, managed_pos in list(self.positions.items()):
            # Check if this is a gap trade (marked during entry)
            is_gap_trade = getattr(managed_pos, 'gap_trade', False)
            if is_gap_trade and managed_pos.days_held == 0:
                # Gap trades should be closed same day (intraday strategy)
                gap_pct = getattr(managed_pos, 'gap_pct', 0)
                logger.info(f"⚡ Closing GAP TRADE {symbol} at market close "
                           f"(gap: {gap_pct:+.1f}%, held: intraday)")
                self._close_position(symbol, managed_pos, "GAP_TRADE_EOD")
                continue  # Skip other checks for this position

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
                            # v5.0: Day 0 — use PDT budget if available to avoid earnings overnight risk
                            pdt_status = self.pdt_guard.get_pdt_status()
                            if pdt_status.remaining >= 1:
                                logger.warning(f"EARNINGS DAY0-SELL (pre-close): {symbol} — earnings in {days_until} day(s), using PDT budget ({pdt_status.remaining} remaining)")
                                self._close_position(symbol, managed_pos, "EARNINGS_DAY0_SELL", force=True)
                            else:
                                logger.warning(f"EARNINGS: {symbol} Day 0, PDT budget=0 — hold for EARNINGS_AUTO_SELL on Day 1+")
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
                    sl_order = self.broker.place_stop_loss(symbol, managed_pos.qty, sl_price)
                    if sl_order:
                        managed_pos.sl_order_id = sl_order.id
                        managed_pos.current_sl_price = sl_order.stop_price
                        self._save_positions_state()
                        logger.info(f"EOD SL placed for {symbol}: ${sl_order.stop_price:.2f}")
            except Exception as e:
                logger.error(f"EOD SL error for {symbol}: {e}")

    def daily_summary(self) -> Dict:
        """Generate daily summary"""
        account = self.broker.get_account()

        summary = {
            'date': self.daily_stats.date,
            'regime_status': self.daily_stats.regime_status,  # v4.0
            'regime_skipped': self.daily_stats.regime_skipped,  # v4.0
            'signals_found': self.daily_stats.signals_found,
            'signals_executed': self.daily_stats.signals_executed,
            'trades_won': self.daily_stats.trades_won,
            'trades_lost': self.daily_stats.trades_lost,
            'realized_pnl': self.daily_stats.realized_pnl,
            'account_value': account.portfolio_value,
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

    # =========================================================================
    # RUN LOOP HELPERS (v6.6 Refactor)
    # =========================================================================

    def _loop_check_loss_limits(self, mode: str) -> bool:
        """Check all loss limits. Returns True if ANY limit hit (trading blocked)."""
        if self.check_daily_loss_limit(mode=mode):
            logger.warning("Daily loss limit - no new trades today")
            return True
        if self.check_weekly_loss_limit(mode=mode):
            logger.warning("Weekly loss limit - no new trades this week")
            return True
        if self.check_consecutive_loss_cooldown(mode=mode):
            logger.warning("Consecutive loss cooldown - no new trades today")
            return True
        return False

    def _loop_get_screener_data(self) -> tuple:
        """Get data_cache and sector_regime from screener. Loads if empty."""
        data_cache = self.screener.data_cache if self.screener else {}
        if not data_cache and self.screener:
            universe = self.screener.generate_universe()[:100]
            self.screener.load_data(universe)
            data_cache = self.screener.data_cache
        sector_regime = self.screener.sector_regime if self.screener and hasattr(self.screener, 'sector_regime') else None
        return data_cache, sector_regime

    def _loop_add_breakout_signals(self, signals: list, context: str, check_pdt: bool = False) -> list:
        """Add breakout scanner signals to existing signals list."""
        if not (self.breakout_scanner and self.BREAKOUT_SCAN_ENABLED):
            return signals

        # PDT check for morning BEAR scan
        if check_pdt:
            pdt_status = self.pdt_guard.get_pdt_status()
            if pdt_status.remaining < 1:
                logger.info(f"{context}: SKIP (PDT budget=0, wait for afternoon)")
                return signals

        try:
            data_cache, sector_regime = self._loop_get_screener_data()
            breakout_signals = self.breakout_scanner.scan(
                universe=data_cache,
                sector_regime=sector_regime,
                min_score=self.BREAKOUT_MIN_SCORE,
                min_volume_mult=self.BREAKOUT_MIN_VOLUME_MULT,
                target_pct=self.BREAKOUT_TARGET_PCT,
                sl_pct=self.BREAKOUT_SL_PCT,
            )
            if breakout_signals:
                pdt_info = f" (PDT budget={self.pdt_guard.get_pdt_status().remaining})" if check_pdt else ""
                logger.info(f"{context}: {len(breakout_signals)} signals{pdt_info}")
                signals.extend(breakout_signals)
                signals.sort(key=lambda x: getattr(x, 'score', 0), reverse=True)
        except Exception as e:
            logger.warning(f"{context} error: {e}")
        return signals

    def _loop_add_overnight_signals(self, signals: list, context: str) -> list:
        """Add overnight gap scanner signals to existing signals list."""
        if not (self.overnight_scanner and self.OVERNIGHT_GAP_ENABLED):
            return signals

        try:
            data_cache, sector_regime = self._loop_get_screener_data()
            overnight_signals = self.overnight_scanner.scan(
                universe=data_cache,
                sector_regime=sector_regime,
                min_score=self.OVERNIGHT_GAP_MIN_SCORE,
                position_pct=self.OVERNIGHT_GAP_POSITION_PCT,
                target_pct=self.OVERNIGHT_GAP_TARGET_PCT,
                sl_pct=self.OVERNIGHT_GAP_SL_PCT,
            )
            if overnight_signals:
                logger.info(f"{context}: {len(overnight_signals)} signals")
                signals.extend(overnight_signals)
                signals.sort(key=lambda x: getattr(x, 'score', 0), reverse=True)
        except Exception as e:
            logger.warning(f"{context} error: {e}")
        return signals

    def _loop_with_afternoon_params(self, scan_func, scan_type: str, max_positions: int):
        """Execute scan with stricter afternoon parameters, then restore."""
        logger.info(f"🔍 ENTER _loop_with_afternoon_params: {scan_type}")
        saved_min_score = self.MIN_SCORE
        saved_gap_up = self.GAP_MAX_UP
        saved_gap_down = self.GAP_MAX_DOWN
        self.MIN_SCORE = max(self.MIN_SCORE, self.AFTERNOON_MIN_SCORE)
        self.GAP_MAX_UP = self.AFTERNOON_GAP_MAX_UP
        self.GAP_MAX_DOWN = self.AFTERNOON_GAP_MAX_DOWN
        try:
            logger.info(f"📊 Executing {scan_type} scan...")
            signals = scan_func()
            logger.info(f"✅ {scan_type}: Found {len(signals)} signals")
            self._process_scan_signals(signals, scan_type, max_positions=max_positions)
        except Exception as e:
            logger.error(f"❌ {scan_type} scan error: {e}")
        finally:
            self.MIN_SCORE = saved_min_score
            self.GAP_MAX_UP = saved_gap_up
            self.GAP_MAX_DOWN = saved_gap_down

    def _loop_update_regime_status(self, is_bull: bool):
        """Update daily_stats.regime_status based on market regime."""
        if is_bull:
            self.daily_stats.regime_status = "BULL"
        elif self.BEAR_MODE_ENABLED:
            self.daily_stats.regime_status = "BEAR_MODE"
        else:
            self.daily_stats.regime_status = "BEAR"

    def _loop_morning_scan(self, today: str) -> bool:
        """
        Execute morning scan logic. Returns True if should continue to next loop iteration.
        Handles late start, BEAR mode, and BULL mode scanning.
        """
        et_now = self._get_et_time()
        market_open = et_now.replace(
            hour=self.MARKET_OPEN_HOUR,
            minute=self.MARKET_OPEN_MINUTE,
            second=0, microsecond=0
        )
        scan_time = market_open + timedelta(minutes=self.MARKET_OPEN_SCAN_DELAY)

        # Wait for market to settle (09:30-09:35 = spread wide, volatile)
        if et_now < scan_time:
            wait_secs = (scan_time - et_now).total_seconds()
            logger.info(f"⏳ Waiting {wait_secs:.0f}s for market to settle (scan at {scan_time.strftime('%H:%M')} ET)")
            time.sleep(wait_secs)

        # Check for late start
        is_late, late_reason = self._is_late_start()
        if is_late:
            # Skip separate late_start scan — let continuous scan handle it immediately.
            # Reason: late_start scan uses stricter afternoon params → often finds 0 signals,
            # writes stale 0 to cache, and burns rate-limit quota before continuous scan runs.
            # Continuous scan (normal params, no rate-limit double-hit) handles recovery better.
            logger.info(f"⏰ {late_reason} — skipping late_start scan, continuous scan will handle")
            self.daily_stats.late_start_skipped = True
            is_bull, _ = self._check_market_regime()
            self._loop_update_regime_status(is_bull)
            self._last_continuous_scan = None  # force immediate continuous scan on next iteration

            self._morning_scan_done = today
            return True  # Continue to next iteration

        # Normal morning scan
        is_bull, _ = self._check_market_regime()
        self._loop_update_regime_status(is_bull)

        # v4.7: Check for upcoming holidays (skip new positions before long weekends)
        skip_holiday, holiday_reason = self._should_skip_before_holiday()
        if skip_holiday:
            logger.warning(f"📅 {holiday_reason}")
            self.daily_stats.regime_skipped = True
            self._morning_scan_done = today
            return False

        if not is_bull and not self.BEAR_MODE_ENABLED:
            logger.warning(f"📉 BEAR market - skipping all new trades today")
            self.daily_stats.regime_skipped = True
        elif not is_bull and self.BEAR_MODE_ENABLED:
            # BEAR mode - trade defensive sectors only
            logger.info(f"🐻 BEAR market — Smart Bear Mode active (defensive sectors only)")
            params = self._get_effective_params()
            mode = params.get('mode', 'BEAR')
            if not self._loop_check_loss_limits(mode):
                self._clear_queue_end_of_day()
                effective_max = params.get('max_positions') or self.MAX_POSITIONS
                signals = self.scan_for_signals()
                signals = self._loop_add_breakout_signals(signals, "BEAR breakout", check_pdt=True)
                # Note: overnight gap morning signals rarely fire (no today's close data yet)
                # Real overnight scan runs at 15:30 ET via _loop_overnight_gap_scan
                self._process_scan_signals(signals, "morning", max_positions=effective_max)
        else:
            # BULL mode
            params = self._get_effective_params()
            mode = params.get('mode', 'NORMAL')
            if not self._loop_check_loss_limits(mode):
                self._clear_queue_end_of_day()
                signals = self.scan_for_signals()
                signals = self._loop_add_breakout_signals(signals, "Breakout scan")
                # Note: overnight gap morning signals rarely fire (no today's close data yet)
                # Real overnight scan runs at 15:30 ET via _loop_overnight_gap_scan
                self._process_scan_signals(signals, "morning")

        self._morning_scan_done = today
        return False

    def _loop_afternoon_scan(self, today: str):
        """Execute afternoon scan if conditions are met."""
        if not self.AFTERNOON_SCAN_ENABLED:
            return
        if hasattr(self, '_afternoon_scan_done') and self._afternoon_scan_done == today:
            return

        et_now = self._get_et_time()
        afternoon_time = et_now.replace(
            hour=self.AFTERNOON_SCAN_HOUR,
            minute=self.AFTERNOON_SCAN_MINUTE,
            second=0, microsecond=0
        )
        if et_now < afternoon_time:
            return

        params = self._get_effective_params()
        afternoon_max = params.get('max_positions') or self.MAX_POSITIONS
        if len(self.positions) >= afternoon_max:
            return

        logger.info(f"☀️ Afternoon scan: {len(self.positions)}/{afternoon_max} positions, scanning for more...")
        self._afternoon_scan_done = today

        mode = params.get('mode', 'NORMAL')
        is_bull, _ = self._check_market_regime()
        if not (is_bull or self.BEAR_MODE_ENABLED) or self._loop_check_loss_limits(mode):
            return

        def scan_with_breakout():
            signals = self.scan_for_signals()
            return self._loop_add_breakout_signals(signals, "Afternoon breakout")

        self._loop_with_afternoon_params(scan_with_breakout, "afternoon", afternoon_max)

    def _loop_intraday_prefilter(self, today: str):
        """
        Run scheduled intraday pre-filter refresh (v6.27).

        Schedule (from config pre_filter_intraday_schedule + pre_filter_intraday_minute):
          Default: 10:45 (before Midday), 13:45 (before Afternoon), 15:45 (Pre-close pool update)

        Each scheduled refresh runs 'python3 pre_filter.py evening' in background —
        full 987-stock universe scan (~5-10 min), ensuring pool never shrinks.

        Benefits:
          10:45 → fresh pool with all new dip candidates since open
          13:45 → updates RSI/momentum for afternoon session
          15:45 → fresh pool ready for next morning gap-scanner
        """
        if not self.PRE_FILTER_INTRADAY_ENABLED:
            return

        et_now = self._get_et_time()
        current_hour = et_now.hour
        current_minute = et_now.minute
        sched_minute = self.PRE_FILTER_INTRADAY_MINUTE

        # Find which scheduled hour we should trigger (if any)
        triggered_hour = None
        for sched_hour in self.PRE_FILTER_INTRADAY_SCHEDULE:
            if current_hour == sched_hour and current_minute >= sched_minute:
                done_attr = f'_intraday_prefilter_done_{sched_hour}'
                if getattr(self, done_attr, None) != today:
                    triggered_hour = sched_hour
                    setattr(self, done_attr, today)
                    break

        if triggered_hour is None:
            return

        import subprocess
        import os as _os
        pre_filter_script = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)),
            'pre_filter.py'
        )

        window_labels = {10: 'Midday-prep', 13: 'Afternoon-prep', 15: 'Pre-close-update'}
        label = window_labels.get(triggered_hour, f'hour-{triggered_hour}')

        try:
            subprocess.Popen(
                ['python3', pre_filter_script, 'evening'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            logger.info(
                f"🔄 Intraday pre-filter FULL refresh [{label}] triggered at "
                f"{et_now.strftime('%H:%M')} ET (schedule {triggered_hour}:{sched_minute:02d})"
            )
        except Exception as e:
            logger.error(f"Intraday pre-filter trigger failed: {e}")

    def _loop_evening_prefilter(self, today: str):
        """
        Run evening pre-filter scan at 20:00 ET (after market close).
        Full 987-stock scan to build fresh pool for next trading day.
        Runs once per day in the sleeping/closed block.
        """
        if not self.PRE_FILTER_INTRADAY_ENABLED:
            return

        et_now = self._get_et_time()
        if et_now.hour < 20:
            return
        if getattr(self, '_evening_prefilter_done', None) == today:
            return
        self._evening_prefilter_done = today

        import subprocess
        import os as _os
        pre_filter_script = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)),
            'pre_filter.py'
        )
        try:
            subprocess.Popen(
                ['python3', pre_filter_script, 'evening'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            logger.info(f"🌙 Evening pre-filter scan triggered at {et_now.strftime('%H:%M')} ET (full 987 stocks)")
        except Exception as e:
            logger.error(f"Evening pre-filter trigger failed: {e}")

    def _loop_pre_open_prefilter(self, today: str):
        """
        Run pre-open pre-filter scan at 09:00 ET (before market open).
        Re-validates existing pool with latest prices — fast update before trading starts.
        Runs once per day in the sleeping/closed block.
        """
        if not self.PRE_FILTER_INTRADAY_ENABLED:
            return

        et_now = self._get_et_time()
        # Only run between 09:00 and 09:30 ET
        if not (et_now.hour == 9 and et_now.minute < 30):
            return
        if getattr(self, '_pre_open_prefilter_done', None) == today:
            return
        self._pre_open_prefilter_done = today

        import subprocess
        import os as _os
        pre_filter_script = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)),
            'pre_filter.py'
        )
        try:
            subprocess.Popen(
                ['python3', pre_filter_script, 'evening'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            logger.info(f"🌅 Pre-open pre-filter scan triggered at {et_now.strftime('%H:%M')} ET (full 987 stocks)")
        except Exception as e:
            logger.error(f"Pre-open pre-filter trigger failed: {e}")

    def _loop_continuous_scan(self, today: str):
        """Execute continuous scan with dynamic interval (volatile: 3min, normal: 5min)."""
        if not self.CONTINUOUS_SCAN_ENABLED:
            return
        if not (hasattr(self, '_morning_scan_done') and self._morning_scan_done == today):
            return
        if self._is_pre_close():
            return

        et_now = self._get_et_time()

        # v6.18: Dynamic interval based on VIX or time
        if self.CONTINUOUS_SCAN_DYNAMIC_ENABLED:
            # VIX-based dynamic interval
            regime_data = self.regime_detector.get_regime()
            current_vix = regime_data.get('vix', 0)
            is_volatile = current_vix > self.CONTINUOUS_SCAN_VIX_THRESHOLD
            interval_minutes = self.CONTINUOUS_SCAN_DYNAMIC_VOLATILE_INTERVAL if is_volatile else self.CONTINUOUS_SCAN_DYNAMIC_CALM_INTERVAL
            interval_label = f"VIX {current_vix:.1f} ({'volatile' if is_volatile else 'calm'})"
        else:
            # Time-based interval (original logic)
            is_volatile_period = et_now.hour < self.CONTINUOUS_SCAN_VOLATILE_END_HOUR
            interval_minutes = self.CONTINUOUS_SCAN_VOLATILE_INTERVAL if is_volatile_period else self.CONTINUOUS_SCAN_INTERVAL_MINUTES
            interval_label = "volatile" if is_volatile_period else "normal"

        interval_seconds = interval_minutes * 60

        # Check timing
        last_cont_scan = getattr(self, '_last_continuous_scan', None)
        if last_cont_scan is not None:
            elapsed = (et_now - last_cont_scan).total_seconds()
            if elapsed < interval_seconds:
                return

        params = self._get_effective_params()
        cont_max = params.get('max_positions') or self.MAX_POSITIONS
        cont_mode = params.get('mode', 'NORMAL')

        is_bull, _ = self._check_market_regime()
        if not (is_bull or self.BEAR_MODE_ENABLED) or self._loop_check_loss_limits(cont_mode):
            self._last_continuous_scan = et_now
            return

        # Dynamic params based on time of day
        use_afternoon = et_now.hour >= self.CONTINUOUS_SCAN_MIDDAY_HOUR
        session_label = "afternoon" if use_afternoon else "morning"
        is_full = len(self.positions) >= cont_max
        full_tag = " [FULL]" if is_full else ""
        logger.info(f"🔄 Continuous scan ({session_label} params, {interval_minutes}min/{interval_label}): {len(self.positions)}/{cont_max} positions{full_tag}")

        if use_afternoon:
            self._loop_with_afternoon_params(self.scan_for_signals, f"continuous_{session_label}", cont_max)
        else:
            signals = self.scan_for_signals()
            self._process_scan_signals(signals, f"continuous_{session_label}", max_positions=cont_max)

        self._last_continuous_scan = et_now

    def _loop_overnight_gap_scan(self, today: str):
        """Execute overnight gap scan (15:30-15:50 ET)."""
        if not (self.overnight_scanner and self.OVERNIGHT_GAP_ENABLED):
            return
        if hasattr(self, '_overnight_scan_done') and self._overnight_scan_done == today:
            return

        et_now = self._get_et_time()
        gap_scan_start = et_now.replace(
            hour=self.OVERNIGHT_GAP_SCAN_HOUR,
            minute=self.OVERNIGHT_GAP_SCAN_MINUTE,
            second=0, microsecond=0
        )
        gap_scan_end = et_now.replace(hour=15, minute=50, second=0, microsecond=0)
        if not (gap_scan_start <= et_now < gap_scan_end):
            return

        params = self._get_effective_params()
        overnight_max = params.get('max_positions') or self.MAX_POSITIONS
        if len(self.positions) >= overnight_max:
            return

        logger.info(f"Overnight gap scan: {len(self.positions)}/{overnight_max} positions")
        self._overnight_scan_done = today

        mode = params.get('mode', 'NORMAL')
        is_bull, _ = self._check_market_regime()
        if not (is_bull or self.BEAR_MODE_ENABLED) or self._loop_check_loss_limits(mode):
            return

        try:
            data_cache, sector_regime = self._loop_get_screener_data()
            gap_signals = self.overnight_scanner.scan(
                universe=data_cache,
                sector_regime=sector_regime,
                min_score=self.OVERNIGHT_GAP_MIN_SCORE,
                position_pct=self.OVERNIGHT_GAP_POSITION_PCT,
                target_pct=self.OVERNIGHT_GAP_TARGET_PCT,
                sl_pct=self.OVERNIGHT_GAP_SL_PCT,
            )
            self._process_scan_signals(gap_signals, "overnight_gap", max_positions=overnight_max)
        except Exception as e:
            logger.warning(f"Overnight gap scan error: {e}")

    def _loop_premarket_gap_scan(self, today: str):
        """
        Execute pre-market gap scan (6:00-9:30 AM ET)

        v6.11: New scanner based on backtest (100% win rate)
        - Scan AFTER gaps already happened
        - Detect gaps 5%+ with high volume
        - Calculate rotation worthiness
        - Only buy gaps worth rotating (net benefit > 0)
        """
        if not self.premarket_gap_scanner:
            return

        # Check if already scanned today
        if hasattr(self, '_premarket_scan_done') and self._premarket_scan_done == today:
            return

        # Check time window (6:00 AM - 9:30 AM ET)
        et_now = self._get_et_time()
        scan_start = et_now.replace(hour=6, minute=0, second=0, microsecond=0)
        scan_end = et_now.replace(hour=9, minute=30, second=0, microsecond=0)

        if not (scan_start <= et_now < scan_end):
            return

        # Check if we have room for new positions
        params = self._get_effective_params()
        max_pos = params.get('max_positions') or self.MAX_POSITIONS

        if len(self.positions) >= max_pos:
            logger.debug(f"PreMarket Gap: Positions full ({len(self.positions)}/{max_pos})")
            return

        # Mark as scanned
        self._premarket_scan_done = today

        logger.info(f"🔍 Pre-Market Gap Scan starting ({len(self.positions)}/{max_pos} positions)")

        try:
            # Scan for gaps (min confidence 80% for high-quality signals)
            gap_signals = self.premarket_gap_scanner.scan_premarket(min_confidence=80)

            if not gap_signals:
                logger.info("Pre-Market Gap: No high-confidence gaps found")
                return

            logger.info(f"✅ Found {len(gap_signals)} gap signals")

            # Convert to RapidRotationSignal format
            converted_signals = []
            for sig in gap_signals:
                # Only trade gaps worth rotating
                if not sig.worth_rotating:
                    logger.info(f"  {sig.symbol}: Gap {sig.gap_pct:+.1f}% (conf {sig.confidence}%) "
                               f"- NOT worth rotating (benefit: {sig.rotation_benefit:+.1f}%)")
                    continue

                logger.info(f"  {sig.symbol}: Gap {sig.gap_pct:+.1f}% (conf {sig.confidence}%) "
                           f"- WORTH ROTATING (benefit: {sig.rotation_benefit:+.1f}%)")

                # Create signal compatible with existing system
                try:
                    from screeners.rapid_rotation_screener import RapidRotationSignal
                except ImportError:
                    from src.screeners.rapid_rotation_screener import RapidRotationSignal

                # Entry at market open (current pre-market price)
                entry_price = sig.current_price

                # Stop loss: 2% (conservative for gap trades)
                stop_loss = round(entry_price * 0.98, 2)

                # Take profit based on estimated return
                tp_pct = min(sig.day_return_estimate, 5.0)  # Cap at 5%
                take_profit = round(entry_price * (1 + tp_pct / 100), 2)

                # Calculate risk/reward
                risk_pct = 2.0
                reward_pct = tp_pct
                risk_reward = reward_pct / risk_pct if risk_pct > 0 else 0

                # Score based on confidence + rotation benefit
                score = int(sig.confidence + min(sig.rotation_benefit * 5, 20))

                rapid_signal = RapidRotationSignal(
                    symbol=sig.symbol,
                    score=score,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_reward=round(risk_reward, 2),
                    atr_pct=3.0,  # Default ATR
                    rsi=50.0,  # Neutral RSI
                    momentum_5d=sig.gap_pct,  # Use gap as momentum
                    momentum_20d=0.0,
                    distance_from_high=0.0,
                    reasons=[
                        f"Gap: {sig.gap_pct:+.1f}%",
                        f"Confidence: {sig.confidence}%",
                        f"Catalyst: {sig.catalyst_type}",
                        f"Volume: {sig.volume_ratio:.1f}x",
                        f"Rotation benefit: {sig.rotation_benefit:+.1f}%",
                        f"Exit: Same day close (intraday)"  # Exit strategy
                    ],
                    sector="",
                    market_regime="",
                    sector_score=0,
                    alt_data_score=0,
                    sl_method="premarket_gap_fixed",
                    tp_method="premarket_gap_estimated",
                    volume_ratio=sig.volume_ratio,
                )

                # v6.11: Mark as gap trade for special exit handling
                # Gap trades should be closed at market close (same day)
                if hasattr(rapid_signal, '__dict__'):
                    rapid_signal.__dict__['gap_trade'] = True
                    rapid_signal.__dict__['gap_confidence'] = sig.confidence
                    rapid_signal.__dict__['gap_pct'] = sig.gap_pct

                converted_signals.append(rapid_signal)

            # Process signals through existing pipeline
            if converted_signals:
                self._process_scan_signals(converted_signals, "premarket_gap", max_positions=max_pos)
                logger.info(f"Pre-Market Gap: Processed {len(converted_signals)} signals")
            else:
                logger.info("Pre-Market Gap: No gaps worth rotating after filter")

        except Exception as e:
            logger.error(f"Pre-Market Gap scan error: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _loop_pem_scan(self, today: str):
        """
        v6.29: Post-Earnings Momentum scan at market open (9:35 ET).

        Detects stocks that gapped up 8%+ at open (earnings catalyst).
        Buys at market and holds until EOD (gap_trade=True → pre_close_check exits).

        Runs once per day at 9:35 ET, right after morning_scan_done.
        """
        if not self.PEM_ENABLED or not self.pem_screener:
            return
        if hasattr(self, '_pem_scan_done') and self._pem_scan_done == today:
            return

        et_now = self._get_et_time()
        scan_time = et_now.replace(
            hour=self.PEM_SCAN_HOUR,
            minute=self.PEM_SCAN_MINUTE,
            second=0, microsecond=0
        )
        # Only run between 9:35 and 10:15 (after that, open price no longer valid)
        scan_window_end = et_now.replace(hour=10, minute=15, second=0, microsecond=0)
        if et_now < scan_time or et_now > scan_window_end:
            return

        # Verify market is open
        params = self._get_effective_params()
        max_pos = params.get('max_positions') or self.MAX_POSITIONS

        # Count non-PEM positions to check if there's room
        pem_count = sum(1 for pos in self.positions.values() if getattr(pos, 'source', '') == 'pem')
        if pem_count >= self.PEM_MAX_POSITIONS:
            logger.debug(f"PEM: Max PEM positions reached ({pem_count}/{self.PEM_MAX_POSITIONS})")
            return
        if len(self.positions) >= max_pos:
            logger.debug(f"PEM: All positions full ({len(self.positions)}/{max_pos}), skipping PEM")
            return

        self._pem_scan_done = today
        logger.info(f"📊 PEM Scan: {len(self.positions)}/{max_pos} positions, "
                   f"scanning for earnings gaps ≥{self.PEM_GAP_THRESHOLD_PCT}%...")

        try:
            raw_signals = self.pem_screener.scan()
            if not raw_signals:
                return

            try:
                from screeners.rapid_rotation_screener import RapidRotationSignal
            except ImportError:
                from src.screeners.rapid_rotation_screener import RapidRotationSignal

            converted = []
            for sig in raw_signals:
                entry_price = sig['entry_price']
                sl_pct = sig['sl_pct']
                stop_loss = round(entry_price * (1 - sl_pct / 100), 2)

                rapid_signal = RapidRotationSignal(
                    symbol=sig['symbol'],
                    score=sig['score'],
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=0.0,   # EOD exit — no TP target
                    risk_reward=2.0,
                    atr_pct=sig['atr_pct'],
                    rsi=50.0,          # Neutral RSI (not a dip-bounce signal)
                    momentum_5d=sig['gap_pct'],
                    momentum_20d=0.0,
                    distance_from_high=0.0,
                    reasons=[
                        f"Earnings gap: {sig['gap_pct']:+.1f}%",
                        f"Early vol ratio: {sig['volume_early_ratio']:.2f}x",
                        f"SL: {sl_pct:.1f}% | Exit: EOD",
                    ],
                    sector="",
                    market_regime="",
                    sector_score=0,
                    alt_data_score=0,
                    sl_method="pem",     # Used to bypass gap/stock-D filters
                    tp_method="pem_eod",
                    volume_ratio=sig.get('volume_early_ratio', 1.0),
                )

                # Mark as gap trade (EOD exit) and PEM source (filter bypass)
                rapid_signal.__dict__['gap_trade'] = True
                rapid_signal.__dict__['gap_pct'] = sig['gap_pct']
                rapid_signal.__dict__['gap_confidence'] = 100
                rapid_signal.__dict__['source'] = 'pem'
                rapid_signal.__dict__['skip_entry_protection'] = True   # Bypass VWAP/timing
                rapid_signal.__dict__['skip_earnings_filter'] = True    # PEM IS the earnings play

                converted.append(rapid_signal)

            if converted:
                self._process_scan_signals(converted, "pem", max_positions=max_pos)
                logger.info(f"PEM: Processed {len(converted)} earnings gap signals")

        except Exception as e:
            logger.error(f"PEM scan error: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _run_loop(self):
        """Main trading loop (v6.6 refactored)"""
        logger.info("Trading loop started")

        last_scan_date = None
        consecutive_errors = 0

        while self.running:
            try:
                now = self._get_et_time()

                # Skip weekends
                if self._is_weekend():
                    self.state = TradingState.SLEEPING
                    time.sleep(60)
                    continue

                # Check market status (fail-closed on error)
                try:
                    clock = self.broker.get_clock()
                except Exception as clock_err:
                    err_str = str(clock_err).lower()
                    if any(kw in err_str for kw in ['maintenance', '503', '502', 'service unavailable']):
                        logger.warning(f"Alpaca API maintenance detected — waiting 60s")
                    else:
                        logger.warning(f"Clock API failed ({clock_err}) — assuming market closed (fail-closed)")
                    self.state = TradingState.SLEEPING
                    time.sleep(60)
                    continue

                if not clock.is_open:
                    self.state = TradingState.SLEEPING
                    if not getattr(self, '_market_closed_cache_written', False):
                        self._save_market_closed_cache()
                        self._market_closed_cache_written = True
                    _closed_today = now.strftime('%Y-%m-%d')
                    # Pre-market gap scan (06:00-09:30 ET)
                    self._loop_premarket_gap_scan(_closed_today)
                    # Pre-filter evening scan (20:00 ET, after close) — full 987 stocks
                    self._loop_evening_prefilter(_closed_today)
                    # Pre-filter pre-open scan (09:00 ET, before open) — re-validate ~200 stocks
                    self._loop_pre_open_prefilter(_closed_today)
                    time.sleep(60)
                    continue
                else:
                    self._market_closed_cache_written = False

                # Detect early close (e.g., day before Thanksgiving)
                try:
                    next_close = clock.next_close
                    if next_close and hasattr(next_close, 'hour') and next_close.hour < 16:
                        if not hasattr(self, '_early_close_warned') or self._early_close_warned != now.date():
                            logger.warning(f"⚠️ EARLY CLOSE today at {next_close.strftime('%H:%M ET')} — adjusting scan windows")
                            self._early_close_warned = now.date()
                except Exception:
                    pass

                # Market is open
                self.state = TradingState.TRADING
                self._reconcile_positions()

                # Morning scan (once per day)
                today = now.strftime('%Y-%m-%d')
                if last_scan_date != today:
                    # v6.21: Set date FIRST to prevent repeated execution if exception occurs
                    last_scan_date = today
                    self._loop_morning_scan(today)

                # Scheduled scans
                self._loop_pem_scan(today)           # v6.29: PEM scan at 9:35 ET
                self._loop_afternoon_scan(today)
                self._loop_intraday_prefilter(today)
                self._loop_continuous_scan(today)
                self._loop_overnight_gap_scan(today)

                # Pre-close check
                if self._is_pre_close():
                    self.state = TradingState.CLOSING
                    self.pre_close_check()

                # Monitor positions
                self.state = TradingState.MONITORING
                self.monitor_positions()
                self._write_heartbeat()

                time.sleep(self.MONITOR_INTERVAL_SECONDS)
                consecutive_errors = 0

            except Exception as e:
                # v6.21: Ignore signal handler errors (background threads can't install signal handlers)
                error_str = str(e)
                if "signal only works in main thread" in error_str:
                    logger.debug(f"Ignoring signal handler error in background thread: {e}")
                    # Don't count as error, don't set ERROR state
                    continue

                logger.error(f"Loop error: {e}")
                self.state = TradingState.ERROR
                consecutive_errors += 1

                if consecutive_errors >= self.CIRCUIT_BREAKER_MAX_ERRORS:
                    logger.critical(f"🚨 CIRCUIT BREAKER: {consecutive_errors} consecutive errors — EMERGENCY STOP")
                    self.alerts.alert_circuit_breaker(consecutive_errors)
                    self.running = False
                    self.state = TradingState.STOPPED
                    break

                time.sleep(30)

        self.daily_summary()

    # =========================================================================
    # STATUS & INFO
    # =========================================================================

    def _write_heartbeat(self):
        """v4.7 Fix #15: Write heartbeat file for external watchdog monitoring"""
        from engine.state_manager import write_heartbeat
        heartbeat_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'heartbeat.json')
        write_heartbeat(heartbeat_path, {'state': self.state.value, 'positions': len(self.positions), 'running': self.running})

    def _get_scanner_schedule(self) -> Dict:
        """Get scanner timing for UI timeline bar."""
        today = datetime.now().strftime('%Y-%m-%d')

        # v6.4: Get market calendar from Alpaca
        market_calendar = {'is_open': False, 'next_open': None, 'next_close': None, 'is_trading_day': False}
        try:
            clock = self.broker.get_clock()
            market_calendar['is_open'] = clock.is_open
            if clock.next_open:
                next_open_dt = clock.next_open if isinstance(clock.next_open, datetime) else datetime.fromisoformat(str(clock.next_open).replace('Z', '+00:00'))
                market_calendar['next_open'] = next_open_dt.isoformat()
                # Use centralized market calendar utility (Single Source of Truth)
                from src.utils.market_calendar import is_trading_day_today
                market_calendar['is_trading_day'] = is_trading_day_today(
                    next_open=next_open_dt,
                    is_market_open=clock.is_open
                )
            if clock.next_close:
                next_close_dt = clock.next_close if isinstance(clock.next_close, datetime) else datetime.fromisoformat(str(clock.next_close).replace('Z', '+00:00'))
                market_calendar['next_close'] = next_close_dt.isoformat()
        except Exception as e:
            logger.debug(f"Failed to get market calendar: {e}")

        # v6.3: Calculate next continuous scan time from engine state
        next_continuous_scan = None
        next_continuous_interval = None
        if self.CONTINUOUS_SCAN_ENABLED:
            et_now = self._get_et_time()
            last_cont = getattr(self, '_last_continuous_scan', None)

            # Determine interval based on current time (volatile vs normal)
            is_volatile = et_now.hour < self.CONTINUOUS_SCAN_VOLATILE_END_HOUR
            interval_min = self.CONTINUOUS_SCAN_VOLATILE_INTERVAL if is_volatile else self.CONTINUOUS_SCAN_INTERVAL_MINUTES
            next_continuous_interval = interval_min

            # Calculate next scan time
            if last_cont:
                next_scan = last_cont + timedelta(minutes=interval_min)
            else:
                # If no previous scan, next scan is now + interval
                next_scan = et_now + timedelta(minutes=interval_min)

            # Don't show past times or pre-close times
            pre_close_cutoff = et_now.replace(hour=15, minute=45, second=0, microsecond=0)
            if next_scan > et_now and next_scan < pre_close_cutoff:
                next_continuous_scan = next_scan.isoformat()

        # v6.10: Get sessions from RapidRotationConfig (single source of truth)
        if self._core_config:
            sessions_cfg = self._core_config.sessions
            market_open = self._core_config.market_open_minutes
            market_close = self._core_config.market_close_minutes
        else:
            # Fallback (shouldn't happen as _core_config is always loaded)
            sessions_cfg = {}
            market_open = 570
            market_close = 960

        # Build sessions list for UI timeline
        # v6.11: Added gapscan session for pre-market gap scanner
        sessions = []
        for key in ['gapscan', 'morning', 'midday', 'afternoon', 'preclose']:
            if key in sessions_cfg:
                s = sessions_cfg[key]
                # v6.10: SessionConfig object (has attributes, not dict)
                sessions.append({
                    'name': key,
                    'label': s.label if hasattr(s, 'label') else key.capitalize(),
                    'start': s.start if hasattr(s, 'start') else 0,
                    'end': s.end if hasattr(s, 'end') else 0,
                    'interval': s.interval if hasattr(s, 'interval') else 5,
                })
            elif key == 'gapscan':
                # v6.11: Gap scan not in config, add manually
                sessions.append({
                    'name': 'gapscan',
                    'label': 'Gap Scan',
                    'start': 360,  # 06:00 AM
                    'end': 575,    # 09:35 AM
                    'interval': -1,  # Once per day
                })

        return {
            'morning_scan': f"09:{30 + self.MARKET_OPEN_SCAN_DELAY:02d}",
            'morning_done': getattr(self, '_morning_scan_done', None) == today,
            'afternoon_scan': f"{self.AFTERNOON_SCAN_HOUR}:{self.AFTERNOON_SCAN_MINUTE:02d}",
            'afternoon_done': getattr(self, '_afternoon_scan_done', None) == today,
            'overnight_scan': f"{self.OVERNIGHT_GAP_SCAN_HOUR}:{self.OVERNIGHT_GAP_SCAN_MINUTE:02d}",
            'overnight_done': getattr(self, '_overnight_scan_done', None) == today,
            'pre_close': f"15:{self.PRE_CLOSE_MINUTE}",
            # v6.3: Continuous scan info from engine state
            'continuous_enabled': self.CONTINUOUS_SCAN_ENABLED,
            'next_continuous_scan': next_continuous_scan,
            'next_continuous_interval': next_continuous_interval,
            'last_continuous_scan': getattr(self, '_last_continuous_scan', None).isoformat() if getattr(self, '_last_continuous_scan', None) else None,
            # v6.4: Market calendar for UI
            'market_calendar': market_calendar,
            # v6.4: Session definitions from config (single source of truth)
            'market_open': market_open,
            'market_close': market_close,
            'sessions': sessions,
        }

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

        try:
            account = self.broker.get_account()
            # Handle both dict and object access (Alpaca SDK inconsistency)
            if isinstance(account, dict):
                account_value = account.get('portfolio_value', 0)
                account_cash = account.get('cash', 0)
            else:
                account_value = getattr(account, 'portfolio_value', 0)
                account_cash = getattr(account, 'cash', 0)
        except Exception as e:
            logger.warning(f"Failed to get account info: {e}")
            account_value = 0
            account_cash = 0
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

        # v4.9.5: Get regime details from cache
        regime_details = None
        if self._regime_cache and len(self._regime_cache) >= 4:
            regime_details = self._regime_cache[3]
            regime_details['cache_age_seconds'] = int((datetime.now() - self._regime_cache[2]).total_seconds())

        # v6.11: Add calendar status for UI header (HOLIDAY vs CLOSED display)
        from utils.market_calendar import get_market_calendar_status
        try:
            clock = self.broker.api.get_clock()
            calendar_status = get_market_calendar_status(
                next_open=clock.next_open,
                next_close=clock.next_close,
                is_market_open=clock.is_open
            )
            # Merge calendar info into regime_details for UI
            if regime_details is None:
                regime_details = {}
            regime_details['calendar'] = calendar_status
        except Exception as e:
            logger.warning(f"Calendar status error: {e}")

        return {
            'state': self.state.value,
            'running': self.running,
            'market_open': self.broker.is_market_open(),
            'market_regime': 'BULL' if is_bull else ('BEAR_MODE' if self.BEAR_MODE_ENABLED else 'BEAR'),  # v4.9.2
            'regime_detail': regime_reason,  # v4.0
            'regime_details': regime_details,  # v4.9.5: SPY details + calendar for UI
            'bear_mode_enabled': self.BEAR_MODE_ENABLED,  # v4.9.2
            'bear_allowed_sectors': self._get_bear_allowed_sectors() if not is_bull and self.BEAR_MODE_ENABLED else None,  # v4.9.2
            'bull_blocked_sectors': self._get_bull_blocked_sectors() if is_bull else None,  # v4.9.3
            'low_risk_mode': is_low_risk,  # v4.5
            'low_risk_reason': low_risk_reason,  # v4.5
            'positions': positions_count,
            'account_value': account_value,
            'cash': account_cash,
            'daily_stats': asdict(self.daily_stats),
            'safety': safety_status,
            'version': 'v6.11',  # v6.11: Gap Scanner + UI Timeline (5 sessions)
            # v4.1: Queue status
            'queue_size': queue_size,
            'queue': self.get_queue_status(),
            # v4.7: Sector exposure
            'sector_exposure': sector_exposure,
            # v4.9: Loss protection snapshot
            'consecutive_losses': consecutive_losses,
            'weekly_pnl': weekly_pnl,
            # v4.9.5: Effective runtime params
            'effective_params': self._get_effective_params(),
            # v4.9.6: Scanner schedule for UI timeline
            'scanner_schedule': self._get_scanner_schedule(),
            # VIX Adaptive tier
            'vix_tier': (
                self.vix_adaptive.strategy.current_tier.upper()
                if self.vix_adaptive and self.vix_adaptive.enabled
                   and self.vix_adaptive.strategy.current_tier
                else 'N/A'
            ),
            'vix_value': (
                round(self.vix_adaptive.strategy.current_vix, 2)
                if self.vix_adaptive and self.vix_adaptive.enabled
                   and self.vix_adaptive.strategy.current_vix is not None
                else None
            ),
            # Dynamic Sector Gate
            'effective_sector_max': self._get_effective_sector_max(),
        }

    def get_full_config(self) -> Dict:
        """
        v4.9.5: Return ALL runtime config values for UI Single Source of Truth.
        Groups all 87+ parameters so the UI never needs hardcoded values.
        """
        return {
            # --- Position Management ---
            'max_positions': self.MAX_POSITIONS,
            'position_size_pct': self.POSITION_SIZE_PCT,
            'simulated_capital': self.SIMULATED_CAPITAL,
            'risk_parity_enabled': self.RISK_PARITY_ENABLED,
            'risk_budget_pct': self.RISK_BUDGET_PCT,
            'max_position_pct': self.MAX_POSITION_PCT,

            # --- ATR-based SL/TP ---
            'sl_atr_multiplier': self.SL_ATR_MULTIPLIER,
            'sl_min_pct': self.SL_MIN_PCT,
            'sl_max_pct': self.SL_MAX_PCT,
            'tp_atr_multiplier': self.TP_ATR_MULTIPLIER,
            'tp_min_pct': self.TP_MIN_PCT,
            'tp_max_pct': self.TP_MAX_PCT,
            'target_rr': self.TARGET_RR,
            'stop_loss_pct': self.STOP_LOSS_PCT,
            'take_profit_pct': self.TAKE_PROFIT_PCT,
            'pdt_tp_threshold': self.PDT_TP_THRESHOLD,

            # --- Trailing Stop ---
            'trail_activation_pct': self.TRAIL_ACTIVATION_PCT,
            'trail_lock_pct': self.TRAIL_LOCK_PCT,
            'max_hold_days': self.MAX_HOLD_DAYS,

            # --- Risk Limits ---
            'daily_loss_limit_pct': self.DAILY_LOSS_LIMIT_PCT,
            'weekly_loss_limit_pct': self.WEEKLY_LOSS_LIMIT_PCT,
            'max_consecutive_losses': self.MAX_CONSECUTIVE_LOSSES,
            'min_score': self.MIN_SCORE,

            # --- Signal Queue ---
            'queue_enabled': self.QUEUE_ENABLED,
            'queue_atr_mult': self.QUEUE_ATR_MULT,
            'queue_min_deviation': self.QUEUE_MIN_DEVIATION,
            'queue_max_deviation': self.QUEUE_MAX_DEVIATION,
            'queue_max_size': self.QUEUE_MAX_SIZE,
            'queue_freshness_window': self.QUEUE_FRESHNESS_WINDOW,
            'queue_rescan_on_empty': self.QUEUE_RESCAN_ON_EMPTY,

            # --- Sector Diversification ---
            'sector_filter_enabled': self.SECTOR_FILTER_ENABLED,
            'max_per_sector': self.MAX_PER_SECTOR,
            'sector_loss_tracking_enabled': self.SECTOR_LOSS_TRACKING_ENABLED,
            'max_sector_consecutive_loss': self.MAX_SECTOR_CONSECUTIVE_LOSS,
            'sector_cooldown_days': self.SECTOR_COOLDOWN_DAYS,
            # Dynamic Sector Gate
            'dynamic_sector_gate_enabled': self.DYNAMIC_SECTOR_GATE_ENABLED,
            'sector_gate_normal_max': self.SECTOR_GATE_NORMAL_MAX,
            'sector_gate_skip_max': self.SECTOR_GATE_SKIP_MAX,
            'sector_gate_high_max': self.SECTOR_GATE_HIGH_MAX,
            'sector_gate_extreme_max': self.SECTOR_GATE_EXTREME_MAX,
            'effective_sector_max': self._get_effective_sector_max(),

            # --- Smart Order Execution ---
            'smart_order_enabled': self.SMART_ORDER_ENABLED,
            'smart_order_max_spread_pct': self.SMART_ORDER_MAX_SPREAD_PCT,
            'smart_order_wait_seconds': self.SMART_ORDER_WAIT_SECONDS,

            # --- Gap Filter ---
            'gap_filter_enabled': self.GAP_FILTER_ENABLED,
            'gap_max_up': self.GAP_MAX_UP,
            'gap_max_down': self.GAP_MAX_DOWN,

            # --- Earnings Filter ---
            'earnings_filter_enabled': self.EARNINGS_FILTER_ENABLED,
            'earnings_skip_days_before': self.EARNINGS_SKIP_DAYS_BEFORE,
            'earnings_skip_days_after': self.EARNINGS_SKIP_DAYS_AFTER,
            'earnings_no_data_action': self.EARNINGS_NO_DATA_ACTION,
            'earnings_auto_sell': self.EARNINGS_AUTO_SELL,
            'earnings_auto_sell_buffer_min': self.EARNINGS_AUTO_SELL_BUFFER_MIN,

            # --- Low Risk Mode ---
            'low_risk_mode_enabled': self.LOW_RISK_MODE_ENABLED,
            'low_risk_gap_max_up': self.LOW_RISK_GAP_MAX_UP,
            'low_risk_min_score': self.LOW_RISK_MIN_SCORE,
            'low_risk_position_size_pct': self.LOW_RISK_POSITION_SIZE_PCT,
            'low_risk_max_atr_pct': self.LOW_RISK_MAX_ATR_PCT,

            # --- Bear Mode ---
            'bear_mode_enabled': self.BEAR_MODE_ENABLED,
            'bear_sectors': self.BEAR_SECTORS,
            'bear_sector_threshold': self.BEAR_SECTOR_THRESHOLD,
            'bear_max_positions': self.BEAR_MAX_POSITIONS,
            'bear_min_score': self.BEAR_MIN_SCORE,
            'bear_gap_max_up': self.BEAR_GAP_MAX_UP,
            'bear_gap_max_down': self.BEAR_GAP_MAX_DOWN,
            'bear_position_size_pct': self.BEAR_POSITION_SIZE_PCT,
            'bear_max_atr_pct': self.BEAR_MAX_ATR_PCT,

            # --- Bull Sector Filter ---
            'bull_sector_filter_enabled': self.BULL_SECTOR_FILTER_ENABLED,
            'bull_sector_min_return': self.BULL_SECTOR_MIN_RETURN,

            # --- v5.3 Quant Research Findings ---
            'stock_d_filter_enabled': self.STOCK_D_FILTER_ENABLED,
            'bear_dd_control_exempt': self.BEAR_DD_CONTROL_EXEMPT,

            # --- Conviction Sizing ---
            'conviction_sizing_enabled': self.CONVICTION_SIZING_ENABLED,
            'conviction_a_plus_pct': self.CONVICTION_A_PLUS_PCT,
            'conviction_a_pct': self.CONVICTION_A_PCT,
            'conviction_b_pct': self.CONVICTION_B_PCT,

            # --- Smart Day Trade ---
            'smart_day_trade_enabled': self.SMART_DAY_TRADE_ENABLED,
            'day_trade_gap_threshold': self.DAY_TRADE_GAP_THRESHOLD,
            'day_trade_momentum_threshold': self.DAY_TRADE_MOMENTUM_THRESHOLD,
            'day_trade_emergency_enabled': self.DAY_TRADE_EMERGENCY_ENABLED,

            # --- Overnight Gap Scanner ---
            'overnight_gap_enabled': self.OVERNIGHT_GAP_ENABLED,
            'overnight_gap_scan_hour': self.OVERNIGHT_GAP_SCAN_HOUR,
            'overnight_gap_scan_minute': self.OVERNIGHT_GAP_SCAN_MINUTE,
            'overnight_gap_min_score': self.OVERNIGHT_GAP_MIN_SCORE,
            'overnight_gap_position_pct': self.OVERNIGHT_GAP_POSITION_PCT,
            'overnight_gap_target_pct': self.OVERNIGHT_GAP_TARGET_PCT,
            'overnight_gap_sl_pct': self.OVERNIGHT_GAP_SL_PCT,

            # --- Breakout Scanner ---
            'breakout_scan_enabled': self.BREAKOUT_SCAN_ENABLED,
            'breakout_min_volume_mult': self.BREAKOUT_MIN_VOLUME_MULT,
            'breakout_min_score': self.BREAKOUT_MIN_SCORE,
            'breakout_target_pct': self.BREAKOUT_TARGET_PCT,
            'breakout_sl_pct': self.BREAKOUT_SL_PCT,

            # --- Regime Filter ---
            'regime_filter_enabled': self.REGIME_FILTER_ENABLED,
            'regime_sma_period': self.REGIME_SMA_PERIOD,
            'regime_rsi_min': self.REGIME_RSI_MIN,
            'regime_return_5d_min': self.REGIME_RETURN_5D_MIN,
            'regime_vix_max': self.REGIME_VIX_MAX,

            # --- Timing ---
            'market_open_scan_delay': self.MARKET_OPEN_SCAN_DELAY,
            'market_open_scan_window': self.MARKET_OPEN_SCAN_WINDOW,
            'late_start_protection': self.LATE_START_PROTECTION,
            'afternoon_scan_enabled': self.AFTERNOON_SCAN_ENABLED,
            'afternoon_scan_hour': self.AFTERNOON_SCAN_HOUR,
            'afternoon_scan_minute': self.AFTERNOON_SCAN_MINUTE,
            'afternoon_min_score': self.AFTERNOON_MIN_SCORE,
            'afternoon_gap_max_up': self.AFTERNOON_GAP_MAX_UP,
            'afternoon_gap_max_down': self.AFTERNOON_GAP_MAX_DOWN,
            'monitor_interval_seconds': self.MONITOR_INTERVAL_SECONDS,
            'pre_close_minute': self.PRE_CLOSE_MINUTE,
        }

    def get_sector_regimes(self) -> list:
        """Return sector regime data for UI sector strip."""
        if not self.screener or not hasattr(self.screener, 'sector_regime'):
            return []
        sr = self.screener.sector_regime
        if not sr or not sr.sector_regimes:
            return []
        result = []
        for etf, sector_name in sr.SECTOR_ETFS.items():
            regime = sr.sector_regimes.get(etf, 'UNKNOWN')
            metrics = sr.sector_metrics.get(etf, {})
            result.append({
                'etf': etf,
                'sector': sector_name,
                'regime': regime,
                'return_20d': round(metrics.get('return_20d', 0), 2),
                'return_1d': round(metrics.get('return_1d', 0), 2),
                'return_1d_source': metrics.get('return_1d_source', 'etf'),  # v5.5: mcw or etf
                'rsi': round(metrics.get('rsi', 50), 1),
            })
        result.sort(key=lambda x: x['return_20d'], reverse=True)
        return result

    def get_positions_status(self) -> List[Dict]:
        """Get detailed positions status"""
        status = []

        for symbol, managed_pos in list(self.positions.items()):  # copy to avoid iteration error
            alpaca_pos = self.broker.get_position(symbol)
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
