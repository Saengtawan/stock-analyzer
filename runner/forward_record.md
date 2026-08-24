# runner — forward record (OFF-RECORD, separate from all trading systems)

**What this is:** a ~10:30-ET confirm scan for penny / small-cap TOP GAINERS, predicting which CLOSE up
>+10% on the day. The edge (backtest-seeded): a penny gainer's direction is a coin flip at the 09:30
open but has resolved + persists by ~10:15-10:30 (83% on n≈12), so runner reads the *confirmed* movers,
filters by who-buys (flow arriving vs consumed), and calls the >+10% closers.

**Isolation (hard):** lives ONLY here + `data/runner.db`. NEVER written to resonance/overnight/exec_ai/
swing/rotation. It forecasts/experiments; it does not trade.

**Honest prior:** penny top-gainers are pump-and-dump prone; 83% persistence is n≈12, high variance,
selection-biased. Every call carries honest odds and is graded forward at the close. Nothing sized until
the >+10%-close calls beat chance over a real forward sample.

---

## Record
_(one line per graded pick: called at 10:30 -> closed -> hit >+10%? -> trade-from-scan)_

_(empty — first live 10:30 scan pending)_
