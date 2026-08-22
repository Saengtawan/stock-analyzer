# rotation — forward record (OFF-RECORD, separate from all trading systems)

**What this is:** a post-close cross-asset THEME/REGIME forecaster. Every session it stores the
cross-asset picture + the forward catalyst calendar and predicts which themes are likely live (and the
regime) for the next session / this week — the goal is a step of LEAD TIME over the reactive trading
systems. It forecasts; it does not trade.

**Isolation (hard):** lives ONLY here + `data/rotation.db`. NEVER written to resonance/overnight/
exec_ai/swing data, plans, or records. Its calls do not enter any trading journal.

**Honest prior:** cross-asset rotation forecasting is the hardest prediction and the easiest to
over-fit. Every call has a pre-registered falsifiable and is graded forward; linkages are never hardened
from a short record. The scoreboard is whether the forecasts beat naive "yesterday's theme repeats"
over a real forward sample, and only then do they feed the trading systems (as weighed context, never a
gate).

---

## Record
_(one dated line per graded pass: called → hit/miss → linkages held/broke → running hit-rate)_

_(empty — first live post-close pass pending)_
