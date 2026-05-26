"""
Phase Re-G: Make swing model SMARTER (no external rules).

Two approaches tested:
  A) Higher threshold (0.85 / 0.90) — filter signals harder
  B) Class-weighted training — penalize crisis-period false positives

Test on war periods + normal Phase 5 OOS to ensure no regression.
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

BASE_LGB = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 31, 'max_depth': 5, 'min_child_samples': 30,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 1.0, 'reg_lambda': 1.0,
    'n_estimators': 300, 'n_jobs': 4, 'verbose': -1,
}

TP_PCT = 2.0
DD_PCT = -3.0
WINDOW = 7

TEST_PERIODS = [
    # Normal — baseline
    {'name': 'Normal-2026-Mar-May', 'train_end': '2026-03-01', 'test_start': '2026-03-01', 'test_end': '2026-05-15', 'is_crisis': False},
    # War periods
    {'name': 'Russia-Ukraine-2022',  'train_end': '2022-01-15', 'test_start': '2022-02-15', 'test_end': '2022-04-30', 'is_crisis': True},
    {'name': 'Rate-Hike-2022',        'train_end': '2022-05-01', 'test_start': '2022-05-15', 'test_end': '2022-07-31', 'is_crisis': True},
    {'name': 'Israel-Hamas-2023',    'train_end': '2023-09-15', 'test_start': '2023-10-07', 'test_end': '2023-12-15', 'is_crisis': True},
    {'name': 'Iran-Israel-Apr-2024', 'train_end': '2024-03-15', 'test_start': '2024-04-01', 'test_end': '2024-05-31', 'is_crisis': True},
    {'name': 'Iran-Israel-Oct-2024', 'train_end': '2024-09-15', 'test_start': '2024-10-01', 'test_end': '2024-11-30', 'is_crisis': True},
]

# Approach A: thresholds to test
THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]

# Approach B: class weighting (higher weight = more penalty for false positives in that group)
# Weight rule: if VIX > 25 (crisis-ish), weight = 3
CRISIS_VIX_THRESHOLD = 25
CRISIS_WEIGHT = 3.0


def get_feature_cols(df):
    drop = {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
            'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund',
            'market_cap', 'avg_volume', 'avg_dollar_vol'}
    return [c for c in df.columns
            if c not in drop and not c.startswith(('fhigh_', 'flow_', 'fclose_', 'L_'))
            and df[c].dtype != 'object']


def evaluate_picks(picks, tp, w):
    if len(picks) == 0:
        return None
    fhigh = picks[f'fhigh_pct_{w}d'].values
    flow = picks[f'flow_pct_{w}d'].values
    fclose = picks[f'fclose_pct_{w}d'].values
    pnl = np.where(fhigh >= tp, tp, fclose)
    wins = (pnl > 0).sum()
    return {
        'n': len(picks),
        'wr': round(wins / len(picks), 3),
        'avg_pnl': round(pnl.mean(), 3),
        'worst_pnl': round(pnl.min(), 2),
        'worst_dd': round(flow.min(), 2),
        'pct_safe_5': round((flow > -5).mean(), 3),
    }


def train_predict(df_train, df_test, feature_cols, label_col, use_class_weight=False):
    X_train = df_train[feature_cols].fillna(-999).values
    y_train = df_train[label_col].astype(int).values
    X_test = df_test[feature_cols].fillna(-999).values

    if use_class_weight:
        # Crisis-period sample weighting: weight up high-VIX samples
        weights = np.ones(len(df_train))
        if 'vix_x' in df_train.columns:
            vix = df_train['vix_x'].fillna(20).values
            weights = np.where(vix >= CRISIS_VIX_THRESHOLD, CRISIS_WEIGHT, 1.0)
        model = lgb.LGBMClassifier(**BASE_LGB, random_state=42)
        model.fit(X_train, y_train, sample_weight=weights)
    else:
        model = lgb.LGBMClassifier(**BASE_LGB, random_state=42)
        model.fit(X_train, y_train)

    return model.predict_proba(X_test)[:, 1]


def main():
    print("== Phase Re-G: Make Model Smarter (No External Rules) ==", flush=True)

    print("\nLoading + filtering universe...", flush=True)
    df = pd.read_pickle(CACHE / 'phase2_features.pkl')
    con = sqlite3.connect(str(DB))
    funda = pd.read_sql("SELECT symbol, market_cap, avg_volume FROM stock_fundamentals", con)
    con.close()
    df = df.merge(funda, on='symbol', how='left')
    df['avg_dollar_vol'] = df['avg_volume'] * df['close']
    mask = (
        (df['close'] >= 5.0) &
        (df['market_cap'] >= 1e9) &
        (df['avg_dollar_vol'] >= 10e6)
    )
    df = df[mask].copy()

    # Build label
    h = df[f'fhigh_pct_{WINDOW}d']
    l = df[f'flow_pct_{WINDOW}d']
    df['L_main'] = ((h >= TP_PCT) & (l >= DD_PCT)).astype(float)
    df.loc[h.isna() | l.isna(), 'L_main'] = np.nan
    df = df[df['L_main'].notna()]
    feature_cols = get_feature_cols(df)
    print(f"  Filtered: {df.shape}, features: {len(feature_cols)}", flush=True)

    all_results = []

    for period in TEST_PERIODS:
        print(f"\n{'='*70}", flush=True)
        print(f"{period['name']} {'[CRISIS]' if period['is_crisis'] else '[NORMAL]'}", flush=True)
        print(f"  Train ≤ {period['train_end']} | Test {period['test_start']} → {period['test_end']}", flush=True)
        print('='*70, flush=True)

        train_cutoff = pd.Timestamp(period['train_end'])
        test_start = pd.Timestamp(period['test_start'])
        test_end = pd.Timestamp(period['test_end'])

        train_mask = df['date'] < train_cutoff
        test_mask = (df['date'] >= test_start) & (df['date'] <= test_end)
        df_train = df[train_mask].copy()
        df_test = df[test_mask].copy()

        if len(df_train) < 30000 or len(df_test) < 100:
            print(f"  ❌ insufficient data", flush=True)
            continue

        # === APPROACH A: vary threshold (regular training) ===
        print(f"  Approach A: vary threshold (regular model)", flush=True)
        prob_a = train_predict(df_train, df_test, feature_cols, 'L_main', use_class_weight=False)
        df_test_a = df_test.copy()
        df_test_a['prob'] = prob_a

        for thr in THRESHOLDS:
            picks = df_test_a[df_test_a['prob'] >= thr]
            r = evaluate_picks(picks, TP_PCT, WINDOW)
            if r is None:
                continue
            row = {
                'period': period['name'], 'is_crisis': period['is_crisis'],
                'approach': 'A_thr', 'thr': thr, 'class_weight': False,
                **r,
            }
            all_results.append(row)
            print(f"    thr={thr}: N={r['n']:5d} WR={r['wr']*100:.1f}% EV={r['avg_pnl']:+.2f}% worst={r['worst_pnl']:+.2f}% safe5={r['pct_safe_5']*100:.0f}%", flush=True)

        # === APPROACH B: class-weighted (penalize crisis losses) ===
        print(f"  Approach B: class-weighted training (VIX>{CRISIS_VIX_THRESHOLD} weight {CRISIS_WEIGHT}x)", flush=True)
        prob_b = train_predict(df_train, df_test, feature_cols, 'L_main', use_class_weight=True)
        df_test_b = df_test.copy()
        df_test_b['prob'] = prob_b

        for thr in [0.75, 0.85]:
            picks = df_test_b[df_test_b['prob'] >= thr]
            r = evaluate_picks(picks, TP_PCT, WINDOW)
            if r is None:
                continue
            row = {
                'period': period['name'], 'is_crisis': period['is_crisis'],
                'approach': 'B_cw', 'thr': thr, 'class_weight': True,
                **r,
            }
            all_results.append(row)
            print(f"    thr={thr}: N={r['n']:5d} WR={r['wr']*100:.1f}% EV={r['avg_pnl']:+.2f}% worst={r['worst_pnl']:+.2f}% safe5={r['pct_safe_5']*100:.0f}%", flush=True)

    if all_results:
        rdf = pd.DataFrame(all_results)
        rdf.to_csv(RESULTS / 'phaseRE_smarter.csv', index=False)

        # Summary: average across crisis periods only
        print(f"\n{'='*70}", flush=True)
        print(f"AVERAGE ACROSS CRISIS PERIODS ONLY", flush=True)
        print('='*70, flush=True)
        crisis = rdf[rdf['is_crisis']]
        summary = crisis.groupby(['approach', 'thr']).agg(
            avg_wr=('wr', 'mean'),
            avg_ev=('avg_pnl', 'mean'),
            worst_pnl_overall=('worst_pnl', 'min'),
            avg_safe5=('pct_safe_5', 'mean'),
            total_n=('n', 'sum'),
        ).round(3)
        print(summary.to_string(), flush=True)

        # Normal period comparison
        print(f"\n== NORMAL PERIOD (Mar-May 2026) ==", flush=True)
        normal = rdf[~rdf['is_crisis']]
        normal_summary = normal.groupby(['approach', 'thr']).agg(
            n=('n', 'sum'),
            wr=('wr', 'first'),
            avg_pnl=('avg_pnl', 'first'),
            worst=('worst_pnl', 'first'),
        ).round(3)
        print(normal_summary.to_string(), flush=True)


if __name__ == '__main__':
    main()
