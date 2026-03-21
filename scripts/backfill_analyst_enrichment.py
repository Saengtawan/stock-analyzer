#!/usr/bin/env python3
"""
Backfill analyst-related data into signal_outcomes table.

Adds and populates:
  - analyst_action_7d TEXT       most recent upgrade/downgrade/init within 7 days before scan_date
  - analyst_target_upside REAL   (target_mean / scan_price - 1) * 100 from analyst_consensus
  - analyst_rating_count_30d INT number of analyst actions within 30 days before scan_date
  - analyst_bull_score REAL      bull_score from analyst_consensus
"""

import sqlite3
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "trade_history.db")
DB_PATH = os.path.abspath(DB_PATH)


def add_columns_if_missing(conn: sqlite3.Connection) -> list[str]:
    """Add analyst columns to signal_outcomes if they don't exist."""
    cursor = conn.execute("PRAGMA table_info(signal_outcomes)")
    existing = {row[1] for row in cursor.fetchall()}

    columns_to_add = [
        ("analyst_action_7d", "TEXT"),
        ("analyst_target_upside", "REAL"),
        ("analyst_rating_count_30d", "INTEGER"),
        ("analyst_bull_score", "REAL"),
    ]

    added = []
    for col_name, col_type in columns_to_add:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE signal_outcomes ADD COLUMN {col_name} {col_type}")
            added.append(col_name)
            print(f"  Added column: {col_name} {col_type}")
        else:
            print(f"  Column already exists: {col_name}")

    if added:
        conn.commit()
    return added


def load_analyst_ratings(conn: sqlite3.Connection) -> dict:
    """Load all analyst_ratings into a dict keyed by symbol -> list of (date, action)."""
    rows = conn.execute(
        "SELECT symbol, date, action FROM analyst_ratings ORDER BY date DESC"
    ).fetchall()

    by_symbol = defaultdict(list)
    for symbol, date_str, action in rows:
        by_symbol[symbol].append((date_str, action))
    return dict(by_symbol)


def load_analyst_consensus(conn: sqlite3.Connection) -> dict:
    """Load analyst_consensus into a dict keyed by symbol."""
    rows = conn.execute(
        "SELECT symbol, bull_score, target_mean FROM analyst_consensus"
    ).fetchall()

    consensus = {}
    for symbol, bull_score, target_mean in rows:
        consensus[symbol] = {
            "bull_score": bull_score,
            "target_mean": target_mean,
        }
    return consensus


def backfill(conn: sqlite3.Connection) -> dict:
    """Backfill analyst data into signal_outcomes. Returns stats."""
    # Load reference data
    ratings_by_symbol = load_analyst_ratings(conn)
    consensus_by_symbol = load_analyst_consensus(conn)

    print(f"\n  Analyst ratings: {sum(len(v) for v in ratings_by_symbol.values())} rows for {len(ratings_by_symbol)} symbols")
    print(f"  Analyst consensus: {len(consensus_by_symbol)} symbols")

    # Load signal_outcomes rows
    signals = conn.execute(
        "SELECT id, symbol, scan_date, scan_price FROM signal_outcomes"
    ).fetchall()
    print(f"  Signal outcomes: {len(signals)} rows\n")

    stats = {
        "total": len(signals),
        "action_7d_filled": 0,
        "target_upside_filled": 0,
        "rating_count_30d_filled": 0,
        "bull_score_filled": 0,
        "any_filled": 0,
    }

    updates = []

    for row_id, symbol, scan_date_str, scan_price in signals:
        scan_date = datetime.strptime(scan_date_str, "%Y-%m-%d").date()
        date_7d_ago = (scan_date - timedelta(days=7)).isoformat()
        date_30d_ago = (scan_date - timedelta(days=30)).isoformat()
        scan_date_iso = scan_date.isoformat()

        action_7d = None
        count_30d = 0
        target_upside = None
        bull_score = None

        # --- analyst_ratings lookups ---
        if symbol in ratings_by_symbol:
            for r_date, r_action in ratings_by_symbol[symbol]:
                # Ratings are sorted DESC, so first match within window is most recent
                if date_7d_ago <= r_date < scan_date_iso:
                    if action_7d is None:
                        action_7d = r_action
                if date_30d_ago <= r_date < scan_date_iso:
                    count_30d += 1

        # --- analyst_consensus lookup ---
        if symbol in consensus_by_symbol:
            c = consensus_by_symbol[symbol]
            bull_score = c["bull_score"]
            if c["target_mean"] and scan_price and scan_price > 0:
                target_upside = round((c["target_mean"] / scan_price - 1) * 100, 2)

        any_filled = (
            action_7d is not None
            or count_30d > 0
            or target_upside is not None
            or bull_score is not None
        )

        if any_filled:
            stats["any_filled"] += 1
        if action_7d is not None:
            stats["action_7d_filled"] += 1
        if target_upside is not None:
            stats["target_upside_filled"] += 1
        if count_30d > 0:
            stats["rating_count_30d_filled"] += 1
        if bull_score is not None:
            stats["bull_score_filled"] += 1

        updates.append((action_7d, target_upside, count_30d, bull_score, row_id))

    # Batch update
    conn.executemany(
        """UPDATE signal_outcomes
           SET analyst_action_7d = ?,
               analyst_target_upside = ?,
               analyst_rating_count_30d = ?,
               analyst_bull_score = ?
           WHERE id = ?""",
        updates,
    )
    conn.commit()

    return stats


def report_correlations(conn: sqlite3.Connection):
    """Print correlation between analyst features and outcome_5d."""
    print("\n" + "=" * 70)
    print("CORRELATION ANALYSIS: Analyst Features vs outcome_5d")
    print("=" * 70)

    # --- 1. outcome_5d by analyst_action_7d ---
    print("\n--- outcome_5d by analyst_action_7d ---")
    rows = conn.execute(
        """SELECT analyst_action_7d,
                  COUNT(*) as n,
                  ROUND(AVG(outcome_5d), 3) as avg_5d,
                  ROUND(AVG(CASE WHEN outcome_5d > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) as win_rate
           FROM signal_outcomes
           WHERE outcome_5d IS NOT NULL
           GROUP BY analyst_action_7d
           ORDER BY avg_5d DESC"""
    ).fetchall()
    print(f"  {'Action':<12} {'N':>5} {'Avg 5d%':>10} {'WinRate%':>10}")
    print(f"  {'-'*12} {'-'*5} {'-'*10} {'-'*10}")
    for action, n, avg_5d, wr in rows:
        label = action if action else "(none)"
        avg_str = f"{avg_5d:.3f}" if avg_5d is not None else "N/A"
        wr_str = f"{wr:.1f}" if wr is not None else "N/A"
        print(f"  {label:<12} {n:>5} {avg_str:>10} {wr_str:>10}")

    # --- 2. outcome_5d by analyst_bull_score buckets ---
    print("\n--- outcome_5d by analyst_bull_score bucket ---")
    rows = conn.execute(
        """SELECT
              CASE
                WHEN analyst_bull_score IS NULL THEN 'no_data'
                WHEN analyst_bull_score >= 1.5 THEN 'high (>=1.5)'
                WHEN analyst_bull_score >= 1.0 THEN 'med (1.0-1.5)'
                ELSE 'low (<1.0)'
              END as bucket,
              COUNT(*) as n,
              ROUND(AVG(outcome_5d), 3) as avg_5d,
              ROUND(AVG(CASE WHEN outcome_5d > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) as win_rate
           FROM signal_outcomes
           WHERE outcome_5d IS NOT NULL
           GROUP BY bucket
           ORDER BY avg_5d DESC"""
    ).fetchall()
    print(f"  {'Bucket':<16} {'N':>5} {'Avg 5d%':>10} {'WinRate%':>10}")
    print(f"  {'-'*16} {'-'*5} {'-'*10} {'-'*10}")
    for bucket, n, avg_5d, wr in rows:
        avg_str = f"{avg_5d:.3f}" if avg_5d is not None else "N/A"
        wr_str = f"{wr:.1f}" if wr is not None else "N/A"
        print(f"  {bucket:<16} {n:>5} {avg_str:>10} {wr_str:>10}")

    # --- 3. outcome_5d by analyst_target_upside buckets ---
    print("\n--- outcome_5d by analyst_target_upside bucket ---")
    rows = conn.execute(
        """SELECT
              CASE
                WHEN analyst_target_upside IS NULL THEN 'no_data'
                WHEN analyst_target_upside >= 40 THEN 'high (>=40%)'
                WHEN analyst_target_upside >= 15 THEN 'med (15-40%)'
                WHEN analyst_target_upside >= 0  THEN 'low (0-15%)'
                ELSE 'negative (<0%)'
              END as bucket,
              COUNT(*) as n,
              ROUND(AVG(outcome_5d), 3) as avg_5d,
              ROUND(AVG(CASE WHEN outcome_5d > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) as win_rate
           FROM signal_outcomes
           WHERE outcome_5d IS NOT NULL
           GROUP BY bucket
           ORDER BY avg_5d DESC"""
    ).fetchall()
    print(f"  {'Bucket':<18} {'N':>5} {'Avg 5d%':>10} {'WinRate%':>10}")
    print(f"  {'-'*18} {'-'*5} {'-'*10} {'-'*10}")
    for bucket, n, avg_5d, wr in rows:
        avg_str = f"{avg_5d:.3f}" if avg_5d is not None else "N/A"
        wr_str = f"{wr:.1f}" if wr is not None else "N/A"
        print(f"  {bucket:<18} {n:>5} {avg_str:>10} {wr_str:>10}")

    # --- 4. Distribution of analyst_target_upside ---
    print("\n--- analyst_target_upside distribution ---")
    rows = conn.execute(
        """SELECT
              MIN(analyst_target_upside) as min_val,
              MAX(analyst_target_upside) as max_val,
              ROUND(AVG(analyst_target_upside), 2) as avg_val,
              COUNT(analyst_target_upside) as n_filled,
              COUNT(*) - COUNT(analyst_target_upside) as n_null
           FROM signal_outcomes"""
    ).fetchone()
    min_v, max_v, avg_v, n_filled, n_null = rows
    print(f"  Filled: {n_filled} | NULL: {n_null}")
    print(f"  Min: {min_v}% | Max: {max_v}% | Avg: {avg_v}%")

    # Histogram-style bucketing
    print("\n  Upside% histogram:")
    hist_rows = conn.execute(
        """SELECT
              CASE
                WHEN analyst_target_upside < -20 THEN '< -20%'
                WHEN analyst_target_upside < 0   THEN '-20% to 0%'
                WHEN analyst_target_upside < 15  THEN '0% to 15%'
                WHEN analyst_target_upside < 30  THEN '15% to 30%'
                WHEN analyst_target_upside < 50  THEN '30% to 50%'
                WHEN analyst_target_upside < 100 THEN '50% to 100%'
                ELSE '>= 100%'
              END as bin,
              COUNT(*) as n
           FROM signal_outcomes
           WHERE analyst_target_upside IS NOT NULL
           GROUP BY bin
           ORDER BY MIN(analyst_target_upside)"""
    ).fetchall()
    for bin_label, n in hist_rows:
        bar = "#" * min(n, 60)
        print(f"  {bin_label:>14}: {n:>4} {bar}")

    # --- 5. rating_count_30d vs outcome ---
    print("\n--- outcome_5d by analyst_rating_count_30d ---")
    rows = conn.execute(
        """SELECT
              CASE
                WHEN analyst_rating_count_30d = 0 THEN '0 (none)'
                WHEN analyst_rating_count_30d <= 2 THEN '1-2'
                WHEN analyst_rating_count_30d <= 5 THEN '3-5'
                ELSE '6+'
              END as bucket,
              COUNT(*) as n,
              ROUND(AVG(outcome_5d), 3) as avg_5d,
              ROUND(AVG(CASE WHEN outcome_5d > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) as win_rate
           FROM signal_outcomes
           WHERE outcome_5d IS NOT NULL
           GROUP BY bucket
           ORDER BY avg_5d DESC"""
    ).fetchall()
    print(f"  {'Count':<10} {'N':>5} {'Avg 5d%':>10} {'WinRate%':>10}")
    print(f"  {'-'*10} {'-'*5} {'-'*10} {'-'*10}")
    for bucket, n, avg_5d, wr in rows:
        avg_str = f"{avg_5d:.3f}" if avg_5d is not None else "N/A"
        wr_str = f"{wr:.1f}" if wr is not None else "N/A"
        print(f"  {bucket:<10} {n:>5} {avg_str:>10} {wr_str:>10}")


def main():
    print(f"DB: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    # Step 1: Add columns
    print("\n[1/3] Adding analyst columns to signal_outcomes...")
    add_columns_if_missing(conn)

    # Step 2: Backfill
    print("\n[2/3] Backfilling analyst data...")
    stats = backfill(conn)

    print("=" * 50)
    print("BACKFILL RESULTS")
    print("=" * 50)
    print(f"  Total signal_outcomes rows:   {stats['total']}")
    print(f"  Rows with ANY analyst data:   {stats['any_filled']} ({stats['any_filled']*100/stats['total']:.1f}%)")
    print(f"  analyst_action_7d filled:     {stats['action_7d_filled']}")
    print(f"  analyst_rating_count_30d > 0: {stats['rating_count_30d_filled']}")
    print(f"  analyst_target_upside filled: {stats['target_upside_filled']}")
    print(f"  analyst_bull_score filled:    {stats['bull_score_filled']}")

    # Step 3: Report correlations
    print("\n[3/3] Analyzing correlations...")
    report_correlations(conn)

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
