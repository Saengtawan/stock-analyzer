"""
Phase Re-I: Comprehensive Ensemble Grid Test.

Build v2.2 (disciplined: top 8 macro features + strong reg).
Test all combinations:
  Pure: v2.0, v2.1, v2.2 at multiple thresholds
  Weighted: 0.7/0.3, 0.5/0.5, 0.3/0.7, 1/3-each
  Strict AND: v2.0 AND v2.1 thresholds
  Majority voting: ≥2 of 3 models agree

User priority: QUALITY > QUANTITY (OK if some days = 0 picks)

Test periods: 5 war + 1 normal
Metric: avg WR, worst PnL, Sharpe, total N
Pick: highest Sharpe with worst >= -5% across all periods
"""
import sqlite3
import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')

# Baseline HPs (v2.0, v2.1)
LGB_BASELINE = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 31, 'max_depth': 5, 'min_child_samples': 30,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 1.0, 'reg_lambda': 1.0,
    'n_estimators': 300, 'n_jobs': 4, 'verbose': -1,
}

# Disciplined HPs (v2.2)
LGB_DISCIPLINED = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 15, 'max_depth': 4, 'min_child_samples': 50,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 3.0, 'reg_lambda': 3.0,
    'n_estimators': 200, 'n_jobs': 4, 'verbose': -1,
}

# v2.2 selected new features (top 8 unique signals from v2.1)
V22_NEW_FEATURES = [
    'iwm_spy_ratio',
    'gold_spy_ratio',
    'move_level',
    'vix_vix3m_ratio',
    'defensive_minus_cyclical_5d',
    'oil_20d_chg',
    'vvix_5d_chg',
    'sector_dispersion_5d',
]

TP_PCT = 2.0
DD_PCT = -3.0
WINDOW = 7

PERIODS = [
    ('Normal-2026', '2026-02-15', '2026-03-01', '2026-05-15', False),
    ('RussiaUkraine22', '2022-01-15', '2022-02-15', '2022-04-30', True),
    ('RateHike22', '2022-05-01', '2022-05-15', '2022-07-31', True),
    ('IsraelHamas23', '2023-09-15', '2023-10-07', '2023-12-15', True),
    ('IranIsraelApr24', '2024-03-15', '2024-04-01', '2024-05-31', True),
    ('IranIsraelOct24', '2024-09-15', '2024-10-01', '2024-11-30', True),
]


def build_extended_macro_features():
    con = sqlite3.connect(str(DB))
    macro_db = pd.read_sql("""
        SELECT date, vix_close, vix3m_close, vvix_close, skew_close,
               spy_close, dxy_close, gold_close, crude_close, copper_close,
               hyg_close, tlt_close, lqd_close, ief_close, eem_close,
               yield_10y, yield_3m, yield_spread, usdjpy_close, btc_close
        FROM macro_snapshots
        WHERE date >= '2019-01-01' ORDER BY date
    """, con)
    con.close()
    macro_db['date'] = pd.to_datetime(macro_db['date'])
    ext = pd.read_pickle(CACHE / 'extended_macro.pkl')
    ext['date'] = pd.to_datetime(ext['date'])
    ext_pivot = ext.pivot_table(index='date', columns='symbol', values='close').reset_index()
    df = macro_db.merge(ext_pivot, on='date', how='outer').sort_values('date').reset_index(drop=True)
    df = df.ffill(limit=5)

    # Build features
    for sector in ['XLF', 'XLE', 'XLK', 'XLV', 'XLU', 'XLI', 'XLY', 'XLP', 'XLB', 'XLRE', 'XLC']:
        if sector in df.columns:
            df[f'{sector.lower()}_5d_pct'] = df[sector].pct_change(5) * 100

    sec_5d_cols = [c for c in df.columns if c.endswith('_5d_pct') and c.startswith('xl')]
    if sec_5d_cols:
        df['sector_dispersion_5d'] = df[sec_5d_cols].max(axis=1) - df[sec_5d_cols].min(axis=1)
        defensive = df[['xlu_5d_pct', 'xlp_5d_pct']].mean(axis=1)
        cyclical = df[['xlk_5d_pct', 'xly_5d_pct']].mean(axis=1)
        df['defensive_minus_cyclical_5d'] = defensive - cyclical

    if 'vix3m_close' in df.columns and 'vix_close' in df.columns:
        df['vix_vix3m_ratio'] = df['vix_close'] / df['vix3m_close']
    if 'vvix_close' in df.columns:
        df['vvix_5d_chg'] = df['vvix_close'].pct_change(5) * 100
    if '^MOVE' in df.columns:
        df['move_level'] = df['^MOVE']
    if 'crude_close' in df.columns:
        df['oil_20d_chg'] = df['crude_close'].pct_change(20) * 100
    if 'gold_close' in df.columns and 'spy_close' in df.columns:
        df['gold_spy_ratio'] = df['gold_close'] / df['spy_close']
    if 'IWM' in df.columns and 'spy_close' in df.columns:
        df['iwm_spy_ratio'] = df['IWM'] / df['spy_close']

    keep = ['date'] + V22_NEW_FEATURES
    keep = [c for c in keep if c in df.columns]
    return df[keep]


def get_base_features(df):
    drop = {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
            'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund',
            'market_cap', 'avg_volume', 'avg_dollar_vol'}
    return [c for c in df.columns
            if c not in drop and not c.startswith(('fhigh_', 'flow_', 'fclose_', 'L_'))
            and c not in V22_NEW_FEATURES  # exclude new feats from baseline
            and df[c].dtype != 'object']


def evaluate_picks(picks):
    if len(picks) < 3:
        return None
    fhigh = picks[f'fhigh_pct_{WINDOW}d'].values
    flow = picks[f'flow_pct_{WINDOW}d'].values
    fclose = picks[f'fclose_pct_{WINDOW}d'].values
    pnl = np.where(fhigh >= TP_PCT, TP_PCT, fclose)
    n = len(pnl)
    wins = (pnl > 0).sum()
    wr = wins / n
    avg = pnl.mean()
    std = pnl.std()
    worst = pnl.min()
    worst_dd = flow.min()
    sharpe = avg / std * np.sqrt(252 / WINDOW) if std > 0 else 0
    return {
        'n': n, 'wr': round(wr, 3), 'avg_pnl': round(avg, 3),
        'worst_pnl': round(worst, 2), 'worst_dd': round(worst_dd, 2),
        'sharpe': round(sharpe, 2),
    }


def main():
    print("== Phase Re-I: Comprehensive Ensemble Grid ==", flush=True)

    print("\nLoading data...", flush=True)
    df = pd.read_pickle(CACHE / 'phase2_features.pkl')
    con = sqlite3.connect(str(DB))
    funda = pd.read_sql("SELECT symbol, market_cap, avg_volume FROM stock_fundamentals", con)
    con.close()
    df = df.merge(funda, on='symbol', how='left')
    df['avg_dollar_vol'] = df['avg_volume'] * df['close']
    mask = (df['close'] >= 5.0) & (df['market_cap'] >= 1e9) & (df['avg_dollar_vol'] >= 10e6)
    df = df[mask].copy()
    print(f"  Filtered: {df.shape}", flush=True)

    # Build extended macro
    ext_df = build_extended_macro_features()
    df = df.merge(ext_df, on='date', how='left')

    # Label
    h = df[f'fhigh_pct_{WINDOW}d']
    l = df[f'flow_pct_{WINDOW}d']
    df['L_main'] = ((h >= TP_PCT) & (l >= DD_PCT)).astype(float)
    df.loc[h.isna() | l.isna(), 'L_main'] = np.nan
    df = df[df['L_main'].notna()]

    base_feats = get_base_features(df)
    v22_feats = base_feats + [f for f in V22_NEW_FEATURES if f in df.columns]
    v21_all_extended = [c for c in df.columns if c not in base_feats
                         and c not in {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
                                       'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund',
                                       'market_cap', 'avg_volume', 'avg_dollar_vol', 'L_main'}
                         and not c.startswith(('fhigh_', 'flow_', 'fclose_'))
                         and df[c].dtype != 'object']
    print(f"  Base v2.0 features: {len(base_feats)}", flush=True)
    print(f"  v2.2 features (base + selected 8): {len(v22_feats)}", flush=True)
    print(f"  v2.1 all features (incl all extended): {len(v21_all_extended)}", flush=True)

    all_results = []
    for name, train_end, test_start, test_end, is_crisis in PERIODS:
        print(f"\n--- {name} {'[CRISIS]' if is_crisis else '[NORMAL]'} ---", flush=True)
        train_cutoff = pd.Timestamp(train_end)
        test_mask = (df['date'] >= pd.Timestamp(test_start)) & (df['date'] <= pd.Timestamp(test_end))
        train_mask = df['date'] < train_cutoff
        if train_mask.sum() < 30000 or test_mask.sum() < 100:
            continue

        # === Train 3 models ===
        # v2.0: baseline 61 features, baseline HP
        X_train_v2 = df.loc[train_mask, base_feats].fillna(-999).values
        X_test_v2 = df.loc[test_mask, base_feats].fillna(-999).values
        y_train = df.loc[train_mask, 'L_main'].astype(int).values
        model_v20 = lgb.LGBMClassifier(**LGB_BASELINE, random_state=42)
        model_v20.fit(X_train_v2, y_train)
        prob_v20 = model_v20.predict_proba(X_test_v2)[:, 1]

        # v2.1: extended ~91 features, baseline HP
        X_train_v21 = df.loc[train_mask, v21_all_extended].fillna(-999).values
        X_test_v21 = df.loc[test_mask, v21_all_extended].fillna(-999).values
        model_v21 = lgb.LGBMClassifier(**LGB_BASELINE, random_state=42)
        model_v21.fit(X_train_v21, y_train)
        prob_v21 = model_v21.predict_proba(X_test_v21)[:, 1]

        # v2.2: selected 69 features, disciplined HP
        X_train_v22 = df.loc[train_mask, v22_feats].fillna(-999).values
        X_test_v22 = df.loc[test_mask, v22_feats].fillna(-999).values
        model_v22 = lgb.LGBMClassifier(**LGB_DISCIPLINED, random_state=42)
        model_v22.fit(X_train_v22, y_train)
        prob_v22 = model_v22.predict_proba(X_test_v22)[:, 1]

        test_df = df.loc[test_mask].copy()
        test_df['p20'] = prob_v20
        test_df['p21'] = prob_v21
        test_df['p22'] = prob_v22

        # === Test all combinations ===
        combos = {
            # Pure
            'v20_t0.80': test_df['p20'] >= 0.80,
            'v20_t0.85': test_df['p20'] >= 0.85,
            'v20_t0.90': test_df['p20'] >= 0.90,
            'v20_t0.95': test_df['p20'] >= 0.95,
            'v21_t0.80': test_df['p21'] >= 0.80,
            'v21_t0.85': test_df['p21'] >= 0.85,
            'v21_t0.90': test_df['p21'] >= 0.90,
            'v22_t0.80': test_df['p22'] >= 0.80,
            'v22_t0.85': test_df['p22'] >= 0.85,
            'v22_t0.90': test_df['p22'] >= 0.90,
            # Weighted average
            'avg73_t0.80': (0.7*test_df['p20'] + 0.3*test_df['p21']) >= 0.80,
            'avg73_t0.85': (0.7*test_df['p20'] + 0.3*test_df['p21']) >= 0.85,
            'avg55_t0.80': (0.5*test_df['p20'] + 0.5*test_df['p21']) >= 0.80,
            'avg55_t0.85': (0.5*test_df['p20'] + 0.5*test_df['p21']) >= 0.85,
            'avg_3way_0.80': ((test_df['p20']+test_df['p21']+test_df['p22'])/3) >= 0.80,
            'avg_3way_0.85': ((test_df['p20']+test_df['p21']+test_df['p22'])/3) >= 0.85,
            # Strict AND (highest quality)
            'AND_2085_2175': (test_df['p20'] >= 0.85) & (test_df['p21'] >= 0.75),
            'AND_2085_2185': (test_df['p20'] >= 0.85) & (test_df['p21'] >= 0.85),
            'AND_2090_2180': (test_df['p20'] >= 0.90) & (test_df['p21'] >= 0.80),
            'AND_3way_85': (test_df['p20'] >= 0.85) & (test_df['p21'] >= 0.85) & (test_df['p22'] >= 0.85),
            'AND_3way_75': (test_df['p20'] >= 0.75) & (test_df['p21'] >= 0.75) & (test_df['p22'] >= 0.75),
            # Majority voting
            'maj_at075': ((test_df['p20']>=0.75).astype(int) + (test_df['p21']>=0.75).astype(int) + (test_df['p22']>=0.75).astype(int)) >= 2,
            'maj_at085': ((test_df['p20']>=0.85).astype(int) + (test_df['p21']>=0.85).astype(int) + (test_df['p22']>=0.85).astype(int)) >= 2,
        }

        for combo_name, mask_c in combos.items():
            sub = test_df[mask_c]
            m = evaluate_picks(sub)
            if m is None:
                continue
            m.update({
                'period': name, 'is_crisis': is_crisis,
                'combo': combo_name,
            })
            all_results.append(m)
            crisis_flag = '🔴' if is_crisis else '🟢'
            print(f"  {crisis_flag} {combo_name:20s} N={m['n']:4d} WR={m['wr']*100:.0f}% EV={m['avg_pnl']:+.2f}% worst={m['worst_pnl']:+.2f}% Sharpe={m['sharpe']:.2f}", flush=True)

    rdf = pd.DataFrame(all_results)
    rdf.to_csv(RESULTS / 'phaseRE_ensemble_grid.csv', index=False)

    # === Aggregate analysis ===
    print(f"\n{'='*80}", flush=True)
    print("CRISIS-AVG vs NORMAL — Quality Ranking", flush=True)
    print('='*80, flush=True)

    summary = rdf.groupby(['combo', 'is_crisis']).agg(
        n=('n', 'sum'),
        wr=('wr', 'mean'),
        avg_pnl=('avg_pnl', 'mean'),
        worst_pnl=('worst_pnl', 'min'),  # min = worst trade across periods
        sharpe=('sharpe', 'mean'),
    ).round(3).reset_index()

    pivot = summary.pivot(index='combo', columns='is_crisis',
                           values=['n', 'wr', 'avg_pnl', 'worst_pnl', 'sharpe'])
    pivot.columns = [f'{m}_{"crisis" if c else "normal"}' for m, c in pivot.columns]

    # Quality score: avg(WR) × avg(EV) / (1 + |worst|)
    # higher = better
    pivot['crisis_quality'] = (pivot['wr_crisis'] * pivot['avg_pnl_crisis'] /
                                (1 + pivot['worst_pnl_crisis'].abs()))
    pivot['normal_quality'] = (pivot['wr_normal'] * pivot['avg_pnl_normal'] /
                                (1 + pivot['worst_pnl_normal'].abs()))
    pivot['overall_quality'] = (pivot['crisis_quality'] + pivot['normal_quality']) / 2

    pivot = pivot.sort_values('overall_quality', ascending=False)

    print(f"\n📊 TOP 15 BY OVERALL QUALITY:", flush=True)
    cols_show = ['n_crisis', 'wr_crisis', 'worst_pnl_crisis',
                  'n_normal', 'wr_normal', 'worst_pnl_normal',
                  'overall_quality']
    print(pivot[cols_show].head(15).round(3).to_string(), flush=True)

    # Strict criteria: worst >= -5 in both regimes, positive EV
    print(f"\n⭐ STRICT QUALITY FILTER (worst_pnl >= -5 in both regimes):", flush=True)
    strict = pivot[(pivot['worst_pnl_crisis'] >= -5) & (pivot['worst_pnl_normal'] >= -5)]
    strict = strict.sort_values('overall_quality', ascending=False)
    if len(strict) > 0:
        print(strict[cols_show].head(10).to_string(), flush=True)
    else:
        print("  (None pass strict criteria)", flush=True)

    print(f"\n⭐⭐ ULTRA STRICT (worst_pnl >= -7, WR >= 0.75 in both):", flush=True)
    ultra = pivot[(pivot['worst_pnl_crisis'] >= -7) & (pivot['worst_pnl_normal'] >= -7) &
                   (pivot['wr_crisis'] >= 0.75) & (pivot['wr_normal'] >= 0.75)]
    if len(ultra) > 0:
        print(ultra[cols_show].head(10).to_string(), flush=True)
    else:
        print("  (None pass ultra strict)", flush=True)

    pivot.to_csv(RESULTS / 'phaseRE_ensemble_quality_ranked.csv')


if __name__ == '__main__':
    main()
