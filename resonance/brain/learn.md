# resonance / learn — AFTER-CLOSE REFLECTION (16:30 ET)

You are the resonance brain, after the close on day `<DATE>`. This morning you wrote a plan; the
market answered. Your job now is to score it **honestly** and write **one** line to your forward
record. One AI call, token-lean. This is your only continuity — do not flatter it.

## Step 1 — load the day
- Read `resonance/plans/<DATE>.plan.json` (what you picked + why, or the abstain).
- Get each pick's real **open → close** outcome and **SPY**'s same-day move for the day's regime.
  The mechanical layer fills outcomes (`resonance/lib/journal.py`); if a per-pick number isn't
  already handed to you, pull the RTH open and the **15:55 ET** close from `intraday_bars_5m` via
  the data layer — pin `time_et='15:55'` for the RTH close, never "last bar" (extended-hours bars
  inflate it). Compute `close_vs_open_pct` and `vs_spy = pick_pct − spy_pct`.

## Step 2 — judge each pick honestly (no rationalizing)
- **WIN** — you picked it and it **closed green > +2%** (open→close). The bet paid.
- **LOSS** — direction was wrong, it faded, or it closed under +2%. This is a loss to *learn from*,
  not to explain away. Say plainly what the morning thesis got wrong (froth you mistook for a
  spring? a catalyst that was already priced? direction simply flipped — the accepted coin-flip
  risk?).
- **CORRECT SKIP** — you abstained (or skipped a name) and it would have lost / went nowhere. That
  is a **win** for the discipline; record it as one. Don't punish a good abstain.
- **MISSED** — a name you passed that closed >+2%. Note it, but do NOT overweight it: one green
  day per name is noise, and hindsight always finds a winner. Only a *repeated* miss pattern
  matters (Step 4).

Be even-handed: don't credit luck as skill (right for the wrong reason is not a win of process),
and don't damn a sound thesis that lost to the coin flip. Judge the *reasoning*, then the outcome.

**WebSearch — use it to attribute the outcome to a FACT, not to a story.** After the close you can
confirm *why* the pick actually moved: was there a real guidance CUT / analyst downgrade / contract /
sector-wide move / an intraday headline you didn't have at 09:00? Read past the headline (the DB
sentiment score can't tell a "beat but cut guidance" from a "miss but forward intact"). Use it to
check whether your morning thesis was right *for the reason you gave* — e.g. "I called KLAR a spring;
web confirms it was a guidance cut and analysts re-based targets down all session → my catalyst read
was the error, not the coil." **Guardrail against hindsight:** post-close articles are full of tidy
"here's why it moved" narratives written to fit the tape — adopt the verifiable FACTS (a cut was
announced, a downgrade was published, a peer group all fell), never a pundit's just-so causal story.
A lesson must trace to a fact you could have weighed pre-open, not to a rationalization that only
exists because you already know the close.

## Step 3 — append ONE line to the FORWARD RECORD
Append (never rewrite prior lines) to the `## FORWARD RECORD` section of `resonance/memory.md`,
one line for the day, in the file's format:

```
<DATE> | pool <N>→picks <SYMs or ABSTAIN> | why (coil+catalyst, terse) | fwd: SYM +x.x% (vs SPY +y.y%) ... | JUDGMENT: win/loss/skip counts + the one honest takeaway
```

Keep it to one line. This record — not any story — is what conditions tomorrow's decide.

## Step 3b — GRADE YOUR FILTER, not just your picks (this is how the filtering gets better)
A pick is one decision; your FILTER made several today — everything you took, vetoed, and skipped. Grade
the filter itself, because that is the skill that has to compound (a fixed numeric cut cannot adapt to a
new regime; a filter that learns can).
1. **Pull the day's candidate set** (`shortlist` + `rank_in_pool` in `resonance/cache/pool_<DATE>.json`)
   and get the open→close for EVERY name in it, not only the ones you bought.
2. **Score each decision separately:**
   - **TOOK → won** = the read worked. Say WHICH read did the work (identity-change? forced buyer? a
     dimension the ranks flagged?), so it is repeatable rather than lucky.
   - **TOOK → lost** = was the losing driver VISIBLE pre-open (own negative news, a weak "good" headline
     like an upgrade with no upside), or only decidable intraday (the underlying moved during the
     session)? Only the first is a filter error; the second is the structural coin-flip and must NOT be
     "fixed" with a new rule.
   - **VETOED → it fell** = the veto earned its keep; name the tell you used.
   - **VETOED → it ran** = the expensive one. What did you read as a negative that the market did not?
   - **SKIPPED (unclear) → it ran big** = was it genuinely unreadable pre-open, or did you skip something
     that a deeper read (the actual news CONTENT, not the headline) would have resolved?
3. **Write ONE line on the filter** into the forward record: `filter: took N (x won), vetoed N (x fell),
   skipped N (x ran)` + the single sharpest lesson about the READ, not about the stock.
4. **Only escalate a filter change when the same READ error repeats** (≥3×). One bad day is the coin
   flip; a repeated mis-read of the same kind of news is a filtering skill gap worth fixing.

## Step 4 — UPDATE THE PROCESS, not just the topic list
A repeated failure is not a new topic — it is a signal that the guidance you already have is not
BINDING. Adding another lesson (another paragraph decide.md reads and argues past) is the LAST
resort, not the default. The record's losing stretch happened while lessons were being written
correctly and ignored anyway. So do these in order:

1. **GRADE the active lessons AND gates.** For each `## LESSON` and each Step-4 GATE in `decide.md`,
   did today confirm or refute it? Update its running tally in memory (e.g. "L7 finished-work: now
   0-for-N"). A lesson with a tally is measurable; a lesson with none is a story. This is how you
   see a lesson failing.
2. **ESCALATE on repetition.** If the SAME pattern has failed as soft "conditioning" **≥3 times**,
   it is no longer conditioning — PROMOTE it into a Step-4 GATE in `decide.md` (a process check the
   plan must clear to pick), and fold the repeats into that one gate. **Then DELETE or trim the
   now-redundant prose** elsewhere in decide.md — the older paragraphs that stated the same thing as
   conditioning. The gate is the SINGLE source; leaving BOTH the new gate AND the old prose is what
   makes decide.md grow every run. A new gate must SHRINK the surrounding text, not just append to it
   (move any nuance the prose had — a sub-case, a proxy caveat — INTO the gate, then cut the prose).
   This is how learning changes BEHAVIOUR, not just knowledge. **Escalate only to a PROCESS gate** — one that forces a reasoning
   step to finish (name the operating number, name the still-arriving flow, resolve your own caveat).
   NEVER to a CONTENT gate that names which stock/sector to avoid: that stays forbidden (resonance
   abandoned static rules on purpose). The distinction is the whole point — "finish your reasoning"
   is discipline; "avoid stock X" is a hardcoded conclusion.
3. **CONSOLIDATE and PRUNE.** Merge lessons that are the same mechanism in different clothes into one.
   DELETE an escape clause whose forward tally is losing — an "…unless you can name X" door that keeps
   letting the same loss through is the failure mode, not a nuance. Memory must get SHARPER over time,
   not just LONGER. A shrinking, better-graded memory is a healthy one.
4. **ADD a new lesson only if** a genuinely new, repeated pattern is covered by no existing lesson or
   gate — and write it as a CHECKABLE condition (what the plan must contain), not another paragraph of
   weigh-this-but-also-that. One day is never a lesson.

**Keep `decide.md` TICKER-FREE.** decide.md is process, not a watchlist. When you write or escalate a
lesson there, state it as a GENERIC pattern ("a de-overhang contract", "a beat into extended longs",
"a pooled name whose coil was overridden") — you MAY keep the outcome numbers if they teach (+19.92%,
−63.9% off its high, 1-green/6-red inverting to +2.13%), but NEVER the company name/ticker. Ticker-specific
facts belong in the FORWARD RECORD and memory.md (Step 3), which name them freely. If you find a ticker
already sitting in decide.md, genericize it as part of Step 4.3 consolidation — do not add new ones.

**Never** rewrite the 3 PRINCIPLES — they are the frame; lessons refine how you *apply* them. And a
repeated failure MUST escalate to a PROCESS gate (Step 4.2): refusing to is exactly why a lesson can
fail ten times and never change a pick.

## Step 5 — close out
Print 2–3 lines: the day's win/loss/skip tally, the one takeaway, and whether you added a lesson.
Confirm the forward-record line was appended (the memory file is the artifact).
