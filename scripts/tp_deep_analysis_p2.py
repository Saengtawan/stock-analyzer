#!/usr/bin/env python3
"""
Deep TP/Holding Period Analysis — Phase 2 (Feature Engineering) & Phase 3 (Profiles)
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB = Path("data/trade_history.db")
conn = sqlite3.connect(DB)

# ============================================================
# LOAD DATA
# ============================================================
signals = pd.read_sql("""
    SELECT s.*,
           b0.open as d0_open, b0.high as d0_high, b0.low as d0_low, b0.close as d0_close, b0.volume as d0_volume,
           b1.open as d1_open, b1.high as d1_high, b1.low as d1_low, b1.close as d1_close, b1.volume as d1_volume,
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
# PHASE 2: FEATURE ENGINEERING
# ============================================================
print("\n" + "=" * 80)
print("PHASE 2: FEATURE ENGINEERING & CORRELATION")
print("=" * 80)

# D0 candle features
signals['d0_body_ratio'] = (signals['d0_close'] - signals['d0_open']) / (signals['d0_high'] - signals['d0_low'] + 1e-8)
signals['d0_close_position'] = (signals['d0_close'] - signals['d0_low']) / (signals['d0_high'] - signals['d0_low'] + 1e-8)
signals['d0_range_pct'] = (signals['d0_high'] - signals['d0_low']) / signals['entry'] * 100
signals['d0_return'] = (signals['d0_close'] - signals['entry']) / signals['entry'] * 100

# D1 gap
signals['d1_gap'] = (signals['d1_open'] - signals['d0_close']) / signals['d0_close'] * 100

# ATR utilization on D0 (how much of ATR was "used")
signals['d0_atr_usage'] = signals['d0_range_pct'] / (signals['atr_pct'] + 1e-8)

# Momentum vs distance interaction
signals['mom_x_dist'] = signals['momentum_5d'] * signals['distance_from_20d_high']

# VIX regime
signals['vix_regime'] = pd.cut(signals['vix_at_signal'], bins=[0, 20, 25, 35, 100], labels=['BULL', 'ELEVATED', 'STRESS', 'CRISIS'])

# Target variables
# "TP hit day" for TP=1.5x (a reasonable middle ground)
for tp_ratio in [1.0, 1.5, 2.0]:
    tp_level = signals['entry'] + signals['atr_dollar'] * tp_ratio
    sl_level = signals['entry'] - signals['atr_dollar'] * 1.0

    hit_day = np.full(len(signals), 99, dtype=int)
    hit_result = np.zeros(len(signals))

    for d in range(6):
        h = signals[f'd{d}_high'].values
        l = signals[f'd{d}_low'].values
        tp = tp_level.values
        sl = sl_level.values
        entry = signals['entry'].values

        sl_hit = (l <= sl) & (hit_day == 99)
        tp_hit = (h >= tp) & ~sl_hit & (hit_day == 99)

        hit_day[sl_hit] = d
        hit_result[sl_hit] = -1  # SL
        hit_day[tp_hit] = d
        hit_result[tp_hit] = 1  # TP

    signals[f'tp_hit_{tp_ratio}'] = (hit_result == 1).astype(int)
    signals[f'hit_day_{tp_ratio}'] = hit_day

# Correlation analysis
features = ['atr_pct', 'volume_ratio', 'momentum_5d', 'distance_from_20d_high',
            'vix_at_signal', 'd0_body_ratio', 'd0_close_position', 'd0_range_pct',
            'd0_return', 'd1_gap', 'd0_atr_usage', 'mom_x_dist']

targets = ['outcome_1d', 'outcome_3d', 'outcome_max_gain_5d', 'tp_hit_1.0', 'tp_hit_1.5', 'tp_hit_2.0']

print("\nFeature Correlations:")
print(f"{'Feature':30s}", end="")
for t in targets:
    print(f"  {t:>18s}", end="")
print()
print("-" * 150)

for f in features:
    print(f"{f:30s}", end="")
    for t in targets:
        valid = signals[[f, t]].dropna()
        corr = valid[f].corr(valid[t])
        print(f"  {corr:+18.4f}", end="")
    print()

# ============================================================
# PHASE 2.5: Top feature interactions
# ============================================================
print("\n" + "=" * 80)
print("PHASE 2.5: CONDITIONAL ANALYSIS — KEY FEATURE SPLITS")
print("=" * 80)

# D1 gap + momentum interaction
print("\nD1_GAP × MOMENTUM → D3 outcome:")
signals['d1_gap_dir'] = np.where(signals['d1_gap'] > 0.3, 'gap_up', np.where(signals['d1_gap'] < -0.3, 'gap_down', 'flat'))
signals['mom_dir'] = np.where(signals['momentum_5d'] < -3, 'bearish', np.where(signals['momentum_5d'] > 0, 'bullish', 'neutral'))

ct = signals.groupby(['d1_gap_dir', 'mom_dir']).agg(
    n=('outcome_3d', 'count'),
    d3_mean=('outcome_3d', 'mean'),
    d3_wr=('outcome_3d', lambda x: (x > 0).mean() * 100),
    max_gain=('outcome_max_gain_5d', 'mean'),
    max_dd=('outcome_max_dd_5d', 'mean')
).round(3)
print(ct.to_string())

# Distance from high + VIX interaction
print("\nDIST_FROM_20D_HIGH × VIX_REGIME → D3 outcome:")
signals['dist_bucket'] = pd.cut(signals['distance_from_20d_high'], bins=[-100, -10, -5, -2, 0], labels=['deep_dip', 'moderate', 'near_high', 'at_high'])
ct2 = signals.groupby(['dist_bucket', 'vix_regime']).agg(
    n=('outcome_3d', 'count'),
    d3_mean=('outcome_3d', 'mean'),
    d3_wr=('outcome_3d', lambda x: (x > 0).mean() * 100),
    max_gain=('outcome_max_gain_5d', 'mean'),
).round(3)
print(ct2.to_string())

# ============================================================
# PHASE 3: PROFILE-BASED OPTIMAL EXIT
# ============================================================
print("\n" + "=" * 80)
print("PHASE 3: PROFILE-BASED OPTIMAL EXIT STRATEGY")
print("=" * 80)

def simulate_exit(df, tp_ratio, hold_days, label=""):
    """Simulate TP/SL with time exit at hold_days close."""
    entry = df['entry'].values
    atr_dollar = df['atr_dollar'].values
    tp_level = entry + atr_dollar * tp_ratio
    sl_level = entry - atr_dollar * 1.0

    returns = np.zeros(len(df))
    exit_reasons = np.zeros(len(df), dtype=int)  # 0=time, 1=tp, 2=sl

    for i in range(len(df)):
        exited = False
        for d in range(min(hold_days + 1, 6)):
            h = df.iloc[i][f'd{d}_high']
            l = df.iloc[i][f'd{d}_low']

            if l <= sl_level[i]:
                returns[i] = (sl_level[i] - entry[i]) / entry[i] * 100
                exit_reasons[i] = 2
                exited = True
                break
            if h >= tp_level[i]:
                returns[i] = (tp_level[i] - entry[i]) / entry[i] * 100
                exit_reasons[i] = 1
                exited = True
                break

        if not exited:
            # Time exit at hold_days close
            close_col = f'd{min(hold_days, 5)}_close'
            returns[i] = (df.iloc[i][close_col] - entry[i]) / entry[i] * 100
            exit_reasons[i] = 0

    n = len(df)
    wr = (returns > 0).sum() / n * 100
    avg_r = returns.mean()
    med_r = np.median(returns)
    tp_pct = (exit_reasons == 1).sum() / n * 100
    sl_pct = (exit_reasons == 2).sum() / n * 100
    time_pct = (exit_reasons == 0).sum() / n * 100

    return {
        'n': n, 'wr': wr, 'avg_r': avg_r, 'med_r': med_r,
        'tp_pct': tp_pct, 'sl_pct': sl_pct, 'time_pct': time_pct,
        'returns': returns
    }

# Define profiles
profiles = {
    'A: Low ATR, Near High, Calm': (signals['atr_pct'] < 2.5) & (signals['distance_from_20d_high'] > -5) & (signals['vix_at_signal'] < 20),
    'B: Low ATR, Deep Dip, Stressed': (signals['atr_pct'] < 2.5) & (signals['distance_from_20d_high'] < -10) & (signals['vix_at_signal'] > 20),
    'C: High ATR, Mom Down': (signals['atr_pct'] > 5) & (signals['momentum_5d'] < -5),
    'D: High ATR, High Volume': (signals['atr_pct'] > 5) & (signals['volume_ratio'] > 1.5),
    'E: Medium ATR, Moderate Dip': (signals['atr_pct'].between(2, 4)) & (signals['distance_from_20d_high'].between(-8, -3)),
    'F: ALL SIGNALS': pd.Series(True, index=signals.index),
}

tp_ratios = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
hold_days_list = [1, 2, 3, 5]

for pname, pmask in profiles.items():
    sub = signals[pmask]
    if len(sub) < 50:
        print(f"\n{pname}: SKIPPED (n={len(sub)})")
        continue

    print(f"\n{'='*80}")
    print(f"PROFILE: {pname} (n={len(sub):,})")
    print(f"{'='*80}")

    # Header
    print(f"{'TP_ratio':>10s} {'Hold':>6s} {'WR%':>7s} {'AvgR%':>8s} {'MedR%':>8s} {'TP%':>7s} {'SL%':>7s} {'Time%':>7s} {'E[R]*n':>10s}")
    print("-" * 80)

    best_er = -999
    best_combo = ""

    for tp_r in tp_ratios:
        for hd in hold_days_list:
            res = simulate_exit(sub, tp_r, hd)
            er_n = res['avg_r'] * res['n']  # total expected return
            marker = ""
            if res['avg_r'] > best_er:
                best_er = res['avg_r']
                best_combo = f"TP={tp_r}x, Hold=D{hd}"
            print(f"{tp_r:10.1f} {hd:6d} {res['wr']:7.1f} {res['avg_r']:+8.3f} {res['med_r']:+8.3f} {res['tp_pct']:7.1f} {res['sl_pct']:7.1f} {res['time_pct']:7.1f} {er_n:+10.0f}")

    print(f"\n  >>> BEST for this profile: {best_combo} (avg_r={best_er:+.3f}%)")

# ============================================================
# PHASE 3.5: The "REAL" E[R] comparison — fixed vs adaptive
# ============================================================
print("\n" + "=" * 80)
print("PHASE 3.5: FIXED vs PROFILE-ADAPTIVE STRATEGY")
print("=" * 80)

# Fixed strategy: one TP ratio for all
print("\nFixed strategy (all signals, TP=Xx, Hold=D3):")
for tp_r in tp_ratios:
    res = simulate_exit(signals, tp_r, 3)
    monthly_er = res['avg_r'] / 100 * 1250 * res['n'] / 48  # assume 48 months, $1250 per trade
    print(f"  TP={tp_r}x: WR={res['wr']:.1f}%, AvgR={res['avg_r']:+.3f}%, ~${monthly_er:+.0f}/mo")

# Adaptive: assign best (tp, hold) per profile
print("\nAdaptive strategy (per-profile optimal):")
# Re-compute to find actual best per profile
total_returns = []
total_n = 0

for pname, pmask in profiles.items():
    if pname.startswith('F:'):
        continue
    sub = signals[pmask]
    if len(sub) < 50:
        continue

    best_er = -999
    best_returns = None
    best_combo = ""

    for tp_r in tp_ratios:
        for hd in hold_days_list:
            res = simulate_exit(sub, tp_r, hd)
            if res['avg_r'] > best_er:
                best_er = res['avg_r']
                best_returns = res['returns']
                best_combo = f"TP={tp_r}x, Hold=D{hd}"

    total_returns.extend(best_returns.tolist())
    total_n += len(sub)
    monthly_er = best_er / 100 * 1250 * len(sub) / 48
    print(f"  {pname}: {best_combo} → AvgR={best_er:+.3f}%, ~${monthly_er:+.0f}/mo (n={len(sub):,})")

if total_returns:
    adaptive_avg = np.mean(total_returns)
    adaptive_monthly = adaptive_avg / 100 * 1250 * total_n / 48
    print(f"\n  Adaptive total: AvgR={adaptive_avg:+.3f}%, ~${adaptive_monthly:+.0f}/mo (n={total_n:,})")

conn.close()
print("\n\nPhase 2 & 3 complete.")
