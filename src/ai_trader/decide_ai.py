"""Automated AI judgment step — closes the AI-in-loop gap.

Builds the v2 context brief, hands it to Claude, and writes plans/decisions/<date>.json.
This is what makes the pipeline run WITHOUT a human: cron can call it between v2brief
and v2execute. Requires ANTHROPIC_API_KEY (+ `pip install anthropic`).

Two ways to run the AI judgment:
  * this script  — headless, scheduled (needs API key). Fully automated.
  * a Claude Code session — read `v2brief`, web-search names, write the decision by hand.
    Richer (live web-search) but needs a session in the loop.

Fail-safe: any error -> writes an ABSTAIN decision (never trades blind).
"""
from __future__ import annotations
import argparse, json, os, re
from .context_v2 import build as build_brief
from .decision import Decision, DecisionPick, ARCHETYPES, EXIT_STYLES

MODEL = "claude-opus-4-8"

SYSTEM = f"""You are the trader in an AI-first intraday system. You receive a morning
context brief: a broad field of liquid movers (up and down), each stock's news/story,
and the macro narrative. Judge like a discretionary trader IN CONTEXT — do not apply
crude price rules.

Assign each stock you like an archetype and pick only genuine setups. The names below are
EXAMPLES / priors — if a setup doesn't fit them, COIN YOUR OWN archetype name that
describes the pattern (e.g. "sympathy-overreaction laggard", "post-halt continuation").
The only reserved label is "sympathy_junk" = a hard veto (never buy). Priors (not gates):
- gap_down_reversal: gapped down on idiosyncratic bad news in a healthy context -> buyers
  step in. Strongest when the tape is weak (fighting a red tape = real relative strength).
- oversold_bounce: beaten multi-day, capitulation flush, snapback.
- news_catalyst: moving on a real, fresh, mispriced catalyst.
- breakout: new high on real demand (be skeptical — weak in this universe historically).
- sympathy_junk: moving only by association / illiquid froth -> never pick.

CRITICAL — this is an INTRADAY system (buy ~09:37, flat by 16:00). The buy reason MUST be
an intraday move that will happen TODAY and HASN'T happened yet — UNRESOLVED edge (mismatch
not yet reclaimed, laggard not yet caught up, reversal not yet bounced). A multi-day /
fundamental catalyst by itself (cheap valuation, re-rate over days) is a SWING thesis, NOT
intraday. If the day's reaction is already SPENT (ran far from the open then flattening/
fading, e.g. a low-vol mega-cap +2% rolling over like JNJ), SKIP it. BUT a fresh EARNINGS
GAP-AND-GO ("earnings_gap_and_go") IS a valid buy: gapped up on a real same-day catalyst
and STILL ACCELERATING early from the open (from-open positive and RISING, not yet
extended) — the continuation is happening NOW. The line vs "spent" is momentum + how far it
has run: still building early = buy; already ran a lot and flattening = skip.

Abstaining is always fine and never penalized; forcing trades loses. If the tape weakness
is a real risk-off (war / rate shock / hot inflation), prefer to abstain.

Return ONLY a JSON object, no prose:
{{"regime": "<one line>", "picks": [{{"sym": "...", "archetype": "...", "reason": "...",
"exit_style": "hold_eod|trail", "hard_stop": -4.0, "trail_pct": null}}],
"abstain_reason": null}}
Up to 5 picks, RANKED best-first; do NOT pad — include only genuine setups (if only 2 are
clean, return 2). The top 2 are shown/traded, the rest are bench. trail needs a trail_pct."""


def _parse(text, date) -> Decision:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in model output")
    raw = json.loads(m.group(0))
    picks = []
    for p in raw.get("picks", [])[:5]:
        if p.get("archetype") == "sympathy_junk":
            continue
        picks.append(DecisionPick(
            sym=p["sym"], archetype=p.get("archetype", "other"), reason=p.get("reason", ""),
            exit_style=p.get("exit_style", "hold_eod"),
            hard_stop=float(p.get("hard_stop", -4.0)),
            trail_pct=(float(p["trail_pct"]) if p.get("trail_pct") else None)))
    return Decision(date=date, regime=raw.get("regime", ""), picks=picks,
                    abstain_reason=(raw.get("abstain_reason") if not picks else None))


def decide(date, top=100, save=True) -> Decision:
    try:
        import anthropic
    except ImportError:
        raise SystemExit("need `pip install anthropic` in the issara env for headless AI decisions")
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        for l in open(".env"):
            if l.strip().startswith("ANTHROPIC_API_KEY="):
                key = l.strip().split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise SystemExit("set ANTHROPIC_API_KEY (env or .env) for headless AI decisions")

    brief = build_brief(date, top=top)
    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(model=MODEL, max_tokens=1500, system=SYSTEM,
                                     messages=[{"role": "user", "content": brief}])
        dec = _parse(msg.content[0].text, date)
    except Exception as e:
        dec = Decision.abstain(date, f"AI decision failed: {e}")
    if save:
        dec.save()
    return dec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--top", type=int, default=100)
    a = ap.parse_args()
    dec = decide(a.date, top=a.top)
    print(dec.to_json())


if __name__ == "__main__":
    main()
