"""
Base Strategy Interface

All trading strategies must inherit from BaseStrategy and implement
the required methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import pandas as pd
import time


@dataclass
class TradingSignal:
    """
    Universal signal format for all strategies.

    Each strategy returns signals in this format with strategy-specific tagging.
    """
    # Basic info
    symbol: str
    strategy: str  # "dip_bounce", "mean_reversion", "breakout", etc.

    # Entry/Exit
    entry_price: float
    stop_loss: float
    take_profit: float

    # Scoring
    score: int
    confidence: float = 0.0  # 0-100%

    # Risk metrics
    risk_reward: float = 0.0
    max_loss_pct: float = 0.0
    expected_gain_pct: float = 0.0

    # Technical indicators
    atr_pct: float = 0.0
    rsi: float = 0.0
    momentum_5d: float = 0.0
    momentum_20d: float = 0.0
    distance_from_high: float = 0.0

    # Strategy-specific
    reasons: List[str] = field(default_factory=list)
    sector: str = ""
    market_regime: str = ""
    sector_score: float = 0.0

    # SL/TP details
    sl_method: str = ""
    tp_method: str = ""
    swing_low: float = 0.0
    resistance: float = 0.0
    volume_ratio: float = 1.0

    # Metadata
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def expected_gain(self) -> float:
        """Expected gain in %"""
        if self.expected_gain_pct:
            return self.expected_gain_pct
        return ((self.take_profit - self.entry_price) / self.entry_price) * 100

    @property
    def max_loss(self) -> float:
        """Maximum loss in %"""
        if self.max_loss_pct:
            return self.max_loss_pct
        return ((self.entry_price - self.stop_loss) / self.entry_price) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'symbol': self.symbol,
            'strategy': self.strategy,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'score': self.score,
            'confidence': self.confidence,
            'risk_reward': self.risk_reward,
            'atr_pct': self.atr_pct,
            'rsi': self.rsi,
            'momentum_5d': self.momentum_5d,
            'momentum_20d': self.momentum_20d,
            'distance_from_high': self.distance_from_high,
            'reasons': self.reasons,
            'sector': self.sector,
            'market_regime': self.market_regime,
            'sl_method': self.sl_method,
            'tp_method': self.tp_method,
            'expected_gain': self.expected_gain,
            'max_loss': self.max_loss,
            'timestamp': self.timestamp,
        }


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Each strategy must implement:
    - name: Unique identifier
    - scan: Main scanning logic
    - analyze_stock: Single stock analysis
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize strategy with optional configuration.

        Args:
            config: Strategy-specific configuration dict
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)

        # Generic trace system (works for all strategies)
        self.enable_trace = self.config.get('enable_trace', False)
        self._init_trace_system()

    def _init_trace_system(self):
        """
        Initialize trace tracking system.

        Called automatically during __init__.
        Sets up stage definitions and tracking structures.
        """
        if self.enable_trace:
            # Get stage definitions from strategy
            self.stages = self.define_stages()

            # Auto-create timings dict from stages
            self.stage_timings: Dict[str, List[float]] = {
                stage['name']: [] for stage in self.stages
            }

            # Store individual stock traces
            self.execution_trace: List[Dict[str, Any]] = []

            # Cache for quick lookup of stock traces
            self._trace_cache: Dict[str, Dict[str, Any]] = {}

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Strategy identifier (lowercase, underscore-separated).

        Examples: "dip_bounce", "mean_reversion", "breakout"
        """
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """
        Human-readable strategy name.

        Examples: "Dip-Bounce", "Mean Reversion", "Breakout"
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Brief description of the strategy.
        """
        pass

    @abstractmethod
    def define_stages(self) -> List[Dict[str, str]]:
        """
        Define pipeline stages for this strategy.

        Each strategy MUST implement this to define its execution stages.
        This enables generic trace tracking and visualization.

        Returns:
            List of stage definitions with metadata:
            [
                {
                    'name': 'INPUT',           # Stage identifier (required)
                    'icon': '📥',              # Icon for UI (required)
                    'title': 'Input',          # Display name (required)
                    'description': '...'       # Optional description
                },
                ...
            ]

        Example (DipBounce):
            return [
                {'name': 'INPUT', 'icon': '📥', 'title': 'Input'},
                {'name': 'BASIC_FILTERS', 'icon': '🔍', 'title': 'Basic Filters'},
                {'name': 'BOUNCE_FILTERS', 'icon': '🎯', 'title': 'Bounce Confirmation'},
                {'name': 'SCORING', 'icon': '📊', 'title': 'Scoring'},
                {'name': 'THRESHOLD', 'icon': '✅', 'title': 'Threshold'},
                {'name': 'OUTPUT', 'icon': '🚀', 'title': 'Output'},
            ]

        Example (Future Candlestick):
            return [
                {'name': 'INPUT', 'icon': '📥', 'title': 'Input'},
                {'name': 'PATTERN_DETECTION', 'icon': '🕯️', 'title': 'Pattern Detection'},
                {'name': 'CONTEXT_FILTERS', 'icon': '📈', 'title': 'Context Filters'},
                {'name': 'SCORING', 'icon': '📊', 'title': 'Scoring'},
                {'name': 'OUTPUT', 'icon': '🚀', 'title': 'Output'},
            ]
        """
        pass

    @abstractmethod
    def scan(
        self,
        universe: List[str],
        data_cache: Dict[str, pd.DataFrame],
        market_data: Dict[str, Any] = None,
        progress_callback = None
    ) -> List[TradingSignal]:
        """
        Scan universe and return signals.

        Args:
            universe: List of stock symbols to scan
            data_cache: Dict mapping symbol -> DataFrame with OHLCV data
            market_data: Optional market context (regime, sector data, etc.)
            progress_callback: Optional callback for progress updates

        Returns:
            List of TradingSignal objects
        """
        pass

    @abstractmethod
    def analyze_stock(
        self,
        symbol: str,
        data: pd.DataFrame,
        market_data: Dict[str, Any] = None
    ) -> Optional[TradingSignal]:
        """
        Analyze a single stock and return signal if criteria met.

        Args:
            symbol: Stock symbol
            data: OHLCV DataFrame for the stock
            market_data: Optional market context

        Returns:
            TradingSignal if criteria met, None otherwise
        """
        pass

    def is_enabled(self) -> bool:
        """Check if strategy is enabled"""
        return self.enabled

    def enable(self):
        """Enable this strategy"""
        self.enabled = True

    def disable(self):
        """Disable this strategy"""
        self.enabled = False

    def get_info(self) -> Dict[str, Any]:
        """Get strategy information"""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'enabled': self.enabled,
            'config': self.config,
        }

    # ===== Generic Trace System Methods =====

    def track_stage_timing(self, stage_name: str, duration_ms: float):
        """
        Track execution time for a stage.

        This is a generic helper that works for any strategy.
        Call this from analyze_stock() after each stage completes.

        Args:
            stage_name: Name of the stage (e.g., 'BASIC_FILTERS')
            duration_ms: Duration in milliseconds

        Example:
            start = time.time()
            # ... stage processing ...
            duration = (time.time() - start) * 1000
            self.track_stage_timing('BASIC_FILTERS', duration)
        """
        if self.enable_trace and stage_name in self.stage_timings:
            self.stage_timings[stage_name].append(duration_ms)

    def get_stock_trace(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get trace data for a specific stock.

        Useful for routing decisions (check rejection stage).

        Args:
            symbol: Stock symbol

        Returns:
            Trace dict if found, None otherwise

        Example:
            trace = strategy.get_stock_trace('AAPL')
            if trace and trace.get('rejection_stage') == 'BOUNCE_FILTERS':
                # Route to mean reversion
                ...
        """
        if not self.enable_trace:
            return None

        # Check cache first
        if symbol in self._trace_cache:
            return self._trace_cache[symbol]

        # Search in execution_trace
        for trace in self.execution_trace:
            if trace.get('symbol') == symbol:
                self._trace_cache[symbol] = trace
                return trace

        return None

    def get_trace_summary(self) -> Dict[str, Any]:
        """
        Get aggregated trace summary for visualization.

        This is a generic method that works for ANY strategy.
        It auto-generates summary from stage definitions.

        Returns:
            {
                'strategy': 'dip_bounce',
                'total_stocks': 260,
                'stages': {
                    'INPUT': {
                        'name': 'INPUT',
                        'icon': '📥',
                        'title': 'Input',
                        'description': '...',
                        'total': 260,
                        'passed': 260,
                        'failed': 0,
                        'stocks': [...],
                        'average_duration_ms': 0.0
                    },
                    ...
                },
                'rejection_breakdown': {
                    'no_dip': 189,
                    'still_falling': 28,
                    ...
                }
            }
        """
        if not self.enable_trace:
            return {'error': 'Trace not enabled'}

        # Initialize summary structure from stage definitions
        summary = {
            'strategy': self.name,
            'total_stocks': len(self.execution_trace),
            'stages': {},
            'rejection_breakdown': {},
        }

        # Auto-populate stages from define_stages()
        for stage in self.stages:
            stage_name = stage['name']
            summary['stages'][stage_name] = {
                'name': stage_name,
                'icon': stage['icon'],
                'title': stage['title'],
                'description': stage.get('description', ''),
                'total': 0,
                'passed': 0,
                'failed': 0,
                'stocks': [],
                'average_duration_ms': 0.0
            }

        # Populate from trace data
        for trace in self.execution_trace:
            symbol = trace['symbol']

            # Process each stage in trace
            for stage_name in summary['stages'].keys():
                stage_data = trace.get('stages', {}).get(stage_name)

                if stage_data:
                    summary['stages'][stage_name]['total'] += 1

                    if stage_data.get('passed'):
                        summary['stages'][stage_name]['passed'] += 1
                        summary['stages'][stage_name]['stocks'].append(symbol)
                    else:
                        summary['stages'][stage_name]['failed'] += 1

                        # Track rejection reason
                        reason = stage_data.get('reason', 'Unknown')
                        if reason not in summary['rejection_breakdown']:
                            summary['rejection_breakdown'][reason] = 0
                        summary['rejection_breakdown'][reason] += 1

        # Add average timing
        for stage_name, timings in self.stage_timings.items():
            if timings and stage_name in summary['stages']:
                avg_duration = sum(timings) / len(timings)
                summary['stages'][stage_name]['average_duration_ms'] = round(avg_duration, 2)

        return summary
