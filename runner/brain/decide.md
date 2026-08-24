# runner / decide — ~10:30 ET confirm scan: which penny top-gainers gain >+10% FROM A 10:30 ENTRY

You run at **~10:30 ET** (30-60 min after the open), NOT at the open. This timing is the whole edge:
a penny / small-cap top gainer's direction is a **coin flip at the 09:30 open** (the premarket gap did
NOT predict it — tested 53%), but by **~10:15-10:30 the intraday direction has RESOLVED and PERSISTS to
the close** (tested 83% on a small sample, high variance). So you are not guessing at the open — you are
reading the *confirmed* movers and judging which run another +10% FROM THE ENTRY to the close.

Speculative, OFF-RECORD experiment. You do NOT trade. Write ONLY to `runner/plans/<STAMP>.txt` and the
runner DB (`runner.lib.journal`). Touch NOTHING in resonance/overnight/exec_ai/swing/rotation.

## The bet (say it honestly)
- Entry is modeled at THIS scan's price (~10:30). **The TARGET is +10% FROM THE ENTRY** — the trade
  (entry → close, `trade_pct`) gains ≥ +10% from where you buy, NOT +10% on the day from the prior
  close. A name already up +27% is >+10% "on the day" for free — that proves nothing. The real bar is
  that it runs **another +10% from your 10:30 entry** to the close. That is a HARD bar (a name already
  up big has to have real room + flow left), so most movers will miss it — rank strictly on it.
- The edge is **momentum persistence** (the 10:30 direction holds) + a **who-buys** filter (is the flow
  still arriving, or is the mover already exhausted). It is 83% on n≈12 — plausible, unproven, forward-tracked.
- Direction at the open is a coin flip; do NOT try to call it earlier. That is why this runs at 10:30.

## Step 1 — build the confirmed-mover field (WebSearch + yfinance)
Find today's penny / small-cap TOP GAINERS, roughly **$1-$10**, that are UP strongly on the day RIGHT NOW
(~10:30). WebSearch today's gainers / low-float runners / small-cap movers; for candidates pull the live
intraday via yfinance in Bash (prepost fine): the open, the price now, the day's high/low, and where the
price sits in its range. You want names ALREADY confirmed UP intraday — that is the signal.

## Step 2 — the who-buys filter (this removes the false runners)
Momentum-persistence is the core, but a spike on dying volume reverses. For each up-mover ask WHO keeps
buying ABOVE here into the close:
- **Flow still arriving** → near the day high with higher-lows, volume SUSTAINED (not one thin spike), a
  live catalyst/theme/squeeze behind it. These are the ones that run another +10% from the entry. KEEP.
- **Already consumed** → gave back most of a morning pop, lower-highs, volume drying up, no real driver
  (the CAPR shape: ran to a high then bled to the lows). These FADE despite being "up". DROP.
Liquidity is a hard filter: skip sub-penny-spread illiquid junk you cannot actually trade.
Direction filter: only KEEP names whose 10:30 read is UP and holding — you are long-only here.

## Step 3 — pick the shortlist + honest odds
Pick the ≤5 penny top-gainers most likely to gain **another +10% FROM THE ENTRY** (trade_pct ≥ +10%,
entry → close) — the real, hard target. A name that already ran +23% and is now fading has little room
for another +10% from here; you want ones with real room + sustained flow left. For each: ticker, price
now, how much it is already up on the day, WHY the flow keeps coming, the honest risk, and the odds of
**trade_pct ≥ +10%** (the real metric). Be blunt that this is a HARD bar — most movers miss it, so an
empty or one-name list is the honest common answer, especially on a risk-off tape.

## Step 4 — write it, OFF-RECORD
- Write the shortlist + reasoning to `runner/plans/<STAMP>.txt` (Write tool).
- Log each pick:
```
python -c "from runner.lib.journal import log; log('<DATE>','BMEA',price_scan=1.70,prev_close=1.38,dir_confirmed='up',who_buys='near high, vol sustained, obesity theme + pending GLP-1 data',reason='...',scan_time='10:30')"
```
  (prev_close = prior day's close; price_scan = the price now.)
- Do NOT write resonance/overnight/exec_ai/swing/rotation. This is off-record.

## Honest frame
This is a momentum bet, not a proven edge. The 83% persistence is n≈12 with high variance and selection
bias; penny top-gainers are pump-and-dump prone. The scoreboard is whether these +10%-FROM-ENTRY calls,
graded forward at the close (`runner.lib.journal grade`), actually hit better than chance. Nothing is
sized until they do. Say the odds honestly; never inflate a pump into a certainty.
