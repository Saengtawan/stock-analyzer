"""Step 35-C experiment: Z1-recipe universally applied to Z2/Z3/Z4.

Hypothesis: If Z1 achieves ~100% WR using:
  - label_z12_market_3dd (EOD > scan × 0.998 AND no -3% DD)
  - HP: lr=0.0678, depth=2, leaves=40, etc.
  - R9 ranking: win_p × max(0, 1-pred_r)**0.5
  - threshold ZONE_THR=0.60, ZONE_LOSS_THR=0.40

... then can we reproduce ~100% WR by applying this same recipe to Z2/Z3/Z4?

Walk-forward methodology (mirrors validate_retrain.py):
  - Test window: 2025-09-01 to 2026-04-30 (8 months OOS)
  - Monthly refit: each test month uses 840-day train ending day before month start
  - Per zone: train win/loss/adapt models (Z1 HP for ALL), pick top-1 daily,
    simulate LIMIT fill, hold to EOD.

Two configs per zone:
  A) "current" = production ZONE_LABEL/HP/CW/THR (already deployed)
  B) "z1_recipe" = label_z12_market_3dd (extended to all mfo, computed here),
                    HP=Z1 HP, cw=None, THR=0.60, LOSS_THR=0.40,
                    rank by R9 (matches Z1 prod ranking)

Note: label_z12_market_3dd in pkl is computed only for mfo ≤ 29. For Z3/Z4,
we synthesize the same formula (EOD > scan × 0.998 AND no -3% DD) using
label_z34_market — which is the SAME formula restricted to mfo ≥ 30.
So:
  Z1: pkl label_z12_market_3dd (mfo 0-9 portion)
  Z2: pkl label_z12_market_3dd (mfo 10-29 portion)
  Z3: pkl label_z34_market    (mfo 30-44 portion) ≡ same formula
  Z4: pkl label_z34_market    (mfo 45-75 portion) ≡ same formula
The two labels share an identical definition (verified in feature_builder.py
lines 754-759).

Output: /tmp/step35_C/comparison.csv + report.md
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import lightgbm as lgb

ROOT = Path('/home/saengtawan/work/project/cc/stock-analyzer')
sys.path.insert(0, str(ROOT / 'backtests'))
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, N_SEEDS, add_interactions

DB = ROOT / 'data' / 'trade_history.db'
BARS = ROOT / 'cache' / 'wf_1min_bars.db'
PKL = ROOT / 'cache' / 'bt_features' / 'features.pkl'
OUT = Path('/tmp/step35_C')
OUT.mkdir(parents=True, exist_ok=True)

# ========================================================================
# CONFIGS
# ========================================================================
ZONE_RANGE = {'Z1':(0,9), 'Z2':(10,29), 'Z3':(30,44), 'Z4':(45,75)}

# --- CONFIG A: current production (mirrored from validate_retrain.py) ---
PROD = {
    'ZONE_LABEL': {'Z1':'label_z12_market_3dd', 'Z2':'label_custom_dd',
                   'Z3':'label_smart_v2', 'Z4':'label_smart_v2'},
    'ZONE_THR':   {'Z1':0.60, 'Z2':0.65, 'Z3':0.50, 'Z4':0.50},
    'ZONE_LOSS_THR': {'Z1':0.40, 'Z2':0.20, 'Z3':0.40, 'Z4':0.50},
    'ZONE_BUF':   {'Z1':(0.005,0.0020), 'Z2':(0.005,0.0015),
                   'Z3':(0.000,0.0020), 'Z4':(0.000,0.0020)},
    'ZONE_CW':    {'Z1':None, 'Z2':None, 'Z3':2.0, 'Z4':2.0},
    'ZONE_HP': {
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
    },
    'ranking': {'Z1':'r9', 'Z2':'win', 'Z3':'win_only_smart', 'Z4':'win_only_smart'},
}

# --- CONFIG B: Z1 recipe applied to ALL zones ---
Z1_HP = dict(learning_rate=0.0678, max_depth=2, num_leaves=40, min_child_samples=44,
             reg_alpha=3.463, reg_lambda=3.818, n_estimators=600,
             bagging_fraction=0.945, feature_fraction=0.926)
Z1RECIPE = {
    'ZONE_LABEL': {z: 'label_z1formula' for z in ['Z1','Z2','Z3','Z4']},  # synthesized below
    'ZONE_THR':   {z: 0.60 for z in ['Z1','Z2','Z3','Z4']},
    'ZONE_LOSS_THR': {z: 0.40 for z in ['Z1','Z2','Z3','Z4']},
    'ZONE_BUF':   PROD['ZONE_BUF'],   # keep production buffers (entry-execution thing)
    'ZONE_CW':    {z: None for z in ['Z1','Z2','Z3','Z4']},
    'ZONE_HP':    {z: Z1_HP for z in ['Z1','Z2','Z3','Z4']},
    'ranking': {z: 'r9' for z in ['Z1','Z2','Z3','Z4']},
}

LOSS_HP = dict(learning_rate=0.03, max_depth=3, num_leaves=8, min_child_samples=50,
               reg_alpha=1.0, reg_lambda=5.0, n_estimators=300,
               bagging_fraction=0.8, feature_fraction=0.8)
ADAPT_HP = dict(objective='regression', learning_rate=0.05, max_depth=4, num_leaves=15,
                min_child_samples=30, reg_alpha=0.5, reg_lambda=1.0, n_estimators=300,
                bagging_fraction=0.8, feature_fraction=0.8)

Z4_DIP = 0.009
TRAIN_DAYS = 840
SCAN_MFOS = list(range(0, 76, 5))

# ========================================================================
# LOAD pkl + synthesize unified Z1-formula label
# ========================================================================
print(f"Loading pkl ({PKL})...", flush=True)
df = pd.read_pickle(PKL)
df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
print(f"  rows={len(df):,}, date range {df['date'].min()} → {df['date'].max()}")

# Synthesize label_z1formula = label_z12_market_3dd ∪ label_z34_market
# (both share identical formula: EOD > scan×0.998 AND no -3% DD)
df['label_z1formula'] = df['label_z12_market_3dd'].fillna(df['label_z34_market'])
print(f"  label_z1formula: avail={df['label_z1formula'].notna().sum():,} "
      f"(z12={df['label_z12_market_3dd'].notna().sum():,}, "
      f"z34={df['label_z34_market'].notna().sum():,})")

feats_avail = [f for f in V7_FEATS+CROSS_FEATS if f in df.columns]
NEW_FEATS = sorted([c for c in df.columns if c.startswith('feat_')])
df = add_interactions(df)

# Features per zone — matches validate_retrain.py
def feats_for_zone(zone):
    use_inter = zone in ('Z1','Z2')
    return feats_avail + (INTERACTIONS if use_inter else []) + NEW_FEATS

# Adaptlim label
if 'label_adaptlim' not in df.columns:
    print("Computing label_adaptlim from 1-min bars...", flush=True)
    con_b = sqlite3.connect(str(BARS))
    sym_dates = df[['sym','date']].drop_duplicates().itertuples(index=False)
    bar_cache = {}
    for sym, date in sym_dates:
        rows = con_b.execute("SELECT em, l, c FROM bars WHERE sym=? AND date=? ORDER BY em",
                             (sym,date)).fetchall()
        if rows: bar_cache[(sym, date)] = rows
    con_b.close()
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

# ========================================================================
# WALK-FORWARD: month-by-month refit
# ========================================================================
TEST_START = '2025-09-01'
TEST_END = '2026-04-30'

# Generate list of test months
def month_iter(start, end):
    s = datetime.strptime(start, '%Y-%m-%d')
    e = datetime.strptime(end, '%Y-%m-%d')
    cur = s.replace(day=1)
    while cur < e:
        if cur.month == 12:
            nxt = cur.replace(year=cur.year+1, month=1)
        else:
            nxt = cur.replace(month=cur.month+1)
        yield cur.strftime('%Y-%m-%d'), min(nxt, e).strftime('%Y-%m-%d')
        cur = nxt

months = list(month_iter(TEST_START, TEST_END))
print(f"\nWalk-forward {TEST_START} → {TEST_END}: {len(months)} monthly refits")

con_db = sqlite3.connect(str(DB))
con_b = sqlite3.connect(str(BARS))

def get_eod(sym, date):
    r = con_db.execute("SELECT close FROM intraday_bars_5m WHERE symbol=? AND DATE(timestamp)=? "
                       "AND time(timestamp)>'13:30:00' AND time(timestamp)<='20:00:00' "
                       "ORDER BY timestamp DESC LIMIT 1", (sym, date)).fetchone()
    return r[0] if r else None

def get_intraday(sym, date, mfo):
    rows = con_b.execute("SELECT em, l, c FROM bars WHERE sym=? AND date=? ORDER BY em",
                        (sym, date)).fetchall()
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


def train_zone(zone, cfg, train_start, train_end):
    """Train win/loss/adapt models for a zone with the given config."""
    feats = feats_for_zone(zone)
    LO, HI = ZONE_RANGE[zone]
    mask = ((df['date']>=train_start) & (df['date']<train_end) &
            (df['mins_from_open']>=LO) & (df['mins_from_open']<=HI))
    sub = df[mask]
    if len(sub) < 500:
        return None
    X_full = sub[feats].fillna(0).values

    # WIN model
    wl = cfg['ZONE_LABEL'][zone]
    mw = sub[wl].notna()
    if mw.sum() < 200:
        return None
    Xw = sub[mw][feats].fillna(0).values
    yw = sub[mw][wl].astype(int).values
    hp_w = {**cfg['ZONE_HP'][zone], 'objective':'binary', 'bagging_freq':1,
            'verbose':-1, 'n_jobs':4}
    cw_z = cfg['ZONE_CW'].get(zone)
    sw_w = np.where(yw == 0, cw_z, 1.0) if cw_z and cw_z > 1.0 else None
    wseeds = []
    for s in range(N_SEEDS):
        m = lgb.LGBMClassifier(**{**hp_w, 'random_state':s})
        m.fit(Xw, yw, sample_weight=sw_w)
        wseeds.append(m.booster_)

    # LOSS model
    yl = (sub['label_fixed3'] <= -1.0).astype(int).values
    hp_l = {**LOSS_HP, 'objective':'binary', 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
    lseeds = []
    for s in range(N_SEEDS):
        m = lgb.LGBMClassifier(**{**hp_l, 'random_state':s})
        m.fit(X_full, yl)
        lseeds.append(m.booster_)

    # ADAPT model
    ma = sub['label_adaptlim'].notna()
    Xa = sub[ma][feats].fillna(0).values
    ya = sub[ma]['label_adaptlim'].values
    hp_a = {**ADAPT_HP, 'bagging_freq':1, 'verbose':-1, 'n_jobs':4}
    aseeds = []
    for s in range(N_SEEDS):
        m = lgb.LGBMRegressor(**{**hp_a, 'random_state':s})
        m.fit(Xa, ya)
        aseeds.append(m.booster_)

    return {'win': wseeds, 'loss': lseeds, 'adapt': aseeds}


def simulate_month(zone, cfg, models, m_start, m_end):
    """Simulate top-1 per scan_mfo per day, return list of trade dicts."""
    feats = feats_for_zone(zone)
    LO, HI = ZONE_RANGE[zone]
    test = df[(df['date']>=m_start) & (df['date']<m_end) &
              (df['mins_from_open']>=LO) & (df['mins_from_open']<=HI)].copy()
    if 'gain_from_prev' in test.columns:
        test = test[(test['gain_from_prev']>=2) & (test['gain_from_prev']<5)]
    trades = []
    for date, g in test.groupby('date'):
        recent_syms = set()
        for mfo in [m for m in SCAN_MFOS if LO<=m<=HI]:
            zg = g[g['mins_from_open']==mfo].copy()
            zg = zg[~zg['sym'].isin(recent_syms)]
            if len(zg) == 0: continue
            X = zg[feats].fillna(0).values
            win_p = np.array([m.predict(X) for m in models['win']]).min(axis=0)
            loss_p = np.array([m.predict(X) for m in models['loss']]).max(axis=0)
            pred_r = np.array([m.predict(X) for m in models['adapt']]).mean(axis=0)
            valid = (win_p >= cfg['ZONE_THR'][zone]) & (loss_p < cfg['ZONE_LOSS_THR'][zone])
            if zone == 'Z4':
                valid &= (1 - pred_r) >= Z4_DIP
            if not valid.any(): continue
            idx = np.where(valid)[0]
            # Ranking
            rk = cfg['ranking'][zone]
            if rk == 'r9':
                cushion = np.maximum(0, 1 - pred_r[idx]) ** 0.5
                score = win_p[idx] * cushion
            else:  # 'win' or 'win_only_smart' — both rank by win_p only
                score = win_p[idx]
            top = idx[score.argmax()]
            pick = zg.iloc[top]
            sym = pick['sym']; mfo_i = int(pick['mins_from_open'])
            recent_syms.add(sym)
            scan_p, min_low, after = get_intraday(sym, date, mfo_i)
            if scan_p is None: continue
            atr = float(pick.get('feat_atr_pct_14d', 3.0))
            bb, bc = cfg['ZONE_BUF'][zone]
            pr = float(pred_r[top])
            limit = scan_p * pr * (1 + bb + bc*atr)
            if min_low <= limit:
                eod = get_eod(sym, date)
                if eod is None: continue
                pnl = (eod - limit) / limit * 100 - 0.1  # 0.1% slippage/fee
                trades.append({'date': date, 'sym': sym, 'mfo': mfo_i,
                               'scan_p': scan_p, 'limit': limit, 'eod': eod,
                               'win_p': float(win_p[top]),
                               'loss_p': float(loss_p[top]),
                               'pred_r': pr, 'pnl': pnl, 'zone': zone})
    return trades


def run_config(name, cfg):
    """Run walk-forward for all 4 zones under one config."""
    print(f"\n========== CONFIG: {name} ==========", flush=True)
    all_trades = {z: [] for z in ['Z1','Z2','Z3','Z4']}
    for m_start, m_end in months:
        train_end_dt = datetime.strptime(m_start, '%Y-%m-%d')
        train_start = (train_end_dt - timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
        train_end = m_start  # train < month, test = month
        print(f"  month {m_start[:7]}: train {train_start} → {train_end}", flush=True)
        for zone in ['Z1','Z2','Z3','Z4']:
            models = train_zone(zone, cfg, train_start, train_end)
            if models is None:
                print(f"    {zone}: skip (too few rows or label avail)")
                continue
            trades = simulate_month(zone, cfg, models, m_start, m_end)
            all_trades[zone].extend(trades)
            wr = np.mean([t['pnl']>0 for t in trades]) if trades else 0
            tot = sum(t['pnl'] for t in trades) if trades else 0
            print(f"    {zone}: N={len(trades):3d} WR={wr*100:>3.0f}% total={tot:+6.1f}%",
                  flush=True)
    return all_trades


# ========================================================================
# RUN BOTH CONFIGS
# ========================================================================
prod_trades = run_config('CURRENT (production)', PROD)
z1r_trades = run_config('Z1-RECIPE (universal)', Z1RECIPE)


# ========================================================================
# AGGREGATE
# ========================================================================
def summarize(trades_dict, label):
    rows = []
    for z in ['Z1','Z2','Z3','Z4']:
        ts = trades_dict[z]
        if not ts:
            rows.append({'config': label, 'zone': z, 'N': 0, 'WR': None,
                         'avg': None, 'total': None, 'worst': None, 'best': None})
            continue
        pnls = np.array([t['pnl'] for t in ts])
        rows.append({
            'config': label,
            'zone': z,
            'N': len(pnls),
            'WR': float((pnls > 0).mean()),
            'avg': float(pnls.mean()),
            'total': float(pnls.sum()),
            'worst': float(pnls.min()),
            'best': float(pnls.max()),
        })
    return rows

summary = summarize(prod_trades, 'current') + summarize(z1r_trades, 'z1_recipe')
sdf = pd.DataFrame(summary)
sdf.to_csv(OUT / 'comparison.csv', index=False)
print(f"\nSaved: {OUT/'comparison.csv'}")

# Save per-trade ledger too
ledger = []
for z, ts in prod_trades.items():
    for t in ts: ledger.append({**t, 'config':'current'})
for z, ts in z1r_trades.items():
    for t in ts: ledger.append({**t, 'config':'z1_recipe'})
pd.DataFrame(ledger).to_csv(OUT / 'trades_ledger.csv', index=False)
print(f"Saved: {OUT/'trades_ledger.csv'} ({len(ledger)} trades)")


# ========================================================================
# PRINT FINAL TABLE
# ========================================================================
print("\n\n========== FINAL COMPARISON ==========")
print(f"{'Zone':4s} {'Config':12s} {'N':>4s} {'WR':>6s} {'avg':>7s} {'total':>9s} {'worst':>7s}")
for z in ['Z1','Z2','Z3','Z4']:
    for cfg_name in ['current', 'z1_recipe']:
        r = sdf[(sdf.zone==z) & (sdf.config==cfg_name)].iloc[0]
        if r['N'] == 0:
            print(f"{z:4s} {cfg_name:12s} {'0':>4s} {'-':>6s} {'-':>7s} {'-':>9s} {'-':>7s}")
        else:
            print(f"{z:4s} {cfg_name:12s} {r['N']:>4d} {r['WR']*100:>5.0f}% "
                  f"{r['avg']:>+6.2f}% {r['total']:>+8.1f}% {r['worst']:>+6.2f}%")

con_db.close()
con_b.close()
print("\nDone.")
