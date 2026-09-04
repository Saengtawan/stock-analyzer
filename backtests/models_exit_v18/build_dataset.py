"""Augment exit dataset: +SPY rollover (market dd-from-high) +sector breadth +interaction. Multi-cost NEW labels."""
import json, sqlite3, sys, numpy as np, pandas as pd, warnings, pickle, time
warnings.filterwarnings('ignore')
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'; sys.path.insert(0,ROOT)
from src.exit_ml.inference import build_features, tomin, SPEC
DB=f'{ROOT}/data/trade_history.db'; SECMAP=SPEC['sector_name_map']
P=pd.read_csv('/tmp/wf_h12a_preds.csv')
fdf=pd.read_pickle(f'{ROOT}/cache/bt_features/features_5yr_noleak.pkl'); fdf=fdf.loc[:,~fdf.columns.duplicated()]
fdf['date']=pd.to_datetime(fdf['date']).dt.strftime('%Y-%m-%d')
rf=['vix','vix_5d_chg','spy_intra','sec_rel_strength','gain_from_open']
P=P.merge(fdf[['sym','date','mins_from_open']+rf],on=['sym','date','mins_from_open'],how='left')
cells=json.load(open(f'{ROOT}/configs/h12a_cell_ratings.json'))['cells_by_zone']
GOOD={'Consumer Defensive','Basic Materials','Technology'}
def cok(z,s):
    if z=='Z4':return True
    c=cells.get(z,{}).get(s); return True if c is None else ((c['avg']>0)or(c['WR']>=50) if z=='Z1' else (c['avg']>0)and(c['WR']>=50))
def gate(r):
    z=r.zone;vix=r.vix;v5=r.vix_5d_chg;ss=r.sec_rel_strength;spy=r.spy_intra;dow=r.dow;sec=r.sector
    if z=='Z1': return not((pd.notna(vix)and vix>=20)or(pd.notna(ss)and ss<=0))
    if z=='Z2': return not(pd.notna(v5)and v5>=0)
    if z=='Z3': return not((pd.notna(ss)and ss<=0)or dow==4)
    if z=='Z4':
        if pd.isna(vix)or pd.isna(spy):return True
        return (spy>0.2 if sec in GOOD else spy>0.5) if vix<25 else spy>0.5
    return True
def ef(r): return not(r.zone=='Z1' and pd.notna(r.gain_from_open) and r.gain_from_open>4.5)
Pc=P[P.apply(lambda r:cok(r.zone,r.sector),axis=1)&(P.wp_use>=0.70)].copy()
broad=Pc.sort_values('wp_use',ascending=False).groupby(['sym','date','zone']).head(1).copy()
gated=Pc[Pc.apply(gate,axis=1)&Pc.apply(ef,axis=1)].sort_values('wp_use',ascending=False).groupby(['date','zone']).head(1)
gset=set(zip(gated.sym,gated.date,gated.zone))
broad['gated']=[(s,d,z) in gset for s,d,z in zip(broad.sym,broad.date,broad.zone)]

con=sqlite3.connect(DB); cur=con.cursor()
ALLETF=sorted({e for v in SPEC['sector_etfs'].values() for e in v})
etf_cache={}; spy_hi_cache={}
def etf_day(date):
    if date in etf_cache: return etf_cache[date]
    out={}
    for e in ALLETF:
        rr=cur.execute("SELECT time_et,open,close FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et>='09:30' AND time_et<='16:00' ORDER BY time_et",(e,date)).fetchall()
        if rr: op=rr[0][1]; out[e]={tomin(t):(c/op-1)*100 if op else 0 for t,_,c in rr}
    etf_cache[date]=out
    # SPY running-high dd map
    spy=out.get('SPY',{}); ems=sorted(spy); hi=-1e9; dd={}
    for m in ems: hi=max(hi,spy[m]); dd[m]=spy[m]-hi
    spy_hi_cache[date]=dd
    return out
def sbars(sym,date):
    rr=cur.execute("SELECT time_et,open,high,low,close,volume FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et>='09:30' AND time_et<='16:00' ORDER BY time_et",(sym,date)).fetchall()
    return [(tomin(t),o,h,l,cl,v) for t,o,h,l,cl,v in rr if cl]
def near(dd_map,em):
    ks=[k for k in dd_map if k<=em]; return dd_map[max(ks)] if ks else 0.0

COSTS=[0.3,0.75,1.5]; rows=[]; n=0; t0=time.time()
for _,r in broad.iterrows():
    sec=SECMAP.get(r.sector)
    if sec is None or sec not in SPEC['sector_etfs']: continue
    em=570+int(r.mins_from_open); fill_em=em+5
    sb=sbars(r.sym,r.date)
    if len(sb)<5: continue
    entry=next((cl for m,o,h,l,cl,v in sb if m>=em),None)
    if not entry or entry<=0: continue
    eod=sb[-1][4]; pnl_eod=(eod/entry-1)*100
    ed_full=etf_day(r.date); spy_dd=spy_hi_cache[r.date]
    se=SPEC['sector_etfs'][sec]; ed={e:ed_full[e] for e in se if e in ed_full}
    fwd=[b for b in sb if b[0]>=fill_em]
    snaps=build_features(fill_em,entry,fwd,ed,se,e_gain=r.get('gain_from_open',0.0) or 0.0,e_beta=1.0,sec_name=sec)
    closes={m:cl for m,o,h,l,cl,v in sb}
    for s in snaps:
        emn=s['em']; cur_p=s['cur_pnl']; cc=s['c']; X=list(s['X'])
        # AUG features
        sdd=near(spy_dd,emn)                                   # SPY drawdown from intraday high (<=0)
        stock_dd=X[8] if len(X)>8 else 0                       # build_features dd is index 8
        breadth=sum(1 for e in se if (ed.get(e,{}).get(emn,0)-(max([ed.get(e,{}).get(k,0) for k in ed.get(e,{}) if k<=emn] or [0])))< -0.3)
        X += [sdd, sdd*abs(stock_dd), breadth]
        c15=closes.get(emn+15); c30=closes.get(emn+30)
        d15=(c15/cc-1)*100 if c15 else None; d30=(c30/cc-1)*100 if c30 else None; dE=(eod/cc-1)*100
        drops=sum(1 for x in [d15,d30,dE] if x is not None and x<-0.5)
        rec=[r.sym,r.date,r.zone,sec,bool(r.gated),emn,emn-fill_em,cur_p,pnl_eod,1 if drops>=2 else 0]
        for cst in COSTS: rec.append(1 if (cur_p-pnl_eod)>cst else 0)
        rec.append(X); rows.append(rec)
    n+=1
    if n%1500==0: print(f"  {n}/{len(broad)} {time.time()-t0:.0f}s",flush=True)
con.close()
cols=['sym','date','zone','sector','gated','em','elapsed','cur_pnl','pnl_eod','old_lab']+[f'new_{c}' for c in COSTS]+['X']
D=pd.DataFrame(rows,columns=cols)
print(f"snaps {len(D)} xlen {len(D.X.iloc[0])} | base: OLD {D.old_lab.mean():.3f} "+" ".join(f"new{c} {D[f'new_{c}'].mean():.3f}" for c in COSTS),flush=True)
pickle.dump(D,open('/tmp/exit_aug_ds.pkl','wb')); print("saved",flush=True)
