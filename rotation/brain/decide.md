# rotation / decide — predict TOMORROW's live themes + regime (post-close pass)

You run POST-CLOSE (~16:10 ET). Today's tape is complete. Your job: read the cross-asset picture +
the forward catalyst calendar + your own accumulated linkage memory, and **predict what is likely to
be LIVE and which way it leans for the next session, this week, and the regime** — so the trading
systems (resonance/overnight) get a step of lead time instead of reacting a day late.

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
Read `rotation/memory.md` (narrative lessons) AND the structured registry from the DB:
```
python -c "from rotation.lib.journal import linkage_registry,regime_history; import json; print('LINKAGES',json.dumps(linkage_registry())); print('REGIMES',json.dumps(regime_history()))"
```
The LINKAGE REGISTRY is your growing brain — each lead has a forward tally + status
(unconfirmed/holding/broken). **Weight a linkage by its status:** `holding` = earned, lean on it;
`unconfirmed` = watch, do not bet weight on it yet; `broken` = stop using it. A linkage 0-for-many is
broken — drop it. The regime history tells you what regime preceded what (learn the transitions:
"profit-surge day → next-day fade", etc.).

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
would express through), **`kind`**, **`priced`**, `confidence` (0-1, honest), and the ONE
**falsifiable** that would prove it wrong.

**Tag every call `kind` — this is the difference between a real lean and a coin flip:**
- **`mechanism`** — a KNOWN structural driver is in motion whose transmission is documented, so the
  DIRECTION is leanable, not a coin flip (e.g. Treasury liquidity injection → hard assets/gold/BTC up +
  dollar down; rate cuts → rate-sensitives up; a fresh tariff → the named winner up / loser down). Here
  you MAY lean direction.
- **`event`** — the driver is an OUTCOME not yet known (an earnings print, an FDA decision, a Fed
  hawk/dove call). Direction is ~a coin flip — call the theme LIVE and the timing, but do NOT call the
  sign.
- **`regime`** — the environment read (risk-on/off/rotation/chop).
Also tag **`priced`**: even a true mechanism pays only if the move is still AHEAD (`unspent`), not
already in the price (`priced`). A mechanism everyone already traded (BTC already +20% on the liquidity
news) is `priced` — the mechanism is real but the entry is late; say so. And a mechanism-trend catches
a name only when that name is ALSO unspent within it (the MARA/HOOD lesson: crypto-liquidity was a live
mechanism, and the catch was the name that had NOT run yet — HOOD ret_prev1d −0.70 — not the ones
already up). So a mechanism call is strongest when `kind=mechanism` AND `priced=unspent`.
- **tomorrow** — which themes are most likely LIVE next session + lean + names. Weight live-ness over
  direction. A theme running today with a fresh driver (not consumed) tends to persist; a theme with a
  dated catalyst tomorrow is live by the clock; a theme extended/consumed is a fade candidate.
- **week** — which dated catalysts this week will light which themes, and any building rotation.
- **regime** — one line: risk-on / risk-off / rotation / chop, from VIX+rates+breadth+leadership.

Guardrails you owe the record:
- **theme-live is NOT theme-up.** A sector can be live and SELL every print (retail did: ROST/BJ beat,
  ROST −2%). Say when a theme is live-but-you-can't-call-direction.
- **names are candidates for the trading systems to judge, not buys** — you predict WHERE the flow is;
  resonance/overnight apply the who-buys test per name.
- do NOT let any single linkage become a hardcoded rule — weigh it, cite the record, keep the falsifiable.

## Step 5 — WRITE (mandatory)
1. Write `rotation/plans/<DATE>.json` (Write tool):
```json
{
  "date": "<DATE>",
  "regime": "one line: risk-on/off/rotation/chop + why (VIX/rates/breadth/leadership)",
  "tomorrow": [
    {"theme":"gold/metals","lean":"up","kind":"mechanism","priced":"unspent","names":"GLD,GDX,NEM",
     "confidence":0.6,"falsifiable":"if GDX closes red with the dollar down, the liquidity->metals lead is wrong",
     "reason":"..."}
  ],
  "week": [ {"theme":"AI/semis around NVDA","lean":"live","kind":"event","priced":null,"names":"NVDA,SMH",
             "confidence":0.85,"falsifiable":"...","reason":"live by the clock; sign NOT called"} ],
  "linkages_watching": [ {"id":"liquidity->metals","kind":"mechanism","note":"Treasury buyback -> soft DXY -> gold/BTC"} ]
}
```
2. Log to the DB:
   - each prediction row (horizon ∈ tomorrow|week|regime):
```
python -c "from rotation.lib.journal import log_prediction as p; p('<DATE>','tomorrow','gold/metals','up','GLD,GDX','mechanism','unspent',0.6,'if GDX red w/ DXY down the lead is wrong','...')"
```
   - the regime tag:
```
python -c "from rotation.lib.journal import log_regime as r; r('<DATE>','rotation/bond-stress',None,'VIX complacent but week red; rates the driver')"
```
   - each linkage you are watching (registers it as unconfirmed so the learn pass can start scoring it forward):
```
python -c "from rotation.lib.journal import upsert_linkage as u; u('liquidity->metals',trigger='Treasury buyback/soft DXY',target='GLD,GDX,BTC',kind='mechanism',note='the apparent chain of the week — do not over-fit')"
```
3. Print a short receipt: regime line + the top 2-3 themes with lean+kind+confidence.

Do NOT write anything outside `rotation/`, `data/rotation.db`. This is off-record — its calls do not
enter any trading journal until the forward record proves the forecaster earns its keep.
