#!/usr/bin/env python3
"""v10.0 Full System Simulation — Walk-Forward 4 Years."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import sqlite3, numpy as np
from collections import defaultdict
from sklearn.ensemble import GradientBoostingClassifier

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'trade_history.db')
conn = sqlite3.connect(DB)

rows = conn.execute('''
    SELECT b.scan_date, b.symbol, b.outcome_5d, b.atr_pct, b.momentum_5d,
           b.distance_from_20d_high, b.volume_ratio, b.vix_at_signal, b.sector,
           COALESCE(m.vix_close, 20), m.spy_close, m.crude_close,
           COALESCE(m.vix3m_close, 22), m.yield_10y,
           mb.pct_above_20d_ma, mb.new_52w_lows, mb.new_52w_highs,
           d1.open, d1.high, d1.low, d1.close,
           d3.high, d3.low, d3.close,
           d5.close
    FROM backfill_signal_outcomes b
    LEFT JOIN macro_snapshots m ON b.scan_date = m.date
    LEFT JOIN market_breadth mb ON b.scan_date = mb.date
    JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
    JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
    JOIN signal_daily_bars d5 ON b.scan_date=d5.scan_date AND b.symbol=d5.symbol AND d5.day_offset=5
    WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0 AND d1.open > 0
    AND m.spy_close IS NOT NULL AND mb.pct_above_20d_ma IS NOT NULL
    ORDER BY b.scan_date
''').fetchall()

sector_rows = conn.execute('''
    SELECT date, sector, pct_change FROM sector_etf_daily_returns
    WHERE sector NOT IN ('S&P 500','US Dollar','Treasury Long','Gold') ORDER BY date
''').fetchall()
sector_daily = defaultdict(dict)
for r in sector_rows:
    sector_daily[r[0]][r[1]] = r[2]
sector_dates = sorted(sector_daily.keys())

spy_data = {r[0]: r[1] for r in conn.execute('SELECT date, spy_close FROM macro_snapshots WHERE spy_close IS NOT NULL').fetchall()}
conn.close()

monthly = defaultdict(list)
for r in rows:
    monthly[r[0][:7]].append(r)
months = sorted(monthly.keys())

def sim_trade(d1o, d1h, d1l, d3h, d3l, d3c, d5c, atr, tp_r):
    sl = max(1.5, min(5.0, 1.5 * atr))
    tp = max(0.5, tp_r * atr)
    for h, l in [(d1h, d1l), (d3h, d3l)]:
        if (l/d1o-1)*100 <= -sl: return -sl
        if (h/d1o-1)*100 >= tp: return tp
    return (d5c/d1o-1)*100

print(f"{'Mo':8s} {'v5.3$':>7s} {'v5WR':>5s} {'v10$':>7s} {'v10WR':>5s} {'Mkt$':>7s} {'MkWR':>5s} {'All$':>7s} {'AlWR':>5s}")
print("-" * 65)

totals = {k: {'t':0,'w':0,'p':0} for k in ['v53','v10','mkt','all']}
mo_pnl = {k: [] for k in ['v53','v10','mkt','all']}

for mi, month in enumerate(months):
    if mi < 12: continue
    train = []
    for m in months[mi-12:mi]:
        train.extend(monthly[m])
    test = monthly[month]
    if len(train) < 500 or len(test) < 10: continue

    # Train RegimeBrain
    td = defaultdict(list)
    for s in train: td[s[0]].append(s)
    X, y = [], []
    for dt, sigs in td.items():
        s = sigs[0]
        X.append([s[9],s[12],s[10],s[11] or 75,s[13] or 4,s[14],s[15],s[16] or 50])
        y.append(1 if np.mean([1 if ss[2]>0 else 0 for ss in sigs]) > 0.55 else 0)
    clf = GradientBoostingClassifier(n_estimators=200,max_depth=3,learning_rate=0.05,min_samples_leaf=10,subsample=0.8,random_state=42)
    clf.fit(np.array(X), np.array(y))

    td2 = defaultdict(list)
    for s in test: td2[s[0]].append(s)

    v53p,v53t,v53w = 0,0,0
    v10p,v10t,v10w = 0,0,0
    mkp,mkt2,mkw = 0,0,0

    for dt, sigs in td2.items():
        s0 = sigs[0]
        f = [s0[9],s0[12],s0[10],s0[11] or 75,s0[13] or 4,s0[14],s0[15],s0[16] or 50]
        rp = clf.predict_proba(np.array(f).reshape(1,-1))[0,1]
        size = 1.0 if rp>=0.50 else 0.5 if rp>=0.35 else 0.25

        top3 = sorted(sigs, key=lambda s: s[5] or 0)[:3]
        for s in top3:
            p53 = sim_trade(s[17],s[18],s[19],s[21],s[22],s[23],s[24],s[3],0.5)
            v53p += p53; v53t += 1
            if p53 > 0: v53w += 1
            p10 = sim_trade(s[17],s[18],s[19],s[21],s[22],s[23],s[24],s[3],1.2)
            v10p += p10*size; v10t += 1
            if p10 > 0: v10w += 1

        # Sector contrarian
        if dt in sector_dates:
            idx = sector_dates.index(dt)
            if idx >= 16 and idx+5 < len(sector_dates):
                sr = {sec: sum(sector_daily[sector_dates[j]].get(sec,0) or 0 for j in range(idx-16,idx)) for sec in sector_daily[dt]}
                if sr:
                    worst = min(sr, key=sr.get)
                    fwd = sum(sector_daily[sector_dates[j]].get(worst,0) or 0 for j in range(idx+1,min(idx+6,len(sector_dates))))
                    mkp += fwd*0.5; mkt2 += 1
                    if fwd > 0: mkw += 1

    v53wr = v53w/v53t*100 if v53t else 0
    v10wr = v10w/v10t*100 if v10t else 0
    mkwr = mkw/mkt2*100 if mkt2 else 0
    allp = v10p + mkp
    allt = v10t + mkt2
    allw = v10w + mkw
    allwr = allw/allt*100 if allt else 0

    print(f"{month:8s} {v53p*5:+6.0f} {v53wr:4.0f}% {v10p*5:+6.0f} {v10wr:4.0f}% {mkp*5:+6.0f} {mkwr:4.0f}% {allp*5:+6.0f} {allwr:4.0f}%")

    for k,v in [('v53',v53p*5),('v10',v10p*5),('mkt',mkp*5),('all',allp*5)]: mo_pnl[k].append(v)
    for k,(t,w,p) in [('v53',(v53t,v53w,v53p)),('v10',(v10t,v10w,v10p)),('mkt',(mkt2,mkw,mkp)),('all',(allt,allw,allp))]:
        totals[k]['t']+=t; totals[k]['w']+=w; totals[k]['p']+=p

print("=" * 65)
print()
print(f"{'':18s} {'v5.3(old)':>12s} {'v10 DIP':>12s} {'Market':>12s} {'COMBINED':>12s}")
print("-" * 66)
for name, fn in [
    ('Trades', lambda k: str(totals[k]['t'])),
    ('WR', lambda k: f"{totals[k]['w']/totals[k]['t']*100:.1f}%" if totals[k]['t'] else 'N/A'),
    ('E[R]/trade', lambda k: f"{totals[k]['p']/totals[k]['t']:+.3f}%" if totals[k]['t'] else 'N/A'),
    ('$/mo avg', lambda k: f"${np.mean(mo_pnl[k]):+.0f}"),
    ('Worst month', lambda k: f"${min(mo_pnl[k]):+.0f}" if mo_pnl[k] else 'N/A'),
    ('Best month', lambda k: f"${max(mo_pnl[k]):+.0f}" if mo_pnl[k] else 'N/A'),
    ('Win months', lambda k: f"{sum(1 for x in mo_pnl[k] if x>0)}/{len(mo_pnl[k])}"),
]:
    vals = [fn(k) for k in ['v53','v10','mkt','all']]
    print(f"{name:18s} {vals[0]:>12s} {vals[1]:>12s} {vals[2]:>12s} {vals[3]:>12s}")
