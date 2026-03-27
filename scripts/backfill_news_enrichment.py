#!/usr/bin/env python3
"""
backfill_news_enrichment.py
Backfill news-related columns in signal_outcomes and screener_rejections.

Join logic (no lookahead bias):
  For each (symbol, scan_date) row, find news published within 24h BEFORE scan_date.
  If multiple matches, take the most recent one.

  1. Try news_events first:
     - catalyst_type = event_type (or category as fallback)
     - news_sentiment = sentiment_score
     - news_impact_score = impact_score
  2. If no news_events match, fall back to stock_news:
     - news_sentiment = sentiment (VADER compound)
     - catalyst_type and news_impact_score remain NULL

Tables affected:
  - signal_outcomes  (catalyst_type, news_sentiment, news_impact_score)
  - screener_rejections (catalyst_type + adds news_sentiment, news_impact_score if missing)
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "trade_history.db")


def ensure_columns(conn):
    """Add news_sentiment and news_impact_score to screener_rejections if missing."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(screener_rejections)")
    existing = {r[1] for r in cur.fetchall()}

    added = []
    if "news_sentiment" not in existing:
        cur.execute("ALTER TABLE screener_rejections ADD COLUMN news_sentiment TEXT")
        added.append("news_sentiment")
    if "news_impact_score" not in existing:
        cur.execute("ALTER TABLE screener_rejections ADD COLUMN news_impact_score REAL")
        added.append("news_impact_score")

    if added:
        conn.commit()
        print(f"[schema] Added columns to screener_rejections: {added}")
    else:
        print("[schema] screener_rejections already has news_sentiment and news_impact_score")


def backfill_signal_outcomes(conn):
    """Backfill news columns in signal_outcomes."""
    cur = conn.cursor()

    # ----- Load all signal_outcomes rows that need filling -----
    cur.execute("""
        SELECT id, symbol, scan_date
        FROM signal_outcomes
        WHERE (catalyst_type IS NULL OR catalyst_type = '')
          AND (news_sentiment IS NULL OR news_sentiment = '')
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"\n[signal_outcomes] {total} rows to backfill")

    filled_news_events = 0
    filled_stock_news = 0
    skipped = 0

    for row_id, symbol, scan_date in rows:
        # scan_date is like '2026-02-05' (date only, ET).
        # We want news published within 24h before the start of the scan day.
        # Scan typically happens early morning ET, so window:
        #   FROM: scan_date - 1 day, 00:00 UTC  (covers previous day)
        #   TO:   scan_date + 0 day, 14:30 UTC   (= 09:30 ET, before market open)
        # Since news_events.published_at is in UTC (Z suffix),
        # we compare directly with UTC timestamps.
        #
        # Window: [scan_date - 1 day 00:00 UTC, scan_date 14:30 UTC)
        # This gives a ~38.5h window which is generous but avoids lookahead.
        window_start = f"{scan_date}T00:00:00Z"  # will be shifted by -1 day in SQL
        window_end = f"{scan_date}T14:30:00Z"

        # --- Try news_events first ---
        cur.execute("""
            SELECT event_type, category, sentiment_score, impact_score
            FROM news_events
            WHERE symbol = ?
              AND published_at >= datetime(?, '-1 day')
              AND published_at < ?
            ORDER BY published_at DESC
            LIMIT 1
        """, (symbol, window_start, window_end))

        ne_row = cur.fetchone()
        if ne_row:
            event_type, category, sentiment_score, impact_score = ne_row
            catalyst = event_type if event_type else category
            cur.execute("""
                UPDATE signal_outcomes
                SET catalyst_type = ?,
                    news_sentiment = ?,
                    news_impact_score = ?
                WHERE id = ?
            """, (catalyst, str(sentiment_score) if sentiment_score is not None else None,
                  impact_score, row_id))
            filled_news_events += 1
            continue

        # --- Fallback: stock_news ---
        # stock_news.published_at has timezone offset like '+00:00'
        # Normalize by comparing as text (both ISO-ish)
        cur.execute("""
            SELECT sentiment
            FROM stock_news
            WHERE symbol = ?
              AND published_at >= datetime(?, '-1 day')
              AND published_at < ?
            ORDER BY published_at DESC
            LIMIT 1
        """, (symbol, window_start, window_end))

        sn_row = cur.fetchone()
        if sn_row:
            sentiment = sn_row[0]
            cur.execute("""
                UPDATE signal_outcomes
                SET news_sentiment = ?
                WHERE id = ?
            """, (str(sentiment) if sentiment is not None else None, row_id))
            filled_stock_news += 1
            continue

        skipped += 1

    conn.commit()
    print(f"  Filled from news_events: {filled_news_events}")
    print(f"  Filled from stock_news:  {filled_stock_news}")
    print(f"  Total filled:            {filled_news_events + filled_stock_news}")
    print(f"  No match (NULL):         {skipped}")
    return filled_news_events, filled_stock_news, skipped


def backfill_screener_rejections(conn):
    """Backfill news columns in screener_rejections."""
    cur = conn.cursor()

    cur.execute("""
        SELECT id, symbol, scan_date
        FROM screener_rejections
        WHERE (catalyst_type IS NULL OR catalyst_type = '')
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"\n[screener_rejections] {total} rows to backfill")

    filled_news_events = 0
    filled_stock_news = 0
    skipped = 0

    batch_updates_ne = []
    batch_updates_sn = []

    for row_id, symbol, scan_date in rows:
        window_start = f"{scan_date}T00:00:00Z"
        window_end = f"{scan_date}T14:30:00Z"

        # --- Try news_events ---
        cur.execute("""
            SELECT event_type, category, sentiment_score, impact_score
            FROM news_events
            WHERE symbol = ?
              AND published_at >= datetime(?, '-1 day')
              AND published_at < ?
            ORDER BY published_at DESC
            LIMIT 1
        """, (symbol, window_start, window_end))

        ne_row = cur.fetchone()
        if ne_row:
            event_type, category, sentiment_score, impact_score = ne_row
            catalyst = event_type if event_type else category
            batch_updates_ne.append((
                catalyst,
                str(sentiment_score) if sentiment_score is not None else None,
                impact_score,
                row_id
            ))
            filled_news_events += 1

            # Flush in batches of 500
            if len(batch_updates_ne) >= 500:
                cur.executemany("""
                    UPDATE screener_rejections
                    SET catalyst_type = ?, news_sentiment = ?, news_impact_score = ?
                    WHERE id = ?
                """, batch_updates_ne)
                batch_updates_ne.clear()
            continue

        # --- Fallback: stock_news ---
        cur.execute("""
            SELECT sentiment
            FROM stock_news
            WHERE symbol = ?
              AND published_at >= datetime(?, '-1 day')
              AND published_at < ?
            ORDER BY published_at DESC
            LIMIT 1
        """, (symbol, window_start, window_end))

        sn_row = cur.fetchone()
        if sn_row:
            sentiment = sn_row[0]
            batch_updates_sn.append((
                str(sentiment) if sentiment is not None else None,
                row_id
            ))
            filled_stock_news += 1

            if len(batch_updates_sn) >= 500:
                cur.executemany("""
                    UPDATE screener_rejections
                    SET news_sentiment = ?
                    WHERE id = ?
                """, batch_updates_sn)
                batch_updates_sn.clear()
            continue

        skipped += 1

    # Flush remaining
    if batch_updates_ne:
        cur.executemany("""
            UPDATE screener_rejections
            SET catalyst_type = ?, news_sentiment = ?, news_impact_score = ?
            WHERE id = ?
        """, batch_updates_ne)
    if batch_updates_sn:
        cur.executemany("""
            UPDATE screener_rejections
            SET news_sentiment = ?
            WHERE id = ?
        """, batch_updates_sn)

    conn.commit()
    print(f"  Filled from news_events: {filled_news_events}")
    print(f"  Filled from stock_news:  {filled_stock_news}")
    print(f"  Total filled:            {filled_news_events + filled_stock_news}")
    print(f"  No match (NULL):         {skipped}")
    return filled_news_events, filled_stock_news, skipped


def print_summary(conn):
    """Print final fill-rate summary."""
    cur = conn.cursor()

    print("\n" + "=" * 60)
    print("FINAL FILL RATES")
    print("=" * 60)

    # signal_outcomes
    cur.execute("SELECT COUNT(*) FROM signal_outcomes")
    so_total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM signal_outcomes WHERE catalyst_type IS NOT NULL AND catalyst_type != ''")
    so_catalyst = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM signal_outcomes WHERE news_sentiment IS NOT NULL AND news_sentiment != ''")
    so_sentiment = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM signal_outcomes WHERE news_impact_score IS NOT NULL")
    so_impact = cur.fetchone()[0]

    print(f"\nsignal_outcomes ({so_total} rows):")
    print(f"  catalyst_type:    {so_catalyst}/{so_total} ({100*so_catalyst/so_total:.1f}%)")
    print(f"  news_sentiment:   {so_sentiment}/{so_total} ({100*so_sentiment/so_total:.1f}%)")
    print(f"  news_impact_score:{so_impact}/{so_total} ({100*so_impact/so_total:.1f}%)")

    # screener_rejections
    cur.execute("SELECT COUNT(*) FROM screener_rejections")
    sr_total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM screener_rejections WHERE catalyst_type IS NOT NULL AND catalyst_type != ''")
    sr_catalyst = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM screener_rejections WHERE news_sentiment IS NOT NULL AND news_sentiment != ''")
    sr_sentiment = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM screener_rejections WHERE news_impact_score IS NOT NULL")
    sr_impact = cur.fetchone()[0]

    print(f"\nscreener_rejections ({sr_total} rows):")
    print(f"  catalyst_type:    {sr_catalyst}/{sr_total} ({100*sr_catalyst/sr_total:.1f}%)")
    print(f"  news_sentiment:   {sr_sentiment}/{sr_total} ({100*sr_sentiment/sr_total:.1f}%)")
    print(f"  news_impact_score:{sr_impact}/{sr_total} ({100*sr_impact/sr_total:.1f}%)")

    # Sample filled rows
    print("\n--- Sample filled signal_outcomes ---")
    cur.execute("""
        SELECT symbol, scan_date, catalyst_type, news_sentiment, news_impact_score
        FROM signal_outcomes
        WHERE catalyst_type IS NOT NULL AND catalyst_type != ''
        ORDER BY scan_date DESC
        LIMIT 5
    """)
    for r in cur.fetchall():
        print(f"  {r[0]:6s} {r[1]} | catalyst={r[2]}, sentiment={r[3]}, impact={r[4]}")


def main():
    print(f"DB: {DB_PATH}")
    assert os.path.exists(DB_PATH), f"DB not found: {DB_PATH}"

    conn = None  # via get_session()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    try:
        ensure_columns(conn)
        backfill_signal_outcomes(conn)
        backfill_screener_rejections(conn)
        print_summary(conn)
    finally:
        conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
