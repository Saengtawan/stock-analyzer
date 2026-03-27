#!/usr/bin/env python3
"""
Kernel Redesign Analysis — Data-Driven Discovery Kernel from Scratch.

NO hardcoded gates. NO sector exclusions. The kernel learns EVERYTHING from data.

Phases:
  1. Feature Universe IC Analysis (Spearman IC vs outcome_5d)
  2. Correlation Matrix of top features
  3. Greedy Feature Selection with walk-forward backtest
  4. Final Comparison vs production kernel
  5. Sector Analysis — does the kernel naturally avoid bad sectors?

Usage:
    python scripts/kernel_redesign_analysis.py
"""

import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np
from scipy import stats as sp_stats

warnings.filterwarnings('ignore')

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# ═══════════════════════════════════════════════════════════════════
# SECTOR MAPPING: fine-grained signal sectors → ETF sector names
# ═══════════════════════════════════════════════════════════════════
SECTOR_MAP = {
    'Technology': 'Technology',
    'Semiconductors': 'Technology',
    'Communication Services': 'Communication Services',
    'Media': 'Communication Services',
    'Telecom': 'Communication Services',
    'Consumer Cyclical': 'Consumer Cyclical',
    'Consumer_Retail': 'Consumer Cyclical',
    'Consumer_Travel': 'Consumer Cyclical',
    'Consumer_Auto': 'Consumer Cyclical',
    'Consumer Defensive': 'Consumer Defensive',
    'Consumer_Staples': 'Consumer Defensive',
    'Consumer_Food': 'Consumer Defensive',
    'Financial Services': 'Financial Services',
    'Finance_Insurance': 'Financial Services',
    'Finance_Payments': 'Financial Services',
    'Finance_Banks': 'Financial Services',
    'Finance_Capital_Markets': 'Financial Services',
    'Healthcare': 'Healthcare',
    'Healthcare_Pharma': 'Healthcare',
    'Healthcare_MedDevices': 'Healthcare',
    'Healthcare_Biotech': 'Healthcare',
    'Industrials': 'Industrials',
    'Industrial_Aerospace': 'Industrials',
    'Industrial_Machinery': 'Industrials',
    'Industrial_Transport': 'Industrials',
    'Industrial_Conglomerate': 'Industrials',
    'Energy': 'Energy',
    'Energy_Oil': 'Energy',
    'Energy_Refining': 'Energy',
    'Energy_Services': 'Energy',
    'Energy_Midstream': 'Energy',
    'Basic Materials': 'Basic Materials',
    'Materials_Metals': 'Basic Materials',
    'Materials_Chemicals': 'Basic Materials',
    'Real Estate': 'Real Estate',
    'Real_Estate_Residential': 'Real Estate',
    'Real_Estate_Retail': 'Real Estate',
    'Real_Estate_REIT': 'Real Estate',
    'Utilities': 'Utilities',
    'Utilities_Electric': 'Utilities',
    'Utilities_Gas': 'Utilities',
}


def load_data():
    """Load combined signal + backfill data with macro + breadth JOINs."""
    conn = None  # via get_session())
    conn.row_factory = dict

    # Main signal data
    rows = conn.execute("""
        WITH combined AS (
            SELECT scan_date, symbol, outcome_5d, outcome_max_dd_5d,
                   atr_pct, volume_ratio, momentum_20d, entry_rsi, momentum_5d,
                   distance_from_20d_high, vix_at_signal, sector,
                   sector_1d_change, sector_5d_return, sector_etf_1d_pct,
                   distance_from_high, spy_pct_above_sma, new_score,
                   close_to_high_pct, consecutive_down_days,
                   distance_from_200d_ma, short_percent_of_float,
                   first_30min_return, bounce_pct_from_lod,
                   entry_vs_open_pct, entry_vs_vwap_pct,
                   margin_to_rsi, margin_to_atr, margin_to_score,
                   1 as priority
            FROM signal_outcomes WHERE outcome_5d IS NOT NULL AND atr_pct IS NOT NULL
            UNION ALL
            SELECT scan_date, symbol, outcome_5d, outcome_max_dd_5d,
                   atr_pct, volume_ratio, momentum_20d, entry_rsi, momentum_5d,
                   distance_from_20d_high, vix_at_signal, sector,
                   NULL, NULL, NULL,
                   NULL, NULL, NULL,
                   NULL, NULL,
                   NULL, NULL,
                   NULL, NULL,
                   NULL, NULL,
                   NULL, NULL, NULL,
                   2 as priority
            FROM backfill_signal_outcomes WHERE outcome_5d IS NOT NULL AND atr_pct IS NOT NULL
        ),
        deduped AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY scan_date, symbol ORDER BY priority ASC) as rn
            FROM combined
        )
        SELECT d.*,
               m.crude_close, m.gold_close, m.vix_close, m.vix3m_close,
               m.yield_10y, m.yield_3m, m.yield_spread, m.dxy_close,
               m.spy_close, m.hyg_close,
               b.pct_above_20d_ma, b.pct_above_50d_ma, b.ad_ratio,
               b.new_52w_highs, b.new_52w_lows
        FROM deduped d
        LEFT JOIN macro_snapshots m
            ON m.date = CASE
                WHEN strftime('%w', d.scan_date) = '6' THEN date(d.scan_date, '-1 day')
                WHEN strftime('%w', d.scan_date) = '0' THEN date(d.scan_date, '-2 days')
                ELSE d.scan_date END
        LEFT JOIN market_breadth b
            ON b.date = CASE
                WHEN strftime('%w', d.scan_date) = '6' THEN date(d.scan_date, '-1 day')
                WHEN strftime('%w', d.scan_date) = '0' THEN date(d.scan_date, '-2 days')
                ELSE d.scan_date END
        WHERE d.rn = 1
        ORDER BY d.scan_date
    """).fetchall()

    # Sector ETF returns (for JOIN)
    sector_etf_rows = conn.execute("""
        SELECT date, sector, pct_change
        FROM sector_etf_daily_returns
        ORDER BY date
    """).fetchall()
    conn.close()

    # Build sector ETF lookup: (date, sector_name) -> pct_change
    sector_etf = {}
    for r in sector_etf_rows:
        sector_etf[(r['date'], r['sector'])] = r['pct_change']

    return rows, sector_etf


def build_feature_matrix(rows, sector_etf):
    """Convert raw DB rows into a dict of arrays for each feature + outcome."""
    n = len(rows)

    # Pre-allocate with NaN
    data = {
        'scan_date': [],
        'symbol': [],
        'sector': [],
        'outcome_5d': np.full(n, np.nan),
        'outcome_max_dd_5d': np.full(n, np.nan),
        # Stock-level features
        'atr_pct': np.full(n, np.nan),
        'volume_ratio': np.full(n, np.nan),
        'momentum_20d': np.full(n, np.nan),
        'entry_rsi': np.full(n, np.nan),
        'momentum_5d': np.full(n, np.nan),
        'distance_from_20d_high': np.full(n, np.nan),
        'vix_at_signal': np.full(n, np.nan),
        # Extra signal features
        'sector_1d_change': np.full(n, np.nan),
        'sector_5d_return': np.full(n, np.nan),
        'sector_etf_1d_pct': np.full(n, np.nan),
        'distance_from_high': np.full(n, np.nan),
        'spy_pct_above_sma': np.full(n, np.nan),
        'new_score': np.full(n, np.nan),
        'close_to_high_pct': np.full(n, np.nan),
        'consecutive_down_days': np.full(n, np.nan),
        'distance_from_200d_ma': np.full(n, np.nan),
        'short_percent_of_float': np.full(n, np.nan),
        'first_30min_return': np.full(n, np.nan),
        'bounce_pct_from_lod': np.full(n, np.nan),
        'entry_vs_open_pct': np.full(n, np.nan),
        'entry_vs_vwap_pct': np.full(n, np.nan),
        # Macro features
        'crude_close': np.full(n, np.nan),
        'gold_close': np.full(n, np.nan),
        'vix_close': np.full(n, np.nan),
        'vix3m_close': np.full(n, np.nan),
        'yield_10y': np.full(n, np.nan),
        'yield_3m': np.full(n, np.nan),
        'yield_spread': np.full(n, np.nan),
        'dxy_close': np.full(n, np.nan),
        'spy_close': np.full(n, np.nan),
        'hyg_close': np.full(n, np.nan),
        # Breadth features
        'pct_above_20d_ma': np.full(n, np.nan),
        'pct_above_50d_ma': np.full(n, np.nan),
        'ad_ratio': np.full(n, np.nan),
        'new_52w_highs': np.full(n, np.nan),
        'new_52w_lows': np.full(n, np.nan),
        # Sector ETF pct (joined separately)
        'sector_etf_pct': np.full(n, np.nan),
    }

    for i, r in enumerate(rows):
        data['scan_date'].append(r['scan_date'])
        data['symbol'].append(r['symbol'])
        data['sector'].append(r['sector'])

        for col in ['outcome_5d', 'outcome_max_dd_5d',
                     'atr_pct', 'volume_ratio', 'momentum_20d', 'entry_rsi',
                     'momentum_5d', 'distance_from_20d_high', 'vix_at_signal',
                     'sector_1d_change', 'sector_5d_return', 'sector_etf_1d_pct',
                     'distance_from_high', 'spy_pct_above_sma', 'new_score',
                     'close_to_high_pct', 'consecutive_down_days',
                     'distance_from_200d_ma', 'short_percent_of_float',
                     'first_30min_return', 'bounce_pct_from_lod',
                     'entry_vs_open_pct', 'entry_vs_vwap_pct',
                     'crude_close', 'gold_close', 'vix_close', 'vix3m_close',
                     'yield_10y', 'yield_3m', 'yield_spread', 'dxy_close',
                     'spy_close', 'hyg_close',
                     'pct_above_20d_ma', 'pct_above_50d_ma', 'ad_ratio',
                     'new_52w_highs', 'new_52w_lows']:
            val = r[col]
            if val is not None:
                data[col][i] = float(val)

        # Sector ETF JOIN
        sector = r['sector']
        scan_date = r['scan_date']
        if sector:
            etf_sector = SECTOR_MAP.get(sector, sector)
            # Map date for weekends
            import datetime
            try:
                dt = datetime.date.fromisoformat(scan_date)
                if dt.weekday() == 5:  # Saturday
                    dt = dt - datetime.timedelta(days=1)
                elif dt.weekday() == 6:  # Sunday
                    dt = dt - datetime.timedelta(days=2)
                key = (dt.isoformat(), etf_sector)
                if key in sector_etf:
                    data['sector_etf_pct'][i] = sector_etf[key]
            except (ValueError, TypeError):
                pass

    return data


def compute_derived_features(data):
    """Compute derived features from raw data."""
    n = len(data['outcome_5d'])

    # atr_risk = atr_pct * vix_close / 20
    data['atr_risk'] = np.full(n, np.nan)
    mask = ~np.isnan(data['atr_pct']) & ~np.isnan(data['vix_close'])
    data['atr_risk'][mask] = data['atr_pct'][mask] * data['vix_close'][mask] / 20.0

    # vix_term_structure = vix3m_close - vix_close
    data['vix_term_structure'] = np.full(n, np.nan)
    mask = ~np.isnan(data['vix3m_close']) & ~np.isnan(data['vix_close'])
    data['vix_term_structure'][mask] = data['vix3m_close'][mask] - data['vix_close'][mask]

    # breadth_delta_5d: pct_above_20d_ma - LAG(5 trading days)
    data['breadth_delta_5d'] = np.full(n, np.nan)
    dates = data['scan_date']
    unique_dates = sorted(set(dates))
    date_to_breadth = {}
    for i, d in enumerate(dates):
        if not np.isnan(data['pct_above_20d_ma'][i]):
            date_to_breadth[d] = data['pct_above_20d_ma'][i]

    for i in range(n):
        d = dates[i]
        if np.isnan(data['pct_above_20d_ma'][i]):
            continue
        try:
            idx = unique_dates.index(d)
            if idx >= 5:
                prev_date = unique_dates[idx - 5]
                if prev_date in date_to_breadth:
                    data['breadth_delta_5d'][i] = data['pct_above_20d_ma'][i] - date_to_breadth[prev_date]
        except (ValueError, IndexError):
            pass

    # crude_change_5d, gold_change_5d (rate of change)
    for name, src in [('crude_change_5d', 'crude_close'), ('gold_change_5d', 'gold_close')]:
        data[name] = np.full(n, np.nan)
        date_to_val = {}
        for i, d in enumerate(dates):
            if not np.isnan(data[src][i]):
                date_to_val[d] = data[src][i]
        for i in range(n):
            d = dates[i]
            if np.isnan(data[src][i]):
                continue
            try:
                idx = unique_dates.index(d)
                if idx >= 5:
                    prev_date = unique_dates[idx - 5]
                    if prev_date in date_to_val and date_to_val[prev_date] != 0:
                        data[name][i] = (data[src][i] - date_to_val[prev_date]) / date_to_val[prev_date] * 100.0
            except (ValueError, IndexError):
                pass

    # hi_lo_ratio = new_52w_highs / (new_52w_highs + new_52w_lows + 1)
    data['hi_lo_ratio'] = np.full(n, np.nan)
    mask = ~np.isnan(data['new_52w_highs']) & ~np.isnan(data['new_52w_lows'])
    data['hi_lo_ratio'][mask] = data['new_52w_highs'][mask] / (
        data['new_52w_highs'][mask] + data['new_52w_lows'][mask] + 1.0)

    # vix_distance_from_20 = vix_close - 20 (distance from "normal" threshold)
    data['vix_distance_from_20'] = np.full(n, np.nan)
    mask = ~np.isnan(data['vix_close'])
    data['vix_distance_from_20'][mask] = data['vix_close'][mask] - 20.0

    # spy_change_5d (rate of change)
    data['spy_change_5d'] = np.full(n, np.nan)
    date_to_spy = {}
    for i, d in enumerate(dates):
        if not np.isnan(data['spy_close'][i]):
            date_to_spy[d] = data['spy_close'][i]
    for i in range(n):
        d = dates[i]
        if np.isnan(data['spy_close'][i]):
            continue
        try:
            idx = unique_dates.index(d)
            if idx >= 5:
                prev_date = unique_dates[idx - 5]
                if prev_date in date_to_spy and date_to_spy[prev_date] != 0:
                    data['spy_change_5d'][i] = (data['spy_close'][i] - date_to_spy[prev_date]) / date_to_spy[prev_date] * 100.0
        except (ValueError, IndexError):
            pass

    # rsi_distance_from_30 = entry_rsi - 30 (how oversold)
    data['rsi_distance_from_30'] = np.full(n, np.nan)
    mask = ~np.isnan(data['entry_rsi'])
    data['rsi_distance_from_30'][mask] = data['entry_rsi'][mask] - 30.0

    return data


# ═══════════════════════════════════════════════════════════════════
# PHASE 1: Feature Universe IC Analysis
# ═══════════════════════════════════════════════════════════════════
def phase1_ic_analysis(data):
    """Compute Spearman IC for every feature vs outcome_5d."""
    print("=" * 80)
    print("PHASE 1: FEATURE UNIVERSE — SPEARMAN IC vs outcome_5d")
    print("=" * 80)

    outcome = data['outcome_5d']

    # All candidate features
    feature_names = [
        # Stock-level
        'atr_pct', 'volume_ratio', 'momentum_20d', 'entry_rsi', 'momentum_5d',
        'distance_from_20d_high', 'vix_at_signal',
        # Extra signal features
        'sector_1d_change', 'sector_5d_return', 'sector_etf_1d_pct',
        'distance_from_high', 'spy_pct_above_sma', 'new_score',
        'close_to_high_pct', 'consecutive_down_days',
        'distance_from_200d_ma', 'short_percent_of_float',
        'first_30min_return', 'bounce_pct_from_lod',
        'entry_vs_open_pct', 'entry_vs_vwap_pct',
        # Macro
        'crude_close', 'gold_close', 'vix_close', 'vix3m_close',
        'yield_10y', 'yield_3m', 'yield_spread', 'dxy_close',
        'spy_close', 'hyg_close',
        # Breadth
        'pct_above_20d_ma', 'pct_above_50d_ma', 'ad_ratio',
        'new_52w_highs', 'new_52w_lows',
        # Sector ETF
        'sector_etf_pct',
        # Derived
        'atr_risk', 'vix_term_structure', 'breadth_delta_5d',
        'crude_change_5d', 'gold_change_5d', 'hi_lo_ratio',
        'vix_distance_from_20', 'spy_change_5d', 'rsi_distance_from_30',
    ]

    results = []
    for feat_name in feature_names:
        if feat_name not in data:
            continue
        feat = data[feat_name]
        # Valid mask: both feature and outcome not NaN
        valid = ~np.isnan(feat) & ~np.isnan(outcome)
        n_valid = int(valid.sum())
        if n_valid < 30:
            results.append((feat_name, np.nan, np.nan, n_valid))
            continue
        ic, pval = sp_stats.spearmanr(feat[valid], outcome[valid])
        results.append((feat_name, ic, pval, n_valid))

    # Sort by |IC|
    results.sort(key=lambda x: abs(x[1]) if not np.isnan(x[1]) else 0, reverse=True)

    print(f"\n{'Feature':<28} {'IC':>8} {'p-value':>12} {'|IC|':>8} {'N':>6}  Sig")
    print("-" * 80)
    for feat_name, ic, pval, n_valid in results:
        if np.isnan(ic):
            print(f"{feat_name:<28} {'N/A':>8} {'N/A':>12} {'N/A':>8} {n_valid:>6}")
            continue
        sig = '***' if pval < 0.001 else '**' if pval < 0.01 else '*' if pval < 0.05 else ''
        print(f"{feat_name:<28} {ic:>+8.4f} {pval:>12.2e} {abs(ic):>8.4f} {n_valid:>6}  {sig}")

    print(f"\nTotal features analyzed: {len(results)}")
    print("Significance: *** p<0.001, ** p<0.01, * p<0.05")

    # Also compute IC vs binary win (outcome_5d > 0)
    print("\n\n--- IC vs BINARY WIN (outcome_5d > 0) ---")
    print(f"{'Feature':<28} {'IC':>8} {'p-value':>12} {'N':>6}  Sig")
    print("-" * 70)
    win = (outcome > 0).astype(float)
    win[np.isnan(outcome)] = np.nan
    results_win = []
    for feat_name in feature_names:
        if feat_name not in data:
            continue
        feat = data[feat_name]
        valid = ~np.isnan(feat) & ~np.isnan(win)
        n_valid = int(valid.sum())
        if n_valid < 30:
            continue
        ic, pval = sp_stats.spearmanr(feat[valid], win[valid])
        results_win.append((feat_name, ic, pval, n_valid))
    results_win.sort(key=lambda x: abs(x[1]), reverse=True)
    for feat_name, ic, pval, n_valid in results_win[:20]:
        sig = '***' if pval < 0.001 else '**' if pval < 0.01 else '*' if pval < 0.05 else ''
        print(f"{feat_name:<28} {ic:>+8.4f} {pval:>12.2e} {n_valid:>6}  {sig}")

    return results


# ═══════════════════════════════════════════════════════════════════
# PHASE 2: Correlation Matrix
# ═══════════════════════════════════════════════════════════════════
def phase2_correlation(data, ic_results):
    """Show correlation between top features by |IC|."""
    print("\n\n" + "=" * 80)
    print("PHASE 2: CORRELATION MATRIX — Top 15 Features by |IC|")
    print("=" * 80)

    # Get top 15 features with valid IC
    top_feats = [r[0] for r in ic_results if not np.isnan(r[1])][:15]

    print(f"\nTop 15 features: {top_feats}")

    # Build matrix
    n = len(data['outcome_5d'])
    mat = np.column_stack([data[f] for f in top_feats])

    # Pairwise correlations
    print(f"\n{'':>28}", end='')
    for j, f in enumerate(top_feats):
        print(f" {f[:6]:>6}", end='')
    print()

    redundant_pairs = []
    for i, fi in enumerate(top_feats):
        print(f"{fi:<28}", end='')
        for j, fj in enumerate(top_feats):
            vi = data[fi]
            vj = data[fj]
            valid = ~np.isnan(vi) & ~np.isnan(vj)
            if valid.sum() < 30:
                print(f" {'N/A':>6}", end='')
                continue
            r, _ = sp_stats.pearsonr(vi[valid], vj[valid])
            if i < j and abs(r) > 0.7:
                redundant_pairs.append((fi, fj, r))
            if i == j:
                print(f" {'1.000':>6}", end='')
            else:
                print(f" {r:>6.3f}", end='')
        print()

    if redundant_pairs:
        print(f"\n*** REDUNDANT PAIRS (|r| > 0.7): ***")
        for fi, fj, r in redundant_pairs:
            print(f"  {fi} <-> {fj}: r={r:.3f}")
    else:
        print("\nNo redundant pairs found (|r| > 0.7)")

    return top_feats, redundant_pairs


# ═══════════════════════════════════════════════════════════════════
# GAUSSIAN KERNEL — core implementation
# ═══════════════════════════════════════════════════════════════════
def gaussian_kernel_predict(train_X, train_y, test_x, bw):
    """
    Gaussian kernel regression.
    train_X: (N, D) already z-scored
    test_x: (D,) already z-scored using TRAINING stats
    Returns: (er, n_eff)
    """
    dists = np.sqrt(np.sum((train_X - test_x) ** 2, axis=1))
    weights = np.exp(-0.5 * (dists / bw) ** 2)
    total_w = weights.sum()
    if total_w < 1e-10:
        return 0.0, 0.0
    er = float(np.sum(weights * train_y) / total_w)
    n_eff = float(total_w ** 2 / np.sum(weights ** 2))
    return er, n_eff


def walk_forward_backtest(data, feature_list, bw, min_train_dates=20, top_n=5,
                          min_er=0.0, min_n_eff=3.0, verbose=False):
    """
    Walk-forward backtest: for each date, train on ALL prior dates, predict on current.
    Select top_n by E[R] where E[R]>0 and n_eff>=3.

    Returns dict with WR, AvgRet, SLRate, total_picks, daily_picks list.
    """
    n = len(data['outcome_5d'])
    dates = data['scan_date']
    unique_dates = sorted(set(dates))

    if len(unique_dates) < min_train_dates + 1:
        return None

    # Pre-extract feature arrays
    feat_arrays = [data[f] for f in feature_list]
    outcome = data['outcome_5d']
    max_dd = data['outcome_max_dd_5d']

    all_picks = []
    daily_results = []

    for test_date_idx in range(min_train_dates, len(unique_dates)):
        test_date = unique_dates[test_date_idx]
        train_dates_set = set(unique_dates[:test_date_idx])

        # Build train indices
        train_idx = []
        test_idx = []
        for i in range(n):
            # Check all features are valid for this row
            all_valid = True
            for fa in feat_arrays:
                if np.isnan(fa[i]):
                    all_valid = False
                    break
            if not all_valid or np.isnan(outcome[i]):
                continue

            if dates[i] in train_dates_set:
                train_idx.append(i)
            elif dates[i] == test_date:
                test_idx.append(i)

        if len(train_idx) < 50 or len(test_idx) == 0:
            continue

        train_idx = np.array(train_idx)
        test_idx = np.array(test_idx)

        # Build train matrix
        train_X = np.column_stack([fa[train_idx] for fa in feat_arrays])
        train_y = outcome[train_idx]

        # Z-score using training stats
        means = train_X.mean(axis=0)
        stds = train_X.std(axis=0)
        stds[stds == 0] = 1.0
        train_X_norm = (train_X - means) / stds

        # Score each test row
        candidates = []
        for ti in test_idx:
            x = np.array([fa[ti] for fa in feat_arrays])
            if np.any(np.isnan(x)):
                continue
            x_norm = (x - means) / stds
            er, n_eff = gaussian_kernel_predict(train_X_norm, train_y, x_norm, bw)
            if er > min_er and n_eff >= min_n_eff:
                candidates.append({
                    'idx': ti,
                    'symbol': data['symbol'][ti],
                    'sector': data['sector'][ti],
                    'er': er,
                    'n_eff': n_eff,
                    'actual': outcome[ti],
                    'max_dd': max_dd[ti] if not np.isnan(max_dd[ti]) else None,
                })

        # Select top_n by E[R]
        candidates.sort(key=lambda c: c['er'], reverse=True)
        picks = candidates[:top_n]

        if picks:
            for p in picks:
                p['date'] = test_date
                all_picks.append(p)

            wr = sum(1 for p in picks if p['actual'] > 0) / len(picks) * 100
            avg_ret = np.mean([p['actual'] for p in picks])
            sl_count = sum(1 for p in picks if p['max_dd'] is not None and p['max_dd'] <= -3.0)
            sl_rate = sl_count / len(picks) * 100

            daily_results.append({
                'date': test_date,
                'n_picks': len(picks),
                'wr': wr,
                'avg_ret': avg_ret,
                'sl_rate': sl_rate,
            })

    if not all_picks:
        return None

    # Aggregate results
    total_picks = len(all_picks)
    wins = sum(1 for p in all_picks if p['actual'] > 0)
    wr = wins / total_picks * 100
    avg_ret = np.mean([p['actual'] for p in all_picks])
    sl_count = sum(1 for p in all_picks if p['max_dd'] is not None and p['max_dd'] <= -3.0)
    sl_rate = sl_count / total_picks * 100
    expectancy = avg_ret * (wr / 100) + np.mean([p['actual'] for p in all_picks if p['actual'] <= 0] or [0]) * (1 - wr / 100)

    return {
        'wr': wr,
        'avg_ret': avg_ret,
        'sl_rate': sl_rate,
        'total_picks': total_picks,
        'expectancy': avg_ret,  # already net expectancy
        'daily_results': daily_results,
        'all_picks': all_picks,
        'wins': wins,
    }


# ═══════════════════════════════════════════════════════════════════
# PHASE 3: Greedy Feature Selection
# ═══════════════════════════════════════════════════════════════════
def phase3_greedy_selection(data, ic_results):
    """Greedy forward feature selection with walk-forward backtest."""
    print("\n\n" + "=" * 80)
    print("PHASE 3: GREEDY FEATURE SELECTION (Walk-Forward, No Gates)")
    print("=" * 80)

    # Candidate features — those with |IC| > 0 and enough data
    candidate_features = []
    for feat_name, ic, pval, n_valid in ic_results:
        if np.isnan(ic):
            continue
        if n_valid < 500:  # need enough data for walk-forward
            continue
        candidate_features.append(feat_name)

    print(f"\nCandidate features ({len(candidate_features)}): {candidate_features}")
    print(f"Bandwidths to test: [0.5, 0.6, 0.7, 0.8]")
    print(f"Selection criterion: best WR improvement")
    print()

    bandwidths = [0.5, 0.6, 0.7, 0.8]
    selected = []
    best_results_history = []
    remaining = list(candidate_features)

    # Step 0: baseline (no kernel, just pick all with outcome)
    outcome = data['outcome_5d']
    valid_outcome = ~np.isnan(outcome)
    baseline_wr = np.mean(outcome[valid_outcome] > 0) * 100
    print(f"Baseline (random pick): WR={baseline_wr:.1f}%, N={int(valid_outcome.sum())}")
    print()

    step = 0
    best_overall_wr = 0.0

    while remaining and step < 12:  # Max 12 features
        step += 1
        print(f"\n--- STEP {step}: Testing addition of each remaining feature ---")

        best_feat = None
        best_bw = None
        best_wr = 0.0
        best_result = None

        for candidate in remaining:
            test_feats = selected + [candidate]

            # Quick data availability check
            feat_arrays = [data[f] for f in test_feats]
            valid_mask = ~np.isnan(data['outcome_5d'])
            for fa in feat_arrays:
                valid_mask = valid_mask & ~np.isnan(fa)
            n_valid = int(valid_mask.sum())
            if n_valid < 200:
                continue

            for bw in bandwidths:
                result = walk_forward_backtest(data, test_feats, bw)
                if result is None:
                    continue
                if result['total_picks'] < 20:
                    continue

                if result['wr'] > best_wr:
                    best_wr = result['wr']
                    best_feat = candidate
                    best_bw = bw
                    best_result = result

            # Print progress
            sys.stdout.write('.')
            sys.stdout.flush()

        print()

        if best_feat is None:
            print("  No valid candidate found. Stopping.")
            break

        # Check if improvement is meaningful
        if step > 1 and best_wr <= best_overall_wr + 0.3:
            print(f"  Best candidate: +{best_feat} (bw={best_bw})")
            print(f"  WR={best_wr:.1f}% vs prev best {best_overall_wr:.1f}% — improvement < 0.3pp, STOPPING")
            # Still record this one but mark as stopping point
            selected.append(best_feat)
            remaining.remove(best_feat)
            best_results_history.append({
                'step': step,
                'feature_added': best_feat,
                'features': list(selected),
                'bw': best_bw,
                'result': best_result,
                'marginal': False,
            })
            break

        selected.append(best_feat)
        remaining.remove(best_feat)
        best_overall_wr = best_wr

        best_results_history.append({
            'step': step,
            'feature_added': best_feat,
            'features': list(selected),
            'bw': best_bw,
            'result': best_result,
            'marginal': True,
        })

        r = best_result
        print(f"  SELECTED: +{best_feat} (bw={best_bw})")
        print(f"  Features: {selected}")
        print(f"  WR={r['wr']:.1f}%  AvgRet={r['avg_ret']:+.2f}%  SL={r['sl_rate']:.1f}%  "
              f"Picks={r['total_picks']}  Wins={r['wins']}")

    # Summary table
    print("\n\n" + "=" * 80)
    print("GREEDY SELECTION SUMMARY")
    print("=" * 80)
    print(f"\n{'Step':<5} {'Feature Added':<28} {'BW':>4} {'WR%':>6} {'AvgRet':>8} {'SL%':>6} {'Picks':>6}")
    print("-" * 75)
    for h in best_results_history:
        r = h['result']
        flag = ' *' if not h['marginal'] else ''
        print(f"{h['step']:<5} {h['feature_added']:<28} {h['bw']:>4.1f} {r['wr']:>6.1f} "
              f"{r['avg_ret']:>+8.2f} {r['sl_rate']:>6.1f} {r['total_picks']:>6}{flag}")
    print("(* = marginal improvement, stopping point)")

    # Find best step
    best_step = max(best_results_history, key=lambda h: h['result']['wr'])
    print(f"\nBest configuration: Step {best_step['step']}")
    print(f"  Features: {best_step['features']}")
    print(f"  Bandwidth: {best_step['bw']}")
    r = best_step['result']
    print(f"  WR={r['wr']:.1f}%  AvgRet={r['avg_ret']:+.2f}%  SL={r['sl_rate']:.1f}%  Picks={r['total_picks']}")

    # Now do bandwidth sweep on the best feature set
    print("\n\n--- BANDWIDTH SWEEP on best feature set ---")
    best_feats = best_step['features']
    print(f"Features: {best_feats}")
    print(f"\n{'BW':>4} {'WR%':>6} {'AvgRet':>8} {'SL%':>6} {'Picks':>6} {'Expectancy':>10}")
    print("-" * 50)
    bw_results = {}
    for bw in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5]:
        result = walk_forward_backtest(data, best_feats, bw)
        if result and result['total_picks'] >= 10:
            r = result
            bw_results[bw] = result
            print(f"{bw:>4.1f} {r['wr']:>6.1f} {r['avg_ret']:>+8.2f} {r['sl_rate']:>6.1f} "
                  f"{r['total_picks']:>6} {r['avg_ret']:>+10.3f}")

    return best_results_history, bw_results


# ═══════════════════════════════════════════════════════════════════
# PHASE 3b: Greedy Selection — HIGH COVERAGE ONLY (>=90%)
# ═══════════════════════════════════════════════════════════════════
def phase3b_high_coverage_selection(data, ic_results):
    """Same as Phase 3 but only features with >=90% coverage (deployable kernel)."""
    print("\n\n" + "=" * 80)
    print("PHASE 3b: GREEDY SELECTION — HIGH COVERAGE FEATURES ONLY (>=90%)")
    print("  (Deployable kernel — works on ALL data including backfill)")
    print("=" * 80)

    outcome = data['outcome_5d']
    total_with_outcome = int((~np.isnan(outcome)).sum())

    # Filter to features with >=90% coverage
    candidate_features = []
    for feat_name, ic, pval, n_valid in ic_results:
        if np.isnan(ic):
            continue
        if n_valid < total_with_outcome * 0.90:
            continue
        candidate_features.append(feat_name)

    print(f"\nHigh-coverage features ({len(candidate_features)}):")
    for f in candidate_features:
        valid_f = ~np.isnan(data[f]) & ~np.isnan(outcome)
        pct = int(valid_f.sum()) / total_with_outcome * 100
        # find IC for this feature
        ic_val = next((ic for fn, ic, _, _ in ic_results if fn == f), 0)
        print(f"  {f:<28} coverage={pct:.0f}%  IC={ic_val:+.4f}")

    print(f"\nBandwidths to test: [0.5, 0.6, 0.7, 0.8]")

    bandwidths = [0.5, 0.6, 0.7, 0.8]
    selected = []
    best_results_history = []
    remaining = list(candidate_features)

    baseline_wr = np.mean(outcome[~np.isnan(outcome)] > 0) * 100
    print(f"Baseline (random pick): WR={baseline_wr:.1f}%")

    step = 0
    best_overall_wr = 0.0

    while remaining and step < 12:
        step += 1
        print(f"\n--- STEP {step}: Testing addition of each remaining feature ---")

        best_feat = None
        best_bw = None
        best_wr = 0.0
        best_result = None

        for candidate in remaining:
            test_feats = selected + [candidate]

            feat_arrays = [data[f] for f in test_feats]
            valid_mask = ~np.isnan(data['outcome_5d'])
            for fa in feat_arrays:
                valid_mask = valid_mask & ~np.isnan(fa)
            n_valid = int(valid_mask.sum())
            if n_valid < 200:
                continue

            for bw in bandwidths:
                result = walk_forward_backtest(data, test_feats, bw)
                if result is None:
                    continue
                if result['total_picks'] < 20:
                    continue
                if result['wr'] > best_wr:
                    best_wr = result['wr']
                    best_feat = candidate
                    best_bw = bw
                    best_result = result

            sys.stdout.write('.')
            sys.stdout.flush()

        print()

        if best_feat is None:
            print("  No valid candidate found. Stopping.")
            break

        if step > 1 and best_wr <= best_overall_wr + 0.3:
            print(f"  Best candidate: +{best_feat} (bw={best_bw})")
            print(f"  WR={best_wr:.1f}% vs prev best {best_overall_wr:.1f}% — improvement < 0.3pp, STOPPING")
            selected.append(best_feat)
            remaining.remove(best_feat)
            best_results_history.append({
                'step': step, 'feature_added': best_feat, 'features': list(selected),
                'bw': best_bw, 'result': best_result, 'marginal': False,
            })
            break

        selected.append(best_feat)
        remaining.remove(best_feat)
        best_overall_wr = best_wr

        best_results_history.append({
            'step': step, 'feature_added': best_feat, 'features': list(selected),
            'bw': best_bw, 'result': best_result, 'marginal': True,
        })

        r = best_result
        print(f"  SELECTED: +{best_feat} (bw={best_bw})")
        print(f"  Features: {selected}")
        print(f"  WR={r['wr']:.1f}%  AvgRet={r['avg_ret']:+.2f}%  SL={r['sl_rate']:.1f}%  "
              f"Picks={r['total_picks']}  Wins={r['wins']}")

    # Summary
    print("\n\n" + "=" * 80)
    print("GREEDY SELECTION SUMMARY (HIGH COVERAGE)")
    print("=" * 80)
    print(f"\n{'Step':<5} {'Feature Added':<28} {'BW':>4} {'WR%':>6} {'AvgRet':>8} {'SL%':>6} {'Picks':>6}")
    print("-" * 75)
    for h in best_results_history:
        r = h['result']
        flag = ' *' if not h['marginal'] else ''
        print(f"{h['step']:<5} {h['feature_added']:<28} {h['bw']:>4.1f} {r['wr']:>6.1f} "
              f"{r['avg_ret']:>+8.2f} {r['sl_rate']:>6.1f} {r['total_picks']:>6}{flag}")

    best_step = max(best_results_history, key=lambda h: h['result']['wr'])
    print(f"\nBest HC configuration: Step {best_step['step']}")
    print(f"  Features: {best_step['features']}")
    print(f"  Bandwidth: {best_step['bw']}")
    r = best_step['result']
    print(f"  WR={r['wr']:.1f}%  AvgRet={r['avg_ret']:+.2f}%  SL={r['sl_rate']:.1f}%  Picks={r['total_picks']}")

    # Bandwidth sweep on best HC feature set
    print("\n\n--- BANDWIDTH SWEEP on best HC feature set ---")
    best_feats = best_step['features']
    print(f"Features: {best_feats}")
    print(f"\n{'BW':>4} {'WR%':>6} {'AvgRet':>8} {'SL%':>6} {'Picks':>6}")
    print("-" * 40)
    bw_results = {}
    for bw in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5]:
        result = walk_forward_backtest(data, best_feats, bw)
        if result and result['total_picks'] >= 10:
            r = result
            bw_results[bw] = result
            print(f"{bw:>4.1f} {r['wr']:>6.1f} {r['avg_ret']:>+8.2f} {r['sl_rate']:>6.1f} "
                  f"{r['total_picks']:>6}")

    return best_results_history, bw_results


# ═══════════════════════════════════════════════════════════════════
# PHASE 4: Final Comparison
# ═══════════════════════════════════════════════════════════════════
def phase4_comparison(data, best_history, bw_results,
                      best_history_hc=None, bw_results_hc=None):
    """Compare production kernel (6feat+gates) vs best new kernel (no gates)."""
    print("\n\n" + "=" * 80)
    print("PHASE 4: FINAL COMPARISON — Production vs Best New Kernel")
    print("=" * 80)

    # --- Production kernel: 6 features + gates + sector exclude ---
    prod_features = ['atr_pct', 'volume_ratio', 'momentum_20d',
                     'crude_close', 'gold_close', 'pct_above_20d_ma']
    prod_bw = 0.7

    # Sector exclusions
    exclude_sectors = {'Technology', 'Semiconductors', 'Communication Services'}

    print("\n--- PRODUCTION CONFIG ---")
    print(f"Features: {prod_features}")
    print(f"Bandwidth: {prod_bw}")
    print(f"Exclude sectors: {exclude_sectors}")
    print(f"Gates: ATR [2.5, 4.0], volume >= 1.0, dist_20d >= -5.0, VIX < 24")

    # Run production with gates
    prod_result = walk_forward_with_gates(
        data, prod_features, prod_bw,
        exclude_sectors=exclude_sectors,
        gates={
            'atr_pct': (2.5, 4.0),
            'volume_ratio': (1.0, None),
            'distance_from_20d_high': (-5.0, None),
            'vix_at_signal': (None, 24.0),
        }
    )

    # --- Best new kernel (all features): no gates, no exclusions ---
    best_step = max(best_history, key=lambda h: h['result']['wr'])
    new_features = best_step['features']
    if bw_results:
        best_bw_entry = max(bw_results.items(), key=lambda x: x[1]['wr'])
        new_bw = best_bw_entry[0]
    else:
        new_bw = best_step['bw']

    print(f"\n--- NEW KERNEL (ALL FEATURES) CONFIG ---")
    print(f"Features: {new_features}")
    print(f"Bandwidth: {new_bw}")
    print(f"Gates: NONE (E[R]>0 and n_eff>=3 only)")

    new_result = walk_forward_backtest(data, new_features, new_bw)

    # --- Best HC kernel (high-coverage only) ---
    hc_result = None
    hc_features = []
    hc_bw = 0.7
    if best_history_hc:
        best_step_hc = max(best_history_hc, key=lambda h: h['result']['wr'])
        hc_features = best_step_hc['features']
        if bw_results_hc:
            best_bw_hc = max(bw_results_hc.items(), key=lambda x: x[1]['wr'])
            hc_bw = best_bw_hc[0]
        else:
            hc_bw = best_step_hc['bw']

        print(f"\n--- NEW KERNEL (HIGH COVERAGE) CONFIG ---")
        print(f"Features: {hc_features}")
        print(f"Bandwidth: {hc_bw}")
        print(f"Gates: NONE (E[R]>0 and n_eff>=3 only)")

        hc_result = walk_forward_backtest(data, hc_features, hc_bw)

    # --- Also run production features WITHOUT gates for fair comparison ---
    prod_no_gates = walk_forward_backtest(data, prod_features, prod_bw)

    # Print comparison
    print("\n\n" + "-" * 100)
    print(f"{'Metric':<20} {'Prod (gates)':<16} {'Prod (no gate)':<16} {'New (all feat)':<16} {'New (HC only)':<16}")
    print("-" * 100)

    configs = [
        ('Prod (gates)', prod_result),
        ('Prod (no gates)', prod_no_gates),
        ('New (all feat)', new_result),
        ('New (HC only)', hc_result),
    ]

    metrics = ['wr', 'avg_ret', 'sl_rate', 'total_picks', 'wins']
    labels = ['WR (%)', 'Avg Return (%)', 'SL Rate (%)', 'Total Picks', 'Wins']
    fmts = ['.1f', '+.2f', '.1f', 'd', 'd']

    for metric, label, f in zip(metrics, labels, fmts):
        vals = []
        for _, r in configs:
            if r is None:
                vals.append('N/A')
            else:
                v = r[metric]
                if f == 'd':
                    vals.append(str(int(v)))
                else:
                    vals.append(f"{v:{f}}")
        print(f"{label:<20} {vals[0]:<16} {vals[1]:<16} {vals[2]:<16} {vals[3]:<16}")

    # Monthly breakdown for HC kernel
    print("\n\n--- MONTHLY BREAKDOWN (New Kernel — High Coverage) ---")
    if hc_result:
        monthly = {}
        for p in hc_result['all_picks']:
            month = p['date'][:7]
            if month not in monthly:
                monthly[month] = {'wins': 0, 'total': 0, 'returns': [], 'sl': 0}
            monthly[month]['total'] += 1
            if p['actual'] > 0:
                monthly[month]['wins'] += 1
            monthly[month]['returns'].append(p['actual'])
            if p['max_dd'] is not None and p['max_dd'] <= -3.0:
                monthly[month]['sl'] += 1

        print(f"{'Month':<10} {'Picks':>6} {'WR%':>6} {'AvgRet':>8} {'SL%':>6}")
        print("-" * 40)
        for month in sorted(monthly):
            m = monthly[month]
            wr = m['wins'] / m['total'] * 100 if m['total'] > 0 else 0
            avg = np.mean(m['returns'])
            sl = m['sl'] / m['total'] * 100 if m['total'] > 0 else 0
            print(f"{month:<10} {m['total']:>6} {wr:>6.1f} {avg:>+8.2f} {sl:>6.1f}")

    # Monthly breakdown for new kernel (all features)
    print("\n--- MONTHLY BREAKDOWN (New Kernel — All Features) ---")
    if new_result:
        monthly = {}
        for p in new_result['all_picks']:
            month = p['date'][:7]
            if month not in monthly:
                monthly[month] = {'wins': 0, 'total': 0, 'returns': [], 'sl': 0}
            monthly[month]['total'] += 1
            if p['actual'] > 0:
                monthly[month]['wins'] += 1
            monthly[month]['returns'].append(p['actual'])
            if p['max_dd'] is not None and p['max_dd'] <= -3.0:
                monthly[month]['sl'] += 1

        print(f"{'Month':<10} {'Picks':>6} {'WR%':>6} {'AvgRet':>8} {'SL%':>6}")
        print("-" * 40)
        for month in sorted(monthly):
            m = monthly[month]
            wr = m['wins'] / m['total'] * 100 if m['total'] > 0 else 0
            avg = np.mean(m['returns'])
            sl = m['sl'] / m['total'] * 100 if m['total'] > 0 else 0
            print(f"{month:<10} {m['total']:>6} {wr:>6.1f} {avg:>+8.2f} {sl:>6.1f}")

    # Monthly breakdown for production
    print("\n--- MONTHLY BREAKDOWN (Production with Gates) ---")
    if prod_result:
        monthly = {}
        for p in prod_result['all_picks']:
            month = p['date'][:7]
            if month not in monthly:
                monthly[month] = {'wins': 0, 'total': 0, 'returns': [], 'sl': 0}
            monthly[month]['total'] += 1
            if p['actual'] > 0:
                monthly[month]['wins'] += 1
            monthly[month]['returns'].append(p['actual'])
            if p['max_dd'] is not None and p['max_dd'] <= -3.0:
                monthly[month]['sl'] += 1

        print(f"{'Month':<10} {'Picks':>6} {'WR%':>6} {'AvgRet':>8} {'SL%':>6}")
        print("-" * 40)
        for month in sorted(monthly):
            m = monthly[month]
            wr = m['wins'] / m['total'] * 100 if m['total'] > 0 else 0
            avg = np.mean(m['returns'])
            sl = m['sl'] / m['total'] * 100 if m['total'] > 0 else 0
            print(f"{month:<10} {m['total']:>6} {wr:>6.1f} {avg:>+8.2f} {sl:>6.1f}")

    return prod_result, new_result, hc_result


def walk_forward_with_gates(data, feature_list, bw, exclude_sectors=None,
                            gates=None, min_train_dates=20, top_n=5):
    """Walk-forward backtest WITH hardcoded gates and sector exclusions (production sim)."""
    n = len(data['outcome_5d'])
    dates = data['scan_date']
    unique_dates = sorted(set(dates))
    outcome = data['outcome_5d']
    max_dd = data['outcome_max_dd_5d']

    if exclude_sectors is None:
        exclude_sectors = set()
    if gates is None:
        gates = {}

    feat_arrays = [data[f] for f in feature_list]
    all_picks = []

    for test_date_idx in range(min_train_dates, len(unique_dates)):
        test_date = unique_dates[test_date_idx]
        train_dates_set = set(unique_dates[:test_date_idx])

        train_idx = []
        test_idx = []
        for i in range(n):
            all_valid = True
            for fa in feat_arrays:
                if np.isnan(fa[i]):
                    all_valid = False
                    break
            if not all_valid or np.isnan(outcome[i]):
                continue

            if dates[i] in train_dates_set:
                train_idx.append(i)
            elif dates[i] == test_date:
                # Apply gates for test candidates
                sector = data['sector'][i]
                if sector in exclude_sectors:
                    continue

                gate_pass = True
                for gate_feat, (lo, hi) in gates.items():
                    if gate_feat in data:
                        val = data[gate_feat][i]
                        if np.isnan(val):
                            gate_pass = False
                            break
                        if lo is not None and val < lo:
                            gate_pass = False
                            break
                        if hi is not None and val >= hi:
                            gate_pass = False
                            break

                if gate_pass:
                    test_idx.append(i)

        if len(train_idx) < 50 or len(test_idx) == 0:
            continue

        train_idx = np.array(train_idx)
        test_idx = np.array(test_idx)

        train_X = np.column_stack([fa[train_idx] for fa in feat_arrays])
        train_y = outcome[train_idx]
        means = train_X.mean(axis=0)
        stds = train_X.std(axis=0)
        stds[stds == 0] = 1.0
        train_X_norm = (train_X - means) / stds

        candidates = []
        for ti in test_idx:
            x = np.array([fa[ti] for fa in feat_arrays])
            if np.any(np.isnan(x)):
                continue
            x_norm = (x - means) / stds
            er, n_eff = gaussian_kernel_predict(train_X_norm, train_y, x_norm, bw)
            if er > 0 and n_eff >= 3:
                candidates.append({
                    'idx': ti,
                    'symbol': data['symbol'][ti],
                    'sector': data['sector'][ti],
                    'er': er,
                    'n_eff': n_eff,
                    'actual': outcome[ti],
                    'max_dd': max_dd[ti] if not np.isnan(max_dd[ti]) else None,
                    'date': test_date,
                })

        candidates.sort(key=lambda c: c['er'], reverse=True)
        picks = candidates[:top_n]
        all_picks.extend(picks)

    if not all_picks:
        return None

    total_picks = len(all_picks)
    wins = sum(1 for p in all_picks if p['actual'] > 0)
    wr = wins / total_picks * 100
    avg_ret = np.mean([p['actual'] for p in all_picks])
    sl_count = sum(1 for p in all_picks if p['max_dd'] is not None and p['max_dd'] <= -3.0)
    sl_rate = sl_count / total_picks * 100

    return {
        'wr': wr,
        'avg_ret': avg_ret,
        'sl_rate': sl_rate,
        'total_picks': total_picks,
        'wins': wins,
        'all_picks': all_picks,
    }


# ═══════════════════════════════════════════════════════════════════
# PHASE 5: Sector Analysis
# ═══════════════════════════════════════════════════════════════════
def phase5_sector_analysis(new_result, data):
    """Sector breakdown for new kernel — does it naturally learn sector patterns?"""
    print("\n\n" + "=" * 80)
    print("PHASE 5: SECTOR ANALYSIS — Does the Kernel Learn Sector Patterns?")
    print("=" * 80)

    if new_result is None:
        print("No new kernel results to analyze.")
        return

    # Sector breakdown of picks
    sector_stats = {}
    for p in new_result['all_picks']:
        s = SECTOR_MAP.get(p['sector'], p['sector']) if p['sector'] else 'Unknown'
        if s not in sector_stats:
            sector_stats[s] = {'wins': 0, 'total': 0, 'returns': [], 'sl': 0}
        sector_stats[s]['total'] += 1
        if p['actual'] > 0:
            sector_stats[s]['wins'] += 1
        sector_stats[s]['returns'].append(p['actual'])
        if p['max_dd'] is not None and p['max_dd'] <= -3.0:
            sector_stats[s]['sl'] += 1

    # Also compute overall sector distribution in the universe
    outcome = data['outcome_5d']
    universe_sectors = {}
    for i in range(len(outcome)):
        if np.isnan(outcome[i]):
            continue
        s = SECTOR_MAP.get(data['sector'][i], data['sector'][i]) if data['sector'][i] else 'Unknown'
        if s not in universe_sectors:
            universe_sectors[s] = {'total': 0, 'wins': 0, 'returns': []}
        universe_sectors[s]['total'] += 1
        if outcome[i] > 0:
            universe_sectors[s]['wins'] += 1
        universe_sectors[s]['returns'].append(outcome[i])

    print(f"\n{'Sector':<25} {'Picks':>6} {'WR%':>6} {'AvgRet':>8} {'SL%':>6}  |  "
          f"{'Univ.N':>7} {'Univ.WR%':>9} {'Univ.Ret':>9}  Selection%")
    print("-" * 110)

    for s in sorted(sector_stats, key=lambda x: sector_stats[x]['total'], reverse=True):
        ss = sector_stats[s]
        wr = ss['wins'] / ss['total'] * 100
        avg = np.mean(ss['returns'])
        sl = ss['sl'] / ss['total'] * 100
        u = universe_sectors.get(s, {'total': 0, 'wins': 0, 'returns': [0]})
        u_wr = u['wins'] / u['total'] * 100 if u['total'] > 0 else 0
        u_avg = np.mean(u['returns']) if u['returns'] else 0
        sel_pct = ss['total'] / u['total'] * 100 if u['total'] > 0 else 0
        print(f"{s:<25} {ss['total']:>6} {wr:>6.1f} {avg:>+8.2f} {sl:>6.1f}  |  "
              f"{u['total']:>7} {u_wr:>9.1f} {u_avg:>+9.2f}  {sel_pct:>9.1f}%")

    # Show sectors the kernel AVOIDS (low selection rate vs universe)
    print("\n--- SECTOR SELECTION BIAS ---")
    print("Sectors the kernel naturally avoids (selection rate < 5%):")
    for s in sorted(universe_sectors, key=lambda x: universe_sectors[x]['total'], reverse=True):
        u = universe_sectors[s]
        ss = sector_stats.get(s, {'total': 0})
        sel_pct = ss['total'] / u['total'] * 100 if u['total'] > 0 else 0
        u_wr = u['wins'] / u['total'] * 100 if u['total'] > 0 else 0
        u_avg = np.mean(u['returns']) if u['returns'] else 0
        if sel_pct < 5.0 and u['total'] >= 20:
            print(f"  {s:<25} selected {ss['total']:>3}/{u['total']} ({sel_pct:.1f}%) "
                  f"— universe WR={u_wr:.1f}%, AvgRet={u_avg:+.2f}%")

    print("\nSectors the kernel favors (selection rate > 10%):")
    for s in sorted(universe_sectors, key=lambda x: universe_sectors[x]['total'], reverse=True):
        u = universe_sectors[s]
        ss = sector_stats.get(s, {'total': 0})
        sel_pct = ss['total'] / u['total'] * 100 if u['total'] > 0 else 0
        u_wr = u['wins'] / u['total'] * 100 if u['total'] > 0 else 0
        u_avg = np.mean(u['returns']) if u['returns'] else 0
        if sel_pct > 10.0 and u['total'] >= 20:
            print(f"  {s:<25} selected {ss['total']:>3}/{u['total']} ({sel_pct:.1f}%) "
                  f"— universe WR={u_wr:.1f}%, AvgRet={u_avg:+.2f}%")

    # Key question: does the kernel pick from "excluded" sectors and do well?
    excluded = {'Technology', 'Communication Services'}
    print(f"\n--- EXCLUDED SECTORS IN PRODUCTION: {excluded} ---")
    for s in excluded:
        ss = sector_stats.get(s, {'total': 0, 'wins': 0, 'returns': []})
        if ss['total'] > 0:
            wr = ss['wins'] / ss['total'] * 100
            avg = np.mean(ss['returns'])
            print(f"  {s}: {ss['total']} picks, WR={wr:.1f}%, AvgRet={avg:+.2f}%")
        else:
            print(f"  {s}: 0 picks (kernel naturally avoids)")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    print("=" * 80)
    print("DISCOVERY KERNEL REDESIGN — DATA-DRIVEN ANALYSIS")
    print("No hardcoded gates. No sector exclusions. Pure data learning.")
    print("=" * 80)

    print("\nLoading data...")
    rows, sector_etf = load_data()
    print(f"  Raw rows: {len(rows)}")

    print("Building feature matrix...")
    data = build_feature_matrix(rows, sector_etf)
    print(f"  Total rows: {len(data['outcome_5d'])}")
    print(f"  Unique dates: {len(set(data['scan_date']))}")
    print(f"  Date range: {min(data['scan_date'])} to {max(data['scan_date'])}")

    # Count non-NaN for key features
    outcome = data['outcome_5d']
    valid = ~np.isnan(outcome)
    print(f"  Rows with outcome_5d: {int(valid.sum())}")
    wr = np.mean(outcome[valid] > 0) * 100
    avg = np.mean(outcome[valid])
    print(f"  Overall WR: {wr:.1f}%  AvgRet: {avg:+.2f}%")

    print("\nComputing derived features...")
    data = compute_derived_features(data)

    # Show feature coverage
    print("\n--- Feature Coverage ---")
    feat_names = [k for k in data if k not in ['scan_date', 'symbol', 'sector',
                                                 'outcome_5d', 'outcome_max_dd_5d',
                                                 'priority', 'rn']]
    for f in sorted(feat_names):
        if f in data and isinstance(data[f], np.ndarray):
            valid_f = ~np.isnan(data[f])
            both = valid_f & ~np.isnan(outcome)
            print(f"  {f:<28} N={int(both.sum()):>5}  ({int(both.sum())/int((~np.isnan(outcome)).sum())*100:.0f}%)")

    # Phase 1
    ic_results = phase1_ic_analysis(data)

    # Phase 2
    top_feats, redundant_pairs = phase2_correlation(data, ic_results)

    # Phase 3: Greedy selection (all features)
    best_history, bw_results = phase3_greedy_selection(data, ic_results)

    # Phase 3b: Greedy selection RESTRICTED to high-coverage features (>90%)
    best_history_hc, bw_results_hc = phase3b_high_coverage_selection(data, ic_results)

    # Phase 4
    prod_result, new_result, hc_result = phase4_comparison(
        data, best_history, bw_results, best_history_hc, bw_results_hc)

    # Phase 5 — use HC result as primary (deployable)
    best_for_sector = hc_result if hc_result else new_result
    phase5_sector_analysis(best_for_sector, data)

    print("\n\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
