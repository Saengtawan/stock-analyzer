# Agent C — Pipeline Parity Audit

**Date:** 2026-05-28
**Models:** `backtests/models_prod_v22/`
**Sources:** `src/scan/ml_scorer.py`, `src/scan/strategies/ml_filter.py`, `scripts/train_zones.py`, `scripts/validate_retrain.py`

## Audit A — Constants match

| constant | zone | live | validate | match |
| --- | --- | --- | --- | --- |
| ZONE_THR | Z1 | 0.6 | 0.6 | ✓ |
| ZONE_LOSS_THR | Z1 | 0.4 | 0.4 | ✓ |
| ZONE_BUF | Z1 | (0.005, 0.002) | (0.005, 0.002) | ✓ |
| ZONE_LIMIT_W_R | Z1 | - | - | ✓ |
| ZONE_THR | Z2 | 0.65 | 0.65 | ✓ |
| ZONE_LOSS_THR | Z2 | 0.2 | 0.2 | ✓ |
| ZONE_BUF | Z2 | (0.005, 0.0015) | (0.005, 0.0015) | ✓ |
| ZONE_LIMIT_W_R | Z2 | - | - | ✓ |
| ZONE_THR | Z3 | 0.5 | 0.5 | ✓ |
| ZONE_LOSS_THR | Z3 | 0.4 | 0.4 | ✓ |
| ZONE_BUF | Z3 | (0.0, 0.002) | (0.0, 0.002) | ✓ |
| ZONE_LIMIT_W_R | Z3 | 0.7 | 0.7 | ✓ |
| ZONE_THR | Z4 | 0.5 | 0.5 | ✓ |
| ZONE_LOSS_THR | Z4 | 0.5 | 0.5 | ✓ |
| ZONE_BUF | Z4 | (0.0, 0.002) | (0.0, 0.002) | ✓ |
| ZONE_LIMIT_W_R | Z4 | 0.45 | 0.45 | ✓ |
| Z4_DIP_FILTER | Z4 | 0.009 | 0.009 | ✓ |

## Audit B — Ensemble combination

| model | live | validate | match |
| --- | --- | --- | --- |
| win_p | min(preds_28)  # line 424, 522 | np.array([m.predict(X) for m in win_m[zone]]).min(axis=0)  # line 214 | ✓ |
| loss_p | max([... m.predict for m in zone_loss_models[zone]])  # 425, 523 | np.array([m.predict(X) for m in loss_m[zone]]).max(axis=0)  # line 215 | ✓ |
| adapt_r (pred_r) | np.mean(preds)  # predict_adaptive_limit_ratio line 267 | np.array([m.predict(X) for m in adapt_m[zone]]).mean(axis=0)  # line 216 | ✓ |
| adapt_opt | sum(preds)/len(preds)  # predict_opt_entry_ratio line 251-252 | np.array([m.predict(Xpick) for m in adaptopt_m[zone]]).mean()  # line 235 | ✓ |

## Audit C — Ranking

| zone | live | validate | match | note |
| --- | --- | --- | --- | --- |
| Z1 (bucket 09:30-10:00) | R9 = win_p * max(0,1-pred_r)**0.5  # ml_filter.py 892-900 | top = idx[win_p[idx].argmax()]  # validate_retrain.py line 222 → win_only | ✗ | MISMATCH: live uses R9 for Z1, validate uses win_only for ALL zones |
| Z2 (bucket 09:30-10:00) | R9 = win_p * max(0,1-pred_r)**0.5 | top = idx[win_p[idx].argmax()]  # win_only | ✗ | MISMATCH: live uses R9 for Z2, validate uses win_only |
| Z3 (bucket 10:00-10:45) | win_only (R9 disabled in `_rank` for bucket 10:00-10:45) | win_only | ✓ |  |
| Z4 (bucket 10:00-10:45) | win_only | win_only | ✓ |  |

## Audit D — Per-zone LIMIT (Step 33)

| zone | live_formula | validate_formula | match |
| --- | --- | --- | --- |
| Z3 | pred_target = 0.7 * pred_r + 0.30 * pred_opt  # ml_filter.py 780-781 | pred_target = 0.7 * pr + 0.30 * pred_opt  # validate_retrain.py 236-237 | ✓ |
| Z4 | pred_target = 0.45 * pred_r + 0.55 * pred_opt  # ml_filter.py 780-781 | pred_target = 0.45 * pr + 0.55 * pred_opt  # validate_retrain.py 236-237 | ✓ |

## Audit E — Model files present

| category | expected | present | match |
| --- | --- | --- | --- |
| lgb_tp1_{Z1-4}_seed{0-4} | 20 | 20 | ✓ |
| lgb_loss_{Z1-4}_seed{0-4} | 20 | 20 | ✓ |
| lgb_adaptlim_{Z1-4}_seed{0-4} | 20 | 20 | ✓ |
| lgb_adaptopt_{Z3,Z4}_seed{0-4} | 10 | 10 | ✓ |
| TOTAL | 70 | 70 | ✓ |
| all 70 files lgb.Booster() loadable | 0 | 0 | ✓ |

## Audit F — Reproduce live score

| id | ts | sym | stored_ml_prob | bucket | raw_features_in_json | reproducible |
| --- | --- | --- | --- | --- | --- | --- |
| 265 | 2026-05-27 10:40:50 | RCL | 0.7222 | 10:00-10:45 | ✗ (extra_dict only) | ✗ — schema does not persist raw feature vector |
| 264 | 2026-05-27 10:20:51 | WSM | 0.7051 | 10:00-10:45 | ✗ (extra_dict only) | ✗ — schema does not persist raw feature vector |
| 263 | 2026-05-27 10:05:48 | NKE | 0.7713 | 10:00-10:45 | ✗ (extra_dict only) | ✗ — schema does not persist raw feature vector |

> **Data limitation:** `scan_picks.features_json` stores only `extra_dict` (ml_filter.py:854-868), which contains `ml_prob`, `pred_ratio`, `threshold`, `bucket`, `gain_pct`, `beta`, `sector`, `limit_price`, `adaptive_limit`, `scan_price`, `use_market`, `day_open`, `exit_strategy` — NOT the 89-dim ML input feature vector. `scan_candidates.features_json` has the same schema. Therefore stored ml_prob cannot be replayed without rebuilding features from `data/scan_snapshots/*.json.gz` (snaps+bars+macro+DB state) via the full feature pipeline. **This itself is a parity-audit gap** — add raw feature persistence to enable post-mortem replay.

## Findings

- **Audit A:** All constants (ZONE_THR / ZONE_LOSS_THR / ZONE_BUF / ZONE_LIMIT_W_R / Z4_DIP) match between `ml_scorer.py` and `validate_retrain.py`.
- **Audit B:** Ensemble combinations identical (win=min, loss=max, adapt_r=mean, adapt_opt=mean).
- **Audit C: ranking MISMATCH** — Z1/Z2 live uses R9, validate uses win_only.
    - File: `scripts/validate_retrain.py:222` always picks `idx[win_p[idx].argmax()]` (= win_only) for every zone.
    - File: `src/scan/strategies/ml_filter.py:892-900` uses R9 for bucket `09:30-10:00` (Z1+Z2).
    - **Fix:** make validate match live → add `r9 = win_p[idx] * np.maximum(0, 1-pred_r[idx])**0.5; top = idx[r9.argmax()]` for Z1/Z2 (bucket 09:30-10:00). OR change live to win_only for all zones (Step 18 baseline).
- **Audit D:** Per-zone LIMIT formula identical (Z3 w_r=0.7, Z4 w_r=0.45).
- **Audit E:** All 70 expected zone models present + load successfully.
- **Audit F:** 0/3 picks reproducible — `features_json` stores only the `extra_dict` summary, NOT the raw model-input feature vector. Cannot independently verify live ml_prob == model.predict(features) from journal data alone. To reproduce, code must be modified to persist the raw 89-dim feature dict into the journal (or extracted from `data/scan_snapshots/*.json.gz` via the full feature pipeline replay).

## Summary

**Mismatches found in:** ranking (C), score reproduction (F)

**Highest-impact mismatch:** **Audit C — ranking divergence for Z1/Z2.**
Validate picks the candidate with highest `win_p` (validate_retrain.py:222), but live picks via R9 = `win_p * max(0, 1-pred_r)^0.5` (ml_filter.py:892-900).
Effect: on Z1/Z2 scans live will prefer candidates with predicted bigger dip (knife-catcher bias) while validate prefers highest win_p. Different picks → different outcomes. Live may pick deeper-dip stocks that fail to recover.

**Caveat for Audit F:** journal does not persist the raw 89-dim feature vector — only the `extra_dict` summary (ml_prob, pred_ratio, threshold, gain_pct, beta, sector, prices). Score parity cannot be verified post-hoc until live persistence is extended. **Recommended fix:** in `ml_filter.py:854`, expand `extra_dict` with the full `features` dict (or write to a separate compressed log).
