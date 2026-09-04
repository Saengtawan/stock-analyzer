# exec_ai — the execution brain (AI #3)

A third AI, same data + web access as resonance, but it does ONLY **execution** — the entry and the
exit — never selection.

```
resonance AI  → SELECTION (which stock)          → resonance/plans/<DATE>.plan.json
exec_ai       → ENTRY (limit/buffer) + EXIT (hold / take-profit / trail)   ← this
   ├─ brain/decide.md   read the pick → classify (remodel/attention/other) → entry limit (judged +
   │                    flat ×1.015) + stop → exit strategy + reason
   ├─ brain/learn.md    after close: did entry beat market-open? did the exit beat hold-EOD? → lessons
   ├─ lib/journal.py    data/exec_ai.db (SEPARATE) — decision + outcome per pick
   ├─ run/exec.sh       on-demand runner (decide | learn)
   └─ memory.md         PRINCIPLES + earned LESSONS + FORWARD RECORD
```

## Run (on-demand, cc env, from project root)
```bash
bash exec_ai/run/exec.sh                 # decide entry+exit for today's resonance pick
bash exec_ai/run/exec.sh 2026-08-18 learn   # after close: grade entry+exit
python -m exec_ai.lib.journal recent      # the execution forward record
```

## What it decides
- **CLASSIFY** the pick from its catalyst: REMODEL (current-numbers beat → holds) vs ATTENTION
  (award/story/guidance-cut → pops then fades) vs OTHER.
- **ENTRY** — winLo (mechanical) + a JUDGED buffer (with reason) AND the flat ×1.015, side by side +
  a stop. (Buffer is judgment, not a hardcode — but level-timing is hard, so both shown to compare.)
- **EXIT** — AI-judged, NO class→exit rule: HOLD / TAKE PROFIT / TRAIL chosen by reasoning about the
  specific name's catalyst + tape. The record's patterns (beats tend to drift to the close, story/pop
  names tend to fade, trailing caps the tail) are evidence to weigh, not a switch to obey.

## Boundary
Separate dir `exec_ai/`, separate DB `data/exec_ai.db`, separate plans. Reads trade_history.db
READ-ONLY via `resonance.data.access`. Reads (never writes) `resonance/plans/`. Does NOT affect
resonance or swing.

## Status: v0, UNPROVEN
The benchmark it must beat = **"market-buy at open + hold-to-EOD."** Entry (cheaper limit) and exit
(hold/take-profit/trail) only earn their keep if they beat that over the forward record. Honest caveat
already logged: AI-judged buffer FAILED its first live test (KLAR 08-18 — judged tighter, predicted a
deeper dip that didn't come, missed worse than flat). Level-timing is hard; favor principled
classification (hold vs take-profit) over precise level-guessing. Paper-track before trusting.
