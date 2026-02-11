"""
Mean Reversion Strategy

For NORMAL tier (VIX < 20): Buy quality dips with high scores.

Entry Logic:
- Score >= threshold (adaptive: 70-90 based on regime)
- Yesterday dip <= -1.0%
- Max 3 positions
- Position sizing: [40%, 40%, 20%] by score rank

Exit Logic:
- Stop loss: 2-4% (ATR-based, capped)
- Trailing stop: Activate at +2%, lock 75% of gains
- Time exit: 10 days

Backtest Performance (2020-2024):
- Win rate: 52.4%
- Avg PnL: +3.85%
- Trades: 144
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
    reason: str = ""


class MeanReversionStrategy:
    """
    Mean reversion strategy for NORMAL VIX tier.

    Usage:
        >>> strategy = MeanReversionStrategy(config)
        >>> signals = strategy.scan_signals(date=today, stock_data=data, score_threshold=80)
        >>> for sig in signals:
        ...     print(f"{sig.symbol}: score={sig.score:.1f}, price=${sig.price:.2f}")
    """

    def __init__(self, config: Dict):
        """
        Initialize mean reversion strategy.

        Args:
            config: Configuration dict with keys:
                - min_dip_yesterday: Minimum dip % (e.g., -1.0)
                - max_positions: Max concurrent positions (e.g., 3)
                - position_sizes: Position sizes in % (e.g., [40, 40, 20])
                - stop_loss_range: (min%, max%) e.g., (2.0, 4.0)
                - trail_activation_pct: % gain to activate trailing (e.g., 2.0)
                - trail_lock_pct: % of gain to lock (e.g., 75)
                - max_hold_days: Max days to hold (e.g., 10)
        """
        self.config = config
        self.min_dip = config.get('min_dip_yesterday', -1.0)
        self.max_positions = config.get('max_positions', 3)
        self.position_sizes = config.get('position_sizes', [40, 40, 20])
        self.stop_loss_range = config.get('stop_loss_range', (2.0, 4.0))
        self.trail_activation = config.get('trail_activation_pct', 2.0)
        self.trail_lock = config.get('trail_lock_pct', 75)
        self.max_hold_days = config.get('max_hold_days', 10)

    def scan_signals(
        self,
        date,
        stock_data: Dict[str, pd.DataFrame],
        score_threshold: float
    ) -> List[Signal]:
        """
        Scan for mean reversion signals.

        Args:
            date: Current date (datetime.date or pd.Timestamp)
            stock_data: Dict of {symbol: DataFrame} with columns:
                - score, close, atr_pct, yesterday_dip
            score_threshold: Minimum score (adaptive based on regime)

        Returns:
            List of Signal objects, sorted by score (highest first)
        """
        # Convert date to lookup format
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
            if pd.isna(row['score']) or pd.isna(row['atr_pct']) or pd.isna(row['yesterday_dip']):
                continue

            # Filter 1: Score threshold
            if row['score'] < score_threshold:
                continue

            # Filter 2: Yesterday dip
            if row['yesterday_dip'] > self.min_dip:
                continue

            # Create signal
            signal = Signal(
                symbol=symbol,
                score=float(row['score']),
                price=float(row['close']),
                atr_pct=float(row['atr_pct']),
                reason=f"mean_reversion (score={row['score']:.1f}, dip={row['yesterday_dip']:.2f}%)"
            )

            signals.append(signal)

        # Sort by score (highest first)
        signals.sort(key=lambda x: x.score, reverse=True)

        if signals:
            logger.info(f"Found {len(signals)} mean reversion signals on {lookup_date}")

        return signals[:self.max_positions]  # Limit to max positions

    def calculate_stop_loss(self, entry_price: float, atr_pct: float) -> float:
        """
        Calculate ATR-based stop loss, capped to range.

        Args:
            entry_price: Entry price
            atr_pct: ATR as % of price

        Returns:
            Stop loss price
        """
        # ATR-based stop: 1.5x ATR
        atr_stop_pct = atr_pct * 1.5

        # Cap to range (2-4%)
        atr_stop_pct = max(self.stop_loss_range[0], min(atr_stop_pct, self.stop_loss_range[1]))

        stop_loss = entry_price * (1 - atr_stop_pct / 100)

        return stop_loss

    def calculate_trailing_stop(
        self,
        entry_price: float,
        peak_price: float,
        current_price: float
    ) -> Optional[float]:
        """
        Calculate trailing stop price.

        Activates when price >= entry + trail_activation_pct
        Locks trail_lock_pct % of gains

        Args:
            entry_price: Entry price
            peak_price: Peak price since entry
            current_price: Current price

        Returns:
            Trailing stop price or None if not activated
        """
        # Check if trailing should activate
        gain_pct = (current_price - entry_price) / entry_price * 100

        if gain_pct < self.trail_activation:
            return None

        # Calculate trail stop
        gain_amount = peak_price - entry_price
        locked_gain = gain_amount * (self.trail_lock / 100)
        trail_stop = entry_price + locked_gain

        return trail_stop

    def __repr__(self) -> str:
        return (
            f"MeanReversionStrategy("
            f"dip<={self.min_dip}%, "
            f"max_pos={self.max_positions}, "
            f"stop={self.stop_loss_range[0]}-{self.stop_loss_range[1]}%)"
        )
