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
    distance_from_20d_high: float = 0.0

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

    # Pre-market validation + intraday scan (v4.5)
    premarket_price: Optional[float] = None
    gap_pct: Optional[float] = None
    scan_type: str = 'evening'  # 'evening' | 'intraday'

    # Limit-buy strategy (v4.6)
    limit_entry_price: Optional[float] = None   # target buy price (open - pullback)
    limit_pct: Optional[float] = None            # pullback % from open (0.3 × ATR)
    entry_price: Optional[float] = None          # actual entry price when limit filled
    entry_status: str = 'pending'                # pending / filled / missed
    entry_filled_at: Optional[str] = None        # timestamp when filled

    # Status
    status: str = 'active'  # active / expired / hit_tp1 / hit_sl

    @property
    def risk_reward_ratio(self) -> float:
        """TP1 reward / SL risk ratio."""
        if self.sl_pct > 0 and self.tp1_pct > 0:
            return round(self.tp1_pct / self.sl_pct, 1)
        return 0.0

    @property
    def validation_status(self) -> str:
        """Pre-market gap validation: pending/confirmed/unconfirmed."""
        if self.gap_pct is None:
            return 'pending'
        return 'confirmed' if self.gap_pct >= 0.0 else 'unconfirmed'

    @property
    def earnings_warning(self) -> bool:
        """True if earnings within 5 trading days — risk event."""
        return self.days_to_earnings is not None and 0 <= self.days_to_earnings <= 5

    @property
    def score_tier(self) -> str:
        """Score quality tier for display.
        v3: layer2_score stores E[R] (0-5% range).
        v2: layer2_score stores composite (0-100 range).
        Detect by value range: E[R] is always < 10, v2 score is always >= 10.
        """
        s = self.layer2_score
        if s < 10:
            # v3 E[R] mode
            if s >= 2.0:
                return 'A+'
            elif s >= 1.0:
                return 'A'
            elif s >= 0.5:
                return 'B'
            return 'C'
        else:
            # v2 score mode (backward compat for old DB rows)
            if s >= 80:
                return 'A+'
            elif s >= 70:
                return 'A'
            elif s >= 60:
                return 'B'
            return 'C'

    def to_dict(self) -> dict:
        def _r(v, n=2):
            return round(v, n) if v is not None else None

        pct_change = round((self.current_price / self.scan_price - 1) * 100, 2) if self.scan_price and self.current_price else 0
        return {
            'symbol': self.symbol,
            'scan_date': self.scan_date,
            'scan_price': _r(self.scan_price),
            'current_price': _r(self.current_price),
            'layer2_score': _r(self.layer2_score, 1),
            'score_tier': self.score_tier,
            'beta': _r(self.beta),
            'atr_pct': _r(self.atr_pct, 1),
            'distance_from_high': _r(self.distance_from_high, 1),
            'distance_from_20d_high': _r(self.distance_from_20d_high, 1),
            'rsi': _r(self.rsi, 0),
            'momentum_5d': _r(self.momentum_5d, 1),
            'momentum_20d': _r(self.momentum_20d, 1),
            'volume_ratio': _r(self.volume_ratio),
            'sl_price': _r(self.sl_price),
            'sl_pct': _r(self.sl_pct, 1),
            'tp1_price': _r(self.tp1_price),
            'tp1_pct': _r(self.tp1_pct, 1),
            'tp2_price': _r(self.tp2_price),
            'tp2_pct': _r(self.tp2_pct, 1),
            'risk_reward': self.risk_reward_ratio,
            'expected_gain': _r(self.expected_gain),
            'rr_ratio': _r(self.rr_ratio),
            'sector': self.sector,
            'market_cap': self.market_cap,
            'vix_close': _r(self.vix_close, 1),
            'pct_above_20d_ma': _r(self.pct_above_20d_ma, 0),
            'status': self.status,
            'pct_change': pct_change,
            'days_to_earnings': self.days_to_earnings,
            'earnings_warning': self.earnings_warning,
            'short_pct_float': _r(self.short_pct_float, 1),
            # Macro stress (v1.2)
            'stress_score': _r(self.stress_score, 1),
            'breadth_delta_5d': _r(self.breadth_delta_5d, 1),
            'vix_delta_5d': _r(self.vix_delta_5d, 1),
            'crude_close': _r(self.crude_close),
            # Pre-market validation (v4.5)
            'premarket_price': _r(self.premarket_price),
            'gap_pct': _r(self.gap_pct, 2),
            'scan_type': self.scan_type,
            'validation_status': self.validation_status,
            # Limit-buy (v4.6)
            'limit_entry_price': _r(self.limit_entry_price),
            'limit_pct': _r(self.limit_pct, 2),
            'entry_price': _r(self.entry_price),
            'entry_status': self.entry_status,
            'entry_filled_at': self.entry_filled_at,
            # v5.2: TP timeline + weekend play (persisted as JSON in DB)
            'tp_timeline': getattr(self, 'tp_timeline', None),
            'weekend_play': getattr(self, 'weekend_play', None),
            # v6.0: Ensemble scoring
            'ensemble': getattr(self, 'ensemble', None),
        }
