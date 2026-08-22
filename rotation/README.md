# rotation — cross-asset theme / regime forecaster (predict tomorrow, one step ahead)

A standalone, OFF-RECORD forecasting experiment. The trading systems (resonance/overnight) are
*reactive* — they read today's setup and act. rotation is *predictive*: every post-close it accumulates
the cross-asset picture + the forward catalyst calendar, and forecasts which THEMES are likely live
(and the regime) for the next session / this week — so we get a step of lead time instead of reacting a
day late. If it earns a forward record, its output later feeds the trading systems as weighed context.

```
rotation/
  data/snapshot.py    MECHANICAL 0-token cross-asset snapshot (yfinance) -> data/rotation.db
  lib/journal.py      the DB layer: snapshots + graded predictions (log/grade/query lead-lag)
  brain/decide.md     AI: snapshot + forward calendar + memory -> predict tomorrow/week/regime + names
  brain/learn.md      AI: grade the prior session's calls -> update linkage memory
  run/daily.sh        post-close: snapshot -> learn (grade) -> decide (predict). ONE daily pass.
  plans/<date>.json   the day's forecast (flexible JSON)
  memory.md           accumulating LINKAGE MEMORY + lessons (the "market memory" the AI digests)
  forward_record.md   human-readable running log + hit-rate
```

## Storage — HYBRID by design (each data type in the format that fits)
- **SQLite `data/rotation.db`** — numeric time-series (`snapshots`, LONG format) + graded `predictions`.
  Queryable, so lead-lag / correlation / hit-rate can be computed over time.
- **JSON `rotation/plans/<date>.json`** — the AI's full daily forecast (flexible, nested themes).
- **Markdown `rotation/memory.md`** — the AI's accumulating linkage memory + lessons (evolving narrative).

## Run
```bash
bash rotation/run/daily.sh            # post-close: snapshot + grade prior + predict next
python -m rotation.lib.journal recent # predictions + hit-rate by horizon
```
Cron (suggested): `10 16 * * 1-5` ET (= ~03:10 BKK) — after the close, before next day's resonance run.

## Isolation (hard) + OFF-RECORD
- Writes ONLY to `data/rotation.db` and `rotation/*`. NEVER touches resonance/overnight/exec_ai/swing.
- It FORECASTS; it does not trade. Its calls do not enter any trading journal until forward-proven.

## Horizons & output
- **tomorrow** — themes likely live next session + lean + names + falsifiable.
- **week** — dated catalysts lighting themes this week + building rotation.
- **regime** — risk-on / risk-off / rotation / chop.
Names are candidates for the trading systems to who-buys-test — rotation predicts WHERE the flow is,
not what to buy.

## Status: UNPROVEN — over-fit is the risk
Cross-asset rotation forecasting is the hardest kind of prediction and the easiest to over-fit. Every
call carries a pre-registered falsifiable and is graded forward; linkages are never hardened from a
short record. The scoreboard is whether the forecasts beat naive "yesterday's theme repeats" over a
real forward sample. Nothing feeds the trading systems until it does.
