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

(Old per-strategy WR/EV numbers removed 2026-05-13 — see deployed config below
for current expectations. Earlier numbers like "78% honest WF" / "78.3% WF" /
"88% WR" / "86.8% Triple Blend" / "0.1% live -81%" are OBSOLETE — they
referred to deprecated configurations and feature pipelines.)

### ml_filter (PRIMARY) — deployed 2026-05-16 (Step 22: V3 super-strict thresholds)

**Step 22 (2026-05-16) — Stricter thresholds for higher WR**
  - Z1: 0.60 → 0.80 (+0.20)
  - Z2: 0.65 → 0.80 (+0.15)
  - Z3: 0.50 → 0.70 (+0.20)
  - Z4: 0.50 → 0.70 (+0.20)
  - WF: N=1041 / WR 82% / +1889% / worst -3.24%
  - Trade-off: -1.2% total vs V1 baseline (+1931%) for +3pp WR + 36% tighter tail.
  - User preference: WR consistency > absolute total. Worst trade -5.09%→-3.24%.

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
