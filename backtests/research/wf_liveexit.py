"""CORRECTNESS rebuild: evaluate on LIVE-ACTUAL exit (hold-to-EOD Z1-Z3, -3%SL Z4),
realistic fill (entry=CLOSE of entry bar, not open). Decompose: current-live (binary,
hold-EOD) vs new-selection (hold-EOD) vs new-sel+exit-timing. Show label_fixed3 ref + the
open-fill vs close-fill sensitivity. 9-seed x 2 sets."""
import sys, warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, lightgbm as lgb, sqlite3
from datetime import datetime, timedelta
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'; sys.path.insert(0,f'{ROOT}/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions
ZHP={'Z1':dict(learning_rate=0.05,max_depth=3,num_leaves=24,min_child_samples=50,reg_alpha=1.0,reg_lambda=1.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.9),
 'Z2':dict(learning_rate=0.03,max_depth=5,num_leaves=47,min_child_samples=80,reg_alpha=0.5,reg_lambda=3.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8),
 'Z3':dict(learning_rate=0.05,max_depth=4,num_leaves=31,min_child_samples=30,reg_alpha=0.5,reg_lambda=1.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8),
 'Z4':dict(learning_rate=0.05,max_depth=3,num_leaves=8,min_child_samples=30,reg_alpha=1.0,reg_lambda=3.0,n_estimators=400,bagging_fraction=0.7,feature_fraction=0.7)}
LOSS_HP=dict(learning_rate=0.03,max_depth=3,num_leaves=8,min_child_samples=50,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8)
RK=['learning_rate','max_depth','num_leaves','min_child_samples','reg_alpha','reg_lambda','n_estimators','bagging_fraction','feature_fraction']
PATH=['path_r_squared','path_peak_diff','path_low_diff','path_consol_range','path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel','path_momentum_accel','path_speed_early','path_up_vol_ratio','path_support_touches','path_bar_size_trend','path_wick_ratio','path_lower_wick_ratio','path_gap_ratio','path_time_at_high','path_vol_at_peaks','path_vwap_slope','path_ret_skewness']
ZCFG={'Z1':(0,9,True,'label_z12_market_3dd',False,0.40,30),'Z2':(10,29,True,'label_eod_green_v2',True,0.20,60),
      'Z3':(30,44,False,'label_z34_market',True,0.40,60),'Z4':(45,75,False,'label_z34_market',False,0.50,None)}
WIN_THR=0.75; TRAIN_DAYS=840
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']; HOLD=['2026-03','2026-04','2026-05']
df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
av=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]; NEW=sorted([c for c in df.columns if c.startswith('feat_')])
con=sqlite3.connect(f'{ROOT}/data/trade_history.db'); barcache={}
def fitb(X,y,hp,seeds): return [lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}).fit(X,y) for s in seeds]
def grade(tv,v): qs=pd.Series(tv).quantile([.25,.5,.75]).values; return np.digitize(np.asarray(v,dtype=float),qs).astype(int)
def to_min(t): h,m=t.split(':'); return int(h)*60+int(m)
def getbars(sym,date):
    k=(sym,date)
    if k not in barcache:
        barcache[k]=[(to_min(t),o,lo,c) for t,o,lo,c in con.execute("SELECT time_et,open,low,close FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et>='09:30' AND time_et<='16:00' ORDER BY time_et",(sym,date)).fetchall()]
    return barcache[k]
def at(bars,tm):
    sel=None
    for b in bars:
        if b[0]<=tm: sel=b
        else: break
    return sel
def trade_ret(sym,date,etime,exitH,fill,sl=None):
    bars=getbars(sym,date)
    if not bars: return None
    em=to_min(etime); eb=at(bars,em)
    if eb is None: return None
    entry=eb[3] if fill=='close' else eb[1]  # close-fill realistic vs open-fill
    if entry<=0: return None
    tgt=to_min('15:55') if exitH is None else em+exitH
    fwd=[b for b in bars if em<b[0]<=tgt] if fill=='close' else [b for b in bars if em<=b[0]<=tgt]
    if sl is not None:
        for b in fwd:
            if b[2] <= entry*(1-sl): return -sl*100  # -3% SL hit (low)
    xb=at(bars,tgt)
    return None if xb is None else (xb[3]/entry-1)*100
def picks(z,seeds):
    lo,hi,ui,wlab,usep,lth,exitH=ZCFG[z]; feats=av+(INTERACTIONS if ui else [])+NEW+(PATH if usep else [])
    zdf=df[(df.mins_from_open>=lo)&(df.mins_from_open<=hi)].copy(); rows=[]
    for tm in MONTHS:
        ts=tm+'-01'; cut=(datetime.strptime(ts,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
        tr=zdf[(zdf.date>=cut)&(zdf.date<ts)]; te=zdf[zdf.month==tm].copy()
        if len(tr)<1000 or len(te)==0: continue
        yw=tr[wlab]; mw=yw.notna()
        if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
        wm=fitb(tr[mw][feats].fillna(0).values,yw[mw].astype(int).values,ZHP[z],seeds)
        te['wp']=np.min([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in wm],axis=0)
        lm=fitb(tr[feats].fillna(0).values,(tr['label_fixed3']<=-1.0).astype(int).values,LOSS_HP,seeds)
        te['lp']=np.max([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in lm],axis=0)
        if z=='Z1':
            trw=tr[mw].copy(); trw['_g']=grade(trw['label_fixed3'].values,trw['label_fixed3'].values)
            s=trw.sort_values('date'); grp=s.groupby('date',sort=False).size().values; rhp={k:ZHP[z][k] for k in RK}
            rms=[lgb.LGBMRanker(**{**rhp,'objective':'lambdarank','lambdarank_truncation_level':1,'bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':sd}).fit(s[feats].fillna(0).values,s['_g'].astype(int).values,group=grp) for sd in seeds]
            te['rk']=np.mean([m.predict(te[feats].fillna(0).values) for m in rms],axis=0)
        else: te['rk']=te['wp']
        rows.append(te[['sym','date','time','month','label_fixed3','wp','lp','rk','range_pct']])
    D=pd.concat(rows,ignore_index=True)
    old=D[(D.wp>=WIN_THR)&(D.lp<=lth)].sort_values('wp',ascending=False).groupby('date').head(1)
    if z=='Z1': new=D[D.lp<=lth].sort_values('rk',ascending=False).groupby('date').head(1)
    elif z=='Z2': new=D[(D.wp>=WIN_THR)&(D.lp<=lth)].sort_values('range_pct',ascending=True).groupby('date').head(1)
    else: new=D[(D.wp>=WIN_THR)&(D.lp<=lth)].sort_values('wp',ascending=False).groupby('date').head(1)
    return old[old.month.isin(HOLD)], new[new.month.isin(HOLD)], exitH
def wr(g,exitH,fill,sl):
    rr=[trade_ret(r['sym'],r['date'],r['time'],exitH,fill,sl) for _,r in g.iterrows()]; rr=[x for x in rr if x is not None]
    if not rr: return "N=0"
    a=np.array(rr); return f"N={len(a)} WR={(a>0).mean()*100:4.1f}% tot={a.sum():+5.0f} worst={a.min():+5.1f}"
print("=== LIVE-EXIT rebuild (entry=CLOSE-fill; Z1-3 hold-EOD, Z4 -3%SL) ===")
for seeds,lbl in [(list(range(0,9)),'seeds0-8'),(list(range(200,209)),'seeds200-8')]:
    print(f"\n##### {lbl} #####")
    for z in ['Z1','Z2','Z3','Z4']:
        old,new,exitH=picks(z,seeds); sl=0.03 if z=='Z4' else None
        lf=(old['label_fixed3']>0).mean()*100
        print(f" {z}: label_fixed3 WR={lf:.0f}%  | current-live(OLD sel, hold-EOD): {wr(old,None,'close',sl)}")
        print(f"     new-sel hold-EOD:        {wr(new,None,'close',sl)}")
        if exitH: print(f"     new-sel + exit+{exitH}:      {wr(new,exitH,'close',None)}")
con.close(); print("\nDONE")
