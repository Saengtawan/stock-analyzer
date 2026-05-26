"""
Phase 5 — Validation Funnel for top swing candidates.

Tests top 3 candidates (label, threshold, TP, SL) through 4 phases:
  F1: Walk-forward monthly refit (6 months OOS)
  F2: Cross-regime (VIX-based)
  F3: TRUE OOS (last 60-90 days)
  F4: Smoke tests

Must pass all phases. Output: phase5_funnel.csv + funnel_report.md
"""
import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path
from datetime import datetime
from sklearn.metrics import roc_auc_score
import warnings
warnings.filterwarnings('ignore')

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')
MODELS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/models_swing')

LGB_PARAMS = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 31, 'max_depth': 5, 'min_child_samples': 30,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 1.0, 'reg_lambda': 1.0,
    'n_estimators': 300, 'n_jobs': 4, 'verbose': -1,
}

# Top 3 candidates from Phase 4 — diverse: WR-max, Sharpe-max, more-trades
CANDIDATES = [
    # Top by deterministic Sharpe (no SL — single number)
    {'label': 'L_touch_3_in_5d', 'window': 5, 'threshold': 0.90,
     'tp': 5.0, 'sl': None, 'name': 'C1_winner_run'},
    # Best Sharpe with SL protection
    {'label': 'L_touch_3_in_5d', 'window': 5, 'threshold': 0.90,
     'tp': 5.0, 'sl': -2.0, 'name': 'C2_sl_protected'},
    # More trades (7d window)
    {'label': 'L_touch_3_in_7d', 'window': 7, 'threshold': 0.90,
     'tp': 5.0, 'sl': -2.0, 'name': 'C3_more_trades'},
    # WR-max (label TP only)
    {'label': 'L_touch_3_in_5d', 'window': 5, 'threshold': 0.90,
     'tp': 3.0, 'sl': None, 'name': 'C4_wr_max'},
    # Original ask (5% / 30d)
    {'label': 'L_touch_5_in_30d', 'window': 30, 'threshold': 0.90,
     'tp': 5.0, 'sl': None, 'name': 'C5_30d_5pct'},
]


def get_feature_cols(df):
    drop = {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
            'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund'}
    return [c for c in df.columns
            if c not in drop and not c.startswith(('fhigh_', 'flow_', 'fclose_', 'L_'))
            and df[c].dtype != 'object']


def compute_pnl_vectorized(preds_df, cand, mode='mid'):
    """Compute P&L per pick using forward arrays.
    mode: 'cons' (worst path), 'opt' (best path), 'mid' (average), 'tp_only' (no SL deterministic)
    """
    w = cand['window']
    tp = cand['tp']
    sl = cand['sl']
    fhigh = preds_df[f'fhigh_pct_{w}d'].values
    flow = preds_df[f'flow_pct_{w}d'].values
    fclose = preds_df[f'fclose_pct_{w}d'].values
    valid = ~np.isnan(fhigh)

    if sl is None:
        # Deterministic: if hit TP → TP, else fclose
        return np.where(valid & (fhigh >= tp), tp,
                np.where(valid, fclose, np.nan))

    if mode == 'cons':
        # Worst: SL hit first if both touch
        return np.where(~valid, np.nan,
                np.where(flow <= sl, sl,
                  np.where(fhigh >= tp, tp, fclose)))
    elif mode == 'opt':
        # Best: TP hit first if both touch
        return np.where(~valid, np.nan,
                np.where(fhigh >= tp, tp,
                  np.where(flow <= sl, sl, fclose)))
    else:
        # Mid
        c = compute_pnl_vectorized(preds_df, cand, 'cons')
        o = compute_pnl_vectorized(preds_df, cand, 'opt')
        return (c + o) / 2


def funnel_F1(df, cand, feature_cols, test_start='2025-09-01', test_end='2026-02-28'):
    """Walk-forward monthly refit."""
    label = cand['label']
    thr = cand['threshold']
    w = cand['window']
    df_l = df[df[label].notna()].copy()
    df_l = df_l.sort_values(['date', 'symbol']).reset_index(drop=True)

    test_months = pd.period_range(test_start, test_end, freq='M')
    all_preds = []
    for tm in test_months:
        tm_start = tm.start_time
        tm_end = tm.end_time
        train_cutoff = tm_start - pd.Timedelta(days=w + 5)
        train_mask = df_l['date'] < train_cutoff
        test_mask = (df_l['date'] >= tm_start) & (df_l['date'] <= tm_end)
        if train_mask.sum() < 50000 or test_mask.sum() < 100:
            continue
        X_train = df_l.loc[train_mask, feature_cols].fillna(-999).values
        y_train = df_l.loc[train_mask, label].astype(int).values
        X_test = df_l.loc[test_mask, feature_cols].fillna(-999).values
        model = lgb.LGBMClassifier(**LGB_PARAMS, random_state=42)
        model.fit(X_train, y_train)
        prob = model.predict_proba(X_test)[:, 1]
        sub = df_l.loc[test_mask, ['symbol', 'date',
                                    f'fhigh_pct_{w}d', f'flow_pct_{w}d',
                                    f'fclose_pct_{w}d', 'vix_regime']].copy()
        sub['prob'] = prob
        all_preds.append(sub)

    if not all_preds:
        return None
    preds = pd.concat(all_preds, ignore_index=True)
    picks = preds[preds['prob'] >= thr].copy()
    if len(picks) == 0:
        return None
    picks['pnl_mid'] = compute_pnl_vectorized(picks, cand, 'mid')
    picks['pnl_cons'] = compute_pnl_vectorized(picks, cand, 'cons')
    picks['pnl_opt'] = compute_pnl_vectorized(picks, cand, 'opt')

    pnl = picks['pnl_mid'].dropna()
    wr = (pnl > 0).mean()
    avg = pnl.mean()
    sharpe = avg / pnl.std() * np.sqrt(252 / w) if pnl.std() > 0 else 0

    passed = wr >= 0.80 and avg >= 0.5 and sharpe >= 1.5
    return {
        'wr': round(wr, 3), 'avg_pnl_mid': round(avg, 3),
        'avg_pnl_cons': round(picks['pnl_cons'].dropna().mean(), 3),
        'avg_pnl_opt': round(picks['pnl_opt'].dropna().mean(), 3),
        'sharpe': round(sharpe, 2), 'n': len(picks),
        'status': 'PASS' if passed else 'FAIL',
        '_picks': picks,
    }


def funnel_F2(picks_df, cand):
    """Cross-regime."""
    regimes = ['Calm', 'Normal', 'Elevated', 'Stress', 'Crisis']
    rows = []
    critical_pass = True
    for reg in regimes:
        sub = picks_df[picks_df['vix_regime'] == reg]
        if len(sub) == 0:
            rows.append({'regime': reg, 'wr': None, 'avg_pnl': None, 'n': 0})
            continue
        pnl = sub['pnl_mid'].dropna()
        wr = (pnl > 0).mean()
        avg = pnl.mean()
        rows.append({'regime': reg, 'wr': round(wr, 3),
                     'avg_pnl': round(avg, 3), 'n': len(sub)})
        if reg == 'Crisis' and (wr < 0.70 or pd.isna(wr)):
            critical_pass = False
    n_positive = sum(1 for r in rows if r['avg_pnl'] is not None and r['avg_pnl'] > 0)
    passed = n_positive >= 4 and critical_pass
    return {'regimes': rows, 'n_positive': n_positive,
            'critical_pass': critical_pass,
            'status': 'PASS' if passed else 'FAIL'}


def funnel_F3(df, cand, feature_cols, holdout_start='2026-03-01', holdout_end='2026-05-15'):
    """TRUE OOS — train on all data before holdout, predict on holdout."""
    label = cand['label']
    thr = cand['threshold']
    w = cand['window']
    df_l = df[df[label].notna()].copy()
    train_cutoff = pd.Timestamp(holdout_start) - pd.Timedelta(days=w + 5)
    train_mask = df_l['date'] < train_cutoff
    test_mask = (df_l['date'] >= pd.Timestamp(holdout_start)) & (df_l['date'] <= pd.Timestamp(holdout_end))
    if train_mask.sum() < 50000 or test_mask.sum() < 50:
        return None
    X_train = df_l.loc[train_mask, feature_cols].fillna(-999).values
    y_train = df_l.loc[train_mask, label].astype(int).values
    X_test = df_l.loc[test_mask, feature_cols].fillna(-999).values

    model = lgb.LGBMClassifier(**LGB_PARAMS, random_state=42)
    model.fit(X_train, y_train)
    prob = model.predict_proba(X_test)[:, 1]
    sub = df_l.loc[test_mask, ['symbol', 'date',
                                f'fhigh_pct_{w}d', f'flow_pct_{w}d',
                                f'fclose_pct_{w}d']].copy()
    sub['prob'] = prob
    picks = sub[sub['prob'] >= thr].copy()
    if len(picks) == 0:
        return None
    picks['pnl_mid'] = compute_pnl_vectorized(picks, cand, 'mid')
    pnl = picks['pnl_mid'].dropna()
    wr = (pnl > 0).mean()
    avg = pnl.mean()
    passed = wr >= 0.75 and avg >= 0.3
    return {'wr': round(wr, 3), 'avg_pnl': round(avg, 3),
            'n': len(picks), 'status': 'PASS' if passed else 'FAIL'}


def funnel_F4(df, cand, feature_cols, f1_result):
    """Smoke tests."""
    checks = []
    label = cand['label']

    # 1. Label binary
    vals = set(df[label].dropna().unique())
    checks.append({'check': 'label_binary', 'pass': vals.issubset({0, 1, 0.0, 1.0})})

    # 2. No forward leakage in feature_cols
    has_fwd = any(f.startswith(('fhigh_', 'flow_', 'fclose_')) for f in feature_cols)
    checks.append({'check': 'no_forward_features', 'pass': not has_fwd})

    # 3. Training data size
    n = len(df[df[label].notna()])
    checks.append({'check': 'training_data', 'pass': n >= 100000, 'value': n})

    # 4. Predictions have variation (not all same)
    if '_picks' in f1_result:
        prob_std = f1_result['_picks']['prob'].std()
        checks.append({'check': 'prob_variation', 'pass': prob_std > 0.05, 'value': round(prob_std, 3)})
    else:
        checks.append({'check': 'prob_variation', 'pass': False})

    # 5. WR consistent across years (compute mini per-year WR)
    if '_picks' in f1_result:
        picks = f1_result['_picks']
        picks['year'] = picks['date'].dt.year
        wr_per_year = picks.groupby('year').apply(lambda g: (g['pnl_mid'] > 0).mean())
        wr_std = wr_per_year.std()
        checks.append({'check': 'wr_stable_per_year', 'pass': wr_std < 0.15, 'value': round(wr_std, 3) if not pd.isna(wr_std) else None})
    else:
        checks.append({'check': 'wr_stable_per_year', 'pass': True})

    # 6. Sufficient unique picks (not just same symbols repeating)
    if '_picks' in f1_result:
        n_syms = f1_result['_picks']['symbol'].nunique()
        checks.append({'check': 'symbol_diversity', 'pass': n_syms >= 20, 'value': n_syms})
    else:
        checks.append({'check': 'symbol_diversity', 'pass': True})

    # 7. No NaN in critical features
    crit = ['close', 'rsi_14', 'dist_ma20', 'vol_ratio_20']
    crit = [c for c in crit if c in df.columns]
    if crit:
        nan_pct = df[crit].isna().mean().max()
        checks.append({'check': 'features_clean', 'pass': nan_pct < 0.3, 'value': round(nan_pct, 3)})
    else:
        checks.append({'check': 'features_clean', 'pass': True})

    n_pass = sum(1 for c in checks if c['pass'])
    return {'checks': checks, 'n_pass': n_pass, 'n_total': len(checks),
            'status': 'PASS' if n_pass == len(checks) else 'FAIL'}


def run_full_funnel(df, cand, feature_cols):
    print(f"\n{'='*70}", flush=True)
    print(f"FUNNEL: {cand['name']}", flush=True)
    print(f"  Label: {cand['label']} @ thr={cand['threshold']}", flush=True)
    print(f"  Exit: TP={cand['tp']}% / SL={cand['sl']} / window={cand['window']}d", flush=True)
    print('='*70, flush=True)

    # F1
    print("\n→ F1: Walk-forward monthly refit (6mo OOS) ...", flush=True)
    f1 = funnel_F1(df, cand, feature_cols)
    if f1 is None:
        print("  ❌ no_data", flush=True)
        return {'overall': 'FAIL', 'F1': None}
    print(f"  WR {f1['wr']} / EV_mid {f1['avg_pnl_mid']}% / Sharpe {f1['sharpe']} / N {f1['n']} → {f1['status']}", flush=True)
    print(f"  Range: cons EV {f1['avg_pnl_cons']}% ↔ opt EV {f1['avg_pnl_opt']}%", flush=True)

    # F2
    print("\n→ F2: Cross-regime ...", flush=True)
    f2 = funnel_F2(f1['_picks'], cand)
    for r in f2['regimes']:
        print(f"  {r['regime']:10s}: WR {r['wr']} / EV {r['avg_pnl']} / N {r['n']}", flush=True)
    print(f"  {f2['n_positive']}/5 regimes positive | Crisis critical: {f2['critical_pass']} → {f2['status']}", flush=True)

    # F3
    print("\n→ F3: TRUE OOS (last 75 days) ...", flush=True)
    f3 = funnel_F3(df, cand, feature_cols)
    if f3:
        print(f"  WR {f3['wr']} / EV {f3['avg_pnl']}% / N {f3['n']} → {f3['status']}", flush=True)
    else:
        print("  ⚠️ insufficient data", flush=True)

    # F4
    print("\n→ F4: Smoke tests ...", flush=True)
    f4 = funnel_F4(df, cand, feature_cols, f1)
    for c in f4['checks']:
        v = f' (={c.get("value", "")})' if 'value' in c else ''
        print(f"  {'✓' if c['pass'] else '✗'} {c['check']}{v}", flush=True)
    print(f"  {f4['n_pass']}/{f4['n_total']} pass → {f4['status']}", flush=True)

    overall = 'PASS' if (f1['status'] == 'PASS' and f2['status'] == 'PASS'
                          and (f3 is not None and f3['status'] == 'PASS')
                          and f4['status'] == 'PASS') else 'FAIL'
    print(f"\n{'='*70}", flush=True)
    print(f"OVERALL: {overall}", flush=True)
    print('='*70, flush=True)
    return {'overall': overall, 'F1': f1, 'F2': f2, 'F3': f3, 'F4': f4}


def main():
    print("== Phase 5: Validation Funnel ==", flush=True)
    start = datetime.now()

    print("Loading Phase 2 features...", flush=True)
    df = pd.read_pickle(CACHE / 'phase2_features.pkl')
    feature_cols = get_feature_cols(df)
    print(f"  shape: {df.shape}, features: {len(feature_cols)}", flush=True)

    all_results = []
    for cand in CANDIDATES:
        result = run_full_funnel(df, cand, feature_cols)
        all_results.append({
            'name': cand['name'],
            'label': cand['label'],
            'threshold': cand['threshold'],
            'tp': cand['tp'],
            'sl': cand['sl'],
            'overall': result['overall'],
            'f1_wr': result.get('F1', {}).get('wr') if result.get('F1') else None,
            'f1_ev_mid': result.get('F1', {}).get('avg_pnl_mid') if result.get('F1') else None,
            'f1_sharpe': result.get('F1', {}).get('sharpe') if result.get('F1') else None,
            'f1_n': result.get('F1', {}).get('n') if result.get('F1') else None,
            'f2_positive': result.get('F2', {}).get('n_positive') if result.get('F2') else None,
            'f3_wr': result.get('F3', {}).get('wr') if result.get('F3') else None,
            'f3_ev': result.get('F3', {}).get('avg_pnl') if result.get('F3') else None,
            'f4_pass': result.get('F4', {}).get('n_pass') if result.get('F4') else None,
        })

    final = pd.DataFrame(all_results)
    final.to_csv(RESULTS / 'phase5_funnel.csv', index=False)
    print("\n== Funnel Summary ==", flush=True)
    print(final.to_string(index=False), flush=True)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Phase 5 done in {elapsed:.0f}s ({elapsed/60:.1f} min)", flush=True)


if __name__ == '__main__':
    main()
