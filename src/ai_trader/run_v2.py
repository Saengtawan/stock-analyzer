"""v2 orchestrator — AI-first pipeline runner.

  brief    : gather universe -> assemble context -> print (the AI reads this ~09:35 ET)
  execute  : load the AI's plans/decisions/<date>.json -> validate live prices -> log + emit
  outcome  : fill realized outcomes per pick (archetype-matched exit)

The AI (a Claude session) sits between `brief` and `execute`: reads the brief, judges,
writes the decision file. Fail-safe: no decision file -> abstain (no trade).
"""
from __future__ import annotations
import argparse, datetime, sqlite3, zoneinfo, requests
from .context_v2 import build as build_brief
from .decision import Decision
from . import journal

UTC = zoneinfo.ZoneInfo("UTC"); ET = zoneinfo.ZoneInfo("America/New_York")


def _keys():
    kk = {}
    for l in open(".env"):
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1); kk[k.strip()] = v.strip().strip("\"'")
    return {"APCA-API-KEY-ID": kk.get("ALPACA_API_KEY"),
            "APCA-API-SECRET-KEY": kk.get("ALPACA_SECRET_KEY")}


def _live_prices(syms):
    if not syms:
        return {}
    hdr = _keys()
    r = requests.get("https://data.alpaca.markets/v2/stocks/trades/latest",
                     headers=hdr, params={"symbols": ",".join(syms), "feed": "iex"},
                     timeout=15).json()
    return {s: t["p"] for s, t in r.get("trades", {}).items()}


def _sectors(syms, db="data/trade_history.db"):
    if not syms:
        return {}
    p = sqlite3.connect(db)
    q = "SELECT symbol, sector FROM stock_fundamentals WHERE symbol IN (%s)" % ",".join("?" * len(syms))
    return {s: sec for s, sec in p.execute(q, syms) if sec}


def execute(date, log=True, primary_n=2, mode="live"):
    try:
        dec = Decision.load(date)
    except Exception as e:
        dec = Decision.abstain(date, f"no decision file ({e})")
    prices = _live_prices([pk.sym for pk in dec.picks])
    sectors = _sectors([pk.sym for pk in dec.picks])
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    if log:
        journal.log_decision(dec, prices, ts, primary_n=primary_n, mode=mode, sectors=sectors)

    print(f"=== ai_trader v2 execute {date} ({mode}) ===")
    print(f"regime: {dec.regime}")
    if not dec.picks:
        print(f"ABSTAIN — {dec.abstain_reason}")
        return dec
    # B4: warn if the two primaries are the same bet (same sector) — correlated, not diversified
    prim = dec.picks[:primary_n]
    psec = [sectors.get(pk.sym) for pk in prim]
    if len(prim) >= 2 and psec[0] and psec[0] == psec[1]:
        print(f"⚠️ CORRELATION: both primaries are {psec[0]} — same bet, not 2 independent picks "
              f"(size as ~one position).")
    # show the top `primary_n`; the rest are bench (found, tracked, revealed on request)
    for pk in prim:
        px = prices.get(pk.sym, "?")
        ex = f"trail {pk.trail_pct}%" if pk.exit_style == "trail" else "hold-EOD"
        print(f"PICK {pk.sym} [{pk.archetype}] @ {px}  exit={ex} stop{pk.hard_stop}%  ({sectors.get(pk.sym,'?')})")
        print(f"     why: {pk.reason}")
    bench = dec.picks[primary_n:]
    if bench:
        print(f"BENCH ({len(bench)} more found, ask to see): "
              + ", ".join(f"{pk.sym}[{pk.archetype}]" for pk in bench))
    return dec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["brief", "execute", "outcome"])
    ap.add_argument("--date", required=True)
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--sim-minute", type=int, default=None,
                    help="reconstruct the field at this ET minute-from-midnight (576=09:36)")
    ap.add_argument("--no-log", action="store_true")
    ap.add_argument("--replay", action="store_true",
                    help="mark this as a dev/backfill re-run (mode='replay') so it never counts "
                         "as a live trade in the forward record")
    a = ap.parse_args()
    if a.cmd == "brief":
        print(build_brief(a.date, top=a.top, sim_minute=a.sim_minute))
    elif a.cmd == "execute":
        execute(a.date, log=not a.no_log, mode=("replay" if a.replay else "live"))
    elif a.cmd == "outcome":
        from .outcome_v2 import fill
        fill(a.date)


if __name__ == "__main__":
    main()
