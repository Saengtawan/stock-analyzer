"""Train MFO-zone models for ml_filter (Z1/Z2/Z3/Z4) — production-ready.

Usage:
  python3 scripts/train_zones.py --end-date YYYY-MM-DD

Trains 40 models (4 zones × tp1+loss × 5 seeds) on 1y data ending at end-date.
Saves to backtests/models_prod_v22/ as lgb_{tp1,loss}_{Z1-Z4}_seed{0-4}.txt
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backtests'))
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, CFG, N_SEEDS, add_interactions

ZONES = [
    ('Z1', 0, 9, True),
    ('Z2', 10, 29, True),
    ('Z3', 30, 44, False),
    ('Z4', 45, 75, False),
]
TRAIN_DAYS = 840  # 28 months — WF validated 2026-04-30: +1.16pp WR vs 365 (Z2 +11.9pp)
PROD_DIR = Path(__file__).resolve().parents[1] / 'backtests' / 'models_prod_v22'
PKL = '/tmp/bt_features_v27.pkl'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end-date', default=datetime.today().strftime('%Y-%m-%d'))
    ap.add_argument('--pkl', default=PKL)
    args = ap.parse_args()

    print(f"Loading {args.pkl}...", flush=True)
    df = pd.read_pickle(args.pkl)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    feats_avail = [f for f in V7_FEATS+CROSS_FEATS if f in df.columns]
    for c in feats_avail+['label_decay','label_fixed3']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = add_interactions(df)

    cutoff = (datetime.strptime(args.end_date,'%Y-%m-%d') - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    print(f"Train window: {cutoff} → {args.end_date}\n")

    PROD_DIR.mkdir(parents=True, exist_ok=True)

    for zname, lo, hi, use_inter in ZONES:
        feats = feats_avail + (INTERACTIONS if use_inter else [])
        train_mask = (
            (df['date']>=cutoff) & (df['date']<=args.end_date) &
            (df['mins_from_open']>=lo) & (df['mins_from_open']<=hi)
        )
        sub = df[train_mask]
        X = sub[feats].fillna(0).values
        print(f"  {zname} (mfo {lo}-{hi}): {len(sub):,} rows, {len(feats)} feats", flush=True)
        if len(sub) < 1000:
            print(f"    ⚠️ Too few rows, skip", flush=True)
            continue

        for tag, label_col, thr_v, op in [('tp1','label_decay',1.0,'ge'),('loss','label_fixed3',-1.0,'le')]:
            y = (sub[label_col]>=thr_v if op=='ge' else sub[label_col]<=thr_v).astype(int).values
            for seed in range(N_SEEDS):
                m = lgb.LGBMClassifier(**{**CFG, 'random_state':seed})
                m.fit(X, y)
                fp = PROD_DIR / f'lgb_{tag}_{zname}_seed{seed}.txt'
                m.booster_.save_model(str(fp))
            print(f"    {tag}: pos={y.mean():.3f}, saved 5 seeds", flush=True)

    # Save zone feature lists (for scorer to load)
    (PROD_DIR/'features_zone_z1.txt').write_text('\n'.join(feats_avail+INTERACTIONS))
    (PROD_DIR/'features_zone_z2.txt').write_text('\n'.join(feats_avail+INTERACTIONS))
    (PROD_DIR/'features_zone_z3.txt').write_text('\n'.join(feats_avail))
    (PROD_DIR/'features_zone_z4.txt').write_text('\n'.join(feats_avail))

    print(f"\n✅ All zone models saved to {PROD_DIR}")

if __name__ == '__main__':
    main()
