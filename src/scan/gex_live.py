"""gex_live.py — scan-time GEX from cached chain (no API), fast enough for the 09:37 pick.

The slow part of GEX (pulling the full option chain + OI + quotes) is done by the daily
gex_snapshot run and stored in data/gex_snapshots.db (table gex_chain: strike, expiry, type,
oi, iv per contract). OI is prior-day data — it does NOT change intraday — so yesterday's cached
chain is the correct GEX OI for today. gex_live() loads the most recent cached chain for a symbol
and RECOMPUTES gamma with the live spot + today's time-to-expiry (pure math, no API) -> <100ms.

Returns naive GEX (call_gex - put_gex). Sign convention UNVALIDATED (see memory) — today's
cross-section had POS-GEX +1.94% vs NEG-GEX -0.30%, so POS = supportive / NEG = fade-risk, but
N=1 day. Returns None if the symbol has no cached chain (caller should treat as "no signal").
"""
from __future__ import annotations
import os, sqlite3, datetime as _dt
from math import erf, exp, log, sqrt, pi
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "gex_snapshots.db"
RFR = 0.04


def _gamma(S, K, T, sig):
    if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (log(S / K) + (RFR + 0.5 * sig * sig) * T) / (sig * sqrt(T))
    return exp(-0.5 * d1 * d1) / sqrt(2 * pi) / (S * sig * sqrt(T))


def gex_live(symbol: str, spot: float, date: str, db_path: Optional[str] = None) -> Optional[float]:
    """Naive GEX (call-minus-put) for `symbol` at `spot` on `date`, from the latest cached chain
    on or before `date`. None if no cache / no usable contracts."""
    if not spot or spot <= 0:
        return None
    try:
        con = sqlite3.connect(db_path or DB)
        sd = con.execute("SELECT MAX(snap_date) FROM gex_chain WHERE underlying=? AND snap_date<=?",
                         (symbol, date)).fetchone()
        if not sd or not sd[0]:
            con.close(); return None
        rows = con.execute("SELECT strike, expiry, type, oi, iv FROM gex_chain "
                           "WHERE underlying=? AND snap_date=?", (symbol, sd[0])).fetchall()
        con.close()
    except sqlite3.OperationalError:
        return None
    today = _dt.date.fromisoformat(date)
    call_gex = put_gex = 0.0
    used = 0
    for strike, expiry, typ, oi, iv in rows:
        if not oi or oi <= 0 or not iv or iv <= 0:
            continue
        T = (_dt.date.fromisoformat(expiry) - today).days / 365
        if T <= 0:
            continue
        g = _gamma(spot, float(strike), T, float(iv))
        leg = g * oi * 100 * spot * spot * 0.01
        if (typ or "").lower().startswith("c") or typ == "C":
            call_gex += leg
        else:
            put_gex += leg
        used += 1
    if used == 0:
        return None
    return call_gex - put_gex


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    spot = float(sys.argv[2]) if len(sys.argv) > 2 else 295.0
    date = sys.argv[3] if len(sys.argv) > 3 else _dt.date.today().isoformat()
    g = gex_live(sym, spot, date)
    print(f"{sym} @ {spot} ({date}): GEX {g:,.0f} ({'POS' if (g or 0) > 0 else 'NEG'})" if g is not None
          else f"{sym}: no cached chain")
