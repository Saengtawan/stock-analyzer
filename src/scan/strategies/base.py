"""
Base strategy interface for scan system.

Each scan strategy inherits from BaseStrategy and implements:
- time_window: when this strategy runs
- entry_criteria: what passes as a BUY signal
- exit_rules: SL / TP / trail / EOD logic
- scan(): produces picks list

Design principles (from 2026-04-11 rebuild):
1. 1 file = 1 strategy = 1 thesis
2. Backtest-validated rules only
3. Explicit time windows (hard gates, not soft decay)
4. No catalyst bonuses (backtest: catalyst hurts momentum)
5. Trail 1% from peak > fixed TP/SL (validated EV +0.93%)
6. Wider SL -1.5% > tight -0.5% (validated, tight = noise stops)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pytz

ET = pytz.timezone('US/Eastern')


@dataclass
class Pick:
    """A single BUY signal from a strategy."""
    symbol: str
    entry: float
    sl_price: float
    tp_price: Optional[float] = None
    trail_pct: Optional[float] = None
    reason: str = ""
    score: Optional[int] = None
    atr_pct: Optional[float] = None
    extra: dict = field(default_factory=dict)


@dataclass
class ScanResult:
    """Output of a strategy scan."""
    strategy: str
    timestamp_et: str
    status: str   # 'active' | 'out_of_window' | 'skipped_gate' | 'no_picks'
    reason: str = ""
    picks: list = field(default_factory=list)  # list[Pick]
    regime: str = ""
    metadata: dict = field(default_factory=dict)


class BaseStrategy(ABC):
    """Base class for all scan strategies."""

    # Metadata (override in subclass)
    name: str = ""
    description: str = ""
    expected_wr: float = 0.0        # from backtest
    expected_ev: float = 0.0        # from backtest
    time_start: str = "00:00"       # ET, HH:MM
    time_end: str = "23:59"
    version: str = "1.0"

    def current_et(self) -> datetime:
        return datetime.now(ET)

    def time_et_str(self) -> str:
        return self.current_et().strftime("%H:%M")

    def in_time_window(self) -> bool:
        """Check if current ET time is within strategy's window."""
        now = self.time_et_str()
        return self.time_start <= now <= self.time_end

    @abstractmethod
    def scan(self) -> ScanResult:
        """Run the strategy and return picks.

        Must handle:
        - time window check (return out_of_window if outside)
        - hard gates (AD, VIX, SPY regime)
        - entry criteria per this strategy's thesis
        - return ScanResult with picks list (may be empty)
        """
        ...

    def out_of_window(self) -> ScanResult:
        return ScanResult(
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='out_of_window',
            reason=f"{self.name} runs {self.time_start}-{self.time_end} ET"
        )

    def gate_failed(self, reason: str) -> ScanResult:
        return ScanResult(
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='skipped_gate',
            reason=reason
        )

    def no_picks(self, reason: str = "No qualifying setups") -> ScanResult:
        return ScanResult(
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='no_picks',
            reason=reason
        )
