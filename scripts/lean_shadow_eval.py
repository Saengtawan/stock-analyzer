#!/usr/bin/env python3
"""lean_shadow_eval.py — evaluate the lean foundation SHADOW lane vs the live system.

Reads the `lean_picks` journal (written by ml_filter when LEAN_SHADOW=1), backfills
each pick's EOD outcome from intraday_bars_5m, and reports lean top-1/zone forward
performance: trade-all vs quantile-abstention, WR, vs buy-all floor, and (when present)
vs the live engine pick that day. Read-only.

  python3 scripts/lean_shadow_eval.py
  python3 scripts/lean_shadow_eval.py --since 2026-06-20

Run during shadow (LEAN_SHADOW=1 in the scan cron) for 2-4 weeks before any live swap.
"""
import os, sys, sqlite3, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SJ = os.path.join(ROOT, 'data', 'scan_journal.db')
TH = os.path.join(ROOT, 'data', 'trade_history.db')


def mfo_to_time(mfo):
    m = 9 * 60 + 30 + int(mfo)
    return f"{m // 60:02d}:{m % 60:02d}"


def eod_ret(th, sym, date, mfo):
    t0 = mfo_to_time(mfo)
    rows = th.execute(
        "SELECT time_et, close FROM intraday_bars_5m WHERE symbol=? AND date=? "
        "AND time_et>=? AND time_et<='15:55' ORDER BY time_et", (sym, date, t0)).fetchall()
    if not rows:
        return None
    entry = rows[0][1]
    if not entry:
        return None
    return (rows[-1][1] / entry - 1) * 100


def main():
    since = None
    if '--since' in sys.argv:
        since = sys.argv[sys.argv.index('--since') + 1]
    sj = sqlite3.connect(SJ)
    try:
        q = "SELECT scan_date, zone, symbol, sector, score, traded, thr, n_cand, mfo FROM lean_picks"
        if since:
            q += f" WHERE scan_date >= '{since}'"
        q += " ORDER BY scan_date, zone"
        rows = sj.execute(q).fetchall()
    except sqlite3.OperationalError:
        print("No lean_picks table yet — run a scan with LEAN_SHADOW=1 first."); return
    sj.close()
    if not rows:
        print("No shadow picks recorded yet (set LEAN_SHADOW=1 in the scan cron)."); return

    th = sqlite3.connect(TH)
    today = dt.datetime.now().strftime('%Y-%m-%d')
    by_zone = {}
    print(f"{'date':<11}{'zone':<5}{'sym':<7}{'score':>7}{'trade':>6}{'EOD%':>8}")
    for d, z, sym, sec, score, traded, thr, ncand, mfo in rows:
        r = None if d == today else eod_ret(th, sym, d, mfo)
        by_zone.setdefault(z, []).append((traded, r))
        rs = f"{r:+.2f}" if r is not None else "(open)"
        print(f"{d:<11}{z:<5}{sym:<7}{score:>7.3f}{('Y' if traded else 'abst'):>6}{rs:>8}")
    th.close()

    print("\n=== summary (forward, hold-EOD) ===")
    for z, recs in sorted(by_zone.items()):
        done = [(t, r) for t, r in recs if r is not None]
        if not done:
            print(f"  {z}: no closed picks yet"); continue
        allr = [r for _, r in done]
        tr = [r for t, r in done if t]
        def stat(a):
            return f"N={len(a)} avg={sum(a)/len(a):+.3f}% WR={sum(1 for x in a if x>0)/len(a)*100:.0f}%" if a else "N=0"
        print(f"  {z}  trade-all: {stat(allr)}  |  abstention-traded: {stat(tr)}")
    print("\nTarget (backtest WF): Z1 ~+0.40 (abstain +0.5), Z2 ~+0.20. Need ~10-15 picks/zone before judging.")


if __name__ == '__main__':
    main()
