"""STAGING-ONLY zone trainer with path_* features (P6-5a, 2026-05-30).

Identical to scripts/train_zones.py EXCEPT: for Z2 and Z3 the win+loss+adaptlim
feature set is augmented with the 20 compute_path_features() bar-shape features.
Z1 and Z4 are trained EXACTLY as prod (no path) so they cannot regress.

This is a SEPARATE script so the prod trainer (scripts/train_zones.py, used by
monthly_retrain.sh -> writes models_prod_v22) stays untouched. Live ml_filter.py
does NOT compute path feats yet, so these models are STAGING ONLY and must not be
swapped into prod until the live port (P6-5b) lands.

Validated edge (5-seed WF dev/holdout, /tmp/wf_label_sweep.py):
  Z2 +20 path: holdout WR 51->58.5%, tot +3.8->+27 (keep label_eod_green_v2)
  Z3 +20 path: holdout WR 36.4->57.1%, tot -5.3->+6.0 (keep label_z34_market)
  Z1 path inert; Z4 path rejected (single-month mirage) -> both excluded.

Usage:
  python3 scripts/train_zones_path.py \
    --pkl cache/bt_features/features_staging_noleak.pkl \
    --out-dir backtests/models_staging_path --end-date 2026-05-30
"""
import argparse
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import lightgbm as lgb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backtests'))
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, N_SEEDS, add_interactions

# import the prod zone config verbatim so HP/labels stay identical
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_zones import (ZONES, ZONE_LABEL, ZONE_HP, LOSS_HP, ADAPT_HP,
                         TRAIN_DAYS, compute_adaptlim_label)

PATH_FEATS = ['path_r_squared', 'path_peak_diff', 'path_low_diff', 'path_consol_range',
              'path_max_drawdown', 'path_choppiness', 'path_speed_late', 'path_speed_accel',
              'path_momentum_accel', 'path_speed_early', 'path_up_vol_ratio',
              'path_support_touches', 'path_bar_size_trend', 'path_wick_ratio',
              'path_lower_wick_ratio', 'path_gap_ratio', 'path_time_at_high',
              'path_vol_at_peaks', 'path_vwap_slope', 'path_ret_skewness']
# zones that get the path bundle (validated wins only)
ZONE_USE_PATH = {'Z1': False, 'Z2': True, 'Z3': True, 'Z4': False}

CACHE_DB = Path(__file__).resolve().parents[1] / 'cache' / 'wf_1min_bars.db'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end-date', default=datetime.today().strftime('%Y-%m-%d'))
    ap.add_argument('--pkl', default='cache/bt_features/features_staging_noleak.pkl')
    ap.add_argument('--out-dir', default='backtests/models_staging_path')
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()

    print(f"Loading {args.pkl}...", flush=True)
    df = pd.read_pickle(args.pkl)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

    feats_avail = [f for f in V7_FEATS + CROSS_FEATS if f in df.columns]
    NEW_FEATS = sorted([c for c in df.columns if c.startswith('feat_')])
    df = add_interactions(df)
    if len(NEW_FEATS) < 16:
        print(f"  WARN: only {len(NEW_FEATS)} feat_* (expected 16). Pkl stale?")

    miss_path = [c for c in PATH_FEATS if c not in df.columns]
    if miss_path:
        print(f"  ERROR: missing path feats: {miss_path}"); sys.exit(1)

    needed_labels = set(ZONE_LABEL.values()) | {'label_fixed3'}
    missing = [l for l in needed_labels if l not in df.columns]
    if missing:
        print(f"  ERROR: missing labels: {missing}"); sys.exit(1)

    print("Computing adaptive limit label (intraday_low_ratio)...", flush=True)
    df = compute_adaptlim_label(df)

    cutoff = (datetime.strptime(args.end_date, '%Y-%m-%d') - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    print(f"Train window: {cutoff} -> {args.end_date}\n")
    out_dir.mkdir(parents=True, exist_ok=True)

    for zname, lo, hi, use_inter in ZONES:
        feats = feats_avail + (INTERACTIONS if use_inter else []) + NEW_FEATS
        if ZONE_USE_PATH[zname]:
            feats = feats + PATH_FEATS
        win_label = ZONE_LABEL[zname]
        train_mask = (
            (df['date'] >= cutoff) & (df['date'] <= args.end_date) &
            (df['mins_from_open'] >= lo) & (df['mins_from_open'] <= hi)
        )
        sub = df[train_mask]
        tagp = '+PATH' if ZONE_USE_PATH[zname] else ''
        print(f"  {zname} (mfo {lo}-{hi}) {tagp}: {len(sub):,} rows, {len(feats)} feats", flush=True)
        if len(sub) < 1000:
            print("    WARN too few rows, skip"); continue

        X = sub[feats].fillna(0).values

        # 1. Win model
        yw_raw = sub[win_label]
        mask_w = yw_raw.notna()
        X_w = sub[mask_w][feats].fillna(0).values
        y_w = yw_raw[mask_w].astype(int).values
        hp = {**ZONE_HP[zname], 'objective': 'binary', 'bagging_freq': 1, 'verbose': -1, 'n_jobs': 4}
        for seed in range(N_SEEDS):
            m = lgb.LGBMClassifier(**{**hp, 'random_state': seed})
            m.fit(X_w, y_w)
            m.booster_.save_model(str(out_dir / f'lgb_tp1_{zname}_seed{seed}.txt'))
        print(f"    win ({win_label}): pos={y_w.mean():.3f}, saved 5 seeds")

        # 2. Loss model
        yl = (sub['label_fixed3'] <= -1.0).astype(int).values
        hp_l = {**LOSS_HP, 'objective': 'binary', 'bagging_freq': 1, 'verbose': -1, 'n_jobs': 4}
        for seed in range(N_SEEDS):
            m = lgb.LGBMClassifier(**{**hp_l, 'random_state': seed})
            m.fit(X, yl)
            m.booster_.save_model(str(out_dir / f'lgb_loss_{zname}_seed{seed}.txt'))
        print(f"    loss: pos={yl.mean():.3f}, saved 5 seeds")

        # 3. Adaptive limit model
        if 'label_adaptlim' in sub.columns and sub['label_adaptlim'].notna().any():
            mask_a = sub['label_adaptlim'].notna()
            X_a = sub[mask_a][feats].fillna(0).values
            y_a = sub[mask_a]['label_adaptlim'].values
            hp_a = {**ADAPT_HP, 'bagging_freq': 1, 'verbose': -1, 'n_jobs': 4}
            for seed in range(N_SEEDS):
                m = lgb.LGBMRegressor(**{**hp_a, 'random_state': seed})
                m.fit(X_a, y_a)
                m.booster_.save_model(str(out_dir / f'lgb_adaptlim_{zname}_seed{seed}.txt'))
            print(f"    adaptlim: N={mask_a.sum()}, saved 5 seeds")
        else:
            print("    WARN label_adaptlim missing, skip adaptlim")

        (out_dir / f'features_zone_z{zname[1]}.txt').write_text('\n'.join(feats))

    print(f"\nDONE. Staging+path models saved to {out_dir}")


if __name__ == '__main__':
    main()
