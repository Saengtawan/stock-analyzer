"""resonance / universe / update_daily.py — keep the EXTRAS' daily coil history fresh.

The resonance coil feature measures each name's compression vs its own daily "normal", so the
`resonance_universe` extras need their daily OHLC kept current. The existing `update_stock_ohlc`
cron only refreshes `universe_stocks` (core) — it never touches the ~1000 resonance-only extras.
This module fills exactly that gap: it appends the most-recent completed session(s) of DAILY OHLC
for `resonance_universe` (status='active') symbols into the SHARED `stock_daily_ohlc` table.

SAFE / additive, like backfill_bars:
  - auto_trading derives its tradable list from `universe_stocks`, not from any bar table, so extra
    daily rows for extra symbols never change what it trades.
  - writes use INSERT OR IGNORE against UNIQUE(symbol, date): existing rows (core or extra) are
    never overwritten, and re-runs are idempotent.

A short trailing window (default 7 calendar days) is pulled so weekends/holidays are handled and a
missed run self-heals; only genuinely-missing (symbol, date) rows are added.

CLI:  python -m resonance.universe.update_daily
      python -m resonance.universe.update_daily --days 7
"""
from __future__ import annotations

import argparse
import datetime
import sqlite3

from resonance.universe.backfill_bars import DB, _data_client, _load_env


def update_daily(days=7, db=DB, verbose=True):
    """Append the last `days` of daily OHLC for resonance_universe extras. Returns a stats dict."""
    _load_env()
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.enums import Adjustment
    from alpaca.data.timeframe import TimeFrame

    conn = sqlite3.connect(db)
    syms = [r[0] for r in conn.execute(
        "SELECT symbol FROM resonance_universe WHERE status='active' ORDER BY symbol")]
    db_latest_before = conn.execute("SELECT MAX(date) FROM stock_daily_ohlc").fetchone()[0]
    if verbose:
        print(f"update_daily: {len(syms)} resonance extras  |  DB latest daily = {db_latest_before}")

    end = datetime.date.today()
    start = end - datetime.timedelta(days=int(days))

    import time
    dc = _data_client()
    total_added = 0
    syms_with_rows = 0
    BATCH = 100
    for i in range(0, len(syms), BATCH):
        batch = syms[i:i + BATCH]
        # Retry with backoff, then FALL BACK sip -> iex. The live extras daily stalled at 07-31
        # because every SIP batch threw APIError (free-SIP recent-data restriction / entitlement)
        # with no retry and no fallback -> +0 rows -> coil features computed on stale daily. IEX
        # daily is available on the basic plan and enough for the extras' OHLC. (Same fix as
        # build_universe.fetch_dollar_vol.)
        df = None
        for feed in ("sip", "iex"):
            for attempt in range(3):
                try:
                    req = StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day,
                                           start=start, end=end, adjustment=Adjustment.ALL, feed=feed)
                    df = dc.get_stock_bars(req).df
                    break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
                        continue
                    if verbose:
                        print(f"  [warn] batch {i}-{i+len(batch)} feed={feed} failed after 3 tries: {type(e).__name__}")
            if df is not None:
                break
        if df is None or df.empty:
            continue
        rows = []
        for (sym, ts), r in df.iterrows():
            d = ts.date().isoformat()   # daily bar session date == trading date
            rows.append((str(sym), d, float(r["open"]), float(r["high"]),
                         float(r["low"]), float(r["close"]), int(r["volume"])))
        before = conn.total_changes
        conn.executemany(
            """INSERT OR IGNORE INTO stock_daily_ohlc
                   (symbol, date, open, high, low, close, volume)
               VALUES (?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
        total_added += conn.total_changes - before
        syms_with_rows += df.index.get_level_values("symbol").nunique()

    db_latest_after = conn.execute("SELECT MAX(date) FROM stock_daily_ohlc").fetchone()[0]
    conn.close()
    stats = {"extras": len(syms), "rows_added": total_added, "symbols_touched": syms_with_rows,
             "db_latest_before": db_latest_before, "db_latest_after": db_latest_after}
    if verbose:
        print("=" * 64)
        print(f"update_daily done: +{total_added} rows across ~{syms_with_rows} extras  |  "
              f"DB latest {db_latest_before} -> {db_latest_after}")
    return stats


def main():
    ap = argparse.ArgumentParser(description="append recent daily OHLC for resonance_universe extras")
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()
    update_daily(a.days)


if __name__ == "__main__":
    main()
