"""Broad morning-movers universe — the FIELD the AI sees (replaces the pre-filtered dump).

v1's mistake was feeding the AI a pre-crushed H12-A gainer dump. v2 starts from the
market's real movers (up AND down / gappers) and applies ONLY a liquidity/quality floor
(a safety guardrail, not an alpha filter). The AI classifies + selects from this field.

Source: Alpaca movers screener (real-time), intersected with the curated liquid
`universe_stocks` (drops penny/warrant/junk). Enrich each with prev_close (for gap) so
the context layer can describe the situation.
"""
from __future__ import annotations
import sqlite3, requests
from dataclasses import dataclass

DB = "data/trade_history.db"
MOVERS_URL = "https://data.alpaca.markets/v1beta1/screener/stocks/movers"


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
    pct_change: float   # daily % (from prev close) per the screener
    price: float
    direction: str      # 'up' | 'down'
    prev_close: float | None = None


def _liquidity(p, sym):
    """(dollar_vol, prev_close) from recent daily OHLC; None if too little history."""
    r = [x for x in p.execute(
        "SELECT close, volume FROM stock_daily_ohlc WHERE symbol=? AND close IS NOT NULL "
        "ORDER BY date DESC LIMIT 20", (sym,)) if x[0] is not None]
    if len(r) < 10:
        return None, None
    import statistics
    return r[0][0] * statistics.mean([x[1] or 0 for x in r]), r[0][0]


def gather_universe(top=100, min_price=5.0, min_dollar_vol=20e6, db=DB) -> list[Mover]:
    """Broad field of liquid movers. Guardrail = price + $-volume floor (safety, not alpha).
    Curated `universe_stocks` membership is a bonus, not a hard gate."""
    hdr = _keys()
    p = sqlite3.connect(db)
    curated = {r[0] for r in p.execute("SELECT symbol FROM universe_stocks")}
    # Alpaca screener caps `top` at 50; a larger value 400s -> silent empty field.
    r = requests.get(MOVERS_URL, headers=hdr, params={"top": min(top, 50)}, timeout=15).json()
    out = []
    for direction, key in (("up", "gainers"), ("down", "losers")):
        for x in r.get(key, []):
            sym = x.get("symbol", "")
            price = x.get("price") or 0
            if price < min_price:
                continue
            dv, pc = _liquidity(p, sym)
            # keep if liquid enough OR in the curated universe (belt-and-suspenders)
            if (dv is None or dv < min_dollar_vol) and sym not in curated:
                continue
            out.append(Mover(sym=sym, pct_change=x.get("percent_change", 0.0), price=price,
                             direction=direction, prev_close=pc))
    return out


if __name__ == "__main__":
    for m in gather_universe():
        gap = f"{(m.price/m.prev_close-1)*100:+.1f}%" if m.prev_close else "?"
        print(f"  {m.sym:6} {m.direction:4} day{m.pct_change:+6.1f}% ${m.price:.2f} vs prevclose {gap}")
