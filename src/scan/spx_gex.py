"""spx_gex.py — latest SPX gamma exposure (SqueezeMetrics free CSV), market-fragility gate.

SPX GEX < 0 = options dealers are net SHORT gamma (past the gamma-flip at 0) -> they hedge by
buying into strength and selling into weakness = they AMPLIFY market moves -> fragile/reversal-prone
regime. Validated on 15 years (N=3808): prior-day GEX<0 -> next-day |move| 1.53% vs 0.64% for GEX>=0
(2.4x); 16 of the 20 most-volatile days were preceded by GEX<0. Orthogonal to spy_intra (39% of
GEX<0 days are SPY-green) -> it flags "green-but-fragile" reversal days the direction signals miss.

The most recent completed CSV row = the PRIOR trading day at a 09:37 scan (SqueezeMetrics computes
GEX from EOD option positioning, published after close), so it is lookahead-safe. We exclude any row
dated >= the scan date to guarantee that. Caches the CSV locally so a fetch failure degrades to the
last known value instead of failing the scan.

Source: https://squeezemetrics.com/monitor/static/DIX.csv (cols: date,price,dix,gex)
"""
from __future__ import annotations
import csv, io, urllib.request, datetime as dt
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
URL = "https://squeezemetrics.com/monitor/static/DIX.csv"
CACHE = ROOT / "data" / "spx_gex_cache.csv"


def latest_spx_gex(before_date: Optional[str] = None, timeout: int = 15) -> Tuple[Optional[str], Optional[float]]:
    """Return (date, gex) for the most recent completed day STRICTLY BEFORE `before_date`
    (default = today UTC). Fetches the SqueezeMetrics CSV, refreshes the local cache, and falls
    back to the cache on failure. Returns (None, None) if nothing usable."""
    text = None
    try:
        with urllib.request.urlopen(URL, timeout=timeout) as r:
            text = r.read().decode()
        try:
            CACHE.write_text(text)
        except Exception:
            pass
    except Exception:
        if CACHE.exists():
            try:
                text = CACHE.read_text()
            except Exception:
                text = None
    if not text:
        return None, None
    cutoff = before_date or dt.date.today().isoformat()
    last = (None, None)
    for row in csv.DictReader(io.StringIO(text)):
        d = row.get("date")
        if not d or d >= cutoff:          # strictly prior day -> lookahead-safe
            continue
        try:
            last = (d, float(row["gex"]))
        except (KeyError, ValueError):
            continue
    return last


if __name__ == "__main__":
    import sys
    bd = sys.argv[1] if len(sys.argv) > 1 else None
    d, g = latest_spx_gex(bd)
    if g is None:
        print("SPX GEX: unavailable")
    else:
        print(f"SPX GEX {d}: {g:,.0f} ({g/1e9:+.2f}B) -> {'NEG (fragile, abstain)' if g < 0 else 'POS (ok)'}")
