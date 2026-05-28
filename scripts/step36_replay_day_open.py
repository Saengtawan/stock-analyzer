"""
Step 36 — Replay test: would day_open fix have improved live WR?

For each live pick since 2026-04-28:
1. Find trainer pkl row at SAME (sym, date, mfo) — has CORRECT features (RTH day_open)
2. Score with current Step 33 prod models
3. Compare: would this pick still pass threshold?
4. Subset that still passes → check WR vs original 47%/62%

Skipped picks (not in pkl) get bucketed for diagnostics.

Output: per-zone WR before vs after fix + drift breakdown.
"""
import sys
import sqlite3
import json
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backtests'))
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions

JOURNAL = ROOT / 'data' / 'scan_journal.db'
PKL = ROOT / 'cache' / 'bt_features' / 'features.pkl'
PROD = ROOT / 'backtests' / 'models_prod_v22'

# Step 33 prod config
ZONE_THR = {'Z1': 0.60, 'Z2': 0.65, 'Z3': 0.50, 'Z4': 0.50}
ZONE_LOSS_THR = {'Z1': 0.40, 'Z2': 0.40, 'Z3': 0.40, 'Z4': 0.40}
ZONE_RANGE = {'Z1': (0, 9), 'Z2': (10, 29), 'Z3': (30, 44), 'Z4': (45, 75)}
Z4_DIP = 0.009


def mfo_to_zone(mfo):
    for z, (lo, hi) in ZONE_RANGE.items():
        if lo <= mfo <= hi:
            return z
    return None


def load_models():
    models = {'win': {}, 'loss': {}, 'adapt': {}, 'adaptopt': {}}
    for zone in ['Z1', 'Z2', 'Z3', 'Z4']:
        models['win'][zone] = [lgb.Booster(model_file=str(PROD / f'lgb_tp1_{zone}_seed{s}.txt')) for s in range(5)]
        models['loss'][zone] = [lgb.Booster(model_file=str(PROD / f'lgb_loss_{zone}_seed{s}.txt')) for s in range(5)]
        models['adapt'][zone] = [lgb.Booster(model_file=str(PROD / f'lgb_adaptlim_{zone}_seed{s}.txt')) for s in range(5)]
        if zone in ('Z3', 'Z4'):
            models['adaptopt'][zone] = [lgb.Booster(model_file=str(PROD / f'lgb_adaptopt_{zone}_seed{s}.txt')) for s in range(5)]
    return models


def predict_zone(models, zone, X):
    win_p = np.array([m.predict(X) for m in models['win'][zone]]).min(axis=0)
    loss_p = np.array([m.predict(X) for m in models['loss'][zone]]).max(axis=0)
    pred_r = np.array([m.predict(X) for m in models['adapt'][zone]]).mean(axis=0)
    return win_p, loss_p, pred_r


def main():
    print("Step 36 — Day_open fix replay test\n", flush=True)

    # 1. Load live picks with outcomes
    con = sqlite3.connect(str(JOURNAL))
    picks = pd.read_sql("""
        SELECT sp.id AS pick_id, sp.scan_date, sp.symbol, sp.bucket, sp.entry, sp.ml_prob,
               sp.ml_threshold, sp.features_json,
               po.pnl_pct, po.exit_reason
        FROM scan_picks sp
        LEFT JOIN pick_outcomes po ON sp.id = po.pick_id
        WHERE sp.strategy = 'ml_filter' AND sp.scan_date >= '2026-04-28'
        ORDER BY sp.scan_date
    """, con)
    con.close()
    print(f"Live picks loaded (raw): {len(picks)}")
    # DEDUP: ABBV 04-30 has 18 duplicate rows (journal logging bug). Keep first per (sym,date,bucket).
    before = len(picks)
    picks = picks.sort_values('pick_id').drop_duplicates(subset=['symbol', 'scan_date', 'bucket'], keep='first')
    print(f"  after dedup (sym,date,bucket): {len(picks)} ({before-len(picks)} dups removed)")
    print(f"  with outcomes: {picks['pnl_pct'].notna().sum()}\n")

    # 2. Load trainer pkl
    print("Loading trainer pkl...", flush=True)
    df = pd.read_pickle(PKL)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    feats_avail = [f for f in V7_FEATS + CROSS_FEATS if f in df.columns]
    NEW_FEATS = sorted([c for c in df.columns if c.startswith('feat_')])
    df = add_interactions(df)
    feats_by_zone = {
        'Z1': feats_avail + INTERACTIONS + NEW_FEATS,
        'Z2': feats_avail + INTERACTIONS + NEW_FEATS,
        'Z3': feats_avail + NEW_FEATS,
        'Z4': feats_avail + NEW_FEATS,
    }
    print(f"  pkl shape: {df.shape}, last date: {df['date'].max()}\n", flush=True)

    # 3. Match picks to pkl rows via mfo (parse from features_json) or bucket
    # Get mfo from agent B csv since it parsed bucket→mfo correctly
    agB = pd.read_csv(ROOT / 'backtests' / 'research_step36' / 'agent_B_day_open.csv')
    picks = picks.merge(agB[['pick_id', 'mfo', 'zone']], on='pick_id', how='left')
    print(f"After mfo merge: {picks['mfo'].notna().sum()}/{len(picks)} have mfo\n")

    # 4. Load models
    print("Loading prod models...", flush=True)
    models = load_models()
    print("  models loaded\n")

    # 5. For each pick: find pkl row, score with corrected features
    print("Scoring picks with corrected features (from pkl)...\n", flush=True)
    results = []
    # Build lookup: (sym, date, mfo) → row index
    key_to_idx = {(r.sym, r.date, r.mins_from_open): i for i, r in enumerate(df.itertuples(index=False))}

    for _, p in picks.iterrows():
        if pd.isna(p['mfo']):
            continue
        sym, date, mfo, zone = p['symbol'], p['scan_date'], int(p['mfo']), p['zone']
        idx = key_to_idx.get((sym, date, mfo))
        if idx is None:
            results.append({
                'pick_id': p['pick_id'], 'sym': sym, 'date': date, 'mfo': mfo, 'zone': zone,
                'in_pkl': False, 'corrected_pass': None,
                'pnl_pct': p['pnl_pct'], 'live_ml_prob': p['ml_prob']
            })
            continue

        row = df.iloc[idx]
        feats = feats_by_zone[zone]
        X = pd.DataFrame([row[feats].fillna(0).values], columns=feats).values
        win_p, loss_p, pred_r = predict_zone(models, zone, X)
        win_p, loss_p, pred_r = float(win_p[0]), float(loss_p[0]), float(pred_r[0])

        thr = ZONE_THR[zone]
        loss_thr = ZONE_LOSS_THR[zone]
        pass_win = win_p >= thr
        pass_loss = loss_p < loss_thr
        pass_dip = (zone != 'Z4') or ((1 - pred_r) >= Z4_DIP)
        corrected_pass = pass_win and pass_loss and pass_dip

        results.append({
            'pick_id': p['pick_id'], 'sym': sym, 'date': date, 'mfo': mfo, 'zone': zone,
            'in_pkl': True,
            'live_ml_prob': p['ml_prob'],
            'corrected_win_p': win_p, 'corrected_loss_p': loss_p, 'corrected_pred_r': pred_r,
            'pass_win': pass_win, 'pass_loss': pass_loss, 'pass_dip': pass_dip,
            'corrected_pass': corrected_pass,
            'pnl_pct': p['pnl_pct']
        })

    r = pd.DataFrame(results)
    print("=== Summary by zone ===\n", flush=True)
    print(f"{'Zone':5s} {'N':>4s} {'inPkl':>5s} {'LiveWR':>7s} {'CorrPass':>9s} {'AfterWR':>8s} {'Filtered':>10s}")

    for zone in ['Z1', 'Z2', 'Z3', 'Z4']:
        zr = r[r['zone'] == zone].copy()
        if len(zr) == 0:
            print(f"{zone:5s} {'0':>4s}")
            continue
        n = len(zr)
        n_pkl = zr['in_pkl'].sum()
        zr_o = zr[zr['pnl_pct'].notna()].copy()
        live_wr = (zr_o['pnl_pct'] > 0).mean() * 100 if len(zr_o) else 0
        # After fix: only picks that still pass corrected scoring
        corr = zr[(zr['in_pkl']) & (zr['corrected_pass'] == True)]
        corr_o = corr[corr['pnl_pct'].notna()]
        after_wr = (corr_o['pnl_pct'] > 0).mean() * 100 if len(corr_o) else 0
        filtered_out = zr[(zr['in_pkl']) & (zr['corrected_pass'] == False)]
        filtered_loss = (filtered_out['pnl_pct'] < 0).sum() if 'pnl_pct' in filtered_out else 0
        filtered_win = (filtered_out['pnl_pct'] > 0).sum() if 'pnl_pct' in filtered_out else 0
        print(f"{zone:5s} {n:>4d} {n_pkl:>5d} {live_wr:>6.0f}% {len(corr):>5d}/{n_pkl} {after_wr:>7.0f}% {filtered_win}w/{filtered_loss}l filtered")

    # Detail: which losers would the fix have caught?
    print("\n=== Losers the fix would CATCH (filtered out, was loss) ===\n")
    catches = r[(r['in_pkl']) & (r['corrected_pass'] == False) & (r['pnl_pct'] < 0)].sort_values('pnl_pct')
    if len(catches):
        print(catches[['date', 'sym', 'zone', 'mfo', 'live_ml_prob', 'corrected_win_p', 'pnl_pct']].to_string(index=False))
    else:
        print("  (none)")

    # Detail: winners the fix would KILL (filtered out, was win)
    print("\n=== Winners the fix would KILL (filtered out, was win) ===\n")
    kills = r[(r['in_pkl']) & (r['corrected_pass'] == False) & (r['pnl_pct'] > 0)].sort_values('pnl_pct', ascending=False)
    if len(kills):
        print(kills[['date', 'sym', 'zone', 'mfo', 'live_ml_prob', 'corrected_win_p', 'pnl_pct']].head(20).to_string(index=False))
    else:
        print("  (none)")

    # Overall summary
    print("\n=== OVERALL ===")
    all_o = r[r['pnl_pct'].notna()]
    live_n = len(all_o)
    live_wr = (all_o['pnl_pct'] > 0).mean() * 100
    in_pkl = all_o[all_o['in_pkl'] == True]
    print(f"All picks with outcome: {live_n}, live WR {live_wr:.0f}%")
    print(f"  in pkl: {len(in_pkl)} ({len(in_pkl)/live_n*100:.0f}%)")
    print(f"  NOT in pkl: {live_n - len(in_pkl)} ({(live_n-len(in_pkl))/live_n*100:.0f}%) — universe gap")
    if len(in_pkl):
        corr = in_pkl[in_pkl['corrected_pass'] == True]
        print(f"\nAfter day_open fix (pkl-matched subset):")
        print(f"  Would still pass: {len(corr)}/{len(in_pkl)} ({len(corr)/len(in_pkl)*100:.0f}%)")
        if len(corr):
            print(f"  New WR: {(corr['pnl_pct'] > 0).mean()*100:.0f}%")

    # Save full results
    out = ROOT / 'backtests' / 'research_step36' / 'step36_replay_results.csv'
    r.to_csv(out, index=False)
    print(f"\n✓ Saved: {out}")


if __name__ == '__main__':
    main()
