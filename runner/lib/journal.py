"""runner/lib/journal.py — the runner (catalyst + good-entry) experiment's OWN journal.

The bet (REVISED after the 08-24 forward day, forward-UNPROVEN): work backwards from "which small-cap /
low-price names END the day up big" and catch them early (~10:30) at a GOOD entry — a fresh CATALYST
still re-rating and NOT yet extended (flat/basing, or faded-then-reclaiming). Enter ~10:30, exit on a
TRAILING stop, target +10% FROM THE ENTRY; scoreboard = `trail_pct`. (The original momentum-persistence
thesis — follow the 10:30 up-confirmed — was FALSIFIED 08-24: it bought extended tops (BTCT +55%→−32%)
and missed the faded-catalyst winner PMI +17.5%.) A ">+10% day close" is nearly free for a name already
up big, so it is only a reference — the real metric is trail_pct from the ~10:30 entry.

Fully isolated + OFF-RECORD: writes ONLY to data/runner.db + runner/*. Reads market data via yfinance.
NEVER touches resonance/overnight/exec_ai/swing/rotation. It is a speculative experiment; nothing is
sized until the catalyst+good-entry read beats chance over a real forward sample.

CLI:
  python -m runner.lib.journal recent
  python -m runner.lib.journal grade      # grade today's picks at the close (deterministic, yfinance)
"""
from __future__ import annotations
import os, sqlite3, sys, datetime, warnings, zoneinfo

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                  "data", "runner.db")
ET = zoneinfo.ZoneInfo("America/New_York")


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS picks (
        date TEXT, sym TEXT,
        scan_time TEXT,       -- when the confirm scan ran (ET)
        price_scan REAL,      -- modeled entry = price at the ~10:30 scan
        prev_close REAL,      -- prior day's close (for day % + gap)
        day_pct_at_scan REAL, -- how much it was already up on the day at scan (prev_close -> price_scan)
        dir_confirmed TEXT,   -- 'up' (we only follow up-confirmed)
        who_buys TEXT,        -- flow read: arriving / consumed / theme / squeeze note
        target_pct REAL,      -- the >+10% day target
        reason TEXT,
        close_px REAL, day_close_pct REAL,   -- prev_close -> close (the day gain)
        trade_pct REAL,       -- price_scan -> close (hold-to-close result — the OLD exit)
        peak_pct REAL,        -- entry -> intraday peak after entry (the best it offered)
        trail_pct REAL,       -- entry -> a simulated TRAILING-stop exit (the real exit; hold-to-close threw away DAIC +42%)
        hit INTEGER,          -- 1 if trail_pct >= target_pct (the trailed trade made the +10%-from-entry bar)
        graded INTEGER DEFAULT 0,
        PRIMARY KEY (date, sym))""")
    for col, typ in (("peak_pct", "REAL"), ("trail_pct", "REAL")):
        try:
            c.execute(f"ALTER TABLE picks ADD COLUMN {col} {typ}")
        except Exception:
            pass
    return c


def log(date, sym, price_scan, prev_close, dir_confirmed, who_buys, reason,
        scan_time=None, target_pct=10.0):
    day_at = round((price_scan / prev_close - 1) * 100, 2) if prev_close else None
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO picks
        (date,sym,scan_time,price_scan,prev_close,day_pct_at_scan,dir_confirmed,who_buys,target_pct,reason)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
              (date, sym, scan_time, price_scan, prev_close, day_at, dir_confirmed, who_buys, target_pct, reason))
    c.commit(); c.close()
    print(f"[runner] logged {sym} {date} @{price_scan} (day {day_at:+}% at scan) target +{target_pct}%")


TRAIL_STOP = 15.0  # % below the running peak that exits the trade (these are volatile penny names)


def grade(verbose=True, trail_stop=TRAIL_STOP):
    """Grade today's ungraded picks at the close — deterministic, yfinance. Records THREE exits:
      trade_pct = hold-to-close (the OLD exit),
      peak_pct  = entry -> best intraday high after entry (what was offered),
      trail_pct = a simulated TRAILING-stop exit (exit when price falls `trail_stop`% off the running
                  peak) — the real exit, since hold-to-close threw away DAIC's +42% peak (08-24).
    `hit` = trail_pct >= target (+10% from entry). Entry is modeled at the entry_time bar (~10:30)."""
    import yfinance as yf
    warnings.filterwarnings("ignore")
    c = _conn()
    rows = c.execute("SELECT date,sym,price_scan,prev_close,target_pct,scan_time FROM picks WHERE graded=0").fetchall()
    n = 0
    for date, sym, ps, pc, tgt, et in rows:
        d = datetime.date.fromisoformat(date)
        df = yf.download(sym, start=date, end=(d + datetime.timedelta(days=1)).isoformat(),
                         interval="1m", prepost=False, progress=False, auto_adjust=False)
        if df is None or df.empty:
            continue
        if hasattr(df.columns, "levels"):
            df.columns = [x[0] for x in df.columns]
        df = df.tz_convert(ET)
        rth = df[df.index.strftime("%H:%M") >= "09:30"]
        if not len(rth):
            continue
        b = rth[rth.index.strftime("%H:%M") == "15:55"]
        close = float(b["Close"].iloc[0]) if len(b) else float(rth["Close"].iloc[-1])
        # path AFTER the entry time (default 10:20 if scan_time missing) — for peak + trailing exit
        et = et or "10:20"
        path = rth[rth.index.strftime("%H:%M") >= et]
        if not len(path):
            path = rth
        peak = float(path["High"].max())
        # simulate a trailing stop: walk bars, track running peak, exit when a bar's low <= peak*(1-trail)
        run_peak = float(path["Close"].iloc[0]); exit_px = close
        for _, bar in path.iterrows():
            run_peak = max(run_peak, float(bar["High"]))
            stop = run_peak * (1 - trail_stop / 100)
            if float(bar["Low"]) <= stop:
                exit_px = stop      # trailing stop hit
                break
        day_close_pct = round((close / pc - 1) * 100, 2) if pc else None
        trade_pct = round((close / ps - 1) * 100, 2) if ps else None       # hold-to-close (old)
        peak_pct = round((peak / ps - 1) * 100, 2) if ps else None
        trail_pct = round((exit_px / ps - 1) * 100, 2) if ps else None     # trailing exit (real)
        hit = 1 if (trail_pct is not None and trail_pct >= (tgt or 10)) else 0
        c.execute("""UPDATE picks SET close_px=?, day_close_pct=?, trade_pct=?, peak_pct=?, trail_pct=?,
                     hit=?, graded=1 WHERE date=? AND sym=?""",
                  (close, day_close_pct, trade_pct, peak_pct, trail_pct, hit, date, sym))
        n += 1
        if verbose:
            print(f"  {sym} {date}: entry {ps} | peak {peak_pct:+.1f}% | "
                  f"**trail(-{trail_stop:.0f}%) {trail_pct:+.1f}% ({'HIT' if hit else 'miss'} +{tgt}%)** | "
                  f"hold-to-close {trade_pct:+.1f}% | day {day_close_pct:+.1f}% (free ref)")
    c.commit(); c.close()
    if verbose:
        print(f"[runner] graded {n} pick(s)")
    return n


def recent(k=25):
    c = _conn()
    print("== recent runner picks (peak / trail / hold-to-close, from entry) ==")
    for r in c.execute("""SELECT date,sym,peak_pct,trail_pct,trade_pct,hit,graded FROM picks
                          ORDER BY date DESC LIMIT ?""", (k,)):
        print(r)
    print("== SCOREBOARD: +10%-FROM-ENTRY via TRAILING exit (hit = trail_pct >= +10%) ==")
    for r in c.execute("SELECT COUNT(*),SUM(hit),AVG(trail_pct),AVG(trade_pct) FROM picks WHERE graded=1"):
        tot, hits, avg_trail, avg_hold = r
        if tot:
            print(f"  hit {hits or 0}/{tot} = {100*(hits or 0)/tot:.0f}% | avg TRAIL {avg_trail:+.2f}% | avg hold-to-close {avg_hold:+.2f}% (the old exit)")
        c.close(); return
    for r in c.execute("SELECT COUNT(*),SUM(hit),AVG(trade_pct) FROM picks WHERE graded=1"):
        tot, hits, avg = r
        if tot:
            print(f"  hit +10%-from-entry: {hits or 0}/{tot} = {100*(hits or 0)/tot:.0f}% | avg trade (entry->close) {avg:+.2f}%")
    c.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recent"
    grade() if cmd == "grade" else recent()
