"""P6-10I: is Z1 REALLY maxed? Try the one principled untried refinement —
focus the ranker on POSITION-1 only (we trade just the top-1/day, so optimizing NDCG@1
matches the task tighter than generic lambdarank). Variants vs V0 (graded-4, 79.5):
  V0     : lambdarank default
  T1     : lambdarank_truncation_level=1  (gradient on top rank only)
  T3     : lambdarank_truncation_level=3
  LGsteep: label_gain steep [0,1,4,16] (emphasize top bucket)
  D4     : ranker max_depth 3->4 (more capacity for ranking)
Volume-matched, DEV + HOLDOUT + per-month. Z1 only."""
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
WLAB='label_z12_market_3dd'; LOSS_THR=0.40; WIN_THR=0.75; TRAIN_DAYS=840; N_SEEDS=5
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']
DEV={'2025-11','2025-12','2026-01','2026-02'}; HOLD={'2026-03','2026-04','2026-05'}
df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
feats=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]+INTERACTIONS+sorted([c for c in df.columns if c.startswith('feat_')])
zdf=df[(df['mins_from_open']>=LO)&(df['mins_from_open']<=HI)].copy()
def fitb(X,y,hp): return [lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}).fit(X,y) for s in range(N_SEEDS)]
def pmin(ms,X): return np.min([m.predict_proba(X)[:,1] for m in ms],axis=0)
def pmax(ms,X): return np.max([m.predict_proba(X)[:,1] for m in ms],axis=0)
def grade(tv,v,ng):
    qs=pd.Series(tv).quantile([i/ng for i in range(1,ng)]).values
    return np.digitize(np.asarray(v,dtype=float),qs).astype(int)
def fitr(tr,rel,extra,depth=3):
    s=tr.sort_values('date'); grp=s.groupby('date',sort=False).size().values
    rhp={k:HP[k] for k in RK}; rhp['max_depth']=depth
    return [lgb.LGBMRanker(**{**rhp,'objective':'lambdarank','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s_,**extra}).fit(s[feats].fillna(0).values,s[rel].astype(int).values,group=grp) for s_ in range(N_SEEDS)]
def rmean(ms,X): return np.mean([m.predict(X) for m in ms],axis=0)
# (tag, extra-params, label_gain?, depth)
VARS=[('V0',{},None,3),('T1',{'lambdarank_truncation_level':1},None,3),('T3',{'lambdarank_truncation_level':3},None,3),
      ('LGsteep',{'label_gain':[0,1,4,16]},None,3),('D4',{},None,4)]
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
    for tag,extra,_,depth in VARS:
        rms=fitr(trw,'_g',extra,depth); te[tag]=rmean(rms,te[feats].fillna(0).values)
    rows.append(te[['date','month','label_fixed3','lp']+[v[0] for v in VARS]])
D=pd.concat(rows,ignore_index=True)
# baseline N for matching (reuse known: full 53, holdout 44 from binary@0.75)
NF,NH=53,44
def wr(P,split,N,col):
    h=P[P.month.isin(split)].sort_values(col,ascending=False).head(N)['label_fixed3'].dropna()
    return (len(h),(h>0).mean()*100 if len(h) else float('nan'))
print("=== Z1 position-focus refinement (matched HOLD N=44) ===")
print(f"  {'config':<10}{'DEV_WR':>8}{'HOLD_WR':>9}")
nd=len(D[(D['lp']<=LOSS_THR)&(D.month.isin(DEV))].drop_duplicates('date'))  # approx dev capacity
for tag,_,_,_ in VARS:
    t1=D[D['lp']<=LOSS_THR].sort_values(tag,ascending=False).groupby('date').head(1)
    dN,dW=wr(t1,DEV,9,tag); hN,hW=wr(t1,HOLD,NH,tag)
    print(f"  {tag:<10}{dW:>8.1f}{hW:>9.1f}")
print("\n  per-month HOLDOUT each config:")
for tag,_,_,_ in VARS:
    t1=D[D['lp']<=LOSS_THR].sort_values(tag,ascending=False).groupby('date').head(1)
    hod=t1[t1.month.isin(HOLD)].sort_values(tag,ascending=False).head(NH)
    line=' '.join(f"{m[5:]}:{((hod[hod.month==m]['label_fixed3']>0).mean()*100 if len(hod[hod.month==m]) else 0):.0f}%" for m in sorted(HOLD))
    print(f"    {tag:<10} {line}")
print("=== DONE ===  (V0=79.5 reference; beat it to reopen Z1)")
