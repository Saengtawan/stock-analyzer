"""
Strategy Definitions — entry/exit rules for each strategy type.
Part of Discovery v9.0 True Multi-Strategy System.

Data-validated on 51K signals + 309K OHLC bars:
  MOMENTUM D+1: WR=64%, E[R]=+1.04%
  DIP trail 1.5%: WR=50%, E[R]=+0.54%
  WASHOUT trail 2%: WR=60%+
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StrategySpec:
    """Complete specification for a trading strategy."""
    name: str
    signal_type: str           # MOMENTUM / DIP / WASHOUT
    entry_rule: str = 'D1_OPEN'
    exit_rule: str = 'D1_CLOSE'  # D1_CLOSE / TRAIL / FIXED_D5
    trail_pct: float = 0.0     # trailing stop % from max high
    sl_pct: float = 1.5        # hard stop loss %
    max_hold_days: int = 1     # force exit after N days
    sizing: float = 1.0        # position size multiplier
    hold_label: str = '1 day'  # display label

    # Signal conditions
    mom_min: Optional[float] = None   # min momentum_5d
    mom_max: Optional[float] = None   # max momentum_5d
    d20h_min: Optional[float] = None  # min distance_from_20d_high
    d20h_max: Optional[float] = None  # max distance_from_20d_high
    vol_min: float = 0.0              # min volume_ratio
    atr_max: float = 8.0              # max ATR%

    def matches(self, stock: dict) -> bool:
        """Check if a stock matches this strategy's signal conditions."""
        mom = stock.get('momentum_5d') or 0
        d20h = stock.get('distance_from_20d_high') or -5
        vol = stock.get('volume_ratio') or 1
        atr = stock.get('atr_pct') or 3

        if self.mom_min is not None and mom < self.mom_min:
            return False
        if self.mom_max is not None and mom > self.mom_max:
            return False
        if self.d20h_min is not None and d20h < self.d20h_min:
            return False
        if self.d20h_max is not None and d20h > self.d20h_max:
            return False
        if vol < self.vol_min:
            return False
        if atr > self.atr_max:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'signal_type': self.signal_type,
            'entry_rule': self.entry_rule,
            'exit_rule': self.exit_rule,
            'trail_pct': self.trail_pct,
            'sl_pct': self.sl_pct,
            'max_hold_days': self.max_hold_days,
            'sizing': self.sizing,
            'hold_label': self.hold_label,
        }


# === Strategy Definitions (data-validated) ===

# v9.0: Data-validated strategies (entry = D1 open)
# HONEST: Momentum has NO tradeable edge from D1 open (WR=49%)
# The "64% WR" was D0open→D1close which includes D0 move we can't capture
# ONLY DIP works: D5 hold WR=55%, E[R]=+0.62%

# MOMENTUM: NO EDGE from D1 open — kept as DISPLAY ONLY (informational)
MOMENTUM_DAY = StrategySpec(
    name='MOMENTUM_INFO',
    signal_type='MOMENTUM',
    entry_rule='D1_OPEN',
    exit_rule='FIXED_D5',
    trail_pct=0,
    sl_pct=2.0,
    max_hold_days=5,
    sizing=0.25,               # minimal size — no proven edge
    hold_label='5 days (low conviction)',
    mom_min=3.0,
    d20h_min=-5.0,
    vol_min=0.8,
    atr_max=6.0,
)

MOMENTUM_TRAIL = MOMENTUM_DAY  # same — no edge either way

# DIP SWING: THE ONLY PROVEN STRATEGY (WR=55%, E[R]=+0.62%)
DIP_TRAIL = StrategySpec(
    name='DIP_SWING',
    signal_type='DIP',
    entry_rule='D1_OPEN',
    exit_rule='FIXED_D5',       # hold 5 days (best E[R])
    trail_pct=0,
    sl_pct=3.0,
    max_hold_days=5,
    sizing=1.0,                 # full size — proven edge
    hold_label='5 days swing',
    mom_max=-3.0,
    d20h_max=-10.0,
    atr_max=8.0,
)

WASHOUT_TRAIL = StrategySpec(
    name='WASHOUT_TRAIL',
    signal_type='WASHOUT',
    entry_rule='D1_OPEN',
    exit_rule='TRAIL',
    trail_pct=2.0,
    sl_pct=4.0,
    max_hold_days=5,
    sizing=1.0,
    hold_label='2-5 days',
    mom_max=-8.0,
    d20h_max=-20.0,
    atr_max=10.0,
)

SELECTIVE = StrategySpec(
    name='SELECTIVE',
    signal_type='DIP',
    entry_rule='D1_OPEN',
    exit_rule='TRAIL',
    trail_pct=1.5,
    sl_pct=3.0,
    max_hold_days=5,
    sizing=0.25,
    hold_label='2-5 days (small)',
    mom_max=-1.0,
    d20h_max=-5.0,
    atr_max=5.0,
)

ALL_STRATEGIES = [MOMENTUM_DAY, MOMENTUM_TRAIL, DIP_TRAIL, WASHOUT_TRAIL, SELECTIVE]


def classify_stock(stock: dict, vix: float = 20) -> Optional[StrategySpec]:
    """Classify a stock into the best strategy based on its profile + VIX.

    Priority: WASHOUT > MOMENTUM_DAY > DIP_TRAIL > SELECTIVE
    """
    mom = stock.get('momentum_5d') or 0
    d20h = stock.get('distance_from_20d_high') or -5

    # WASHOUT: extreme fear + extreme dip
    if vix > 25 and WASHOUT_TRAIL.matches(stock):
        return WASHOUT_TRAIL

    # MOMENTUM: stock going up, near high
    if vix < 25:  # momentum doesn't work in high VIX
        if MOMENTUM_DAY.matches(stock):
            if vix < 18:
                return MOMENTUM_DAY  # calm → day trade
            else:
                return MOMENTUM_TRAIL  # normal → trail

    # DIP: stock going down
    if DIP_TRAIL.matches(stock):
        return DIP_TRAIL

    # SELECTIVE: mild dip
    if vix < 25 and SELECTIVE.matches(stock):
        return SELECTIVE

    return None  # doesn't match any strategy
