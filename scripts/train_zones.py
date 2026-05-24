"""Train MFO-zone models for ml_filter (Step 18 — 2026-05-14).

Trains all 60 models: 4 zones × (win + loss + adaptlim) × 5 seeds.

Per-zone config (Step 24 — 2026-05-17):
  Z1: label=label_z12_market_3dd, lr=0.05, depth=3, leaves=24, n_est=500
  Z2: label=label_custom_dd,      lr=0.03, depth=5, leaves=47, n_est=500  # Step 24
  Z3: label=label_z34_market,     lr=0.05, depth=4, leaves=31, n_est=300
  Z4: label=label_z34_market,     lr=0.05, depth=3, leaves=8,  n_est=400

Adaptive limit (Step 7): regression on label `intraday_low_ratio`
(min(low after scan) / scan_price). Generated on-the-fly from cache/wf_1min_bars.db.

Loss model: trained on label_fixed3 ≤ -1% (binary).

Usage:
  python3 scripts/train_zones.py --end-date 2026-05-14 \\
    --pkl cache/bt_features/features.pkl
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

ZONES = [
    ('Z1', 0, 9, True),
    ('Z2', 10, 29, True),
    ('Z3', 30, 44, False),
    ('Z4', 45, 75, False),
]

ZONE_LABEL = {
    # Step 26 (2026-05-17): Z3+Z4 → label_custom_dd (A1 +59% WF)
    # Step 33 (2026-05-24) v2.6.0: Z3+Z4 → label_smart_v2 (TRIPLE_B
    #   Phase 4 OOS +22.7%, Phase 3 5/5 positive, 2/2 CRITICAL PASS)
    'Z1': 'label_z12_market_3dd',
    'Z2': 'label_custom_dd',
    'Z3': 'label_smart_v2',    # Step 33 v2.6.0: TRIPLE_B
    'Z4': 'label_smart_v2',    # Step 33 v2.6.0: TRIPLE_B
}

ZONE_HP = {
    # Step 26 (2026-05-17): Optuna-optimized HPs (A2 experiment +137% val total)
    # Step 31 (2026-05-21): Z2+Z4 re-tuned with label_custom_dd + cw=2.0 setup.
    #   Phase 2 6-mo refit: Z2 +9.7% Total, Z4 +6.1%. Phase 4 30-day OOS: Z4 worst -2.96% → +0.03%.
    'Z1': dict(learning_rate=0.0678, max_depth=2, num_leaves=40, min_child_samples=44,
               reg_alpha=3.463, reg_lambda=3.818, n_estimators=600,
               bagging_fraction=0.945, feature_fraction=0.926),
    'Z2': dict(learning_rate=0.0970, max_depth=2, num_leaves=56, min_child_samples=120,
               reg_alpha=3.345, reg_lambda=4.341, n_estimators=400,
               bagging_fraction=0.820, feature_fraction=0.841),
    'Z3': dict(learning_rate=0.0435, max_depth=2, num_leaves=28, min_child_samples=99,
               reg_alpha=1.466, reg_lambda=4.900, n_estimators=600,
               bagging_fraction=0.884, feature_fraction=0.950),
    'Z4': dict(learning_rate=0.0827, max_depth=5, num_leaves=5, min_child_samples=69,
               reg_alpha=3.859, reg_lambda=4.159, n_estimators=800,
               bagging_fraction=0.889, feature_fraction=0.869),
}
# Step 29 (2026-05-20): class weighting on losers in win model.
# Validated Z3 Phase 2 ΔWR +2.6pp / Phase 3 4/5 regimes pass.
# Validated Z4 Phase 2 ΔT +1.7% ΔWR +0.6pp ΔWorst +0.54pp / Phase 3 4/5 + 3/3 critical.
ZONE_CW = {'Z1': None, 'Z2': None, 'Z3': 2.0, 'Z4': 2.0}
LOSS_HP = dict(learning_rate=0.03, max_depth=3, num_leaves=8, min_child_samples=50,
               reg_alpha=1.0, reg_lambda=5.0, n_estimators=300,
               bagging_fraction=0.8, feature_fraction=0.8)
ADAPT_HP = dict(objective='regression', learning_rate=0.05, max_depth=4, num_leaves=15,
                min_child_samples=30, reg_alpha=0.5, reg_lambda=1.0, n_estimators=300,
                bagging_fraction=0.8, feature_fraction=0.8)

TRAIN_DAYS = 840  # 28 months
PROD_DIR = Path(__file__).resolve().parents[1] / 'backtests' / 'models_prod_v22'
CACHE_DB = Path(__file__).resolve().parents[1] / 'cache' / 'wf_1min_bars.db'


def compute_adaptlim_label(df):
    """For each row, compute intraday_low_ratio = min(low after scan) / scan_price.

    Returns df with new 'label_adaptlim' column.
    """
    if not CACHE_DB.exists():
        print(f"  ⚠️ {CACHE_DB} missing — skip adaptive limit training")
        df['label_adaptlim'] = np.nan
        return df

    con = sqlite3.connect(str(CACHE_DB))
    sym_dates = df[['sym','date']].drop_duplicates().itertuples(index=False)
    bar_cache = {}
    for sym, date in sym_dates:
        rows = con.execute("SELECT em, l, c FROM bars WHERE sym=? AND date=? ORDER BY em",(sym,date)).fetchall()
        if rows: bar_cache[(sym, date)] = rows
    con.close()

    ratios = []
    for _, r in df.iterrows():
        bars = bar_cache.get((r['sym'], r['date']))
        if not bars: ratios.append(np.nan); continue
        target_em = 570 + int(r['mins_from_open'])
        scan_p = None; lows = []
        for em, l, c in bars:
            if em == target_em and c and c > 0: scan_p = c
            if em > target_em and l and l > 0: lows.append(l)
        if scan_p is None or not lows: ratios.append(np.nan); continue
        ratios.append(min(lows) / scan_p)
    df['label_adaptlim'] = ratios
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end-date', default=datetime.today().strftime('%Y-%m-%d'))
    ap.add_argument('--pkl', default='cache/bt_features/features.pkl')
    args = ap.parse_args()

    print(f"Loading {args.pkl}...", flush=True)
    df = pd.read_pickle(args.pkl)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

    feats_avail = [f for f in V7_FEATS+CROSS_FEATS if f in df.columns]
    NEW_FEATS = sorted([c for c in df.columns if c.startswith('feat_')])
    df = add_interactions(df)
    if len(NEW_FEATS) < 16:
        print(f"  ⚠️ Only {len(NEW_FEATS)} feat_* found (expected 16). Pkl may be stale — rebuild via feature_builder.py")

    # Verify required labels present
    needed_labels = set(ZONE_LABEL.values()) | {'label_fixed3'}
    missing = [l for l in needed_labels if l not in df.columns]
    if missing:
        print(f"  ⚠️ Missing labels: {missing}. Rebuild pkl with updated feature_builder.py")
        sys.exit(1)

    # Compute adaptive limit label
    print("Computing adaptive limit label (intraday_low_ratio)...", flush=True)
    df = compute_adaptlim_label(df)

    cutoff = (datetime.strptime(args.end_date,'%Y-%m-%d') - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    print(f"Train window: {cutoff} → {args.end_date}\n")

    PROD_DIR.mkdir(parents=True, exist_ok=True)

    for zname, lo, hi, use_inter in ZONES:
        feats = feats_avail + (INTERACTIONS if use_inter else []) + NEW_FEATS
        win_label = ZONE_LABEL[zname]
        train_mask = (
            (df['date']>=cutoff) & (df['date']<=args.end_date) &
            (df['mins_from_open']>=lo) & (df['mins_from_open']<=hi)
        )
        sub = df[train_mask]
        print(f"  {zname} (mfo {lo}-{hi}): {len(sub):,} rows, {len(feats)} feats", flush=True)
        if len(sub) < 1000:
            print(f"    ⚠️ Too few rows, skip"); continue

        X = sub[feats].fillna(0).values

        # 1. Win model — Step 18 per-zone labels + HP
        if win_label not in sub.columns:
            print(f"    ⚠️ {win_label} missing, skip win")
        else:
            yw_raw = sub[win_label]
            mask_w = yw_raw.notna()
            X_w = sub[mask_w][feats].fillna(0).values
            y_w = yw_raw[mask_w].astype(int).values
            hp = {**ZONE_HP[zname], 'objective':'binary', 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
            cw = ZONE_CW.get(zname)
            sw_w = np.where(y_w == 0, cw, 1.0) if cw and cw > 1.0 else None
            for seed in range(N_SEEDS):
                m = lgb.LGBMClassifier(**{**hp, 'random_state':seed})
                m.fit(X_w, y_w, sample_weight=sw_w)
                m.booster_.save_model(str(PROD_DIR / f'lgb_tp1_{zname}_seed{seed}.txt'))
            cw_tag = f" cw={cw}" if cw else ""
            print(f"    win ({win_label}){cw_tag}: pos={y_w.mean():.3f}, saved 5 seeds")

        # 2. Loss model — label_fixed3 ≤ -1%
        yl = (sub['label_fixed3'] <= -1.0).astype(int).values
        hp_l = {**LOSS_HP, 'objective':'binary', 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
        for seed in range(N_SEEDS):
            m = lgb.LGBMClassifier(**{**hp_l, 'random_state':seed})
            m.fit(X, yl)
            m.booster_.save_model(str(PROD_DIR / f'lgb_loss_{zname}_seed{seed}.txt'))
        print(f"    loss: pos={yl.mean():.3f}, saved 5 seeds")

        # 3. Adaptive limit model — regression on intraday_low_ratio
        if 'label_adaptlim' in sub.columns:
            mask_a = sub['label_adaptlim'].notna()
            X_a = sub[mask_a][feats].fillna(0).values
            y_a = sub[mask_a]['label_adaptlim'].values
            hp_a = {**ADAPT_HP, 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
            for seed in range(N_SEEDS):
                m = lgb.LGBMRegressor(**{**hp_a, 'random_state':seed})
                m.fit(X_a, y_a)
                m.booster_.save_model(str(PROD_DIR / f'lgb_adaptlim_{zname}_seed{seed}.txt'))
            print(f"    adaptlim: N={mask_a.sum()}, saved 5 seeds")
        else:
            print(f"    ⚠️ label_adaptlim missing, skip adaptlim")

        # 4. Step 33 v2.6.0: opt_entry model (Z3/Z4 only) — for per_zone LIMIT
        if zname in ('Z3','Z4') and 'label_opt_entry' in sub.columns:
            mask_o = sub['label_opt_entry'].notna()
            if mask_o.sum() >= 1000:
                X_o = sub[mask_o][feats].fillna(0).values
                y_o = sub[mask_o]['label_opt_entry'].values
                hp_o = {**ADAPT_HP, 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
                for seed in range(N_SEEDS):
                    m = lgb.LGBMRegressor(**{**hp_o, 'random_state':seed})
                    m.fit(X_o, y_o)
                    m.booster_.save_model(str(PROD_DIR / f'lgb_adaptopt_{zname}_seed{seed}.txt'))
                print(f"    adaptopt: N={mask_o.sum()}, saved 5 seeds")
            else:
                print(f"    ⚠️ label_opt_entry insufficient, skip adaptopt")

        # Update zone feature list
        (PROD_DIR / f'features_zone_z{zname[1]}.txt').write_text('\n'.join(feats))

    print(f"\n✅ All zone models saved to {PROD_DIR}")


if __name__ == '__main__':
    main()
