"""rotation/data/snapshot.py — MECHANICAL cross-asset snapshot (0 AI tokens).

Pulls the daily close for a broad cross-asset universe via yfinance, computes 1d/5d/20d returns +
relative volume, and stores them LONG-format into data/rotation.db (via lib.journal.log_snapshot).
This is the neutral plumbing: it records WHAT the tape did across assets, imposes NO interpretation.
The brain (decide.md) reads these rows and finds the linkages itself.

Run:  python -m rotation.data.snapshot [YYYY-MM-DD]   (default = today ET)
"""
from __future__ import annotations
import sys, datetime, warnings
import pandas as pd
import yfinance as yf
from rotation.lib.journal import log_snapshot

warnings.filterwarnings("ignore")

# LONG format in the DB → adding an asset here is the ONLY change needed to track it.
UNIVERSE = {
    "index":     ["SPY", "QQQ", "IWM", "DIA"],
    "vol":       ["^VIX", "^VVIX"],
    "rate":      ["^TNX", "^FVX", "^IRX", "TLT", "IEF"],        # 10y/5y/13w yields + bond ETFs
    "fx":        ["DX-Y.NYB", "UUP"],                           # dollar
    "commodity": ["CL=F", "GC=F", "SI=F", "HG=F", "USO", "GLD"],# oil/gold/silver/copper
    "crypto":    ["BTC-USD", "ETH-USD", "SOL-USD"],
    "sector":    ["XLK", "XLE", "XLV", "XLF", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"],
    "theme":     ["SMH", "IGV", "XBI", "IBB", "ITA", "TAN", "ARKK", "IWO", "KRE", "XRT", "JETS"],
    # SMH=semis IGV=software XBI/IBB=biotech ITA=defense TAN=solar ARKK=innovation
    # IWO=smallgrowth KRE=regionalbanks XRT=retail JETS=airlines
}


def _metrics(df):
    """From a daily OHLC frame, return (close, ret_1d, ret_5d, ret_20d, rvol) for the last row."""
    if df is None or df.empty or len(df) < 2:
        return None
    c = df["Close"].dropna()
    if len(c) < 2:
        return None
    close = float(c.iloc[-1])
    def ret(n):
        return round((float(c.iloc[-1]) / float(c.iloc[-1 - n]) - 1) * 100, 2) if len(c) > n else None
    rvol = None
    if "Volume" in df and df["Volume"].notna().sum() > 21:
        v = df["Volume"].dropna()
        avg20 = float(v.iloc[-21:-1].mean())
        if avg20 > 0:
            rvol = round(float(v.iloc[-1]) / avg20, 2)
    return close, ret(1), ret(5), ret(20), rvol


def build(date=None):
    date = date or datetime.datetime.now().astimezone(datetime.timezone(-datetime.timedelta(hours=4))).strftime("%F")
    tickers = [t for lst in UNIVERSE.values() for t in lst]
    end = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
    start = (datetime.date.fromisoformat(date) - datetime.timedelta(days=45)).isoformat()
    ok = fail = 0
    for cls, lst in UNIVERSE.items():
        for t in lst:
            try:
                df = yf.download(t, start=start, end=end, interval="1d",
                                 progress=False, auto_adjust=False)
                if df is None or df.empty:
                    fail += 1; continue
                if hasattr(df.columns, "levels"):
                    df.columns = [x[0] for x in df.columns]
                # keep only rows up to `date`
                df = df[df.index <= pd.Timestamp(date)]
                m = _metrics(df)
                if m is None:
                    fail += 1; continue
                close, r1, r5, r20, rvol = m
                log_snapshot(date, t, cls, close, r1, r5, r20, rvol)
                ok += 1
            except Exception:
                fail += 1
    print(f"[rotation.snapshot] {date}: stored {ok} assets, {fail} failed")
    return ok


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
