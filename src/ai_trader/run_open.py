"""At-open runner — load plan, decide the pick from live candidates, log to journal.

Run ~09:36 ET. Emits the pick (or abstain) and records it for forward A/B vs backtest.
Fail-safe: missing plan -> abstain_default (no trade).
"""
from __future__ import annotations
import argparse, datetime
from .contract import Plan
from .premarket_ai import decide_plan
from .live_candidates import from_dump
from .scanner import decide, default_registry
from .name_select import load_verdicts, apply_verdicts, surface
from . import journal


def run(date, backend="llm", plans_dir="plans", save_plan=True, log=True):
    # 1) plan: prefer a saved plan.json; else generate now (AI layer)
    try:
        plan = Plan.load(date, plans_dir)
    except Exception:
        plan = decide_plan(date, backend=backend)
        if save_plan:
            plan.save(plans_dir)

    # 2) live candidates + context from the morning dump
    cands, ctx = from_dump(date)

    # 2b) per-name AI selection (if a Claude session filed verdicts for today)
    nv = load_verdicts(date)
    if nv:
        cands = apply_verdicts(cands, nv)

    # 3) rule layer decides
    picks = decide(cands, plan, ctx)
    pick = picks[0] if picks else None

    ts = datetime.datetime.now().isoformat(timespec="seconds")
    if log:
        journal.log_day(date, plan, pick, ctx, ts)

    # 4) report
    print(f"=== ai_trader open {date} ===")
    print(f"plan: regime={plan.regime} risk={plan.risk} enabled={plan.enabled_classifies} "
          f"by={plan.generated_by}")
    if plan.notes.get("_regime"):
        print(f"      reason: {plan.notes['_regime']}")
    print(f"candidates={len(cands)}  spy_morning={ctx.spy_morning:+.2f}%  vix={ctx.vix}")
    if pick:
        c = pick.candidate
        print(f"PICK [{pick.classify}]: {c.sym} @ {c.price}  gain {c.gain:+.2f}%  gap {c.gap:+.2f}%  "
              f"size x{pick.size_mult}")
    else:
        why = "abstain (plan)" if plan.risk == "abstain" else "no candidate matched an enabled classify"
        print(f"NO TRADE — {why}")
    return plan, pick


def surface_cell(date, backend="llm", plans_dir="plans"):
    """Print the eligible gap-down cell for a Claude session to judge (~09:36)."""
    try:
        plan = Plan.load(date, plans_dir)
    except Exception:
        plan = decide_plan(date, backend=backend)
    cands, ctx = from_dump(date)
    reg = default_registry()
    if plan.risk == "abstain" or not plan.enabled_classifies:
        print(f"=== NAME-SELECT {date} ===\nplan abstains ({plan.regime}) — nothing to judge")
        return
    for name in plan.enabled_classifies:
        cl = reg.get(name)
        if cl:
            print(surface(cands, cl, ctx))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--backend", default="llm", choices=["mechanical", "llm"])
    ap.add_argument("--surface", action="store_true", help="print the cell for AI to judge, then exit")
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    if a.surface:
        surface_cell(a.date, backend=a.backend)
        return
    run(a.date, backend=a.backend, log=not a.no_log)


if __name__ == "__main__":
    main()
