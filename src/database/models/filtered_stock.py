"""Filtered Stock Model"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class FilteredStock:
    """
    Filtered stock model.

    Represents a stock that passed pre-filter criteria.
    Maps to filtered_stocks table and entries in pre_filtered.json.
    """

    # Primary key
    id: Optional[int] = None

    # Foreign key
    session_id: Optional[int] = None

    # Stock Identity
    symbol: str = ""
    sector: Optional[str] = None

    # Pre-filter Score
    score: Optional[float] = None

    # Technical Indicators (snapshot)
    close_price: Optional[float] = None
    volume_avg_20d: Optional[float] = None
    atr_pct: Optional[float] = None
    rsi: Optional[float] = None

    # Metadata
    filter_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)

        # Convert datetime to ISO string
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()

        return data

    @classmethod
    def from_row(cls, row: dict) -> 'FilteredStock':
        """Create from database row."""
        # Handle datetime parsing
        if row.get('created_at') and isinstance(row['created_at'], str):
            row['created_at'] = datetime.fromisoformat(row['created_at'])

        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json_entry(cls, entry: dict, session_id: Optional[int] = None) -> 'FilteredStock':
        """
        Create from pre_filtered.json entry.

        Args:
            entry: Stock entry from JSON (symbol: data dict)
            session_id: Pre-filter session ID
        """
        # Handle both formats:
        # 1. {symbol: {data}} - from pre_filtered.json
        # 2. {symbol: "...", data: {...}} - direct dict

        if isinstance(entry, dict):
            symbol = entry.get('symbol', '')
            data = entry.get('data', entry)  # Fallback to entry itself

            return cls(
                session_id=session_id,
                symbol=symbol or data.get('symbol', ''),
                sector=data.get('sector'),
                score=data.get('score'),
                close_price=data.get('close') or data.get('close_price'),
                volume_avg_20d=data.get('volume_avg_20d'),
                atr_pct=data.get('atr_pct'),
                rsi=data.get('rsi'),
                filter_reason=data.get('reason') or data.get('filter_reason')
            )

        # Fallback: simple string (just symbol)
        return cls(session_id=session_id, symbol=str(entry))

    def validate(self) -> bool:
        """
        Validate filtered stock data.

        Returns:
            True if valid, raises ValueError otherwise
        """
        if not self.symbol:
            raise ValueError("Symbol is required")

        if self.session_id is None:
            raise ValueError("Session ID is required")

        return True
