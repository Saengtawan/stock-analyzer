"""P6-10G: MAX OUT Z1 — lambdarank refinement sweep, DEV-tuned then holdout-reported.
Discipline: pick the best config by DEV WR (2025-11..2026-02), THEN report its holdout
(2026-03..05). Avoids holdout-fishing. Variants:
  V0 graded-4 lambdarank (current, ~79.5 holdout reference)
  V1 graded-3 ; V2 graded-5
  V3 rank_xendcg objective (graded-4)
  V4 graded-4 + MARKET-AWARE interaction feats (spy_green*gain, spy_intra*gain,
     vix_5d_chg*gain, ad_ratio*gain) — extract the market-direction residual loss-attr found
All volume-matched (to baseline-binary N) per split. Z1 only."""
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
# market-aware interaction feats
for a in ['spy_green','spy_intra','vix_5d_chg','ad_ratio']:
    df[f'mkt_{a}_x_gain']=df[a]*df['gain_from_open']
MKT=['mkt_spy_green_x_gain','mkt_spy_intra_x_gain','mkt_vix_5d_chg_x_gain','mkt_ad_ratio_x_gain']
base_feats=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]+INTERACTIONS+sorted([c for c in df.columns if c.startswith('feat_')])
zdf=df[(df['mins_from_open']>=LO)&(df['mins_from_open']<=HI)].copy()
def fitb(X,y,hp): return [lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}).fit(X,y) for s in range(N_SEEDS)]
def pmin(ms,X): return np.min([m.predict_proba(X)[:,1] for m in ms],axis=0)
def pmax(ms,X): return np.max([m.predict_proba(X)[:,1] for m in ms],axis=0)
def grade(tv,v,ng):
    qs=pd.Series(tv).quantile([i/ng for i in range(1,ng)]).values
    return np.digitize(np.asarray(v,dtype=float),qs).astype(int)
def fitr(tr,feats,rel,obj):
    s=tr.sort_values('date'); grp=s.groupby('date',sort=False).size().values; rhp={k:HP[k] for k in RK}
    return [lgb.LGBMRanker(**{**rhp,'objective':obj,'bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s_}).fit(s[feats].fillna(0).values,s[rel].astype(int).values,group=grp) for s_ in range(N_SEEDS)]
def rmean(ms,X): return np.mean([m.predict(X) for m in ms],axis=0)

VARS=[('V0_g4',base_feats,4,'lambdarank'),('V1_g3',base_feats,3,'lambdarank'),('V2_g5',base_feats,5,'lambdarank'),
      ('V3_xendcg',base_feats,4,'rank_xendcg'),('V4_mkt',base_feats+MKT,4,'lambdarank')]
rows=[]
for tm in MONTHS:
    ts=tm+'-01'; cut=(datetime.strptime(ts,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    tr=zdf[(zdf['date']>=cut)&(zdf['date']<ts)]; te=zdf[zdf['month']==tm].copy()
    if len(tr)<1000 or len(te)==0: continue
    yw=tr[WLAB]; mw=yw.notna()
    if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
    trw=tr[mw].copy()
    lms=fitb(tr[base_feats].fillna(0).values,(tr['label_fixed3']<=-1.0).astype(int).values,LOSS_HP)
    te['lp']=pmax(lms,te[base_feats].fillna(0).values)
    gms=fitb(trw[base_feats].fillna(0).values,yw[mw].astype(int).values,HP)
    te['wp']=pmin(gms,te[base_feats].fillna(0).values)
    for tag,feats,ng,obj in VARS:
        trw[f'_rel_{tag}']=grade(trw['label_fixed3'].values,trw['label_fixed3'].values,ng)
        rms=fitr(trw,feats,f'_rel_{tag}',obj); te[tag]=rmean(rms,te[feats].fillna(0).values)
    rows.append(te[['date','month','label_fixed3','lp','wp']+[v[0] for v in VARS]])
D=pd.concat(rows,ignore_index=True)
def split_stat(P,split):
    r=P[P.month.isin(split)]['label_fixed3'].dropna(); return (len(r),(r>0).mean()*100 if len(r) else float('nan'))
# baseline binary picks define matched N per split
bl=D[(D['wp']>=WIN_THR)&(D['lp']<=LOSS_THR)].sort_values('wp',ascending=False).groupby('date').head(1)
nd=len(bl[bl.month.isin(DEV)]); nh=len(bl[bl.month.isin(HOLD)])
bdw=split_stat(bl,DEV); bhw=split_stat(bl,HOLD)
print(f"=== Z1 MAX sweep (matched: DEV N={nd}, HOLD N={nh}) ===")
print(f"  {'config':<12}{'DEV_WR':>8}{'HOLD_WR':>9}   (tune on DEV, read HOLD)")
print(f"  {'baseline':<12}{bdw[1]:>8.1f}{bhw[1]:>9.1f}")
best=None
for tag,_,_,_ in VARS:
    t1=D[D['lp']<=LOSS_THR].sort_values(tag,ascending=False).groupby('date').head(1)
    dev=t1[t1.month.isin(DEV)].sort_values(tag,ascending=False).head(nd)
    hod=t1[t1.month.isin(HOLD)].sort_values(tag,ascending=False).head(nh)
    dw=(dev['label_fixed3']>0).mean()*100 if len(dev) else float('nan')
    hw=(hod['label_fixed3']>0).mean()*100 if len(hod) else float('nan')
    flag=''
    if best is None or dw>best[1]: best=(tag,dw,hw)
    print(f"  {tag:<12}{dw:>8.1f}{hw:>9.1f}")
print(f"\n  DEV-BEST config = {best[0]}  (DEV {best[1]:.1f})  ->  its HOLDOUT = {best[2]:.1f}%")
print(f"  (V0_g4 is the current 79.5 reference; only deploy a variant if it beats V0 on DEV)")
# per-month holdout for V0 and DEV-best
print("\n  per-month HOLDOUT (V0_g4 | DEV-best):")
for tag in ['V0_g4',best[0]]:
    t1=D[D['lp']<=LOSS_THR].sort_values(tag,ascending=False).groupby('date').head(1)
    hod=t1[t1.month.isin(HOLD)].sort_values(tag,ascending=False).head(nh)
    line=' '.join(f"{m[5:]}:{((hod[hod.month==m]['label_fixed3']>0).mean()*100 if len(hod[hod.month==m]) else 0):.0f}%({len(hod[hod.month==m])})" for m in sorted(HOLD))
    print(f"    {tag:<10} {line}")
print("=== DONE ===")
