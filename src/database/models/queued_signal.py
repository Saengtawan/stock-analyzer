"""Queued Signal Model"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List
import json


@dataclass
class QueuedSignal:
    """
    Queued signal data model.

    Represents a signal waiting for position slot.
    Maps to signal_queue table and signal_queue.json structure.
    """

    # Primary key
    id: Optional[int] = None

    # Core Signal Data
    symbol: str = ""  # Unique - only one entry per symbol
    signal_price: float = 0.0
    score: int = 0

    # Risk Management
    stop_loss: float = 0.0
    take_profit: float = 0.0
    sl_pct: Optional[float] = None
    tp_pct: Optional[float] = None

    # Queue Metadata
    queued_at: Optional[datetime] = None
    attempts: int = 0  # Execution attempts
    last_attempt_at: Optional[datetime] = None

    # Technical Context (minimal)
    atr_pct: Optional[float] = None
    reasons: Optional[List[str]] = None

    # Signal Reference
    signal_id: Optional[int] = None  # FK to trading_signals

    # Status
    status: str = "waiting"  # waiting, executing, removed

    # Audit
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)

        # Convert datetime to ISO string
        if self.queued_at:
            data['queued_at'] = self.queued_at.isoformat()
        if self.last_attempt_at:
            data['last_attempt_at'] = self.last_attempt_at.isoformat()
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()

        # Convert reasons list to JSON string
        if self.reasons:
            data['reasons'] = json.dumps(self.reasons)

        return data

    @classmethod
    def from_row(cls, row: dict) -> 'QueuedSignal':
        """Create from database row."""
        # Handle datetime parsing
        if row.get('queued_at') and isinstance(row['queued_at'], str):
            row['queued_at'] = datetime.fromisoformat(row['queued_at'])
        if row.get('last_attempt_at') and isinstance(row['last_attempt_at'], str):
            row['last_attempt_at'] = datetime.fromisoformat(row['last_attempt_at'])
        if row.get('created_at') and isinstance(row['created_at'], str):
            row['created_at'] = datetime.fromisoformat(row['created_at'])
        if row.get('updated_at') and isinstance(row['updated_at'], str):
            row['updated_at'] = datetime.fromisoformat(row['updated_at'])

        # Parse reasons JSON string to list
        if row.get('reasons') and isinstance(row['reasons'], str):
            try:
                row['reasons'] = json.loads(row['reasons'])
            except json.JSONDecodeError:
                row['reasons'] = []

        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json_queue(cls, queue_data: dict) -> 'QueuedSignal':
        """
        Create from signal_queue.json format.

        Args:
            queue_data: Queue item dict from JSON
        """
        queued_at_str = queue_data.get('queued_at')
        queued_at = None
        if queued_at_str:
            try:
                queued_at = datetime.fromisoformat(queued_at_str)
            except (ValueError, TypeError):
                queued_at = datetime.now()

        return cls(
            symbol=queue_data.get('symbol', ''),
            signal_price=queue_data.get('signal_price', 0.0),
            score=queue_data.get('score', 0),
            stop_loss=queue_data.get('stop_loss', 0.0),
            take_profit=queue_data.get('take_profit', 0.0),
            sl_pct=queue_data.get('sl_pct'),
            tp_pct=queue_data.get('tp_pct'),
            queued_at=queued_at or datetime.now(),
            atr_pct=queue_data.get('atr_pct'),
            reasons=queue_data.get('reasons', [])
        )

    @classmethod
    def from_signal(cls, signal: 'TradingSignal') -> 'QueuedSignal':
        """
        Create from TradingSignal.

        Args:
            signal: TradingSignal instance
        """
        return cls(
            symbol=signal.symbol,
            signal_price=signal.signal_price,
            score=signal.score,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            sl_pct=signal.sl_pct,
            tp_pct=signal.tp_pct,
            queued_at=datetime.now(),
            atr_pct=signal.atr_pct,
            reasons=signal.reasons,
            signal_id=signal.id
        )

    def validate(self) -> bool:
        """
        Validate queued signal data.

        Returns:
            True if valid, raises ValueError otherwise
        """
        if not self.symbol:
            raise ValueError("Symbol is required")

        if self.score < 0:
            raise ValueError(f"Invalid score: {self.score}")

        if self.signal_price <= 0:
            raise ValueError(f"Invalid signal price: {self.signal_price}")

        if self.stop_loss <= 0:
            raise ValueError(f"Invalid stop loss: {self.stop_loss}")

        # v6.78: PEM uses TP=0 (EOD exit) — allow if sl_method indicates EOD strategy
        _eod_exit = getattr(self, 'sl_method', '') == 'pem' or getattr(self, 'tp_method', '') in ('pem_eod', 'ped_autosell')
        if self.take_profit <= 0 and not _eod_exit:
            raise ValueError(f"Invalid take profit: {self.take_profit}")

        if self.status not in ('waiting', 'executing', 'removed'):
            raise ValueError(f"Invalid status: {self.status}")

        return True
