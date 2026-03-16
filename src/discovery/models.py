from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiscoveryPick:
    """A stock pick from the Discovery Engine — display only, no execution."""
    symbol: str
    scan_date: str
    scan_price: float
    current_price: float = 0.0
    layer2_score: float = 0.0

    # Layer 1 features (hard filter values)
    beta: float = 0.0
    atr_pct: float = 0.0
    distance_from_high: float = 0.0

    # Technical
    rsi: float = 0.0
    momentum_5d: float = 0.0
    momentum_20d: float = 0.0
    volume_ratio: float = 0.0

    # SL / TP (adaptive regression v1.6)
    sl_price: float = 0.0
    sl_pct: float = 0.0
    tp1_price: float = 0.0
    tp1_pct: float = 0.0
    tp2_price: float = 0.0
    tp2_pct: float = 0.0
    expected_gain: float = 0.0
    rr_ratio: float = 0.0

    # Context
    sector: str = ''
    market_cap: float = 0.0

    # Macro snapshot at scan time
    vix_close: float = 0.0
    pct_above_20d_ma: float = 0.0

    # L2 features (persisted for calibration)
    vix_term_structure: float = 0.0
    new_52w_highs: float = 0.0
    bull_score: Optional[float] = None
    news_count: float = 0.0
    news_pos_ratio: Optional[float] = None
    highs_lows_ratio: float = 0.0
    ad_ratio: float = 0.0
    mcap_log: float = 0.0
    sector_1d_change: float = 0.0
    vix3m_close: float = 0.0
    upside_pct: Optional[float] = None

    # Additional features for calibration
    days_to_earnings: Optional[int] = None
    put_call_ratio: Optional[float] = None
    short_pct_float: Optional[float] = None

    # Macro stress features (v1.2)
    breadth_delta_5d: Optional[float] = None
    vix_delta_5d: Optional[float] = None
    crude_close: Optional[float] = None
    gold_close: Optional[float] = None
    dxy_delta_5d: Optional[float] = None
    stress_score: Optional[float] = None

    # Status
    status: str = 'active'  # active / expired / hit_tp1 / hit_sl

    @property
    def risk_reward_ratio(self) -> float:
        """TP1 reward / SL risk ratio."""
        if self.sl_pct > 0 and self.tp1_pct > 0:
            return round(self.tp1_pct / self.sl_pct, 1)
        return 0.0

    @property
    def earnings_warning(self) -> bool:
        """True if earnings within 5 trading days — risk event."""
        return self.days_to_earnings is not None and 0 <= self.days_to_earnings <= 5

    @property
    def score_tier(self) -> str:
        """Score quality tier for display."""
        if self.layer2_score >= 80:
            return 'A+'
        elif self.layer2_score >= 70:
            return 'A'
        elif self.layer2_score >= 60:
            return 'B'
        return 'C'

    def to_dict(self) -> dict:
        pct_change = round((self.current_price / self.scan_price - 1) * 100, 2) if self.scan_price > 0 and self.current_price > 0 else 0
        return {
            'symbol': self.symbol,
            'scan_date': self.scan_date,
            'scan_price': round(self.scan_price, 2),
            'current_price': round(self.current_price, 2),
            'layer2_score': round(self.layer2_score, 1),
            'score_tier': self.score_tier,
            'beta': round(self.beta, 2),
            'atr_pct': round(self.atr_pct, 1),
            'distance_from_high': round(self.distance_from_high, 1),
            'rsi': round(self.rsi, 0),
            'momentum_5d': round(self.momentum_5d, 1),
            'momentum_20d': round(self.momentum_20d, 1),
            'volume_ratio': round(self.volume_ratio, 2),
            'sl_price': round(self.sl_price, 2),
            'sl_pct': round(self.sl_pct, 1),
            'tp1_price': round(self.tp1_price, 2),
            'tp1_pct': round(self.tp1_pct, 1),
            'tp2_price': round(self.tp2_price, 2),
            'tp2_pct': round(self.tp2_pct, 1),
            'risk_reward': self.risk_reward_ratio,
            'expected_gain': self.expected_gain,
            'rr_ratio': self.rr_ratio,
            'sector': self.sector,
            'market_cap': self.market_cap,
            'vix_close': round(self.vix_close, 1),
            'pct_above_20d_ma': round(self.pct_above_20d_ma, 0),
            'status': self.status,
            'pct_change': pct_change,
            'days_to_earnings': self.days_to_earnings,
            'earnings_warning': self.earnings_warning,
            'short_pct_float': round(self.short_pct_float, 1) if self.short_pct_float else None,
            # Macro stress (v1.2)
            'stress_score': round(self.stress_score, 1) if self.stress_score is not None else None,
            'breadth_delta_5d': round(self.breadth_delta_5d, 1) if self.breadth_delta_5d is not None else None,
            'vix_delta_5d': round(self.vix_delta_5d, 1) if self.vix_delta_5d is not None else None,
            'crude_close': round(self.crude_close, 2) if self.crude_close is not None else None,
        }
