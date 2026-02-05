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
import os
import json
import queue
import sqlite3
import tempfile
import threading
import uuid
from datetime import datetime, date, timedelta
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import pytz

from loguru import logger


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
    spy_vs_sma: Optional[str] = None
    regime: Optional[str] = None
    vix: Optional[float] = None
    sector: Optional[str] = None
    sector_status: Optional[str] = None

    # Price Context (BUY)
    prev_close: Optional[float] = None
    gap_pct: Optional[float] = None
    signal_score: Optional[float] = None
    atr_pct: Optional[float] = None
    rsi: Optional[float] = None
    momentum_5d: Optional[float] = None
    premarket_price: Optional[float] = None

    # Exit Context (SELL)
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    trail_active: bool = False
    peak_price: Optional[float] = None
    trail_sl: Optional[float] = None

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
    correlation_id: Optional[str] = None  # Links BUY to its corresponding SELL

    # Meta
    order_id: Optional[str] = None
    version: str = "v4.8"
    source: str = "AUTO"        # AUTO, MANUAL
    signal_source: Optional[str] = None  # v4.9.9: "dip_bounce", "overnight_gap", "breakout"
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

        # Initialize SQLite
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

        logger.info(f"TradeLogger initialized - logs: {self.log_dir}, db: {self.db_path}")

    def _init_db(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # v4.9: Enable WAL mode for crash safety and concurrent reads
        cursor.execute('PRAGMA journal_mode=WAL')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                date TEXT,
                action TEXT,
                symbol TEXT,
                qty INTEGER,
                price REAL,
                reason TEXT,
                entry_price REAL,
                pnl_usd REAL,
                pnl_pct REAL,
                hold_duration TEXT,
                pdt_used INTEGER,
                pdt_remaining INTEGER,
                day_held INTEGER,
                mode TEXT,
                regime TEXT,
                spy_price REAL,
                signal_score REAL,
                gap_pct REAL,
                atr_pct REAL,
                from_queue INTEGER,
                version TEXT,
                source TEXT,
                full_data TEXT
            )
        ''')

        # Index for common queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON trades(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON trades(symbol)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_action ON trades(action)')

        conn.commit()
        conn.close()

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
        rsi: float = None,  # v4.9.9
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
            rsi=rsi,  # v4.9.9
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
            note=note
        )

        self._add_entry(entry)
        logger.info(f"📝 Trade Log: BUY {symbol} x{qty} @ ${price:.2f} [{reason}]")
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
        rsi: float = None,
        momentum_5d: float = None,
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
            rsi=rsi,
            momentum_5d=momentum_5d,
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
                    self._archive_to_db(entry)
                except Exception as e:
                    logger.error(f"Async DB archive error: {e}")
                finally:
                    self._log_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Log worker error: {e}")

    def flush(self):
        """Flush pending log entries (blocks until queue empty)"""
        try:
            self._log_queue.join()
        except Exception as e:
            logger.error(f"Error flushing trade logger: {e}")

    def _archive_to_db(self, entry: TradeLogEntry):
        """Archive entry to SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()

                # Extract date from timestamp
                dt = datetime.fromisoformat(entry.timestamp.replace('Z', '+00:00'))
                trade_date = dt.strftime('%Y-%m-%d')

                cursor.execute('''
                    INSERT OR REPLACE INTO trades (
                        id, timestamp, date, action, symbol, qty, price, reason,
                        entry_price, pnl_usd, pnl_pct, hold_duration,
                        pdt_used, pdt_remaining, day_held, mode,
                        regime, spy_price, signal_score, gap_pct, atr_pct,
                        from_queue, version, source, full_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    entry.id, entry.timestamp, trade_date, entry.action,
                    entry.symbol, entry.qty, entry.price, entry.reason,
                    entry.entry_price, entry.pnl_usd, entry.pnl_pct, entry.hold_duration,
                    1 if entry.pdt_used else 0, entry.pdt_remaining, entry.day_held, entry.mode,
                    entry.regime, entry.spy_price, entry.signal_score, entry.gap_pct, entry.atr_pct,
                    1 if entry.from_queue else 0, entry.version, entry.source,
                    json.dumps(asdict(entry), default=str)
                ))

                conn.commit()
            finally:
                conn.close()
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
        """Query historical trades from SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT * FROM trades WHERE 1=1"
            params = []

            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if action:
                query += " AND action = ?"
                params.append(action)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error querying history: {e}")
            return []

    def get_performance_stats(self, days: int = 30) -> Dict:
        """Get performance statistics for the last N days"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Total trades
            cursor.execute(
                "SELECT COUNT(*) FROM trades WHERE date >= ? AND action = 'SELL'",
                (start_date,)
            )
            total_sells = cursor.fetchone()[0]

            # Winners/Losers
            cursor.execute(
                "SELECT COUNT(*) FROM trades WHERE date >= ? AND action = 'SELL' AND pnl_usd > 0",
                (start_date,)
            )
            winners = cursor.fetchone()[0]

            # Total P&L
            cursor.execute(
                "SELECT SUM(pnl_usd) FROM trades WHERE date >= ? AND action = 'SELL'",
                (start_date,)
            )
            total_pnl = cursor.fetchone()[0] or 0

            # Average P&L
            cursor.execute(
                "SELECT AVG(pnl_usd) FROM trades WHERE date >= ? AND action = 'SELL'",
                (start_date,)
            )
            avg_pnl = cursor.fetchone()[0] or 0

            conn.close()

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
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if days == 0:
                start_date = '2020-01-01'  # All time
            else:
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            result = {
                'summary': self._get_summary(cursor, start_date),
                'by_score': self._get_by_score(cursor, start_date),
                'by_sector': self._get_by_sector(cursor, start_date),
                'by_hold_days': self._get_by_hold_days(cursor, start_date),
                'by_signal_source': self._get_by_signal_source(cursor, start_date),  # v4.9.9
                'by_mode': self._get_by_mode(cursor, start_date),  # v4.9.9
                'by_regime': self._get_by_regime(cursor, start_date),  # v4.9.9
                'by_rsi': self._get_by_rsi(cursor, start_date),  # v4.9.9
                'by_exit_reason': self._get_by_exit_reason(cursor, start_date),  # v4.9.9
                'equity_curve': self._get_equity_curve(cursor, start_date),
                'recent_trades': self._get_recent_trades(cursor, start_date, limit=50),
                'period_days': days,
                'start_date': start_date,
            }

            conn.close()
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

    def _get_summary(self, cursor, start_date: str) -> Dict:
        """Overall summary stats"""
        cursor.execute("""
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
            FROM trades WHERE date >= ?
        """, (start_date,))

        row = cursor.fetchone()
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

    def _get_by_score(self, cursor, start_date: str) -> list:
        """Win rate by score range"""
        cursor.execute("""
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
            WHERE date >= ? AND action = 'SELL' AND signal_score IS NOT NULL
            GROUP BY score_range
            ORDER BY score_range DESC
        """, (start_date,))

        results = []
        for row in cursor.fetchall():
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

    def _get_by_sector(self, cursor, start_date: str) -> list:
        """Win rate by sector (extracted from full_data JSON)"""
        cursor.execute("""
            SELECT
                json_extract(full_data, '$.sector') as sector,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= ? AND action = 'SELL'
                AND json_extract(full_data, '$.sector') IS NOT NULL
                AND json_extract(full_data, '$.sector') != ''
            GROUP BY sector
            ORDER BY total DESC
        """, (start_date,))

        results = []
        for row in cursor.fetchall():
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

    def _get_by_hold_days(self, cursor, start_date: str) -> list:
        """Win rate by holding period"""
        cursor.execute("""
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
            WHERE date >= ? AND action = 'SELL' AND day_held IS NOT NULL
            GROUP BY hold_group
            ORDER BY MIN(day_held)
        """, (start_date,))

        results = []
        for row in cursor.fetchall():
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

    def _get_by_signal_source(self, cursor, start_date: str) -> list:
        """Win rate by signal source type (v4.9.9)"""
        cursor.execute("""
            SELECT
                COALESCE(json_extract(full_data, '$.signal_source'), 'unknown') as signal_source,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= ? AND action = 'SELL'
                AND json_extract(full_data, '$.signal_source') IS NOT NULL
            GROUP BY signal_source
            ORDER BY total DESC
        """, (start_date,))

        labels = {'dip_bounce': 'Bounce', 'overnight_gap': 'O/N Gap', 'breakout': 'Breakout'}
        results = []
        for row in cursor.fetchall():
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

    def _get_by_mode(self, cursor, start_date: str) -> list:
        """Win rate by trading mode (v4.9.9)"""
        cursor.execute("""
            SELECT
                COALESCE(mode, 'UNKNOWN') as trade_mode,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= ? AND action = 'SELL' AND mode IS NOT NULL
            GROUP BY trade_mode
            ORDER BY total DESC
        """, (start_date,))

        results = []
        for row in cursor.fetchall():
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

    def _get_by_regime(self, cursor, start_date: str) -> list:
        """Win rate by market regime at entry (v4.9.9)"""
        cursor.execute("""
            SELECT
                COALESCE(regime, 'UNKNOWN') as trade_regime,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= ? AND action = 'SELL' AND regime IS NOT NULL
            GROUP BY trade_regime
            ORDER BY total DESC
        """, (start_date,))

        results = []
        for row in cursor.fetchall():
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

    def _get_by_rsi(self, cursor, start_date: str) -> list:
        """Win rate by RSI range at entry (v4.9.9)"""
        cursor.execute("""
            SELECT
                CASE
                    WHEN json_extract(full_data, '$.rsi') < 30 THEN 'RSI <30'
                    WHEN json_extract(full_data, '$.rsi') < 40 THEN 'RSI 30-39'
                    WHEN json_extract(full_data, '$.rsi') < 50 THEN 'RSI 40-49'
                    WHEN json_extract(full_data, '$.rsi') < 60 THEN 'RSI 50-59'
                    ELSE 'RSI 60+'
                END as rsi_range,
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winners,
                ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
                ROUND(SUM(pnl_usd), 2) as total_pnl
            FROM trades
            WHERE date >= ? AND action = 'SELL'
                AND json_extract(full_data, '$.rsi') IS NOT NULL
                AND json_extract(full_data, '$.rsi') > 0
            GROUP BY rsi_range
            ORDER BY MIN(json_extract(full_data, '$.rsi'))
        """, (start_date,))

        results = []
        for row in cursor.fetchall():
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

    def _get_by_exit_reason(self, cursor, start_date: str) -> list:
        """Win rate by exit reason (v4.9.9)"""
        cursor.execute("""
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
            WHERE date >= ? AND action = 'SELL'
            GROUP BY exit_type
            ORDER BY total DESC
        """, (start_date,))

        results = []
        for row in cursor.fetchall():
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

    def _get_equity_curve(self, cursor, start_date: str) -> list:
        """Cumulative P&L over time (by trade, not by date)"""
        cursor.execute("""
            SELECT timestamp, date, symbol, pnl_usd, pnl_pct
            FROM trades
            WHERE date >= ? AND action = 'SELL'
            ORDER BY timestamp ASC
        """, (start_date,))

        curve = []
        cum_pnl = 0
        for row in cursor.fetchall():
            pnl = row['pnl_usd'] or 0
            cum_pnl += pnl
            curve.append({
                'date': row['date'],
                'symbol': row['symbol'],
                'pnl': round(pnl, 2),
                'cum_pnl': round(cum_pnl, 2),
            })
        return curve

    def _get_recent_trades(self, cursor, start_date: str, limit: int = 50) -> list:
        """Recent trades for history table"""
        cursor.execute("""
            SELECT
                timestamp, date, action, symbol, qty, price, reason,
                entry_price, pnl_usd, pnl_pct, day_held, signal_score,
                mode, regime, gap_pct, atr_pct,
                json_extract(full_data, '$.sector') as sector
            FROM trades
            WHERE date >= ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (start_date, limit))

        results = []
        for row in cursor.fetchall():
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
