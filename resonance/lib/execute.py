"""resonance / lib / execute.py — PAPER execution (never places a real order).

NOTE ON THE ENTRY PRICE (2026-09-04): the paper record grades at the 09:30 open, but that is NOT how
the trade is actually entered. The operator buys with a LIMIT set ~09:25 at winLo(09:05-09:25) x an
AI-judged buffer, and the plan now carries `winlo` / `limit` / `limit_reason` / `limit_flat_1015` for
every pick. Grading at the open is kept deliberately: it is unambiguous, needs no fill assumption, and
is CONSERVATIVE — across 11 picks the limit priced about +0.87pp better than the open. So the forward
record understates the operator's method rather than flattering it, which is the right direction for a
record to be wrong in. If limit fills are ever graded here, they must be modelled explicitly (a resting
limit fills when price trades at or below it) and never scored before the close.

The resonance trade is mechanical to *execute*: entry = the RTH 09:30 open, exit = the 15:55 ET
close, hold-to-EOD, no intraday management. So this module just resolves those two prices from the
stored 5-min bars and writes the forward record. NO Alpaca order is EVER sent — the user places the
buy manually at their broker. Sizing is small/fixed/equal (no size-up lever by design; the account
rails cap it: 1% risk, <= 3 positions).

Price resolution (respects the extended-hours gotcha — memory `reference_intraday_bars_extended_hours`):
  entry "open"      -> the `open` of the pinned time_et='09:30' RTH bar (never "first bar").
  exit  "hold_eod"  -> the `close` of the pinned time_et='15:55' RTH bar (never "last bar" —
                       extended-hours bars would inflate it).

Flow:
  paper_buy(date, sym, mode)  -> resolve 09:30 open, enforce price cap <$400 + max-3, log the pick.
  realize(date, sym, mode)    -> resolve 15:55 close, compute result% + vs_spy (SPY open->close),
                                 stamp the journal row via journal.fill_outcome.
  process_plan(date, mode)    -> read plans/<DATE>.plan.json, paper_buy up to 3 picks (cap-gated),
                                 then realize each — the whole mechanical half of learn.sh.

CLI:
  python -m resonance.lib.execute plan    DATE [mode]     # buy + realize the plan's picks
  python -m resonance.lib.execute realize DATE SYM [mode] # realize a single already-logged pick
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

from resonance.lib import journal

try:                                    # .env carries the Alpaca keys the SIP fallback needs.
    from dotenv import load_dotenv      # Under cron/CLI they are NOT in os.environ, so without
    load_dotenv(".env")                 # this the fallback raised KeyError inside its bare
except Exception:                       # `except Exception` and silently skipped picks (TEAM,
    pass                                # 2026-08-07) and every vs_spy. Never fatal.

PRICE_DB = "data/trade_history.db"     # source of the 5-min bars (read-only)
PRICE_CAP = 400.0                       # skip any name whose entry >= this (account-rail guard)
MAX_PICKS = 3                           # max simultaneous paper positions
PLANS_DIR = "resonance/plans"


# ------------------------------------------------------------------------------- price channel
def _price_conn(db=PRICE_DB):
    """Read-only connection to the bars DB. Writes are blocked at the DB layer."""
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


_SIP_CACHE = {}


def _sip_session(sym, date):
    """Fallback: fetch RTH 5-min bars for (sym, date) from Alpaca SIP when the LOCAL bars DB is
    missing them. The local intraday_bars_5m is routinely incomplete at the 16:30 learn — SPY has
    had 0 rows for days and fresh picks often lack a 09:30 print — which silently made the mechanical
    grader SKIP winning picks (the learn AI had to hand-patch from SIP). At 16:30 ET the session
    closed 30 min ago, so it is outside SIP's 15-min recent-data restriction. Returns
    {time_et: (open, close)} or {} on any failure (missing keys / API error -> caller sees None,
    same as before, never crashes learn)."""
    key = (sym.upper(), date)
    if key in _SIP_CACHE:
        return _SIP_CACHE[key]
    out = {}
    try:
        import datetime, zoneinfo
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from alpaca.data.enums import DataFeed, Adjustment
        ET = zoneinfo.ZoneInfo("America/New_York")
        dc = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
        d = datetime.date.fromisoformat(date)
        start = datetime.datetime.combine(d, datetime.time(9, 30), ET)
        end = datetime.datetime.combine(d, datetime.time(16, 0), ET)
        req = StockBarsRequest(symbol_or_symbols=[sym.upper()],
                               timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                               start=start, end=end, adjustment=Adjustment.ALL, feed=DataFeed.SIP)
        df = dc.get_stock_bars(req).df
        if df is not None and not df.empty:
            for (_s, ts), r in df.iterrows():
                et = ts.tz_convert(ET)
                if et.date().isoformat() != date:
                    continue
                out[et.strftime("%H:%M")] = (float(r["open"]), float(r["close"]))
    except Exception:
        out = {}
    _SIP_CACHE[key] = out
    return out


def _bar_field(sym, date, time_et, field, db=PRICE_DB):
    """Return `field` ('open'|'close') of the pinned (sym, date, time_et) 5-min bar, or None.
    time_et is pinned exactly ('09:30' / '15:55') — never a MIN/MAX 'first/last bar' (which would
    pull an extended-hours print). Falls back to Alpaca SIP when the local bar is absent so the
    grader self-heals instead of silently skipping the pick."""
    assert field in ("open", "close")
    c = _price_conn(db)
    try:
        r = c.execute(
            f"SELECT {field} FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et=?",
            (sym.upper(), date, time_et),
        ).fetchone()
    finally:
        c.close()
    val = None if r is None or r[0] is None else float(r[0])
    if val is None:                                   # local miss -> SIP fallback (self-heal)
        b = _sip_session(sym, date).get(time_et)
        if b is not None:
            val = b[0] if field == "open" else b[1]
    return val


def entry_open(sym, date, db=PRICE_DB):
    """RTH 09:30 open (paper entry)."""
    return _bar_field(sym, date, "09:30", "open", db)


def exit_close(sym, date, db=PRICE_DB):
    """RTH 15:55 close (hold-to-EOD exit)."""
    return _bar_field(sym, date, "15:55", "close", db)


def _spy_pct(date, db=PRICE_DB):
    """SPY same-day open(09:30) -> close(15:55) %, for vs_spy. None if either bar is missing."""
    o = entry_open("SPY", date, db)
    cl = exit_close("SPY", date, db)
    if o is None or cl is None or o == 0:
        return None
    return (cl / o - 1.0) * 100.0


# ------------------------------------------------------------------------------- paper actions
def paper_buy(date, sym, mode="live", *, coil_reason=None, catalyst_reason=None,
              db=journal.DB, price_db=PRICE_DB):
    """Resolve the 09:30 open and log a paper pick. NEVER sends a live order. Returns a dict
    describing the action. Skips (and says why) if there is no open bar or the price cap is hit;
    a skipped name is NOT written to the journal (nothing to hold)."""
    sym = sym.upper()
    px = entry_open(sym, date, price_db)
    if px is None:
        return {"sym": sym, "action": "SKIP", "reason": "no 09:30 open bar", "mode": mode}
    if px >= PRICE_CAP:
        return {"sym": sym, "action": "SKIP",
                "reason": f"price cap: 09:30 open ${px:.2f} >= ${PRICE_CAP:.0f}",
                "entry_px": round(px, 4), "mode": mode}
    journal.log_pick(date, sym, coil_reason=coil_reason, catalyst_reason=catalyst_reason,
                     entry_px=round(px, 4), open_et="09:30", mode=mode, db=db)
    return {
        "sym": sym, "action": "PAPER_BUY", "entry_px": round(px, 4), "open_et": "09:30",
        "size": "fixed/equal (account rail: 1% risk, <=3 positions)", "exit_plan": "hold_eod",
        "mode": mode, "note": "PAPER ONLY — no live order sent; user fills manually",
    }


def realize(date, sym, mode="live", db=journal.DB, price_db=PRICE_DB):
    """Fill an already-logged pick's outcome: 15:55 close -> result% + vs_spy, then
    journal.fill_outcome. Returns a dict (or {'action':'SKIP',...} if the pick/bars are missing).
    Judgment is left for the learn brain; this stamps only the mechanical numbers (judgment=None
    preserves any grade the brain later writes via fill_outcome)."""
    sym = sym.upper()
    rr = [r for r in journal.rows(date, mode, db=db) if r["sym"] == sym]
    if not rr:
        return {"sym": sym, "action": "SKIP", "reason": "no logged pick to realize", "mode": mode}
    entry_px = rr[0]["entry_px"]
    if entry_px in (None, 0):
        return {"sym": sym, "action": "SKIP", "reason": "pick has no entry_px", "mode": mode}
    close_px = exit_close(sym, date, price_db)
    if close_px is None:
        return {"sym": sym, "action": "SKIP", "reason": "no 15:55 close bar", "mode": mode}
    result_pct = (close_px / entry_px - 1.0) * 100.0
    spy_pct = _spy_pct(date, price_db)
    vs_spy = None if spy_pct is None else result_pct - spy_pct
    judgment = rr[0].get("judgment")   # keep any grade already written; mechanical fill only
    journal.fill_outcome(date, sym, round(close_px, 4), result_pct, vs_spy, judgment,
                         mode=mode, db=db)
    return {
        "sym": sym, "action": "REALIZE", "entry_px": entry_px, "close_px": round(close_px, 4),
        "result_pct": round(result_pct, 3),
        "vs_spy": None if vs_spy is None else round(vs_spy, 3),
        "spy_pct": None if spy_pct is None else round(spy_pct, 3), "mode": mode,
    }


def _load_plan(date, plans_dir=PLANS_DIR):
    path = f"{plans_dir}/{date}.plan.json"
    if not os.path.exists(path):
        return None, path
    with open(path) as f:
        return json.load(f), path


def process_plan(date, mode="live", db=journal.DB, price_db=PRICE_DB, plans_dir=PLANS_DIR):
    """Mechanical half of learn.sh: read plans/<DATE>.plan.json, paper_buy up to MAX_PICKS picks
    (price-cap-gated), then realize each. Returns a summary dict. Abstain plans (no picks) are a
    valid recorded decision — nothing to buy, empty summary."""
    plan, path = _load_plan(date, plans_dir)
    if plan is None:
        return {"date": date, "mode": mode, "error": f"no plan file at {path}",
                "bought": [], "realized": []}
    picks = plan.get("picks") or []
    bought, realized, skipped = [], [], []
    for p in picks[:MAX_PICKS]:
        sym = (p.get("sym") or "").upper()
        if not sym:
            continue
        b = paper_buy(date, sym, mode, coil_reason=p.get("coil_reason"),
                      catalyst_reason=p.get("catalyst_reason"), db=db, price_db=price_db)
        if b["action"] == "PAPER_BUY":
            bought.append(b)
            realized.append(realize(date, sym, mode, db=db, price_db=price_db))
        else:
            skipped.append(b)
    if len(picks) > MAX_PICKS:
        skipped.append({"action": "SKIP", "reason": f"plan had {len(picks)} picks; capped at "
                        f"{MAX_PICKS}", "dropped": [p.get("sym") for p in picks[MAX_PICKS:]]})
    return {"date": date, "mode": mode, "n_picks": len(picks),
            "bought": bought, "realized": realized, "skipped": skipped}


# ------------------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="resonance paper execution (never a live order)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan"); pl.add_argument("date"); pl.add_argument("mode", nargs="?", default="live")
    rz = sub.add_parser("realize"); rz.add_argument("date"); rz.add_argument("sym")
    rz.add_argument("mode", nargs="?", default="live")
    a = ap.parse_args()
    if a.cmd == "plan":
        res = process_plan(a.date, a.mode)
        print(json.dumps(res, indent=1, default=str))
        if res.get("error"):
            sys.exit(1)
    elif a.cmd == "realize":
        print(json.dumps(realize(a.date, a.sym, a.mode), indent=1, default=str))


if __name__ == "__main__":
    main()
