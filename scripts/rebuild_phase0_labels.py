"""Rebuild phase0 labels (pnl_EOD + horizons) from 5-min bars for all feature rows.
import os
Matches /tmp/phase0_labels_5yr.pkl format: sym,date,mins_from_open,pnl_EOD,pnl_+30,+60,+90
"""
import sqlite3, time, warnings
import pandas as pd, numpy as np
warnings.filterwarnings('ignore')

ROOT = '/home/saengtawan/work/project/cc/stock-analyzer'
t0 = time.time()

# Feature rows we need labels for
feat = pd.read_pickle(f'{ROOT}/cache/bt_features/features_5yr_noleak.pkl')
feat['date'] = pd.to_datetime(feat['date']).dt.strftime('%Y-%m-%d')
need = feat[['sym','date','mins_from_open']].drop_duplicates()
print(f"Need labels for {len(need):,} rows, {need.sym.nunique()} syms, {need.date.nunique()} days")

def mins(t): return (int(t[:2])-9)*60 + (int(t[3:5])-30)

con = sqlite3.connect(f'{ROOT}/data/trade_history.db')
syms = sorted(need.sym.unique())
out_rows = []

for i, sym in enumerate(syms):
    # Load all regular-session bars for this symbol
    rows = con.execute(
        "SELECT date, time_et, close FROM intraday_bars_5m WHERE symbol=? ORDER BY date, time_et",
        (sym,)).fetchall()
    if not rows: continue
    # group by date
    by_date = {}
    for d, t, cl in rows:
        m = mins(t)
        if m < 0 or m > 400: continue  # regular session only (09:30-16:00)
        by_date.setdefault(d, []).append((m, cl))
    # for each needed (date, mfo)
    sub = need[need.sym == sym]
    for _, r in sub.iterrows():
        d = r['date']; mfo = int(r['mins_from_open'])
        bars = by_date.get(d)
        if not bars: continue
        bars.sort()
        ms = [b[0] for b in bars]; cls = [b[1] for b in bars]
        # entry = first bar with m >= mfo
        ei = next((j for j,m in enumerate(ms) if m >= mfo), None)
        if ei is None: continue
        entry = cls[ei]
        if entry <= 0: continue
        eod = cls[-1]
        def at(target):
            j = next((k for k,m in enumerate(ms) if m >= mfo+target), None)
            return cls[j] if j is not None else eod
        out_rows.append({
            'sym': sym, 'date': d, 'mins_from_open': mfo,
            'pnl_EOD': (eod/entry-1)*100,
            'pnl_+30': (at(30)/entry-1)*100,
            'pnl_+60': (at(60)/entry-1)*100,
            'pnl_+90': (at(90)/entry-1)*100,
        })
    if (i+1) % 50 == 0:
        print(f"  {i+1}/{len(syms)} syms | {len(out_rows):,} labels | {(time.time()-t0)/60:.1f}min")

con.close()
df = pd.DataFrame(out_rows)
df.to_pickle(os.environ.get('PHASE0_LABELS_OUT','/tmp/phase0_labels_5yr.pkl'))
print(f"\nSaved {len(df):,} labels to /tmp/phase0_labels_5yr.pkl | {(time.time()-t0)/60:.1f}min")
print(f"Date range: {df.date.min()} → {df.date.max()}")
print(f"Sample pnl_EOD stats: mean={df.pnl_EOD.mean():.2f}% std={df.pnl_EOD.std():.2f}%")
