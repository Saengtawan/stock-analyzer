"""
Trade Journal — record every pick and its outcome for drift monitoring.

Tables:
- scan_picks: every pick emitted by a strategy (at scan time)
- pick_outcomes: outcome of each pick (filled in at close or next day)

Usage:
    from src.scan.journal import Journal
    j = Journal()
    j.record_pick(strategy, symbol, entry, sl, tp, prob, bucket, features)
    j.update_outcomes()  # call after close
    j.weekly_report()  # actual vs backtest WR by strategy/bucket
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
import pytz

ET = pytz.timezone('US/Eastern')
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'scan_journal.db'


class Journal:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_ts TEXT NOT NULL,
                scan_date TEXT NOT NULL,
                strategy TEXT NOT NULL,
                bucket TEXT,
                symbol TEXT NOT NULL,
                entry REAL NOT NULL,
                sl_price REAL,
                tp_price REAL,
                trail_pct REAL,
                ml_prob REAL,
                ml_threshold REAL,
                expected_wr REAL,
                reason TEXT,
                features_json TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pick_outcomes (
                pick_id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                exit_price REAL,
                exit_reason TEXT,
                exit_ts TEXT,
                pnl_pct REAL,
                reached_tp BOOLEAN,
                hit_sl BOOLEAN,
                max_gain_pct REAL,
                max_drawdown_pct REAL,
                outcome_label INTEGER,
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (pick_id) REFERENCES scan_picks(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_picks_date ON scan_picks(scan_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_picks_strategy ON scan_picks(strategy)")
        conn.commit()
        conn.close()

    def record_pick(self, strategy: str, bucket: str, symbol: str,
                    entry: float, sl_price: float, tp_price: float = None,
                    trail_pct: float = None, ml_prob: float = None,
                    ml_threshold: float = None, expected_wr: float = None,
                    reason: str = "", features: dict = None) -> int:
        """Record a new pick. Returns pick_id."""
        now_et = datetime.now(ET)
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO scan_picks (
                scan_ts, scan_date, strategy, bucket, symbol,
                entry, sl_price, tp_price, trail_pct,
                ml_prob, ml_threshold, expected_wr, reason, features_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_et.strftime('%Y-%m-%d %H:%M:%S'),
            now_et.strftime('%Y-%m-%d'),
            strategy, bucket, symbol,
            entry, sl_price, tp_price, trail_pct,
            ml_prob, ml_threshold, expected_wr, reason,
            json.dumps(features) if features else None,
        ))
        pick_id = cur.lastrowid
        conn.commit()
        conn.close()
        return pick_id

    def record_outcome(self, pick_id: int, exit_price: float, exit_reason: str,
                       pnl_pct: float, reached_tp: bool, hit_sl: bool,
                       max_gain_pct: float, max_drawdown_pct: float):
        """Record outcome of a pick."""
        label = 1 if pnl_pct > 0 else 0
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT OR REPLACE INTO pick_outcomes (
                pick_id, symbol, exit_price, exit_reason, exit_ts,
                pnl_pct, reached_tp, hit_sl, max_gain_pct, max_drawdown_pct,
                outcome_label
            ) VALUES (
                ?, (SELECT symbol FROM scan_picks WHERE id=?),
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            pick_id, pick_id, exit_price, exit_reason,
            datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S'),
            pnl_pct, reached_tp, hit_sl, max_gain_pct, max_drawdown_pct, label,
        ))
        conn.commit()
        conn.close()

    def report(self, days: int = 30) -> dict:
        """WR by strategy + bucket over last N days."""
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("""
            SELECT p.strategy, p.bucket,
                   COUNT(*) as n,
                   SUM(o.outcome_label) as wins,
                   AVG(o.pnl_pct) as avg_pnl,
                   AVG(p.expected_wr) as expected_wr
            FROM scan_picks p
            LEFT JOIN pick_outcomes o ON p.id = o.pick_id
            WHERE p.scan_date >= date('now', ?)
            AND o.pick_id IS NOT NULL
            GROUP BY p.strategy, p.bucket
            ORDER BY p.strategy, p.bucket
        """, (f'-{days} days',)).fetchall()
        conn.close()

        out = []
        for r in rows:
            strategy, bucket, n, wins, avg_pnl, exp_wr = r
            wr = (wins / n * 100) if n > 0 else 0
            out.append({
                'strategy': strategy,
                'bucket': bucket,
                'n': n,
                'wins': wins or 0,
                'actual_wr': round(wr, 1),
                'expected_wr': round(exp_wr * 100, 1) if exp_wr else None,
                'avg_pnl': round(avg_pnl or 0, 3),
                'drift': round(wr - (exp_wr * 100 if exp_wr else 0), 1),
            })
        return out

    def pending_outcomes(self):
        """List picks without outcomes yet (need follow-up)."""
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("""
            SELECT p.id, p.symbol, p.entry, p.scan_ts, p.strategy
            FROM scan_picks p
            LEFT JOIN pick_outcomes o ON p.id = o.pick_id
            WHERE o.pick_id IS NULL
            AND p.scan_date >= date('now', '-3 days')
        """).fetchall()
        conn.close()
        return [dict(zip(['id','symbol','entry','scan_ts','strategy'], r)) for r in rows]


# Singleton
_journal = None
def get_journal() -> Journal:
    global _journal
    if _journal is None:
        _journal = Journal()
    return _journal
