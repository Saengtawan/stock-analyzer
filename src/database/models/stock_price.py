"""Stock Price Model"""

from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Optional


@dataclass
class StockPrice:
    """
    Stock price data model (OHLCV).
    
    Represents daily price data for a stock.
    """
    
    # Primary key
    id: Optional[int] = None
    
    # Core data
    symbol: str = ""
    date: Optional[date] = None
    
    # OHLCV
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    
    # Adjusted
    adj_close: Optional[float] = None
    
    # Technical indicators (pre-computed)
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    rsi: Optional[float] = None
    atr: Optional[float] = None
    
    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)
        if self.date:
            data['date'] = self.date.isoformat()
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data
    
    @classmethod
    def from_row(cls, row: dict) -> 'StockPrice':
        """Create from database row."""
        # Handle date/datetime parsing
        if row.get('date'):
            if isinstance(row['date'], str):
                row['date'] = date.fromisoformat(row['date'])
        
        if row.get('created_at') and isinstance(row['created_at'], str):
            row['created_at'] = datetime.fromisoformat(row['created_at'])
        
        if row.get('updated_at') and isinstance(row['updated_at'], str):
            row['updated_at'] = datetime.fromisoformat(row['updated_at'])
        
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})
    
    def validate(self) -> bool:
        """
        Validate price data.
        
        Returns:
            True if valid, raises ValueError otherwise
        """
        if not self.symbol:
            raise ValueError("Symbol is required")
        
        if not self.date:
            raise ValueError("Date is required")
        
        if self.open <= 0:
            raise ValueError(f"Invalid open: {self.open}")
        
        if self.high <= 0:
            raise ValueError(f"Invalid high: {self.high}")
        
        if self.low <= 0:
            raise ValueError(f"Invalid low: {self.low}")
        
        if self.close <= 0:
            raise ValueError(f"Invalid close: {self.close}")
        
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) < Low ({self.low})")
        
        if self.volume < 0:
            raise ValueError(f"Invalid volume: {self.volume}")
        
        return True
    
    def intraday_range_pct(self) -> float:
        """Calculate intraday range percentage."""
        return ((self.high - self.low) / self.low) * 100
    
    def gap_from_prev_close(self, prev_close: float) -> float:
        """Calculate gap percentage from previous close."""
        return ((self.open - prev_close) / prev_close) * 100
