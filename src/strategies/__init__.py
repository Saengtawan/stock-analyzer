"""
Strategies Package

Contains trading strategy implementations and utilities:
- SL/TP Calculator: Single source of truth for stop loss and take profit calculations
- Strategy Pattern: Multi-strategy architecture support
- DipBounceStrategy: Buy dips with bounce confirmation
"""

from .sl_tp_calculator import SLTPCalculator, SLTPResult, calculate_sl_tp

# Strategy pattern
try:
    from .base_strategy import BaseStrategy, TradingSignal
    from .strategy_manager import StrategyManager
    from .strategy_orchestrator import StrategyOrchestrator
    from .dip_bounce_strategy import DipBounceStrategy
    __all__ = [
        'SLTPCalculator', 'SLTPResult', 'calculate_sl_tp',
        'BaseStrategy', 'TradingSignal', 'StrategyManager', 'StrategyOrchestrator',
        'DipBounceStrategy'
    ]
except ImportError:
    __all__ = ['SLTPCalculator', 'SLTPResult', 'calculate_sl_tp']
