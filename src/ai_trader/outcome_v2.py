"""v2 outcome — realize each pick using ITS AI-assigned exit (hold_eod / trail + hard_stop).

Fetches 1-min bars (Alpaca SIP, any date >15min old), enters ~09:37, applies the pick's
own exit, nets a round-trip cost. Closes the forward-tracking loop for the v2 journal.
"""
from __future__ import annotations
import argparse, sqlite3, zoneinfo, datetime, requests, json, os
from . import journal

UTC = zoneinfo.ZoneInfo("UTC"); ET = zoneinfo.ZoneInfo("America/New_York")
COST = 0.30
FIELD_DIR = "plans/field"


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


def realize(sym, date, hard_stop, exit_style, trail_pct, entry_price=None):
    """Realize the pick's outcome. Entry = the LOGGED `entry_price` (the price the human was
    actually told to buy at) when available — NOT the SIP 09:37 bar open — so the outcome is
    measured off the same price/feed as the recommendation (removes the IEX-vs-SIP entry skew).
    Bars are still walked for the stop/trail/EOD path."""
    seq = _bars(sym, date)
    start = next((m for m, b in seq if m >= 577), None)
    if start is None:
        return None
    if entry_price and entry_price > 0:
        e = entry_price          # measure from the recommended/actual fill price
    else:
        entry = next((b for m, b in seq if m >= 577), None)
        if not entry or entry["o"] <= 0:
            return None
        e = entry["o"]           # legacy fallback (no logged price)
    # hold_eod = pure hold to the close, NO stop and NO trail (ride the whole day)
    if exit_style != "trail":
        return (seq[-1][1]["c"] / e - 1) * 100 - COST
    peak = 0.0
    for m, b in seq:
        if m < 577:
            continue
        cur = (b["c"] / e - 1) * 100
        hi = (b["h"] / e - 1) * 100
        peak = max(peak, hi)
        held = m - start
        if hard_stop is not None and held >= 15 and (b["l"] / e - 1) * 100 <= hard_stop:
            return hard_stop - COST
        if trail_pct and peak >= trail_pct and (peak - cur) >= trail_pct:
            return cur - COST
    return (seq[-1][1]["c"] / e - 1) * 100 - COST   # hold to EOD


def realize_baselines(date, db=journal.DB):
    """Control arm: realize (a) SPY hold-EOD and (b) a mechanical field pick — the deepest
    gap-down already reclaiming off its low — so we can ask 'did the AI beat a dumb rule?'."""
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    spy = realize("SPY", date, -100.0, "hold_eod", None)   # no stop = pure buy-and-hold market
    if spy is not None:
        journal.log_baseline(date, "spy", "SPY", spy, ts, db=db)
        print(f"  baseline spy: SPY {spy:+.2f}%")
    # mechanical field_reclaim from the persisted field snapshot (if any)
    fp = os.path.join(FIELD_DIR, f"{date}.json")
    if os.path.exists(fp):
        field = json.load(open(fp))
        cand = [m for m in field if (m.get("gap") or 0) <= -1.5 and (m.get("off_trough") or 0) >= 2.0]
        cand.sort(key=lambda m: m.get("gap") or 0)   # deepest gap first
        if cand:
            sym = cand[0]["sym"]
            r = realize(sym, date, -4.0, "hold_eod", None)
            if r is not None:
                journal.log_baseline(date, "field_reclaim", sym, r, ts, db=db)
                print(f"  baseline field_reclaim: {sym} {r:+.2f}%")


def fill(date=None, db=journal.DB):
    c = sqlite3.connect(db); journal._migrate_v2(c)
    # fill BOTH primary picks and bench — bench outcomes are free calibration of the AI's ranking
    q = ("SELECT date,sym,hard_stop,exit_style,trail_pct,entry_price FROM ai_journal_v2 "
         "WHERE status IN ('picked','bench') AND outcome_pct IS NULL AND sym<>''")
    rows = list(c.execute(q + (" AND date=?" if date else ""), (date,) if date else ()))
    dates = sorted({d for d, *_ in rows} | ({date} if date else set()))
    c.close()
    for d, sym, hs, style, tp, ep in rows:
        r = realize(sym, d, hs if hs is not None else -4.0, style or "hold_eod", tp, entry_price=ep)
        if r is None:
            print(f"{d} {sym}: no bars"); continue
        journal.update_outcome_v2(d, sym, r)
        print(f"{d} {sym}: {r:+.2f}%")
    if not rows:
        print("no open v2 picks to update")
    for d in dates:      # always realize the control arm for each touched date
        realize_baselines(d, db=db)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    fill(ap.parse_args().date)
