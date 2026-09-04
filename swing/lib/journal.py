"""swing/lib/journal.py — forward record for the swing sibling. SEPARATE DB (data/swing.db) — never
touches resonance.db. The forward record (how picks resolve over the following weeks) is the only
thing that can tell us this system has an edge; backtest/screen is optimistically biased.

DELETE-before-insert per (date, sym) so re-runs never pollute the record.
CLI: python -m swing.lib.journal recent [N]
"""
import os
import sys
import sqlite3
import datetime

DB = "data/swing.db"

DDL = """
CREATE TABLE IF NOT EXISTS record (
    date        TEXT NOT NULL,      -- decision date
    sym         TEXT NOT NULL,
    thesis      TEXT,
    catalyst    TEXT,
    entry_px    REAL,
    stop_px     REAL,
    target_px   REAL,
    conviction  TEXT,
    horizon     TEXT DEFAULT '1w-1m',
    status      TEXT DEFAULT 'open',   -- open | closed
    close_px    REAL,
    close_date  TEXT,
    result_pct  REAL,
    notes       TEXT,
    created_at  TEXT,
    PRIMARY KEY (date, sym)
);
"""


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("PRAGMA busy_timeout=30000")
    c.executescript(DDL)
    return c


def log_pick(date, sym, thesis="", catalyst="", entry_px=None, stop_px=None,
             target_px=None, conviction="", notes=""):
    c = _conn()
    c.execute("DELETE FROM record WHERE date=? AND sym=?", (date, sym.upper()))
    c.execute(
        """INSERT INTO record (date,sym,thesis,catalyst,entry_px,stop_px,target_px,
                               conviction,notes,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (date, sym.upper(), thesis, catalyst, entry_px, stop_px, target_px,
         conviction, notes, datetime.datetime.now().isoformat(timespec="seconds")),
    )
    c.commit()
    c.close()


def close_pick(date, sym, close_px, close_date, notes=""):
    c = _conn()
    row = c.execute("SELECT entry_px FROM record WHERE date=? AND sym=?",
                    (date, sym.upper())).fetchone()
    result = None
    if row and row[0]:
        result = round((close_px / row[0] - 1) * 100, 2)
    c.execute(
        """UPDATE record SET status='closed', close_px=?, close_date=?, result_pct=?, notes=?
           WHERE date=? AND sym=?""",
        (close_px, close_date, result, notes, date, sym.upper()),
    )
    c.commit()
    c.close()
    return result


def recent(n=30):
    c = _conn()
    rows = c.execute(
        """SELECT date,sym,conviction,status,entry_px,stop_px,target_px,result_pct,thesis
           FROM record ORDER BY date DESC, sym LIMIT ?""", (n,)).fetchall()
    c.close()
    return rows


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "recent":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        for r in recent(n):
            print(r)
    else:
        print("usage: python -m swing.lib.journal recent [N]")
