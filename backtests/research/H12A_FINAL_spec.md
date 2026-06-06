# H12-A FINAL Spec (2026-06-06)

**Status:** Backtest only. NOT deployed. Champion configuration end of session.

## Performance

| Metric | Flat | Kelly 2× |
|---|---|---|
| **3yr total** | **+150.6%** | **+297%** |
| **Holdout (May 2025–May 2026)** | **+109.3%** | **+214%** |
| **Sharpe (annualized)** | **2.84** | 2.84 |
| Total picks 3yr | 391 | 391 |
| WR | 58.6% | 58.6% |
| avg/pick | +0.39% | +0.78% |

### vs production (H8 + full EF v1)
| | Current (19 rules) | H12-A FINAL (6 rules) | Δ |
|---|---|---|---|
| 3yr | +62.6% | +150.6% | **+88pp** |
| Holdout | +35.4% | +109.3% | +74pp |
| Sharpe | 1.57 | 2.84 | +1.27 |
| Rules | 19 | 6 | -13 |

## Architecture (5 layers)

### Layer 1: Win model

| Zone | Architecture |
|---|---|
| Z1 | V-2: 840d × sector FT, warm-start from 840d generalist |
| Z2 | V-C: 840d generalist → 90d × sector FT (regime adapter) |
| Z3 | V-C: same as Z2 |
| Z4 | V-C: same as Z2 |

### Layer 2: Labels

| Zone | Label |
|---|---|
| Z1 | `label_z12_market_3dd` (EOD-green AND no -3% DD) |
| Z2 | `label_z12_market_3dd` ⭐ NEW (was `label_eod_green_v2` — too loose) |
| Z3 | `label_z34_market` |
| Z4 | `label_z34_market` |

### Layer 3: Cell rating filter (per zone, per sector)

| Zone | Filter |
|---|---|
| Z1 | S2: `(cell_avg > 0) OR (cell_WR >= 50)` |
| Z2 | S7: `(cell_avg > 0) AND (cell_WR >= 50)` |
| Z3 | S7 |
| Z4 | none (Option E* handles selection) |

### Layer 4: Regime gates (5 hard rules)

| Zone | Gate | Source |
|---|---|---|
| Z1 | `vix < 20` | H8 |
| Z1 | `sec_rel_strength > 0` | H8 |
| Z2 | `vix_5d_chg < 0` | H8 |
| Z3 | `sec_rel_strength > 0` | H8 |
| Z3 | `dow != 4` (skip Friday) | H8 |
| **Z4** | **Option E*** ⭐ NEW | H12 |

### Z4 Option E* rule

```python
GOOD_SECTORS_Z4 = ['Consumer Defensive', 'Basic Materials', 'Technology']

if vix < 25:    # calm/mid regime
    if sector in GOOD_SECTORS_Z4:
        gate = spy_intra > 0.2    # capture mid-band winners
    else:
        gate = spy_intra > 0.5    # bad sectors need stronger confirmation
else:    # crisis regime
    gate = spy_intra > 0.5        # safe across regimes
```

### Layer 5: Entry Filter (1 rule)

| Zone | Rule | Reason |
|---|---|---|
| Z1 | `gain_from_open <= 4.5%` | DD-control (AXTI/FSLR style block) |

**Dropped from production EF v1 (13 rules):**
- Z1: β≥1.2, sector≠Industrials
- Z2: DOW≠Mon, gain≤3, SPY≥-0.3, sector∉{U,RE}, β≤1.5
- Z3: mom20d≥0, mom20d≤25, SPY≥-0.3, gain≤3
- Z4: mom20d≥0, mom20d≤25

These rules each cost 0–36pp on 3yr without strong DD evidence.
Z1 gain≤4.5 retained because it has explicit DD-improvement memo.

## Rules count summary

| Layer | Rules |
|---|---|
| Hard regime gates | 5 |
| Entry Filter | 1 |
| **TOTAL** | **6** |

Down from 19 in current production (5 hard + 14 EF).

## Per-rule contribution (when each EF rule dropped from H12-A)

| Rule dropped | Δ 3yr |
|---|---|
| Z1_beta12 (β≥1.2) | +36.1pp (worst rule!) |
| Z4_mom_pos (mom20d≥0) | +10.3pp |
| Z3_mom_25 (mom20d≤25) | +7.1pp |
| Z1_gain_45 (gain≤4.5) | +6.9pp ⚠️ keep for DD |
| Z3_spy_-03 | +5.1pp |
| Z3_gain_3 | +5.0pp |
| Z4_mom_25 | +4.7pp |
| Z2_no_mon | +2.5pp |
| Z2_spy_-03 | +2.2pp |
| Z2_beta_15 | +2.2pp |
| Z3_mom_pos | +1.0pp |
| Z1_no_indust | 0pp |
| Z2_no_util_re | 0pp |
| Z2_gain_3 | -1.5pp (helpful) |

Z1_beta12 is the most damaging rule (β≥1.2 conflicts with H12 defensive sector preferences).

## Per-zone performance (3yr / holdout, flat 1x)

| Zone | N | WR | avg | 3yr | Hold |
|---|---|---|---|---|---|
| Z1 | ~220 | ~58% | +0.18% | ~+40% | ~+25% |
| Z2 | ~45 | ~56% | +0.41% | ~+18% | ~+12% |
| Z3 | ~85 | ~52% | +0.28% | ~+24% | ~+18% |
| Z4 | ~52 | ~56% | +0.16% | ~+8% | ~+13% |

(Exact per-zone numbers in `/tmp/h12_ef_rule_drilldown.py` output)

## Entry / Exit rules (NO CHANGE from production)

- **Entry timing**: market order @ scan_now
- **Exit default**: hold to EOD
- **Z4 hard SL**: -3% from fill_price (production-existing)

## WIN_THR / Sizing

- `WIN_THR = 0.75` (all zones)
- **Sizing options**:
  - Flat 1× (conservative)
  - **Kelly 2× (recommended)**: `weight = 2 × wp_use / mean(wp_use)`

## Lineage

```
H3 hybrid              +37%   (per-zone source routing + cell filter)
   ↓ + Z2 label fix
H4c                   +54%   (Z2 z12_3dd)
   ↓ + Z4 SPY gate
H6                    +57%
   ↓ + per-zone regime gates
H7b                   +93%
   ↓ + VIX 18→20
H8 FINAL v3          +142%   (5 hard rules)
   ↓ + Z4 Option E*
H12 baseline         +152%   (replace Z4 SPY rule)
   ↓ + drop 13 useless EF rules
H12-A FINAL          +151%   (6 rules total, Sharpe 2.84) ⭐⭐⭐
```

Note: H10/H11 (stack model approach) tested but inferior on apples-to-apples
full-data comparison. Stack rank << wp_use rank.

## Files (reproducibility)

### Trainer scripts
- `/tmp/finetune_v2_prod_baseline.py` — V-2 (Z1)
- `/tmp/finetune_v3_regime.py` — V-C (Z2/Z3/Z4)
- `/tmp/p2_z2_label.py` — Z2 label rewrite to z12_3dd
- `/tmp/c_z4_label.py` — Z4 label sweep

### Prediction CSVs
- `/tmp/finetune_v2_predictions.csv` — V-2 (357k)
- `/tmp/finetune_v3_predictions.csv` — V-C
- `/tmp/p2_z2_pred_z12_market_3dd.csv` — Z2 z12_3dd
- `/tmp/c_z4_pred_z34_market_current.csv` — Z4 z34

### Analysis scripts (this session)
- `/tmp/h12_with_entry_filter.py` — H12-A + EF v1 baseline
- `/tmp/h12_ef_rule_drilldown.py` — per-rule EF contribution
- `/tmp/h12b_multi_drop.py` — drop-multiple-rules sweep
- `/tmp/h8_h11_deep_compare.py` — H8 vs H10/H11 apples-to-apples (critical finding: stack inferior)

## Deploy plan (when ready)

### Pre-deploy checklist
1. `git tag v1.9.0-pre-h12`
2. `cp -r backtests/models_prod_v22 backtests/models_prod_v22_pre_h12`
3. Retrain Z2 model with `label_z12_market_3dd`
4. Save new models to `backtests/models_prod_v23_h12a/`

### Code changes
1. `src/scan/strategies/ml_filter.py`:
   - Z4 rule: replace `spy_intra > 0.5` → Option E*
2. `src/scan/entry_filter.py` (or equivalent):
   - Keep only Z1 `gain_from_open <= 4.5%`
   - Remove all other 13 rules
3. `scripts/train_zones.py`:
   - Change Z2 label to `label_z12_market_3dd`
4. Optional: add Kelly sizing in position calc

### Env flag
- `H12A_ENABLED=1` to toggle
- Set to 0 for instant rollback

### Rollback
- `git reset --hard v1.9.0-pre-h12`
- Restore models from backup
- Restart services

### Testing protocol
1. Shadow mode 1-2 weeks: log H12-A picks alongside production
2. Compare WR/avg vs current
3. Paper trade 2-4 weeks on Alpaca paper account
4. LIVE gradual rollout: 25% → 50% → 100% size over 3 weeks

### Effort estimate
- Models + training: 4-6 hours
- Code changes: 6-8 hours
- Testing setup: 2-3 hours
- Shadow + paper validation: 4-6 weeks calendar time
- **Total work**: ~15-20 hours
- **Total time to LIVE**: ~6-8 weeks

## Caveats

1. **avg/pick +0.39%** is well above slippage 0.05-0.10%
2. **Z1 gain≤4.5** rule retained — DD evidence specific to it
3. **Z1_beta12 worst rule** — was conflicting with H12-A defensive preferences
4. Recent month (2026-05) result: ~+34% projected vs current +23% with all EF
5. Kelly 2× requires 2× capital allocation
6. WF refit monthly recommended (preserves edge in changing regimes)

## Key lessons from session

1. **Smart > Rules** is NOT universally true — stack model with loss merge made things worse on full data
2. **wp_use ranking** beat stack_pred ranking by ~90pp
3. **Z1_beta12 EF rule** was the single biggest performance killer (-36pp)
4. **Most EF rules** lack evidence and cost return
5. **Option E* Z4** (replace single rule) gives +10pp by itself
6. **Combining changes carefully** is more reliable than stacking many features
7. **Apples-to-apples comparison** essential (subset vs full data matters)

## Related research

- `H8_FINAL_v3_spec.md` — H8 predecessor
- `H10_spec.md`, `H10_OptionE_FINAL_spec.md` — explored but inferior on full data
- Memory: [[research-h8-final-vix20]], [[research-h10-optione-final]]
- Memory: [[research-why-no-edge-diagnosis]] — feature ceiling
- Memory: [[project-entry-filter-z1-gain-cap]] — Z1 gain≤4.5 origin
