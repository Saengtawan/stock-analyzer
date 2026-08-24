# runner — penny top-gainer momentum, confirm-at-10:30, target >+10% close

A standalone, OFF-RECORD, speculative experiment. It tests a backtest-seeded edge on penny / small-cap
TOP GAINERS: their direction is a **coin flip at the 09:30 open** (premarket gap did NOT predict it —
53% in test), but by **~10:15-10:30 the intraday direction has RESOLVED and PERSISTS to the close**
(83% on n≈12, high variance, selection-biased). So runner scans the *confirmed* movers at ~10:30,
applies a who-buys flow filter, and predicts which CLOSE up >+10% on the day. Entry is modeled at the
10:30 scan price.

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

## Why 10:30 (the whole edge)
| when | direction predictable? |
|---|---|
| 09:30 open (premarket gap) | NO — 53% coin flip |
| ~10:00 | 75% persistence |
| **~10:15-10:30** | **82-83% persistence** (best; direction resolved + still runs) |
So runner deliberately WAITS to 10:30 — the open is a coin flip, the confirmed 10:30 direction is not.

## Isolation (hard) + OFF-RECORD
- Writes ONLY to `data/runner.db` and `runner/plans/`. NEVER touches resonance/overnight/exec_ai/swing/
  rotation. It forecasts/experiments; it does not trade.

## Status: UNPROVEN — pump-prone, n small
Penny top-gainers are pump-and-dump prone and the 83% is n≈12 with high variance + selection bias. Every
pick carries honest odds and is graded forward at the close. Nothing is sized until the forward record
shows the >+10%-close calls beat chance.
