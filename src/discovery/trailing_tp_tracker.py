"""
Trailing Take-Profit Tracker for Discovery picks.

Monitors active picks and generates alerts when trailing TP triggers:
1. Track peak price since scan_date for each active pick
2. If peak >= scan_price * 1.02 (hit +2%), activate trailing stop
3. Trailing stop = peak * 0.995 (0.5% below peak)
4. If current price drops below trailing stop -> alert TAKE_PROFIT

Integrated into DiscoveryEngine.refresh_prices() cycle (every 5 min).
Peak prices persisted in discovery_picks.peak_price column.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from database.orm.base import get_session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Trailing TP configuration
TRAILING_ACTIVATION_PCT = 1.02   # Activate trailing after +2% from entry
TRAILING_STOP_PCT = 0.995        # Trail 0.5% below peak


@dataclass
class TrailingAlert:
    symbol: str
    action: str           # 'TAKE_PROFIT' or 'TRAILING_ACTIVE'
    scan_price: float
    peak_price: float
    current_price: float
    trailing_stop: float
    gain_pct: float
    peak_gain_pct: float
    reason: str
    scan_date: str = ''
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'action': self.action,
            'scan_price': round(self.scan_price, 2),
            'peak_price': round(self.peak_price, 2),
            'current_price': round(self.current_price, 2),
            'trailing_stop': round(self.trailing_stop, 2),
            'gain_pct': round(self.gain_pct, 2),
            'peak_gain_pct': round(self.peak_gain_pct, 2),
            'reason': self.reason,
            'scan_date': self.scan_date,
        }


class TrailingTPTracker:
    """Track Discovery picks and alert when trailing TP should trigger.

    For each active pick:
    - Track peak price since scan_date
    - If peak >= scan_price * TRAILING_ACTIVATION_PCT -> activate trailing
    - If current < peak * TRAILING_STOP_PCT -> ALERT: take profit

    Updates from price refresh cycle (every 5 min during market hours).
    """

    def __init__(self):
        self._alerts: list[TrailingAlert] = []
        self._active_trails: dict[str, dict] = {}  # symbol -> trailing state
        self._ensure_column()

    def _ensure_column(self):
        """Add peak_price column to discovery_picks if not exists."""
        try:
            with get_session() as session:
                session.execute(text(
                    "ALTER TABLE discovery_picks ADD COLUMN peak_price REAL"))
        except Exception:
            pass  # column already exists

    def update(self, picks, current_prices: dict) -> list[TrailingAlert]:
        """Update peak prices and check trailing stops for active picks.

        Args:
            picks: list of DiscoveryPick objects (active only)
            current_prices: dict of {symbol: current_price}

        Returns:
            list of TrailingAlert for picks that triggered
        """
        alerts = []
        updates = []  # (symbol, scan_date, peak_price) for DB batch update

        for pick in picks:
            if pick.status != 'active':
                continue
            # Use filled entry price if available, otherwise scan_price
            entry = pick.entry_price if (pick.entry_status == 'filled' and pick.entry_price) else pick.scan_price
            if not entry or entry <= 0:
                continue

            symbol = pick.symbol
            current = current_prices.get(symbol) or pick.current_price
            if not current or current <= 0:
                continue

            # Get or init peak price
            old_peak = getattr(pick, 'peak_price', None) or entry
            peak = max(old_peak, current)

            # Update peak on pick object
            pick.peak_price = peak

            # Track for DB update
            if peak > old_peak:
                updates.append((symbol, pick.scan_date, peak))

            # Check trailing TP activation
            activation_price = entry * TRAILING_ACTIVATION_PCT
            if peak >= activation_price:
                trailing_stop = peak * TRAILING_STOP_PCT
                gain_pct = (current / entry - 1) * 100
                peak_gain_pct = (peak / entry - 1) * 100

                # Track active trail state
                self._active_trails[symbol] = {
                    'entry': entry,
                    'peak': peak,
                    'trailing_stop': trailing_stop,
                    'activated': True,
                }

                if current <= trailing_stop:
                    alert = TrailingAlert(
                        symbol=symbol,
                        action='TAKE_PROFIT',
                        scan_price=entry,
                        peak_price=peak,
                        current_price=current,
                        trailing_stop=trailing_stop,
                        gain_pct=gain_pct,
                        peak_gain_pct=peak_gain_pct,
                        reason=(f"Trailing TP: peaked at ${peak:.2f} "
                                f"(+{peak_gain_pct:.1f}%), now ${current:.2f} "
                                f"(+{gain_pct:.1f}%) below trail ${trailing_stop:.2f}"),
                        scan_date=pick.scan_date,
                        created_at=time.time(),
                    )
                    alerts.append(alert)
                    logger.info("Discovery trailing TP: %s — %s", symbol, alert.reason)

        # Batch update peak prices in DB
        if updates:
            try:
                with get_session() as session:
                    for symbol, scan_date, peak in updates:
                        session.execute(text(
                            "UPDATE discovery_picks SET peak_price = :peak "
                            "WHERE symbol = :sym AND scan_date = :sd AND status = 'active'"),
                            {'peak': peak, 'sym': symbol, 'sd': scan_date})
            except Exception as e:
                logger.error("Discovery trailing TP: DB update error: %s", e)

        self._alerts = alerts
        return alerts

    def get_alerts(self) -> list[dict]:
        """Return current alerts as dicts for API."""
        return [a.to_dict() for a in self._alerts]

    def get_trailing_state(self) -> dict:
        """Return trailing state for all tracked symbols (for display)."""
        result = {}
        for symbol, state in self._active_trails.items():
            if state.get('activated'):
                result[symbol] = {
                    'entry': round(state['entry'], 2),
                    'peak': round(state['peak'], 2),
                    'trailing_stop': round(state['trailing_stop'], 2),
                    'gain_from_entry_pct': round(
                        (state['peak'] / state['entry'] - 1) * 100, 1)
                        if state['entry'] > 0 else 0,
                }
        return result
