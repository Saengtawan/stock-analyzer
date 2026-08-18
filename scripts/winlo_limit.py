#!/usr/bin/env python3
"""winlo_limit.py SYM [MULT] — LIVE dynamic-limit for a resonance pick (user's entry rule).

  winLo  = lowest low in the 09:05-09:25 ET premarket window
  limit  = winLo * MULT   (MULT default 1.015)

Run at ~09:25-09:27 ET, before the 09:30 open, to set the resting limit.

DATA SOURCE = yfinance premarket 1-min (prepost=True). This is the FIX for the live train/serve gap:
Alpaca free-tier SIP historical BLOCKS the most recent ~16 min ("subscription does not permit
querying recent SIP data"), so at 09:25 it cannot return the 09:09-09:25 bars; and Alpaca IEX has
essentially NO premarket prints for these names (only a junk-wide quote). yfinance prepost 1-min is
free and near-real-time (latest bar ~current minute), so it serves the exact window live.

Backtest of the rule used HISTORICAL SIP (no delay) — that is why it looked fine offline but failed
live. yfinance premarket restores parity. Cross-check note: yfinance premarket lows are usually
within a cent or two of SIP; confirm against the broker platform for a thin name if it matters.

Usage:
  python3 scripts/winlo_limit.py LUNR
  python3 scripts/winlo_limit.py LUNR 1.02          # different multiplier
  python3 scripts/winlo_limit.py LUNR 1.015 09:05 09:25
"""
import sys
import yfinance as yf

ET = "America/New_York"


def winlo_limit(sym, mult=1.015, start="09:05", end="09:25"):
    df = yf.download(sym, period="1d", interval="1m", prepost=True,
                     progress=False, auto_adjust=False)
    if df is None or df.empty:
        return None
    idx = df.index.tz_convert(ET) if df.index.tz is not None else df.index.tz_localize(ET)
    df.index = idx
    win = df.between_time(start, end)
    if win.empty:
        return None
    low_col = ("Low", sym) if ("Low", sym) in win.columns else "Low"
    winlo = float(win[low_col].min())
    return {"sym": sym, "winlo": round(winlo, 2), "limit": round(winlo * mult, 2),
            "mult": mult, "n_bars": int(len(win)), "latest": df.index[-1].strftime("%H:%M")}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 scripts/winlo_limit.py SYM [MULT] [START] [END]")
        sys.exit(1)
    sym = sys.argv[1].upper()
    mult = float(sys.argv[2]) if len(sys.argv) > 2 else 1.015
    start = sys.argv[3] if len(sys.argv) > 3 else "09:05"
    end = sys.argv[4] if len(sys.argv) > 4 else "09:25"
    r = winlo_limit(sym, mult, start, end)
    if not r:
        print(f"{sym}: no premarket {start}-{end} data yet — retry in 1-2 min, "
              f"or read the window low off the broker platform and x{mult}.")
    else:
        print(f"{sym}  winLo({start}-{end}) = {r['winlo']}  ->  LIMIT x{r['mult']} = {r['limit']}"
              f"   ({r['n_bars']} bars, latest {r['latest']} ET)")
