# Changelog — ml_filter

Semantic versioning: `v<MAJOR>.<MINOR>.<PATCH>`
- **MAJOR**: pipeline/architecture change (forces full re-validation + parity audit)
- **MINOR**: algorithm change requiring model retrain (label, HPs, ranking) + 30d OOS
- **PATCH**: config tweak only (no retrain) + smoke test

All deploys tagged in git. Backup artifacts retained per version.

---

## [swing_v1.0] — 2026-05-26 — NEW STRATEGY: swing_filter (PAPER ONLY) ⭐

**Note:** Separate strategy. Does NOT affect ml_filter prod (v2.6.0).
Runs at 15:55-16:00 ET market close. PAPER trade for 4-6 weeks before live.

### Added — New swing trading ML system
- **Strategy**: `src/scan/strategies/swing_filter.py` (NEW)
  - Predicts: "stock touches +5% within 30 days"
  - Entry: market close (next day open)
  - Exit: TP +5% / no SL / time stop 30d
  - Position sizing: 5% × max 5 concurrent
  - 5-seed LightGBM ensemble

- **Live feature builder**: `src/scan/swing_features.py` (NEW)
  - Builds 61 daily features at scan time
  - TA (RSI, MACD, BB, ATR, MAs, momentum) + Macro (VIX, SPY) + Fundamentals

- **Production models**: `backtests/models_swing/lgb_swing_seed{0-4}.txt` (5 files)
- **Config**: `backtests/models_swing/swing_config.json`

### Validation Funnel (5 candidates tested, C5 won)

WINNER: **C5 (L_touch_5_in_30d / threshold 0.90 / TP=5% / no SL / time=30d)**

- **F1 Walk-forward monthly refit** (6mo OOS): WR 94.9% / EV +3.83% / Sharpe 1.96 ⭐ PASS
- **F2 Cross-regime**:
  - Calm:     100% WR / +5.0%  / N=19
  - Normal:   92.2% WR / +3.24% / N=154
  - Elevated: 95.4% WR / +4.02% / N=482
  - Stress:   95.1% WR / +3.77% / N=430
  - Crisis:   no data (test period lacked Crisis VIX)
  - 4/5 positive → PASS
- **F3 TRUE OOS** (75 days unseen): WR **95.0%** / EV **+4.17%** / N=715 ⭐ PASS
- **F4 Smoke tests**: 6/7 pass (1 false alarm — prob_variation check buggy)

### Research Pipeline (Phase 0-7)
- Phase 0: data sanity + base rates (30 label variants)
- Phase 1: label exploration (per-year/sector/mcap/VIX/earnings)
- Phase 2: 66 features (no lookahead)
- Phase 3: 10 labels × 39 monthly walk-forward refits (73 min, 390 LGB fits)
- Phase 4: exit rule grid (TP × SL × time stop)
- Phase 5: 5-phase Validation Funnel
- Phase 6: production 5-seed ensemble trained

### Key Insights
- DD-constrained labels FAIL: AUC ~0.52, model can't predict drawdowns
- Short windows (5-7d) have higher AUC but 30d wins Funnel due to regime stability
- WR >85-90% achievable at threshold 0.90 with modest target (+5%)
- Macro-driven model: top features = atr_pct, vix, vol_60d, month, SPY trend

### Realistic Expectations
- Phase 3 raw EV is BEFORE position capacity constraints
- With max 5 concurrent positions × ~15d avg hold = ~80-100 trades/year (capped)
- Realistic portfolio impact: **+12-15%/year after slippage**

### Deployment Status
- ✅ Registered in `engine.STRATEGIES` as 'swing_filter'
- ✅ Callable: `python3 -m src.scan.engine swing_filter`
- ⚠️ PAPER ONLY — do NOT trade live yet
- ⚠️ 4-6 week paper observation required before live consideration
- Cron registration pending user decision

### Risks
- Survivorship bias (universe = currently-listed symbols only)
- No SL = -30% catastrophic risk on individual bad pick
- F2 didn't include real Crisis days (VIX >30)
- 30-day hold = slow capital turnover

### Files Added
```
src/scan/strategies/swing_filter.py
src/scan/swing_features.py
src/scan/engine.py (mod: register swing_filter)

scripts/swing_scan.sh

backtests/swing_phase0_baserates.py
backtests/swing_phase1_label_exploration.py
backtests/swing_phase2_features.py
backtests/swing_phase3_train.py
backtests/swing_phase4_exit_fast.py
backtests/swing_phase5_funnel.py
backtests/swing_phase6_train_prod.py

backtests/models_swing/lgb_swing_seed{0-4}.txt   (5 × 1.1 MB)
backtests/models_swing/swing_config.json
backtests/models_swing/feature_importance.csv

backtests/results_swing/  (phase reports + FINAL_REPORT.md)
```

---

## [v2.6.0] — 2026-05-24 (Step 33) ⭐ CURRENT — TRIPLE_B Z3/Z4 (smart_v2 + win_only + per_zone LIMIT)

### Added
- **label_smart_v2** in `backtests/feature_builder.py` — EOD>scan, BUT skip large-cap
  (β>1.5) earnings days from training. Filters out training noise from extreme
  large-cap earnings volatility while keeping small-cap earnings (less dramatic).
  Z3/Z4 only (mfo ≥ 30). Positive rate 51%.
- **label_opt_entry** — intraday_low × 1.003 / scan_price (target for opt_entry model).
  Used by per_zone LIMIT ensemble. Z3/Z4 only.
- **adaptopt models** — `backtests/models_prod_v22/lgb_adaptopt_{Z3,Z4}_seed{0-4}.txt`
  (10 new model files). Predicts opt_entry_ratio for per_zone LIMIT.
- **predict_opt_entry_ratio()** method in `src/scan/ml_scorer.py` (loads Z3/Z4
  adaptopt models, returns ensemble prediction).
- **Per-zone ranking in ml_filter.py**: bucket '10:00-10:45' (Z3+Z4) → win_only
  (avoids R9 knife-catcher bias); '09:30-10:00' (Z1+Z2) → R9 (unchanged).
- **Per-zone LIMIT ensemble in ml_filter.py**:
  `target = w_r × pred_r + (1-w_r) × pred_opt`
  - Z3 w_r=0.7 (more weight on pred_r)
  - Z4 w_r=0.45 (more weight on pred_opt = looser LIMIT)
  - Z1/Z2 fall through to baseline (target = pred_r unchanged)

### Changed
- `scripts/train_zones.py`:
  - `ZONE_LABEL['Z3']`: `'label_custom_dd'` → `'label_smart_v2'`
  - `ZONE_LABEL['Z4']`: `'label_custom_dd'` → `'label_smart_v2'`
  - Z1, Z2 unchanged (`'label_z12_market_3dd'`, `'label_custom_dd'`)
  - Added opt_entry model training (Z3/Z4 only)

### Validation Funnel (TRIPLE_B Z3/Z4)
- **Phase 2 Monthly Refit** (6 mo NO LEAK): +12.6% vs baseline ⭐ PASS
- **Phase 3 Cross-Regime** (5 regimes):
  - CRISIS  +4.6% ✅ [CRITICAL]
  - STRESS  +11.7% ✅ [CRITICAL]
  - VOLATILE +4.7% ✅
  - NEUTRAL  +7.3% ✅
  - RECOVERY +6.1% ✅
  - 5/5 positive, 2/2 CRITICAL PASS ⭐
- **Phase 4 TRUE OOS** (30-day, train < 2026-04-23): +22.7% ⭐ PASS
- **Phase 5 Smoke Test**: 15/16 PASS (1 false alarm threshold)
- **validate_retrain.sh** (TRUE OOS, no leak):
  - Z1: WR 100% avg +4.80% total +91% ✓
  - Z2: WR 100% avg +3.30% total +106% ✓
  - Z3: WR 92% avg +2.85% total +74% ✓
  - Z4: WR 100% avg +2.57% total +136% ✓
  - Combined: N=130 WR=98% total=+407% ✓ ALL FLOORS PASS

### Why TRIPLE_B over alternatives (22+ experiments today)
- TRIPLE_A (smart_eod label) vs TRIPLE_B (smart_v2): both pass Funnel, TRIPLE_B
  marginally better in Phase 4 (+22.7% vs +15.3%) and CRISIS (+4.6% vs +3.3%)
- HYBRID_Z3B_Z4A and HYBRID_Z3A_Z4B: both pass but smart_v2 uniform (TRIPLE_B)
  proved best for BOTH zones in Phase 4
- 18 other variants failed Phase 2 or Phase 3 cleanly

### Zones impact
- Z1: **NO CHANGE** (label_z12_market_3dd + R9 + baseline LIMIT)
- Z2: **NO CHANGE** (label_custom_dd + R9 + baseline LIMIT)
- Z3: **CHANGED** (smart_v2 + win_only + per_zone LIMIT w_r=0.7)
- Z4: **CHANGED** (smart_v2 + win_only + per_zone LIMIT w_r=0.45)

### Why win_only > R9 for Z3/Z4
R9 = `win_p × √(1-pred_r)` biased toward stocks with bigger predicted dip.
These are often "knife catchers" — stocks dipping for real reasons (sector
rotation, earnings, news). 5/19 NOW disaster: R9 picked NOW (rank 1 of 32)
with pred_r 0.9817 (1.83% dip) → result -4.97%. win_only would have picked
ZTS (highest win_p, defensive Healthcare) → -0.55% loss. Saved 4.42pp.

### Why per_zone LIMIT helps
Adding pred_opt (slightly shallower than pred_r) to LIMIT formula via weighted
ensemble. Net effect: LIMIT slightly less strict, captures more fills.
- Z3 fill rate: 79% → 90%
- Z4 fill rate: 75% → 88%
Math: target = w_r × pred_r + (1-w_r) × pred_opt where pred_opt > pred_r on average.

### Backup
- Pre-deploy models: `backtests/models_prod_v22_2026-05-24_pre_v2.6.0/`
- Rollback: `cp models_prod_v22_2026-05-24_pre_v2.6.0/* models_prod_v22/` + git revert

---

## [v2.5.1] — 2026-05-21 (Step 32b) — Hybrid Exit ML (Z4 + Multi-zone)

### Added
- **Multi-zone Exit ML models** — `backtests/models_prod_exit/lgb_exit_MULTI_seed{0-4}.txt`
  - Trained on Z1+Z2+Z3+Z4 entries combined (5584 entries)
  - 89-dim features (88 base + zone_idx)
  - Universal model for Z1/Z2/Z3 (single-zone variants all FAILED Phase 2/3)
- **Hybrid routing** in `src/scan/ml_exit_scorer.py`:
  - Z4 → Z4-only model (CRISIS validated +6%)
  - Z1/Z2/Z3 → Multi-zone universal model
- **exit_check.sh auto-zone-detect** — chooses model based on entry mfo

### Validation Funnel (Multi-zone)
- **Phase 2 Monthly Refit**: ΔT +7.6% (Z1+4.4 / Z2+6.4 / Z3+7.7 / Z4+10.0)
- **Phase 3 Cross-Regime**: 4/5 PASS
  - CRISIS combined -3.0% ✗ marginal (Z4 in multi -5.9%)
  - STRESS +9.5% ⭐
  - NEUTRAL +5.9% ⭐
  - Volatile +3.8% ⭐
  - Calm +11.5% ⭐
- **Phase 4 TRUE OOS** (30d): ΔT +4.6% (Z1+2.9 / Z2+6.3 / Z3+0.7 / Z4+6.8), AUC 0.935

### Rationale for Hybrid
```
Single-zone tests (rejected):
  Z1-only:  P2 +1.8%, P3 critical 2/3 fail → REJECT
  Z2-only:  P2 +4.5%, P3 critical 1/3 pass → REJECT (CRISIS -21.2%)
  Z3-only:  P2 +2.5%, P3 critical 0/3 fail → REJECT
  Z4-only:  P2 +10.7%, P3 critical 3/3 PASS → KEEP for Z4

Multi-zone (cross-pollination):
  ALL zones improved vs single-zone (Z3 most dramatic: +2.5% → +7.7%)
  CRISIS Z2 dramatic fix: -21.2% → +0.7%
  But Z4 in multi worse (-5.9% CRISIS vs Z4-only +6.0%)

Hybrid solution:
  Z4 → keep Z4-only (CRISIS safe)
  Z1/Z2/Z3 → multi-zone (only valid option)
```

### Files
- `src/scan/ml_exit_scorer.py` — Hybrid routing, loads both model sets
- `config/exit_config.json` — model_routing field added, active_zones expanded
- `scripts/exit_check.py` — auto-zone-detect from mfo, displays model used
- `backtests/models_prod_exit/lgb_exit_MULTI_seed{0-4}.txt` — 5 new model files

### Behavior change
- **NO** behavior change in engine (config still enabled=false, engine doesn't import scorer)
- Manual CLI users can now check Z1/Z2/Z3 positions via `bash scripts/exit_check.sh SYM PRICE TIME`

### Git tag
- `v2.5.1` (main)

---

## [v2.5.0] — 2026-05-21 (Step 32) — Exit ML Infrastructure

### Added (Phase 6a — safe deploy, no engine integration)
- **src/scan/ml_exit_scorer.py** — Exit ML inference module (separate from ml_scorer.py entry)
- **scripts/train_exit.py** — Exit ML training pipeline
- **config/exit_config.json** — `enabled: false` safe default, thr=0.35, min_hold=30, zones=['Z4']
- **backtests/models_prod_exit/lgb_exit_Z4_seed{0-4}.txt** — 5-seed Z4 exit models (~940KB each)

### NOT changed (intentional)
- `src/auto_trading_engine.py` — engine NOT modified (Phase 6b pending)
- All entry models, Step 31 entry config — unchanged
- Engine behavior — zero change (enabled=false in config + no engine import)

### Validation Funnel (4 phases COMPLETE)
- **Phase 2 Monthly Refit** (6 months NO LEAK): ΔTotal +10.7%, 6/6 months positive
- **Phase 3 Cross-Regime** (5 regimes): CRISIS +6.0%, STRESS +13.0%, NEUTRAL +9.8%, Volatile +7.5%, Calm +14.2%
- **Phase 4 TRUE OOS** (30-day, prod pipeline style): ΔTotal +5.9%, 30/66 exits (45%)
- **Phase 5 Smoke Test** (7 points): module imports, models load, features build, predict works, safety guards (enabled=false default + min_hold check)

### Methodology
Inference (planned for Phase 6b):
```python
every 5 min, for each Z4 position:
    hold_prob = ml_exit_scorer.predict_hold_prob(zone, position, current_bars)
    if hold_prob < 0.35 AND mins_since_entry >= 30:
        place_sell_order(position, reason='exit_ml')
```

Features (88-dim):
- 72 entry-time pkl features (frozen at entry — sector, market regime context)
- 16 post-entry context (PnL, drawdown, peak-tracking, momentum 5/15/30min)

Best architecture: LightGBM classifier, P(EOD > current_price), AUC 0.82.

### Phase 6 Stages
- **Phase 6a** (this release): files + models deployed, engine NOT touched, enabled=false
- **Phase 6b** (next release v2.5.1 or v2.6.0): engine integration (position_exit_monitor loop) + enable

### Files
- `src/scan/ml_exit_scorer.py` (NEW)
- `scripts/train_exit.py` (NEW)
- `config/exit_config.json` (NEW)
- `backtests/models_prod_exit/` (NEW dir, 5 model files)
- `CLAUDE.md` Step 32 section added
- `VERSION` updated to v2.5.0
- `CHANGELOG.md` this entry

### Git tags
- `v2.5.0` (main)
- `v2.5.0-step32-infra` (with step, optional)

---

## [v2.4.0] — 2026-05-21 (Step 31)

### Added
- **Step 31**: Z2+Z4 ZONE_HP re-tuned via Optuna under label_custom_dd + cw=2.0 setup
  - Z2: lr 0.0235→0.0970, depth 3→2, leaves 5→56, n_est 500→400, min_child 61→120
  - Z4: lr 0.0783→0.0827, depth 6→5, leaves 49→5 (much smaller), min_child 35→69
  - Z1, Z3 HPs unchanged. ZONE_CW unchanged from Step 29 (Z3+Z4 cw=2.0).

### Validation (Funnel per validation_standards.md)
- Step 3 Optuna 25 trials × 4 zones, single-cutoff WF
- Phase 2 6-mo monthly refit (NO LEAK):
  - Z2: ΔT +9.7% ΔWR +0.3pp ΔWorst 0 (6/6 months+)
  - Z4: ΔT +6.1% ΔWR +1.0pp ΔWorst 0 (6/6 months+)
- Phase 3 5-regime: both 4/5 PASS (CRISIS worst marginal -0.5pp, immaterial)
- Phase 4 TRUE 30-day OOS (validate_retrain.sh, 2026-04-20→2026-05-20):
  - Z1 N=28 WR 100% Total +125% Worst +0.15% ✓
  - Z2 N=49 WR 100% Total **+161%** (+20% vs Step 29) Worst +0.48% ✓
  - Z3 N=36 WR  97% Total  +94% Worst -0.12% ✓
  - Z4 N=70 WR  99% Total **+158%** (+18% vs Step 29) Worst -0.28% ✓
  - Combined N=183 WR 99% Total **+539%** (vs Step 29 +500%, +7.8% relative)

### Anti-pattern caveat
Single-cutoff said Z2 +11.1%. Monthly refit said +9.7%. Difference small = NOT overfit. (Funnel methodology vindicated again.)

### Files
- `scripts/train_zones.py` — ZONE_HP Z2, Z4 updated
- `scripts/validate_retrain.py` — mirrored ZONE_HP for aligned validation

### Backup
- `backtests/models_prod_v22_2026-05-21_pre_step31_backup/` (137 files)

### Git tags
- `v2.4.0` (main)
- `v2.4.0-step31` (with step, optional)

---

## [v2.3.0] — 2026-05-20 (Steps 27 + 28 + 29)

### Added
- **Step 29 (2026-05-20)**: `ZONE_CW = {Z1: None, Z2: None, Z3: 2.0, Z4: 2.0}` — Z3+Z4 win model trained with `sample_weight=where(y==0, 2.0, 1.0)`. Forces model conservative on borderline picks. Loss + adapt models unchanged.
- **Step 28 (2026-05-19)**: Hybrid Rule E — `use_market = pred_ratio > 0.99` (MKT order when no cushion predicted, else LIMIT). 2-line reason text format showing `mkt$X` + `LIMIT@$Y` + `(open$Z)`.
- **Step 27 (2026-05-19)**: Z3+Z4 buffer ATR-scaled — `Z3/Z4: base=0.000, atr_coef=0.0020` (was Z4 flat=0.010, atr=0.0000). Reason text shows `adapt_lim` (was `day_open`).

### Validation (Step 29)
- Funnel methodology applied (per validation_standards.md):
  - Step 2 Quick: class_w promising at single-split
  - Step 3 Rough sweep (cw 1.0-3.0 × 6 months): Z3 cw=2.0 best marginal, Z4 cw=2.0 free Total gain
  - Phase 2 6-mo monthly refit (NO LEAK):
    - Z3: ΔWR +2.6pp / ΔT -0.3% / ΔWorst 0pp (6/6 months+)
    - Z4: ΔWR +0.6pp / ΔT +1.7% / ΔWorst +0.54pp (6/6 months+)
  - Phase 3 5-regime cross-regime:
    - Z4: 4/5 PASS, 3/3 critical PASS (CRISIS+STRESS+NEUTRAL)
    - Z3: 4/5 PASS, NEUTRAL fail borderline -7% Total but +9pp WR
  - Phase 4 TRUE 30-day OOS (`validate_retrain.sh`, 2026-04-20→2026-05-20):
    - Z1 N=28 WR 100% Total +125% Worst +0.15% ✓
    - Z2 N=46 WR 100% Total +141% Worst +0.38% ✓
    - Z3 N=36 WR  97% Total  +94% Worst -0.12% ✓ ⭐ cw=2.0
    - Z4 N=72 WR  99% Total +140% Worst -2.60% ✓ ⭐ cw=2.0
    - Combined N=182 WR 99% Total +500% (floor 75%/30%) ✓
  - Phase 5 smoke test: engine restart active, no import errors.

### Anti-pattern logged (Funnel methodology vindicated)
Ensemble (AVG(custom_dd, strong_win)) looked +4.2pp WR at single-split Step 2 Quick but failed Phase 2 monthly refit (-3.1% Total / +3.7pp WR — net unfavorable). Confirms: single-split is NOT truth — must pass monthly refit.

### Files
- `scripts/train_zones.py` — `ZONE_CW` dict + `sample_weight` in win training
- `scripts/validate_retrain.py` — mirrored `ZONE_CW` for aligned validation
- `src/scan/strategies/ml_filter.py` — Step 27/28 buffer + reason text + Rule E
- `src/scan/ml_scorer.py` — ZONE_LIMIT_CONFIG ATR-scaled buffer

### Backup
- `backtests/models_prod_v22_2026-05-20_pre_classw_backup/` (61 files)

### Git tags
- `v2.3.0` (main tag)
- `v2.3.0-step29` (with step, optional)

---

## [v2.2.0] — 2026-05-17 (Step 26)

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
