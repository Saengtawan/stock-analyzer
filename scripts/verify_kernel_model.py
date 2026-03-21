#!/usr/bin/env python3
"""
Independent verification of enriched Gaussian Kernel Regression model claims.
Claimed: WR ~59-60%, AvgRet ~+1.2%

Verification agent: reproduce EXACTLY, then stress-test.
"""

import sqlite3
import numpy as np
import pandas as pd
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

DB_PATH = "/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db"

# ─────────────────────────────────────────────────────────────────────
# Data Loading
# ─────────────────────────────────────────────────────────────────────

def load_data():
    """Load and merge all data sources."""
    conn = sqlite3.connect(DB_PATH)

    # 1. Backfill signal outcomes
    bso = pd.read_sql_query("""
        SELECT scan_date, symbol, sector, scan_price, atr_pct, entry_rsi,
               distance_from_20d_high, momentum_5d, momentum_20d, volume_ratio,
               vix_at_signal, outcome_5d, outcome_max_gain_5d, outcome_max_dd_5d
        FROM backfill_signal_outcomes
        WHERE outcome_5d IS NOT NULL
    """, conn)
    bso['source'] = 'backfill'

    # 2. Live signal outcomes (dip_bounce only to match backfill)
    so = pd.read_sql_query("""
        SELECT scan_date, symbol, sector, scan_price, atr_pct, entry_rsi,
               distance_from_20d_high, momentum_5d, momentum_20d, volume_ratio,
               vix_at_signal, outcome_5d, outcome_max_gain_5d, outcome_max_dd_5d,
               new_score
        FROM signal_outcomes
        WHERE outcome_5d IS NOT NULL
          AND signal_source = 'dip_bounce'
    """, conn)
    so['source'] = 'live'

    # 3. Analyst consensus
    analyst = pd.read_sql_query("""
        SELECT symbol, upside_pct FROM analyst_consensus WHERE upside_pct IS NOT NULL
    """, conn)

    # 4. Stock fundamentals
    fundies = pd.read_sql_query("""
        SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL
    """, conn)

    conn.close()

    print("=" * 80)
    print("DATA LOADING SUMMARY")
    print("=" * 80)
    print(f"Backfill rows:       {len(bso):,} ({bso['scan_date'].min()} to {bso['scan_date'].max()})")
    print(f"Live rows:           {len(so):,} ({so['scan_date'].min()} to {so['scan_date'].max()})")
    print(f"Analyst consensus:   {len(analyst):,} symbols with upside_pct")
    print(f"Stock fundamentals:  {len(fundies):,} symbols with beta")

    # 5. Combine backfill + live
    # Ensure column alignment
    if 'new_score' not in bso.columns:
        bso['new_score'] = np.nan
    combined = pd.concat([bso, so], ignore_index=True)

    # 6. Deduplicate: prefer live over backfill
    combined['_priority'] = combined['source'].map({'live': 0, 'backfill': 1})
    combined = combined.sort_values('_priority').drop_duplicates(
        subset=['scan_date', 'symbol'], keep='first'
    ).drop(columns=['_priority'])

    print(f"Combined (deduped):  {len(combined):,}")
    dup_count = len(bso) + len(so) - len(combined)
    print(f"  Duplicates removed: {dup_count}")

    # 7. JOIN with analyst + fundamentals
    combined = combined.merge(analyst, on='symbol', how='left')
    combined = combined.merge(fundies, on='symbol', how='left')

    # 8. Compute atr_risk
    combined['atr_risk'] = combined['atr_pct'] * combined['vix_at_signal'] / 20.0

    print(f"\nAfter joins:")
    print(f"  Rows with upside_pct: {combined['upside_pct'].notna().sum():,} / {len(combined):,} "
          f"({100*combined['upside_pct'].notna().mean():.1f}%)")
    print(f"  Rows with beta:       {combined['beta'].notna().sum():,} / {len(combined):,} "
          f"({100*combined['beta'].notna().mean():.1f}%)")

    # Sort by date
    combined['scan_date'] = pd.to_datetime(combined['scan_date'])
    combined = combined.sort_values('scan_date').reset_index(drop=True)

    return combined


# ─────────────────────────────────────────────────────────────────────
# Gaussian Kernel Regression
# ─────────────────────────────────────────────────────────────────────

def gaussian_kernel(distances_sq, bandwidth):
    """Gaussian kernel: K(u) = exp(-u^2 / (2*bw^2))"""
    return np.exp(-distances_sq / (2 * bandwidth ** 2))


def predict_kernel(X_train, y_train, X_test, bandwidth):
    """
    Kernel regression prediction.
    X_train: (n_train, n_features)
    y_train: (n_train,)
    X_test: (n_test, n_features)
    Returns: predictions (n_test,)
    """
    predictions = np.zeros(len(X_test))
    for i in range(len(X_test)):
        diff = X_train - X_test[i]
        dist_sq = np.sum(diff ** 2, axis=1)
        weights = gaussian_kernel(dist_sq, bandwidth)
        w_sum = weights.sum()
        if w_sum > 1e-12:
            predictions[i] = np.sum(weights * y_train) / w_sum
        else:
            predictions[i] = y_train.mean()
    return predictions


# ─────────────────────────────────────────────────────────────────────
# Model Runner
# ─────────────────────────────────────────────────────────────────────

def run_model(df, features, bandwidth=1.0, top_k=5, min_train_days=20,
              exclude_sectors=None, min_er=None, label='Model'):
    """
    Expanding window kernel regression.
    Returns DataFrame of all picks with predictions.
    """
    if exclude_sectors is None:
        exclude_sectors = []

    # Filter to rows with all required features + outcome
    required_cols = features + ['outcome_5d', 'scan_date', 'symbol', 'sector']
    subset = df.dropna(subset=features + ['outcome_5d']).copy()

    if len(subset) == 0:
        print(f"[{label}] ERROR: No rows with all features present!")
        return pd.DataFrame()

    # Apply sector exclusion to TEST candidates only (not training)
    dates = sorted(subset['scan_date'].unique())

    all_picks = []
    skipped_dates = 0

    for test_date in dates:
        # Train: all data strictly before test_date
        train_mask = subset['scan_date'] < test_date
        train_data = subset[train_mask]

        # Check min training days
        n_train_dates = train_data['scan_date'].nunique()
        if n_train_dates < min_train_days:
            continue

        # Test: data on test_date
        test_mask = subset['scan_date'] == test_date
        test_data = subset[test_mask].copy()

        # Apply sector exclusion to test candidates
        if exclude_sectors:
            test_data = test_data[~test_data['sector'].isin(exclude_sectors)]

        if len(test_data) == 0:
            skipped_dates += 1
            continue

        # Normalize using training data mean/std
        X_train = train_data[features].values.astype(float)
        y_train = train_data['outcome_5d'].values.astype(float)

        train_mean = X_train.mean(axis=0)
        train_std = X_train.std(axis=0)
        train_std[train_std < 1e-10] = 1.0  # avoid div by zero

        X_train_norm = (X_train - train_mean) / train_std

        X_test = test_data[features].values.astype(float)
        X_test_norm = (X_test - train_mean) / train_std

        # Predict
        preds = predict_kernel(X_train_norm, y_train, X_test_norm, bandwidth)
        test_data = test_data.copy()
        test_data['predicted_er'] = preds

        # Apply E[R] filter
        if min_er is not None:
            test_data = test_data[test_data['predicted_er'] >= min_er]

        if len(test_data) == 0:
            skipped_dates += 1
            continue

        # Top K by predicted E[R]
        top = test_data.nlargest(top_k, 'predicted_er')
        all_picks.append(top)

    if not all_picks:
        print(f"[{label}] No picks generated!")
        return pd.DataFrame()

    picks_df = pd.concat(all_picks, ignore_index=True)
    return picks_df


def report_metrics(picks_df, label):
    """Print comprehensive metrics for a set of picks."""
    print(f"\n{'─' * 70}")
    print(f"  {label}")
    print(f"{'─' * 70}")

    if len(picks_df) == 0:
        print("  NO PICKS GENERATED")
        return

    n = len(picks_df)
    n_days = picks_df['scan_date'].nunique()
    outcomes = picks_df['outcome_5d']

    wins = (outcomes > 0).sum()
    wr = 100 * wins / n
    avg_ret = outcomes.mean()
    med_ret = outcomes.median()
    tp_3 = 100 * (outcomes >= 3.0).sum() / n
    sl_3 = 100 * (outcomes <= -3.0).sum() / n
    std_ret = outcomes.std()
    sharpe_like = avg_ret / std_ret if std_ret > 0 else 0

    big_wins = (outcomes >= 5.0).sum()
    big_losses = (outcomes <= -5.0).sum()

    print(f"  Total picks:       {n:,}")
    print(f"  Active days:       {n_days}")
    print(f"  Picks/day:         {n/n_days:.1f}")
    print(f"  Win Rate:          {wr:.1f}%  ({wins}/{n})")
    print(f"  Avg Return:        {avg_ret:+.2f}%")
    print(f"  Median Return:     {med_ret:+.2f}%")
    print(f"  Std Return:        {std_ret:.2f}%")
    print(f"  Sharpe-like:       {sharpe_like:.3f}")
    print(f"  TP >= +3% rate:    {tp_3:.1f}%")
    print(f"  SL <= -3% rate:    {sl_3:.1f}%")
    print(f"  Big wins >= +5%:   {big_wins}")
    print(f"  Big losses <= -5%: {big_losses}")

    # Percentiles
    pcts = [10, 25, 50, 75, 90]
    pct_vals = np.percentile(outcomes, pcts)
    pct_str = " | ".join([f"P{p}={v:+.1f}%" for p, v in zip(pcts, pct_vals)])
    print(f"  Percentiles:       {pct_str}")

    return {
        'n': n, 'days': n_days, 'wr': wr, 'avg_ret': avg_ret,
        'med_ret': med_ret, 'tp3': tp_3, 'sl3': sl_3
    }


# ─────────────────────────────────────────────────────────────────────
# Main Tests
# ─────────────────────────────────────────────────────────────────────

def main():
    df = load_data()

    FEATURES_7 = ['distance_from_20d_high', 'atr_pct', 'volume_ratio',
                   'momentum_20d', 'atr_risk', 'upside_pct', 'beta']
    FEATURES_5 = ['distance_from_20d_high', 'atr_pct', 'volume_ratio',
                   'momentum_20d', 'atr_risk']
    EXCLUDE_SECTORS = ['Technology', 'Semiconductors']

    # ═══════════════════════════════════════════════════════════════════
    # TEST 1: Reproduce enriched kernel model EXACTLY
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("TEST 1: REPRODUCE ENRICHED KERNEL MODEL (Claimed: WR ~59-60%, AvgRet ~+1.2%)")
    print("=" * 80)
    print("Config: 7 features, bw=1.0, top 5, min 20 train days, "
          "exclude Tech+Semi, E[R]>=1.0")

    picks_1 = run_model(df, FEATURES_7, bandwidth=1.0, top_k=5,
                         min_train_days=20, exclude_sectors=EXCLUDE_SECTORS,
                         min_er=1.0, label='Test1')
    m1 = report_metrics(picks_1, "TEST 1: Full Enriched Model (CLAIMED BEST)")

    if m1:
        print(f"\n  >>> CLAIM CHECK: WR={m1['wr']:.1f}% (claimed ~59-60%), "
              f"AvgRet={m1['avg_ret']:+.2f}% (claimed ~+1.2%)")
        wr_match = 57.0 <= m1['wr'] <= 63.0
        ar_match = 0.8 <= m1['avg_ret'] <= 1.6
        print(f"  >>> WR in range [57-63%]:   {'PASS' if wr_match else 'FAIL'}")
        print(f"  >>> AvgRet in range [0.8-1.6%]: {'PASS' if ar_match else 'FAIL'}")

    # ═══════════════════════════════════════════════════════════════════
    # TEST 2: Baseline (no enrichment)
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("TEST 2: BASELINE — 5 features, no sector exclusion, no E[R] filter")
    print("=" * 80)

    picks_2 = run_model(df, FEATURES_5, bandwidth=1.0, top_k=5,
                         min_train_days=20, exclude_sectors=[],
                         min_er=None, label='Test2')
    m2 = report_metrics(picks_2, "TEST 2: Baseline (5 features, no filters)")

    if m1 and m2:
        print(f"\n  >>> IMPROVEMENT over baseline:")
        print(f"      WR:     {m1['wr']:.1f}% vs {m2['wr']:.1f}% ({m1['wr']-m2['wr']:+.1f}pp)")
        print(f"      AvgRet: {m1['avg_ret']:+.2f}% vs {m2['avg_ret']:+.2f}% ({m1['avg_ret']-m2['avg_ret']:+.2f}pp)")

    # ═══════════════════════════════════════════════════════════════════
    # TEST 3: Ablation studies
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("TEST 3: ABLATION — Isolating each component's contribution")
    print("=" * 80)

    # 3a: 7 features, no sector exclusion, no E[R] filter
    print("\n--- 3a: 7 features only (no sector excl, no E[R] filter) ---")
    picks_3a = run_model(df, FEATURES_7, bandwidth=1.0, top_k=5,
                          min_train_days=20, exclude_sectors=[],
                          min_er=None, label='Test3a')
    m3a = report_metrics(picks_3a, "3a: 7 features, no filters")

    # 3b: 7 features + sector exclusion, no E[R] filter
    print("\n--- 3b: 7 features + sector exclusion (no E[R] filter) ---")
    picks_3b = run_model(df, FEATURES_7, bandwidth=1.0, top_k=5,
                          min_train_days=20, exclude_sectors=EXCLUDE_SECTORS,
                          min_er=None, label='Test3b')
    m3b = report_metrics(picks_3b, "3b: 7 features + sector exclusion")

    # 3c: 7 features + E[R] >= 1.0, no sector exclusion
    print("\n--- 3c: 7 features + E[R]>=1.0 (no sector exclusion) ---")
    picks_3c = run_model(df, FEATURES_7, bandwidth=1.0, top_k=5,
                          min_train_days=20, exclude_sectors=[],
                          min_er=1.0, label='Test3c')
    m3c = report_metrics(picks_3c, "3c: 7 features + E[R]>=1.0")

    # 3d: 5 features + sector exclusion + E[R] >= 1.0
    print("\n--- 3d: 5 features + sector exclusion + E[R]>=1.0 ---")
    picks_3d = run_model(df, FEATURES_5, bandwidth=1.0, top_k=5,
                          min_train_days=20, exclude_sectors=EXCLUDE_SECTORS,
                          min_er=1.0, label='Test3d')
    m3d = report_metrics(picks_3d, "3d: 5 features + both filters")

    # Ablation summary
    print(f"\n{'─' * 70}")
    print(f"  ABLATION SUMMARY")
    print(f"{'─' * 70}")
    configs = [
        ('Baseline (5f, no filter)', m2),
        ('3a: 7f only', m3a),
        ('3b: 7f + sector excl', m3b),
        ('3c: 7f + E[R]>=1.0', m3c),
        ('3d: 5f + both filters', m3d),
        ('Full (7f + both filters)', m1),
    ]
    print(f"  {'Config':<30} {'N':>5} {'Days':>5} {'WR':>7} {'AvgRet':>8} {'MedRet':>8} {'TP3%':>6} {'SL3%':>6}")
    for name, m in configs:
        if m:
            print(f"  {name:<30} {m['n']:>5} {m['days']:>5} {m['wr']:>6.1f}% {m['avg_ret']:>+7.2f}% "
                  f"{m['med_ret']:>+7.2f}% {m['tp3']:>5.1f}% {m['sl3']:>5.1f}%")
        else:
            print(f"  {name:<30}  --- no picks ---")

    # ═══════════════════════════════════════════════════════════════════
    # TEST 4: Monthly breakdown of best config
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("TEST 4: MONTHLY BREAKDOWN OF FULL ENRICHED MODEL")
    print("=" * 80)

    if len(picks_1) > 0:
        picks_1['month'] = picks_1['scan_date'].dt.to_period('M')
        monthly = picks_1.groupby('month').agg(
            n=('outcome_5d', 'count'),
            wr=('outcome_5d', lambda x: 100 * (x > 0).mean()),
            avg_ret=('outcome_5d', 'mean'),
            med_ret=('outcome_5d', 'median'),
            min_ret=('outcome_5d', 'min'),
            max_ret=('outcome_5d', 'max'),
        ).reset_index()

        print(f"\n  {'Month':<10} {'N':>5} {'WR':>7} {'AvgRet':>8} {'MedRet':>8} {'Min':>8} {'Max':>8}")
        print(f"  {'─'*10} {'─'*5} {'─'*7} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        for _, row in monthly.iterrows():
            print(f"  {str(row['month']):<10} {row['n']:>5} {row['wr']:>6.1f}% "
                  f"{row['avg_ret']:>+7.2f}% {row['med_ret']:>+7.2f}% "
                  f"{row['min_ret']:>+7.2f}% {row['max_ret']:>+7.2f}%")

        # Flag concern: single-month dominance?
        best_month = monthly.loc[monthly['avg_ret'].idxmax()]
        worst_month = monthly.loc[monthly['avg_ret'].idxmin()]
        print(f"\n  Best month:  {best_month['month']} (AvgRet={best_month['avg_ret']:+.2f}%, n={best_month['n']})")
        print(f"  Worst month: {worst_month['month']} (AvgRet={worst_month['avg_ret']:+.2f}%, n={worst_month['n']})")

        if len(monthly) <= 3:
            print("\n  >>> CONCERN: Only {len(monthly)} months of data — too few for confidence.")

    # ═══════════════════════════════════════════════════════════════════
    # TEST 5: Stress tests
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("TEST 5: STRESS TESTS")
    print("=" * 80)

    # 5a: Different bandwidths
    print("\n--- 5a: Bandwidth sensitivity ---")
    bw_results = {}
    for bw in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
        picks = run_model(df, FEATURES_7, bandwidth=bw, top_k=5,
                           min_train_days=20, exclude_sectors=EXCLUDE_SECTORS,
                           min_er=1.0, label=f'BW={bw}')
        if len(picks) > 0:
            wr = 100 * (picks['outcome_5d'] > 0).mean()
            ar = picks['outcome_5d'].mean()
            n = len(picks)
            bw_results[bw] = (n, wr, ar)
            print(f"  bw={bw:.2f}: n={n:>4}, WR={wr:.1f}%, AvgRet={ar:+.2f}%")
        else:
            print(f"  bw={bw:.2f}: NO PICKS")

    # 5b: Min training days = 30
    print("\n--- 5b: Min training days = 30 ---")
    picks_5b = run_model(df, FEATURES_7, bandwidth=1.0, top_k=5,
                          min_train_days=30, exclude_sectors=EXCLUDE_SECTORS,
                          min_er=1.0, label='MinDays=30')
    m5b = report_metrics(picks_5b, "5b: min_train_days=30")

    # 5c: Top 3 instead of top 5
    print("\n--- 5c: Top 3 instead of top 5 ---")
    picks_5c = run_model(df, FEATURES_7, bandwidth=1.0, top_k=3,
                          min_train_days=20, exclude_sectors=EXCLUDE_SECTORS,
                          min_er=1.0, label='Top3')
    m5c = report_metrics(picks_5c, "5c: Top 3 picks")

    # 5d: E[R] >= 0.5 instead of >= 1.0
    print("\n--- 5d: E[R] >= 0.5 ---")
    picks_5d = run_model(df, FEATURES_7, bandwidth=1.0, top_k=5,
                          min_train_days=20, exclude_sectors=EXCLUDE_SECTORS,
                          min_er=0.5, label='ER>=0.5')
    m5d = report_metrics(picks_5d, "5d: E[R] >= 0.5")

    # Stress test summary
    print(f"\n{'─' * 70}")
    print(f"  STRESS TEST SUMMARY")
    print(f"{'─' * 70}")
    stress_configs = [
        ('Original (bw=1.0, top5, ER>=1.0)', m1),
        ('5b: min_train=30', m5b),
        ('5c: top 3', m5c),
        ('5d: E[R]>=0.5', m5d),
    ]
    print(f"  {'Config':<40} {'N':>5} {'WR':>7} {'AvgRet':>8}")
    for name, m in stress_configs:
        if m:
            print(f"  {name:<40} {m['n']:>5} {m['wr']:>6.1f}% {m['avg_ret']:>+7.2f}%")
        else:
            print(f"  {name:<40}  --- no picks ---")

    # ═══════════════════════════════════════════════════════════════════
    # TEST 6: Data coverage check
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("TEST 6: DATA COVERAGE CHECK")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)

    # 6a: backfill coverage
    bso_raw = pd.read_sql_query("""
        SELECT b.symbol, b.scan_date,
               a.upside_pct, f.beta
        FROM backfill_signal_outcomes b
        LEFT JOIN analyst_consensus a ON b.symbol = a.symbol
        LEFT JOIN stock_fundamentals f ON b.symbol = f.symbol
        WHERE b.outcome_5d IS NOT NULL
    """, conn)

    print(f"\n  6a: backfill_signal_outcomes coverage:")
    print(f"    Total rows:       {len(bso_raw):,}")
    print(f"    Has upside_pct:   {bso_raw['upside_pct'].notna().sum():,} "
          f"({100*bso_raw['upside_pct'].notna().mean():.1f}%)")
    print(f"    Has beta:         {bso_raw['beta'].notna().sum():,} "
          f"({100*bso_raw['beta'].notna().mean():.1f}%)")
    has_both_bso = (bso_raw['upside_pct'].notna() & bso_raw['beta'].notna()).sum()
    print(f"    Has BOTH:         {has_both_bso:,} "
          f"({100*has_both_bso/len(bso_raw):.1f}%)")

    # 6b: live coverage
    so_raw = pd.read_sql_query("""
        SELECT s.symbol, s.scan_date,
               a.upside_pct, f.beta
        FROM signal_outcomes s
        LEFT JOIN analyst_consensus a ON s.symbol = a.symbol
        LEFT JOIN stock_fundamentals f ON s.symbol = f.symbol
        WHERE s.outcome_5d IS NOT NULL
          AND s.signal_source = 'dip_bounce'
    """, conn)

    print(f"\n  6b: signal_outcomes (live) coverage:")
    print(f"    Total rows:       {len(so_raw):,}")
    print(f"    Has upside_pct:   {so_raw['upside_pct'].notna().sum():,} "
          f"({100*so_raw['upside_pct'].notna().mean():.1f}%)")
    print(f"    Has beta:         {so_raw['beta'].notna().sum():,} "
          f"({100*so_raw['beta'].notna().mean():.1f}%)")
    has_both_so = (so_raw['upside_pct'].notna() & so_raw['beta'].notna()).sum()
    print(f"    Has BOTH:         {has_both_so:,} "
          f"({100*has_both_so/len(so_raw):.1f}%)")

    conn.close()

    # 6c: Dates with no candidates after all filters
    if len(picks_1) > 0:
        # Get all dates that had data but no picks
        all_dates_with_data = df.dropna(subset=FEATURES_7 + ['outcome_5d'])
        all_dates_with_data = all_dates_with_data[
            ~all_dates_with_data['sector'].isin(EXCLUDE_SECTORS)
        ]
        all_data_dates = set(all_dates_with_data['scan_date'].unique())
        pick_dates = set(picks_1['scan_date'].unique())
        no_pick_dates = all_data_dates - pick_dates

        # Also count dates where we had data but not enough training
        all_sorted = sorted(all_data_dates)
        too_early = sum(1 for d in all_sorted
                       if df[df['scan_date'] < d]['scan_date'].nunique() < 20)

        print(f"\n  6c: Date coverage:")
        print(f"    Total dates with eligible data: {len(all_data_dates)}")
        print(f"    Dates with picks:               {len(pick_dates)}")
        print(f"    Dates with NO picks:            {len(no_pick_dates)}")
        print(f"    Dates skipped (< 20 train days): ~{too_early}")

    # ═══════════════════════════════════════════════════════════════════
    # FINAL VERDICT
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FINAL VERDICT & CONCERNS")
    print("=" * 80)

    if m1:
        print(f"\n  Reproduced metrics: WR={m1['wr']:.1f}%, AvgRet={m1['avg_ret']:+.2f}%")
        print(f"  Claimed metrics:    WR=~59-60%, AvgRet=~+1.2%")

        # Check claim
        wr_delta = abs(m1['wr'] - 59.5)
        ar_delta = abs(m1['avg_ret'] - 1.2)

        if wr_delta <= 3.0 and ar_delta <= 0.4:
            print(f"\n  VERDICT: Claims are APPROXIMATELY REPRODUCED (within tolerance)")
        elif wr_delta <= 5.0 or ar_delta <= 0.6:
            print(f"\n  VERDICT: Claims are PARTIALLY REPRODUCED (some deviation)")
        else:
            print(f"\n  VERDICT: Claims CANNOT BE REPRODUCED")

    # Concerns
    print(f"\n  CONCERNS:")
    concerns = []

    if m1 and m1['n'] < 100:
        concerns.append(f"  - SMALL SAMPLE: Only {m1['n']} picks — high variance in metrics")
    if m1 and m1['days'] < 30:
        concerns.append(f"  - SHORT HISTORY: Only {m1['days']} active days")

    # Check data coverage concern
    if len(df) > 0:
        both_pct = 100 * df.dropna(subset=['upside_pct', 'beta']).shape[0] / len(df)
        if both_pct < 50:
            concerns.append(f"  - DATA COVERAGE: Only {both_pct:.0f}% of rows have both upside_pct+beta")

    # Check if enrichment actually helps
    if m1 and m2:
        if m1['wr'] - m2['wr'] < 2.0 and m1['avg_ret'] - m2['avg_ret'] < 0.2:
            concerns.append(f"  - MARGINAL ENRICHMENT: 7-feature model only slightly better than 5-feature baseline")

    # Check bandwidth sensitivity
    if bw_results:
        wrs = [v[1] for v in bw_results.values()]
        ars = [v[2] for v in bw_results.values()]
        if max(wrs) - min(wrs) > 10:
            concerns.append(f"  - BW SENSITIVITY: WR varies {min(wrs):.0f}-{max(wrs):.0f}% across bandwidths (fragile)")

    # Check if sector exclusion is doing heavy lifting
    if m1 and m3c:
        if abs(m1['wr'] - m3c['wr']) > 5:
            concerns.append(f"  - SECTOR EXCLUSION dominant: {abs(m1['wr'] - m3c['wr']):.1f}pp WR difference")

    # Check monthly consistency
    if len(picks_1) > 0:
        monthly_wrs = picks_1.groupby(picks_1['scan_date'].dt.to_period('M'))['outcome_5d'].apply(
            lambda x: 100 * (x > 0).mean()
        )
        if monthly_wrs.std() > 15:
            concerns.append(f"  - INCONSISTENT: Monthly WR varies widely (std={monthly_wrs.std():.1f}pp)")

    # Overfitting check
    if m1 and m2:
        train_size = len(df.dropna(subset=FEATURES_7 + ['outcome_5d']))
        n_features = len(FEATURES_7)
        if train_size / n_features < 50:
            concerns.append(f"  - OVERFITTING RISK: {train_size} samples / {n_features} features = "
                          f"{train_size/n_features:.0f} ratio (want > 50)")

    # Survivorship bias in analyst/fundamentals data
    concerns.append(f"  - LOOK-AHEAD BIAS RISK: analyst_consensus and stock_fundamentals have no "
                   f"date versioning — current values are joined to historical signals")

    if not concerns:
        print("  None identified.")
    else:
        for c in concerns:
            print(c)

    print("\n" + "=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
