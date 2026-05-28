"""
Step 36 — top-1 per zone simulation.

For each scan (date, mfo, zone) since 2026-04-28:
1. Get ALL passed-filter candidates from scan_candidates
2. Apply Step 36 filters:
   - Z2-Z4: remove syms not in pkl_universe
   - Recompute features from pkl row (correct day_open)
   - Re-score with current models
3. Select new top-1 by zone-appropriate ranking (R9 for Z1/Z2, win_only for Z3/Z4)
4. Look up outcome from intraday_bars_5m EOD price

Compare new top-1 outcomes vs original top-1 outcomes per zone.
"""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backtests'))
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions

JOURNAL = ROOT / 'data' / 'scan_journal.db'
TRADE_DB = ROOT / 'data' / 'trade_history.db'
PKL = ROOT / 'cache' / 'bt_features' / 'features.pkl'
PROD = ROOT / 'backtests' / 'models_prod_v22'

ZONE_THR = {'Z1': 0.60, 'Z2': 0.65, 'Z3': 0.50, 'Z4': 0.50}
ZONE_LOSS_THR = {'Z1': 0.40, 'Z2': 0.40, 'Z3': 0.40, 'Z4': 0.40}
ZONE_RANGE = {'Z1': (0, 9), 'Z2': (10, 29), 'Z3': (30, 44), 'Z4': (45, 75)}
Z4_DIP = 0.009


def load_models():
    m = {'win':{}, 'loss':{}, 'adapt':{}, 'adaptopt':{}}
    for zone in ['Z1','Z2','Z3','Z4']:
        m['win'][zone] = [lgb.Booster(model_file=str(PROD/f'lgb_tp1_{zone}_seed{s}.txt')) for s in range(5)]
        m['loss'][zone] = [lgb.Booster(model_file=str(PROD/f'lgb_loss_{zone}_seed{s}.txt')) for s in range(5)]
        m['adapt'][zone] = [lgb.Booster(model_file=str(PROD/f'lgb_adaptlim_{zone}_seed{s}.txt')) for s in range(5)]
        if zone in ('Z3','Z4'):
            m['adaptopt'][zone] = [lgb.Booster(model_file=str(PROD/f'lgb_adaptopt_{zone}_seed{s}.txt')) for s in range(5)]
    return m


def main():
    print("Step 36 — Top-1 per zone simulation\n", flush=True)

    pkl_universe = set((ROOT/'cache/bt_features/pkl_universe.txt').read_text().strip().split('\n'))
    print(f"PKL universe: {len(pkl_universe)} syms\n")

    # 1. Load candidates with outcomes if available
    con = sqlite3.connect(str(JOURNAL))
    cands = pd.read_sql("""
        SELECT sc.scan_date, sc.scan_ts, sc.zone, sc.mfo, sc.symbol,
               sc.win_p, sc.loss_p, sc.pred_r, sc.r9_score,
               sc.rank_by_win, sc.rank_by_r9, sc.selected,
               sc.scan_price, sc.adaptive_limit, sc.gain_from_open
        FROM scan_candidates sc
        WHERE sc.scan_ts >= '2026-04-28'
        ORDER BY sc.scan_date, sc.scan_ts, sc.zone, sc.rank_by_win
    """, con)
    con.close()
    print(f"Candidates loaded: {len(cands)}\n")

    # 2. Load pkl
    print("Loading pkl + models...", flush=True)
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
    key_to_idx = {(r.sym, r.date, r.mins_from_open): i for i, r in enumerate(df.itertuples(index=False))}
    models = load_models()
    print(f"  pkl shape {df.shape}, last {df['date'].max()}\n")

    # 3. EOD + scan price lookups (from intraday_bars_5m, timestamps in UTC)
    con_db = sqlite3.connect(str(TRADE_DB))
    def get_eod(sym, date):
        r = con_db.execute("""
            SELECT close FROM intraday_bars_5m
            WHERE symbol=? AND DATE(timestamp)=? AND time(timestamp)>'13:30:00' AND time(timestamp)<='20:00:00'
            ORDER BY timestamp DESC LIMIT 1
        """, (sym, date)).fetchone()
        return r[0] if r else None

    def get_scan_price(sym, date, mfo):
        # mfo from 09:30 ET = 13:30 UTC. Get close of 5-min bar AT that time.
        from datetime import datetime, timedelta
        utc_minute = 13*60 + 30 + mfo  # mins from UTC midnight
        hh, mm = divmod(utc_minute, 60)
        target_time = f"{hh:02d}:{mm:02d}:00"
        r = con_db.execute("""
            SELECT close FROM intraday_bars_5m
            WHERE symbol=? AND DATE(timestamp)=? AND time(timestamp)=?
            LIMIT 1
        """, (sym, date, target_time)).fetchone()
        return r[0] if r else None

    # 4. Process per (scan_ts, zone) → recompute top-1
    results = []
    for (scan_ts, zone), g in cands.groupby(['scan_ts', 'zone']):
        date = g['scan_date'].iloc[0]
        mfo = int(g['mfo'].iloc[0])

        # ORIGINAL top-1 = selected=1 (or rank_by_win=1 if zone in Z3/Z4 else rank_by_r9=1)
        rank_col = 'rank_by_win' if zone in ('Z3','Z4') else 'rank_by_r9'
        orig_top = g[g[rank_col] == 1]
        if len(orig_top) == 0:
            orig_top = g.head(1)
        orig_sym = orig_top['symbol'].iloc[0]
        orig_price = orig_top['scan_price'].iloc[0]
        if orig_price is None or pd.isna(orig_price) or orig_price <= 0:
            orig_price = get_scan_price(orig_sym, date, mfo)

        # STEP 36 simulation
        g_sim = g.copy()
        # 36d universe filter (Z2-Z4 only)
        if zone != 'Z1':
            g_sim = g_sim[g_sim['symbol'].isin(pkl_universe)]
        if len(g_sim) == 0:
            results.append({
                'scan_ts': scan_ts, 'date': date, 'mfo': mfo, 'zone': zone,
                'orig_sym': orig_sym, 'orig_price': orig_price,
                'new_sym': None, 'new_price': None, 'orig_pnl': None, 'new_pnl': None,
                'note': 'all_filtered_universe'
            })
            continue

        # Re-score each candidate with corrected features from pkl
        new_scores = []
        feats = feats_by_zone[zone]
        for _, c in g_sim.iterrows():
            sym = c['symbol']
            idx = key_to_idx.get((sym, date, mfo))
            if idx is None:
                # Sym not in pkl → if Z1, keep original score; if Z2-Z4, would have been filtered (defensive)
                if zone == 'Z1':
                    new_scores.append({
                        'symbol': sym, 'win_p': c['win_p'], 'loss_p': c['loss_p'], 'pred_r': c['pred_r'],
                        'pass': True, 'rank_score': c['r9_score'] if zone in ('Z1','Z2') else c['win_p']
                    })
                continue

            row = df.iloc[idx]
            X = pd.DataFrame([row[feats].fillna(0).values], columns=feats).values
            win_p = float(np.array([m.predict(X) for m in models['win'][zone]]).min(axis=0)[0])
            loss_p = float(np.array([m.predict(X) for m in models['loss'][zone]]).max(axis=0)[0])
            pred_r = float(np.array([m.predict(X) for m in models['adapt'][zone]]).mean(axis=0)[0])

            pass_win = win_p >= ZONE_THR[zone]
            pass_loss = loss_p < ZONE_LOSS_THR[zone]
            pass_dip = (zone != 'Z4') or ((1 - pred_r) >= Z4_DIP)
            if not (pass_win and pass_loss and pass_dip):
                continue

            # Ranking
            if zone in ('Z3','Z4'):
                rank_score = win_p
            else:
                rank_score = win_p * max(0.0, 1 - pred_r) ** 0.5
            new_scores.append({
                'symbol': sym, 'win_p': win_p, 'loss_p': loss_p, 'pred_r': pred_r,
                'pass': True, 'rank_score': rank_score
            })

        if not new_scores:
            results.append({
                'scan_ts': scan_ts, 'date': date, 'mfo': mfo, 'zone': zone,
                'orig_sym': orig_sym, 'orig_price': orig_price,
                'new_sym': None, 'new_price': None, 'orig_pnl': None, 'new_pnl': None,
                'note': 'no_pass_after_fix'
            })
            continue

        new_top = sorted(new_scores, key=lambda x: -x['rank_score'])[0]
        new_sym = new_top['symbol']

        # Look up scan_price for new_sym from candidates table or bars
        cnew = g_sim[g_sim['symbol'] == new_sym].iloc[0]
        new_price = cnew['scan_price']
        if new_price is None or pd.isna(new_price) or new_price <= 0:
            new_price = get_scan_price(new_sym, date, mfo)

        # Outcomes (EOD-based, since pure-hold-to-EOD strategy)
        orig_eod = get_eod(orig_sym, date)
        new_eod = get_eod(new_sym, date)
        orig_pnl = ((orig_eod - orig_price) / orig_price * 100 - 0.1) if (orig_eod and orig_price) else None
        new_pnl = ((new_eod - new_price) / new_price * 100 - 0.1) if (new_eod and new_price) else None

        results.append({
            'scan_ts': scan_ts, 'date': date, 'mfo': mfo, 'zone': zone,
            'orig_sym': orig_sym, 'orig_price': orig_price, 'orig_pnl': orig_pnl,
            'new_sym': new_sym, 'new_price': new_price, 'new_pnl': new_pnl,
            'note': 'OK' if orig_sym == new_sym else 'CHANGED'
        })

    r = pd.DataFrame(results)
    print(f"Scans processed: {len(r)}\n")

    # 5. Summary per zone (top-1 only)
    print(f"{'Zone':5s} {'N':>4s} {'OrigWR':>7s} {'OrigAvg':>8s} {'OrigT':>7s} | {'NewWR':>6s} {'NewAvg':>8s} {'NewT':>7s} | {'Δ N':>5s} {'Δ WR':>5s} {'Δ Total':>7s}")
    for zone in ['Z1','Z2','Z3','Z4']:
        zr = r[r['zone'] == zone].copy()
        orig = zr[zr['orig_pnl'].notna()]
        new = zr[zr['new_pnl'].notna()]
        if len(orig) == 0:
            print(f"{zone:5s} {'-':>4s}")
            continue
        ow = (orig['orig_pnl']>0).mean()*100
        oa = orig['orig_pnl'].mean()
        ot = orig['orig_pnl'].sum()
        if len(new):
            nw = (new['new_pnl']>0).mean()*100
            na = new['new_pnl'].mean()
            nt = new['new_pnl'].sum()
        else:
            nw=na=nt=0
        print(f"{zone:5s} {len(orig):>4d} {ow:>6.0f}% {oa:>+7.2f}% {ot:>+6.0f}% | "
              f"{nw:>5.0f}% {na:>+7.2f}% {nt:>+6.0f}% | "
              f"{len(new)-len(orig):>+4d} {nw-ow:>+4.0f}pp {nt-ot:>+6.0f}%")

    # Combined
    orig_all = r[r['orig_pnl'].notna()]
    new_all = r[r['new_pnl'].notna()]
    print()
    if len(orig_all) and len(new_all):
        print(f"COMBINED orig: N={len(orig_all)} WR={(orig_all['orig_pnl']>0).mean()*100:.0f}% avg={orig_all['orig_pnl'].mean():+.2f}% total={orig_all['orig_pnl'].sum():+.0f}%")
        print(f"COMBINED new : N={len(new_all)} WR={(new_all['new_pnl']>0).mean()*100:.0f}% avg={new_all['new_pnl'].mean():+.2f}% total={new_all['new_pnl'].sum():+.0f}%")

    # Cases where pick changed
    changed = r[r['note'] == 'CHANGED']
    print(f"\nPicks CHANGED: {len(changed)}/{len(r)} ({len(changed)/max(1,len(r))*100:.0f}%)")
    if len(changed):
        ok_changes = changed[(changed['new_pnl'] > changed['orig_pnl'])]
        print(f"  Better after change: {len(ok_changes)}/{len(changed)}")
        print(f"\nSample changes:")
        print(changed[['date','mfo','zone','orig_sym','orig_pnl','new_sym','new_pnl']].head(15).to_string(index=False))

    out = ROOT / 'backtests' / 'research_step36' / 'step36_top1_results.csv'
    r.to_csv(out, index=False)
    print(f"\n✓ Saved: {out}")


if __name__ == '__main__':
    main()
