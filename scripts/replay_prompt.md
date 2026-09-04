# resonance replay — the canonical agent prompt

Replay is the only cheap way to test a change to the brain BEFORE it goes live, and this session
proved it is also easy to run wrong: across eight replays the agents disclosed **five distinct leak
channels**, every one of which I had to patch after the fact. Hand-writing the guards each time is how
one gets forgotten, so they live here. Substitute `<DATE>` and paste.

**Before running, produce the context and read what it prints:**

```bash
python scripts/make_replay_context.py <DATE> <SCRATCH>     # prints the EDGAR_AS_OF line too
python -c "from resonance.screen import pool; pool.pool('<DATE>', cache_dir='<SCRATCH>', write=True)"
```

**Run the agent with `EDGAR_AS_OF=<DATE>` set in its environment.**

**Concurrency:** run **at most two** replays at once. Four in parallel exhausted the session's 200-call
WebSearch budget and three agents then decided with **no web access at all** — they said so, and their
reads were correspondingly thin. A replay without search is not a like-for-like test of a brain whose
Step 3 depends on it.

---

## The prompt

> CONTROLLED REPLAY — resonance pre-open decision for **`<DATE>`**.
>
> Working directory: `/home/saengtawan/work/project/cc/stock-analyzer`
> Scratch: `<SCRATCH>`
>
> 1. Read and follow `resonance/brain/decide.md` in full. `<DATE>` is the date above. Follow its Step
>    order exactly.
> 2. **MEMORY OVERRIDE:** do NOT read `resonance/memory.md` — it is the graded forward record and holds
>    this session's outcome. Read `<SCRATCH>/memory_<DATE>.md` (same file, truncated and scrubbed).
> 3. **POOL OVERRIDE:** read `<SCRATCH>/pool_<DATE>.json`, not the one under `resonance/cache/`.
> 4. `resonance/brain/evidence.md` is available when a gate is unclear — consult sections, do not read
>    it end to end.
> 5. Do NOT write to `resonance/plans/`. Return the plan as text in your final message.
>
> ### ⚠️ HINDSIGHT GUARD
> It is **09:00 ET on `<DATE>`, before the open**. Use ONLY information published before that moment.
> - You MUST NOT read, use, or infer how the session went: no closes, no "surged/fell" recaps, nothing
>   dated `<DATE>` afternoon or later.
> - Do NOT query any local DB or file for this date's open/close or outcomes, and do not grep any file
>   for this date's results.
> - **Mis-stamped items are real.** Some web items carry a wrong timestamp and look pre-open while
>   describing a later session. **If a headline's content contradicts the premarket tape you measured
>   yourself, treat it as mis-stamped, discard it, and say so.** One agent caught exactly this: an item
>   stamped 07:28 ET describing a rally that its own tape showed was not happening.
> - EDGAR is a live index. `EDGAR_AS_OF` is set for you, but if any filing still comes back dated after
>   `<DATE>`, discard it unread and say so.
> - **Search budget: keep to roughly 15 targeted queries.** Exhausting the shared budget leaves later
>   work with none.
> - If anything reveals the outcome, DISCARD it, disclose it plainly, and do not let it influence the
>   decision. Disclosure is not a failure — every replay that found a leak found it this way.
>
> ### Return
> A. **TAKE** — ≤3 names (or none), each with the direction thesis and the specific pre-open fact.
> B. **VETO** — pooled names actively rejected, one line each.
> C. **SKIP (unreadable)** — grouped, but each with its own observable.
> D. `cohort_baseline` **for your name's gap sign** (`by_gap_sign`) and why the pick beats it.
> E. If you abstain, name the ONE name you would have taken if forced, and why (`closest_call`).
> F. Final lines: (i) any outcome leak, and from where? (ii) did you read decide.md in full — was any
>    part unclear or self-contradictory? (iii) anything in the pool file that did not match the tape you
>    measured?
>
> Be concise. Your final message is the deliverable.

---

## What replay still cannot do

State this whenever a replay result is used to justify a change:

- **A lesson written after `<DATE>` can still encode hindsight** even with its outcome numbers scrubbed.
  Truncation removes the answers, not every trace of them.
- **The current brain is judging an older morning.** Gates written after the replay date are applied
  anyway; this is not a reconstruction of what that morning's brain would have done.
- **Web search is unbounded** and cannot be date-fenced the way EDGAR and the memory file can.
- **n is tiny.** Four sessions is four sessions. The reverted "look for winners first" experiment read
  as a clear improvement in every agent's own account of its process and still lost on the tape —
  process feedback is not outcome evidence.

Replay is for catching a change that is *wrong* before it ships. It cannot show that one is *right*.
Only forward tracking does that.
