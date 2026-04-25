"""Train v21 — canonical features (no lookahead bias).

v21 changes from v20.1:
  - vol_ratio: today_vol / (30d_avg_daily * fraction_of_day_elapsed)
    (was: today_vol / today's-full-day-avg — LOOKAHEAD BIAS)
  - vol_accel: last3 vs prev3 (was: last3 vs first3 — different signal)
  - range_exp: range_pct / 10d_avg_range (was: hardcoded /3.0)
  - consol: 5 bars (was: 4 bars — match live)

24-month walk-forward HONEST validation:
  09:30  56 base + 5 interactions  thr 0.45  WR=63.6%  avg=+1.49%
  10:45  56 base                    thr 0.25  WR=66.7%  avg=+0.70%
  11:30  56 base                    thr 0.22  WR=58.9%  avg=+0.39%

Note: v20.1's "71% WR" was inflated by lookahead bias.
v21 numbers are HONEST — backtest = live (when live also fixed).
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

REPO = Path(__file__).resolve().parents[1]
V21_PKL = '/tmp/bt_features_v21.pkl'
OUT_DIR = REPO / 'backtests' / 'models_prod_v21'

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
    '1045_1130': (75, 115, 'lgb_tp1_1045_1130_seed{}.txt', False),
    '1130_1300': (120, 200, 'lgb_tp1_1130_1300_seed{}.txt', False),
}
TRAIN_DAYS = 365
N_SEEDS = 5

CFG = dict(
    objective='binary', learning_rate=0.03, num_leaves=8, max_depth=3,
    min_child_samples=50, reg_alpha=1.0, reg_lambda=5.0, n_estimators=300,
    verbose=-1, n_jobs=4,
)


def add_interactions(df):
    df['gain_x_spy'] = df['gain_from_open'].fillna(0) * df['spy_intra'].fillna(0)
    df['vol_x_mcap'] = df['vol_ratio'].fillna(1) * df['mcap_bucket'].fillna(1)
    df['gain_x_xlk'] = df['gain_from_open'].fillna(0) * df['xlk_intra'].fillna(0)
    df['gain_div_vix'] = df['gain_from_open'].fillna(0) / (df['vix'].fillna(20) / 20.0)
    df['range_pullback'] = df['range_pct'].fillna(0) * (5 - df['gain_from_open'].fillna(0).clip(0, 5))
    return df


def train_bucket(df, feats_avail, bucket_key, spec, end_date):
    mfo_lo, mfo_hi, model_pattern, use_inter = spec
    feats = feats_avail + (INTERACTIONS if use_inter else [])
    cutoff = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    train_mask = (
        (df['date'] >= cutoff) & (df['date'] <= end_date) &
        (df['mins_from_open'] >= mfo_lo) & (df['mins_from_open'] <= mfo_hi)
    )
    df_train = df[train_mask]
    print(f"\n=== Bucket {bucket_key} (mfo {mfo_lo}-{mfo_hi}) ===")
    print(f"Features: {len(feats)} ({'with interactions' if use_inter else 'base only'})")
    print(f"Training rows: {len(df_train):,}  cutoff {cutoff} → {end_date}")

    if len(df_train) < 5000:
        print(f"ERROR: too few training rows ({len(df_train)})", file=sys.stderr)
        return False

    X = df_train[feats].fillna(0).values
    y = (df_train['label_decay'] >= 1.0).astype(int).values
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
    args = ap.parse_args()

    print(f"Loading {V21_PKL}...")
    df = pd.read_pickle(V21_PKL)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

    feats = V7_FEATS + CROSS_FEATS
    feats_avail = [f for f in feats if f in df.columns]
    missing = [f for f in feats if f not in df.columns]
    if missing:
        print(f"WARN: missing features in pkl: {missing}", file=sys.stderr)
    print(f"Base features: {len(feats_avail)} ({len(V7_FEATS)} V7 + {len(CROSS_FEATS)} cross)")

    for c in feats_avail + ['label_decay']:
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
        train_bucket(df, feats_avail, key, BUCKET_SPECS[key], args.end_date)

    print(f"\n✅ v20.1 models saved to {OUT_DIR}")


if __name__ == '__main__':
    main()
