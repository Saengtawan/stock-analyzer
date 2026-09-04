"""resonance / universe / backfill_bars.py — ~1yr DAILY history for the extra universe.

For every `resonance_universe` (status='active') symbol, backfill ~1 year of DAILY OHLC from
Alpaca into the SHARED `stock_daily_ohlc` table. This is SAFE / additive:

  auto_trading derives its tradable symbol list from `universe_stocks`, NOT from any bar table.
  Extra daily rows for extra symbols therefore never change what auto_trading trades — they only
  give resonance's coil feature the "normal" history it needs to measure compression.

Writes use INSERT OR IGNORE against the table's UNIQUE(symbol, date) constraint, so:
  - existing rows (any symbol, incl. core) are NEVER overwritten,
  - re-runs are idempotent (only genuinely missing (symbol,date) rows get added).

Well-covered symbols (already have a deep, fresh daily series) are skipped to save API calls.

CLI:  python -m resonance.universe.backfill_bars
      python -m resonance.universe.backfill_bars --years 1 --force
"""
from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = str(ROOT / "data" / "trade_history.db")

BATCH = 100                 # symbols per Alpaca bars request
WELL_COVERED_BARS = 200     # >= this many bars in the target window ...
FRESH_WITHIN_DAYS = 6       # ... AND max(date) within this many days of the DB's latest date => skip


def _load_env():
    envf = ROOT / ".env"
    for ln in envf.read_text().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def _data_client():
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])


def _coverage(conn) -> dict[str, tuple[int, str]]:
    """{symbol: (n_bars_in_window, max_date)} for resonance symbols already in stock_daily_ohlc."""
    cov = {}
    for sym, n, mx in conn.execute(
        """SELECT o.symbol, COUNT(*), MAX(o.date)
             FROM stock_daily_ohlc o
             JOIN resonance_universe r ON r.symbol = o.symbol
            WHERE r.status='active'
            GROUP BY o.symbol"""
    ):
        cov[sym] = (int(n), mx)
    return cov


def backfill(years=1, force=False, db=DB):
    _load_env()
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.enums import Adjustment
    from alpaca.data.timeframe import TimeFrame

    conn = sqlite3.connect(db)
    syms = [r[0] for r in conn.execute(
        "SELECT symbol FROM resonance_universe WHERE status='active' ORDER BY symbol")]
    print(f"resonance_universe active symbols: {len(syms)}")

    db_latest = conn.execute("SELECT MAX(date) FROM stock_daily_ohlc").fetchone()[0]
    fresh_cutoff = (datetime.date.fromisoformat(db_latest)
                    - datetime.timedelta(days=FRESH_WITHIN_DAYS)).isoformat()
    cov = _coverage(conn)

    todo = []
    skipped = 0
    for s in syms:
        n, mx = cov.get(s, (0, None))
        if (not force) and n >= WELL_COVERED_BARS and mx and mx >= fresh_cutoff:
            skipped += 1
            continue
        todo.append(s)
    print(f"skipping {skipped} well-covered (>= {WELL_COVERED_BARS} bars & fresh >= {fresh_cutoff})")
    print(f"to backfill: {len(todo)} symbols")

    end = datetime.date.today()
    start = end - datetime.timedelta(days=int(round(years * 365)) + 5)

    dc = _data_client()
    total_rows = 0
    sym_with_rows = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            req = StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day,
                                   start=start, end=end, adjustment=Adjustment.ALL, feed="sip")
            df = dc.get_stock_bars(req).df
        except Exception as e:
            print(f"  [warn] batch {i}-{i+len(batch)} failed: {type(e).__name__}")
            continue
        if df is None or df.empty:
            print(f"  batch {i+len(batch)}/{len(todo)}: no bars")
            continue

        rows = []
        for (sym, ts), r in df.iterrows():
            d = ts.date().isoformat()   # daily bar UTC-stamped @ session date; .date() == trading date
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
        added = conn.total_changes - before
        total_rows += added
        sym_with_rows += df.index.get_level_values("symbol").nunique()
        print(f"  batch {i+len(batch)}/{len(todo)}: +{added} rows "
              f"({df.index.get_level_values('symbol').nunique()} symbols this batch)")

    conn.close()
    print("=" * 64)
    print(f"backfill done: +{total_rows} rows across ~{sym_with_rows} symbols "
          f"({skipped} skipped as well-covered)")
    return {"rows_added": total_rows, "symbols_touched": sym_with_rows, "skipped": skipped}


def _extras_only(conn):
    """resonance_universe (active) symbols that are NOT in universe_stocks (core).

    STRICT scoping for the destructive re-adjust: a symbol present in BOTH tables counts as CORE
    and is EXCLUDED, so a DELETE keyed on this list can never touch a core symbol's daily rows.
    """
    return [r[0] for r in conn.execute(
        """SELECT symbol FROM resonance_universe
            WHERE status='active'
              AND symbol NOT IN (SELECT symbol FROM universe_stocks)
            ORDER BY symbol""")]


# ⚠️ CORE IS NOT COVERED, AND IT IS ALSO CORRUPTED (measured 2026-09-04).
# readjust_extras deliberately protects `universe_stocks` — the DELETE is scoped to extras-only because
# core daily rows are shared with ml_filter, exec_ai and swing, and dropping them mid-session would
# break live systems. That safety is right. The consequence is that core names still carry PRE-split
# rows written before the Adjustment.ALL change, and nothing repairs them: update_daily writes with
# INSERT OR IGNORE, so an existing wrong row is never overwritten.
# Scope on the day this was measured: ~25 core symbols show the signature (a 252d high more than 3x
# the recent range) — BKNG reads a 252d high of 5628 against a 195 last close (-97%), KLAC 2431 vs 173,
# CVNA 487 vs 73. Those are splits, not crashes.
# Impact is BOUNDED, which is why this is documented rather than repaired in a hurry: build.py's
# dd_suspect guard detects the signature and nulls the depth, so no name is ever ADMITTED on a fake
# drawdown. The cost is exclusion — roughly one otherwise-qualifying name a day never reaches the pool.
# Same-day open->close returns are unaffected (both prices come from the same row), so graded outcomes
# and every measurement in this session are safe.
# A SAFE repair would: re-fetch those symbols with Adjustment.ALL into a staging table, diff it against
# stock_daily_ohlc, and UPDATE only the rows that differ — never DELETE from a table three live systems
# read. Do it outside market hours. Do not point readjust_extras at core.


def readjust_extras(years=1, db=DB):
    """Rewrite the EXTRAS' daily OHLC onto the corrected split+dividend-adjusted basis.

    backfill/update_daily historically wrote RAW daily, so the ~1yr history straddles any split as a
    discontinuity (e.g. FCUV's 2026-06-23 4:1 reverse split: 0.543 -> 4.11 raw) — which inflates
    prime()'s gap for any name near its split date. INSERT OR IGNORE can't overwrite those raw rows,
    so we DELETE the extras' daily rows and re-insert with Adjustment.ALL.

    SAFETY: the DELETE is scoped to `_extras_only` (resonance actives MINUS universe_stocks), so core
    daily data is never touched. Returns a stats dict.
    """
    _load_env()
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.enums import Adjustment
    from alpaca.data.timeframe import TimeFrame

    conn = sqlite3.connect(db)
    core_before = conn.execute("""SELECT COUNT(*) FROM stock_daily_ohlc
                                   WHERE symbol IN (SELECT symbol FROM universe_stocks)""").fetchone()[0]
    extras = _extras_only(conn)
    print(f"readjust_extras: {len(extras)} extra symbols (resonance actives NOT in core universe_stocks)")

    # DELETE strictly the extras' daily rows (core untouched by construction of `extras`).
    before_del = conn.total_changes
    conn.executemany("DELETE FROM stock_daily_ohlc WHERE symbol=?", [(s,) for s in extras])
    conn.commit()
    deleted = conn.total_changes - before_del
    print(f"  deleted {deleted} raw extra daily rows")

    end = datetime.date.today()
    start = end - datetime.timedelta(days=int(round(years * 365)) + 5)
    dc = _data_client()
    total_rows = 0
    syms_with_rows = 0
    for i in range(0, len(extras), BATCH):
        batch = extras[i:i + BATCH]
        try:
            req = StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day,
                                   start=start, end=end, adjustment=Adjustment.ALL, feed="sip")
            df = dc.get_stock_bars(req).df
        except Exception as e:
            print(f"  [warn] batch {i}-{i+len(batch)} failed: {type(e).__name__}")
            continue
        if df is None or df.empty:
            continue
        rows = []
        for (sym, ts), r in df.iterrows():
            d = ts.date().isoformat()
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
        total_rows += conn.total_changes - before
        syms_with_rows += df.index.get_level_values("symbol").nunique()
        print(f"  batch {i+len(batch)}/{len(extras)}: +{conn.total_changes - before} adjusted rows")

    core_after = conn.execute("""SELECT COUNT(*) FROM stock_daily_ohlc
                                  WHERE symbol IN (SELECT symbol FROM universe_stocks)""").fetchone()[0]
    conn.close()
    print("=" * 64)
    print(f"readjust done: -{deleted} raw / +{total_rows} adjusted rows across ~{syms_with_rows} extras")
    print(f"core daily rows UNCHANGED: {core_before} -> {core_after} "
          f"({'OK' if core_before == core_after else 'MISMATCH!'})")
    return {"extras": len(extras), "deleted": deleted, "readded": total_rows,
            "symbols_touched": syms_with_rows,
            "core_rows_before": core_before, "core_rows_after": core_after}


def main():
    ap = argparse.ArgumentParser(description="backfill ~1yr daily OHLC for resonance_universe symbols")
    ap.add_argument("--years", type=float, default=1.0)
    ap.add_argument("--force", action="store_true", help="re-fetch even well-covered symbols")
    ap.add_argument("--readjust", action="store_true",
                    help="DELETE extras' daily rows + re-insert on split/div-adjusted basis (core untouched)")
    a = ap.parse_args()
    if a.readjust:
        readjust_extras(a.years)
    else:
        backfill(a.years, a.force)


if __name__ == "__main__":
    main()
