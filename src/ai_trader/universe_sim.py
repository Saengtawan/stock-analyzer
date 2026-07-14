"""Simulated point-in-time universe — reconstruct the FIELD as it was at HH:MM ET.

Live `universe.py` reflects "now" (e.g. full-day movers at midday). To see what the AI
would have judged AT 09:36, we rebuild the field from 1-min bars: for every liquid name,
its gain-from-open and gap-vs-prev-close at that minute. Broad (up AND down movers),
not just the screener's top-% names. For demo/replay; the live path uses universe.py.
"""
from __future__ import annotations
import sqlite3, zoneinfo, datetime, requests
from .universe import Mover, _keys

DB = "data/trade_history.db"
UTC = zoneinfo.ZoneInfo("UTC"); ET = zoneinfo.ZoneInfo("America/New_York")


def _bars_batch(syms, date, hdr):
    """1-min bars 09:30-09:40 ET for a batch of symbols (SIP; date must be >15min old)."""
    u0 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=9, minute=30, tzinfo=ET).astimezone(UTC)
    u1 = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=9, minute=40, tzinfo=ET).astimezone(UTC)
    out, tok = {}, None
    for _ in range(10):
        params = {"symbols": ",".join(syms), "timeframe": "1Min",
                  "start": u0.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": u1.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "feed": "sip", "limit": 10000}
        if tok:
            params["page_token"] = tok
        r = requests.get("https://data.alpaca.markets/v2/stocks/bars", headers=hdr, params=params, timeout=30).json()
        for s, bl in r.get("bars", {}).items():
            out.setdefault(s, []).extend(bl)
        tok = r.get("next_page_token")
        if not tok:
            break
    return out


def gather_universe_sim(date, minute=576, min_gain=1.0, min_price=5.0, db=DB) -> list[Mover]:
    """Field at `minute` (min-from-midnight; 576=09:36). Keep names that moved >=min_gain%
    from the 09:30 open OR gapped >=min_gain% vs prev close. Liquid (in universe_stocks)."""
    hdr = _keys()
    p = sqlite3.connect(db)
    syms = [r[0] for r in p.execute("SELECT symbol FROM universe_stocks")]
    prev = {s: c for s, c in p.execute(
        "SELECT symbol, close FROM stock_daily_ohlc WHERE date=("
        "SELECT MAX(date) FROM stock_daily_ohlc WHERE date<?) AND close IS NOT NULL", (date,))}
    out = []
    tmin = minute - 570  # bars index from 09:30
    for i in range(0, len(syms), 200):
        batch = syms[i:i+200]
        bars = _bars_batch(batch, date, hdr)
        for s in batch:
            bl = bars.get(s, [])
            if not bl:
                continue
            o930 = bl[0]["o"]
            # bar at/just before target minute
            atbar = None
            for b in bl:
                dt = datetime.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
                if dt.hour * 60 + dt.minute <= minute:
                    atbar = b
                else:
                    break
            if not atbar or o930 <= 0 or atbar["c"] < min_price:
                continue
            gain = (atbar["c"] / o930 - 1) * 100
            pc = prev.get(s)
            gap = (o930 / pc - 1) * 100 if pc else 0.0
            if abs(gain) < min_gain and abs(gap) < min_gain:
                continue
            out.append(Mover(sym=s, pct_change=round(gain, 2), price=round(atbar["c"], 2),
                             direction=("up" if gain >= 0 else "down"), prev_close=pc))
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--date", required=True)
    ap.add_argument("--minute", type=int, default=576)
    a = ap.parse_args()
    ms = gather_universe_sim(a.date, a.minute)
    print(f"field at minute {a.minute}: {len(ms)} movers")
    for m in sorted(ms, key=lambda m: m.pct_change):
        gap = f"{(m.price/m.prev_close-1)*100:+.1f}%" if m.prev_close else "?"
        print(f"  {m.sym:6} {m.direction:4} from-open{m.pct_change:+6.1f}% ${m.price:.2f} gap{gap}")
