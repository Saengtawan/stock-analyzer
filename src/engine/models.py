"""
Engine Models - Extracted from auto_trading_engine.py (Phase 1)
================================================================

Classes:
- TradingState: Enum for engine states
- SignalSource: Signal source constants
- ManagedPosition: Position with trailing stop management
- DailyStats: Daily trading statistics
- QueuedSignal: Signal queue entry
"""

from datetime import datetime
from typing import List, Tuple
from dataclasses import dataclass
from enum import Enum


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


class SignalSource:
    """v5.1 P2-10: Signal source constants — prevents typo bugs in string comparisons."""
    DIP_BOUNCE = "dip_bounce"
    OVERNIGHT_GAP = "overnight_gap"
    BREAKOUT = "breakout"
    PEM = "pem"                      # v6.29: Post-Earnings Momentum
    PED = "ped"                      # v6.53: Pre-Earnings Drift
    PREMARKET_GAP = "premarket_gap"  # v6.84: Pre-Market Gap scan
    ALL = (DIP_BOUNCE, OVERNIGHT_GAP, BREAKOUT, PEM, PED, PREMARKET_GAP)


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
    # v4.9.4: Signal source tracking
    source: str = "dip_bounce"   # "dip_bounce", "overnight_gap", "breakout"
    # v4.9.8: Entry signal score for analytics (carry to SELL log)
    signal_score: float = 0.0
    # v4.9.9: Entry context for analytics
    entry_mode: str = "NORMAL"   # Mode at entry (NORMAL, LOW_RISK, BEAR+LOW_RISK)
    entry_regime: str = "BULL"   # Regime at entry (BULL, BEAR)
    entry_rsi: float = 0.0      # RSI at entry (v5.1 P3-23: renamed from rsi)
    momentum_5d: float = 0.0    # 5-day momentum at entry


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
    stock_d_rejected: int = 0       # v5.3: Signals rejected by Stock-D filter (no dip-bounce)


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
        Example: ATR 6% * 0.5 = 3% -> capped to 1.5%
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
