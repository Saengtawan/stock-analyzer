"""rotation/lib/journal.py — the rotation (cross-asset / theme forecaster) data layer.

HYBRID STORAGE by design (each data type in the format that fits it):
  1. SQLite  data/rotation.db      — numeric time-series + graded predictions (QUERYABLE: lead-lag,
                                      correlation, hit-rate over time). This module owns it.
  2. JSON    rotation/plans/<date>.json  — the AI's full daily prediction record (flexible; the brain writes it).
  3. Markdown rotation/memory.md    — the AI's accumulating LINKAGE MEMORY + lessons (the brain reads/writes it).

Fully isolated: writes ONLY to data/rotation.db and rotation/*. Reads market data via yfinance.
NEVER touches resonance / overnight / exec_ai / swing databases, plans, or records. This is a
standalone, off-record FORECASTING experiment — its predictions do not enter any live trading journal.

Tables:
  snapshots   — one row per (date, asset): the daily cross-asset numeric snapshot (LONG format, so a
                new asset is just new rows — no schema change).
  predictions — one row per (date, horizon, theme): the AI's forward call + how it graded.

CLI:
  python -m rotation.lib.journal recent
  python -m rotation.lib.journal grade      # grade any ungraded predictions whose target has resolved
"""
from __future__ import annotations
import os, sqlite3, json, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                  "data", "rotation.db")


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS snapshots (
        date TEXT, asset TEXT, class TEXT, close REAL,
        ret_1d REAL, ret_5d REAL, ret_20d REAL, rvol REAL, extra TEXT,
        PRIMARY KEY (date, asset))""")
    c.execute("""CREATE TABLE IF NOT EXISTS predictions (
        date TEXT,            -- the day the call was MADE (post-close)
        horizon TEXT,         -- 'tomorrow' | 'week' | 'regime'
        theme TEXT,           -- e.g. 'AI/semis', 'crypto', 'space/defense', or 'REGIME'
        lean TEXT,            -- 'up' | 'down' | 'live' | 'risk-on' | 'risk-off' ...
        names TEXT,           -- comma list of tickers the theme would express through (optional)
        confidence REAL,      -- 0..1
        falsifiable TEXT,     -- the pre-registered test that would prove the call wrong
        reason TEXT,
        graded INTEGER DEFAULT 0,
        outcome TEXT,         -- filled by grade(): what actually happened
        correct INTEGER,      -- 1/0/NULL
        PRIMARY KEY (date, horizon, theme))""")
    return c


def log_snapshot(date, asset, cls, close, ret_1d=None, ret_5d=None, ret_20d=None, rvol=None, extra=None):
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO snapshots (date,asset,class,close,ret_1d,ret_5d,ret_20d,rvol,extra)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
              (date, asset, cls, close, ret_1d, ret_5d, ret_20d, rvol,
               json.dumps(extra) if extra is not None else None))
    c.commit(); c.close()


def log_prediction(date, horizon, theme, lean, names=None, confidence=None, falsifiable=None, reason=None):
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO predictions
                 (date,horizon,theme,lean,names,confidence,falsifiable,reason)
                 VALUES (?,?,?,?,?,?,?,?)""",
              (date, horizon, theme, lean, names, confidence, falsifiable, reason))
    c.commit(); c.close()
    print(f"[rotation] logged {horizon}/{theme} lean={lean} conf={confidence}")


def grade_prediction(date, horizon, theme, outcome, correct):
    c = _conn()
    c.execute("""UPDATE predictions SET outcome=?, correct=?, graded=1
                 WHERE date=? AND horizon=? AND theme=?""", (outcome, int(correct), date, horizon, theme))
    c.commit(); c.close()


def snapshot_asof(date):
    """All snapshot rows for a date (the cross-asset picture that day) — for the brain to read."""
    c = _conn()
    rows = [dict(zip(("asset", "class", "close", "ret_1d", "ret_5d", "ret_20d", "rvol"), r))
            for r in c.execute("""SELECT asset,class,close,ret_1d,ret_5d,ret_20d,rvol FROM snapshots
                                  WHERE date=? ORDER BY class,asset""", (date,))]
    c.close(); return rows


def ungraded():
    c = _conn()
    rows = [dict(zip(("date", "horizon", "theme", "lean", "names", "falsifiable"), r))
            for r in c.execute("""SELECT date,horizon,theme,lean,names,falsifiable FROM predictions
                                  WHERE graded=0 ORDER BY date""")]
    c.close(); return rows


def recent(n=40):
    c = _conn()
    print("== recent predictions ==")
    for r in c.execute("""SELECT date,horizon,theme,lean,confidence,graded,correct FROM predictions
                          ORDER BY date DESC LIMIT ?""", (n,)):
        print(r)
    print("== hit rate by horizon (graded) ==")
    for r in c.execute("""SELECT horizon, COUNT(*) n, SUM(correct) hits FROM predictions
                          WHERE graded=1 GROUP BY horizon"""):
        h, nn, hits = r
        print(f"  {h}: {hits or 0}/{nn} = {100*(hits or 0)/nn:.0f}%")
    c.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recent"
    if cmd == "grade":
        # grading is AI-driven (learn.md decides if a theme went live) — this CLI just lists what's pending
        print("Ungraded predictions (grade via rotation/run/learn.sh -> brain/learn.md):")
        for r in ungraded():
            print(" ", r)
    else:
        recent()
