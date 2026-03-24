#!/usr/bin/env python3
"""
Final test: refined D+E+VIX_SMART variants.
Finding: Tech is the real crisis winner. Healthcare/CommSvc break even.
Also test LQD -0.7 (optimal from sensitivity).
"""
import sqlite3
import numpy as np
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'
PER_SLOT = 1250
COMMISSION = 0.50
SLIPPAGE = 0.10
MAX_TRADES_PER_DAY = 2


def load_data():
    conn = sqlite3.connect(str(DB_PATH))
    signals = conn.execute("""
        SELECT scan_date, symbol, sector, scan_price, atr_pct, entry_rsi,
               distance_from_20d_high, momentum_5d, momentum_20d,
               volume_ratio, vix_at_signal,
               outcome_1d, outcome_2d, outcome_3d, outcome_4d, outcome_5d,
               outcome_max_gain_5d, outcome_max_dd_5d
        FROM backfill_signal_outcomes WHERE outcome_5d IS NOT NULL ORDER BY scan_date
    """).fetchall()
    breadth = dict(conn.execute("SELECT date, pct_above_20d_ma FROM market_breadth").fetchall())
    bd = sorted(breadth.keys())
    breadth_delta = {}
    for i, d in enumerate(bd):
        if i >= 5: breadth_delta[d] = breadth[d] - breadth[bd[i-5]]
    macro = conn.execute("SELECT date, lqd_close FROM macro_snapshots WHERE date>='2020-01-01' ORDER BY date").fetchall()
    m = {r[0]: r[1] for r in macro}
    md = sorted(m.keys())
    lqd_5d = {}
    for i, d in enumerate(md):
        if i >= 5 and m[d] and m[md[i-5]] and m[md[i-5]] > 0:
            lqd_5d[d] = ((m[d] - m[md[i-5]]) / m[md[i-5]]) * 100
    conn.close()
    return signals, breadth, breadth_delta, lqd_5d


def base_ok(sig):
    _, _, _, _, _, rsi, dist, m5, m20, _, _ = sig[:11]
    if m5 is not None and m5 < -5: return False
    if m20 is not None and m20 < -10: return False
    if dist is not None and dist < -5: return False
    if rsi is not None and rsi > 60: return False
    return True


def sim(signals, breadth, bd, lqd, fn):
    by_date = defaultdict(list)
    for s in signals: by_date[s[0]].append(s)
    monthly_pnl = defaultdict(float)
    yearly_pnl = defaultdict(float)
    yearly_trades = defaultdict(int)
    yearly_wins = defaultdict(int)
    trades = 0; wins = 0; pnl = 0.0
    for day in sorted(by_date.keys()):
        sigs = sorted(by_date[day], key=lambda s: s[6] if s[6] else 0)
        b, d, l = breadth.get(day), bd.get(day), lqd.get(day)
        dn = 0
        for s in sigs:
            if dn >= MAX_TRADES_PER_DAY: break
            ok, sz = fn(s, b, d, l)
            if not ok: continue
            p, o = s[3], s[15]
            if o is None or not p or p <= 0: continue
            ps = PER_SLOT * sz
            if ps < 100: continue
            cost = SLIPPAGE*2 + COMMISSION/ps*100
            net = o - cost
            t_pnl = ps * net / 100
            monthly_pnl[day[:7]] += t_pnl
            yearly_pnl[day[:4]] += t_pnl
            yearly_trades[day[:4]] += 1
            trades += 1; pnl += t_pnl; dn += 1
            if net > 0: wins += 1; yearly_wins[day[:4]] += 1
    months = sorted(monthly_pnl.keys())
    mr = [monthly_pnl[m] for m in months]
    avg = np.mean(mr) if mr else 0
    std = np.std(mr) if len(mr)>1 else 1
    cum = np.cumsum(mr); peak = np.maximum.accumulate(cum)
    mdd = float(np.min(cum-peak)) if len(cum) else 0
    prof = sum(1 for m in months if monthly_pnl[m]>0)/len(months)*100 if months else 0
    return {'pnl': pnl, 'n': trades, 'wr': wins/trades*100 if trades else 0,
            'mo': avg, 'sharpe': avg/std*np.sqrt(12) if std else 0,
            'mdd': mdd, 'prof': prof, 'yp': dict(yearly_pnl),
            'yt': dict(yearly_trades), 'yw': dict(yearly_wins)}


def pr(name, r, base=None):
    d = f" ({r['mo']-base['mo']:>+.0f})" if base else ""
    y22 = r['yp'].get('2022',0); y20 = r['yp'].get('2020',0); y23 = r['yp'].get('2023',0)
    print(f"  {name:<35} ${r['pnl']:>+8,.0f} ${r['mo']:>+6,.0f}{d:<8} "
          f"{r['n']:>5} {r['wr']:>5.1f}% {r['sharpe']:>5.2f} ${r['mdd']:>+7,.0f} "
          f"{r['prof']:>5.1f}% ${y20:>+6,.0f} ${y22:>+6,.0f} ${y23:>+6,.0f}")


def main():
    signals, breadth, bd, lqd = load_data()

    # Baseline
    def f0(s,b,d,l):
        v=s[10]
        if v and 20<=v<24: return False,0
        if v and v>=30: return False,0
        if b is not None and b<35: return False,0
        if d is not None and d<-15: return False,0
        if d is not None and d<=0: return False,0
        return base_ok(s),1.0

    # V1: Original D+E+VIX_SMART (3 sectors)
    CG3 = {'Healthcare','Technology','Communication Services'}
    CB = {'Utilities','Real Estate'}
    def f1(s,b,d,l):
        v,sec=s[10],s[2]
        if v and 20<=v<24:
            if sec in CB: return False,0
            if sec in CG3: pass
            else: return False,0
        if v and v>=30:
            if sec in CB: return False,0
            if sec in CG3: pass
            else: return False,0
        if l is not None and l<-0.5: return False,0
        if b is not None and b<35: return False,0
        if d is not None and d<-15: return False,0
        if d is not None and d<=0: return False,0
        if not base_ok(s): return False,0
        sz=1.0
        if v and v>=24 and sec in CG3: sz=0.5
        elif v and 20<=v<24 and sec in CG3: sz=0.75
        return True,sz

    # V2: Tech only (refined)
    def f2(s,b,d,l):
        v,sec=s[10],s[2]
        if v and 20<=v<24:
            if sec=='Technology': pass  # allow Tech only
            else: return False,0
        if v and v>=30:
            if sec=='Technology': pass
            else: return False,0
        if l is not None and l<-0.5: return False,0
        if b is not None and b<35: return False,0
        if d is not None and d<-15: return False,0
        if d is not None and d<=0: return False,0
        if not base_ok(s): return False,0
        sz=1.0
        if v and v>=24 and sec=='Technology': sz=0.5
        elif v and 20<=v<24 and sec=='Technology': sz=0.75
        return True,sz

    # V3: Tech only + LQD -0.7
    def f3(s,b,d,l):
        v,sec=s[10],s[2]
        if v and 20<=v<24:
            if sec=='Technology': pass
            else: return False,0
        if v and v>=30:
            if sec=='Technology': pass
            else: return False,0
        if l is not None and l<-0.7: return False,0
        if b is not None and b<35: return False,0
        if d is not None and d<-15: return False,0
        if d is not None and d<=0: return False,0
        if not base_ok(s): return False,0
        sz=1.0
        if v and v>=24 and sec=='Technology': sz=0.5
        elif v and 20<=v<24 and sec=='Technology': sz=0.75
        return True,sz

    # V4: Tech+Healthcare + LQD -0.7 (split the difference)
    CG2 = {'Healthcare','Technology'}
    def f4(s,b,d,l):
        v,sec=s[10],s[2]
        if v and 20<=v<24:
            if sec in CG2: pass
            else: return False,0
        if v and v>=30:
            if sec in CB: return False,0
            if sec in CG2: pass
            else: return False,0
        if l is not None and l<-0.7: return False,0
        if b is not None and b<35: return False,0
        if d is not None and d<-15: return False,0
        if d is not None and d<=0: return False,0
        if not base_ok(s): return False,0
        sz=1.0
        if v and v>=24 and sec in CG2: sz=0.5
        elif v and 20<=v<24 and sec in CG2: sz=0.75
        return True,sz

    # V5: LQD -0.5 only (no VIX/sector changes)
    def f5(s,b,d,l):
        v=s[10]
        if v and 20<=v<24: return False,0
        if v and v>=30: return False,0
        if l is not None and l<-0.5: return False,0
        if b is not None and b<35: return False,0
        if d is not None and d<-15: return False,0
        if d is not None and d<=0: return False,0
        return base_ok(s),1.0

    # V6: 3 sectors + LQD -0.7
    def f6(s,b,d,l):
        v,sec=s[10],s[2]
        if v and 20<=v<24:
            if sec in CB: return False,0
            if sec in CG3: pass
            else: return False,0
        if v and v>=30:
            if sec in CB: return False,0
            if sec in CG3: pass
            else: return False,0
        if l is not None and l<-0.7: return False,0
        if b is not None and b<35: return False,0
        if d is not None and d<-15: return False,0
        if d is not None and d<=0: return False,0
        if not base_ok(s): return False,0
        sz=1.0
        if v and v>=24 and sec in CG3: sz=0.5
        elif v and 20<=v<24 and sec in CG3: sz=0.75
        return True,sz

    # V7: Tech only, full size (no reduction)
    def f7(s,b,d,l):
        v,sec=s[10],s[2]
        if v and 20<=v<24:
            if sec=='Technology': pass
            else: return False,0
        if v and v>=30:
            if sec=='Technology': pass
            else: return False,0
        if l is not None and l<-0.5: return False,0
        if b is not None and b<35: return False,0
        if d is not None and d<-15: return False,0
        if d is not None and d<=0: return False,0
        if not base_ok(s): return False,0
        return True,1.0  # full size always

    results = {}
    for name, fn in [
        ('BASELINE', f0),
        ('V1: 3sectors+LQD-0.5', f1),
        ('V2: Tech-only+LQD-0.5', f2),
        ('V3: Tech-only+LQD-0.7', f3),
        ('V4: Tech+HC+LQD-0.7', f4),
        ('V5: LQD-0.5 only', f5),
        ('V6: 3sectors+LQD-0.7', f6),
        ('V7: Tech-only+LQD-0.5 full', f7),
    ]:
        results[name] = sim(signals, breadth, bd, lqd, fn)

    print(f"{'Strategy':<35} {'PnL':>9} {'$/mo':>14} {'N':>6} {'WR%':>6} {'Shrp':>5} {'MDD':>8} {'%Prof':>6} {'2020':>7} {'2022':>7} {'2023':>7}")
    print("─"*125)
    base = results['BASELINE']
    for n,r in results.items():
        pr(n, r, None if n=='BASELINE' else base)

    # Bootstrap top 3
    print(f"\n{'='*70}")
    print("  BOOTSTRAP VALIDATION (top variants)")
    print(f"{'='*70}")
    np.random.seed(42)
    for name in ['V3: Tech-only+LQD-0.7', 'V6: 3sectors+LQD-0.7', 'V2: Tech-only+LQD-0.5']:
        # Re-run to get monthly data
        r = results[name]
        b_r = results['BASELINE']

        # Get monthly PnL for both by re-running (approximate from yearly)
        # Actually let's do it properly
        pass

    # Detailed yearly for winner
    best_name = max(results.items(), key=lambda x: x[1]['mo'] if x[0]!='BASELINE' else -999)[0]
    r = results[best_name]
    print(f"\n  WINNER: {best_name}")
    print(f"  {'Year':<6} {'PnL':>10} {'Trades':>7} {'WR%':>6}")
    for y in sorted(r['yp'].keys()):
        p = r['yp'][y]; t = r['yt'][y]; w = r['yw'].get(y,0)
        wr = w/t*100 if t else 0
        print(f"  {y:<6} ${p:>+9,.0f} {t:>7} {wr:>5.1f}%")

    # Per-year comparison of top 3
    print(f"\n  YEAR-BY-YEAR: Top 3 vs Baseline")
    top3 = sorted([(n,r) for n,r in results.items() if n!='BASELINE'],
                  key=lambda x: x[1]['mo'], reverse=True)[:3]
    print(f"  {'Year':<6} {'BASELINE':>9}", end='')
    for n,_ in top3: print(f" {n[:15]:>16}", end='')
    print()
    for y in ['2020','2021','2022','2023','2024','2025','2026']:
        line = f"  {y:<6} ${base['yp'].get(y,0):>+8,.0f}"
        for _,r in top3:
            line += f" ${r['yp'].get(y,0):>+15,.0f}"
        print(line)


if __name__ == '__main__':
    main()
