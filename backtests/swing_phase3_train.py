"""
Phase 3 — Grid search training with walk-forward validation.

For each candidate label, train LightGBM classifier with monthly walk-forward
refit. For each threshold (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
  - Compute WR (true positive rate when predicted >= thr)
  - Count N (number of picks per year)
  - Compute avg_win, avg_loss (using forward returns)
  - Compute EV per trade
  - Compute Sharpe estimate

Filter: WR ≥80% AND N ≥50/yr AND EV > 0
Output: backtests/results_swing/phase3_grid.csv
"""
import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path
from datetime import datetime
from sklearn.metrics import roc_auc_score

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')
MODELS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/models_swing')
RESULTS.mkdir(exist_ok=True)
MODELS.mkdir(exist_ok=True)

# Labels to train (top 10 from Phase 0/1)
LABEL_CONFIGS = {
    'L_touch_1.5_in_5d':       {'target': 1.5, 'window': 5,  'dd': None},
    'L_touch_2_in_7d':         {'target': 2.0, 'window': 7,  'dd': None},
    'L_touch_3_in_14d':        {'target': 3.0, 'window': 14, 'dd': None},
    'L_touch_5_in_30d':        {'target': 5.0, 'window': 30, 'dd': None},
    'L_touch_2_in_5d':         {'target': 2.0, 'window': 5,  'dd': None},
    'L_touch_3_in_7d':         {'target': 3.0, 'window': 7,  'dd': None},
    'L_touch_5_dd-10_in_30d':  {'target': 5.0, 'window': 30, 'dd': -10.0},
    'L_touch_2_dd-5_in_5d':    {'target': 2.0, 'window': 5,  'dd': -5.0},
    'L_touch_3_in_5d':         {'target': 3.0, 'window': 5,  'dd': None},
    'L_touch_7_in_30d':        {'target': 7.0, 'window': 30, 'dd': None},
}

# Training HP
LGB_PARAMS = {
    'objective': 'binary',
    'metric': 'auc',
    'learning_rate': 0.05,
    'num_leaves': 31,
    'max_depth': 5,
    'min_child_samples': 30,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'reg_alpha': 1.0,
    'reg_lambda': 1.0,
    'n_estimators': 300,
    'n_jobs': 4,
    'verbose': -1,
}

THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]


def get_feature_cols(df):
    drop_cols = {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
                 'sector', 'mcap_bucket', 'vix_regime', 'industry',
                 'vix_y', 'beta_fund'}  # remove duplicates
    feature_cols = []
    for c in df.columns:
        if c in drop_cols:
            continue
        if c.startswith('fhigh_') or c.startswith('flow_') or c.startswith('fclose_'):
            continue
        if c.startswith('L_'):
            continue
        if df[c].dtype == 'object':
            continue
        feature_cols.append(c)
    return feature_cols


def compute_trade_outcome(row, target, dd, window):
    """For a pick (row), what's the actual P&L using exit rules?
    Exit rules:
      - Hit target → exit at +target%
      - Hit DD limit → exit at dd% (if dd not None)
      - Else exit at fclose_{window}d
    """
    h_col = f'fhigh_pct_{window}d'
    l_col = f'flow_pct_{window}d'
    c_col = f'fclose_pct_{window}d'

    fhigh = row[h_col]
    flow = row[l_col]
    fclose = row[c_col]

    if pd.isna(fhigh) or pd.isna(flow):
        return np.nan

    # If hit target → take profit
    if fhigh >= target:
        # But check: did DD hit FIRST? (heuristic: if both, assume DD first → conservative)
        if dd is not None and flow <= dd:
            # Both hit — conservative: assume DD hit first
            return dd
        return target

    # If DD hit (and target didn't)
    if dd is not None and flow <= dd:
        return dd

    # Otherwise — time stop at fclose
    return fclose if not pd.isna(fclose) else 0


def walk_forward_train_eval(df, label_name, label_def, feature_cols,
                              train_start='2020-01-01', test_start='2023-01-01',
                              test_end='2026-04-01'):
    """Train monthly walk-forward: train on past data, predict on next month."""
    df = df[df[label_name].notna()].copy()
    df = df.sort_values(['date', 'symbol']).reset_index(drop=True)

    # Use clean dates
    df['ym'] = df['date'].dt.to_period('M')

    # Months from test_start to test_end
    test_months = pd.period_range(test_start, test_end, freq='M')

    all_preds = []
    for tm in test_months:
        tm_start = tm.start_time
        tm_end = tm.end_time

        # Train: all data before tm_start, with at least window days gap (to avoid label leakage)
        train_cutoff = tm_start - pd.Timedelta(days=label_def['window'] + 5)
        train_mask = df['date'] < train_cutoff
        test_mask = (df['date'] >= tm_start) & (df['date'] <= tm_end)

        if train_mask.sum() < 50000 or test_mask.sum() < 100:
            continue

        X_train = df.loc[train_mask, feature_cols].fillna(-999).values
        y_train = df.loc[train_mask, label_name].astype(int).values

        X_test = df.loc[test_mask, feature_cols].fillna(-999).values
        y_test = df.loc[test_mask, label_name].astype(int).values

        model = lgb.LGBMClassifier(**LGB_PARAMS, random_state=42)
        model.fit(X_train, y_train)

        prob = model.predict_proba(X_test)[:, 1]
        test_df = df.loc[test_mask, ['symbol', 'date', label_name] +
                          [f'fhigh_pct_{label_def["window"]}d', f'flow_pct_{label_def["window"]}d',
                           f'fclose_pct_{label_def["window"]}d', 'has_earnings_nearby']].copy()
        test_df['prob'] = prob
        all_preds.append(test_df)

    if not all_preds:
        return None
    return pd.concat(all_preds, ignore_index=True)


def evaluate_thresholds(preds_df, label_name, label_def):
    """For each threshold, compute metrics."""
    target = label_def['target']
    dd = label_def['dd']
    window = label_def['window']

    h_col = f'fhigh_pct_{window}d'
    l_col = f'flow_pct_{window}d'
    c_col = f'fclose_pct_{window}d'

    # Compute trade outcomes using exit rules
    def outcome_row(row):
        return compute_trade_outcome(row, target, dd, window)

    preds_df['trade_pnl_pct'] = preds_df.apply(outcome_row, axis=1)

    rows = []
    for thr in THRESHOLDS:
        sel = preds_df[preds_df['prob'] >= thr]
        n = len(sel)
        if n == 0:
            continue
        wr = sel[label_name].mean()
        avg_pnl = sel['trade_pnl_pct'].mean()
        win_mask = sel[label_name] == 1
        avg_win = sel.loc[win_mask, 'trade_pnl_pct'].mean() if win_mask.sum() > 0 else np.nan
        avg_loss = sel.loc[~win_mask, 'trade_pnl_pct'].mean() if (~win_mask).sum() > 0 else np.nan

        # Days in test
        days_test = (preds_df['date'].max() - preds_df['date'].min()).days
        n_per_year = n * 365 / max(days_test, 1)

        # Std of PnL (Sharpe estimate)
        sharpe = avg_pnl / sel['trade_pnl_pct'].std() if sel['trade_pnl_pct'].std() > 0 else 0
        sharpe *= np.sqrt(252 / max(window, 1))  # annualized

        rows.append({
            'label': label_name,
            'threshold': thr,
            'n_picks': n,
            'n_per_year': round(n_per_year, 0),
            'wr': round(wr, 3),
            'avg_pnl_pct': round(avg_pnl, 3),
            'avg_win_pct': round(avg_win, 3) if not pd.isna(avg_win) else None,
            'avg_loss_pct': round(avg_loss, 3) if not pd.isna(avg_loss) else None,
            'sharpe_est': round(sharpe, 2),
        })
    return pd.DataFrame(rows)


def main():
    print("== Phase 3: Grid Search Training ==")
    start = datetime.now()

    print("Loading Phase 2 features...")
    df = pd.read_pickle(CACHE / 'phase2_features.pkl')
    print(f"  shape: {df.shape}")

    feature_cols = get_feature_cols(df)
    print(f"  Features: {len(feature_cols)}")

    # AUC + WR table
    all_results = []

    for label_name, label_def in LABEL_CONFIGS.items():
        print(f"\n--- Training: {label_name} ---")
        t0 = datetime.now()
        preds = walk_forward_train_eval(df, label_name, label_def, feature_cols)
        if preds is None:
            print(f"  ❌ No predictions generated")
            continue

        elapsed = (datetime.now() - t0).total_seconds()
        print(f"  Walk-forward done in {elapsed:.0f}s, {len(preds):,} predictions")

        # AUC overall
        try:
            auc = roc_auc_score(preds[label_name], preds['prob'])
            print(f"  AUC: {auc:.3f}")
        except Exception as e:
            print(f"  AUC error: {e}")
            auc = np.nan

        # Save preds for replay
        preds.to_pickle(MODELS / f'preds_{label_name}.pkl')

        # Per-threshold metrics
        metrics = evaluate_thresholds(preds, label_name, label_def)
        metrics['auc'] = round(auc, 3)
        print(metrics.to_string(index=False))

        all_results.append(metrics)

    final = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    final.to_csv(RESULTS / 'phase3_grid_results.csv', index=False)

    # Top survivors: WR ≥80, N ≥50/yr, EV > 0
    print("\n== Top survivors (WR ≥80%, N ≥50/yr, EV > 0) ==")
    survivors = final[(final['wr'] >= 0.80) & (final['n_per_year'] >= 50) & (final['avg_pnl_pct'] > 0)]
    survivors = survivors.sort_values('sharpe_est', ascending=False)
    print(survivors.to_string(index=False))
    survivors.to_csv(RESULTS / 'phase3_survivors.csv', index=False)

    # Also: best Sharpe regardless of WR
    print("\n== Best Sharpe overall (any threshold) ==")
    by_sharpe = final.sort_values('sharpe_est', ascending=False).head(20)
    print(by_sharpe.to_string(index=False))

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Phase 3 done in {elapsed:.0f}s ({elapsed/60:.1f} min)")


if __name__ == '__main__':
    main()
