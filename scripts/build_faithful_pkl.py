"""Build the faithful (train==serve) feature pkl + labels, current to --end.
1) feature_builder -> base pkl (macro/daily/ETF + feature_builder OHLC)
2) graft faithful OHLC (gain/range/from_peak/consol/hh/bars_since_hi) from wf_1min IEX 1-min
3) build pnl_EOD labels (standard phase0 convention) for all rows
4) add sector
Outputs: --out-pkl (faithful pkl) and --out-labels (labels pkl). Requires wf_1min already extended."""
import os, sys, argparse, subprocess, sqlite3, time
from pathlib import Path
import pandas as pd, numpy as np
ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
OHLC = ['gain_from_open','range_pct','from_peak_pct','consol','hh_count','bars_since_hi']

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2023-09-01'); ap.add_argument('--end', required=True)
    ap.add_argument('--out-pkl', default=str(ROOT/'cache/v2_faithful_current.pkl'))
    ap.add_argument('--out-labels', default='/tmp/phase0_labels_current.pkl')
    ap.add_argument('--base', default='/tmp/v2_base_build.pkl')
    a = ap.parse_args(); t0 = time.time()
    print(f"[1/4] feature_builder base -> {a.base} ({a.start}..{a.end})", flush=True)
    subprocess.run([PY, 'backtests/feature_builder.py', '--start', a.start, '--end', a.end,
                    '--output', a.base, '--limit', '500'], cwd=ROOT, check=True)
    f = pd.read_pickle(a.base); f = f.loc[:, ~f.columns.duplicated()]
    f['date'] = pd.to_datetime(f['date']).dt.strftime('%Y-%m-%d')
    sub = f[f.mins_from_open <= 75].copy()
    print(f"[2/4] graft faithful OHLC from wf_1min ({len(sub)} rows)", flush=True)
    w = sqlite3.connect(str(ROOT/'cache/wf_1min_bars.db')); bars = {}
    for s, d, em, o, h, l, cl in w.execute(f"SELECT sym,date,em,o,h,l,c FROM bars WHERE em<=650 AND date>='{a.start}'"):
        bars.setdefault((s, d), []).append((em, o, h, l, cl))
    w.close()
    for k in bars: bars[k].sort()
    def rc(sym, date, mfo):
        b = [x for x in bars.get((sym, date), []) if x[0] <= 570+mfo]
        if not b or b[0][0] != 570 or b[0][1] <= 0: return None
        o = b[0][1]; hi = max(x[2] for x in b); lo = min(x[3] for x in b); cl = b[-1][4]
        return {'gain_from_open': (cl/o-1)*100, 'range_pct': (hi-lo)/o*100,
                'from_peak_pct': (cl/hi-1)*100 if hi > 0 else 0,
                'consol': (max(x[4] for x in b)-min(x[4] for x in b))/o*100,
                'hh_count': sum(1 for i in range(1, len(b)) if b[i][2] > b[i-1][2]),
                'bars_since_hi': len(b)-1-max(range(len(b)), key=lambda i: b[i][2])}
    upd = {k: [] for k in OHLC}; ok = []
    for _, r in sub.iterrows():
        x = rc(r['sym'], r['date'], int(r['mins_from_open'])); ok.append(x is not None)
        for k in OHLC: upd[k].append(x[k] if x else r.get(k, 0))
    fa = sub.copy()
    for k in OHLC: fa[k] = upd[k]
    fa['range_exp'] = fa['range_pct']*(sub['range_exp']/sub['range_pct'].replace(0, np.nan)).fillna(0.3).values
    fa = fa[pd.Series(ok, index=sub.index)].copy()
    # sector
    if 'sector' not in fa.columns:
        fa['sector'] = fa['sector_full'] if 'sector_full' in fa.columns else None
    print(f"[3/4] build pnl_EOD labels", flush=True)
    th = sqlite3.connect(str(ROOT/'data/trade_history.db'))
    need = fa[['sym', 'date', 'mins_from_open']].drop_duplicates()
    dts = sorted(need.date.unique()); barsl = {}
    ph = ','.join('?'*len(dts))
    for s, d, t, c in th.execute(f"SELECT symbol,date,time_et,close FROM intraday_bars_5m WHERE date IN ({ph})", dts):
        m = (int(t[:2])-9)*60+(int(t[3:5])-30)
        if 0 <= m <= 400: barsl.setdefault((s, d), []).append((m, c))
    th.close()
    rows = []
    for _, r in need.iterrows():
        b = barsl.get((r['sym'], r['date']))
        if not b: continue
        b.sort(); mfo = int(r['mins_from_open'])
        ei = next((i for i, x in enumerate(b) if x[0] >= mfo), None)
        if ei is None or b[ei][1] <= 0: continue
        rows.append((r['sym'], r['date'], mfo, (b[-1][1]/b[ei][1]-1)*100))
    lab = pd.DataFrame(rows, columns=['sym', 'date', 'mins_from_open', 'pnl_EOD'])
    lab.to_pickle(a.out_labels); fa.to_pickle(a.out_pkl)
    print(f"[4/4] SAVED {a.out_pkl} ({len(fa)} rows) + {a.out_labels} ({len(lab)} labels) to {fa.date.max()} ({time.time()-t0:.0f}s)", flush=True)

if __name__ == '__main__': main()
