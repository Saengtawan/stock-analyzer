# Changelog — ml_filter

Semantic versioning: `v<MAJOR>.<MINOR>.<PATCH>`
- **MAJOR**: pipeline/architecture change (forces full re-validation + parity audit)
- **MINOR**: algorithm change requiring model retrain (label, HPs, ranking) + 30d OOS
- **PATCH**: config tweak only (no retrain) + smoke test

All deploys tagged in git. Backup artifacts retained per version.

---

## [v2.2.0] — 2026-05-17 (Step 26) ⭐ CURRENT

### Added
- Z3 + Z4 win label: `label_custom_dd` (DD-aware, EOD>scan AND no -3% DD)
- Optuna-optimized HPs per zone (30 trials each):
  - Z1: depth 3→2, leaves 24→40 (shallower + wider)
  - Z2: depth 5→3, leaves 47→5 (much simpler)
  - Z3: depth 4→2, leaves 31→28 (shallower)
  - Z4: depth 3→6, leaves 8→49 (deeper for complex patterns)
- R9 ranking: `win_p × max(0, 1-pred_r)^0.5` (was `win_p` only)
  - Bonus weight for picks with predicted cushion (more discount on adaptive limit)

### Performance
- WF 6mo: based on Step 25 +1854% / WR 81% / -4.75% (+Step 26 incremental boosts)
- 30d OOS (Apr 17-May 17): N=206 / WR 97% / +555% / -3.72%
- vs v2.1.1 (Step 25): +33% total, +2pp WR, Z2 worst -2.57% → +0.12%

### Files
- `scripts/train_zones.py` (ZONE_LABEL Z3/Z4, ZONE_HP all)
- `src/scan/strategies/ml_filter.py` (R9 ranking, pred_ratio in extra_dict)
- `scripts/validate_retrain.py` (sync to v2.2.0 config)

---

## [v2.1.1] — 2026-05-17 (Step 25)

### Removed
- Z4 hard SL -3% (`ZONE_HARD_SL = {}`)

### Changed
- Exit strategy: pure hold to EOD for ALL zones (was Z4 SL -3%, others pure hold)

### Rationale
After Step 23 dip filter + Step 24 better Z2 ML, the SL was converting recoverable
-1 to -2.5% intraday dips into -3.10% locks (whipsaw). DD>3% trades: 25 → 4.

### Performance
- WF 6mo: +1854% / WR 81% / -4.75% (vs Step 24 +1796% / -3.45%)
- Z4 WR: 79% → 81%

---

## [v2.1.0] — 2026-05-17 (Step 24)

### Added
- New label `label_custom_dd`: EOD>scan × 1.0 AND no -3% intraday DD
- Available in pkl after rebuild (data-dense 38% pkl-wide, 96% Z2-only)

### Changed
- Z2 win model: `label_eod_green_v2` → `label_custom_dd` (DD-aware)
- Z2 win-prob trained on stricter target (EOD strict + DD constraint)

### Performance
- WF 6mo: +1796% / WR 81% / -3.45% (vs Step 23 +1518%)
- Z2 WR: 79% → 84%
- 30d OOS Z2 worst: -3.48% → -2.57%

### Pipeline
- pkl rebuilt (1.4GB → 1.6GB, 137 cols)
- 60 models retrained
- Backup: `backtests/models_prod_v22_pre_step24/`

---

## [v2.0.1] — 2026-05-17 (Step 23)

### Changed
- `Z4_DIP_FILTER`: 0.005 → 0.009 (skip Z4 if pred_r > 0.991)

### Rationale
Z4 picks with high pred_r (>0.991) had adaptive limit ≥ scan_price (no cushion).
Tail trades PGR -6.21%, VALE -4.99% were over-buffered cases. Filter eliminates
these structurally.

### Performance
- WF 6mo: +1518% / WR 81% / -3.48% (vs Step 21 +1931% / -5.09%)
- Z4 picks: 534 → 268 (-50%), Z4 WR 73% → 84%

---

## [v2.0.0] — 2026-05-16 (Step 20-21) ⭐ MAJOR

### Changed (BREAKING)
- VWAP formula: close-weighted `sum(c×v)/sum(v)` → HLC/3 weighted (both training + live)
- Scan timing: 1-min real-time snap → 5-min boundary snap (Option A)
- First scan time: 09:31:30 ET → 09:35:30 ET (wait for first 5-min bar + 30s buffer)

### Fixed
- validate_retrain lookahead bias (train ≤ end_date - 30 days)
- Cross-scan dedup TZ mismatch (SQLite UTC vs scan_ts ET)

### Rationale
Pipeline diverged: training pkl computed VWAP with close-weighted, live used HLC/3.
Live also snapped at off-boundary mfo (1,2,3...) generating phantom positives that
didn't exist in training (FIS/BR 5/15 case: 1-min score 0.91 → 5-min score 0.17).

### Performance impact
- Pipeline consistency: 10/10 (was diverging, live -81% over 4 weeks)
- WF rebaselined: +1931% honest (was +1188% inflated pre-fix)

### Migration
- All v1.x.x models DEPRECATED (trained on different VWAP)
- Pkl rebuilt with HLC/3 + label_eod_green_v2 in `_add_market_labels`
- Live engine reads new 5-min snap mfo

---

## [v1.9.0] — 2026-05-14 (Step 19 — 5/14-5/15 LIVE PRODUCTION) ⚠️

### Status
**LEGACY rollback target** — reconstructed 2026-05-18 from commit `26a75e5`.
**Identified as ACTUAL 5/14-5/15 production commit** (was on master HEAD during those trading days).
**KNOWN BUG**: pre-pipeline-fix (live ≠ training, phantom positives on 1-min snap).

### Config (exact match to 5/14-5/15 live)
- 1-min scan snap (off-boundary mfo: 1, 2, 3...)
- VWAP formula: close-weighted `sum(c × v) / sum(v)`
- **Z1: `label_z12_market_3dd`** ✓
- **Z2: `label_eod_green_v2`** ✓
- **Z3/Z4: `label_z34_market`** ✓
- Z4 hard SL -3%
- `Z4_DIP_FILTER = 0.005` (looser)
- Top-1 by `win_p` (no R9)
- HPs: defaults from Step 16 (no Optuna)

### Live picks on 5/14-5/15 (for reference)
- 5/14: AVGO, F, HPE, MRVL, APO, NVDA, ARES
- 5/15: WDAY, FIS, BR, DVN, ZS, MSFT

### Reconstruction (2026-05-18)
- Built via git worktree at commit `26a75e5` (Step 19 — ACTUAL 5/14 production commit)
- pkl rebuilt with data ≤ 2026-05-13 (matches what 5/14 retrain used)
- Market labels patched in manually (worktree feature_builder had bug with full-DF processing)
- Models trained with Step 19 config (proper labels per zone)
- Artifacts: `backtests/models_prod_v22_v1.9.0/` (137 files, 50MB) + `features_v1.9.0.pkl` (1.6GB)

### Note: v1.8.0 was incorrect
Initially tagged at `a5bd6a7` (Step 18) but actual 5/14 production was Step 19 deployed at
05:32 ET 5/14 morning (before market open). v1.8.0 has been removed and replaced with v1.9.0.

### Rollback usage
```bash
bash scripts/rollback.sh v1.9.0 --dry-run   # preview
bash scripts/rollback.sh v1.9.0             # interactive
```

### ⚠️ Warnings
- Pipeline bug returns (live ≠ training, phantom positives on 1-min mfo)
- FIS 0.91 → 0.17 type mismatch will recur
- Random seeds may produce slightly different model bytes than original 5/14 (LightGBM parallel)
- Training data has minor updates between 5/14 and reconstruction date
- DO NOT use unless explicit forensic need / regression test
- Production WAS profitable on 5/14-5/15 but BUGGY across longer window (-81% Apr-May overall)

---

## [v1.x.x] — pre-2026-05-16 (Step 6-19, DEPRECATED)

Old era — pipeline buggy, live performance diverged from WF.
- Live Apr-May: -81% (vs WF claimed +1188%)
- DO NOT use v1.x.x WF numbers as baseline (except v1.8.0 reconstructed above)
- Models incompatible with v2.x.x pipeline

Kept in git for historical reference only.

---

## Version policy

### When to bump MAJOR (x.0.0):
- Pipeline change forcing model incompatibility
- Feature schema change (add/remove columns)
- Training data range/universe change
- Validation methodology change

### When to bump MINOR (x.y.0):
- New ML label or model
- Hyperparameter retune (Optuna, grid search)
- Ranking formula change
- New filter (Z4 dip, etc.) requiring retrain

### When to bump PATCH (x.y.z):
- Threshold tweak (no retrain)
- Filter parameter change (e.g., dip 0.5% → 0.9%)
- SL on/off
- Bug fix in pick logic
- Cron timing change

### Tag format
- `v2.2.0` (main tag)
- `v2.2.0-step26` (with step number, optional)
- Push to remote: `git push origin --tags && git push github --tags`
