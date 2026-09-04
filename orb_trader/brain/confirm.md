# brain / confirm.md — PASS ② DECIDE / PREDICT → EXECUTE

**You fire ~09:33 ET, once the first three 1-min bars are in. Output: your decision + paper
orders.** `DATE` = today (America/New_York).

This is the pass the whole framework exists for. Pre-market you built a story. Now you DECIDE.

**The shift (own it):** this used to be a CONFIRM-GATE — you had to wait for a mechanical price
break to "confirm" before you were allowed to buy. That was distrust of your own judgment wearing
a discipline costume. The entire reason this system is AI-driven is that you read THIS specific
name's context — not a pool average, not a break-rule. So Pass ② is now a **DECIDE / PREDICT**
pass: you decide which watchlist names to buy using your full contextual read. The live price
action is **one input you weigh, not a gate you wait on**. If your read says the setup is real,
you may buy at the ~09:33 price (`cur`) *without* an OR-high break — earlier is cheaper, and you
are predicting, not confirming.

The honest tradeoff: you are now betting your read beats the crowd. Sometimes it won't. The
**forward record is the judge** — if your predictions lose, you'll see it in the next day's memory
and you adjust. Abstaining is still fully honest: if your read says a name will fade, skip it. But
"no break yet" is no longer an automatic drop, and "the story is still good" is not enough on its
own either (RAIL 1). Never buy a name that wasn't on the plan — abstain, don't invent.

## 0. Load the plan and memory
- `cat orb_trader/plans/DATE.plan.json` — this morning's watchlist, each name's story, trigger
  level, invalidation, exit. Missing file or empty watchlist → nothing to do, write an empty
  decision and stop.
- Keep the 3 rails from `orb_trader/memory.md` in mind (loaded this morning).

## 1. Timing — read the open honestly (1-min opening range)
The opening range is built from the first **three ONE-minute bars** (09:30, 09:31, 09:32), so it
completes at **~09:33 ET** (the 09:32 bar closes at 09:33). Use the ET minute-from-midnight as
`MINUTE`, and decide at **MINUTE >= 573 (09:33)**; earlier than 573 the OR is still forming
(`or_bars` < 3 → provisional, wait a bar or note it). (09:33 = 573, 09:36 = 576, 09:38 = 578.)
1-min bars come from Alpaca (feed = iex today, sip past). The confirm output carries `or_bars`
and `feed`. Point-in-time holds: `or_high`/`or_low` never change if you re-check later — no
backward leak into the 09:33 range.

## 2. Read each watchlist name's live price action
For each name in the plan:
```
python -m orb_trader.channels.numeric confirm DATE SYM MINUTE
```
Returns: `or_high, or_low, cur, cur_vs_or_high_pct, vol_surge, vwap_reclaim, still_extending,
or_bars, feed`. If the output is an `error` (Alpaca 1-min unavailable for a past date, or no RTH
bars yet), you can't read that name's tape — skip it for this run, don't guess.

**Weigh this snapshot as evidence, not as a gate.** A held break above `or_high` with volume, a
VWAP reclaim, or a name still extending are all *bullish confirmation* of your thesis — lean in.
But a name sitting just under `or_high`, or one you can already buy cheap before it breaks, is a
DECISION for you to make on your read of why the move happens — not an automatic pass. The old
`trigger_fired` FIRES-or-not logic is gone; you interpret.

Still respect **invalidation**: if a name is doing the thing the plan said would kill it (below
`or_low`, lost VWAP, driver rolled over), that's real evidence against your thesis — usually a
skip. Invalidation is the one place the tape overrides a good story.

Optional context for a macro/beta play: `python -m orb_trader.channels.numeric drivers DATE
MINUTE` (is the driver still extending?) and `... breadth DATE MINUTE` (is the tape with you?).
Don't fight a red tape into a long unless the name's own read is loud.

## 3. RAIL 1 — your own consideration, not a checkbox
A public catalyst is already in the price by 09:33. So ask, per name: **does my read see something
the crowd hasn't priced yet** — a fresh continuation, a second-order consequence, a leg the tape
hasn't caught? If yes, that's your edge and a reason to buy. If the edge is already spent (the
catalyst is old, the pop already happened, everyone's in), that's a reason to skip — and it's YOUR
call, decided by your read, not a rule. Record that call as `rail1_check`.

## 4. Decide — buy vs skip
- **Your read predicts this name closes >2% → buy.** Entry = `cur` from the snapshot (a
  market-style fill at your decision minute; you are not waiting for or chasing the plan's limit).
- **Your read predicts a fade, or RAIL 1 says the edge is spent, or the name is invalidated →
  skip.** Log it plainly. Zero buys is a fine, disciplined outcome — report it as such.

## 5. Execute (paper) and write the decision
Log every BUY through the real lib — `paper_buy` writes the journal row (NEVER an Alpaca order)
and hands back the dict you drop into the decision json:
```python
from orb_trader.lib.execute import paper_buy
d = paper_buy(DATE, sym, entry_px=cur, entry_et="09:33", size="1 unit (fixed/equal)",
              exit_plan="hold_eod", trigger_fired="predict: fresh continuation, tape green",
              mode="live")
```
Use `mode="replay"` for a dev re-run so it never counts as a live trade. For a SKIP, log it too
(so the record shows what you passed on):
```python
from orb_trader.lib import journal
journal.log_decision(DATE, sym, watchlisted=True, confirmed=False, trigger_fired=None, mode="live")
```
Then write `plans/DATE.decision.json` from those dicts. Size is **small, fixed, equal** across
BUY names (respect the account rails: 1% risk, ≤3 positions). Exit = the plan's exit (`hold_eod`
default, or the `trigger_stop` level). Journal DB is `data/orb_trader.db`; inspect any time with
`python -m orb_trader.lib.journal rows DATE [mode]`.

```json
{
  "date": "DATE",
  "checked_et": "09:33",
  "decisions": [
    {
      "sym": "XYZ",
      "decision": "buy",
      "entry_px": 0,
      "predicted_reason": "I predict >2% close: driver still extending + this name lagged the move at open, fresh continuation the crowd hasn't chased yet",
      "price_read": { "or_high": 0, "or_low": 0, "cur": 0, "cur_vs_or_high_pct": 0,
                      "vol_surge": true, "vwap_reclaim": false, "still_extending": true },
      "rail1_check": "catalyst is 2h old but the second-order read (supplier follow-through) is not priced — edge not spent",
      "size": "1 unit (fixed/equal)",
      "exit_plan": "hold_eod"
    },
    {
      "sym": "ABC",
      "decision": "skip",
      "entry_px": null,
      "predicted_reason": "I predict a fade: pop already happened pre-open, lost VWAP by 09:33",
      "price_read": { "or_high": 0, "or_low": 0, "cur": 0, "cur_vs_or_high_pct": -0.4,
                      "vol_surge": false, "vwap_reclaim": false, "still_extending": false },
      "rail1_check": "edge spent — the catalyst was fully priced at the open"
    }
  ]
}
```
Print a one-line summary per name (BUY/SKIP + the prediction). That's the pass. Position
management until the close is per the exit plan; you don't re-decide the entry.

**MANDATORY FINAL STEP — the run FAILS without it.** Your task is NOT complete until the Write
tool has actually created `plans/DATE.decision.json` on disk. Printing the summary, the table, or
the JSON as text is NOT sufficient — if the file does not exist, the run has failed (the record
of what you decided is lost and the learn pass has nothing to read). Even an all-SKIP / zero-buy
day MUST be written as a valid JSON file (a `decisions` array with the SKIP rows, or an empty
array + a `notes` reason if the plan was empty). Writing the file is your LAST action. Do not end
your turn before it exists.
