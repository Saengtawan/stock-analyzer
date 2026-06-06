"""P6-10J: Z1 LAYER-6 loss-side drill. We only ever fixed the WIN model; loss-gate
(loss_p<=0.40) was never re-examined. loss-attr showed picks' winners loss_p=0.039 vs
losers 0.065 (0.58 sd sep) yet gate=0.40 is far too loose to ever bind for Z1.
Test: with the WINNING win-ranker (graded-4 lambdarank), sweep the loss-gate DOWN and
see the WR/volume tradeoff — can a tighter gate cut the residual (market-red) losers?
Also test loss-aware SELECTION: rank by rk minus penalty*loss_p. DEV-tuned, per-month."""
import sys, warnings
warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, lightgbm as lgb
from datetime import datetime, timedelta
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'
sys.path.insert(0, f'{ROOT}/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions
LO,HI=0,9
HP=dict(learning_rate=0.05,max_depth=3,num_leaves=24,min_child_samples=50,reg_alpha=1.0,reg_lambda=1.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.9)
LOSS_HP=dict(learning_rate=0.03,max_depth=3,num_leaves=8,min_child_samples=50,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8)
RK=['learning_rate','max_depth','num_leaves','min_child_samples','reg_alpha','reg_lambda','n_estimators','bagging_fraction','feature_fraction']
WLAB='label_z12_market_3dd'; TRAIN_DAYS=840; N_SEEDS=5
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']
DEV={'2025-11','2025-12','2026-01','2026-02'}; HOLD={'2026-03','2026-04','2026-05'}
df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
feats=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]+INTERACTIONS+sorted([c for c in df.columns if c.startswith('feat_')])
zdf=df[(df['mins_from_open']>=LO)&(df['mins_from_open']<=HI)].copy()
def fitb(X,y,hp): return [lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}).fit(X,y) for s in range(N_SEEDS)]
def pmax(ms,X): return np.max([m.predict_proba(X)[:,1] for m in ms],axis=0)
def grade(tv,v,ng):
    qs=pd.Series(tv).quantile([i/ng for i in range(1,ng)]).values
    return np.digitize(np.asarray(v,dtype=float),qs).astype(int)
def fitr(tr,rel):
    s=tr.sort_values('date'); grp=s.groupby('date',sort=False).size().values; rhp={k:HP[k] for k in RK}
    return [lgb.LGBMRanker(**{**rhp,'objective':'lambdarank','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s_}).fit(s[feats].fillna(0).values,s[rel].astype(int).values,group=grp) for s_ in range(N_SEEDS)]
def rmean(ms,X): return np.mean([m.predict(X) for m in ms],axis=0)
rows=[]
for tm in MONTHS:
    ts=tm+'-01'; cut=(datetime.strptime(ts,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    tr=zdf[(zdf['date']>=cut)&(zdf['date']<ts)]; te=zdf[zdf['month']==tm].copy()
    if len(tr)<1000 or len(te)==0: continue
    yw=tr[WLAB]; mw=yw.notna()
    if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
    trw=tr[mw].copy(); trw['_g']=grade(trw['label_fixed3'].values,trw['label_fixed3'].values,4)
    lms=fitb(tr[feats].fillna(0).values,(tr['label_fixed3']<=-1.0).astype(int).values,LOSS_HP)
    te['lp']=pmax(lms,te[feats].fillna(0).values)
    rms=fitr(trw,'_g'); te['rk']=rmean(rms,te[feats].fillna(0).values)
    rows.append(te[['date','month','label_fixed3','lp','rk']])
D=pd.concat(rows,ignore_index=True)
def split_wr(P,split):
    r=P[P.month.isin(split)]['label_fixed3'].dropna(); return (len(r),(r>0).mean()*100 if len(r) else float('nan'),r.sum())
print("=== Z1 loss-gate sweep (win-ranker graded-4 fixed; vary loss_thr) ===")
print(f"  {'loss_thr':<9}{'DEV N/WR':>14}{'HOLD N/WR/tot':>20}")
for thr in [0.03,0.05,0.07,0.10,0.15,0.20,0.30,0.40]:
    g=D[D['lp']<=thr].sort_values('rk',ascending=False).groupby('date').head(1)
    dN,dW,_=split_wr(g,DEV); hN,hW,hT=split_wr(g,HOLD)
    print(f"  {thr:<9}{f'{dN}/{dW:.0f}%':>14}{f'{hN}/{hW:.1f}%/{hT:+.0f}':>20}")
print("\n  (current prod gate = 0.40; 79.5% @ holdout N44. tighter = fewer trades, maybe higher WR)")
# loss-aware selection: rank by rk - penalty*lp (keep gate 0.40)
print("\n=== loss-aware SELECTION: score = rk - k*lp, gate 0.40 (volume ~unchanged) ===")
print(f"  {'k':<6}{'DEV N/WR':>14}{'HOLD N/WR/tot':>20}")
for k in [0.0,2.0,5.0,10.0,20.0]:
    D['_s']=D['rk']-k*D['lp']
    g=D[D['lp']<=0.40].sort_values('_s',ascending=False).groupby('date').head(1)
    dN,dW,_=split_wr(g,DEV); hN,hW,hT=split_wr(g,HOLD)
    print(f"  {k:<6}{f'{dN}/{dW:.0f}%':>14}{f'{hN}/{hW:.1f}%/{hT:+.0f}':>20}")
print("=== DONE ===")
