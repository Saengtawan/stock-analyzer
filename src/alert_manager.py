#!/usr/bin/env python3
"""
Alert Manager - Centralized alert storage for Rapid Trader

Stores alerts as JSON file, viewable in web UI.
Designed for future LINE Notify / webhook integration.

Alert levels:
  - CRITICAL: Immediate action needed (SL hit, system crash, sell failed)
  - WARNING:  Attention needed (orphan position, health check fail, stale data)
  - INFO:     Informational (trade executed, TP hit, regime change)

Usage:
    from alert_manager import get_alert_manager
    alerts = get_alert_manager()
    alerts.add('CRITICAL', 'SL Hit', 'AAPL hit stop loss at $150.00', symbol='AAPL')
"""

import os
import json
import tempfile
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class Alert:
    """Single alert entry"""
    id: int
    level: str          # CRITICAL, WARNING, INFO
    title: str          # Short title
    message: str        # Detailed message
    category: str       # trade, system, health, regime
    symbol: str         # Stock symbol (if applicable)
    timestamp: str      # ISO format
    acknowledged: bool  # User has seen it

    def to_dict(self) -> dict:
        return asdict(self)


class AlertManager:
    """Manages alert storage and retrieval"""

    MAX_ALERTS = 200       # Keep last N alerts
    ALERT_FILE = 'alerts.json'

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), '..', 'data'
            )
        self._data_dir = os.path.abspath(data_dir)
        os.makedirs(self._data_dir, exist_ok=True)
        self._file_path = os.path.join(self._data_dir, self.ALERT_FILE)
        self._lock = threading.Lock()
        self._alerts: List[Alert] = []
        self._next_id = 1
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(
        self,
        level: str,
        title: str,
        message: str,
        category: str = 'system',
        symbol: str = '',
    ) -> Alert:
        """Add a new alert. Thread-safe."""
        level = level.upper()
        if level not in ('CRITICAL', 'WARNING', 'INFO'):
            level = 'INFO'

        with self._lock:
            alert = Alert(
                id=self._next_id,
                level=level,
                title=title,
                message=message,
                category=category,
                symbol=symbol,
                timestamp=datetime.now().isoformat(),
                acknowledged=False,
            )
            self._next_id += 1
            self._alerts.append(alert)

            # Trim old alerts
            if len(self._alerts) > self.MAX_ALERTS:
                self._alerts = self._alerts[-self.MAX_ALERTS:]

            self._save()
            logger.info(f"Alert [{level}] {title}: {message}")
            return alert

    def get_recent(
        self,
        limit: int = 50,
        level: Optional[str] = None,
        category: Optional[str] = None,
        unacknowledged_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get recent alerts, newest first."""
        with self._lock:
            alerts = list(reversed(self._alerts))

        if level:
            alerts = [a for a in alerts if a.level == level.upper()]
        if category:
            alerts = [a for a in alerts if a.category == category]
        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]

        return [a.to_dict() for a in alerts[:limit]]

    def acknowledge(self, alert_id: int) -> bool:
        """Mark an alert as acknowledged."""
        with self._lock:
            for alert in self._alerts:
                if alert.id == alert_id:
                    alert.acknowledged = True
                    self._save()
                    return True
        return False

    def acknowledge_all(self) -> int:
        """Mark all alerts as acknowledged. Returns count."""
        with self._lock:
            count = 0
            for alert in self._alerts:
                if not alert.acknowledged:
                    alert.acknowledged = True
                    count += 1
            if count > 0:
                self._save()
            return count

    def clear_old(self, days: int = 7) -> int:
        """Remove alerts older than N days. Returns count removed."""
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()

        with self._lock:
            before = len(self._alerts)
            self._alerts = [
                a for a in self._alerts if a.timestamp >= cutoff_iso
            ]
            removed = before - len(self._alerts)
            if removed > 0:
                self._save()
            return removed

    def get_summary(self) -> Dict[str, Any]:
        """Get alert counts by level."""
        with self._lock:
            total = len(self._alerts)
            unack = sum(1 for a in self._alerts if not a.acknowledged)
            by_level = {}
            for a in self._alerts:
                if not a.acknowledged:
                    by_level[a.level] = by_level.get(a.level, 0) + 1

        return {
            'total': total,
            'unacknowledged': unack,
            'critical': by_level.get('CRITICAL', 0),
            'warning': by_level.get('WARNING', 0),
            'info': by_level.get('INFO', 0),
        }

    # ------------------------------------------------------------------
    # Convenience methods for common alerts
    # ------------------------------------------------------------------

    def alert_sl_hit(self, symbol: str, price: float, sl_price: float, pnl_pct: float):
        self.add(
            'CRITICAL',
            f'SL Hit: {symbol}',
            f'{symbol} hit stop loss at ${price:.2f} (SL ${sl_price:.2f}, P&L {pnl_pct:+.1f}%)',
            category='trade',
            symbol=symbol,
        )

    def alert_tp_hit(self, symbol: str, price: float, tp_price: float, pnl_pct: float):
        self.add(
            'INFO',
            f'TP Hit: {symbol}',
            f'{symbol} hit take profit at ${price:.2f} (TP ${tp_price:.2f}, P&L {pnl_pct:+.1f}%)',
            category='trade',
            symbol=symbol,
        )

    def alert_trade_executed(self, symbol: str, action: str, price: float, qty: int):
        self.add(
            'INFO',
            f'{action}: {symbol}',
            f'{action} {qty} shares of {symbol} at ${price:.2f}',
            category='trade',
            symbol=symbol,
        )

    def alert_sell_failed(self, symbol: str, reason: str):
        self.add(
            'CRITICAL',
            f'Sell Failed: {symbol}',
            f'{symbol} sell order not filled: {reason}',
            category='trade',
            symbol=symbol,
        )

    def alert_orphan_positions(self, symbols: List[str]):
        self.add(
            'WARNING',
            'Orphan Positions',
            f'Positions at Alpaca not tracked by engine: {", ".join(symbols)}',
            category='system',
        )

    def alert_health_check_fail(self, issues: List[str]):
        self.add(
            'WARNING',
            'Health Check Failed',
            f'{len(issues)} issue(s): {"; ".join(issues)}',
            category='health',
        )

    def alert_regime_change(self, new_regime: str, reason: str):
        self.add(
            'INFO',
            f'Regime: {new_regime}',
            reason,
            category='regime',
        )

    def alert_engine_error(self, error: str):
        self.add(
            'CRITICAL',
            'Engine Error',
            error,
            category='system',
        )

    def alert_emergency_stop(self, reason: str):
        self.add(
            'CRITICAL',
            'Emergency Stop',
            reason,
            category='system',
        )

    def alert_trailing_activated(self, symbol: str, price: float, peak: float):
        self.add(
            'INFO',
            f'Trail Active: {symbol}',
            f'{symbol} trailing stop activated at ${price:.2f} (peak ${peak:.2f})',
            category='trade',
            symbol=symbol,
        )

    def alert_max_hold_exit(self, symbol: str, days: int, pnl_pct: float):
        self.add(
            'WARNING',
            f'Max Hold: {symbol}',
            f'{symbol} exited after {days} days (P&L {pnl_pct:+.1f}%)',
            category='trade',
            symbol=symbol,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self):
        """Atomic write to JSON file. Caller must hold self._lock."""
        try:
            data = {
                'next_id': self._next_id,
                'alerts': [a.to_dict() for a in self._alerts],
            }
            fd, tmp_path = tempfile.mkstemp(
                dir=self._data_dir, suffix='.tmp'
            )
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                os.replace(tmp_path, self._file_path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.error(f"Failed to save alerts: {e}")

    def _load(self):
        """Load alerts from JSON file."""
        try:
            if not os.path.exists(self._file_path):
                return
            with open(self._file_path, 'r') as f:
                data = json.load(f)

            self._next_id = data.get('next_id', 1)
            for d in data.get('alerts', []):
                self._alerts.append(Alert(**d))

            logger.info(f"Loaded {len(self._alerts)} alerts (next_id={self._next_id})")
        except Exception as e:
            logger.error(f"Failed to load alerts: {e}")
            self._alerts = []
            self._next_id = 1


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------
_instance: Optional[AlertManager] = None
_instance_lock = threading.Lock()


def get_alert_manager() -> AlertManager:
    """Get or create the singleton AlertManager."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = AlertManager()
    return _instance
