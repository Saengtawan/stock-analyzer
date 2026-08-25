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

## Open finding — the catalyst filter has dropped the day's biggest winner 2 days running

The thesis SELECTS on a fresh catalyst + not-extended entry and DROPS no-catalyst momentum. Two straight
live days, the single biggest mover on the board was a no-catalyst name the filter dropped:
- **08-24:** dropped **PMI** (faded −2.2% at 10:30 → +17.5%); the up-confirmed momentum names it would
  have bought under the OLD thesis crashed (BTCT +55% → −32%). This is what forced the catalyst revision.
- **08-25 [hindsight, late-fire replay]:** dropped **NCPL +111% peak / trail +10.0% HIT** and **PMI +47%
  peak / trail +25.0% HIT** — both verified no fresh catalyst (PMI last item Q2 08-19, NCPL last PR 08-12,
  a float-squeeze/consolidation bucket). Both were also *extended* at 10:30 → fail both filters.

**NOT rewriting the thesis on this.** The same no-catalyst bucket also held every big LOSER on the 08-25
board (AIXI −8.3%, TNMG −11.3%, BTCT −11.9%, OFAL −8.0%, DAIC −2.2%). It is the high-variance bucket the
filter was built to avoid paying for. The open question — is avoiding it worth the winners it costs? — is
settled by the forward record, not another same-day post-hoc revision. Watch whether the dropped winners
keep beating the picked catalyst names over a real sample.

**Window note:** a 10:20 window was tried + reverted 08-25 (noise: +0.55% on n=3, worse on PRZO). Entry
stays modeled at the 10:30 bar. scan.sh now flags a late fire so a post-10:30 lookup can't be logged as a
forecast.

## Record
_(one line per graded pick: called at 10:30 -> closed -> hit >+10%? -> trade-from-scan)_

**08-25 (first live scan, 10:30):** logged PRZO / GRML / RZLV — grade after 16:00 ET.
Hand-graded controls (NOT in DB): PMI, NCPL, JEM (drop-side, no-catalyst); RZLV also the extended-side test.
