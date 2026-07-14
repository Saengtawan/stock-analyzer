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
  status       TEXT,     -- picked | abstained | closed
  logged_at    TEXT,
  UNIQUE(date, sym)
);
"""


def log_decision(decision, entry_prices, ts, db=DB):
    """Log a v2 Decision (AI archetype+reasoning per pick). entry_prices: {sym: price}."""
    c = _conn(db); c.execute(DDL_V2)
    if not decision.picks:
        c.execute("INSERT OR REPLACE INTO ai_journal_v2 "
                  "(date,regime,sym,archetype,reason,status,logged_at) VALUES (?,?,?,?,?,?,?)",
                  (decision.date, decision.regime, "", "", decision.abstain_reason or "",
                   "abstained", ts))
    for pk in decision.picks:
        c.execute("INSERT OR REPLACE INTO ai_journal_v2 "
                  "(date,regime,sym,archetype,reason,exit_style,hard_stop,trail_pct,"
                  "entry_price,status,logged_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (decision.date, decision.regime, pk.sym, pk.archetype, pk.reason,
                   pk.exit_style, pk.hard_stop, pk.trail_pct,
                   entry_prices.get(pk.sym), "picked", ts))
    c.commit(); c.close()


def update_outcome_v2(date, sym, outcome_pct, db=DB):
    c = _conn(db); c.execute(DDL_V2)
    c.execute("UPDATE ai_journal_v2 SET outcome_pct=?, status='closed' WHERE date=? AND sym=?",
              (round(outcome_pct, 3), date, sym))
    c.commit(); c.close()


def report_v2(db=DB):
    c = _conn(db); c.execute(DDL_V2)
    rows = list(c.execute("SELECT date,sym,archetype,status,outcome_pct,reason FROM ai_journal_v2 "
                          "ORDER BY date, sym"))
    c.close()
    return rows


def report(db=DB):
    c = _conn(db)
    rows = list(c.execute(
        "SELECT date,status,risk,pick_sym,entry_gain,outcome_pct,regime FROM ai_journal ORDER BY date"))
    c.close()
    return rows
