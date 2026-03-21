#!/usr/bin/env python3
"""
Comprehensive Stop-Loss Hit Rate Analysis
Goal: Reduce SL hit rate WITHOUT widening SL (keep at 3% or tighter)
"""

import sqlite3
import numpy as np
import pandas as pd
from scipy import stats
from itertools import combinations

DB_PATH = "data/trade_history.db"
SL_PCT = 3.0  # Current SL = 3%

def load_data():
    """Load and union both tables, dedup on (scan_date, symbol)"""
    conn = sqlite3.connect(DB_PATH)

    # backfill_signal_outcomes
    bso = pd.read_sql_query("""
        SELECT scan_date, symbol, sector, scan_price, atr_pct, entry_rsi,
               distance_from_20d_high, momentum_5d, momentum_20d, volume_ratio,
               vix_at_signal, outcome_5d, outcome_max_gain_5d, outcome_max_dd_5d
        FROM backfill_signal_outcomes
        WHERE outcome_max_dd_5d IS NOT NULL
          AND outcome_5d IS NOT NULL
    """, conn)
    bso['source'] = 'backfill'

    # signal_outcomes
    so = pd.read_sql_query("""
        SELECT scan_date, symbol, sector, scan_price, atr_pct, entry_rsi,
               distance_from_20d_high, momentum_5d, momentum_20d, volume_ratio,
               vix_at_signal, outcome_5d, outcome_max_gain_5d, outcome_max_dd_5d,
               outcome_1d, outcome_2d, outcome_3d, outcome_4d
        FROM signal_outcomes
        WHERE outcome_max_dd_5d IS NOT NULL
          AND outcome_5d IS NOT NULL
    """, conn)
    so['source'] = 'live'

    # For the combined dataset, only keep columns both have
    common_cols = ['scan_date', 'symbol', 'sector', 'scan_price', 'atr_pct', 'entry_rsi',
                   'distance_from_20d_high', 'momentum_5d', 'momentum_20d', 'volume_ratio',
                   'vix_at_signal', 'outcome_5d', 'outcome_max_gain_5d', 'outcome_max_dd_5d', 'source']

    combined = pd.concat([bso[common_cols], so[common_cols]], ignore_index=True)
    combined = combined.drop_duplicates(subset=['scan_date', 'symbol'], keep='last')

    # Create SL_hit binary
    combined['SL_hit'] = (combined['outcome_max_dd_5d'] <= -SL_PCT).astype(int)

    # Derived features
    combined['atr_risk'] = combined['atr_pct'] * combined['vix_at_signal'] / 20.0
    combined['dist_x_rsi'] = combined['distance_from_20d_high'] * combined['entry_rsi']
    combined['mean_reversion_score'] = (combined['entry_rsi'] - 50) * combined['distance_from_20d_high']
    combined['rsi_over_50'] = (combined['entry_rsi'] > 50).astype(int)
    combined['mom_accel'] = combined['momentum_5d'] - (combined['momentum_20d'] / 4)  # 5d vs 5d-equivalent of 20d

    conn.close()
    return combined, so

def print_separator(title):
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")

def analysis_1(df):
    """What predicts SL hits? IC analysis"""
    print_separator("ANALYSIS 1: Feature IC (Spearman) with SL_hit")

    features = ['atr_pct', 'entry_rsi', 'distance_from_20d_high', 'momentum_5d',
                'momentum_20d', 'volume_ratio', 'vix_at_signal',
                'atr_risk', 'dist_x_rsi', 'mean_reversion_score', 'mom_accel']

    results = []
    for feat in features:
        valid = df[[feat, 'SL_hit']].dropna()
        if len(valid) < 30:
            continue
        ic, pval = stats.spearmanr(valid[feat], valid['SL_hit'])
        results.append({
            'Feature': feat,
            'IC': ic,
            'p_value': pval,
            'n': len(valid),
            'Significant': '***' if pval < 0.001 else '**' if pval < 0.01 else '*' if pval < 0.05 else ''
        })

    results.sort(key=lambda x: abs(x['IC']), reverse=True)

    print(f"\n{'Feature':<30} {'IC':>8} {'p-value':>12} {'n':>6} {'Sig':>5}")
    print("-" * 65)
    for r in results:
        print(f"{r['Feature']:<30} {r['IC']:>8.4f} {r['p_value']:>12.6f} {r['n']:>6d} {r['Significant']:>5}")

    # Special: Do winners also hit SL?
    print(f"\n--- Winners vs SL hits ---")
    winners = df[df['outcome_5d'] > 0]
    losers = df[df['outcome_5d'] <= 0]
    print(f"Winners (outcome_5d > 0): n={len(winners)}, SL_hit_rate={winners['SL_hit'].mean()*100:.1f}%")
    print(f"Losers  (outcome_5d <= 0): n={len(losers)}, SL_hit_rate={losers['SL_hit'].mean()*100:.1f}%")

    # Among those that hit SL, what was their max gain?
    sl_hits = df[df['SL_hit'] == 1]
    print(f"\nAmong SL hits (n={len(sl_hits)}):")
    print(f"  avg outcome_5d:        {sl_hits['outcome_5d'].mean():.2f}%")
    print(f"  avg max_gain_5d:       {sl_hits['outcome_max_gain_5d'].mean():.2f}%")
    print(f"  % that ended positive: {(sl_hits['outcome_5d'] > 0).mean()*100:.1f}%")
    print(f"  % with max_gain > 2%:  {(sl_hits['outcome_max_gain_5d'] > 2).mean()*100:.1f}%")

    non_hits = df[df['SL_hit'] == 0]
    print(f"\nAmong NON-SL hits (n={len(non_hits)}):")
    print(f"  avg outcome_5d:        {non_hits['outcome_5d'].mean():.2f}%")
    print(f"  avg max_gain_5d:       {non_hits['outcome_max_gain_5d'].mean():.2f}%")
    print(f"  WR (outcome_5d > 0):   {(non_hits['outcome_5d'] > 0).mean()*100:.1f}%")

    return [r['Feature'] for r in results[:7]]  # top 7

def analysis_2(df, top_features):
    """SL hit rate by feature quintiles"""
    print_separator("ANALYSIS 2: SL Hit Rate by Feature Quintiles")

    for feat in top_features[:5]:
        valid = df[[feat, 'SL_hit', 'outcome_5d', 'outcome_max_dd_5d']].dropna()
        if len(valid) < 50:
            continue

        try:
            valid['bucket'] = pd.qcut(valid[feat], 5, labels=False, duplicates='drop')
        except:
            continue

        print(f"\n--- {feat} ---")
        print(f"{'Quintile':<10} {'Range':<25} {'n':>5} {'SL_hit%':>8} {'WR%':>6} {'avg_ret':>8} {'avg_maxDD':>10}")
        print("-" * 80)

        for q in sorted(valid['bucket'].unique()):
            group = valid[valid['bucket'] == q]
            lo = group[feat].min()
            hi = group[feat].max()
            n = len(group)
            sl_rate = group['SL_hit'].mean() * 100
            wr = (group['outcome_5d'] > 0).mean() * 100
            avg_ret = group['outcome_5d'].mean()
            avg_dd = group['outcome_max_dd_5d'].mean()
            print(f"Q{q:<9} [{lo:>8.2f}, {hi:>8.2f}] {n:>5} {sl_rate:>7.1f}% {wr:>5.1f}% {avg_ret:>7.2f}% {avg_dd:>9.2f}%")

def analysis_3(df):
    """Pre-filter tests to exclude SL-prone picks"""
    print_separator("ANALYSIS 3: Individual Pre-Filters to Reduce SL Hits")

    baseline_n = len(df)
    baseline_sl = df['SL_hit'].mean() * 100
    baseline_wr = (df['outcome_5d'] > 0).mean() * 100
    baseline_ret = df['outcome_5d'].mean()

    print(f"\nBASELINE: n={baseline_n}, SL_hit={baseline_sl:.1f}%, WR={baseline_wr:.1f}%, avg_ret={baseline_ret:.2f}%")

    filters = {
        'ATR < 2.0%':               lambda x: x['atr_pct'] < 2.0,
        'ATR < 2.5%':               lambda x: x['atr_pct'] < 2.5,
        'ATR < 3.0%':               lambda x: x['atr_pct'] < 3.0,
        'ATR < 3.5%':               lambda x: x['atr_pct'] < 3.5,
        'ATR < 4.0%':               lambda x: x['atr_pct'] < 4.0,
        'vol_ratio > 0.5':          lambda x: x['volume_ratio'] > 0.5,
        'vol_ratio > 0.8':          lambda x: x['volume_ratio'] > 0.8,
        'vol_ratio > 1.0':          lambda x: x['volume_ratio'] > 1.0,
        '|mom_5d| < 5%':            lambda x: x['momentum_5d'].abs() < 5,
        '|mom_5d| < 3%':            lambda x: x['momentum_5d'].abs() < 3,
        'mom_5d > -5%':             lambda x: x['momentum_5d'] > -5,
        'mom_5d > -3%':             lambda x: x['momentum_5d'] > -3,
        'dist_20d_high > -5%':      lambda x: x['distance_from_20d_high'] > -5,
        'dist_20d_high > -8%':      lambda x: x['distance_from_20d_high'] > -8,
        'dist_20d_high > -10%':     lambda x: x['distance_from_20d_high'] > -10,
        'VIX < 20':                 lambda x: x['vix_at_signal'] < 20,
        'VIX < 22':                 lambda x: x['vix_at_signal'] < 22,
        'VIX < 25':                 lambda x: x['vix_at_signal'] < 25,
        'RSI 30-55':                lambda x: (x['entry_rsi'] >= 30) & (x['entry_rsi'] <= 55),
        'RSI 35-55':                lambda x: (x['entry_rsi'] >= 35) & (x['entry_rsi'] <= 55),
        'RSI 25-50':                lambda x: (x['entry_rsi'] >= 25) & (x['entry_rsi'] <= 50),
        'RSI < 50':                 lambda x: x['entry_rsi'] < 50,
        'RSI < 45':                 lambda x: x['entry_rsi'] < 45,
        'atr_risk < 3.0':           lambda x: x['atr_risk'] < 3.0,
        'atr_risk < 4.0':           lambda x: x['atr_risk'] < 4.0,
        'atr_risk < 5.0':           lambda x: x['atr_risk'] < 5.0,
    }

    print(f"\n{'Filter':<25} {'n':>6} {'%kept':>6} {'SL_hit%':>8} {'dSL':>6} {'WR%':>6} {'dWR':>5} {'avg_ret':>8} {'EV_chg':>7}")
    print("-" * 85)

    filter_results = []
    for name, fn in filters.items():
        try:
            valid = df.dropna(subset=['atr_pct', 'entry_rsi', 'distance_from_20d_high',
                                       'momentum_5d', 'volume_ratio', 'vix_at_signal'])
            mask = fn(valid)
            subset = valid[mask]
            if len(subset) < 30:
                continue
            n = len(subset)
            pct_kept = n / len(valid) * 100
            sl_rate = subset['SL_hit'].mean() * 100
            wr = (subset['outcome_5d'] > 0).mean() * 100
            avg_ret = subset['outcome_5d'].mean()
            d_sl = sl_rate - baseline_sl
            d_wr = wr - baseline_wr

            filter_results.append({
                'name': name, 'n': n, 'pct_kept': pct_kept,
                'sl_rate': sl_rate, 'd_sl': d_sl, 'wr': wr, 'd_wr': d_wr, 'avg_ret': avg_ret
            })

            print(f"{name:<25} {n:>6} {pct_kept:>5.1f}% {sl_rate:>7.1f}% {d_sl:>+5.1f} {wr:>5.1f}% {d_wr:>+4.1f} {avg_ret:>+7.2f}% {avg_ret-baseline_ret:>+6.2f}")
        except Exception as e:
            print(f"{name:<25} ERROR: {e}")

    return filter_results

def analysis_4(df):
    """Tighter SL - is it better?"""
    print_separator("ANALYSIS 4: Different SL Levels (1.5% to 5%)")

    sl_levels = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]

    print(f"\n{'SL%':>5} {'SL_hit%':>8} {'n_hit':>6} {'n_miss':>7} {'avg_out_hit':>12} {'avg_out_miss':>13} {'WR_miss':>8} {'EV':>8}")
    print("-" * 80)

    valid = df.dropna(subset=['outcome_max_dd_5d', 'outcome_5d'])

    for sl in sl_levels:
        hit = valid[valid['outcome_max_dd_5d'] <= -sl]
        miss = valid[valid['outcome_max_dd_5d'] > -sl]

        hit_rate = len(hit) / len(valid) * 100
        avg_out_hit = hit['outcome_5d'].mean() if len(hit) > 0 else 0
        avg_out_miss = miss['outcome_5d'].mean() if len(miss) > 0 else 0
        wr_miss = (miss['outcome_5d'] > 0).mean() * 100 if len(miss) > 0 else 0

        # EV = hit_rate * (-SL) + miss_rate * avg_outcome_non_hits
        ev = (hit_rate/100) * (-sl) + (1 - hit_rate/100) * avg_out_miss

        print(f"{sl:>5.1f} {hit_rate:>7.1f}% {len(hit):>6} {len(miss):>7} {avg_out_hit:>+11.2f}% {avg_out_miss:>+12.2f}% {wr_miss:>7.1f}% {ev:>+7.3f}")

    # Key question: Do stopped-out trades recover?
    print(f"\n--- Recovery Analysis: Among SL hits at -3%, do they recover? ---")
    sl_hits = valid[valid['outcome_max_dd_5d'] <= -SL_PCT]
    if len(sl_hits) > 0:
        recovered = sl_hits[sl_hits['outcome_5d'] > -SL_PCT]
        went_worse = sl_hits[sl_hits['outcome_5d'] <= -SL_PCT]
        print(f"Total SL hits at -3%: {len(sl_hits)}")
        print(f"  Recovered above -3% by day 5: {len(recovered)} ({len(recovered)/len(sl_hits)*100:.1f}%)")
        print(f"    avg final outcome: {recovered['outcome_5d'].mean():.2f}%" if len(recovered) > 0 else "")
        print(f"    ended positive:    {(recovered['outcome_5d'] > 0).sum()} ({(recovered['outcome_5d'] > 0).mean()*100:.1f}%)" if len(recovered) > 0 else "")
        print(f"  Stayed below -3% by day 5:   {len(went_worse)} ({len(went_worse)/len(sl_hits)*100:.1f}%)")
        print(f"    avg final outcome: {went_worse['outcome_5d'].mean():.2f}%" if len(went_worse) > 0 else "")

        # Breakdown of final outcomes for SL hits
        print(f"\n  Final outcome distribution for SL-hit trades:")
        bins = [(-999, -10), (-10, -5), (-5, -3), (-3, -1), (-1, 0), (0, 3), (3, 5), (5, 999)]
        for lo, hi in bins:
            group = sl_hits[(sl_hits['outcome_5d'] > lo) & (sl_hits['outcome_5d'] <= hi)]
            if len(group) > 0:
                pct = len(group) / len(sl_hits) * 100
                label = f"({lo}%, {hi}%]" if hi < 999 else f"({lo}%, +inf)"
                if lo == -999:
                    label = f"(-inf, {hi}%]"
                print(f"    {label:<20} {len(group):>5} ({pct:.1f}%)")

def analysis_5(df):
    """Conditional SL based on ATR"""
    print_separator("ANALYSIS 5: ATR-Proportional Stop Loss (SL = ATR × multiplier)")

    valid = df.dropna(subset=['atr_pct', 'outcome_max_dd_5d', 'outcome_5d'])

    multipliers = [0.5, 0.6, 0.75, 0.8, 1.0, 1.25, 1.5, 2.0]

    print(f"\n{'Mult':>5} {'avg_SL':>7} {'med_SL':>7} {'SL_hit%':>8} {'n_hit':>6} {'WR_all':>7} {'EV':>8} {'avg_ret':>8}")
    print("-" * 65)

    for mult in multipliers:
        valid_copy = valid.copy()
        valid_copy['dynamic_sl'] = valid_copy['atr_pct'] * mult
        valid_copy['sl_hit_dynamic'] = valid_copy['outcome_max_dd_5d'] <= -valid_copy['dynamic_sl']

        avg_sl = valid_copy['dynamic_sl'].mean()
        med_sl = valid_copy['dynamic_sl'].median()
        hit_rate = valid_copy['sl_hit_dynamic'].mean() * 100
        n_hit = valid_copy['sl_hit_dynamic'].sum()

        # EV: for each trade, if SL hit -> loss = -dynamic_sl, else -> outcome_5d
        valid_copy['trade_pnl'] = np.where(
            valid_copy['sl_hit_dynamic'],
            -valid_copy['dynamic_sl'],
            valid_copy['outcome_5d']
        )
        ev = valid_copy['trade_pnl'].mean()
        wr_all = (valid_copy['outcome_5d'] > 0).mean() * 100
        avg_ret = valid_copy['outcome_5d'].mean()

        print(f"{mult:>5.2f} {avg_sl:>6.2f}% {med_sl:>6.2f}% {hit_rate:>7.1f}% {int(n_hit):>6} {wr_all:>6.1f}% {ev:>+7.3f} {avg_ret:>+7.2f}%")

    # Compare: fixed 3% vs ATR×1.0
    print(f"\n--- Fixed 3% vs ATR×1.0 comparison ---")
    valid_copy = valid.copy()
    valid_copy['dynamic_sl'] = valid_copy['atr_pct'] * 1.0

    # Low ATR stocks
    low_atr = valid_copy[valid_copy['atr_pct'] < 3.0]
    high_atr = valid_copy[valid_copy['atr_pct'] >= 3.0]

    print(f"\nLow ATR (<3%): n={len(low_atr)}")
    print(f"  Fixed 3% SL hit rate:   {(low_atr['outcome_max_dd_5d'] <= -3).mean()*100:.1f}%")
    print(f"  ATR×1.0 SL hit rate:    {(low_atr['outcome_max_dd_5d'] <= -low_atr['atr_pct']).mean()*100:.1f}%")
    print(f"  avg ATR (=dynamic SL):  {low_atr['atr_pct'].mean():.2f}%")

    print(f"\nHigh ATR (>=3%): n={len(high_atr)}")
    print(f"  Fixed 3% SL hit rate:   {(high_atr['outcome_max_dd_5d'] <= -3).mean()*100:.1f}%")
    print(f"  ATR×1.0 SL hit rate:    {(high_atr['outcome_max_dd_5d'] <= -high_atr['atr_pct']).mean()*100:.1f}%")
    print(f"  avg ATR (=dynamic SL):  {high_atr['atr_pct'].mean():.2f}%")

def analysis_6(df, so_df):
    """Time-based SL analysis"""
    print_separator("ANALYSIS 6: Time-Based SL Analysis (When do SL hits happen?)")

    # Use signal_outcomes which has daily breakdowns
    valid = so_df.dropna(subset=['outcome_1d', 'outcome_5d', 'outcome_max_dd_5d'])

    # We can infer approximate timing from daily outcomes
    print(f"\nUsing signal_outcomes with daily outcomes: n={len(valid)}")

    sl_hits = valid[valid['outcome_max_dd_5d'] <= -SL_PCT]
    print(f"SL hits (max_dd <= -3%): n={len(sl_hits)}")

    if len(sl_hits) > 0:
        # Day 1 already hit -3%?
        day1_hit = sl_hits[sl_hits['outcome_1d'] <= -SL_PCT]
        print(f"\n  Day 1 already at/below -{SL_PCT}%: {len(day1_hit)} ({len(day1_hit)/len(sl_hits)*100:.1f}%)")
        if 'outcome_2d' in sl_hits.columns:
            valid_2d = sl_hits.dropna(subset=['outcome_2d'])
            day2_hit = valid_2d[(valid_2d['outcome_1d'] > -SL_PCT) & (valid_2d['outcome_2d'] <= -SL_PCT)]
            print(f"  Day 2 first hit:                 {len(day2_hit)} ({len(day2_hit)/len(sl_hits)*100:.1f}%)")

        # Approximation: use outcome_1d to detect "early crash"
        print(f"\n  --- Outcome_1d distribution for SL-hit trades ---")
        print(f"  Mean outcome_1d: {sl_hits['outcome_1d'].mean():.2f}%")
        print(f"  Median outcome_1d: {sl_hits['outcome_1d'].median():.2f}%")

        bins_1d = [(-999, -5), (-5, -3), (-3, -1), (-1, 0), (0, 2), (2, 999)]
        print(f"\n  {'Day1 range':<15} {'n':>5} {'%':>6} {'avg_5d':>8} {'recovered%':>11}")
        print(f"  " + "-" * 50)
        for lo, hi in bins_1d:
            group = sl_hits[(sl_hits['outcome_1d'] > lo) & (sl_hits['outcome_1d'] <= hi)]
            if len(group) > 0:
                pct = len(group) / len(sl_hits) * 100
                avg_5d = group['outcome_5d'].mean()
                recovered = (group['outcome_5d'] > -SL_PCT).mean() * 100
                label = f"({lo}%, {hi}%]" if hi < 999 else f">{lo}%"
                if lo == -999:
                    label = f"<={hi}%"
                print(f"  {label:<15} {len(group):>5} {pct:>5.1f}% {avg_5d:>+7.2f}% {recovered:>10.1f}%")

    # Non-SL-hit: when is their worst day?
    print(f"\n  --- Day 1 outcome for ALL trades ---")
    print(f"  All trades with day1 data: {len(valid)}")
    print(f"  Day1 < -3%:  {(valid['outcome_1d'] <= -3).sum()} ({(valid['outcome_1d'] <= -3).mean()*100:.1f}%)")
    print(f"  Day1 < -2%:  {(valid['outcome_1d'] <= -2).sum()} ({(valid['outcome_1d'] <= -2).mean()*100:.1f}%)")
    print(f"  Day1 < -1%:  {(valid['outcome_1d'] <= -1).sum()} ({(valid['outcome_1d'] <= -1).mean()*100:.1f}%)")
    print(f"  Day1 > 0%:   {(valid['outcome_1d'] > 0).sum()} ({(valid['outcome_1d'] > 0).mean()*100:.1f}%)")

    # "Would waiting 1 day help?"
    # Proxy: trades where day1 was bad but day 5 was good
    print(f"\n  --- 'Wait 1 day' proxy analysis ---")
    bad_day1 = valid[valid['outcome_1d'] <= -1]
    good_day1 = valid[valid['outcome_1d'] > 0]
    print(f"  Bad day1 (<=−1%): n={len(bad_day1)}, eventual SL_hit={( bad_day1['outcome_max_dd_5d'] <= -3).mean()*100:.1f}%")
    print(f"  Good day1 (>0%):  n={len(good_day1)}, eventual SL_hit={(good_day1['outcome_max_dd_5d'] <= -3).mean()*100:.1f}%")

def analysis_7(df):
    """Safety Score Filter"""
    print_separator("ANALYSIS 7: Safety Score (Composite SL Avoidance Score)")

    # Use IC to weight features
    features = ['atr_pct', 'entry_rsi', 'distance_from_20d_high', 'momentum_5d',
                'momentum_20d', 'volume_ratio', 'vix_at_signal']

    valid = df.dropna(subset=features + ['SL_hit', 'outcome_5d'])

    # Compute ICs
    ics = {}
    for feat in features:
        ic, _ = stats.spearmanr(valid[feat], valid['SL_hit'])
        ics[feat] = ic

    print(f"\nFeature ICs for SL_hit (positive = MORE SL hits):")
    for feat, ic in sorted(ics.items(), key=lambda x: abs(x[1]), reverse=True):
        print(f"  {feat:<30} IC = {ic:>+.4f}")

    # Build safety score: higher = SAFER (less likely to hit SL)
    # Normalize each feature to [0, 1] and weight by -IC (since positive IC means more SL)
    scored = valid.copy()

    for feat in features:
        lo = scored[feat].quantile(0.01)
        hi = scored[feat].quantile(0.99)
        scored[f'{feat}_norm'] = ((scored[feat] - lo) / (hi - lo)).clip(0, 1)

    # Weight: -IC * normalized (higher = safer)
    scored['safety_score'] = 0
    total_weight = sum(abs(ics[f]) for f in features)
    for feat in features:
        direction = -1 if ics[feat] > 0 else 1  # Flip so higher = safer
        weight = abs(ics[feat]) / total_weight
        scored['safety_score'] += direction * weight * scored[f'{feat}_norm']

    # Normalize to 0-100
    smin = scored['safety_score'].min()
    smax = scored['safety_score'].max()
    scored['safety_score'] = ((scored['safety_score'] - smin) / (smax - smin)) * 100

    print(f"\nSafety Score distribution:")
    print(f"  Mean: {scored['safety_score'].mean():.1f}, Median: {scored['safety_score'].median():.1f}")
    print(f"  Std:  {scored['safety_score'].std():.1f}")

    # Test thresholds
    print(f"\n{'Threshold':>10} {'n':>6} {'%kept':>6} {'SL_hit%':>8} {'WR%':>6} {'avg_ret':>8} {'EV':>8}")
    print("-" * 60)

    thresholds = [20, 30, 35, 40, 45, 50, 55, 60, 65, 70]
    for t in thresholds:
        subset = scored[scored['safety_score'] >= t]
        if len(subset) < 20:
            continue
        n = len(subset)
        pct_kept = n / len(scored) * 100
        sl_rate = subset['SL_hit'].mean() * 100
        wr = (subset['outcome_5d'] > 0).mean() * 100
        avg_ret = subset['outcome_5d'].mean()
        ev = (sl_rate/100) * (-3) + (1 - sl_rate/100) * subset[subset['SL_hit']==0]['outcome_5d'].mean() if (subset['SL_hit']==0).any() else 0

        print(f"{t:>10} {n:>6} {pct_kept:>5.1f}% {sl_rate:>7.1f}% {wr:>5.1f}% {avg_ret:>+7.2f}% {ev:>+7.3f}")

    return scored

def analysis_8(df):
    """Combined Filter Strategy"""
    print_separator("ANALYSIS 8: Combined Filter Strategies (Pareto Frontier)")

    valid = df.dropna(subset=['atr_pct', 'entry_rsi', 'distance_from_20d_high',
                               'momentum_5d', 'momentum_20d', 'volume_ratio',
                               'vix_at_signal', 'SL_hit', 'outcome_5d'])

    baseline_n = len(valid)
    baseline_sl = valid['SL_hit'].mean() * 100
    baseline_wr = (valid['outcome_5d'] > 0).mean() * 100
    baseline_ret = valid['outcome_5d'].mean()

    # Define atomic filters (use the ones that worked best from Analysis 3)
    atomic_filters = {
        'ATR<3.0':    lambda x: x['atr_pct'] < 3.0,
        'ATR<3.5':    lambda x: x['atr_pct'] < 3.5,
        'ATR<4.0':    lambda x: x['atr_pct'] < 4.0,
        'ATR<2.5':    lambda x: x['atr_pct'] < 2.5,
        'VIX<22':     lambda x: x['vix_at_signal'] < 22,
        'VIX<25':     lambda x: x['vix_at_signal'] < 25,
        'RSI<50':     lambda x: x['entry_rsi'] < 50,
        'RSI35-55':   lambda x: (x['entry_rsi'] >= 35) & (x['entry_rsi'] <= 55),
        'mom5>-5':    lambda x: x['momentum_5d'] > -5,
        'mom5>-3':    lambda x: x['momentum_5d'] > -3,
        'dist>-8':    lambda x: x['distance_from_20d_high'] > -8,
        'dist>-10':   lambda x: x['distance_from_20d_high'] > -10,
        'vol>0.5':    lambda x: x['volume_ratio'] > 0.5,
        '|mom5|<5':   lambda x: x['momentum_5d'].abs() < 5,
        'atr_risk<4': lambda x: (x['atr_pct'] * x['vix_at_signal'] / 20) < 4.0,
        'atr_risk<5': lambda x: (x['atr_pct'] * x['vix_at_signal'] / 20) < 5.0,
    }

    # Test all single + pair + triple combinations
    results = []

    filter_names = list(atomic_filters.keys())

    # Singles
    for name in filter_names:
        mask = atomic_filters[name](valid)
        subset = valid[mask]
        if len(subset) < 50:
            continue
        n = len(subset)
        sl_rate = subset['SL_hit'].mean() * 100
        wr = (subset['outcome_5d'] > 0).mean() * 100
        avg_ret = subset['outcome_5d'].mean()
        results.append({
            'combo': name, 'n': n, 'pct_kept': n/baseline_n*100,
            'sl_rate': sl_rate, 'wr': wr, 'avg_ret': avg_ret,
            'd_sl': sl_rate - baseline_sl, 'd_wr': wr - baseline_wr
        })

    # Pairs
    for i, name1 in enumerate(filter_names):
        for name2 in filter_names[i+1:]:
            mask = atomic_filters[name1](valid) & atomic_filters[name2](valid)
            subset = valid[mask]
            if len(subset) < 40:
                continue
            n = len(subset)
            sl_rate = subset['SL_hit'].mean() * 100
            wr = (subset['outcome_5d'] > 0).mean() * 100
            avg_ret = subset['outcome_5d'].mean()
            results.append({
                'combo': f"{name1} + {name2}", 'n': n, 'pct_kept': n/baseline_n*100,
                'sl_rate': sl_rate, 'wr': wr, 'avg_ret': avg_ret,
                'd_sl': sl_rate - baseline_sl, 'd_wr': wr - baseline_wr
            })

    # Triples (only promising combos)
    promising_singles = [r['combo'] for r in results if r['d_sl'] < -3 and r['n'] > 100]
    for i, name1 in enumerate(promising_singles):
        for j, name2 in enumerate(promising_singles[i+1:]):
            for name3 in promising_singles[i+j+2:]:
                if name1 in atomic_filters and name2 in atomic_filters and name3 in atomic_filters:
                    mask = atomic_filters[name1](valid) & atomic_filters[name2](valid) & atomic_filters[name3](valid)
                    subset = valid[mask]
                    if len(subset) < 30:
                        continue
                    n = len(subset)
                    sl_rate = subset['SL_hit'].mean() * 100
                    wr = (subset['outcome_5d'] > 0).mean() * 100
                    avg_ret = subset['outcome_5d'].mean()
                    results.append({
                        'combo': f"{name1} + {name2} + {name3}", 'n': n, 'pct_kept': n/baseline_n*100,
                        'sl_rate': sl_rate, 'wr': wr, 'avg_ret': avg_ret,
                        'd_sl': sl_rate - baseline_sl, 'd_wr': wr - baseline_wr
                    })

    # Sort by SL reduction
    results.sort(key=lambda x: x['sl_rate'])

    print(f"\nBASELINE: n={baseline_n}, SL_hit={baseline_sl:.1f}%, WR={baseline_wr:.1f}%, avg_ret={baseline_ret:.2f}%")

    # Show TOP 30 by lowest SL hit rate (min n=40)
    print(f"\n--- TOP 30 by Lowest SL Hit Rate (min n=40) ---")
    print(f"{'#':>3} {'Combo':<45} {'n':>5} {'%kept':>6} {'SL%':>6} {'dSL':>6} {'WR%':>6} {'dWR':>5} {'avg_ret':>8}")
    print("-" * 100)

    shown = 0
    for r in results:
        if r['n'] < 40:
            continue
        shown += 1
        if shown > 30:
            break
        print(f"{shown:>3} {r['combo']:<45} {r['n']:>5} {r['pct_kept']:>5.1f}% {r['sl_rate']:>5.1f}% {r['d_sl']:>+5.1f} {r['wr']:>5.1f}% {r['d_wr']:>+4.1f} {r['avg_ret']:>+7.2f}%")

    # Pareto frontier: best WR:SL tradeoff
    print(f"\n--- PARETO FRONTIER: Best WR given SL constraints (min n=50) ---")
    print(f"{'SL_max':>7} {'Best Combo':<45} {'n':>5} {'SL%':>6} {'WR%':>6} {'avg_ret':>8}")
    print("-" * 85)

    for sl_max in [35, 40, 45, 50, 55]:
        candidates = [r for r in results if r['sl_rate'] <= sl_max and r['n'] >= 50]
        if candidates:
            best = max(candidates, key=lambda x: x['wr'])
            print(f"{sl_max:>6}% {best['combo']:<45} {best['n']:>5} {best['sl_rate']:>5.1f}% {best['wr']:>5.1f}% {best['avg_ret']:>+7.2f}%")
        else:
            print(f"{sl_max:>6}% --- no combo found ---")

    # Best avg return combos
    print(f"\n--- TOP 10 by Best Average Return (min n=50) ---")
    by_ret = sorted([r for r in results if r['n'] >= 50], key=lambda x: x['avg_ret'], reverse=True)
    print(f"{'#':>3} {'Combo':<45} {'n':>5} {'SL%':>6} {'WR%':>6} {'avg_ret':>8}")
    print("-" * 80)
    for i, r in enumerate(by_ret[:10]):
        print(f"{i+1:>3} {r['combo']:<45} {r['n']:>5} {r['sl_rate']:>5.1f}% {r['wr']:>5.1f}% {r['avg_ret']:>+7.2f}%")

    # Best "efficiency" combos: minimize SL while keeping WR > baseline
    print(f"\n--- TOP 10 'Efficient' Combos: SL drop without WR drop (WR >= {baseline_wr:.0f}%, n >= 50) ---")
    efficient = [r for r in results if r['wr'] >= baseline_wr and r['n'] >= 50]
    efficient.sort(key=lambda x: x['sl_rate'])
    print(f"{'#':>3} {'Combo':<45} {'n':>5} {'SL%':>6} {'dSL':>6} {'WR%':>6} {'avg_ret':>8}")
    print("-" * 90)
    for i, r in enumerate(efficient[:10]):
        print(f"{i+1:>3} {r['combo']:<45} {r['n']:>5} {r['sl_rate']:>5.1f}% {r['d_sl']:>+5.1f} {r['wr']:>5.1f}% {r['avg_ret']:>+7.2f}%")

def analysis_9_sector(df):
    """Bonus: SL hit rate by sector"""
    print_separator("BONUS: SL Hit Rate by Sector")

    valid = df.dropna(subset=['sector', 'SL_hit', 'outcome_5d'])

    print(f"\n{'Sector':<30} {'n':>5} {'SL_hit%':>8} {'WR%':>6} {'avg_ret':>8} {'avg_maxDD':>10}")
    print("-" * 75)

    sector_stats = []
    for sector in valid['sector'].unique():
        group = valid[valid['sector'] == sector]
        if len(group) < 10:
            continue
        sector_stats.append({
            'sector': sector,
            'n': len(group),
            'sl_rate': group['SL_hit'].mean() * 100,
            'wr': (group['outcome_5d'] > 0).mean() * 100,
            'avg_ret': group['outcome_5d'].mean(),
            'avg_dd': group['outcome_max_dd_5d'].mean()
        })

    sector_stats.sort(key=lambda x: x['sl_rate'])
    for s in sector_stats:
        print(f"{s['sector']:<30} {s['n']:>5} {s['sl_rate']:>7.1f}% {s['wr']:>5.1f}% {s['avg_ret']:>+7.2f}% {s['avg_dd']:>9.2f}%")

def main():
    print("=" * 90)
    print("  COMPREHENSIVE STOP-LOSS HIT RATE ANALYSIS")
    print("  Goal: Reduce SL hits WITHOUT widening SL (keep 3% or tighter)")
    print("=" * 90)

    # Load data
    combined, so_df = load_data()
    print(f"\nDataset: {len(combined)} unique (scan_date, symbol) rows")
    print(f"  Backfill: {(combined['source']=='backfill').sum()}")
    print(f"  Live:     {(combined['source']=='live').sum()}")
    print(f"  SL hit rate (max_dd <= -3%): {combined['SL_hit'].mean()*100:.1f}%")
    print(f"  WR (outcome_5d > 0):         {(combined['outcome_5d'] > 0).mean()*100:.1f}%")
    print(f"  Avg outcome_5d:              {combined['outcome_5d'].mean():.2f}%")
    print(f"  Avg max_dd_5d:               {combined['outcome_max_dd_5d'].mean():.2f}%")
    print(f"  Avg max_gain_5d:             {combined['outcome_max_gain_5d'].mean():.2f}%")

    # Run all analyses
    top_features = analysis_1(combined)
    analysis_2(combined, top_features)
    filter_results = analysis_3(combined)
    analysis_4(combined)
    analysis_5(combined)
    analysis_6(combined, so_df)
    scored = analysis_7(combined)
    analysis_8(combined)
    analysis_9_sector(combined)

    # Final summary
    print_separator("EXECUTIVE SUMMARY & RECOMMENDATIONS")
    print("""
KEY FINDINGS:
(See numbered analyses above for full details)

The analysis tested:
1. Feature ICs with SL hits - which features predict stop-loss hits
2. Quintile analysis - safe zones for top predictive features
3. Individual filters - 25+ single-filter tests
4. Different SL levels - is tighter SL better or worse?
5. ATR-proportional SL - dynamic SL based on volatility
6. Time-based analysis - when do SL hits occur?
7. Safety score - composite SL avoidance score
8. Combined filters - Pareto frontier of best combinations
9. Sector analysis - which sectors are safest?

REVIEW THE TABLES ABOVE TO IDENTIFY:
- Top features predicting SL avoidance
- Best single and combo filters
- Whether tighter or dynamic SL improves EV
- Whether time-based entry delay helps
    """)

if __name__ == "__main__":
    main()
