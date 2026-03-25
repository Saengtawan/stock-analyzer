"""
Context Scorer — penalizes risky stocks using Knowledge Graph.
Part of Discovery v13.1.

v13.1 fix: VIX sensitivity threshold -0.15 → -0.50
  Before: 96% of stocks triggered penalty when VIX>25 (meaningless)
  After:  only top 10% most VIX-sensitive stocks get penalty
  Crude threshold -0.15 → -0.10 (only 5 stocks have crude corr < -0.10)

Penalty tiers scaled by correlation magnitude (not flat -0.2).
"""
import logging
import sqlite3
import json
from pathlib import Path

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


class ContextScorer:
    """Score stocks using Knowledge Graph context.
    v17: spec_skip threshold learned per sector×regime via AdaptiveParams.
    """

    def __init__(self, knowledge_graph, adaptive_params=None):
        self._kg = knowledge_graph
        self._adaptive = adaptive_params

    def score(self, symbol: str, macro: dict = None) -> dict:
        """Compute context score for a stock. Returns penalties + flags.

        Penalty system: start at 0, go negative for risks.
        Speculative flags: score from KG (typically -0.3 to -1.0)
        Macro mismatch: scaled by correlation strength
        """
        ctx = self._kg.get_context(symbol)
        penalties = []
        total_penalty = 0

        # 1. Speculative flags
        spec = ctx['flags'].get('SPECULATIVE_FLAG', {})
        if spec:
            spec_score = spec.get('score', 0)
            total_penalty += spec_score
            flags = json.loads(spec.get('value', '[]')) if isinstance(spec.get('value'), str) else []
            if flags:
                penalties.append(f'SPECULATIVE({",".join(flags)}) {spec_score:+.1f}')

        # 2. Macro sensitivity — REMOVED (v17)
        # crude>85: removed — SectorScorer handles sector blocking adaptively
        # VIX corr<-0.50: removed — data shows VIX-sensitive stocks OUTPERFORM
        #   when VIX>25 (WR 58.3% vs 56.3% normal). Penalty was counterproductive.
        #   NeuralGraph Layer 3 still handles VIX dead zone (25-28) separately.

        # 3. Supply chain risk (informational only, no penalty)
        if ctx['upstream']:
            penalties.append(f'SUPPLY_CHAIN({len(ctx["upstream"])} upstream)')

        result = {
            'penalty': round(total_penalty, 2),
            'penalties': penalties,
            'flags': list(ctx['flags'].keys()),
            'upstream': [u['symbol'] for u in ctx['upstream'][:3]],
            'downstream': [d['symbol'] for d in ctx['downstream'][:3]],
            'is_speculative': 'SPECULATIVE_FLAG' in ctx['flags'],
        }

        return result

    def should_skip(self, symbol: str, macro: dict = None) -> tuple:
        """Should this stock be skipped entirely?

        Returns: (skip: bool, reason: str)
        """
        result = self.score(symbol, macro)

        # v17: adaptive skip threshold (learned per sector×regime, default -0.7)
        skip_thresh = -0.7
        if self._adaptive:
            skip_thresh = self._adaptive.get('', 'BULL', 'spec_skip')
        if result['penalty'] < skip_thresh:
            return True, f'HIGH_RISK penalty={result["penalty"]} (thresh={skip_thresh})'

        return False, ''

    def size_adjustment(self, symbol: str, macro: dict = None) -> float:
        """Position size multiplier based on context. 0.25 to 1.0.
        v17: tiers proportional to penalty (no hardcoded -0.5/-0.3).
        """
        result = self.score(symbol, macro)
        penalty = result['penalty']

        # v17: proportional sizing instead of hardcoded tiers
        if penalty < -0.7:
            return 0.25
        elif penalty < -0.5:
            return 0.25 + (penalty + 0.7) * 1.25  # -0.7→0.25, -0.5→0.5
        elif penalty < -0.3:
            return 0.5 + (penalty + 0.5) * 1.25   # -0.5→0.5, -0.3→0.75
        elif penalty < -0.1:
            return 0.75 + (penalty + 0.3) * 1.25   # -0.3→0.75, -0.1→1.0
        elif penalty < -0.1:
            return 0.75
        return 1.0
