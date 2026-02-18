"""
VIX Adaptive Strategy - Trading Engine Integration

This module provides easy integration of VIX Adaptive v3.0 with AutoTradingEngine.

Usage in auto_trading_engine.py:
    from strategies.vix_adaptive.engine_integration import VIXAdaptiveIntegration

    # In __init__
    self.vix_adaptive = VIXAdaptiveIntegration(config_path='config/vix_adaptive.yaml')

    # In _run_loop (before or after regular screener)
    vix_signals = self.vix_adaptive.scan_signals(date=today, stock_data=self.stock_data_cache)
"""

import yaml
from typing import Dict, List, Optional
from pathlib import Path
import pandas as pd
from loguru import logger

from .vix_adaptive_strategy import VIXAdaptiveStrategy, Action
from data.vix_data_provider import VIXDataProvider


class VIXAdaptiveIntegration:
    """
    Easy integration wrapper for VIX Adaptive Strategy.

    Handles:
    - Config loading
    - VIX data provider setup
    - Strategy initialization
    - Signal generation
    - Indicator validation
    """

    def __init__(
        self,
        config_path: str = 'config/vix_adaptive.yaml',
        enabled: bool = True
    ):
        """
        Initialize VIX Adaptive integration.

        Args:
            config_path: Path to vix_adaptive.yaml config file
            enabled: Enable/disable strategy (for easy on/off)
        """
        self.enabled = enabled

        if not self.enabled:
            logger.info("VIX Adaptive Strategy: DISABLED")
            return

        # Load config
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"VIX Adaptive config not found: {config_path}")
            self.enabled = False
            return

        with open(config_file) as f:
            self.config = yaml.safe_load(f)

        logger.info(f"VIX Adaptive v{self.config.get('version', '3.0')}: Loading...")

        # Initialize VIX data provider
        self.vix_provider = VIXDataProvider(
            cache_duration_hours=self.config['data'].get('cache_duration_hours', 1)
        )

        # Fetch initial VIX data
        try:
            self.vix_provider.fetch_vix_data()
            logger.info(f"VIX data loaded: {self.vix_provider}")
        except Exception as e:
            logger.error(f"Failed to fetch VIX data: {e}")
            self.enabled = False
            return

        # Initialize strategy
        self.strategy = VIXAdaptiveStrategy(self.config, self.vix_provider)

        # Pre-compute initial tier from latest VIX (so repr shows correct tier at startup)
        try:
            from datetime import date as _date
            today = _date.today()
            initial_vix = self.vix_provider.get_vix_for_date(today)
            if initial_vix is not None:
                self.strategy.current_vix = initial_vix
                self.strategy.current_tier = self.strategy.tier_manager.get_tier(initial_vix)
                logger.info(
                    f"Initial VIX: {initial_vix:.2f} → tier={self.strategy.current_tier.upper()}"
                )
        except Exception as e:
            logger.debug(f"Could not pre-compute initial VIX tier: {e}")

        logger.info(f"✅ VIX Adaptive v3.0 initialized")
        logger.info(f"   Boundaries: {self.config['boundaries']}")
        logger.info(f"   Score adaptation: {self.config['score_adaptation']['enabled']}")

    def scan_signals(
        self,
        date,
        stock_data: Dict[str, pd.DataFrame],
        active_positions: List = None
    ) -> List[Dict]:
        """
        Scan for VIX Adaptive signals.

        Args:
            date: Current date (datetime.date or pd.Timestamp)
            stock_data: Dict of {symbol: DataFrame with indicators}
            active_positions: List of currently active positions

        Returns:
            List of signal dicts with keys:
                - symbol, tier, score, price, reason, stop_loss, etc.
        """
        if not self.enabled:
            return []

        if active_positions is None:
            active_positions = []

        # Validate indicators
        missing_indicators = self._check_required_indicators(stock_data)
        if missing_indicators:
            logger.warning(
                f"VIX Adaptive: Missing indicators {missing_indicators}. "
                f"Add to TechnicalIndicators.calculate_vix_adaptive_indicators()"
            )
            return []

        # Get actions from strategy
        try:
            actions = self.strategy.update(
                date=date,
                stock_data=stock_data,
                active_positions=active_positions
            )
        except Exception as e:
            logger.error(f"VIX Adaptive scan failed: {e}")
            return []

        # Convert actions to signal format
        # v6.23: Pass stock_data and date to calculate gap_pct for adaptive timing
        signals = []
        for action in actions:
            if action.action_type == 'open':
                signal_dict = self._action_to_signal(action, stock_data, date)
                signals.append(signal_dict)
            elif action.action_type == 'close':
                # Handle close actions (add to result if needed)
                logger.warning(
                    f"VIX Adaptive: Close signal for {action.symbol} "
                    f"(reason: {action.reason})"
                )

        if signals:
            tier = self.strategy.get_current_tier()
            vix = self.strategy.get_current_vix()
            logger.info(
                f"VIX Adaptive: {len(signals)} signals "
                f"(VIX={vix:.2f}, tier={tier.upper()})"
            )

        return signals

    def _check_required_indicators(
        self,
        stock_data: Dict[str, pd.DataFrame]
    ) -> List[str]:
        """
        Check if required indicators exist in stock data.

        Returns:
            List of missing indicator names (empty if all present)
        """
        required = ['score', 'atr_pct', 'yesterday_dip', 'return_2d', 'dip_from_3d_high']

        # Check first stock
        if not stock_data:
            return required

        first_symbol = next(iter(stock_data))
        df = stock_data[first_symbol]

        missing = [ind for ind in required if ind not in df.columns]

        return missing

    def _action_to_signal(
        self,
        action: Action,
        stock_data: Dict[str, pd.DataFrame] = None,
        date = None
    ) -> Dict:
        """
        Convert Action object to signal dict format.

        Args:
            action: Action from VIXAdaptiveStrategy
            stock_data: Dict of {symbol: DataFrame} (v6.23: for gap_pct calculation)
            date: Current date (v6.23: for gap_pct calculation)

        Returns:
            Signal dict compatible with trading engine
        """
        signal = action.signal

        # Get tier config for stop loss calculation
        tier_config = self.strategy.get_tier_config(action.tier)

        # Calculate stop loss
        if action.tier == 'normal':
            stop_loss = self.strategy.mean_reversion.calculate_stop_loss(
                signal.price,
                signal.atr_pct
            )
        else:  # high tier
            stop_loss = self.strategy.bounce_strategy.calculate_stop_loss(
                signal.price,
                signal.atr_pct
            )

        # v6.23: Calculate gap_pct for adaptive entry timing
        gap_pct = 0.0
        if stock_data and date and signal.symbol in stock_data:
            try:
                import pandas as pd
                df = stock_data[signal.symbol]

                # Convert date if needed
                if isinstance(date, pd.Timestamp):
                    lookup_date = date.date()
                else:
                    lookup_date = date

                if lookup_date in df.index:
                    row = df.loc[lookup_date]
                    # Get previous close
                    date_idx = df.index.get_loc(lookup_date)
                    if date_idx > 0:
                        prev_row = df.iloc[date_idx - 1]
                        prev_close = prev_row['close']

                        # Calculate gap from open to previous close
                        if 'open' in row:
                            today_open = row['open']
                            gap_pct = ((today_open - prev_close) / prev_close) * 100
            except Exception as e:
                logger.debug(f"Could not calculate gap_pct for {signal.symbol}: {e}")
                gap_pct = 0.0

        # Build signal dict
        signal_dict = {
            'symbol': signal.symbol,
            'tier': action.tier,
            'score': signal.score,
            'entry_price': signal.price,
            'stop_loss': stop_loss,
            'atr_pct': signal.atr_pct,
            'reason': signal.reason,
            'strategy': 'vix_adaptive',
            'max_hold_days': tier_config.get('max_hold_days', 10),
            'gap_pct': round(gap_pct, 2),  # v6.23: For adaptive entry timing
        }

        # Add tier-specific fields
        if action.tier == 'high':
            signal_dict['bounce_gain'] = signal.bounce_gain
            signal_dict['dip_from_high'] = signal.dip_from_high

        return signal_dict

    def get_current_tier(self) -> Optional[str]:
        """Get current VIX tier."""
        if not self.enabled:
            return None
        return self.strategy.get_current_tier()

    def get_current_vix(self) -> Optional[float]:
        """Get current VIX value."""
        if not self.enabled:
            return None
        return self.strategy.get_current_vix()

    def refresh_vix_data(self):
        """Refresh VIX data from source."""
        if not self.enabled:
            return

        try:
            self.vix_provider.fetch_vix_data(force_refresh=True)
            logger.info(f"VIX data refreshed: {self.vix_provider}")
        except Exception as e:
            logger.error(f"Failed to refresh VIX data: {e}")

    def __repr__(self) -> str:
        if not self.enabled:
            return "VIXAdaptiveIntegration(DISABLED)"

        tier = self.strategy.get_current_tier() if self.strategy else None
        vix = self.strategy.get_current_vix() if self.strategy else None

        tier_str = tier.upper() if tier else "N/A"
        vix_str = f"{vix:.1f}" if vix is not None else "N/A"

        return f"VIXAdaptiveIntegration(tier={tier_str}, VIX={vix_str})"
