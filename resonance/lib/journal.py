"""resonance / lib / journal.py — the FORWARD RECORD store (the only fitness).

Logs each day's decide-pass picks (coil+catalyst reasons + paper entry), and the real
09:30-open -> 15:55-close outcome plus vs-SPY. This is the sole continuity of the system: the
forward record — not any backtest statistic — is what conditions tomorrow's decide.

DELETE-before-insert per (date, sym, mode) so dev re-runs never pollute the record (the
contamination bug that hit the old ai_trader journal). mode = 'live' | 'replay' kept separate so a
replay/backfill never mixes into the live forward record.

Schema is deliberately flat — one row per (date, sym, mode). `log_pick` writes the morning
decision (reasons + paper entry). `fill_outcome` later stamps the realized close / result% /
vs_spy / learn-pass judgment. There is NO statistical-baseline arm by design (resonance abandoned
bucket statistics — the only fitness here is the forward outcome).

CLI:
  python -m resonance.lib.journal rows DATE [mode]
"""
from __future__ import annotations

import argparse
import datetime
import os
import sqlite3

DB = "data/resonance.db"

DDL = """
CREATE TABLE IF NOT EXISTS record (
  date            TEXT,    -- trading day (America/New_York), 'YYYY-MM-DD'
  sym             TEXT,    -- ticker
  coil_reason     TEXT,    -- WHY the spring was loaded (from the plan)
  catalyst_reason TEXT,    -- WHY it should release UP + hold to close (from the plan)
  entry_px        REAL,    -- paper entry = the RTH 09:30 open (filled by execute.paper_buy)
  open_et         TEXT,    -- 'HH:MM' ET of the paper entry (always '09:30' for this system)
  close_px        REAL,    -- realized 15:55 ET close (filled after the close)
  result_pct      REAL,    -- (close/entry - 1) * 100 ; filled after close
  vs_spy          REAL,    -- result_pct - SPY's same-day open->close % ; filled after close
  judgment        TEXT,    -- learn-pass grade: win | loss | correct_skip | miss (+ note)
  mode            TEXT,    -- 'live' (real morning cron) | 'replay' (dev re-run / backfill)
  created_at      TEXT,    -- when this row was logged
  UNIQUE(date, sym, mode)
);
"""


def _conn(db=DB):
    os.makedirs(os.path.dirname(db), exist_ok=True)
    c = sqlite3.connect(db)
    c.execute(DDL)
    return c


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def log_pick(date, sym, *, coil_reason=None, catalyst_reason=None, entry_px=None,
             open_et="09:30", mode="live", db=DB):
    """Log (or replace) one pick for `date`. DELETE-before-insert per (date, sym, mode) so a
    re-run REPLACES the row — a dev re-run that now drops a name must wipe its earlier paper
    entry, otherwise a stale row pollutes the forward record. Outcome fields (close_px,
    result_pct, vs_spy, judgment) are left null here and stamped later by `fill_outcome`."""
    c = _conn(db)
    c.execute("DELETE FROM record WHERE date=? AND sym=? AND mode=?", (date, sym.upper(), mode))
    c.execute(
        "INSERT INTO record (date,sym,coil_reason,catalyst_reason,entry_px,open_et,"
        "close_px,result_pct,vs_spy,judgment,mode,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (date, sym.upper(), coil_reason, catalyst_reason, entry_px, open_et,
         None, None, None, None, mode, _now()),
    )
    c.commit(); c.close()


def fill_outcome(date, sym, close_px, result_pct, vs_spy, judgment, mode="live", db=DB):
    """After the close: stamp the realized close, result %, vs-SPY, and the learn-pass judgment
    onto an existing pick row. Returns the number of rows updated (0 if never logged)."""
    c = _conn(db)
    n = c.execute(
        "UPDATE record SET close_px=?, result_pct=?, vs_spy=?, judgment=? "
        "WHERE date=? AND sym=? AND mode=?",
        (close_px,
         round(result_pct, 3) if result_pct is not None else None,
         round(vs_spy, 3) if vs_spy is not None else None,
         judgment, date, sym.upper(), mode),
    ).rowcount
    c.commit(); c.close()
    return n


def rows(date, mode="live", db=DB):
    """All logged rows for a (date, mode), as dicts, newest-picked first."""
    c = _conn(db)
    c.row_factory = sqlite3.Row
    r = list(c.execute(
        "SELECT date,sym,coil_reason,catalyst_reason,entry_px,open_et,close_px,result_pct,"
        "vs_spy,judgment,mode,created_at FROM record "
        "WHERE date=? AND mode=? ORDER BY created_at, sym", (date, mode)))
    c.close()
    return [dict(x) for x in r]


def _delete_row(date, sym, mode, db=DB):
    """Test/util helper: drop a single (date, sym, mode) row (used by the self-test cleanup)."""
    c = _conn(db)
    n = c.execute("DELETE FROM record WHERE date=? AND sym=? AND mode=?",
                  (date, sym.upper(), mode)).rowcount
    c.commit(); c.close()
    return n


def main():
    ap = argparse.ArgumentParser(description="resonance forward-record journal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rows"); r.add_argument("date")
    r.add_argument("mode", nargs="?", default="live")
    a = ap.parse_args()
    if a.cmd == "rows":
        rr = rows(a.date, a.mode)
        print(f"# RECORD {a.date} mode={a.mode} — {len(rr)} rows")
        cols = ("sym", "entry_px", "open_et", "close_px", "result_pct", "vs_spy", "judgment",
                "coil_reason", "catalyst_reason")
        print("\t".join(cols))
        for x in rr:
            print("\t".join("" if x[k] is None else str(x[k]) for k in cols))


if __name__ == "__main__":
    main()
