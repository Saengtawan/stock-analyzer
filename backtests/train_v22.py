"""Train v22 — REAL ensemble (bagging + feature fraction) + min-seed selection.

v22 changes from v21:
  - Enable bagging_fraction=0.8 + feature_fraction=0.8
    (v21 had no bagging → 5 seeds = identical model, ensemble no-op)
  - Live scorer uses MIN of 5 seed predictions (not MEAN)
    Filters out "lucky outlier high" picks where seeds disagree

24-month walk-forward HONEST validation:
  09:30  thr 0.42  WR=65.3%  avg=+1.57%  (vs v21 mean: 63.5% / +1.50%)
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

REPO = Path(__file__).resolve().parents[1]
V22_PKL = '/tmp/bt_features_v22.pkl'   # ETF-clean (no multi-tf)
V27_PKL = '/tmp/bt_features_v27.pkl'   # v27: + multi-timeframe features (15m/30m/1h)
OUT_DIR = REPO / 'backtests' / 'models_prod_v22'

# v19 baseline features minus 6 always-zero placeholders.
V7_FEATS = ['mins_from_open', 'gain_from_open', 'range_pct', 'from_peak_pct', 'vs_vwap',
    'vol_ratio', 'vol_accel', 'bars_since_hi', 'hh_count', 'consol', 'range_exp',
    'gap_from_prev', 'beta', 'mcap_bucket', 'spy_green', 'spy_intra', 'vix',
    'vix_5d_chg', 'ad_ratio', 'mom5d', 'mom20d', 'dist_sma20',
    'pct_52w_hi', 'pct_52w_lo', 'dow', 'btc_5d_chg', 'jpy_5d_chg',
    'skew', 'vvix', 'vix_term_spread', 'sec_rel_strength']  # 31 (was 37, dropped 6)

# Cross-asset ETF intraday (25)
CROSS_FEATS = ['xlb_intra', 'xlc_intra', 'xle_intra', 'xlf_intra', 'xli_intra',
    'xlk_intra', 'xlp_intra', 'xlre_intra', 'xlu_intra', 'xlv_intra', 'xly_intra',
    'smh_intra', 'qqq_intra', 'iwm_intra', 'dbc_intra', 'eem_intra', 'gld_intra',
    'hyg_intra', 'igv_intra', 'ief_intra', 'lqd_intra', 'tlt_intra', 'uso_intra',
    'uup_intra', 'vxx_intra']

# Quality interactions — only added to 09:30 model (validated to hurt late buckets)
INTERACTIONS = ['gain_x_spy', 'vol_x_mcap', 'gain_x_xlk', 'gain_div_vix', 'range_pullback']

# Bucket specs: (mfo_lo, mfo_hi, model_pattern, use_interactions)
BUCKET_SPECS = {
    '0930_1000': (5, 25, 'lgb_tp1_0930_1000_seed{}.txt', True),
    '1000_1045': (30, 75, 'lgb_tp1_1000_1045_seed{}.txt', False),
    '1045_1130': (75, 115, 'lgb_tp1_1045_1130_seed{}.txt', False),
    '1130_1300': (120, 200, 'lgb_tp1_1130_1300_seed{}.txt', False),
}

# Loss reject model patterns (v23 — explicit "predict loss > 1%" model per bucket)
LOSS_MODEL_SPECS = {
    '0930_1000': (5, 25, 'lgb_loss_0930_1000_seed{}.txt', True),
    '1000_1045': (30, 75, 'lgb_loss_1000_1045_seed{}.txt', False),
    '1045_1130': (75, 115, 'lgb_loss_1045_1130_seed{}.txt', False),
    '1130_1300': (120, 200, 'lgb_loss_1130_1300_seed{}.txt', False),
}

# v25 Tech-specialized model (09:30 only, validated +3.1pp WR vs unified)
TECH_SECTORS_TRAIN = {'Technology', 'Communication Services'}
TECH_MODEL_SPECS = {
    '0930_1000_tech': (5, 25, 'lgb_tp1_tech_0930_1000_seed{}.txt', True),
    '0930_1000_tech_loss': (5, 25, 'lgb_loss_tech_0930_1000_seed{}.txt', True),
}

# v27 Multi-timeframe models (10:00 + 11:30 only, validated to help these buckets)
TF_FEATURES = []
for tf in ['15m', '30m', '1h']:
    for f in ['gain', 'range', 'vol_norm', 'green_pct', 'high_break']:
        TF_FEATURES.append(f'{tf}_{f}')
TF_BUCKET_SPECS = {
    '1000_1045_tf':      (30, 75, 'lgb_tp1_tf_1000_1045_seed{}.txt', False),
    '1000_1045_tf_loss': (30, 75, 'lgb_loss_tf_1000_1045_seed{}.txt', False),
    '1130_1300_tf':      (120, 200, 'lgb_tp1_tf_1130_1300_seed{}.txt', False),
    '1130_1300_tf_loss': (120, 200, 'lgb_loss_tf_1130_1300_seed{}.txt', False),
}
TRAIN_DAYS = 365
N_SEEDS = 5

CFG = dict(
    objective='binary', learning_rate=0.03, num_leaves=8, max_depth=3,
    min_child_samples=50, reg_alpha=1.0, reg_lambda=5.0, n_estimators=300,
    verbose=-1, n_jobs=4,
    # v22: enable bagging so 5 seeds give DIFFERENT trees (real ensemble)
    bagging_fraction=0.8, bagging_freq=1, feature_fraction=0.8,
)


def add_interactions(df):
    df['gain_x_spy'] = df['gain_from_open'].fillna(0) * df['spy_intra'].fillna(0)
    df['vol_x_mcap'] = df['vol_ratio'].fillna(1) * df['mcap_bucket'].fillna(1)
    df['gain_x_xlk'] = df['gain_from_open'].fillna(0) * df['xlk_intra'].fillna(0)
    df['gain_div_vix'] = df['gain_from_open'].fillna(0) / (df['vix'].fillna(20) / 20.0)
    df['range_pullback'] = df['range_pct'].fillna(0) * (5 - df['gain_from_open'].fillna(0).clip(0, 5))
    return df


def train_bucket(df, feats_avail, bucket_key, spec, end_date,
                 label_col='label_decay', label_thr=1.0, label_op='ge', tag='tp1'):
    mfo_lo, mfo_hi, model_pattern, use_inter = spec
    feats = feats_avail + (INTERACTIONS if use_inter else [])
    cutoff = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    train_mask = (
        (df['date'] >= cutoff) & (df['date'] <= end_date) &
        (df['mins_from_open'] >= mfo_lo) & (df['mins_from_open'] <= mfo_hi)
    )
    df_train = df[train_mask]
    print(f"\n=== {tag.upper()} bucket {bucket_key} (mfo {mfo_lo}-{mfo_hi}) ===")
    print(f"Training rows: {len(df_train):,}  feats: {len(feats)}")

    if len(df_train) < 5000:
        print(f"ERROR: too few training rows ({len(df_train)})", file=sys.stderr)
        return False

    X = df_train[feats].fillna(0).values
    if label_op == 'ge':
        y = (df_train[label_col] >= label_thr).astype(int).values
    else:  # 'le'
        y = (df_train[label_col] <= label_thr).astype(int).values
    print(f"Positive rate: {y.mean():.3f} ({y.sum():,}/{len(y):,})")

    for seed in range(N_SEEDS):
        m = lgb.LGBMClassifier(**{**CFG, 'random_state': seed})
        m.fit(X, y)
        out = OUT_DIR / model_pattern.format(seed)
        m.booster_.save_model(str(out))
        print(f"  seed {seed}: saved {out.name}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end-date', default=datetime.today().strftime('%Y-%m-%d'))
    ap.add_argument('--buckets', nargs='+', default=list(BUCKET_SPECS.keys()))
    ap.add_argument('--train-v27-tf', action='store_true',
                    help='Also train v27 multi-timeframe models (10:00 + 11:30)')
    args = ap.parse_args()

    print(f"Loading {V22_PKL}...")
    df = pd.read_pickle(V22_PKL)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

    feats = V7_FEATS + CROSS_FEATS
    feats_avail = [f for f in feats if f in df.columns]
    missing = [f for f in feats if f not in df.columns]
    if missing:
        print(f"WARN: missing features in pkl: {missing}", file=sys.stderr)
    print(f"Base features: {len(feats_avail)} ({len(V7_FEATS)} V7 + {len(CROSS_FEATS)} cross)")

    for c in feats_avail + ['label_decay', 'label_fixed3']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    df = add_interactions(df)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save 2 feature lists (per-bucket model input order)
    feats_0930 = feats_avail + INTERACTIONS  # 56 + 5 = 61
    feats_late = feats_avail                  # 56
    with open(OUT_DIR / 'features_0930.txt', 'w') as f:
        for ft in feats_0930: f.write(ft + '\n')
    with open(OUT_DIR / 'features_late.txt', 'w') as f:
        for ft in feats_late: f.write(ft + '\n')
    print(f"Wrote features_0930.txt ({len(feats_0930)}) and features_late.txt ({len(feats_late)})")

    for key in args.buckets:
        if key not in BUCKET_SPECS:
            print(f"WARN: unknown bucket {key}", file=sys.stderr)
            continue
        # tp1 win model (predict label_decay >= 1.0)
        train_bucket(df, feats_avail, key, BUCKET_SPECS[key], args.end_date,
                     label_col='label_decay', label_thr=1.0, label_op='ge', tag='tp1')
        # loss reject model (predict label_fixed3 <= -1.0)
        train_bucket(df, feats_avail, key, LOSS_MODEL_SPECS[key], args.end_date,
                     label_col='label_fixed3', label_thr=-1.0, label_op='le', tag='loss')

    # v25: Tech-specialized 09:30 model (validated +3.1pp WR vs unified at 09:30)
    if '0930_1000' in args.buckets:
        # Load sector map
        import sqlite3 as _sql
        _conn = _sql.connect('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
        sec_map = dict(_conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
        _conn.close()
        df_tech = df[df['sym'].apply(lambda s: sec_map.get(s, '') in TECH_SECTORS_TRAIN)].copy()
        print(f"\n=== TECH-SPECIALIZED 09:30 (v25) ===")
        print(f"Tech rows: {len(df_tech):,}/{len(df):,} ({len(df_tech)/len(df)*100:.1f}%)")
        train_bucket(df_tech, feats_avail, '0930_1000_tech',
                     TECH_MODEL_SPECS['0930_1000_tech'], args.end_date,
                     label_col='label_decay', label_thr=1.0, label_op='ge', tag='tech-tp1')
        train_bucket(df_tech, feats_avail, '0930_1000_tech_loss',
                     TECH_MODEL_SPECS['0930_1000_tech_loss'], args.end_date,
                     label_col='label_fixed3', label_thr=-1.0, label_op='le', tag='tech-loss')

    # v27: Multi-timeframe models for 10:00 + 11:30 (validated +6.2pp at 10:00, +1.6pp at 11:30)
    if args.train_v27_tf:
        print(f"\n=== v27 MULTI-TIMEFRAME (10:00 + 11:30 only) ===")
        # Load v27 pkl which has multi-tf features
        df_tf = pd.read_pickle(V27_PKL)
        df_tf['date'] = pd.to_datetime(df_tf['date']).dt.strftime('%Y-%m-%d')
        tf_feats_avail = [f for f in TF_FEATURES if f in df_tf.columns]
        print(f"  Multi-tf features available: {len(tf_feats_avail)}/{len(TF_FEATURES)}")
        # Numeric conversion
        for c in feats_avail + tf_feats_avail + ['label_decay', 'label_fixed3']:
            if c in df_tf.columns:
                df_tf[c] = pd.to_numeric(df_tf[c], errors='coerce')
        df_tf = add_interactions(df_tf)
        # Save tf feature list (base 56 + multi-tf 15 = 71)
        feats_late_tf = feats_avail + tf_feats_avail
        with open(OUT_DIR / 'features_late_tf.txt', 'w') as f:
            for ft in feats_late_tf:
                f.write(ft + '\n')
        print(f"  Wrote features_late_tf.txt ({len(feats_late_tf)} features)")
        # Train tp1 + loss for 10:00 and 11:30 with multi-tf
        for bucket_key in ['1000_1045', '1130_1300']:
            train_bucket(df_tf, feats_late_tf, f'{bucket_key}_tf',
                         TF_BUCKET_SPECS[f'{bucket_key}_tf'], args.end_date,
                         label_col='label_decay', label_thr=1.0, label_op='ge', tag='tf-tp1')
            train_bucket(df_tf, feats_late_tf, f'{bucket_key}_tf_loss',
                         TF_BUCKET_SPECS[f'{bucket_key}_tf_loss'], args.end_date,
                         label_col='label_fixed3', label_thr=-1.0, label_op='le', tag='tf-loss')

    print(f"\n✅ v27 models saved to {OUT_DIR}")


if __name__ == '__main__':
    main()
