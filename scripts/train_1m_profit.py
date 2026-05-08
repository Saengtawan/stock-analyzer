"""Production retrain for 1m_profit ensemble — Triple Blend partner.

Usage:
  python3 scripts/train_1m_profit.py [--end-date YYYY-MM-DD]

Reads:  cache/bt_features_500_profit_labels.pkl
Writes: backtests/models_prod_v22_1m/lgb_{tp1,loss}_Z{1-4}_seed{0-4}.txt

Trains a SINGLE current model set (not 12-month WF) on most recent 840 days,
matching the production deployment (B2/Triple Blend uses one model, not WF).

Skips with non-zero exit if labels pkl is missing or too stale (>45 days).
"""
import sys, time, argparse
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd, numpy as np, lightgbm as lgb
sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, N_SEEDS, add_interactions
import warnings; warnings.filterwarnings('ignore')

ROOT = Path('/home/saengtawan/work/project/cc/stock-analyzer')
PKL = ROOT/'cache'/'bt_features_500_profit_labels.pkl'
OUT = ROOT/'backtests'/'models_prod_v22_1m'
TRAIN_DAYS = 840
MAX_PKL_AGE_DAYS = 45
ZONES = [('Z1',0,9,True),('Z2',10,29,True),('Z3',30,44,False),('Z4',45,75,False)]

CFG = {'n_estimators':100, 'learning_rate':0.05, 'num_leaves':63, 'min_child_samples':50,
       'reg_alpha':0.1, 'reg_lambda':0.1, 'feature_fraction':0.8, 'bagging_fraction':0.8,
       'bagging_freq':5, 'objective':'binary', 'metric':'binary_logloss', 'verbose':-1}

ap = argparse.ArgumentParser()
ap.add_argument('--end-date', default=datetime.utcnow().strftime('%Y-%m-%d'))
args = ap.parse_args()
end_date = args.end_date
cut = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')

if not PKL.exists():
    print(f"SKIP: {PKL} not found. Generate via: python3 cache/p2_labels_profit.py")
    sys.exit(2)

age = (time.time() - PKL.stat().st_mtime) / 86400
if age > MAX_PKL_AGE_DAYS:
    print(f"SKIP: {PKL} is {age:.0f}d old (>{MAX_PKL_AGE_DAYS}d). Refresh 1-min bars + run p2_labels_profit.py")
    sys.exit(2)

OUT.mkdir(parents=True, exist_ok=True)

print(f"[{datetime.utcnow():%Y-%m-%d %H:%M:%S}] Loading {PKL}...")
df = pd.read_pickle(PKL)
df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
feats_avail = [f for f in V7_FEATS+CROSS_FEATS if f in df.columns]
for c in feats_avail + ['label_profit_1m', 'label_loss_profit_1m']:
    if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
df = add_interactions(df)
has = df['label_profit_1m'].notna() & df['label_loss_profit_1m'].notna()
df = df[has].copy()
print(f"  Labeled rows: {len(df):,}")
print(f"  Train window: {cut} → {end_date}")

t0 = time.time()
trained = 0
for zname, lo, hi, use_inter in ZONES:
    feats = feats_avail + (INTERACTIONS if use_inter else [])
    m = (df['date']>=cut) & (df['date']<=end_date) & \
        (df['mins_from_open']>=lo) & (df['mins_from_open']<=hi)
    sub = df[m]
    if len(sub) < 1000:
        print(f"  {zname}: only {len(sub)} rows, skip")
        continue
    X = sub[feats].fillna(0).values
    print(f"  {zname} (mfo {lo}-{hi}): {len(sub):,} rows, {len(feats)} feats", flush=True)
    for tag, lbl in [('tp1','label_profit_1m'), ('loss','label_loss_profit_1m')]:
        y = (sub[lbl] >= 0.5).astype(int).values
        pos = y.mean()
        print(f"    {tag}: pos={pos:.3f}", flush=True)
        for s in range(N_SEEDS):
            mdl = lgb.LGBMClassifier(**{**CFG, 'random_state':s})
            mdl.fit(X, y)
            out_path = OUT / f'lgb_{tag}_{zname}_seed{s}.txt'
            mdl.booster_.save_model(str(out_path))
            trained += 1

print(f"\n[{datetime.utcnow():%Y-%m-%d %H:%M:%S}] Done in {(time.time()-t0)/60:.1f}min")
print(f"  Saved {trained} model files → {OUT}")
