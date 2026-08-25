# runner — penny catalyst + good-entry (~10:30), target >+10% from entry

A standalone, OFF-RECORD, speculative experiment. **Thesis (REVISED after the 08-24 forward day):**
work backwards from "which small-cap / low-price names END the day up big" and catch them EARLY (~10:30)
at a GOOD entry — a **fresh CATALYST that is still re-rating and NOT yet extended** (flat/basing, or
faded-then-reclaiming), entered cheap before the run, exited on a TRAILING stop, target +10% from entry.

The ORIGINAL thesis (momentum-persistence: "follow the 10:30 up-confirmed direction", 83% on n≈12) was
FALSIFIED on 08-24 — following the up-confirmed bought extended tops (BTCT +55% at 10:30 → −32% close)
and missed the winner PMI (faded −2.2% at 10:30 → +17.5% on a fresh catalyst). So runner now selects on
CATALYST + not-extended ENTRY, not price-momentum.

```
runner/
  brain/decide.md   ~10:30 confirm scan: confirmed penny gainers -> who-buys filter -> which close >+10%
  run/scan.sh       runner (~10:30 ET). timeout 900, WebSearch+Bash+yfinance.
  run/grade.sh      grade at the close (15:55 ET), deterministic
  lib/journal.py    data/runner.db (log picks + grade)
  plans/<stamp>.txt output
  forward_record.md running log + hit rate
```

## Run
```bash
bash runner/run/scan.sh     # ~10:30 ET — today's confirmed penny gainers most likely to close >+10%
bash runner/run/grade.sh    # after the close — did they hit
python -m runner.lib.journal recent
```

## Why ~10:30 (the entry window)
Late enough that a fresh catalyst's re-rating is visible (which movers have a REAL driver vs a spent
pump), early enough that a not-yet-extended name still has room to run to the close. NOT a
momentum-confirm window — the old "direction persists by 10:30" rationale (75% @10:00, 83% @10:30) was
FALSIFIED 08-24 (up-confirmed bought tops). 10:30 is now the moment to read catalyst + entry quality.

## Isolation (hard) + OFF-RECORD
- Writes ONLY to `data/runner.db` and `runner/plans/`. NEVER touches resonance/overnight/exec_ai/swing/
  rotation. It forecasts/experiments; it does not trade.

## Status: UNPROVEN — pump-prone, n small
Penny top-gainers are pump-and-dump prone and the 83% is n≈12 with high variance + selection bias. Every
pick carries honest odds and is graded forward at the close. Nothing is sized until the forward record
shows the >+10%-close calls beat chance.
