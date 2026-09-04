"""Rule layer — the at-open decision.

Reads the AI's plan + the day's candidates/context, runs ONLY the enabled
classifies, and returns the trade picks. Pure and deterministic: given the same
plan + candidates + context it always returns the same picks (backtestable).
"""
from __future__ import annotations
from dataclasses import dataclass
from .contract import Plan, Candidate, Context
from .classifies.base import Classify


@dataclass
class Pick:
    classify: str
    candidate: Candidate
    size_mult: float     # from plan risk posture (1.0 / 0.5)


# central registry — add a classify here once it's built + validated
def default_registry() -> dict:
    from .classifies.gap_down_reversal import GapDownReversal
    return {c.name: c for c in (GapDownReversal(),)}


def decide(candidates, plan: Plan, ctx: Context, registry: dict | None = None):
    """Return a list of Pick, respecting the plan. Empty list = abstain."""
    if plan.risk == "abstain" or plan.max_positions <= 0:
        return []
    registry = registry or default_registry()
    skip = plan.skip_syms()
    size = plan.size_mult()

    picks: list[Pick] = []
    used = set()
    # iterate classifies in the order the AI listed them (priority)
    for name in plan.enabled_classifies:
        cl: Classify | None = registry.get(name)
        if cl is None:
            continue
        # eligible() returns [] if the at-open regime gate (regime_ok) fails.
        # Take best-ranked candidates up to the remaining position budget
        # (max_positions>1 = diversify within the cell, spreads idiosyncratic risk).
        for cand in cl.eligible(candidates, ctx, skip=skip):
            if cand.sym in used:
                continue
            picks.append(Pick(classify=name, candidate=cand, size_mult=size))
            used.add(cand.sym)
            if len(picks) >= plan.max_positions:
                break
        if len(picks) >= plan.max_positions:
            break
    return picks[:plan.max_positions]
