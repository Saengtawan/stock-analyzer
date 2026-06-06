"""LtR test: lambdarank win-model vs pointwise binary, volume-matched on holdout.
Win-model only changes. Loss-gate identical to baseline. Selection: top-1/day.
Ranker variants:
  RankB  = lambdarank, relevance = binary win-label (0/1)
  RankG  = lambdarank, relevance = graded (label_fixed3 bucketed 0..3 by quantile)
Comparison: baseline = (loss-gate & win_p>=0.75) -> top1/day.
  Ranker = loss-gate -> top1/day by ranker score, then restrict to dates whose
  top-1 score is in top percentile so picked-N ~= baseline-N (matched volume).
Per zone, full + holdout, + per-month holdout spread."""
import sys, warnings
warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, lightgbm as lgb
from datetime import datetime, timedelta
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'
sys.path.insert(0, f'{ROOT}/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions

ZONES=[('Z1',0,9,True),('Z2',10,29,True),('Z3',30,44,False),('Z4',45,75,False)]
ZONE_LABEL={'Z1':'label_z12_market_3dd','Z2':'label_eod_green_v2','Z3':'label_z34_market','Z4':'label_z34_market'}
ZONE_HP={
 'Z1':dict(learning_rate=0.05,max_depth=3,num_leaves=24,min_child_samples=50,reg_alpha=1.0,reg_lambda=1.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.9),
 'Z2':dict(learning_rate=0.03,max_depth=5,num_leaves=47,min_child_samples=80,reg_alpha=0.5,reg_lambda=3.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8),
 'Z3':dict(learning_rate=0.05,max_depth=4,num_leaves=31,min_child_samples=30,reg_alpha=0.5,reg_lambda=1.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8),
 'Z4':dict(learning_rate=0.05,max_depth=3,num_leaves=8,min_child_samples=30,reg_alpha=1.0,reg_lambda=3.0,n_estimators=400,bagging_fraction=0.7,feature_fraction=0.7)}
LOSS_HP=dict(learning_rate=0.03,max_depth=3,num_leaves=8,min_child_samples=50,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8)
ZONE_USE_PATH={'Z1':False,'Z2':True,'Z3':True,'Z4':False}
LOSS_THR={'Z1':0.40,'Z2':0.20,'Z3':0.40,'Z4':0.50}
PATH=['path_r_squared','path_peak_diff','path_low_diff','path_consol_range','path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel','path_momentum_accel','path_speed_early','path_up_vol_ratio','path_support_touches','path_bar_size_trend','path_wick_ratio','path_lower_wick_ratio','path_gap_ratio','path_time_at_high','path_vol_at_peaks','path_vwap_slope','path_ret_skewness']
WIN_THR=0.75; TRAIN_DAYS=840; N_SEEDS=5
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']; HOLD={'2026-03','2026-04','2026-05'}
df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
feats_avail=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]; NEW=sorted([c for c in df.columns if c.startswith('feat_')])

# only HP keys lambdarank uses
RANK_KEYS=['learning_rate','max_depth','num_leaves','min_child_samples','reg_alpha','reg_lambda','n_estimators','bagging_fraction','feature_fraction']

def fit_binary(X,y,hp):
    ms=[]
    for s in range(N_SEEDS):
        m=lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}); m.fit(X,y); ms.append(m)
    return ms
def pred_min(ms,X):
    return np.min([m.predict_proba(X)[:,1] for m in ms],axis=0)

def fit_ranker(tr_sorted,feats,relcol,hp):
    # groups = rows per date (contiguous since sorted by date)
    grp=tr_sorted.groupby('date',sort=False).size().values
    X=tr_sorted[feats].fillna(0).values; y=tr_sorted[relcol].astype(int).values
    rhp={k:hp[k] for k in RANK_KEYS}
    ms=[]
    for s in range(N_SEEDS):
        m=lgb.LGBMRanker(**{**rhp,'objective':'lambdarank','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s})
        m.fit(X,y,group=grp); ms.append(m)
    return ms
def pred_rank_mean(ms,X):
    # ranker scores: average over seeds (no probability; rank by mean score)
    return np.mean([m.predict(X) for m in ms],axis=0)

def run(zname,lo,hi,use_i):
    feats=feats_avail+(INTERACTIONS if use_i else [])+NEW+(PATH if ZONE_USE_PATH[zname] else [])
    wlab=ZONE_LABEL[zname]; hp=ZONE_HP[zname]; lthr=LOSS_THR[zname]
    zdf=df[(df['mins_from_open']>=lo)&(df['mins_from_open']<=hi)].copy()
    rows=[]
    for tm in MONTHS:
        tm_start=tm+'-01'; cutoff=(datetime.strptime(tm_start,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
        tr=zdf[(zdf['date']>=cutoff)&(zdf['date']<tm_start)]; te=zdf[zdf['month']==tm].copy()
        if len(tr)<1000 or len(te)==0: continue
        yw=tr[wlab]; mw=yw.notna()
        if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
        trw=tr[mw].copy()
        # ---- baseline binary win ----
        gms=fit_binary(trw[feats].fillna(0).values, yw[mw].astype(int).values, hp)
        te['wp_glob']=pred_min(gms, te[feats].fillna(0).values)
        # ---- loss gate (identical) ----
        lms=fit_binary(tr[feats].fillna(0).values,(tr['label_fixed3']<=-1.0).astype(int).values,LOSS_HP)
        te['lp']=np.max([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in lms],axis=0)
        # ---- ranker (binary relevance) ----
        trw_s=trw.sort_values('date').copy()
        trw_s['_relB']=trw_s[wlab].astype(int)
        rmsB=fit_ranker(trw_s,feats,'_relB',hp)
        te['rankB']=pred_rank_mean(rmsB, te[feats].fillna(0).values)
        # ---- ranker (graded relevance) ----
        # bucket label_fixed3 within training into 0..3 by quantile (use train dist)
        rfit=trw_s['label_fixed3'].astype(float)
        qs=rfit.quantile([0.25,0.50,0.75]).values
        def grade(v):
            v=np.asarray(v,dtype=float)
            return (np.digitize(v,qs)).astype(int)  # 0..3
        trw_s['_relG']=grade(trw_s['label_fixed3'].values)
        rmsG=fit_ranker(trw_s,feats,'_relG',hp)
        te['rankG']=pred_rank_mean(rmsG, te[feats].fillna(0).values)
        rows.append(te[['date','month','label_fixed3','wp_glob','lp','rankB','rankG']])
    if not rows: return None
    return pd.concat(rows,ignore_index=True)

def base_picks(D,lthr):
    g=D[(D['wp_glob']>=WIN_THR)&(D['lp']<=lthr)]
    if len(g)==0: return g
    return g.sort_values('wp_glob',ascending=False).groupby('date').head(1)

def ranker_top1(D,scorecol,lthr):
    # loss-gate, then top-1/day by score
    g=D[D['lp']<=lthr]
    if len(g)==0: return g
    return g.sort_values(scorecol,ascending=False).groupby('date').head(1)

def match_volume(top1,scorecol,target_n):
    # restrict to dates whose top-1 score is highest, keep ~target_n
    if len(top1)==0 or target_n<=0: return top1.iloc[0:0]
    t=top1.sort_values(scorecol,ascending=False)
    return t.head(min(target_n,len(t)))

def match_volume_hold(top1,scorecol,target_n_hold):
    # match on holdout months only
    h=top1[top1.month.isin(HOLD)]
    if len(h)==0 or target_n_hold<=0: return h.iloc[0:0]
    t=h.sort_values(scorecol,ascending=False)
    return t.head(min(target_n_hold,len(t)))

def stat(r):
    r=r['label_fixed3'].dropna(); return (len(r),(r>0).mean()*100 if len(r) else float('nan'),r.sum())

print("=== LtR lambdarank vs pointwise-binary win-model (volume-matched) ===")
for zname,lo,hi,use_i in ZONES:
    D=run(zname,lo,hi,use_i)
    if D is None:
        print(f"  {zname}: no data"); continue
    lthr=LOSS_THR[zname]
    bp=base_picks(D,lthr)
    bf=bp; bh=bp[bp.month.isin(HOLD)]
    bnf,bwf,btf=stat(bf); bnh,bwh,bth=stat(bh)
    print(f"\n--- {zname} (baseline binary @{WIN_THR}) ---")
    print(f"  baseline:        full N={bnf} WR={bwf:.1f} tot={btf:.1f} | hold N={bnh} WR={bwh:.1f} tot={bth:.1f}")
    for tag,col in [('RankB',  'rankB'),('RankG','rankG')]:
        t1=ranker_top1(D,col,lthr)
        # match full volume
        mf=match_volume(t1,col,bnf)
        # match holdout volume independently
        mh=match_volume_hold(t1,col,bnh)
        nf,wf,tf=stat(mf); nh,wh,th=stat(mh)
        dwf=wf-bwf if wf==wf and bwf==bwf else float('nan')
        dwh=wh-bwh if wh==wh and bwh==bwh else float('nan')
        print(f"  {tag} matched:    full N={nf} WR={wf:.1f} tot={tf:.1f} (dWR {dwf:+.1f}) | hold N={nh} WR={wh:.1f} tot={th:.1f} (dWR {dwh:+.1f})")
    # per-month holdout spread
    print(f"  per-month HOLDOUT (base | RankB-matched | RankG-matched):")
    t1B=ranker_top1(D,'rankB',lthr); mhB=match_volume_hold(t1B,'rankB',bnh)
    t1G=ranker_top1(D,'rankG',lthr); mhG=match_volume_hold(t1G,'rankG',bnh)
    for m in sorted(HOLD):
        def mm(P):
            r=P[P.month==m]['label_fixed3'].dropna(); return (len(r),(r>0).mean()*100 if len(r) else 0.0,r.sum())
        gN,gW,gT=mm(bp); bN,bW,bT=mm(mhB); rN,rW,rT=mm(mhG)
        print(f"    {m}: base N={gN} WR={gW:.0f} | RankB N={bN} WR={bW:.0f} | RankG N={rN} WR={rW:.0f}")
print("\n=== DONE ===")
