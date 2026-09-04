"""Z2 low-range exit-horizon test. WF refit per month, validated Z2 config (9-seed),
select top-1/day by LOWEST range_pct among gated candidates (wp>=0.75, lp<=0.20).
For each holdout pick compute realized return at +30/+60/+90/+120min and EOD(15:55)
from intraday_bars_5m. Entry/exit price = close of the 5-min bar at-or-just-before
target ET time. Decision uses only <=entry-time info (validated config)."""
import sys, warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, lightgbm as lgb, sqlite3
from datetime import datetime, timedelta
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'; sys.path.insert(0,f'{ROOT}/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions

WINHP=dict(learning_rate=0.03,max_depth=5,num_leaves=47,min_child_samples=80,reg_alpha=0.5,reg_lambda=3.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8)
CURLOSS=dict(learning_rate=0.03,max_depth=3,num_leaves=8,min_child_samples=50,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8)
WLAB='label_eod_green_v2'; WIN_THR=0.75; LOSS_THR=0.20; LO,HI=10,29; TRAIN_DAYS=840; SEEDS=list(range(0,9))
PATH=['path_r_squared','path_peak_diff','path_low_diff','path_consol_range','path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel','path_momentum_accel','path_speed_early','path_up_vol_ratio','path_support_touches','path_bar_size_trend','path_wick_ratio','path_lower_wick_ratio','path_gap_ratio','path_time_at_high','path_vol_at_peaks','path_vwap_slope','path_ret_skewness']
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']; HOLD=['2026-03','2026-04','2026-05']

df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
feats=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]+INTERACTIONS+sorted([c for c in df.columns if c.startswith('feat_')])+PATH
zdf=df[(df.mins_from_open>=LO)&(df.mins_from_open<=HI)].copy()

def fit(X,y,hp,seeds):
    return [lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}).fit(X,y) for s in seeds]

rows=[]
for tm in MONTHS:
    ts=tm+'-01'; cut=(datetime.strptime(ts,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
    tr=zdf[(zdf.date>=cut)&(zdf.date<ts)]; te=zdf[zdf.month==tm].copy()
    if len(tr)<1000 or len(te)==0: continue
    yw=tr[WLAB]; mw=yw.notna()
    if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
    wm=fit(tr[mw][feats].fillna(0).values,yw[mw].astype(int).values,WINHP,SEEDS)
    te['wp']=np.min([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in wm],axis=0)
    lm=fit(tr[feats].fillna(0).values,(tr['label_fixed3']<=-1.0).astype(int).values,CURLOSS,SEEDS)
    te['lp']=np.max([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in lm],axis=0)
    rows.append(te[['sym','date','time','month','mins_from_open','label_fixed3','wp','lp','range_pct']])
D=pd.concat(rows,ignore_index=True)
# validated selection: gated, top-1/day by LOWEST range_pct
g=D[(D.wp>=WIN_THR)&(D.lp<=LOSS_THR)].sort_values('range_pct',ascending=True).groupby('date').head(1).copy()
g=g[g.month.isin(HOLD)].reset_index(drop=True)
print(f"Holdout low-range picks: N={len(g)}  EOD-label WR={(g.label_fixed3>0).mean()*100:.1f}%  per-month-N: "+
      " ".join(f"{m[5:]}:{(g.month==m).sum()}" for m in HOLD))

# --- pull bars for needed (sym,date) and compute horizon returns ---
con=sqlite3.connect(f'{ROOT}/data/trade_history.db')
HORIZONS=[30,60,90,120]  # minutes
def to_min(t):  # 'HH:MM' -> minutes since midnight
    h,m=t.split(':'); return int(h)*60+int(m)
def bar_at_or_before(bars, target_min):
    # bars: list of (min_et, open, close) sorted asc. pick last bar with min_et<=target
    sel=None
    for mn,op,cl in bars:
        if mn<=target_min: sel=(op,cl)
        else: break
    return sel

results={H:[] for H in HORIZONS}; eod_rets=[]
miss=0
for _,r in g.iterrows():
    q="SELECT time_et,open,close FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et>='09:30' AND time_et<='16:00' ORDER BY time_et"
    bars=[(to_min(te),op,cl) for te,op,cl in con.execute(q,(r['sym'],r['date'])).fetchall()]
    if not bars: miss+=1; continue
    entry_min=to_min(r['time'])
    eb=bar_at_or_before(bars, entry_min)
    if eb is None or eb[0]<=0: miss+=1; continue
    entry_px=eb[0]  # entry = OPEN of entry bar (matches label_fixed3 convention)
    # EOD = 15:55 close (or last bar <=15:55)
    eod_px=bar_at_or_before(bars, to_min('15:55'))[1]
    eod_rets.append((r['month'], eod_px/entry_px-1))
    for H in HORIZONS:
        b=bar_at_or_before(bars, entry_min+H)
        if b is None: continue
        results[H].append((r['month'], b[1]/entry_px-1))  # exit = close of horizon bar

def summ(arr):
    if not arr: return "N=0"
    rs=np.array([x[1] for x in arr]); wr=(rs>0).mean()*100
    pm=" ".join(f"{m[5:]}:{ (np.array([x[1] for x in arr if x[0]==m])>0).mean()*100 if any(x[0]==m for x in arr) else 0:.0f}%({sum(1 for x in arr if x[0]==m)})" for m in HOLD)
    return f"N={len(arr):2d}  WR={wr:4.1f}%  avg={rs.mean()*100:+.2f}%  | {pm}"

print(f"\nmissing-bar picks dropped: {miss}")
print(f"{'horizon':<10}{'summary'}")
for H in HORIZONS:
    print(f"+{H:<8}{summ(results[H])}")
print(f"{'EOD':<9}{summ(eod_rets)}")
con.close()
print("DONE")
