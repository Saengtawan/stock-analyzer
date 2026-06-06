"""Z2 LOSS-MODEL retrain. WIN-model (path-binary, label_eod_green_v2) IDENTICAL.
Vary loss-model: loss-label threshold T in {-0.5,-1.0(cur),-1.5,-2.0}
  x loss-HP variants (current + 2-3 more expressive).
For each (T x HP), re-tune loss-gate on DEV, report DEV-best gate's HOLDOUT
WR/N/tot + per-month spread. Baseline Z2 holdout WR ~= 59%.
WF: monthly refit, TRAIN_DAYS=840, 5-seed (win_p=min, loss_p=max), top1/day.
"""
import sys, warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, lightgbm as lgb
from datetime import datetime, timedelta
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'; sys.path.insert(0,f'{ROOT}/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions
LO,HI=10,29
# WIN-model HP (Z2) -- IDENTICAL, never touched
HP=dict(learning_rate=0.03,max_depth=5,num_leaves=47,min_child_samples=80,reg_alpha=0.5,reg_lambda=3.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8)
# loss-model HP variants
LOSS_HP_CUR=dict(learning_rate=0.03,max_depth=3,num_leaves=8,min_child_samples=50,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8)
LOSS_HP_VARIANTS={
 'cur(d3/l8/mc50)':LOSS_HP_CUR,
 'd4/l16/mc30'    :dict(learning_rate=0.03,max_depth=4,num_leaves=16,min_child_samples=30,reg_alpha=1.0,reg_lambda=3.0,n_estimators=400,bagging_fraction=0.8,feature_fraction=0.8),
 'd5/l31/mc20'    :dict(learning_rate=0.03,max_depth=5,num_leaves=31,min_child_samples=20,reg_alpha=0.5,reg_lambda=2.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8),
 'd5/l47/mc10'    :dict(learning_rate=0.05,max_depth=5,num_leaves=47,min_child_samples=10,reg_alpha=0.3,reg_lambda=1.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8),
}
LOSS_THRESHOLDS=[-0.5,-1.0,-1.5,-2.0]   # loss-label definition T: loser = label_fixed3 <= T
GATES=[0.05,0.10,0.15,0.20,0.25,0.30,0.40,0.50]  # loss-gate candidates
WLAB='label_eod_green_v2'; WIN_THR=0.75; TRAIN_DAYS=840
N_SEEDS=int(sys.argv[1]) if len(sys.argv)>1 else 5
PATH=['path_r_squared','path_peak_diff','path_low_diff','path_consol_range','path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel','path_momentum_accel','path_speed_early','path_up_vol_ratio','path_support_touches','path_bar_size_trend','path_wick_ratio','path_lower_wick_ratio','path_gap_ratio','path_time_at_high','path_vol_at_peaks','path_vwap_slope','path_ret_skewness']
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']
DEV={'2025-11','2025-12','2026-01','2026-02'}; HOLD={'2026-03','2026-04','2026-05'}
df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
feats=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]+INTERACTIONS+sorted([c for c in df.columns if c.startswith('feat_')])+PATH
zdf=df[(df['mins_from_open']>=LO)&(df['mins_from_open']<=HI)].copy()
def fitb(X,y,hp): return [lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}).fit(X,y) for s in range(N_SEEDS)]
def pmin(ms,X): return np.min([m.predict_proba(X)[:,1] for m in ms],axis=0)
def pmax(ms,X): return np.max([m.predict_proba(X)[:,1] for m in ms],axis=0)

# WF: per month, fit win-model once; fit each (T x HP) loss-model. cache lp columns.
rows=[]
for tm in MONTHS:
    ts=tm+'-01'; cut=(datetime.strptime(ts,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    tr=zdf[(zdf['date']>=cut)&(zdf['date']<ts)]; te=zdf[zdf['month']==tm].copy()
    if len(tr)<1000 or len(te)==0: continue
    yw=tr[WLAB]; mw=yw.notna()
    if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
    Xtr=tr[feats].fillna(0).values; Xte=te[feats].fillna(0).values
    # win-model (identical)
    gms=fitb(tr[mw][feats].fillna(0).values,yw[mw].astype(int).values,HP)
    te['wp']=pmin(gms,Xte)
    lf=tr['label_fixed3']
    for T in LOSS_THRESHOLDS:
        yl=(lf<=T).astype(int).values
        if len(np.unique(yl))<2: continue
        for hpname,hp in LOSS_HP_VARIANTS.items():
            lms=fitb(Xtr,yl,hp)
            te[f'lp__{T}__{hpname}']=pmax(lms,Xte)
    rows.append(te)
    print(f"[fit] {tm} tr={len(tr)} te={len(te)}",flush=True)
D=pd.concat(rows,ignore_index=True)

def swr(P,split):
    r=P[P.month.isin(split)]['label_fixed3'].dropna(); return (len(r),(r>0).mean()*100 if len(r) else float('nan'),r.sum())
def pm(P):
    return ' '.join(f"{m[5:]}:{((P[P.month==m]['label_fixed3']>0).mean()*100 if len(P[P.month==m]) else 0):.0f}%({len(P[P.month==m])})" for m in sorted(HOLD))

print(f"\n=== Z2 loss-model retrain (path-binary win IDENTICAL). N_SEEDS={N_SEEDS} ===")
print("Baseline Z2 holdout WR ~= 59%. Real only if HOLD WR>59 AND all 3 months represented.\n")
print(f"{'lossT':<6}{'HP':<16}{'gate*':<7}{'DEVwr':>6}{'HOLD N/WR/tot':>18}   per-month-HOLD")
best=[]
for T in LOSS_THRESHOLDS:
    for hpname in LOSS_HP_VARIANTS:
        col=f'lp__{T}__{hpname}'
        if col not in D.columns:
            print(f"{T:<6}{hpname:<16}  (single-class loss-label, skipped)"); continue
        # tune gate on DEV
        best_gate=None; best_devwr=-1; best_devn=0
        for gt in GATES:
            g=D[(D['wp']>=WIN_THR)&(D[col]<=gt)].sort_values('wp',ascending=False).groupby('date').head(1)
            dn,dw,dt=swr(g,DEV)
            if dn<10 or dw!=dw: continue
            if dw>best_devwr: best_devwr=dw; best_gate=gt; best_devn=dn
        if best_gate is None:
            print(f"{T:<6}{hpname:<16} (no valid DEV gate)"); continue
        g=D[(D['wp']>=WIN_THR)&(D[col]<=best_gate)].sort_values('wp',ascending=False).groupby('date').head(1)
        gh=g[g.month.isin(HOLD)]
        hn,hw,ht=swr(g,HOLD)
        nmonths=gh['month'].nunique()
        flag=' <<<' if (hw==hw and hw>59 and nmonths==3) else ''
        print(f"{T:<6}{hpname:<16}{best_gate:<7}{best_devwr:>6.1f}{f'{hn}/{hw:.0f}%/{ht:+.0f}':>18}   {pm(gh)}{flag}")
        best.append((T,hpname,best_gate,best_devwr,hn,hw,ht,nmonths))
print("\n--- candidates beating 59% holdout with all 3 months ---")
robust=[b for b in best if b[5]==b[5] and b[5]>59 and b[7]==3]
if robust:
    for b in robust: print(f"  lossT={b[0]} HP={b[1]} gate={b[2]} DEVwr={b[3]:.1f} HOLD N={b[4]} WR={b[5]:.1f} tot={b[6]:+.1f}")
else:
    print("  NONE.")
print("=== DONE ===")
