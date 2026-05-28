"""Validate retrained zone models via TRUE OOS single-month WF.

2026-05-16: Fixed lookahead bias — train cutoff = end_date - 30 days
(was end_date which caused test data to be in training set).

Trains validation-only models in-memory with shifted cutoff, tests on
last 30 days. Production models are NOT touched.

Exit code:
  0 = validation passed
  1 = validation FAILED
"""
import argparse, json, sys, sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import lightgbm as lgb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backtests'))
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, N_SEEDS, add_interactions

PROD = Path(__file__).resolve().parents[1] / 'backtests' / 'models_prod_v22'
DB = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'
BARS = Path(__file__).resolve().parents[1] / 'cache' / 'wf_1min_bars.db'
BASELINE = Path(__file__).resolve().parents[1] / 'configs' / 'wf_baseline.json'

ZONE_RANGE = {'Z1':(0,9),'Z2':(10,29),'Z3':(30,44),'Z4':(45,75)}
ZONE_THR = {'Z1':0.60,'Z2':0.65,'Z3':0.50,'Z4':0.50}
ZONE_LOSS_THR = {'Z1':0.40,'Z2':0.20,'Z3':0.40,'Z4':0.50}
# FIX 2026-05-28: ZONE_BUF match ml_scorer.py (Step 27 deployed values)
ZONE_BUF = {'Z1':(0.005,0.0020),'Z2':(0.005,0.0015),'Z3':(0.000,0.0020),'Z4':(0.000,0.0020)}
ZONE_HARD_SL = {}  # Step 25: pure hold all zones
Z4_DIP = 0.009  # Step 23
# Step 35 (2026-05-28): Z3+Z4 → label_real_pnl_05 (Agent D winner)
ZONE_LABEL = {'Z1':'label_z12_market_3dd','Z2':'label_custom_dd','Z3':'label_smart_v2','Z4':'label_smart_v2'}
# Step 33: per_zone LIMIT ensemble weights (Z3/Z4 only)
ZONE_LIMIT_W_R = {'Z3': 0.7, 'Z4': 0.45}  # weight on baseline pred_r (vs pred_opt)

HP = {
    # Step 31 (2026-05-21): Z2+Z4 re-tuned with label_custom_dd + cw=2.0
    'Z1': dict(learning_rate=0.0678, max_depth=2, num_leaves=40, min_child_samples=44, reg_alpha=3.463, reg_lambda=3.818, n_estimators=600, bagging_fraction=0.945, feature_fraction=0.926),
    'Z2': dict(learning_rate=0.0970, max_depth=2, num_leaves=56, min_child_samples=120, reg_alpha=3.345, reg_lambda=4.341, n_estimators=400, bagging_fraction=0.820, feature_fraction=0.841),
    'Z3': dict(learning_rate=0.0435, max_depth=2, num_leaves=28, min_child_samples=99, reg_alpha=1.466, reg_lambda=4.900, n_estimators=600, bagging_fraction=0.884, feature_fraction=0.950),
    'Z4': dict(learning_rate=0.0827, max_depth=5, num_leaves=5, min_child_samples=69, reg_alpha=3.859, reg_lambda=4.159, n_estimators=800, bagging_fraction=0.889, feature_fraction=0.869),
}
# Step 29 (2026-05-20): class weighting on losers — must match train_zones.py
ZONE_CW = {'Z1': None, 'Z2': None, 'Z3': 2.0, 'Z4': 2.0}
LOSS_HP = dict(learning_rate=0.03, max_depth=3, num_leaves=8, min_child_samples=50, reg_alpha=1.0, reg_lambda=5.0, n_estimators=300, bagging_fraction=0.8, feature_fraction=0.8)
ADAPT_HP = dict(objective='regression', learning_rate=0.05, max_depth=4, num_leaves=15, min_child_samples=30, reg_alpha=0.5, reg_lambda=1.0, n_estimators=300, bagging_fraction=0.8, feature_fraction=0.8)
TRAIN_DAYS = 840


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end-date', default=datetime.today().strftime('%Y-%m-%d'))
    ap.add_argument('--pkl', default='cache/bt_features/features.pkl')
    ap.add_argument('--test-days', type=int, default=30, help='days of OOS testing')
    args = ap.parse_args()

    end_dt = datetime.strptime(args.end_date, '%Y-%m-%d')
    test_start = (end_dt - timedelta(days=args.test_days)).strftime('%Y-%m-%d')
    test_end = args.end_date
    # 2026-05-16 FIX: train cutoff = test_start (NOT end_date) — no leak
    train_end = test_start
    train_start = (end_dt - timedelta(days=args.test_days + TRAIN_DAYS)).strftime('%Y-%m-%d')

    print(f"=== Validate retrain (TRUE OOS, no leak) ===", flush=True)
    print(f"  Train window: {train_start} → {train_end}")
    print(f"  Test window:  {test_start} → {test_end}")
    print(f"Loading pkl {args.pkl}...", flush=True)
    baseline = json.loads(BASELINE.read_text())
    df = pd.read_pickle(args.pkl)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    feats_avail = [f for f in V7_FEATS+CROSS_FEATS if f in df.columns]
    NEW_FEATS = sorted([c for c in df.columns if c.startswith('feat_')])
    df = add_interactions(df)
    FEATS_BY_ZONE = {
        'Z1': feats_avail + INTERACTIONS + NEW_FEATS,
        'Z2': feats_avail + INTERACTIONS + NEW_FEATS,
        'Z3': feats_avail + NEW_FEATS,
        'Z4': feats_avail + NEW_FEATS,
    }

    # Need label_adaptlim — compute if missing
    if 'label_adaptlim' not in df.columns:
        print("  Computing label_adaptlim from 1-min cache...", flush=True)
        con_bars = sqlite3.connect(str(BARS))
        sym_dates = df[['sym','date']].drop_duplicates().itertuples(index=False)
        bar_cache = {}
        for sym, date in sym_dates:
            rows = con_bars.execute("SELECT em, l, c FROM bars WHERE sym=? AND date=? ORDER BY em",(sym,date)).fetchall()
            if rows: bar_cache[(sym, date)] = rows
        con_bars.close()
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

    # Train validation models in-memory with no-leak cutoff
    print(f"\nTraining validation models (train ≤ {train_end})...", flush=True)
    win_m, loss_m, adapt_m, adaptopt_m = {}, {}, {}, {}  # adaptopt for Step 33 Z3/Z4
    for zone in ['Z1','Z2','Z3','Z4']:
        feats = FEATS_BY_ZONE[zone]
        LO, HI = ZONE_RANGE[zone]
        mask = (df['date']>=train_start) & (df['date']<train_end) & (df['mins_from_open']>=LO) & (df['mins_from_open']<=HI)
        sub = df[mask]
        if len(sub) < 500:
            print(f"  ⚠️ {zone}: only {len(sub)} train rows, skip")
            continue

        X_full = sub[feats].fillna(0).values
        wl = ZONE_LABEL[zone]
        mw = sub[wl].notna()
        Xw = sub[mw][feats].fillna(0).values
        yw = sub[mw][wl].astype(int).values
        cfg = {**HP[zone], 'objective':'binary', 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
        cw_z = ZONE_CW.get(zone)
        sw_w = np.where(yw == 0, cw_z, 1.0) if cw_z and cw_z > 1.0 else None
        wseeds = []
        for s in range(N_SEEDS):
            m = lgb.LGBMClassifier(**{**cfg, 'random_state':s})
            m.fit(Xw, yw, sample_weight=sw_w)
            wseeds.append(m.booster_)

        yl = (sub['label_fixed3'] <= -1.0).astype(int).values
        hp_l = {**LOSS_HP, 'objective':'binary', 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
        lseeds = []
        for s in range(N_SEEDS):
            m = lgb.LGBMClassifier(**{**hp_l, 'random_state':s})
            m.fit(X_full, yl)
            lseeds.append(m.booster_)

        ma = sub['label_adaptlim'].notna()
        Xa = sub[ma][feats].fillna(0).values
        ya = sub[ma]['label_adaptlim'].values
        hp_a = {**ADAPT_HP, 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
        aseeds = []
        for s in range(N_SEEDS):
            m = lgb.LGBMRegressor(**{**hp_a, 'random_state':s})
            m.fit(Xa, ya)
            aseeds.append(m.booster_)

        win_m[zone] = wseeds
        loss_m[zone] = lseeds
        adapt_m[zone] = aseeds

        # Step 33 v2.6.0: Train opt_entry model for Z3/Z4 per_zone LIMIT ensemble
        if zone in ('Z3', 'Z4') and 'label_opt_entry' in sub.columns:
            mo = sub['label_opt_entry'].notna()
            if mo.sum() >= 1000:
                Xo = sub[mo][feats].fillna(0).values
                yo = sub[mo]['label_opt_entry'].values
                hp_o = {**ADAPT_HP, 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
                oseeds = []
                for s in range(N_SEEDS):
                    m = lgb.LGBMRegressor(**{**hp_o, 'random_state':s})
                    m.fit(Xo, yo)
                    oseeds.append(m.booster_)
                adaptopt_m[zone] = oseeds

        print(f"  {zone}: {len(sub):,} train rows, models ready")

    con_db = sqlite3.connect(str(DB))
    con_bars = sqlite3.connect(str(BARS))

    def get_eod(sym, date):
        r = con_db.execute("SELECT close FROM intraday_bars_5m WHERE symbol=? AND DATE(timestamp)=? "
                           "AND time(timestamp)>'13:30:00' AND time(timestamp)<='20:00:00' "
                           "ORDER BY timestamp DESC LIMIT 1", (sym, date)).fetchone()
        return r[0] if r else None

    def get_intraday(sym, date, mfo):
        rows = con_bars.execute("SELECT em, l, c FROM bars WHERE sym=? AND date=? ORDER BY em",(sym, date)).fetchall()
        if not rows: return None, None, None
        target = 570+mfo
        scan_p = None; lows = []; after = []
        for em, l, c in rows:
            if em == target and c and c>0: scan_p = c
            if em > target:
                if l and l>0: lows.append(l)
                after.append((em,l,c))
        if scan_p is None or not lows: return None, None, None
        return scan_p, min(lows), after

    all_pass = True
    combined_pnls = []
    print(f"\nTest window: {test_start} → {test_end}\n")
    print(f"  {'Zone':5s} {'N':>4s} {'WR':>5s} {'avg':>7s} {'total':>8s} {'worst':>7s} {'pass?'}")
    SCAN_MFOS = list(range(0, 76, 5))

    for zone, (lo, hi) in ZONE_RANGE.items():
        if zone not in win_m: continue
        feats = FEATS_BY_ZONE[zone]
        test = df[(df['date']>=test_start) & (df['date']<test_end) & (df['mins_from_open']>=lo) & (df['mins_from_open']<=hi)].copy()
        if 'gain_from_prev' in test.columns:
            test = test[(test['gain_from_prev']>=2) & (test['gain_from_prev']<5)]
        pnls = []
        for date, g in test.groupby('date'):
            recent_syms = set()
            for mfo in [m for m in SCAN_MFOS if lo<=m<=hi]:
                zg = g[g['mins_from_open']==mfo].copy()
                zg = zg[~zg['sym'].isin(recent_syms)]
                if len(zg) == 0: continue
                X = zg[feats].fillna(0).values
                win_p = np.array([m.predict(X) for m in win_m[zone]]).min(axis=0)
                loss_p = np.array([m.predict(X) for m in loss_m[zone]]).max(axis=0)
                pred_r = np.array([m.predict(X) for m in adapt_m[zone]]).mean(axis=0)
                valid = (win_p>=ZONE_THR[zone]) & (loss_p<ZONE_LOSS_THR[zone])
                if zone == 'Z4':
                    valid &= (1-pred_r) >= Z4_DIP
                if not valid.any(): continue
                idx = np.where(valid)[0]
                top = idx[win_p[idx].argmax()]
                pick = zg.iloc[top]
                sym = pick['sym']; mfo_i = int(pick['mins_from_open'])
                recent_syms.add(sym)
                scan_p, min_low, after = get_intraday(sym, date, mfo_i)
                if scan_p is None: continue
                atr = float(pick.get('feat_atr_pct_14d', 3.0))
                bb, bc = ZONE_BUF[zone]
                pr = float(pred_r[top])
                # Step 33: per_zone LIMIT ensemble for Z3/Z4 (target = w_r×pred_r + (1-w_r)×pred_opt)
                pred_target = pr
                if zone in ('Z3', 'Z4') and zone in adaptopt_m:
                    Xpick = zg.iloc[[top]][feats].fillna(0).values
                    pred_opt = float(np.array([m.predict(Xpick) for m in adaptopt_m[zone]]).mean())
                    w_r = ZONE_LIMIT_W_R[zone]
                    pred_target = w_r * pr + (1 - w_r) * pred_opt
                limit = scan_p * pred_target * (1 + bb + bc*atr)
                if min_low <= limit:
                    eod = get_eod(sym, date)
                    if eod is None: continue
                    # Step 25: pure hold all zones (ZONE_HARD_SL={})
                    sl_pct = ZONE_HARD_SL.get(zone)
                    if sl_pct is not None:
                        sl = limit * (1 - sl_pct)
                        sl_hit = any(b[1] and b[1] <= sl for b in after[1:])
                        pnl = (sl-limit)/limit*100-0.1 if sl_hit else (eod-limit)/limit*100-0.1
                    else:
                        pnl = (eod-limit)/limit*100 - 0.1
                    pnls.append(pnl)

        pnls = np.array(pnls)
        if len(pnls) == 0:
            print(f"  {zone:5s} {'0':>4s} {'-':>5s} {'-':>7s} {'-':>8s} {'-':>7s} ⚠️ no picks")
            all_pass = False
            continue

        wr = (pnls>0).mean(); avg = pnls.mean()
        floor = baseline['per_zone_monthly_floor'][zone]
        zone_pass = wr >= floor['min_wr'] and avg >= floor['min_avg_pct']
        if not zone_pass: all_pass = False
        mark = '✓' if zone_pass else f'✗ (need WR>={floor["min_wr"]*100:.0f}%, avg>={floor["min_avg_pct"]:.1f}%)'
        print(f"  {zone:5s} {len(pnls):>4d} {wr*100:>4.0f}% {avg:+6.2f}% {pnls.sum():+7.0f}% {pnls.min():+6.2f}% {mark}")
        combined_pnls.extend(pnls.tolist())

    combined = np.array(combined_pnls)
    if len(combined) > 0:
        c_wr = (combined>0).mean(); c_total = combined.sum()
        cf = baseline['combined_floor']
        comb_pass = c_wr >= cf['min_wr'] and c_total >= cf['min_total_pct']
        if not comb_pass: all_pass = False
        mark = '✓' if comb_pass else f'✗ (need WR>={cf["min_wr"]*100:.0f}%, total>={cf["min_total_pct"]:.0f}%)'
        print(f"\n  Combined: N={len(combined)} WR={c_wr*100:.0f}% total={c_total:+.0f}% {mark}")

    if all_pass:
        print("\n✅ Validation PASSED (true OOS, no leak) — safe to deploy")
        return 0
    else:
        print("\n❌ Validation FAILED — caller should roll back")
        return 1


if __name__ == '__main__':
    sys.exit(main())
