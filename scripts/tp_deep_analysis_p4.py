#!/usr/bin/env python3
"""
Deep TP/Holding Period Analysis — Phase 4 (Predictability) & Phase 5 (Recommendations)
Can we predict optimal TP/hold per stock? Out-of-sample test.
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict

DB = Path("data/trade_history.db")
conn = None  # via get_session()

# ============================================================
# LOAD DATA
# ============================================================
signals = pd.read_sql("""
    SELECT s.*,
           b0.open as d0_open, b0.high as d0_high, b0.low as d0_low, b0.close as d0_close, b0.volume as d0_volume,
           b1.open as d1_open, b1.high as d1_high, b1.low as d1_low, b1.close as d1_close,
           b2.open as d2_open, b2.high as d2_high, b2.low as d2_low, b2.close as d2_close,
           b3.open as d3_open, b3.high as d3_high, b3.low as d3_low, b3.close as d3_close,
           b4.open as d4_open, b4.high as d4_high, b4.low as d4_low, b4.close as d4_close,
           b5.open as d5_open, b5.high as d5_high, b5.low as d5_low, b5.close as d5_close
    FROM backfill_signal_outcomes s
    JOIN signal_daily_bars b0 ON s.scan_date=b0.scan_date AND s.symbol=b0.symbol AND b0.day_offset=0
    JOIN signal_daily_bars b1 ON s.scan_date=b1.scan_date AND s.symbol=b1.symbol AND b1.day_offset=1
    JOIN signal_daily_bars b2 ON s.scan_date=b2.scan_date AND s.symbol=b2.symbol AND b2.day_offset=2
    JOIN signal_daily_bars b3 ON s.scan_date=b3.scan_date AND s.symbol=b3.symbol AND b3.day_offset=3
    JOIN signal_daily_bars b4 ON s.scan_date=b4.scan_date AND s.symbol=b4.symbol AND b4.day_offset=4
    JOIN signal_daily_bars b5 ON s.scan_date=b5.scan_date AND s.symbol=b5.symbol AND b5.day_offset=5
""", conn)

print(f"Loaded {len(signals)} signals")

signals['entry'] = signals['scan_price']
signals['atr_dollar'] = signals['entry'] * signals['atr_pct'] / 100.0

# ============================================================
# HELPER: Simulate exit strategy
# ============================================================
def simulate_exit_vec(df, tp_ratio, hold_days):
    """Vectorized TP/SL simulation, returns array of per-trade returns."""
    entry = df['entry'].values
    atr_dollar = df['atr_dollar'].values
    tp_level = entry + atr_dollar * tp_ratio
    sl_level = entry - atr_dollar * 1.0

    returns = np.zeros(len(df))
    exited = np.zeros(len(df), dtype=bool)

    for d in range(min(hold_days + 1, 6)):
        h = df[f'd{d}_high'].values
        l = df[f'd{d}_low'].values

        # SL first (conservative)
        sl_hit = (l <= sl_level) & ~exited
        returns[sl_hit] = (sl_level[sl_hit] - entry[sl_hit]) / entry[sl_hit] * 100
        exited[sl_hit] = True

        # TP
        tp_hit = (h >= tp_level) & ~exited
        returns[tp_hit] = (tp_level[tp_hit] - entry[tp_hit]) / entry[tp_hit] * 100
        exited[tp_hit] = True

    # Time exit
    not_exited = ~exited
    close_col = f'd{min(hold_days, 5)}_close'
    returns[not_exited] = (df[close_col].values[not_exited] - entry[not_exited]) / entry[not_exited] * 100

    return returns

# ============================================================
# PHASE 4.1: For each signal, find the BEST strategy ex-post
# ============================================================
print("\n" + "=" * 80)
print("PHASE 4.1: EX-POST OPTIMAL STRATEGY PER SIGNAL")
print("=" * 80)

strategies = []
for tp_r in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
    for hd in [1, 2, 3, 5]:
        strategies.append((tp_r, hd))

# Compute returns for ALL strategy combos
all_returns = {}
for tp_r, hd in strategies:
    key = f"tp{tp_r}_hd{hd}"
    all_returns[key] = simulate_exit_vec(signals, tp_r, hd)

# For each signal, find best strategy
returns_matrix = np.column_stack([all_returns[f"tp{tp_r}_hd{hd}"] for tp_r, hd in strategies])
best_idx = np.argmax(returns_matrix, axis=1)
best_returns = returns_matrix[np.arange(len(signals)), best_idx]

print(f"If we could pick the PERFECT strategy per signal:")
print(f"  Avg return: {best_returns.mean():+.3f}%")
print(f"  WR: {(best_returns > 0).mean()*100:.1f}%")
print(f"  Monthly est: ${best_returns.mean()/100*1250*len(signals)/48:+.0f}/mo")

# What does the distribution of "best" strategies look like?
strat_counts = defaultdict(int)
for idx in best_idx:
    tp_r, hd = strategies[idx]
    strat_counts[f"TP={tp_r}x,D{hd}"] += 1

print(f"\nDistribution of ex-post optimal strategies:")
for k, v in sorted(strat_counts.items(), key=lambda x: -x[1])[:15]:
    print(f"  {k}: {v:,} ({v/len(signals)*100:.1f}%)")

# ============================================================
# PHASE 4.2: Can we PREDICT optimal strategy from features?
# ============================================================
print("\n" + "=" * 80)
print("PHASE 4.2: WALK-FORWARD PREDICTION TEST")
print("=" * 80)

# Simple approach: bucket signals by features, find best strategy per bucket
# Then test out-of-sample

# Features for bucketing
signals['atr_bucket'] = pd.qcut(signals['atr_pct'], q=3, labels=['low_atr', 'med_atr', 'high_atr'])
signals['dist_bucket'] = pd.qcut(signals['distance_from_20d_high'], q=3, labels=['deep_dip', 'moderate', 'near_high'])
signals['vix_bucket'] = pd.cut(signals['vix_at_signal'], bins=[0, 20, 25, 100], labels=['bull', 'elevated', 'stressed'])
signals['mom_bucket'] = pd.qcut(signals['momentum_5d'], q=3, labels=['bearish', 'neutral', 'bullish'])

# Sort by date for walk-forward
signals = signals.sort_values('scan_date').reset_index(drop=True)

# Walk-forward: train on first 70%, test on last 30%
split_idx = int(len(signals) * 0.7)
train = signals.iloc[:split_idx]
test = signals.iloc[split_idx:]

print(f"Train: {len(train):,} signals ({train['scan_date'].min()} to {train['scan_date'].max()})")
print(f"Test:  {len(test):,} signals ({test['scan_date'].min()} to {test['scan_date'].max()})")

# Build lookup: (atr_bucket, dist_bucket, vix_bucket) → best (tp, hold) from training
bucket_cols = ['atr_bucket', 'dist_bucket', 'vix_bucket']
lookup = {}

for name, group in train.groupby(bucket_cols):
    if len(group) < 30:
        continue

    best_er = -999
    best_strat = (1.0, 3)

    for tp_r, hd in strategies:
        r = simulate_exit_vec(group, tp_r, hd)
        er = r.mean()
        if er > best_er:
            best_er = er
            best_strat = (tp_r, hd)

    lookup[name] = best_strat

print(f"\nLookup table ({len(lookup)} buckets):")
for k, v in sorted(lookup.items()):
    print(f"  {k} → TP={v[0]}x, Hold=D{v[1]}")

# Apply lookup to test set
test_returns_adaptive = np.zeros(len(test))
test_returns_fixed = simulate_exit_vec(test, 1.0, 3)  # baseline: TP=1x, D3
n_matched = 0

default_strat = (1.0, 3)

for i, row in test.iterrows():
    idx = i - split_idx
    key = (row['atr_bucket'], row['dist_bucket'], row['vix_bucket'])
    tp_r, hd = lookup.get(key, default_strat)
    r = simulate_exit_vec(test.iloc[idx:idx+1], tp_r, hd)
    test_returns_adaptive[idx] = r[0]
    if key in lookup:
        n_matched += 1

print(f"\nOut-of-sample results (n={len(test):,}, matched={n_matched:,}):")
print(f"  Fixed (TP=1x, D3): AvgR={test_returns_fixed.mean():+.4f}%, WR={(test_returns_fixed>0).mean()*100:.1f}%")
print(f"  Adaptive (lookup): AvgR={test_returns_adaptive.mean():+.4f}%, WR={(test_returns_adaptive>0).mean()*100:.1f}%")
print(f"  Improvement:       {(test_returns_adaptive.mean() - test_returns_fixed.mean()):+.4f}%")
monthly_fixed = test_returns_fixed.mean() / 100 * 1250 * len(test) / (48 * 0.3)
monthly_adaptive = test_returns_adaptive.mean() / 100 * 1250 * len(test) / (48 * 0.3)
print(f"  Monthly est:  Fixed=${monthly_fixed:+.0f}  Adaptive=${monthly_adaptive:+.0f}")

# ============================================================
# PHASE 4.3: Simpler approach — just 2-3 regimes
# ============================================================
print("\n" + "=" * 80)
print("PHASE 4.3: SIMPLE REGIME-BASED STRATEGY")
print("=" * 80)

# Use D1 gap (available at open) as primary signal
signals['d1_gap'] = (signals['d1_open'] - signals['d0_close']) / signals['d0_close'] * 100

# NOTE: D1 gap is available AFTER D1 open — so it's known when we decide to hold or exit
# Regimes based on pre-signal features only
regimes = {
    'VIX<20 + Near High (D20H>-5)': (signals['vix_at_signal'] < 20) & (signals['distance_from_20d_high'] > -5),
    'VIX<20 + Deep Dip (D20H<-8)': (signals['vix_at_signal'] < 20) & (signals['distance_from_20d_high'] < -8),
    'VIX<20 + Moderate': (signals['vix_at_signal'] < 20) & (signals['distance_from_20d_high'].between(-8, -5)),
    'VIX 20-25': (signals['vix_at_signal'].between(20, 25)),
    'VIX>25 + Near High': (signals['vix_at_signal'] > 25) & (signals['distance_from_20d_high'] > -5),
    'VIX>25 + Deep Dip': (signals['vix_at_signal'] > 25) & (signals['distance_from_20d_high'] < -5),
}

print(f"\n{'Regime':45s} {'n':>7s} {'BestTP':>8s} {'BestHD':>8s} {'WR%':>7s} {'AvgR%':>8s} {'$/mo':>8s}")
print("-" * 100)

for rname, rmask in regimes.items():
    # Train on first 70%
    rtrain = train[rmask.iloc[:split_idx]]
    rtest = test[rmask.iloc[split_idx:]]

    if len(rtrain) < 30 or len(rtest) < 10:
        print(f"{rname:45s} SKIPPED (train={len(rtrain)}, test={len(rtest)})")
        continue

    # Find best on train
    best_er = -999
    best_tp = 1.0
    best_hd = 3

    for tp_r in [0.5, 1.0, 1.5, 2.0]:
        for hd in [1, 2, 3, 5]:
            r = simulate_exit_vec(rtrain, tp_r, hd)
            er = r.mean()
            if er > best_er:
                best_er = er
                best_tp = tp_r
                best_hd = hd

    # Test
    test_r = simulate_exit_vec(rtest, best_tp, best_hd)
    wr = (test_r > 0).mean() * 100
    avg_r = test_r.mean()
    monthly = avg_r / 100 * 1250 * len(rtest) / (48 * 0.3)

    print(f"{rname:45s} {len(rtest):7,} {best_tp:8.1f} {best_hd:8d} {wr:7.1f} {avg_r:+8.4f} {monthly:+8.0f}")

# Compare with fixed baseline on same test period
baseline_r = simulate_exit_vec(test, 1.0, 3)
print(f"\n{'BASELINE (TP=1x, D3, all)':45s} {len(test):7,} {'1.0':>8s} {'3':>8s} {(baseline_r>0).mean()*100:7.1f} {baseline_r.mean():+8.4f} {baseline_r.mean()/100*1250*len(test)/(48*0.3):+8.0f}")

# ============================================================
# PHASE 4.4: The D1 gap "decision point" strategy
# ============================================================
print("\n" + "=" * 80)
print("PHASE 4.4: D1 GAP DECISION POINT — EXIT AT D1 OPEN OR HOLD?")
print("=" * 80)

# Compute d1_gap on full signals (before train/test split)
signals['d1_gap'] = (signals['d1_open'] - signals['d0_close']) / signals['d0_close'] * 100
# Re-slice test
test = signals.iloc[split_idx:]

# If D1 gap < -0.5%, should we just exit immediately?
# vs holding to D3 with TP/SL

# This is a REALISTIC decision: at D1 open, we see the gap and decide
for gap_thresh in [-1.0, -0.5, -0.3, 0.0, 0.3, 0.5]:
    exit_early = test['d1_gap'] < gap_thresh
    n_exit = exit_early.sum()

    # For early exits, return = D1 gap (sell at open)
    # For holds, return = standard TP/SL D3 strategy
    hold_returns = simulate_exit_vec(test, 1.0, 3)
    early_returns = test['d1_gap'].values.copy()

    combined = np.where(exit_early.values, early_returns, hold_returns)

    wr = (combined > 0).mean() * 100
    avg_r = combined.mean()
    print(f"  Exit if D1gap < {gap_thresh:+.1f}%: exits={n_exit:,} ({n_exit/len(test)*100:.0f}%), WR={wr:.1f}%, AvgR={avg_r:+.4f}%")

print(f"  HOLD ALL (no early exit): WR={(hold_returns>0).mean()*100:.1f}%, AvgR={hold_returns.mean():+.4f}%")

# ============================================================
# PHASE 4.5: Trailing stop analysis (vectorized)
# ============================================================
print("\n" + "=" * 80)
print("PHASE 4.5: TRAILING STOP ANALYSIS")
print("=" * 80)

# Once price moves up, trail the stop — vectorized
for trail_pct in [0.3, 0.5, 0.7, 1.0]:
    entry = signals['entry'].values
    atr = signals['atr_dollar'].values
    sl = entry - atr  # initial SL
    highest = entry.copy()
    returns = np.zeros(len(signals))
    exited = np.zeros(len(signals), dtype=bool)

    for d in range(6):
        h = signals[f'd{d}_high'].values
        l = signals[f'd{d}_low'].values

        # Update highest
        new_high = h > highest
        highest = np.maximum(highest, h)
        new_sl = highest - atr * trail_pct
        sl = np.maximum(sl, new_sl)

        # Check SL hit
        sl_hit = (l <= sl) & ~exited
        returns[sl_hit] = (sl[sl_hit] - entry[sl_hit]) / entry[sl_hit] * 100
        exited[sl_hit] = True

    # Time exit at D3 close for unexited
    not_exited = ~exited
    returns[not_exited] = (signals['d3_close'].values[not_exited] - entry[not_exited]) / entry[not_exited] * 100

    wr = (returns > 0).mean() * 100
    avg_r = returns.mean()
    monthly = avg_r / 100 * 1250 * len(signals) / 48
    print(f"  Trail={trail_pct}x ATR: WR={wr:.1f}%, AvgR={avg_r:+.4f}%, ~${monthly:+.0f}/mo")

# Baseline: no trailing, just D3 close
r0 = (signals['d3_close'] - signals['entry']) / signals['entry'] * 100
print(f"  No trail, D3 close: WR={(r0>0).mean()*100:.1f}%, AvgR={r0.mean():+.4f}%, ~${r0.mean()/100*1250*len(signals)/48:+.0f}/mo")

# ============================================================
# PHASE 5: E[R] by realistic filtered subset
# ============================================================
print("\n" + "=" * 80)
print("PHASE 5: REALISTIC FILTERED STRATEGIES")
print("=" * 80)

# In production, the kernel filters signals. Simulate top-N% selection
# Sort by some quality proxy and test top quartiles
signals['quality'] = -signals['distance_from_20d_high']  # near high = better

for q_label, q_range in [('Top 25% quality', (0.75, 1.0)), ('Top 50%', (0.50, 1.0)), ('Bottom 50%', (0.0, 0.50)), ('Bottom 25%', (0.0, 0.25))]:
    q_lo = signals['quality'].quantile(q_range[0])
    q_hi = signals['quality'].quantile(q_range[1])
    sub = signals[(signals['quality'] >= q_lo) & (signals['quality'] <= q_hi)]

    for tp_r in [0.5, 1.0, 1.5]:
        r = simulate_exit_vec(sub, tp_r, 3)
        wr = (r > 0).mean() * 100
        avg_r = r.mean()
        print(f"  {q_label:20s} TP={tp_r}x D3: n={len(sub):,}, WR={wr:.1f}%, AvgR={avg_r:+.4f}%")

# ============================================================
# PHASE 5.1: The "smart TP" regression idea — test with binned approach
# ============================================================
print("\n" + "=" * 80)
print("PHASE 5.1: BINNED SMART TP — ATR-AWARE RATIO")
print("=" * 80)

# Different ATR stocks might need different TP ratios
for atr_lo, atr_hi, label in [(0, 2, 'ATR<2%'), (2, 3, 'ATR 2-3%'), (3, 5, 'ATR 3-5%'), (5, 100, 'ATR>5%')]:
    sub = signals[(signals['atr_pct'] >= atr_lo) & (signals['atr_pct'] < atr_hi)]
    if len(sub) < 100:
        continue

    # Find best TP for this ATR bucket
    best_er = -999
    best_tp = 1.0
    for tp_r in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
        r = simulate_exit_vec(sub, tp_r, 3)
        er = r.mean()
        if er > best_er:
            best_er = er
            best_tp = tp_r

    # Also test on second half only
    half = len(sub) // 2
    sub2 = sub.iloc[half:]
    r_test = simulate_exit_vec(sub2, best_tp, 3)
    wr_test = (r_test > 0).mean() * 100

    print(f"  {label:12s} (n={len(sub):,}): Best TP={best_tp}x, AvgR={best_er:+.4f}%, Test WR={wr_test:.1f}%")

# ============================================================
# PHASE 5.2: Max gain vs ATR ratio — what TP is actually reachable?
# ============================================================
print("\n" + "=" * 80)
print("PHASE 5.2: MAX GAIN REACHABILITY BY ATR")
print("=" * 80)

signals['max_gain_atr_ratio'] = signals['outcome_max_gain_5d'] / signals['atr_pct']
signals['max_dd_atr_ratio'] = signals['outcome_max_dd_5d'] / signals['atr_pct']

for atr_lo, atr_hi, label in [(0, 2, 'ATR<2%'), (2, 3, 'ATR 2-3%'), (3, 5, 'ATR 3-5%'), (5, 100, 'ATR>5%')]:
    sub = signals[(signals['atr_pct'] >= atr_lo) & (signals['atr_pct'] < atr_hi)]
    if len(sub) < 100:
        continue

    mg = sub['max_gain_atr_ratio']
    md = sub['max_dd_atr_ratio']

    print(f"\n  {label} (n={len(sub):,}):")
    print(f"    Max gain / ATR: mean={mg.mean():.2f}x, median={mg.median():.2f}x, p75={mg.quantile(0.75):.2f}x, p90={mg.quantile(0.9):.2f}x")
    print(f"    Max DD / ATR:   mean={md.mean():.2f}x, median={md.median():.2f}x, p75={md.quantile(0.25):.2f}x, p90={md.quantile(0.1):.2f}x")

    # What % of signals reach TP at each ratio?
    for tp_r in [0.5, 1.0, 1.5, 2.0, 3.0]:
        reach_pct = (mg >= tp_r).mean() * 100
        sl_hit_pct = (md <= -1.0).mean() * 100
        print(f"    Reach {tp_r}x ATR: {reach_pct:.1f}%  |  SL hit (1x): {sl_hit_pct:.1f}%")

conn.close()
print("\n\nPhase 4 & 5 complete.")
