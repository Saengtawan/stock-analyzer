"""Scan Session Model"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import json


@dataclass
class ScanSession:
    """
    Scan session data model.

    Represents metadata from a single scan execution.
    Maps to scan_sessions table and rapid_signals.json metadata.
    """

    # Primary key
    id: Optional[int] = None

    # Session Identity
    session_type: str = ""  # morning, midday, afternoon, pem, ovn, etc.
    scan_time: Optional[datetime] = None
    scan_time_et: Optional[str] = None  # "11:33:02 ET"

    # Market State
    mode: Optional[str] = None  # market, premarket, afterhours
    is_market_open: Optional[bool] = None
    market_regime: Optional[str] = None  # BULL_MODE, BEAR_MODE, NORMAL

    # Scan Results
    signal_count: int = 0
    waiting_count: int = 0
    pool_size: Optional[int] = None
    scan_duration_seconds: Optional[float] = None

    # Position Context
    positions_current: Optional[int] = None
    positions_max: Optional[int] = None
    positions_full: Optional[bool] = None

    # Next Scan
    next_scan_et: Optional[str] = None
    next_scan_timestamp: Optional[datetime] = None
    next_open: Optional[datetime] = None
    next_close: Optional[datetime] = None

    # Status
    status: str = "completed"  # running, completed, failed

    # Metadata
    metadata: Optional[str] = None

    # v7.5: Link to signal_outcomes.scan_id (string key)
    scan_id: Optional[str] = None

    # Audit
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)

        # Convert datetime to ISO string
        if self.scan_time:
            data['scan_time'] = self.scan_time.isoformat()
        if self.next_scan_timestamp:
            data['next_scan_timestamp'] = self.next_scan_timestamp.isoformat()
        if self.next_open:
            data['next_open'] = self.next_open.isoformat()
        if self.next_close:
            data['next_close'] = self.next_close.isoformat()
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()

        return data

    @classmethod
    def from_row(cls, row: dict) -> 'ScanSession':
        """Create from database row."""
        # Handle datetime parsing
        if row.get('scan_time') and isinstance(row['scan_time'], str):
            row['scan_time'] = datetime.fromisoformat(row['scan_time'])
        if row.get('next_scan_timestamp') and isinstance(row['next_scan_timestamp'], str):
            row['next_scan_timestamp'] = datetime.fromisoformat(row['next_scan_timestamp'])
        if row.get('next_open') and isinstance(row['next_open'], str):
            row['next_open'] = datetime.fromisoformat(row['next_open'])
        if row.get('next_close') and isinstance(row['next_close'], str):
            row['next_close'] = datetime.fromisoformat(row['next_close'])
        if row.get('created_at') and isinstance(row['created_at'], str):
            row['created_at'] = datetime.fromisoformat(row['created_at'])

        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json_signals(cls, signals_data: dict, session_type: str = "unknown",
                         scan_duration: Optional[float] = None) -> 'ScanSession':
        """
        Create from rapid_signals.json metadata.

        Args:
            signals_data: Full signals JSON data
            session_type: Scan session type
            scan_duration: Scan duration in seconds
        """
        # Parse timestamps
        timestamp_str = signals_data.get('timestamp')
        scan_time = None
        if timestamp_str:
            try:
                scan_time = datetime.fromisoformat(timestamp_str)
            except (ValueError, TypeError):
                scan_time = datetime.now()

        next_scan_str = signals_data.get('next_scan_timestamp')
        next_scan_timestamp = None
        if next_scan_str:
            try:
                next_scan_timestamp = datetime.fromisoformat(next_scan_str)
            except (ValueError, TypeError):
                pass

        next_open_str = signals_data.get('next_open')
        next_open = None
        if next_open_str:
            try:
                next_open = datetime.fromisoformat(next_open_str)
            except (ValueError, TypeError):
                pass

        next_close_str = signals_data.get('next_close')
        next_close = None
        if next_close_str:
            try:
                next_close = datetime.fromisoformat(next_close_str)
            except (ValueError, TypeError):
                pass

        # Extract position status
        pos_status = signals_data.get('positions_status', {})

        return cls(
            session_type=session_type or signals_data.get('session', 'unknown'),
            scan_time=scan_time or datetime.now(),
            scan_time_et=signals_data.get('scan_time'),

            # Market state
            mode=signals_data.get('mode'),
            is_market_open=signals_data.get('is_market_open'),
            market_regime=signals_data.get('regime'),

            # Results
            signal_count=signals_data.get('count', 0),
            waiting_count=len(signals_data.get('waiting_signals', [])),
            pool_size=signals_data.get('pool_size'),
            scan_duration_seconds=scan_duration or signals_data.get('scan_duration_seconds'),

            # Positions
            positions_current=pos_status.get('current'),
            positions_max=pos_status.get('max'),
            positions_full=pos_status.get('is_full'),

            # Next scan
            next_scan_et=signals_data.get('next_scan'),
            next_scan_timestamp=next_scan_timestamp,
            next_open=next_open,
            next_close=next_close
        )

    def validate(self) -> bool:
        """
        Validate scan session data.

        Returns:
            True if valid, raises ValueError otherwise
        """
        if not self.session_type:
            raise ValueError("Session type is required")

        if not self.scan_time:
            raise ValueError("Scan time is required")

        if self.signal_count < 0:
            raise ValueError(f"Invalid signal count: {self.signal_count}")

        if self.waiting_count < 0:
            raise ValueError(f"Invalid waiting count: {self.waiting_count}")

        if self.status not in ('running', 'completed', 'failed'):
            raise ValueError(f"Invalid status: {self.status}")

        return True
