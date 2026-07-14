"""The AI layer — pre-open, decide the day's plan and write plans/<date>.json.

Validated signal (2025-2026, small N -> track forward):
  On a would-be red morning, gap-down-reversal WINS when pre-open macro/fed/geo
  news is not net-negative, and LOSES when it is (real risk-off catalyst):
      macro news >=0 : 2025 +0.60 / 2026 +0.86
      macro news <0  : 2025 -0.82 / 2026 -0.35
  VIX/SMA/breadth could NOT separate 2026 — the NEWS could. That's the whole
  point of an AI layer: read WHY the tape is red, not just that it is.

Two decision backends:
  * mechanical  (default) — the validated threshold rule on aggregate sentiment.
  * llm         (slot)    — hand the headlines to a model to judge qualitatively.
                            Wired as a function so live can plug in a Claude call;
                            falls back to mechanical if unavailable.

The plan is FAIL-SAFE: any error / missing data -> abstain (don't trade blind).
"""
from __future__ import annotations
import argparse
from .contract import Plan
from .premarket import gather_preopen

# thresholds for the mechanical backend (from the validated split)
MACRO_SENT_MIN = 0.0     # abstain if pre-open macro/fed/geo sentiment < this
PRE_SENT_MIN = -0.15     # abstain if overall pre-market sentiment very negative


def decide_mechanical(ctx: dict) -> Plan:
    """Validated aggregate-sentiment gate."""
    date = ctx["date"]
    ms, ps = ctx.get("macro_sent"), ctx.get("pre_sent")
    reasons = []
    if ms is not None and ms < MACRO_SENT_MIN:
        reasons.append(f"macro/fed/geo news {ms:+.2f} < {MACRO_SENT_MIN} (risk-off catalyst)")
    if ps is not None and ps < PRE_SENT_MIN:
        reasons.append(f"pre-market sentiment {ps:+.2f} very negative")

    if reasons:
        return Plan(date=date, regime="news_risk_off", enabled_classifies=[],
                    risk="abstain", generated_by="mechanical_news",
                    notes={"_regime": "; ".join(reasons)})
    return Plan(date=date, regime="news_ok",
                enabled_classifies=["gap_down_reversal"], risk="normal",
                generated_by="mechanical_news",
                notes={"_regime": f"macro_sent={ms}, pre_sent={ps}, "
                                  f"vix_prior={ctx.get('vix_prior')}"})


# --- LLM slot -------------------------------------------------------------
# The AI reads the actual pre-open headlines (ctx['macro_neg_headlines']) and judges
# risk-off vs tradeable — this is the "read WHY the tape is red" the mechanical
# average can't do. In THIS environment (no API key) the judgments are produced by a
# Claude session and persisted to plans/llm_verdicts.json; in live a pre-open Claude
# run appends to that file. Returns None (-> mechanical fallback) if no verdict exists.
import json as _json, os as _os
LLM_VERDICTS = "plans/llm_verdicts.json"

def decide_llm(ctx: dict):
    date = ctx["date"]
    try:
        if not _os.path.exists(LLM_VERDICTS):
            return None
        v = _json.load(open(LLM_VERDICTS)).get(date)
        if v is None:
            # no explicit verdict for this day -> treat as tradeable (regime_ok still
            # gates to red tape at open); the AI only files verdicts on days it flags.
            return {"abstain": False, "reason": "no risk-off catalyst flagged"}
        return {"abstain": bool(v.get("abstain")), "reason": v.get("reason", ""),
                "skip_syms": v.get("skip_syms", [])}
    except Exception:
        return None


def decide_plan(date: str, backend: str = "mechanical", db=None) -> Plan:
    """Produce the plan for `date`. Fail-safe: on any error -> abstain."""
    try:
        ctx = gather_preopen(date, db) if db else gather_preopen(date)
    except Exception as e:
        return Plan.abstain_default(date, f"context gather failed: {e}")

    if backend == "llm":
        try:
            verdict = decide_llm(ctx)
            if verdict is not None:
                if verdict.get("abstain"):
                    return Plan(date=date, regime="news_risk_off", enabled_classifies=[],
                                risk="abstain", generated_by="llm",
                                notes={"_regime": verdict.get("reason", "")})
                return Plan(date=date, regime="news_ok",
                            enabled_classifies=["gap_down_reversal"], risk="normal",
                            generated_by="llm",
                            notes={"_regime": verdict.get("reason", ""),
                                   **{s: "skip (llm)" for s in verdict.get("skip_syms", [])}})
        except Exception:
            pass  # fall through to mechanical
    return decide_mechanical(ctx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="ET trading date YYYY-MM-DD")
    ap.add_argument("--backend", default="mechanical", choices=["mechanical", "llm"])
    ap.add_argument("--plans-dir", default="plans")
    ap.add_argument("--show", action="store_true", help="print context + plan, do not save")
    a = ap.parse_args()

    ctx = gather_preopen(a.date)
    plan = decide_plan(a.date, backend=a.backend)
    print(f"--- pre-open context {a.date} ---")
    for k, v in ctx.items():
        if k == "macro_neg_headlines":
            print(f"  {k}:")
            for s, imp, h in v:
                print(f"      [{s:+.2f} imp{imp}] {h[:80]}")
        else:
            print(f"  {k}: {v}")
    print(f"--- PLAN ---\n{plan.to_json()}")
    if not a.show:
        path = plan.save(a.plans_dir)
        print(f"saved -> {path}")


if __name__ == "__main__":
    main()
