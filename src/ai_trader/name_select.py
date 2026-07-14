"""Per-name AI selection — the judgment layer mechanical rank can't do.

Why this exists: within a day's gap-down cell, 55% of outcome variance is
*which name* (not which day), and picking the best 2 vs random is +3.18 vs +1.14
per pick — a ~2% prize. Yet 6 mechanical rankings (gain/own-sector/news/depth/
steady) all fail to capture it. That's the textbook case for judgment: real
dispersion, real prize, no formula. So at ~09:36 the AI READS the cell (company
knowledge + live web-search of each name's catalyst) and picks / vetoes.

Not backtestable here (per-name news is ~5% coverage; in-session judging = hindsight)
-> validated FORWARD: does AI selection beat random toward oracle?

Contract: plans/name_verdicts/<date>.json
  {"picks": ["UNH","CNC"],           # optional: trade exactly these, in order
   "skip":  ["USAR"],                # optional: veto (junk / killer catalyst)
   "reason": {"USAR": "$32M illiquid froth", "UNH": "real guidance-cut reversal"}}
Empty / missing file -> no per-name override (rule layer uses its own ranking).
"""
from __future__ import annotations
import json, os

VERDICT_DIR = "plans/name_verdicts"


def load_verdicts(date, vdir=VERDICT_DIR) -> dict | None:
    path = os.path.join(vdir, f"{date}.json")
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path))
    except Exception:
        return None


def apply_verdicts(candidates, verdicts) -> list:
    """Filter/reorder candidates by the AI's per-name verdicts.
    - skip: drop those symbols
    - picks: keep only those, in the given order (AI's explicit selection)
    Returns candidates unchanged if verdicts is None/empty."""
    if not verdicts:
        return candidates
    skip = {s.upper() for s in verdicts.get("skip", [])}
    cands = [c for c in candidates if c.sym.upper() not in skip]
    picks = [s.upper() for s in verdicts.get("picks", [])]
    if picks:
        by = {c.sym.upper(): c for c in cands}
        cands = [by[s] for s in picks if s in by]
    return cands


def surface(candidates, classify, ctx) -> str:
    """Render the eligible gap-down cell for a Claude session to judge at ~09:36."""
    elig = classify.eligible(candidates, ctx)
    L = [f"=== NAME-SELECT {ctx.date} | {classify.name} | spy_morning {ctx.spy_morning:+.2f}% ===",
         f"eligible candidates: {len(elig)}   (read each name's catalyst; pick genuine",
         f"idiosyncratic-bad-news reversals in a healthy context; veto illiquid froth)"]
    if not elig:
        L.append("  (none — regime_ok false or no candidate matched)")
    for c in elig:
        L.append(f"  {c.sym:6} gain{c.gain:+.1f}% gap{c.gap:+.1f}% ${c.dollar_vol/1e6:.0f}M {c.sector}")
    L += ["", f"-> write picks/skip to plans/name_verdicts/{ctx.date}.json"]
    return "\n".join(L)
