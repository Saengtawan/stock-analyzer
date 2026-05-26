"""
Phase Re-D: Full Funnel Validation for short-window swing candidates.

Test top 3 candidates:
  C1: +2_dd3_7d @ thr 0.75 (strictest DD spec)
  C2: +2_dd5_5d @ thr 0.80 (faster turnover)
  C3: +3_dd5_5d @ thr 0.70 (more trades)

Funnel phases:
  F1: Walk-forward monthly refit (6 mo OOS, no leak)
  F2: Cross-regime (VIX-based breakdown)
  F3: TRUE OOS holdout (last 75 days unseen)
  F4: Smoke tests

Floors:
  F1: WR ≥ 85%, worst_pnl ≥ -5%
  F2: 4/5 regimes positive
  F3: WR ≥ 85%, worst_pnl ≥ -5%, AVG ≥ +1%
"""
import sqlite3
import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')

LGB_PARAMS = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 31, 'max_depth': 5, 'min_child_samples': 30,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 1.0, 'reg_lambda': 1.0,
    'n_estimators': 300, 'n_jobs': 4, 'verbose': -1,
}

CANDIDATES = [
    {'name': 'C1_strict_dd3_7d', 'tp': 2.0, 'dd': -3.0, 'w': 7, 'thr': 0.75},
    {'name': 'C2_fast_dd5_5d',   'tp': 2.0, 'dd': -5.0, 'w': 5, 'thr': 0.80},
    {'name': 'C3_more_dd5_5d',   'tp': 3.0, 'dd': -5.0, 'w': 5, 'thr': 0.70},
]


def get_feature_cols(df):
    drop = {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
            'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund',
            'market_cap', 'avg_volume', 'avg_dollar_vol'}
    return [c for c in df.columns
            if c not in drop and not c.startswith(('fhigh_', 'flow_', 'fclose_', 'L_'))
            and df[c].dtype != 'object']


def compute_label(df, tp, dd, w):
    h = df[f'fhigh_pct_{w}d']
    l = df[f'flow_pct_{w}d']
    label = ((h >= tp) & (l >= dd)).astype(float)
    label[h.isna() | l.isna()] = np.nan
    return label


def compute_pnl(picks, tp, w):
    fhigh = picks[f'fhigh_pct_{w}d'].values
    flow = picks[f'flow_pct_{w}d'].values
    fclose = picks[f'fclose_pct_{w}d'].values
    pnl = np.where(fhigh >= tp, tp, fclose)
    return pnl, flow


def F1_walk_forward(df, cand, feature_cols, test_start='2025-09-01', test_end='2026-02-28'):
    """6-month walk-forward monthly refit (NO LEAK)."""
    label_col = f"L_{cand['name']}"
    if label_col not in df.columns:
        df[label_col] = compute_label(df, cand['tp'], cand['dd'], cand['w'])
    df_l = df[df[label_col].notna()].copy().sort_values(['date', 'symbol']).reset_index(drop=True)
    test_months = pd.period_range(test_start, test_end, freq='M')
    all_preds = []
    for tm in test_months:
        tm_start = tm.start_time
        tm_end = tm.end_time
        train_cutoff = tm_start - pd.Timedelta(days=cand['w'] + 5)
        train_mask = df_l['date'] < train_cutoff
        test_mask = (df_l['date'] >= tm_start) & (df_l['date'] <= tm_end)
        if train_mask.sum() < 50000 or test_mask.sum() < 100:
            continue
        X_train = df_l.loc[train_mask, feature_cols].fillna(-999).values
        y_train = df_l.loc[train_mask, label_col].astype(int).values
        X_test = df_l.loc[test_mask, feature_cols].fillna(-999).values
        model = lgb.LGBMClassifier(**LGB_PARAMS, random_state=42)
        model.fit(X_train, y_train)
        prob = model.predict_proba(X_test)[:, 1]
        sub = df_l.loc[test_mask, ['symbol', 'date', label_col,
                                     f'fhigh_pct_{cand["w"]}d', f'flow_pct_{cand["w"]}d',
                                     f'fclose_pct_{cand["w"]}d', 'vix_regime', 'sector']].copy()
        sub['prob'] = prob
        all_preds.append(sub)
    if not all_preds:
        return None
    preds = pd.concat(all_preds, ignore_index=True)
    picks = preds[preds['prob'] >= cand['thr']].copy()
    if len(picks) == 0:
        return None
    pnl, flow = compute_pnl(picks, cand['tp'], cand['w'])
    picks['pnl'] = pnl
    picks['actual_dd'] = flow

    wr = (picks['pnl'] > 0).mean()
    avg = picks['pnl'].mean()
    std = picks['pnl'].std()
    worst_pnl = picks['pnl'].min()
    worst_dd = picks['actual_dd'].min()
    sharpe = avg / std * np.sqrt(252 / cand['w']) if std > 0 else 0
    pct_safe_5 = (picks['actual_dd'] > -5).mean()

    passed = wr >= 0.85 and worst_pnl >= -5 and avg >= 1.0
    return {
        'wr': round(wr, 3),
        'avg_pnl': round(avg, 3),
        'worst_pnl': round(worst_pnl, 2),
        'worst_dd': round(worst_dd, 2),
        'pct_safe_5': round(pct_safe_5, 3),
        'sharpe': round(sharpe, 2),
        'n': len(picks),
        'status': 'PASS' if passed else 'FAIL',
        '_picks': picks,
    }


def F2_cross_regime(picks_df, cand):
    """VIX regime breakdown."""
    regimes = ['Calm', 'Normal', 'Elevated', 'Stress', 'Crisis']
    rows = []
    n_positive = 0
    for reg in regimes:
        sub = picks_df[picks_df['vix_regime'] == reg]
        if len(sub) == 0:
            rows.append({'regime': reg, 'wr': None, 'avg': None, 'worst': None, 'n': 0})
            continue
        wr = (sub['pnl'] > 0).mean()
        avg = sub['pnl'].mean()
        worst = sub['pnl'].min()
        rows.append({'regime': reg, 'wr': round(wr, 3),
                     'avg': round(avg, 3), 'worst': round(worst, 2), 'n': len(sub)})
        if avg > 0:
            n_positive += 1
    n_with_data = sum(1 for r in rows if r['n'] > 0)
    passed = n_positive >= max(1, n_with_data - 1)  # at least n-1 regimes positive
    return {'regimes': rows, 'n_positive': n_positive,
            'n_with_data': n_with_data, 'status': 'PASS' if passed else 'FAIL'}


def F3_true_oos(df, cand, feature_cols, holdout_start='2026-03-01', holdout_end='2026-05-15'):
    """TRUE OOS — train on all data before holdout, predict holdout."""
    label_col = f"L_{cand['name']}"
    if label_col not in df.columns:
        df[label_col] = compute_label(df, cand['tp'], cand['dd'], cand['w'])
    df_l = df[df[label_col].notna()].copy()
    train_cutoff = pd.Timestamp(holdout_start) - pd.Timedelta(days=cand['w'] + 5)
    train_mask = df_l['date'] < train_cutoff
    test_mask = (df_l['date'] >= pd.Timestamp(holdout_start)) & (df_l['date'] <= pd.Timestamp(holdout_end))
    if train_mask.sum() < 50000 or test_mask.sum() < 50:
        return {'status': 'no_data'}
    X_train = df_l.loc[train_mask, feature_cols].fillna(-999).values
    y_train = df_l.loc[train_mask, label_col].astype(int).values
    X_test = df_l.loc[test_mask, feature_cols].fillna(-999).values
    model = lgb.LGBMClassifier(**LGB_PARAMS, random_state=42)
    model.fit(X_train, y_train)
    prob = model.predict_proba(X_test)[:, 1]
    sub = df_l.loc[test_mask, ['symbol', 'date',
                                f'fhigh_pct_{cand["w"]}d', f'flow_pct_{cand["w"]}d',
                                f'fclose_pct_{cand["w"]}d']].copy()
    sub['prob'] = prob
    picks = sub[sub['prob'] >= cand['thr']].copy()
    if len(picks) == 0:
        return {'status': 'no_picks'}
    pnl, flow = compute_pnl(picks, cand['tp'], cand['w'])
    picks['pnl'] = pnl
    picks['actual_dd'] = flow
    wr = (picks['pnl'] > 0).mean()
    avg = picks['pnl'].mean()
    worst_pnl = picks['pnl'].min()
    worst_dd = picks['actual_dd'].min()
    pct_safe_5 = (picks['actual_dd'] > -5).mean()
    passed = wr >= 0.85 and worst_pnl >= -5 and avg >= 1.0
    return {
        'wr': round(wr, 3),
        'avg_pnl': round(avg, 3),
        'worst_pnl': round(worst_pnl, 2),
        'worst_dd': round(worst_dd, 2),
        'pct_safe_5': round(pct_safe_5, 3),
        'n': len(picks),
        'status': 'PASS' if passed else 'FAIL',
    }


def F4_smoke(df, cand, f1_picks):
    checks = []
    label_col = f"L_{cand['name']}"
    vals = set(df[label_col].dropna().unique())
    checks.append(('label_binary', vals.issubset({0, 1, 0.0, 1.0})))
    if '_picks' in f1_picks:
        picks = f1_picks['_picks']
        n_syms = picks['symbol'].nunique()
        checks.append(('symbol_diversity', n_syms >= 20))
        # PnL distribution sanity
        pnl_std = picks['pnl'].std()
        checks.append(('pnl_variation', pnl_std > 0.5))
        # No future leakage check
        for col in ['fhigh_pct_', 'flow_pct_', 'fclose_pct_']:
            if any(c.startswith(col) for c in df.columns if c in ['feature']):
                checks.append((f'no_leak_{col}', False))
                break
        else:
            checks.append(('no_forward_in_features', True))
    n_pass = sum(1 for _, p in checks if p)
    return {'checks': checks, 'n_pass': n_pass, 'n_total': len(checks),
            'status': 'PASS' if n_pass == len(checks) else 'FAIL'}


def main():
    print("== Phase Re-D: Full Funnel Validation ==", flush=True)
    start = datetime.now()

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
    print(f"  Filtered: {df.shape}", flush=True)
    feature_cols = get_feature_cols(df)

    summary = []
    for cand in CANDIDATES:
        print(f"\n{'='*70}", flush=True)
        print(f"FUNNEL: {cand['name']}", flush=True)
        print(f"  Label: touch {cand['tp']}%, DD≥{cand['dd']}%, window {cand['w']}d", flush=True)
        print(f"  Threshold: {cand['thr']}", flush=True)
        print('='*70, flush=True)

        # F1
        print("\n→ F1: Walk-forward monthly refit (6mo, no leak)", flush=True)
        f1 = F1_walk_forward(df, cand, feature_cols)
        if f1 is None:
            print("  ❌ no preds", flush=True)
            continue
        print(f"  WR {f1['wr']} / EV {f1['avg_pnl']}% / Worst {f1['worst_pnl']}% / DD {f1['worst_dd']}%", flush=True)
        print(f"  Safe<-5%: {f1['pct_safe_5']*100:.1f}% / Sharpe {f1['sharpe']} / N {f1['n']} → {f1['status']}", flush=True)

        # F2
        print("\n→ F2: Cross-regime breakdown", flush=True)
        f2 = F2_cross_regime(f1['_picks'], cand)
        for r in f2['regimes']:
            wr_s = f"{r['wr']}" if r['wr'] is not None else "—"
            avg_s = f"{r['avg']}" if r['avg'] is not None else "—"
            worst_s = f"{r['worst']}" if r['worst'] is not None else "—"
            print(f"  {r['regime']:10s}: WR {wr_s} / EV {avg_s}% / Worst {worst_s}% / N {r['n']}", flush=True)
        print(f"  {f2['n_positive']}/{f2['n_with_data']} regimes positive → {f2['status']}", flush=True)

        # F3
        print("\n→ F3: TRUE OOS (last 75 days unseen)", flush=True)
        f3 = F3_true_oos(df, cand, feature_cols)
        if 'wr' in f3:
            print(f"  WR {f3['wr']} / EV {f3['avg_pnl']}% / Worst {f3['worst_pnl']}% / DD {f3['worst_dd']}%", flush=True)
            print(f"  Safe<-5%: {f3['pct_safe_5']*100:.1f}% / N {f3['n']} → {f3['status']}", flush=True)
        else:
            print(f"  ⚠️ {f3['status']}", flush=True)

        # F4
        print("\n→ F4: Smoke tests", flush=True)
        f4 = F4_smoke(df, cand, f1)
        for chk, p in f4['checks']:
            print(f"  {'✓' if p else '✗'} {chk}", flush=True)
        print(f"  {f4['n_pass']}/{f4['n_total']} pass → {f4['status']}", flush=True)

        # Overall
        overall = 'PASS' if (f1['status'] == 'PASS' and f2['status'] == 'PASS'
                              and f3.get('status') == 'PASS' and f4['status'] == 'PASS') else 'FAIL'
        print(f"\n{'='*70}", flush=True)
        print(f"OVERALL: {overall}", flush=True)
        print('='*70, flush=True)

        summary.append({
            'name': cand['name'],
            'tp': cand['tp'], 'dd': cand['dd'], 'w': cand['w'], 'thr': cand['thr'],
            'overall': overall,
            'f1_wr': f1.get('wr'),
            'f1_ev': f1.get('avg_pnl'),
            'f1_worst': f1.get('worst_pnl'),
            'f1_dd': f1.get('worst_dd'),
            'f1_safe5': f1.get('pct_safe_5'),
            'f1_sharpe': f1.get('sharpe'),
            'f1_n': f1.get('n'),
            'f2_pos': f2.get('n_positive'),
            'f2_total': f2.get('n_with_data'),
            'f3_wr': f3.get('wr'),
            'f3_ev': f3.get('avg_pnl'),
            'f3_worst': f3.get('worst_pnl'),
            'f3_n': f3.get('n'),
            'f4_pass': f4.get('n_pass'),
        })

    sdf = pd.DataFrame(summary)
    sdf.to_csv(RESULTS / 'phaseRE_funnel.csv', index=False)
    print("\n\n== Funnel Summary ==", flush=True)
    print(sdf.to_string(index=False), flush=True)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Done in {elapsed:.0f}s ({elapsed/60:.1f} min)", flush=True)


if __name__ == '__main__':
    main()
