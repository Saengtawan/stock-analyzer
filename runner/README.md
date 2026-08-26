# runner — penny catalyst + good-entry (~10:30), target >+10% from entry

A standalone, OFF-RECORD, speculative experiment. **Thesis (REVISED by the 08-24..08-26 retrospective):**
the biggest EOD winners were high-momentum, low-price **squeeze/gapper** names — mostly NO catalyst — that
the old fresh-catalyst filter kept dropping, while the catalyst picks fizzled. So: POND = today's biggest
low-price gappers (NOT catalyst-filtered); the edge is a **crash-GATE — drop the BLOW-OFFS** (a violent
first-hour single-bar reversal, ~−13% reference); enter ~10:30, HELD TO CLOSE (no trailing), target +10%
from entry. It is a crash-avoider, not a winner-picker (validation in-sample, n=14 — see `forward_record.md`).

The ORIGINAL thesis (momentum-persistence: "follow the 10:30 up-confirmed direction", 83% on n≈12) was
FALSIFIED on 08-24 — following the up-confirmed bought extended tops (BTCT +55% at 10:30 → −32% close)
and missed the winner PMI (faded −2.2% at 10:30 → +17.5% on a fresh catalyst). So runner now selects on
CATALYST + not-extended ENTRY, not price-momentum.

```
runner/
  brain/decide.md   ~10:30 scan: fresh-catalyst penny movers -> good-entry filter -> which close >+10%
  run/scan.sh       runner (~10:30 ET). timeout 900, WebSearch+Bash+yfinance.
  run/grade.sh      grade at the close (15:55 ET), deterministic
  lib/journal.py    data/runner.db (log picks + grade)
  plans/<stamp>.txt output
  forward_record.md running log + hit rate
```

## Run
```bash
bash runner/run/scan.sh     # ~10:30 ET — today's fresh-catalyst penny movers with room to close >+10%
bash runner/run/grade.sh    # after the close — did they hit
python -m runner.lib.journal recent
```

## Why ~10:30 (the entry window)
Late enough that a fresh catalyst's re-rating is visible (which movers have a REAL driver vs a spent
pump), early enough that a not-yet-extended name still has room to run to the close. NOT a
momentum-confirm window — the old "direction persists by 10:30" rationale (75% @10:00, 83% @10:30) was
FALSIFIED 08-24 (up-confirmed bought tops). 10:30 is the moment to read catalyst + entry quality.

**A 10:20 window was tried and reverted 08-25 (same day).** Rationale for moving was "PRZO's high
printed 10:12 so 10:30 is late" — but the tape inverted it: at 10:20 PRZO was still pinned to that high
(0.80) and by 10:30 had pulled back cheaper (0.78). Across the day's 3 names 10:20 was +0.55% on average
= noise. The window is not the edge — catalyst + not-extended is. (The minute tape also showed the real
confirmation point is ~10:00-10:05, but that is n=1 hindsight; not chasing it without a forward sample.)

## Isolation (hard) + OFF-RECORD
- Writes ONLY to `data/runner.db` and `runner/plans/`. NEVER touches resonance/overnight/exec_ai/swing/
  rotation. It forecasts/experiments; it does not trade.

## Status: UNPROVEN — pump-prone, n small
Penny top-gainers are pump-and-dump prone and the 83% is n≈12 with high variance + selection bias. Every
pick carries honest odds and is graded forward at the close. Nothing is sized until the forward record
shows the >+10%-close calls beat chance.
