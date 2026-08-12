# resonance — coiled-spring intraday system (pre-open, token-lean)

Fresh build started **2026-08-01**, on the **`cc`** pyenv (production env: pandas 2.1.3, ta-lib,
statsmodels, alpaca all present). Successor to `orb_trader/`. Forgets old rule/statistics baggage.

## The core bet (why this exists)

Intraday **direction** ≈ coin flip and confirming a break does NOT verify the *close* — so we do
not chase direction and we do not wait for a confirm. Instead:

> **Volatility is predictable even when direction is not.** Find the stocks whose spring is
> **coiled** (unusually quiet vs their own normal = energy stored, a move is *due*) **and primed**
> (a catalyst/positioning reason to release *today*). Screen these **before the open**. An AI reads
> the compact feature digest + full context, weights it itself, predicts which ~3 release UP and
> **close** green, buys at the open, and **holds to EOD**. No confirm.

- COILED gives **magnitude** (vol clusters + mean-reverts — the one robust, predictable thing).
- CATALYST gives **direction + durability** (a real fundamental surprise drifts to the close;
  a technical poke fades). We accept we'll be wrong on direction sometimes — nothing verifies the
  close; the forward record is the judge.

## Token discipline (hard requirement)

Mechanical code + libraries do **all** the heavy compute (features, screen) over already-stored
raw data — **zero AI tokens**. The AI is used for **judgment only**, ~2 short calls/day, each
reading a **compact pre-computed digest** (not raw bars). AI weights the features; it never
computes them.

| work | who | tokens |
|---|---|---|
| refresh + compute coil/prime features for the universe | 🔧 lib (ta-lib/pandas/statsmodels) | 0 |
| screen → high-recall candidate pool | 🔧 lib | 0 |
| read pool digest → weight → pick ~3 | 🧠 AI (1 call) | small |
| fill outcomes | 🔧 lib | 0 |
| write one forward lesson | 🧠 AI (1 call) | small |

## Layout

```
resonance/
├── README.md
├── requirements.txt   pinned extras (arch optional; rest already in cc)
├── data/access.py     🔧 read-only channels over the DB tables we use (below)
├── features/
│   ├── coil.py        🔧 compression: ATR%ile, BB bandwidth, NR7, realized-vol (ta-lib/pandas)
│   ├── prime.py       🔧 release triggers: gap, premkt-vol wake, news, earnings, analyst,
│   │                     options_flow, put/call, short_interest, float
│   └── build.py       🔧 run the universe → compact feature table → cache/
├── screen/pool.py     🔧 high-recall candidate pool (unusual on ANY axis; no weighted judgment)
├── brain/
│   ├── decide.md      🧠 read pool digest + context → weight → pick ~3 (coiled+catalyst) → plan
│   └── learn.md       🧠 forward reflection → memory.md
├── lib/
│   ├── store.py       feature/pool cache I/O
│   ├── journal.py     forward-record DB (data/resonance.db)
│   └── execute.py     paper only (never a real order)
├── run/
│   ├── premarket.sh   🔧 build features+pool  →  🧠 decide (1 call)   [pre-open]
│   └── learn.sh       🔧 fill outcomes        →  🧠 learn (1 call)    [after close]
├── cache/  plans/     [gitignored]
└── memory.md          forward record + principles [gitignored]
```

## Data channels (the context the AI can read — DB tables we sweep)

daily OHLC (compute each name's *normal*) · premarket 5-min bars (04:00+, wake/gap) ·
stock_fundamentals (float, beta, mcap) · institutional_holdings + major_holders_summary (who
holds) · short_interest + daily_short_volume (squeeze fuel) · options_flow + cboe_put_call
(positioning) · news_events + analyst_ratings + earnings_calendar (catalyst) ·
stock_relationships + stock_clusters + sector_movers (rotation/sympathy) · macro_snapshots +
market_breadth (tape/regime). News gets a semantic index later; everything else is SQL digests.

## Env

**`cc`** — `~/.pyenv/versions/cc/bin/python`. See memory `reference_python_env_cc`.

## Status

Skeleton laid 2026-08-01. Mechanical feature/screen layer + brain: **to be built by the AI** in
this structure, stage by stage, on cc. Nothing wired to cron until built + verified.
