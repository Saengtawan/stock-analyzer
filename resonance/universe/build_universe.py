"""resonance / universe / build_universe.py — DECOUPLED expanded spring universe.

Builds the table `resonance_universe` in data/trade_history.db: a set of LIQUID small/mid-cap
"spring" candidates that live ALONGSIDE (never inside) the live `universe_stocks` that
auto_trading reads. auto_trading gets its symbol list ONLY from universe_stocks — this table is
invisible to it. `resonance.data.access.universe()` unions the two so resonance sees more names.

Pipeline (all mechanical, zero AI tokens):
  1. Alpaca get_all_assets(active, us_equity, tradable) — the tradable US equity list.
  2. Keep NASDAQ / NYSE / AMEX listings only (drop OTC + the ARCA/BATS ETF-heavy venues), and
     drop anything already in `universe_stocks` (the core list stays the core list).
  3. Batch-fetch ~20 recent DAILY bars/symbol from Alpaca → avg dollar-volume + last price.
  4. LIQUIDITY + PRICE screen: avg_dollar_vol >= MIN_DOLLAR_VOL (default $3M/day — avoids fake
     springs on thin tape), PRICE_MIN <= last_price <= PRICE_MAX ($3..$400 → buyable, not penny).
  5. market_cap joined from stock_fundamentals where available (springs live in small/mid cap) —
     surfaced as context, NOT hard-required (most small-caps lack a mcap row).
  6. If more than MAX_EXTRAS survive, keep the MOST LIQUID MAX_EXTRAS (top by dollar-vol) so the
     pool stays a sensible size. The effective floor (min kept dollar-vol) is reported.
  7. Idempotent UPSERT into resonance_universe.

Table `resonance_universe`:
  symbol PK, market_cap, avg_dollar_vol, last_price, source, added_date, status

CLI:  python -m resonance.universe.build_universe
      python -m resonance.universe.build_universe --min-dollar-vol 5e6 --max-extras 800
"""
from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = str(ROOT / "data" / "trade_history.db")

# ---- screen knobs (defaults; overridable via CLI) -----------------------------------------
MIN_DOLLAR_VOL = 3_000_000.0     # liquidity floor: avg $-volume/day (avoid fake springs on thin tape)
MAX_DOLLAR_VOL = 400_000_000.0   # liquidity CEILING: drop true mega-caps (trade $1B+/day) — springs
                                 # live in small/mid cap, not AT&T. Keeps the $3M..$400M/day band.
PRICE_MIN = 3.0
PRICE_MAX = 400.0
MAX_EXTRAS = 1000                # cap the pool to the most-liquid N if more survive
BAR_LOOKBACK_DAYS = 32           # calendar days back to fetch (~20 trading bars)
MIN_BARS_FOR_SCREEN = 10         # need at least this many bars to trust the $-vol avg
KEEP_EXCHANGES = {"NASDAQ", "NYSE", "AMEX"}   # operating-company listing venues (drop ARCA/BATS/OTC)
BATCH = 200                      # symbols per Alpaca bars request

# ETFs/ETNs/leveraged funds are classed us_equity by Alpaca and some list on NASDAQ/NYSE — they are
# NOT springs. Exclude by name (fund-sponsor + product markers). Case-insensitive substring match.
ETF_NAME_MARKERS = (
    " ETF", " ETN", "ETF TRUST", "PROSHARES", "DIREXION", "ISHARES", "SPDR", "INVESCO",
    "VANECK", "GLOBAL X", "GRANITESHARES", "COINSHARES", "SIMPLIFY", "DEFIANCE", "YIELDMAX",
    "ULTRAPRO", "ULTRASHORT", "LEVERAGED", "INVERSE", "INDEX FUND", "CLOSED-END", " 2X ", " 3X ",
)


def _is_fund(name: str) -> bool:
    n = (name or "").upper()
    return any(m in n for m in ETF_NAME_MARKERS)


# ---------------------------------------------------------------------------- env / clients
def _load_env():
    """Load ALPACA_* (and friends) from .env into os.environ. Never prints values."""
    envf = ROOT / ".env"
    for ln in envf.read_text().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def _trading_client():
    from alpaca.trading.client import TradingClient
    return TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)


def _data_client():
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])


# ------------------------------------------------------------------------------------ schema
def ensure_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS resonance_universe (
               symbol         TEXT PRIMARY KEY,
               market_cap     REAL,
               avg_dollar_vol REAL,
               last_price     REAL,
               source         TEXT,
               added_date     TEXT,
               status         TEXT DEFAULT 'active'
           )"""
    )
    conn.commit()


# ------------------------------------------------------------------------------- asset list
def fetch_candidate_symbols(existing_core: set) -> list[str]:
    """Active + tradable US-equity assets on the listing venues we keep, minus the core universe."""
    from alpaca.trading.requests import GetAssetsRequest
    from alpaca.trading.enums import AssetStatus, AssetClass
    tc = _trading_client()
    assets = tc.get_all_assets(
        GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
    )
    out, n_fund = [], 0
    for a in assets:
        if not a.tradable:
            continue
        exch = str(a.exchange).split(".")[-1]     # "AssetExchange.NASDAQ" -> "NASDAQ"
        if exch not in KEEP_EXCHANGES:
            continue
        sym = a.symbol
        if "/" in sym:                            # skip crypto-style / pair symbols
            continue
        if sym in existing_core:
            continue
        if _is_fund(getattr(a, "name", "")):      # drop ETFs/ETNs/leveraged funds
            n_fund += 1
            continue
        out.append(sym)
    print(f"  (excluded {n_fund} ETF/ETN/fund names by product-name heuristic)")
    return sorted(set(out))


# --------------------------------------------------------------------------- bar aggregation
def fetch_dollar_vol(symbols: list[str], lookback_days: int) -> dict[str, dict]:
    """Batch-fetch recent DAILY bars → {sym: {avg_dollar_vol, last_price, n_bars}}."""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.enums import Adjustment
    from alpaca.data.timeframe import TimeFrame
    import time
    dc = _data_client()
    end = datetime.date.today()
    start = end - datetime.timedelta(days=lookback_days)
    out: dict[str, dict] = {}
    fail_batches = 0
    for i in range(0, len(symbols), BATCH):
        batch = symbols[i:i + BATCH]
        # Retry with backoff, and FALL BACK sip -> iex. The Sunday 2026-08-02 build lost the whole
        # screen because every SIP batch threw APIError (weekend/subscription hiccup) with no retry
        # and no fallback -> 0 symbols. IEX is available on the basic plan and enough for a daily
        # $-vol / last-price screen. The GUARD downstream is the final backstop, but not zeroing the
        # screen in the first place is better.
        df = None
        for feed in ("sip", "iex"):
            for attempt in range(3):
                try:
                    req = StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day,
                                           start=start, end=end, adjustment=Adjustment.RAW, feed=feed)
                    df = dc.get_stock_bars(req).df
                    break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))       # 2s, 4s backoff
                        continue
                    print(f"  [warn] bars batch {i}-{i+len(batch)} feed={feed} failed after 3 tries: {type(e).__name__}")
            if df is not None:
                break
        if df is None:
            fail_batches += 1
            continue
        if df.empty:
            continue
        # df is MultiIndex (symbol, timestamp); iterate per symbol group
        for sym, g in df.groupby(level="symbol"):
            g = g.sort_index()
            closes = g["close"].to_numpy(dtype=float)
            vols = g["volume"].to_numpy(dtype=float)
            n = len(closes)
            if n < MIN_BARS_FOR_SCREEN:
                continue
            dollar = (closes * vols)
            out[str(sym)] = {
                "avg_dollar_vol": float(dollar.mean()),
                "last_price": float(closes[-1]),
                "n_bars": int(n),
            }
        print(f"  bars {i+len(batch)}/{len(symbols)} fetched "
              f"({len(out)} symbols with >= {MIN_BARS_FOR_SCREEN} bars so far)")
    return out


def load_market_caps(conn, symbols: set) -> dict[str, float]:
    """market_cap from stock_fundamentals where present (context only, not required)."""
    caps = {}
    for sym, mc in conn.execute(
        "SELECT symbol, market_cap FROM stock_fundamentals WHERE market_cap IS NOT NULL"
    ):
        if sym in symbols:
            caps[sym] = float(mc)
    return caps


# ---------------------------------------------------------------------------------- build
def build(min_dollar_vol=MIN_DOLLAR_VOL, price_min=PRICE_MIN, price_max=PRICE_MAX,
          max_extras=MAX_EXTRAS, lookback_days=BAR_LOOKBACK_DAYS,
          max_dollar_vol=MAX_DOLLAR_VOL, db=DB):
    _load_env()
    conn = sqlite3.connect(db)
    ensure_table(conn)

    core = {r[0] for r in conn.execute("SELECT symbol FROM universe_stocks")}
    print(f"core universe_stocks symbols: {len(core)} (excluded from candidates)")

    cands = fetch_candidate_symbols(core)
    print(f"candidate US-equity symbols (NASDAQ/NYSE/AMEX, tradable, not core): {len(cands)}")

    barstats = fetch_dollar_vol(cands, lookback_days)
    print(f"symbols with usable recent bars: {len(barstats)}")

    # liquidity band + price screen
    kept = []
    for sym, s in barstats.items():
        if not (min_dollar_vol <= s["avg_dollar_vol"] <= max_dollar_vol):
            continue
        if not (price_min <= s["last_price"] <= price_max):
            continue
        kept.append((sym, s))
    print(f"passed liquidity([${min_dollar_vol:,.0f},${max_dollar_vol:,.0f}]) "
          f"+ price([{price_min},{price_max}]): {len(kept)}")

    # cap to the most-liquid MAX_EXTRAS
    kept.sort(key=lambda x: x[1]["avg_dollar_vol"], reverse=True)
    capped = kept[:max_extras]
    effective_floor = capped[-1][1]["avg_dollar_vol"] if len(kept) > max_extras else min_dollar_vol

    # GUARD (against the observed failure where a hiccup wiped the whole universe): a healthy screen
    # returns ~max_extras. If it collapses (Alpaca outage / bad-data day / few usable bars), do NOT
    # touch the table — the reconcile below would inactivate every previously-active extra. Leave the
    # existing active set intact and warn loudly instead.
    MIN_HEALTHY = max(50, max_extras // 2)
    if len(capped) < MIN_HEALTHY:
        prior = conn.execute("SELECT COUNT(*) FROM resonance_universe WHERE status='active'").fetchone()[0]
        print(f"🔴 GUARD: screen returned only {len(capped)} (< {MIN_HEALTHY}) — likely a data "
              f"failure. ABORTED: table untouched, {prior} active preserved. No reconcile.")
        conn.close()
        return {"written": 0, "active_total": prior, "aborted": True}

    caps = load_market_caps(conn, {s for s, _ in capped})
    added_date = str(datetime.date.today())

    # UPSERT: refresh live metrics + status; keep first added_date on conflict
    rows = [(sym, caps.get(sym), s["avg_dollar_vol"], s["last_price"], "alpaca_screen",
             added_date, "active") for sym, s in capped]
    conn.executemany(
        """INSERT INTO resonance_universe
               (symbol, market_cap, avg_dollar_vol, last_price, source, added_date, status)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(symbol) DO UPDATE SET
               market_cap     = excluded.market_cap,
               avg_dollar_vol = excluded.avg_dollar_vol,
               last_price     = excluded.last_price,
               source         = excluded.source,
               status         = 'active'""",
        rows,
    )
    # reconcile: any previously-active symbol NOT in this build is retired (status='inactive').
    # Keeps the table a faithful mirror of the latest screen (idempotent across differing runs).
    current = [sym for sym, _ in capped]
    placeholders = ",".join("?" * len(current)) if current else "''"
    retired = conn.execute(
        f"UPDATE resonance_universe SET status='inactive' "
        f"WHERE status='active' AND symbol NOT IN ({placeholders})",
        current,
    ).rowcount
    conn.commit()
    if retired:
        print(f"retired {retired} symbols no longer in screen (status=inactive)")

    total = conn.execute("SELECT COUNT(*) FROM resonance_universe WHERE status='active'").fetchone()[0]
    n_with_mcap = sum(1 for s, _ in capped if s in caps)
    conn.close()

    print("=" * 64)
    print(f"resonance_universe: wrote {len(rows)} rows  (active total now {total})")
    print(f"liquidity floor requested : ${min_dollar_vol:,.0f}/day")
    print(f"effective floor (min kept): ${effective_floor:,.0f}/day"
          + ("  [capped to most-liquid %d]" % max_extras if len(kept) > max_extras else ""))
    print(f"price band                : ${price_min} .. ${price_max}")
    print(f"symbols with market_cap   : {n_with_mcap}/{len(rows)}")
    return {"written": len(rows), "active_total": total,
            "requested_floor": min_dollar_vol, "effective_floor": effective_floor}


def main():
    ap = argparse.ArgumentParser(description="build the resonance_universe spring-candidate table")
    ap.add_argument("--min-dollar-vol", type=float, default=MIN_DOLLAR_VOL)
    ap.add_argument("--price-min", type=float, default=PRICE_MIN)
    ap.add_argument("--price-max", type=float, default=PRICE_MAX)
    ap.add_argument("--max-extras", type=int, default=MAX_EXTRAS)
    ap.add_argument("--lookback-days", type=int, default=BAR_LOOKBACK_DAYS)
    ap.add_argument("--max-dollar-vol", type=float, default=MAX_DOLLAR_VOL)
    a = ap.parse_args()
    build(a.min_dollar_vol, a.price_min, a.price_max, a.max_extras, a.lookback_days,
          a.max_dollar_vol)


if __name__ == "__main__":
    main()
