"""Trading Signal Model"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List
import json


@dataclass
class TradingSignal:
    """
    Trading signal data model.

    Represents a trading signal from the scanner with full context.
    Maps to trading_signals table and rapid_signals.json structure.
    """

    # Primary key
    id: Optional[int] = None

    # Core Signal Data
    symbol: str = ""
    score: int = 0
    signal_price: float = 0.0  # entry_price in JSON
    signal_time: Optional[datetime] = None

    # Risk Management
    stop_loss: float = 0.0
    take_profit: float = 0.0
    sl_pct: Optional[float] = None
    tp_pct: Optional[float] = None
    risk_reward: Optional[float] = None
    expected_gain: Optional[float] = None
    max_loss: Optional[float] = None

    # Technical Indicators
    atr_pct: Optional[float] = None
    rsi: Optional[float] = None
    momentum_5d: Optional[float] = None
    momentum_20d: Optional[float] = None
    distance_from_high: Optional[float] = None
    swing_low: Optional[float] = None
    resistance: Optional[float] = None
    volume_ratio: Optional[float] = None
    vwap: Optional[float] = None

    # Market Context
    sector: Optional[str] = None
    market_regime: Optional[str] = None  # BULL, BEAR, NORMAL
    sector_score: Optional[int] = None
    alt_data_score: Optional[int] = None

    # Strategy Methods
    sl_method: Optional[str] = None  # EMA5, ATR, SwingLow, etc.
    tp_method: Optional[str] = None  # 52wHigh, Resistance, RR, etc.

    # v7.5: IC-weighted DIP quality score
    new_score: Optional[float] = None  # IC-weighted score [0-100]; DIP_SCORE_REJECT if < 70

    # Signal Status
    status: str = "active"  # active, waiting, executed, expired
    wait_reason: Optional[str] = None  # positions_full, etc.

    # Scan Context
    scan_session_id: Optional[int] = None
    session_type: Optional[str] = None  # morning, midday, afternoon, etc.
    scan_time_et: Optional[str] = None  # "11:33:02 ET"

    # Execution Tracking
    executed_at: Optional[datetime] = None
    execution_result: Optional[str] = None  # BOUGHT, SKIPPED_FILTER, QUEUED, etc.

    # Signal Reasons (JSON array in DB, List in Python)
    reasons: Optional[List[str]] = None

    # Metadata (JSON)
    metadata: Optional[str] = None

    # Audit
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)

        # Convert datetime to ISO string
        if self.signal_time:
            data['signal_time'] = self.signal_time.isoformat()
        if self.executed_at:
            data['executed_at'] = self.executed_at.isoformat()
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()

        # Convert reasons list to JSON string
        if self.reasons:
            data['reasons'] = json.dumps(self.reasons)

        return data

    @classmethod
    def from_row(cls, row: dict) -> 'TradingSignal':
        """Create from database row."""
        # Handle datetime parsing
        if row.get('signal_time') and isinstance(row['signal_time'], str):
            row['signal_time'] = datetime.fromisoformat(row['signal_time'])
        if row.get('executed_at') and isinstance(row['executed_at'], str):
            row['executed_at'] = datetime.fromisoformat(row['executed_at'])
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
    def from_json_signal(cls, signal_data: dict, status: str = "active",
                        scan_session_id: Optional[int] = None) -> 'TradingSignal':
        """
        Create from rapid_signals.json format.

        Args:
            signal_data: Signal dict from JSON (signals or waiting_signals array)
            status: Signal status (active, waiting)
            scan_session_id: Optional FK to scan_sessions
        """
        return cls(
            symbol=signal_data.get('symbol', ''),
            score=signal_data.get('score', 0),
            signal_price=signal_data.get('entry_price', 0.0),
            signal_time=datetime.now(),

            # Risk
            stop_loss=signal_data.get('stop_loss', 0.0),
            take_profit=signal_data.get('take_profit', 0.0),
            sl_pct=signal_data.get('sl_pct'),
            tp_pct=signal_data.get('tp_pct'),
            risk_reward=signal_data.get('risk_reward'),
            expected_gain=signal_data.get('expected_gain'),
            max_loss=signal_data.get('max_loss'),

            # Technicals
            atr_pct=signal_data.get('atr_pct'),
            rsi=signal_data.get('rsi'),
            momentum_5d=signal_data.get('momentum_5d'),
            momentum_20d=signal_data.get('momentum_20d'),
            distance_from_high=signal_data.get('distance_from_high'),
            swing_low=signal_data.get('swing_low'),
            resistance=signal_data.get('resistance'),
            volume_ratio=signal_data.get('volume_ratio'),
            vwap=signal_data.get('vwap'),

            # Market Context
            sector=signal_data.get('sector'),
            market_regime=signal_data.get('market_regime'),
            sector_score=signal_data.get('sector_score'),
            alt_data_score=signal_data.get('alt_data_score'),

            # Strategy
            sl_method=signal_data.get('sl_method'),
            tp_method=signal_data.get('tp_method'),
            new_score=signal_data.get('new_score'),

            # Status
            status=status,
            wait_reason=signal_data.get('reason'),  # positions_full, etc.

            # Scan Context
            scan_session_id=scan_session_id,

            # Reasons
            reasons=signal_data.get('reasons', [])
        )

    def validate(self) -> bool:
        """
        Validate signal data.

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

        # v6.78: PEM uses EOD exit (tp_method='pem_eod') so TP=0 is valid.
        # sl_method='pem' is a defensive fallback in case tp_method is lost in serialization.
        _eod_exit = self.tp_method in ('pem_eod', 'ped_autosell') or self.sl_method == 'pem'
        if self.take_profit <= 0 and not _eod_exit:
            raise ValueError(f"Invalid take profit: {self.take_profit}")

        if self.status not in ('active', 'waiting', 'executed', 'expired'):
            raise ValueError(f"Invalid status: {self.status}")

        return True
