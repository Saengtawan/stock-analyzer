"""
VIX Adaptive Strategy Wrapper
==============================

Wraps VIXAdaptiveIntegration to conform to BaseStrategy interface
for integration with StrategyManager.
"""

from typing import List, Optional, Dict, Any
import pandas as pd
from datetime import datetime
from loguru import logger

from strategies.base_strategy import BaseStrategy, TradingSignal
from strategies.vix_adaptive.engine_integration import VIXAdaptiveIntegration
from strategies.vix_adaptive.data_enricher import add_vix_indicators_to_cache


class VIXAdaptiveStrategyWrapper(BaseStrategy):
    """
    Wrapper for VIX Adaptive Strategy to integrate with StrategyManager.

    This wraps the existing VIXAdaptiveIntegration and adapts it to the
    BaseStrategy interface.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize VIX Adaptive wrapper.

        Args:
            config: Configuration dict with optional keys:
                - config_path: Path to vix_adaptive.yaml
                - enabled: Enable/disable strategy
                - enable_trace: Enable execution tracing
        """
        super().__init__(config)

        # Initialize VIX Adaptive
        config_path = self.config.get('config_path', 'config/vix_adaptive.yaml')
        vix_enabled = self.config.get('enabled', True)

        try:
            self.vix_adaptive = VIXAdaptiveIntegration(
                config_path=config_path,
                enabled=vix_enabled
            )
            logger.info(f"✅ VIX Adaptive wrapper initialized: {self.vix_adaptive}")
        except Exception as e:
            logger.error(f"Failed to initialize VIX Adaptive: {e}")
            self.vix_adaptive = None
            self.enabled = False

    @property
    def name(self) -> str:
        """Strategy identifier"""
        return "vix_adaptive"

    @property
    def display_name(self) -> str:
        """Human-readable name"""
        return "VIX Adaptive"

    @property
    def description(self) -> str:
        """Strategy description"""
        return "VIX-based adaptive strategy with 4 tiers (NORMAL/SKIP/HIGH/EXTREME)"

    def define_stages(self) -> List[Dict[str, str]]:
        """
        Define VIX Adaptive pipeline stages.

        Returns:
            List of stage definitions
        """
        return [
            {
                'name': 'INPUT',
                'icon': '📥',
                'title': 'Input',
                'description': 'Load stock data'
            },
            {
                'name': 'VIX_TIER',
                'icon': '📊',
                'title': 'VIX Tier Detection',
                'description': 'Determine current VIX tier'
            },
            {
                'name': 'INDICATOR_ENRICHMENT',
                'icon': '🔧',
                'title': 'Indicator Calculation',
                'description': 'Add VIX-specific indicators'
            },
            {
                'name': 'TIER_STRATEGY',
                'icon': '🎯',
                'title': 'Tier Strategy Selection',
                'description': 'Choose strategy based on tier'
            },
            {
                'name': 'SIGNAL_GENERATION',
                'icon': '⚡',
                'title': 'Signal Generation',
                'description': 'Generate signals for current tier'
            },
            {
                'name': 'OUTPUT',
                'icon': '🚀',
                'title': 'Output',
                'description': 'Return validated signals'
            },
        ]

    def scan(
        self,
        universe: List[str],
        data_cache: Dict[str, pd.DataFrame],
        market_data: Dict[str, Any] = None,
        progress_callback = None
    ) -> List[TradingSignal]:
        """
        Scan universe using VIX Adaptive strategy.

        Args:
            universe: List of stock symbols to scan
            data_cache: Dict mapping symbol -> DataFrame with OHLCV data
            market_data: Optional market context
            progress_callback: Optional progress callback

        Returns:
            List of TradingSignal objects
        """
        if not self.enabled or not self.vix_adaptive or not self.vix_adaptive.enabled:
            return []

        try:
            # Stage 1: Enrich data cache with VIX indicators
            add_vix_indicators_to_cache(data_cache)

            # Stage 2: Get signals from VIX Adaptive
            vix_signals = self.vix_adaptive.scan_signals(
                date=datetime.now().date(),
                stock_data=data_cache,
                active_positions=[]  # TODO: Get from market_data if available
            )

            # Stage 3: Convert to TradingSignal format
            trading_signals = []
            for signal in vix_signals:
                trading_signal = self._convert_to_trading_signal(signal)
                if trading_signal:
                    trading_signals.append(trading_signal)

            if trading_signals:
                tier = self.vix_adaptive.get_current_tier()
                vix = self.vix_adaptive.get_current_vix()
                logger.info(
                    f"VIX Adaptive: {len(trading_signals)} signals "
                    f"(VIX={vix:.1f if vix else 'N/A'}, tier={tier.upper() if tier else 'N/A'})"
                )

            return trading_signals

        except Exception as e:
            logger.error(f"VIX Adaptive scan failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def analyze_stock(
        self,
        symbol: str,
        data: pd.DataFrame,
        market_data: Dict[str, Any] = None
    ) -> Optional[TradingSignal]:
        """
        Analyze a single stock (not used - VIX Adaptive scans in batch).

        Returns None because VIX Adaptive processes all stocks at once
        in scan() method.
        """
        # VIX Adaptive doesn't analyze stocks individually
        # It processes all stocks in batch based on tier
        return None

    def _convert_to_trading_signal(self, vix_signal: Dict[str, Any]) -> Optional[TradingSignal]:
        """
        Convert VIX Adaptive signal dict to TradingSignal object.

        Args:
            vix_signal: Signal dict from VIX Adaptive

        Returns:
            TradingSignal object or None
        """
        try:
            # Extract data from VIX signal
            symbol = vix_signal['symbol']
            tier = vix_signal.get('tier', 'unknown')
            score = vix_signal.get('score', 0)
            entry_price = vix_signal.get('entry_price', 0)
            stop_loss = vix_signal.get('stop_loss', 0)
            atr_pct = vix_signal.get('atr_pct', 0)
            reason = vix_signal.get('reason', '')

            # Calculate take profit (simple 2:1 R:R for now)
            sl_distance = entry_price - stop_loss
            take_profit = entry_price + (sl_distance * 2.0)

            # Build TradingSignal
            # v6.23: Include gap_pct in metadata for adaptive entry timing
            signal = TradingSignal(
                symbol=symbol,
                strategy='vix_adaptive',
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                score=score,
                confidence=70.0,  # Base confidence from backtest
                atr_pct=atr_pct,
                reasons=[reason, f"Tier: {tier}"],
                market_regime=tier,
                metadata={
                    'tier': tier,
                    'vix_strategy': 'mean_reversion' if tier == 'normal' else 'bounce',
                    'max_hold_days': vix_signal.get('max_hold_days', 10),
                    'gap_pct': vix_signal.get('gap_pct', 0.0),  # v6.23: For adaptive timing
                }
            )

            # Add tier-specific metadata
            if tier == 'high':
                signal.metadata['bounce_gain'] = vix_signal.get('bounce_gain', 0)
                signal.metadata['dip_from_high'] = vix_signal.get('dip_from_high', 0)

            return signal

        except Exception as e:
            logger.error(f"Failed to convert VIX signal to TradingSignal: {e}")
            return None

    def get_current_tier(self) -> Optional[str]:
        """Get current VIX tier"""
        if self.vix_adaptive:
            return self.vix_adaptive.get_current_tier()
        return None

    def get_current_vix(self) -> Optional[float]:
        """Get current VIX value"""
        if self.vix_adaptive:
            return self.vix_adaptive.get_current_vix()
        return None

    def __repr__(self) -> str:
        if not self.vix_adaptive:
            return "VIXAdaptiveStrategyWrapper(DISABLED)"

        tier = self.get_current_tier()
        vix = self.get_current_vix()

        tier_str = tier.upper() if tier else "N/A"
        vix_str = f"{vix:.1f}" if vix is not None else "N/A"

        return f"VIXAdaptiveStrategyWrapper(tier={tier_str}, VIX={vix_str})"
