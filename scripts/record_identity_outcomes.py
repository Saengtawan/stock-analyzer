"""record_identity_outcomes.py — daily forward update of the per-stock identity track record.

Keeps data/stock_track_record.db current so the identity gate learns from recent days instead of
freezing at the backtest seed. For the target day, every gain>0.5 candidate at 09:35 (the Z1/riser
universe) gets its LIVE-FAITHFUL outcome recorded: entry = 09:35 close ('buy at display'),
exit = 15:55 close (eod_flatten) — the convention identity is significant on (p=0.010).

Runs after the close once intraday_bars_5m has the 15:55 bar. Idempotent (record_outcome keys on
(symbol,date)), so re-runs are safe. No args = the most recent complete trading day in the table.

Usage: record_identity_outcomes.py [YYYY-MM-DD]
"""
import sqlite3, sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.scan import stock_track_record as STR

TH = ROOT / 'data' / 'trade_history.db'


def main():
    th = sqlite3.connect(str(TH))
    if len(sys.argv) > 1:
        day = sys.argv[1]
    else:
        # most recent date that has a 15:55 bar (= a complete trading day)
        row = th.execute("SELECT MAX(date) FROM intraday_bars_5m WHERE time_et='15:55'").fetchone()
        day = row[0] if row else None
    if not day:
        print("no complete day found"); return
    rows = th.execute("""SELECT symbol,time_et,open,close FROM intraday_bars_5m
        WHERE date=? AND time_et IN ('09:30','09:35','15:55')""", (day,)).fetchall()
    th.close()
    by = defaultdict(dict)
    for s, t, o, c in rows:
        by[s][t] = (o, c)
    cand = added = 0
    for s, v in by.items():
        if '09:30' not in v or '09:35' not in v or '15:55' not in v:
            continue
        dop, entry, exit = v['09:30'][0], v['09:35'][1], v['15:55'][1]
        if not (dop and entry and exit and dop > 0 and entry > 0):
            continue
        if (entry / dop - 1) * 100 <= 0.5:          # gain>0.5 candidate criterion
            continue
        cand += 1
        ret = (exit / entry - 1) * 100
        if abs(ret) > 40:                            # split-artifact guard
            continue
        STR.record_outcome(s, day, ret, source='live_5m')
        added += 1
    print(f"[identity] {day}: {cand} gain>0.5 candidates, recorded {added} outcomes")


if __name__ == "__main__":
    main()
