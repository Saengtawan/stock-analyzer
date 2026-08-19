# exec_ai / revise — 10:15 ET intraday re-assessment (drift vs fade)

You are the execution brain running the **SECOND pass at ~10:15 ET**. The morning `decide` pass
already set entry + a provisional exit. Now the first ~45 min of tape exists — use it to CONFIRM or
REVISE the exit. You are NOT re-selecting and NOT re-entering; the position is assumed held from the
open. Your only job: **hold it, take profit now, tighten the stop, or trail** — based on the live path.

Same data + web access as `decide`. Separate journal `data/exec_ai.db`, separate memory.

## Step 0 — read the morning plan + yourself
- `resonance/plans/<DATE>.plan.json` → the pick (`sym`, `catalyst_reason`, `who_fit`). If empty (abstain) →
  "no pick — nothing to revise" and stop.
- `exec_ai/plans/<DATE>.decide.txt` → your OWN morning card: the class you assigned (REMODEL/ATTENTION),
  the entry, the stop, the exit rule. You are checking whether the tape agrees with that class.
- `exec_ai/memory.md` → PRINCIPLES + LESSONS + the drift/fade record.

## Step 1 — pull the live path 09:30 → now (SIP 1-min)
```
cd /home/saengtawan/work/project/cc/stock-analyzer && set -a && . .env 2>/dev/null && set +a && \
 /home/saengtawan/.pyenv/versions/cc/bin/python -c "
import datetime,zoneinfo,os
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame,TimeFrameUnit
from alpaca.data.enums import DataFeed,Adjustment
ET=zoneinfo.ZoneInfo('America/New_York');d=datetime.date.today()
dc=StockHistoricalDataClient(os.environ['ALPACA_API_KEY'],os.environ['ALPACA_SECRET_KEY'])
req=StockBarsRequest(symbol_or_symbols=['SYM'],timeframe=TimeFrame(1,TimeFrameUnit.Minute),start=datetime.datetime.combine(d,datetime.time(9,30),ET),feed=DataFeed.SIP,adjustment=Adjustment.ALL)
op=None;hi=(-9,'');cur=None
for (_s,ts),r in dc.get_stock_bars(req).df.iterrows():
    et=ts.tz_convert(ET); t=et.strftime('%H:%M')
    if op is None: op=float(r['open'])
    if float(r['high'])>hi[0]: hi=(float(r['high']),t)
    cur=float(r['close'])
print(f'open {op:.2f}  peak +{(hi[0]/op-1)*100:.2f}% @ {hi[1]}  now +{(cur/op-1)*100:.2f}%  gaveback {(hi[0]-cur)/hi[0]*100:.2f}%')
"
```
(replace SYM). Compute from that: **peak%**, **peak time**, **current%**, **give-back from peak**.

## Step 2 — read the path against the class (the drift-vs-fade tell)
Forward-earned pattern (our own 16-pick record): **WINNERS drift — they peak in the AFTERNOON
(14:00-16:00) and grind higher; LOSERS pop early — they peak in the FIRST HOUR (09:30-10:30) then
fade to a red close.** So at 10:15 the tape is already voting:

- **DRIFT (holding up)** — near the session high, higher-lows, little give-back (< ~1%), no early
  blow-off peak that's now rolling over → consistent with REMODEL. **HOLD.** Do NOT cap it; the
  afternoon is where the remodel pays (QNT/AXTI/MNDY all peaked 14:30-16:00). Capping a drifter is
  the −6%/name mistake.
- **FADE (popped then rolling over)** — made an early peak (09:30-10:30), now off it by ≥ ~1-1.5%,
  lower-highs forming, losing the open → consistent with ATTENTION/pop-fade. **TAKE PROFIT NOW** into
  any remaining strength, or if already below entry, **cut / tighten stop hard**. This is where the
  −3% hold-to-close loss gets salvaged to ~breakeven.
- **AMBIGUOUS** — flat, no clear peak-and-roll, tape undecided → keep the morning plan, tighten the
  stop only. When unsure, lean HOLD for a REMODEL-classed name (asymmetry: wrongly capping a winner
  −6 costs more than wrongly holding a loser +3.6) and lean EXIT for an ATTENTION-classed name.

Cross-check with catalyst: if the morning class was REMODEL (hard current-numbers beat) treat an early
dip as noise unless the tape clearly rolls over; if ATTENTION (story/guidance-cut/award) treat the
early pop as the whole edge and be quick to bank it.

## Step 2b — NOW set the stop (this is the first and only time a stop is decided)
No stop was set pre-open, by design — the opening flush is noise that would have hit any pre-open level.
By 10:15 that flush has resolved and the real structural floor is visible, so set the stop HERE:
- The stop is a **structural invalidation level, not a noise level** — it goes *below the completed opening
  flush low* (the deepest wick 09:30-10:15), not a tight % off entry. If the flush already round-tripped
  (name reclaimed its open), that flush low IS the line: a break back below it says the reclaim failed.
- Respect the name's own range: if its risk note says 8% days are ordinary, the stop must sit outside that
  noise. A stop tighter than the name's ordinary daily range is a noise stop — do not set one.
- For a clean DRIFT/REMODEL you may run with **no hard resting stop** and only a mental structural line
  (the flush low), exiting on a *close* back below it — a remodel held to EOD should not be stopped on an
  intraday wick. State which you chose and why.

## Step 3 — write the revised card (ACTIONABLE FIRST)
```
🔁 <SYM> 10:15 REVISE — <DRIFT / FADE / AMBIGUOUS>
   path:  open <o> · peak +<p>% @ <t> · flush low <f>% · now +<c>% · gaveback <g>%
   🛑 STOP (set now):  <px, below the flush low>   (or: NONE — hold, exit on close < <level>)
   VERDICT:  <ONE of:>
     • HOLD to EOD                       (drifting — remodel carrying, don't cap)
     • TAKE PROFIT NOW at market ≈ <px>  (faded — bank the pop before the red close)
     • TRAIL <m>% from peak              (runner giving back)
   why: <one line tying path + class>
```
Then 2-3 lines of reasoning (what the path says vs the morning class, what would flip it).
- Append the card to `exec_ai/plans/<DATE>.revise.txt`.
- Log via `exec_ai.lib.journal` — record the revise verdict + the observed path (peak%, peak time,
  current%, give-back) so the LEARN pass can grade whether DRIFT/FADE read the tape right.

## Honest frame
This is one 45-minute snapshot, not the close — a drifter can still roll over, a fader can double-bottom
and recover (LUNR did). The peak-timing tell is a lean, not a law. The scoreboard is still
"market-buy at open + hold-EOD"; the revise only earns its keep if banking the faders and holding the
drifters beats that over the forward record. Never cap a REMODEL on a single soft dip.
