"""Trade Model"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import json


@dataclass
class Trade:
    """
    Trade data model with validation.
    
    Represents a single trade (entry or exit) with full context.
    """
    
    # Primary key
    id: Optional[int] = None
    
    # Core trade data
    symbol: str = ""
    action: str = ""  # BUY, SELL
    qty: int = 0
    price: float = 0.0
    timestamp: Optional[datetime] = None
    
    # Entry data
    entry_date: Optional[datetime] = None
    entry_price: Optional[float] = None
    
    # Exit data
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    
    # P&L
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    
    # Strategy
    strategy: str = ""
    signal_score: Optional[float] = None
    
    # Risk management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # Market context
    spy_price: Optional[float] = None
    vix: Optional[float] = None
    regime: Optional[str] = None
    sector: Optional[str] = None
    
    # Technical indicators
    rsi: Optional[float] = None
    atr_pct: Optional[float] = None
    gap_pct: Optional[float] = None
    momentum_5d: Optional[float] = None
    
    # Exit reason
    exit_reason: Optional[str] = None  # SL, TP, TRAILING, MAX_HOLD, etc.
    
    # PDT tracking
    pdt_used: bool = False
    day_held: int = 0
    
    # Additional context (JSON)
    metadata: Optional[str] = None  # JSON string for flexible data
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert datetime to ISO string
        if self.timestamp:
            data['timestamp'] = self.timestamp.isoformat()
        if self.entry_date:
            data['entry_date'] = self.entry_date.isoformat()
        if self.exit_date:
            data['exit_date'] = self.exit_date.isoformat()
        return data
    
    @classmethod
    def from_row(cls, row: dict) -> 'Trade':
        """Create from database row."""
        # Handle datetime parsing
        if row.get('timestamp') and isinstance(row['timestamp'], str):
            row['timestamp'] = datetime.fromisoformat(row['timestamp'])
        if row.get('entry_date') and isinstance(row['entry_date'], str):
            row['entry_date'] = datetime.fromisoformat(row['entry_date'])
        if row.get('exit_date') and isinstance(row['exit_date'], str):
            row['exit_date'] = datetime.fromisoformat(row['exit_date'])
        
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})
    
    def validate(self) -> bool:
        """
        Validate trade data.
        
        Returns:
            True if valid, raises ValueError otherwise
        """
        if not self.symbol:
            raise ValueError("Symbol is required")
        
        if self.action not in ('BUY', 'SELL'):
            raise ValueError(f"Invalid action: {self.action}")
        
        if self.qty <= 0:
            raise ValueError(f"Invalid quantity: {self.qty}")
        
        if self.price <= 0:
            raise ValueError(f"Invalid price: {self.price}")
        
        return True
