"""v2 outcome — realize each pick using ITS AI-assigned exit (hold_eod / trail + hard_stop).

Fetches 1-min bars (Alpaca SIP, any date >15min old), enters ~09:37, applies the pick's
own exit, nets a round-trip cost. Closes the forward-tracking loop for the v2 journal.
"""
from __future__ import annotations
import argparse, sqlite3, zoneinfo, datetime, requests
from . import journal

UTC = zoneinfo.ZoneInfo("UTC"); ET = zoneinfo.ZoneInfo("America/New_York")
COST = 0.30


def _keys():
    kk = {}
    for l in open(".env"):
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1); kk[k.strip()] = v.strip().strip("\"'")
    return {"APCA-API-KEY-ID": kk.get("ALPACA_API_KEY"),
            "APCA-API-SECRET-KEY": kk.get("ALPACA_SECRET_KEY")}


def _bars(sym, date):
    hdr = _keys()
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


def realize(sym, date, hard_stop, exit_style, trail_pct):
    seq = _bars(sym, date)
    entry = next((b for m, b in seq if m >= 577), None)
    if not entry or entry["o"] <= 0:
        return None
    e = entry["o"]; peak = 0.0; start = next(m for m, b in seq if m >= 577)
    for m, b in seq:
        if m < 577:
            continue
        cur = (b["c"] / e - 1) * 100
        hi = (b["h"] / e - 1) * 100
        peak = max(peak, hi)
        held = m - start
        if held >= 15 and (b["l"] / e - 1) * 100 <= hard_stop:   # hard stop (intrabar low)
            return hard_stop - COST
        if exit_style == "trail" and trail_pct and peak >= trail_pct and (peak - cur) >= trail_pct:
            return cur - COST
    return (seq[-1][1]["c"] / e - 1) * 100 - COST   # hold to EOD


def fill(date=None, db=journal.DB):
    c = sqlite3.connect(db); c.execute(journal.DDL_V2)
    q = ("SELECT date,sym,hard_stop,exit_style,trail_pct FROM ai_journal_v2 "
         "WHERE status='picked' AND outcome_pct IS NULL")
    rows = list(c.execute(q + (" AND date=?" if date else ""), (date,) if date else ()))
    c.close()
    if not rows:
        print("no open v2 picks to update"); return
    for d, sym, hs, style, tp in rows:
        r = realize(sym, d, hs if hs is not None else -4.0, style or "hold_eod", tp)
        if r is None:
            print(f"{d} {sym}: no bars"); continue
        journal.update_outcome_v2(d, sym, r)
        print(f"{d} {sym}: {r:+.2f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    fill(ap.parse_args().date)
