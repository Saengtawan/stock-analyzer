"""score snapshot ด้วย H12-A (live-faithful). validate บน snapshot วันนี้ 09:36."""
import gzip,json,sys,numpy as np
from pathlib import Path
from datetime import datetime
ROOT=Path('/home/saengtawan/work/project/cc/stock-analyzer'); sys.path.insert(0,str(ROOT))
from src.scan.alpaca_bars import extract_multibar_features
from src.scan.ml_scorer_h12a import get_scorer_h12a
from src.scan.h12a_picker import score_and_filter_h12a, get_zone
snapf=sys.argv[1] if len(sys.argv)>1 else 'data/scan_snapshots/2026-06-11_09-36-05.json.gz'
snap=json.load(gzip.open(ROOT/snapf)); date=snap['scan_ts_et'][:10]
ds=json.load(gzip.open(ROOT/f'data/scan_snapshots/db_state_{date}.json.gz'))
snaps=snap['snaps']; etf=snap['etf_snaps']; sectors=snap['sectors']; betas=snap['betas']; mcaps=snap['mcaps']
macro=snap['macro']; bars_by=snap.get('bars_by_sym',{}); mfo=snap['minutes_from_open']
dh=ds['daily_hist']; dhl=ds['daily_hl']; adv=ds['avg_daily_vol']
def ei(s):
    d=etf.get(s,{}).get('dailyBar',{}); o=d.get('o',0); c=d.get('c',0); return (c/o-1)*100 if o>0 else 0
spy_intra=ei('SPY'); secchg={k:ei(v) for k,v in {'Technology':'XLK','Healthcare':'XLV','Financial Services':'XLF','Consumer Cyclical':'XLY','Communication Services':'XLC','Industrials':'XLI','Consumer Defensive':'XLP','Energy':'XLE','Basic Materials':'XLB','Real Estate':'XLRE','Utilities':'XLU'}.items()}
sc=get_scorer_h12a()
def feats_of(sym):
    s=snaps[sym]; sec=sectors.get(sym,''); db=s['dailyBar']; pb=s['prevDailyBar']
    o=db['o']; now=db['c']; hi=db['h']; lo=db['l']; pc=pb.get('c',0)
    if o<1 or pc<1: return None,sec
    gain=(now/o-1)*100; rng=(hi-lo)/o*100; fpk=(now/hi-1)*100 if hi>0 else 0
    vw=db.get('vw',0); vsv=(now/vw-1)*100 if vw>0 else 0; gap=(o/pc-1)*100
    tv=db.get('v',0) or 0; av=adv.get(sym,0); frac=max(5,mfo+5)/390.0
    vr=min(20.,tv/(av*frac)) if av>0 else 1.0
    beta=betas.get(sym,1.5); mc=mcaps.get(sym,0) or 0
    mcb=4 if mc>=100e9 else 3 if mc>=20e9 else 2 if mc>=5e9 else 1 if mc>=500e6 else 0
    h=dh.get(sym,[]); cl=[x[1] for x in h[-21:] if x[1]]
    if len(cl)<21: return None,sec
    m5=(cl[-1]/cl[-6]-1)*100 if cl[-6] else 0; m20=(cl[-1]/cl[0]-1)*100 if cl[0] else 0
    sma=np.mean(cl[-20:]); dsma=(now/sma-1)*100
    full=[x[1] for x in h if x[1]]
    if len(full)<100: return None,sec
    p52h=(now/max(full)-1)*100; p52l=(now/min(full)-1)*100
    hl=dhl.get(sym,[]); rr=[(x[1]-x[2])/x[3]*100 for x in hl if len(x)>=4 and x[3]]; r10=np.mean(rr) if rr else 3.0
    rexp=rng/r10 if r10>0 else 1
    sb=bars_by.get(sym,[]); bf=extract_multibar_features(sb,sb[0].get('o',o)) if sb else {}
    f={'mins_from_open':mfo,'gain_from_open':gain,'range_pct':rng,'from_peak_pct':fpk,'vs_vwap':vsv,
       'vol_ratio':vr,'vol_accel':bf.get('vol_accel',1.0),'bars_since_hi':bf.get('bars_since_hi',0),
       'hh_count':bf.get('hh_count',0),'consol':bf.get('consol',rng),'range_exp':rexp,'gap_from_prev':gap,
       'beta':beta,'mcap_bucket':mcb,'spy_green':macro['spy_green'],'spy_intra':spy_intra,'vix':macro['vix'],
       'vix_5d_chg':macro['vix_5d_chg'],'ad_ratio':macro.get('ad_ratio',1.0),'mom5d':m5,'mom20d':m20,
       'dist_sma20':dsma,'pct_52w_hi':p52h,'pct_52w_lo':p52l,'dow':datetime.strptime(date,'%Y-%m-%d').weekday(),
       'btc_5d_chg':macro['btc_5d_chg'],'jpy_5d_chg':macro['jpy_5d_chg'],'skew':macro['skew'],'vvix':macro['vvix'],
       'vix_term_spread':macro.get('vix_term_spread',1.5),'sec_rel_strength':secchg.get(sec,0)-spy_intra}
    for e,col in [('XLK','xlk_intra'),('XLV','xlv_intra'),('XLF','xlf_intra'),('XLY','xly_intra'),('XLC','xlc_intra'),('XLI','xli_intra'),('XLP','xlp_intra'),('XLE','xle_intra'),('XLB','xlb_intra'),('XLRE','xlre_intra'),('XLU','xlu_intra'),('IWM','iwm_intra'),('USO','uso_intra'),('SMH','smh_intra'),('QQQ','qqq_intra'),('TLT','tlt_intra'),('LQD','lqd_intra'),('IEF','ief_intra'),('HYG','hyg_intra'),('VXX','vxx_intra'),('GLD','gld_intra'),('UUP','uup_intra'),('EEM','eem_intra'),('DBC','dbc_intra'),('IGV','igv_intra')]:
        f[col]=ei(e)
    f['anomaly_score']=0
    return f,sec
print(f"snapshot {snapf} mfo={mfo} — H12-A win_p (live-faithful):")
for sym in ['AMD','ASML','ASTS','SNDK','TXN','STX']:
    if sym not in snaps: continue
    f,sec=feats_of(sym)
    if f is None: print(f"  {sym}: skip"); continue
    wp=sc.score(f,mfo,sec)
    print(f"  {sym:<6} win_p={wp:.4f}  gain={f['gain_from_open']:+.2f}% spy_intra={f['spy_intra']:+.2f} sec={sec[:10]}")
