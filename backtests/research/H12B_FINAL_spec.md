# H12-B FINAL spec — ⛔ REVERTED 2026-06-08 (LOOKAHEAD)

> **STATUS: REVERTED to H12-A on 2026-06-08, before first live trade.**
> The AD-conditional threshold was validated on **same-day EOD ad_ratio**, but
> `market_breadth` updates EOD-only (cron ~17:00 ET) so the live engine at 09:30
> can only read **prior-day** AD. `corr(same-day AD, prior-day AD) = -0.04` (AD has
> no day-to-day persistence), so the +27pp "edge" was lookahead. With realistic
> prior-day AD: full +119% Sh 2.90 / holdout +128% Sh 4.45 — **≈ or worse than
> H12-A** (full +99% Sh 2.94 / holdout +117% Sh 5.21, lower total but better Sharpe).
> No legitimate at-scan proxy (spy_intra) robustly beat H12-A flat 0.75. The
> AD signal IS real *same-day* (broad rally → more winners) but that's only known
> at EOD — to recover it legitimately would require computing a **same-day intraday
> breadth proxy at scan time** (open research, not yet built/validated).
> **Live system = H12-A** (`ML_FILTER_VARIANT=h12a`). H12-A gates use no ad_ratio
> (vix/sec_rel_strength/spy_intra/dow — all prior-day-consistent or at-scan), so
> H12-A is clean of this lookahead.

---

# H12-B FINAL spec (deployed to paper 2026-06-07, reverted 2026-06-08)

H12-B = **H12-A + AD-conditional WIN_THR on Z1/Z3 only**. Everything else
(models, cell filter, regime gates, entry filter, exit) is identical to H12-A.

## The one change vs H12-A

```
For Z1 and Z3 candidates, replace the fixed WIN_THR=0.75 with:
    AD_ratio > 1.5  ->  WIN_THR = 0.68   (broad rally: lower the bar)
    AD_ratio < 0.7  ->  WIN_THR = 0.80   (thin tape: raise the bar)
    otherwise       ->  WIN_THR = 0.75   (unchanged)

Z2 and Z4 keep fixed WIN_THR = 0.75 (AD-conditional hurts these thin zones).
```

`AD_ratio` = latest `market_breadth.ad_ratio` (advance/decline), already
fetched in `ml_filter.py` at scan time. If the fetch fails (ad_ratio=0.0),
the rule resolves to the strict branch (0.80) — fail-closed / conservative.

## Why AD-conditional (validated, not data-mined)

1. **Mechanistic** — in the 0.65–0.75 win_p "extra capture" band, winner
   base rate rises with breadth: AD<0.7 → 42.7% WR (losing), AD 1.5–2.0 →
   59.4% WR (+0.44% avg), AD>2.0 → 57.3% (+0.45%). Broad rally lifts even
   medium-confidence picks; thin tape sinks them.
2. **AD beats other regime vars** — same conditional logic on SPY_intra
   (Sharpe 2.66), VIX (2.28), vix_5d_chg (2.88) all lose to AD (3.59).
   Breadth captures "how wide" better than index level or fear.
3. **Adds selection, not just volume** — flat-lower to 0.68 (no AD): N=413,
   WR 55.7%, +118.3%, Sharpe 1.89. AD-conditional: N=275, WR 61.1%,
   +132.8%, Sharpe 3.59. Fewer picks, higher WR + total + ~2× Sharpe.

## WF validation (2yr, 2024-05 to 2026-05, monthly refit, no lookahead)

| Strategy | N | WR | avg | total | Sharpe |
|---|---|---|---|---|---|
| H12-A (0.75 all) | 246 | 59.8% | +0.40% | +98.9% | 2.94 |
| **H12-B (AD-cond Z1/Z3)** | 302 | 59.9% | +0.42% | **+126.1%** | **3.30** |

(robustness run with EF applied: H12-B N=275 WR 61.1% +132.8% Sharpe 3.59)

Per-zone Δ (why Z1/Z3 only):
- Z1 +33.3% → +53.1% (+19.8pp) ✅
- Z3 +28.4% → +42.5% (+14.1pp) ✅
- Z2 +18.1% → +14.2% (−3.9pp) ❌ kept fixed
- Z4 +19.1% → +16.2% (−2.9pp) ❌ kept fixed

Robustness:
- 7/9 quarters H12-B ≥ baseline
- Worst single day identical (−9.51%) — no added tail risk
- avg/pick ≈ unchanged (+0.42 vs +0.40) — gain is from N + selection, not luck

## Recent week sanity (06-01..06-05, serving models, actual EOD pnl)

| Date | AD | Zone | Sym | wp | PnL |
|---|---|---|---|---|---|
| 06-01 | 0.74 | Z1 | NVDA | 0.761 | +1.71% ✅ |
| 06-02 | 1.26 | Z1 | ANET | 0.812 | −1.20% ❌ |
| 06-02 | 1.26 | Z3 | FFIV | 0.777 | +0.33% ✅ |
| 06-04 | 2.30 | Z1 | RDDT | 0.696 | +4.38% ✅ |
| 06-04 | 2.30 | Z3 | SATS | 0.692 | −1.57% ❌ |

H12-B N=5 WR 60% +3.64% vs H12-A N=3 WR 67% +0.83%. The 06-04 rally
(AD=2.30) is where AD-cond captured RDDT+SATS (both wp<0.75) — net +2.81%
that H12-A missed (0 picks that day).

## Implementation

- `src/scan/strategies/ml_filter.py` — env `ML_FILTER_VARIANT=h12b` enables
  H12-A path + AD-conditional `_eff_thr` on Z1/Z3 (≈12 added lines).
- `.env` — `ML_FILTER_VARIANT=h12b` + `ENTRY_FILTER_SPEC=v2-h12a`.
- Models / cell ratings / picker / EF: unchanged from H12-A.

## Reversibility

- To H12-A: set `ML_FILTER_VARIANT=h12a` in `.env` + restart auto-trading.service.
- Full off: comment both `.env` lines + restart.
- Hard rollback: `git reset --hard v1.9.0-pre-h12a` + restore models/pkl.
- Backups: `.env.bak_pre_h12b`, `ml_filter.py.bak_pre_h12a`.

## Ceiling note

WR ~60% / avg +0.4% is the proven OHLCV ceiling (see
`research_why_no_edge_diagnosis`: Cohen's d 0.15, OOS AUC 0.47-0.52).
SATS-type losers cannot be separated from RDDT-type winners with OHLCV
(vol_ratio corr ≈ 0). Further gains require NEW information (order flow /
options) or multi-pick / position sizing — not more OHLCV reshuffling.
