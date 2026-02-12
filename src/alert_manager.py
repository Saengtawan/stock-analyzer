#!/usr/bin/env python3
"""
Alert Manager - Centralized alert storage for Rapid Trader

Database-backed alert storage using AlertsRepository.

Alert levels:
  - CRITICAL: Immediate action needed (SL hit, system crash, sell failed)
  - WARNING:  Attention needed (orphan position, health check fail, stale data)
  - INFO:     Informational (trade executed, TP hit, regime change)

Usage:
    from alert_manager import get_alert_manager
    alerts = get_alert_manager()
    alerts.add('CRITICAL', 'SL Hit', 'AAPL hit stop loss at $150.00', symbol='AAPL')
"""

import threading
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from loguru import logger
try:
    import pytz
    _ET = pytz.timezone('US/Eastern')
except ImportError:
    _ET = None

from database import AlertsRepository, Alert as DBAlert


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
    """Manages alert storage and retrieval (Database-backed)"""

    def __init__(self):
        self._lock = threading.Lock()
        self._repo = AlertsRepository()
        logger.info("AlertManager using database storage")

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
            timestamp = datetime.now(_ET).isoformat() if _ET else datetime.now().isoformat()

            db_alert = DBAlert(
                level=level,
                message=f"{title}: {message}",
                timestamp=timestamp,
                active=True,
                metadata={
                    'title': title,
                    'category': category,
                    'symbol': symbol,
                    'acknowledged': False
                }
            )
            alert_id = self._repo.create(db_alert)

            # Return Alert object for backward compatibility
            alert = Alert(
                id=alert_id,
                level=level,
                title=title,
                message=message,
                category=category,
                symbol=symbol,
                timestamp=timestamp,
                acknowledged=False,
            )
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
        # Get recent alerts from database
        if level:
            db_alerts = self._repo.get_by_level(level.upper(), limit=limit * 2)
        elif unacknowledged_only:
            db_alerts = self._repo.get_active(limit=limit * 2)
        else:
            db_alerts = self._repo.get_recent(hours=24 * 7, limit=limit * 2)  # Last week

        # Convert to Alert format
        alerts = []
        for db_alert in db_alerts:
            metadata = db_alert.metadata or {}
            alert_dict = {
                'id': db_alert.id,
                'level': db_alert.level,
                'title': metadata.get('title', ''),
                'message': db_alert.message,
                'category': metadata.get('category', 'system'),
                'symbol': metadata.get('symbol', ''),
                'timestamp': db_alert.timestamp,
                'acknowledged': metadata.get('acknowledged', False) or not db_alert.active
            }

            # Apply filters
            if category and alert_dict['category'] != category:
                continue
            if unacknowledged_only and alert_dict['acknowledged']:
                continue

            alerts.append(alert_dict)

        return alerts[:limit]

    def acknowledge(self, alert_id: int) -> bool:
        """Mark an alert as acknowledged."""
        return self._repo.resolve(alert_id)

    def acknowledge_all(self) -> int:
        """Mark all alerts as acknowledged. Returns count."""
        return self._repo.resolve_all()

    def clear_old(self, days: int = 7) -> int:
        """Remove alerts older than N days. Returns count removed."""
        return self._repo.delete_old(days=days)

    def get_summary(self) -> Dict[str, Any]:
        """Get alert counts by level."""
        stats = self._repo.get_statistics(hours=24 * 7)  # Last week
        return {
            'total': stats['total'],
            'unacknowledged': stats['active'],
            'critical': stats['critical'],
            'warning': stats['warning'],
            'info': stats['info'],
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

    def alert_gap_risk(self, symbol: str, gap_pct: float, severity: str):
        level = 'CRITICAL' if severity == 'CATASTROPHIC' else 'WARNING'
        self.add(
            level,
            f'Gap Risk: {symbol}',
            f'{severity} overnight gap {gap_pct:+.1f}% on {symbol}',
            category='risk',
            symbol=symbol,
        )

    def alert_earnings_warning(self, symbol: str, reason: str):
        self.add(
            'WARNING',
            f'Earnings: {symbol}',
            f'{symbol} has upcoming earnings: {reason}',
            category='risk',
            symbol=symbol,
        )

    def alert_circuit_breaker(self, error_count: int):
        self.add(
            'CRITICAL',
            'Circuit Breaker Triggered',
            f'Engine stopped after {error_count} consecutive errors',
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
