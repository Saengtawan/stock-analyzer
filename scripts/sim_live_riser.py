"""Sim-live replay: run the DEPLOYED riser config on saved live-faithful snapshots.
Mirrors riser_capture.sh gates exactly (band + vix + identity), reads .env flags.
Outcome = correct riser label (entry 09:35-bar close, exit 15:55-bar close)."""
import os, sys, gzip, json, glob, sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
for ln in (ROOT/'.env').read_text().splitlines():
    ln = ln.strip()
    if ln and not ln.startswith('#') and '=' in ln:
        k, v = ln.split('=', 1); os.environ.setdefault(k.strip(), v.strip().strip('"\''))
from src.scan import stock_track_record as STR
MIN_G = float(os.environ.get('RISER_MIN_GAIN', '2')); MAX_G = float(os.environ.get('RISER_MAX_GAIN', '3.5'))
VIX_GATE = os.environ.get('RISER_VIX_GATE', '0') == '1'; ID_GATE = os.environ.get('RISER_IDENTITY_GATE', '0') == '1'
ID_MINN = 8
th = sqlite3.connect(str(ROOT/'data/trade_history.db'))
def label(s, d):
    e = th.execute("SELECT close FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et='09:35'", (s, d)).fetchone()
    x = th.execute("SELECT close FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et='15:55'", (s, d)).fetchone()
    return (x[0]/e[0]-1)*100 if (e and x and e[0] > 0) else None
def vix_prior(d):
    r = th.execute("SELECT vix_close FROM macro_snapshots WHERE vix_close IS NOT NULL AND date<? ORDER BY date DESC LIMIT 1", (d,)).fetchone()
    return r[0] if r else None
print(f"sim-live riser | band {MIN_G}-{MAX_G} | vix_gate={'ON' if VIX_GATE else 'off'} | id_gate={'ON(n>={})'.format(ID_MINN) if ID_GATE else 'off'}\n")
print(f" {'date':<11} {'LIVE(gain)':<16} {'DEPLOYED':<18}")
tot_b = tot_d = 0; nb = nd = 0
for fp in sorted(glob.glob(str(ROOT/'data/scan_snapshots/*_09-37*.json.gz'))):
    d = fp.split('/')[-1][:10]
    snap = json.load(gzip.open(fp)); cands = []
    for sym, s in snap['snaps'].items():
        db = s.get('dailyBar', {}); o = db.get('o', 0); now = db.get('c', 0); pc = s.get('prevDailyBar', {}).get('c', 0)
        if o < 1 or now < 1 or pc < 1: continue
        g = (now/o-1)*100
        if MIN_G <= g <= MAX_G: cands.append({'sym': sym, 'gain': g})
    cands.sort(key=lambda x: -x['gain'])
    base = cands[0] if cands else None
    v = vix_prior(d)
    if VIX_GATE and v is not None and v >= 20:
        dep = None  # abstain
    else:
        pool = [c for c in cands if (not ID_GATE) or STR.passes_gate(c['sym'], d, min_n=ID_MINN)]
        dep = pool[0] if pool else None
    bl = label(base['sym'], d) if base else None
    dl = label(dep['sym'], d) if dep else None
    if bl is not None: tot_b += bl; nb += 1
    if dep is None or dl is not None:
        tot_d += (dl or 0); nd += 1
    print(f" {d:<11} {(base['sym']+' '+'%+.1f'%bl) if (base and bl is not None) else 'na':<16} {(dep['sym']+' '+'%+.1f'%dl) if (dep and dl is not None) else ('ABSTAIN' if dep is None else 'na'):<18}")
print(f"\n รวม: LIVE(gain) {tot_b:+.1f}% ({nb}ไม้) | DEPLOYED {tot_d:+.1f}% ({nd}ไม้-รวม abstain)")
print(f" หมายเหตุ: N={nb} วัน = noise, ดู forward สะสม")
th.close()
