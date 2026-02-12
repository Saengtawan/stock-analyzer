"""Position Model"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Position:
    """
    Active position data model.
    
    Represents a currently held position with entry context.
    """
    
    # Core position data
    symbol: str = ""
    qty: int = 0
    entry_price: float = 0.0
    entry_date: Optional[datetime] = None
    
    # Strategy
    strategy: str = ""
    signal_score: Optional[float] = None
    
    # Risk management
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop: bool = False
    peak_price: Optional[float] = None
    trough_price: Optional[float] = None
    sl_pct: Optional[float] = None
    tp_pct: Optional[float] = None
    
    # Market context at entry
    spy_price: Optional[float] = None
    vix: Optional[float] = None
    regime: Optional[str] = None
    sector: Optional[str] = None
    source: Optional[str] = None
    mode: Optional[str] = None
    momentum_5d: Optional[float] = None
    
    # Technical indicators at entry
    entry_rsi: Optional[float] = None
    entry_atr_pct: Optional[float] = None
    gap_pct: Optional[float] = None
    
    # PDT tracking
    day_held: int = 0

    # Order IDs
    sl_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
    entry_order_id: Optional[str] = None

    # Additional context (JSON)
    metadata: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)
        if self.entry_date:
            data['entry_date'] = self.entry_date.isoformat()
        return data
    
    @classmethod
    def from_row(cls, row: dict) -> 'Position':
        """Create from database row."""
        # Handle datetime parsing
        if row.get('entry_date') and isinstance(row['entry_date'], str):
            row['entry_date'] = datetime.fromisoformat(row['entry_date'])
        
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})
    
    @classmethod
    def from_json_dict(cls, data: dict) -> 'Position':
        """Create from JSON dictionary (rapid_portfolio.json format)."""
        return cls(
            symbol=data.get('symbol', ''),
            qty=data.get('qty', 0),
            entry_price=data.get('entry_price', 0.0),
            entry_date=datetime.fromisoformat(data['entry_date']) if data.get('entry_date') else None,
            strategy=data.get('strategy', ''),
            signal_score=data.get('signal_score'),
            stop_loss=data.get('stop_loss', 0.0),
            take_profit=data.get('take_profit', 0.0),
            trailing_stop=data.get('trailing_stop', False),
            peak_price=data.get('peak_price'),
            spy_price=data.get('spy_price'),
            vix=data.get('vix'),
            regime=data.get('regime'),
            sector=data.get('sector'),
            entry_rsi=data.get('entry_rsi'),
            entry_atr_pct=data.get('entry_atr_pct'),
            gap_pct=data.get('gap_pct'),
            day_held=data.get('day_held', 0)
        )
    
    def validate(self) -> bool:
        """
        Validate position data.
        
        Returns:
            True if valid, raises ValueError otherwise
        """
        if not self.symbol:
            raise ValueError("Symbol is required")
        
        if self.qty <= 0:
            raise ValueError(f"Invalid quantity: {self.qty}")
        
        if self.entry_price <= 0:
            raise ValueError(f"Invalid entry price: {self.entry_price}")
        
        if self.stop_loss <= 0:
            raise ValueError(f"Invalid stop loss: {self.stop_loss}")
        
        if self.take_profit <= 0:
            raise ValueError(f"Invalid take profit: {self.take_profit}")
        
        return True
    
    def unrealized_pnl(self, current_price: float) -> tuple[float, float]:
        """
        Calculate unrealized P&L.
        
        Args:
            current_price: Current market price
            
        Returns:
            (pnl_usd, pnl_pct)
        """
        pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
        pnl_usd = (current_price - self.entry_price) * self.qty
        return pnl_usd, pnl_pct
