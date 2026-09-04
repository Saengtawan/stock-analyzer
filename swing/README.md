# swing — the medium-term sibling of resonance

A separate paper system, **same philosophy as resonance, different objective**: hold **~1 week to
1 month** instead of intraday.

- **Mechanical layer = the predictable part** (`features/mechanical.py`): volatility COMPRESSION +
  trend LEADERSHIP, measured from daily bars — the swing analog of coil.
  - **TTM Squeeze** (BB inside Keltner = coiled) + **VCP** (leader making tighter pullbacks on
    drying volume). NO hardcoded buy-thresholds — raw pattern defs + measures relative to the
    stock's own history.
- **AI = the unpredictable part** (`brain/decide.md`): direction, catalyst, regime, conviction —
  exactly what the pattern alone can't give.

```
data ── (reuses resonance.data.access, READ-ONLY, mode=ro) ── trade_history.db
 └─ features/mechanical.py   9-axis compression BLEND (resonance-style) — RAW components, NO score/ranking
      squeeze(TTM) · fired · contract(VCP) · nr7(Crabel) · bbsqz(Bollinger) · tight(ATR%) ·
      rvolcontr(realized-vol) · rangecontr(10/40) · loaded(deep drawdown). + trend/RS raw.
 └─ screen/pool.py           UNION-OF-AXES (>=1 of 9, percentile top-Q%) + structural prereqs; breadth-first
 └─ brain/decide.md          AI weighs the raw axes: direction/catalyst/regime -> picks + stop/target
 └─ lib/journal.py           forward record in data/swing.db (SEPARATE)
 └─ run/scan.sh              ON-DEMAND runner (pool -> AI). NOT on cron.
```

## Run (on-demand, cc env, from project root)
```bash
python -m swing.screen.pool                 # just the raw pool -> swing/pool/<date>.json + table
SWING_NO_AI=1 bash swing/run/scan.sh         # pool only
bash swing/run/scan.sh                        # pool + AI judgment -> swing/plans/<date>.txt
python -m swing.lib.journal recent            # forward record
```
Env knobs (structural prereqs + percentile breadth, NOT alpha tuning / NOT ranking):
`SWING_MIN_DVOL` (15e6, tradable), `SWING_MIN_ADR` (0.8, drop pinned flatlines),
`SWING_BREADTH_Q` (0.06, tightest fraction of universe = a "tight" axis hit), `SWING_TOP_N` (45,
display/enrichment cap only — cut by tightness, not a ranking).

Resonance parity: mechanical emits RAW components (no compression score); pool is UNION-OF-AXES (no
weighted composite, no direction/strength gate); decide.md carries no hardcoded market priors — the
AI weighs everything and earns its own lessons from the forward record.

## HARD boundary — does not touch resonance
- Separate dir `swing/`, separate DB `data/swing.db`, separate `swing/plans/`, `swing/pool/`.
- Reads `trade_history.db` **read-only** via `resonance.data.access` (SELECT, `mode=ro`); imports
  are read-only and have zero side effects on resonance.
- **No cron.** Manual/on-demand only. Nothing in resonance/ is read-mutated or scheduled by this.

## Status: v0, UNPROVEN
Screen + AI wired end-to-end; **no forward record yet**. Swing validation is inherently slow (few
independent samples, week-long resolution) — treat every pick as a watchlist item, size for the
stop, and **forward-track before trusting or sizing up.** Backtest/screen is optimistically biased;
forward is the only judge.
