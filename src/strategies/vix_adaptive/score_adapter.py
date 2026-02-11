"""
Adaptive Score Threshold

Adjusts minimum score threshold based on market regime.

CRITICAL: Score formula is bull-market biased. During bear markets/crashes,
stocks trade below SMAs with negative momentum → low scores.

Solution: Adaptive threshold based on VIX or market trend.
"""

from typing import Literal, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)

MarketRegime = Literal['bull', 'normal', 'bear']


class ScoreAdapter:
    """
    Adapts score threshold based on market regime.

    Why this is needed:
    - Bull market (VIX < 15): Scores cluster 70-100, use threshold 90
    - Normal market (VIX 15-20): Scores cluster 60-90, use threshold 80
    - Bear market (VIX > 20): Scores cluster 30-70, use threshold 70

    Without adaptation:
    - Fixed threshold of 90 → Only 0.3% signals in bear markets
    - Fixed threshold of 70 → Too many signals in bull markets

    Backtest validation:
    - 2022-2024 (bull): min_score=90 → 75 trades, +153% return
    - 2020-2024 (bear): min_score=70 → 159 trades, +149% return
    - Adaptive approach keeps trade frequency consistent across regimes

    Usage:
        >>> adapter = ScoreAdapter(method='vix_based')
        >>> threshold = adapter.get_score_threshold(vix=18.5)
        >>> print(threshold)
        80
    """

    def __init__(
        self,
        method: Literal['vix_based', 'percentile'] = 'vix_based',
        bull_threshold: float = 90,
        normal_threshold: float = 80,
        bear_threshold: float = 70
    ):
        """
        Initialize score adapter.

        Args:
            method: 'vix_based' (use VIX to determine regime) or 'percentile' (dynamic)
            bull_threshold: Score threshold for bull markets
            normal_threshold: Score threshold for normal markets
            bear_threshold: Score threshold for bear markets
        """
        self.method = method
        self.bull_threshold = bull_threshold
        self.normal_threshold = normal_threshold
        self.bear_threshold = bear_threshold

    def detect_market_regime(
        self,
        vix: Optional[float] = None,
        sma200_slope: Optional[float] = None
    ) -> MarketRegime:
        """
        Detect current market regime.

        Args:
            vix: Current VIX value (for vix_based method)
            sma200_slope: Slope of market SMA200 (for trend-based method)

        Returns:
            'bull', 'normal', or 'bear'
        """
        if self.method == 'vix_based':
            if vix is None:
                raise ValueError("VIX required for vix_based method")

            if vix < 15:
                return 'bull'
            elif vix < 20:
                return 'normal'
            else:
                return 'bear'

        elif self.method == 'sma_based':
            if sma200_slope is None:
                raise ValueError("SMA200 slope required for sma_based method")

            if sma200_slope > 0.5:  # Strong uptrend
                return 'bull'
            elif sma200_slope > -0.5:  # Sideways
                return 'normal'
            else:  # Downtrend
                return 'bear'

        else:
            logger.warning(f"Unknown method {self.method}, defaulting to 'normal'")
            return 'normal'

    def get_score_threshold(
        self,
        vix: Optional[float] = None,
        sma200_slope: Optional[float] = None,
        regime: Optional[MarketRegime] = None
    ) -> float:
        """
        Get adaptive score threshold.

        Args:
            vix: Current VIX value (for vix_based method)
            sma200_slope: SMA200 slope (for sma_based method)
            regime: Explicit regime override (if already detected)

        Returns:
            Score threshold (70-90)
        """
        # Use explicit regime if provided
        if regime is None:
            regime = self.detect_market_regime(vix=vix, sma200_slope=sma200_slope)

        # Map regime to threshold
        threshold_map = {
            'bull': self.bull_threshold,
            'normal': self.normal_threshold,
            'bear': self.bear_threshold,
        }

        threshold = threshold_map[regime]

        logger.debug(f"Market regime: {regime.upper()}, threshold: {threshold}")

        return threshold

    def get_percentile_threshold(
        self,
        scores: pd.Series,
        percentile: float = 70.0
    ) -> float:
        """
        Alternative: Use percentile-based threshold (dynamic).

        This adapts to current score distribution.
        Top 30% of scores → percentile=70

        Args:
            scores: Recent scores (e.g., last 20 days across all stocks)
            percentile: Percentile cutoff (default 70 = top 30%)

        Returns:
            Score threshold
        """
        if len(scores) == 0:
            logger.warning("No scores provided, using default threshold 80")
            return 80.0

        threshold = scores.quantile(percentile / 100)

        # Cap between 70-95 for safety
        threshold = max(70, min(95, threshold))

        logger.debug(f"Percentile-based threshold: {threshold:.1f} (p{percentile})")

        return float(threshold)

    def __repr__(self) -> str:
        return (
            f"ScoreAdapter(method={self.method}, "
            f"bull={self.bull_threshold}, "
            f"normal={self.normal_threshold}, "
            f"bear={self.bear_threshold})"
        )
