#!/usr/bin/env python3
"""Backfill + daily fill: track outcomes for market-level signals."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import sqlite3
import logging
import numpy as np
from datetime import datetime
from pathlib import Path
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / 'data' / 'trade_history.db'


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_signal_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            entry_price REAL,
            exit_price REAL,
            outcome_5d REAL,
            wr_expected REAL,
            sizing REAL,
            params_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(signal_date, signal_type, symbol)
        )
    """)
    conn.commit()


def backfill_sector_contrarian(conn):
    """Backfill sector contrarian signals from historical data."""
    rows = conn.execute("""
        SELECT s.date, s.sector, s.pct_change
        FROM sector_etf_daily_returns s
        WHERE s.sector NOT IN ('S&P 500','US Dollar','Treasury Long','Gold')
        ORDER BY s.date
    """).fetchall()

    daily = defaultdict(dict)
    for r in rows:
        daily[r[0]][r[1]] = r[2]
    dates = sorted(daily.keys())

    sector_etf = {
        'Technology': 'XLK', 'Healthcare': 'XLV', 'Financial Services': 'XLF',
        'Energy': 'XLE', 'Consumer Cyclical': 'XLY', 'Consumer Defensive': 'XLP',
        'Industrials': 'XLI', 'Utilities': 'XLU', 'Real Estate': 'XLRE',
        'Basic Materials': 'XLB', 'Communication Services': 'XLC',
    }

    inserted = 0
    for i in range(20, len(dates) - 5):
        dt = dates[i]
        sector_20d = {}
        for s in daily[dt]:
            rets = [daily[dates[j]].get(s, 0) or 0 for j in range(i - 20, i)]
            sector_20d[s] = sum(rets)

        if not sector_20d:
            continue
        worst = min(sector_20d, key=sector_20d.get)
        etf = sector_etf.get(worst, '')
        if not etf:
            continue

        # 5d forward return
        fwd = sum(daily[dates[j]].get(worst, 0) or 0 for j in range(i + 1, min(i + 6, len(dates))))

        try:
            conn.execute("""
                INSERT OR IGNORE INTO market_signal_outcomes
                (signal_date, signal_type, symbol, outcome_5d, wr_expected, sizing)
                VALUES (?, 'SECTOR_CONTRARIAN', ?, ?, 58, 0.5)
            """, (dt, etf, round(fwd, 4)))
            inserted += 1
        except Exception:
            pass

    conn.commit()
    logger.info(f"Sector contrarian backfill: {inserted} signals")


def backfill_crude_momentum(conn):
    """Backfill crude momentum signals."""
    rows = conn.execute("""
        SELECT date, crude_close FROM macro_snapshots
        WHERE crude_close IS NOT NULL ORDER BY date
    """).fetchall()

    sector_rows = conn.execute("""
        SELECT date, pct_change FROM sector_etf_daily_returns
        WHERE sector = 'Energy' ORDER BY date
    """).fetchall()
    energy = {r[0]: r[1] for r in sector_rows}
    dates_e = sorted(energy.keys())

    inserted = 0
    crude = {r[0]: r[1] for r in rows}
    dates = sorted(crude.keys())

    for i in range(5, len(dates) - 5):
        dt = dates[i]
        if dates[i - 5] not in crude:
            continue
        chg = (crude[dt] / crude[dates[i - 5]] - 1) * 100

        if chg < 3:
            continue

        # 5d forward Energy return
        idx = dates_e.index(dt) if dt in dates_e else -1
        if idx < 0 or idx + 5 >= len(dates_e):
            continue
        fwd = sum(energy.get(dates_e[j], 0) or 0 for j in range(idx + 1, min(idx + 6, len(dates_e))))

        wr = 69 if chg >= 5 else 67
        try:
            conn.execute("""
                INSERT OR IGNORE INTO market_signal_outcomes
                (signal_date, signal_type, symbol, outcome_5d, wr_expected, sizing, params_json)
                VALUES (?, 'CRUDE_MOMENTUM', 'XLE', ?, ?, 0.5, ?)
            """, (dt, round(fwd, 4), wr, f'{{"crude_chg": {chg:.1f}}}'))
            inserted += 1
        except Exception:
            pass

    conn.commit()
    logger.info(f"Crude momentum backfill: {inserted} signals")


def backfill_spy_drawdown(conn):
    """Backfill SPY drawdown signals."""
    rows = conn.execute("""
        SELECT date, spy_close FROM macro_snapshots
        WHERE spy_close IS NOT NULL ORDER BY date
    """).fetchall()

    dates = [r[0] for r in rows]
    spy = {r[0]: r[1] for r in rows}

    inserted = 0
    for i in range(20, len(dates) - 5):
        dt = dates[i]
        prices = [spy[dates[j]] for j in range(i - 19, i + 1)]
        high_20d = max(prices)
        dd = (spy[dt] / high_20d - 1) * 100

        if dd > -7:
            continue

        fwd = (spy[dates[i + 5]] / spy[dt] - 1) * 100
        wr = 69 if dd <= -10 else 64

        try:
            conn.execute("""
                INSERT OR IGNORE INTO market_signal_outcomes
                (signal_date, signal_type, symbol, outcome_5d, wr_expected, sizing, params_json)
                VALUES (?, 'SPY_DRAWDOWN', 'SPY', ?, ?, 0.75, ?)
            """, (dt, round(fwd, 4), wr, f'{{"drawdown": {dd:.1f}}}'))
            inserted += 1
        except Exception:
            pass

    conn.commit()
    logger.info(f"SPY drawdown backfill: {inserted} signals")


def main():
    conn = sqlite3.connect(str(DB_PATH))
    ensure_table(conn)

    # Check if already backfilled
    n = conn.execute('SELECT COUNT(*) FROM market_signal_outcomes').fetchone()[0]
    if n < 100:
        logger.info("Backfilling market signal outcomes...")
        backfill_sector_contrarian(conn)
        backfill_crude_momentum(conn)
        backfill_spy_drawdown(conn)
    else:
        logger.info(f"Already have {n} outcomes, skipping backfill")

    # Summary
    for sig_type in ['SECTOR_CONTRARIAN', 'CRUDE_MOMENTUM', 'SPY_DRAWDOWN']:
        r = conn.execute("""
            SELECT COUNT(*), ROUND(AVG(CASE WHEN outcome_5d > 0 THEN 1.0 ELSE 0.0 END)*100, 1),
                   ROUND(AVG(outcome_5d), 3)
            FROM market_signal_outcomes WHERE signal_type = ?
        """, (sig_type,)).fetchone()
        logger.info(f"  {sig_type}: n={r[0]} WR={r[1]}% E[R]={r[2]:+.3f}%")

    conn.close()


if __name__ == '__main__':
    main()
