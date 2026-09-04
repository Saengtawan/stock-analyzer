"""orb_trader / channels / numeric.py — DIGESTING numeric channels (SQL, point-in-time).

Rule: every channel RETURNS A SHORT SUMMARY, never a raw dump. The channel does the reduction
so the brain reads a few computed fields per name, not thousands of rows. This is the token win.
All channels are read-only and must be point-in-time (no close-stamped / look-ahead fields):
every read uses ONLY bars with time_et <= the given ET minute, so calling a channel at minute M
gives the SAME answer whether or not later bars exist. This is RAIL 3 (live-faithful): each field
is computable identically in real time from the same source.

Channels
  situation(date, minute)    -> per liquid-universe name AT that ET minute, ONE compact row:
                                {sym, gap_pct, premkt_vol_vs_avg, rel_vol, vwap_dist_pct,
                                 is_reclaiming, from_open_pct, sector}. The early read for pass ①.
  confirm(date, sym, minute) -> the ORB trigger signals for one name:
                                {or_high, or_low, cur, cur_vs_or_high_pct, vol_surge,
                                 vwap_reclaim, still_extending, or_bars, feed}. Opening range =
                                 first N=3 ONE-minute bars (09:30-09:32, complete at 09:33), so
                                 confirm can fire ~09:33 instead of ~09:40. 1-min bars come from
                                 Alpaca (feed=iex today / sip past) — intraday_bars_5m has no
                                 1-min data. For pass ②.
  drivers(date, minute)      -> live macro proxies (IBIT/USO/TLT/GLD/UUP/SMH/QQQ/SPY/XLE/VXX):
                                gain-from-open + last-10min delta (still extending?). Confirm a
                                beta play is actually running now. Feed: iex today / sip past.
  breadth(date, minute)      -> tape state: SPY gain, sectors green/red, VXX move. Point-in-time.

Data source: data/trade_history.db (intraday_bars_5m, universe_stocks, stock_fundamentals,
stock_daily_ohlc). The macro-proxy ETFs (IBIT/VXX) are not reliably in the DB intraday, so
drivers/breadth read those from the Alpaca bars API (the same source the live scanner uses).

Point-in-time logic is mined from src/ai_trader/data_access.py (action/names/drivers); the
statistical / bucket-average parts of that module are intentionally dropped.

CLI:
  python -m orb_trader.channels.numeric situation DATE MINUTE [TOPN]
  python -m orb_trader.channels.numeric confirm   DATE SYM MINUTE
  python -m orb_trader.channels.numeric drivers    DATE MINUTE
  python -m orb_trader.channels.numeric breadth    DATE MINUTE
"""
from __future__ import annotations
import argparse
import datetime
import sqlite3
import zoneinfo

DB = "data/trade_history.db"
ET = zoneinfo.ZoneInfo("America/New_York")
UTC = zoneinfo.ZoneInfo("UTC")
BARS_PER_DAY = 390.0 / 5.0       # 78 five-minute bars in a RTH session


def _cut(minute):
    """ET minute-from-midnight -> 'HH:MM' string cutoff (inclusive)."""
    minute = int(minute)
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _conn(db):
    """Read-only connection — writes are blocked at the DB layer, never by us."""
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


# ----------------------------------------------------------------------------- situation
def situation(date, minute, db=DB):
    """Early read of the liquid universe as of ET `minute`. Point-in-time: only bars whose
    time_et <= `minute` are touched. Returns ONE compact row per name (a dict), sorted by
    rel_vol descending so the standouts sort to the top. Never returns raw bars.

    Fields per name:
      gap_pct           09:30 open vs prior daily close  (pre-open knowable)
      premkt_vol_vs_avg pre-market volume (04:00-09:29) as a fraction of a normal day's volume
      rel_vol           RTH volume so far / (avg-daily * fraction-of-session-elapsed)
      vwap_dist_pct     current price vs session VWAP so far
      is_reclaiming     dipped >=0.5% red off the open then green now (beaten name being bought)
      from_open_pct     current price vs the 09:30 open
      sector            sector (universe_stocks, backfilled from fundamentals when 'Unknown')
    """
    cut = _cut(minute)
    c = _conn(db)
    rows = c.execute(
        """
        WITH base AS (
            SELECT symbol, substr(time_et,1,5) tm, open, high, low, close, volume, vwap
            FROM intraday_bars_5m
            WHERE date = ? AND substr(time_et,1,5) <= ?
        ),
        op AS (SELECT symbol, open op FROM base WHERE tm = '09:30'),
        rth AS (SELECT * FROM base WHERE tm >= '09:30'),
        agg AS (
            SELECT symbol,
                   MAX(high) hi, MIN(low) lo,
                   SUM(volume) cumvol,
                   SUM(COALESCE(vwap, close) * volume) vwn,
                   SUM(volume) vwd,
                   COUNT(*) nb
            FROM rth GROUP BY symbol
        ),
        cur AS (
            SELECT symbol, close cl FROM (
                SELECT symbol, close,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY tm DESC) rn
                FROM rth
            ) WHERE rn = 1
        ),
        pm AS (SELECT symbol, SUM(volume) pmv FROM base WHERE tm < '09:30' GROUP BY symbol),
        pc AS (
            SELECT symbol, close prev FROM stock_daily_ohlc
            WHERE date = (SELECT MAX(date) FROM stock_daily_ohlc WHERE date < ?)
        ),
        av AS (
            SELECT symbol, AVG(volume) a FROM stock_daily_ohlc
            WHERE date < ? AND date >= date(?, '-30 day') GROUP BY symbol
        )
        SELECT u.symbol,
               COALESCE(NULLIF(u.sector, 'Unknown'), sf.sector, '?') sector,
               op.op, cur.cl, agg.hi, agg.lo, agg.cumvol, agg.vwn, agg.vwd, agg.nb,
               pm.pmv, pc.prev, av.a
        FROM universe_stocks u
        JOIN op  ON op.symbol  = u.symbol
        JOIN cur ON cur.symbol = u.symbol
        JOIN agg ON agg.symbol = u.symbol
        LEFT JOIN pm ON pm.symbol = u.symbol
        LEFT JOIN pc ON pc.symbol = u.symbol
        LEFT JOIN av ON av.symbol = u.symbol
        LEFT JOIN stock_fundamentals sf ON sf.symbol = u.symbol
        WHERE u.status = 'active' AND op.op > 0 AND cur.cl >= 3
        """,
        (date, cut, date, date, date),
    ).fetchall()

    out = []
    for (sym, sec, op, cl, hi, lo, cumvol, vwn, vwd, nb,
         pmv, prev, avg) in rows:
        vwap = (vwn / vwd) if vwd else None
        frac = (nb * 5.0 / 390.0) if nb else None
        out.append({
            "sym": sym,
            "gap_pct": round((op / prev - 1) * 100, 2) if prev else None,
            "premkt_vol_vs_avg": round(pmv / avg, 2) if (pmv and avg) else 0.0,
            "rel_vol": round(cumvol / (avg * frac), 2) if (avg and frac) else None,
            "vwap_dist_pct": round((cl / vwap - 1) * 100, 2) if vwap else None,
            "is_reclaiming": bool(cl > op and lo is not None and lo < op * 0.995),
            "from_open_pct": round((cl / op - 1) * 100, 2),
            "sector": sec,
        })
    out.sort(key=lambda r: (r["rel_vol"] is not None, r["rel_vol"] or 0), reverse=True)
    return out


# ------------------------------------------------------------------------------- confirm
OR_1MIN_BARS = 3   # opening range = first N one-minute bars (09:30,09:31,09:32 → complete 09:33)


def _etmin(t):
    """UTC ISO bar timestamp -> ET minute-from-midnight of the bar's START."""
    d = datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(ET)
    return d.hour * 60 + d.minute


def _alpaca_1min(sym, date, minute):
    """Point-in-time RTH 1-min bars for `sym` on `date`, from the Alpaca bars API — the SAME
    source (and iex-today / sip-past feed rule) the live scanner and drivers channel use, so it
    is live-faithful (RAIL 3). intraday_bars_5m has NO 1-minute data, so 1-min MUST come here.

    Point-in-time: a 1-min bar whose START is minute T closes at T+1, so it is only knowable at
    ET minute >= T+1. We therefore keep bars whose START etmin < `minute` (bar closed by `minute`)
    and >= 09:30. Calling at minute M never touches a bar that had not yet closed at M — so the
    answer at 09:33 can never use the 09:33/09:34 bars (they close later). Returns (bars, feed)
    where bars = [{t,o,h,l,c,v,vw}] sorted by time; empty list if the feed returned nothing."""
    import requests
    from src.ai_trader.universe import _keys
    minute = int(minute)
    today = datetime.datetime.now(ET).strftime("%Y-%m-%d")
    feed = "iex" if date == today else "sip"
    u0 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=9, minute=30, tzinfo=ET).astimezone(UTC)
    # request through `minute`; Python filter below enforces the strict point-in-time cut.
    u1 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(
        hour=minute // 60, minute=minute % 60, tzinfo=ET).astimezone(UTC)
    try:
        r = requests.get(
            "https://data.alpaca.markets/v2/stocks/bars", headers=_keys(),
            params={"symbols": sym, "timeframe": "1Min",
                    "start": u0.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": u1.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "feed": feed, "limit": 10000}, timeout=30).json()
    except Exception:
        return [], feed
    raw = r.get("bars", {}).get(sym, []) or []
    # RTH only + strict point-in-time: keep bars that had CLOSED by `minute` (start etmin < minute).
    bars = [b for b in raw if 570 <= _etmin(b["t"]) < minute]
    bars.sort(key=lambda b: b["t"])
    return bars, feed


def confirm(date, sym, minute, db=DB, n=OR_1MIN_BARS):
    """ORB trigger signals for one name as of ET `minute`, from Alpaca 1-MINUTE bars.
    Point-in-time (only bars that had closed by `minute`; see _alpaca_1min). The faster read:
    opening range = the first `n` one-minute bars from 09:30 (default 3 = 09:30,09:31,09:32,
    complete at 09:33), so confirm can fire ~09:33 instead of waiting for the 09:35 5-min bar.

    Returns:
      or_high, or_low        opening-range high / low over the first `n` 1-min bars
      cur                    latest price (last 1-min close <= minute)
      cur_vs_or_high_pct     how far current price is above (or below) the OR high — the break
      vol_surge              latest 1-min bar volume > 3x the avg 1-min bar volume so far
      vwap_reclaim           back above session VWAP (from the 1-min bars so far) after dipping below
      still_extending        rising into the print AND within 0.5% of the session high (not fading)
      or_bars                how many 1-min bars actually formed the opening range (<= n)
      feed                   'iex' (today) or 'sip' (past) — which Alpaca feed answered
    """
    bars, feed = _alpaca_1min(sym, date, minute)
    if not bars:
        why = ("Alpaca 1-min unavailable for this past date (sip returned no bars) — "
               "cannot confirm" if feed == "sip" else "no RTH 1-min bars <= minute yet")
        return {"sym": sym, "error": why, "feed": feed, "or_bars": 0}

    # opening range = first `n` 1-min bars from 09:30 (whatever is available so far)
    or_slice = bars[:n]
    or_high = max(b["h"] for b in or_slice)
    or_low = min(b["l"] for b in or_slice)

    cur = bars[-1]["c"]
    hi_sofar = max(b["h"] for b in bars)
    lo_sofar = min(b["l"] for b in bars)
    vwd = sum(b["v"] for b in bars)
    vwap = (sum(b.get("vw", b["c"]) * b["v"] for b in bars) / vwd) if vwd else None

    # 1-min-scaled volume surge: latest bar vs the average 1-min bar so far (need a few bars for
    # the average to mean anything). 3x mirrors the old 5-min "3x a normal bar" threshold, now on
    # the session's own 1-min pace rather than a 30-day daily average.
    vols = [b["v"] for b in bars]
    avg_1min_vol = (sum(vols) / len(vols)) if vols else 0
    vol_surge = bool(len(bars) >= 3 and avg_1min_vol > 0 and vols[-1] > 3 * avg_1min_vol)

    vwap_reclaim = bool(vwap and cur >= vwap and lo_sofar < vwap)

    rising = len(bars) >= 2 and bars[-1]["c"] > bars[-2]["c"]
    near_high = cur >= hi_sofar * 0.995
    still_extending = bool(rising and near_high)

    return {
        "sym": sym,
        "or_high": round(or_high, 2),
        "or_low": round(or_low, 2),
        "cur": round(cur, 2),
        "cur_vs_or_high_pct": round((cur / or_high - 1) * 100, 2) if or_high else None,
        "vol_surge": vol_surge,
        "vwap_reclaim": vwap_reclaim,
        "still_extending": still_extending,
        "or_bars": len(or_slice),
        "feed": feed,
    }


# ------------------------------------------------------------------ Alpaca bars (drivers/VXX)
def _alpaca_gains(syms, date, minute):
    """Point-in-time gain-from-open + last~10min delta for `syms` as of ET `minute`, from the
    Alpaca 1-min bars API (feed = iex today, sip for past dates — same source the live scanner
    uses, so it is live-faithful). Only requests bars 09:30..minute, so no look-ahead by
    construction. Returns ({sym: {gain, d10, last, open}}, feed) (missing symbols omitted)."""
    import requests
    from src.ai_trader.universe import _keys
    minute = int(minute)
    today = datetime.datetime.now(ET).strftime("%Y-%m-%d")
    feed = "iex" if date == today else "sip"
    u0 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=9, minute=30, tzinfo=ET).astimezone(UTC)
    u1 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(
        hour=minute // 60, minute=minute % 60, tzinfo=ET).astimezone(UTC)
    try:
        r = requests.get(
            "https://data.alpaca.markets/v2/stocks/bars", headers=_keys(),
            params={"symbols": ",".join(syms), "timeframe": "1Min",
                    "start": u0.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": u1.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "feed": feed, "limit": 10000}, timeout=30).json()
    except Exception:
        return {}, feed
    out = {}
    for sym in syms:
        bl = r.get("bars", {}).get(sym, [])
        if not bl:
            continue
        o, last = bl[0]["o"], bl[-1]["c"]
        gain = (last / o - 1) * 100 if o else None
        d10 = (last / bl[-11]["c"] - 1) * 100 if len(bl) >= 11 and bl[-11]["c"] else None
        out[sym] = {"gain": gain, "d10": d10, "last": last, "open": o}
    return out, feed


# ------------------------------------------------------------------------------- drivers
_PROXIES = {
    "IBIT": "Bitcoin", "USO": "Crude oil", "TLT": "Rates (up=yields DOWN)", "GLD": "Gold",
    "UUP": "US dollar", "SMH": "Semis", "QQQ": "Big tech", "SPY": "Broad mkt",
    "XLE": "Energy", "VXX": "Volatility",
}


def drivers(date, minute, db=DB):
    """Live macro proxies as of ET `minute`: is the driver actually MOVING right now? Point-in-time
    (only bars 09:30..minute). Returns {feed, proxies:[...]}, one dict per proxy:
      {proxy, driver, gain, d10, still_extending}  where gain=% vs 09:30 open, d10=last~10min move.
    still_extending = gain and d10 point the same way (the move is still being pushed)."""
    gains, feed = _alpaca_gains(list(_PROXIES), date, minute)
    out = []
    for sym, name in _PROXIES.items():
        g = gains.get(sym)
        if not g or g["gain"] is None:
            out.append({"proxy": sym, "driver": name, "gain": None, "d10": None,
                        "still_extending": None})
            continue
        gain, d10 = g["gain"], g["d10"]
        ext = None if d10 is None else ((gain > 0 and d10 > 0) or (gain < 0 and d10 < 0))
        out.append({"proxy": sym, "driver": name, "gain": round(gain, 2),
                    "d10": round(d10, 2) if d10 is not None else None, "still_extending": ext})
    return {"feed": feed, "proxies": out}


# ------------------------------------------------------------------------------- breadth
def breadth(date, minute, db=DB):
    """Tape state as of ET `minute`, point-in-time. Returns:
      spy_gain_pct       SPY gain from its 09:30 open (from DB 5-min bars)
      vxx_gain_pct       VXX move from open (from Alpaca; None if unavailable)
      sectors_green      # of sectors whose movers are net-green on average now
      sectors_red        # net-red
      n_movers           universe names moving >=1% (abs) from the open right now
      sector_detail      per-sector {n, avg_from_open} (movers >=1% abs, price>=3), sorted
    """
    cut = _cut(minute)
    c = _conn(db)

    spy = c.execute(
        """
        WITH b AS (SELECT substr(time_et,1,5) tm, open, close FROM intraday_bars_5m
                   WHERE date=? AND symbol='SPY' AND substr(time_et,1,5)>='09:30'
                         AND substr(time_et,1,5)<=?)
        SELECT (SELECT open FROM b WHERE tm='09:30'),
               (SELECT close FROM b ORDER BY tm DESC LIMIT 1)
        """,
        (date, cut),
    ).fetchone()
    spy_gain = round((spy[1] / spy[0] - 1) * 100, 2) if (spy and spy[0] and spy[1]) else None

    rows = c.execute(
        """
        WITH o AS (SELECT symbol, open op FROM intraday_bars_5m
                   WHERE date=? AND substr(time_et,1,5)='09:30'),
             cur AS (
                SELECT symbol, close cl FROM (
                    SELECT symbol, close,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY substr(time_et,1,5) DESC) rn
                    FROM intraday_bars_5m
                    WHERE date=? AND substr(time_et,1,5)>='09:30' AND substr(time_et,1,5)<=?
                ) WHERE rn=1)
        SELECT COALESCE(NULLIF(u.sector,'Unknown'), sf.sector, '?') sector,
               (cur.cl/o.op-1)*100 g
        FROM universe_stocks u
        JOIN o   ON o.symbol=u.symbol
        JOIN cur ON cur.symbol=u.symbol
        LEFT JOIN stock_fundamentals sf ON sf.symbol=u.symbol
        WHERE u.status='active' AND o.op>0 AND cur.cl>=3 AND ABS((cur.cl/o.op-1)*100)>=1.0
        """,
        (date, date, cut),
    ).fetchall()

    agg = {}
    for sec, g in rows:
        d = agg.setdefault(sec, [0, 0.0])
        d[0] += 1
        d[1] += g
    sector_detail = {sec: {"n": n, "avg_from_open": round(s / n, 2)}
                     for sec, (n, s) in agg.items() if n >= 3}
    green = sum(1 for v in sector_detail.values() if v["avg_from_open"] > 0)
    red = sum(1 for v in sector_detail.values() if v["avg_from_open"] < 0)

    vxx = _alpaca_gains(["VXX"], date, minute)[0].get("VXX")
    vxx_gain = round(vxx["gain"], 2) if (vxx and vxx["gain"] is not None) else None

    return {
        "spy_gain_pct": spy_gain,
        "vxx_gain_pct": vxx_gain,
        "sectors_green": green,
        "sectors_red": red,
        "n_movers": len(rows),
        "sector_detail": dict(sorted(sector_detail.items(),
                                     key=lambda kv: -kv[1]["avg_from_open"])),
    }


# ----------------------------------------------------------------------------------- CLI
def _fmt(v):
    return "" if v is None else (f"{v:+.2f}" if isinstance(v, float) else str(v))


def main():
    ap = argparse.ArgumentParser(description="orb_trader digesting numeric channels")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("situation"); s.add_argument("date"); s.add_argument("minute")
    s.add_argument("topn", nargs="?", default="25")
    cf = sub.add_parser("confirm"); cf.add_argument("date"); cf.add_argument("sym"); cf.add_argument("minute")
    dr = sub.add_parser("drivers"); dr.add_argument("date"); dr.add_argument("minute")
    br = sub.add_parser("breadth"); br.add_argument("date"); br.add_argument("minute")
    a = ap.parse_args()

    if a.cmd == "situation":
        rows = situation(a.date, a.minute)
        n = int(a.topn)
        print(f"# SITUATION {a.date} as of {_cut(a.minute)} ET — {len(rows)} liquid names, top {n} by rel_vol")
        print("sym\tsector\tgap%\tpmVolxAvg\trel_vol\tvwap_dist%\treclaim\tfrom_open%")
        for r in rows[:n]:
            print(f"{r['sym']}\t{r['sector'][:14]}\t{_fmt(r['gap_pct'])}\t{_fmt(r['premkt_vol_vs_avg'])}"
                  f"\t{_fmt(r['rel_vol'])}\t{_fmt(r['vwap_dist_pct'])}\t{'Y' if r['is_reclaiming'] else '-'}"
                  f"\t{_fmt(r['from_open_pct'])}")

    elif a.cmd == "confirm":
        r = confirm(a.date, a.sym, a.minute)
        print(f"# CONFIRM {a.sym} {a.date} as of {_cut(a.minute)} ET")
        for k, v in r.items():
            print(f"{k}\t{v}")

    elif a.cmd == "drivers":
        r = drivers(a.date, a.minute)
        print(f"# DRIVERS {a.date} as of {_cut(a.minute)} ET ({r['feed']}) — gain=vs open, d10=last~10min")
        print("proxy\tdriver\tgain\td10\tstill_extending")
        for p in r["proxies"]:
            ext = "" if p["still_extending"] is None else ("YES" if p["still_extending"] else "no(fading)")
            print(f"{p['proxy']}\t{p['driver']}\t{_fmt(p['gain'])}\t{_fmt(p['d10'])}\t{ext}")

    elif a.cmd == "breadth":
        r = breadth(a.date, a.minute)
        print(f"# BREADTH {a.date} as of {_cut(a.minute)} ET")
        print(f"spy_gain_pct\t{_fmt(r['spy_gain_pct'])}")
        print(f"vxx_gain_pct\t{_fmt(r['vxx_gain_pct'])}")
        print(f"sectors_green\t{r['sectors_green']}")
        print(f"sectors_red\t{r['sectors_red']}")
        print(f"n_movers\t{r['n_movers']}")
        print("-- sector_detail (sorted by avg_from_open) --")
        print("sector\tn\tavg_from_open%")
        for sec, d in r["sector_detail"].items():
            print(f"{sec[:16]}\t{d['n']}\t{_fmt(d['avg_from_open'])}")


if __name__ == "__main__":
    main()
