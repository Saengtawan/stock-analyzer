"""
Context Scorer — penalizes risky stocks using Knowledge Graph.
Part of Discovery v11.0 Contextual Intelligence.

PENALTY system: reduce score for risky stocks, don't boost good ones.
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
        -0.3 per SPECULATIVE flag
        -0.2 for macro sensitivity mismatch
        -0.1 for supply chain risk
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
            crude = macro.get('crude_close', 75)
            vix = macro.get('vix_close', 20)

            crude_sens = ctx['flags'].get('CRUDE_SENSITIVE', {})
            if crude_sens and crude > 90:
                corr = crude_sens.get('score', 0)
                if corr < -0.15:  # stock negatively correlated with crude + crude high
                    total_penalty -= 0.2
                    penalties.append(f'CRUDE_HIGH+NEG_CORR({corr:+.2f}) -0.2')

            vix_sens = ctx['flags'].get('VIX_SENSITIVE', {})
            if vix_sens and vix > 25:
                corr = vix_sens.get('score', 0)
                if corr < -0.15:  # stock drops when VIX high
                    total_penalty -= 0.2
                    penalties.append(f'VIX_HIGH+NEG_CORR({corr:+.2f}) -0.2')

        # 3. Supply chain risk (simplified)
        if ctx['upstream']:
            # Check if any major supplier is in a risky sector
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
