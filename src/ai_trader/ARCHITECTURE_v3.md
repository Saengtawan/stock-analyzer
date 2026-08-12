# ai_trader v3 — the self-improving brain I actually run (design 2026-07-19)

This supersedes `ARCHITECTURE_V2.md`. v2 got the *spirit* right (AI reasons over
context, never a crude bucket rule) but was silent on the three things that actually
decide whether this works: **look-ahead quarantine, the recursive-overfit trap, and my
own documented behavioral bias.** v3 is built around those three, using the real modules
already in `src/ai_trader/` and the frozen findings in `DAY_MODEL_v2.md` +
`data/ai_trader_memory.md`.

Read this with the two evidence files open. Every design choice below traces to a line
in one of them. Nothing here is aspirational; it's the loop I operate tomorrow.

---

## 0. The premise I refuse to lie about

**Edge ≈ zero at scale.** 1,433 days say the only survivors are thin: an up>2 early-
momentum tilt (~+0.3–0.4%/yr over field, ~51% hit, tail-carried) and a year-dependent
oversold snapback. The reclaim thesis the whole v2 model was built on replicated to
+0.04%/yr — gone after cost. The published LLM-agent research says the same hard thing:
LLM advantages **deteriorate** under broad/long evaluation and don't beat the market
long-run; a system whose fitness is backtest return **recursively reinforces its own
overfitting** (adds leverage right before a crash); LLM agents are **poorly calibrated
to regimes**; look-ahead bias is pervasive.

So v3's job is **not** "beat the market." It is: **stay disciplined, abstain by default,
occasionally catch a genuinely foreseeable pre-open catalyst at small size, and never
blow up.** Every mechanism below serves that, not a Sharpe fantasy.

---

## 1. The daily loop, end-to-end (where LEARNING enters marked ★)

```
PRE-OPEN  08:00–09:25 ET
  ★ MEMORY READ: cat data/ai_trader_memory.md  (lessons + full forward record)
  context_v2.build(date)  → macro calendar, overnight, PRE-OPEN-KNOWABLE regime inputs
       inputs allowed: prior-day SPY tape return, VIX LEVEL at/near the open, prior-day
       VIX, "was D−1 a down/washout day", scheduled Fed/CPI/jobs times.
       inputs BANNED: same-day spy_regime, same-day vix_close, any close-stamped label.
  → set POSTURE (default = ABSTAIN-lean) + active GATES from the frozen priors (§3).
  → pre-open the only high-quality knowable catalyst is an EARNINGS gap-and-go; note it.

OPEN  09:35 ET  (the field resolves)
  context_v2.build(date, sim_minute=576)  → broad movers + g0935 + per-name news/story.
  3-pass judgment (§2): THESIS → SKEPTIC → DECIDER  → writes plans/decisions/<date>.json
       (Decision contract in decision.py; empty picks = abstain; no file = abstain).

EXECUTE  ~09:37 ET
  run_v2 execute → validate live prices, correlation-check primaries, log to journal,
  emit ≤2 primary picks + bench.  Entry = the price the human is actually told to buy.

INTRADAY
  Nothing by default. Exits are mechanical (hold_eod / trail + hard_stop in outcome_v2).
  OPTIONAL 10:00 observational note only — the day's real rotation usually breaks
  intraday, but the "reclaim/breadth building by 10:00" signal is UNPROVEN at scale
  (memory §5 ⚠). It may inform tomorrow's read; it NEVER resizes or adds a position today.

CLOSE  16:00 ET
  run_v2 outcome → outcome_v2.fill(date): realized return per pick, net of cost, vs FIELD.
  ★ REFLECTION WRITE: append to the forward record in data/ai_trader_memory.md:
       pick(s), archetype, the thesis, the skeptic's objection, decision, realized fwd,
       field fwd that day, and the one honest judgment line —
       "foreseeable catalyst caught" | "story I talked myself into" | "correct abstain"
       | "knife I stepped on" | "right process, unlucky tail".
  ★ Prune stale lessons so the file stays a brain, not a log.
```

**Fitness = forward outcome (pick vs field, net of cost) + judgment quality.** Process is
scored separately from the single-day result: a sound abstain on a green day is a WIN;
a lucky win on a story I shouldn't have traded is a process LOSS. One day is noise; the
record is the judge (memory: "trust it over any backtest, including my own").

---

## 2. Multiple agents — YES, exactly three, and here's the proof I need them

A single agent already ran (v2) and produced my single worst, best-documented failure:
**fixating on the loud macro headline (oil/war) and talking myself into a story that was
not the day's trade.** That is precisely the failure the multi-agent research
(TradingAgents / ContestTrade) addresses with an adversarial risk/skeptic role. So the
skeptic isn't decoration — it's the direct antidote to a bias I have on the record.

But the research *also* warns LLM advantages deteriorate and more agents ≠ more edge. So
I build the **minimum** adversarial structure, not an analyst/researcher/trader zoo (that
is theater the evidence explicitly discounts). Three roles, and they are **one model in
three passes** — cheap, no services:

- **THESIS** — per candidate, build the strongest bull case from context (the catalyst,
  why it's mispriced, which archetype).
- **SKEPTIC** — adversarial, prompted to *default to "trap"*: "the loud headline is
  usually NOT today's trade — is this oil-fixation? is this sympathy_junk moving only by
  association? is a VIX>28 knife live? am I conditioning on a close-stamped label? read
  the ACTION (up>2 count / reclaim count), not the story." It must try to kill each pick.
- **DECIDER** — weighs thesis vs skeptic, applies the frozen priors (§3) + memory + risk
  gates (§4), and emits the Decision or abstains. **Ties and unresolved skeptic
  objections resolve to ABSTAIN.**

One agent is insufficient (documented bias). Five agents is waste (evidence says the
extra roles don't add edge). Three is the load-bearing minimum.

---

## 3. Regime read — pre-open-knowable only; kills the oil-fixation & intraday blindspot

The regime read outputs **gates**, not a headline. It uses ONLY frozen, causal priors
from `DAY_MODEL_v2.md`, all pre-open-knowable:

| condition (pre-open / at-open knowable) | gate |
|---|---|
| VIX **at the open** > ~28 AND weak open | **KNIFE** → do not dip-buy the red pool; abstain/defensive (model §4) |
| D−1 crashed < −1% (best if VIX already >28) | snapback prior ACTIVE on the beaten pool — but small; year-dependent (§3, §6) |
| healthy tape, no knife | lean to the **up>2 pool**, harvest the tail across a few names, small (§6 ✅) |
| Fed/CPI/jobs on the calendar pre-print | reduce/abstain into the print |

**Oil-fixation guard (the SKEPTIC owns this):** a macro headline earns a trade ONLY when
it mechanically shows in *price* — crude actually gaps AND the names are up>2 at 09:35,
i.e. the action confirms. "Winners travel in packs; read the reclaim count, not the
headline" (memory). No confirming price action → the headline is noise → no trade.

**Intraday-catalyst blindspot (accepted, not fought):** the day's real rotation often
breaks intraday and is NOT pre-open-knowable. I do not pretend otherwise. Consequence:
the honest pre-open/at-open posture is frequently **abstain or small**. The one catalyst
that genuinely *is* pre-open-knowable is the earnings gap-and-go — so that, plus the
up>2 momentum tail and the clean post-washout snapback, are the only setups I reach for.
I don't need to trade every day to have a good record; I need to not trade the days I
can't see.

**Banned forever:** conditioning on `spy_regime` or same-day `vix_close`. They are
stamped at the close and co-move with the very forward return I'm predicting — the
"+0.8/−0.67 regime edge" was this artifact (model §2, §8). The SKEPTIC screens for it.

---

## 4. Risk — sizing, positions, abstain default, anti-overfit guards

- **Default posture = ABSTAIN.** Trade only when a candidate clears THESIS, survives the
  SKEPTIC, and fits a frozen prior. Abstaining is free and is never penalized in fitness.
- **Max 2 primary positions**, correlation-checked (run_v2 already warns + sizes-as-one
  when both primaries share a sector). Bench is tracked, not traded.
- **Sizing = small, fixed, equal.** The edge is a right-tail harvested across names, not a
  per-name money-maker (~51% hit) — so no concentrated bet. Risk per trade capped by the
  hard_stop (−4% default, per pick in the Decision contract).
- **Guards against the recursive-overfitting trap** (the research's #2 warning):
  1. **Fitness is forward outcomes + judgment, never backtest return.** Backtest cannot
     enter the fitness loop (§5).
  2. **Priors are FROZEN.** The system may not re-fit `DAY_MODEL_v2` numbers on its own
     live record. New priors require a *fresh, quarantined* study, reviewed by me, not an
     autonomous refit.
  3. **Position size is a constant with NO up-lever.** There is no code path that
     increases size after a winning streak. This removes, by construction, the exact
     "adds leverage right before a crash" failure — you can't pull a lever that doesn't
     exist.
  4. **Posture changes need ≥20–30 forward days AND a process reason**, never a single
     good/bad day and never a backtest tweak.
  5. **Everything is logged** — abstains, bench, and the field return — so audits run
     against the true baseline, not a cherry-picked one.

---

## 5. Backtest quarantine (one-time hypothesis generation, walled off)

`backtest.py` / `DAY_MODEL_v2.md` are **hypothesis generators, used once, to produce the
FROZEN priors in §3.** That is their only role. Hard wall:

- Backtest output → priors → frozen. Priors never update from the live record automatically.
- The **forward record** (data/ai_trader_memory.md) is the ONLY thing that adjusts my
  operating posture, and it adjusts it through *my judgment in reflection*, not an
  optimizer.
- No fitness function anywhere reads a backtest number. If I ever feel the urge to "re-run
  the backtest to see if the edge is still there and size up," that IS the overfit trap
  (memory: "backtests here are optimistically biased and overfit fast") — the answer is
  the forward record or nothing.

---

## 6. What this honestly delivers

**Not alpha. Discipline + rare real catches + no blowup.** Concretely, a good v3 forward
record looks like:

- A **high abstain rate** — most days I can't see the trade (intraday rotation), so I sit.
- On the days I do trade: **earnings gap-and-gos, up>2 momentum tails, clean post-washout
  snapbacks** — small, ≤2 names, tail-harvest sizing.
- **Zero knife catastrophes** — the VIX>28 gate keeps me out of dip-buying live fear.
- Net result over 20–30 forward days: **flat-to-slightly-positive vs the field, with the
  left tail cut off.** If the picks don't beat the field net of cost over that window, the
  correct response is **trade less / abstain more**, not add complexity or size.

That's the whole honest promise: I will be a *disciplined* agent that occasionally catches
a foreseeable catalyst and does not blow up — because the evidence says that, not
market-beating alpha, is what's actually on the table.

---

## 7. Build order (reuse what exists; three small additions)

1. `context_v2.py` — extend to emit the §3 gate block (VIX-at-open, D−1 tape, D−1 VIX,
   calendar) as PRE-OPEN-KNOWABLE fields; assert no close-stamped label leaks in.
2. `judge.py` *(new)* — the THESIS→SKEPTIC→DECIDER 3-pass over the brief; writes the
   `decision.py` Decision. Skeptic prompt hard-codes the oil-fixation + look-ahead +
   knife + sympathy_junk screens; unresolved objection → abstain.
3. `run_v2.py` — already the brief/execute/outcome spine; add the ★ reflection-write step
   after `outcome` (append forward record + prune) so learning is part of the loop, not
   a manual afterthought.
4. `outcome_v2.py` / `journal.py` — unchanged; they already realize vs field, net cost,
   and log everything including abstains.

Nothing new is fit to price history. The only thing that "learns" is the forward record I
read every morning and reflect into every night.
