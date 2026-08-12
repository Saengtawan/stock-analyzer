# orb_trader — context-first ORB trigger-confirm intraday brain

Clean rebuild started **2026-07-31**. Replaces the statistics-heavy `src/ai_trader/` v2
(frozen, not deleted — old brain crons PAUSED, memory archived at
`data/ai_trader_memory.archive_20260731.md`).

## What this is

An AI intraday paper-trader that reasons on **the present moment** (live raw data + web),
forms a thesis **pre-market**, then at ~09:33 **predicts and acts** on its read of each specific
situation — the live opening price action is one input it weighs, not a gate it waits on. It
**abandons backtest statistics and historical bucket-averages by design** — the only fitness is
its own **forward record**, which it writes after each close and reads the next day.

The bet is **PREDICT, not a statistical veto**: the brain acts on its contextual read of the
specific name (not the pool average), entering early/cheap rather than waiting for a mechanical
confirm. The honest cost — it is betting its read beats the crowd, so some predictions lose; the
**forward record**, not a break-rule, is what tells it when its read is real vs self-deception.

## The daily flow (3 present-time touchpoints)

```
① PRE-MARKET   ~09:05 ET   THESIS   read raw context (channels) + web/news → build a small
                                     watchlist. For each name: the story, the ORB TRIGGER level,
                                     and the INVALIDATION. Writes plans/YYYY-MM-DD.plan.json.
                                     NO buy yet.
② OPEN+bars    ~09:33 DECIDE (predict & act)   the brain PREDICTS each watchlist name's close from
                                     full context, weighing the live price action (1-min opening
                                     range / vwap reclaim / vol surge / still-extending) as ONE
                                     input — NOT a break-gate it must wait on. The opening range is
                                     built from the first 2-3 ONE-minute bars (09:30-09:32), so it
                                     completes at ~09:33 — not the old 09:40 five-minute read. It
                                     buys its predicted winners at the ~09:33 price (may enter before
                                     any break); skips names it reads as fades. Betting its read
                                     beats the crowd — forward record is the judge.
                                     Writes plans/YYYY-MM-DD.decision.json.
③ HOLD→CLOSE               exit per the plan (hold-EOD or trigger-based stop).
④ AFTER CLOSE  16:30 ET    LEARN    fill real outcomes, write ONE forward lesson to memory.md.
                                     Fitness = the forward outcome AND whether the confirm/
                                     abstain judgment was right (a correct no-trade is a win).
```

## Layout (one home, one concern per file)

```
orb_trader/
├── README.md          this map
├── memory.md          AI's clean forward memory: the 3 rails + forward record   [gitignored]
├── channels/
│   ├── numeric.py     digesting SQL channels — return a SHORT summary, never a raw dump
│   └── text.py        news + web text retrieval (embedding similarity — text only)
├── brain/
│   ├── thesis.md      prompt for pass ① (watchlist + triggers)
│   ├── confirm.md     prompt for pass ② (trigger check → execute)
│   └── learn.md       prompt for pass ④ (forward reflection)
├── run/
│   ├── premarket.sh   cron ①   ·   confirm.sh  cron ②   ·   learn.sh  cron ④
├── plans/             today's plan + decision json   [gitignored]
└── lib/
    ├── journal.py     forward-record DB
    └── execute.py     paper log (never places a real order)
```

## The rails (why token-light + why not just statistics)

- **Numeric data → digesting SQL channels, NOT vectors.** The channel does the reduction and
  returns a few computed fields per name (gap, rel-vol, vwap-dist, is-reclaiming, OR break),
  so the brain reads a short table, not thousands of rows. This is the token win.
- **Text data (news/web) → embedding similarity.** The one place vectors earn their keep:
  "is this catalyst fresh or already priced / stale, and what theme does it belong to."
- **Forward-only learning.** No backtest optimizer. `memory.md` holds 3 survival principles
  (rails) + a forward record the AI grows itself. See memory.md.

## Status

Skeleton laid 2026-07-31. Channel + brain logic: **to be designed by the AI itself** in this
structure. Nothing wired to cron until the brain is built and reviewed.
