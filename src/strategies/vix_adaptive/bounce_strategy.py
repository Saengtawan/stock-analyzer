"""
Bounce Strategy

For HIGH tier (VIX 24-38): Buy confirmed bounces, not falling knives.

Entry Logic:
- Score >= 85
- Bounce confirmed: +1.0% gain over 2 days (return_2d >= 1.0%)
- Recent dip: Dip from 3-day high <= -3.0%
- VIX falling (today < yesterday) ← CRITICAL FILTER
- Max 1 position

Exit Logic:
- Stop loss: 3-6% (wider for volatility)
- NO trailing stop (avoids whipsaw)
- Time exit: 10 days

Why This Works:
- Mean reversion fails at high VIX (44.7% win rate)
- Bounce strategy waits for recovery confirmation
- VIX falling filter: 66.7-100% win rate ✅
- VIX any direction: 16.7% win rate ❌

Backtest Performance (2020-2024):
- Win rate: 60.0% (9/15 trades)
- Avg PnL: +4.32%
- Critical during COVID crash and 2022 bear market
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Trading signal."""
    symbol: str
    score: float
    price: float
    atr_pct: float
    bounce_gain: float
    dip_from_high: float
    reason: str = ""


class BounceStrategy:
    """
    Bounce strategy for HIGH VIX tier.

    CRITICAL: Only buy on VIX falling days. VIX direction is THE key filter.

    Usage:
        >>> strategy = BounceStrategy(config)
        >>> signals = strategy.scan_bounce_signals(
        ...     date=today,
        ...     stock_data=data,
        ...     vix_falling=True
        ... )
    """

    def __init__(self, config: Dict):
        """
        Initialize bounce strategy.

        Args:
            config: Configuration dict with keys:
                - min_score: Minimum score (default 85)
                - bounce_type: 'gain_2d_1.0' (must gain 1% over 2 days)
                - dip_requirement: 'dip_3d_-3' (must have dipped -3% from 3d high)
                - vix_condition: 'falling_1d' (VIX must be falling)
                - max_positions: Max positions (should be 1)
                - stop_loss_range: (min%, max%) e.g., (3.0, 6.0)
                - use_trailing: False (disabled for HIGH tier)
                - max_hold_days: Max days to hold (e.g., 10)
        """
        self.config = config
        self.min_score = config.get('min_score', 85)
        self.bounce_type = config.get('bounce_type', 'gain_2d_1.0')
        self.dip_requirement = config.get('dip_requirement', 'dip_3d_-3')
        self.vix_condition = config.get('vix_condition', 'falling_1d')
        self.max_positions = config.get('max_positions', 1)
        self.stop_loss_range = config.get('stop_loss_range', (3.0, 6.0))
        self.use_trailing = config.get('use_trailing', False)
        self.max_hold_days = config.get('max_hold_days', 10)

    def check_bounce_signal(self, row: pd.Series) -> bool:
        """
        Check if bounce conditions are met.

        Args:
            row: Stock data row with indicators

        Returns:
            True if bounce confirmed, False otherwise
        """
        # Check dip requirement
        if self.dip_requirement == 'dip_3d_-3':
            if pd.isna(row['dip_from_3d_high']) or row['dip_from_3d_high'] > -3.0:
                return False

        # Check bounce confirmation
        if self.bounce_type == 'gain_2d_1.0':
            if pd.isna(row['return_2d']) or row['return_2d'] < 1.0:
                return False

        return True

    def scan_bounce_signals(
        self,
        date,
        stock_data: Dict[str, pd.DataFrame],
        vix_falling: bool
    ) -> List[Signal]:
        """
        Scan for bounce signals.

        Args:
            date: Current date (datetime.date or pd.Timestamp)
            stock_data: Dict of {symbol: DataFrame} with columns:
                - score, close, atr_pct, return_2d, dip_from_3d_high
            vix_falling: True if VIX is falling today

        Returns:
            List of Signal objects, sorted by score
        """
        # CRITICAL: VIX falling filter
        if self.vix_condition == 'falling_1d' and not vix_falling:
            logger.debug("VIX not falling, skipping bounce signals")
            return []

        # Convert date
        if isinstance(date, pd.Timestamp):
            lookup_date = date.date()
        else:
            lookup_date = date

        signals = []

        for symbol, df in stock_data.items():
            # Check if date exists
            if lookup_date not in df.index:
                continue

            row = df.loc[lookup_date]

            # Check required fields
            if pd.isna(row['score']) or pd.isna(row['atr_pct']):
                continue

            # Filter 1: Score threshold
            if row['score'] < self.min_score:
                continue

            # Filter 2: Bounce confirmation
            if not self.check_bounce_signal(row):
                continue

            # Create signal
            bounce_gain = float(row.get('return_2d', 0))
            dip = float(row.get('dip_from_3d_high', 0))

            signal = Signal(
                symbol=symbol,
                score=float(row['score']),
                price=float(row['close']),
                atr_pct=float(row['atr_pct']),
                bounce_gain=bounce_gain,
                dip_from_high=dip,
                reason=f"bounce (score={row['score']:.1f}, gain_2d={bounce_gain:+.2f}%, dip_3d={dip:.2f}%)"
            )

            signals.append(signal)

        # Sort by score
        signals.sort(key=lambda x: x.score, reverse=True)

        if signals:
            logger.info(f"Found {len(signals)} bounce signals on {lookup_date} (VIX falling)")

        return signals[:self.max_positions]  # Limit to 1

    def calculate_stop_loss(self, entry_price: float, atr_pct: float) -> float:
        """
        Calculate ATR-based stop loss, capped to range.

        Wider range for high volatility (3-6% vs 2-4%).

        Args:
            entry_price: Entry price
            atr_pct: ATR as % of price

        Returns:
            Stop loss price
        """
        # ATR-based stop: 1.5x ATR
        atr_stop_pct = atr_pct * 1.5

        # Cap to range (3-6%)
        atr_stop_pct = max(self.stop_loss_range[0], min(atr_stop_pct, self.stop_loss_range[1]))

        stop_loss = entry_price * (1 - atr_stop_pct / 100)

        return stop_loss

    def __repr__(self) -> str:
        return (
            f"BounceStrategy("
            f"score>={self.min_score}, "
            f"{self.bounce_type}, "
            f"{self.dip_requirement}, "
            f"VIX_falling, "
            f"stop={self.stop_loss_range[0]}-{self.stop_loss_range[1]}%)"
        )
