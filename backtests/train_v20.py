"""Train v20 models — A approach winner (V7+cross, 365d window).

Phase 5 deployment: replace v19 09:30 tp1 model with v20.
v20 features = v19 V7 (37 feats) + cross-asset ETF intraday (25 feats) = 62 feats.
v20 training window = 365 days (vs v19 = 180 days).

Other buckets (10:00 Huber, 10:45 tp1, 11:30 tp1) NOT updated — kept as v19.
The 24-month walk-forward backtest validated +8.1pp WR / +0.57pp avg improvement
on 09:30 bucket only. Other buckets had threshold/distribution mismatches in pkl
that prevented validation; safer to leave them on v19 until separately validated.
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

REPO = Path(__file__).resolve().parents[1]
V19_PKL = '/tmp/bt_features_v19.pkl'
OUT_DIR = REPO / 'backtests' / 'models_prod_v20'

# v19 baseline features (37, in features_0930.txt order)
V7_FEATS = ['mins_from_open', 'gain_from_open', 'range_pct', 'from_peak_pct', 'vs_vwap',
    'vol_ratio', 'vol_accel', 'bars_since_hi', 'hh_count', 'consol', 'range_exp',
    'gap_from_prev', 'beta', 'mcap_bucket', 'spy_green', 'spy_intra', 'vix',
    'vix_5d_chg', 'ad_ratio', 'sec3d', 'mom5d', 'mom20d', 'dist_sma20',
    'pct_52w_hi', 'pct_52w_lo', 'dow', 'insider_net_30d', 'news_sentiment',
    'earnings_days', 'pm_vol_ratio', 'short_pct', 'btc_5d_chg', 'jpy_5d_chg',
    'skew', 'vvix', 'vix_term_spread', 'sec_rel_strength']

# v20 additional features: cross-asset ETF intraday (25)
CROSS_FEATS = ['xlb_intra', 'xlc_intra', 'xle_intra', 'xlf_intra', 'xli_intra',
    'xlk_intra', 'xlp_intra', 'xlre_intra', 'xlu_intra', 'xlv_intra', 'xly_intra',
    'smh_intra', 'qqq_intra', 'iwm_intra', 'dbc_intra', 'eem_intra', 'gld_intra',
    'hyg_intra', 'igv_intra', 'ief_intra', 'lqd_intra', 'tlt_intra', 'uso_intra',
    'uup_intra', 'vxx_intra']

# 09:30 bucket spec (mins_from_open range; matches v19 training)
BUCKET_LO = 5
BUCKET_HI = 25
TRAIN_DAYS = 365
N_SEEDS = 5

CFG = dict(
    objective='binary', learning_rate=0.03, num_leaves=8, max_depth=3,
    min_child_samples=50, reg_alpha=1.0, reg_lambda=5.0, n_estimators=300,
    verbose=-1, n_jobs=4,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end-date', default=datetime.today().strftime('%Y-%m-%d'),
        help='Last date to include in training (cutoff = end - 365d)')
    args = ap.parse_args()

    print(f"Loading {V19_PKL}...")
    df = pd.read_pickle(V19_PKL)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

    feats = V7_FEATS + CROSS_FEATS
    feats_avail = [f for f in feats if f in df.columns]
    missing = [f for f in feats if f not in df.columns]
    if missing:
        print(f"WARN: missing features in pkl: {missing}", file=sys.stderr)
    print(f"Training with {len(feats_avail)} features ({len(V7_FEATS)} V7 + {len(CROSS_FEATS)} cross)")

    for c in feats_avail + ['label_decay']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    end_date = args.end_date
    cutoff = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    train_mask = (
        (df['date'] >= cutoff) & (df['date'] <= end_date) &
        (df['mins_from_open'] >= BUCKET_LO) & (df['mins_from_open'] <= BUCKET_HI)
    )
    df_train = df[train_mask]
    print(f"Training rows: {len(df_train):,} (cutoff {cutoff} → {end_date}, mfo {BUCKET_LO}-{BUCKET_HI})")

    if len(df_train) < 5000:
        print(f"ERROR: too few training rows ({len(df_train)})", file=sys.stderr)
        sys.exit(1)

    X = df_train[feats_avail].fillna(0).values
    y = (df_train['label_decay'] >= 1.0).astype(int).values
    print(f"Positive rate: {y.mean():.3f} ({y.sum():,}/{len(y):,})")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save features list (order matches model input)
    feats_path = OUT_DIR / 'features_0930.txt'
    with open(feats_path, 'w') as f:
        for ft in feats_avail:
            f.write(ft + '\n')
    print(f"Wrote {feats_path}")

    # Train 5 seeds
    for seed in range(N_SEEDS):
        m = lgb.LGBMClassifier(**{**CFG, 'random_state': seed})
        m.fit(X, y)
        out = OUT_DIR / f'lgb_tp1_0930_1000_seed{seed}.txt'
        m.booster_.save_model(str(out))
        train_acc = (m.predict_proba(X)[:, 1] >= 0.5).mean()
        print(f"  seed {seed}: train_pos_rate@0.5={train_acc:.3f}  saved {out.name}")

    print(f"\n✅ v20 09:30 models saved to {OUT_DIR}")
    print(f"   Other buckets unchanged — keep using v19 paths in ml_scorer.py")


if __name__ == '__main__':
    main()
