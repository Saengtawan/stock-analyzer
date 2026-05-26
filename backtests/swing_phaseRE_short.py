"""
Phase Re-Short: Try SHORT swing windows (3d/5d/7d) with strict DD.

User insight: longer hold = more external event exposure = more DD risk.
Try short windows to limit exposure.

Labels:
  Pure hold, time stop at window day.
  Exit: TP at +X% if hit, else fclose at day W.
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

# Short windows with DD constraint
CANDIDATES = [
    # 3-day window
    {'tp': 2.0, 'dd': -3.0, 'w': 3, 'name': '+2_dd3_3d'},
    {'tp': 2.0, 'dd': -5.0, 'w': 3, 'name': '+2_dd5_3d'},
    {'tp': 3.0, 'dd': -3.0, 'w': 3, 'name': '+3_dd3_3d'},
    {'tp': 3.0, 'dd': -5.0, 'w': 3, 'name': '+3_dd5_3d'},
    # 5-day window
    {'tp': 2.0, 'dd': -3.0, 'w': 5, 'name': '+2_dd3_5d'},
    {'tp': 2.0, 'dd': -5.0, 'w': 5, 'name': '+2_dd5_5d'},
    {'tp': 3.0, 'dd': -3.0, 'w': 5, 'name': '+3_dd3_5d'},
    {'tp': 3.0, 'dd': -5.0, 'w': 5, 'name': '+3_dd5_5d'},
    {'tp': 5.0, 'dd': -5.0, 'w': 5, 'name': '+5_dd5_5d'},
    # 7-day window
    {'tp': 2.0, 'dd': -3.0, 'w': 7, 'name': '+2_dd3_7d'},
    {'tp': 3.0, 'dd': -3.0, 'w': 7, 'name': '+3_dd3_7d'},
    {'tp': 3.0, 'dd': -5.0, 'w': 7, 'name': '+3_dd5_7d'},
    {'tp': 5.0, 'dd': -5.0, 'w': 7, 'name': '+5_dd5_7d'},
]

THRESHOLDS = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90]


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


def evaluate(preds, label_col, tp, w):
    h_col = f'fhigh_pct_{w}d'
    l_col = f'flow_pct_{w}d'
    c_col = f'fclose_pct_{w}d'
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
        if n < 30:
            continue
        wr_pnl = (sel['pnl'] > 0).mean()
        avg_pnl = sel['pnl'].mean()
        std_pnl = sel['pnl'].std()
        worst_pnl = sel['pnl'].min()
        worst_dd = sel['actual_dd'].min()
        p5_dd = sel['actual_dd'].quantile(0.05)
        avg_dd = sel['actual_dd'].mean()
        pct_safe_3 = (sel['actual_dd'] > -3).mean()
        pct_safe_5 = (sel['actual_dd'] > -5).mean()
        sharpe = avg_pnl / std_pnl * np.sqrt(252 / w) if std_pnl > 0 else 0
        rows.append({
            'thr': thr,
            'n': n,
            'n_per_year': round(n * 365 / max(days_test, 1)),
            'wr_pnl': round(wr_pnl, 3),
            'avg_pnl': round(avg_pnl, 3),
            'worst_pnl': round(worst_pnl, 2),
            'avg_dd': round(avg_dd, 2),
            'worst_dd': round(worst_dd, 2),
            'p5_dd': round(p5_dd, 2),
            'pct_safe_3': round(pct_safe_3, 3),
            'pct_safe_5': round(pct_safe_5, 3),
            'sharpe': round(sharpe, 2),
        })
    return pd.DataFrame(rows)


def main():
    print("== Phase Re-Short: Short Windows (3d/5d/7d) + DD constraint ==", flush=True)
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

    all_results = []
    for cand in CANDIDATES:
        print(f"\n--- {cand['name']} ---", flush=True)
        t0 = datetime.now()
        label_col = f"L_{cand['name']}"
        df[label_col] = compute_label(df, cand['tp'], cand['dd'], cand['w'])
        base = df[label_col].dropna().mean()
        preds = walk_forward(df, feature_cols, label_col, cand['w'])
        if preds is None:
            continue
        elapsed = (datetime.now() - t0).total_seconds()
        from sklearn.metrics import roc_auc_score
        try:
            auc = roc_auc_score(preds[label_col].astype(int), preds['prob'])
        except:
            auc = np.nan
        print(f"  base {base:.3f} AUC {auc:.3f} ({elapsed:.0f}s, {len(preds):,} preds)", flush=True)

        metrics = evaluate(preds, label_col, cand['tp'], cand['w'])
        metrics['label'] = cand['name']
        metrics['auc'] = round(auc, 3)
        metrics['base_rate'] = round(base, 3)
        if len(metrics) > 0:
            print(metrics[['thr','n','wr_pnl','avg_pnl','worst_pnl','worst_dd','p5_dd','pct_safe_5','sharpe']].to_string(index=False), flush=True)
        all_results.append(metrics)

    if all_results:
        final = pd.concat(all_results, ignore_index=True)
        final.to_csv(RESULTS / 'phaseRE_short_grid.csv', index=False)

        # Best by strict criteria
        print("\n== ⭐ BEST CANDIDATES (worst_pnl ≥ -5, wr_pnl ≥ 0.80) ==", flush=True)
        good = final[(final['worst_pnl'] >= -5) & (final['wr_pnl'] >= 0.80) & (final['n'] >= 50)]
        good = good.sort_values('sharpe', ascending=False)
        print(good.to_string(index=False) if len(good) > 0 else "  (none)", flush=True)

        print("\n== ⭐ BEST CANDIDATES (worst_dd ≥ -5, wr_pnl ≥ 0.80) - STRICTEST DD ==", flush=True)
        strict = final[(final['worst_dd'] >= -5) & (final['wr_pnl'] >= 0.80) & (final['n'] >= 50)]
        strict = strict.sort_values('sharpe', ascending=False)
        print(strict.to_string(index=False) if len(strict) > 0 else "  (none)", flush=True)

        print("\n== ⭐ BEST BY SHARPE (any criteria) ==", flush=True)
        top10 = final.sort_values('sharpe', ascending=False).head(15)
        print(top10[['label','thr','n','wr_pnl','avg_pnl','worst_pnl','worst_dd','sharpe','auc']].to_string(index=False), flush=True)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Done in {elapsed:.0f}s ({elapsed/60:.1f} min)", flush=True)


if __name__ == '__main__':
    main()
