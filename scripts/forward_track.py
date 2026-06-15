#!/usr/bin/env python3
"""Forward-tracking scorecard: live exit verdicts vs backtest expectation.

Reads exit_ml_journal.db (exit_checks = every exit_check/exit_loop verdict logged),
reconstructs each pick's realized outcome two ways:
  - FOLLOWED : exit at the first EXIT verdict's cur_pnl (else hold to EOD)
  - HOLD-EOD : entry -> EOD close (the do-nothing baseline)
classifies the lane (riser_picks table = riser, else H12-A/v18), and prints WR/avg
per lane next to the backtest benchmark, flagging drift.

Usage:
  python3 scripts/forward_track.py                # all logged picks
  python3 scripts/forward_track.py --days 30      # last 30 days
  python3 scripts/forward_track.py --live-only    # only --live checks (exclude shadow)
Backtest benchmarks (holdout 2025-05+): see BENCH below.
"""
import argparse, sqlite3, sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
EXIT_JOURNAL = str(ROOT / "data/exit_ml_journal.db")
SCAN_JOURNAL = str(ROOT / "data/scan_journal.db")
TRADE_DB = str(ROOT / "data/trade_history.db")

# Backtest holdout expectations (2025-05+), for drift comparison.
BENCH = {
    "H12-A/v18": {"wr": 63.4, "avg": 0.487, "note": "Sharpe 3.89, worst -3.0"},
    "riser":     {"wr": 54.5, "avg": 0.467, "note": "ret/DD 1.97 (EOD metric)"},
}
DRIFT_WR = 8.0      # pp gap that flags investigation
DRIFT_AVG = 0.30    # %/pick gap that flags


def tomin(t):
    if " " in t: t = t.split(" ")[1]
    return int(t[:2]) * 60 + int(t[3:5])


def riser_dates(symbol):
    try:
        con = sqlite3.connect(SCAN_JOURNAL)
        rows = con.execute("SELECT scan_date FROM riser_picks WHERE symbol=?", (symbol,)).fetchall()
        con.close()
        return {r[0] for r in rows}
    except sqlite3.OperationalError:
        return set()


def eod_close(symbol, date):
    con = sqlite3.connect(TRADE_DB)
    r = con.execute(
        "SELECT close FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et<='16:00' "
        "ORDER BY time_et DESC LIMIT 1", (symbol, date)).fetchone()
    con.close()
    return r[0] if r else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--live-only", action="store_true")
    ap.add_argument("--max-lag-days", type=int, default=2,
                    help="FORWARD filter: only count picks whose check was RUN within N days of the "
                         "trade date (a genuine same-day forward check, not a later replay). "
                         "Set high (e.g. 9999) to include replays too.")
    ap.add_argument("--max-move", type=float, default=30.0,
                    help="skip picks with |hold return| > this %% (data errors / splits)")
    args = ap.parse_args()

    con = sqlite3.connect(EXIT_JOURNAL)
    q = ("SELECT symbol, date, entry_price, entry_time, check_ts, cur_pnl_pct, verdict, shadow_mode "
         "FROM exit_checks WHERE date IS NOT NULL")
    if args.live_only:
        q += " AND shadow_mode=0"
    if args.days:
        q += f" AND date >= date('now','-{args.days} days')"
    rows = con.execute(q + " ORDER BY symbol, date, check_ts").fetchall()
    con.close()
    if not rows:
        print("no logged exit checks yet — run scan_track / exit_loop first, then re-run this.")
        return

    # group by (symbol, date)
    picks = defaultdict(list)
    for r in rows:
        picks[(r[0], r[1])].append(r)

    from datetime import date as _date
    def _d(s): return _date.fromisoformat(s[:10])

    lanes = defaultdict(list)  # lane -> list of (followed_ret, hold_ret, exited?)
    detail = []
    skipped_replay = skipped_outlier = 0
    for (sym, date), recs in picks.items():
        recs.sort(key=lambda x: x[4])
        entry = recs[0][2]
        if not entry or entry <= 0:
            continue
        # FORWARD filter: the check must have been RUN near the trade date (same-day, not replay)
        lag = abs((_d(recs[0][4]) - _d(date)).days)
        if lag > args.max_lag_days:
            skipped_replay += 1
            continue
        lane = "riser" if date in riser_dates(sym) else "H12-A/v18"
        # followed: first EXIT verdict's cur_pnl
        exit_rec = next((r for r in recs if r[6] and "EXIT" in r[6].upper()), None)
        # hold-EOD: from EOD close
        eod = eod_close(sym, date)
        hold_ret = (eod / entry - 1) * 100 if eod else None
        if exit_rec is not None and exit_rec[5] is not None:
            followed = exit_rec[5]; exited = True
        else:
            followed = hold_ret; exited = False
        if hold_ret is None:
            continue
        if abs(hold_ret) > args.max_move:
            skipped_outlier += 1
            continue
        lanes[lane].append((followed, hold_ret, exited))
        detail.append((date, sym, lane, followed, hold_ret, exited, recs[-1][7]))

    print(f"\n{'='*72}\nFORWARD TRACKING — live exit verdicts vs backtest  ({len(detail)} forward picks)\n{'='*72}")
    if skipped_replay or skipped_outlier:
        print(f"  (skipped {skipped_replay} replay/non-same-day checks, {skipped_outlier} outliers |move|>{args.max_move}%)")
    if not detail:
        print("\n  No genuine forward picks yet (all logged checks were session replays).")
        print("  → As scan_track/riser_capture run live on real trading days, this fills in.")
        print("  → Re-run weekly: python3 scripts/forward_track.py")
        return
    for lane, items in sorted(lanes.items()):
        f = [x[0] for x in items]; h = [x[1] for x in items]; nex = sum(1 for x in items if x[2])
        n = len(f)
        fwr = sum(1 for x in f if x > 0) / n * 100; favg = sum(f) / n
        hwr = sum(1 for x in h if x > 0) / n * 100; havg = sum(h) / n
        b = BENCH.get(lane, {})
        print(f"\n[{lane}]  N={n}  (exits fired: {nex})")
        print(f"  FOLLOWED exit : WR {fwr:4.1f}%  avg {favg:+.3f}%  tot {sum(f):+.1f}")
        print(f"  HOLD-EOD ref  : WR {hwr:4.1f}%  avg {havg:+.3f}%  tot {sum(h):+.1f}   (exit edge {favg-havg:+.3f}%/pick)")
        if b:
            dwr = fwr - b["wr"]; davg = favg - b["avg"]
            flag = "  ⚠️ DRIFT" if (abs(dwr) > DRIFT_WR or abs(davg) > DRIFT_AVG) else "  ✓ in-line"
            print(f"  BACKTEST exp  : WR {b['wr']:4.1f}%  avg {b['avg']:+.3f}%   ({b['note']})")
            print(f"  vs backtest   : ΔWR {dwr:+.1f}pp  Δavg {davg:+.3f}%{flag}")
        if n < 10:
            print(f"  → only {n} picks — need ~10-15 for a trustworthy read")

    print(f"\n{'-'*72}\nPER-PICK ({len(detail)} rows):")
    for d, sym, lane, fwd, hld, ex, mode in sorted(detail):
        tag = "EXIT" if ex else "held"
        m = "LIVE" if mode == 0 else "shdw"
        print(f"  {d} {sym:6} {lane:10} {tag:4} followed {fwd:+6.2f}%  hold {hld:+6.2f}%  [{m}]")
    print()


if __name__ == "__main__":
    main()
