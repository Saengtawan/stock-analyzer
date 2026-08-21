"""overnight/lib/journal.py — the overnight-catalyst experiment's OWN journal.

Fully isolated: writes only to data/overnight.db and reads market data via yfinance (consolidated,
free). It NEVER touches resonance/exec_ai/swing databases, plans, or forward records. The play, and
the scoreboard: BUY before the close (pre-print) → SELL at the END of the after-hours session the
same evening (~19:59 ET) — capture the AH pop, do NOT hold it into the next open's give-back. The
result is end-of-AH vs the pre-close entry; next-open is kept only as a reference comparison.

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
    """Grade the play the user actually runs: BUY before the close (rth_close) → SELL at the END of
    the after-hours session the SAME evening (the last prepost print, ~19:59 ET). The result is
    `ah_pct` = end-of-AH mark vs the pre-close entry. This does NOT wait for the next open — the
    exit is the AH pop itself (selling into it, not holding it into the next open's give-back).

    For reference only (non-blocking), if the NEXT session's open has printed it also fills
    `next_open` / `held_pct` so we can compare "sold end-of-AH" vs "held to the open"."""
    import datetime, zoneinfo
    import yfinance as yf
    ET = zoneinfo.ZoneInfo("America/New_York")
    c = _conn()
    rows = c.execute("SELECT date, sym, rth_close, ah_mark FROM picks WHERE graded=0").fetchall()
    graded = 0
    for date, sym, rth_close, ah_mark in rows:
        d = datetime.date.fromisoformat(date)
        # END-OF-AH mark on the pick's OWN date: last prepost 1-min bar in the 16:00-20:00 ET window.
        df = yf.download(sym, start=date, end=(d + datetime.timedelta(days=1)).isoformat(),
                         interval="1m", prepost=True, progress=False, auto_adjust=False)
        if df is None or df.empty:
            continue
        if hasattr(df.columns, "levels"):
            df.columns = [x[0] for x in df.columns]
        df = df.tz_convert(ET)
        ah = df[(df.index.date == d) & (df.index.strftime("%H:%M") >= "16:00")]
        if not len(ah):
            continue
        end_ah = float(ah["Close"].iloc[-1])          # the actual end-of-AH sell mark
        end_ah_t = ah.index[-1].strftime("%H:%M")
        ah_pct = round((end_ah / rth_close - 1) * 100, 2) if rth_close else None

        # reference: next-session open, if it has printed (does NOT block grading)
        nd = d + datetime.timedelta(days=1)
        while nd.weekday() >= 5:
            nd += datetime.timedelta(days=1)
        nopen = nopen_pct = held = None
        try:
            ndf = yf.download(sym, start=nd.isoformat(),
                              end=(nd + datetime.timedelta(days=1)).isoformat(),
                              interval="1m", prepost=False, progress=False, auto_adjust=False)
            if ndf is not None and not ndf.empty:
                if hasattr(ndf.columns, "levels"):
                    ndf.columns = [x[0] for x in ndf.columns]
                ndf = ndf.tz_convert(ET)
                r = ndf[ndf.index.date == nd]
                if len(r):
                    nopen = float(r["Open"].iloc[0])
                    nopen_pct = round((nopen / rth_close - 1) * 100, 2) if rth_close else None
                    held = round((nopen / end_ah - 1) * 100, 2)   # end-AH sell vs holding to open
        except Exception:
            pass

        c.execute("""UPDATE picks SET ah_mark=?, ah_pct=?, next_open=?, next_open_pct=?,
                     held_pct=?, graded=1 WHERE date=? AND sym=?""",
                  (end_ah, ah_pct, nopen, nopen_pct, held, date, sym))
        graded += 1
        if verbose:
            ref = "" if nopen is None else (f" | next open {nopen:.2f} ({nopen_pct:+.2f}% vs entry; "
                                            f"selling end-AH beat holding-to-open by {(ah_pct - nopen_pct):+.2f}pp)")
            print(f"  {sym} {date}: BUY {rth_close} -> SELL end-AH {end_ah:.2f} @{end_ah_t} = "
                  f"**{ah_pct:+.2f}%**{ref}")
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
