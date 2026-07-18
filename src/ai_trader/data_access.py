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
      WHERE e.en>=5 AND o.op>0 AND (f.hi/e.en-1)*100 >= ?
      ORDER BY fwd_max_gain DESC LIMIT 60
    """, (date, date, date, date, date, date, date, date, minpct)).fetchall()
    print(f"# winners on {date}: gained >= {minpct}% from the 09:35 price to a later high")
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
    a = ap.parse_args()
    if a.cmd == "schema": schema()
    elif a.cmd == "sql": run_sql(a.query)
    elif a.cmd == "bars": bars(a.sym, a.date, a.feed)
    elif a.cmd == "field": field(a.date, a.minute)
    elif a.cmd == "winners": winners(a.date, a.minpct)


if __name__ == "__main__":
    main()
