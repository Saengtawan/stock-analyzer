"""Morning brief — the pre-open context a Claude session reads to file its verdict.

Run this pre-open; a Claude session (or the operator) reads the headlines and, if
there's a real risk-off catalyst (war / rate-shock / inflation / crisis), appends a
verdict to plans/llm_verdicts.json:

    "<date>": {"abstain": true, "reason": "..."}

If nothing risk-off, file nothing (default = tradeable; regime_ok gates to red tape).
Then `premarket_ai --date <date> --backend llm` writes plans/<date>.json.
"""
from __future__ import annotations
import argparse
from .premarket import gather_preopen


def brief(date: str) -> str:
    ctx = gather_preopen(date)
    L = [f"=== PRE-OPEN BRIEF {date} ===",
         f"news items (pre/overnight): {ctx['n_news']}",
         f"macro/fed/geo avg sentiment: {ctx['macro_sent']}  (n={ctx['n_macro']})",
         f"overall pre-market sentiment: {ctx['pre_sent']}",
         f"prior VIX: {ctx['vix_prior']}   term: {ctx['vix_term_prior']}   "
         f"regime: {ctx['spy_regime_prior']}   yield-spread: {ctx['yield_spread_prior']}",
         "",
         "TOP MACRO/FED/GEO HEADLINES (read the CONTENT, not the score):"]
    if ctx["macro_neg_headlines"]:
        for s, imp, h in ctx["macro_neg_headlines"]:
            L.append(f"  [{s:+.2f} imp{imp}] {h}")
    else:
        L.append("  (none flagged negative)")
    L += ["",
          "DECISION: is today a real RISK-OFF day (war / rate-hike shock / hot inflation /",
          "crisis / broad market-wide catalyst)? If YES -> append abstain verdict to",
          "plans/llm_verdicts.json. If just company noise / mixed / no macro threat -> file nothing."]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    print(brief(ap.parse_args().date))


if __name__ == "__main__":
    main()
