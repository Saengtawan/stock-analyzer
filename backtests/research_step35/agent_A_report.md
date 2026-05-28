# Agent A — Label Correctness Investigation (Step 35)

**Scope:** Live ml_filter picks 2026-05-17 → 2026-05-27. N=25 picks, 17 with outcomes.
**pkl coverage:** ends 2026-05-22 features; labels stop at 2026-05-08 (forward-looking).

## TL;DR
- **Labels themselves are not "broken"** in the definitional sense — they encode `pnl > 0` (+ optional DD constraint) and align 100% with realized outcome when applied to actual PnL.
- **The label CHOICE for Z3/Z4 (`label_smart_v2`) is the structural weakness**: it has no intraday-DD constraint. ~2.9% of Z3/Z4 training "winners" are stocks that survived a ≥-3% drawdown intraday. The model learns this is a survivable scenario; live, deep DDs frequently realize as losses.
- **Z1 (`label_z12_market_3dd`) bakes DD≤-3% in as a winner criterion** → trains the model to avoid deep-DD candidates → live WR 100%.
- **All 5 Z3/Z4 live losses (post-Step 25) had max_dd ≤ -3%**. Z1 had 0/5 picks with deep DD.

## Confusion matrix (per zone) — using synthetic label derived from actual outcome

Synthetic label = the label DEFINITION applied to realized (pnl, max_dd). Since every pick was a model-positive prediction (model said "win"), "model TP" = label says win too, "model FP" = label says loss.

| Zone | Label | N | Model TP | Model FP | TN | FN | Real WR |
|---|---|---|---|---|---|---|---|
| Z1 | label_z12_market_3dd | 5 | 5 | 0 | 0 | 0 | 100% |
| Z2 | label_custom_dd | 0 | – | – | – | – | – (no completed Z2 picks in window) |
| Z3 | label_smart_v2 | 6 | 3 | 3 | 0 | 0 | 50% |
| Z4 | label_smart_v2 | 6 | 4 | 2 | 0 | 0 | 67% |

`outcome_label` in scan_journal stores `1 if pnl>0 else 0` and matches the synthetic label exactly in every row (Z3 GPN -0.99% pnl: smart_v2 says 0, db outcome 0; etc.). **Label-vs-PnL alignment = 100% in all zones.**

## Why Z2/Z3/Z4 WR drops (root cause)

Cross-label comparison on Z3/Z4 training pool (Nov 2025 → May 8, 2026):

| | label_custom_dd | label_smart_v2 |
|---|---|---|
| Constraint | EOD > scan AND max_dd > -3% | EOD > scan (no DD constraint), large-cap-earnings masked |
| Z3+Z4 positives | 18,433 | 18,993 |
| Disagreement (custom=0, smart=1) | – | **560 rows = 2.9% of smart winners are deep-DD survivors** |

In other words, ~3% of Z3/Z4 "winning" examples the model is taught to mimic are stocks that suffered ≥-3% intraday DD. These trades look great EOD but are extremely uncomfortable (and often lose in live where slippage/timing differ from EOD bar close).

**100% of live Z3/Z4 losses had max_dd ≤ -3%:**
- Z1: 0/5 picks with deep DD; 0 losses.
- Z3: 3/6 deep DD; **3 losses** (GPN -1.0%, NOW -5.0%, SMTC -0.6%) all had dd ≤ -3.4%.
- Z4: 3/6 deep DD; **2 losses** (OMC -2.6%, ALAB -2.2%) and 1 deep-DD winner (WING +2.5%).

## False-positive feature dossier (model said win, lost)

| Sym | Date | Zone | win_p | pred_r | gain_open | vol_ratio | vs_vwap | mom20d | dist_sma20 | β |
|---|---|---|---|---|---|---|---|---|---|---|
| GPN | 05-18 | Z3 | 0.627 | 0.988 | +2.79 | 0.84 | +1.09 | -6.6 | -0.47 | 0.76 |
| NOW | 05-19 | Z3 | 0.732 | 0.982 | -2.22 | 5.30 | -0.60 | +3.7 | +16.95 | 0.82 |
| OMC | 05-19 | Z4 | 0.560 | 0.991 | +1.97 | 0.99 | +0.24 | -6.8 | -1.55 | 0.68 |
| SMTC | 05-21 | Z3 | 0.860 | 0.991 | (no pkl row) | – | – | – | – | 2.22 |
| ALAB | 05-22 | Z4 | 0.679 | 0.991 | +3.92 | 1.96 | +0.52 | +50.8 | +42.99 | 3.36 |

Patterns:
- **NOW** was already DOWN -2.22% at scan time, with 5.3× volume spike (high-conviction sell flow). Model overweighted `mom20d=+3.7`/`dist_sma20=+16.95` (extended) and missed the volume×gain interaction. Worst FP.
- **ALAB** was extended (`dist_sma20=+43%`, `mom20d=+51%`, β=3.36) — classic high-beta extension that label_smart_v2 still labels as winner if EOD > scan. The deep-DD pattern wasn't a training penalty.
- **GPN / OMC** had weak intraday trend (down-trending sectors, weak `mom5d`, `mom20d` negative). label_smart_v2 has no penalty for "winners that draw down hard then mean-revert" → model treats them as safe-equivalent.

By contrast, TP samples (FFIV, MKSI, CIFR, SMTC 05-20, MELI) tended to be:
- Solid `vol_ratio` at scan (≥1.0 typical),
- `gain_from_open` either small positive or near zero (clean start), and
- DDs in real outcome all < -3%.

## Recommendation

**Label is the bug — specifically the Z3/Z4 choice, not the model.**

The model is faithfully predicting `P(label_smart_v2=1)`. The label tolerates deep-DD survivors as wins, so the model learns that some deep-DD setups recover. In live, those deep-DD setups become the dominant loss bucket because:
1. Live execution differs from training (5-min closes vs 1-min ticks; slippage on dips).
2. The intraday DD is itself a hidden risk the user must endure; under manual exits, a -4% DD can panic-close before EOD recovery.
3. Step 23 already added a Z4 dip filter (pred_r > 0.991) but only at scan time, not in the LABEL the model trains against.

### Concrete options (no code change in this report)

- **A. Switch Z3/Z4 win label from `label_smart_v2` → `label_custom_dd`** (already DD-aware, available, well-populated). Expected: trims ~3% of training winners (deep-DD survivors) → tighter model prior on dip resistance.
- **B. Add a DD constraint to `label_smart_v2`** ("EOD > scan AND max_dd > -3%, with large-cap-earnings still masked") — combines Step 33's earnings-noise filter with Step 24's DD-awareness.
- **C. Hard scan-time gate: reject candidates whose `pred_r < 0.991` for Z3 too** (currently only Z4 dip filter @ 0.009).
- **D. Lower win-threshold sensitivity to `dist_sma20 > 30%` and `gain_from_open < -1%` features** — both observed in worst FPs (NOW, ALAB).

Validation funnel must be re-run before any deploy: Phase 2 monthly refit (6mo), Phase 3 cross-regime (CRISIS critical for Z3/Z4 — Step 33 chose smart_v2 partly because Z4-only CRISIS critical passed; a DD-aware Z4 label must re-clear CRISIS).

## Files

- `/tmp/step35_A/picks_labels_outcomes.csv` — raw join: picks × scan_candidates × pkl labels.
- `/tmp/step35_A/picks_full_confusion.csv` — adds synthetic-label confusion + per-pick fields.
- `/home/saengtawan/work/project/cc/stock-analyzer/backtests/research_step35/agent_A_report.md` — this report.

## Caveats

- **N=17 is small.** Z2 has zero completed picks in window (only 2 picks, both 5-26/5-27 awaiting outcomes). Z3/Z4 each N=6. Conclusions are directional, not statistically conclusive.
- **Pkl labels stop 2026-05-08**, so the analysis used the label *formula* against realized outcomes rather than stored label values. Formulas were lifted verbatim from `backtests/feature_builder.py:_add_market_labels`.
- The "deep-DD survivor" share is 2.9% of winners in training; this is a *small but structural* mismatch. The live signal (100% of losses had deep DD) is much stronger than the training prevalence suggests, hinting at additional live-vs-train drift (execution / 5-min snap / regime).
