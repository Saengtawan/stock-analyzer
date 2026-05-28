# Step 36 Agent A — Live vs Trainer Feature Parity

Window: `scan_date >= 2026-04-28` (last 30 days). Generated 2026-05-28.

## Coverage

- Live candidates: **532** (179 picks). Joined to trainer pkl on `(sym,date,mfo)`: **196/532 = 36.8%**.
- Trainer pkl: **35,987 rows**, 19 dates, 477 syms. **Last date = `2026-05-22`**.
- Picks on dates AFTER pkl freeze: **249/532 = 46.8%** — unauditable.
- On common dates: **196/283 = 69.3%** matched; remaining 87 = symbols outside trainer universe filter.
- Zero-coverage dates: `2026-05-26`, `2026-05-27`. Live zones: Z1=145, Z2=65, Z3=263 (largest), Z4=59 (selected 48/2/117/12).

## CRITICAL CAVEAT — storage gap

`scan_candidates.features_json` and `scan_picks.features_json` **do not store the 140-dim feature vector** the model actually scores. They contain only a summary dict (`ml_filter.py:976-997`): `ml_prob, threshold, bucket, gain_pct, beta, sector, limit_price, adaptive_limit, scan_price, day_open, pred_ratio`. The ~130 ML features (`vol_ratio`, `vs_vwap`, multi-tf, 25 ETF intras, `path_*`, `anomaly_score`, `feat_*`) **cannot be audited from logs**. Drift below is on context fields only — they share raw inputs with many derived features, so drift here implies upstream mismatch.

## Drift summary (all comparable fields, ranked)

| feature | n | mean \|Δ\| | p50 \|Δ\| | p95 \|Δ\| | max \|Δ\| | %>tol | tol |
|---|---|---|---|---|---|---|---|
| gain_from_open native vs trainer | 196 | 1.378 | 0.804 | 4.965 | 4.965 | **64.3%** | 0.5 (pp) |
| gain_pct (extra) vs trainer       | 196 | 1.378 | 0.804 | 4.965 | 4.965 | **64.3%** | 0.5 (pp) |
| beta native vs trainer            | 196 | 0.132 | 0.004 | 0.439 | 0.840 | **43.9%** | 0.05 |
| beta (extra) vs trainer           | 196 | 0.132 | 0.004 | 0.439 | 0.840 | **43.9%** | 0.05 |
| pred_ratio profile (live-only)    | 104 | 0.988 | 0.989 | 0.991 | 0.998 | n/a | — |

(`day_open`/`limit_price`/`adaptive_limit` were stored in only ~70% of rows; trainer-implied open `scan_price/(1+gfo/100)` could not be computed for the same reason. They were not rankable but examples are below.)

## Top features — hypothesis + 3 distinct examples

### 1. `gain_from_open` — 64% rows drift > 0.5pp (mean Δ = 1.38pp)
**Cause:** Live `(scan_price−day_open)/day_open`. Trainer reads first 1-min bar open via `feature_builder.py`. Live `day_open` is Alpaca `snapshot.dailyBar.o` (close-weighted aggregation — documented CLAUDE.md gotcha). Different open ⇒ every open-derived feature is wrong (`vs_vwap` near open, `range_pct`, `from_peak_pct`, `gap_from_prev`, all `path_*`).

| symbol | date | mfo | live | trainer | Δ (pp) |
|---|---|---|---|---|---|
| ABBV | 2026-04-30 | 30 | +6.40 | +1.44 | **4.96** |
| AMD  | 2026-04-30 | 30 | +3.46 | +0.80 | 2.66 |
| AVAV | 2026-05-22 | 65 | −0.32 | +2.34 | 2.66 |

(ABBV row recurs 116× in DB — same stale value rebroadcast across pre-market `scan_ts` timestamps, hinting at a scan-time/date bookkeeping issue too.)

### 2. `beta` — 44% rows drift > 0.05 (mean Δ = 0.13, max 0.84)
**Cause:** Live beta = current `stock_fundamentals` row (refreshed by maintenance jobs). Trainer beta frozen at pkl build. Distribution diverges post-build. Even small drift shifts zone routing (β cutoffs 1.0/1.5) and `feat_mom_x_vol`, `feat_sec_avg_intra`.

| symbol | date | mfo | live | trainer | Δ |
|---|---|---|---|---|---|
| INTC | 2026-05-01 | 30 | 1.35 | 2.19 | **0.84** |
| AMD  | 2026-04-30 | 30 | 1.96 | 2.40 | 0.44 |
| CHTR | 2026-05-01 | 5  | 1.03 | 0.76 | 0.27 |

### 3. `pred_ratio` profile (live-only)
Distribution clusters near 1.0 (median 0.989, max 0.998). Confirms adaptive-limit fed back into score but unmeasurable vs trainer.

## Recommendation — primary suspects

1. **`day_open` source mismatch (highest impact).** Live `snapshot.dailyBar.o` vs trainer "first 1-min bar open" causes 64% of rows to disagree on `gain_from_open` by >0.5pp (mean 1.38pp). Propagates into ~30 downstream features (`vs_vwap`, `range_pct`, `from_peak_pct`, `gap_from_prev`, all `path_*`, `feat_velocity`).

2. **Beta-snapshot drift.** 44% rows >0.05; INTC live 1.35 vs trainer 2.19 means zone routing almost certainly mis-assigned some picks.

3. **Trainer-universe gap (47% picks unaudited).** Pkl frozen at 5-22 vs live through 5-27. On common dates, 30% of live picks aren't in trainer universe at all — model scoring out-of-distribution symbols. Z3 (n=263) matched only 71%.

4. **Unmeasured ~130 features.** Hidden features likely carry similar/worse mismatches. **Immediate fix: instrument `ml_filter.py` to persist the full `model.predict` input dict into `scan_candidates.features_json` so this audit is routine and CI-able.**

5. **Bookkeeping anomaly.** ABBV 2026-04-30: 116 identical rows logged 12+ hrs before ET open (BKK 03:29 = ET 15:29 prev day per CLAUDE.md timezone gotcha), stale 6.40% gain. Suggests stale-data or mislabeled `scan_date`.

**Bottom line.** Two structural mismatches (open source, beta snapshot) plus a 47% universe gap are already enough to plausibly explain a 35-50pp WR shortfall. Step 35's label/HP retune could not close any of these — they are feature-pipeline and data-distribution problems, not modelling problems.
