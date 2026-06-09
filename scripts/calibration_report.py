#!/usr/bin/env python3
"""Forward calibration report — live scan_journal vs backtest expectation.

Closes the parity loop: proves backtest numbers match live actuals (the P6-11
lesson — old WF said 66-88% while live was 41.5%; calibration catches that gap).

Usage:
  python3 scripts/calibration_report.py                 # H12-A era (>=2026-06-08)
  python3 scripts/calibration_report.py --since 2026-06-04   # custom start
  python3 scripts/calibration_report.py --all           # all journal picks

Per-zone live WR/avg from scan_journal (joined with outcomes) vs the H12-A
backtest baseline. Flags any |live - backtest| gap > GAP_FLAG_PP.
"""
import sqlite3, argparse, sys
from datetime import datetime

DB = "data/scan_journal.db"
H12A_LIVE_START = "2026-06-08"   # first H12-A trading day
GAP_FLAG_PP = 10.0               # flag if live WR differs from backtest by > this

# H12-A backtest expectation (honest WF holdout — the number-to-match).
# These are what live SHOULD deliver if parity holds. avg in %.
BACKTEST = {
    "Z1": {"wr": 57, "avg": 0.23},
    "Z2": {"wr": 71, "avg": 0.75},
    "Z3": {"wr": 59, "avg": 0.58},
    "Z4": {"wr": 66, "avg": 0.66},
    "ALL": {"wr": 59, "avg": 0.40},   # combined honest forward
}

def zone_of_scan_ts(scan_ts: str) -> str:
    """Derive zone from ET scan time (scan_ts is ET 'YYYY-MM-DD HH:MM:SS')."""
    try:
        hh, mm = int(scan_ts[11:13]), int(scan_ts[14:16])
    except Exception:
        return "?"
    mfo = (hh - 9) * 60 + (mm - 30)
    if 0 <= mfo <= 9: return "Z1"
    if 10 <= mfo <= 29: return "Z2"
    if 30 <= mfo <= 44: return "Z3"
    if 45 <= mfo <= 75: return "Z4"
    return "?"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=H12A_LIVE_START)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    since = None if args.all else args.since

    con = sqlite3.connect(DB)
    q = ("SELECT p.scan_ts, p.symbol, p.strategy, p.ml_prob, p.expected_wr, "
         "o.pnl_pct, o.outcome_label "
         "FROM scan_picks p LEFT JOIN pick_outcomes o ON o.pick_id = p.id "
         "WHERE p.strategy='ml_filter'")
    if since:
        q += f" AND p.scan_ts >= '{since}'"
    rows = con.execute(q + " ORDER BY p.scan_ts").fetchall()
    con.close()

    label = "ALL journal" if args.all else f"since {since}"
    print(f"=== Calibration report — ml_filter live vs backtest ({label}) ===")
    print(f"    flagging gaps > {GAP_FLAG_PP:.0f}pp WR\n")

    with_outcome = [r for r in rows if r[5] is not None]
    pending = len(rows) - len(with_outcome)
    if not with_outcome:
        print(f"  picks: {len(rows)} | with outcome: 0 | pending: {pending}")
        print("  → no settled picks yet in this window. H12-A live started "
              f"{H12A_LIVE_START}; report populates as outcomes land.")
        return

    # bucket per zone
    by = {}
    for scan_ts, sym, strat, mlp, ewr, pnl, lbl in with_outcome:
        z = zone_of_scan_ts(scan_ts)
        by.setdefault(z, []).append(pnl)
        by.setdefault("ALL", []).append(pnl)

    print(f"  picks: {len(rows)} | settled: {len(with_outcome)} | pending: {pending}\n")
    print(f"  {'zone':<6}{'N':<5}{'live WR':<10}{'live avg':<11}"
          f"{'bt WR':<8}{'bt avg':<9}{'WR gap':<9}{'flag'}")
    for z in ["Z1", "Z2", "Z3", "Z4", "ALL"]:
        v = by.get(z)
        if not v:
            continue
        wr = sum(1 for x in v if x > 0) / len(v) * 100
        avg = sum(v) / len(v)
        bt = BACKTEST.get(z, {})
        gap = wr - bt.get("wr", 0)
        flag = "⚠️ INVESTIGATE" if abs(gap) > GAP_FLAG_PP else "ok"
        print(f"  {z:<6}{len(v):<5}{wr:<9.0f}%{avg:<+10.2f}%"
              f"{bt.get('wr',0):<7.0f}%{bt.get('avg',0):<+8.2f}%{gap:<+8.0f}pp{flag}")
    print(f"\n  baseline = H12-A WF holdout. Gap > {GAP_FLAG_PP:.0f}pp = parity/regime"
          " issue → investigate before trusting further backtests.")

if __name__ == "__main__":
    main()
