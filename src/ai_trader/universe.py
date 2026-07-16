"""Broad LIVE universe — the real field the AI sees, computed from 1-min bars.

Lesson from the IBM day: the Alpaca movers screener (top-% gainers/losers) is penny-heavy
and, once the quality floor is applied, collapses to 1-2 names — so the live path saw only
IBM while the reconstructed field had 530 movers (and the real reversal, NOW). So the live
field is now built the SAME way as the sim: fetch 1-min bars over the curated liquid
universe and compute each name's gain-from-open + gap. Live uses feed=iex (SIP blocks
recent <15min data); replay (universe_sim) uses feed=sip. Guardrail = price floor only.
"""
from __future__ import annotations
import sqlite3, requests, datetime, zoneinfo, statistics
from dataclasses import dataclass

DB = "data/trade_history.db"
ET = zoneinfo.ZoneInfo("America/New_York")
UTC = zoneinfo.ZoneInfo("UTC")
MOVERS_URL = "https://data.alpaca.markets/v1beta1/screener/stocks/movers"  # legacy fallback


def _keys():
    kk = {}
    for l in open(".env"):
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1); kk[k.strip()] = v.strip().strip("\"'")
    return {"APCA-API-KEY-ID": kk.get("ALPACA_API_KEY"),
            "APCA-API-SECRET-KEY": kk.get("ALPACA_SECRET_KEY")}


@dataclass
class Mover:
    sym: str
    pct_change: float   # % from the 09:30 open at the observation minute (the "now" level)
    price: float
    direction: str      # 'up' | 'down'
    prev_close: float | None = None
    peak_pct: float = 0.0    # highest % above the open so far (session-to-now)
    trough_pct: float = 0.0  # lowest % below the open so far

    @property
    def off_peak(self):     # how far below the peak it now sits (spent-move tell)
        return self.pct_change - self.peak_pct
    @property
    def off_trough(self):   # how far it has reclaimed off the low (reversal tell)
        return self.pct_change - self.trough_pct


def _liquidity(p, sym):
    r = [x for x in p.execute(
        "SELECT close, volume FROM stock_daily_ohlc WHERE symbol=? AND close IS NOT NULL "
        "ORDER BY date DESC LIMIT 20", (sym,)) if x[0] is not None]
    if len(r) < 10:
        return None, None
    return r[0][0] * statistics.mean([x[1] or 0 for x in r]), r[0][0]


def _bars_batch(syms, start_iso, end_iso, hdr, feed):
    """1-min bars for a batch of symbols over [start,end], paginated."""
    out, tok = {}, None
    for _ in range(12):
        params = {"symbols": ",".join(syms), "timeframe": "1Min",
                  "start": start_iso, "end": end_iso, "feed": feed, "limit": 10000}
        if tok:
            params["page_token"] = tok
        r = requests.get("https://data.alpaca.markets/v2/stocks/bars", headers=hdr,
                         params=params, timeout=30).json()
        for s, bl in r.get("bars", {}).items():
            out.setdefault(s, []).extend(bl)
        tok = r.get("next_page_token")
        if not tok:
            break
    return out


def _field_from_bars(date, start_iso, end_iso, feed, min_gain, min_price, db):
    """Shared field builder: gain-from-open + gap for every liquid name that moved."""
    p = sqlite3.connect(db)
    syms = [r[0] for r in p.execute("SELECT symbol FROM universe_stocks")]
    prev = {s: c for s, c in p.execute(
        "SELECT symbol, close FROM stock_daily_ohlc WHERE date=("
        "SELECT MAX(date) FROM stock_daily_ohlc WHERE date<?) AND close IS NOT NULL", (date,))}
    hdr = _keys()
    out = []
    for i in range(0, len(syms), 200):
        batch = syms[i:i+200]
        bars = _bars_batch(batch, start_iso, end_iso, hdr, feed)
        for s in batch:
            bl = bars.get(s, [])
            if not bl:
                continue
            o930, last = bl[0]["o"], bl[-1]["c"]
            if o930 <= 0 or last < min_price:
                continue
            gain = (last / o930 - 1) * 100
            peak = (max(b["h"] for b in bl) / o930 - 1) * 100
            trough = (min(b["l"] for b in bl) / o930 - 1) * 100
            pc = prev.get(s)
            gap = (o930 / pc - 1) * 100 if pc else 0.0
            if abs(gain) < min_gain and abs(gap) < min_gain:
                continue
            out.append(Mover(sym=s, pct_change=round(gain, 2), price=round(last, 2),
                             direction=("up" if gain >= 0 else "down"), prev_close=pc,
                             peak_pct=round(peak, 2), trough_pct=round(trough, 2)))
    return out


def gather_universe(min_gain=1.0, min_price=5.0, db=DB, top=None) -> list[Mover]:
    """LIVE broad field: IEX 1-min bars over the curated universe, 09:30 -> now.
    `top` is accepted for backward-compat and ignored."""
    now = datetime.datetime.now(UTC)
    today = datetime.datetime.now(ET).strftime("%Y-%m-%d")
    u0 = datetime.datetime.now(ET).replace(hour=9, minute=30, second=0, microsecond=0).astimezone(UTC)
    return _field_from_bars(today, u0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            now.strftime("%Y-%m-%dT%H:%M:%SZ"), "iex", min_gain, min_price, db)


if __name__ == "__main__":
    ms = gather_universe()
    print(f"live field: {len(ms)} movers")
    for m in sorted(ms, key=lambda m: m.pct_change)[:40]:
        gap = f"{(m.price/m.prev_close-1)*100:+.1f}%" if m.prev_close else "?"
        print(f"  {m.sym:6} {m.direction:4} from-open{m.pct_change:+6.1f}% ${m.price:.2f} gap{gap}")
