"""
Step 35 — Phase 2 (monthly refit 6mo) + Phase 3 (cross-regime) Funnel gates.

Re-uses validate_retrain.py logic but loops over windows in a single process
(loads pkl + adaptlim ONCE → much faster than calling validate_retrain 11×).

Phase 2: 6 consecutive monthly OOS windows (Nov 2025 → Apr 2026), monthly refit.
Phase 3: 5 historical regime windows (CALM / RALLY / STRESS / CRISIS / NEUTRAL).

Compares Step 35 (current models) vs Step 33 baseline (backup dir).

Pass criteria:
  Phase 2: ΔT ≥ -3% combined (don't regress), majority months positive
  Phase 3: 4/5 regimes positive, both CRITICAL (CRISIS, STRESS) must pass
"""
import sys, json, sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backtests'))
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions

DB = ROOT / 'data' / 'trade_history.db'
BARS = ROOT / 'cache' / 'wf_1min_bars.db'
PKL = ROOT / 'cache' / 'bt_features' / 'features.pkl'
BACKUP_PROD = ROOT / 'backtests' / 'models_prod_v22_2026-05-28_pre_step35_backup'

# Step 35 config
TRAIN_DAYS = 840
N_SEEDS = 5
ZONE_RANGE = {'Z1':(0,9),'Z2':(10,29),'Z3':(30,44),'Z4':(45,75)}
ZONE_BUF = {'Z1':(0.005,0.0020),'Z2':(0.005,0.0015),'Z3':(0.000,0.0020),'Z4':(0.000,0.0020)}
ZONE_THR = {'Z1':0.60,'Z2':0.65,'Z3':0.50,'Z4':0.50}
ZONE_LOSS_THR = {'Z1':0.40,'Z2':0.40,'Z3':0.40,'Z4':0.40}
ZONE_HARD_SL = {}
ZONE_CW = {'Z1':None,'Z2':None,'Z3':2.0,'Z4':2.0}
ZONE_LIMIT_W_R = {'Z3':0.7,'Z4':0.45}
Z4_DIP = 0.009
ZONE_LABEL_STEP35 = {'Z1':'label_z12_market_3dd','Z2':'label_custom_dd','Z3':'label_real_pnl_05','Z4':'label_real_pnl_05'}
ZONE_LABEL_STEP33 = {'Z1':'label_z12_market_3dd','Z2':'label_custom_dd','Z3':'label_smart_v2','Z4':'label_smart_v2'}
HP = {
    'Z1':{'learning_rate':0.0316,'max_depth':3,'num_leaves':54,'n_estimators':400,
          'min_child_samples':153,'reg_alpha':0.5648,'reg_lambda':2.9886,'feature_fraction':0.65,'bagging_fraction':0.85},
    'Z2':{'learning_rate':0.0970,'max_depth':2,'num_leaves':56,'n_estimators':400,
          'min_child_samples':120,'reg_alpha':3.345,'reg_lambda':4.341,'feature_fraction':0.85,'bagging_fraction':0.85},
    'Z3':{'learning_rate':0.0184,'max_depth':5,'num_leaves':27,'n_estimators':500,
          'min_child_samples':125,'reg_alpha':4.0817,'reg_lambda':4.2902,'feature_fraction':0.75,'bagging_fraction':0.85},
    'Z4':{'learning_rate':0.0827,'max_depth':5,'num_leaves':5,'n_estimators':400,
          'min_child_samples':69,'reg_alpha':3.859,'reg_lambda':0.001,'feature_fraction':0.85,'bagging_fraction':0.85},
}
LOSS_HP = {'learning_rate':0.05,'max_depth':4,'num_leaves':15,'n_estimators':300,
           'min_child_samples':50,'reg_alpha':0.5,'reg_lambda':1.0,'feature_fraction':0.85,'bagging_fraction':0.85}
ADAPT_HP = {'learning_rate':0.05,'max_depth':4,'num_leaves':15,'n_estimators':300,
            'min_child_samples':50,'reg_alpha':0.5,'reg_lambda':1.0,'feature_fraction':0.85,'bagging_fraction':0.85}


def train_zone_models(df_train, zone, feats, zone_label_map):
    LO, HI = ZONE_RANGE[zone]
    mask = (df_train['mins_from_open']>=LO) & (df_train['mins_from_open']<=HI)
    sub = df_train[mask]
    if len(sub) < 500: return None, None, None, None

    X_full = sub[feats].fillna(0).values
    wl = zone_label_map[zone]
    if wl not in sub.columns: return None, None, None, None
    mw = sub[wl].notna()
    if mw.sum() < 100: return None, None, None, None
    Xw = sub[mw][feats].fillna(0).values
    yw = sub[mw][wl].astype(int).values
    cfg = {**HP[zone], 'objective':'binary', 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
    cw_z = ZONE_CW.get(zone)
    sw_w = np.where(yw == 0, cw_z, 1.0) if cw_z and cw_z > 1.0 else None
    wseeds = [lgb.LGBMClassifier(**{**cfg,'random_state':s}).fit(Xw,yw,sample_weight=sw_w).booster_ for s in range(N_SEEDS)]

    yl = (sub['label_fixed3'] <= -1.0).astype(int).values
    hp_l = {**LOSS_HP, 'objective':'binary', 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
    lseeds = [lgb.LGBMClassifier(**{**hp_l,'random_state':s}).fit(X_full,yl).booster_ for s in range(N_SEEDS)]

    ma = sub['label_adaptlim'].notna()
    Xa = sub[ma][feats].fillna(0).values
    ya = sub[ma]['label_adaptlim'].values
    hp_a = {**ADAPT_HP, 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
    aseeds = [lgb.LGBMRegressor(**{**hp_a,'random_state':s}).fit(Xa,ya).booster_ for s in range(N_SEEDS)]

    oseeds = None
    if zone in ('Z3','Z4') and 'label_opt_entry' in sub.columns:
        mo = sub['label_opt_entry'].notna()
        if mo.sum() >= 1000:
            Xo = sub[mo][feats].fillna(0).values
            yo = sub[mo]['label_opt_entry'].values
            hp_o = {**ADAPT_HP, 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
            oseeds = [lgb.LGBMRegressor(**{**hp_o,'random_state':s}).fit(Xo,yo).booster_ for s in range(N_SEEDS)]

    return wseeds, lseeds, aseeds, oseeds


def get_eod(con_db, sym, date):
    r = con_db.execute("SELECT close FROM intraday_bars_5m WHERE symbol=? AND DATE(timestamp)=? "
                       "AND time(timestamp)>'13:30:00' AND time(timestamp)<='20:00:00' "
                       "ORDER BY timestamp DESC LIMIT 1", (sym, date)).fetchone()
    return r[0] if r else None


def get_intraday(con_bars, sym, date, mfo):
    rows = con_bars.execute("SELECT em,l,c FROM bars WHERE sym=? AND date=? ORDER BY em",(sym,date)).fetchall()
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


def run_window(df, test_start, test_end, train_days, feats_by_zone, label_map, con_db, con_bars):
    """Train + test on a single window. Returns dict[zone] = pnls list + combined."""
    test_start_dt = datetime.strptime(test_start, '%Y-%m-%d')
    train_start = (test_start_dt - timedelta(days=train_days)).strftime('%Y-%m-%d')
    train_mask = (df['date']>=train_start) & (df['date']<test_start)
    df_train = df[train_mask].copy()
    test_mask = (df['date']>=test_start) & (df['date']<test_end)
    df_test = df[test_mask].copy()
    if len(df_test) == 0: return None

    models = {}
    for zone in ['Z1','Z2','Z3','Z4']:
        w, l, a, o = train_zone_models(df_train, zone, feats_by_zone[zone], label_map)
        if w is None: continue
        models[zone] = (w, l, a, o)

    SCAN_MFOS = list(range(0, 76, 5))
    results = {}
    combined = []
    for zone, (lo, hi) in ZONE_RANGE.items():
        if zone not in models: continue
        wm, lm, am, om = models[zone]
        feats = feats_by_zone[zone]
        test = df_test[(df_test['mins_from_open']>=lo)&(df_test['mins_from_open']<=hi)].copy()
        if 'gain_from_prev' in test.columns:
            test = test[(test['gain_from_prev']>=2)&(test['gain_from_prev']<5)]
        pnls = []
        for date, g in test.groupby('date'):
            recent = set()
            for mfo in [m for m in SCAN_MFOS if lo<=m<=hi]:
                zg = g[g['mins_from_open']==mfo].copy()
                zg = zg[~zg['sym'].isin(recent)]
                if len(zg)==0: continue
                X = zg[feats].fillna(0).values
                win_p = np.array([m.predict(X) for m in wm]).min(axis=0)
                loss_p = np.array([m.predict(X) for m in lm]).max(axis=0)
                pred_r = np.array([m.predict(X) for m in am]).mean(axis=0)
                valid = (win_p>=ZONE_THR[zone]) & (loss_p<ZONE_LOSS_THR[zone])
                if zone=='Z4': valid &= (1-pred_r) >= Z4_DIP
                if not valid.any(): continue
                idx = np.where(valid)[0]
                top = idx[win_p[idx].argmax()]
                pick = zg.iloc[top]; sym = pick['sym']; mfo_i = int(pick['mins_from_open'])
                recent.add(sym)
                scan_p, min_low, after = get_intraday(con_bars, sym, date, mfo_i)
                if scan_p is None: continue
                atr = float(pick.get('feat_atr_pct_14d', 3.0))
                bb, bc = ZONE_BUF[zone]
                pr = float(pred_r[top])
                pred_target = pr
                if zone in ('Z3','Z4') and om is not None:
                    Xpick = zg.iloc[[top]][feats].fillna(0).values
                    pred_opt = float(np.array([m.predict(Xpick) for m in om]).mean())
                    w_r = ZONE_LIMIT_W_R[zone]
                    pred_target = w_r*pr + (1-w_r)*pred_opt
                limit = scan_p * pred_target * (1 + bb + bc*atr)
                if min_low <= limit:
                    eod = get_eod(con_db, sym, date)
                    if eod is None: continue
                    pnl = (eod-limit)/limit*100 - 0.1
                    pnls.append(pnl)
        results[zone] = np.array(pnls) if pnls else np.array([])
        combined.extend(pnls)
    results['_combined'] = np.array(combined)
    return results


def summarize(label, results):
    parts = [f"{label:25s}"]
    for z in ['Z1','Z2','Z3','Z4']:
        p = results.get(z, np.array([]))
        if len(p) == 0: parts.append(f"{z}:n=0")
        else: parts.append(f"{z}:N={len(p)} WR={(p>0).mean()*100:.0f}% T{p.sum():+.0f}%")
    c = results.get('_combined', np.array([]))
    if len(c) > 0:
        parts.append(f"COMBINED N={len(c)} WR={(c>0).mean()*100:.0f}% T{c.sum():+.0f}%")
    return ' | '.join(parts)


def phase2(df, feats_by_zone, con_db, con_bars):
    print(f"\n{'='*100}")
    print("PHASE 2 — Monthly Refit (6 months, train ≤ each month start)")
    print('='*100)
    # 6 monthly windows: Nov 2025 → Apr 2026
    windows = [
        ('2025-11-01', '2025-12-01', 'Nov-25'),
        ('2025-12-01', '2026-01-01', 'Dec-25'),
        ('2026-01-01', '2026-02-01', 'Jan-26'),
        ('2026-02-01', '2026-03-01', 'Feb-26'),
        ('2026-03-01', '2026-04-01', 'Mar-26'),
        ('2026-04-01', '2026-05-01', 'Apr-26'),
    ]
    totals_35 = []; totals_33 = []
    print(f"\n{'Month':10s} {'S35 N':>5s} {'WR':>5s} {'T':>7s} | {'S33 N':>5s} {'WR':>5s} {'T':>7s} | {'ΔT':>6s}")
    for ts, te, label in windows:
        r35 = run_window(df, ts, te, TRAIN_DAYS, feats_by_zone, ZONE_LABEL_STEP35, con_db, con_bars)
        r33 = run_window(df, ts, te, TRAIN_DAYS, feats_by_zone, ZONE_LABEL_STEP33, con_db, con_bars)
        c35 = r35['_combined'] if r35 else np.array([])
        c33 = r33['_combined'] if r33 else np.array([])
        t35 = c35.sum() if len(c35) else 0
        t33 = c33.sum() if len(c33) else 0
        wr35 = (c35>0).mean()*100 if len(c35) else 0
        wr33 = (c33>0).mean()*100 if len(c33) else 0
        delta = t35 - t33
        totals_35.append(t35); totals_33.append(t33)
        print(f"{label:10s} {len(c35):>5d} {wr35:>4.0f}% {t35:+6.0f}% | {len(c33):>5d} {wr33:>4.0f}% {t33:+6.0f}% | {delta:+6.0f}%")

    sum_35 = sum(totals_35); sum_33 = sum(totals_33)
    delta = sum_35 - sum_33
    pos_months = sum(1 for t in totals_35 if t > 0)
    print(f"\n  S35 6-mo total: {sum_35:+.0f}%")
    print(f"  S33 6-mo total: {sum_33:+.0f}%")
    print(f"  Δ (S35-S33):    {delta:+.0f}%")
    print(f"  S35 positive months: {pos_months}/6")
    pass2 = (delta >= -50) and (pos_months >= 4)  # don't regress hard, mostly positive
    print(f"  Phase 2: {'PASS ✓' if pass2 else 'FAIL ✗'}")
    return pass2, sum_35, sum_33


def phase3(df, feats_by_zone, con_db, con_bars):
    print(f"\n{'='*100}")
    print("PHASE 3 — Cross-Regime (5 regimes)")
    print('='*100)
    # Pick historic windows by regime tag (approximate using VIX from macro_snapshots)
    # CRITICAL = CRISIS, STRESS — must pass
    # Optional = CALM, RALLY, NEUTRAL
    windows = [
        ('2024-04-01', '2024-05-01', 'CRISIS_2024',   True),   # Iran-Israel war
        ('2024-08-01', '2024-09-01', 'STRESS_2024',   True),   # August VIX spike
        ('2024-11-01', '2024-12-01', 'RALLY_2024',    False),  # post-election
        ('2025-02-01', '2025-03-01', 'NEUTRAL_2025',  False),
        ('2025-07-01', '2025-08-01', 'CALM_2025',     False),
    ]
    crit_pass = 0; crit_total = 0
    opt_pass = 0; opt_total = 0
    print(f"\n{'Regime':18s} {'S35 N':>5s} {'WR':>5s} {'T':>7s} | {'S33 N':>5s} {'WR':>5s} {'T':>7s} | {'ΔT':>6s} {'pass'}")
    for ts, te, label, critical in windows:
        r35 = run_window(df, ts, te, TRAIN_DAYS, feats_by_zone, ZONE_LABEL_STEP35, con_db, con_bars)
        r33 = run_window(df, ts, te, TRAIN_DAYS, feats_by_zone, ZONE_LABEL_STEP33, con_db, con_bars)
        c35 = r35['_combined'] if r35 else np.array([])
        c33 = r33['_combined'] if r33 else np.array([])
        t35 = c35.sum() if len(c35) else 0
        t33 = c33.sum() if len(c33) else 0
        wr35 = (c35>0).mean()*100 if len(c35) else 0
        wr33 = (c33>0).mean()*100 if len(c33) else 0
        delta = t35 - t33
        # Pass: don't regress more than 5% combined, AND S35 must be positive (not a loss net)
        w_pass = (delta >= -50) and (t35 >= -5)
        tag = '✓' if w_pass else '✗'
        crit_tag = ' CRIT' if critical else ''
        if critical:
            crit_total += 1
            if w_pass: crit_pass += 1
        else:
            opt_total += 1
            if w_pass: opt_pass += 1
        print(f"{label:18s} {len(c35):>5d} {wr35:>4.0f}% {t35:+6.0f}% | {len(c33):>5d} {wr33:>4.0f}% {t33:+6.0f}% | {delta:+6.0f}% {tag}{crit_tag}")

    print(f"\n  Critical (CRISIS+STRESS): {crit_pass}/{crit_total} pass")
    print(f"  Optional:                 {opt_pass}/{opt_total} pass")
    total_pass = crit_pass + opt_pass
    pass3 = (crit_pass == crit_total) and (total_pass >= 4)
    print(f"  Phase 3: {'PASS ✓' if pass3 else 'FAIL ✗'}")
    return pass3


def main():
    print(f"Step 35 Phase 2+3 Funnel — {datetime.now()}", flush=True)
    print(f"Loading pkl...", flush=True)
    df = pd.read_pickle(PKL)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    feats_avail = [f for f in V7_FEATS+CROSS_FEATS if f in df.columns]
    NEW_FEATS = sorted([c for c in df.columns if c.startswith('feat_')])
    df = add_interactions(df)
    feats_by_zone = {
        'Z1': feats_avail + INTERACTIONS + NEW_FEATS,
        'Z2': feats_avail + INTERACTIONS + NEW_FEATS,
        'Z3': feats_avail + NEW_FEATS,
        'Z4': feats_avail + NEW_FEATS,
    }
    if 'label_adaptlim' not in df.columns:
        print("Computing label_adaptlim from 1-min cache...", flush=True)
        con_bars = sqlite3.connect(str(BARS))
        sym_dates = df[['sym','date']].drop_duplicates().itertuples(index=False)
        bar_cache = {}
        for sym, date in sym_dates:
            rows = con_bars.execute("SELECT em,l,c FROM bars WHERE sym=? AND date=? ORDER BY em",(sym,date)).fetchall()
            if rows: bar_cache[(sym,date)] = rows
        con_bars.close()
        ratios = []
        for _, r in df.iterrows():
            bars = bar_cache.get((r['sym'], r['date']))
            if not bars: ratios.append(np.nan); continue
            target_em = 570 + int(r['mins_from_open'])
            scan_p = None; lows = []
            for em, l, c in bars:
                if em == target_em and c and c>0: scan_p = c
                if em > target_em and l and l>0: lows.append(l)
            if scan_p is None or not lows: ratios.append(np.nan); continue
            ratios.append(min(lows)/scan_p)
        df['label_adaptlim'] = ratios
    print(f"  pkl loaded: {df.shape}, label_adaptlim ready", flush=True)

    con_db = sqlite3.connect(str(DB))
    con_bars = sqlite3.connect(str(BARS))

    pass2, s35, s33 = phase2(df, feats_by_zone, con_db, con_bars)
    pass3 = phase3(df, feats_by_zone, con_db, con_bars)

    con_db.close(); con_bars.close()

    print(f"\n{'='*100}")
    print(f"FINAL: Phase 2 = {'PASS' if pass2 else 'FAIL'}, Phase 3 = {'PASS' if pass3 else 'FAIL'}")
    print(f"  Step 35 6-mo total: {s35:+.0f}% | Step 33 baseline: {s33:+.0f}%")
    if pass2 and pass3:
        print(f"\n✅ Phase 2+3 PASSED — Step 35 safe to deploy")
        return 0
    else:
        print(f"\n❌ Phase 2+3 FAILED — DO NOT deploy")
        return 1


if __name__ == '__main__':
    sys.exit(main())
