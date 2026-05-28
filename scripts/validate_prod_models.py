"""
Test ACTUAL production models (models_prod_v22/) using validate_retrain logic.

Instead of training fresh in-memory, load stored prod models.
See if prod models give same 100% WR as validate's fresh models.
"""
import sys, json, sqlite3
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

ZONE_RANGE = {'Z1':(0,9),'Z2':(10,29),'Z3':(30,44),'Z4':(45,75)}
ZONE_THR = {'Z1':0.60,'Z2':0.65,'Z3':0.50,'Z4':0.50}
ZONE_LOSS_THR = {'Z1':0.40,'Z2':0.20,'Z3':0.40,'Z4':0.50}
ZONE_BUF = {'Z1':(0.005,0.0020),'Z2':(0.005,0.0015),'Z3':(0.000,0.0020),'Z4':(0.000,0.0020)}
ZONE_LIMIT_W_R = {'Z3': 0.7, 'Z4': 0.45}
Z4_DIP = 0.009


def load_seeds(prefix):
    """Load all seeds for a given prefix."""
    models = []
    for s in range(N_SEEDS):
        p = PROD / f'{prefix}_seed{s}.txt'
        if p.exists():
            models.append(lgb.Booster(model_file=str(p)))
    return models


def main():
    end_dt = datetime.strptime('2026-05-28', '%Y-%m-%d')
    test_start = (end_dt - timedelta(days=30)).strftime('%Y-%m-%d')
    test_end = '2026-05-28'

    print(f"Testing PROD models on {test_start} → {test_end}", flush=True)

    df = pd.read_pickle('cache/bt_features/features.pkl')
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

    # Load all prod models
    win_m, loss_m, adapt_m, adaptopt_m = {}, {}, {}, {}
    for zone in ['Z1','Z2','Z3','Z4']:
        win_m[zone] = load_seeds(f'lgb_tp1_{zone}')
        loss_m[zone] = load_seeds(f'lgb_loss_{zone}')
        adapt_m[zone] = load_seeds(f'lgb_adaptlim_{zone}')
        if zone in ('Z3', 'Z4'):
            adaptopt_m[zone] = load_seeds(f'lgb_adaptopt_{zone}')
        print(f"  {zone}: win={len(win_m[zone])} loss={len(loss_m[zone])} adapt={len(adapt_m[zone])} adaptopt={len(adaptopt_m.get(zone,[]))}", flush=True)

    con_db = sqlite3.connect(str(DB))
    con_bars = sqlite3.connect(str(BARS))

    def get_eod(sym, date):
        r = con_db.execute("SELECT close FROM intraday_bars_5m WHERE symbol=? AND DATE(timestamp)=? "
                           "AND time(timestamp)>'13:30:00' AND time(timestamp)<='20:00:00' "
                           "ORDER BY timestamp DESC LIMIT 1", (sym, date)).fetchone()
        return r[0] if r else None

    def get_intraday(sym, date, mfo):
        rows = con_bars.execute("SELECT em, l, c FROM bars WHERE sym=? AND date=? ORDER BY em",(sym, date)).fetchall()
        if not rows: return None, None
        target = 570+mfo
        scan_p = None; lows = []
        for em, l, c in rows:
            if em == target and c and c>0: scan_p = c
            if em > target and l and l>0: lows.append(l)
        if scan_p is None or not lows: return None, None
        return scan_p, min(lows)

    SCAN_MFOS = list(range(0, 76, 5))
    print(f"\n{'Zone':5s} {'N':>4s} {'WR':>5s} {'avg':>7s} {'total':>8s} {'worst':>7s}", flush=True)

    combined = []
    for zone, (lo, hi) in ZONE_RANGE.items():
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
                scan_p, min_low = get_intraday(sym, date, mfo_i)
                if scan_p is None: continue
                atr = float(pick.get('feat_atr_pct_14d', 3.0))
                bb, bc = ZONE_BUF[zone]
                pr = float(pred_r[top])
                pred_target = pr
                if zone in ('Z3', 'Z4') and zone in adaptopt_m and adaptopt_m[zone]:
                    Xpick = zg.iloc[[top]][feats].fillna(0).values
                    pred_opt = float(np.array([m.predict(Xpick) for m in adaptopt_m[zone]]).mean())
                    w_r = ZONE_LIMIT_W_R[zone]
                    pred_target = w_r * pr + (1 - w_r) * pred_opt
                limit = scan_p * pred_target * (1 + bb + bc*atr)
                if min_low <= limit:
                    eod = get_eod(sym, date)
                    if eod is None: continue
                    pnl = (eod-limit)/limit*100 - 0.1
                    pnls.append((date, sym, pnl))
        if not pnls:
            print(f"  {zone:5s} 0 picks", flush=True)
            continue
        ps = np.array([p[2] for p in pnls])
        wr = (ps>0).mean()
        avg = ps.mean()
        total = ps.sum()
        worst = ps.min()
        print(f"  {zone:5s} {len(ps):>4d} {wr*100:.0f}%  {avg:+.2f}%  {total:+.0f}%  {worst:+.2f}%", flush=True)
        combined.extend(ps)
    if combined:
        cm = np.array(combined)
        print(f"\n  Combined: N={len(cm)} WR={(cm>0).mean()*100:.0f}% total={cm.sum():+.0f}%", flush=True)


if __name__ == '__main__':
    main()
