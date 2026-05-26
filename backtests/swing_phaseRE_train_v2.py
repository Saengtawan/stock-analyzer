"""
Train production 5-seed ensemble for swing_filter v2.0.

Config:
  Universe: price>$5, mcap>$1B, ADV>$10M (~936 symbols)
  Label: L_touch_2_dd-3_in_7d  ("+2% touch AND no DD <-3% within 7 days")
  Threshold: 0.75
  Exit: TP +2% / no SL / time stop 7d

Files saved:
  backtests/models_swing/lgb_swing_v2_seed{0-4}.txt (overwrite v1.0)
  backtests/models_swing/swing_config.json (updated)
  backtests/models_swing/feature_importance_v2.csv
"""
import sqlite3
import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
MODELS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/models_swing')

CONFIG = {
    'strategy_version': 'swing_v2.0',
    'deploy_date': '2026-05-26',
    'label': 'L_touch_2_dd-3_in_7d',
    'window_days': 7,
    'target_pct': 2.0,
    'dd_constraint_pct': -3.0,
    'threshold': 0.75,
    'exit_rules': {
        'tp_pct': 2.0,
        'sl_pct': None,
        'time_stop_days': 7,
    },
    'position_sizing': {
        'pct_per_position': 5.0,
        'max_concurrent': 5,
        'rank_by': 'prob',
    },
    'universe_filter': {
        'min_price': 5.0,
        'min_market_cap': 1e9,
        'min_avg_dollar_volume': 10e6,
    },
    'scan_window_et': '15:55-09:29 (post-close to pre-next-open)',
    'expected_metrics': {
        'wr': 0.93,
        'ev_per_trade': 1.78,
        'sharpe': 12.97,
        'worst_exit_pct': -2.27,
        'pct_safe_5pct_dd': 0.982,
        'oos_wr': 1.00,
        'oos_ev': 1.99,
        'oos_worst_pct': 1.48,
        'oos_n': 96,
    },
}

LGB_PARAMS = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 31, 'max_depth': 5, 'min_child_samples': 30,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 1.0, 'reg_lambda': 1.0,
    'n_estimators': 300, 'n_jobs': 4, 'verbose': -1,
}

N_SEEDS = 5


def get_feature_cols(df):
    drop = {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
            'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund',
            'market_cap', 'avg_volume', 'avg_dollar_vol'}
    return [c for c in df.columns
            if c not in drop and not c.startswith(('fhigh_', 'flow_', 'fclose_', 'L_'))
            and df[c].dtype != 'object']


def main():
    print("== Train swing_filter v2.0 — Production Models ==", flush=True)
    print(f"Config:", flush=True)
    print(f"  Label:     {CONFIG['label']}", flush=True)
    print(f"  Threshold: {CONFIG['threshold']}", flush=True)
    print(f"  Exit:      TP {CONFIG['exit_rules']['tp_pct']}% / no SL / {CONFIG['exit_rules']['time_stop_days']}d", flush=True)
    print(f"  Universe:  price≥${CONFIG['universe_filter']['min_price']}, mcap≥${CONFIG['universe_filter']['min_market_cap']/1e9:.1f}B, ADV≥${CONFIG['universe_filter']['min_avg_dollar_volume']/1e6:.0f}M", flush=True)

    print("\nLoading + filtering universe...", flush=True)
    df = pd.read_pickle(CACHE / 'phase2_features.pkl')
    con = sqlite3.connect(str(DB))
    funda = pd.read_sql("SELECT symbol, market_cap, avg_volume FROM stock_fundamentals", con)
    con.close()
    df = df.merge(funda, on='symbol', how='left')
    df['avg_dollar_vol'] = df['avg_volume'] * df['close']
    uf = CONFIG['universe_filter']
    mask = (
        (df['close'] >= uf['min_price']) &
        (df['market_cap'] >= uf['min_market_cap']) &
        (df['avg_dollar_vol'] >= uf['min_avg_dollar_volume'])
    )
    df = df[mask].copy()
    n_syms = df['symbol'].nunique()
    print(f"  Filtered: {len(df):,} rows × {n_syms} symbols", flush=True)

    # Build label
    print(f"\nBuilding label {CONFIG['label']}...", flush=True)
    w = CONFIG['window_days']
    tp = CONFIG['target_pct']
    dd = CONFIG['dd_constraint_pct']
    h = df[f'fhigh_pct_{w}d']
    l = df[f'flow_pct_{w}d']
    df[CONFIG['label']] = ((h >= tp) & (l >= dd)).astype(float)
    df.loc[h.isna() | l.isna(), CONFIG['label']] = np.nan
    base_rate = df[CONFIG['label']].dropna().mean()
    print(f"  Base rate: {base_rate:.3f}", flush=True)

    feature_cols = get_feature_cols(df)
    CONFIG['feature_cols'] = feature_cols
    print(f"  Features: {len(feature_cols)}", flush=True)

    # Prep training data (use all available data)
    mask_valid = df[CONFIG['label']].notna()
    X = df.loc[mask_valid, feature_cols].fillna(-999).values
    y = df.loc[mask_valid, CONFIG['label']].astype(int).values
    print(f"\nTraining samples: {len(X):,}", flush=True)
    print(f"Positive rate: {y.mean():.3f}", flush=True)

    # Train 5-seed ensemble
    for seed in range(N_SEEDS):
        print(f"\nTraining seed {seed}...", flush=True)
        params = {**LGB_PARAMS, 'random_state': seed}
        model = lgb.LGBMClassifier(**params)
        model.fit(X, y)
        out_path = MODELS / f'lgb_swing_v2_seed{seed}.txt'
        model.booster_.save_model(str(out_path))
        print(f"  saved: {out_path.name} ({out_path.stat().st_size / 1e6:.1f} MB)", flush=True)

    # Save config
    config_path = MODELS / 'swing_config.json'
    # Convert numpy types to python for JSON
    config_clean = {}
    for k, v in CONFIG.items():
        if isinstance(v, dict):
            config_clean[k] = {kk: (float(vv) if isinstance(vv, (np.floating, np.integer)) else vv) for kk, vv in v.items()}
        else:
            config_clean[k] = v
    with open(config_path, 'w') as f:
        json.dump(config_clean, f, indent=2)
    print(f"\nConfig saved: {config_path}", flush=True)

    # Feature importance from seed 0
    print("\n== Top 30 Feature Importance (seed 0) ==", flush=True)
    booster = lgb.Booster(model_file=str(MODELS / 'lgb_swing_v2_seed0.txt'))
    importance = booster.feature_importance(importance_type='gain')
    fi_df = pd.DataFrame({'feature': feature_cols, 'gain': importance})
    fi_df = fi_df.sort_values('gain', ascending=False)
    print(fi_df.head(30).to_string(index=False), flush=True)
    fi_df.to_csv(MODELS / 'feature_importance_v2.csv', index=False)

    print("\n✅ v2.0 production models trained", flush=True)
    print(f"   Models: {N_SEEDS} × lgb_swing_v2_seed*.txt", flush=True)


if __name__ == '__main__':
    main()
