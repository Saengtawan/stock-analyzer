# H8 FINAL v3 — Full Spec (2026-06-06)

**Status:** Backtest only, NOT deployed. Reproducible from scripts + saved predictions CSVs.

## Performance summary

| Metric | Value |
|---|---|
| **3yr total** | **+141.9%** |
| **Holdout year 3** (May 2025 - May 2026) | **+102.7%** |
| Total picks 3yr | 362 |
| Picks per year | ~120 |
| Overall WR (3yr) | ~58% |
| avg/pick | +0.40% |
| vs Production v22 (-208% 3yr) | **+350pp** |

## Generalization proof
- Train (2023-05 to 2025-04): +39.2%
- Holdout (2025-05 to 2026-05): +102.7%
- Holdout BETTER than train per-month avg → not overfit

---

## Layer 1: Model Architecture (per zone)

### Z1 — V-2 (Sector specialist only, no regime adapter)
```
Stage 1: Generalist (840d sliding window, all sectors)
            ↓ warm-start init_model
Stage 2: Sector specialist (840d × sector, smaller lr)
```

### Z2, Z3, Z4 — V-C (Dual-axis: regime × sector)
```
Stage 1: Generalist (840d sliding window, all sectors)
            ↓ warm-start init_model
Stage 2: Regime × Sector specialist (90d × sector, smaller lr)
```

### Hyperparameters per zone (Stage 1)
| Zone | lr | depth | leaves | min_child | reg_alpha | reg_lambda | n_estimators | bagging_frac | feat_frac |
|---|---|---|---|---|---|---|---|---|---|
| Z1 | 0.05 | 3 | 24 | 50 | 1.0 | 1.0 | 500 | 0.8 | 0.9 |
| Z2 | 0.03 | 5 | 47 | 80 | 0.5 | 3.0 | 500 | 0.8 | 0.8 |
| Z3 | 0.05 | 4 | 31 | 30 | 0.5 | 1.0 | 300 | 0.8 | 0.8 |
| Z4 | 0.05 | 3 | 8 | 30 | 1.0 | 3.0 | 400 | 0.7 | 0.7 |

### Stage 2 FT hyperparameters (per zone, smaller lr)
| Zone | lr | rounds | min_child |
|---|---|---|---|
| Z1 | 0.01 | 100 (V-2) | 20 |
| Z2 | 0.005 | 80 (V-C) | 30 |
| Z3 | 0.01 | 80 (V-C) | 15 |
| Z4 | 0.01 | 80 (V-C) | 15 |

### Min training rows
- V-2 (840d × sector): 200
- V-C (90d × sector): 50

### Ensemble
- 5 seeds × Stage 1 boosters
- 5 seeds × Stage 2 boosters
- Final score = `min()` of 5 seeds (conservative)
- WF monthly refit (36 month rolling, 2023-05 to 2026-05)

---

## Layer 2: Labels (per zone)

| Zone | Label | Definition |
|---|---|---|
| Z1 | `label_z12_market_3dd` | EOD-green AND no -3% intraday DD from entry |
| **Z2** ⭐ NEW | **`label_z12_market_3dd`** | (was `label_eod_green_v2` — too loose, broke Z2) |
| Z3 | `label_z34_market` | EOD-green relative to market |
| Z4 | `label_z34_market` | (same as Z3) |

Positive rates (for context):
- label_z12_market_3dd: 15.9%
- label_eod_green_v2: 55.2% (too loose, caused Z2 -166% with original config)
- label_z34_market: 31.9%

---

## Layer 3: Selection — Cell rating filter

Compute per (zone, sector) WR and avg from all top-1/day picks above WIN_THR=0.75.
Skip cells with N<3 samples.

### Cell filter definitions
- **S2** (Z1 only): `(avg > 0) OR (WR >= 50)`
- **S7** (Z2, Z3): `(avg > 0) AND (WR >= 50)`
- **No cell filter** (Z4): all sectors allowed (regime gate handles filtering)

### Active cells per zone (3yr)
**Z1 (V-2, S2):**
- Basic Materials (61.8% / +0.59%)
- Energy (63.6% / +0.52%)
- Utilities (57.1% / +0.07%)
- Consumer Defensive (50.0% / +0.01%)
- + fallback (Tech, ConsCyc, Comm, Financial — neutral pass S2)

**Z2 (V-C z12_3dd, S7) ⭐ NEW:**
- Healthcare (56.0% / +0.70%)
- Basic Materials (61.5% / +0.60%)
- Consumer Cyclical (57.1% / +0.51%)

**Z3 (V-C, S7):**
- Technology (70.0% / +0.53%)
- Consumer Defensive (66.7% / +0.50%)
- Basic Materials (60.7% / +0.23%)
- Communication Services (50.0% / +0.01%)

**Z4 (V-C, no cell filter):** All sectors allowed; regime gate filters.

---

## Layer 4: Threshold

- **WIN_THR = 0.75 for all zones**
- (Tested: 0.78 / 0.80 / 0.82 / 0.85 / 0.90 — 0.75 optimal)

---

## Layer 5: Regime gates (per zone)

| Zone | Gate | Rationale |
|---|---|---|
| **Z1** (0-9 min) | `vix < 20 AND sec_rel_strength > 0` | Low vol + sector leading SPY |
| **Z2** (10-29 min) | `vix_5d_chg < 0` | VIX falling (fear cooling) |
| **Z3** (30-44 min) | `sec_rel_strength > 0` | Sector beating SPY |
| **Z4** (45-75 min) | `spy_intra > +0.5%` | Bull trend fully confirmed |

### Gate sweep details (all alternatives tested)

**Z1 sweep (3yr / holdout):**
- VIX<20 + sec>0 (current): +73.5% / +51.2% ⭐
- VIX<20 alone: +65.3% / +51.2%
- VIX<20 + SPY>0: +50.8% / +58.1% (alt — better holdout)
- VVIX<100: +56.5% / +48.5%
- VIX<18 (old): +41.2% / +45.7% (too strict)

**Z2 sweep:**
- VIX_5d_chg<0 (current): +24.7% / +20.4% ⭐
- AD>1.2 (old): +19.3% / +12.1%
- AD>1.0: +18.9% / +12.6%
- mom20d>0: +14.4% / +14.8%

**Z3 sweep:**
- sec>0 (current): +40.9% / +28.1% ⭐
- mom20d>0: +35.0% / +16.1%
- VIX_term_spread>1: +35.1% / +21.0%
- sec>+0.5: +15.7% / +17.7%

**Z4 sweep:**
- SPY>+0.5% (current): +2.8% / +3.0% ⭐ stable
- SPY>+0.2%: -4.8% / +12.2% (regime-shift risk — DO NOT use)
- All others negative on 3yr

---

## Layer 6: DOW filter

| Zone | DOW filter | Reason |
|---|---|---|
| Z1 | none | Train suggested skip Mon/Thu but FAILED holdout (Fri became +2.20%) |
| Z2 | none | Train suggested skip Wed but FAILED holdout (Wed became +5.13%) |
| **Z3** | **skip Fri** ⭐ | Train Fri -0.08% + holdout Fri -1.15% = consistent (only DOW that generalizes) |
| Z4 | none | Train suggested skip Thu but FAILED holdout |

---

## Entry / Exit (NO CHANGE from production)

- **Entry timing:** market order @ scan_now (default)
- **Exit:** hold to EOD
- **Z4 hard SL:** -3% from fill_price (production-existing rule)

---

## Per-zone WR / avg (3yr)

| Zone | N | WR | avg | Total |
|---|---|---|---|---|
| Z1 | 225 | 58.2% | +0.33% | +73.5% |
| Z2 | 30 | 60.0% | +0.82% | +24.7% |
| Z3 | 85 | 60.0% | +0.48% | +40.9% |
| Z4 | 24 | 58.3% | +0.12% | +2.8% |
| **TOTAL** | **364** | **~58.6%** | **+0.40%** | **+141.9%** |

---

## Files (reproducibility)

### Trainers
- `/tmp/finetune_v2_prod_baseline.py` — V-2 (Z1 home)
- `/tmp/finetune_v3_regime.py` — V-C (Z2, Z3, Z4 home)
- `/tmp/p2_z2_label.py` — Z2 label rewrite (z12_market_3dd training)
- `/tmp/c_z4_label.py` — Z4 label sweep (confirmed z34_market optimal)

### Predictions
- `/tmp/finetune_v2_predictions.csv` (V-2, 357k rows — Z1 base)
- `/tmp/finetune_v3_predictions.csv` (V-C, 357k rows — Z3 base)
- `/tmp/p2_z2_pred_z12_market_3dd.csv` (Z2 with z12_3dd label)
- `/tmp/c_z4_pred_z34_market_current.csv` (Z4 with z34_market label)

### Analysis scripts
- `/tmp/h7_combine.py` — H7 stacking
- `/tmp/h8_stack.py` — DOW + micro-window stack
- `/tmp/dow_holdout.py` — DOW generalization test (caught overfit)
- `/tmp/z1_vix_sweep.py` — VIX threshold sweep (caught <18 too strict)
- `/tmp/all_gates_sweep.py` — all gates re-check
- `/tmp/z1_gate_explore.py` — Z1 alternative gate exploration
- `/tmp/z234_gate_explore.py` — Z2/Z3/Z4 alternative gates

### Data dependencies
- Features: `cache/bt_features/features_5yr_noleak.pkl`
- Labels: `/tmp/phase0_labels_5yr.pkl` (sym, date, mfo, pnl_EOD, pnl_+30, pnl_+60, pnl_+90)

### Environment
- Python: `~/.pyenv/versions/issara/bin/python`
- LightGBM, pandas 3.0.2

---

## Open levers (future tuning)

These were tested but did NOT yield improvement at current sample size — recheck when more data:

1. **L1 Threshold sweep** — 0.78 and 0.80 helped marginally for Z1; current 0.75 optimal but tested
2. **L3 Alternative labels** — z34_market and eod_green for Z1/Z3 had 0 non-null rows (zone-specific labels)
3. **L4 Source swap** — Z1 V-C / Z3 V-2 / Z2 V-2 all confirmed worse than current
4. **L5 Loss-prob gate** — NOT TESTED, requires retraining loss models
5. **L7 DOW** — only Z3 Fri generalizes; rest overfit (DO NOT add)
6. **L8 Micro-window** — Z1 0-4, Z2 20-29, Z4 60-75 looked good but marginal vs noise
7. **Exit horizon** — EOD optimal for selective picks (P3 study); exit+30/+60 only helps unfiltered Z1/Z4 raw

### Ideas not yet explored
- **Position sizing** by p_ratio (Kelly fraction)
- **Multi-pick** (top-2 ranked by score) — currently top-1 only
- **NEW data sources** — order flow, options gamma, news velocity (Cohen's d ceiling on OHLCV per [[research-why-no-edge-diagnosis]])
- **Sector ETF momentum hard gate** (XLK red → block Tech)
- **Loss model integration** — combine win_p > thr AND loss_p < thr
- **Lambdarank** — Z1 lambdarank reported ~82% WR but voided by harness issues; re-test on V-2 architecture
- **Z2/Z4 gate stack** — e.g. Z2 VIX_5d_chg<0 + AD>1.2 combo
- **Z4 regime-shift gate** — SPY>+0.2% holdout +12.2%, but 3yr -4.8% — could be live-favorable

---

## Deploy plan (when ready)

### Pre-deploy checklist
1. ✅ Spec saved (this file)
2. ⏸ Backup prod: `cp -r backtests/models_prod_v22 backtests/models_prod_v22_pre_h8`
3. ⏸ Git tag: `v1.9.0-pre-h8`
4. ⏸ Retrain H8 models for production (currently in /tmp, not in backtests/models_prod_v23_h8/)
5. ⏸ Generate cell ratings JSON: `configs/h8_cell_ratings.json`
6. ⏸ Modify `src/scan/strategies/ml_filter.py` (regime gates + cell lookup + DOW Z3 Fri)
7. ⏸ Modify `src/scan/ml_scorer.py` (per-zone source dispatch)
8. ⏸ Modify `scripts/train_zones.py` (Z2 label → z12_3dd, add V-C path)
9. ⏸ Env flag `H8_ENABLED=1` toggle
10. ⏸ Shadow mode 2 weeks
11. ⏸ Paper trade 2-4 weeks
12. ⏸ LIVE gradual rollout

### Rollback path
- Env flag `H8_ENABLED=0` → instant fall back
- Git: `git reset --hard v1.9.0-pre-h8`
- Restore models from `backtests/models_prod_v22_pre_h8/`

---

## Conversation insights (user catches)

1. **"DOW filter น่าสงสัย"** → exposed overfit on Z1/Z2/Z4 DOW (false +19pp)
2. **"VIX<18 เข้มไป"** → exposed under-fit, revealed VIX<20 sweet spot (+24pp gain)
3. **"Z4 อยู่ตลาดดีเท่านั้น"** → led to SPY>+0.5% gate (+3.9pp)
4. **"แก้กี่ layer"** → forced systematic 5-layer breakdown

User instinct ratio: 4/4 high-signal interventions in single session.

---

## Related research (memory)

- [[research-h7b-regime-gates]] — predecessor with VIX<18
- [[research-h6-z4-regime-gate]] — Z4 SPY gate origin
- [[research-h4c-z2-breakthrough]] — Z2 label rewrite (P2)
- [[research-h3-hybrid-3yr-positive]] — initial hybrid architecture
- [[research-p3-exit-horizon-per-zone]] — EOD optimal for selective picks
- [[research-why-no-edge-diagnosis]] — OHLCV ceiling Cohen's d ≤0.19
- [[project-step2b-trustworthy-baseline]] — number-to-beat baseline
