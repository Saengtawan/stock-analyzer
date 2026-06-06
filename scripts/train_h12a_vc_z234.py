"""H12-A Z2/Z3/Z4 — V-C production training (dual-axis warm-start).

Trains Z2/Z3/Z4 win models using V-C architecture for production deployment:
  Stage 1: Generalist (840d × all sectors)
  Stage 2: Sector × regime specialists (last 90d × sector, warm-start)

Saves serving models to backtests/models_prod_v23_h12a/Z{N}/
  - generalist_seed{0..4}.txt
  - sector_{name}_seed{0..4}.txt
  - meta.json

Usage:
  python3 scripts/train_h12a_vc_z234.py [--cutoff 2026-06-07] [--zones Z2,Z3,Z4]
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
REGIME_DAYS = 90
SEEDS = [0, 1, 2, 3, 4]
FT_ROUNDS = 80
MIN_FT_ROWS = 50

# Per-zone config (from H12-A spec)
ZONE_CONFIG = {
    'Z2': {
        'label': 'label_z12_market_3dd',  # CHANGED from label_eod_green_v2 (H12-A fix)
        'mfo_range': (10, 29),
        'gen_hp': dict(learning_rate=0.03, max_depth=5, num_leaves=47, min_child_samples=80,
                       reg_alpha=0.5, reg_lambda=3.0, n_estimators=500,
                       bagging_fraction=0.8, feature_fraction=0.8),
        'ft_hp': dict(learning_rate=0.005, max_depth=5, num_leaves=47, min_child_samples=30,
                      reg_alpha=0.5, reg_lambda=3.0,
                      bagging_fraction=0.8, feature_fraction=0.8,
                      objective='binary', verbose=-1, n_jobs=4),
    },
    'Z3': {
        'label': 'label_z34_market',
        'mfo_range': (30, 44),
        'gen_hp': dict(learning_rate=0.05, max_depth=4, num_leaves=31, min_child_samples=30,
                       reg_alpha=0.5, reg_lambda=1.0, n_estimators=300,
                       bagging_fraction=0.8, feature_fraction=0.8),
        'ft_hp': dict(learning_rate=0.01, max_depth=4, num_leaves=31, min_child_samples=15,
                      reg_alpha=0.5, reg_lambda=1.0,
                      bagging_fraction=0.8, feature_fraction=0.8,
                      objective='binary', verbose=-1, n_jobs=4),
    },
    'Z4': {
        'label': 'label_z34_market',
        'mfo_range': (45, 75),
        'gen_hp': dict(learning_rate=0.05, max_depth=3, num_leaves=8, min_child_samples=30,
                       reg_alpha=1.0, reg_lambda=3.0, n_estimators=400,
                       bagging_fraction=0.7, feature_fraction=0.7),
        'ft_hp': dict(learning_rate=0.01, max_depth=3, num_leaves=8, min_child_samples=15,
                      reg_alpha=1.0, reg_lambda=3.0,
                      bagging_fraction=0.7, feature_fraction=0.7,
                      objective='binary', verbose=-1, n_jobs=4),
    },
}

MAJOR_SECTORS = ['Technology', 'Industrials', 'Consumer Cyclical', 'Financial Services',
                 'Basic Materials', 'Healthcare', 'Energy', 'Communication Services',
                 'Consumer Defensive', 'Utilities', 'Real Estate']


def train_zone(zone, df, cutoff, out_base):
    cfg = ZONE_CONFIG[zone]
    LABEL = cfg['label']
    mfo_lo, mfo_hi = cfg['mfo_range']
    GEN_HP = cfg['gen_hp']
    FT_HP = cfg['ft_hp']

    out_dir = out_base / zone
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[{zone}] V-C train | label={LABEL} | mfo={mfo_lo}-{mfo_hi}")

    # Train window: full 840d for generalist; last 90d for sector FT
    cut_start_840 = (datetime.strptime(cutoff, '%Y-%m-%d') - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    cut_start_90 = (datetime.strptime(cutoff, '%Y-%m-%d') - timedelta(days=REGIME_DAYS)).strftime('%Y-%m-%d')

    z = df[(df.mins_from_open >= mfo_lo) & (df.mins_from_open <= mfo_hi)]
    train_840 = z[(z.date >= cut_start_840) & (z.date < cutoff) & (z[LABEL].notna())]
    train_90 = train_840[train_840.date >= cut_start_90]
    print(f"  Train 840d: {len(train_840):,} rows | Train 90d (regime): {len(train_90):,} rows")
    print(f"  Positive rate (840d): {(train_840[LABEL]==1).mean()*100:.1f}%")

    feats = [f for f in open(ROOT / f'backtests/models_prod_v22/features_zone_{zone.lower()}.txt').read().split()
             if f in df.columns]
    print(f"  Features: {len(feats)}")

    X_840 = train_840[feats].fillna(0).values
    y_840 = train_840[LABEL].astype(int).values

    # === STAGE 1: Generalist (840d) ===
    print(f"  [stage1] Generalist boosters (840d, 5 seeds)...")
    gen_boosters = []
    for seed in SEEDS:
        params = {k: v for k, v in GEN_HP.items() if k != 'n_estimators'}
        params.update(objective='binary', verbose=-1, n_jobs=4, bagging_freq=1, seed=seed)
        ds = lgb.Dataset(X_840, label=y_840)
        b = lgb.train(params, ds, num_boost_round=GEN_HP['n_estimators'])
        gen_boosters.append(b)
        b.save_model(str(out_dir / f'generalist_seed{seed}.txt'))

    # === STAGE 2: Sector × regime specialists (90d × sector, warm-start) ===
    print(f"  [stage2] Sector specialists (90d FT, warm-start)...")
    sectors_done = []
    for sec in MAJOR_SECTORS:
        tr_sec = train_90[train_90.sector_full == sec]
        if len(tr_sec) < MIN_FT_ROWS:
            print(f"    {sec:<25} SKIP ({len(tr_sec)} < {MIN_FT_ROWS})")
            continue
        X_sec = tr_sec[feats].fillna(0).values
        y_sec = tr_sec[LABEL].astype(int).values
        for seed_idx, gen_b in enumerate(gen_boosters):
            ft_params = {**FT_HP, 'bagging_freq': 1, 'seed': SEEDS[seed_idx]}
            ds = lgb.Dataset(X_sec, label=y_sec)
            ft_b = lgb.train(ft_params, ds, num_boost_round=FT_ROUNDS, init_model=gen_b)
            sec_safe = sec.replace(' ', '_').replace('/', '_')
            ft_b.save_model(str(out_dir / f'sector_{sec_safe}_seed{SEEDS[seed_idx]}.txt'))
        sectors_done.append(sec)
        print(f"    {sec:<25} OK ({len(tr_sec)} × 5 seeds)")

    meta = {
        'zone': zone,
        'arch': 'V-C',
        'label': LABEL,
        'cutoff': cutoff,
        'train_days': TRAIN_DAYS,
        'regime_days': REGIME_DAYS,
        'mfo_range': list(cfg['mfo_range']),
        'features': feats,
        'sectors': sectors_done,
        'seeds': SEEDS,
        'gen_hp': {k: v for k, v in GEN_HP.items()},
        'ft_hp': {k: v for k, v in FT_HP.items()},
        'ft_rounds': FT_ROUNDS,
        'train_rows_840': len(train_840),
        'train_rows_90': len(train_90),
        'positive_rate': float((train_840[LABEL]==1).mean()),
        'trained_at': datetime.now().isoformat(),
    }
    with open(out_dir / 'meta.json', 'w') as f:
        json.dump(meta, f, indent=2)
    return sectors_done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cutoff', default=None)
    parser.add_argument('--pkl', default=str(ROOT / 'cache/bt_features/features_5yr_noleak.pkl'))
    parser.add_argument('--labels-pkl', default='/tmp/phase0_labels_5yr.pkl')
    parser.add_argument('--out', default=str(ROOT / 'backtests/models_prod_v23_h12a'))
    parser.add_argument('--zones', default='Z2,Z3,Z4', help='Comma-separated zones to train')
    args = parser.parse_args()

    cutoff = args.cutoff or datetime.now().strftime('%Y-%m-%d')
    zones_list = [z.strip() for z in args.zones.split(',')]
    out_base = Path(args.out)

    print(f"[H12-A train V-C] cutoff={cutoff} zones={zones_list} out={out_base}")

    t0 = time.time()
    print(f"\n[load] {args.pkl}")
    df = pd.read_pickle(args.pkl)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    lab = pd.read_pickle(args.labels_pkl)
    df = df.merge(lab[['sym','date','mins_from_open','pnl_EOD']],
                  on=['sym','date','mins_from_open'], how='inner')
    df = add_interactions(df)

    con = sqlite3.connect(str(ROOT / 'data/trade_history.db'))
    SEC = {s:sec for s, sec in con.execute(
        "SELECT symbol, sector FROM stock_fundamentals WHERE sector IS NOT NULL").fetchall()}
    con.close()
    df['sector_full'] = df['sym'].map(SEC).fillna('Other')

    summary = {}
    for zone in zones_list:
        if zone not in ZONE_CONFIG:
            print(f"[skip] unknown zone {zone}"); continue
        sectors = train_zone(zone, df, cutoff, out_base)
        summary[zone] = len(sectors)

    print(f"\n[done] elapsed {(time.time()-t0)/60:.1f} min")
    for z, n in summary.items():
        print(f"  {z}: {n} sectors trained")


if __name__ == '__main__':
    main()
