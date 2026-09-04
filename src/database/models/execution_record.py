"""Execution Record Model"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import json


@dataclass
class ExecutionRecord:
    """
    Execution record data model.

    Represents a single execution attempt with outcome.
    Maps to execution_history table and execution_status.json structure.
    """

    # Primary key
    id: Optional[int] = None

    # Core Data
    symbol: str = ""
    action: str = ""  # BOUGHT, SKIPPED_FILTER, QUEUED, QUEUE_FULL
    timestamp: Optional[datetime] = None

    # Skip Reason (for SKIPPED_FILTER, QUEUE_FULL)
    skip_reason: Optional[str] = None

    # Signal Reference
    signal_id: Optional[int] = None  # FK to trading_signals
    signal_score: Optional[int] = None
    signal_price: Optional[float] = None

    # Execution Context
    scan_session_id: Optional[int] = None
    session_type: Optional[str] = None
    market_regime: Optional[str] = None

    # Position Context (for BOUGHT)
    entry_price: Optional[float] = None
    qty: Optional[int] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Metadata
    metadata: Optional[str] = None

    # Audit
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)

        # Convert datetime to ISO string
        if self.timestamp:
            data['timestamp'] = self.timestamp.isoformat()
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()

        return data

    @classmethod
    def from_row(cls, row: dict) -> 'ExecutionRecord':
        """Create from database row."""
        # Handle datetime parsing
        if row.get('timestamp') and isinstance(row['timestamp'], str):
            row['timestamp'] = datetime.fromisoformat(row['timestamp'])
        if row.get('created_at') and isinstance(row['created_at'], str):
            row['created_at'] = datetime.fromisoformat(row['created_at'])

        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json_status(cls, symbol: str, status_data: dict) -> 'ExecutionRecord':
        """
        Create from execution_status.json format.

        Args:
            symbol: Stock symbol
            status_data: Status dict from JSON {action, timestamp, skip_reason}
        """
        timestamp_str = status_data.get('timestamp')
        timestamp = None
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except (ValueError, TypeError):
                timestamp = datetime.now()

        return cls(
            symbol=symbol,
            action=status_data.get('action', 'UNKNOWN'),
            timestamp=timestamp or datetime.now(),
            skip_reason=status_data.get('skip_reason')
        )

    @classmethod
    def from_scan_result(cls, scan_result: dict, scan_session_id: Optional[int] = None) -> 'ExecutionRecord':
        """
        Create from auto_trading_engine scan_results.

        Args:
            scan_result: Result dict from scan_for_signals
            scan_session_id: Optional FK to scan_sessions
        """
        return cls(
            symbol=scan_result.get('symbol', ''),
            action=scan_result.get('action_taken', 'UNKNOWN'),
            timestamp=datetime.now(),
            skip_reason=scan_result.get('skip_reason'),
            signal_score=scan_result.get('score'),
            signal_price=scan_result.get('entry_price'),
            scan_session_id=scan_session_id,
            market_regime=scan_result.get('market_regime')
        )

    def validate(self) -> bool:
        """
        Validate execution record data.

        Returns:
            True if valid, raises ValueError otherwise
        """
        if not self.symbol:
            raise ValueError("Symbol is required")

        if self.action not in ('BOUGHT', 'SKIPPED_FILTER', 'QUEUED', 'QUEUE_FULL', 'UNKNOWN'):
            raise ValueError(f"Invalid action: {self.action}")

        if not self.timestamp:
            raise ValueError("Timestamp is required")

        return True
