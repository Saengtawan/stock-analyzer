"""LOCK Z2 deploy candidate on LIVE-matching metric: close-fill entry, hold-EOD vs +60min.
OLD(win_p,hold-EOD) vs low-range(hold-EOD) vs low-range+exit60. 3 seed sets + per-month.
Anchor: real live ml_filter = 41.5%."""
import sys, warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, lightgbm as lgb, sqlite3
from datetime import datetime, timedelta
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'; sys.path.insert(0,f'{ROOT}/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions
HP=dict(learning_rate=0.03,max_depth=5,num_leaves=47,min_child_samples=80,reg_alpha=0.5,reg_lambda=3.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8)
LOSS_HP=dict(learning_rate=0.03,max_depth=3,num_leaves=8,min_child_samples=50,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8)
WLAB='label_eod_green_v2'; WIN_THR=0.75; LOSS_THR=0.20; LO,HI=10,29; TRAIN_DAYS=840
PATH=['path_r_squared','path_peak_diff','path_low_diff','path_consol_range','path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel','path_momentum_accel','path_speed_early','path_up_vol_ratio','path_support_touches','path_bar_size_trend','path_wick_ratio','path_lower_wick_ratio','path_gap_ratio','path_time_at_high','path_vol_at_peaks','path_vwap_slope','path_ret_skewness']
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']; HOLD=['2026-03','2026-04','2026-05']
df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
feats=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]+INTERACTIONS+sorted([c for c in df.columns if c.startswith('feat_')])+PATH
zdf=df[(df.mins_from_open>=LO)&(df.mins_from_open<=HI)].copy()
con=sqlite3.connect(f'{ROOT}/data/trade_history.db'); bc={}
def fitb(X,y,hp,seeds): return [lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}).fit(X,y) for s in seeds]
def to_min(t): h,m=t.split(':'); return int(h)*60+int(m)
def gb(s,d):
    k=(s,d)
    if k not in bc: bc[k]=[(to_min(t),o,c) for t,o,c in con.execute("SELECT time_et,open,close FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et>='09:30' AND time_et<='16:00' ORDER BY time_et",(s,d)).fetchall()]
    return bc[k]
def at(bars,tm):
    sel=None
    for b in bars:
        if b[0]<=tm: sel=b
        else: break
    return sel
def ret(s,d,et,H):  # close-fill entry, exit at H or EOD
    bars=gb(s,d)
    if not bars: return None
    em=to_min(et); eb=at(bars,em)
    if eb is None or eb[2]<=0: return None
    entry=eb[2]; tgt=to_min('15:55') if H is None else em+H; xb=at(bars,tgt)
    return None if xb is None else (xb[2]/entry-1)*100
def build(seeds):
    rows=[]
    for tm in MONTHS:
        ts=tm+'-01'; cut=(datetime.strptime(ts,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
        tr=zdf[(zdf.date>=cut)&(zdf.date<ts)]; te=zdf[zdf.month==tm].copy()
        if len(tr)<1000 or len(te)==0: continue
        yw=tr[WLAB]; mw=yw.notna()
        if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
        wm=fitb(tr[mw][feats].fillna(0).values,yw[mw].astype(int).values,HP,seeds)
        te['wp']=np.min([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in wm],axis=0)
        lm=fitb(tr[feats].fillna(0).values,(tr['label_fixed3']<=-1.0).astype(int).values,LOSS_HP,seeds)
        te['lp']=np.max([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in lm],axis=0)
        rows.append(te[['sym','date','time','month','wp','lp','range_pct']])
    return pd.concat(rows,ignore_index=True)
def summ(g,H):
    rr=[(r['month'],ret(r['sym'],r['date'],r['time'],H)) for _,r in g.iterrows()]; rr=[x for x in rr if x[1] is not None]
    if not rr: return "N=0"
    a=np.array([x[1] for x in rr]); pm=' '.join(f"{m[5:]}:{(np.array([x[1] for x in rr if x[0]==m])>0).mean()*100 if any(x[0]==m for x in rr) else 0:.0f}%" for m in HOLD)
    return f"N={len(a)} WR={(a>0).mean()*100:4.1f}% tot={a.sum():+4.0f} | {pm}"
print("=== Z2 DEPLOY confirm (close-fill, LIVE metric; anchor live=41.5%) ===")
for seeds,lbl in [(list(range(0,9)),'s0-8'),(list(range(100,109)),'s100-8'),(list(range(200,209)),'s200-8')]:
    D=build(list(seeds)); G=D[(D.wp>=WIN_THR)&(D.lp<=LOSS_THR)]
    old=G.sort_values('wp',ascending=False).groupby('date').head(1); old=old[old.month.isin(HOLD)]
    lr=G.sort_values('range_pct',ascending=True).groupby('date').head(1); lr=lr[lr.month.isin(HOLD)]
    print(f"\n-- {lbl} --")
    print(f"  OLD (win_p, hold-EOD)      {summ(old,None)}")
    print(f"  low-range, hold-EOD        {summ(lr,None)}")
    print(f"  low-range + exit+60        {summ(lr,60)}")
con.close(); print("\nDONE")
