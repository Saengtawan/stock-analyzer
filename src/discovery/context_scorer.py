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
    """Score stocks using Knowledge Graph context."""

    def __init__(self, knowledge_graph):
        self._kg = knowledge_graph

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

        # 2. Macro sensitivity mismatch
        if macro:
            crude = macro.get('crude_close') or 75
            vix = macro.get('vix_close') or 20

            # Crude: penalize stocks that DROP when crude is HIGH
            # threshold -0.10 (only ~5 stocks: TLT, CLX, KMB etc.)
            crude_sens = ctx['flags'].get('CRUDE_SENSITIVE', {})
            if crude_sens and crude > 85:
                corr = crude_sens.get('score', 0)
                if corr < -0.10:
                    penalty = round(corr * 2, 2)  # scale: corr=-0.15 → -0.30
                    total_penalty += penalty
                    penalties.append(f'CRUDE_HIGH+NEG_CORR({corr:+.2f}) {penalty:+.2f}')

            # VIX: penalize only HIGHLY sensitive stocks (corr < -0.50)
            # Before fix: threshold -0.15 triggered on 96% of stocks
            # After fix: threshold -0.50 triggers on ~10% (QQQ, SOXX, GS, etc.)
            vix_sens = ctx['flags'].get('VIX_SENSITIVE', {})
            if vix_sens and vix > 25:
                corr = vix_sens.get('score', 0)
                if corr < -0.50:  # only extreme VIX sensitivity
                    penalty = round((corr + 0.50) * 0.5, 2)  # scale: -0.70 → -0.10
                    total_penalty += penalty
                    penalties.append(f'VIX_HIGH+EXTREME_SENS({corr:+.2f}) {penalty:+.2f}')

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

        # Skip if very speculative (penalty < -0.7)
        if result['penalty'] < -0.7:
            return True, f'HIGH_RISK penalty={result["penalty"]}'

        return False, ''

    def size_adjustment(self, symbol: str, macro: dict = None) -> float:
        """Position size multiplier based on context. 0.25 to 1.0."""
        result = self.score(symbol, macro)
        penalty = result['penalty']

        if penalty < -0.5:
            return 0.25  # quarter size
        elif penalty < -0.3:
            return 0.5   # half size
        elif penalty < -0.1:
            return 0.75
        return 1.0
