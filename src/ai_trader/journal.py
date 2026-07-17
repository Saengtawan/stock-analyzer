"""Forward-tracking journal for ai_trader — the live record that backtests can't give.

One row per trading day: the plan the AI produced, the pick the rule layer emitted
(or abstain), and (filled after close) the realized outcome. This is how we confirm
live == backtest for the novel AI layer.
"""
from __future__ import annotations
import sqlite3, os

DB = "data/ai_trader_journal.db"

DDL = """
CREATE TABLE IF NOT EXISTS ai_journal (
  date          TEXT PRIMARY KEY,
  generated_by  TEXT,     -- mechanical_news | llm | fallback
  regime        TEXT,
  risk          TEXT,     -- normal | reduced | abstain
  enabled       TEXT,     -- comma-joined enabled classifies
  reason        TEXT,     -- AI's regime reason
  pick_classify TEXT,     -- '' if abstain / no pick
  pick_sym      TEXT,
  pick_price    REAL,
  entry_gain    REAL,
  entry_gap     REAL,
  spy_morning   REAL,
  outcome_pct   REAL,     -- filled after close (EOD % from entry, net of cost)
  status        TEXT,     -- planned | picked | abstained | closed
  logged_at     TEXT
);
"""


def _conn(db=DB):
    os.makedirs(os.path.dirname(db), exist_ok=True)
    c = sqlite3.connect(db)
    c.execute(DDL)
    return c


def log_day(date, plan, pick, ctx, ts, db=DB):
    """Upsert the day's plan + pick (outcome filled later)."""
    c = _conn(db)
    if pick is not None:
        cand = pick.candidate
        row = (date, plan.generated_by, plan.regime, plan.risk,
               ",".join(plan.enabled_classifies), plan.notes.get("_regime", ""),
               pick.classify, cand.sym, cand.price, round(cand.gain, 3),
               round(cand.gap, 3), round(ctx.spy_morning, 3), None, "picked", ts)
    else:
        status = "abstained" if plan.risk == "abstain" else "no_pick"
        row = (date, plan.generated_by, plan.regime, plan.risk,
               ",".join(plan.enabled_classifies), plan.notes.get("_regime", ""),
               "", "", None, None, None, round(ctx.spy_morning, 3), None, status, ts)
    c.execute("INSERT OR REPLACE INTO ai_journal VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
    c.commit(); c.close()


def update_outcome(date, outcome_pct, db=DB):
    c = _conn(db)
    c.execute("UPDATE ai_journal SET outcome_pct=?, status='closed' WHERE date=?",
              (round(outcome_pct, 3), date))
    c.commit(); c.close()


DDL_V2 = """
CREATE TABLE IF NOT EXISTS ai_journal_v2 (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  date         TEXT,
  regime       TEXT,
  sym          TEXT,
  archetype    TEXT,
  reason       TEXT,
  exit_style   TEXT,
  hard_stop    REAL,
  trail_pct    REAL,
  entry_price  REAL,
  outcome_pct  REAL,
  status       TEXT,     -- picked | bench | abstained | closed
  logged_at    TEXT,
  mode         TEXT DEFAULT 'live',   -- live (real morning cron) | replay (dev re-run)
  sector       TEXT,
  actual_entry REAL,     -- the price the HUMAN actually filled at (null = simulated only)
  UNIQUE(date, sym)
);
"""

# baseline control arm — realized the same day so we can ask "did AI beat a dumb rule / SPY?"
DDL_BASE = """
CREATE TABLE IF NOT EXISTS ai_baseline_v2 (
  date        TEXT,
  kind        TEXT,      -- spy | field_reclaim (mechanical: deepest gap-down already reclaiming)
  sym         TEXT,
  outcome_pct REAL,
  logged_at   TEXT,
  UNIQUE(date, kind)
);
"""


def _migrate_v2(c):
    """Add columns introduced after the table already existed (idempotent)."""
    c.execute(DDL_V2); c.execute(DDL_BASE)
    have = {r[1] for r in c.execute("PRAGMA table_info(ai_journal_v2)")}
    for col, decl in (("mode", "TEXT DEFAULT 'live'"), ("sector", "TEXT"),
                      ("actual_entry", "REAL")):
        if col not in have:
            c.execute(f"ALTER TABLE ai_journal_v2 ADD COLUMN {col} {decl}")


def log_decision(decision, entry_prices, ts, db=DB, primary_n=2, mode="live", sectors=None):
    """Log a v2 Decision. First `primary_n` ranked picks -> status 'picked' (the ones
    shown/tradeable); the rest -> 'bench' (found + tracked, revealed on request).

    DELETE-before-insert so a re-run REPLACES the whole day (a dev re-run that abstains
    must wipe the earlier pick rows — otherwise stale picks pollute the live record).
    `mode='replay'` marks a dev/backfill re-run so it never counts as a live trade."""
    c = _conn(db); _migrate_v2(c)
    sectors = sectors or {}
    c.execute("DELETE FROM ai_journal_v2 WHERE date=?", (decision.date,))
    if not decision.picks:
        c.execute("INSERT INTO ai_journal_v2 "
                  "(date,regime,sym,archetype,reason,status,logged_at,mode) VALUES (?,?,?,?,?,?,?,?)",
                  (decision.date, decision.regime, "", "", decision.abstain_reason or "",
                   "abstained", ts, mode))
    for i, pk in enumerate(decision.picks):
        status = "picked" if i < primary_n else "bench"
        c.execute("INSERT INTO ai_journal_v2 "
                  "(date,regime,sym,archetype,reason,exit_style,hard_stop,trail_pct,"
                  "entry_price,status,logged_at,mode,sector) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (decision.date, decision.regime, pk.sym, pk.archetype, pk.reason,
                   pk.exit_style, pk.hard_stop, pk.trail_pct,
                   entry_prices.get(pk.sym), status, ts, mode, sectors.get(pk.sym)))
    c.commit(); c.close()


def update_outcome_v2(date, sym, outcome_pct, db=DB):
    c = _conn(db); _migrate_v2(c)
    c.execute("UPDATE ai_journal_v2 SET outcome_pct=?, status='closed' WHERE date=? AND sym=?",
              (round(outcome_pct, 3), date, sym))
    c.commit(); c.close()


def log_baseline(date, kind, sym, outcome_pct, ts, db=DB):
    c = _conn(db); _migrate_v2(c)
    c.execute("INSERT OR REPLACE INTO ai_baseline_v2 (date,kind,sym,outcome_pct,logged_at) "
              "VALUES (?,?,?,?,?)", (date, kind, sym, round(outcome_pct, 3), ts))
    c.commit(); c.close()


def record_fill(date, sym, actual_entry, db=DB):
    """The human confirms they actually bought `sym` at `actual_entry` — turns a simulated
    row into a real forward trade."""
    c = _conn(db); _migrate_v2(c)
    n = c.execute("UPDATE ai_journal_v2 SET actual_entry=? WHERE date=? AND sym=?",
                  (actual_entry, date, sym.upper())).rowcount
    c.commit(); c.close()
    return n


def recent_outcomes(n=8, db=DB):
    """Last N realized LIVE picks (for feeding the AI its own track record)."""
    c = _conn(db); _migrate_v2(c)
    rows = list(c.execute(
        "SELECT date,sym,archetype,outcome_pct FROM ai_journal_v2 "
        "WHERE status='closed' AND mode='live' AND sym<>'' ORDER BY date DESC, sym LIMIT ?", (n,)))
    c.close()
    return rows


def report_v2(db=DB, live_only=True):
    c = _conn(db); _migrate_v2(c)
    q = ("SELECT date,sym,archetype,status,outcome_pct,reason,mode FROM ai_journal_v2 "
         + ("WHERE mode='live' " if live_only else "") + "ORDER BY date, sym")
    rows = list(c.execute(q))
    base = list(c.execute("SELECT date,kind,sym,outcome_pct FROM ai_baseline_v2 ORDER BY date,kind"))
    c.close()
    return rows, base


def report(db=DB):
    c = _conn(db)
    rows = list(c.execute(
        "SELECT date,status,risk,pick_sym,entry_gain,outcome_pct,regime FROM ai_journal ORDER BY date"))
    c.close()
    return rows
