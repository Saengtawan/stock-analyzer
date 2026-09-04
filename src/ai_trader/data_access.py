"""Read-only historical data access — so the AI can DIGEST the data ITSELF.

Neutral plumbing ONLY. No thresholds, no filters, no 'buy/avoid', no conclusions.
The AI calls this to investigate whatever IT wants — how movers behave by time of
day, a name's past intraday path, the base rate of some setup — and draws its OWN
conclusions from the raw numbers. Code hands over facts; the AI does all the judging.

CLI (via scripts/ai_trader_data.sh):
  schema                      -> tables + columns in the historical DB
  sql "<SELECT ...>"          -> run a read-only query (DB opened mode=ro; SELECT only)
  bars SYM YYYY-MM-DD [feed]  -> raw 1-min OHLCV for that symbol/day (feed sip|iex)
  field YYYY-MM-DD MINUTE     -> the reconstructed mover field at a past ET minute
  winners YYYY-MM-DD [minpct] -> past day's actual >=minpct% intraday winners + their 09:35 look
  gates YYYY-MM-DD            -> pre-open-KNOWABLE gate inputs + frozen-prior gate STATE (KNIFE/SNAPBACK)
"""
from __future__ import annotations
import argparse, sqlite3, datetime, zoneinfo, requests, os, re
from .universe import _keys

DB = "data/trade_history.db"
ET = zoneinfo.ZoneInfo("America/New_York")
UTC = zoneinfo.ZoneInfo("UTC")
# sim guard: when set (AI_SIM_CUTOFF=YYYY-MM-DD), refuse any access to data ON OR AFTER that
# date, so a point-in-time replay can't peek at the sim day or the future (no lookahead).
SIM_CUTOFF = os.environ.get("AI_SIM_CUTOFF")


def _blocked(dates):
    if SIM_CUTOFF:
        for d in dates:
            if d and d >= SIM_CUTOFF:
                print(f"BLOCKED (sim lookahead guard): data on/after {SIM_CUTOFF} is off-limits "
                      f"(you referenced {d}). Query only strictly-earlier dates.")
                return True
    return False


def _ro():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)   # read-only at the DB level


def schema():
    c = _ro()
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        cols = [r[1] for r in c.execute(f"PRAGMA table_info('{t}')")]
        try:
            n = c.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
        except Exception:
            n = "?"
        print(f"{t} ({n} rows): {', '.join(cols)}")


def run_sql(q, limit=300):
    # mode=ro already blocks writes; this is just a clearer error than a lock failure
    if not q.lstrip().lower().startswith(("select", "with")):
        print("ERROR: read-only — start with SELECT (or WITH ... SELECT)."); return
    if _blocked(re.findall(r"\d{4}-\d{2}-\d{2}", q)):   # any date literal >= sim cutoff -> refuse
        return
    c = _ro()
    try:
        cur = c.execute(q)
        cols = [d[0] for d in cur.description]
        print("\t".join(cols))
        for i, row in enumerate(cur):
            if i >= limit:
                print(f"... (stopped at {limit} rows — add LIMIT / aggregate to see the rest)"); break
            print("\t".join("" if x is None else str(x) for x in row))
    except Exception as e:
        print("ERROR:", e)


def bars(sym, date, feed="sip"):
    """Raw 1-min OHLCV 09:30-16:00 ET for one symbol/day — no computed columns added."""
    if _blocked([date]):
        return
    hdr = _keys()
    u0 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=9, minute=30, tzinfo=ET).astimezone(UTC)
    u1 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=16, minute=0, tzinfo=ET).astimezone(UTC)
    r = requests.get("https://data.alpaca.markets/v2/stocks/bars", headers=hdr, params={
        "symbols": sym, "timeframe": "1Min", "start": u0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": u1.strftime("%Y-%m-%dT%H:%M:%SZ"), "feed": feed, "limit": 10000}, timeout=30).json()
    print("et_min\tt\to\th\tl\tc\tv\tvw")
    for b in r.get("bars", {}).get(sym, []):
        dt = datetime.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        print(f"{dt.hour*60+dt.minute}\t{dt:%H:%M}\t{b['o']}\t{b['h']}\t{b['l']}\t{b['c']}\t{b['v']}\t{b.get('vw','')}")


def drivers(date, minute=576):
    """LIVE MACRO DRIVERS as of ET `minute` (default 576=09:36) — the tradeable proxies for the
    forces that move a whole group, so you can CONFIRM a driver is actually running at scan time
    (the missing 'is BTC really ripping right now?' check). Point-in-time: 1-min bars <= minute.
    gain = % vs 09:30 open; d10 = last ~10-min move (still extending?). feed=iex today, sip past."""
    minute = int(minute)
    proxies = {"IBIT": "Bitcoin", "USO": "Crude oil", "TLT": "Rates (up=yields DOWN)",
               "GLD": "Gold", "UUP": "US dollar", "SMH": "Semis", "QQQ": "Big tech",
               "SPY": "Broad mkt", "XLE": "Energy", "VXX": "Volatility"}
    today = datetime.datetime.now(ET).strftime("%Y-%m-%d")
    feed = "iex" if date == today else "sip"
    hdr = _keys()
    u0 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=9, minute=30, tzinfo=ET).astimezone(UTC)
    endet = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=minute//60, minute=minute % 60, tzinfo=ET)
    u1 = endet.astimezone(UTC)
    r = requests.get("https://data.alpaca.markets/v2/stocks/bars", headers=hdr, params={
        "symbols": ",".join(proxies), "timeframe": "1Min", "start": u0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": u1.strftime("%Y-%m-%dT%H:%M:%SZ"), "feed": feed, "limit": 10000}, timeout=30).json()
    print(f"# LIVE MACRO DRIVERS on {date} as of {minute//60:02d}:{minute%60:02d} ET ({feed}) — "
          "is the driver actually moving NOW? gain=vs open, d10=last~10min")
    print("proxy\tdriver\tgain\td10\tstill_extending")
    for sym, name in proxies.items():
        bl = r.get("bars", {}).get(sym, [])
        if not bl:
            print(f"{sym}\t{name}\t(no data)"); continue
        o, last = bl[0]["o"], bl[-1]["c"]
        gain = (last / o - 1) * 100 if o else 0.0
        d10 = (last / bl[-11]["c"] - 1) * 100 if len(bl) >= 11 and bl[-11]["c"] else None
        ext = "YES" if (d10 is not None and ((gain > 0 and d10 > 0) or (gain < 0 and d10 < 0))) else ("na" if d10 is None else "no(fading)")
        print(f"{sym}\t{name}\t{gain:+.2f}\t{('%+.2f'%d10) if d10 is not None else 'na'}\t{ext}")


def action(date, minute=600):
    """MARKET ACTION as of ET `minute` (minute-from-midnight; 600=10:00), per SECTOR — the raw
    fact of what money is ACTUALLY doing right now (not what the headlines say). Point-in-time by
    construction: only reads 5-min bars at/before `minute`, so no lookahead even on the sim day.
    Shows, per sector: how many movers, their avg gain-from-open NOW, and how many are RECLAIMING
    (were red earlier, green now = the beaten group being bought back)."""
    minute = int(minute); cut = f"{minute//60:02d}:{minute%60:02d}"
    c = _ro()
    rows = c.execute("""
      WITH o AS (SELECT symbol, open op FROM intraday_bars_5m WHERE date=? AND time_et LIKE '09:30%'),
           b AS (SELECT symbol, close cl, low lo, time_et,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY time_et DESC) rn
                 FROM intraday_bars_5m WHERE date=? AND substr(time_et,1,5)<=?),
           lo AS (SELECT symbol, MIN(lo) lomin FROM b GROUP BY symbol),
           nowc AS (SELECT symbol, cl FROM b WHERE rn=1),
           f AS (SELECT symbol FROM stock_fundamentals)
      SELECT sf.sector,
             (nowc.cl/o.op-1)*100 gain_now,
             (lo.lomin/o.op-1)*100 low_sofar
      FROM o JOIN nowc ON o.symbol=nowc.symbol JOIN lo ON o.symbol=lo.symbol
             JOIN stock_fundamentals sf ON o.symbol=sf.symbol
      WHERE o.op>0 AND nowc.cl>=5 AND ABS((nowc.cl/o.op-1)*100)>=1.0 AND sf.sector IS NOT NULL
    """, (date, date, cut)).fetchall()
    agg = {}
    for sec, g, lows in rows:
        d = agg.setdefault(sec, [0, 0.0, 0])
        d[0] += 1; d[1] += g
        if g > 0 and lows is not None and lows < -1.0:   # green now but was red -> reclaiming
            d[2] += 1
    print(f"# MARKET ACTION on {date} as of {cut} ET — per sector (raw, point-in-time)")
    print("sector\tn_movers\tavg_gain_now\tn_reclaiming(red->green)")
    for sec, (n, gs, rec) in sorted(agg.items(), key=lambda kv: -(kv[1][1]/kv[1][0] if kv[1][0] else 0)):
        if n < 3: continue
        print(f"{sec}\t{n}\t{gs/n:+.2f}\t{rec}")


def gates(date):
    """PRE-OPEN GATES — the frozen-prior gate inputs, using ONLY pre-open-knowable info
    (prior-session closes). NEVER reads a same-day close-stamped label (spy_regime / same-day
    vix_close) — those co-move with the very forward return we predict (circular look-ahead).

    Prints the raw facts (prior VIX close, prior-session SPY tape return) AND the resulting
    frozen-prior gate STATE (KNIFE / SNAPBACK / MOMENTUM) from DAY_MODEL_v2. The live-VIX-at-open
    and the economic calendar are NOT in this DB — the gate defers those to a live ^VIX quote and
    a calendar check (WebSearch), using the prior close as the pre-open baseline."""
    if _blocked([date]):
        return
    c = _ro()
    # last 3 sessions strictly before `date` that actually have a close stamped (skips
    # not-yet-collected weekend/holiday rows) — all pre-open-knowable this morning.
    rows = c.execute(
        "SELECT date, vix_close, spy_close FROM macro_snapshots "
        "WHERE date < ? AND spy_close IS NOT NULL AND vix_close IS NOT NULL "
        "ORDER BY date DESC LIMIT 3", (date,)).fetchall()
    print(f"# PRE-OPEN GATES for {date} — pre-open-KNOWABLE inputs ONLY (no same-day close label)")
    if len(rows) < 2:
        print("insufficient prior macro rows — cannot form the gate; treat as ABSTAIN-lean and "
              "confirm VIX/tape live via WebSearch.")
        return
    d1, vix1, spy1 = rows[0]
    d2, _, spy2 = rows[1]
    d1_ret = (spy1 / spy2 - 1) * 100 if (spy1 and spy2) else None
    print(f"prior_close_date   {d1}")
    print(f"prior_vix_close    {vix1}   # proxy for VIX-at-open; CONFIRM with a live ^VIX quote (WebSearch)")
    print(f"d1_spy_tape_ret    {d1_ret:+.2f}%   # prior session: {d2}->{d1}  (down/washout vs healthy)")
    print("# --- frozen-prior GATE STATE (DAY_MODEL_v2; all derived from the above only) ---")
    knife = vix1 is not None and vix1 > 28
    print(f"KNIFE gate     : prior VIX {vix1} {'>' if knife else '<='} 28  -> "
          + ("ARMED by prior close — if live VIX>28 AND the open is weak, do NOT dip-buy the red pool; abstain/defensive."
             if knife else
             "not armed by prior close (still CONFIRM live VIX + open before dip-buying a red pool)."))
    wash = d1_ret is not None and d1_ret < -1.0
    print(f"SNAPBACK prior : D-1 ret {d1_ret:+.2f}% {'<' if wash else '>='} -1%  -> "
          + (("ACTIVE on the beaten pool — small; year-dependent; strongest when prior VIX>28."
              if wash else "INACTIVE (no washout to snap back from).")))
    print("MOMENTUM tilt  : on a healthy tape (no knife), default lean = the up>2 pool at 09:35, "
          "small & tail-harvested across a few names — NOT one concentrated bet.")
    print("REMINDER: read the ACTION (ai_trader_data.sh action %s 576) not the headline — a macro story "
          "earns a trade ONLY if the underlying gapped AND its names are actually up>2 at 09:35. Check the "
          "econ calendar (Fed/CPI/jobs) via WebSearch; reduce/abstain into a pre-print." % date)
    print("BANNED: same-day spy_regime & same-day vix_close (close-stamped look-ahead).")


def names(date, sector, minute=600):
    """Point-in-time (bars <= `minute`, same cutoff as action() so NO lookahead): the individual
    movers inside ONE sector as of ET minute — gain-from-open now, low-so-far (reclaim depth),
    price. Lets the AI see WHICH names in the bid group have room to keep running."""
    minute = int(minute); cut = f"{minute//60:02d}:{minute%60:02d}"
    c = _ro()
    rows = c.execute("""
      WITH o AS (SELECT symbol, open op FROM intraday_bars_5m WHERE date=? AND time_et LIKE '09:30%'),
           b AS (SELECT symbol, close cl, low lo, time_et,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY time_et DESC) rn
                 FROM intraday_bars_5m WHERE date=? AND substr(time_et,1,5)<=?),
           lo AS (SELECT symbol, MIN(lo) lomin FROM b GROUP BY symbol),
           nowc AS (SELECT symbol, cl FROM b WHERE rn=1)
      SELECT sf.sector, o.symbol,
             ROUND((nowc.cl/o.op-1)*100,2) gain_now,
             ROUND((lo.lomin/o.op-1)*100,2) low_sofar,
             ROUND(nowc.cl,2) px
      FROM o JOIN nowc ON o.symbol=nowc.symbol JOIN lo ON o.symbol=lo.symbol
             JOIN stock_fundamentals sf ON o.symbol=sf.symbol
      WHERE o.op>0 AND nowc.cl>=5 AND ((nowc.cl/o.op-1)*100)>=1.0 AND sf.sector=?
      ORDER BY gain_now DESC
    """, (date, date, cut, sector)).fetchall()
    print(f"# {sector} movers on {date} as of {cut} ET (point-in-time)")
    print("sym\tgain_now\tlow_sofar\tpx\treclaim(red->green)")
    for sec, sym, g, lows, px in rows:
        rec = "YES" if (g > 0 and lows is not None and lows < -1.0) else ""
        print(f"{sym}\t{g:+.2f}\t{lows:+.2f}\t{px}\t{rec}")


def winners(date, minpct=3.0):
    """Raw fact table: on a PAST day, which stocks actually gained >=minpct% intraday from the
    ~09:35 price to their later high, and WHAT THEY LOOKED LIKE at 09:35 (gain-from-open, gap,
    early relative volume). No interpretation — study it and draw your own conclusions about
    what a 09:32 winner looks like. Uses 5-min bars from the DB (intraday_bars_5m)."""
    if _blocked([date]):
        return
    minpct = float(minpct)
    c = _ro()
    rows = c.execute("""
      WITH o AS (SELECT symbol,close op FROM intraday_bars_5m WHERE date=? AND time_et LIKE '09:30%'),
           e AS (SELECT symbol,close en FROM intraday_bars_5m WHERE date=? AND time_et LIKE '09:35%'),
           ev AS (SELECT symbol,SUM(volume) v FROM intraday_bars_5m WHERE date=? AND time_et<'09:40' GROUP BY symbol),
           f AS (SELECT symbol,MAX(high) hi, (SELECT close FROM intraday_bars_5m b2 WHERE b2.symbol=b1.symbol AND b2.date=? ORDER BY time_et DESC LIMIT 1) cl
                 FROM intraday_bars_5m b1 WHERE date=? AND time_et>='09:35' GROUP BY symbol),
           pc AS (SELECT symbol,close prev FROM stock_daily_ohlc WHERE date=(SELECT MAX(date) FROM stock_daily_ohlc WHERE date<?)),
           av AS (SELECT symbol,AVG(volume) a FROM stock_daily_ohlc WHERE date<? AND date>=date(?, '-30 day') GROUP BY symbol)
      SELECT o.symbol,
             round((e.en/o.op-1)*100,1)  AS gain_at_0935,
             round((o.op/pc.prev-1)*100,1) AS gap,
             round(ev.v/(av.a*10.0/390),1) AS rv_0935,
             round((f.hi/e.en-1)*100,1)   AS fwd_max_gain,
             round((f.cl/e.en-1)*100,1)   AS fwd_close
      FROM o JOIN e ON o.symbol=e.symbol JOIN f ON o.symbol=f.symbol
             JOIN ev ON o.symbol=ev.symbol LEFT JOIN pc ON o.symbol=pc.symbol LEFT JOIN av ON o.symbol=av.symbol
      WHERE e.en>=5 AND o.op>0 AND (f.cl/e.en-1)*100 >= ?
      ORDER BY fwd_close DESC LIMIT 60
    """, (date, date, date, date, date, date, date, date, minpct)).fetchall()
    print(f"# EOD winners on {date}: bought at 09:35 and HELD to the close, gained >= {minpct}% "
          f"at the 16:00 close (no stop). fwd_close = the actual hold-to-close return.")
    print("symbol\tgain_at_0935\tgap\trv_0935\tfwd_max_gain\tfwd_close")
    for r in rows:
        print("\t".join("" if x is None else str(x) for x in r))


def field(date, minute):
    """The reconstructed mover field at a past ET minute (raw Mover rows, no filtering)."""
    if _blocked([date]):
        return
    from .universe_sim import gather_universe_sim
    ms = gather_universe_sim(date, minute=int(minute), db=DB)
    print("sym\tgain\tprice\tpeak\ttrough\tslope10\tvwap_dist\trel_vol\tprev_close")
    for m in ms:
        print(f"{m.sym}\t{m.pct_change}\t{m.price}\t{m.peak_pct}\t{m.trough_pct}\t{m.slope10}\t"
              f"{m.vwap_dist}\t{m.rel_vol}\t{m.prev_close}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("schema")
    s = sub.add_parser("sql"); s.add_argument("query")
    b = sub.add_parser("bars"); b.add_argument("sym"); b.add_argument("date"); b.add_argument("feed", nargs="?", default="sip")
    f = sub.add_parser("field"); f.add_argument("date"); f.add_argument("minute")
    w = sub.add_parser("winners"); w.add_argument("date"); w.add_argument("minpct", nargs="?", default="3")
    ac = sub.add_parser("action"); ac.add_argument("date"); ac.add_argument("minute", nargs="?", default="600")
    gt = sub.add_parser("gates"); gt.add_argument("date")
    nm = sub.add_parser("names"); nm.add_argument("date"); nm.add_argument("sector"); nm.add_argument("minute", nargs="?", default="600")
    dr = sub.add_parser("drivers"); dr.add_argument("date"); dr.add_argument("minute", nargs="?", default="576")
    a = ap.parse_args()
    if a.cmd == "schema": schema()
    elif a.cmd == "sql": run_sql(a.query)
    elif a.cmd == "bars": bars(a.sym, a.date, a.feed)
    elif a.cmd == "field": field(a.date, a.minute)
    elif a.cmd == "winners": winners(a.date, a.minpct)
    elif a.cmd == "action": action(a.date, a.minute)
    elif a.cmd == "gates": gates(a.date)
    elif a.cmd == "names": names(a.date, a.sector, a.minute)
    elif a.cmd == "drivers": drivers(a.date, a.minute)


if __name__ == "__main__":
    main()
