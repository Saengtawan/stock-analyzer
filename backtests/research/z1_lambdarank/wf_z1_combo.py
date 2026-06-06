"""P6-10K: Z1 combine LAYER-4 (T1: lambdarank truncation_level=1 -> 84.1%) with
LAYER-6 (loss-aware: tighter gate / rk - k*lp -> ~81%). Different layers => should stack.
Win-ranker = graded-4 lambdarank, truncation_level=1. Then loss-side levers.
Report DEV + HOLDOUT + per-month. matched-N44 AND natural-volume views."""
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
    return [lgb.LGBMRanker(**{**rhp,'objective':'lambdarank','lambdarank_truncation_level':1,'bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s_}).fit(s[feats].fillna(0).values,s[rel].astype(int).values,group=grp) for s_ in range(N_SEEDS)]
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
def swr(P,split):
    r=P[P.month.isin(split)]['label_fixed3'].dropna(); return (len(r),(r>0).mean()*100 if len(r) else float('nan'),r.sum())
def permo(P,tag):
    line=' '.join(f"{m[5:]}:{((P[P.month==m]['label_fixed3']>0).mean()*100 if len(P[P.month==m]) else 0):.0f}%({len(P[P.month==m])})" for m in sorted(HOLD))
    print(f"    {tag:<22} {line}")
print("=== Z1 COMBO: T1 ranker (84.1 ref) + loss-side ===")
print("--- A) T1 + loss-aware selection (rk - k*lp), gate 0.40, natural vol ---")
print(f"  {'k':<6}{'DEV N/WR':>13}{'HOLD N/WR/tot':>20}")
bestk=None
for k in [0.0,5.0,10.0,20.0,40.0]:
    D['_s']=D['rk']-k*D['lp']
    g=D[D['lp']<=0.40].sort_values('_s',ascending=False).groupby('date').head(1)
    dN,dW,_=swr(g,DEV); hN,hW,hT=swr(g,HOLD)
    if bestk is None or dW>bestk[1]: bestk=(k,dW,hW,hT)
    print(f"  {k:<6}{f'{dN}/{dW:.0f}%':>13}{f'{hN}/{hW:.1f}%/{hT:+.0f}':>20}")
print("--- B) T1 + tighter loss-gate (pure rk), natural vol ---")
print(f"  {'gate':<6}{'DEV N/WR':>13}{'HOLD N/WR/tot':>20}")
for thr in [0.10,0.15,0.20,0.30,0.40]:
    g=D[D['lp']<=thr].sort_values('rk',ascending=False).groupby('date').head(1)
    dN,dW,_=swr(g,DEV); hN,hW,hT=swr(g,HOLD)
    print(f"  {thr:<6}{f'{dN}/{dW:.0f}%':>13}{f'{hN}/{hW:.1f}%/{hT:+.0f}':>20}")
print("--- C) matched N=44 holdout: T1 pure vs T1+loss-aware(best DEV k) ---")
t1=D[D['lp']<=0.40].sort_values('rk',ascending=False).groupby('date').head(1)
mh=t1[t1.month.isin(HOLD)].sort_values('rk',ascending=False).head(44)
print(f"  T1 pure        : N={len(mh)} WR={(mh['label_fixed3']>0).mean()*100:.1f}% tot={mh['label_fixed3'].sum():+.0f}"); permo(mh,'T1 pure')
D['_s']=D['rk']-bestk[0]*D['lp']
t1b=D[D['lp']<=0.40].sort_values('_s',ascending=False).groupby('date').head(1)
mhb=t1b[t1b.month.isin(HOLD)].sort_values('_s',ascending=False).head(44)
print(f"  T1+lossaware k={bestk[0]:<4}: N={len(mhb)} WR={(mhb['label_fixed3']>0).mean()*100:.1f}% tot={mhb['label_fixed3'].sum():+.0f}"); permo(mhb,f'T1+lossaware')
print("=== DONE ===  (beat 84.1 = layers stack)")
