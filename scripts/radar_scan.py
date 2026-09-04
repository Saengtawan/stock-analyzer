"""scripts/radar_scan.py — one radar pass (mechanical, NO AI, NO trading). Flags low-price names that are
IGNITING at a fresh clean HOD, with dedup + no-chase, and APPENDS each flag to data/radar_log/<DATE>.txt
for forward grading. Run on a loop 10:10-12:30 ET by scripts/radar_loop.sh (cron). The agent-judge of each
flag happens later in-session when a human/assistant reviews the log — this pass only DETECTS + LOGS.

Rule (validated 09-02): CONFIRMED igniter = fresh HOD (<=12m) + holding at high (vsHOD>-2) + no recent
slam + no blow-off all session. NO-CHASE = a name flagged today re-flags ONLY at the same price or cheaper,
never higher. Read-only yfinance; state + log live under data/radar_log/.
"""
from __future__ import annotations
import sys, os, json, warnings, zoneinfo, datetime, statistics as st
warnings.filterwarnings("ignore")
ET = zoneinfo.ZoneInfo("America/New_York")
import yfinance as yf
from yfinance import EquityQuery as Q

LOGDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "radar_log")
os.makedirs(LOGDIR, exist_ok=True)
DATE = datetime.datetime.now(ET).strftime("%F")
now = datetime.datetime.now(ET).strftime("%H:%M")
LOG = os.path.join(LOGDIR, f"{DATE}.txt")
PREV = os.path.join(LOGDIR, "_prev.txt")
FF = os.path.join(LOGDIR, "_firstflag.json")

try:
    q = Q("and", [Q("gt", ["percentchange", 10]), Q("gt", ["intradayprice", 1]),
                  Q("lt", ["intradayprice", 15]), Q("eq", ["region", "us"]),
                  Q("gt", ["dayvolume", 1_000_000])])
    board = yf.screen(q, sortField="percentchange", sortAsc=False, size=25).get("quotes", [])
except Exception as e:
    print(f"{now} ET  radar-error(board): {str(e)[:50]}"); sys.exit(0)

hits = []
for x in board:
    s = x.get("symbol"); chg = x.get("regularMarketChangePercent")
    if not s:
        continue
    # RE-VALIDATE THE GAIN. The screener selects on `percentchange > 10`, but its membership and the
    # quote it hands back can disagree — early in a session, and on leveraged/derivative tickers whose
    # Yahoo fields are unreliable, a name arrives here already down on the day. Without this the flag
    # line prints things like "+-1% day", which is not an igniter by any reading. Trust the quote, not
    # the screen. (Found 2026-09-04 running a pass at 09:44, before radar's usual 10:10 window.)
    if chg is None or chg < 10:
        continue
    try:
        d = yf.Ticker(s).history(period="1d", interval="1m", prepost=False)
        if d.empty:
            continue
        d = d.tz_convert(ET); d = d[d.index.date == d.index[-1].date()]
        if len(d) < 15:
            continue
        last = float(d["Close"].iloc[-1]); hi = float(d["High"].max())
        hi_row = d.loc[d["High"].idxmax()].name
        hod_age = (datetime.datetime.now(ET) - hi_row.to_pydatetime()).total_seconds() / 60
        vs_hod = (last / hi - 1) * 100
        slam5 = min((float(b["Low"]) / float(b["High"]) - 1) * 100 for _, b in d.tail(5).iterrows())
        blowoff_all = min((float(b["Low"]) / float(b["High"]) - 1) * 100 for _, b in d.iterrows())
        # CONFIRMED igniter at a fresh clean HOD (the validated baseline).
        if hod_age <= 12 and vs_hod > -2 and slam5 > -6 and blowoff_all > -10:
            sf = None
            try:
                sf = yf.Ticker(s).info.get("shortPercentOfFloat")
                sf = round(sf * 100) if sf is not None else None
            except Exception:
                pass
            hits.append((chg or 0, s, last, hi, chg, hi_row.strftime("%H:%M"), vs_hod, sf))
    except Exception:
        continue

prev = set(open(PREV).read().split()) if os.path.exists(PREV) else set()
firstflag = json.load(open(FF)) if os.path.exists(FF) else {}
cur = [h[1] for h in hits]
for chg, s, last, hi, c, hodt, vh, sf in sorted(hits, key=lambda h: h[0], reverse=True):
    if s in prev:
        continue
    if s in firstflag and last > firstflag[s] * 1.01:   # already flagged today, now HIGHER = chase -> skip
        continue
    sq = f" short{sf}%" if sf else ""
    line = f"{now} ET  {s} ${last:.2f} (HOD ${hi:.2f}@{hodt}) +{c:.0f}% day | vsHOD{vh:+.0f}%{sq}"
    print("🟢 " + line)
    with open(LOG, "a") as f:
        f.write(line + "\n")
    if s not in firstflag:
        firstflag[s] = last
with open(PREV, "w") as f:
    f.write(" ".join(cur))
json.dump(firstflag, open(FF, "w"))
