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

import os
import json
import sqlite3
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

    # Meta
    order_id: Optional[str] = None
    version: str = "v4.5"
    source: str = "AUTO"        # AUTO, MANUAL
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
        self.db_path = db_path or os.path.join(base_dir, "trade_history.db")

        # Create log directory
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

        # Timezone
        self.et_tz = pytz.timezone('US/Eastern')

        # Initialize SQLite
        self._init_db()

        # Today's log cache
        self._today_logs: List[TradeLogEntry] = []
        self._load_today_logs()

        logger.info(f"TradeLogger initialized - logs: {self.log_dir}, db: {self.db_path}")

    def _init_db(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

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
        """Save today's logs to JSON file"""
        filepath = self._get_today_file()
        try:
            data = [asdict(entry) for entry in self._today_logs]
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
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
        sector: str = None,
        from_queue: bool = False,
        queue_signal_price: float = None,
        queue_deviation_pct: float = None,
        queue_time_minutes: float = None,
        order_id: str = None,
        # Analysis data (for future filter decisions)
        dist_from_52w_high: float = None,
        return_5d: float = None,
        return_20d: float = None,
        market_cap: float = None,
        market_cap_tier: str = None,
        beta: float = None,
        volume_ratio: float = None,
        note: str = ""
    ) -> TradeLogEntry:
        """Log a BUY trade"""
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
            sector=sector,
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
        note: str = ""
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
            note=note
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
        """Add entry to today's logs and save"""
        self._today_logs.append(entry)
        self._save_today_logs()
        self._archive_to_db(entry)

    def _archive_to_db(self, entry: TradeLogEntry):
        """Archive entry to SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
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
            conn.close()
        except Exception as e:
            logger.error(f"Error archiving to DB: {e}")

    # =========================================================================
    # QUERY METHODS
    # =========================================================================

    def get_today_logs(self, action: str = None) -> List[TradeLogEntry]:
        """Get today's logs, optionally filtered by action"""
        if action:
            return [e for e in self._today_logs if e.action == action]
        return self._today_logs.copy()

    def get_today_summary(self) -> Dict:
        """Get summary of today's trading"""
        logs = self._today_logs

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
