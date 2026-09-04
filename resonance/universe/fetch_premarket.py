"""resonance / universe / fetch_premarket.py — LIVE premarket bars for the FULL universe.

STAGE 2 live-readiness fix. At ~09:00 ET (when run/premarket.sh fires, BEFORE the open) TODAY's
premarket 5-min bars are NOT yet in intraday_bars_5m: the DB collectors write intraday post-open
(~10:29 ET) and coverage is spotty (on 2026-07-31 AAPL had 0 premarket rows), while the resonance
extras have NO intraday history at all. So prime.premarket() — the gap/wake release-trigger, a core
resonance axis — is empty live for both core and extras. The 07-30 replay only "worked" because the
bars happened to exist post-hoc.

This module closes that gap. For a DATE it fetches the premarket + early-session 5-min bars
MEASURED LIMIT (2026-09-04) — READ BEFORE "JUST FETCHING AGAIN". The window ends at `now` when this
STARTS, and the cron starts it at 09:00, so the stored premarket always ends ~09:00 while the brain
decides at ~09:20-09:25. The obvious fix — run it a second time before the AI call — does not work, and
the numbers say why: SIP is capped at now-16min by the free-tier restriction, so a 09:02 re-run reaches
only 08:46, and IEX (which has no such cap) covered just **4 of 48 pooled names** past 08:45 on the day
this was measured — JOBY, KEEL, ORCL, SOUN, the liquid ones. For the other 34 whose tape stops at 08:40,
IEX simply has no prints. That is a real IEX coverage limit on small caps, not a bug here, and no
scheduling change repairs it.
The path that DOES work is a per-name pull at decision time: `scripts/winlo_limit.py <SYM>` reads
yfinance premarket 1-min with prepost=True, free and near-real-time, cross-checked against SIP to about
a cent. decide.md's G3 requires it. Do not replace that with another batch fetch here.

(04:00 ET -> the current ET minute) LIVE from Alpaca (feed=IEX — the real-time entitlement) for the
FULL resonance universe (access.universe() = core + resonance extras, ~2000) and UPSERTs them into
intraday_bars_5m matching the EXACT existing schema.

Idempotent + collector-safe. Rows are written with INSERT OR IGNORE against the table's natural key
UNIQUE(symbol, timestamp), and the timestamp is formatted with the SAME string the collectors use
('YYYY-MM-DDTHH:MM:SSZ', UTC). So:
  - re-running adds nothing (only genuinely-missing (symbol,timestamp) rows land),
  - the post-open collectors' rows for the same (symbol,timestamp) collide harmlessly — never
    duplicated (whoever writes a given key first wins; the value is identical raw Alpaca data).

Thin names (e.g. GRND) can have NO IEX premarket prints on a given day — that is a real IEX data
limit for illiquid symbols, not a failure. Those names simply carry no gap/wake (coil-only);
this module never fabricates a bar.

CLI:  python -m resonance.universe.fetch_premarket [DATE]     # DATE (ET) defaults to today
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

BATCH = 100                 # symbols per Alpaca bars request
PM_START = datetime.time(4, 0)      # premarket opens 04:00 ET
SESSION_END = datetime.time(16, 5)  # for a PAST date: fetch through the close (bounded)


def _load_env():
    """Load ALPACA_* creds from .env (same pattern as build_snap / backfill_bars). Never printed."""
    envf = ROOT / ".env"
    for ln in envf.read_text().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def _data_client():
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])


def fetch_premarket(date=None, db=DB, verbose=True):
    """Fetch 5-min bars 04:00 ET -> now (or -> close for a past date) for the full universe and
    UPSERT into intraday_bars_5m. Returns a stats dict."""
    _load_env()
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed, Adjustment

    from resonance.data import access

    t0 = time.time()
    now_et = datetime.datetime.now(ET)
    date = date or now_et.date().isoformat()
    d = datetime.date.fromisoformat(date)

    start_et = datetime.datetime.combine(d, PM_START, ET)
    if date == now_et.date().isoformat():
        end_et = now_et                                    # LIVE: through the current ET minute
    else:
        end_et = datetime.datetime.combine(d, SESSION_END, ET)   # past date: bounded to the close
    # This account's SIP entitlement forbids querying the last ~15 min (free-SIP restriction) — an
    # end inside that window makes the whole SIP batch APIError. Cap SIP's end to now-16min so it
    # only asks for data it's allowed to return (04:00..~08:45 at the 09:00 build = full premarket
    # coverage for thin small-caps). IEX (real-time entitlement) fills the freshest last ~15 min.
    sip_end_et = min(end_et, now_et - datetime.timedelta(minutes=16))

    uni = access.universe()
    syms = uni["syms"]
    if verbose:
        print(f"fetch_premarket {date}  window {start_et:%H:%M}-{end_et:%H:%M} ET  "
              f"universe={len(syms)} (core={uni['n_core']} resonance={uni['n_resonance']})  feed=SIP+IEX")

    conn = sqlite3.connect(db)
    # At the 09:00 ET build, intraday_snapshot_cron (*/5) and the live services write the same 13GB
    # DB concurrently — a bare connect() raised "database is locked" on executemany and the whole
    # premarket fetch died (empty prime layer). Wait for the lock instead of crashing.
    conn.execute("PRAGMA busy_timeout=30000")
    dc = _data_client()
    tf = TimeFrame(5, TimeFrameUnit.Minute)

    total_added = 0
    pm_added = 0
    syms_with_bars = set()
    batches_failed = 0
    for i in range(0, len(syms), BATCH):
        batch = syms[i:i + BATCH]
        # SIP first (full consolidated premarket coverage — thin small-caps have SIP prints even
        # when IEX has none; SIP's ~15-min delay still yields the ~04:00-08:45 window at the 09:00
        # build). IEX second to add the freshest last ~15 min for the liquid names SIP hasn't
        # published yet. INSERT OR IGNORE dedupes the overlap. (The live path was IEX-only, so
        # pm_vol/gap were 0 across the small-cap pool EVERY live day since go-live — the gap/pm_wake
        # trigger axes were dead. SIP restores them. adjustment=ALL keeps one split/div basis with
        # the daily fetchers so prime()'s gap can't be inflated by an unadjusted split.)
        rows = []
        batch_syms = set()
        got_any = False
        for feed in (DataFeed.SIP, DataFeed.IEX):
            feed_end = sip_end_et if feed == DataFeed.SIP else end_et
            if feed_end <= start_et:          # nothing SIP is allowed to return yet (very early run)
                continue
            try:
                req = StockBarsRequest(symbol_or_symbols=batch, timeframe=tf,
                                       start=start_et, end=feed_end, feed=feed,
                                       adjustment=Adjustment.ALL)
                df = dc.get_stock_bars(req).df
            except Exception as e:
                if verbose:
                    print(f"  [warn] batch {i}-{i+len(batch)} feed={feed} failed: {type(e).__name__}")
                continue
            if df is None or df.empty:
                continue
            got_any = True
            batch_syms.update(df.index.get_level_values("symbol").unique().tolist())
            for (sym, ts), r in df.iterrows():
                ts_utc = ts.tz_convert("UTC")
                et = ts.tz_convert(ET)
                if et.date().isoformat() != date:         # keep only bars on the requested ET date
                    continue
                ts_str = ts_utc.strftime("%Y-%m-%dT%H:%M:%SZ")   # EXACT collector key format
                time_et = et.strftime("%H:%M")
                rows.append((str(sym), ts_str, date, time_et,
                             float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                             int(r["volume"]) if r["volume"] == r["volume"] else 0,
                             float(r["vwap"]) if r["vwap"] == r["vwap"] else None,
                             int(r["trade_count"]) if r["trade_count"] == r["trade_count"] else None,
                             time_et < "09:30"))
        if not got_any:
            batches_failed += 1
        if not rows:
            continue
        before = conn.total_changes
        conn.executemany(
            """INSERT OR IGNORE INTO intraday_bars_5m
                   (symbol, timestamp, date, time_et, open, high, low, close, volume, vwap, n_trades)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [row[:11] for row in rows],
        )
        conn.commit()
        added = conn.total_changes - before
        total_added += added
        # count how many of the freshly-written rows were premarket (approximate: proportion of the
        # batch's rows that are pm, since INSERT OR IGNORE only tells us the aggregate delta).
        pm_flags = [row[11] for row in rows]
        if rows:
            pm_added += int(round(added * (sum(pm_flags) / len(pm_flags))))
        syms_with_bars.update(batch_syms)

    conn.close()
    elapsed = time.time() - t0
    stats = {
        "date": date,
        "universe": len(syms),
        "symbols_fetched": len(syms_with_bars),
        "bars_written": total_added,
        "premarket_bars_written_est": pm_added,
        "batches_failed": batches_failed,
        "elapsed_s": round(elapsed, 1),
    }
    if verbose:
        print("=" * 64)
        print(f"fetched bars for {len(syms_with_bars)}/{len(syms)} symbols  |  "
              f"wrote +{total_added} rows (~{pm_added} premarket)  |  "
              f"{batches_failed} batches failed  |  {elapsed:.1f}s")
    return stats


def main():
    ap = argparse.ArgumentParser(description="live premarket 5-min bars -> intraday_bars_5m (full universe)")
    ap.add_argument("date", nargs="?", default=None, help="ET date YYYY-MM-DD (default: today ET)")
    a = ap.parse_args()
    fetch_premarket(a.date)


if __name__ == "__main__":
    main()
