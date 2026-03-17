#!/usr/bin/env python3
"""
Backtest: Discovery v3 Self-Calibrating E[R] Model vs Current v2 Score System

v3.1: Uses COMBINED dataset (live signal_outcomes + backfill_signal_outcomes)
      with proper expanding-window CV (train only on data BEFORE test date).

Methods:
  1. Bucket-based hierarchical Bayesian E[R] with shrinkage
  2. Kernel regression (Gaussian weighting, no discrete buckets)
  3. Derived features: dist_x_rsi, mean_reversion_score, atr_risk

Reports: WR, TP hit rates, avg return, picks/day, expectancy
"""
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime as dt
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────
COST = 0.003          # 0.3% slippage + commission
PRIOR_K = 20          # Shrinkage strength
MAX_PICKS_PER_DAY = 10

# Feature bucket definitions
BUCKETS = {
    'distance_from_20d_high': [('above', 0, 999), ('near', -3, 0), ('mid', -6, -3), ('far', -10, -6), ('deep', -999, -10)],
    'vix_at_signal': [('low', 0, 18), ('normal', 18, 20), ('elevated', 20, 22), ('high', 22, 25), ('extreme', 25, 99)],
    'atr_pct': [('tight', 0, 2.5), ('low', 2.5, 3.5), ('mid', 3.5, 4.5), ('high', 4.5, 99)],
    'momentum_5d': [('deep_dip', -99, -5), ('pullback', -5, -1), ('flat', -1, 2), ('momentum', 2, 99)],
    'entry_rsi': [('oversold', 0, 40), ('low', 40, 50), ('mid', 50, 58), ('high', 58, 99)],
}
SECTOR_FEATURE = 'sector'
FEATURES = list(BUCKETS.keys()) + [SECTOR_FEATURE]

# Kernel regression features (continuous, no buckets)
KERNEL_FEATURES = ['distance_from_20d_high', 'atr_pct', 'entry_rsi', 'momentum_5d', 'vix_at_signal']
# Derived features
DERIVED_FEATURES = ['dist_x_rsi', 'mean_reversion_score', 'atr_risk']
ALL_KERNEL_FEATURES = KERNEL_FEATURES + DERIVED_FEATURES

# Kernel bandwidth (validated: bw=1.0 was best in prior analysis)
KERNEL_BW = 1.0


# ──────────────────────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────────────────────
def load_data():
    """Load combined dataset: live signal_outcomes + backfill_signal_outcomes."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Live signal_outcomes (has new_score for v2 comparison)
    live_rows = conn.execute("""
        SELECT scan_date, symbol, action_taken, scan_price,
               outcome_5d, outcome_max_gain_5d, outcome_max_dd_5d,
               distance_from_20d_high, vix_at_signal, atr_pct,
               momentum_5d, entry_rsi, volume_ratio, sector,
               new_score
        FROM signal_outcomes
        WHERE outcome_5d IS NOT NULL
          AND distance_from_20d_high IS NOT NULL
          AND vix_at_signal IS NOT NULL
          AND atr_pct IS NOT NULL
          AND momentum_5d IS NOT NULL
          AND entry_rsi IS NOT NULL
    """).fetchall()

    # Backfill synthetic outcomes
    backfill_rows = conn.execute("""
        SELECT scan_date, symbol, sector, scan_price,
               atr_pct, entry_rsi, distance_from_20d_high,
               momentum_5d, momentum_20d, volume_ratio,
               vix_at_signal, outcome_5d,
               outcome_max_gain_5d, outcome_max_dd_5d
        FROM backfill_signal_outcomes
        WHERE outcome_5d IS NOT NULL
    """).fetchall()
    conn.close()

    live_data = []
    for r in live_rows:
        d = dict(r)
        d['source'] = 'live'
        _add_derived_features(d)
        live_data.append(d)

    backfill_data = []
    for r in backfill_rows:
        d = dict(r)
        d['source'] = 'backfill'
        d['new_score'] = None  # backfill has no v2 score
        d['action_taken'] = None
        _add_derived_features(d)
        backfill_data.append(d)

    combined = backfill_data + live_data

    # Deduplicate: if same (scan_date, symbol) in both, keep live
    seen = {}
    for row in combined:
        key = (row['scan_date'], row['symbol'])
        if key in seen:
            if row['source'] == 'live':
                seen[key] = row
        else:
            seen[key] = row
    combined = sorted(seen.values(), key=lambda r: r['scan_date'])

    live_count = sum(1 for r in combined if r['source'] == 'live')
    bf_count = sum(1 for r in combined if r['source'] == 'backfill')

    dates = sorted(set(r['scan_date'] for r in combined))
    print(f"Combined dataset: {len(combined)} rows ({live_count} live + {bf_count} backfill)")
    print(f"Date range: {dates[0]} to {dates[-1]} ({len(dates)} unique dates)")

    return combined


def _add_derived_features(row):
    """Compute derived interaction features."""
    dist = row.get('distance_from_20d_high')
    rsi = row.get('entry_rsi')
    atr = row.get('atr_pct')
    vix = row.get('vix_at_signal')
    mom5d = row.get('momentum_5d')

    # dist_x_rsi: strongest single predictor (IC=0.289 in prior analysis)
    if dist is not None and rsi is not None:
        row['dist_x_rsi'] = dist * rsi  # large negative × high RSI = bad
    else:
        row['dist_x_rsi'] = None

    # mean_reversion_score: (RSI-50) × distance (IC=0.211)
    if rsi is not None and dist is not None:
        row['mean_reversion_score'] = (rsi - 50) * dist
    else:
        row['mean_reversion_score'] = None

    # atr_risk: ATR × VIX/20 (IC=-0.167)
    if atr is not None and vix is not None:
        row['atr_risk'] = atr * (vix / 20.0)
    else:
        row['atr_risk'] = None


def discretize(row, feature):
    """Map a raw feature value to its bucket label."""
    if feature == SECTOR_FEATURE:
        return row.get('sector', 'Unknown') or 'Unknown'
    val = row.get(feature)
    if val is None:
        return None
    for label, lo, hi in BUCKETS[feature]:
        if lo <= val < hi:
            return label
    return BUCKETS[feature][-1][0]


# ──────────────────────────────────────────────────────────────
# Hierarchical Bayesian Estimator (Bucket-based)
# ──────────────────────────────────────────────────────────────
class HierarchicalEstimator:
    def __init__(self, k=PRIOR_K):
        self.k = k
        self.global_mean = 0.0
        self.global_var = 1.0
        self.marginals = {}

    def fit(self, train_data):
        returns = [r['outcome_5d'] for r in train_data]
        if not returns:
            return
        self.global_mean = np.mean(returns)
        self.global_var = np.var(returns) if len(returns) > 1 else 1.0
        self.marginals = {}

        for feature in FEATURES:
            buckets = defaultdict(list)
            for row in train_data:
                bucket = discretize(row, feature)
                if bucket is not None:
                    buckets[bucket].append(row['outcome_5d'])

            for bucket, rets in buckets.items():
                n = len(rets)
                if n < 3:
                    continue
                x_bar = np.mean(rets)
                s2 = np.var(rets, ddof=1) if n > 1 else self.global_var
                w = n / (n + self.k)
                shrunk_mean = w * x_bar + (1 - w) * self.global_mean
                se = math.sqrt(w * (s2 / n) + (1 - w) * self.global_var / max(self.k, 1))
                self.marginals[(feature, bucket)] = {
                    'mean': shrunk_mean, 'se': se, 'n': n, 'weight': w, 'raw_mean': x_bar,
                }

    def estimate(self, row):
        estimates = []
        details = {}
        for feature in FEATURES:
            bucket = discretize(row, feature)
            if bucket is None:
                continue
            key = (feature, bucket)
            if key not in self.marginals:
                continue
            m = self.marginals[key]
            if m['se'] <= 0:
                continue
            precision = 1.0 / (m['se'] ** 2)
            estimates.append((m['mean'], precision, m['n'], feature, bucket))
            details[feature] = {
                'bucket': bucket, 'er': round(m['mean'], 3),
                'n': m['n'], 'w': round(m['weight'], 2),
            }
        if not estimates:
            return self.global_mean, math.sqrt(self.global_var), details
        total_precision = sum(p for _, p, _, _, _ in estimates)
        combined_mean = sum(m * p for m, p, _, _, _ in estimates) / total_precision
        combined_se = 1.0 / math.sqrt(total_precision)
        return combined_mean, combined_se, details


# ──────────────────────────────────────────────────────────────
# Kernel Regression Estimator (Gaussian weighting, continuous)
# ──────────────────────────────────────────────────────────────
class KernelEstimator:
    """Kernel regression using Gaussian distance weighting.
    No discrete buckets — uses continuous distance in normalized feature space."""

    def __init__(self, bandwidth=KERNEL_BW, features=None):
        self.bw = bandwidth
        self.features = features or ALL_KERNEL_FEATURES
        self.train_data = []
        self.train_returns = np.array([])
        self.train_features = np.array([])
        self.feature_means = np.zeros(len(self.features))
        self.feature_stds = np.ones(len(self.features))

    def fit(self, train_data):
        self.train_data = train_data
        if not train_data:
            return

        # Extract feature matrix
        rows = []
        returns = []
        for r in train_data:
            vals = [r.get(f) for f in self.features]
            if any(v is None for v in vals):
                continue
            rows.append(vals)
            returns.append(r['outcome_5d'])

        if len(rows) < 10:
            self.train_features = np.array([])
            return

        self.train_features = np.array(rows, dtype=float)
        self.train_returns = np.array(returns, dtype=float)

        # Normalize features (z-score)
        self.feature_means = self.train_features.mean(axis=0)
        self.feature_stds = self.train_features.std(axis=0)
        self.feature_stds[self.feature_stds == 0] = 1.0  # avoid div/0
        self.train_features = (self.train_features - self.feature_means) / self.feature_stds

    def estimate(self, row):
        """Return (E[R], SE, n_effective)."""
        if len(self.train_features) == 0:
            return 0.0, 10.0, 0

        vals = [row.get(f) for f in self.features]
        if any(v is None for v in vals):
            return 0.0, 10.0, 0

        x = (np.array(vals, dtype=float) - self.feature_means) / self.feature_stds

        # Gaussian kernel weights
        dists = np.sqrt(np.sum((self.train_features - x) ** 2, axis=1))
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)

        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 10.0, 0

        # Weighted mean (E[R])
        er = np.sum(weights * self.train_returns) / total_w

        # Effective sample size
        n_eff = total_w ** 2 / np.sum(weights ** 2)

        # Weighted SE
        if n_eff > 1:
            residuals = self.train_returns - er
            weighted_var = np.sum(weights * residuals ** 2) / total_w
            se = math.sqrt(weighted_var / n_eff)
        else:
            se = 10.0

        return float(er), float(se), float(n_eff)


# ──────────────────────────────────────────────────────────────
# Backtest: Expanding Window Cross Validation
# ──────────────────────────────────────────────────────────────
def run_backtest(data, v3_mode='rank_top_n', v3_top_n=10, er_floor=None,
                 method='bucket', kernel_bw=KERNEL_BW, min_train_days=20,
                 sector_cap_pct=None, breadth_gate=False,
                 max_atr_pct=None, min_volume_ratio=None,
                 exclude_sectors=None):
    """
    Expanding window CV: train on ALL data strictly before test_date.

    method: 'bucket' (hierarchical Bayesian) or 'kernel' (Gaussian regression)
            or 'hybrid' (v2 score gate + v3 ranking)
    sector_cap_pct: if set, cap picks from any single sector to this % of total
    max_atr_pct: pre-filter ATR gate (SL reduction)
    min_volume_ratio: pre-filter volume gate
    exclude_sectors: set of sectors to exclude
    """
    # Apply pre-filters
    filtered = data
    if max_atr_pct is not None:
        filtered = [r for r in filtered if (r.get('atr_pct') or 0) <= max_atr_pct]
    if min_volume_ratio is not None:
        filtered = [r for r in filtered if (r.get('volume_ratio') or 0) >= min_volume_ratio]
    if exclude_sectors:
        filtered = [r for r in filtered if (r.get('sector') or '') not in exclude_sectors]

    dates = sorted(set(r['scan_date'] for r in filtered))
    if not dates:
        print("No data after filtering")
        return [], [], []
    print(f"\nDates: {len(dates)} ({dates[0]} to {dates[-1]})")
    print(f"Total signals: {len(filtered)} (from {len(data)})")
    print(f"Method: {method}, v3 mode: {v3_mode}" +
          (f" (top_n={v3_top_n})" if v3_mode == 'rank_top_n' else ''))
    if max_atr_pct:
        print(f"ATR gate: ≤ {max_atr_pct}%")
    if min_volume_ratio:
        print(f"Volume gate: ≥ {min_volume_ratio}")
    if exclude_sectors:
        print(f"Excluded sectors: {exclude_sectors}")
    if sector_cap_pct:
        print(f"Sector cap: {sector_cap_pct:.0f}%")

    v3_results = []
    v2_results = []
    skipped_dates = 0

    for i, test_date in enumerate(dates):
        # Expanding window: train on ALL data strictly BEFORE test_date
        train = [r for r in filtered if r['scan_date'] < test_date]
        test = [r for r in filtered if r['scan_date'] == test_date]

        if not test:
            continue

        # Skip if insufficient training data
        train_dates = set(r['scan_date'] for r in train)
        if len(train_dates) < min_train_days:
            skipped_dates += 1
            continue

        # ── v3: Fit estimator on train, predict on test ──
        if method == 'kernel' or method == 'hybrid':
            estimator = KernelEstimator(bandwidth=kernel_bw)
        else:
            estimator = HierarchicalEstimator(k=PRIOR_K)
        estimator.fit(train)

        candidates = []
        for row in test:
            if method == 'kernel' or method == 'hybrid':
                er, se, n_eff = estimator.estimate(row)
                details = {'n_eff': round(n_eff, 1)}
            else:
                er, se, details = estimator.estimate(row)

            candidates.append({
                'row': row, 'er': er, 'se': se, 'details': details,
            })

        # Hybrid: apply v2 score gate first, then rank by v3
        if method == 'hybrid':
            candidates = [c for c in candidates
                          if (c['row'].get('new_score') or 0) >= 70
                          or c['row']['source'] == 'backfill']  # backfill has no score

        # v3 pick selection based on mode
        if v3_mode == 'conservative':
            v3_picks = [c for c in candidates if c['er'] - se > COST]
        elif v3_mode == 'er_positive':
            v3_picks = [c for c in candidates if c['er'] > 0]
        elif v3_mode == 'er_floor':
            floor = er_floor or 0.5
            v3_picks = [c for c in candidates if c['er'] > floor]
        else:  # rank_top_n
            v3_picks = list(candidates)

        v3_picks.sort(key=lambda c: c['er'], reverse=True)
        max_picks = v3_top_n if v3_mode == 'rank_top_n' else MAX_PICKS_PER_DAY

        # Apply sector cap if requested
        if sector_cap_pct and v3_picks:
            v3_picks = _apply_sector_cap(v3_picks, max_picks, sector_cap_pct)
        v3_picks = v3_picks[:max_picks]

        for c in v3_picks:
            r = c['row']
            v3_results.append({
                'date': test_date, 'symbol': r['symbol'],
                'er': c['er'], 'se': c['se'],
                'outcome_5d': r['outcome_5d'],
                'max_gain': r.get('outcome_max_gain_5d'),
                'max_dd': r.get('outcome_max_dd_5d'),
                'sector': r.get('sector', ''),
                'source': r.get('source', 'unknown'),
                'details': c['details'],
            })

        # ── v2: Score-based (only for rows with new_score) ──
        v2_picks = [r for r in test if (r.get('new_score') or 0) >= 70]
        v2_picks.sort(key=lambda r: r.get('new_score', 0) or 0, reverse=True)
        v2_picks = v2_picks[:MAX_PICKS_PER_DAY]

        for r in v2_picks:
            v2_results.append({
                'date': test_date, 'symbol': r['symbol'],
                'score': r.get('new_score', 0),
                'outcome_5d': r['outcome_5d'],
                'max_gain': r.get('outcome_max_gain_5d'),
                'max_dd': r.get('outcome_max_dd_5d'),
                'sector': r.get('sector', ''),
                'source': r.get('source', 'unknown'),
            })

    print(f"Skipped {skipped_dates} dates (< {min_train_days} train days)")
    return v3_results, v2_results, dates


def _apply_sector_cap(picks, max_n, cap_pct):
    """Cap picks from any single sector to cap_pct of max_n."""
    max_per_sector = max(1, int(max_n * cap_pct / 100))
    sector_counts = defaultdict(int)
    result = []
    for p in picks:
        sector = p['row'].get('sector', 'Unknown') or 'Unknown'
        if sector_counts[sector] < max_per_sector:
            result.append(p)
            sector_counts[sector] += 1
    return result


# ──────────────────────────────────────────────────────────────
# Reporting
# ──────────────────────────────────────────────────────────────
def compute_metrics(results, label, show_detail=True):
    if not results:
        print(f"\n{'='*60}")
        print(f"  {label}: NO PICKS")
        print(f"{'='*60}")
        return {}

    n = len(results)
    dates_active = len(set(r['date'] for r in results))
    outcomes = [r['outcome_5d'] for r in results]
    max_gains = [r['max_gain'] for r in results if r['max_gain'] is not None]
    max_dds = [r['max_dd'] for r in results if r['max_dd'] is not None]

    wins = sum(1 for o in outcomes if o > 0)
    wr = wins / n * 100 if n > 0 else 0
    avg_ret = np.mean(outcomes)
    median_ret = np.median(outcomes)

    # TP hit rates
    tp_2 = sum(1 for g in max_gains if g >= 2.0) / len(max_gains) * 100 if max_gains else 0
    tp_3 = sum(1 for g in max_gains if g >= 3.0) / len(max_gains) * 100 if max_gains else 0

    # SL hit rates
    sl_2 = sum(1 for d in max_dds if d <= -2.0) / len(max_dds) * 100 if max_dds else 0
    sl_3 = sum(1 for d in max_dds if d <= -3.0) / len(max_dds) * 100 if max_dds else 0

    # Expectancy with TP3/SL3
    expectancy_3_3 = []
    for r in results:
        mg, md = r.get('max_gain'), r.get('max_dd')
        if mg is None or md is None:
            continue
        if md <= -3.0:
            expectancy_3_3.append(-3.0)
        elif mg >= 3.0:
            expectancy_3_3.append(3.0)
        else:
            expectancy_3_3.append(r['outcome_5d'])
    exp_3_3 = np.mean(expectancy_3_3) if expectancy_3_3 else 0

    picks_per_day = n / dates_active if dates_active > 0 else 0

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Total picks:       {n}")
    print(f"  Active days:       {dates_active}")
    print(f"  Picks/day:         {picks_per_day:.1f}")
    print(f"  Win Rate:          {wr:.1f}%  ({wins}/{n})")
    print(f"  Avg Return 5d:     {avg_ret:+.2f}%")
    print(f"  Median Return 5d:  {median_ret:+.2f}%")
    print(f"  TP ≥ 2.0%:         {tp_2:.1f}%")
    print(f"  TP ≥ 3.0%:         {tp_3:.1f}%")
    print(f"  SL ≤ -2.0%:        {sl_2:.1f}%")
    print(f"  SL ≤ -3.0%:        {sl_3:.1f}%")
    print(f"  Expectancy TP3/SL3:{exp_3_3:+.3f}%")

    if show_detail:
        # Monthly breakdown
        month_stats = defaultdict(lambda: {'n': 0, 'wins': 0, 'total': 0})
        for r in results:
            m = r['date'][:7]
            month_stats[m]['n'] += 1
            if r['outcome_5d'] > 0:
                month_stats[m]['wins'] += 1
            month_stats[m]['total'] += r['outcome_5d']

        print(f"\n  Monthly Breakdown:")
        print(f"    {'Month':<10} {'n':>5} {'WR%':>6} {'AvgRet':>8}")
        for m in sorted(month_stats.keys()):
            ms = month_stats[m]
            m_wr = ms['wins'] / ms['n'] * 100 if ms['n'] > 0 else 0
            m_avg = ms['total'] / ms['n'] if ms['n'] > 0 else 0
            print(f"    {m:<10} {ms['n']:>5} {m_wr:>5.1f}% {m_avg:>+7.2f}%")

        # Top sectors
        sector_stats = defaultdict(lambda: {'n': 0, 'wins': 0, 'total': 0})
        for r in results:
            s = r.get('sector', 'Unknown') or 'Unknown'
            sector_stats[s]['n'] += 1
            if r['outcome_5d'] > 0:
                sector_stats[s]['wins'] += 1
            sector_stats[s]['total'] += r['outcome_5d']

        print(f"\n  Sector Breakdown (top 10):")
        print(f"    {'Sector':<25} {'n':>4} {'WR%':>6} {'AvgRet':>8} {'Share':>6}")
        for s in sorted(sector_stats, key=lambda x: sector_stats[x]['n'], reverse=True)[:10]:
            ss = sector_stats[s]
            s_wr = ss['wins'] / ss['n'] * 100 if ss['n'] > 0 else 0
            s_avg = ss['total'] / ss['n'] if ss['n'] > 0 else 0
            s_share = ss['n'] / n * 100
            print(f"    {s:<25} {ss['n']:>4} {s_wr:>5.1f}% {s_avg:>+7.2f}% {s_share:>5.1f}%")

    return {
        'n': n, 'dates': dates_active, 'picks_per_day': picks_per_day,
        'wr': wr, 'avg_ret': avg_ret, 'median_ret': median_ret,
        'tp_2': tp_2, 'tp_3': tp_3, 'sl_2': sl_2, 'sl_3': sl_3,
        'exp_3_3': exp_3_3,
    }


def show_comparison(m_v3, m_v2, label=''):
    if not m_v3 or not m_v2:
        return
    print(f"\n{'='*60}")
    print(f"  HEAD-TO-HEAD{' — ' + label if label else ''}")
    print(f"{'='*60}")
    print(f"  {'Metric':<25} {'v2':>12} {'v3':>12} {'Delta':>10}")
    print(f"  {'-'*60}")

    metrics = [
        ('Total Picks', 'n', 'd'),
        ('Picks/Day', 'picks_per_day', '.1f'),
        ('Win Rate %', 'wr', '.1f'),
        ('Avg Return 5d %', 'avg_ret', '+.2f'),
        ('Median Return 5d %', 'median_ret', '+.2f'),
        ('TP ≥ 2.0%', 'tp_2', '.1f'),
        ('TP ≥ 3.0%', 'tp_3', '.1f'),
        ('SL ≤ -2.0%', 'sl_2', '.1f'),
        ('SL ≤ -3.0%', 'sl_3', '.1f'),
        ('Expectancy TP3/SL3 %', 'exp_3_3', '+.3f'),
    ]

    for name, key, fmt in metrics:
        v2_val = m_v2.get(key, 0)
        v3_val = m_v3.get(key, 0)
        delta = v3_val - v2_val
        if fmt == 'd':
            print(f"  {name:<25} {v2_val:>12d} {v3_val:>12d} {delta:>+10d}")
        else:
            clean_fmt = fmt.replace('+', '')
            v2_str = f"{v2_val:{clean_fmt}}"
            v3_str = f"{v3_val:{clean_fmt}}"
            d_str = f"{delta:+{clean_fmt}}"
            print(f"  {name:<25} {v2_str:>12} {v3_str:>12} {d_str:>10}")


# ──────────────────────────────────────────────────────────────
# Feature Importance via Kernel
# ──────────────────────────────────────────────────────────────
def analyze_feature_importance(data):
    """Test each feature individually as a kernel predictor."""
    print(f"\n{'='*60}")
    print(f"  FEATURE IMPORTANCE (single-feature kernel, expanding CV)")
    print(f"{'='*60}")

    dates = sorted(set(r['scan_date'] for r in data))
    # Use dates from the middle third for testing
    test_start_idx = len(dates) // 3
    test_dates = dates[test_start_idx:]

    results = {}
    features_to_test = KERNEL_FEATURES + DERIVED_FEATURES

    for feat in features_to_test:
        picks = []
        for test_date in test_dates:
            train = [r for r in data if r['scan_date'] < test_date and r.get(feat) is not None]
            test = [r for r in data if r['scan_date'] == test_date and r.get(feat) is not None]
            if len(train) < 50 or not test:
                continue

            # Simple 1D kernel
            train_x = np.array([r[feat] for r in train], dtype=float)
            train_y = np.array([r['outcome_5d'] for r in train], dtype=float)
            mu, sigma = train_x.mean(), train_x.std()
            if sigma == 0:
                continue
            train_x_norm = (train_x - mu) / sigma

            for row in test:
                x = (row[feat] - mu) / sigma
                dists = np.abs(train_x_norm - x)
                weights = np.exp(-0.5 * (dists / 1.0) ** 2)
                total_w = weights.sum()
                if total_w < 1e-10:
                    continue
                er = np.sum(weights * train_y) / total_w
                picks.append((er, row['outcome_5d']))

        if len(picks) < 50:
            continue

        # Pick top 30% by E[R] each day
        picks.sort(key=lambda x: x[0], reverse=True)
        top_n = max(1, len(picks) // 3)
        top_picks = picks[:top_n]
        bottom_picks = picks[-top_n:]

        top_wr = sum(1 for _, o in top_picks if o > 0) / len(top_picks) * 100
        top_avg = np.mean([o for _, o in top_picks])
        bot_wr = sum(1 for _, o in bottom_picks if o > 0) / len(bottom_picks) * 100
        bot_avg = np.mean([o for _, o in bottom_picks])
        spread = top_avg - bot_avg

        results[feat] = {
            'n': len(picks), 'top_wr': top_wr, 'top_avg': top_avg,
            'bot_wr': bot_wr, 'bot_avg': bot_avg, 'spread': spread,
        }

    print(f"  {'Feature':<25} {'n':>5} {'TopWR':>6} {'TopAvg':>8} {'BotWR':>6} {'BotAvg':>8} {'Spread':>8}")
    print(f"  {'-'*70}")
    for f in sorted(results, key=lambda x: results[x]['spread'], reverse=True):
        r = results[f]
        print(f"  {f:<25} {r['n']:>5} {r['top_wr']:>5.1f}% {r['top_avg']:>+7.2f}% "
              f"{r['bot_wr']:>5.1f}% {r['bot_avg']:>+7.2f}% {r['spread']:>+7.2f}%")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 70)
    print("  DISCOVERY v3 BACKTEST (v3.1 — Combined Dataset + Expanding Window)")
    print("=" * 70)

    data = load_data()

    # ════════════════════════════════════════════════════════════
    # TEST 1: Bucket-based E[R] — Ranking Top 5
    # ════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  TEST 1: BUCKET-BASED E[R] — Top 5 per day")
    print("=" * 70)
    v3_r, v2_r, dates = run_backtest(data, v3_mode='rank_top_n', v3_top_n=5,
                                      method='bucket')
    m_bucket5 = compute_metrics(v3_r, "v3 Bucket: Top 5 by E[R]")
    m_v2 = compute_metrics(v2_r, "v2: score≥70 (live dates only)")
    show_comparison(m_bucket5, m_v2, "Bucket Top5 vs v2")

    # ════════════════════════════════════════════════════════════
    # TEST 2: Kernel Regression — Ranking Top 5
    # ════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  TEST 2: KERNEL REGRESSION — Top 5 per day")
    print("=" * 70)
    v3_kr, _, _ = run_backtest(data, v3_mode='rank_top_n', v3_top_n=5,
                                method='kernel')
    m_kernel5 = compute_metrics(v3_kr, "v3 Kernel: Top 5 by E[R]")
    show_comparison(m_kernel5, m_v2, "Kernel Top5 vs v2")

    # ════════════════════════════════════════════════════════════
    # TEST 3: Kernel + Sector Cap 30%
    # ════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  TEST 3: KERNEL + SECTOR CAP 30%")
    print("=" * 70)
    v3_krc, _, _ = run_backtest(data, v3_mode='rank_top_n', v3_top_n=5,
                                 method='kernel', sector_cap_pct=30)
    m_kernel5_cap = compute_metrics(v3_krc, "v3 Kernel Top5 + Sector Cap 30%")
    show_comparison(m_kernel5_cap, m_v2, "Kernel+SectorCap vs v2")

    # ════════════════════════════════════════════════════════════
    # TEST 4: Kernel E[R] > 0 filter
    # ════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  TEST 4: KERNEL E[R] > 0 FILTER")
    print("=" * 70)
    v3_kp, _, _ = run_backtest(data, v3_mode='er_positive', method='kernel')
    m_kernel_pos = compute_metrics(v3_kp, "v3 Kernel: E[R] > 0 only")
    show_comparison(m_kernel_pos, m_v2, "Kernel E[R]>0 vs v2")

    # ════════════════════════════════════════════════════════════
    # TEST 5: Kernel E[R] > 0.5% floor
    # ════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  TEST 5: KERNEL E[R] > 0.5% FLOOR")
    print("=" * 70)
    v3_k05, _, _ = run_backtest(data, v3_mode='er_floor', er_floor=0.5,
                                 method='kernel')
    m_kernel_05 = compute_metrics(v3_k05, "v3 Kernel: E[R] > 0.5%")
    if m_kernel_05:
        show_comparison(m_kernel_05, m_v2, "Kernel E[R]>0.5% vs v2")

    # ════════════════════════════════════════════════════════════
    # TEST 6: Bandwidth sensitivity
    # ════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print(f"  BANDWIDTH SENSITIVITY (Kernel, Top 5)")
    print(f"{'='*70}")
    bw_results = []
    for bw in [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]:
        v3_bw, _, _ = run_backtest(data, v3_mode='rank_top_n', v3_top_n=5,
                                    method='kernel', kernel_bw=bw)
        m = compute_metrics(v3_bw, f"Kernel bw={bw}", show_detail=False)
        if m:
            bw_results.append((bw, m))
    print(f"\n  {'BW':>5} {'n':>5} {'p/day':>6} {'WR%':>6} {'AvgRet':>8} {'Exp3/3':>8}")
    print(f"  {'-'*42}")
    for bw, m in bw_results:
        print(f"  {bw:>5.2f} {m['n']:>5} {m['picks_per_day']:>5.1f} {m['wr']:>5.1f}% {m['avg_ret']:>+7.2f}% {m['exp_3_3']:>+7.3f}%")

    # ════════════════════════════════════════════════════════════
    # Feature importance
    # ════════════════════════════════════════════════════════════
    analyze_feature_importance(data)

    # ════════════════════════════════════════════════════════════
    # TEST 7: PRODUCTION CONFIG — Kernel + ATR<2.5 + Vol>0.5 + Sector Exclusion
    # ════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  TEST 7: PRODUCTION CONFIG (ATR<2.5 + Vol>0.5 + Exclude Tech/Semi)")
    print("=" * 70)
    v3_prod, _, _ = run_backtest(data, v3_mode='er_floor', er_floor=0.5,
                                  method='kernel', max_atr_pct=2.5,
                                  min_volume_ratio=0.5,
                                  exclude_sectors={'Technology', 'Semiconductors'})
    m_prod = compute_metrics(v3_prod, "v3 PRODUCTION: E[R]>0.5% + ATR<2.5 + Vol>0.5")
    if m_prod:
        show_comparison(m_prod, m_v2, "PRODUCTION vs v2")

    # TEST 7b: Same but top 5 ranking
    print("\n" + "=" * 70)
    print("  TEST 7b: PRODUCTION + Top 5 Ranking")
    print("=" * 70)
    v3_prod5, _, _ = run_backtest(data, v3_mode='rank_top_n', v3_top_n=5,
                                   method='kernel', max_atr_pct=2.5,
                                   min_volume_ratio=0.5,
                                   exclude_sectors={'Technology', 'Semiconductors'})
    m_prod5 = compute_metrics(v3_prod5, "v3 PROD Top5: ATR<2.5 + Vol>0.5")
    if m_prod5:
        show_comparison(m_prod5, m_v2, "PROD Top5 vs v2")

    # ════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print(f"  FINAL SUMMARY — ALL MODES")
    print(f"{'='*70}")
    all_modes = [
        ('v2: score≥70', m_v2),
        ('Bucket Top5', m_bucket5),
        ('Kernel Top5', m_kernel5),
        ('Kernel Top5+Cap30', m_kernel5_cap),
        ('Kernel E[R]>0', m_kernel_pos),
        ('Kernel E[R]>0.5%', m_kernel_05),
        ('PROD E[R]>0.5%', m_prod),
        ('PROD Top5', m_prod5),
    ]
    print(f"  {'Mode':<22} {'n':>5} {'p/day':>6} {'WR%':>6} {'AvgRet':>8} {'TP2%':>6} {'TP3%':>6} {'SL3%':>6} {'Exp3/3':>8}")
    print(f"  {'-'*75}")
    for name, m in all_modes:
        if not m:
            continue
        print(f"  {name:<22} {m['n']:>5} {m['picks_per_day']:>5.1f} {m['wr']:>5.1f}% {m['avg_ret']:>+7.2f}% "
              f"{m['tp_2']:>5.1f}% {m['tp_3']:>5.1f}% {m['sl_3']:>5.1f}% {m['exp_3_3']:>+7.3f}%")

    print(f"\n{'='*70}")
    print(f"  BACKTEST COMPLETE — Combined Dataset ({len(data)} rows)")
    print(f"{'='*70}")
