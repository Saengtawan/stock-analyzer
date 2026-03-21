#!/usr/bin/env python3
"""
fix_data_quality.py — Fix known data quality issues in Discovery Engine DB.

Issues addressed:
  1. NULL vix_close on 2026-03-13 in macro_snapshots
  2. Deduplicate signal_outcomes on (symbol, scan_date)
  3. volume_ratio = 0 for HUBB 2026-02-24 in backfill_signal_outcomes
  4. NULL momentum_20d for 4 rows in backfill_signal_outcomes
  5. Spot-check outcome_5d against stocks.db prices

Run: python scripts/fix_data_quality.py
"""
import sqlite3
import sys
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
STOCKS_DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'database', 'stocks.db')

DB_PATH = os.path.abspath(DB_PATH)
STOCKS_DB = os.path.abspath(STOCKS_DB)

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def fix_vix_close_march13(conn):
    """Issue 1: NULL vix_close on 2026-03-13 in macro_snapshots."""
    section("Issue 1: NULL vix_close on 2026-03-13")

    cur = conn.execute(
        "SELECT id, date, vix_close, vix3m_close, spy_close, yield_10y "
        "FROM macro_snapshots WHERE date = '2026-03-13'"
    )
    row = cur.fetchone()
    if not row:
        print("  [SKIP] No row for 2026-03-13 in macro_snapshots")
        return

    row_id, date, vix_close, vix3m_close, spy_close, yield_10y = row
    print(f"  Current row: id={row_id}, date={date}")
    print(f"    vix_close={vix_close}, vix3m_close={vix3m_close}")
    print(f"    spy_close={spy_close}, yield_10y={yield_10y}")

    if vix_close is not None:
        print(f"  [SKIP] vix_close already filled: {vix_close}")
        return

    # Try yfinance
    vix_value = None
    try:
        import yfinance as yf
        vix_data = yf.Ticker('^VIX').history(start='2026-03-13', end='2026-03-14')
        if not vix_data.empty:
            vix_value = round(float(vix_data['Close'].iloc[0]), 2)
            print(f"  [yfinance] VIX close for 2026-03-13: {vix_value}")
        else:
            print("  [yfinance] No data returned for 2026-03-13")
    except Exception as e:
        print(f"  [yfinance] Failed: {e}")

    # Fallback: interpolate from surrounding dates
    if vix_value is None:
        print("  Falling back to interpolation from surrounding dates...")
        cur = conn.execute(
            "SELECT date, vix_close FROM macro_snapshots "
            "WHERE date IN ('2026-03-12', '2026-03-14') AND vix_close IS NOT NULL "
            "ORDER BY date"
        )
        neighbors = cur.fetchall()
        if len(neighbors) == 2:
            vix_value = round((neighbors[0][1] + neighbors[1][1]) / 2, 2)
            print(f"  Interpolated from {neighbors[0][0]}={neighbors[0][1]} "
                  f"and {neighbors[1][0]}={neighbors[1][1]}: {vix_value}")
        elif len(neighbors) == 1:
            # Only one neighbor available — use it
            vix_value = neighbors[0][1]
            print(f"  Only neighbor {neighbors[0][0]}={neighbors[0][1]}, using that: {vix_value}")
        else:
            print("  [SKIP] No neighboring data to interpolate from")
            return

    # Also fill regime_label if it is NULL
    cur = conn.execute(
        "SELECT regime_label FROM macro_snapshots WHERE date = '2026-03-13'"
    )
    regime = cur.fetchone()[0]

    conn.execute(
        "UPDATE macro_snapshots SET vix_close = ? WHERE date = '2026-03-13'",
        (vix_value,)
    )
    print(f"  [FIXED] SET vix_close = {vix_value} for 2026-03-13")

    # Determine regime_label based on VIX value
    if regime is None and vix_value is not None:
        if vix_value < 20:
            label = 'NORMAL'
        elif vix_value < 24:
            label = 'SKIP'
        elif vix_value < 38:
            label = 'HIGH'
        else:
            label = 'EXTREME'
        conn.execute(
            "UPDATE macro_snapshots SET regime_label = ? WHERE date = '2026-03-13'",
            (label,)
        )
        print(f"  [FIXED] SET regime_label = '{label}' for 2026-03-13 (derived from VIX={vix_value})")


def deduplicate_signal_outcomes(conn):
    """Issue 2: Deduplicate signal_outcomes on (symbol, scan_date)."""
    section("Issue 2: Deduplicate signal_outcomes")

    cur = conn.execute(
        "SELECT symbol, scan_date, COUNT(*) as cnt "
        "FROM signal_outcomes GROUP BY symbol, scan_date HAVING cnt > 1"
    )
    dups = cur.fetchall()

    if not dups:
        print("  [SKIP] No duplicate (symbol, scan_date) pairs found")
        return

    print(f"  Found {len(dups)} duplicate (symbol, scan_date) pairs:")
    for symbol, scan_date, cnt in dups:
        print(f"    {symbol} / {scan_date}: {cnt} rows")

    # Check if they actually have different signal_source (legitimate multi-source)
    print("\n  Checking if duplicates have different signal_source (legitimate)...")
    truly_dup = []
    multi_source = []

    for symbol, scan_date, cnt in dups:
        cur = conn.execute(
            "SELECT id, signal_source, action_taken, scan_price, outcome_1d, outcome_5d "
            "FROM signal_outcomes "
            "WHERE symbol = ? AND scan_date = ? ORDER BY id",
            (symbol, scan_date)
        )
        rows = cur.fetchall()
        sources = set(r[1] for r in rows)

        if len(sources) == cnt:
            # Each row has a different signal_source — this is legitimate
            multi_source.append((symbol, scan_date, rows))
        else:
            truly_dup.append((symbol, scan_date, rows))

    if multi_source:
        print(f"\n  {len(multi_source)} pairs have different signal_source (legitimate, not deduplicating):")
        for symbol, scan_date, rows in multi_source:
            sources = [r[1] for r in rows]
            print(f"    {symbol} / {scan_date}: sources={sources}")

    if truly_dup:
        print(f"\n  {len(truly_dup)} pairs are true duplicates (same signal_source):")
        total_deleted = 0
        for symbol, scan_date, rows in truly_dup:
            # Group by signal_source
            by_source = {}
            for r in rows:
                src = r[1]
                by_source.setdefault(src, []).append(r)

            for src, src_rows in by_source.items():
                if len(src_rows) <= 1:
                    continue

                # Keep the row with the most non-NULL columns
                def count_filled(row):
                    return sum(1 for v in row if v is not None)

                src_rows.sort(key=lambda r: (count_filled(r), r[0]), reverse=True)
                keep = src_rows[0]
                delete_ids = [r[0] for r in src_rows[1:]]
                print(f"    {symbol}/{scan_date}/{src}: keeping id={keep[0]}, deleting ids={delete_ids}")
                conn.execute(
                    f"DELETE FROM signal_outcomes WHERE id IN ({','.join('?' * len(delete_ids))})",
                    delete_ids
                )
                total_deleted += len(delete_ids)

        print(f"  [FIXED] Deleted {total_deleted} truly duplicate rows")
    else:
        print("\n  All duplicates are multi-source (legitimate). No deletions needed.")


def fix_hubb_volume_ratio(conn):
    """Issue 3: volume_ratio = 0 for HUBB on 2026-02-24 in backfill_signal_outcomes."""
    section("Issue 3: HUBB volume_ratio = 0 on 2026-02-24")

    cur = conn.execute(
        "SELECT id, scan_date, symbol, volume_ratio, scan_price "
        "FROM backfill_signal_outcomes "
        "WHERE symbol = 'HUBB' AND scan_date = '2026-02-24'"
    )
    row = cur.fetchone()
    if not row:
        print("  [SKIP] No row for HUBB/2026-02-24")
        return

    row_id, scan_date, symbol, vol_ratio, scan_price = row
    print(f"  Current: id={row_id}, volume_ratio={vol_ratio}, scan_price={scan_price}")

    if vol_ratio != 0.0 and vol_ratio is not None:
        print(f"  [SKIP] volume_ratio already non-zero: {vol_ratio}")
        return

    # Try to compute from stocks.db
    computed = None
    if os.path.exists(STOCKS_DB):
        sconn = sqlite3.connect(STOCKS_DB)
        try:
            # Check if we have HUBB data near that date
            scur = sconn.execute(
                "SELECT date, volume FROM stock_prices "
                "WHERE symbol = 'HUBB' AND date <= '2026-02-24' "
                "ORDER BY date DESC LIMIT 21"
            )
            prices = scur.fetchall()
            if len(prices) >= 21:
                # Day's volume / avg of prior 20 days
                day_vol = prices[0][1]
                avg_vol = sum(p[1] for p in prices[1:21]) / 20
                if avg_vol > 0:
                    computed = round(day_vol / avg_vol, 4)
                    print(f"  Computed from stocks.db: day_vol={day_vol}, avg_20d={avg_vol:.0f}, ratio={computed}")
            else:
                print(f"  stocks.db has only {len(prices)} rows for HUBB up to 2026-02-24 (need 21)")
                if prices:
                    print(f"  Latest HUBB date in stocks.db: {prices[0][0]}")
                else:
                    print("  No HUBB data in stocks.db")
        finally:
            sconn.close()

    if computed is not None:
        conn.execute(
            "UPDATE backfill_signal_outcomes SET volume_ratio = ? WHERE id = ?",
            (computed, row_id)
        )
        print(f"  [FIXED] SET volume_ratio = {computed}")
    else:
        # Set to NULL — honest about missing data
        conn.execute(
            "UPDATE backfill_signal_outcomes SET volume_ratio = NULL WHERE id = ?",
            (row_id,)
        )
        print("  [FIXED] SET volume_ratio = NULL (no price data available to compute, NULL is honest)")


def fix_null_momentum_20d(conn):
    """Issue 4: Fix 4 NULL momentum_20d rows in backfill_signal_outcomes."""
    section("Issue 4: NULL momentum_20d in backfill_signal_outcomes")

    targets = [
        ('CTSH', '2025-10-22'),
        ('BOH', '2025-11-06'),
        ('KEY', '2025-11-21'),
        ('BLBD', '2025-12-24'),
    ]

    if not os.path.exists(STOCKS_DB):
        print(f"  [SKIP] stocks.db not found at {STOCKS_DB}")
        return

    sconn = sqlite3.connect(STOCKS_DB)
    fixed_count = 0

    for symbol, scan_date in targets:
        cur = conn.execute(
            "SELECT id, momentum_20d, scan_price FROM backfill_signal_outcomes "
            "WHERE symbol = ? AND scan_date = ?",
            (symbol, scan_date)
        )
        row = cur.fetchone()
        if not row:
            print(f"  [{symbol}/{scan_date}] No row found")
            continue

        row_id, current_mom, scan_price = row
        if current_mom is not None:
            print(f"  [{symbol}/{scan_date}] Already filled: {current_mom}")
            continue

        # Try to compute momentum_20d from stocks.db
        # momentum_20d = (close_today / close_20_trading_days_ago - 1) * 100
        scur = sconn.execute(
            "SELECT date, close FROM stock_prices "
            "WHERE symbol = ? AND date <= ? "
            "ORDER BY date DESC LIMIT 21",
            (symbol, scan_date)
        )
        prices = scur.fetchall()

        if len(prices) >= 21:
            close_today = prices[0][1]
            close_20d_ago = prices[20][1]
            mom_20d = round((close_today / close_20d_ago - 1) * 100, 2)
            print(f"  [{symbol}/{scan_date}] close={close_today} ({prices[0][0]}), "
                  f"close_20d_ago={close_20d_ago} ({prices[20][0]}), momentum_20d={mom_20d}")

            conn.execute(
                "UPDATE backfill_signal_outcomes SET momentum_20d = ? WHERE id = ?",
                (mom_20d, row_id)
            )
            print(f"  [{symbol}/{scan_date}] [FIXED] SET momentum_20d = {mom_20d}")
            fixed_count += 1
        else:
            avail = len(prices)
            if prices:
                print(f"  [{symbol}/{scan_date}] Only {avail} rows in stocks.db "
                      f"(latest: {prices[0][0]}). Cannot compute. Leaving NULL.")
            else:
                print(f"  [{symbol}/{scan_date}] No data for {symbol} in stocks.db. Leaving NULL.")

    sconn.close()
    print(f"\n  Summary: fixed {fixed_count}/{len(targets)} rows")


def spot_check_outcome_5d(conn):
    """Issue 5: Spot-check 10 random outcome_5d values against stocks.db prices."""
    section("Issue 5: Spot-check outcome_5d vs stocks.db")

    if not os.path.exists(STOCKS_DB):
        print(f"  [SKIP] stocks.db not found at {STOCKS_DB}")
        return

    sconn = sqlite3.connect(STOCKS_DB)

    # Get 10 random rows with non-NULL outcome_5d
    cur = conn.execute(
        "SELECT id, scan_date, symbol, scan_price, outcome_5d "
        "FROM backfill_signal_outcomes "
        "WHERE outcome_5d IS NOT NULL "
        "ORDER BY RANDOM() LIMIT 10"
    )
    rows = cur.fetchall()

    if not rows:
        print("  [SKIP] No rows with outcome_5d to check")
        sconn.close()
        return

    print(f"  Checking {len(rows)} random rows...\n")
    print(f"  {'Symbol':<8} {'ScanDate':<12} {'Stored%':>8} {'Computed%':>10} {'Diff%':>8} {'Status'}")
    print(f"  {'-'*8} {'-'*12} {'-'*8} {'-'*10} {'-'*8} {'-'*10}")

    discrepancies = []
    checked = 0
    skipped = 0

    for row_id, scan_date, symbol, scan_price, stored_outcome in rows:
        # Find the close price ~5 trading days after scan_date
        scur = sconn.execute(
            "SELECT date, close FROM stock_prices "
            "WHERE symbol = ? AND date > ? "
            "ORDER BY date ASC LIMIT 5",
            (symbol, scan_date)
        )
        future_prices = scur.fetchall()

        if len(future_prices) < 5:
            # Also check close on scan_date as reference
            scur = sconn.execute(
                "SELECT close FROM stock_prices WHERE symbol = ? AND date = ?",
                (symbol, scan_date)
            )
            scan_close = scur.fetchone()
            print(f"  {symbol:<8} {scan_date:<12} {stored_outcome:>8.2f} {'N/A':>10} {'N/A':>8} "
                  f"SKIP (only {len(future_prices)} future bars in stocks.db)")
            skipped += 1
            continue

        # Get the scan-day close for reference
        scur = sconn.execute(
            "SELECT close FROM stock_prices WHERE symbol = ? AND date = ?",
            (symbol, scan_date)
        )
        scan_day_close = scur.fetchone()
        if scan_day_close is None:
            print(f"  {symbol:<8} {scan_date:<12} {stored_outcome:>8.2f} {'N/A':>10} {'N/A':>8} "
                  f"SKIP (no scan-date close)")
            skipped += 1
            continue

        base_price = scan_day_close[0]
        day5_close = future_prices[4][1]
        day5_date = future_prices[4][0]
        computed = round((day5_close / base_price - 1) * 100, 2)
        diff = round(abs(stored_outcome - computed), 2)

        status = "OK" if diff <= 0.5 else "MISMATCH"
        if status == "MISMATCH":
            discrepancies.append((symbol, scan_date, stored_outcome, computed, diff, day5_date))

        print(f"  {symbol:<8} {scan_date:<12} {stored_outcome:>8.2f} {computed:>10.2f} {diff:>8.2f} {status}"
              f"  (base={base_price:.2f}, d5={day5_close:.2f} @ {day5_date})")
        checked += 1

    print(f"\n  Checked: {checked}, Skipped: {skipped}")
    if discrepancies:
        print(f"\n  ** {len(discrepancies)} DISCREPANCIES (diff > 0.5%) found:")
        for sym, sd, stored, computed, diff, d5d in discrepancies:
            print(f"     {sym} {sd}: stored={stored:.2f}%, computed={computed:.2f}%, diff={diff:.2f}%")
        print("\n  NOTE: Discrepancies may be due to scan_price vs close price difference")
        print("        (backfill uses scan_price; spot-check uses close).")
        print("        Only flag if the pattern is systematic.")
    else:
        print("  No discrepancies found (all within 0.5%).")

    sconn.close()


def main():
    print("=" * 60)
    print("  Discovery Engine Data Quality Fix Script")
    print(f"  DB: {DB_PATH}")
    print(f"  Stocks DB: {STOCKS_DB}")
    print(f"  Run at: {datetime.now().isoformat()}")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        fix_vix_close_march13(conn)
        deduplicate_signal_outcomes(conn)
        fix_hubb_volume_ratio(conn)
        fix_null_momentum_20d(conn)
        conn.commit()
        print("\n  ** All fixes committed to DB **")

        # Spot check is read-only, run after commit
        spot_check_outcome_5d(conn)

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()

    print("\n" + "=" * 60)
    print("  Done.")
    print("=" * 60)


if __name__ == '__main__':
    main()
