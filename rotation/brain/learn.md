# rotation / learn — grade yesterday's forecast, update the linkage memory

You run POST-CLOSE, right before today's decide pass. Today's tape is complete, so EVERY prior call whose
target session is today — no matter which horizon it was made at — can now be graded. Because decide now
emits a multi-day path, today's close is the target of several earlier forecasts at once: yesterday's
`day+1`, the prior session's `day+2`, and the one before's `day+3` all predicted TODAY. Grade them all,
and track accuracy BY horizon — the whole point of a multi-day path is to learn whether a 2-3 day-ahead
call holds up or decays to noise. Your job: score them honestly, and update `rotation/memory.md` with what
the forward record teaches about which linkages/leads hold and which broke.

OFF-RECORD, isolated: read/write only `data/rotation.db` and `rotation/memory.md`. Touch NOTHING in
resonance/overnight/exec_ai/swing.

## Step 1 — pull the ungraded calls
```
python -m rotation.lib.journal grade      # lists ungraded predictions
```
Grade every ungraded call — at ANY horizon (`day+1`/`day+2`/`day+3`/`week`) — whose target session is now
closed. Each per-day call carries the date it was FOR (in its `for_date` / reason); grade it against THAT
session. A `day+2` or `day+3` call was made 2-3 sessions ago, so several forecasts land on today at once —
grade each on the same closed tape but keep its original horizon label, so the record can separate day+1
vs day+2 vs day+3 accuracy. (Week/regime calls grade when their window resolves.)

## Step 2 — grade each against today's snapshot
Read today's cross-asset snapshot (`snapshot_asof('<TODAY>')`) — the assets/sector/theme ETFs and the
named tickers. For each prediction:
- **Did the theme go LIVE?** (its ETF/names moved with real range/volume, not inert) — the primary test.
- **Did the LEAN hit?** (up/down/risk-on-off correct) — the secondary test; be honest that direction is
  the harder call.
- **Did the falsifiable FIRE?** If the pre-registered test triggered, say so plainly.
Grade LIVENESS and DIRECTION as TWO SEPARATE marks — never collapse them into one ✅. A "live/up" call
can be liveness-correct (it was live) AND direction-wrong (closed down): record BOTH in `outcome`
("live ✅ / dir ✗") and count them in SEPARATE tallies. A "hit on the letter, half in substance" is a
liveness hit and a direction MISS — say exactly that; do not bank it as a clean win (that inflation is
how the record lied to itself).
**Enforce the direction HARD RULE (process check).** A directional `lean` (up/down) is legitimate ONLY on
`kind=mechanism` + `priced=unspent` + POST-trigger. If decide signed a direction on an `event`, a
`regime`, or a PRE-trigger mechanism, that is a PROCESS ERROR — flag it ("illegal direction sign") and do
NOT credit the direction even if it happened to hit (right for a forbidden reason is not skill). Track the
running count of illegal signs; it should trend to zero. Track DIRECTION accuracy ONLY on the legitimate
(post-trigger mechanism-unspent) subset — that is the only direction number that means anything.
```
python -c "from rotation.lib.journal import grade_prediction as g; g('<CALL_DATE>','day+1','AI/semis','SMH +1.8% live, lean up HIT',1)"
```
(`<CALL_DATE>` = the date the call was MADE, and the horizon = its original label, so the (date,horizon,
theme) key matches the row you logged. Grade day+2/day+3 rows the same way when their session closes.)

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
- **Keep the LESSONS section from bloating — but preserve the "what survived contact" trail (it is
  deliberate).** Early on, full prior versions were kept intact on purpose so it stays visible which
  hypotheses survived — that audit value is real for a young record and must NOT be bulk-deleted. What is
  NOT wanted is the same lesson restated as a FULL paragraph in three stacked "UPDATE after <date>" blocks
  that decide then reads as three contradictory L1s. Reconcile the two: **one lesson = ONE current
  paragraph**, and where its history teaches, compress that to a short status trail on the SAME entry
  ("L1 — <current form>. (provisional 08-24 → survived 08-25 → OVERTURNED by L12 08-26)") rather than
  keeping the full superseded paragraphs above it. Collapse a lesson's stacked versions into its one
  current paragraph + trail once the lesson has matured (clearly confirmed or clearly overturned, not
  still in its first session or two). Fully DROP a lesson only when the record has REFUTED it AND a newer
  lesson already carries the correction. Only the FORWARD RECORD section is append-only; the LESSONS
  section should sharpen — one paragraph per lesson — the way the DB registry retires a `broken` linkage.

## Step 4 — one honest line to the forward record
Append a dated line to `rotation/forward_record.md`: what was called, what hit, what missed, and the
running hit-rate **by horizon** — day+1 vs day+2 vs day+3 separately. **Report THREE tallies, never one
blended number:** (1) LIVENESS hit-rate vs the naive "yesterday's theme repeats" baseline (skill only if
it BEATS baseline); (2) DIRECTION hit-rate on the legitimate post-trigger-mechanism-unspent subset ONLY,
with the illegal-sign count; (3) COMPRESSION/inert hit-rate vs the "everything is quiet before its event"
baseline (the 11/11 means nothing if the baseline is also ~100% — state the delta). A number that does not
beat its baseline is not an edge; say so plainly. State plainly whether accuracy
DECAYS with horizon as it should (a day+3 call that scores like day+1 is either luck or a leaked lookup;
a day+3 no better than the naive "today repeats" baseline means the far horizon is not yet earning its
keep — say so). Keep it blunt — over-claiming is the failure mode.

Nothing written outside `rotation/`. The scoreboard is whether these forecasts, graded forward, beat
naive "yesterday's theme repeats" — and only once they do should the calls feed the trading systems.
