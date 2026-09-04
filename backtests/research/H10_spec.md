# H10 Spec — Smart Stack + 2 Hard Rules (2026-06-06)

**Status:** Backtest only, NOT deployed. Built on top of H9 + smarter feature engineering.

## Performance summary

| Metric | Value |
|---|---|
| **3yr total (stack-subset)** | **+38.5%** |
| **Holdout (stack-subset)** | **+36.2%** |
| Picks | 183 |
| vs H9 | +2.9pp / +2.5pp |
| vs H8 (apples-to-apples) | +19.4pp / +15.2pp |
| Hard rules | **2** (down from 5) |

## H10 architecture (7 layers)

| Layer | Component |
|---|---|
| 1 | Win model — V-2 (Z1) + V-C (Z2/Z3/Z4) |
| 2 | Loss model — V-2/V-C, label `pnl_EOD < -1%`, `max()` of 5 seeds |
| 3 | Cell filter — S2 (Z1) / S7 (Z2,Z3) / none (Z4) |
| 4 | **STACK model** — LightGBM regression, depth 3, 100 rounds, 5 seeds, 180d training window |
| 5 | **2 HARD GATES** (down from 5) |
| 6 | Rank by stack_pred |
| 7 | Kelly sizing — linear by wp_use, avg 2× |

## Hard gates (only 2 remain)

| Zone | Gate | Why kept |
|---|---|---|
| Z1 | `sec_rel_strength > 0` | Stack can't fully learn relative strength conditional |
| Z3 | `skip Friday (dow != 4)` | DOW pattern not learnable from features alone |
| ~~Z1~~ | ~~VIX<20~~ | DROPPED — stack handles via VIX feature |
| ~~Z3~~ | ~~sec>0~~ | DROPPED — stack handles via sec feature |
| ~~Z2~~ | ~~vix_5d_chg<0~~ | DROPPED — stack handles via vix_x_vix5d interaction |
| Z4 | `spy_intra > +0.5%` | TRADE-OFF (3yr -23pp / holdout +7pp if dropped) — keep for safety |

Net: **Z2 has NO regime gate**, **Z1 only sec>0**, **Z3 only ¬Fri**, **Z4 SPY>+0.5%**

## Stack feature set (21 features)

```
Direct features (15):
  wp_use, lp_use,
  spy_intra, vix, vix_5d_chg, ad_ratio, sec_rel_strength,
  vvix, skew, vix_term_spread, mom5d, mom20d, spy_green,
  cell_WR, cell_avg, mins_from_open

DOW one-hot (5) — included for experiment, did not help:
  dow_mon, dow_tue, dow_wed, dow_thu, dow_fri

Interactions (12) — KEY improvement:
  vix_x_vix5d       — VIX level × VIX trend (enables Z2 gate replacement)
  spy_x_sec         — SPY × sector strength (Z1 top feature #8)
  vix_x_spy         — vol × momentum interaction
  ad_x_spy          — breadth × momentum
  mom5_x_mom20      — trend consistency (Z1 top feature #2!)
  wp_x_sec          — win prob × sector
  wp_minus_lp       — directional confidence
  vix_inv           — inverse VIX
  sec_strong (>1)   — binary indicator
  vix_low (<20)     — binary indicator
  spy_strong (>0.5) — binary indicator
  vix5d_falling (<0)— binary indicator
```

## Stack model hyperparameters

```python
params = dict(
    objective='regression',
    metric='mae',
    learning_rate=0.05,
    max_depth=3,
    num_leaves=8,
    min_child_samples=10,
    reg_alpha=1.0,
    reg_lambda=1.0,
    n_estimators=100,
    seeds=[0,1,2,3,4],
    aggregation='mean',
)
training_window_days = 180  # 6 months
target = 'pnl_EOD'  # regression
```

## Feature importance (Z1, last training month)

| Rank | Feature | Gain | Notes |
|---|---|---|---|
| 1 | vix_term_spread | 1342 | term structure dominant |
| 2 | mom5_x_mom20 | 595 | trend consistency interaction |
| 3 | ad_ratio | 366 | breadth |
| 4 | mom5d | 339 | direct momentum |
| 5 | mom20d | 333 | medium momentum |
| 6 | skew | 309 | tail risk gauge |
| 7 | wp_use | 301 | win model output |
| 8 | spy_x_sec | 249 | interaction! |
| 9 | lp_use | 218 | loss model |
| 10 | cell_avg | 191 | cell rating |

Notable: raw `vix` only ranks #16 with gain 17 — interactions absorbed it.

## Performance details (stack subset)

| Zone | N | WR | avg | 3yr | Holdout |
|---|---|---|---|---|---|
| Z1 | 60 | ~62% | +0.30% | +18% | +9% |
| Z2 | 45 | ~55% | +0.20% | (full re-eval needed) | |
| Z3 | 59 | ~53% | +0.12% | +7% | +11% |
| Z4 | 24 | ~63% | -0.11% | -3% | +2% |

Z2 increased N from 15 → 45 by dropping vix_5d gate.

## Files

### Trainer/predictor scripts
- `/tmp/loss_models_train.py` — loss models (V-2 Z1, V-C Z2/Z3/Z4, label pnl_EOD<-1%)
- `/tmp/h10_smarter_stack.py` — H10 stack with interactions + drop tests

### Prediction data
- Loss predictions: `/tmp/loss_pred_Z1.csv`, `Z2.csv`, `Z3.csv`, `Z4.csv`
- Win predictions: same as H8/H9 — `/tmp/finetune_v2_predictions.csv` etc.

### Analysis
- H10 vs H9 vs H8 sweep across feature sets and drop combos

## H10 vs prior versions

| Version | 3yr (subset) | Holdout | Hard rules | Notes |
|---|---|---|---|---|
| H8 | +19.1% | +21.0% | 5 | hard rules baseline |
| H9 (drop Z1 VIX + Z3 sec) | +35.6% | +33.7% | 3 | stack handles 2 rules |
| **H10 (+ drop Z2 vix5d + interactions)** | **+38.5%** | **+36.2%** | **2** | smart stack |
| H10 + drop Z4 SPY (risky) | +12.1% | +40.6% | 1 | regime trade-off |

## Open questions / future work

1. **Z4 SPY relax** — drop or relax to +0.3% in current regime (improves holdout but hurts 3yr)
2. **Larger stack model** (depth 4-5) — may overfit but could capture more nuance
3. **Z3 ¬Fri replacement** — DOW one-hot didn't work; need different approach (regime × DOW interaction?)
4. **Stack on V-2 architecture** for Z1 (currently shared) — might improve Z1 further
5. **Full 36-month validation** — H10 only tested on stack-eligible subset

## Deploy implications (relative to H9)

If deploying H10 over H9:
- Engineer 12 new interaction features in feature builder
- Add 5 DOW one-hot features (even if low importance, validates negative result)
- Remove Z2 vix_5d_chg hard rule from ml_filter.py
- Otherwise: same as H9 deploy plan

## Related research

- [[research-h8-final-vix20]] — H8 baseline
- H9 (stack + drop 2 rules) — implicit predecessor, see /tmp/h9_validate.py
- [[research-why-no-edge-diagnosis]] — feature ceiling justification
