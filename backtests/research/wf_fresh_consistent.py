"""FRESH START: self-consistent, realistic harness. Entry = CLOSE of decision-bar (no
look-ahead, = live MARKET `now`). For each exit policy build label = realized PnL of THAT
exact trade from intraday_bars_5m. Train win-model on that label, WF holdout, compare exits.
Z1+Z2 (decent N). Exits: EOD / +30 / +60 / +90 / trail3%. 2 seeds. per-month."""
import sys, warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, lightgbm as lgb, sqlite3
from datetime import datetime, timedelta
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'; sys.path.insert(0,f'{ROOT}/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions
ZHP={'Z1':dict(learning_rate=0.05,max_depth=3,num_leaves=24,min_child_samples=50,reg_alpha=1.0,reg_lambda=1.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.9),
 'Z2':dict(learning_rate=0.03,max_depth=5,num_leaves=47,min_child_samples=80,reg_alpha=0.5,reg_lambda=3.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8)}
LOSS_HP=dict(learning_rate=0.03,max_depth=3,num_leaves=8,min_child_samples=50,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8)
PATH=['path_r_squared','path_peak_diff','path_low_diff','path_consol_range','path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel','path_momentum_accel','path_speed_early','path_up_vol_ratio','path_support_touches','path_bar_size_trend','path_wick_ratio','path_lower_wick_ratio','path_gap_ratio','path_time_at_high','path_vol_at_peaks','path_vwap_slope','path_ret_skewness']
ZCFG={'Z1':(0,9,True,False),'Z2':(10,29,True,True)}; LOSS_THR={'Z1':0.40,'Z2':0.20}
WIN_THR=0.75; TRAIN_DAYS=840; EXITS=['EOD','+30','+60','+90','trail3']
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']; HOLD=['2026-03','2026-04','2026-05']
df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
av=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]; NEWF=sorted([c for c in df.columns if c.startswith('feat_')])
con=sqlite3.connect(f'{ROOT}/data/trade_history.db')
def to_min(t): h,m=t.split(':'); return int(h)*60+int(m)
EOD_MIN=to_min('15:55')
# ---- build realistic labels for Z1+Z2 rows (cache) ----
import os, pickle
CACHE='/tmp/fresh_labels.pkl'
zmask=((df.mins_from_open>=0)&(df.mins_from_open<=29))
sub=df[zmask][['sym','date','time','mins_from_open']].copy()
if os.path.exists(CACHE):
    lab=pd.read_pickle(CACHE); print(f"loaded label cache {len(lab)}",flush=True)
else:
    print(f"building labels for {len(sub)} rows...",flush=True)
    barcache={}
    def bars_of(s,d):
        k=(s,d)
        if k not in barcache:
            barcache[k]=[(to_min(t),o,hi,lo,c) for t,o,hi,lo,c in con.execute("SELECT time_et,open,high,low,close FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et>='09:30' AND time_et<='16:00' ORDER BY time_et",(s,d)).fetchall()]
        return barcache[k]
    out=[]
    for i,(_,r) in enumerate(sub.iterrows()):
        if i%20000==0: print(f"  {i}/{len(sub)}",flush=True)
        bars=bars_of(r['sym'],r['date']); em=to_min(r['time'])
        eb=None
        for b in bars:
            if b[0]<=em: eb=b
            else: break
        rec={'sym':r['sym'],'date':r['date'],'mins_from_open':r['mins_from_open']}
        if eb is None or eb[4]<=0:
            for e in EXITS: rec['pnl_'+e]=np.nan
            out.append(rec); continue
        entry=eb[4]  # CLOSE of decision bar = realistic fill
        fwd=[b for b in bars if b[0]>em]
        # timed/EOD exits
        for e,H in [('EOD',None),('+30',30),('+60',60),('+90',90)]:
            tgt=EOD_MIN if H is None else em+H
            xb=eb
            for b in bars:
                if b[0]<=tgt: xb=b
                else: break
            rec['pnl_'+e]=(xb[4]/entry-1)*100
        # trail 3%
        peak=entry; ex=None
        for b in fwd:
            if b[2]>peak: peak=b[2]
            if b[3]<=peak*0.97: ex=(peak*0.97/entry-1)*100; break
        if ex is None:
            xb=eb
            for b in bars:
                if b[0]<=EOD_MIN: xb=b
            ex=(xb[4]/entry-1)*100
        rec['pnl_trail3']=ex
        out.append(rec)
    lab=pd.DataFrame(out); lab.to_pickle(CACHE); print("cache built",flush=True)
df=df.merge(lab,on=['sym','date','mins_from_open'],how='left')
def fitb(X,y,hp,seeds): return [lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}).fit(X,y) for s in seeds]
def run(z,exit_e,seeds):
    lo,hi,ui,usep=ZCFG[z]; feats=av+(INTERACTIONS if ui else [])+NEWF+(PATH if usep else [])
    pcol='pnl_'+exit_e; zdf=df[(df.mins_from_open>=lo)&(df.mins_from_open<=hi)].copy()
    rows=[]
    for tm in MONTHS:
        ts=tm+'-01'; cut=(datetime.strptime(ts,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
        tr=zdf[(zdf.date>=cut)&(zdf.date<ts)]; te=zdf[zdf.month==tm].copy()
        if len(tr)<1000 or len(te)==0: continue
        yw=(tr[pcol]>0).astype(int); m=tr[pcol].notna()
        if m.sum()<500 or len(np.unique(yw[m]))<2: continue
        wm=fitb(tr[m][feats].fillna(0).values,yw[m].values,ZHP[z],seeds)
        te['wp']=np.min([mm.predict_proba(te[feats].fillna(0).values)[:,1] for mm in wm],axis=0)
        lm=fitb(tr[m][feats].fillna(0).values,(tr[m][pcol]<=-1.0).astype(int).values,LOSS_HP,seeds)
        te['lp']=np.max([mm.predict_proba(te[feats].fillna(0).values)[:,1] for mm in lm],axis=0)
        te['pnl']=te[pcol]; rows.append(te[['date','month','pnl','wp','lp']])
    D=pd.concat(rows,ignore_index=True)
    g=D[D.lp<=LOSS_THR[z]].sort_values('wp',ascending=False).groupby('date').head(1)
    h=g[g.month.isin(HOLD)]; r=h['pnl'].dropna()
    if len(r)==0: return "N=0"
    pm=' '.join(f"{mm[5:]}:{((h[h.month==mm]['pnl']>0).mean()*100 if len(h[h.month==mm]) else 0):.0f}%" for mm in HOLD)
    return f"N={len(r)} WR={(r>0).mean()*100:4.1f}% tot={r.sum():+4.0f} worst={r.min():+4.1f} | {pm}"
print("=== FRESH honest exit comparison (realistic close-fill entry, consistent label) ===")
for z in ['Z1','Z2']:
    print(f"\n##### {z} #####")
    for e in EXITS:
        for seeds,lbl in [(list(range(0,9)),'s0-8'),(list(range(200,209)),'s200-8')]:
            print(f"  exit {e:<6} {lbl}: {run(z,e,list(seeds))}")
con.close(); print("\nDONE")
