"""Fill realized outcomes for picked days — closes the forward-tracking loop.

For each journal row with status='picked' and no outcome, fetch the pick's 1-min
bars (Alpaca SIP; works for any date >15min old) and apply the classify's own exit
(hold-EOD + hard stop) from the ~09:37 entry. Net of a round-trip cost.
"""
from __future__ import annotations
import argparse, sqlite3, zoneinfo, datetime, requests
from .classifies.gap_down_reversal import GapDownReversal
from .classifies.base import PositionState
from . import journal

UTC = zoneinfo.ZoneInfo("UTC"); ET = zoneinfo.ZoneInfo("America/New_York")
COST = 0.30
_GDR = GapDownReversal()


def _keys(db="data/trade_history.db"):
    kk = {}
    for l in open(".env"):
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1); kk[k.strip()] = v.strip().strip("\"'")
    return {"APCA-API-KEY-ID": kk.get("ALPACA_API_KEY"),
            "APCA-API-SECRET-KEY": kk.get("ALPACA_SECRET_KEY")}


def _bars(sym, date, hdr):
    u0 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=9, minute=30, tzinfo=ET).astimezone(UTC)
    u1 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=16, minute=0, tzinfo=ET).astimezone(UTC)
    r = requests.get("https://data.alpaca.markets/v2/stocks/bars", headers=hdr, params={
        "symbols": sym, "timeframe": "1Min", "start": u0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": u1.strftime("%Y-%m-%dT%H:%M:%SZ"), "feed": "sip", "limit": 10000}, timeout=30).json()
    out = []
    for b in r.get("bars", {}).get(sym, []):
        dt = datetime.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        out.append((dt.hour * 60 + dt.minute, b))
    return sorted(x for x in out if 570 <= x[0] <= 955)


def realized(sym, date, hdr):
    seq = _bars(sym, date, hdr)
    entry = next((b for m, b in seq if m >= 577), None)
    if not entry or entry["o"] <= 0:
        return None
    e = entry["o"]; peak = 0.0
    start = next(m for m, b in seq if m >= 577)
    for m, b in seq:
        if m < 577:
            continue
        cur = (b["c"] / e - 1) * 100
        peak = max(peak, (b["h"] / e - 1) * 100)
        if _GDR.exit(PositionState(minutes_held=m - start, cur_pnl=cur, peak_pnl=peak)) == "EXIT":
            return cur - COST
    return (seq[-1][1]["c"] / e - 1) * 100 - COST


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="only this date; default = all open picks")
    a = ap.parse_args()
    hdr = _keys()
    c = sqlite3.connect(journal.DB)
    q = "SELECT date,pick_sym FROM ai_journal WHERE status='picked' AND outcome_pct IS NULL"
    rows = list(c.execute(q + (" AND date=?" if a.date else ""), (a.date,) if a.date else ()))
    c.close()
    if not rows:
        print("no open picks to update"); return
    for date, sym in rows:
        r = realized(sym, date, hdr)
        if r is None:
            print(f"{date} {sym}: no bars"); continue
        journal.update_outcome(date, r)
        print(f"{date} {sym}: outcome {r:+.2f}%")


if __name__ == "__main__":
    main()
