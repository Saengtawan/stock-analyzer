"""
Strategy Manager

Orchestrates multiple trading strategies, combining their signals
and handling deduplication.
"""

from typing import List, Dict, Any, Optional
from loguru import logger
import pandas as pd

from .base_strategy import BaseStrategy, TradingSignal


class StrategyManager:
    """
    Manages multiple trading strategies.

    Responsibilities:
    - Register/unregister strategies
    - Run all enabled strategies
    - Combine and deduplicate signals
    - Track per-strategy performance
    """

    def __init__(self):
        """Initialize empty strategy manager"""
        self.strategies: List[BaseStrategy] = []
        self._stats: Dict[str, Dict[str, Any]] = {}

    def register(self, strategy: BaseStrategy) -> None:
        """
        Register a new strategy.

        Args:
            strategy: Strategy instance to register
        """
        if strategy.name in [s.name for s in self.strategies]:
            logger.warning(f"Strategy {strategy.name} already registered, skipping")
            return

        self.strategies.append(strategy)
        self._stats[strategy.name] = {
            'scans': 0,
            'signals': 0,
            'last_run': None,
        }
        logger.info(f"✅ Registered strategy: {strategy.display_name} ({strategy.name})")

    def unregister(self, strategy_name: str) -> bool:
        """
        Unregister a strategy by name.

        Args:
            strategy_name: Name of strategy to remove

        Returns:
            True if removed, False if not found
        """
        for i, strategy in enumerate(self.strategies):
            if strategy.name == strategy_name:
                self.strategies.pop(i)
                logger.info(f"Unregistered strategy: {strategy_name}")
                return True
        return False

    def get_strategy(self, name: str) -> Optional[BaseStrategy]:
        """Get strategy by name"""
        for strategy in self.strategies:
            if strategy.name == name:
                return strategy
        return None

    def list_strategies(self) -> List[Dict[str, Any]]:
        """
        List all registered strategies with their info.

        Returns:
            List of strategy info dicts
        """
        return [s.get_info() for s in self.strategies]

    def scan_all(
        self,
        universe: List[str],
        data_cache: Dict[str, pd.DataFrame],
        market_data: Dict[str, Any] = None,
        progress_callback = None,
        enabled_only: bool = True
    ) -> List[TradingSignal]:
        """
        Run all strategies and combine results.

        Args:
            universe: List of symbols to scan
            data_cache: Dict of symbol -> OHLCV DataFrame
            market_data: Optional market context
            progress_callback: Optional progress callback
            enabled_only: Only run enabled strategies

        Returns:
            Combined list of signals from all strategies
        """
        all_signals = []
        strategies_to_run = self.strategies if not enabled_only else [s for s in self.strategies if s.is_enabled()]

        logger.info(f"🔍 Running {len(strategies_to_run)} strategies on {len(universe)} stocks")

        for strategy in strategies_to_run:
            try:
                logger.info(f"   Running {strategy.display_name}...")
                signals = strategy.scan(
                    universe=universe,
                    data_cache=data_cache,
                    market_data=market_data,
                    progress_callback=progress_callback
                )

                # Update stats
                self._stats[strategy.name]['scans'] += 1
                self._stats[strategy.name]['signals'] += len(signals)
                self._stats[strategy.name]['last_run'] = pd.Timestamp.now().isoformat()

                logger.info(f"   ✅ {strategy.display_name}: {len(signals)} signals")
                all_signals.extend(signals)

            except Exception as e:
                logger.error(f"   ❌ {strategy.display_name} failed: {e}")
                continue

        # Deduplicate signals (if same stock appears in multiple strategies)
        deduplicated = self._deduplicate_signals(all_signals)

        logger.info(f"📊 Total: {len(all_signals)} signals ({len(deduplicated)} unique stocks)")

        return deduplicated

    def _deduplicate_signals(self, signals: List[TradingSignal]) -> List[TradingSignal]:
        """
        Handle duplicate signals (same stock from multiple strategies).

        Strategy:
        1. Group by symbol
        2. If single strategy: keep as-is
        3. If multiple strategies: keep highest score
           - Add metadata noting which strategies found it

        Args:
            signals: List of all signals

        Returns:
            Deduplicated list of signals
        """
        if not signals:
            return []

        # Group by symbol
        by_symbol: Dict[str, List[TradingSignal]] = {}
        for sig in signals:
            if sig.symbol not in by_symbol:
                by_symbol[sig.symbol] = []
            by_symbol[sig.symbol].append(sig)

        # Deduplicate
        result = []
        for symbol, sigs in by_symbol.items():
            if len(sigs) == 1:
                # Only one strategy found this
                result.append(sigs[0])
            else:
                # Multiple strategies found this - keep highest score
                best = max(sigs, key=lambda s: s.score)

                # Add metadata about other strategies
                strategies = [s.strategy for s in sigs]
                best.metadata['all_strategies'] = strategies
                best.metadata['strategy_count'] = len(strategies)

                # Update reasons to include all
                all_reasons = []
                for sig in sigs:
                    all_reasons.extend(sig.reasons)
                best.reasons = list(set(all_reasons))  # Deduplicate reasons

                logger.debug(f"   {symbol}: Found by {len(strategies)} strategies ({', '.join(strategies)}), keeping {best.strategy} (score={best.score})")
                result.append(best)

        return result

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all strategies"""
        return self._stats.copy()

    def reset_stats(self):
        """Reset all statistics"""
        for strategy_name in self._stats:
            self._stats[strategy_name] = {
                'scans': 0,
                'signals': 0,
                'last_run': None,
            }
        logger.info("Statistics reset")
