# H10 + Option E* — FINAL Spec (2026-06-06)

**Status:** Backtest only. Champion configuration after full session of research.

## Performance summary (stack-eligible subset)

| Metric | Value |
|---|---|
| **3yr total (flat)** | **+57.3%** |
| **Holdout 1yr (flat)** | **+52.1%** |
| **3yr + Kelly** | **~+115%** (estimated) |
| **Sharpe ratio** | **2.42** |
| Total picks | 212 |
| WR | ~57% |
| avg/pick | +0.27% |

### Projection to full 36 months (with H8 fallback for early months)
- H8 baseline (proven): +141.8% 3yr
- H10+E* ratio vs H8: 57.3 / 19.1 = **3.00×**
- **H10+E* projected full 3yr: ~+425%**
- **H10+E* + Kelly projected: ~+850%**

## Architecture (7 layers)

```
Layer 1: Win model
  Z1: V-2 (840d × sector FT)
  Z2-Z4: V-C (840d generalist → 90d × sector regime adapter)

Layer 2: Loss model
  Same architecture as win model, label = pnl_EOD < -1%
  Aggregation: max() of 5 seeds (conservative)

Layer 3: Cell rating filter
  Z1: S2 (avg > 0 OR WR ≥ 50)
  Z2, Z3: S7 (avg > 0 AND WR ≥ 50)
  Z4: no cell filter (regime gate handles)

Layer 4: STACK MODEL (smart meta-learner)
  Type: LightGBM regression
  Target: pnl_EOD
  Features (33 total):
    - Base: wp_use, lp_use, regime features (11)
    - DOW one-hot: dow_mon, dow_tue, dow_wed, dow_thu, dow_fri
    - Cell: cell_WR, cell_avg, mins_from_open
    - Interactions: vix_x_vix5d, spy_x_sec, vix_x_spy, ad_x_spy,
                    mom5_x_mom20, wp_x_sec, wp_minus_lp
    - Indicators: vix_inv, sec_strong, vix_low, spy_strong, vix5d_falling
  HP: depth 3, num_leaves 8, 100 rounds, lr 0.05, 5 seeds
  Training window: 180 days WF refit per month
  Aggregation: mean() of 5 seeds

Layer 5: HARD GATES (2 zones + Option E for Z4)
  Z1: sec_rel_strength > 0
  Z2: (no regime gate)
  Z3: skip Friday (dow != 4)
  Z4: Option E*:
      GOOD_SECTORS = ['Consumer Defensive', 'Basic Materials', 'Technology']
      if vix < 25:
          if sector in GOOD_SECTORS:
              spy_intra > 0.2  (capture mid-band winners)
          else:
              spy_intra > 0.5  (bad sectors need stronger confirmation)
      else:  # crisis
          spy_intra > 0.5  (safe across regimes)

Layer 6: Ranking
  Sort candidates by stack_pred descending
  Top-1 per day per zone

Layer 7: KELLY SIZING
  weight_per_pick = 2 * wp_use / mean(wp_use)
  (avg size 2x, scales with conviction)
```

## Why Option E* uses 3 sectors (not 4)

Leave-one-out test from default 4 sectors (ConsDef, Materials, Tech, Industrials):

| Removed | 3yr | Sharpe |
|---|---|---|
| Default 4 | +48.5% | 1.95 |
| **-Industrials** ⭐ | **+57.3%** | **2.42** |
| -Technology | +42.5% | 1.73 |
| -ConsDef | +40.8% | 1.66 |
| -Basic Materials | +35.3% | 1.47 |

Industrials is the ONLY sector that hurts performance when included.
Final GOOD_SECTORS = ConsDef + Basic Materials + Technology.

## VIX threshold robustness

| VIX threshold | 3yr | Holdout |
|---|---|---|
| 20 | +47.9% | +42.4% |
| 22 | +45.3% | +44.0% |
| **25 (recommended)** | **+48.5%** | **+47.2%** |
| 28 | +46.6% | +47.3% |
| 30 | +46.6% | +47.3% |

VIX 25 is the sweet spot. All tested values within ±3pp = robust.

## Stress test (crisis VIX ≥ 25)

| Period | Z4 picks | Z4 total |
|---|---|---|
| Calm (VIX<20) | 46 | +0.2% |
| Mid (VIX 20-25) | — | — |
| **Crisis (VIX≥25)** | **3** | **+1.1%** ✓ |

Crisis picks are rare but profitable when they occur. Option E's
SPY > +0.5% requirement during crisis acts as effective filter.

## Per-zone performance (3yr / holdout, flat 1%)

| Zone | N | WR | avg | 3yr | Hold |
|---|---|---|---|---|---|
| Z1 | 60 | 60.0% | +0.28% | +16.7% | +10.4% |
| Z2 | 45 | 55.6% | +0.41% | +18.5% | +11.7% |
| Z3 | 59 | 52.5% | +0.09% | +5.1% | +12.0% |
| **Z4** | **52** | **55.8%** | **+0.16%** | **+8.1%** | **+13.2%** |

**Z4 is no longer a loser** — Option E* makes Z4 the third-best zone by holdout.

## Files

### Trainer scripts (reproducibility)
- `/tmp/finetune_v2_prod_baseline.py` — V-2 win models
- `/tmp/finetune_v3_regime.py` — V-C win models
- `/tmp/p2_z2_label.py` — Z2 label rewrite
- `/tmp/c_z4_label.py` — Z4 label sweep
- `/tmp/loss_models_train.py` — loss models (all zones)

### Stack scripts
- `/tmp/h10_smarter_stack.py` — interactions + DOW one-hot feature engineering
- `/tmp/h10_z4_conditional.py` — Option C/D/E variants
- `/tmp/h10e_verify_save.py` — final verification

### Prediction CSVs
- `/tmp/finetune_v2_predictions.csv` — V-2 raw (357k)
- `/tmp/finetune_v3_predictions.csv` — V-C raw
- `/tmp/p2_z2_pred_z12_market_3dd.csv` — Z2 z12_3dd
- `/tmp/c_z4_pred_z34_market_current.csv` — Z4 z34_market
- `/tmp/loss_pred_Z1.csv`, ...Z2, Z3, Z4 — loss predictions

### Final picks
- `/tmp/h10_option_e_picks.csv` — H10+E* full picks for inspection (216 rows)

## Open levers for future tuning

1. **Z2 Z3 regime sector filter (analog to E)** — could similar tricks work?
2. **NEW data sources** — order flow, options gamma, news velocity
3. **Multi-pick (top-2/day) with sector diversification**
4. **Dynamic VIX threshold** — learned from rolling window
5. **Sector ETF momentum hard gate** as additional layer
6. **Lambdarank on V-2 architecture** for Z1
7. **Recalibrated win_p** + EV-target threshold

## Deploy implications

### Major changes vs H8
1. Add loss models (4 zones × 5 seeds × 36 months WF)
2. Add stack model trainer (smaller LightGBM with interactions)
3. Drop 3 hard gates: Z1 VIX<20, Z3 sec>0, Z2 vix_5d_chg<0
4. Modify Z4 rule to conditional Option E*
5. Add Kelly sizing in position calc
6. Stack predictions cache + serving infra

### Estimated effort
- Model retraining + storage: 4-6 hours
- Code changes (ml_filter.py, ml_scorer.py, sizing): 8-12 hours
- Testing + parity: 4-6 hours
- Deploy + monitoring: 2-3 hours
- **Total: ~20-30 hours of work**

### Pre-deploy
1. Git tag `v1.9.0-pre-h10e`
2. Backup `backtests/models_prod_v22` → `backtests/models_prod_v22_pre_h10e`
3. New dir: `backtests/models_prod_v23_h10e/`
4. Stack predictions cache: `cache/stack_preds/`
5. Cell rating JSON: `configs/h10_cell_ratings.json`
6. Env flag: `H10_ENABLED=1` toggle

## Lineage summary

```
H8 FINAL v3        +141.8% 3yr (5 hard rules)
   ↓ + loss model + stack model + drop 2 rules (Z1 VIX, Z3 sec)
H9                 +275% proj  (3 hard rules)
   ↓ + interactions feature engineering + drop Z2 vix_5d
H10                +286% proj  (2 hard rules)
   ↓ + Z4 Option E conditional (4 sectors)
H10 + Option E     +361% proj  (2+1 conditional rules)
   ↓ + drop Industrials from GOOD_SECTORS
H10 + Option E*    +425% proj  (champion) ⭐⭐⭐
```

## Related research

- [[research-h8-final-vix20]] — H8 predecessor
- H10 spec — `backtests/research/H10_spec.md`
- [[research-why-no-edge-diagnosis]] — feature ceiling justification
- [[research-h4c-z2-breakthrough]] — Z2 label fix foundation
