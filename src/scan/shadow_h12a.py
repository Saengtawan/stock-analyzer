"""H12-A Shadow mode — log H12-A picks alongside production picks WITHOUT trading.

When ML_FILTER_VARIANT=h12a_shadow:
  - Production scorer (v22) is used for actual picks (no behavior change)
  - H12-A scorer is also run on the same candidates
  - H12-A picks are logged to data/h12a_shadow_journal.db for offline comparison

Tables:
  shadow_picks: per-zone H12-A top-1 picks per scan
    columns: scan_ts, date, mfo, zone, sym, sector, score, ef_reason, was_prod_pick
  shadow_rejects: candidates that H12-A filtered out
    columns: scan_ts, date, mfo, zone, sym, sector, reason

Usage from ml_filter.py:
  from src.scan.shadow_h12a import is_shadow_mode, log_h12a_shadow_pick, log_h12a_reject

After 1-2 weeks of shadow logs, compare via:
  sqlite3 data/h12a_shadow_journal.db
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = ROOT / 'data/h12a_shadow_journal.db'

_DB_INITIALIZED = False


def is_shadow_mode() -> bool:
    """Return True if H12-A shadow mode is enabled."""
    return os.environ.get('ML_FILTER_VARIANT', '') == 'h12a_shadow'


def _init_db():
    global _DB_INITIALIZED
    if _DB_INITIALIZED: return
    SHADOW_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SHADOW_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shadow_picks (
            scan_ts TEXT,
            date TEXT,
            mfo INTEGER,
            zone TEXT,
            sym TEXT,
            sector TEXT,
            score REAL,
            ef_reason TEXT,
            was_prod_pick INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shadow_rejects (
            scan_ts TEXT,
            date TEXT,
            mfo INTEGER,
            zone TEXT,
            sym TEXT,
            sector TEXT,
            reason TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shadow_picks_ts ON shadow_picks(scan_ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shadow_rejects_ts ON shadow_rejects(scan_ts)")
    conn.commit()
    conn.close()
    _DB_INITIALIZED = True


def log_h12a_shadow_pick(date: str, mfo: int, zone: str, sym: str,
                         sector: str, score: float, ef_reason: str = '',
                         was_prod_pick: bool = False):
    """Log a H12-A pick (won't be traded — just for comparison)."""
    try:
        _init_db()
        conn = sqlite3.connect(str(SHADOW_DB))
        conn.execute("""
            INSERT INTO shadow_picks (scan_ts, date, mfo, zone, sym, sector, score, ef_reason, was_prod_pick)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), date, mfo, zone, sym, sector,
              score, ef_reason, 1 if was_prod_pick else 0))
        conn.commit()
        conn.close()
    except Exception:
        pass  # never break scan


def log_h12a_reject(date: str, mfo: int, zone: str, sym: str,
                    sector: str, reason: str):
    """Log a candidate that H12-A rejected."""
    try:
        _init_db()
        conn = sqlite3.connect(str(SHADOW_DB))
        conn.execute("""
            INSERT INTO shadow_rejects (scan_ts, date, mfo, zone, sym, sector, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), date, mfo, zone, sym, sector, reason))
        conn.commit()
        conn.close()
    except Exception:
        pass
