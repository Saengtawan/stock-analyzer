"""
Phase 6 — Train production models for swing_filter.

Trains 5-seed LightGBM ensemble on FULL data (2020-now) for the winning
label: L_touch_5_in_30d (+5% within 30 days).

Models saved to: backtests/models_swing/lgb_swing_seed{0-4}.txt
Config saved to: backtests/models_swing/swing_config.json
"""
import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
MODELS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/models_swing')
MODELS.mkdir(exist_ok=True)

WINNER_CONFIG = {
    'strategy_version': 'swing_v1.0',
    'label': 'L_touch_5_in_30d',
    'window_days': 30,
    'target_pct': 5.0,
    'threshold': 0.90,
    'exit_rules': {
        'tp_pct': 5.0,
        'sl_pct': None,
        'time_stop_days': 30,
    },
    'position_sizing': {
        'pct_per_position': 5.0,
        'max_concurrent': 5,
        'rank_by': 'prob',
    },
    'scan_window_et': '15:55-16:00',
    'expected_metrics': {
        'wr': 0.95,
        'ev_per_trade': 4.17,
        'sharpe': 1.96,
        'n_per_year_unfiltered': 3500,
        'phase4_oos_wr': 0.95,
        'phase4_oos_ev': 4.17,
    },
    'data': {
        'train_start': '2020-01-01',
        'features_pkl': str(CACHE / 'phase2_features.pkl'),
        'n_features': 61,
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
            'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund'}
    return [c for c in df.columns
            if c not in drop and not c.startswith(('fhigh_', 'flow_', 'fclose_', 'L_'))
            and df[c].dtype != 'object']


def main():
    print("== Phase 6: Train Production Models ==", flush=True)
    print(f"Winning label: {WINNER_CONFIG['label']}", flush=True)
    print(f"Threshold: {WINNER_CONFIG['threshold']}", flush=True)
    print(f"Exit: TP {WINNER_CONFIG['exit_rules']['tp_pct']}% / SL {WINNER_CONFIG['exit_rules']['sl_pct']} / time {WINNER_CONFIG['exit_rules']['time_stop_days']}d", flush=True)

    print("\nLoading features...", flush=True)
    df = pd.read_pickle(CACHE / 'phase2_features.pkl')
    feature_cols = get_feature_cols(df)
    print(f"  shape: {df.shape}, features: {len(feature_cols)}", flush=True)

    label = WINNER_CONFIG['label']
    mask = df[label].notna()
    X = df.loc[mask, feature_cols].fillna(-999).values
    y = df.loc[mask, label].astype(int).values
    print(f"\nTraining samples: {len(X):,}", flush=True)
    print(f"Positive rate: {y.mean():.3f}", flush=True)

    for seed in range(N_SEEDS):
        print(f"\nTraining seed {seed}...", flush=True)
        params = {**LGB_PARAMS, 'random_state': seed}
        model = lgb.LGBMClassifier(**params)
        model.fit(X, y)
        out_path = MODELS / f'lgb_swing_seed{seed}.txt'
        model.booster_.save_model(str(out_path))
        print(f"  saved: {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)", flush=True)

    # Save feature columns + config
    config = {**WINNER_CONFIG, 'feature_cols': feature_cols}
    config_path = MODELS / 'swing_config.json'
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"\nConfig saved: {config_path}", flush=True)

    # Feature importance from seed 0
    print("\n== Top 30 Feature Importance (seed 0) ==", flush=True)
    booster = lgb.Booster(model_file=str(MODELS / 'lgb_swing_seed0.txt'))
    importance = booster.feature_importance(importance_type='gain')
    fi_df = pd.DataFrame({'feature': feature_cols, 'gain': importance})
    fi_df = fi_df.sort_values('gain', ascending=False)
    print(fi_df.head(30).to_string(index=False), flush=True)
    fi_df.to_csv(MODELS / 'feature_importance.csv', index=False)

    print("\n✅ Phase 6 production models trained", flush=True)
    print(f"   Models: {N_SEEDS} × lgb_swing_seed*.txt", flush=True)
    print(f"   Config: swing_config.json", flush=True)


if __name__ == '__main__':
    main()
