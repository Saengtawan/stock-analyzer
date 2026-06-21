"""Per-stock causal track record — the identity edge (research_stock_identity_edge 2026-06-20).

A stock's prior riser/Z1 EOD outcomes predict its future EOD (orthogonal to OHLCV, which
pooled-analysis called no-edge). Used as a GATE (binary trust), not an ML feature (which
dilutes it among noise — proven). Gate: prior_n >= MIN_N and prior_avg > 0.

CAUSAL: prior_avg(sym) at decision time uses ONLY outcomes strictly before today. Updated
from the live journal (pick_outcomes) after each close + seeded from backtest history.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'data' / 'stock_track_record.db'
MIN_N = 6          # need >=6 prior appearances before trusting (validated plateau)

DDL = """
CREATE TABLE IF NOT EXISTS stock_outcomes (
  symbol TEXT, date TEXT, eod_ret REAL, source TEXT,
  PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_sym_date ON stock_outcomes(symbol, date);
"""


def _conn():
    c = sqlite3.connect(str(DB))
    c.executescript(DDL)
    return c


def record_outcome(symbol: str, date: str, eod_ret: float, source: str = 'live'):
    """Append one realized outcome (idempotent on (symbol,date))."""
    c = _conn()
    c.execute("INSERT OR REPLACE INTO stock_outcomes VALUES (?,?,?,?)",
              (symbol, date, float(eod_ret), source))
    c.commit(); c.close()


def prior_stats(symbol: str, before_date: str) -> tuple[int, Optional[float]]:
    """(n, avg_eod) over this symbol's outcomes STRICTLY BEFORE before_date. Causal."""
    c = _conn()
    rows = c.execute(
        "SELECT eod_ret FROM stock_outcomes WHERE symbol=? AND date < ? ORDER BY date",
        (symbol, before_date)).fetchall()
    c.close()
    n = len(rows)
    return n, (sum(r[0] for r in rows) / n if n else None)


def passes_gate(symbol: str, before_date: str, min_n: int = MIN_N) -> bool:
    """Identity gate: trusted iff >=min_n prior appearances AND prior_avg > 0.
    Unknown/new stocks (n<min_n) do NOT pass — 'allow-new' was proven not to help
    (edge = select PROVEN-good, not just avoid proven-bad)."""
    n, avg = prior_stats(symbol, before_date)
    return n >= min_n and avg is not None and avg > 0


if __name__ == '__main__':  # quick self-check
    print('DB:', DB, '| MIN_N:', MIN_N)
    c = _conn()
    n = c.execute("SELECT COUNT(*) FROM stock_outcomes").fetchone()[0]
    syms = c.execute("SELECT COUNT(DISTINCT symbol) FROM stock_outcomes").fetchone()[0]
    print(f'outcomes={n} symbols={syms}')
    c.close()
