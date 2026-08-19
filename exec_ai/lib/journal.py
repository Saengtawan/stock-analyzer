"""exec_ai/lib/journal.py — execution forward record. SEPARATE DB (data/exec_ai.db). Logs the
execution DECISION (entry limits + exit strategy) per resonance pick, then the OUTCOME (did the
judged limit fill / at what price, did the chosen exit beat a naive hold-to-EOD). The forward record
is the only thing that tells us the execution layer adds edge over "market-buy at open + hold EOD".

DELETE-before-insert per (date, sym) so re-runs don't pollute the record.
CLI: python -m exec_ai.lib.journal recent [N]
"""
import os
import sys
import sqlite3
import datetime

DB = "data/exec_ai.db"

DDL = """
CREATE TABLE IF NOT EXISTS record (
    date          TEXT NOT NULL,     -- decision date
    sym           TEXT NOT NULL,
    klass         TEXT,              -- remodel | attention | other
    entry_judged  REAL,             -- exec_ai's judged limit
    entry_flat    REAL,             -- the flat x1.015 baseline
    stop_px       REAL,
    exit_strategy TEXT,             -- hold | take_profit@X | trail X%@+Y% | ...
    reason        TEXT,
    -- outcomes (filled by the learn/grade pass) --
    open_px       REAL,
    filled_judged INTEGER,          -- 1/0 did the judged limit fill in RTH
    filled_flat   INTEGER,
    peak_pct      REAL,             -- intraday peak vs open
    close_pct     REAL,             -- open->15:55
    exit_pct      REAL,             -- what the chosen exit actually captured
    hold_eod_pct  REAL,             -- naive hold-EOD benchmark
    edge_vs_hold  REAL,             -- exit_pct - hold_eod_pct
    notes         TEXT,
    created_at    TEXT,
    PRIMARY KEY (date, sym)
);
"""


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("PRAGMA busy_timeout=30000")
    c.executescript(DDL)
    return c


def log(date, sym, klass="", entry_judged=None, entry_flat=None, stop_px=None,
        exit_strategy="", reason=""):
    c = _conn()
    c.execute("DELETE FROM record WHERE date=? AND sym=?", (date, sym.upper()))
    c.execute(
        """INSERT INTO record (date,sym,klass,entry_judged,entry_flat,stop_px,exit_strategy,reason,created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (date, sym.upper(), klass, entry_judged, entry_flat, stop_px, exit_strategy, reason,
         datetime.datetime.now().isoformat(timespec="seconds")),
    )
    c.commit()
    c.close()


def grade(date, sym, **kw):
    """Fill outcome fields after the close. kw any of: open_px, filled_judged, filled_flat,
    peak_pct, close_pct, exit_pct, hold_eod_pct, notes. edge_vs_hold auto-computed."""
    c = _conn()
    if kw.get("exit_pct") is not None and kw.get("hold_eod_pct") is not None:
        kw["edge_vs_hold"] = round(kw["exit_pct"] - kw["hold_eod_pct"], 2)
    cols = ", ".join(f"{k}=?" for k in kw)
    c.execute(f"UPDATE record SET {cols} WHERE date=? AND sym=?",
              (*kw.values(), date, sym.upper()))
    c.commit()
    c.close()


def recent(n=30):
    c = _conn()
    rows = c.execute(
        """SELECT date,sym,klass,exit_strategy,entry_judged,entry_flat,exit_pct,hold_eod_pct,edge_vs_hold
           FROM record ORDER BY date DESC, sym LIMIT ?""", (n,)).fetchall()
    c.close()
    return rows


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "recent":
        for r in recent(int(sys.argv[2]) if len(sys.argv) > 2 else 30):
            print(r)
    else:
        print("usage: python -m exec_ai.lib.journal recent [N]")
