"""
lean_abstain — day-level quantile abstention + pick journal for the lean foundation.

Abstention is STATEFUL (needs the rolling history of past daily top-1 scores), so it
cannot live in the stateless per-candidate scorer. This module owns:
  - a `lean_picks` table in scan_journal.db (one row per zone per scan-day)
  - a causal rolling-quantile decision: trade today only if today's top-1 score
    exceeds the q-th percentile of the last W days' scores for that zone.

Tested 2026-06-18: quantile q=0.3-0.4 keeps coverage stable (~74-80%) across regimes
where a fixed-p threshold collapses to 10%. See research_lean_vs_235_ablation.

Causal / no lookahead: the decision for day D uses ONLY days < D.
"""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from typing import Optional, List

import numpy as np

_DB = Path(__file__).resolve().parents[2] / 'data' / 'scan_journal.db'

DEFAULT_Q = float(os.environ.get('LEAN_ABSTAIN_Q', '0.35'))
DEFAULT_WINDOW = int(os.environ.get('LEAN_ABSTAIN_WINDOW', '60'))
WARMUP = int(os.environ.get('LEAN_ABSTAIN_WARMUP', '30'))   # trade-all until this many history days


def _conn(db: Path = _DB) -> sqlite3.Connection:
    c = sqlite3.connect(str(db))
    c.execute("""CREATE TABLE IF NOT EXISTS lean_picks (
        scan_date TEXT, scan_ts TEXT, zone TEXT, mfo INTEGER,
        symbol TEXT, sector TEXT, score REAL, ret_eod REAL,
        traded INTEGER, q REAL, thr REAL, n_cand INTEGER,
        PRIMARY KEY (scan_date, zone))""")
    return c


def past_scores(zone: str, before_date: str, window: int = DEFAULT_WINDOW,
                db: Path = _DB) -> List[float]:
    """Top-1 scores for `zone` from days strictly BEFORE before_date (most recent `window`)."""
    c = _conn(db)
    rows = c.execute(
        "SELECT score FROM lean_picks WHERE zone=? AND scan_date<? ORDER BY scan_date DESC LIMIT ?",
        (zone, before_date, window)).fetchall()
    c.close()
    return [r[0] for r in rows if r[0] is not None]


def decide(zone: str, today_score: float, today_date: str,
           q: float = DEFAULT_Q, window: int = DEFAULT_WINDOW, db: Path = _DB) -> dict:
    """Causal quantile decision. Returns {trade, thr, n_hist}. Trade-all during warmup."""
    hist = past_scores(zone, today_date, window, db)
    if len(hist) < WARMUP:
        return {'trade': True, 'thr': None, 'n_hist': len(hist), 'reason': 'warmup'}
    thr = float(np.quantile(hist, q))
    return {'trade': today_score > thr, 'thr': thr, 'n_hist': len(hist),
            'reason': f'q{q}>{thr:.3f}' if today_score > thr else f'abstain<{thr:.3f}'}


def record(scan_date: str, scan_ts: str, zone: str, mfo: int, symbol: str, sector: str,
           score: float, traded: int, q: float, thr: Optional[float], n_cand: int,
           ret_eod: Optional[float] = None, db: Path = _DB) -> None:
    """Upsert the day's top-1 lean pick for a zone (idempotent on (date, zone))."""
    c = _conn(db)
    c.execute("""INSERT OR REPLACE INTO lean_picks
        (scan_date, scan_ts, zone, mfo, symbol, sector, score, ret_eod, traded, q, thr, n_cand)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (scan_date, scan_ts, zone, mfo, symbol, sector, score, ret_eod, traded, q, thr, n_cand))
    c.commit()
    c.close()
