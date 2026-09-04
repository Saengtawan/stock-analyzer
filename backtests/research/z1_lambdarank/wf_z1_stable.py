"""P6-10M: Z1 STABILITY / layer-5 check — is 86.4% real or a 5-seed fluke?
Config = T1 (lambdarank truncation=1, graded-4) + loss-aware select (rk - 20*lp), gate
0.40, matched holdout N=44. Vary seed count (5/9) and seed-aggregation (mean/median) =
layer-5 (never touched). If WR holds ~85-86 across all -> Z1 genuinely maxed."""
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
WLAB='label_z12_market_3dd'; LOSS_THR=0.40; TRAIN_DAYS=840; K=20.0; NH=44
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']; HOLD={'2026-03','2026-04','2026-05'}
df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
feats=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]+INTERACTIONS+sorted([c for c in df.columns if c.startswith('feat_')])
zdf=df[(df['mins_from_open']>=LO)&(df['mins_from_open']<=HI)].copy()
def grade(tv,v,ng):
    qs=pd.Series(tv).quantile([i/ng for i in range(1,ng)]).values
    return np.digitize(np.asarray(v,dtype=float),qs).astype(int)
def run(nseed,agg,seed0=0):
    rows=[]
    for tm in MONTHS:
        ts=tm+'-01'; cut=(datetime.strptime(ts,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
        tr=zdf[(zdf['date']>=cut)&(zdf['date']<ts)]; te=zdf[zdf['month']==tm].copy()
        if len(tr)<1000 or len(te)==0: continue
        yw=tr[WLAB]; mw=yw.notna()
        if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
        trw=tr[mw].copy(); trw['_g']=grade(trw['label_fixed3'].values,trw['label_fixed3'].values,4)
        s=trw.sort_values('date'); grp=s.groupby('date',sort=False).size().values; rhp={k:HP[k] for k in RK}
        lps=[]; rks=[]
        for sd in range(seed0,seed0+nseed):
            lm=lgb.LGBMClassifier(**{**LOSS_HP,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':sd}).fit(tr[feats].fillna(0).values,(tr['label_fixed3']<=-1.0).astype(int).values)
            lps.append(lm.predict_proba(te[feats].fillna(0).values)[:,1])
            rm=lgb.LGBMRanker(**{**rhp,'objective':'lambdarank','lambdarank_truncation_level':1,'bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':sd}).fit(s[feats].fillna(0).values,s['_g'].astype(int).values,group=grp)
            rks.append(rm.predict(te[feats].fillna(0).values))
        te['lp']=np.max(lps,axis=0)
        te['rk']=(np.median(rks,axis=0) if agg=='median' else np.mean(rks,axis=0))
        rows.append(te[['date','month','label_fixed3','lp','rk']])
    D=pd.concat(rows,ignore_index=True)
    D['_s']=D['rk']-K*D['lp']
    t=D[D['lp']<=LOSS_THR].sort_values('_s',ascending=False).groupby('date').head(1)
    ho=t[t.month.isin(HOLD)].sort_values('_s',ascending=False).head(NH)
    wr=(ho['label_fixed3']>0).mean()*100; pm=' '.join(f"{m[5:]}:{((ho[ho.month==m]['label_fixed3']>0).mean()*100 if len(ho[ho.month==m]) else 0):.0f}%" for m in sorted(HOLD))
    return len(ho),wr,ho['label_fixed3'].sum(),pm
print("=== Z1 STABILITY check (config: T1 + loss-aware k20, matched N44) ===")
print(f"  {'setup':<22}{'HOLD N/WR/tot':>20}   per-month")
for tag,ns,agg,s0 in [('5seed mean (ref)',5,'mean',0),('9seed mean',9,'mean',0),('5seed median',5,'median',0),('5seed seeds5-9',5,'mean',5)]:
    n,wr,tot,pm=run(ns,agg,s0)
    print(f"  {tag:<22}{f'{n}/{wr:.1f}%/{tot:+.0f}':>20}   {pm}")
print("=== DONE ===  (all ~85-86 & spread = Z1 maxed for real)")
