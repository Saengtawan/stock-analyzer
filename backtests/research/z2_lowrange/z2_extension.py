"""Z2 extension-vs-setup hypothesis test.
Part 1 DIAGNOSTIC: among Z2 gated candidates, bucket by extension/consolidation, show fwd WR.
Part 2 STRATEGY: variants (a) lowest gain_from_open, (b) win_p - k*rank(gain), vs 59% baseline.
WF harness + Z2 config copied VERBATIM from wf_lambdarank.py (Z2 only).
PnL=label_fixed3, win-label=label_eod_green_v2, top1/day, loss gate lp<=0.20, win gate wp>=0.75.
"""
import sys, warnings
warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, lightgbm as lgb
from datetime import datetime, timedelta
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'
sys.path.insert(0, f'{ROOT}/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions

# ---- Z2 config VERBATIM ----
LO,HI,USE_I = 10,29,True
WLAB='label_eod_green_v2'
HP=dict(learning_rate=0.03,max_depth=5,num_leaves=47,min_child_samples=80,reg_alpha=0.5,reg_lambda=3.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8)
LOSS_HP=dict(learning_rate=0.03,max_depth=3,num_leaves=8,min_child_samples=50,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8)
USE_PATH=True
LTHR=0.20
PATH=['path_r_squared','path_peak_diff','path_low_diff','path_consol_range','path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel','path_momentum_accel','path_speed_early','path_up_vol_ratio','path_support_touches','path_bar_size_trend','path_wick_ratio','path_lower_wick_ratio','path_gap_ratio','path_time_at_high','path_vol_at_peaks','path_vwap_slope','path_ret_skewness']
WIN_THR=0.75; TRAIN_DAYS=840; N_SEEDS=5
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']; HOLD={'2026-03','2026-04','2026-05'}

# extension / consolidation diagnostic features (carried thru, NOT used for win-model beyond config)
EXT_FEATS=['gain_from_open','from_peak_pct','range_pct','bars_since_hi','vs_vwap','consol','range_exp','hh_count','path_consol_range','path_choppiness','path_r_squared']

df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
feats_avail=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]; NEW=sorted([c for c in df.columns if c.startswith('feat_')])
feats=feats_avail+(INTERACTIONS if USE_I else [])+NEW+(PATH if USE_PATH else [])

def fit_binary(X,y,hp):
    ms=[]
    for s in range(N_SEEDS):
        m=lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}); m.fit(X,y); ms.append(m)
    return ms
def pred_min(ms,X): return np.min([m.predict_proba(X)[:,1] for m in ms],axis=0)

def run():
    zdf=df[(df['mins_from_open']>=LO)&(df['mins_from_open']<=HI)].copy()
    rows=[]
    carry=['date','month','label_fixed3']+[c for c in EXT_FEATS if c in zdf.columns]
    for tm in MONTHS:
        tm_start=tm+'-01'; cutoff=(datetime.strptime(tm_start,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
        tr=zdf[(zdf['date']>=cutoff)&(zdf['date']<tm_start)]; te=zdf[zdf['month']==tm].copy()
        if len(tr)<1000 or len(te)==0: continue
        yw=tr[WLAB]; mw=yw.notna()
        if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
        trw=tr[mw].copy()
        gms=fit_binary(trw[feats].fillna(0).values, yw[mw].astype(int).values, HP)
        te['wp']=pred_min(gms, te[feats].fillna(0).values)
        lms=fit_binary(tr[feats].fillna(0).values,(tr['label_fixed3']<=-1.0).astype(int).values,LOSS_HP)
        te['lp']=np.max([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in lms],axis=0)
        rows.append(te[carry+['wp','lp']])
    return pd.concat(rows,ignore_index=True)

D=run()
# gated candidates = passed loss gate AND win gate (the pool top-1 selects from)
GATED=D[(D['wp']>=WIN_THR)&(D['lp']<=LTHR)].copy()
# baseline picks: top1/day by win_p
def top1(pool,col,asc=False):
    if len(pool)==0: return pool
    return pool.sort_values(col,ascending=asc).groupby('date').head(1)
def stat(r):
    r=r['label_fixed3'].dropna(); return (len(r),(r>0).mean()*100 if len(r) else float('nan'),r.sum())
def permonth(P):
    out={}
    for m in sorted(HOLD):
        r=P[P.month==m]['label_fixed3'].dropna(); out[m]=(len(r),(r>0).mean()*100 if len(r) else float('nan'))
    return out

print("=== Z2 EXTENSION HYPOTHESIS ===")
print(f"GATED candidates: full N={len(GATED)} hold N={(GATED.month.isin(HOLD)).sum()}")

base=top1(GATED,'wp',asc=False)
bf=stat(base); bh=stat(base[base.month.isin(HOLD)])
print(f"\nBASELINE (top1 by win_p): full N={bf[0]} WR={bf[1]:.1f} tot={bf[2]:.1f} | HOLD N={bh[0]} WR={bh[1]:.1f} tot={bh[2]:.1f}")
print(f"  baseline HOLD per-month: {permonth(base[base.month.isin(HOLD)])}")

# ---------- PART 1: DIAGNOSTIC ----------
print("\n=== PART 1: DIAGNOSTIC — fwd WR by extension bucket (GATED candidates, HOLDOUT) ===")
GH=GATED[GATED.month.isin(HOLD)].copy()
GH['win']=(GH['label_fixed3']>0).astype(int)
for feat in EXT_FEATS:
    if feat not in GH.columns: continue
    v=GH[feat].dropna()
    if len(v)<20: continue
    try: q=pd.qcut(GH[feat],4,labels=['Q1(low)','Q2','Q3','Q4(high)'],duplicates='drop')
    except Exception: continue
    g=GH.groupby(q,observed=True).agg(N=('win','size'),WR=('win',lambda x:x.mean()*100),avgR=('label_fixed3','mean'))
    print(f"\n  [{feat}]")
    for idx,r in g.iterrows():
        print(f"    {idx}: N={int(r.N):4d} WR={r.WR:5.1f} avgR={r.avgR:+.2f}")
    # winner vs loser separation: (mean_w - mean_l)/sd
    w=GH[GH.win==1][feat].dropna(); l=GH[GH.win==0][feat].dropna()
    sd=GH[feat].std()
    if sd and sd==sd:
        print(f"    winners mean={w.mean():+.3f} losers mean={l.mean():+.3f}  (W-L)/sd={ (w.mean()-l.mean())/sd:+.3f}")

# ---------- PART 2: STRATEGY VARIANTS ----------
print("\n=== PART 2: STRATEGY VARIANTS vs 59% baseline (HOLDOUT, volume-matched) ===")
print(f"target HOLD N = {bh[0]}")

def vmatch_hold(pool,col,asc,target):
    h=pool[pool.month.isin(HOLD)]
    if len(h)==0 or target<=0: return h.iloc[0:0]
    t=h.sort_values(col,ascending=asc).head(target) if asc else h.sort_values(col,ascending=False).head(target)
    return t

def report(tag,picks,sortcol,asc):
    h=picks[picks.month.isin(HOLD)]
    nh,wh,th=stat(h)
    pm=permonth(h)
    beats=wh>59 and all((pm[m][1]>=50 and pm[m][0]>=5) for m in HOLD if pm[m][1]==pm[m][1])
    print(f"\n  {tag}")
    print(f"    HOLD N={nh} WR={wh:.1f} tot={th:.1f}  per-month={pm}")
    return wh,nh

# (a) lowest gain_from_open among gated, top1/day
va=top1(GATED,'gain_from_open',asc=True)
report("(a) top1 by LOWEST gain_from_open", va,'gain_from_open',True)

# (a2) lowest from_peak_pct (closest to peak = least pulled back? actually from_peak negative). try lowest extension via range_pct
va3=top1(GATED,'range_pct',asc=True)
report("(a3) top1 by LOWEST range_pct", va3,'range_pct',True)

# (a4) highest path_consol_range proxy? lower consol value = tighter. top1 by lowest path_choppiness (smoother trend)
if 'path_consol_range' in GATED.columns:
    va5=top1(GATED,'path_consol_range',asc=True)
    report("(a5) top1 by LOWEST path_consol_range (tightest)", va5,'path_consol_range',True)

# (b) win_p penalized by extension rank: score = win_p - k*rank_norm(gain_from_open)
def variant_b(k):
    G=GATED.copy()
    # per-day rank of gain_from_open (0=lowest extension best). normalize to [0,1] across full pool
    G['ext_rank']=G['gain_from_open'].rank(pct=True)  # high gain -> high rank -> penalized
    G['score_b']=G['wp']-k*G['ext_rank']
    return top1(G,'score_b',asc=False)
for k in [0.05,0.10,0.15,0.20,0.30,0.50]:
    vb=variant_b(k)
    wh,nh=report(f"(b) win_p - {k}*rank(gain_from_open)", vb,'score_b',False)

print("\n=== DONE ===")
