"""train_exit.py — Train Exit ML models per zone.

Separate from train_zones.py (entry training).

Pipeline:
1. Load pkl, prod entry models (Step 31)
2. Replay all historical entries (per zone)
3. Build post-entry snapshots for each entry
4. Train Exit ML on snapshots (label: EOD > current_price)
5. Save to backtests/models_prod_exit/lgb_exit_{zone}_seed{0-4}.txt

Usage:
    python3 scripts/train_exit.py --end-date 2026-05-21 --zones Z4 \\
        --pkl cache/bt_features/features.pkl
"""
import argparse, sys, sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import lightgbm as lgb

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ / 'backtests'))
from train_v22 import add_interactions

PROD_ENTRY = PROJ / 'backtests' / 'models_prod_v22'
PROD_EXIT = PROJ / 'backtests' / 'models_prod_exit'
BARS_DB = PROJ / 'cache' / 'wf_1min_bars.db'

# Per-zone configs (matches entry models)
ZONE_CFG = {
    'Z4': dict(mfo_range=(45,75), thr=0.50, loss_thr=0.50, buf=(0.000,0.0020), dip=0.009, cw=2.0,
               hp=dict(learning_rate=0.0827, max_depth=5, num_leaves=5, min_child_samples=69,
                       reg_alpha=3.859, reg_lambda=4.159, n_estimators=800,
                       bagging_fraction=0.889, feature_fraction=0.869)),
}
EXIT_HP = dict(learning_rate=0.05, max_depth=5, num_leaves=20, n_estimators=400,
               min_child_samples=50, reg_alpha=1.0, reg_lambda=2.0,
               bagging_fraction=0.8, feature_fraction=0.8)
TRAIN_DAYS = 840
N_SEEDS = 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end-date', default=datetime.today().strftime('%Y-%m-%d'))
    ap.add_argument('--pkl', default='cache/bt_features/features.pkl')
    ap.add_argument('--zones', nargs='+', default=['Z4'])
    args = ap.parse_args()

    end_dt = datetime.strptime(args.end_date, '%Y-%m-%d')
    cutoff = end_dt.strftime('%Y-%m-%d')
    train_start = (end_dt - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')

    print(f"=== Train Exit ML ===")
    print(f"  Train window: {train_start} → {cutoff}\n")

    df = pd.read_pickle(args.pkl)
    df = add_interactions(df)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    train_df = df[(df['date'] >= train_start) & (df['date'] < cutoff)]

    PROD_EXIT.mkdir(parents=True, exist_ok=True)
    for zone in args.zones:
        if zone not in ZONE_CFG:
            print(f"  ⚠️ Zone {zone} not configured, skip")
            continue
        cfg = ZONE_CFG[zone]
        print(f"\n=== {zone} ===")
        prod_feats = [l.strip() for l in open(PROD_ENTRY/f'features_zone_{zone.lower()}.txt') if l.strip()]
        loss_models = [lgb.Booster(model_file=str(PROD_ENTRY/f'lgb_loss_{zone}_seed{s}.txt')) for s in range(5)]
        adapt_models = [lgb.Booster(model_file=str(PROD_ENTRY/f'lgb_adaptlim_{zone}_seed{s}.txt')) for s in range(5)]

        # Cache bars
        sym_dates = train_df[train_df['mins_from_open'].between(*cfg['mfo_range'])][['sym','date']].drop_duplicates()
        bar_cache = {}
        con = sqlite3.connect(str(BARS_DB))
        for _, row in sym_dates.iterrows():
            rows = con.execute("SELECT em,o,h,l,c FROM bars WHERE sym=? AND date=? ORDER BY em",
                               (row['sym'], row['date'])).fetchall()
            if rows: bar_cache[(row['sym'], row['date'])] = rows
        con.close()
        print(f"  Cached {len(bar_cache)} pairs")

        # Train entry models
        print(f"  Training entry models...")
        scan_mfos = [m for m in range(0,76,5) if cfg['mfo_range'][0]<=m<=cfg['mfo_range'][1]]
        z = train_df[train_df['mins_from_open'].isin(scan_mfos)]
        if 'gain_from_prev' in z.columns:
            z = z[(z['gain_from_prev'] >= 2) & (z['gain_from_prev'] < 5)]
        z = z.dropna(subset=['label_custom_dd'])
        X = z[prod_feats].fillna(0).values; y = z['label_custom_dd'].values
        sw = np.where(y == 0, cfg['cw'], 1.0) if cfg['cw'] else None
        win_models = [lgb.LGBMClassifier(**cfg['hp'], random_state=s, verbose=-1).fit(X, y, sample_weight=sw) for s in range(N_SEEDS)]

        # Replay + build snapshots
        print(f"  Replaying entries...")
        entries = _replay_entries(train_df, win_models, loss_models, adapt_models, cfg, scan_mfos, prod_feats, bar_cache)
        print(f"    {len(entries)} entries")
        print(f"  Building snapshots...")
        X_tr, y_tr = _build_snapshots(entries)
        print(f"    {len(X_tr)} snapshots")

        # Train Exit ML
        print(f"  Training Exit ML ({N_SEEDS} seeds)...")
        for s in range(N_SEEDS):
            m = lgb.LGBMClassifier(**EXIT_HP, random_state=s, verbose=-1, objective='binary')
            m.fit(X_tr, y_tr)
            m.booster_.save_model(str(PROD_EXIT / f'lgb_exit_{zone}_seed{s}.txt'))
        print(f"  ✅ Saved 5 exit models to {PROD_EXIT}/")


def _replay_entries(df_period, win_models, loss_models, adapt_models, cfg, scan_mfos, prod_feats, bar_cache):
    z = df_period[df_period['mins_from_open'].isin(scan_mfos)]
    if 'gain_from_prev' in z.columns:
        z = z[(z['gain_from_prev'] >= 2) & (z['gain_from_prev'] < 5)]
    entries = []
    for date_str in sorted(z['date'].unique()):
        day = z[z['date'] == date_str]; recent = set()
        for mfo in scan_mfos:
            zg = day[day['mins_from_open'] == mfo].copy()
            zg = zg[~zg['sym'].isin(recent)]
            if len(zg) == 0: continue
            X = zg[prod_feats].fillna(0).values
            win_p = np.array([m.predict_proba(X)[:,1] for m in win_models]).min(axis=0)
            loss_p = np.array([m.predict(X) for m in loss_models]).max(axis=0)
            pred_r = np.array([m.predict(X) for m in adapt_models]).mean(axis=0)
            valid = (win_p >= cfg['thr']) & (loss_p < cfg['loss_thr'])
            if cfg.get('dip'):
                valid &= (1-pred_r) >= cfg['dip']
            if not valid.any(): continue
            idx = np.where(valid)[0]; top = idx[win_p[idx].argmax()]
            pick = zg.iloc[top]; sym = pick['sym']; recent.add(sym)
            bars = bar_cache.get((sym, date_str))
            if not bars: continue
            atr = float(pick.get('feat_atr_pct_14d', 3.0))
            bb,bc = cfg['buf']; pr = float(pred_r[top])
            entry_em = 570+int(mfo); scan_p=None; eod=None; bars_after=[]
            for em,o,h,l,c in bars:
                if em == entry_em and c and c>0: scan_p = c
                if em > entry_em+1: bars_after.append((em,o,h,l,c))
                if c and c>0: eod = c
            if scan_p is None or eod is None or not bars_after: continue
            limit_price = scan_p*pr*(1+bb+bc*atr)
            lows = [b[3] for b in bars_after if b[3] and b[3]>0]
            if min(lows) > limit_price: continue
            entries.append({'sym':sym,'date':date_str,'mfo':mfo,'entry_em':entry_em,
                          'entry_price':limit_price,'eod':eod,'bars':bars,
                          'entry_win_p':float(win_p[top]),'entry_pred_r':float(pred_r[top]),
                          'atr':atr,'entry_pkl_feats':pick[prod_feats].fillna(0).values})
    return entries


def _build_snapshots(entries):
    Xs=[]; ys=[]
    for e in entries:
        sb = [b for b in e['bars'] if b[0]>=570]
        if not sb: continue
        day_open = next((b[1] for b in sb if b[0]==570 and b[1] and b[1]>0), None)
        if day_open is None: continue
        peak=e['entry_price']; last_peak_em=e['entry_em']
        sh = [(em,c,h,l) for em,o,h,l,c in sb if c and c>0]
        for em,c,h,l in sh:
            if em <= e['entry_em']: continue
            if (em - e['entry_em']) % 5 != 0: continue
            mins_since = em - e['entry_em']
            if mins_since < 5: continue
            mins_to_close = 960 - em
            if mins_to_close < 5: break
            if h and h > peak: peak=h; last_peak_em=em
            cp = (c-e['entry_price'])/e['entry_price']*100
            hwm = (peak-e['entry_price'])/e['entry_price']*100
            dd = (c-peak)/peak*100
            bsp = em - last_peak_em
            gfo = (c-day_open)/day_open*100
            sof = [c_ for e_,c_,h_,l_ in sh if e_<=em]
            avg = np.mean(sof); vsa = (c-avg)/avg*100 if avg else 0
            highs = [h_ for e_,c_,h_,l_ in sh if e_<=em and h_ and h_>0]
            lows = [l_ for e_,c_,h_,l_ in sh if e_<=em and l_ and l_>0]
            rt = (max(highs)-min(lows))/day_open*100 if highs and lows else 0
            def pa(t):
                for e_,c_,h_,l_ in sh:
                    if e_==t: return c_
                return None
            c5,c15,c30 = pa(em-5), pa(em-15), pa(em-30)
            l5 = (c-c5)/c5*100 if c5 else 0
            l15 = (c-c15)/c15*100 if c15 else 0
            l30 = (c-c30)/c30*100 if c30 else 0
            future = [(e_,c_,h_,l_) for e_,c_,h_,l_ in sh if e_>em]
            if not future: continue
            L = 1 if future[-1][1] > c else 0
            post = np.array([mins_since,cp,hwm,dd,bsp,mins_to_close,gfo,vsa,rt,l5,l15,l30,
                           e['entry_win_p'],e['entry_pred_r'],e['mfo'],e['atr']])
            Xs.append(np.concatenate([e['entry_pkl_feats'], post]))
            ys.append(L)
    return np.stack(Xs) if Xs else np.zeros((0,88)), np.array(ys)


if __name__ == '__main__':
    main()
