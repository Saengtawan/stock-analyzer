"""GATE 2: head-to-head OLD vs NEW system scorecard, same no-leak WF holdout, bar-based
returns (apples-to-apples), 2 seed sets. Metrics per zone + system: N, WR, avg, total,
worst, max-drawdown(of equity), %pos-months.
OLD = binary win_p>=0.75 top1/day, hold-EOD (current no-leak recipe, all zones).
NEW = Z1 lambdarank-trunc top1-by-rank exit+30 | Z2 low-range exit+60 | Z3 win_p exit+60 |
      Z4 baseline win_p EOD (unchanged, inconclusive)."""
import sys, warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, lightgbm as lgb, sqlite3
from datetime import datetime, timedelta
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'; sys.path.insert(0,f'{ROOT}/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions
ZHP={'Z1':dict(learning_rate=0.05,max_depth=3,num_leaves=24,min_child_samples=50,reg_alpha=1.0,reg_lambda=1.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.9),
 'Z2':dict(learning_rate=0.03,max_depth=5,num_leaves=47,min_child_samples=80,reg_alpha=0.5,reg_lambda=3.0,n_estimators=500,bagging_fraction=0.8,feature_fraction=0.8),
 'Z3':dict(learning_rate=0.05,max_depth=4,num_leaves=31,min_child_samples=30,reg_alpha=0.5,reg_lambda=1.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8),
 'Z4':dict(learning_rate=0.05,max_depth=3,num_leaves=8,min_child_samples=30,reg_alpha=1.0,reg_lambda=3.0,n_estimators=400,bagging_fraction=0.7,feature_fraction=0.7)}
LOSS_HP=dict(learning_rate=0.03,max_depth=3,num_leaves=8,min_child_samples=50,reg_alpha=1.0,reg_lambda=5.0,n_estimators=300,bagging_fraction=0.8,feature_fraction=0.8)
RK=['learning_rate','max_depth','num_leaves','min_child_samples','reg_alpha','reg_lambda','n_estimators','bagging_fraction','feature_fraction']
PATH=['path_r_squared','path_peak_diff','path_low_diff','path_consol_range','path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel','path_momentum_accel','path_speed_early','path_up_vol_ratio','path_support_touches','path_bar_size_trend','path_wick_ratio','path_lower_wick_ratio','path_gap_ratio','path_time_at_high','path_vol_at_peaks','path_vwap_slope','path_ret_skewness']
ZCFG={'Z1':(0,9,True,'label_z12_market_3dd',False,0.40),'Z2':(10,29,True,'label_eod_green_v2',True,0.20),
      'Z3':(30,44,False,'label_z34_market',True,0.40),'Z4':(45,75,False,'label_z34_market',False,0.50)}
NEWEXIT={'Z1':30,'Z2':60,'Z3':60,'Z4':None}  # None=EOD
WIN_THR=0.75; TRAIN_DAYS=840
MONTHS=['2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05']; HOLD=['2026-03','2026-04','2026-05']
df=pd.read_pickle(f'{ROOT}/cache/bt_features/features_staging_noleak.pkl')
df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df=add_interactions(df); df['month']=df['date'].str[:7]
av=[f for f in V7_FEATS+CROSS_FEATS if f in df.columns]; NEW=sorted([c for c in df.columns if c.startswith('feat_')])
con=sqlite3.connect(f'{ROOT}/data/trade_history.db')
def fitb(X,y,hp,seeds): return [lgb.LGBMClassifier(**{**hp,'objective':'binary','bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':s}).fit(X,y) for s in seeds]
def grade(tv,v): qs=pd.Series(tv).quantile([.25,.5,.75]).values; return np.digitize(np.asarray(v,dtype=float),qs).astype(int)
def to_min(t): h,m=t.split(':'); return int(h)*60+int(m)
def bar_ab(bars,tm):
    sel=None
    for mn,o,c in bars:
        if mn<=tm: sel=(o,c)
        else: break
    return sel
barcache={}
def ret(sym,date,etime,H):
    k=(sym,date)
    if k not in barcache:
        barcache[k]=[(to_min(t),o,c) for t,o,c in con.execute("SELECT time_et,open,close FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et>='09:30' AND time_et<='16:00' ORDER BY time_et",(sym,date)).fetchall()]
    bars=barcache[k]
    if not bars: return None
    em=to_min(etime); eb=bar_ab(bars,em)
    if eb is None or eb[0]<=0: return None
    tgt=to_min('15:55') if H is None else em+H
    b=bar_ab(bars,tgt)
    return None if b is None else b[1]/eb[0]-1
def zone_picks(z,seeds):
    lo,hi,ui,wlab,usep,lth=ZCFG[z]; feats=av+(INTERACTIONS if ui else [])+NEW+(PATH if usep else [])
    zdf=df[(df.mins_from_open>=lo)&(df.mins_from_open<=hi)].copy(); rows=[]
    for tm in MONTHS:
        ts=tm+'-01'; cut=(datetime.strptime(ts,'%Y-%m-%d')-timedelta(days=TRAIN_DAYS)).strftime('%Y-%m-%d')
        tr=zdf[(zdf.date>=cut)&(zdf.date<ts)]; te=zdf[zdf.month==tm].copy()
        if len(tr)<1000 or len(te)==0: continue
        yw=tr[wlab]; mw=yw.notna()
        if mw.sum()<500 or len(np.unique(yw[mw].astype(int)))<2: continue
        wm=fitb(tr[mw][feats].fillna(0).values,yw[mw].astype(int).values,ZHP[z],seeds)
        te['wp']=np.min([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in wm],axis=0)
        lm=fitb(tr[feats].fillna(0).values,(tr['label_fixed3']<=-1.0).astype(int).values,LOSS_HP,seeds)
        te['lp']=np.max([m.predict_proba(te[feats].fillna(0).values)[:,1] for m in lm],axis=0)
        if z=='Z1':
            trw=tr[mw].copy(); trw['_g']=grade(trw['label_fixed3'].values,trw['label_fixed3'].values)
            s=trw.sort_values('date'); grp=s.groupby('date',sort=False).size().values; rhp={k:ZHP[z][k] for k in RK}
            rms=[lgb.LGBMRanker(**{**rhp,'objective':'lambdarank','lambdarank_truncation_level':1,'bagging_freq':1,'verbose':-1,'n_jobs':4,'random_state':sd}).fit(s[feats].fillna(0).values,s['_g'].astype(int).values,group=grp) for sd in seeds]
            te['rk']=np.mean([m.predict(te[feats].fillna(0).values) for m in rms],axis=0)
        else: te['rk']=te['wp']
        rows.append(te[['sym','date','time','month','label_fixed3','wp','lp','rk','range_pct']])
    D=pd.concat(rows,ignore_index=True)
    # OLD: gate win_p>=.75 & loss, top1 by win_p
    old=D[(D.wp>=WIN_THR)&(D.lp<=lth)].sort_values('wp',ascending=False).groupby('date').head(1)
    # NEW selection per zone
    if z=='Z1': new=D[D.lp<=lth].sort_values('rk',ascending=False).groupby('date').head(1)
    elif z=='Z2': new=D[(D.wp>=WIN_THR)&(D.lp<=lth)].sort_values('range_pct',ascending=True).groupby('date').head(1)
    else: new=D[(D.wp>=WIN_THR)&(D.lp<=lth)].sort_values('wp',ascending=False).groupby('date').head(1)
    old=old[old.month.isin(HOLD)]; new=new[new.month.isin(HOLD)]
    oldr=[(r['month'],ret(r['sym'],r['date'],r['time'],None)) for _,r in old.iterrows()]
    newr=[(r['month'],ret(r['sym'],r['date'],r['time'],NEWEXIT[z])) for _,r in new.iterrows()]
    return [x for x in oldr if x[1] is not None],[x for x in newr if x[1] is not None]
def card(rr):
    if not rr: return dict(N=0,WR=0,avg=0,tot=0,worst=0,posM=0)
    r=np.array([x[1] for x in rr]); mpos=sum(1 for m in HOLD if any(x[0]==m for x in rr) and np.mean([x[1] for x in rr if x[0]==m])>0)
    return dict(N=len(r),WR=(r>0).mean()*100,avg=r.mean()*100,tot=r.sum()*100,worst=r.min()*100,posM=mpos)
print("=== GATE 2: OLD vs NEW scorecard (holdout, bar-returns) ===")
for seeds,lbl in [(list(range(0,9)),'seeds0-8'),(list(range(200,209)),'seeds200-8')]:
    print(f"\n##### {lbl} #####")
    allold=[]; allnew=[]
    print(f"  {'zone':<5}{'metric':<8}{'OLD':>9}{'NEW':>9}")
    for z in ['Z1','Z2','Z3','Z4']:
        o,n=zone_picks(z,seeds); allold+=o; allnew+=n; co=card(o); cn=card(n)
        print(f"  {z:<5}{'WR%':<8}{co['WR']:>9.1f}{cn['WR']:>9.1f}")
        print(f"  {'':<5}{'tot%':<8}{co['tot']:>9.1f}{cn['tot']:>9.1f}")
        print(f"  {'':<5}{'worst%':<8}{co['worst']:>9.2f}{cn['worst']:>9.2f}")
        os=f"{co['N']}|{co['posM']}"; ns=f"{cn['N']}|{cn['posM']}"
        print(f"  {'':<5}{'N|posMo':<8}{os:>9}{ns:>9}")
    co=card(allold); cn=card(allnew)
    print(f"  SYS  WR%      {co['WR']:>9.1f}{cn['WR']:>9.1f}")
    print(f"       tot%     {co['tot']:>9.1f}{cn['tot']:>9.1f}")
    print(f"       worst%   {co['worst']:>9.2f}{cn['worst']:>9.2f}")
    print(f"       N        {co['N']:>9}{cn['N']:>9}")
con.close(); print("\nDONE")
