"""H12-A Z1 — V-2 production training (single cutoff = serving).

Trains Z1 win model using V-2 architecture for production deployment:
  Stage 1: Generalist (840d × all sectors)
  Stage 2: Sector specialists (840d × sector, warm-start from generalist)

Saves serving models to backtests/models_prod_v23_h12a/Z1/
  - generalist_seed{0..4}.txt  (5 boosters)
  - sector_{name}_seed{0..4}.txt  (5 × 11 sectors = 55 boosters)
  - cell_rating_z1.json  (per-sector WR/avg from training)

Usage:
  python3 scripts/train_h12a_v2_z1.py [--cutoff 2026-06-07]
"""
import argparse, json, sys, sqlite3, time, warnings
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd, numpy as np, lightgbm as lgb
warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backtests'))
from train_v22 import add_interactions

WIN_THR = 0.75
TRAIN_DAYS = 840
SEEDS = [0, 1, 2, 3, 4]
LABEL = 'label_z12_market_3dd'
MFO_RANGE = (0, 9)

GEN_HP = dict(learning_rate=0.05, max_depth=3, num_leaves=24, min_child_samples=50,
              reg_alpha=1.0, reg_lambda=1.0, n_estimators=500,
              bagging_fraction=0.8, feature_fraction=0.9)
FT_HP = dict(learning_rate=0.01, max_depth=3, num_leaves=24, min_child_samples=20,
             reg_alpha=1.0, reg_lambda=1.0,
             bagging_fraction=0.8, feature_fraction=0.9,
             objective='binary', verbose=-1, n_jobs=4)
FT_ROUNDS = 100
MIN_SECTOR_ROWS = 200

MAJOR_SECTORS = ['Technology', 'Industrials', 'Consumer Cyclical', 'Financial Services',
                 'Basic Materials', 'Healthcare', 'Energy', 'Communication Services',
                 'Consumer Defensive', 'Utilities', 'Real Estate']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cutoff', default=None,
                        help='Train cutoff date YYYY-MM-DD (default: today)')
    parser.add_argument('--pkl', default=str(ROOT / 'cache/bt_features/features_5yr_noleak.pkl'))
    parser.add_argument('--labels-pkl', default='/tmp/phase0_labels_5yr.pkl')
    parser.add_argument('--out', default=str(ROOT / 'backtests/models_prod_v23_h12a/Z1'))
    args = parser.parse_args()

    cutoff = args.cutoff or datetime.now().strftime('%Y-%m-%d')
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[H12-A train Z1] cutoff={cutoff} out={out_dir}")
    print(f"  Architecture: V-2 (840d generalist → sector specialist FT)")
    print(f"  Label: {LABEL}")
    print(f"  Stage1 HP: lr={GEN_HP['learning_rate']} depth={GEN_HP['max_depth']} "
          f"trees={GEN_HP['n_estimators']} seeds={len(SEEDS)}")

    t0 = time.time()
    print(f"\n[load] {args.pkl}")
    df = pd.read_pickle(args.pkl)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    lab = pd.read_pickle(args.labels_pkl)
    df = df.merge(lab[['sym','date','mins_from_open','pnl_EOD']],
                  on=['sym','date','mins_from_open'], how='inner')
    df = add_interactions(df)

    # Sector map
    con = sqlite3.connect(str(ROOT / 'data/trade_history.db'))
    SEC = {s:sec for s, sec in con.execute(
        "SELECT symbol, sector FROM stock_fundamentals WHERE sector IS NOT NULL").fetchall()}
    con.close()
    df['sector_full'] = df['sym'].map(SEC).fillna('Other')

    # Filter to zone + train window
    cut_start = (datetime.strptime(cutoff, '%Y-%m-%d') - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    mfo_lo, mfo_hi = MFO_RANGE
    train = df[(df.mins_from_open >= mfo_lo) & (df.mins_from_open <= mfo_hi) &
               (df.date >= cut_start) & (df.date < cutoff) &
               (df[LABEL].notna())]
    print(f"  Train data: {len(train):,} rows from {cut_start} to {cutoff}")
    print(f"  Positive rate: {(train[LABEL]==1).mean()*100:.1f}%")

    feats = [f for f in open(ROOT / 'backtests/models_prod_v22/features_zone_z1.txt').read().split()
             if f in df.columns]
    print(f"  Features: {len(feats)}")

    X_tr = train[feats].fillna(0).values
    y_tr = train[LABEL].astype(int).values

    # === STAGE 1: Generalist boosters (5 seeds) ===
    print(f"\n[stage1] Training generalist boosters (5 seeds)...")
    gen_boosters = []
    for seed in SEEDS:
        params = {k: v for k, v in GEN_HP.items() if k != 'n_estimators'}
        params.update(objective='binary', verbose=-1, n_jobs=4, bagging_freq=1, seed=seed)
        ds = lgb.Dataset(X_tr, label=y_tr)
        b = lgb.train(params, ds, num_boost_round=GEN_HP['n_estimators'])
        gen_boosters.append(b)
        out_path = out_dir / f'generalist_seed{seed}.txt'
        b.save_model(str(out_path))
    print(f"  Saved 5 generalist boosters")

    # === STAGE 2: Sector specialists (warm-start) ===
    print(f"\n[stage2] Training sector specialists (warm-start FT)...")
    sectors_done = []
    for sec in MAJOR_SECTORS:
        tr_sec = train[train.sector_full == sec]
        if len(tr_sec) < MIN_SECTOR_ROWS:
            print(f"  {sec:<25} SKIP (only {len(tr_sec)} rows < {MIN_SECTOR_ROWS})")
            continue
        X_sec = tr_sec[feats].fillna(0).values
        y_sec = tr_sec[LABEL].astype(int).values
        for seed_idx, gen_b in enumerate(gen_boosters):
            ft_params = {**FT_HP, 'bagging_freq': 1, 'seed': SEEDS[seed_idx]}
            ds = lgb.Dataset(X_sec, label=y_sec)
            ft_b = lgb.train(ft_params, ds, num_boost_round=FT_ROUNDS, init_model=gen_b)
            sec_safe = sec.replace(' ', '_').replace('/', '_')
            out_path = out_dir / f'sector_{sec_safe}_seed{SEEDS[seed_idx]}.txt'
            ft_b.save_model(str(out_path))
        sectors_done.append(sec)
        print(f"  {sec:<25} OK ({len(tr_sec)} rows × 5 seeds)")

    # === Save metadata ===
    meta = {
        'zone': 'Z1',
        'arch': 'V-2',
        'label': LABEL,
        'cutoff': cutoff,
        'train_days': TRAIN_DAYS,
        'mfo_range': list(MFO_RANGE),
        'features': feats,
        'sectors': sectors_done,
        'seeds': SEEDS,
        'gen_hp': {k: v for k, v in GEN_HP.items()},
        'ft_hp': {k: v for k, v in FT_HP.items()},
        'ft_rounds': FT_ROUNDS,
        'train_rows': len(train),
        'positive_rate': float((train[LABEL]==1).mean()),
        'trained_at': datetime.now().isoformat(),
    }
    with open(out_dir / 'meta.json', 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"\n[done] elapsed {(time.time()-t0)/60:.1f} min")
    print(f"  Out: {out_dir}")
    print(f"  Sectors trained: {len(sectors_done)}/{len(MAJOR_SECTORS)}")
    print(f"  Total models: {len(SEEDS) * (1 + len(sectors_done))} files")


if __name__ == '__main__':
    main()
