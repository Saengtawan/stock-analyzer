"""Independent verify of Z2 loss-model win: FIXED standout configs, THIRD fresh seed set
(200-208), NO tuning. If holdout ~66-69 holds = real. Win-model path-binary identical."""
import sys, warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, lightgbm as lgb
from datetime import datetime, timedelta
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'; sys.path.insert(0,f'{ROOT}/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions
WINHP=dict(learning_rate=0.03,max_depth=5,num_leaves=47,min_child_samples=80,reg_alpha=0.5,reg_lambda=3.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8)
WLAB='label_eod_green_v2'; WIN_THR=0.75; LO,HI=10,29; TRAIN_DAYS=840
PATH=['path_r_squared','path_peak_diff','path_low_diff','path_consol_range','path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel','path_momentum_accel','path_speed_early','path_up_vol_ratio','path_support_touches','path_bar_size_trend','path_wick_ratio','path_lower_wick_ratio','path_gap_ratio','path_time_at_high','path_vol_at_peaks','path_vwap_slope','path_ret_skewness']
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']; HOLD={'2026-03','2026-04','2026-05'}
df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
feats=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]+INTERACTIONS+sorted([c for c in df.columns if c.startswith('feat_')])+PATH
zdf=df[(df.mins_from_open>=LO)&(df.mins_from_open<=HI)].copy()
def fit(X,y,hp,seeds): return [lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}).fit(X,y) for s in seeds]
def run(lossT,losshp,gate,seeds):
    rows=[]
    for tm in MONTHS:
        ts=tm+'-01'; cut=(datetime.strptime(ts,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
        tr=zdf[(zdf.date>=cut)&(zdf.date<ts)]; te=zdf[zdf.month==tm].copy()
        if len(tr)<1000 or len(te)==0: continue
        yw=tr[WLAB]; mw=yw.notna()
        if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
        wm=fit(tr[mw][feats].fillna(0).values,yw[mw].astype(int).values,WINHP,seeds)
        te['wp']=np.min([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in wm],axis=0)
        lm=fit(tr[feats].fillna(0).values,(tr['label_fixed3']<=lossT).astype(int).values,losshp,seeds)
        te['lp']=np.max([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in lm],axis=0)
        rows.append(te[['date','month','label_fixed3','wp','lp']])
    D=pd.concat(rows,ignore_index=True)
    g=D[(D.wp>=WIN_THR)&(D.lp<=gate)].sort_values('wp',ascending=False).groupby('date').head(1)
    h=g[g.month.isin(HOLD)]
    pm=' '.join(f"{m[5:]}:{((h[h.month==m]['label_fixed3']>0).mean()*100 if len(h[h.month==m]) else 0):.0f}%({len(h[h.month==m])})" for m in sorted(HOLD))
    return len(h),(h['label_fixed3']>0).mean()*100,h['label_fixed3'].sum(),pm
LHP1=dict(learning_rate=0.03,max_depth=4,num_leaves=16,min_child_samples=30,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8)
print("=== Z2 loss-model VERIFY (3rd seed set 200-208; baseline=59%) ===")
for tag,lt,hp,gt in [('cur loss (ref)',-1.0,dict(learning_rate=0.03,max_depth=3,num_leaves=8,min_child_samples=50,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8),0.20),
                      ('T=-1.5 d4/l16 g0.15',-1.5,LHP1,0.15),('T=-2.0 d4/l16 g0.10',-2.0,LHP1,0.10)]:
    for label,seeds in [('seeds200-208',range(200,209)),('seeds50-54',range(50,55))]:
        n,wr,tot,pm=run(lt,hp,gt,list(seeds))
        print(f"  {tag:<22} {label:<13} HOLD N={n} WR={wr:.1f}% tot={tot:+.0f}   {pm}")
print("=== DONE ===")
