"""swing/lib/grade.py — MECHANICAL outcome update for open swing picks (the swing analog of
resonance's journal grader). For each `open` pick in data/swing.db it walks the daily bars from the
pick date forward and resolves it:

  - target hit (a day's HIGH >= target_px)  -> WIN,  exit='target'
  - stop hit   (a day's LOW  <= stop_px)    -> LOSS, exit='stop'
  - if both breached on the SAME day        -> conservatively count the STOP (can't see intraday order)
  - neither, and held >= HORIZON_DAYS (~1mo) -> time-exit at last close, exit='time'
  - else                                     -> still open; print a mark-to-market (no DB write)

Modeling assumption (v0): the pick is treated as FILLED at entry_px from its decision date. Real
fills the user tracks live; this gives an honest, mechanical forward record to reflect on.

Read-only on trade_history.db (mode=ro). Writes ONLY data/swing.db. Nothing in resonance/.
Run:  python -m swing.lib.grade [ASOF=today]
"""
import os
import sys
import sqlite3
import datetime

from swing.lib import journal

PRICE_DB = "data/trade_history.db"
HORIZON_DAYS = int(os.environ.get("SWING_HORIZON_DAYS", 21))  # ~1 trading month = time-exit


def _bars(sym, start, end):
    c = sqlite3.connect(f"file:{PRICE_DB}?mode=ro", uri=True)
    try:
        return c.execute(
            """SELECT date, high, low, close FROM stock_daily_ohlc
               WHERE symbol=? AND date>=? AND date<=? ORDER BY date""",
            (sym.upper(), start, end)).fetchall()
    finally:
        c.close()


def grade(asof=None, verbose=True):
    asof = asof or datetime.date.today().isoformat()
    c = sqlite3.connect("data/swing.db")
    open_rows = c.execute(
        "SELECT date, sym, entry_px, stop_px, target_px FROM record WHERE status='open'").fetchall()
    c.close()

    resolved, still_open = [], []
    for pdate, sym, entry, stop, target in open_rows:
        if not entry:
            continue
        bars = [b for b in _bars(sym, pdate, asof) if b[0] > pdate]  # sessions AFTER the decision day
        exit_kind = res_px = res_date = None
        for d, hi, lo, cl in bars:
            hit_stop = stop is not None and lo is not None and lo <= stop
            hit_tgt = target is not None and hi is not None and hi >= target
            if hit_stop:                       # same-day tie -> stop wins (conservative)
                exit_kind, res_px, res_date = "stop", stop, d
                break
            if hit_tgt:
                exit_kind, res_px, res_date = "target", target, d
                break
        if exit_kind is None and len(bars) >= HORIZON_DAYS and bars:
            exit_kind, res_px, res_date = "time", bars[-1][3], bars[-1][0]

        if exit_kind:
            pct = journal.close_pick(pdate, sym, res_px, res_date, notes=f"exit={exit_kind}")
            resolved.append((sym, exit_kind, pct))
        else:
            last = bars[-1] if bars else None
            mark = round((last[3] / entry - 1) * 100, 2) if last else None
            still_open.append((sym, mark, len(bars)))

    if verbose:
        print(f"[swing grade] asof={asof}  resolved={len(resolved)}  still_open={len(still_open)}")
        for sym, kind, pct in resolved:
            tag = {"target": "🟢WIN", "stop": "🔴LOSS", "time": "🟡TIME"}[kind]
            print(f"  {tag} {sym:6} {kind:7} {pct:+.2f}%")
        for sym, mark, held in still_open:
            print(f"  ⏳OPEN {sym:6} mark {mark:+.2f}% (held {held}d)" if mark is not None
                  else f"  ⏳OPEN {sym:6} (no bars yet)")
    return {"resolved": resolved, "open": still_open}


if __name__ == "__main__":
    grade(sys.argv[1] if len(sys.argv) > 1 else None)
