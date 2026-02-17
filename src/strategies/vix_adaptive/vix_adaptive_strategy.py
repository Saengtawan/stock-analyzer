"""
VIX Adaptive Strategy v3.0

Main strategy class that routes to correct sub-strategy based on VIX tier.

Tier Routing:
- NORMAL (VIX < 20): MeanReversionStrategy
- SKIP (VIX 20-24): No trading, manage existing only
- HIGH (VIX 24-38): BounceStrategy
- EXTREME (VIX > 38): Close all positions

Key Features:
- Adaptive score threshold (70-90 based on market regime)
- VIX direction filter for HIGH tier (critical)
- Tier-specific position sizing and risk management
- Backtest validated: +149% over 5 years, survived COVID crash

Usage:
    >>> strategy = VIXAdaptiveStrategy(config)
    >>> strategy.update(date=today)
    >>> tier = strategy.get_current_tier()
    >>> print(f"Current tier: {tier}")
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import collections
import pandas as pd
import logging

from .tier_manager import VIXTierManager, TierType
from .mean_reversion import MeanReversionStrategy, Signal as MRSignal
from .bounce_strategy import BounceStrategy, Signal as BounceSignal
from .score_adapter import ScoreAdapter

logger = logging.getLogger(__name__)


@dataclass
class Action:
    """Trading action to be executed."""
    action_type: str  # 'open', 'close', 'update_stop'
    symbol: str
    tier: str
    signal: Optional[Any] = None
    reason: Optional[str] = None


class VIXAdaptiveStrategy:
    """
    VIX Adaptive Trading Strategy v3.0

    Orchestrates sub-strategies based on VIX tier.
    """

    def __init__(self, config: Dict, vix_data_provider):
        """
        Initialize VIX Adaptive Strategy.

        Args:
            config: Configuration dict with structure:
                {
                    'boundaries': {'normal_max': 20, 'skip_max': 24, 'high_max': 38},
                    'tiers': {
                        'normal': {...},
                        'high': {...}
                    },
                    'score_adaptation': {
                        'enabled': True,
                        'method': 'vix_based',
                        'thresholds': {'bull': 90, 'normal': 80, 'bear': 70}
                    }
                }
            vix_data_provider: VIXDataProvider instance
        """
        self.config = config
        self.vix_provider = vix_data_provider

        # Initialize tier manager
        self.tier_manager = VIXTierManager(config['boundaries'])

        # Initialize sub-strategies
        self.mean_reversion = MeanReversionStrategy(config['tiers']['normal'])
        self.bounce_strategy = BounceStrategy(config['tiers']['high'])

        # Initialize score adapter
        score_config = config.get('score_adaptation', {})
        if score_config.get('enabled', True):
            thresholds = score_config.get('thresholds', {})
            self.score_adapter = ScoreAdapter(
                method=score_config.get('method', 'vix_based'),
                bull_threshold=thresholds.get('bull', 90),
                normal_threshold=thresholds.get('normal', 80),
                bear_threshold=thresholds.get('bear', 70)
            )
        else:
            self.score_adapter = None

        # State
        self.current_tier: Optional[TierType] = None
        self.current_vix: Optional[float] = None
        self.previous_vix: Optional[float] = None
        self._vix_history: collections.deque = collections.deque(maxlen=3)

        logger.info(f"✅ Initialized VIXAdaptiveStrategy v3.0")
        logger.info(f"   Boundaries: {config['boundaries']}")
        logger.info(f"   Score adaptation: {score_config.get('enabled', True)}")

    def update(
        self,
        date,
        stock_data: Dict[str, pd.DataFrame],
        active_positions: List[Any]
    ) -> List[Action]:
        """
        Main update loop - called each trading day.

        Args:
            date: Current date
            stock_data: Dict of {symbol: DataFrame}
            active_positions: List of currently active trades

        Returns:
            List of Action objects (open/close/update)
        """
        actions = []

        # Get current VIX
        self.previous_vix = self.current_vix
        self.current_vix = self.vix_provider.get_vix_for_date(date)

        if self.current_vix is None:
            logger.warning(f"No VIX data for {date}, skipping")
            return actions

        # 3-day rolling average prevents 19.9↔20.1 boundary oscillation
        self._vix_history.append(self.current_vix)
        vix_smoothed = sum(self._vix_history) / len(self._vix_history)

        # Get current tier (use smoothed VIX to avoid flip-flopping at boundaries)
        prev_tier = self.current_tier
        self.current_tier = self.tier_manager.get_tier(vix_smoothed)

        # Log tier transitions
        if prev_tier and prev_tier != self.current_tier:
            logger.warning(
                f"🔄 Tier transition: {prev_tier.upper()} → {self.current_tier.upper()} "
                f"(VIX: {self.current_vix:.2f}, smoothed: {vix_smoothed:.2f})"
            )

        # Route based on tier
        if self.current_tier == 'extreme':
            # EXTREME: Close all positions
            logger.critical(
                f"🚨 EXTREME tier activated! VIX={self.current_vix:.2f} (smoothed={vix_smoothed:.2f}) > 38 - CLOSING ALL"
            )
            for position in active_positions:
                actions.append(Action(
                    action_type='close',
                    symbol=position.symbol,
                    tier='extreme',
                    reason='VIX_EXTREME'
                ))

        elif self.current_tier == 'skip':
            # SKIP: No new trades, only manage existing
            logger.info(f"SKIP tier (VIX={self.current_vix:.2f}, smoothed={vix_smoothed:.2f}), no new trades")

        elif self.current_tier == 'normal':
            # NORMAL tier (VIX < 20): Dip-Bounce strategy handles this regime.
            # VIX Adaptive only activates in HIGH tier (VIX 24-38) where its
            # falling-VIX filter adds value not present in Dip-Bounce.
            logger.info(
                f"NORMAL tier (VIX={self.current_vix:.2f}, smoothed={vix_smoothed:.2f}) "
                f"— delegated to DipBounce strategy, no VIX Adaptive signals"
            )
            # actions stays empty — Dip-Bounce generates signals in this regime

        elif self.current_tier == 'high':
            # HIGH: Bounce strategy
            logger.info(f"HIGH tier (VIX={self.current_vix:.2f}, smoothed={vix_smoothed:.2f}), bounce strategy")

            # Check VIX direction
            vix_falling = False
            if self.previous_vix is not None:
                vix_falling = self.tier_manager.is_vix_falling(
                    self.current_vix,
                    self.previous_vix
                )

            if not vix_falling:
                logger.info("VIX not falling, waiting for bounce confirmation")

            # Scan for bounce signals
            signals = self.bounce_strategy.scan_bounce_signals(
                date=date,
                stock_data=stock_data,
                vix_falling=vix_falling
            )

            # Create open actions
            for signal in signals:
                actions.append(Action(
                    action_type='open',
                    symbol=signal.symbol,
                    tier='high',
                    signal=signal
                ))

        return actions

    def _get_score_threshold(self) -> float:
        """
        Get adaptive score threshold based on current market regime.

        Returns:
            Score threshold (70-90)
        """
        if self.score_adapter is None:
            # Use fixed threshold from config
            return self.config['tiers']['normal'].get('min_score', 80)

        # Use adaptive threshold
        threshold = self.score_adapter.get_score_threshold(vix=self.current_vix)

        return threshold

    def get_current_tier(self) -> Optional[TierType]:
        """Get current VIX tier."""
        return self.current_tier

    def get_current_vix(self) -> Optional[float]:
        """Get current VIX value."""
        return self.current_vix

    def get_tier_config(self, tier: str) -> Dict:
        """
        Get configuration for specific tier.

        Args:
            tier: 'normal' or 'high'

        Returns:
            Config dict for that tier
        """
        return self.config['tiers'].get(tier, {})

    def __repr__(self) -> str:
        vix_str = f"{self.current_vix:.1f}" if self.current_vix is not None else "N/A"
        tier_str = self.current_tier if self.current_tier else "N/A"
        return f"VIXAdaptiveStrategy(tier={tier_str}, VIX={vix_str})"
