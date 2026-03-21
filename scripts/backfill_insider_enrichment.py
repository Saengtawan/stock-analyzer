#!/usr/bin/env python3
"""
Backfill insider_buy_30d_value and insider_buy_days_ago
into signal_outcomes and screener_rejections tables.

Logic:
  For each (symbol, scan_date) row, find insider_transactions where:
    - same symbol
    - transaction_date within 30 days BEFORE scan_date
    - transaction_type = 'purchase' (all rows are purchases in this dataset)
  Then:
    - insider_buy_30d_value = SUM(total_value) across matching buys
    - insider_buy_days_ago  = days between most recent buy and scan_date
    - If no insider buys found, leave NULL
"""

import sqlite3
from datetime import datetime

DB_PATH = "data/trade_history.db"


def backfill_table(conn, table_name):
    """Backfill insider columns for a given table (signal_outcomes or screener_rejections)."""
    cur = conn.cursor()

    # Get all distinct (id, symbol, scan_date) rows that need filling
    cur.execute(f"""
        SELECT id, symbol, scan_date
        FROM {table_name}
        WHERE insider_buy_30d_value IS NULL
    """)
    rows = cur.fetchall()
    print(f"\n{'='*60}")
    print(f"  {table_name}: {len(rows)} rows to process")
    print(f"{'='*60}")

    if not rows:
        print("  Nothing to backfill.")
        return 0, 0

    # Pre-load all insider transactions into memory for fast lookup
    cur.execute("""
        SELECT symbol, transaction_date, total_value
        FROM insider_transactions
        ORDER BY symbol, transaction_date DESC
    """)
    insider_data = cur.fetchall()

    # Build lookup: symbol -> list of (transaction_date_str, total_value)
    from collections import defaultdict
    insider_by_symbol = defaultdict(list)
    for sym, tdate, tval in insider_data:
        insider_by_symbol[sym].append((tdate, tval))

    updated = 0
    matched = 0

    for row_id, symbol, scan_date in rows:
        if symbol not in insider_by_symbol:
            continue

        # Filter to 30-day window before scan_date
        scan_dt = datetime.strptime(scan_date, "%Y-%m-%d")
        buys_in_window = []
        for tdate_str, tval in insider_by_symbol[symbol]:
            tdt = datetime.strptime(tdate_str, "%Y-%m-%d")
            days_diff = (scan_dt - tdt).days
            if 0 <= days_diff <= 30:
                buys_in_window.append((days_diff, tval))

        if not buys_in_window:
            continue

        total_value = sum(v for _, v in buys_in_window)
        most_recent_days_ago = min(d for d, _ in buys_in_window)

        cur.execute(f"""
            UPDATE {table_name}
            SET insider_buy_30d_value = ?,
                insider_buy_days_ago = ?
            WHERE id = ?
        """, (round(total_value, 2), most_recent_days_ago, row_id))

        matched += 1
        updated += 1

    conn.commit()
    print(f"  Rows with insider buy data: {matched}")
    print(f"  Rows updated: {updated}")
    print(f"  Rows left NULL (no insider buys in window): {len(rows) - matched}")
    return len(rows), matched


def print_summary(conn):
    """Print summary statistics after backfill."""
    cur = conn.cursor()

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")

    # signal_outcomes fill rate
    cur.execute("SELECT COUNT(*) FROM signal_outcomes")
    total_so = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM signal_outcomes WHERE insider_buy_30d_value IS NOT NULL")
    filled_so = cur.fetchone()[0]
    print(f"\n  signal_outcomes: {filled_so}/{total_so} rows have insider buy data ({100*filled_so/total_so:.1f}%)")

    # screener_rejections fill rate
    cur.execute("SELECT COUNT(*) FROM screener_rejections")
    total_sr = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM screener_rejections WHERE insider_buy_30d_value IS NOT NULL")
    filled_sr = cur.fetchone()[0]
    print(f"  screener_rejections: {filled_sr}/{total_sr} rows have insider buy data ({100*filled_sr/total_sr:.1f}%)")

    # Average insider_buy_30d_value when present (signal_outcomes)
    cur.execute("""
        SELECT AVG(insider_buy_30d_value), MIN(insider_buy_30d_value), MAX(insider_buy_30d_value),
               COUNT(DISTINCT symbol)
        FROM signal_outcomes
        WHERE insider_buy_30d_value IS NOT NULL
    """)
    avg_val, min_val, max_val, n_symbols = cur.fetchone()
    if avg_val:
        print(f"\n  signal_outcomes insider buy stats (when present):")
        print(f"    Avg value:   ${avg_val:,.0f}")
        print(f"    Min value:   ${min_val:,.0f}")
        print(f"    Max value:   ${max_val:,.0f}")
        print(f"    Unique symbols: {n_symbols}")

    cur.execute("""
        SELECT AVG(insider_buy_days_ago), MIN(insider_buy_days_ago), MAX(insider_buy_days_ago)
        FROM signal_outcomes
        WHERE insider_buy_days_ago IS NOT NULL
    """)
    avg_days, min_days, max_days = cur.fetchone()
    if avg_days is not None:
        print(f"    Avg days ago: {avg_days:.1f}")
        print(f"    Min days ago: {min_days}")
        print(f"    Max days ago: {max_days}")

    # Detail: which symbols in signal_outcomes have insider buys
    cur.execute("""
        SELECT symbol, scan_date, insider_buy_30d_value, insider_buy_days_ago
        FROM signal_outcomes
        WHERE insider_buy_30d_value IS NOT NULL
        ORDER BY insider_buy_30d_value DESC
    """)
    rows = cur.fetchall()
    if rows:
        print(f"\n  signal_outcomes rows with insider buy data:")
        print(f"    {'Symbol':<8} {'Scan Date':<12} {'30d Value':>14} {'Days Ago':>9}")
        print(f"    {'-'*8} {'-'*12} {'-'*14} {'-'*9}")
        for sym, sd, val, days in rows:
            print(f"    {sym:<8} {sd:<12} ${val:>12,.0f} {days:>9}")

    # Outcome analysis: do stocks with insider buys have better outcome_5d?
    print(f"\n{'='*60}")
    print("  OUTCOME ANALYSIS: Insider Buys vs No Insider Buys")
    print(f"{'='*60}")

    cur.execute("""
        SELECT
            CASE WHEN insider_buy_30d_value IS NOT NULL THEN 'With Insider Buy'
                 ELSE 'No Insider Buy' END AS grp,
            COUNT(*) AS n,
            AVG(outcome_1d) AS avg_1d,
            AVG(outcome_5d) AS avg_5d,
            AVG(outcome_max_gain_5d) AS avg_max_gain,
            AVG(outcome_max_dd_5d) AS avg_max_dd,
            SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(outcome_5d) AS win_rate_5d
        FROM signal_outcomes
        WHERE outcome_5d IS NOT NULL
        GROUP BY grp
    """)
    results = cur.fetchall()
    print(f"\n    {'Group':<20} {'N':>5} {'Avg 1d%':>9} {'Avg 5d%':>9} {'MaxGain%':>9} {'MaxDD%':>9} {'WR 5d%':>8}")
    print(f"    {'-'*20} {'-'*5} {'-'*9} {'-'*9} {'-'*9} {'-'*9} {'-'*8}")
    for grp, n, a1, a5, mg, md, wr in results:
        a1_s = f"{a1:.2f}" if a1 is not None else "N/A"
        a5_s = f"{a5:.2f}" if a5 is not None else "N/A"
        mg_s = f"{mg:.2f}" if mg is not None else "N/A"
        md_s = f"{md:.2f}" if md is not None else "N/A"
        wr_s = f"{wr:.1f}" if wr is not None else "N/A"
        print(f"    {grp:<20} {n:>5} {a1_s:>9} {a5_s:>9} {mg_s:>9} {md_s:>9} {wr_s:>8}")

    # Same for screener_rejections
    cur.execute("""
        SELECT
            CASE WHEN insider_buy_30d_value IS NOT NULL THEN 'With Insider Buy'
                 ELSE 'No Insider Buy' END AS grp,
            COUNT(*) AS n,
            AVG(outcome_1d) AS avg_1d,
            AVG(outcome_5d) AS avg_5d,
            SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(outcome_5d), 0) AS win_rate_5d
        FROM screener_rejections
        WHERE outcome_5d IS NOT NULL
        GROUP BY grp
    """)
    results = cur.fetchall()
    if results:
        print(f"\n  screener_rejections outcome comparison:")
        print(f"    {'Group':<20} {'N':>5} {'Avg 1d%':>9} {'Avg 5d%':>9} {'WR 5d%':>8}")
        print(f"    {'-'*20} {'-'*5} {'-'*9} {'-'*9} {'-'*8}")
        for grp, n, a1, a5, wr in results:
            a1_s = f"{a1:.2f}" if a1 is not None else "N/A"
            a5_s = f"{a5:.2f}" if a5 is not None else "N/A"
            wr_s = f"{wr:.1f}" if wr is not None else "N/A"
            print(f"    {grp:<20} {n:>5} {a1_s:>9} {a5_s:>9} {wr_s:>8}")


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        # Backfill signal_outcomes
        so_total, so_matched = backfill_table(conn, "signal_outcomes")

        # Backfill screener_rejections (only NULL rows)
        sr_total, sr_matched = backfill_table(conn, "screener_rejections")

        # Print summary
        print_summary(conn)

    finally:
        conn.close()

    print(f"\nDone.")


if __name__ == "__main__":
    main()
