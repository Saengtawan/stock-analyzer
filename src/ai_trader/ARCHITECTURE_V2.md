# ai_trader v2 — AI-first pipeline (design 2026-07-14)

## The one principle
**Crude price rules are what lose. The AI reasons over CONTEXT.**
Price setups (gap-down, oversold, breakout…) are *priors the AI weighs*, never gates
that pre-crush the field. The AI is the brain at every judgment step; code only
gathers data, structures the reasoning, executes, and tracks.

Nothing here is backtestable in the crude bucket way — it's AI-in-loop, forward-validated.
That's the deal: we stop reducing the decision to something a dumb rule could compute.

## What went wrong in v1 (and why v2 differs)
- v1 fed the AI a **pre-filtered dump** (H12-A gainers) then filtered AGAIN by price
  bands → the AI never saw the real field. v2 starts from a **broad universe**.
- v1's "AI layers" were secretly **crude thresholds** (abstain if macro_sent<0). v2's
  decisions are **genuine judgment** over headlines/stories, not aggregate scores.
- v1 hardcoded `regime_ok = SPY red`. v2 lets the AI read **why** the tape is where it
  is and judge the regime in context.

## Pipeline (6 stages; AI owns 3-5)
```
1. UNIVERSE      broad morning movers (gainers+losers+gappers), NOT a pre-filtered dump.
                 code: pull from Alpaca movers / screener at ~09:35 ET.
2. CONTEXT       per name: price action + its news/story (DB + live web-search) + sector;
                 day: macro narrative + regime read. code assembles, does not judge.
        │
3. CLASSIFY   ◄─ AI reads each mover IN CONTEXT and assigns an archetype dynamically:
   (AI)          gap_down_reversal | oversold_bounce | news_catalyst | breakout |
                 sympathy_junk | ... — by JUDGMENT (why it's moving), not price thresholds.
        │
4. SELECT     ◄─ AI, regime-aware: which archetypes are favorable TODAY? pick the genuine
   (AI)          ones with reasoning, or abstain. Priors inform, context decides.
        │
5. EXIT PLAN  ◄─ AI assigns each pick an exit approach matched to its archetype + read
   (AI)          (reversal→hold-to-recovery+hard stop; momentum→trail; etc.).
        │
6. EXECUTE       emit picks + entry (~09:37), log plan+reasoning+picks to journal,
                 fill outcomes after close. code only.
```

## Archetypes = priors, not filters
Each archetype is a *pattern with a historical tendency* the AI weighs:
- **gap_down_reversal** — gapped down on idiosyncratic bad news, healthy context, buyers
  step in. (Our one price-validated prior: strong on weak tape, ~breakeven on strong.)
- **oversold_bounce** — beaten multi-day, capitulation flush, snapback.
- **news_catalyst** — moving on a real, fresh, mispriced catalyst.
- **breakout** — new high on real demand (historically weak in this universe → skeptical).
- **sympathy_junk** — moving only by association / illiquid froth → veto.
The AI can create/split archetypes as it sees patterns. The set is not frozen.

## Guardrails (the ONLY hard rules — safety, not alpha)
- liquidity floor (skip illiquid froth that gaps ±15%),
- max positions / max risk per trade,
- abstain is always allowed and never penalized (forcing trades loses).

## Validation
- Forward only. Journal logs the AI's reasoning per pick → we audit whether contextual
  judgment beats the mechanical baseline AND random, over ~15-30 real trading days.
- Success = live picks with reasoning that hold up, not a backtest number.

## Build order
1. `universe.py` — broad morning movers feed (replace dump dependency).
2. `context_brief.py` — already drafted; extend to the broad universe + per-name web-search hooks.
3. `classify_ai.py` / `select_ai.py` — the AI reasoning interface (verdict files a Claude
   session fills: archetype + pick + exit + reasoning).
4. reuse `scanner`/`run_open`/`journal`/`outcome` for execution + tracking.
```
```
