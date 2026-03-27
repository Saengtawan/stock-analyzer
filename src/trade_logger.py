#!/usr/bin/env python3
"""
TRADE LOGGER v1.0
=================
Comprehensive trade logging for Rapid Trader v4.5

Features:
- Log all trades (BUY, SELL, SKIP) with full context
- JSON for today's logs (fast access)
- SQLite for historical archive (query-able)
- Filter tracking for debugging
- PDT tracking for compliance

Author: Auto Trading System
Version: 1.0
"""

import atexit
import glob
import os
import json
import queue
import tempfile
import threading
import time
import uuid
from datetime import datetime, date, timedelta
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import math
import pytz

from loguru import logger

from sqlalchemy import text, func
from database.orm.base import get_session
from database.orm.models import Trade as TradeORM, TradeEvent


def _sanitize_for_json(obj):
    """Replace NaN/Infinity with None for valid JSON (SQLite json_extract requires strict JSON)."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj

# Legacy imports kept for backward compat (use_db_layer path)
from database import TradeRepository, Trade as TradeModel
from database.manager import get_db_manager


@dataclass
class FilterResult:
    """Result of a single filter check"""
    passed: bool
    detail: str


@dataclass
class TradeLogEntry:
    """Complete trade log entry"""
    # Core
    id: str
    timestamp: str              # ISO format with timezone
    action: str                 # BUY, SELL, SKIP
    symbol: str
    qty: int
    price: float
    reason: str                 # SIGNAL, SL, TP, TRAILING, MAX_HOLD, GAP_REJECT, etc.

    # P&L (SELL only)
    entry_price: Optional[float] = None
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    hold_duration: Optional[str] = None

    # PDT
    pdt_used: bool = False
    pdt_remaining: int = 3
    day_held: int = 0
    mode: str = "NORMAL"        # NORMAL, LOW_RISK

    # Filters (BUY/SKIP)
    filters: Optional[Dict[str, Dict]] = None
    skip_reason: Optional[str] = None

    # Market Context
    spy_price: Optional[float] = None
    regime: Optional[str] = None
    vix: Optional[float] = None
    sector: Optional[str] = None
    sector_status: Optional[str] = None

    # Price Context (BUY)
    prev_close: Optional[float] = None
    gap_pct: Optional[float] = None
    signal_score: Optional[float] = None
    atr_pct: Optional[float] = None
    entry_rsi: Optional[float] = None  # v5.1 P3-23: renamed from 'rsi' for consistency with exit_rsi
    momentum_5d: Optional[float] = None

    # Exit Context (SELL)
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    trail_active: bool = False
    peak_price: Optional[float] = None

    # Queue Context (if from queue)
    from_queue: bool = False
    queue_signal_price: Optional[float] = None
    queue_deviation_pct: Optional[float] = None
    queue_time_minutes: Optional[float] = None

    # Analysis Data (for future filter decisions)
    dist_from_52w_high: Optional[float] = None   # % below 52-week high
    return_5d: Optional[float] = None            # 5-day return before entry
    return_20d: Optional[float] = None           # 20-day return (trend)
    market_cap: Optional[float] = None           # Market cap in billions
    market_cap_tier: Optional[str] = None        # MEGA/LARGE/MID/SMALL
    beta: Optional[float] = None                 # Stock beta
    volume_ratio: Optional[float] = None         # Today volume / avg volume
    composite_score: Optional[float] = None      # v6.96: Env quality 0-1 (RSI+Ret20d+Mom5d+SPY+Sector)
    new_score: Optional[float] = None            # v7.5: IC-weighted DIP quality score [0-100] (logged for DIP_SCORE_REJECT analysis)
    momentum_20d: Optional[float] = None         # v7.5: 20d momentum (for LONG_TERM_DOWNTREND filter analysis)
    distance_from_high: Optional[float] = None   # v7.5: distance from 20d high, positive conv (for NOT_NEAR_HIGH analysis)

    # Execution Data (v4.8: Smart Buy tracking)
    order_type: Optional[str] = None          # limit / market_fallback / market
    signal_price: Optional[float] = None      # Price at signal time
    limit_price: Optional[float] = None       # Limit price placed
    fill_price: Optional[float] = None        # Actual fill price
    slippage_pct: Optional[float] = None      # Slippage from signal price
    bid_ask_spread_pct: Optional[float] = None  # Spread at order time
    fill_time_sec: Optional[float] = None     # Seconds to fill
    fill_status: Optional[str] = None         # filled / partial / cancelled

    # Price Action (v4.8: Trailing Stop tracking)
    trough_price: Optional[float] = None      # Lowest price during hold
    max_gain_pct: Optional[float] = None      # Peak unrealized gain %
    max_drawdown_pct: Optional[float] = None  # Max drawdown from entry %
    exit_efficiency: Optional[float] = None   # exit P&L / max_gain (how much captured)

    # v7.5: Excursion analytics
    mfe_pct: Optional[float] = None          # Max favorable excursion (peak profit % during hold)
    mae_pct: Optional[float] = None          # Max adverse excursion (max loss % during hold)
    hold_minutes: Optional[int] = None       # Actual hold duration in minutes

    # v7.5: Exit quality analytics
    exit_vs_vwap_pct: Optional[float] = None      # Exit price vs VWAP at close time
    pct_from_mfe_to_close: Optional[float] = None # Profit given back: (mfe_pct - final_pnl_pct)
    next_day_open_pct: Optional[float] = None     # OVN: (D+1 open / sell_price - 1) × 100, filled by cron
    mfe_timestamp: Optional[str] = None           # ET timestamp when MFE (peak profit) was achieved

    # v7.5: Config-at-entry snapshot (dedicated columns for cohort analysis)
    sl_multiplier: Optional[float] = None         # ATR multiplier used for SL (e.g. 1.5)
    sl_method: Optional[str] = None               # 'atr' | 'pem' | 'fixed'
    trail_activation_pct: Optional[float] = None  # Trailing activate threshold at entry time
    trail_lock_pct: Optional[float] = None        # Trailing lock % at entry time
    tp_pct: Optional[float] = None                # TP % used at entry time

    # Config Snapshot (v4.8: Version comparison)
    config_version: Optional[str] = None
    config_min_score: Optional[float] = None
    config_position_size_pct: Optional[float] = None
    config_sl_atr_mult: Optional[float] = None
    config_tp_atr_mult: Optional[float] = None
    config_trail_activation_pct: Optional[float] = None
    config_trail_lock_pct: Optional[float] = None
    config_max_hold_days: Optional[int] = None
    config_max_per_sector: Optional[int] = None
    config_gap_max_up_pct: Optional[float] = None
    config_daily_loss_limit_pct: Optional[float] = None
    config_weekly_loss_limit_pct: Optional[float] = None
    config_max_consecutive_losses: Optional[int] = None
    config_smart_order_enabled: Optional[bool] = None

    # Correlation
    scan_id: Optional[str] = None  # v5.1 P2-22: Links BUY to originating scan event
    correlation_id: Optional[str] = None  # Links BUY to its corresponding SELL

    # Meta
    order_id: Optional[str] = None
    version: str = "v5.1.0"
    source: str = "AUTO"        # AUTO, MANUAL
    signal_source: Optional[str] = None  # v4.9.9: "dip_bounce", "overnight_gap", "breakout"
    # v5.0: Earnings context (captured at SKIP time — irreplaceable after earnings)
    earnings_date: Optional[str] = None           # Earnings announcement date
    days_until_earnings: Optional[int] = None     # Days from skip to earnings
    eps_estimate: Optional[float] = None          # Consensus EPS estimate
    eps_estimate_high: Optional[float] = None     # Highest analyst EPS estimate
    eps_estimate_low: Optional[float] = None      # Lowest analyst EPS estimate
    revenue_estimate: Optional[float] = None      # Consensus revenue estimate
    analyst_recommendation: Optional[float] = None # 1.0=Strong Buy to 5.0=Sell
    analyst_count: Optional[int] = None           # Number of analysts covering
    target_mean_price: Optional[float] = None     # Mean analyst price target
    earnings_quarterly_growth: Optional[float] = None  # YoY quarterly earnings growth
    revenue_growth: Optional[float] = None        # Revenue growth rate
    short_percent_of_float: Optional[float] = None     # Short interest %
    # v5.0: Exit-time indicators (current market state at sell time)
    exit_rsi: Optional[float] = None                     # RSI at sell time
    exit_volume_ratio: Optional[float] = None            # Volume ratio at sell time
    exit_momentum_1d: Optional[float] = None             # 1-day momentum at sell time
    exit_spy_change: Optional[float] = None              # SPY 5d return at sell time
    exit_bid_ask_spread: Optional[float] = None          # Bid-ask spread % at sell time
    # v5.0: Entry timing context (market context at buy time)
    entry_minutes_after_open: Optional[int] = None       # Minutes after 9:30 ET
    entry_spy_pct_above_sma: Optional[float] = None    # SPY vs SMA20 at entry
    entry_vix: Optional[float] = None                    # VIX at entry time
    entry_sector_change_1d: Optional[float] = None       # Sector ETF 1d change at entry
    # v6.24: VIX spike detection context (market stress indicators at buy time)
    entry_spy_intraday_pct: Optional[float] = None       # SPY % from today's open (intraday)
    entry_vix_change_pct: Optional[float] = None         # VIX % vs yesterday close
    entry_uvxy_pct: Optional[float] = None               # UVXY % from today's open (fear gauge)
    entry_qqq_spy_spread: Optional[float] = None         # QQQ intraday% - SPY intraday% (risk-on spread)
    note: str = ""


class TradeLogger:
    """
    Trade Logger - handles logging and storage of all trades

    Storage:
    - JSON: Today's logs (rapid_trade_log_YYYY-MM-DD.json)
    - SQLite: Historical archive (trade_history.db)
    """

    def __init__(self, log_dir: str = None, db_path: str = None):
        """Initialize Trade Logger"""
        # Set paths
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.log_dir = log_dir or os.path.join(base_dir, "trade_logs")
        self.db_path = db_path or os.path.join(base_dir, "data", "trade_history.db")

        # Create log directory
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

        # Timezone
        self.et_tz = pytz.timezone('US/Eastern')

        # Use direct SQLite (TradeRepository schema doesn't match trades table)
        self.use_db_layer = False
        self.trade_repo = None
        self._init_db()

        # Today's log cache (thread-safe)
        self._logs_lock = threading.Lock()
        self._today_logs: List[TradeLogEntry] = []
        self._load_today_logs()
        self._loaded_date = datetime.now(self.et_tz).strftime('%Y-%m-%d')

        # v4.7 Fix #14: Async logging with background queue
        self._log_queue: queue.Queue = queue.Queue()
        self._log_worker_thread = threading.Thread(
            target=self._log_worker, daemon=True, name="TradeLogWorker"
        )
        self._log_worker_thread.start()

        # Flush pending log entries on shutdown
        atexit.register(self.flush)

        # v5.1: Clean up old log files on startup
        self._cleanup_old_logs(max_age_days=30)

        # Backfill any JSON logs not yet in DB (catch missed async writes)
        self._backfill_missing_logs()

        db_method = "TradeRepository" if self.use_db_layer else "direct SQLite"
        logger.info(f"TradeLogger initialized - logs: {self.log_dir}, db: {self.db_path} ({db_method})")

    def _cleanup_old_logs(self, max_age_days: int = 30):
        """Delete JSON log files older than max_age_days (v5.1 log rotation)."""
        try:
            cutoff = datetime.now() - timedelta(days=max_age_days)
            pattern = os.path.join(self.log_dir, "rapid_trade_log_*.json")
            removed = 0
            for filepath in glob.glob(pattern):
                try:
                    # Extract date from filename: rapid_trade_log_YYYY-MM-DD.json
                    basename = os.path.basename(filepath)
                    date_str = basename.replace("rapid_trade_log_", "").replace(".json", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if file_date < cutoff:
                        os.remove(filepath)
                        removed += 1
                except (ValueError, OSError):
                    continue
            if removed:
                logger.info(f"Log rotation: removed {removed} log files older than {max_age_days} days")
        except Exception as e:
            logger.warning(f"Log rotation error: {e}")

    def _backfill_missing_logs(self):
        """Backfill JSON log files that were not archived to DB (startup recovery)."""
        try:
            # Get all existing IDs in DB
            with get_session() as session:
                existing_ids = {row[0] for row in session.execute(
                    text("SELECT id FROM trades")
                ).fetchall()}

            # Scan all trade_log_*.json files (current + archive)
            patterns = [
                os.path.join(self.log_dir, "trade_log_*.json"),
                os.path.join(self.log_dir, "archive", "*", "trade_log_*.json"),
            ]
            inserted = 0
            for pattern in patterns:
                for filepath in glob.glob(pattern):
                    try:
                        with open(filepath) as f:
                            entries = json.load(f)
                        if not isinstance(entries, list):
                            continue
                        for t in entries:
                            tid = t.get('id')
                            if not tid or tid in existing_ids:
                                continue
                            ts = t.get('timestamp', '')
                            try:
                                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                trade_date = dt.strftime('%Y-%m-%d')
                            except Exception:
                                trade_date = ts[:10] if ts else ''
                            with get_session() as session:
                                session.execute(text('''
                                    INSERT OR REPLACE INTO trades (
                                        id, timestamp, date, action, symbol, qty, price, reason,
                                        entry_price, pnl_usd, pnl_pct, hold_duration,
                                        pdt_used, pdt_remaining, day_held, mode,
                                        regime, spy_price, signal_score, gap_pct, atr_pct,
                                        from_queue, version, source, full_data,
                                        volume_ratio, composite_score
                                    ) VALUES (:id, :ts, :trade_date, :action, :symbol, :qty, :price, :reason,
                                        :entry_price, :pnl_usd, :pnl_pct, :hold_duration,
                                        :pdt_used, :pdt_remaining, :day_held, :mode,
                                        :regime, :spy_price, :signal_score, :gap_pct, :atr_pct,
                                        :from_queue, :version, :source, :full_data,
                                        :volume_ratio, :composite_score)
                                '''), {
                                    'id': tid, 'ts': ts, 'trade_date': trade_date,
                                    'action': t.get('action'), 'symbol': t.get('symbol'), 'qty': t.get('qty'),
                                    'price': t.get('price') or t.get('fill_price'),
                                    'reason': t.get('reason'), 'entry_price': t.get('entry_price'),
                                    'pnl_usd': t.get('pnl_usd'), 'pnl_pct': t.get('pnl_pct'),
                                    'hold_duration': t.get('hold_duration', str(t.get('day_held', 0)) + 'd'),
                                    'pdt_used': 1 if t.get('pdt_used') else 0,
                                    'pdt_remaining': t.get('pdt_remaining'), 'day_held': t.get('day_held'),
                                    'mode': t.get('mode'),
                                    'regime': t.get('regime'), 'spy_price': t.get('spy_price'),
                                    'signal_score': t.get('signal_score'),
                                    'gap_pct': t.get('gap_pct'), 'atr_pct': t.get('atr_pct'),
                                    'from_queue': 1 if t.get('from_queue') else 0,
                                    'version': t.get('version') or t.get('config_version'),
                                    'source': t.get('source'),
                                    'full_data': json.dumps(t, default=str),
                                    'volume_ratio': t.get('volume_ratio'),
                                    'composite_score': t.get('composite_score'),
                                })
                            existing_ids.add(tid)
                            inserted += 1
                    except Exception as e:
                        logger.debug(f"Backfill skip {filepath}: {e}")
            if inserted > 0:
                logger.info(f"Backfilled {inserted} missing trade records from JSON logs to DB")
        except Exception as e:
            logger.warning(f"Backfill error: {e}")

    def _init_db(self):
        """Initialize database — ORM handles schema via get_session()/engine.
        Table creation is now managed by SQLAlchemy models.
        WAL mode + pragmas are set by database.orm.base.get_engine().
        """
        pass

    def _get_today_file(self) -> str:
        """Get today's JSON log file path"""
        today = datetime.now(self.et_tz).strftime('%Y-%m-%d')
        return os.path.join(self.log_dir, f"trade_log_{today}.json")

    def _load_today_logs(self):
        """Load today's logs from JSON file"""
        filepath = self._get_today_file()
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    self._today_logs = [self._dict_to_entry(d) for d in data]
                logger.info(f"Loaded {len(self._today_logs)} logs from {filepath}")
            except Exception as e:
                logger.error(f"Error loading today's logs: {e}")
                self._today_logs = []
        else:
            self._today_logs = []

    def _save_today_logs(self):
        """Save today's logs to JSON file (atomic write)"""
        filepath = self._get_today_file()
        try:
            data = [asdict(entry) for entry in self._today_logs]
            # Atomic write: temp file + rename (prevents corruption on crash)
            dir_path = os.path.dirname(filepath)
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                os.replace(tmp_path, filepath)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.error(f"Error saving today's logs: {e}")

    def _dict_to_entry(self, d: Dict) -> TradeLogEntry:
        """Convert dict to TradeLogEntry"""
        return TradeLogEntry(**{k: v for k, v in d.items() if k in TradeLogEntry.__dataclass_fields__})

    def _get_et_timestamp(self) -> str:
        """Get current timestamp in ET as ISO string"""
        return datetime.now(self.et_tz).isoformat()

    def _generate_id(self) -> str:
        """Generate unique trade ID"""
        today = datetime.now(self.et_tz).strftime('%Y%m%d')
        short_uuid = str(uuid.uuid4())[:8]
        return f"tr_{today}_{short_uuid}"

    # =========================================================================
    # LOGGING METHODS
    # =========================================================================

    @staticmethod
    def _compute_composite_score(
        entry_rsi: float = None,
        return_20d: float = None,
        momentum_5d: float = None,
        entry_spy_pct_above_sma: float = None,
        entry_sector_change_1d: float = None,
    ) -> Optional[float]:
        """v6.96: Compute 0-1 environment quality score for DIP trades.
        Uses normalized distance from ideal values across 5 dimensions.
          A. RSI        ideal=42, tol=15  (oversold)
          B. Ret20d     ideal=0%,  tol=5  (not extended)
          C. Mom5d      ideal=-1%, tol=4  (slight dip, not crash)
          D. SPY>SMA    ideal=0%,  tol=2  (market neutral/recovering)
          E. Sector_1d  ideal=0.3%,tol=1  (sector aligned)
        Returns None if fewer than 3 dimensions available.
        """
        def _dim(x, ideal, tol):
            if x is None: return None
            return max(0.0, 1.0 - abs(x - ideal) / tol)

        scores = [
            _dim(entry_rsi,                42,   15),
            _dim(return_20d,               0,     5),
            _dim(momentum_5d,             -1.0,   4),
            _dim(entry_spy_pct_above_sma,  0,     2),
            _dim(entry_sector_change_1d,   0.3,   1),
        ]
        known = [s for s in scores if s is not None]
        if len(known) < 3:
            return None
        return round(sum(known) / len(known), 3)

    def log_buy(
        self,
        symbol: str,
        qty: int,
        price: float,
        reason: str = "SIGNAL",
        filters: Dict[str, Dict] = None,
        pdt_remaining: int = 3,
        mode: str = "NORMAL",
        spy_price: float = None,
        regime: str = None,
        prev_close: float = None,
        gap_pct: float = None,
        signal_score: float = None,
        atr_pct: float = None,
        entry_rsi: float = None,  # v5.1 P3-23: renamed from rsi
        momentum_5d: float = None,  # v4.9.9
        sector: str = None,
        signal_source: str = None,  # v4.9.9: "dip_bounce", "overnight_gap", "breakout"
        from_queue: bool = False,
        queue_signal_price: float = None,
        queue_deviation_pct: float = None,
        queue_time_minutes: float = None,
        order_id: str = None,
        # Analysis data
        dist_from_52w_high: float = None,
        return_5d: float = None,
        return_20d: float = None,
        market_cap: float = None,
        market_cap_tier: str = None,
        beta: float = None,
        volume_ratio: float = None,
        momentum_20d: float = None,       # v7.5: for LONG_TERM_DOWNTREND filter analysis
        distance_from_high: float = None, # v7.5: for NOT_NEAR_HIGH filter analysis (positive conv)
        new_score: float = None,          # v7.5: IC-weighted DIP quality score [0-100]
        # Execution data (v4.8)
        order_type: str = None,
        signal_price: float = None,
        limit_price: float = None,
        fill_price: float = None,
        slippage_pct: float = None,
        bid_ask_spread_pct: float = None,
        fill_time_sec: float = None,
        fill_status: str = None,
        # Config snapshot (v4.8)
        config_snapshot: Dict = None,
        correlation_id: str = None,
        scan_id: str = None,  # v5.1 P2-22: links BUY to originating scan
        # v5.0: Entry timing context
        entry_minutes_after_open: int = None,
        entry_spy_pct_above_sma: float = None,
        entry_vix: float = None,
        entry_sector_change_1d: float = None,
        # v6.24: VIX spike detection context
        entry_spy_intraday_pct: float = None,
        entry_vix_change_pct: float = None,
        entry_uvxy_pct: float = None,
        entry_qqq_spy_spread: float = None,
        # v7.5: Config-at-entry for cohort analysis
        sl_multiplier: float = None,
        sl_method: str = None,
        trail_activation_pct: float = None,
        trail_lock_pct: float = None,
        tp_pct: float = None,
        note: str = ""
    ) -> TradeLogEntry:
        """Log a BUY trade"""
        cs = config_snapshot or {}
        entry = TradeLogEntry(
            id=self._generate_id(),
            timestamp=self._get_et_timestamp(),
            action="BUY",
            symbol=symbol,
            qty=qty,
            price=price,
            reason=reason,
            pdt_remaining=pdt_remaining,
            day_held=0,
            mode=mode,
            filters=filters,
            spy_price=spy_price,
            regime=regime,
            prev_close=prev_close,
            gap_pct=gap_pct,
            signal_score=signal_score,
            atr_pct=atr_pct,
            entry_rsi=entry_rsi,  # v5.1 P3-23
            momentum_5d=momentum_5d,  # v4.9.9
            sector=sector,
            signal_source=signal_source,  # v4.9.9
            from_queue=from_queue,
            queue_signal_price=queue_signal_price,
            queue_deviation_pct=queue_deviation_pct,
            queue_time_minutes=queue_time_minutes,
            order_id=order_id,
            # Analysis data
            dist_from_52w_high=dist_from_52w_high,
            return_5d=return_5d,
            return_20d=return_20d,
            market_cap=market_cap,
            market_cap_tier=market_cap_tier,
            beta=beta,
            volume_ratio=volume_ratio,
            momentum_20d=momentum_20d,
            distance_from_high=distance_from_high,
            new_score=new_score,
            # Execution data
            order_type=order_type,
            signal_price=signal_price,
            limit_price=limit_price,
            fill_price=fill_price,
            slippage_pct=slippage_pct,
            bid_ask_spread_pct=bid_ask_spread_pct,
            fill_time_sec=fill_time_sec,
            fill_status=fill_status,
            # Config snapshot
            config_version=cs.get('version'),
            config_min_score=cs.get('min_score'),
            config_position_size_pct=cs.get('position_size_pct'),
            config_sl_atr_mult=cs.get('sl_atr_mult'),
            config_tp_atr_mult=cs.get('tp_atr_mult'),
            config_trail_activation_pct=cs.get('trail_activation_pct'),
            config_trail_lock_pct=cs.get('trail_lock_pct'),
            config_max_hold_days=cs.get('max_hold_days'),
            config_max_per_sector=cs.get('max_per_sector'),
            config_gap_max_up_pct=cs.get('gap_max_up_pct'),
            config_daily_loss_limit_pct=cs.get('daily_loss_limit_pct'),
            config_weekly_loss_limit_pct=cs.get('weekly_loss_limit_pct'),
            config_max_consecutive_losses=cs.get('max_consecutive_losses'),
            config_smart_order_enabled=cs.get('smart_order_enabled'),
            correlation_id=correlation_id,
            scan_id=scan_id,  # v5.1 P2-22
            # v5.0: Entry timing context
            entry_minutes_after_open=entry_minutes_after_open,
            entry_spy_pct_above_sma=entry_spy_pct_above_sma,
            entry_vix=entry_vix,
            entry_sector_change_1d=entry_sector_change_1d,
            # v6.24: VIX spike detection context
            entry_spy_intraday_pct=entry_spy_intraday_pct,
            entry_vix_change_pct=entry_vix_change_pct,
            entry_uvxy_pct=entry_uvxy_pct,
            entry_qqq_spy_spread=entry_qqq_spy_spread,
            # v7.5: Config-at-entry for cohort analysis
            sl_multiplier=sl_multiplier,
            sl_method=sl_method,
            trail_activation_pct=trail_activation_pct,
            trail_lock_pct=trail_lock_pct,
            tp_pct=tp_pct,
            note=note
        )

        # v6.96: compute environment quality score at buy time
        entry.composite_score = self._compute_composite_score(
            entry_rsi=entry_rsi,
            return_20d=return_20d,
            momentum_5d=momentum_5d,
            entry_spy_pct_above_sma=entry_spy_pct_above_sma,
            entry_sector_change_1d=entry_sector_change_1d,
        )

        self._add_entry(entry)
        logger.info(f"📝 Trade Log: BUY {symbol} x{qty} @ ${price:.2f} [{reason}] env={entry.composite_score}")
        return entry

    def log_sell(
        self,
        symbol: str,
        qty: int,
        price: float,
        reason: str,
        entry_price: float,
        pnl_usd: float,
        pnl_pct: float,
        hold_duration: str,
        pdt_used: bool = False,
        pdt_remaining: int = 3,
        day_held: int = 0,
        sl_price: float = None,
        tp_price: float = None,
        trail_active: bool = False,
        peak_price: float = None,
        order_id: str = None,
        # Price action (v4.8)
        trough_price: float = None,
        max_gain_pct: float = None,
        max_drawdown_pct: float = None,
        exit_efficiency: float = None,
        correlation_id: str = None,
        note: str = "",
        # Entry context for analytics (v4.9.8)
        signal_score: float = None,
        sector: str = None,
        atr_pct: float = None,
        # v4.9.9: Additional entry context
        signal_source: str = None,
        mode: str = None,
        regime: str = None,
        entry_rsi: float = None,  # v5.1 P3-23: renamed from rsi
        momentum_5d: float = None,
        # v5.0: Exit-time indicators
        exit_rsi: float = None,
        exit_volume_ratio: float = None,
        exit_momentum_1d: float = None,
        exit_spy_change: float = None,
        exit_bid_ask_spread: float = None,
        # v7.5: Excursion analytics
        mfe_pct: float = None,
        mae_pct: float = None,
        hold_minutes: int = None,
        # v7.5: Exit quality analytics
        exit_vs_vwap_pct: float = None,
        pct_from_mfe_to_close: float = None,
        next_day_open_pct: float = None,
        mfe_timestamp: str = None,
    ) -> TradeLogEntry:
        """Log a SELL trade"""
        entry = TradeLogEntry(
            id=self._generate_id(),
            timestamp=self._get_et_timestamp(),
            action="SELL",
            symbol=symbol,
            qty=qty,
            price=price,
            reason=reason,
            entry_price=entry_price,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            hold_duration=hold_duration,
            pdt_used=pdt_used,
            pdt_remaining=pdt_remaining,
            day_held=day_held,
            sl_price=sl_price,
            tp_price=tp_price,
            trail_active=trail_active,
            peak_price=peak_price,
            order_id=order_id,
            # Price action
            trough_price=trough_price,
            max_gain_pct=max_gain_pct,
            max_drawdown_pct=max_drawdown_pct,
            exit_efficiency=exit_efficiency,
            correlation_id=correlation_id,
            note=note,
            # Entry context for analytics
            signal_score=signal_score,
            sector=sector,
            atr_pct=atr_pct,
            # v4.9.9: Additional entry context
            signal_source=signal_source,
            mode=mode,
            regime=regime,
            entry_rsi=entry_rsi,
            momentum_5d=momentum_5d,
            # v5.0: Exit-time indicators
            exit_rsi=exit_rsi,
            exit_volume_ratio=exit_volume_ratio,
            exit_momentum_1d=exit_momentum_1d,
            exit_spy_change=exit_spy_change,
            exit_bid_ask_spread=exit_bid_ask_spread,
            # v7.5: Excursion analytics
            mfe_pct=mfe_pct,
            mae_pct=mae_pct,
            hold_minutes=hold_minutes,
            # v7.5: Exit quality analytics
            exit_vs_vwap_pct=exit_vs_vwap_pct,
            pct_from_mfe_to_close=pct_from_mfe_to_close,
            next_day_open_pct=next_day_open_pct,
            mfe_timestamp=mfe_timestamp,
        )

        self._add_entry(entry)
        pnl_sign = "+" if pnl_usd >= 0 else ""
        logger.info(f"📝 Trade Log: SELL {symbol} x{qty} @ ${price:.2f} [{reason}] {pnl_sign}${pnl_usd:.2f} ({pnl_sign}{pnl_pct:.1f}%)")
        return entry

    def log_skip(
        self,
        symbol: str,
        price: float,
        reason: str,
        skip_detail: str,
        filters: Dict[str, Dict] = None,
        signal_score: float = None,
        gap_pct: float = None,
        regime: str = None,
        # v5.0: Signal context for outcome tracking
        sector: str = None,
        signal_source: str = None,
        atr_pct: float = None,
        entry_rsi: float = None,  # v5.1 P3-23: renamed from rsi
        momentum_5d: float = None,
        volume_ratio: float = None,  # v7.03
        momentum_20d: float = None,       # v7.5: for LONG_TERM_DOWNTREND filter analysis
        distance_from_high: float = None, # v7.5: for NOT_NEAR_HIGH filter analysis (positive conv)
        mode: str = None,
        # v5.0: Earnings context (EARNINGS_REJECT only)
        earnings_date: str = None,
        days_until_earnings: int = None,
        eps_estimate: float = None,
        eps_estimate_high: float = None,
        eps_estimate_low: float = None,
        revenue_estimate: float = None,
        analyst_recommendation: float = None,
        analyst_count: int = None,
        target_mean_price: float = None,
        earnings_quarterly_growth: float = None,
        revenue_growth: float = None,
        short_percent_of_float: float = None,
        new_score: float = None,     # v7.5: IC-weighted DIP quality score (for DIP_SCORE_REJECT analysis)
        note: str = ""
    ) -> TradeLogEntry:
        """Log a SKIP (rejected signal)"""
        entry = TradeLogEntry(
            id=self._generate_id(),
            timestamp=self._get_et_timestamp(),
            action="SKIP",
            symbol=symbol,
            qty=0,
            price=price,
            reason=reason,
            filters=filters,
            skip_reason=skip_detail,
            signal_score=signal_score,
            gap_pct=gap_pct,
            regime=regime,
            # v5.0: Signal context
            sector=sector,
            signal_source=signal_source,
            atr_pct=atr_pct,
            entry_rsi=entry_rsi,
            momentum_5d=momentum_5d,
            volume_ratio=volume_ratio,  # v7.03
            momentum_20d=momentum_20d,
            distance_from_high=distance_from_high,
            mode=mode,
            # v5.0: Earnings context
            earnings_date=earnings_date,
            days_until_earnings=days_until_earnings,
            eps_estimate=eps_estimate,
            eps_estimate_high=eps_estimate_high,
            eps_estimate_low=eps_estimate_low,
            revenue_estimate=revenue_estimate,
            analyst_recommendation=analyst_recommendation,
            analyst_count=analyst_count,
            target_mean_price=target_mean_price,
            earnings_quarterly_growth=earnings_quarterly_growth,
            revenue_growth=revenue_growth,
            short_percent_of_float=short_percent_of_float,
            new_score=new_score,
            note=note
        )

        self._add_entry(entry)
        logger.info(f"📝 Trade Log: SKIP {symbol} @ ${price:.2f} [{reason}] {skip_detail}")
        return entry

    def _add_entry(self, entry: TradeLogEntry):
        """Add entry to today's logs and queue for async DB archive"""
        with self._logs_lock:
            # Check for midnight rollover
            current_date = datetime.now(self.et_tz).strftime('%Y-%m-%d')
            if self._today_logs and hasattr(self, '_loaded_date') and self._loaded_date != current_date:
                logger.info(f"Midnight rollover: {self._loaded_date} -> {current_date}")
                self._today_logs = []
                self._loaded_date = current_date
            self._today_logs.append(entry)
            # Sync JSON save (fast, ~1ms) — ensures no data loss
            self._save_today_logs()
        # Queue for async DB archive (slower, non-blocking)
        self._log_queue.put(entry)

    def _log_worker(self):
        """Background worker that archives log entries to DB asynchronously"""
        while True:
            try:
                entry = self._log_queue.get(timeout=5)
                try:
                    self._archive_to_db_with_retry(entry)
                except Exception as e:
                    logger.error(f"Async DB archive error (all retries failed): {e}")
                finally:
                    self._log_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Log worker error: {e}")

    def _archive_to_db_with_retry(self, entry, max_retries: int = 3):
        """Archive entry to DB with retry on failure (v5.1)."""
        for attempt in range(max_retries):
            try:
                self._archive_to_db(entry)
                return  # Success
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(f"DB archive retry {attempt + 1}/{max_retries} for {entry.id}: {e}")
                    time.sleep(delay)
                else:
                    raise  # Re-raise on final attempt

    def has_sell_logged(self, symbol: str, since_hours: int = 72) -> bool:
        """Check if a SELL trade was already logged for symbol in last N hours.
        Used to prevent double-logging when detecting offline SL fills on restart."""
        try:
            with get_session() as session:
                count = session.execute(text("""
                    SELECT COUNT(*) FROM trades WHERE symbol=:symbol AND action='SELL'
                    AND timestamp >= datetime('now', :offset)
                """), {'symbol': symbol, 'offset': f'-{since_hours} hours'}).scalar()
                return count > 0
        except Exception:
            return False  # Fail-open: better to log duplicate than miss it

    def flush(self):
        """Flush pending log entries (blocks until queue empty)"""
        try:
            self._log_queue.join()
        except Exception as e:
            logger.error(f"Error flushing trade logger: {e}")

    def _archive_to_db(self, entry: TradeLogEntry):
        """Archive entry to SQLite via ORM session."""
        try:
            dt = datetime.fromisoformat(entry.timestamp.replace('Z', '+00:00'))
            trade_date = dt.strftime('%Y-%m-%d')

            with get_session() as session:
                session.execute(text('''
                    INSERT OR REPLACE INTO trades (
                        id, timestamp, date, action, symbol, qty, price, reason,
                        entry_price, pnl_usd, pnl_pct, hold_duration,
                        pdt_used, pdt_remaining, day_held, mode,
                        regime, spy_price, signal_score, gap_pct, atr_pct,
                        from_queue, version, source, full_data,
                        volume_ratio, composite_score,
                        mfe_pct, mae_pct, hold_minutes,
                        exit_vs_vwap_pct, pct_from_mfe_to_close, next_day_open_pct,
                        signal_source, entry_rsi, entry_vix,
                        new_score, momentum_20d, distance_from_high,
                        mfe_timestamp,
                        sl_multiplier, sl_method,
                        trail_activation_pct, trail_lock_pct, tp_pct,
                        fill_time_sec, slippage_pct, sector,
                        bounce_pct_from_lod
                    ) VALUES (:id, :timestamp, :trade_date, :action,
                        :symbol, :qty, :price, :reason,
                        :entry_price, :pnl_usd, :pnl_pct, :hold_duration,
                        :pdt_used, :pdt_remaining, :day_held, :mode,
                        :regime, :spy_price, :signal_score, :gap_pct, :atr_pct,
                        :from_queue, :version, :source, :full_data,
                        :volume_ratio, :composite_score,
                        :mfe_pct, :mae_pct, :hold_minutes,
                        :exit_vs_vwap_pct, :pct_from_mfe_to_close, :next_day_open_pct,
                        :signal_source, :entry_rsi, :entry_vix,
                        :new_score, :momentum_20d, :distance_from_high,
                        :mfe_timestamp,
                        :sl_multiplier, :sl_method,
                        :trail_activation_pct, :trail_lock_pct, :tp_pct,
                        :fill_time_sec, :slippage_pct, :sector,
                        :bounce_pct_from_lod)
                '''), {
                    'id': entry.id, 'timestamp': entry.timestamp,
                    'trade_date': trade_date, 'action': entry.action,
                    'symbol': entry.symbol, 'qty': entry.qty,
                    'price': entry.price, 'reason': entry.reason,
                    'entry_price': entry.entry_price, 'pnl_usd': entry.pnl_usd,
                    'pnl_pct': entry.pnl_pct, 'hold_duration': entry.hold_duration,
                    'pdt_used': 1 if entry.pdt_used else 0,
                    'pdt_remaining': entry.pdt_remaining,
                    'day_held': entry.day_held, 'mode': entry.mode,
                    'regime': entry.regime, 'spy_price': entry.spy_price,
                    'signal_score': entry.signal_score, 'gap_pct': entry.gap_pct,
                    'atr_pct': entry.atr_pct,
                    'from_queue': 1 if entry.from_queue else 0,
                    'version': entry.version, 'source': entry.source,
                    'full_data': json.dumps(_sanitize_for_json(asdict(entry)), default=str),
                    'volume_ratio': entry.volume_ratio,
                    'composite_score': entry.composite_score,
                    'mfe_pct': entry.mfe_pct, 'mae_pct': entry.mae_pct,
                    'hold_minutes': entry.hold_minutes,
                    'exit_vs_vwap_pct': entry.exit_vs_vwap_pct,
                    'pct_from_mfe_to_close': entry.pct_from_mfe_to_close,
                    'next_day_open_pct': entry.next_day_open_pct,
                    'signal_source': entry.signal_source,
                    'entry_rsi': entry.entry_rsi,
                    'entry_vix': getattr(entry, 'entry_vix', None),
                    'new_score': entry.new_score,
                    'momentum_20d': entry.momentum_20d,
                    'distance_from_high': entry.distance_from_high,
                    'mfe_timestamp': getattr(entry, 'mfe_timestamp', None),
                    'sl_multiplier': getattr(entry, 'sl_multiplier', None),
                    'sl_method': getattr(entry, 'sl_method', None),
                    'trail_activation_pct': getattr(entry, 'trail_activation_pct', None),
                    'trail_lock_pct': getattr(entry, 'trail_lock_pct', None),
                    'tp_pct': getattr(entry, 'tp_pct', None),
                    'fill_time_sec': entry.fill_time_sec,
                    'slippage_pct': entry.slippage_pct,
                    'sector': entry.sector,
                    'bounce_pct_from_lod': getattr(entry, 'bounce_pct_from_lod', None),
                })
        except Exception as e:
            logger.error(f"Error archiving to DB: {e}")

    # =========================================================================
    # QUERY METHODS
    # =========================================================================

    def get_today_logs(self, action: str = None) -> List[TradeLogEntry]:
        """Get today's logs, optionally filtered by action"""
        with self._logs_lock:
            if action:
                return [e for e in self._today_logs if e.action == action]
            return self._today_logs.copy()

    def get_today_summary(self) -> Dict:
        """Get summary of today's trading"""
        with self._logs_lock:
            logs = self._today_logs.copy()

        buys = [e for e in logs if e.action == "BUY"]
        sells = [e for e in logs if e.action == "SELL"]
        skips = [e for e in logs if e.action == "SKIP"]

        total_pnl = sum(e.pnl_usd or 0 for e in sells)
        winners = [e for e in sells if (e.pnl_usd or 0) > 0]
        losers = [e for e in sells if (e.pnl_usd or 0) < 0]

        return {
            'date': datetime.now(self.et_tz).strftime('%Y-%m-%d'),
            'total_trades': len(buys) + len(sells),
            'buys': len(buys),
            'sells': len(sells),
            'skips': len(skips),
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': len(winners) / len(sells) * 100 if sells else 0,
            'total_pnl_usd': total_pnl,
            'pdt_used': sum(1 for e in logs if e.pdt_used),
            'low_risk_trades': sum(1 for e in logs if e.mode == "LOW_RISK"),
            'queue_trades': sum(1 for e in logs if e.from_queue)
        }

    def get_recent_logs(self, limit: int = 10) -> List[Dict]:
        """Get recent logs for UI display"""
        with self._logs_lock:
            logs = self._today_logs[-limit:] if len(self._today_logs) > limit else self._today_logs
            return [asdict(e) for e in reversed(logs)]  # Most recent first

    def query_history(
        self,
        start_date: str = None,
        end_date: str = None,
        symbol: str = None,
        action: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """Query historical trades via ORM session."""
        try:
            with get_session() as session:
                q = session.query(TradeORM)
                if start_date:
                    q = q.filter(TradeORM.date >= start_date)
                if end_date:
                    q = q.filter(TradeORM.date <= end_date)
                if symbol:
                    q = q.filter(TradeORM.symbol == symbol)
                if action:
                    q = q.filter(TradeORM.action == action)
                q = q.order_by(TradeORM.timestamp.desc()).limit(limit)
                rows = q.all()
                # Convert ORM objects to dicts
                result = []
                for r in rows:
                    d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
                    result.append(d)
                return result
        except Exception as e:
            logger.error(f"Error querying history: {e}")
            return []

    def get_performance_stats(self, days: int = 30) -> Dict:
        """Get performance statistics for the last N days via ORM."""
        try:
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            with get_session() as session:
                base = session.query(TradeORM).filter(
                    TradeORM.date >= start_date, TradeORM.action == 'SELL'
                )
                total_sells = base.count()
                winners = base.filter(TradeORM.pnl_usd > 0).count()
                total_pnl = session.query(func.sum(TradeORM.pnl_usd)).filter(
                    TradeORM.date >= start_date, TradeORM.action == 'SELL'
                ).scalar() or 0
                avg_pnl = session.query(func.avg(TradeORM.pnl_usd)).filter(
                    TradeORM.date >= start_date, TradeORM.action == 'SELL'
                ).scalar() or 0

            return {
                'period_days': days,
                'total_sells': total_sells,
                'winners': winners,
                'losers': total_sells - winners,
                'win_rate': winners / total_sells * 100 if total_sells > 0 else 0,
                'total_pnl': total_pnl,
                'avg_pnl': avg_pnl
            }
        except Exception as e:
            logger.error(f"Error getting performance stats: {e}")
            return {}

    # =========================================================================
    # ANALYTICS QUERIES (v1.0 - Trade Performance Dashboard)
    # =========================================================================

    def get_analytics(self, days: int = 30) -> Dict:
        """
        Comprehensive analytics for dashboard.

        Returns all metrics in a single call:
        - summary: total trades, win rate, total P&L, avg P&L
        - by_score: win rate grouped by score ranges
        - by_sector: win rate grouped by sector
        - by_hold_days: win rate grouped by holding period
        - equity_curve: cumulative P&L over time
        - recent_trades: last 50 trades for history table
        """
        try:
            if days == 0:
                start_date = '2020-01-01'  # All time
            else:
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            with get_session() as session:
                result = {
                    'summary': self._get_summary(session, start_date),
                    'by_score': self._get_by_score(session, start_date),
                    'by_sector': self._get_by_sector(session, start_date),
                    'by_hold_days': self._get_by_hold_days(session, start_date),
                    'by_signal_source': self._get_by_signal_source(session, start_date),
                    'by_mode': self._get_by_mode(session, start_date),
                    'by_regime': self._get_by_regime(session, start_date),
                    'by_rsi': self._get_by_rsi(session, start_date),
                    'by_exit_reason': self._get_by_exit_reason(session, start_date),
                    'equity_curve': self._get_equity_curve(session, start_date),
                    'recent_trades': self._get_recent_trades(session, start_date, limit=50),
                    'period_days': days,
                    'start_date': start_date,
                }
            return result

        except Exception as e:
            logger.error(f"Analytics error: {e}")
            return {
                'summary': {},
                'by_score': [],
                'by_sector': [],
                'by_hold_days': [],
                'by_signal_source': [],
                'by_mode': [],
                'by_regime': [],
                'by_rsi': [],
                'by_exit_reason': [],
                'equity_curve': [],
                'recent_trades': [],
                'period_days': days,
                'error': str(e)
            }

    def _get_summary(self, session, start_date: str) -> Dict:
        """Overall summary stats"""
        row = session.execute(text("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN action = 'BUY' THEN 1 ELSE 0 END) as buys,
                SUM(CASE WHEN action = 'SELL' THEN 1 ELSE 0 END) as sells,
                SUM(CASE WHEN action = 'SKIP' THEN 1 ELSE 0 END) as skips,
                SUM(CASE WHEN action = 'SELL' AND pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                SUM(CASE WHEN action = 'SELL' AND pnl_usd <= 0 THEN 1 ELSE 0 END) as losers,
                SUM(CASE WHEN action = 'SELL' THEN pnl_usd ELSE 0 END) as total_pnl,
                AVG(CASE WHEN action = 'SELL' THEN pnl_usd END) as avg_pnl,
                AVG(CASE WHEN action = 'SELL' THEN pnl_pct END) as avg_pnl_pct,
                MAX(CASE WHEN action = 'SELL' THEN pnl_usd END) as best_trade,
                MIN(CASE WHEN action = 'SELL' THEN pnl_usd END) as worst_trade
            FROM trades WHERE date >= :start_date
        """), {'start_date': start_date}).mappings().fetchone()

        if not row or row['total_trades'] == 0:
            return {'total_trades': 0, 'sells': 0, 'win_rate': 0, 'total_pnl': 0}

        sells = row['sells'] or 0
        winners = row['winners'] or 0
        return {
            'total_trades': row['total_trades'],
            'buys': row['buys'] or 0,
            'sells': sells,
            'skips': row['skips'] or 0,
            'winners': winners,
            'losers': row['losers'] or 0,
            'win_rate': round(winners / sells * 100, 1) if sells > 0 else 0,
            'total_pnl': round(row['total_pnl'] or 0, 2),
            'avg_pnl': round(row['avg_pnl'] or 0, 2),
            'avg_pnl_pct': round(row['avg_pnl_pct'] or 0, 2),
            'best_trade': round(row['best_trade'] or 0, 2),
            'worst_trade': round(row['worst_trade'] or 0, 2),
        }

    def _get_by_score(self, session, start_date: str) -> list:
        """Win rate by score range"""
        rows = session.execute(text("""
            SELECT
                CASE
                    WHEN signal_score >= 98 THEN '98-100'
                    WHEN signal_score >= 95 THEN '95-97'
                    WHEN signal_score >= 90 THEN '90-94'
                    WHEN signal_score >= 85 THEN '85-89'
                    ELSE '<85'
                END as score_range,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= :start_date AND action = 'SELL' AND signal_score IS NOT NULL
            GROUP BY score_range
            ORDER BY score_range DESC
        """), {'start_date': start_date}).mappings().fetchall()

        results = []
        for row in rows:
            total = row['total']
            winners = row['winners'] or 0
            results.append({
                'range': row['score_range'],
                'total': total,
                'winners': winners,
                'losers': total - winners,
                'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
                'avg_pnl_pct': row['avg_pnl_pct'] or 0,
                'total_pnl': row['total_pnl'] or 0,
            })
        return results

    def _get_by_sector(self, session, start_date: str) -> list:
        """Win rate by sector (extracted from full_data JSON)"""
        rows = session.execute(text("""
            SELECT
                json_extract(full_data, '$.sector') as sector,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= :start_date AND action = 'SELL'
                AND json_extract(full_data, '$.sector') IS NOT NULL
                AND json_extract(full_data, '$.sector') != ''
            GROUP BY sector
            ORDER BY total DESC
        """), {'start_date': start_date}).mappings().fetchall()

        results = []
        for row in rows:
            total = row['total']
            winners = row['winners'] or 0
            results.append({
                'sector': row['sector'],
                'total': total,
                'winners': winners,
                'losers': total - winners,
                'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
                'avg_pnl_pct': row['avg_pnl_pct'] or 0,
                'total_pnl': row['total_pnl'] or 0,
            })
        return results

    def _get_by_hold_days(self, session, start_date: str) -> list:
        """Win rate by holding period"""
        rows = session.execute(text("""
            SELECT
                CASE
                    WHEN day_held = 0 THEN 'Day 0'
                    WHEN day_held = 1 THEN 'Day 1'
                    WHEN day_held = 2 THEN 'Day 2'
                    WHEN day_held = 3 THEN 'Day 3'
                    WHEN day_held >= 4 THEN 'Day 4+'
                    ELSE 'Unknown'
                END as hold_group,
                day_held as sort_key,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= :start_date AND action = 'SELL' AND day_held IS NOT NULL
            GROUP BY hold_group
            ORDER BY MIN(day_held)
        """), {'start_date': start_date}).mappings().fetchall()

        results = []
        for row in rows:
            total = row['total']
            winners = row['winners'] or 0
            results.append({
                'group': row['hold_group'],
                'total': total,
                'winners': winners,
                'losers': total - winners,
                'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
                'avg_pnl_pct': row['avg_pnl_pct'] or 0,
                'total_pnl': row['total_pnl'] or 0,
            })
        return results

    def _get_by_signal_source(self, session, start_date: str) -> list:
        """Win rate by signal source type (v4.9.9)"""
        rows = session.execute(text("""
            SELECT
                COALESCE(json_extract(full_data, '$.signal_source'), 'unknown') as signal_source,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= :start_date AND action = 'SELL'
                AND json_extract(full_data, '$.signal_source') IS NOT NULL
            GROUP BY signal_source
            ORDER BY total DESC
        """), {'start_date': start_date}).mappings().fetchall()

        labels = {'dip_bounce': 'Bounce', 'overnight_gap': 'O/N Gap', 'breakout': 'Breakout'}
        results = []
        for row in rows:
            total = row['total']
            winners = row['winners'] or 0
            results.append({
                'source': labels.get(row['signal_source'], row['signal_source']),
                'total': total,
                'winners': winners,
                'losers': total - winners,
                'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
                'avg_pnl_pct': row['avg_pnl_pct'] or 0,
                'total_pnl': row['total_pnl'] or 0,
            })
        return results

    def _get_by_mode(self, session, start_date: str) -> list:
        """Win rate by trading mode (v4.9.9)"""
        rows = session.execute(text("""
            SELECT
                COALESCE(mode, 'UNKNOWN') as trade_mode,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= :start_date AND action = 'SELL' AND mode IS NOT NULL
            GROUP BY trade_mode
            ORDER BY total DESC
        """), {'start_date': start_date}).mappings().fetchall()

        results = []
        for row in rows:
            total = row['total']
            winners = row['winners'] or 0
            results.append({
                'mode': row['trade_mode'],
                'total': total,
                'winners': winners,
                'losers': total - winners,
                'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
                'avg_pnl_pct': row['avg_pnl_pct'] or 0,
                'total_pnl': row['total_pnl'] or 0,
            })
        return results

    def _get_by_regime(self, session, start_date: str) -> list:
        """Win rate by market regime at entry (v4.9.9)"""
        rows = session.execute(text("""
            SELECT
                COALESCE(regime, 'UNKNOWN') as trade_regime,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= :start_date AND action = 'SELL' AND regime IS NOT NULL
            GROUP BY trade_regime
            ORDER BY total DESC
        """), {'start_date': start_date}).mappings().fetchall()

        results = []
        for row in rows:
            total = row['total']
            winners = row['winners'] or 0
            results.append({
                'regime': row['trade_regime'],
                'total': total,
                'winners': winners,
                'losers': total - winners,
                'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
                'avg_pnl_pct': row['avg_pnl_pct'] or 0,
                'total_pnl': row['total_pnl'] or 0,
            })
        return results

    def _get_by_rsi(self, session, start_date: str) -> list:
        """Win rate by RSI range at entry (v4.9.9, v5.1 P3-23: entry_rsi compat)"""
        # COALESCE handles both old ($.rsi) and new ($.entry_rsi) JSON field names
        rows = session.execute(text("""
            SELECT
                CASE
                    WHEN COALESCE(json_extract(full_data, '$.entry_rsi'), json_extract(full_data, '$.rsi')) < 30 THEN 'RSI <30'
                    WHEN COALESCE(json_extract(full_data, '$.entry_rsi'), json_extract(full_data, '$.rsi')) < 40 THEN 'RSI 30-39'
                    WHEN COALESCE(json_extract(full_data, '$.entry_rsi'), json_extract(full_data, '$.rsi')) < 50 THEN 'RSI 40-49'
                    WHEN COALESCE(json_extract(full_data, '$.entry_rsi'), json_extract(full_data, '$.rsi')) < 60 THEN 'RSI 50-59'
                    ELSE 'RSI 60+'
                END as rsi_range,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= :start_date AND action = 'SELL'
                AND COALESCE(json_extract(full_data, '$.entry_rsi'), json_extract(full_data, '$.rsi')) IS NOT NULL
                AND COALESCE(json_extract(full_data, '$.entry_rsi'), json_extract(full_data, '$.rsi')) > 0
            GROUP BY rsi_range
            ORDER BY MIN(COALESCE(json_extract(full_data, '$.entry_rsi'), json_extract(full_data, '$.rsi')))
        """), {'start_date': start_date}).mappings().fetchall()

        results = []
        for row in rows:
            total = row['total']
            winners = row['winners'] or 0
            results.append({
                'range': row['rsi_range'],
                'total': total,
                'winners': winners,
                'losers': total - winners,
                'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
                'avg_pnl_pct': row['avg_pnl_pct'] or 0,
                'total_pnl': row['total_pnl'] or 0,
            })
        return results

    def _get_by_exit_reason(self, session, start_date: str) -> list:
        """Win rate by exit reason (v4.9.9)"""
        rows = session.execute(text("""
            SELECT
                CASE
                    WHEN reason LIKE '%SL%' THEN 'Stop Loss'
                    WHEN reason LIKE '%TAKE_PROFIT%' OR reason LIKE '%TP%' THEN 'Take Profit'
                    WHEN reason LIKE '%TRAIL%' THEN 'Trailing Stop'
                    WHEN reason LIKE '%TIME%' OR reason LIKE '%MAX_HOLD%' THEN 'Time Exit'
                    WHEN reason LIKE '%EARNINGS%' THEN 'Earnings'
                    ELSE reason
                END as exit_type,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= :start_date AND action = 'SELL'
            GROUP BY exit_type
            ORDER BY total DESC
        """), {'start_date': start_date}).mappings().fetchall()

        results = []
        for row in rows:
            total = row['total']
            winners = row['winners'] or 0
            results.append({
                'reason': row['exit_type'],
                'total': total,
                'winners': winners,
                'losers': total - winners,
                'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
                'avg_pnl_pct': row['avg_pnl_pct'] or 0,
                'total_pnl': row['total_pnl'] or 0,
            })
        return results

    def _get_equity_curve(self, session, start_date: str) -> list:
        """Cumulative P&L over time (by trade, not by date)"""
        rows = session.execute(text("""
            SELECT timestamp, date, symbol, pnl_usd, pnl_pct
            FROM trades
            WHERE date >= :start_date AND action = 'SELL'
            ORDER BY timestamp ASC
        """), {'start_date': start_date}).mappings().fetchall()

        curve = []
        cum_pnl = 0
        for row in rows:
            pnl = row['pnl_usd'] or 0
            cum_pnl += pnl
            curve.append({
                'date': row['date'],
                'symbol': row['symbol'],
                'pnl': round(pnl, 2),
                'cum_pnl': round(cum_pnl, 2),
            })
        return curve

    def _get_recent_trades(self, session, start_date: str, limit: int = 50) -> list:
        """Recent trades for history table"""
        rows = session.execute(text("""
            SELECT
                timestamp, date, action, symbol, qty, price, reason,
                entry_price, pnl_usd, pnl_pct, day_held, signal_score,
                mode, regime, gap_pct, atr_pct,
                json_extract(full_data, '$.sector') as sector,
                json_extract(full_data, '$.signal_source') as signal_source
            FROM trades
            WHERE date >= :start_date
            ORDER BY timestamp DESC
            LIMIT :limit
        """), {'start_date': start_date, 'limit': limit}).mappings().fetchall()

        results = []
        for row in rows:
            results.append({
                'timestamp': row['timestamp'],
                'date': row['date'],
                'action': row['action'],
                'symbol': row['symbol'],
                'qty': row['qty'],
                'price': row['price'],
                'reason': row['reason'],
                'entry_price': row['entry_price'],
                'pnl_usd': round(row['pnl_usd'], 2) if row['pnl_usd'] else None,
                'pnl_pct': round(row['pnl_pct'], 2) if row['pnl_pct'] else None,
                'day_held': row['day_held'],
                'score': row['signal_score'],
                'sector': row['sector'],
                'mode': row['mode'],
                'regime': row['regime'],
                'signal_source': row['signal_source'],
            })
        return results


# Singleton instance
_logger: Optional[TradeLogger] = None


def get_trade_logger() -> TradeLogger:
    """Get singleton TradeLogger instance"""
    global _logger
    if _logger is None:
        _logger = TradeLogger()
    return _logger


# =============================================================================
# TEST
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("TRADE LOGGER v1.0 - TEST")
    print("=" * 60)

    trade_log = TradeLogger()

    # Test BUY log
    print("\n[1] Testing BUY log...")
    buy_entry = trade_log.log_buy(
        symbol="AMD",
        qty=7,
        price=244.36,
        reason="SIGNAL",
        filters={
            "regime": {"passed": True, "detail": "BULL +0.8%"},
            "gap": {"passed": True, "detail": "+1.2%"},
            "earnings": {"passed": True, "detail": "> 30 days"},
            "score": {"passed": True, "detail": "87"}
        },
        pdt_remaining=3,
        mode="NORMAL",
        spy_price=595.20,
        regime="BULL",
        prev_close=241.50,
        gap_pct=1.2,
        signal_score=87,
        atr_pct=3.5,
        sector="Technology"
    )
    print(f"  Created: {buy_entry.id}")

    # Test SELL log
    print("\n[2] Testing SELL log...")
    sell_entry = trade_log.log_sell(
        symbol="AMD",
        qty=7,
        price=252.08,
        reason="TRAILING",
        entry_price=244.36,
        pnl_usd=54.04,
        pnl_pct=3.1,
        hold_duration="4h 32m",
        pdt_used=True,
        pdt_remaining=2,
        day_held=0,
        trail_active=True,
        peak_price=254.50
    )
    print(f"  Created: {sell_entry.id}")

    # Test SKIP log
    print("\n[3] Testing SKIP log...")
    skip_entry = trade_log.log_skip(
        symbol="NVDA",
        price=142.50,
        reason="GAP_REJECT",
        skip_detail="Gap +3.2% > 2%",
        filters={
            "regime": {"passed": True, "detail": "BULL"},
            "gap": {"passed": False, "detail": "+3.2% > 2%"}
        },
        gap_pct=3.2
    )
    print(f"  Created: {skip_entry.id}")

    # Get today's summary
    print("\n[4] Today's Summary:")
    summary = trade_log.get_today_summary()
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # Get recent logs
    print("\n[5] Recent Logs:")
    recent = trade_log.get_recent_logs(5)
    for log in recent:
        print(f"  {log['timestamp'][:19]} | {log['action']:4} | {log['symbol']:5} | {log['reason']}")

    print("\n" + "=" * 60)
    print("TRADE LOGGER TEST COMPLETE")
    print("=" * 60)
