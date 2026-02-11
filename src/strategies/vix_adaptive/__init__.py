"""
VIX Adaptive Trading Strategy v3.0

A volatility-adaptive trading system that adjusts strategy based on VIX levels.

Tiers:
- NORMAL (VIX < 20): Mean reversion strategy, 3 positions
- SKIP (VIX 20-24): No new trades, manage existing only
- HIGH (VIX 24-38): Bounce strategy, 1 position
- EXTREME (VIX > 38): Close all positions

Author: Claude Code
Date: 2026-02-11
"""

from .tier_manager import VIXTierManager
from .vix_adaptive_strategy import VIXAdaptiveStrategy
from .engine_integration import VIXAdaptiveIntegration

__all__ = [
    'VIXTierManager',
    'VIXAdaptiveStrategy',
    'VIXAdaptiveIntegration',
]

__version__ = '3.0.0'
