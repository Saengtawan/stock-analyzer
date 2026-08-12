# brain / learn.md — PASS ④ AFTER-CLOSE FORWARD REFLECTION

**You fire 16:30 ET, after the close. Output: real outcomes filled + ONE honest line in your
forward record.** `DATE` = today (America/New_York). This is the only place you actually
learn. Your forward record is your entire memory of what works — keep it honest or it poisons
every future morning.

## 0. Load today's decision and memory
- `cat orb_trader/plans/DATE.decision.json` and `orb_trader/plans/DATE.plan.json`.
- `cat orb_trader/memory.md` — you will append to the FORWARD RECORD (and, rarely, LESSONS).
  You do **NOT** rewrite the 3 rails. Ever.

## 1. Fill the real outcomes (09:35 → close)
Read the realized close straight from the bars, then stamp it onto each journal row. For each
name that mattered today (confirmed picks AND the dropped ones you want to grade), get
entry-vs-close:
```
sqlite3 data/trade_history.db \
 "SELECT symbol, substr(time_et,1,5) tm, close FROM intraday_bars_5m
  WHERE date='DATE' AND symbol IN ('SYM1','SYM2') AND substr(time_et,1,5) IN ('09:35','15:55')
  ORDER BY symbol, tm"
```
Entry reference = the confirm-pass entry_px (or the 09:35 close for a name you dropped, to
grade the counterfactual). Result % = (close / entry − 1) × 100. Write each one back through
the real lib (this is the row the next morning reads):
```python
from orb_trader.lib import journal
journal.fill_outcome(DATE, sym, close_px=close, result_pct=result, judgment="win (fresh continuation)",
                     mode="live")   # mode='replay' for a dev re-run
```
`fill_outcome` returns 0 if the name was never logged in pass ② — if so, log it first with
`journal.log_decision(...)`. Inspect the day any time: `python -m orb_trader.lib.journal rows DATE [mode]`.

## 2. Judge honestly — fitness is BOTH outcome and judgment
Grade each name against what the framework actually claims:
- **Confirmed pick that closed > +2% → WIN.** (The trigger earned it.)
- **Confirmed pick that closed flat/red → LOSS.** Was the trigger real, or did you force a
  thin poke past the OR high? Note which.
- **Correct no-trade → WIN.** You dropped it, the thesis never confirmed, and the name faded
  or chopped. The discipline paid. Say so plainly — do not treat every no-trade as a regret.
- **Real MISS → the one that stings.** You DROPPED a name that then ran hard on a trigger you
  *should have seen fire* at the open. This is the only "missed chance" worth the name. A name
  that ran with no trigger you could have acted on is NOT a miss — that was luck, not signal.
- Also sanity-check RAIL 1: did any winner win because *fresh* buying continued (good), or did
  you get paid for pre-open news you shouldn't have (lucky — flag it, don't bank the lesson).

## 3. Append ONE line to the FORWARD RECORD
Add exactly one line under `## FORWARD RECORD` in `orb_trader/memory.md`, in the file's format:
```
DATE | watchlist:A,B,C → confirmed:A | trigger:or_high_break+vol_surge | A +2.8% to close | JUDGMENT: win (fresh continuation); B,C correct no-trades (faded)
```
Keep it one line, dense, true. Record the no-trades too — the record of what you *correctly
skipped* is as much your edge as the wins.

## 4. LESSONS — only on a repeated forward pattern (never one day)
Do not write a lesson from a single day. A lesson is earned only when the FORWARD RECORD shows
the **same thing ≥3 times** (e.g. "thin single-poke or_high breaks with no vol_surge fade by
close" across multiple days). Only then append one crisp line under `## LESSONS`, tied to the
dates that support it.
- **Prune**, don't just add: if a standing lesson is contradicted by newer forward days,
  strike it. The record is the authority, not the lesson.
- A lesson is a *forward-earned* refinement of how you read triggers/context — never a
  statistical rule or a bucket-average (that's the whole thing you abandoned), and never an
  edit to the 3 rails.

Then stop. Tomorrow's thesis pass reads exactly what you wrote here.
