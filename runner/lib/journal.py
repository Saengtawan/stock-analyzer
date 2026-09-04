"""runner/lib/journal.py — the runner (catalyst + good-entry) experiment's OWN journal.

The bet (REVISED after the 08-24..08-26 retrospective, forward-UNPROVEN): the biggest EOD winners were
high-momentum float/squeeze gappers with NO catalyst (NCPL +51%, JEM +21%, PMI +16/+15% hold-to-close) —
the names the old fresh-catalyst filter kept DROPPING, while the catalyst picks fizzled (avg -0.3%). So
selection flipped: POND = today's biggest low-price gappers (not catalyst-filtered); GATE = drop the
BLOW-OFFS (a violent first-hour single-bar reversal; every crasher had a >~16% single-bar drop — BTCT,
CRE — every winner stayed <~11%). Enter ~10:30, HOLD TO CLOSE (no trailing), target +10% FROM ENTRY;
scoreboard = `trade_pct`. Trailing was removed 08-25 (it gave back PRZO's +15.5% peak to -1.8%); peak_pct
and a hypothetical trail_pct are kept only as references. The crash-gate is a crash-AVOIDER not a winner-
picker (in-sample n=14, NCPL-carried, LUCY a false block) — forward-test before trusting. A ">+10% day
close" is nearly free for a name already up big; the real metric is trade_pct (entry->close).

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
        PRIMARY KEY (date, sym, scan_time))""")
    for col, typ in (("peak_pct", "REAL"), ("trail_pct", "REAL")):
        try:
            c.execute(f"ALTER TABLE picks ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # migrate old PK (date,sym) -> (date,sym,scan_time) so multiple entry windows per name coexist
    # (a re-run at the current window logs its own row instead of overwriting the morning 10:30 pick)
    row = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='picks'").fetchone()
    if row and "PRIMARY KEY (date, sym))" in row[0]:
        cols = ("date,sym,scan_time,price_scan,prev_close,day_pct_at_scan,dir_confirmed,who_buys,"
                "target_pct,reason,close_px,day_close_pct,trade_pct,peak_pct,trail_pct,hit,graded")
        c.execute("ALTER TABLE picks RENAME TO picks_old")
        c.execute("""CREATE TABLE picks (
            date TEXT, sym TEXT, scan_time TEXT, price_scan REAL, prev_close REAL, day_pct_at_scan REAL,
            dir_confirmed TEXT, who_buys TEXT, target_pct REAL, reason TEXT, close_px REAL,
            day_close_pct REAL, trade_pct REAL, peak_pct REAL, trail_pct REAL, hit INTEGER,
            graded INTEGER DEFAULT 0, PRIMARY KEY (date, sym, scan_time))""")
        c.execute(f"INSERT INTO picks ({cols}) SELECT {cols} FROM picks_old")
        c.execute("DROP TABLE picks_old")
        c.commit()
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
    for date, sym, ps, pc, tgt, st in rows:
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
        # path AFTER the entry time (default 10:30 if scan_time missing) — for peak + trailing exit
        et = st or "10:30"
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
        trade_pct = round((close / ps - 1) * 100, 2) if ps else None       # hold-to-close = THE exit
        peak_pct = round((peak / ps - 1) * 100, 2) if ps else None         # best offered (reference)
        trail_pct = round((exit_px / ps - 1) * 100, 2) if ps else None     # what a 15% trail WOULD do (ref only)
        # EXIT = hold-to-close, NO trailing (removed 08-25: the 15% trail gave back PRZO's +15.5% peak to
        # -1.8% while hold-to-close booked +3.3%; trailing hurt every pick that day). hit off trade_pct.
        hit = 1 if (trade_pct is not None and trade_pct >= (tgt or 10)) else 0
        c.execute("""UPDATE picks SET close_px=?, day_close_pct=?, trade_pct=?, peak_pct=?, trail_pct=?,
                     hit=?, graded=1 WHERE date=? AND sym=? AND scan_time IS ?""",
                  (close, day_close_pct, trade_pct, peak_pct, trail_pct, hit, date, sym, st))
        n += 1
        if verbose:
            print(f"  {sym} {date}: entry {ps} | peak {peak_pct:+.1f}% | "
                  f"**HOLD-TO-CLOSE {trade_pct:+.1f}% ({'HIT' if hit else 'miss'} +{tgt}%)** | "
                  f"(trail-{trail_stop:.0f}% would've been {trail_pct:+.1f}%, ref) | day {day_close_pct:+.1f}% (free ref)")
    c.commit(); c.close()
    if verbose:
        print(f"[runner] graded {n} pick(s)")
    return n


def recent(k=25):
    c = _conn()
    print("== recent runner picks (date, sym, scan_time, peak / trail / hold-to-close, hit, graded) ==")
    for r in c.execute("""SELECT date,sym,scan_time,peak_pct,trail_pct,trade_pct,hit,graded FROM picks
                          ORDER BY date DESC, sym, scan_time LIMIT ?""", (k,)):
        print(r)
    print("== SCOREBOARD: +10%-FROM-ENTRY via HOLD-TO-CLOSE (hit = trade_pct >= +10%; NO trailing) ==")
    for r in c.execute("SELECT COUNT(*),SUM(hit),AVG(trade_pct),AVG(trail_pct) FROM picks WHERE graded=1"):
        tot, hits, avg_hold, avg_trail = r
        if tot:
            print(f"  hit {hits or 0}/{tot} = {100*(hits or 0)/tot:.0f}% | avg HOLD-TO-CLOSE {avg_hold:+.2f}% "
                  f"| (avg trail-15% would've been {avg_trail:+.2f}%, ref)")
    c.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recent"
    grade() if cmd == "grade" else recent()
