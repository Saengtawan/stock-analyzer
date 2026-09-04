# ai_trader — AI + classify trading system (v0, started 2026-07-14)

A NEW system, separate from `riser` / `ml_filter`. Built fresh after we proved
(from raw stats, no memory) that **no single static formula wins every year** —
markets are regime-dependent, so the intelligence must ADAPT to context, not
freeze a rule.

## Core idea: AI sets the config, rules execute it

```
PRE-OPEN (08:00-09:25 ET)          OPEN (09:31 scan -> 09:34-36 trade)
─────────────────────────          ───────────────────────────────────
AI reads context that a            Rule layer reads plan.json:
formula CAN'T:                       - runs ONLY the classifies AI enabled
 - overnight futures, Asia/EU        - each classify = deterministic
 - macro calendar (Fed/CPI/jobs)       filter + rank + exit (backtestable)
 - geopolitics / crisis              - respects risk posture (abstain/reduced)
 - premarket movers + WHY            - picks trade(s), routes to per-classify exit
 - VIX, recent regime
        │
        ▼  writes
   plans/<date>.json  ──────────►  consumed at open
```

### Why this beats a static formula (and avoids our repeated failure)
- **AI layer is NOT fit to price history** — it reasons over fresh daily context.
  So it can't suffer the train/serve skew that killed 5 prior "improvements."
- **Rule layer is simple + validated** — deterministic, backtestable, no live drift.
- **Regime changes -> AI swaps the config** -> we never need the mythical
  "one formula that wins every year" (proven not to exist).

## The contract (spine)
`plan.json` is the ONLY channel between AI and rules. See `contract.py`.
```json
{
  "date": "2026-07-14",
  "regime": "risk_off_trend",
  "enabled_classifies": ["gap_down_reversal"],
  "risk": "normal",              // normal | reduced | abstain
  "max_positions": 1,
  "notes": {"NVDA": "sympathy pump, no real catalyst -> skip"},
  "generated_by": "stub"         // stub | mechanical | claude
}
```

## Classify library — honest status
We only add a classify when it has BOTH a mechanism AND validated numbers.
NO padding to reach "10 types."

| # | classify | mechanism | status |
|---|----------|-----------|--------|
| 1 | gap_down_reversal | stock gapped down on own news but bounced GREEN = real relative strength, gets bought | ✅ built |
| 2 | momentum_continuation | (tbd) | ⛔ not built — needs per-regime validation |
| 3+ | breakout / oversold / vwap / ... | — | ⛔ add only when validated |

## Layout
```
src/ai_trader/
  contract.py            Plan + Candidate + Context dataclasses, load/save/validate
  classifies/
    base.py              Classify ABC: applies() / rank_key() / exit()
    gap_down_reversal.py classify #1
  scanner.py             decide(candidates, plan, ctx, classifies) -> picks
  backtest.py            deterministic backtest of the RULE layer over history
  premarket_ai.py        pre-open: gather context -> produce plan.json (AI slot)
plans/<date>.json        daily plans
```

## Daily operation (forward tracking) — `scripts/ai_trader_run.sh`
```
pre-open ~09:00 ET   ai_trader_run.sh brief    # prints headlines; a Claude session
                                               # reads + appends risk-off verdicts to
                                               # plans/llm_verdicts.json (else files nothing)
pre-open ~09:15 ET   ai_trader_run.sh plan     # writes plans/<date>.json (backend=llm)
at-open  ~09:36 ET   ai_trader_run.sh names    # surface gap-down cell; a Claude session
                                               # reads each name's catalyst (knowledge+web)
                                               # -> plans/name_verdicts/<date>.json (picks/skip)
at-open  ~09:37 ET   ai_trader_run.sh open     # decide pick from live dump, log journal
post-close ~16:10 ET ai_trader_run.sh outcome  # fill realized outcomes (Alpaca SIP)
any time             ai_trader_run.sh report   # journal + running expectancy
```
Journal: `data/ai_trader_journal.db` (one row/day: plan, pick, outcome).
Candidate source: `data/riser_dumps/<date>/min_0936.jsonl` (shared morning scan).

### Operational dependencies (honest)
- **news freshness** — the AI layer needs `news_events` current to the morning.
  If ingestion lags, the brief is empty → default = tradeable (regime_ok still
  gates to red tape). Keep the news cron alive for the AI layer to add value.
- **morning dump** — `open` needs the 09:36 scan dump to exist for the day.

## Backtest evidence so far (2025-2026, top-1/day, net of 0.3% cost)
| gate | 2025 | 2026 (the year that failed) | worst year | overall/pick |
|------|------|-----------------------------|-----------|--------------|
| always (no gate)      | +1.53 | -1.71 (WR27) | -1.71 | +0.29 |
| news (avg sentiment)  | +1.75 | -2.05 (WR25) | -2.05 | +1.06 |
| **llm (Claude reads headlines)** | +1.32 | **-0.34 (WR50)** | **-0.34** | +1.05 |
Reading headline CONTENT (war / rate-hike / inflation = abstain) beats averaging
sentiment scores, specifically by making the worst year survivable. N is small
(2026 = 4 trades) → this is directional; forward tracking is the real test.

## Two AI layers (both judgment, neither fit to price)
1. **Day gate** (`premarket_ai`, pre-open) — read macro/fed/geo headlines; abstain on
   real risk-off (war/rate-shock/inflation). Validated: turns worst year -1.71 -> -0.34.
2. **Name select** (`name_select`, ~09:36) — within the gap-down cell, judge WHICH
   names are genuine idiosyncratic-bad-news reversals vs illiquid froth, using company
   knowledge + live web-search of each catalyst. Rationale: 55% of cell-outcome variance
   is *which name*, and oracle top-2 = +3.18 vs random +1.14 (~2% prize), yet 6 mechanical
   rankings (gain/own-sector/news/depth/steady) all fail to capture it -> judgment's job.
   NOT backtestable (per-name news ~5%; in-session judging = hindsight) -> forward only.

## Validation posture
- **Rule layer**: deterministic backtest (`backtest.py`) — must show positive
  expectancy with a SURVIVABLE worst year (not "green every year").
- **AI layer**: novel, can't be backtested on price alone -> track FORWARD live.
- Judge by expectancy + risk-adjusted + survivable tail, NOT "positive every year."
