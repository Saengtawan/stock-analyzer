"""
Phase 5b-3: Crisis Regime Test.

F2 in Phase 5 found NO Crisis VIX days (>30) in test period 2025-09 to 2026-02.
Critical to verify swing_filter works in real crisis periods.

Crisis periods in our data:
  - 2020-02-24 to 2020-04-30 (COVID crash, peak VIX 82)
  - 2022-01-01 to 2022-06-30 (rate hike + tech crash, VIX 30-38)
  - 2022-09-01 to 2022-10-31 (Fed hawkish, VIX 30-35)

Strategy:
  - Train model on data BEFORE crisis period
  - Test in crisis period (out-of-sample)
  - Apply config: L_touch_5_in_30d @ 0.90, TP=5%, no SL, 30d
  - Measure WR + EV

Pass criteria: WR ≥ 70%, EV ≥ +1% in each crisis period.
"""
import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')

LGB_PARAMS = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 31, 'max_depth': 5, 'min_child_samples': 30,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 1.0, 'reg_lambda': 1.0,
    'n_estimators': 300, 'n_jobs': 4, 'verbose': -1,
}

LABEL = 'L_touch_5_in_30d'
THRESHOLD = 0.90
WINDOW = 30
TP = 5.0


def get_feature_cols(df):
    drop = {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
            'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund'}
    return [c for c in df.columns
            if c not in drop and not c.startswith(('fhigh_', 'flow_', 'fclose_', 'L_'))
            and df[c].dtype != 'object']


def compute_pnl(picks, tp, window):
    """Forward array exit simulation."""
    fhigh = picks[f'fhigh_pct_{window}d'].values
    flow = picks[f'flow_pct_{window}d'].values
    fclose = picks[f'fclose_pct_{window}d'].values
    valid = ~np.isnan(fhigh)
    pnl = np.where(valid & (fhigh >= tp), tp,
            np.where(valid, fclose, np.nan))
    return pnl[valid]


def test_crisis(df, feature_cols, train_end_str, test_start_str, test_end_str, name):
    """Train on data before train_end, test on [test_start, test_end]."""
    print(f"\n=== Crisis: {name} ===", flush=True)
    print(f"  Train: ≤ {train_end_str}, Test: {test_start_str} to {test_end_str}", flush=True)

    df_l = df[df[LABEL].notna()].copy()
    train_cutoff = pd.Timestamp(train_end_str)
    test_start = pd.Timestamp(test_start_str)
    test_end = pd.Timestamp(test_end_str)

    train_mask = df_l['date'] < train_cutoff
    test_mask = (df_l['date'] >= test_start) & (df_l['date'] <= test_end)

    if train_mask.sum() < 50000 or test_mask.sum() < 100:
        print(f"  ❌ insufficient data: train {train_mask.sum()}, test {test_mask.sum()}", flush=True)
        return None

    print(f"  Train: {train_mask.sum():,}, Test: {test_mask.sum():,}", flush=True)

    X_train = df_l.loc[train_mask, feature_cols].fillna(-999).values
    y_train = df_l.loc[train_mask, LABEL].astype(int).values
    X_test = df_l.loc[test_mask, feature_cols].fillna(-999).values

    print(f"  Training LightGBM...", flush=True)
    model = lgb.LGBMClassifier(**LGB_PARAMS, random_state=42)
    model.fit(X_train, y_train)

    prob = model.predict_proba(X_test)[:, 1]
    sub = df_l.loc[test_mask].copy()
    sub['prob'] = prob

    picks = sub[sub['prob'] >= THRESHOLD]
    if len(picks) == 0:
        print(f"  ❌ no picks above threshold {THRESHOLD}", flush=True)
        return None

    pnl = compute_pnl(picks, TP, WINDOW)
    if len(pnl) == 0:
        print(f"  ❌ no valid PnL", flush=True)
        return None

    wr = (pnl > 0).mean()
    avg = pnl.mean()
    std = pnl.std()
    sharpe = avg / std * np.sqrt(252 / WINDOW) if std > 0 else 0
    n = len(picks)

    # Per-zone VIX breakdown
    if 'vix_regime' in sub.columns:
        picks_vix = picks.copy()
        picks_vix['pnl'] = pnl
        vix_dist = picks_vix.groupby('vix_regime').size().sort_values(ascending=False)
        print(f"  VIX regime in picks: {dict(vix_dist)}", flush=True)

    print(f"  Results:", flush=True)
    print(f"    N picks: {n}", flush=True)
    print(f"    WR: {wr:.3f}", flush=True)
    print(f"    Avg PnL: {avg:+.2f}%", flush=True)
    print(f"    Sharpe: {sharpe:.2f}", flush=True)

    passed = wr >= 0.70 and avg >= 1.0
    print(f"  Verdict: {'✅ PASS' if passed else '❌ FAIL'} (need WR≥70%, EV≥+1%)", flush=True)
    return {
        'name': name, 'train_end': train_end_str,
        'test_period': f"{test_start_str} to {test_end_str}",
        'n': n, 'wr': round(wr, 3), 'avg_pnl': round(avg, 3),
        'sharpe': round(sharpe, 2),
        'status': 'PASS' if passed else 'FAIL',
    }


def main():
    print("== Phase 5b-3: Crisis Regime Test ==", flush=True)

    print("\nLoading features...", flush=True)
    df = pd.read_pickle(CACHE / 'phase2_features.pkl')
    feature_cols = get_feature_cols(df)
    print(f"  shape: {df.shape}, features: {len(feature_cols)}", flush=True)

    # Crisis periods to test
    crisis_tests = [
        # COVID crash (peak VIX 82)
        {
            'name': 'COVID-2020',
            'train_end': '2020-02-01',  # train ends BEFORE COVID
            'test_start': '2020-03-01',
            'test_end': '2020-05-31',
        },
        # 2022 H1 — rate hike + tech crash
        {
            'name': '2022-H1-RateHike',
            'train_end': '2021-12-01',
            'test_start': '2022-01-01',
            'test_end': '2022-06-30',
        },
        # 2022 Sep-Oct (Fed hawkish)
        {
            'name': '2022-Q3-Hawkish',
            'train_end': '2022-08-01',
            'test_start': '2022-09-01',
            'test_end': '2022-10-31',
        },
    ]

    results = []
    for c in crisis_tests:
        r = test_crisis(df, feature_cols, c['train_end'], c['test_start'], c['test_end'], c['name'])
        if r:
            results.append(r)

    if results:
        rdf = pd.DataFrame(results)
        rdf.to_csv(RESULTS / 'phase5b_crisis.csv', index=False)
        print("\n== Crisis Regime Summary ==", flush=True)
        print(rdf.to_string(index=False), flush=True)

        n_pass = (rdf['status'] == 'PASS').sum()
        print(f"\n  Overall: {n_pass}/{len(rdf)} crisis periods passed", flush=True)
        if n_pass == len(rdf):
            print(f"  ✅ ALL CRISIS PERIODS PASS", flush=True)
        elif n_pass >= len(rdf) - 1:
            print(f"  ⚠️ Mostly pass — review borderline", flush=True)
        else:
            print(f"  ❌ FAIL — Crisis robustness not confirmed", flush=True)


if __name__ == '__main__':
    main()
