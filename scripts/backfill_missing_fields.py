#!/usr/bin/env python3
"""
One-time backfill for missing fields across signal_outcomes, trades, and discovery_picks.

Fills:
  signal_outcomes: distance_from_20d_high, momentum_20d, new_score
  trades: new_score, momentum_20d, distance_from_high
  discovery_picks: put_call_ratio

Run manually: python3 scripts/backfill_missing_fields.py
"""
import os
import sys
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

import yfinance as yf
import numpy as np
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')


def compute_dip_score(dist_from_high: float, atr_pct: float, mom_5d: float, rsi: float) -> float:
    """v7.4 IC-weighted DIP quality score [0-100]. Mirrors _compute_dip_score() in screener."""
    norm_dist = max(0.0, 1.0 - dist_from_high / 25.0)
    norm_atr  = max(0.0, 1.0 - (atr_pct - 0.5) / 11.5)
    norm_mom  = max(0.0, min(1.0, (mom_5d + 20.0) / 25.0))
    norm_rsi  = max(0.0, 1.0 - (rsi - 20.0) / 60.0)
    score = (0.481 * norm_dist + 0.288 * norm_atr + 0.130 * norm_mom + 0.101 * norm_rsi) * 100
    return round(score, 1)


def fill_signal_outcomes_yfinance():
    """Fill distance_from_20d_high and momentum_20d from yfinance daily bars."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, symbol, scan_date, scan_price
        FROM signal_outcomes
        WHERE distance_from_20d_high IS NULL OR momentum_20d IS NULL
    """).fetchall()

    if not rows:
        print("  signal_outcomes: nothing to fill (distance_from_20d_high / momentum_20d)")
        conn.close()
        return

    print(f"  signal_outcomes: {len(rows)} rows need distance_from_20d_high / momentum_20d")

    # Group by symbol for batch download
    by_symbol = defaultdict(list)
    for r in rows:
        by_symbol[r['symbol']].append(dict(r))

    symbols = list(by_symbol.keys())
    min_date = min(r['scan_date'] for r in rows)
    start = (datetime.strptime(min_date, '%Y-%m-%d') - timedelta(days=40)).strftime('%Y-%m-%d')

    print(f"  Downloading {len(symbols)} symbols from {start}...")
    batch_size = 50
    filled = 0

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        batch_str = ' '.join(batch)
        try:
            data = yf.download(batch_str, start=start, interval='1d',
                               auto_adjust=True, progress=False, threads=False)
        except Exception as e:
            print(f"  Error downloading batch: {e}")
            continue

        if data.empty:
            continue

        for sym in batch:
            try:
                if len(batch) == 1:
                    df = data
                else:
                    if sym not in data.columns.get_level_values(1):
                        continue
                    df = data.xs(sym, axis=1, level=1)

                if df is None or df.empty:
                    continue

                for row in by_symbol.get(sym, []):
                    scan_dt = pd.Timestamp(row['scan_date'])
                    # Get data up to and including scan_date
                    hist = df[df.index <= scan_dt]
                    if len(hist) < 2:
                        continue

                    close = hist['Close'].values
                    high = hist['High'].values
                    price = float(close[-1])

                    updates = {}

                    # distance_from_20d_high: positive convention (0=at high, 5=5% below)
                    if len(high) >= 2:
                        high_20d = float(np.max(high[-20:])) if len(high) >= 20 else float(np.max(high))
                        dist = (1.0 - price / high_20d) * 100 if high_20d > 0 else 0
                        updates['distance_from_20d_high'] = round(max(0, dist), 2)

                    # momentum_20d
                    if len(close) >= 21:
                        mom20 = (close[-1] / close[-21] - 1) * 100
                        updates['momentum_20d'] = round(float(mom20), 2)

                    if updates:
                        set_parts = ', '.join(f"{k}=?" for k in updates)
                        vals = list(updates.values()) + [row['id']]
                        conn.execute(f"UPDATE signal_outcomes SET {set_parts} WHERE id=?", vals)
                        filled += 1

            except Exception as e:
                print(f"  Error {sym}: {e}")
                continue

    conn.commit()
    conn.close()
    print(f"  signal_outcomes: filled {filled} rows (distance_from_20d_high / momentum_20d)")


def fill_signal_outcomes_new_score():
    """Compute new_score for signal_outcomes rows that have the required features."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, distance_from_20d_high, atr_pct, momentum_5d, entry_rsi
        FROM signal_outcomes
        WHERE new_score IS NULL
          AND distance_from_20d_high IS NOT NULL
          AND atr_pct IS NOT NULL
          AND momentum_5d IS NOT NULL
          AND entry_rsi IS NOT NULL
    """).fetchall()

    if not rows:
        print("  signal_outcomes: nothing to fill (new_score)")
        conn.close()
        return

    filled = 0
    for r in rows:
        # distance_from_20d_high in signal_outcomes uses positive convention
        score = compute_dip_score(r['distance_from_20d_high'], r['atr_pct'],
                                  r['momentum_5d'], r['entry_rsi'])
        conn.execute("UPDATE signal_outcomes SET new_score=? WHERE id=?", (score, r['id']))
        filled += 1

    conn.commit()
    conn.close()
    print(f"  signal_outcomes: filled {filled} new_score values")


def fill_trades_from_signal_outcomes():
    """Backfill trades columns from signal_outcomes (new_score, momentum_20d, distance_from_high)."""
    conn = sqlite3.connect(DB_PATH)

    # new_score
    r1 = conn.execute("""
        UPDATE trades SET new_score = (
            SELECT so.new_score FROM signal_outcomes so
            WHERE so.symbol = trades.symbol AND so.scan_date = trades.date
              AND so.new_score IS NOT NULL AND so.action_taken = 'BOUGHT'
            LIMIT 1
        ) WHERE action='BUY' AND new_score IS NULL
    """)
    print(f"  trades.new_score: filled {r1.rowcount}")

    # momentum_20d
    r2 = conn.execute("""
        UPDATE trades SET momentum_20d = (
            SELECT so.momentum_20d FROM signal_outcomes so
            WHERE so.symbol = trades.symbol AND so.scan_date = trades.date
              AND so.momentum_20d IS NOT NULL AND so.action_taken = 'BOUGHT'
            LIMIT 1
        ) WHERE action='BUY' AND momentum_20d IS NULL
    """)
    print(f"  trades.momentum_20d: filled {r2.rowcount}")

    # distance_from_high (signal_outcomes uses positive conv, trades uses same)
    r3 = conn.execute("""
        UPDATE trades SET distance_from_high = (
            SELECT so.distance_from_high FROM signal_outcomes so
            WHERE so.symbol = trades.symbol AND so.scan_date = trades.date
              AND so.distance_from_high IS NOT NULL AND so.action_taken = 'BOUGHT'
            LIMIT 1
        ) WHERE action='BUY' AND distance_from_high IS NULL
    """)
    print(f"  trades.distance_from_high: filled {r3.rowcount}")

    conn.commit()
    conn.close()


def fill_discovery_put_call():
    """Fill discovery_picks.put_call_ratio from options_flow table."""
    conn = sqlite3.connect(DB_PATH)
    r = conn.execute("""
        UPDATE discovery_picks SET put_call_ratio = (
            SELECT of2.put_call_ratio FROM options_flow of2
            WHERE of2.symbol = discovery_picks.symbol
            ORDER BY of2.date DESC LIMIT 1
        ) WHERE put_call_ratio IS NULL
    """)
    conn.commit()
    print(f"  discovery_picks.put_call_ratio: filled {r.rowcount}")
    conn.close()


if __name__ == '__main__':
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Backfill missing fields")
    print()

    print("Step 1: signal_outcomes — yfinance (distance_from_20d_high, momentum_20d)")
    fill_signal_outcomes_yfinance()
    print()

    print("Step 2: signal_outcomes — new_score (compute from features)")
    fill_signal_outcomes_new_score()
    print()

    print("Step 3: trades — propagate from signal_outcomes")
    fill_trades_from_signal_outcomes()
    print()

    print("Step 4: discovery_picks — put_call_ratio")
    fill_discovery_put_call()
    print()

    print("Done.")
