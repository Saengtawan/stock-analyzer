"""resonance / universe / fetch_intraday.py — FULL-SESSION 5-min bars for the resonance EXTRAS.

DATA-COVERAGE fix. The resonance_universe EXTRAS (the ~1000 liquid small/mid-caps built by
build_universe.py) have backfilled DAILY OHLC but NO full-session intraday bars: the core list
(universe_stocks) gets 09:30-16:00 5-min bars every day from scripts/collect_intraday_5m_daily.py,
while the extras get nothing — fetch_premarket.py only pulls the 04:00->now premarket window on the
live day. Result: a pooled extra (MGM / ACA / APGE — all liquid, $30-200M/day) has 0 intraday bars
on most dates, so it has no 09:30 RTH open and no 15:55 close and is UNMEASURABLE (can't be scored
or traded). On 2026-07-30, 11 of 28 pooled names were dark for exactly this reason.

This module closes the gap for the EXTRAS ONLY. For a DATE it fetches the full regular-session
5-min bars (04:00 premarket through the 16:00 close) for every resonance_universe (status=active)
symbol from Alpaca and UPSERTs them into intraday_bars_5m matching the EXACT existing schema.

SCOPE + IDEMPOTENCY (never touches core rows):
  - Symbols are read ONLY from resonance_universe WHERE status='active'. A symbol that is ALSO in
    the core universe_stocks is skipped (core already has full-session bars from the collector) —
    so this never writes on core's behalf and never competes with it.
  - Rows are INSERT OR IGNORE against the table's natural key UNIQUE(symbol, timestamp), and the
    timestamp uses the SAME string the collectors write ('YYYY-MM-DDTHH:MM:SSZ', UTC). So a
    re-run adds nothing, and if any (symbol,timestamp) already exists (collector, premarket, or a
    prior run) the new write collides harmlessly — whoever wrote the key first wins; the value is
    identical raw Alpaca data. NO core or collector row is ever duplicated or altered.

FEED: past dates use SIP (full-tape historical, same as the daily/backfill fetchers); TODAY uses
IEX (the real-time entitlement — SIP is delayed for the current session). Adjustment.ALL keeps the
intraday on the SAME split/dividend basis as the daily fetchers (backfill_bars / update_daily), so
prime()'s gap can't be inflated by an unadjusted split; for TODAY's live bars ALL == raw.

Thin names can have NO prints in a 5-min slot — that is a real data limit for an illiquid symbol on
a given day, not a failure. This module never fabricates a bar.

CLI:
  python -m resonance.universe.fetch_intraday DATE          # one ET date YYYY-MM-DD
  python -m resonance.universe.fetch_intraday BACKFILL N    # the last N trading days (incl DATE calendar)
"""
from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
import time
import zoneinfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = str(ROOT / "data" / "trade_history.db")
ET = zoneinfo.ZoneInfo("America/New_York")

BATCH = 100                          # symbols per Alpaca bars request
SESSION_START = datetime.time(4, 0)  # premarket opens 04:00 ET (premarket is fine to keep)
SESSION_END = datetime.time(16, 5)   # through the 16:00 close (bounded)


def _load_env():
    """Load ALPACA_* creds from .env (same pattern as fetch_premarket / backfill_bars). Never printed."""
    envf = ROOT / ".env"
    for ln in envf.read_text().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def _data_client():
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])


def _extra_symbols(conn):
    """resonance_universe (status=active) symbols that are NOT in the core universe_stocks.

    Core is skipped so this module only ever fills the EXTRAS — the core already gets full-session
    bars from scripts/collect_intraday_5m_daily.py, and scoping the write to extras guarantees we
    never duplicate or race a core row."""
    core = {r[0] for r in conn.execute("SELECT symbol FROM universe_stocks")}
    extras = [r[0] for r in conn.execute(
        "SELECT symbol FROM resonance_universe WHERE status='active' ORDER BY symbol")]
    return [s for s in extras if s not in core], len(extras), len(extras) - len([s for s in extras if s not in core])


def _trading_days(conn, last_n, upto=None):
    """The last `last_n` trading days at or before `upto` (ET date str, default today ET), taken
    from the DISTINCT dates already present in intraday_bars_5m (core writes one row-set per real
    trading session, so this is a faithful market calendar with no weekend/holiday guessing)."""
    upto = upto or datetime.datetime.now(ET).date().isoformat()
    rows = conn.execute(
        "SELECT DISTINCT date FROM intraday_bars_5m WHERE date <= ? ORDER BY date DESC LIMIT ?",
        (upto, int(last_n)),
    ).fetchall()
    return [r[0] for r in rows][::-1]   # oldest -> newest


def fetch_intraday(date, db=DB, verbose=True, conn=None):
    """Fetch full-session 5-min bars (04:00-16:05 ET) for the resonance EXTRAS on `date` and UPSERT
    into intraday_bars_5m. Returns a stats dict. Pass an open `conn` to reuse it across a backfill."""
    _load_env()
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import Adjustment

    t0 = time.time()
    now_et = datetime.datetime.now(ET)
    d = datetime.date.fromisoformat(date)
    is_today = (date == now_et.date().isoformat())

    # FEED: prefer SIP (full consolidated tape — full volume, ~80 bars/session, matching the core
    # collector and this module's own history). SIP is only unavailable for a session still IN
    # PROGRESS (a ~15-min delay truncates the most-recent bars); once the session has closed and the
    # delay has elapsed the full SIP tape is available. So use SIP for any PAST date, and for TODAY
    # once we're past the close + delay buffer; use IEX only for a genuinely-live intraday run today
    # (where SIP would drop the last quarter-hour). A post-close daily cron therefore gets SIP.
    session_done_et = datetime.datetime.combine(d, datetime.time(16, 15), ET)  # 16:00 close + delay
    live_intraday = is_today and now_et < session_done_et
    from alpaca.data.enums import DataFeed as _DF
    feed = _DF.IEX if live_intraday else _DF.SIP

    start_et = datetime.datetime.combine(d, SESSION_START, ET)
    end_et = now_et if live_intraday else datetime.datetime.combine(d, SESSION_END, ET)

    own = conn is None
    if own:
        conn = sqlite3.connect(db)
    syms, n_active, n_core_overlap = _extra_symbols(conn)

    if verbose:
        print(f"fetch_intraday {date}  window {start_et:%H:%M}-{end_et:%H:%M} ET  "
              f"extras={len(syms)} (active={n_active}, core-overlap skipped={n_core_overlap})  "
              f"feed={'IEX' if live_intraday else 'SIP'}")

    dc = _data_client()
    tf = TimeFrame(5, TimeFrameUnit.Minute)

    total_added = 0
    syms_with_bars = set()
    batches_failed = 0
    for i in range(0, len(syms), BATCH):
        batch = syms[i:i + BATCH]
        try:
            req = StockBarsRequest(symbol_or_symbols=batch, timeframe=tf,
                                   start=start_et, end=end_et, feed=feed,
                                   adjustment=Adjustment.ALL)
            df = dc.get_stock_bars(req).df
        except Exception as e:
            batches_failed += 1
            if verbose:
                print(f"  [warn] batch {i}-{i+len(batch)} failed: {type(e).__name__}")
            continue
        if df is None or df.empty:
            continue

        rows = []
        for (sym, ts), r in df.iterrows():
            ts_utc = ts.tz_convert("UTC")
            et = ts.tz_convert(ET)
            if et.date().isoformat() != date:                 # keep only bars on the requested ET date
                continue
            ts_str = ts_utc.strftime("%Y-%m-%dT%H:%M:%SZ")     # EXACT collector key format
            time_et = et.strftime("%H:%M")
            rows.append((str(sym), ts_str, date, time_et,
                         float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                         int(r["volume"]) if r["volume"] == r["volume"] else 0,
                         float(r["vwap"]) if r["vwap"] == r["vwap"] else None,
                         int(r["trade_count"]) if r["trade_count"] == r["trade_count"] else None))
        if not rows:
            continue
        before = conn.total_changes
        conn.executemany(
            """INSERT OR IGNORE INTO intraday_bars_5m
                   (symbol, timestamp, date, time_et, open, high, low, close, volume, vwap, n_trades)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
        total_added += conn.total_changes - before
        syms_with_bars.update(df.index.get_level_values("symbol").unique().tolist())

    if own:
        conn.close()
    elapsed = time.time() - t0
    stats = {
        "date": date,
        "extras": len(syms),
        "symbols_fetched": len(syms_with_bars),
        "bars_written": total_added,
        "batches_failed": batches_failed,
        "elapsed_s": round(elapsed, 1),
    }
    if verbose:
        print(f"  -> fetched {len(syms_with_bars)}/{len(syms)} symbols  |  wrote +{total_added} rows  |  "
              f"{batches_failed} batches failed  |  {elapsed:.1f}s")
    return stats


def backfill(last_n, db=DB, verbose=True):
    """Fetch full-session extras bars for each of the last `last_n` trading days. One shared conn."""
    conn = sqlite3.connect(db)
    days = _trading_days(conn, last_n)
    if verbose:
        print(f"BACKFILL: last {last_n} trading days = {days[0]}..{days[-1]} ({len(days)} days)")
    t0 = time.time()
    per_day = []
    total = 0
    for dt in days:
        s = fetch_intraday(dt, db=db, verbose=verbose, conn=conn)
        per_day.append(s)
        total += s["bars_written"]
    conn.close()
    elapsed = time.time() - t0
    if verbose:
        print("=" * 68)
        print(f"BACKFILL done: {len(days)} days  |  +{total} bars total  |  {elapsed:.1f}s")
        for s in per_day:
            print(f"    {s['date']}  +{s['bars_written']:>6} bars  "
                  f"{s['symbols_fetched']}/{s['extras']} symbols  {s['batches_failed']} fail")
    return {"days": days, "total_bars": total, "per_day": per_day, "elapsed_s": round(elapsed, 1)}


def main():
    ap = argparse.ArgumentParser(
        description="full-session 5-min bars for the resonance EXTRAS -> intraday_bars_5m")
    ap.add_argument("date", help="ET date YYYY-MM-DD, or the literal BACKFILL")
    ap.add_argument("n", nargs="?", type=int, default=None,
                    help="with BACKFILL: number of most-recent trading days")
    a = ap.parse_args()
    _load_env()
    if a.date.upper() == "BACKFILL":
        if not a.n:
            ap.error("BACKFILL requires N (number of trading days)")
        backfill(a.n)
    else:
        fetch_intraday(a.date)


if __name__ == "__main__":
    main()
