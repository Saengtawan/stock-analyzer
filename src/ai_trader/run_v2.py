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


def execute(date, log=True):
    try:
        dec = Decision.load(date)
    except Exception as e:
        dec = Decision.abstain(date, f"no decision file ({e})")
    prices = _live_prices([pk.sym for pk in dec.picks])
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    if log:
        journal.log_decision(dec, prices, ts)

    print(f"=== ai_trader v2 execute {date} ===")
    print(f"regime: {dec.regime}")
    if not dec.picks:
        print(f"ABSTAIN — {dec.abstain_reason}")
        return dec
    for pk in dec.picks:
        px = prices.get(pk.sym, "?")
        ex = f"trail {pk.trail_pct}%" if pk.exit_style == "trail" else "hold-EOD"
        print(f"PICK {pk.sym} [{pk.archetype}] @ {px}  exit={ex} stop{pk.hard_stop}%")
        print(f"     why: {pk.reason}")
    return dec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["brief", "execute", "outcome"])
    ap.add_argument("--date", required=True)
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--sim-minute", type=int, default=None,
                    help="reconstruct the field at this ET minute-from-midnight (576=09:36)")
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    if a.cmd == "brief":
        print(build_brief(a.date, top=a.top, sim_minute=a.sim_minute))
    elif a.cmd == "execute":
        execute(a.date, log=not a.no_log)
    elif a.cmd == "outcome":
        from .outcome_v2 import fill
        fill(a.date)


if __name__ == "__main__":
    main()
