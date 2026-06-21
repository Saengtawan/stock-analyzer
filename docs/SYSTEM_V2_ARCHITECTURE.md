# Stock Analyzer — System v2 Architecture (clean rebuild)

> Rebuilt 2026-06-18. Replaces the piecemeal v1 (H12-A 235 + stacked hard rules).
> v1's problem: built in fragments, rules added ad-hoc → train/serve skew, lookahead,
> overfit gates, in-sample inflation (~7 false positives caught while designing v2).
> v2 = one coherent pipeline, each layer with a single responsibility, no conflicts.

> ## ⭐⭐ CAPSTONE (2026-06-18) — the system is RADICALLY simpler than L2 below.
> Decisive L2-necessity test (Z1 band N=186, absolute EOD, ret/DD): **gain + vix-gate (ZERO ML)
> = ret/DD 7.98**, vs gain-alone 4.60, vs **ML-substrate win_p-select 1.18** (7× worse). The ML
> substrate (235 → lean → faithful → calibration) is NOT NEEDED — it's worse than plain gain.
> **CLEAN SYSTEM = `gain ranking (select) + vix regime (gate/size) + market-reactive exit`.**
> No lean models, no win_p, no calibration. Edge = magnitude (gain) + regime (vix), NOT ML
> prediction — where every session finding pointed. The lean work = valuable NEGATIVE knowledge
> (rigorously ruled out the ML-selector path). L2/L3-substrate below now OPTIONAL/likely-dropped;
> live-relevant = L4 (gain select) + L5 (vix risk-mgmt) + L0 (faithful gain/vix inputs). CONFIRM
> WF cross-zone before finalizing; direction strong + every component already validated this session.

Build as a **parallel namespace** (`src/scan/v2/`). Do NOT touch v1 until v2 passes
**replay validation** and beats v1 on the same saved snapshots. Then cut over (paper
account → no real-money risk). 1-command rollback kept at every step.

---

## Invariant principles (never violate — earned the hard way)

1. **Parity** — live == backtest. Every feature computed from the SAME source both
   sides; bit-parity tested before inclusion. (killed: gap/open IEX-skew, Yahoo-open)
2. **No lookahead** — PIT-correct everywhere. (killed: feat_daily leak, AD-conditional)
3. **Test before believe** — every layer: walk-forward + controls (positive/negative/
   shuffle), absolute metric not a proxy. (killed: fwd_ret circularity, bars-inflation)
4. **Learned regime > hard rule** — let the model learn regime from features (vix/ad/spy
   are top-importance) instead of hand-coded gates. Remove brittle rules.
5. **Calibration** — win_p is a TRUE probability (isotonic). Thresholds mean something.
6. **Magnitude not direction** — monetize the right tail (gain), manage risk (size/exit).
   WR is NOT the objective; the riser makes money at low WR.

---

## The pipeline (root → execution), 7 layers, one job each

### L0 — DATA (single source of truth)
- ONE source live + backtest: **Alpaca IEX 1-min** (feed='iex' = matches live snapshot).
- PIT-correct: macro/daily/breadth use prior-close; intraday cumulative to scan time.
- **L0 POC findings (2026-06-18):** vs the LIVE saved snapshot, IEX 1-min recompute is
  **bit-exact on range/hi/lo features (median Δ 0.000)** and **~0.2 on open-derived
  (gain/from_peak/vs_vwap)** — the irreducible thin-09:30-open ambiguity (official
  daily-open ≠ first-1min-open). Current training pkl is **~0.6** off live → rebuild
  from IEX 1-min cuts skew ~3x (range → 0). SIP feed is worse (use IEX to match live).
- **Substrate NEEDS the fragile bar features** (proven: dropping them → Z1 −35%, Z2 −85%)
  → rebuild is mandatory, not skippable.
- **Builder DONE:** `src/scan/v2/bar_features_1min.py` (fetch_1min + bar_features,
  validated). Reusable for both pkl-rebuild and live serve.
- **Remaining:** (a) run the rebuild at scale (~2.5yr × universe, API job) → faithful pkl;
  (b) retrain lean on it; (c) measure live-skew drop on saved snapshots. (d) LONG-TERM
  true-0-parity: accumulate live snapshots forward, retrain on real snapshots in N months.

### L1 — FEATURES (clean, parity-verified)
- Include a feature ONLY if it is train/serve bit-parity. Audit each.
- Drop/fix the open-skewed: gain_from_open, gap_from_prev, vs_vwap, path_gap_ratio,
  path_vwap_slope (or recompute on the L0 faithful open).
- Sets: macro-regime block (vix-family, ad_ratio, spy/cross-ETF) + clean-intraday
  (range_pct, from_peak, vol_ratio, range_exp) per zone.
- **Status:** audit started (found 5 skewed feats, importance 2.53%). Need full audit.

### L2 — SUBSTRATE MODEL (the ML root)
- Lean **pooled per zone** + sector as a categorical feature (NOT 235 per-sector —
  proven to overfit, negative OOS Z2/Z3, vs lean WF win every zone, 3-5x less overfit).
- Calibrated (isotonic) · mean-of-10-seeds · regularized (depth-3).
- **Objective = calibration + AUC + stability, NOT WR.**
- NO hard gates baked in — model learns regime from features.
- Zones: Z1, Z2, Z3. **Z4 CUT** (WR<50%, negative all WF folds). Z3 kept but thin
  (afternoon decay — accept lower edge; don't chase WR).
- **Status:** Z1 (macro-15) + Z2 (intraday-clean-12) trained, parity-verified
  (`models_lean_v1/`). Need: Z3 final + tighter calibration (top-1 still overconfident).

### L3 — ABSTENTION (when to trade)
- Causal rolling-**quantile** on calibrated win_p + **ONE validated regime gate (vix<20)**.
- Gate-removal test (2026-06-18): "remove ALL hard rules" is too aggressive — the substrate
  RANKS, it does not self-abstain on bad regimes. The hard **vix<20 gate ADDS value** (Z1
  holdout avg +0.694→+1.007, WR 60→68%) that the model's continuous vix feature + quantile
  only weakly capture (corr win_p,vix = −0.12; quantile +0.794 < vix-gate +1.007). KEEP it.
- DO remove the brittle/overfit rules (13 EF rules, AD-conditional, MOM-30, gap-cap) — those
  were the "rule มั่ว". Keep: vix regime gate (mechanistic, validated since H8) + quantile.
- Replaces the fixed 0.68 threshold (fixed-p collapses across regimes; quantile stays stable).
- **Status:** quantile built+tested (`lean_abstain.py` q=0.35/W=60); vix-gate validated (N=67
  single holdout — confirm WF + on faithful substrate).

### L4 — BOOST (which stock — GAIN ranking, ALL zones)
- **gain ranking is the universal selector — ALL zones, not just Z1.** L4 test (absolute EOD,
  holdout): gain beats win_p everywhere — Z2 gain +1.211 vs win_p +0.425 (3x); Z3 gain +0.743
  vs win_p **−0.097** (win_p NEGATIVE). Same as Z1/riser: win_p looks good on fwd_ret (circular,
  its training target) but LOSES on absolute money. magnitude (gain) selects; win_p does not.
- So the **substrate win_p is NOT a selector for any zone** — it's the regime/abstention signal.
  gain (the riser mechanism) is the selector for Z1/Z2/Z3. (gain×win_p helped Z2 +1.36 but hurt
  Z3 +0.58<gain → use gain-alone, robust.)
- **Status:** Z1 riser live. Z2/Z3 = extend riser (gain rank). Confirm WF + on faithful.
- **⚠️ OPEN — L2 necessity:** if gain selects + vix-gate handles regime, does the ML substrate
  add anything over "gain + vix-gate"? lean win_p is vix-dominated (vix-gate captures most). TEST:
  does substrate beat gain+vix-gate alone? If not → drop the ML substrate, system = gain selector
  + vix regime (ultimate lean). This is the deepest open question of v2.

### L5 — RISK (exit + sizing)
- **Exit = market-reactive, not stock-level price stops** ("cut market not stock"):
  - stable picks → v18 (spy_dd ≤ −0.3% gate). riser → market-vol regime
    (VIX / own_range) dynamic trail + catastrophe SL (−2%/10min, validated).
- **Sizing = VIX-regime (the validated lever).** Test (riser band N=186): vix-regime
  sizing improves ret/DD +15~73% — abstain/zero-size high-vix (vix≥20) → ret/DD 4.60→7.94
  (total ↑, maxDD ↓); continuous inverse-vix tilt 5.27, low-vix tilt 5.62. The correct way
  to reduce DD (NOT a win_p tilt — win_p ⟂ gain). **L5 sizing + L3 vix-gate = the SAME vix
  regime signal** — implement once (vix → trade/size), don't double-count.
- This confirms the session thesis: returns come from RISK-MGMT (vix-regime), not substrate
  selection (which is thin). vix-regime is the unifying risk signal across H12-A (v18) + riser.
- **Status:** exits validated (v18, riser dynamic trail, catastrophe-SL −2%/10min 9/12).
  vix-regime sizing validated (N=186). Implement: unified vix-regime trade/size module.

### L6 — EXECUTION + JOURNAL
- One journal schema, all decisions logged (drift monitor).
- **No live shadow lane.** Validation is offline replay (below), then direct replace.
- **Status:** journal helpers exist (lean_picks). Unify schema for v2.

---

## Validation: REPLAY-then-REPLACE (no forward shadow)

Paper account → skip slow forward-shadow. Instead, before cutover:
1. **Replay** the fully-assembled v2 on the last 30-60 days of saved snapshots
   (`data/scan_snapshots/` = real live-faithful data). Confirm:
   (a) picks are sane, (b) match v2's own backtest, (c) v2 ≥ v1 on the SAME days (A/B).
2. **Tag v1 for rollback** (git tag + model backup), as with v1.9.0-pre-h12a.
3. **Replace** (flip the engine to v2). Observe paper forward (free) the first weeks.
Replay gives ~everything forward-shadow would (integration bugs, A/B, live≈backtest)
in hours, not weeks. Only thing it can't: genuinely new future regime → observed post-cut.

---

## Build order (dependency-staged)

1. **L1 feature parity audit** — full skew/lookahead sweep (root of "trustworthy").
2. **Gate-removal test** — lean-no-gate vs lean+gate vs 235+gate (WF). Confirm the
   substrate stands without hard rules (the core of "remove rules, rely on ML").
3. **L2** — train lean Z3, tighten calibration.
4. **L4/L5** — design Z2/Z3 boost; implement catastrophe-SL + sizing.
5. **Replay-validate** assembled v2 vs v1 → cut over.

## Rollback
Every cutover reversible: git tag pre-v2 + `models_prod_v23_h12a` kept + `.env`
variant flag. Revert = flip flag / restore tag + restart services.

## Reusable from current work
`models_lean_v1/` (L2 Z1/Z2), `ml_scorer_lean.py` (L2), `lean_abstain.py` (L3),
`build_snap_from_1min.py`+`snap2h12a.py` (L0 replay), saved snapshots (validation set).
