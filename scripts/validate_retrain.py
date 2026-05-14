"""Validate freshly retrained zone models via single-month WF.

Usage:
  python3 scripts/validate_retrain.py --end-date YYYY-MM-DD \\
                                       --pkl cache/bt_features/features.pkl

Exit code:
  0 = validation passed (all zones meet floor)
  1 = validation FAILED (at least one zone below floor) — retrain script
      should roll back models.

Speed: ~2 min (1 month test, no monthly refit — uses just-trained models).
"""
import argparse, json, sys, sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import lightgbm as lgb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backtests'))
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions

PROD = Path(__file__).resolve().parents[1] / 'backtests' / 'models_prod_v22'
DB = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'
BARS = Path(__file__).resolve().parents[1] / 'cache' / 'wf_1min_bars.db'
BASELINE = Path(__file__).resolve().parents[1] / 'configs' / 'wf_baseline.json'

ZONE_RANGE = {'Z1':(0,9),'Z2':(10,29),'Z3':(30,44),'Z4':(45,75)}
ZONE_THR = {'Z1':0.60,'Z2':0.65,'Z3':0.50,'Z4':0.50}
ZONE_LOSS_THR = {'Z1':0.40,'Z2':0.20,'Z3':0.40,'Z4':0.50}
ZONE_BUF = {'Z1':(0.005,0.0020),'Z2':(0.005,0.0015),'Z3':(0.005,0.0015),'Z4':(0.010,0.0)}
ZONE_HARD_SL = {'Z4':0.03}
Z4_DIP = 0.005


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end-date', default=datetime.today().strftime('%Y-%m-%d'))
    ap.add_argument('--pkl', default='cache/bt_features/features.pkl')
    ap.add_argument('--test-days', type=int, default=30, help='days of OOS testing')
    args = ap.parse_args()

    print(f"=== Validate retrain (end={args.end_date}, last {args.test_days}d test) ===", flush=True)
    baseline = json.loads(BASELINE.read_text())
    print(f"Loading pkl {args.pkl}...", flush=True)
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

    # Load freshly trained models
    win_m, loss_m, adapt_m = {}, {}, {}
    for z in ['Z1','Z2','Z3','Z4']:
        try:
            win_m[z]   = [lgb.Booster(model_file=str(PROD/f'lgb_tp1_{z}_seed{i}.txt')) for i in range(5)]
            loss_m[z]  = [lgb.Booster(model_file=str(PROD/f'lgb_loss_{z}_seed{i}.txt')) for i in range(5)]
            adapt_m[z] = [lgb.Booster(model_file=str(PROD/f'lgb_adaptlim_{z}_seed{i}.txt')) for i in range(5)]
        except Exception as e:
            print(f"❌ Failed to load {z} models: {e}")
            return 1

    end_dt = datetime.strptime(args.end_date, '%Y-%m-%d')
    test_start = (end_dt - timedelta(days=args.test_days)).strftime('%Y-%m-%d')
    test_end = args.end_date

    con_db = sqlite3.connect(str(DB))
    con_bars = sqlite3.connect(str(BARS))

    def get_eod(sym, date):
        r = con_db.execute("SELECT close FROM intraday_bars_5m WHERE symbol=? AND DATE(timestamp)=? "
                           "AND time(timestamp)>'13:30:00' AND time(timestamp)<='20:00:00' "
                           "ORDER BY timestamp DESC LIMIT 1", (sym,date)).fetchone()
        return r[0] if r else None

    def get_intraday(sym, date, mfo):
        rows = con_bars.execute("SELECT em, l, c FROM bars WHERE sym=? AND date=? ORDER BY em",(sym,date)).fetchall()
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
    print(f"\nTest window: {test_start} → {test_end}\n")
    print(f"  {'Zone':5s} {'N':>4s} {'WR':>5s} {'avg':>7s} {'total':>8s} {'worst':>7s} {'pass?'}")
    combined_pnls = []

    for zone, (lo, hi) in ZONE_RANGE.items():
        feats = FEATS_BY_ZONE[zone]
        test = df[(df['date']>=test_start) & (df['date']<=test_end) &
                  (df['mins_from_open']>=lo) & (df['mins_from_open']<=hi)].copy()
        if 'gain_from_prev' in test.columns:
            test = test[(test['gain_from_prev']>=2) & (test['gain_from_prev']<5)]
        pnls = []
        for date, g in test.groupby('date'):
            if len(g) == 0: continue
            X = g[feats].fillna(0).values
            win_p = np.array([m.predict(X) for m in win_m[zone]]).min(axis=0)
            loss_p = np.array([m.predict(X) for m in loss_m[zone]]).max(axis=0)
            pred_r = np.array([m.predict(X) for m in adapt_m[zone]]).mean(axis=0)
            valid = (win_p>=ZONE_THR[zone]) & (loss_p<ZONE_LOSS_THR[zone])
            if zone == 'Z4':
                valid &= (1-pred_r) >= Z4_DIP
            if not valid.any(): continue
            idx = np.where(valid)[0]
            # Step 18: Top-1 by win only
            top = idx[win_p[idx].argmax()]
            pick = g.iloc[top]
            sym = pick['sym']; mfo = int(pick['mins_from_open'])
            scan_p, min_low, after = get_intraday(sym, date, mfo)
            if scan_p is None: continue
            atr = float(pick.get('feat_atr_pct_14d', 3.0))
            bb, bc = ZONE_BUF[zone]
            limit = scan_p * pred_r[top] * (1 + bb + bc*atr)
            if min_low <= limit:
                eod = get_eod(sym, date)
                if eod is None: continue
                if zone == 'Z4':
                    sl = limit * (1 - ZONE_HARD_SL['Z4'])
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

    # Combined check
    combined = np.array(combined_pnls)
    if len(combined) > 0:
        c_wr = (combined>0).mean(); c_total = combined.sum()
        cf = baseline['combined_floor']
        comb_pass = c_wr >= cf['min_wr'] and c_total >= cf['min_total_pct']
        if not comb_pass: all_pass = False
        mark = '✓' if comb_pass else f'✗ (need WR>={cf["min_wr"]*100:.0f}%, total>={cf["min_total_pct"]:.0f}%)'
        print(f"\n  Combined: N={len(combined)} WR={c_wr*100:.0f}% total={c_total:+.0f}% {mark}")

    if all_pass:
        print("\n✅ Validation PASSED — safe to deploy")
        return 0
    else:
        print("\n❌ Validation FAILED — caller should roll back")
        return 1


if __name__ == '__main__':
    sys.exit(main())
