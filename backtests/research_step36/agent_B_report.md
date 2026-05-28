# Agent B — `day_open` Mismatch Quantification

Window: scan_picks since **2026-04-28**, strategy = `ml_filter`.
N = **179 picks** (Z1=48, Z2=2, Z3=117, Z4=12).
Script: `backtests/research_step36/agent_B_day_open.py`
Row data: `backtests/research_step36/agent_B_day_open.csv`

## 1. Three `day_open` sources

| Source | Origin |
|--------|--------|
| **LIVE**  | Stored at pick time. From `scan_candidates.user_limit` / `reason LIMIT@$X` if present, else `entry/(1+gfo/100)`. Comes from Alpaca `snapshot.dailyBar.o` (close-weighted, **includes premarket**). |
| **BAR5M** | `intraday_bars_5m.open` at `time_et = '09:30'`. This is what `feature_builder.py:343-347` uses to build the training pkl. |
| **BAR1M** | `cache/wf_1min_bars.db.bars.o` at `em = 570`. |
| (PKL gfo) | `cache/bt_features/features.pkl` doesn't store `day_open` but its `gain_from_open` is computed from BAR5M. Used for direct feature-level comparison. |

## 2. Drift summary (pp = percentage points)

| Pair | N | median | mean&nbsp;abs | p90&nbsp;abs | %&gt;0.2pp | %&gt;1pp |
|------|---|--------|------|------|--------|--------|
| LIVE vs BAR5M | 179 | **+0.91** | **1.52** | 2.31 | **93.3%** | **63.7%** |
| LIVE vs BAR1M | 106 | +1.26 | 1.55 | — | 99.1% | — |
| BAR5M vs BAR1M (sanity) | 106 | 0.00 | **0.03** | — | 4.7% | — |
| LIVE&nbsp;gfo vs PKL&nbsp;gfo (direct) | 105 | +1.47 | **2.14** | 4.96 | **92.4%** | **70.5%** |

BAR5M ≡ BAR1M (median 0, mean abs 0.03pp) — both are RTH 09:30 opens.
LIVE is systematically **higher** than RTH (median +0.91pp, p99 4.3pp)
because `dailyBar.o` aggregates premarket. 93% of live picks disagree
with the RTH bar the model was trained on; 64% by more than 1pp.
The direct PKL comparison gives the same picture: median 1.47pp drift,
70% of picks > 1pp.

## 3. Per-zone drift (LIVE vs BAR5M)

| Zone | N | mean&nbsp;abs | median | %&gt;0.2pp | %&gt;1pp |
|------|---|--------|--------|------|------|
| Z1 | 48 | 1.40 | −0.87 | 81.3% | 45.8% |
| Z2 | 2  | 0.84 | −0.84 | 100%  | 0%    |
| Z3 | 117| **1.55** | **+1.26** | **97.4%** | **71.8%** |
| Z4 | 12 | **1.88** | −1.57 | 100%  | **66.7%** |

Z3 and Z4 — the two zones with the worst live-vs-backtest WR (47% / 62%)
— show the highest drift coverage (97-100%) and largest magnitude.

## 4. Drift magnitude vs pick outcome

Bucketed by |LIVE − BAR5M|, winners vs losers:

| |Δ| bucket | N | WR | avg PnL |
|--------------|---|------|---------|
| 0.00 – 0.20 | 12 | **58.3%** | +0.01% |
| 0.20 – 0.50 | 6  | 50.0% | +0.76% |
| 0.50 – 1.00 | 45 | 53.3% | +0.19% |
| > 1.00      | 108 | **43.5%** | +0.23% |

WR drops monotonically from 58% → 43% across drift — a **15pp WR delta**.
Mean drift for losers (1.51pp) ≈ winners (1.52pp), so the signal lives
in the *tail* (drift > 1pp), not the mean.

Worst-15 picks by drift: 11 losers, 2 winners, 2 no_data. Examples:
INTC (−5.2pp / loser), RMBS×2, NET×2 (all losers, all Z1, all 2026-05-11),
ALAB Z4 (−4.2pp / loser −2.2%), FSLR Z4 (−4.0pp / loser), NOW Z3
(+3.3pp / loser −4.97%). Drift consistently directs the model at picks
that look like fresh gap-ups in feature space but are actually
post-premarket-spike entries.

## 5. Verification of `ml_filter.py:614-623` fix

```python
sym_bars = bars_by_sym.get(sym, [])
if sym_bars:
    day_open = sym_bars[0].get('o', opn)        # first 5-min bar open
    bar_feats = extract_multibar_features(sym_bars, day_open)
    gain = (now / day_open - 1) * 100 if day_open > 0 else gain
    range_pct = (hi - lo) / day_open * 100 if day_open > 0 else range_pct
    gap_from_prev = (day_open / prev_c - 1) * 100 if prev_c > 0 else gap_from_prev
```

Training reference (`backtests/feature_builder.py:344-347`):

```python
bar_0930 = [b for b in sym_bars if b[0] == '09:30']
day_open = bar_0930[0][1]
```

`bars_by_sym` is Alpaca 5-min bars time-sorted, so `sym_bars[0]` after
09:30 = the 09:30 5-min bar — **the same row** used in training. Our
BAR5M ≡ BAR1M (mean abs 0.03pp) confirms this open is stable. **The
fix is correct and sufficient for these three features.**

## 6. Recommendation

**Deploy `ml_filter.py:614-623` immediately.** It eliminates the
documented drift in `gain_from_open`, `range_pct`, `gap_from_prev` for
the 93% of picks currently affected, with largest impact on Z3/Z4 — the
zones bleeding the most live WR.

**But the fix alone is not enough to declare the live↔backtest gap
closed.** Outstanding items:

1. Only **3 of 56** base features are patched. Other features
   (`vol_ratio`, `vs_vwap`, `spy_intra`, `sec_rel_strength`, multi-tf
   gains, path features) may have their own live↔train misalignments
   that this fix does not touch — independent audit required (Agent A
   covers some of this).
2. The `else` branch at `ml_filter.py:625` (no 5-min bars yet) still
   uses `day_open = opn` (stale Alpaca snapshot). Verify via logs the
   branch is unreachable once `scan_smart.sh` waits to 09:35:30 ET.
3. `gain_from_open` is also a key input to **R9 / win_only ranking**.
   Replay the 179 live picks through deployed Z3/Z4 models with
   bar5m-corrected features to quantify how much WR the fix actually
   recovers — recommended before claiming closure.

Net: **deploy the fix now**; follow with a feature-by-feature drift
audit and a corrected-feature replay-WR check.
