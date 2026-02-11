"""
VIX Tier Manager

Determines the current market regime based on VIX level and direction.
"""

from typing import Literal, Dict

TierType = Literal['normal', 'skip', 'high', 'extreme']
VIXDirection = Literal['falling', 'rising', 'flat']


class VIXTierManager:
    """
    Manages VIX tier detection based on volatility levels.

    Boundaries (optimized from backtest):
    - VIX < 20: NORMAL tier (mean reversion)
    - VIX 20-24: SKIP tier (no new trades)
    - VIX 24-38: HIGH tier (bounce strategy)
    - VIX > 38: EXTREME tier (close all)

    Usage:
        >>> manager = VIXTierManager({'normal_max': 20, 'skip_max': 24, 'high_max': 38})
        >>> tier = manager.get_tier(vix=18.5)
        >>> print(tier)
        'normal'
    """

    def __init__(self, boundaries: Dict[str, float]):
        """
        Initialize VIX tier manager.

        Args:
            boundaries: Dict with keys 'normal_max', 'skip_max', 'high_max'
        """
        self.boundaries = boundaries
        self.normal_max = boundaries['normal_max']
        self.skip_max = boundaries['skip_max']
        self.high_max = boundaries['high_max']

        # Validate boundaries
        if not (self.normal_max < self.skip_max < self.high_max):
            raise ValueError(
                f"Boundaries must be in order: normal_max ({self.normal_max}) < "
                f"skip_max ({self.skip_max}) < high_max ({self.high_max})"
            )

    def get_tier(self, vix: float) -> TierType:
        """
        Get current VIX tier based on VIX level.

        Args:
            vix: Current VIX value

        Returns:
            Tier name: 'normal', 'skip', 'high', or 'extreme'
        """
        if vix >= self.high_max:
            return 'extreme'
        elif vix >= self.skip_max:
            return 'high'
        elif vix >= self.normal_max:
            return 'skip'
        else:
            return 'normal'

    def get_vix_direction(
        self,
        vix_today: float,
        vix_yesterday: float,
        threshold: float = 0.1
    ) -> VIXDirection:
        """
        Determine if VIX is falling, rising, or flat.

        Args:
            vix_today: Current VIX value
            vix_yesterday: Previous day VIX value
            threshold: Minimum change to consider not flat (default 0.1)

        Returns:
            'falling', 'rising', or 'flat'
        """
        change = vix_today - vix_yesterday

        if change < -threshold:
            return 'falling'
        elif change > threshold:
            return 'rising'
        else:
            return 'flat'

    def is_vix_falling(self, vix_today: float, vix_yesterday: float) -> bool:
        """
        Check if VIX is falling (for HIGH tier bounce strategy).

        Args:
            vix_today: Current VIX value
            vix_yesterday: Previous day VIX value

        Returns:
            True if VIX is falling, False otherwise
        """
        return vix_today < vix_yesterday

    def __repr__(self) -> str:
        return (
            f"VIXTierManager(normal<{self.normal_max}, "
            f"skip<{self.skip_max}, high<{self.high_max})"
        )
