"""Train 49m zone models — bear-regime insurance partner for MoE.

Same architecture as train_zones.py (28m / 840 days) but trained on 49 months
(1470 days), so 2022 bear regime data is included. MoE blends:
  score = w × 28m + (1-w) × 49m
where w = sigmoid((SPY/SPY_50ma - 1) × 50). Bear → 49m takes over.

Usage:
  python3 scripts/train_49m.py [--end-date YYYY-MM-DD]

Reads:  cache/bt_features_v27_500_4yr_full.pkl  (must span ≥49 months)
Writes: backtests/models_prod_v22_49m/lgb_{tp1,loss}_Z{1-4}_seed{0-4}.txt
        backtests/models_prod_v22_49m/features_zone_z{1-4}.txt

Skips with rc=2 if pkl is missing or doesn't span 49 months.
"""
import argparse
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backtests'))
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, CFG, N_SEEDS, add_interactions

ZONES = [
    ('Z1', 0, 9, True),
    ('Z2', 10, 29, True),
    ('Z3', 30, 44, False),
    ('Z4', 45, 75, False),
]
TRAIN_DAYS = 1470  # ~49 months — includes 2022 bear regime
PROD_DIR = ROOT / 'backtests' / 'models_prod_v22_49m'
PKL_DEFAULT = ROOT / 'cache' / 'bt_features_v27_500_4yr_full.pkl'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end-date', default=datetime.utcnow().strftime('%Y-%m-%d'))
    ap.add_argument('--pkl', default=str(PKL_DEFAULT))
    args = ap.parse_args()

    pkl = Path(args.pkl)
    if not pkl.exists():
        print(f"SKIP: {pkl} not found. Run feature_builder.py with --start covering 4y of data.")
        sys.exit(2)

    print(f"[{datetime.utcnow():%Y-%m-%d %H:%M:%S}] Loading {pkl}...", flush=True)
    df = pd.read_pickle(pkl)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    print(f"  {len(df):,} rows, {df['date'].min()} → {df['date'].max()}")

    cutoff = (datetime.strptime(args.end_date, '%Y-%m-%d') - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    if df['date'].min() > cutoff:
        print(f"SKIP: pkl earliest date {df['date'].min()} > 49m cutoff {cutoff}. Pkl too narrow.")
        sys.exit(2)

    print(f"  Train window: {cutoff} → {args.end_date} (49 months)")

    feats_avail = [f for f in V7_FEATS + CROSS_FEATS if f in df.columns]
    missing = [f for f in V7_FEATS + CROSS_FEATS if f not in df.columns]
    if missing:
        print(f"  WARN: missing features: {missing}", file=sys.stderr)
    print(f"  Base features: {len(feats_avail)} ({len(V7_FEATS)} V7 + {len(CROSS_FEATS)} cross)")

    for c in feats_avail + ['label_decay', 'label_fixed3']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    df = add_interactions(df)

    PROD_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    trained = 0

    for zname, lo, hi, use_inter in ZONES:
        feats = feats_avail + (INTERACTIONS if use_inter else [])
        train_mask = (
            (df['date'] >= cutoff) & (df['date'] <= args.end_date) &
            (df['mins_from_open'] >= lo) & (df['mins_from_open'] <= hi)
        )
        sub = df[train_mask]
        print(f"\n  {zname} (mfo {lo}-{hi}): {len(sub):,} rows, {len(feats)} feats", flush=True)
        if len(sub) < 5000:
            print(f"    ⚠️  Too few rows, skip", flush=True)
            continue

        X = sub[feats].fillna(0).values
        for tag, label_col, thr_v, op in [
            ('tp1', 'label_decay', 1.0, 'ge'),
            ('loss', 'label_fixed3', -1.0, 'le'),
        ]:
            y = (sub[label_col] >= thr_v if op == 'ge' else sub[label_col] <= thr_v).astype(int).values
            print(f"    {tag}: pos={y.mean():.3f}", flush=True)
            for seed in range(N_SEEDS):
                m = lgb.LGBMClassifier(**{**CFG, 'random_state': seed})
                m.fit(X, y)
                fp = PROD_DIR / f'lgb_{tag}_{zname}_seed{seed}.txt'
                m.booster_.save_model(str(fp))
                trained += 1

    # Save zone feature lists (scorer reads these to align feature order at inference)
    (PROD_DIR / 'features_zone_z1.txt').write_text('\n'.join(feats_avail + INTERACTIONS))
    (PROD_DIR / 'features_zone_z2.txt').write_text('\n'.join(feats_avail + INTERACTIONS))
    (PROD_DIR / 'features_zone_z3.txt').write_text('\n'.join(feats_avail))
    (PROD_DIR / 'features_zone_z4.txt').write_text('\n'.join(feats_avail))

    print(f"\n[{datetime.utcnow():%Y-%m-%d %H:%M:%S}] Done in {(time.time()-t0)/60:.1f}min")
    print(f"  Saved {trained} model files → {PROD_DIR}")


if __name__ == '__main__':
    main()
