# Stock Analyzer — Claude Code Instructions (v2, rebuilt 2026-04-11)

## How to scan

**Preferred (handles early-scan wait):**
```bash
bash scripts/scan_smart.sh                 # auto-waits until 09:31:30 ET
bash scripts/scan_smart.sh ml_filter       # force ml_filter
```
`scan_smart.sh` is the canonical scan entry point. If invoked between
09:28:00–09:31:30 ET on a weekday, it sleeps until the first 1-min bar
has closed + 30 s ingestion buffer, then forwards to the engine. Outside
that window it passes straight through.

**Raw engine (no wait — only use if you know data is ready):**
```bash
python3 -m src.scan.engine list            # show registered strategies
python3 -m src.scan.engine auto            # auto-pick by time+regime
python3 -m src.scan.engine ml_filter       # force specific strategy
```

Each strategy is one file under `src/scan/strategies/`. Each has its own
entry rules, exit rules, backtest-validated WR/EV, and hard time window.

## User commands → CLI mapping

User พิมพ์คำสั่งเป็นภาษาไทยหรือ slang — ผมแปลงเป็น CLI command ดังนี้:

| User พิมพ์ | Run |
|---|---|
| `scan` / `scan หุ้น` | `bash scripts/scan_smart.sh` (auto-waits if pre-09:31:30 ET) |
| `scan orb` | `orb_gap_preview` (ก่อน 09:30) / `orb_gap_break` (09:30-09:35) / `orb_prep` (03:00 prep) |
| `scan intraday` | `ml_filter` |
| `scan top movers` | `ml_filter` (ถ้าอยู่ใน 09:30-14:00 window) |
| `scan ovn` | removed — backtest showed no edge (gap prediction = coin flip) |
| `scan ml` | `ml_filter` (force) |
| `scan gap` | `orb_gap_preview` หรือ `orb_gap_break` ตามเวลา |
| `scan crisis` / `scan VIX high` | `crisis_reversal` |
| `scan list` | `python3 -m src.scan.engine list` |
| `exit SYM PRICE TIME` | `bash scripts/exit_check.sh SYM PRICE HH:MM` — manual Exit ML check (both price+time REQUIRED to avoid wrong defaults from scan_picks). Returns HOLD/EXIT recommendation (user decides) |

**Default rule**: ถ้าไม่ match อะไรชัด → `auto`

### Output handling (ALL commands)

1. Run the CLI command
2. Report the result **verbatim** to user (can translate/format for readability)
3. If result is `out_of_window` or `skipped_gate`, **do not** override with
   another strategy. The gate exists because backtest showed no edge.
4. If result has picks, present them as-is. Don't add your own analysis
   layer on top of the strategy's reasoning.
5. Scan output auto-recorded to journal for drift monitoring.

## Output rules (hard)

- **Never assume user holds positions.** Each scan is fresh. No "trail SL
  ขึ้นมา", "lock profit", "if you bought". Scan = recommendation, not
  position management.
- **Never override gates.** If strategy says `skipped_gate: SPY red`, that
  is the answer — don't flip to "but sector X is strong".
- **Never mix strategies.** If user asks `ml_filter` and it returns
  out_of_window, say that. Don't say "let's try vwap_reclaim instead".
- **Never invent picks.** If scan returns 0 picks, report 0. Do not
  substitute with ideas from your head.
- **Never cite deprecated rules.** Old v1 rules (Sec3d +2, catalyst +1,
  bounce mode, top 3 sector) were backtest-invalidated. If you find yourself
  referencing them, stop.

## Current strategies (v2 + ML)

### Trade strategies
| Strategy | Window ET | Notes |
|---|---|---|
| **ml_filter** | 09:30-13:00 | ⭐ ENSEMBLE ML — primary. See deployed config below. |
| orb_prep | 03:00-09:30 | watchlist only |
| vwap_reclaim | 13:30-15:30 | afternoon VWAP |
| crisis_reversal | any (VIX≥25) | contrarian |
| eod_flatten | 15:55-16:00 | meta (MOC) |

### Retired strategies (preserved via git)
- **swing_filter** v2.0 — retired 2026-05-27. Stock-based multi-day swing.
  Validated WR 100% TRUE OOS but crisis-vulnerable (WR 25% in Iran-Israel-2024).
  Decision: pivot to ETF-based approach for swing horizon.
  Restore via `git checkout swing-v2.0-final -- src/scan/engine.py` + cron.

(Old per-strategy WR/EV numbers removed 2026-05-13 — see deployed config below
for current expectations. Earlier numbers like "78% honest WF" / "78.3% WF" /
"88% WR" / "86.8% Triple Blend" / "0.1% live -81%" are OBSOLETE — they
referred to deprecated configurations and feature pipelines.)

### ml_filter (PRIMARY) — deployed 2026-05-24 (Step 33: TRIPLE_B Z3/Z4)

**Manual Exit Workflow (decided 2026-05-21): User-driven, no engine auto-exit**
- Engine remains pure-hold-EOD (Step 25 default behavior preserved)
- Exit ML = decision support tool (not autopilot)
- User runs `bash scripts/exit_check.sh SYM PRICE TIME` manually or via Claude /loop
- ML outputs HOLD/EXIT recommendation; user decides + executes sell via broker manually
- Phase 6b engine integration intentionally NOT done (user preference)

**Step 33 (2026-05-24) v2.6.0 — TRIPLE_B Z3/Z4 (smart_v2 + win_only + per_zone LIMIT)**
  - Z3/Z4 ONLY (Z1/Z2 unchanged)
  - NEW label: `label_smart_v2` — EOD>scan, skip large-cap (β>1.5) earnings days from training
  - NEW ranking: `win_only` for Z3/Z4 (R9 kept for Z1/Z2). Avoids R9 knife-catcher bias.
  - NEW LIMIT: per_zone ensemble `target = w_r × pred_r + (1-w_r) × pred_opt`
    - Z3 w_r=0.7, Z4 w_r=0.45
    - Requires NEW adaptopt models (10 new files: `lgb_adaptopt_{Z3,Z4}_seed{0-4}.txt`)
  - 22+ experiments today, 4 passed Phase 2, only TRIPLE_A and TRIPLE_B passed Phase 3 critical
  - Validation Funnel (PASS ALL):
      Phase 2 Monthly Refit: +12.6% (vs custom_dd+R9 baseline)
      Phase 3 Cross-Regime: 5/5 positive, 2/2 CRITICAL PASS (CRISIS +4.6%, STRESS +11.7%)
      Phase 4 TRUE OOS (30d): +22.7%
      Phase 5 Smoke Test: 15/16 PASS
      validate_retrain.sh: N=130 WR=98% +407% all floors PASS
  - Why win_only > R9: 5/19 NOW disaster — R9 picked NOW (deep dip = -4.97%),
    win_only would have picked ZTS (defensive Healthcare = -0.55%). Saved 4.42pp.
  - Why per_zone LIMIT helps: fill rate Z3 79%→90%, Z4 75%→88%. Slightly looser
    LIMIT captures more fills with similar avg PnL.
  - Files: `backtests/feature_builder.py` (+labels), `scripts/train_zones.py`
    (ZONE_LABEL Z3/Z4 + train adaptopt), `src/scan/ml_scorer.py` (load+predict
    adaptopt), `src/scan/strategies/ml_filter.py` (per-zone ranking + LIMIT).
  - Backup: `backtests/models_prod_v22_2026-05-24_pre_v2.6.0/`

**Step 32b (2026-05-21) — Hybrid Exit ML (Z4-only + Multi-zone universal)**
  - NEW models: `backtests/models_prod_exit/lgb_exit_MULTI_seed{0-4}.txt` (multi-zone universal, 89-dim)
  - Existing: `lgb_exit_Z4_seed{0-4}.txt` (Z4-only, 88-dim, kept)
  - ml_exit_scorer.py: routes per zone — Z4 → z4 model, Z1/Z2/Z3 → multi model
  - exit_check.sh: auto-detects zone from entry mfo, uses correct model
  - Validation Funnel for Multi-zone:
      Phase 2 Monthly Refit: ΔT +7.6% (Z1+4.4 / Z2+6.4 / Z3+7.7 / Z4+10.0)
      Phase 3 Cross-Regime: 4/5 PASS (CRISIS marginal -3% combined fail)
      Phase 4 TRUE OOS: ΔT +4.6% (all zones positive)
  - Hybrid rationale: Z4-only keeps CRISIS safety (+6% Phase 3). Multi-zone covers
    Z1/Z2/Z3 which all FAILED single-zone training. Best of both.
  - enabled=false in config = safe default, no actual exits

**Step 32 (2026-05-21) — Exit ML v3.1 infrastructure (Phase 6a, enabled=false)**
  - NEW files: `src/scan/ml_exit_scorer.py`, `scripts/train_exit.py`, `config/exit_config.json`
  - NEW models: `backtests/models_prod_exit/lgb_exit_Z4_seed{0-4}.txt` (5 seeds, 940KB each)
  - `enabled: false` in config = safe default, no actual exits
  - Engine NOT modified (Phase 6b later for integration)
  - Validation Funnel COMPLETE (Phase 2-5):
      Phase 2 Monthly Refit: +10.7% Total, 6/6 months
      Phase 3 Cross-Regime: 5/5 regimes positive (+6 to +14%)
      Phase 4 OOS 30-day: +5.9% Total, 30/66 exits (45%)
      Phase 5 Smoke Test: 7-point all pass
  - Config: thr=0.35, min_hold=30 min, zone Z4 only
  - Features: 88-dim (72 entry pkl + 16 post-entry: mins_since, pnl, hwm, drawdown, momentum)
  - Label: P(EOD > current_price) — classifier
  - Best AUC: 0.82 (vs 0.69 v1 basic features)

**Step 31 (2026-05-21) — Z2+Z4 HPs Optuna re-tune (under label_custom_dd + cw=2.0)**
  - Z2 HPs: lr 0.0235→0.0970, depth 3→2, leaves 5→56, n_est 500→400, min_child 61→120, reg_alpha 4.571→3.345, reg_lambda 2.035→4.341
  - Z4 HPs: lr 0.0783→0.0827, depth 6→5, leaves 49→5 (much smaller), min_child 35→69, reg_alpha 2.668→3.859
  - Z1, Z3 unchanged. ZONE_CW unchanged from Step 29.
  - Funnel: Step 3 Optuna 25 trials per zone → Phase 2 6-mo refit (Z2 +9.7%, Z4 +6.1%) → Phase 3 4/5 regimes → Phase 4 30-day OOS:
      Step 29 baseline: Combined +500%, Z2=+141, Z4=+140
      Step 31 (new):    Combined **+539%** (+7.8%), Z2=+161 (+20%), Z4=+158 (+18%)
      WR 99% across all zones (Z1 100% / Z2 100% / Z3 97% / Z4 99%)
  - Files: `scripts/train_zones.py` (ZONE_HP Z2,Z4), `scripts/validate_retrain.py` (mirrored)
  - Backup: `backtests/models_prod_v22_2026-05-21_pre_step31_backup/`

**Step 29 (2026-05-20) — Z3+Z4 win model class_weighted (cw=2.0 on losers)**
  - `ZONE_CW = {'Z1': None, 'Z2': None, 'Z3': 2.0, 'Z4': 2.0}` in train_zones.py
  - Win model: `sample_weight = where(y==0, 2.0, 1.0)` for Z3+Z4 (losers weighted 2x)
  - Z1, Z2, loss models, adapt models unchanged.
  - Validation funnel (Quick → Sweep → Phase 2 → Phase 3 → Phase 4):
      Phase 2 6-mo monthly refit: Z3 ΔWR +2.6pp ΔT -0.3%, Z4 ΔWR +0.6pp ΔT +1.7% ΔWorst +0.54pp
      Phase 3 5-regime: Z4 4/5 PASS (3/3 critical), Z3 4/5 (NEUTRAL fail borderline -7% but WR +9pp)
      Phase 4 TRUE 30-day OOS (Apr 20-May 20):
        Z1 WR 100% / Z2 WR 100% / Z3 WR 97% / Z4 WR 99%
        Combined N=182 / WR 99% / Total +500% (floor 75%/30%)
  - Anti-pattern logged: ensemble exploration (AVG cd+sw) looked +4.2pp WR at single-split
    but failed Phase 2 monthly refit (-3.1% Total). Funnel methodology vindicated.
  - Files: `scripts/train_zones.py` (ZONE_CW + sample_weight),
           `scripts/validate_retrain.py` (mirrored ZONE_CW for aligned validation)
  - Backup: `backtests/models_prod_v22_2026-05-20_pre_classw_backup/`

**Step 26 (2026-05-17) — Z3/Z4 custom_dd labels + Optuna HPs + R9 ranking**
  - Combined deploy of 3 experiments (A1 + A2 + A3 R9 from research run).
  - **A1: Z3+Z4 win label** `label_z34_market` → `label_custom_dd` (DD-aware).
    WF: combined +59% total, WR +1pp, worst +0.39pp.
  - **A2: Optuna HPs** (30 trials per zone). Pattern: Z1/Z2/Z3 shallower
    (regularize), Z4 deeper (capture complex patterns). Val: +137% total.
  - **A3 R9 ranking**: `win_p × max(0, 1-pred_r)**0.5` (was `win_p` only).
    Bonus for picks with predicted cushion. WF: +226% total.
  - 30-day OOS validation:
      Z1 WR 100% / Z2 WR 100% / Z3 WR 95% / Z4 WR 94%
      Combined **N=206 / WR 97% / +555%** (vs Step 25 +522%, +33%)
      Z2 worst -2.57% → **+0.12%** (huge)
  - Files: `scripts/train_zones.py` (ZONE_LABEL+ZONE_HP),
    `src/scan/strategies/ml_filter.py` (R9 ranking), `scripts/validate_retrain.py`.

**Step 25 (2026-05-17) — Remove Z4 SL: pure hold ALL zones to EOD**
  - `ZONE_HARD_SL = {}` (was `{'Z4': 0.03}` from Step 17).
  - After Step 23 dip filter + Step 24 better Z2 ML, the SL was converting
    21 recoverable -1 to -2.5% dips into -3.10% locks (whipsaw).
  - WF (6mo, monthly refit):
      Step 24 with Z4 SL: N=1071 / WR 81% / +1796% / worst -3.45% / 25 DD>3% trades
      **Step 25 NO SL:    N=1071 / WR 81% / +1854% / worst -4.75% / 4 DD>3% trades** ⭐
  - Δ: +58% total, +2pp Z4 WR (79→81%), DD>3% trades 25→4.
  - Trade-off: worst -3.45% → -4.75% (ALB 2025-11-13, single genuine
    mispredict). 2/466 Z4 trades fall below -3% (0.4%).
  - Aligns with user "smart ML not SL" philosophy.
  - Z4 distribution (no SL): min=-4.75%, p1=-2.70%, p5=-1.39%, p10=-0.64%.

**Step 24 (2026-05-17) — Z2 trained with new custom DD-aware label**
  - New label `label_custom_dd`: EOD > scan_p × 1.0 AND no -3% intraday DD.
    Data-dense (38% pkl avail vs 12.8% for label_z12_market_3dd, 96% Z2-only).
  - Z2 win model retrained: `label_eod_green_v2` → `label_custom_dd` (DD-aware).
  - Z1/Z3/Z4 unchanged.
  - WF (Nov 2025-Apr 2026, monthly refit, Step 23 dip filter active):
      N=1071 / WR 81% / +1796% / worst -3.45%
  - vs Step 23 baseline (+1518% / 81% / -3.48%):
      Total: **+278% (+18%)** / Worst: -0.03pp / Z2 WR: 79%→84% (+5pp)
  - Validation 30d OOS (Apr 17-May 17): WR 95% / +522% / Z2 worst -2.57%
  - Why it works: data-dense label trains Z2 model on full mfo 10-29 rows
    with DD-aware target → model picks differently → cross-scan dedup
    cascade lets Z4 see more good candidates.
  - Pipeline: feature_builder.py adds `label_custom_dd`; train_zones.py
    Z2 → label_custom_dd; no engine code change.

**Step 23 (2026-05-17) — Z4 dip filter 0.5%→0.9% (pred_r > 0.991 skip)**
  - Eliminates over-buffered Z4 picks where adaptive limit ≥ scan_price
    (no cushion if intraday drop). PGR 2025-11-07 -6.21% / VALE 2025-12-10
    -4.99% both eliminated.
  - `Z4_DIP_FILTER = 0.009` (was 0.005) in `src/scan/ml_scorer.py:113`.
  - WF (Nov 2025-Apr 2026, monthly refit, same models as Step 21):
      N=885 / WR 81% / +1518% / worst -3.48%
  - vs Step 21 baseline (+1737% / 77% / -6.21%):
      Total: -219% / Worst: -2.73pp / WR: +4pp / Z4 picks: 534→268 (-50%)
  - Remaining DD>3% trades: 1 (MNST Z2 -3.48% on 2025-11-07).
  - Cost-efficiency vs other DD filters: dominate (sweet spot at cliff
    where VALE pred_r=0.9920 just gets included).

**Step 22 (2026-05-16) — REVERTED**: V3 thresholds (Z1/Z2=0.80, Z3/Z4=0.70) tested
but user rejected as "เยอะเกินไป" (too strict). Reverted to V1 baseline (Step 21).
Stays at Z1=0.60, Z2=0.65, Z3=0.50, Z4=0.50. WF +1931% / WR 79% / -5.09%.

**Step 21 (2026-05-16) — VWAP formula aligned (HLC/3 both sides)**
  - feature_builder.py used close-weighted VWAP (sum(c×v)/sum(v))
    while feature_compute.py (live) uses HLC/3 standard.
  - Fix: feature_builder → HLC/3 (matches live + Alpaca DB stored vwap)
  - Also added: `label_eod_green_v2` to `_add_market_labels` (was missing,
    Z2 trains on this label).
  - Pkl rebuilt + 60 models retrained.
  - Proper WF (Nov 2025-Apr 2026, monthly refit):
      N=1188 / WR 79% / +1931% / worst -5.09%
  - Pre-fix WF +2096% was over-optimistic (live≠train drift).
  - Post-fix: live ≈ WF (no feature drift). Pipeline 10/10 consistent.

**Step 20 (2026-05-16) — Live scan aligned to 5-min boundaries (Option A)**
  - Previous: live used 1-min real-time features at off-boundary mfos (1, 2, 3...)
    causing phantom positives (5/15 FIS: 1-min score 0.91 → 5-min score 0.17).
  - Fix: `ml_filter.py` floors scan time to last closed 5-min bar.
    `scan_smart.sh` waits for next 5-min boundary + 30s buffer.
  - WF perfect refit (Nov 2025-Apr 2026):
      Config A (5-min live): N=1248 / WR 80% / **+2096%** ⭐
      Config B (1-min full): N=3812 / WR 36% / -1708%
      Config C (current prod): N=5267 / WR 38% / **-2248%**
  - Option A unlocks training-aligned execution. Δ vs current: +4344%/6mo.
  - First scan now at 09:35:30 ET (was 09:31:30). 4-min delay traded for
    feature alignment with training pipeline.

**Step 18 (2026-05-14) — Top-1 ranking = `win_score` only (drop +0.10×gain)**
  - WF grid (9 formulas): F1 win-only beats F3 (current) by +174% total.
  - WF combined: +959%/6mo (vs F3 +785%). WR 89% (vs 83%). worst -3.50% (vs -4.48%).
  - Per-zone: Z1 +325%, Z2 +211%, Z3 +206%, Z4 +216% (all under Top-1).
  - Single-line code change: `ml_filter.py:834`.

**Step 17 (2026-05-14) — Z4 Hard SL = -3% from limit_price**
  - All zones still use adaptive limit + label_z*_market (Step 16 config).
  - Z4 EXCEPTION: hard SL at -3% (was pure hold).
  - WF: Z4 worst trade -4.68% → -3.10% (RIVN 2025-12-12 case capped).
  - Total cost: -5% over 6mo (+259% → +254%). WR 92% → 91%.
  - Config: `ZONE_HARD_SL = {'Z4': 0.03}` in `src/scan/ml_scorer.py`.
  - Z1/Z2/Z3 remain pure hold (worst already < -3%).

**Step 16 (2026-05-14) — Z1 retrained with label_z12_market_3dd**
See `docs/ML_METHODOLOGY_2026-05-13.md` for full documentation.

Key changes:
  - **+16 new features** (feat_dist_sma20_d, feat_rsi_14d, feat_atr_pct_14d, etc.)
  - **Per-zone optimal hyperparameters** (random search 10 trials)
  - **Validated via true 6-month walk-forward** (monthly refit), not single-cutoff
  - **MoE + 1m ensemble DISABLED** — pure 28m models (matches WF validation)
  - Loss models retrained with same feature set

**WF validation (6 months, Nov 2025 - Apr 2026):**
| Zone | WR | avg | Total | Worst | p-value |
|---|---|---|---|---|---|
| Z1 | 88% | +3.12% | +290% | -2.54% | 0.0000 ⭐ |
| Z2 | 88% | +2.80% | +95%  | -2.08% | 0.0652 |
| Z3 | 85% | +2.83% | +292% | -2.01% | 0.0000 ⭐ |
| Z4 | 98% | +4.22% | +511% | -2.25% | 0.0000 ⭐ |

Combined 6-month total: **+1188%** (2.8× baseline +422%).

### ml_filter (PRIMARY) — deployed 2026-05-13 (initial)

**Strategy:**
  - Labels (zone-specific, all 840d train except where noted):
    - Z1: `label_safe_eod_1` (EOD-green AND no -1% intraday DD from entry)
    - Z2: `label_eod_green_v2` (EOD-green, baseline kept — safe variants didn't help)
    - Z3: `label_safe_eod_2` (EOD-green AND no -2% intraday DD)
    - Z4: `label_safe_eod_2` (same as Z3)
  - Thresholds: Z1=0.40, Z2=0.40, Z3=0.40, Z4=0.35 (lowered from initial
    based on live evidence: FTI 0.449 / TGT 0.420 on 5/12 both closed
    EOD-green but were blocked by earlier 0.55 threshold).
  - **Exit: pure hold to EOD, no SL, no trail, no Lock** — all zones.
  - **Entry: LIMIT @ 09:30 1-min open** (suggested in scan output as `limit_price`).
    Adverse selection caveat: limit only fills if stock dips back. Practical
    fill rate ~25-40%. Live can also use market order at scan time (higher
    fill, slightly worse entry).

**Expected performance (WF using training pkl, Apr 1-May 8, 2026):**
| Zone | N | WR | avg | Total | Worst |
|---|---|---|---|---|---|
| Z1 | 23 | 83% | +2.65% | +61% | -2.27% |
| Z2 | 16 | 100% | +2.66% | +42% | +0.34% |
| Z3 | 23 | 87% | +2.74% | +63% | -1.06% |
| Z4 | 23 | 100% | +2.87% | +66% | +0.34% |

Improvements vs initial 2026-05-13 deploy (label_eod_green_v2 + label_decay):
  Z1 +12% total (label_safe_eod_1 +1% DD constraint helps Z1 winners hold)
  Z3 +10pp WR, worst -6.96% → -1.06% (huge tail risk reduction)
  Z4 +13pp WR (87→100%), worst -1.65% → +0.34% (no losing trades in OOS)

⚠️ These are the only numbers to trust. Earlier OOS sim numbers (Z1 93%/+136%
etc.) used custom Python feature computation that drifted from the training
pkl — they overestimated performance by ~2-3×. Realistic upper bound shown
above; live likely 5-15pp lower than these due to slippage + feature drift.

**Diagnostic history (2026-05-12):**
Previous live ml_filter was bleeding (-81% / 20% WR since 2026-04-15) under
the old config: `label_decay` + market-order chase + Hard SL -2% + adaptive
trail + Lock SL. Root cause was execution chase (entry above 09:30 open)
combined with tight SL hitting on natural intraday retrace. Six losing
picks (RMBS/GLW/DKNG/AKAM/NET/HL) all would have been winners with
limit @ 09:30 open + no SL.

**Active window: 09:30-13:00 ET only.** Late buckets hard-skipped via
`can_reach_75()` — do not re-enable without new validation.

Features (56 base + 5 interactions @09:30 + 15 multi-tf @10:00/11:30):
  V7 (31): mins_from_open, gain_from_open, range_pct, from_peak_pct,
  vs_vwap, vol_ratio, vol_accel, bars_since_hi, hh_count, consol,
  range_exp, gap_from_prev, beta, mcap_bucket, spy_green, spy_intra,
  vix, vix_5d_chg, ad_ratio, mom5d, mom20d, dist_sma20,
  pct_52w_hi, pct_52w_lo, dow, btc_5d_chg, jpy_5d_chg,
  skew, vvix, vix_term_spread, sec_rel_strength.
  Cross-ETF (25): xlb/xlc/xle/xlf/xli/xlk/xlp/xlre/xlu/xlv/xly_intra,
  smh/qqq/iwm/dbc/eem/gld/hyg/igv/ief/lqd/tlt/uso/uup/vxx_intra.
  Multi-tf (15): {15m,30m,1h}_{gain,range,vol_norm,green_pct,high_break}.

NOTE: vol_ratio is canonical (no lookahead) — uses 30d_avg_daily ×
fraction_elapsed, NOT full-day average. Earlier vol_ratio bug inflated
WR by ~8pp; canonical formula validated 2026-04.

### How to scan with ml_filter

```bash
python3 -m src.scan.engine ml_filter   # force ml_filter
python3 -m src.scan.engine auto        # auto picks ml_filter first
```

Output interpretation:
- `active` + picks → trade these (ensemble prob ≥ threshold)
- `no_picks` → no stocks passed threshold this scan (re-try in 5-10 min)
- `skipped_gate` → current bucket cannot reach 75% WR (13:00+ dead zone)
- `out_of_window` → outside 09:30-13:00 ET

Picks are auto-recorded to data/scan_journal.db for drift monitoring.

### Daily workflow

```
03:00-03:59  orb_prep watchlist scan
04:00-09:29  orb_gap_preview (PM gap watchlist, confidence by time-to-open)
09:30-09:34  ml_filter (09:30 bucket — honest 75-85% WF)
09:35-09:40  orb_gap_break (gap+vol 2x filter)
09:41-10:45  ml_filter (10:00 bucket — sweet spot, most robust)
10:45-11:30  ml_filter (10:45 bucket)
11:30-13:00  ml_filter (11:30 bucket)
13:00-15:55  NO trades (48% WR coin flip — validated, skipped)
15:55-16:00  eod_flatten (exit intraday positions)
```

### Outcome update (after close)

```bash
python3 -m src.scan.outcome_updater           # last 7 days
python3 -m src.scan.outcome_updater --days=30 # last 30 days
```

Or cron:
```
30 16 * * 1-5 cd /path && python3 -m src.scan.outcome_updater
```

### Weekly drift check

```python
from src.scan.journal import get_journal
j = get_journal()
for row in j.report(days=7):
    print(row)
# Shows actual WR vs expected WR per strategy/bucket
# If drift > 5pp → investigate or retrain
```

Backtest source: `backtests/results/SUMMARY.md` (29 tests, 20M bars, 2025+).
ML models: `backtests/models_prod_v22/` (70 model files: 4 buckets × tp1+loss × 5 seeds,
            + Tech-specialized 09:30, + multi-tf 10:00/11:30).
Validation: walk-forward refit per month (gold standard), 6 months OOS.

**Monthly retrain (recommended):**
  Cron: `0 2 1 * *  bash scripts/monthly_retrain.sh`
  Cron: `0 2 * * 0  bash scripts/weekly_zone_retrain.sh` (Sunday — zone-only, faster)

Both scripts now:
  1. Rebuild pkl → `cache/bt_features/features.pkl` (persistent, not /tmp/)
  2. Run `feature_builder.py` (incl 16 feat_* + market labels for Step 18)
  3. Run `train_zones.py` (win + loss + adaptlim, per-zone labels + HP)
  4. **Run `validate_retrain.sh`** before restart — rollback if WF floor missed
  5. Backup old models to `backtests/models_prod_v22_<date>/` (replay)

Validation floors (`configs/wf_baseline.json`):
  Per-zone: Z1 WR≥75%/avg≥1%, Z2 WR≥70%/avg≥0.8%, Z3 WR≥65%/avg≥0.5%, Z4 WR≥70%/avg≥0.5%
  Combined: WR≥75%, total≥30% (30-day OOS).

## Adding a new strategy

1. Create `src/scan/strategies/<name>.py` inheriting `BaseStrategy`
2. Set `name`, `time_start`, `time_end`, `expected_wr`, `expected_ev`
3. Implement `scan()` returning `ScanResult`
4. Register in `src/scan/engine.py` `STRATEGIES` dict
5. Backtest-validate rules BEFORE deploying (see `backtests/`)
6. Paper trade 2 weeks before going live

## Architecture principles

**Specialization over coverage.** Don't build a universal scanner. Build
narrow, proven setups each in their own file. A 60% WR strategy applied
for 40 minutes beats a 52% WR scanner running all day.

**Backtest before deploy.** Every rule must have a backtest that shows
positive edge. No "gut feel" rules. No ported wisdom from prompts without
re-validation.

**Hard gates over soft penalties.** If a condition kills edge (AD<1,
SPY red, VIX>30 for momentum), hard skip. Don't lower score and still
recommend. Score reduction lets "best of bad batch" through.

**Trail from peak > fixed TP/SL.** Backtest +0.93% EV vs +0.43% fixed.
Default exit for most setups is trail 1% from peak.

**Wider SL than noise.** -0.5% = 28% WR (noise stops). Use -1.5% minimum
or ATR-based `-max(1.5%, 0.5×ATR)`.

**No catalyst bonus.** Backtest: no-catalyst = 58% WR, news = 50%,
insider = 40%. Catalysts attract crowds which attract fades.

## System notes

### Service management
```
systemctl --user restart auto-trading.service
systemctl --user restart stock-webapp.service
```
Never `pkill`.

### Logs
- Engine: `logs/auto_trading_engine_error.log`
- Webapp: `logs/web_app.log`
- Scan: `logs/scan.log` (if writing)

### Database
- `data/trade_history.db` — main (13GB)
- Key tables: `stock_daily_ohlc`, `intraday_bars_5m`, `macro_snapshots`,
  `market_breadth`, `universe_stocks`, `stock_fundamentals`,
  `news_events`, `insider_transactions`, `short_interest`,
  `earnings_calendar`

### v1 archive
Old scan code + prompts preserved at `archive/v1/` for reference.
Don't copy rules back without re-validating against backtest v2.

## Account
- Alpaca Paper ($5K start, dynamic budget)
- Position risk: 1% per trade
- Max 3 positions simultaneous
- EOD flat at 15:55 ET (enforced by trail/EOD exit)

## Rebuild history
- **2026-04-11**: Full scan layer rebuild. 29 backtests exposed look-ahead
  bugs and wrong factor weights in v1. Rewrote from scratch with
  per-strategy architecture. First working strategy: `ml_filter`.
  See `archive/v1/CLAUDE_v1.md` for the old monolithic system.
