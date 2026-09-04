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
    import yfinance as yf
    import time

    # NOTE: this DB has several cron writers and three live readers. Without a busy timeout a
    # transient lock raises OperationalError and the job dies silently — cluster_fit did
    # exactly that every Sunday for 5 weeks before anyone looked at its log.
    conn = sqlite3.connect(db, timeout=60)
    syms = [r[0] for r in conn.execute(
        "SELECT symbol FROM resonance_universe WHERE status='active' ORDER BY symbol")]
    db_latest_before = conn.execute("SELECT MAX(date) FROM stock_daily_ohlc").fetchone()[0]
    if verbose:
        print(f"update_daily: {len(syms)} resonance extras  |  DB latest daily = {db_latest_before}")

    end = datetime.date.today()
    start = end - datetime.timedelta(days=int(days))

    total_added = 0
    syms_with_rows = 0
    BATCH = 50
    for i in range(0, len(syms), BATCH):
        batch = syms[i:i + BATCH]
        # Daily OHLC from YFINANCE (consolidated, correct volume) — mirrors the CORE ingest
        # scripts/update_stock_ohlc.py. The previous Alpaca sip->iex fallback returned IEX-only
        # volume (~5-12% of consolidated) under the free-SIP recent-data block, so every extra's
        # rvol / vol_dryup coil axes were computed on a thin feed and broken-volume names got
        # promoted into the pool (diagnosed 2026-08-20: GPC/KNSA/APGE ~5-9% of real volume).
        # Price/OHLC was fine; the fix restores real volume. yfinance needs no SIP entitlement.
        try:
            data = yf.download(' '.join(batch), start=start.isoformat(),
                               end=(end + datetime.timedelta(days=1)).isoformat(),
                               interval='1d', auto_adjust=True, progress=False, threads=False)
        except Exception as e:
            if verbose:
                print(f"  [warn] yf batch {i}-{i+len(batch)} failed: {type(e).__name__}")
            continue
        if data is None or data.empty:
            continue
        rows = []
        for sym in batch:
            try:
                df = data if len(batch) == 1 else data.xs(sym, axis=1, level=1)
            except Exception:
                continue
            for ts, r in df.iterrows():
                try:
                    if r["Close"] and float(r["Close"]) > 0:
                        rows.append((str(sym), ts.strftime("%Y-%m-%d"),
                                     float(r["Open"]), float(r["High"]), float(r["Low"]),
                                     float(r["Close"]), int(r["Volume"]) if r["Volume"] else 0))
                except Exception:
                    continue
        if not rows:
            continue
        before = conn.total_changes
        conn.executemany(
            """INSERT OR IGNORE INTO stock_daily_ohlc
                   (symbol, date, open, high, low, close, volume)
               VALUES (?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
        total_added += conn.total_changes - before
        syms_with_rows += len(set(r[0] for r in rows))
        if i + BATCH < len(syms):
            time.sleep(1)

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
