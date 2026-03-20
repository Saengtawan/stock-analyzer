#!/usr/bin/env python3
"""
Deep TP/Holding Period Analysis — Phase 1 & 2
Analyzes 51K signals to understand TP/SL dynamics and engineer predictive features.
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB = Path("data/trade_history.db")
conn = sqlite3.connect(DB)

# ============================================================
# LOAD DATA: Join signals with daily bars
# ============================================================
print("=" * 80)
print("LOADING DATA")
print("=" * 80)

signals = pd.read_sql("""
    SELECT s.*,
           b0.open as d0_open, b0.high as d0_high, b0.low as d0_low, b0.close as d0_close, b0.volume as d0_volume,
           b1.open as d1_open, b1.high as d1_high, b1.low as d1_low, b1.close as d1_close, b1.volume as d1_volume,
           b2.open as d2_open, b2.high as d2_high, b2.low as d2_low, b2.close as d2_close, b2.volume as d2_volume,
           b3.open as d3_open, b3.high as d3_high, b3.low as d3_low, b3.close as d3_close, b3.volume as d3_volume,
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

print(f"Total signals with full D0-D5 bars: {len(signals)}")

# ============================================================
# PHASE 1.0: Compute SL/TP levels and hit days
# ============================================================
print("\n" + "=" * 80)
print("PHASE 1.0: COMPUTING TP/SL HIT ANALYSIS")
print("=" * 80)

# Entry = scan_price (signal price)
signals['entry'] = signals['scan_price']
signals['atr_dollar'] = signals['entry'] * signals['atr_pct'] / 100.0

# For each TP ratio, find which day it hits
for tp_ratio in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
    tp_col = f'tp_{tp_ratio}'
    sl_col = f'sl_{tp_ratio}'  # SL is always 1x ATR
    hit_col = f'hit_day_{tp_ratio}'
    result_col = f'result_{tp_ratio}'

    signals[f'tp_level'] = signals['entry'] + signals['atr_dollar'] * tp_ratio
    signals[f'sl_level'] = signals['entry'] - signals['atr_dollar'] * 1.0  # SL = 1x ATR always

    # Check each day for TP/SL hit using intraday high/low
    hit_day = np.full(len(signals), -1, dtype=int)  # -1 = neither hit
    hit_result = np.full(len(signals), np.nan)  # actual return

    for d in range(6):  # D0 through D5
        h = signals[f'd{d}_high'].values
        l = signals[f'd{d}_low'].values
        c = signals[f'd{d}_close'].values
        tp = signals['tp_level'].values
        sl = signals['sl_level'].values
        entry = signals['entry'].values

        # TP hit: high >= tp_level AND not already hit
        tp_hit = (h >= tp) & (hit_day == -1)
        # SL hit: low <= sl_level AND not already hit
        sl_hit = (l <= sl) & (hit_day == -1)
        # Both hit same day — assume SL hits first (conservative)
        both = tp_hit & sl_hit

        # SL hits (including "both" cases — conservative)
        sl_mask = sl_hit & (hit_day == -1)
        hit_day[sl_mask] = d
        hit_result[sl_mask] = (sl[sl_mask] - entry[sl_mask]) / entry[sl_mask] * 100

        # TP hits (only if SL didn't hit)
        tp_only = tp_hit & ~sl_hit & (hit_day == -1)
        hit_day[tp_only] = d
        hit_result[tp_only] = (tp[tp_only] - entry[tp_only]) / entry[tp_only] * 100

    # Stocks where neither hit by D5 — use D3 close (default exit)
    neither = hit_day == -1
    hit_day[neither] = 99  # mark as "time exit"
    hit_result[neither] = signals.loc[neither, 'outcome_3d'].values  # exit at D3 close

    signals[hit_col] = hit_day
    signals[result_col] = hit_result

# Cleanup temp cols
signals.drop(['tp_level', 'sl_level'], axis=1, inplace=True)

# ============================================================
# PHASE 1.1: TP/SL hit statistics
# ============================================================
print("\n" + "=" * 80)
print("PHASE 1.1: TP/SL HIT STATISTICS BY RATIO")
print("=" * 80)

for tp_ratio in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
    hit = signals[f'hit_day_{tp_ratio}']
    result = signals[f'result_{tp_ratio}']

    tp_hits = (hit >= 0) & (hit <= 5) & (result > 0)
    sl_hits = (hit >= 0) & (hit <= 5) & (result < 0)
    time_exits = hit == 99

    n = len(signals)
    tp_n = tp_hits.sum()
    sl_n = sl_hits.sum()
    te_n = time_exits.sum()

    tp_wr = tp_n / (tp_n + sl_n) * 100 if (tp_n + sl_n) > 0 else 0

    avg_return = result.mean()
    med_return = result.median()

    print(f"\nTP={tp_ratio}x ATR, SL=1x ATR:")
    print(f"  TP hits: {tp_n:,} ({tp_n/n*100:.1f}%)  |  SL hits: {sl_n:,} ({sl_n/n*100:.1f}%)  |  Time exits: {te_n:,} ({te_n/n*100:.1f}%)")
    print(f"  TP WR (of TP+SL): {tp_wr:.1f}%")
    print(f"  Avg return: {avg_return:.3f}%  |  Median: {med_return:.3f}%")

    # By day
    print(f"  TP hit by day:", end="")
    for d in range(6):
        d_tp = ((hit == d) & (result > 0)).sum()
        print(f"  D{d}={d_tp:,}", end="")
    print()
    print(f"  SL hit by day:", end="")
    for d in range(6):
        d_sl = ((hit == d) & (result < 0)).sum()
        print(f"  D{d}={d_sl:,}", end="")
    print()

# ============================================================
# PHASE 1.2: What happens BEFORE TP hit?
# ============================================================
print("\n" + "=" * 80)
print("PHASE 1.2: D0 PATTERNS → D1-D3 OUTCOME")
print("=" * 80)

# D0 candle features
signals['d0_return'] = (signals['d0_close'] - signals['entry']) / signals['entry'] * 100
signals['d0_body_ratio'] = (signals['d0_close'] - signals['d0_open']) / (signals['d0_high'] - signals['d0_low'] + 1e-8)
signals['d0_close_position'] = (signals['d0_close'] - signals['d0_low']) / (signals['d0_high'] - signals['d0_low'] + 1e-8)
signals['d0_green'] = (signals['d0_close'] > signals['d0_open']).astype(int)

# D1 gap
signals['d1_gap'] = (signals['d1_open'] - signals['d0_close']) / signals['d0_close'] * 100

# Does D0 green predict better D1+ outcomes?
print("\nD0 Close Direction → Subsequent Returns:")
for label, mask in [("D0 GREEN (close > open)", signals['d0_green'] == 1),
                     ("D0 RED   (close < open)", signals['d0_green'] == 0)]:
    sub = signals[mask]
    print(f"\n  {label} (n={len(sub):,}):")
    for d in ['outcome_1d', 'outcome_2d', 'outcome_3d', 'outcome_5d', 'outcome_max_gain_5d', 'outcome_max_dd_5d']:
        print(f"    {d}: mean={sub[d].mean():.3f}%, median={sub[d].median():.3f}%")

# D0 return buckets
print("\nD0 Return Buckets → D3 outcome:")
signals['d0_return_bucket'] = pd.cut(signals['d0_return'], bins=[-20, -3, -1.5, -0.5, 0, 0.5, 1.5, 3, 20])
bucket_stats = signals.groupby('d0_return_bucket').agg(
    n=('outcome_3d', 'count'),
    d1_mean=('outcome_1d', 'mean'),
    d3_mean=('outcome_3d', 'mean'),
    max_gain=('outcome_max_gain_5d', 'mean'),
    max_dd=('outcome_max_dd_5d', 'mean')
).round(3)
print(bucket_stats.to_string())

# ============================================================
# PHASE 1.3: D1 gap analysis
# ============================================================
print("\n" + "=" * 80)
print("PHASE 1.3: D1 OPEN GAP → HOLDING OUTCOME")
print("=" * 80)

signals['d1_gap_bucket'] = pd.cut(signals['d1_gap'], bins=[-20, -1, -0.3, 0, 0.3, 1, 20])
gap_stats = signals.groupby('d1_gap_bucket').agg(
    n=('outcome_3d', 'count'),
    d1_mean=('outcome_1d', 'mean'),
    d2_mean=('outcome_2d', 'mean'),
    d3_mean=('outcome_3d', 'mean'),
    max_gain=('outcome_max_gain_5d', 'mean'),
    max_dd=('outcome_max_dd_5d', 'mean'),
    wr_d3=('outcome_3d', lambda x: (x > 0).mean() * 100)
).round(3)
print(gap_stats.to_string())

# ============================================================
# PHASE 1.4: Early warning signs for SL hits
# ============================================================
print("\n" + "=" * 80)
print("PHASE 1.4: EARLY WARNING SIGNS FOR SL HITS (using TP=1.5x)")
print("=" * 80)

tp_mask = (signals['hit_day_1.5'] <= 5) & (signals['result_1.5'] > 0)
sl_mask = (signals['hit_day_1.5'] <= 5) & (signals['result_1.5'] < 0)

for feature in ['atr_pct', 'volume_ratio', 'momentum_5d', 'distance_from_20d_high',
                'vix_at_signal', 'd0_return', 'd0_body_ratio', 'd0_close_position', 'd1_gap']:
    tp_val = signals.loc[tp_mask, feature].median()
    sl_val = signals.loc[sl_mask, feature].median()
    diff = tp_val - sl_val
    print(f"  {feature:30s}  TP median={tp_val:+.3f}  SL median={sl_val:+.3f}  diff={diff:+.3f}")

# ============================================================
# PHASE 1.5: Golden Window — which day has highest TP probability?
# ============================================================
print("\n" + "=" * 80)
print("PHASE 1.5: GOLDEN WINDOW — CUMULATIVE TP HIT PROBABILITY BY DAY")
print("=" * 80)

for tp_ratio in [1.0, 1.5, 2.0, 2.5, 3.0]:
    print(f"\nTP={tp_ratio}x ATR:")
    hit = signals[f'hit_day_{tp_ratio}']
    result = signals[f'result_{tp_ratio}']
    cum_tp = 0
    cum_sl = 0
    for d in range(6):
        d_tp = ((hit == d) & (result > 0)).sum()
        d_sl = ((hit == d) & (result < 0)).sum()
        cum_tp += d_tp
        cum_sl += d_sl
        wr = cum_tp / (cum_tp + cum_sl) * 100 if (cum_tp + cum_sl) > 0 else 0
        marginal_tp = d_tp / len(signals) * 100
        print(f"  By D{d}: cum_TP={cum_tp:,}  cum_SL={cum_sl:,}  WR={wr:.1f}%  marginal_TP_rate={marginal_tp:.2f}%")

conn.close()
print("\n\nPhase 1 & initial Phase 2 complete.")
