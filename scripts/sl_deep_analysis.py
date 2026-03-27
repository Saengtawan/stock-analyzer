#!/usr/bin/env python3
"""
Deep SL Analysis for Discovery System
SL definition: outcome_max_dd_5d <= -3.0%
"""

import sqlite3
import numpy as np
import pandas as pd
from itertools import combinations
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

DB_PATH = 'data/trade_history.db'
SL_THRESHOLD = -3.0

def load_data():
    """Load and merge backfill + signal_outcomes into one unified DataFrame."""
    conn = None  # via get_session()

    # Load backfill
    bf = pd.read_sql_query("""
        SELECT scan_date, symbol, sector, scan_price,
               atr_pct, entry_rsi, distance_from_20d_high,
               momentum_5d, momentum_20d, volume_ratio, vix_at_signal,
               outcome_5d, outcome_max_gain_5d, outcome_max_dd_5d
        FROM backfill_signal_outcomes
        WHERE outcome_max_dd_5d IS NOT NULL
          AND outcome_max_gain_5d IS NOT NULL
    """, conn)
    bf['source'] = 'backfill'

    # Load signal_outcomes (use distance_from_20d_high)
    so = pd.read_sql_query("""
        SELECT scan_date, symbol, sector, scan_price,
               atr_pct, entry_rsi, distance_from_20d_high,
               momentum_5d, momentum_20d, volume_ratio, vix_at_signal,
               outcome_5d, outcome_max_gain_5d, outcome_max_dd_5d
        FROM signal_outcomes
        WHERE outcome_max_dd_5d IS NOT NULL
          AND outcome_max_gain_5d IS NOT NULL
    """, conn)
    so['source'] = 'signal'

    # Merge
    df = pd.concat([bf, so], ignore_index=True)

    # Deduplicate on (symbol, scan_date) keeping backfill (more complete)
    df = df.sort_values('source').drop_duplicates(subset=['symbol', 'scan_date'], keep='first').reset_index(drop=True)

    # SL flag
    df['sl_hit'] = (df['outcome_max_dd_5d'] <= SL_THRESHOLD).astype(int)

    # Load macro
    macro = pd.read_sql_query("SELECT * FROM macro_snapshots", conn)
    macro['date'] = pd.to_datetime(macro['date'])

    # Load breadth
    breadth = pd.read_sql_query("SELECT * FROM market_breadth", conn)
    breadth['date'] = pd.to_datetime(breadth['date'])

    conn.close()

    # Convert scan_date to datetime for merging
    df['scan_date_dt'] = pd.to_datetime(df['scan_date'])

    # Merge macro (asof join: latest macro on or before scan_date)
    macro_sorted = macro.sort_values('date')
    df_sorted = df.sort_values('scan_date_dt')
    df = pd.merge_asof(df_sorted, macro_sorted[['date', 'vix_close', 'spy_close', 'crude_close',
                                                   'gold_close', 'yield_10y', 'yield_spread', 'regime_label']],
                        left_on='scan_date_dt', right_on='date', direction='backward')

    # Merge breadth
    breadth_sorted = breadth.sort_values('date')
    df = pd.merge_asof(df.sort_values('scan_date_dt'),
                        breadth_sorted[['date', 'pct_above_20d_ma', 'ad_ratio', 'new_52w_highs', 'new_52w_lows']],
                        left_on='scan_date_dt', right_on='date', direction='backward',
                        suffixes=('', '_breadth'))

    # Compute vix_delta_5d from macro
    macro_sorted = macro_sorted.set_index('date')
    vix_delta = {}
    for d in df['scan_date_dt'].unique():
        d_ts = pd.Timestamp(d)
        d_5 = d_ts - pd.Timedelta(days=7)  # ~5 trading days
        current = macro_sorted[macro_sorted.index <= d_ts]['vix_close'].iloc[-1] if len(macro_sorted[macro_sorted.index <= d_ts]) > 0 else np.nan
        past = macro_sorted[macro_sorted.index <= d_5]['vix_close'].iloc[-1] if len(macro_sorted[macro_sorted.index <= d_5]) > 0 else np.nan
        vix_delta[d] = current - past if not np.isnan(current) and not np.isnan(past) else np.nan
    df['vix_delta_5d'] = df['scan_date_dt'].map(vix_delta)

    print(f"Total signals loaded: {len(df)}")
    print(f"SL hits (max_dd <= {SL_THRESHOLD}%): {df['sl_hit'].sum()} ({100*df['sl_hit'].mean():.1f}%)")
    print(f"Date range: {df['scan_date'].min()} to {df['scan_date'].max()}")
    print(f"Unique symbols: {df['symbol'].nunique()}")
    print(f"Unique dates: {df['scan_date'].nunique()}")
    print()

    return df, macro, breadth


def analysis_1_sl_path(df):
    """ANALYSIS 1: SL PATH ANALYSIS"""
    print("=" * 80)
    print("ANALYSIS 1: SL PATH ANALYSIS")
    print("=" * 80)

    sl = df[df['sl_hit'] == 1].copy()
    total_sl = len(sl)
    print(f"\nTotal SL hits: {total_sl}")

    # --- Day-by-day SL timing ---
    # We only have max_dd over 5 days, not day-by-day. But we have outcome_1d..5d in signal_outcomes.
    # For backfill we only have outcome_5d. Let's use what we can.
    # Use the magnitude of max_dd relative to outcome_5d as a proxy.
    # Actually, let's load day-by-day from signal_outcomes where available
    conn = None  # via get_session()
    dayby = pd.read_sql_query("""
        SELECT scan_date, symbol, outcome_1d, outcome_2d, outcome_3d, outcome_4d, outcome_5d,
               outcome_max_dd_5d, outcome_max_gain_5d
        FROM signal_outcomes
        WHERE outcome_max_dd_5d IS NOT NULL
          AND outcome_1d IS NOT NULL
          AND outcome_2d IS NOT NULL
    """, conn)

    # Also check backfill for day-by-day (probably not available)
    bf_cols = pd.read_sql_query("PRAGMA table_info(backfill_signal_outcomes)", conn)
    bf_col_names = bf_cols['name'].tolist()

    # backfill_signal_outcomes has outcome_5d but let's check for 1d-4d
    has_dayby_bf = all(c in bf_col_names for c in ['outcome_1d', 'outcome_2d', 'outcome_3d', 'outcome_4d'])
    if has_dayby_bf:
        bf_dayby = pd.read_sql_query("""
            SELECT scan_date, symbol, outcome_1d, outcome_2d, outcome_3d, outcome_4d, outcome_5d,
                   outcome_max_dd_5d, outcome_max_gain_5d
            FROM backfill_signal_outcomes
            WHERE outcome_max_dd_5d IS NOT NULL
              AND outcome_1d IS NOT NULL
        """, conn)
        dayby = pd.concat([dayby, bf_dayby]).drop_duplicates(subset=['symbol', 'scan_date'], keep='first')
    conn.close()

    if len(dayby) > 0:
        dayby_sl = dayby[dayby['outcome_max_dd_5d'] <= SL_THRESHOLD].copy()
        print(f"\nSignals with day-by-day data AND SL hit: {len(dayby_sl)}")

        if len(dayby_sl) > 0:
            # Check which day first hits SL
            day_cols = ['outcome_1d', 'outcome_2d', 'outcome_3d', 'outcome_4d', 'outcome_5d']
            first_sl_day = []
            for _, row in dayby_sl.iterrows():
                hit_day = None
                for i, col in enumerate(day_cols):
                    val = row[col]
                    if pd.notna(val) and val <= SL_THRESHOLD:
                        hit_day = i + 1
                        break
                first_sl_day.append(hit_day)

            dayby_sl['first_sl_day'] = first_sl_day
            identified = dayby_sl[dayby_sl['first_sl_day'].notna()]
            print(f"\n--- When does SL get hit? (n={len(identified)} with identifiable day) ---")

            for day in range(1, 6):
                n = (identified['first_sl_day'] == day).sum()
                pct = 100 * n / len(identified) if len(identified) > 0 else 0
                print(f"  Day {day}: {n:4d} ({pct:5.1f}%)")

            # Cumulative
            print(f"\n  Cumulative SL hit by day:")
            cum = 0
            for day in range(1, 6):
                cum += (identified['first_sl_day'] == day).sum()
                pct = 100 * cum / len(identified) if len(identified) > 0 else 0
                print(f"  By Day {day}: {cum:4d} ({pct:5.1f}%)")

            unidentified = len(dayby_sl) - len(identified)
            if unidentified > 0:
                print(f"\n  NOTE: {unidentified} SL hits where max_dd <= -3% but no single day reached -3%")
                print(f"  (intraday drawdown exceeded threshold but day's close recovered)")
    else:
        print("\n  No day-by-day outcome data available for timing analysis.")

    # --- SL Path Classification ---
    print(f"\n--- SL Path Classification (all {total_sl} SL hits) ---")

    immediate = sl[(sl['outcome_max_dd_5d'] <= SL_THRESHOLD) & (sl['outcome_max_gain_5d'] < 1.0)]
    head_fake = sl[(sl['outcome_max_gain_5d'] >= 2.0) & (sl['outcome_max_dd_5d'] <= SL_THRESHOLD)]
    slow_bleed = sl[(sl['outcome_max_dd_5d'] > -5.0) & (sl['outcome_max_dd_5d'] <= SL_THRESHOLD) & (sl['outcome_max_gain_5d'] < 2.0)]
    catastrophe = sl[sl['outcome_max_dd_5d'] < -5.0]

    # Remove overlap: immediate crash is a subset of slow_bleed, so redefine
    # immediate = max_gain < 1% (never went up much)
    # slow_bleed = max_dd between -3% and -5% AND max_gain between 1% and 2%
    # head_fake = max_gain >= 2%
    # catastrophe = max_dd < -5%

    # Better: mutually exclusive classification
    cats = []
    for _, row in sl.iterrows():
        dd = row['outcome_max_dd_5d']
        gain = row['outcome_max_gain_5d']
        if dd < -5.0:
            cats.append('catastrophe')
        elif gain >= 2.0:
            cats.append('head_fake')
        elif gain < 1.0:
            cats.append('immediate_crash')
        else:
            cats.append('slow_bleed')
    sl = sl.copy()
    sl['sl_type'] = cats

    for stype in ['immediate_crash', 'head_fake', 'slow_bleed', 'catastrophe']:
        subset = sl[sl['sl_type'] == stype]
        n = len(subset)
        pct = 100 * n / total_sl if total_sl > 0 else 0
        avg_dd = subset['outcome_max_dd_5d'].mean()
        avg_gain = subset['outcome_max_gain_5d'].mean()
        avg_5d = subset['outcome_5d'].mean()
        print(f"\n  {stype.upper()}")
        print(f"    n={n} ({pct:.1f}% of SL hits)")
        print(f"    Avg max_dd: {avg_dd:.2f}%  |  Avg max_gain: {avg_gain:.2f}%  |  Avg outcome_5d: {avg_5d:.2f}%")

    # --- Gain before DD analysis ---
    print(f"\n--- Gain-before-DD analysis (proxy: max_gain vs max_dd magnitude) ---")
    # If max_gain is high relative to |max_dd|, it likely went up before crashing
    sl_copy = sl.copy()
    sl_copy['gain_dd_ratio'] = sl_copy['outcome_max_gain_5d'] / sl_copy['outcome_max_dd_5d'].abs()
    print(f"  Signals where gain > 50% of |dd| (went up first, then crashed): "
          f"{(sl_copy['gain_dd_ratio'] > 0.5).sum()} ({100*(sl_copy['gain_dd_ratio'] > 0.5).mean():.1f}%)")
    print(f"  Signals where gain < 25% of |dd| (crashed without recovery attempt): "
          f"{(sl_copy['gain_dd_ratio'] < 0.25).sum()} ({100*(sl_copy['gain_dd_ratio'] < 0.25).mean():.1f}%)")
    print(f"  Median gain/|dd| ratio: {sl_copy['gain_dd_ratio'].median():.3f}")

    return sl


def analysis_2_feature_heatmap(df):
    """ANALYSIS 2: FEATURE INTERACTION HEATMAP"""
    print("\n" + "=" * 80)
    print("ANALYSIS 2: FEATURE INTERACTION HEATMAP")
    print("=" * 80)

    features = ['atr_pct', 'distance_from_20d_high', 'volume_ratio', 'momentum_20d',
                'momentum_5d', 'entry_rsi', 'vix_at_signal']

    # Compute percentile buckets
    df_work = df.copy()
    for feat in features:
        valid = df_work[feat].dropna()
        if len(valid) < 10:
            print(f"  WARNING: {feat} has only {len(valid)} non-null values, skipping")
            continue
        p33 = valid.quantile(0.333)
        p67 = valid.quantile(0.667)
        df_work[f'{feat}_level'] = pd.cut(df_work[feat], bins=[-np.inf, p33, p67, np.inf],
                                           labels=['low', 'mid', 'high'])
        print(f"  {feat}: low<={p33:.2f}, mid ({p33:.2f},{p67:.2f}], high>{p67:.2f}")

    print(f"\n--- All 2-way Feature Combinations ---")
    print(f"{'Pair':<45} {'Cell':>12} {'SL_Rate':>8} {'N':>6}")
    print("-" * 75)

    dangerous = []  # (pair, cell, sl_rate, n)
    safe = []

    for f1, f2 in combinations(features, 2):
        col1 = f'{f1}_level'
        col2 = f'{f2}_level'
        if col1 not in df_work.columns or col2 not in df_work.columns:
            continue

        subset = df_work.dropna(subset=[col1, col2, 'sl_hit'])
        if len(subset) < 20:
            continue

        for lev1 in ['low', 'mid', 'high']:
            for lev2 in ['low', 'mid', 'high']:
                cell = subset[(subset[col1] == lev1) & (subset[col2] == lev2)]
                n = len(cell)
                if n < 10:
                    continue
                sl_rate = cell['sl_hit'].mean()
                cell_label = f"{lev1}/{lev2}"

                if sl_rate > 0.50:
                    dangerous.append((f"{f1} x {f2}", cell_label, sl_rate, n))
                if sl_rate < 0.20:
                    safe.append((f"{f1} x {f2}", cell_label, sl_rate, n))

    print(f"\n*** DANGEROUS COMBINATIONS (SL rate > 50%) ***")
    print(f"{'Pair':<45} {'Cell':>12} {'SL_Rate':>8} {'N':>6}")
    print("-" * 75)
    dangerous.sort(key=lambda x: -x[2])
    for pair, cell, rate, n in dangerous:
        print(f"  {pair:<43} {cell:>12} {rate:>7.1%} {n:>6}")

    if not dangerous:
        print("  (None found with >50% SL rate and n>=10)")
        # Lower threshold
        print(f"\n*** HIGH RISK COMBINATIONS (SL rate > 40%) ***")
        high_risk = [(p, c, r, n) for p, c, r, n in dangerous if r > 0.40]
        # Recompute with lower threshold
        for f1, f2 in combinations(features, 2):
            col1 = f'{f1}_level'
            col2 = f'{f2}_level'
            if col1 not in df_work.columns or col2 not in df_work.columns:
                continue
            subset = df_work.dropna(subset=[col1, col2, 'sl_hit'])
            for lev1 in ['low', 'mid', 'high']:
                for lev2 in ['low', 'mid', 'high']:
                    cell = subset[(subset[col1] == lev1) & (subset[col2] == lev2)]
                    n = len(cell)
                    if n < 10:
                        continue
                    sl_rate = cell['sl_hit'].mean()
                    if sl_rate > 0.40:
                        high_risk.append((f"{f1} x {f2}", f"{lev1}/{lev2}", sl_rate, n))
        high_risk.sort(key=lambda x: -x[2])
        for pair, cell, rate, n in high_risk[:20]:
            print(f"  {pair:<43} {cell:>12} {rate:>7.1%} {n:>6}")

    print(f"\n*** SAFE COMBINATIONS (SL rate < 20%) ***")
    print(f"{'Pair':<45} {'Cell':>12} {'SL_Rate':>8} {'N':>6}")
    print("-" * 75)
    safe.sort(key=lambda x: x[2])
    for pair, cell, rate, n in safe[:20]:
        print(f"  {pair:<43} {cell:>12} {rate:>7.1%} {n:>6}")

    # Full heatmap for top pair
    if dangerous:
        top_pair = dangerous[0][0]
        f1, f2 = top_pair.split(' x ')
    else:
        # Use pair with widest SL range
        f1, f2 = 'atr_pct', 'momentum_5d'

    print(f"\n--- Full Heatmap: {f1} x {f2} ---")
    col1, col2 = f'{f1}_level', f'{f2}_level'
    if col1 in df_work.columns and col2 in df_work.columns:
        subset = df_work.dropna(subset=[col1, col2, 'sl_hit'])
        pivot = subset.groupby([col1, col2])['sl_hit'].agg(['mean', 'count']).unstack(col2)
        print(pivot.to_string())

    return df_work


def analysis_3_sector_feature(df):
    """ANALYSIS 3: SECTOR x FEATURE DEEP DIVE"""
    print("\n" + "=" * 80)
    print("ANALYSIS 3: SECTOR x FEATURE DEEP DIVE")
    print("=" * 80)

    target_sectors = ['Energy', 'Industrials', 'Financial Services', 'Healthcare',
                      'Consumer Cyclical', 'Basic Materials', 'Technology', 'Communication Services']

    features = ['atr_pct', 'distance_from_20d_high', 'volume_ratio', 'momentum_5d',
                'momentum_20d', 'entry_rsi', 'vix_at_signal']

    # Overall baseline
    overall_sl_rate = df['sl_hit'].mean()
    print(f"\nOverall SL rate: {overall_sl_rate:.1%}")

    # All sectors first
    print(f"\n--- All Sectors SL Rate ---")
    sector_stats = df.groupby('sector').agg(
        n=('sl_hit', 'count'),
        sl_hits=('sl_hit', 'sum'),
        sl_rate=('sl_hit', 'mean')
    ).sort_values('n', ascending=False)
    for sector, row in sector_stats.iterrows():
        if row['n'] >= 10:
            print(f"  {sector:<30} n={row['n']:>5}  SL hits={row['sl_hits']:>4}  SL rate={row['sl_rate']:.1%}")

    print(f"\n--- Per-Sector Feature Analysis ---")

    for sector in target_sectors:
        sect_df = df[df['sector'] == sector]
        if len(sect_df) < 20:
            # Try partial match
            sect_df = df[df['sector'].str.contains(sector.split()[0], na=False)]
        if len(sect_df) < 20:
            print(f"\n  {sector}: Insufficient data (n={len(sect_df)}), skipping")
            continue

        sl_rate = sect_df['sl_hit'].mean()
        n_total = len(sect_df)
        n_sl = sect_df['sl_hit'].sum()

        print(f"\n  *** {sector} (n={n_total}, SL hits={n_sl}, SL rate={sl_rate:.1%}) ***")

        # Correlation of each feature with SL within this sector
        best_corr = 0
        best_feat = None
        correlations = {}
        for feat in features:
            valid = sect_df[[feat, 'sl_hit']].dropna()
            if len(valid) < 20:
                continue
            corr, pval = stats.pointbiserialr(valid['sl_hit'], valid[feat])
            correlations[feat] = (corr, pval, len(valid))
            if abs(corr) > abs(best_corr):
                best_corr = corr
                best_feat = feat

        print(f"    Feature correlations with SL:")
        for feat, (corr, pval, n) in sorted(correlations.items(), key=lambda x: -abs(x[1][0])):
            sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
            print(f"      {feat:<25} r={corr:+.3f}  p={pval:.4f} {sig}  (n={n})")

        if best_feat:
            print(f"    >> Strongest predictor: {best_feat} (r={best_corr:+.3f})")

            # Danger zone for this sector
            valid = sect_df[[best_feat, 'sl_hit']].dropna()
            for q_label, (lo, hi) in [('Bottom 33%', (0, 0.333)), ('Mid 33%', (0.333, 0.667)), ('Top 33%', (0.667, 1.0))]:
                lo_val = valid[best_feat].quantile(lo)
                hi_val = valid[best_feat].quantile(hi)
                bucket = valid[(valid[best_feat] >= lo_val) & (valid[best_feat] <= hi_val)]
                if len(bucket) > 5:
                    rate = bucket['sl_hit'].mean()
                    flag = " *** DANGER ***" if rate > 0.50 else ""
                    print(f"      {best_feat} {q_label} [{lo_val:.2f}, {hi_val:.2f}]: SL={rate:.1%} (n={len(bucket)}){flag}")


def analysis_4_near_miss(df):
    """ANALYSIS 4: NEAR MISS vs CLEAN WIN vs SL HIT"""
    print("\n" + "=" * 80)
    print("ANALYSIS 4: NEAR MISS vs CLEAN WIN vs SL HIT")
    print("=" * 80)

    # Classify
    df_work = df.copy()
    conditions = [
        (df_work['outcome_max_gain_5d'] >= 3.0) & (df_work['outcome_max_dd_5d'] > -3.0),  # Clean Win
        (df_work['outcome_max_dd_5d'] > -3.0) & (df_work['outcome_max_dd_5d'] <= -2.5),    # Near Miss
        (df_work['outcome_max_dd_5d'] <= -3.0),                                              # SL Hit
    ]
    choices = ['clean_win', 'near_miss', 'sl_hit']
    df_work['class'] = np.select(conditions, choices, default='other')

    for cls in ['clean_win', 'near_miss', 'sl_hit', 'other']:
        n = (df_work['class'] == cls).sum()
        pct = 100 * n / len(df_work)
        print(f"  {cls:<15} n={n:>5} ({pct:.1f}%)")

    features = ['atr_pct', 'distance_from_20d_high', 'volume_ratio', 'momentum_5d',
                'momentum_20d', 'entry_rsi', 'vix_at_signal']

    print(f"\n--- Feature Distributions by Class ---")
    print(f"{'Feature':<25} {'Clean Win':>14} {'Near Miss':>14} {'SL Hit':>14} {'NM-SL Diff':>12}")
    print("-" * 85)

    for feat in features:
        vals = {}
        for cls in ['clean_win', 'near_miss', 'sl_hit']:
            subset = df_work[df_work['class'] == cls][feat].dropna()
            vals[cls] = (subset.median(), subset.mean(), len(subset))

        cw = vals['clean_win']
        nm = vals['near_miss']
        sl = vals['sl_hit']
        diff = nm[1] - sl[1]  # mean difference near_miss - sl_hit

        print(f"  {feat:<23} {cw[1]:>7.2f} (n={cw[2]:>4}) {nm[1]:>7.2f} (n={nm[2]:>4}) {sl[1]:>7.2f} (n={sl[2]:>4}) {diff:>+10.3f}")

    # Statistical tests: near_miss vs sl_hit
    print(f"\n--- Statistical Tests: Near Miss vs SL Hit ---")
    for feat in features:
        nm_vals = df_work[df_work['class'] == 'near_miss'][feat].dropna()
        sl_vals = df_work[df_work['class'] == 'sl_hit'][feat].dropna()
        if len(nm_vals) < 5 or len(sl_vals) < 5:
            continue
        stat, pval = stats.mannwhitneyu(nm_vals, sl_vals, alternative='two-sided')
        sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else "n.s."
        effect_size = (nm_vals.mean() - sl_vals.mean()) / sl_vals.std() if sl_vals.std() > 0 else 0
        print(f"  {feat:<25} p={pval:.4f} {sig:>4}  Cohen's d={effect_size:+.3f}")

    # Outcome profiles
    print(f"\n--- Outcome Profiles ---")
    for cls in ['clean_win', 'near_miss', 'sl_hit']:
        subset = df_work[df_work['class'] == cls]
        print(f"\n  {cls.upper()} (n={len(subset)}):")
        print(f"    outcome_5d:        mean={subset['outcome_5d'].mean():+.2f}%  median={subset['outcome_5d'].median():+.2f}%")
        print(f"    max_gain_5d:       mean={subset['outcome_max_gain_5d'].mean():+.2f}%  median={subset['outcome_max_gain_5d'].median():+.2f}%")
        print(f"    max_dd_5d:         mean={subset['outcome_max_dd_5d'].mean():+.2f}%  median={subset['outcome_max_dd_5d'].median():+.2f}%")


def analysis_5_temporal(df, macro, breadth):
    """ANALYSIS 5: TEMPORAL CLUSTERING"""
    print("\n" + "=" * 80)
    print("ANALYSIS 5: TEMPORAL CLUSTERING")
    print("=" * 80)

    # Per-date SL rate
    date_stats = df.groupby('scan_date').agg(
        n_signals=('sl_hit', 'count'),
        n_sl=('sl_hit', 'sum'),
        sl_rate=('sl_hit', 'mean')
    ).reset_index()

    # Classify dates
    date_stats['day_type'] = pd.cut(date_stats['sl_rate'],
                                     bins=[-0.01, 0.20, 0.40, 0.60, 1.01],
                                     labels=['good', 'normal', 'bad', 'massacre'])

    print(f"\n--- Date Classification ---")
    for dtype in ['good', 'normal', 'bad', 'massacre']:
        subset = date_stats[date_stats['day_type'] == dtype]
        n_dates = len(subset)
        n_signals = subset['n_signals'].sum()
        n_sl = subset['n_sl'].sum()
        avg_sl = subset['sl_rate'].mean()
        print(f"  {dtype:<10}: {n_dates:>3} dates, {n_signals:>5} signals, {n_sl:>4} SL hits, avg SL rate={avg_sl:.1%}")

    # Top massacre dates
    print(f"\n--- Top 15 Worst Dates (massacre + bad) ---")
    worst = date_stats.sort_values('sl_rate', ascending=False).head(15)
    for _, row in worst.iterrows():
        print(f"  {row['scan_date']}  SL rate={row['sl_rate']:.1%}  ({row['n_sl']}/{row['n_signals']} signals)")

    # Merge macro+breadth with date_stats
    date_stats['scan_date_dt'] = pd.to_datetime(date_stats['scan_date'])
    macro['date'] = pd.to_datetime(macro['date'])
    breadth['date'] = pd.to_datetime(breadth['date'])

    date_merged = pd.merge_asof(date_stats.sort_values('scan_date_dt'),
                                 macro.sort_values('date')[['date', 'vix_close', 'spy_close', 'crude_close',
                                                             'gold_close', 'yield_10y', 'yield_spread', 'regime_label']],
                                 left_on='scan_date_dt', right_on='date', direction='backward')
    date_merged = pd.merge_asof(date_merged.sort_values('scan_date_dt'),
                                 breadth.sort_values('date')[['date', 'pct_above_20d_ma', 'ad_ratio',
                                                               'new_52w_highs', 'new_52w_lows']],
                                 left_on='scan_date_dt', right_on='date', direction='backward',
                                 suffixes=('', '_b'))

    # Macro comparison: massacre vs good
    print(f"\n--- Macro Features: Massacre Dates vs Good Dates ---")
    macro_feats = ['vix_close', 'spy_close', 'yield_10y', 'yield_spread', 'crude_close',
                   'gold_close', 'pct_above_20d_ma', 'ad_ratio', 'new_52w_highs', 'new_52w_lows']

    print(f"{'Feature':<25} {'Massacre avg':>14} {'Good avg':>14} {'Diff':>10} {'p-value':>10}")
    print("-" * 78)

    massacre = date_merged[date_merged['day_type'] == 'massacre']
    good = date_merged[date_merged['day_type'] == 'good']

    for feat in macro_feats:
        m_vals = massacre[feat].dropna()
        g_vals = good[feat].dropna()
        if len(m_vals) < 3 or len(g_vals) < 3:
            continue
        m_mean = m_vals.mean()
        g_mean = g_vals.mean()
        diff = m_mean - g_mean
        try:
            _, pval = stats.mannwhitneyu(m_vals, g_vals, alternative='two-sided')
        except:
            pval = np.nan
        sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
        print(f"  {feat:<23} {m_mean:>12.2f} {g_mean:>12.2f} {diff:>+10.2f} {pval:>9.4f} {sig}")

    # LEADING INDICATOR: Check 1-3 days before
    print(f"\n--- Leading Indicators (1-3 days before scan_date) ---")
    macro_sorted = macro.sort_values('date').set_index('date')

    for lag in [1, 2, 3]:
        print(f"\n  Lag = {lag} day(s) before scan:")
        for feat in ['vix_close', 'spy_close', 'pct_above_20d_ma', 'ad_ratio', 'yield_spread']:
            lag_vals = []
            for _, row in date_merged.iterrows():
                d = row['scan_date_dt'] - pd.Timedelta(days=lag)
                # Find closest date
                before = macro_sorted[macro_sorted.index <= d]
                if len(before) > 0 and feat in before.columns:
                    lag_vals.append(before[feat].iloc[-1])
                elif feat in ['pct_above_20d_ma', 'ad_ratio']:
                    breadth_sorted = breadth.sort_values('date').set_index('date')
                    before_b = breadth_sorted[breadth_sorted.index <= d]
                    if len(before_b) > 0 and feat in before_b.columns:
                        lag_vals.append(before_b[feat].iloc[-1])
                    else:
                        lag_vals.append(np.nan)
                else:
                    lag_vals.append(np.nan)

            date_merged[f'{feat}_lag{lag}'] = lag_vals
            valid = date_merged[[f'{feat}_lag{lag}', 'sl_rate']].dropna()
            if len(valid) > 10:
                corr, pval = stats.pearsonr(valid[f'{feat}_lag{lag}'], valid['sl_rate'])
                sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
                print(f"    {feat:<25} corr with SL_rate: {corr:+.3f}  p={pval:.4f} {sig}")


def analysis_6_sequential(df):
    """ANALYSIS 6: SEQUENTIAL PATTERN"""
    print("\n" + "=" * 80)
    print("ANALYSIS 6: SEQUENTIAL PATTERN")
    print("=" * 80)

    # --- Per-Stock Sequential Pattern ---
    print(f"\n--- Stock-Level Sequential Pattern ---")
    multi_stocks = df.groupby('symbol').filter(lambda x: len(x) >= 2)
    multi_symbols = multi_stocks['symbol'].unique()
    print(f"  Stocks with 2+ signals: {len(multi_symbols)}")

    prev_sl_next_sl = 0
    prev_sl_next_ok = 0
    prev_ok_next_sl = 0
    prev_ok_next_ok = 0

    for sym in multi_symbols:
        sym_df = df[df['symbol'] == sym].sort_values('scan_date').reset_index(drop=True)
        for i in range(1, len(sym_df)):
            prev_sl = sym_df.iloc[i-1]['sl_hit']
            curr_sl = sym_df.iloc[i]['sl_hit']
            if prev_sl == 1 and curr_sl == 1:
                prev_sl_next_sl += 1
            elif prev_sl == 1 and curr_sl == 0:
                prev_sl_next_ok += 1
            elif prev_sl == 0 and curr_sl == 1:
                prev_ok_next_sl += 1
            else:
                prev_ok_next_ok += 1

    total_pairs = prev_sl_next_sl + prev_sl_next_ok + prev_ok_next_sl + prev_ok_next_ok
    print(f"\n  Transition Matrix (n={total_pairs} sequential pairs):")
    print(f"  {'':>15} {'Next=SL':>10} {'Next=OK':>10} {'SL rate':>10}")
    if prev_sl_next_sl + prev_sl_next_ok > 0:
        after_sl_rate = prev_sl_next_sl / (prev_sl_next_sl + prev_sl_next_ok)
        print(f"  {'Prev=SL':<15} {prev_sl_next_sl:>10} {prev_sl_next_ok:>10} {after_sl_rate:>9.1%}")
    if prev_ok_next_sl + prev_ok_next_ok > 0:
        after_ok_rate = prev_ok_next_sl / (prev_ok_next_sl + prev_ok_next_ok)
        print(f"  {'Prev=OK':<15} {prev_ok_next_sl:>10} {prev_ok_next_ok:>10} {after_ok_rate:>9.1%}")

    if total_pairs > 0:
        base_rate = (prev_sl_next_sl + prev_ok_next_sl) / total_pairs
        print(f"\n  Base SL rate (all pairs): {base_rate:.1%}")
        if prev_sl_next_sl + prev_sl_next_ok > 0:
            print(f"  SL rate after prev SL:    {after_sl_rate:.1%} (lift: {after_sl_rate - base_rate:+.1%})")
        if prev_ok_next_sl + prev_ok_next_ok > 0:
            print(f"  SL rate after prev OK:    {after_ok_rate:.1%} (lift: {after_ok_rate - base_rate:+.1%})")

        # Chi-square test
        try:
            chi2, p, dof, expected = stats.chi2_contingency([
                [prev_sl_next_sl, prev_sl_next_ok],
                [prev_ok_next_sl, prev_ok_next_ok]
            ])
            print(f"\n  Chi-square test: chi2={chi2:.3f}, p={p:.4f} {'***' if p<0.001 else '**' if p<0.01 else '*' if p<0.05 else 'n.s.'}")
        except:
            pass

    # --- Date-Level Sequential Pattern ---
    print(f"\n--- Date-Level Sequential Pattern ---")
    date_stats = df.groupby('scan_date').agg(
        n=('sl_hit', 'count'),
        sl_rate=('sl_hit', 'mean')
    ).sort_index().reset_index()

    date_stats['prev_sl_rate'] = date_stats['sl_rate'].shift(1)
    date_stats['prev_high_sl'] = (date_stats['prev_sl_rate'] > 0.50).astype(int)

    valid_dates = date_stats.dropna(subset=['prev_sl_rate'])

    if len(valid_dates) > 5:
        corr, pval = stats.pearsonr(valid_dates['prev_sl_rate'], valid_dates['sl_rate'])
        print(f"  Autocorrelation of daily SL rate (lag-1): r={corr:+.3f}, p={pval:.4f}")

        after_high = valid_dates[valid_dates['prev_high_sl'] == 1]
        after_low = valid_dates[valid_dates['prev_high_sl'] == 0]

        if len(after_high) > 0:
            print(f"\n  After HIGH SL day (>50%): next day SL rate = {after_high['sl_rate'].mean():.1%} (n={len(after_high)} dates)")
        if len(after_low) > 0:
            print(f"  After LOW SL day (<=50%): next day SL rate = {after_low['sl_rate'].mean():.1%} (n={len(after_low)} dates)")

    # 3-day momentum
    date_stats['sl_rate_3d_avg'] = date_stats['sl_rate'].rolling(3).mean().shift(1)
    valid_3d = date_stats.dropna(subset=['sl_rate_3d_avg'])
    if len(valid_3d) > 5:
        corr, pval = stats.pearsonr(valid_3d['sl_rate_3d_avg'], valid_3d['sl_rate'])
        print(f"\n  3-day rolling SL rate vs next day SL: r={corr:+.3f}, p={pval:.4f}")


def analysis_7_kernel_gaps(df):
    """ANALYSIS 7: WHAT THE KERNEL CAN'T SEE"""
    print("\n" + "=" * 80)
    print("ANALYSIS 7: WHAT THE KERNEL CAN'T SEE")
    print("=" * 80)

    kernel_features = ['distance_from_20d_high', 'atr_pct', 'volume_ratio', 'momentum_20d']
    # atr_risk is derived, not directly in DB

    non_kernel_features = ['momentum_5d', 'entry_rsi', 'vix_at_signal', 'vix_delta_5d',
                           'crude_close', 'gold_close', 'yield_spread', 'yield_10y',
                           'pct_above_20d_ma', 'ad_ratio', 'new_52w_highs', 'new_52w_lows']

    # Also test sector as categorical
    print(f"\n--- Point-Biserial Correlations with SL (binary) ---")
    print(f"{'Feature':<30} {'In Kernel':>10} {'Corr':>8} {'p-value':>10} {'n':>6} {'Status':>12}")
    print("-" * 82)

    all_results = []

    # Kernel features
    for feat in kernel_features:
        valid = df[[feat, 'sl_hit']].dropna()
        if len(valid) < 20:
            continue
        corr, pval = stats.pointbiserialr(valid['sl_hit'], valid[feat])
        sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else "n.s."
        all_results.append((feat, 'YES', corr, pval, len(valid), sig))

    # Non-kernel features
    for feat in non_kernel_features:
        if feat not in df.columns:
            continue
        valid = df[[feat, 'sl_hit']].dropna()
        if len(valid) < 20:
            continue
        corr, pval = stats.pointbiserialr(valid['sl_hit'], valid[feat])
        sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else "n.s."
        candidate = "CANDIDATE" if abs(corr) > 0.10 else ""
        all_results.append((feat, 'NO', corr, pval, len(valid), sig + " " + candidate))

    # Sort by absolute correlation
    all_results.sort(key=lambda x: -abs(x[2]))

    for feat, in_kernel, corr, pval, n, sig in all_results:
        print(f"  {feat:<28} {in_kernel:>10} {corr:>+7.3f} {pval:>10.4f} {n:>6}  {sig}")

    # Sector as categorical
    print(f"\n--- Sector Effect (categorical) ---")
    sector_sl = df.groupby('sector').agg(
        n=('sl_hit', 'count'),
        sl_rate=('sl_hit', 'mean')
    ).sort_values('sl_rate', ascending=False)

    overall_rate = df['sl_hit'].mean()
    for sector, row in sector_sl.iterrows():
        if row['n'] >= 10:
            lift = row['sl_rate'] - overall_rate
            print(f"  {sector:<30} n={row['n']:>5}  SL rate={row['sl_rate']:.1%}  vs baseline: {lift:+.1%}")

    # Cramers V for sector
    valid_sect = df[['sector', 'sl_hit']].dropna()
    ct = pd.crosstab(valid_sect['sector'], valid_sect['sl_hit'])
    if ct.shape[0] > 1 and ct.shape[1] > 1:
        chi2, p, dof, expected = stats.chi2_contingency(ct)
        n_obs = ct.sum().sum()
        cramers_v = np.sqrt(chi2 / (n_obs * (min(ct.shape) - 1)))
        print(f"\n  Cramer's V (sector vs SL): {cramers_v:.3f}  chi2={chi2:.1f}  p={p:.4f}")
        if cramers_v > 0.10:
            print(f"  >> CANDIDATE for kernel expansion (Cramer's V > 0.10)")

    # Interaction: non-kernel features that add info BEYOND kernel features
    print(f"\n--- Incremental Value: Non-Kernel Features ---")
    print(f"  Testing if non-kernel features predict SL AFTER controlling for kernel features...")

    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    # Baseline: kernel-only model
    kernel_cols = [f for f in kernel_features if f in df.columns]
    valid = df[kernel_cols + ['sl_hit']].dropna()
    if len(valid) > 100:
        X_kernel = StandardScaler().fit_transform(valid[kernel_cols])
        y = valid['sl_hit'].values

        try:
            lr_kernel = LogisticRegression(max_iter=1000, random_state=42)
            lr_kernel.fit(X_kernel, y)
            baseline_score = lr_kernel.score(X_kernel, y)
            print(f"  Kernel-only accuracy: {baseline_score:.3f}")

            # Add each non-kernel feature
            for feat in non_kernel_features:
                if feat not in df.columns:
                    continue
                test_cols = kernel_cols + [feat]
                valid_test = df[test_cols + ['sl_hit']].dropna()
                if len(valid_test) < 100:
                    continue
                X_test = StandardScaler().fit_transform(valid_test[test_cols])
                y_test = valid_test['sl_hit'].values
                lr_test = LogisticRegression(max_iter=1000, random_state=42)
                lr_test.fit(X_test, y_test)
                test_score = lr_test.score(X_test, y_test)
                lift = test_score - baseline_score
                indicator = " << ADD" if lift > 0.005 else ""
                print(f"    + {feat:<25} accuracy: {test_score:.3f}  (lift: {lift:+.4f}){indicator}")
        except Exception as e:
            print(f"  Logistic regression failed: {e}")

    # VIX delta deep dive
    print(f"\n--- VIX Delta 5d Deep Dive ---")
    valid_vd = df[['vix_delta_5d', 'sl_hit', 'outcome_5d', 'outcome_max_dd_5d']].dropna()
    if len(valid_vd) > 20:
        for label, lo, hi in [('VIX falling (< -2)', -np.inf, -2),
                                ('VIX stable (-2 to +2)', -2, 2),
                                ('VIX rising (> +2)', 2, np.inf)]:
            bucket = valid_vd[(valid_vd['vix_delta_5d'] >= lo) & (valid_vd['vix_delta_5d'] < hi)]
            if len(bucket) > 5:
                print(f"  {label:<30} n={len(bucket):>5}  SL rate={bucket['sl_hit'].mean():.1%}  "
                      f"avg outcome={bucket['outcome_5d'].mean():+.2f}%  avg dd={bucket['outcome_max_dd_5d'].mean():.2f}%")


def main():
    print("=" * 80)
    print("DISCOVERY SYSTEM — DEEP SL ANALYSIS")
    print(f"SL Threshold: outcome_max_dd_5d <= {SL_THRESHOLD}%")
    print("=" * 80)

    df, macro, breadth = load_data()

    sl_detail = analysis_1_sl_path(df)
    df_work = analysis_2_feature_heatmap(df)
    analysis_3_sector_feature(df)
    analysis_4_near_miss(df)
    analysis_5_temporal(df, macro, breadth)
    analysis_6_sequential(df)
    analysis_7_kernel_gaps(df)

    print("\n" + "=" * 80)
    print("END OF ANALYSIS")
    print("=" * 80)


if __name__ == '__main__':
    main()
