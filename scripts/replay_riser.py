"""replay_riser.py — closest-feasible reconstruction of a MISSED riser day (e.g. 06-25 net-fail).

The bit-exact path (snap2h12a on a saved snapshot) is impossible here because the live scan failed
so NO snapshot was saved. This rebuilds an approximate snapshot from:
  - real 06-25 1-min bars (Alpaca) for the SAME 484-symbol universe + ETFs the live scan covered,
  - db_state rolled forward (prior 06-24 snapshot's daily_hist + the target-day-1 daily close),
  - macro carried from the last saved snapshot but with spy_intra/spy_green recomputed from 06-25,
then scores H12-A win_p (real model) and runs the full riser pipeline (band/identity/win_p/rollover/
mean-rank). NOT bit-exact (macro vix/skew/etc. carried, breadth approx) but FAR closer than the
band-only sim: real universe + real prices + real win_p + real gates.

Usage: replay_riser.py 2026-06-25 [base_snapshot_for_static_fields]
"""
import os, sys, gzip, json, requests, numpy as np
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path('/home/saengtawan/work/project/cc/stock-analyzer'); sys.path.insert(0, str(ROOT))
for ln in (ROOT/'.env').read_text().splitlines():
    ln=ln.strip()
    if ln and not ln.startswith('#') and '=' in ln:
        k,v=ln.split('=',1); os.environ.setdefault(k.strip(),v.strip().strip('"\''))
HDR={'APCA-API-KEY-ID':os.getenv('ALPACA_API_KEY'),'APCA-API-SECRET-KEY':os.getenv('ALPACA_SECRET_KEY')}
ET=ZoneInfo('America/New_York')
from src.scan.alpaca_bars import extract_multibar_features
from src.scan.ml_scorer_h12a import get_scorer_h12a
from src.scan import stock_track_record as STR

DATE = sys.argv[1] if len(sys.argv)>1 else '2026-06-25'
BASE = sys.argv[2] if len(sys.argv)>2 else 'data/scan_snapshots/2026-06-24_09-36-01.json.gz'
CUTOFF = 9*60+36   # 09:36 ET, mfo=6
MFO = 6

base=json.load(gzip.open(ROOT/BASE))
universe=list(base['snaps'].keys()); etfs=list(base['etf_snaps'].keys())
betas=base['betas']; mcaps=base['mcaps']; sectors=base['sectors']
ds=json.load(gzip.open(ROOT/'data/scan_snapshots/db_state_2026-06-24.json.gz'))
dh=ds['daily_hist']; dhl=ds['daily_hl']; adv=ds['avg_daily_vol']

def fetch_1m(syms, date):
    out={}
    for i in range(0,len(syms),100):
        p={'symbols':','.join(syms[i:i+100]),'timeframe':'1Min','start':f'{date}T13:30:00Z','end':f'{date}T20:05:00Z','limit':10000,'feed':'sip'}
        r=requests.get('https://data.alpaca.markets/v2/stocks/bars',headers=HDR,params=p,timeout=40)
        if r.status_code!=200 or not r.json().get('bars'):
            p['feed']='iex'; r=requests.get('https://data.alpaca.markets/v2/stocks/bars',headers=HDR,params=p,timeout=40)
        if r.status_code==200: out.update(r.json().get('bars',{}))
    return out

def fetch_daily(syms, date):
    out={}
    for i in range(0,len(syms),100):
        p={'symbols':','.join(syms[i:i+100]),'timeframe':'1Day','start':date,'end':date,'limit':5000,'feed':'sip'}
        r=requests.get('https://data.alpaca.markets/v2/stocks/bars',headers=HDR,params=p,timeout=30)
        if r.status_code!=200 or not r.json().get('bars'):
            p['feed']='iex'; r=requests.get('https://data.alpaca.markets/v2/stocks/bars',headers=HDR,params=p,timeout=30)
        if r.status_code==200:
            for s,b in r.json().get('bars',{}).items():
                if b: out[s]=b[-1]['c']
    return out

def etmin(t):
    d=datetime.fromisoformat(t.replace('Z','+00:00')).astimezone(ET); return d.hour*60+d.minute

def snap_at(bars, cutoff):
    b=[x for x in bars if etmin(x['t'])<=cutoff]
    if not b: return None
    tv=sum(x['v'] for x in b) or 1
    return {'o':b[0]['o'],'h':max(x['h'] for x in b),'l':min(x['l'] for x in b),'c':b[-1]['c'],
            'v':sum(x['v'] for x in b),'vw':sum(x['v']*x.get('vw',x['c']) for x in b)/tv}, b

print(f"replay {DATE} (closest, macro approx) | universe {len(universe)} + {len(etfs)} ETFs ...")
allbars=fetch_1m(universe+etfs, DATE)
prevclose=fetch_daily(universe, '2026-06-24')   # day-1 close to roll daily_hist forward
print(f"  got 1-min for {sum(1 for s in universe if allbars.get(s))}/{len(universe)} | prevclose {len(prevclose)}")

# ETF intraday (09:36)
def etf_intra(e):
    sn=snap_at(allbars.get(e,[]),CUTOFF)
    if not sn: return 0.0
    d=sn[0]; return (d['c']/d['o']-1)*100 if d['o']>0 else 0.0
spy_intra=etf_intra('SPY'); spy_green=1 if spy_intra>0 else 0
secmap={'Technology':'XLK','Healthcare':'XLV','Financial Services':'XLF','Consumer Cyclical':'XLY','Communication Services':'XLC','Industrials':'XLI','Consumer Defensive':'XLP','Energy':'XLE','Basic Materials':'XLB','Real Estate':'XLRE','Utilities':'XLU'}
secchg={k:etf_intra(v) for k,v in secmap.items()}
macro=dict(base['macro']); macro['spy_green']=spy_green   # carry vix/skew/etc, refresh spy
print(f"  macro: vix={macro['vix']} (carry 06-24) spy_intra={spy_intra:+.2f} (06-25 real)")

sc=get_scorer_h12a()
etfintra={e:etf_intra(e) for e in etfs}

def feats(sym):
    sn=snap_at(allbars.get(sym,[]),CUTOFF)
    if not sn: return None,None
    d,raw=sn; sec=sectors.get(sym,''); o=d['o']; now=d['c']; hi=d['h']; lo=d['l']
    if o<1: return None,sec
    hist=list(dh.get(sym,[]))
    pc=prevclose.get(sym)
    if pc: hist=hist+[['2026-06-24',pc]]      # roll forward to day-1
    cl=[x[1] for x in hist[-21:] if x[1]]
    if len(cl)<21: return None,sec
    prev=cl[-1]
    gain=(now/o-1)*100; rng=(hi-lo)/o*100; fpk=(now/hi-1)*100 if hi>0 else 0
    vw=d.get('vw',0); vsv=(now/vw-1)*100 if vw>0 else 0; gap=(o/prev-1)*100 if prev else 0
    tv=d.get('v',0) or 0; av=adv.get(sym,0); frac=max(5,MFO+5)/390.0
    vr=min(20.,tv/(av*frac)) if av>0 else 1.0
    mc=mcaps.get(sym,0) or 0
    mcb=4 if mc>=100e9 else 3 if mc>=20e9 else 2 if mc>=5e9 else 1 if mc>=500e6 else 0
    m5=(cl[-1]/cl[-6]-1)*100 if cl[-6] else 0; m20=(cl[-1]/cl[0]-1)*100 if cl[0] else 0
    sma=np.mean(cl[-20:]); dsma=(now/sma-1)*100
    full=[x[1] for x in hist if x[1]]
    if len(full)<100: return None,sec
    p52h=(now/max(full)-1)*100; p52l=(now/min(full)-1)*100
    hl=dhl.get(sym,[]); rr=[(x[1]-x[2])/x[3]*100 for x in hl if len(x)>=4 and x[3]]; r10=np.mean(rr) if rr else 3.0
    rexp=rng/r10 if r10>0 else 1
    bf=extract_multibar_features(raw,raw[0].get('o',o)) if raw else {}
    f={'mins_from_open':MFO,'gain_from_open':gain,'range_pct':rng,'from_peak_pct':fpk,'vs_vwap':vsv,
       'vol_ratio':vr,'vol_accel':bf.get('vol_accel',1.0),'bars_since_hi':bf.get('bars_since_hi',0),
       'hh_count':bf.get('hh_count',0),'consol':bf.get('consol',rng),'range_exp':rexp,'gap_from_prev':gap,
       'beta':betas.get(sym,1.5),'mcap_bucket':mcb,'spy_green':macro['spy_green'],'spy_intra':spy_intra,
       'vix':macro['vix'],'vix_5d_chg':macro['vix_5d_chg'],'ad_ratio':macro.get('ad_ratio',1.0),
       'mom5d':m5,'mom20d':m20,'dist_sma20':dsma,'pct_52w_hi':p52h,'pct_52w_lo':p52l,
       'dow':datetime.strptime(DATE,'%Y-%m-%d').weekday(),'btc_5d_chg':macro['btc_5d_chg'],
       'jpy_5d_chg':macro['jpy_5d_chg'],'skew':macro['skew'],'vvix':macro['vvix'],
       'vix_term_spread':macro.get('vix_term_spread',1.5),'sec_rel_strength':secchg.get(sec,0)-spy_intra}
    etcol={'XLK':'xlk_intra','XLV':'xlv_intra','XLF':'xlf_intra','XLY':'xly_intra','XLC':'xlc_intra','XLI':'xli_intra','XLP':'xlp_intra','XLE':'xle_intra','XLB':'xlb_intra','XLRE':'xlre_intra','XLU':'xlu_intra','IWM':'iwm_intra','USO':'uso_intra','SMH':'smh_intra','QQQ':'qqq_intra','TLT':'tlt_intra','LQD':'lqd_intra','IEF':'ief_intra','HYG':'hyg_intra','VXX':'vxx_intra','GLD':'gld_intra','UUP':'uup_intra','EEM':'eem_intra','DBC':'dbc_intra','IGV':'igv_intra'}
    for e,c in etcol.items(): f[c]=etfintra.get(e,0.0)
    f['anomaly_score']=0
    return f,sec,raw

# score all Z1 (mfo 0-9 -> all here since MFO=6), band 2-6
rows=[]
for sym in universe:
    r=feats(sym)
    if r[0] is None: continue
    f,sec,raw=r
    g=f['gain_from_open']
    if not (2<=g<=6): continue
    wp=sc.score(f,MFO,sec)
    # rollover from raw 1-min
    op=raw[0]['o']; gb=((max(x['h'] for x in raw)/op-1)-(raw[-1]['c']/op-1))*100 if op>0 else 0
    rows.append(dict(sym=sym,gain=g,win_p=wp,sec=sec,price=f and raw[-1]['c'],giveback=gb))
print(f"\nband 2-6: {len(rows)} candidates (real universe, real win_p)")
# pipeline: identity -> win_p>=0.45 -> rollover<=1 -> mean-rank
rows=[r for r in rows if STR.passes_gate(r['sym'],DATE,min_n=8)]
rows=[r for r in rows if r['win_p']>=0.45]
rows=[r for r in rows if r['giveback']<=1.0]
print(f"after identity+win_p0.45+rollover: {len(rows)}")
bg=sorted(rows,key=lambda r:-r['gain']); gr={id(r):i+1 for i,r in enumerate(bg)}
bw=sorted(rows,key=lambda r:-r['win_p']); wr={id(r):i+1 for i,r in enumerate(bw)}
rows.sort(key=lambda r:(gr[id(r)]+wr[id(r)])/2)
print("\n>>> CLOSEST replay top-5 (mean-rank):")
for r in rows[:5]:
    print(f"  {r['sym']:6} gain {r['gain']:+.1f}%  win_p {r['win_p']:.3f}  giveback {r['giveback']:.1f}%  sec {r['sec'][:12]}")
print(f"\n  top-2 pick = {[r['sym'] for r in rows[:2]]}")
