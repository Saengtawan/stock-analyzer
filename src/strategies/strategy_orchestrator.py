"""
Strategy Orchestrator

Orchestrates multiple trading strategies with support for:
- Sequential execution (try strategies in order)
- Parallel execution (future)
- Conditional routing (future)
- Strategy deduplication (future)

Current: Runs DipBounce only (but ready for multi-strategy!)
"""

from typing import List, Dict, Any, Optional
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base_strategy import BaseStrategy, TradingSignal


class StrategyOrchestrator:
    """
    Orchestrates multiple trading strategies.

    Features:
    - Sequential execution (first match wins)
    - Parallel execution (future - all strategies run, pick best)
    - Routing rules (future - conditional branching)
    - Deduplication (future - handle same stock from multiple strategies)

    Example (Current - Single Strategy):
        dip_bounce = DipBounceStrategy(config)
        orchestrator = StrategyOrchestrator(
            strategies=[dip_bounce],
            config={'mode': 'sequential'}
        )
        signal = orchestrator.analyze_stock('AAPL', data)

    Example (Future - Multi-Strategy):
        dip_bounce = DipBounceStrategy(config)
        mean_rev = MeanReversionStrategy(config)

        orchestrator = StrategyOrchestrator(
            strategies=[dip_bounce, mean_rev],
            config={
                'mode': 'sequential',
                'routing_rules': {
                    'dip_bounce': {
                        'on_fail': {
                            'BOUNCE_FILTERS': 'mean_reversion'
                        }
                    }
                }
            }
        )
        signal = orchestrator.analyze_stock('AAPL', data)
    """

    def __init__(
        self,
        strategies: List[BaseStrategy],
        config: Dict[str, Any] = None
    ):
        """
        Initialize strategy orchestrator.

        Args:
            strategies: List of strategy instances
            config: Orchestration configuration:
                {
                    'mode': 'sequential',  # or 'parallel' (future)
                    'routing_rules': {},   # future
                    'deduplication': 'highest_confidence'  # future
                }
        """
        if not strategies:
            raise ValueError('At least one strategy required')

        self.strategies = {s.name: s for s in strategies}
        self.config = config or {}
        self.mode = self.config.get('mode', 'sequential')
        self.routing_rules = self.config.get('routing_rules', {})
        self.dedup_method = self.config.get('deduplication', 'highest_confidence')

        logger.info(f'StrategyOrchestrator initialized')
        logger.info(f'  Strategies: {list(self.strategies.keys())}')
        logger.info(f'  Mode: {self.mode}')
        logger.info(f'  Routing rules: {"enabled" if self.routing_rules else "disabled"}')

    def analyze_stock(
        self,
        symbol: str,
        data,
        market_data: Dict[str, Any] = None
    ) -> Optional[TradingSignal]:
        """
        Analyze stock with orchestrated strategies.

        Current: Sequential execution (try strategies in order)
        Future: Support branching and parallel execution

        Args:
            symbol: Stock symbol
            data: Price data DataFrame
            market_data: Optional market context

        Returns:
            TradingSignal if any strategy finds opportunity, None otherwise
        """
        if self.mode == 'sequential':
            return self._sequential_execution(symbol, data, market_data)
        elif self.mode == 'parallel':
            logger.warning('Parallel mode not fully implemented, falling back to sequential')
            return self._parallel_execution(symbol, data, market_data)
        else:
            raise ValueError(f'Unknown execution mode: {self.mode}')

    def _sequential_execution(
        self,
        symbol: str,
        data,
        market_data: Dict[str, Any] = None
    ) -> Optional[TradingSignal]:
        """
        Sequential strategy execution.

        Try strategies in order, return first match.

        Current logic:
            for strategy in strategies:
                result = strategy.analyze(symbol, data)
                if result:
                    return result
            return None

        Future logic (with routing):
            result = dip_bounce.analyze(symbol, data)
            if result:
                return result
            elif dip_bounce.rejection_stage == 'BOUNCE_FILTERS':
                # Route to MeanReversion
                result = mean_reversion.analyze(symbol, data)
                if result:
                    return result
            return None

        Args:
            symbol: Stock symbol
            data: Price data
            market_data: Market context

        Returns:
            TradingSignal or None
        """
        for strategy_name, strategy in self.strategies.items():
            logger.debug(f'{symbol}: Trying strategy {strategy_name}')

            # Analyze with strategy
            result = strategy.analyze_stock(symbol, data, market_data)

            if result:
                logger.info(f'{symbol}: {strategy_name} → SIGNAL (score={result.score})')
                return result
            else:
                logger.debug(f'{symbol}: {strategy_name} → NO SIGNAL')

                # Future: Check routing rules
                if self.routing_rules and strategy_name in self.routing_rules:
                    next_strategy = self._check_routing_rules(strategy_name, strategy, symbol)
                    if next_strategy:
                        logger.debug(f'{symbol}: Routing from {strategy_name} → {next_strategy}')
                        # Would recursively try next strategy here
                        # For now, just log it
                        pass

        return None

    def _parallel_execution(
        self,
        symbol: str,
        data,
        market_data: Dict[str, Any] = None
    ) -> Optional[TradingSignal]:
        """
        Parallel strategy execution (future feature).

        Run all strategies simultaneously, pick best signal.

        Flow:
            1. Run all strategies in parallel (ThreadPoolExecutor)
            2. Collect all signals
            3. Deduplicate by configured method
            4. Return best signal

        Args:
            symbol: Stock symbol
            data: Price data
            market_data: Market context

        Returns:
            Best TradingSignal or None
        """
        signals = []

        # Run strategies in parallel
        with ThreadPoolExecutor(max_workers=len(self.strategies)) as executor:
            futures = {
                executor.submit(strategy.analyze_stock, symbol, data, market_data): name
                for name, strategy in self.strategies.items()
            }

            for future in as_completed(futures):
                strategy_name = futures[future]
                try:
                    result = future.result()
                    if result:
                        signals.append({
                            'strategy': strategy_name,
                            'signal': result,
                            'score': result.score,
                            'confidence': result.confidence
                        })
                        logger.info(f'{symbol}: {strategy_name} → SIGNAL (score={result.score})')
                except Exception as e:
                    logger.error(f'{symbol}: {strategy_name} failed: {e}')

        # Deduplicate and pick best
        if signals:
            best = self._deduplicate_signals(signals)
            logger.info(f'{symbol}: Selected {best["strategy"]} (best of {len(signals)} signals)')
            return best['signal']

        return None

    def _check_routing_rules(
        self,
        strategy_name: str,
        strategy: BaseStrategy,
        symbol: str
    ) -> Optional[str]:
        """
        Check if we should route to another strategy (future).

        Example routing rule:
            'dip_bounce': {
                'on_fail': {
                    'BOUNCE_FILTERS': 'mean_reversion'
                }
            }

        Args:
            strategy_name: Current strategy name
            strategy: Strategy instance
            symbol: Stock symbol

        Returns:
            Next strategy name if routing applies, None otherwise
        """
        if not self.routing_rules or strategy_name not in self.routing_rules:
            return None

        rules = self.routing_rules[strategy_name]
        on_fail_rules = rules.get('on_fail', {})

        if not on_fail_rules:
            return None

        # Get stock trace to check rejection stage
        trace = strategy.get_stock_trace(symbol)
        if not trace:
            return None

        rejection_stage = trace.get('rejection_stage')
        if rejection_stage and rejection_stage in on_fail_rules:
            next_strategy = on_fail_rules[rejection_stage]
            logger.debug(f'Routing rule: {strategy_name}.{rejection_stage} → {next_strategy}')
            return next_strategy

        return None

    def _deduplicate_signals(
        self,
        signals: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Deduplicate signals when multiple strategies signal same stock.

        Methods:
        - highest_confidence: Pick signal with highest confidence
        - highest_score: Pick signal with highest score
        - strategy_priority: Pick by strategy priority order

        Args:
            signals: List of signal dicts with strategy/signal/score/confidence

        Returns:
            Best signal dict
        """
        if not signals:
            return None

        if len(signals) == 1:
            return signals[0]

        if self.dedup_method == 'highest_confidence':
            return max(signals, key=lambda x: (x['confidence'], x['score']))
        elif self.dedup_method == 'highest_score':
            return max(signals, key=lambda x: (x['score'], x['confidence']))
        elif self.dedup_method == 'strategy_priority':
            # Pick first by strategy order
            for strategy_name in self.strategies.keys():
                for sig in signals:
                    if sig['strategy'] == strategy_name:
                        return sig
            return signals[0]
        else:
            logger.warning(f'Unknown dedup method: {self.dedup_method}, using first signal')
            return signals[0]

    def get_trace_summary(self) -> Dict[str, Any]:
        """
        Get aggregated trace from all strategies.

        Returns:
            {
                'strategies': {
                    'dip_bounce': {...},  # DipBounce trace summary
                    'mean_reversion': {...}  # Future
                },
                'total_signals': 25,
                'strategy_breakdown': {
                    'dip_bounce': 25,
                    'mean_reversion': 0  # Future
                }
            }
        """
        summary = {
            'strategies': {},
            'total_signals': 0,
            'strategy_breakdown': {}
        }

        for strategy_name, strategy in self.strategies.items():
            # Get trace summary from each strategy
            strategy_summary = strategy.get_trace_summary()
            summary['strategies'][strategy_name] = strategy_summary

            # Count signals from OUTPUT stage
            if 'stages' in strategy_summary and 'OUTPUT' in strategy_summary['stages']:
                output_stage = strategy_summary['stages']['OUTPUT']
                signal_count = output_stage.get('passed', 0)
                summary['strategy_breakdown'][strategy_name] = signal_count
                summary['total_signals'] += signal_count

        return summary

    def get_info(self) -> Dict[str, Any]:
        """Get orchestrator information."""
        return {
            'mode': self.mode,
            'strategies': list(self.strategies.keys()),
            'routing_enabled': bool(self.routing_rules),
            'deduplication_method': self.dedup_method,
        }
