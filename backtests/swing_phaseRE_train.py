"""
Phase Re-B/C: Train DD-strict labels under filtered universe.

For each candidate label:
  - Walk-forward monthly refit (6 mo OOS, no leak)
  - At each threshold (0.5-0.95), compute:
    - WR (% positives among picks)
    - When pick fails (label=0): what's the actual flow_pct (real DD)?
    - When pick succeeds: avg fhigh (real upside)
  - Realistic exit: pure hold to 30d, TP +TP% if hit, else fclose

Critical metric: worst-trade flow_pct (real path DD), not just avg loss.
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
MODELS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/models_swing_v2')
MODELS.mkdir(exist_ok=True)

LGB_PARAMS = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 31, 'max_depth': 5, 'min_child_samples': 30,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 1.0, 'reg_lambda': 1.0,
    'n_estimators': 300, 'n_jobs': 4, 'verbose': -1,
}

# Candidate labels: (tp_pct, dd_pct, window_days)
CANDIDATES = [
    {'tp': 5.0, 'dd': -3.0, 'w': 30, 'name': '+5_dd3_30d'},   # strictest
    {'tp': 5.0, 'dd': -5.0, 'w': 30, 'name': '+5_dd5_30d'},   # user's spec
    {'tp': 3.0, 'dd': -3.0, 'w': 30, 'name': '+3_dd3_30d'},   # smaller TP
    {'tp': 3.0, 'dd': -5.0, 'w': 30, 'name': '+3_dd5_30d'},   # easier
    {'tp': 5.0, 'dd': -7.0, 'w': 30, 'name': '+5_dd7_30d'},   # looser DD comparison
]

THRESHOLDS = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]


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


def walk_forward(df, feature_cols, label_col, w,
                  test_start='2025-09-01', test_end='2026-02-28'):
    df_l = df[df[label_col].notna()].copy().sort_values(['date', 'symbol']).reset_index(drop=True)
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
        y_train = df_l.loc[train_mask, label_col].astype(int).values
        X_test = df_l.loc[test_mask, feature_cols].fillna(-999).values
        model = lgb.LGBMClassifier(**LGB_PARAMS, random_state=42)
        model.fit(X_train, y_train)
        prob = model.predict_proba(X_test)[:, 1]
        sub = df_l.loc[test_mask, ['symbol', 'date', label_col,
                                     f'fhigh_pct_{w}d', f'flow_pct_{w}d',
                                     f'fclose_pct_{w}d']].copy()
        sub['prob'] = prob
        all_preds.append(sub)
    if not all_preds:
        return None
    return pd.concat(all_preds, ignore_index=True)


def evaluate(preds, label_col, tp, w, dd):
    """For each threshold, compute pure-hold metrics + real DD distribution."""
    h_col = f'fhigh_pct_{w}d'
    l_col = f'flow_pct_{w}d'
    c_col = f'fclose_pct_{w}d'

    # Pure hold exit: TP@tp% if hit, else fclose
    fhigh = preds[h_col].values
    flow = preds[l_col].values
    fclose = preds[c_col].values
    pnl = np.where(fhigh >= tp, tp, fclose)
    preds['pnl'] = pnl
    preds['actual_dd'] = flow

    rows = []
    days_test = (preds['date'].max() - preds['date'].min()).days
    for thr in THRESHOLDS:
        sel = preds[preds['prob'] >= thr]
        n = len(sel)
        if n < 10:
            continue
        wr_label = sel[label_col].mean()  # label-based WR (matches training target)
        wr_pnl = (sel['pnl'] > 0).mean()    # actual PnL-based WR
        avg_pnl = sel['pnl'].mean()
        std_pnl = sel['pnl'].std()
        worst_pnl = sel['pnl'].min()
        worst_dd = sel['actual_dd'].min()  # worst path DD across all picks
        p5_dd = sel['actual_dd'].quantile(0.05)
        p10_dd = sel['actual_dd'].quantile(0.10)
        avg_dd = sel['actual_dd'].mean()
        # % of picks with DD > -3 / -5 / -10
        pct_safe_3 = (sel['actual_dd'] > -3).mean()
        pct_safe_5 = (sel['actual_dd'] > -5).mean()
        pct_safe_10 = (sel['actual_dd'] > -10).mean()
        sharpe = avg_pnl / std_pnl * np.sqrt(252 / w) if std_pnl > 0 else 0
        rows.append({
            'thr': thr,
            'n': n,
            'n_per_year': round(n * 365 / max(days_test, 1)),
            'wr_label': round(wr_label, 3),
            'wr_pnl': round(wr_pnl, 3),
            'avg_pnl': round(avg_pnl, 3),
            'worst_pnl': round(worst_pnl, 2),
            'avg_dd': round(avg_dd, 2),
            'worst_dd': round(worst_dd, 2),
            'p5_dd': round(p5_dd, 2),
            'p10_dd': round(p10_dd, 2),
            'pct_dd_safe_3': round(pct_safe_3, 3),
            'pct_dd_safe_5': round(pct_safe_5, 3),
            'pct_dd_safe_10': round(pct_safe_10, 3),
            'sharpe': round(sharpe, 2),
        })
    return pd.DataFrame(rows)


def main():
    print("== Phase Re-B/C: Train DD-Strict Labels (Filtered Universe) ==", flush=True)
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
    print(f"  Filtered shape: {df.shape}", flush=True)
    feature_cols = get_feature_cols(df)
    print(f"  Features: {len(feature_cols)}", flush=True)

    all_results = []
    for cand in CANDIDATES:
        print(f"\n--- Training: {cand['name']} (TP={cand['tp']}, DD={cand['dd']}, W={cand['w']}) ---", flush=True)
        t0 = datetime.now()
        label_col = f"L_{cand['name']}"
        df[label_col] = compute_label(df, cand['tp'], cand['dd'], cand['w'])
        base = df[label_col].dropna().mean()
        print(f"  Base rate: {base:.3f}", flush=True)
        preds = walk_forward(df, feature_cols, label_col, cand['w'])
        if preds is None:
            print(f"  ❌ no preds", flush=True)
            continue
        elapsed = (datetime.now() - t0).total_seconds()
        from sklearn.metrics import roc_auc_score
        try:
            auc = roc_auc_score(preds[label_col].astype(int), preds['prob'])
        except:
            auc = np.nan
        print(f"  WF done in {elapsed:.0f}s, {len(preds):,} preds, AUC {auc:.3f}", flush=True)

        metrics = evaluate(preds, label_col, cand['tp'], cand['w'], cand['dd'])
        metrics['label'] = cand['name']
        metrics['auc'] = round(auc, 3)
        print(f"\n  Per-threshold metrics:", flush=True)
        print(metrics.to_string(index=False), flush=True)
        all_results.append(metrics)

    if all_results:
        final = pd.concat(all_results, ignore_index=True)
        final.to_csv(RESULTS / 'phaseRE_grid.csv', index=False)

        # Print best candidates: WR high + worst_dd safe
        print("\n== TOP CANDIDATES (filter: wr_pnl ≥ 0.85 AND worst_dd ≥ -10) ==", flush=True)
        good = final[(final['wr_pnl'] >= 0.85) & (final['worst_dd'] >= -10)].copy()
        good = good.sort_values('sharpe', ascending=False)
        print(good.to_string(index=False), flush=True)

        print("\n== TOP CANDIDATES (filter: wr_pnl ≥ 0.85 AND worst_dd ≥ -5) [USER'S STRICT REQ] ==", flush=True)
        strict = final[(final['wr_pnl'] >= 0.85) & (final['worst_dd'] >= -5)].copy()
        strict = strict.sort_values('sharpe', ascending=False)
        print(strict.to_string(index=False), flush=True)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Done in {elapsed:.0f}s ({elapsed/60:.1f} min)", flush=True)


if __name__ == '__main__':
    main()
