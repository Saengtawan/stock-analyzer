# rotation / decide — predict TOMORROW's live themes + regime (post-close pass)

You run POST-CLOSE (~16:10 ET). Today's tape is complete. Your job: read the cross-asset picture +
the forward catalyst calendar + your own accumulated linkage memory, and **predict what is likely to
be LIVE and which way it leans for the next session, this week, and the regime** — so the trading
systems (resonance/nowscan/overnight) get a step of lead time instead of reacting a day late.

This is a STANDALONE, OFF-RECORD forecasting experiment. You do NOT place trades and you do NOT write
to resonance/overnight/exec_ai/swing. Your only outputs are `rotation/plans/<DATE>.json`, the DB
(via `rotation.lib.journal`), and (on the learn pass) `rotation/memory.md`.

## The one honest frame (read before anything)
Direction is hard and regimes shift — the whole reason the trading systems bet only on readable edges.
So predict with CALIBRATION, not false confidence:
- **A theme being LIVE is more predictable than its DIRECTION.** "AI/semis will be in play around NVDA
  Wednesday" is a forecastable statement; "semis close green Wednesday" is much weaker. Separate the two
  — give a theme a `lean`, but weight your confidence toward the *live/attention* call, not the P&L call.
- **Never harden a linkage into a rule.** You may observe "Treasury liquidity → BTC → crypto-equity" and
  weigh it, but the forward record is the only judge of whether that chain actually leads. A linkage
  that fit the past can break tomorrow (the trading systems have been killed by exactly this).
- **Predict every day, even when unsure** — a hedge/abstain teaches the record nothing. State low
  confidence honestly instead of refusing to call. The point is to ACCUMULATE graded calls fast.
- Everything is a PREDICTION about the future — never state a catalyst outcome you cannot see yet
  (an earnings result, an FDA decision); state odds, and VERIFY event dates/times before leaning on them.

## Step 1 — read yourself first
Read `rotation/memory.md` in full: the LINKAGE MEMORY (which leads have actually held forward, which
broke) and the LESSONS. Let your graded record condition today's call. If a linkage is 0-for-many
forward, stop leaning on it; if one keeps holding, weight it.

## Step 2 — read the cross-asset snapshot (mechanical, already stored)
```
python -m rotation.data.snapshot <DATE>      # build today's snapshot first if the runner hasn't
```
Then read it (token-lean): `python -c "import json;from rotation.lib.journal import snapshot_asof;print(json.dumps(snapshot_asof('<DATE>'),indent=0))"`.
Each row = one asset with close + ret_1d/5d/20d + rvol, grouped by class (index/vol/rate/fx/commodity/
crypto/sector/theme). Read it as EVIDENCE of what moved and what's rotating — not a ranking. Look for:
- **regime tells:** VIX level+direction, DXY, 10y/2y (rates), SPY/QQQ/IWM leadership (risk-on vs defensive).
- **rotation tells:** which sector/theme ETFs led vs lagged today and over 5d/20d (XLK/SMH/IGV = tech-AI,
  ITA = defense, XBI/IBB = biotech, TAN = solar, KRE = banks, XRT = retail, XLE = energy).
- **cross-asset leads:** e.g. BTC/ETH + crypto-equity together, oil → XLE, yields → KRE/XLRE/homebuilders,
  gold → miners. Note what led what TODAY as a candidate lead-lag — to be confirmed by the record, not asserted.

## Step 3 — build the FORWARD catalyst calendar (WebSearch)
The edge over pure reaction is that themes have DATED forward catalysts you can see coming. Search for
what lands in the next 1-2 weeks that would light up a theme:
- **Earnings** that anchor a theme (e.g. a mega-cap semis print → AI/semis; a retailer → XRT).
- **FDA / PDUFA / trial readouts / medical conferences** (ASCO/JPM Healthcare) → biotech/vaccine/health.
- **Fed / econ data** (CPI, jobs, FOMC, Jackson Hole) → rates/risk regime.
- **Launches / contracts / index adds / court rulings / policy votes** → space, defense, crypto, etc.
VERIFY each date/time (confirm it lands when you think, and has NOT already happened — the ROST/Jackson
Hole contamination lesson: searches leak prior-year coverage). A dated catalyst is a *scheduled* reason
a theme goes live; note it with its date.

## Step 4 — predict, for EACH horizon (calibrated, with a falsifiable)
Make calls for all three horizons. For each theme/call state: `theme`, `lean`, `names` (the tickers it
would express through), `confidence` (0-1, honest), and the ONE **falsifiable** that would prove it wrong.
- **tomorrow** — which themes are most likely LIVE next session + lean + names. Weight live-ness over
  direction. A theme running today with a fresh driver (not consumed) tends to persist; a theme with a
  dated catalyst tomorrow is live by the clock; a theme extended/consumed is a fade candidate.
- **week** — which dated catalysts this week will light which themes, and any building rotation.
- **regime** — one line: risk-on / risk-off / rotation / chop, from VIX+rates+breadth+leadership.

Guardrails you owe the record:
- **theme-live is NOT theme-up.** A sector can be live and SELL every print (retail did: ROST/BJ beat,
  ROST −2%). Say when a theme is live-but-you-can't-call-direction.
- **names are candidates for the trading systems to judge, not buys** — you predict WHERE the flow is;
  resonance/nowscan apply the who-buys test per name.
- do NOT let any single linkage become a hardcoded rule — weigh it, cite the record, keep the falsifiable.

## Step 5 — WRITE (mandatory)
1. Write `rotation/plans/<DATE>.json` (Write tool):
```json
{
  "date": "<DATE>",
  "regime": "one line: risk-on/off/rotation/chop + why (VIX/rates/breadth/leadership)",
  "tomorrow": [
    {"theme":"AI/semis","lean":"live/up","names":"NVDA,SMH,AMD","confidence":0.6,
     "falsifiable":"if SMH closes red tomorrow with NVDA green, the readthrough lead is wrong",
     "reason":"..."}
  ],
  "week": [ {"theme":"...","lean":"...","names":"...","confidence":0.5,"falsifiable":"...","reason":"..."} ],
  "linkages_watching": ["Treasury buyback -> BTC -> crypto-equity (unconfirmed)", "..."]
}
```
2. Log each call to the DB:
```
python -c "from rotation.lib.journal import log_prediction as p; p('<DATE>','tomorrow','AI/semis','live/up','NVDA,SMH',0.6,'if SMH red w/ NVDA green the lead is wrong','...')"
```
   (one call per prediction row; horizon ∈ tomorrow|week|regime).
3. Print a short receipt: regime line + the top 2-3 themes with lean+confidence.

Do NOT write anything outside `rotation/`, `data/rotation.db`. This is off-record — its calls do not
enter any trading journal until the forward record proves the forecaster earns its keep.
