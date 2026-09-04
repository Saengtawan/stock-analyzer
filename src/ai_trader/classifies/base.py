"""Classify ABC — each archetype owns its filter, ranking, AND exit.

Per the design: a classify is NOT just a filter+rank. It carries its own exit
rule too ("exit ตาม classify นั้นๆ"), because different setups fade differently.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from ..contract import Candidate, Context


@dataclass
class PositionState:
    """Live state of an open trade, fed to Classify.exit() each poll."""
    minutes_held: int
    cur_pnl: float       # % from entry
    peak_pnl: float      # max % from entry seen so far
    spy_dd: float = 0.0  # SPY drawdown from its intraday peak (market context)


class Classify(ABC):
    #: unique name used in plan.enabled_classifies
    name: str = "base"
    #: one-line mechanism, for logs/plans
    mechanism: str = ""

    @abstractmethod
    def applies(self, c: Candidate, ctx: Context) -> bool:
        """Is this candidate an instance of this archetype right now?"""

    @abstractmethod
    def rank_key(self, c: Candidate, ctx: Context) -> float:
        """Higher = pick first among applicable candidates."""

    @abstractmethod
    def exit(self, st: PositionState) -> str:
        """Return 'EXIT' or 'HOLD' given the live position state."""

    def regime_ok(self, ctx: Context) -> bool:
        """Day/market regime gate evaluated AT OPEN (uses at-open ctx, e.g.
        SPY-red at 09:36). The pre-open AI plan decides whether this classify
        is *enabled* at all; regime_ok is the at-open condition the rule layer
        checks because the data (intraday SPY) isn't known pre-open.
        Default: always ok."""
        return True

    def eligible(self, candidates, ctx, skip=frozenset()):
        """Applicable candidates, best-ranked first, minus AI skip list.
        Returns [] if the at-open regime gate fails."""
        if not self.regime_ok(ctx):
            return []
        elig = [c for c in candidates
                if c.sym.upper() not in skip and self.applies(c, ctx)]
        elig.sort(key=lambda c: self.rank_key(c, ctx), reverse=True)
        return elig
