"""Pre-filter Session Model"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class PreFilterSession:
    """
    Pre-filter scan session model.

    Represents metadata from a single pre-filter scan execution.
    Maps to pre_filter_sessions table and pre_filter_status.json.
    """

    # Primary key
    id: Optional[int] = None

    # Session Identity
    scan_type: str = ""  # 'evening' or 'pre_open'
    scan_time: Optional[datetime] = None

    # Scan Results
    pool_size: int = 0
    total_scanned: int = 0

    # Status
    status: str = "running"  # 'running', 'completed', 'failed'
    is_ready: bool = False

    # Performance
    duration_seconds: Optional[float] = None

    # Metadata
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)

        # Convert datetime to ISO string
        if self.scan_time:
            data['scan_time'] = self.scan_time.isoformat()
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()

        return data

    @classmethod
    def from_row(cls, row: dict) -> 'PreFilterSession':
        """Create from database row."""
        # Handle datetime parsing
        if row.get('scan_time') and isinstance(row['scan_time'], str):
            row['scan_time'] = datetime.fromisoformat(row['scan_time'])
        if row.get('created_at') and isinstance(row['created_at'], str):
            row['created_at'] = datetime.fromisoformat(row['created_at'])

        # Handle boolean
        if 'is_ready' in row:
            row['is_ready'] = bool(row['is_ready'])

        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json_status(cls, status_data: dict, scan_type: str = "evening") -> 'PreFilterSession':
        """
        Create from pre_filter_status.json format.

        Args:
            status_data: Full status JSON data
            scan_type: 'evening' or 'pre_open'
        """
        # Parse last_updated timestamp
        last_updated_str = status_data.get('last_updated')
        scan_time = None
        if last_updated_str:
            try:
                scan_time = datetime.fromisoformat(last_updated_str)
            except (ValueError, TypeError):
                scan_time = datetime.now()

        # Determine status from status fields
        evening_status = status_data.get('evening_status', '')
        pre_open_status = status_data.get('pre_open_status', '')

        if scan_type == 'evening':
            status = evening_status or 'completed'
        else:
            status = pre_open_status or 'completed'

        is_ready = status_data.get('is_ready', False)

        return cls(
            scan_type=scan_type,
            scan_time=scan_time or datetime.now(),
            pool_size=status_data.get('pool_size', 0),
            total_scanned=status_data.get('total_scanned', 0),
            status=status if status in ('running', 'completed', 'failed') else 'completed',
            is_ready=is_ready,
            duration_seconds=status_data.get('duration_seconds')
        )

    def validate(self) -> bool:
        """
        Validate pre-filter session data.

        Returns:
            True if valid, raises ValueError otherwise
        """
        if not self.scan_type:
            raise ValueError("Scan type is required")

        if self.scan_type not in ('evening', 'pre_open'):
            raise ValueError(f"Invalid scan type: {self.scan_type}")

        if not self.scan_time:
            raise ValueError("Scan time is required")

        if self.pool_size < 0:
            raise ValueError(f"Invalid pool size: {self.pool_size}")

        if self.total_scanned < 0:
            raise ValueError(f"Invalid total scanned: {self.total_scanned}")

        if self.status not in ('running', 'completed', 'failed'):
            raise ValueError(f"Invalid status: {self.status}")

        return True
