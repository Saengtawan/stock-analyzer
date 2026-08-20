"""overnight/lib/journal.py — the overnight-catalyst experiment's OWN journal.

Fully isolated: writes only to data/overnight.db and reads market data via yfinance (consolidated,
free). It NEVER touches resonance/exec_ai/swing databases, plans, or forward records. The scoreboard
is whether an overnight-held after-hours catalyst beats the naive "buy at next open + it was already
in the gap" — i.e. did the AH gap HOLD to the next regular-hours open.

CLI:
  python -m overnight.lib.journal recent
  python -m overnight.lib.journal grade   # grade any pending picks whose next session has printed
"""
from __future__ import annotations
import os
import sqlite3
import sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                  "data", "overnight.db")


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS picks (
        date TEXT, sym TEXT, play TEXT, odds TEXT, reason TEXT,
        rth_close REAL, ah_mark REAL, ah_pct REAL,
        next_open REAL, next_open_pct REAL, held_pct REAL, graded INTEGER DEFAULT 0,
        PRIMARY KEY (date, sym))""")
    return c


def log(date, sym, play, odds, reason, rth_close=None, ah_mark=None):
    """Record one overnight pick, made on `date` (the after-hours session)."""
    ah_pct = round((ah_mark / rth_close - 1) * 100, 2) if (rth_close and ah_mark) else None
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO picks
        (date, sym, play, odds, reason, rth_close, ah_mark, ah_pct)
        VALUES (?,?,?,?,?,?,?,?)""",
              (date, sym, play, odds, reason, rth_close, ah_mark, ah_pct))
    c.commit(); c.close()
    print(f"[overnight] logged {sym} {date} play={play} ah={ah_pct}%")


def grade(verbose=True):
    """For any ungraded pick, if the NEXT trading session's open has printed, grade whether the
    AH gap held to that open. `held_pct` = next_open vs the AH mark (did holding overnight pay?);
    `next_open_pct` = next_open vs the pre-print RTH close (the full overnight move)."""
    import datetime, zoneinfo
    import yfinance as yf
    ET = zoneinfo.ZoneInfo("America/New_York")
    c = _conn()
    rows = c.execute("SELECT date, sym, rth_close, ah_mark FROM picks WHERE graded=0").fetchall()
    graded = 0
    for date, sym, rth_close, ah_mark in rows:
        d = datetime.date.fromisoformat(date)
        # next trading day (skip weekend)
        nd = d + datetime.timedelta(days=1)
        while nd.weekday() >= 5:
            nd += datetime.timedelta(days=1)
        df = yf.download(sym, start=nd.isoformat(),
                         end=(nd + datetime.timedelta(days=1)).isoformat(),
                         interval="1m", prepost=False, progress=False)
        if df is None or df.empty:
            continue
        if hasattr(df.columns, "levels"):
            df.columns = [x[0] for x in df.columns]
        df = df.tz_convert(ET)
        r = df[df.index.date == nd]
        if not len(r):
            continue
        nopen = float(r["Open"].iloc[0])
        nopen_pct = round((nopen / rth_close - 1) * 100, 2) if rth_close else None
        held = round((nopen / ah_mark - 1) * 100, 2) if ah_mark else None
        c.execute("""UPDATE picks SET next_open=?, next_open_pct=?, held_pct=?, graded=1
                     WHERE date=? AND sym=?""", (nopen, nopen_pct, held, date, sym))
        graded += 1
        if verbose:
            print(f"  {sym} {date}: AH {ah_mark} -> next open {nopen:.2f} | "
                  f"overnight {nopen_pct:+.2f}% (vs pre-print close) | held vs AH mark {held:+.2f}%")
    c.commit(); c.close()
    if verbose:
        print(f"[overnight] graded {graded} pick(s)")
    return graded


def recent(n=20):
    c = _conn()
    for row in c.execute("SELECT date,sym,play,ah_pct,next_open_pct,held_pct,graded FROM picks "
                         "ORDER BY date DESC LIMIT ?", (n,)):
        print(row)
    c.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recent"
    if cmd == "grade":
        grade()
    else:
        recent()
