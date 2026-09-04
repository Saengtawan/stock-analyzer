"""entry_fill_watch.py — after a riser pick, watch ~3 min whether the limit-dip would fill.

The riser suggests a buy LIMIT at display-X% (riser dips ~91% in 1-5 min). The system can't
see your Alpaca order, but it CAN see the price: if the stock trades down to the limit -> your
limit likely FILLED (you're in at a better price). If it never dips in ~3 min -> it's a runner
(no fill) -> CHASE at market NOW (don't switch picks — a non-dipping top-1 is the strongest
momentum). This is the "who tells me to chase" piece.

Usage (launched by riser_capture in background):
  entry_fill_watch.py SYM LIMIT_PRICE DISPLAY_PRICE [DATE]
Logs to data/exit_loops/SYM_DATE_entry.log (riser_watch.sh tails it).
"""
import os, sys, time, requests
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
for ln in (ROOT / ".env").read_text().splitlines():
    ln = ln.strip()
    if ln and not ln.startswith("#") and "=" in ln:
        k, v = ln.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
HDR = {"APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"), "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET_KEY")}
ET = ZoneInfo("America/New_York")

sym = sys.argv[1]
limit = float(sys.argv[2])
disp = float(sys.argv[3])
date = sys.argv[4] if len(sys.argv) > 4 else datetime.now(ET).strftime("%Y-%m-%d")

WATCH_SECS = int(os.environ.get("RISER_FILL_WATCH_SECS", "180"))   # ~3 min
POLL = int(os.environ.get("RISER_FILL_POLL", "25"))


def lows_since_display():
    """Lowest IEX 1-min low + last close from display (em 576) onward today."""
    try:
        r = requests.get(f"https://data.alpaca.markets/v2/stocks/{sym}/bars", headers=HDR,
                         params={"timeframe": "1Min", "start": f"{date}T13:36:00Z", "feed": "iex", "limit": 60}, timeout=15)
        bars = r.json().get("bars", [])
        if not bars:
            return None, None
        return min(b["l"] for b in bars), bars[-1]["c"]
    except Exception:
        return None, None


def main():
    print(f"[entry-fill] watching {sym}: LIMIT ${limit:.2f} (display ${disp:.2f}) — up to {WATCH_SECS//60} min", flush=True)
    t0 = time.time()
    while time.time() - t0 < WATCH_SECS:
        lo, cur = lows_since_display()
        et = datetime.now(ET).strftime("%H:%M")
        if lo is not None:
            if lo <= limit:
                print(f"[entry-fill] {et} ✅ LIMIT FILLED — {sym} dipped to ${lo:.2f} <= ${limit:.2f}. You're IN at the dip.", flush=True)
                return
            print(f"[entry-fill] {et} waiting — low so far ${lo:.2f} (need <= ${limit:.2f}), cur ${cur:.2f}", flush=True)
        time.sleep(POLL)
    lo, cur = lows_since_display()
    cur = cur or disp
    print(f"[entry-fill] {datetime.now(ET):%H:%M} ⚠️ NOT FILLED in {WATCH_SECS//60}min — {sym} is a RUNNER "
          f"(low ${lo:.2f} > limit ${limit:.2f}).", flush=True)
    print(f"[entry-fill]    >>> CHASE {sym} @ MARKET NOW (~${cur:.2f}) — do NOT switch picks <<<", flush=True)
    if os.environ.get("QUIET", "0") != "1":
        print("\a", flush=True)


if __name__ == "__main__":
    main()
