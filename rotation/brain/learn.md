# rotation / learn — grade yesterday's forecast, update the linkage memory

You run POST-CLOSE, right before today's decide pass. Today's tape is complete, so the calls made on
the PRIOR session ("tomorrow" horizon) can now be graded against what actually happened. Your job:
score them honestly, and update `rotation/memory.md` with what the forward record teaches about which
linkages/leads actually hold and which broke.

OFF-RECORD, isolated: read/write only `data/rotation.db` and `rotation/memory.md`. Touch NOTHING in
resonance/overnight/exec_ai/swing.

## Step 1 — pull the ungraded calls
```
python -m rotation.lib.journal grade      # lists ungraded predictions
```
For each ungraded "tomorrow" call whose target session has now closed, grade it. (Week/regime calls
grade when their window resolves.)

## Step 2 — grade each against today's snapshot
Read today's cross-asset snapshot (`snapshot_asof('<TODAY>')`) — the assets/sector/theme ETFs and the
named tickers. For each prediction:
- **Did the theme go LIVE?** (its ETF/names moved with real range/volume, not inert) — the primary test.
- **Did the LEAN hit?** (up/down/risk-on-off correct) — the secondary test; be honest that direction is
  the harder call.
- **Did the falsifiable FIRE?** If the pre-registered test triggered, say so plainly.
Grade `correct` on the call as stated (if the call was "live/up" and it was live but closed down, that
is a HALF — record it honestly in `outcome`, mark correct by whichever the call actually claimed).
```
python -c "from rotation.lib.journal import grade_prediction as g; g('<CALL_DATE>','tomorrow','AI/semis','SMH +1.8% live, lean up HIT',1)"
```

## Step 3 — update the LINKAGE REGISTRY (this is the whole point — the brain that grows)
The registry lives in the DB and auto-manages status from the forward tally. For EACH linkage that had
a testable observation today (its trigger was present, so its target either did or did not follow):
```
python -c "from rotation.lib.journal import record_linkage as r; r('liquidity->metals', held=True, note='GDX +1.8% as DXY fell — held')"
```
`held=True` if the lead played out today, `held=False` if it broke. `record_linkage` updates fwd_hits/
fwd_n and auto-sets status (unconfirmed <5 obs; holding ≥5 obs & ≥70%; broken ≥5 obs & ≤40%). Score
EVERY linkage the day actually tested — including the ones that BROKE (that is how `broken` is earned).
Do not invent an observation for a linkage whose trigger was absent today — only score what the tape tested.

Then append the narrative to `rotation/memory.md` (Write/Edit), forward-earned only:
- a one-line note per linkage scored today (held/broke + the running tally now).
- **calibration:** were high-confidence calls right more than low-confidence ones? were `mechanism`
  calls' DIRECTION right more than `event` calls'? If not, that framing is not yet earning — say so.
- **theme-live vs direction:** note where a theme was live but direction was a coin flip.
- **regime transitions** worth logging (e.g. "profit-surge day → next-day fade" — if the record shows it).
- Never harden a linkage into a rule from a short record; a `holding` status is a lean, never a gate.

## Step 4 — one honest line to the forward record
Append a dated line to `rotation/forward_record.md`: what was called, what hit, what missed, and the
running hit-rate by horizon. Keep it blunt — over-claiming is the failure mode.

Nothing written outside `rotation/`. The scoreboard is whether these forecasts, graded forward, beat
naive "yesterday's theme repeats" — and only once they do should the calls feed the trading systems.
