"""runner/lib/journal.py — the momentum-runner experiment's OWN journal.

The bet (backtest-seeded, forward-UNPROVEN): a penny / small-cap TOP GAINER's direction is a coin flip
at the 09:30 open (premarket gap did NOT predict it — tested 53%), but by ~10:15-10:30 the intraday
direction has RESOLVED and PERSISTS to the close (tested 83% on n=12, high variance). So this system
scans the confirmed movers at ~10:30, applies the who-buys flow read, and predicts which will CLOSE
up big (target >+10% on the day). Entry is modeled at the 10:30 scan price.

Fully isolated + OFF-RECORD: writes ONLY to data/runner.db + runner/*. Reads market data via yfinance.
NEVER touches resonance/overnight/exec_ai/swing/rotation. It is a speculative experiment; nothing is
sized until the forward record proves the 83% persistence holds live.

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
        trade_pct REAL,       -- price_scan -> close (the actual tradeable result)
        hit INTEGER,          -- 1 if day_close_pct >= target_pct
        graded INTEGER DEFAULT 0,
        PRIMARY KEY (date, sym))""")
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


def grade(verbose=True):
    """Grade today's ungraded picks at the close (15:55 ET) — deterministic, yfinance."""
    import yfinance as yf
    warnings.filterwarnings("ignore")
    c = _conn()
    rows = c.execute("SELECT date,sym,price_scan,prev_close,target_pct FROM picks WHERE graded=0").fetchall()
    n = 0
    for date, sym, ps, pc, tgt in rows:
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
        day_close_pct = round((close / pc - 1) * 100, 2) if pc else None
        trade_pct = round((close / ps - 1) * 100, 2) if ps else None
        # PRIMARY scoreboard = the TRADE (scan->close). The ">+10% day close" target is nearly free for a
        # name already up +27%..+407% at scan (it would have to crash to miss), so it proves nothing —
        # `hit` now = did the 10:30 momentum-follow entry actually GAIN to the close (trade_pct > 0).
        hit = 1 if (trade_pct is not None and trade_pct > 0) else 0
        day_hit = 1 if (day_close_pct is not None and day_close_pct >= (tgt or 10)) else 0
        c.execute("""UPDATE picks SET close_px=?, day_close_pct=?, trade_pct=?, hit=?, graded=1
                     WHERE date=? AND sym=?""", (close, day_close_pct, trade_pct, hit, date, sym))
        n += 1
        if verbose:
            print(f"  {sym} {date}: scan {ps} -> close {close:.2f} | "
                  f"**trade-from-scan {trade_pct:+.1f}% ({'WIN' if hit else 'loss'})** | "
                  f"day {day_close_pct:+.1f}% (>+{tgt}% {'yes' if day_hit else 'no'} — free ref)")
    c.commit(); c.close()
    if verbose:
        print(f"[runner] graded {n} pick(s)")
    return n


def recent(k=25):
    c = _conn()
    print("== recent runner picks ==")
    for r in c.execute("""SELECT date,sym,day_pct_at_scan,day_close_pct,trade_pct,hit,graded FROM picks
                          ORDER BY date DESC LIMIT ?""", (k,)):
        print(r)
    print("== TRADE scoreboard (scan->close, the real metric) ==")
    for r in c.execute("SELECT COUNT(*),SUM(hit),AVG(trade_pct) FROM picks WHERE graded=1"):
        tot, hits, avg = r
        if tot:
            print(f"  trade-win {hits or 0}/{tot} = {100*(hits or 0)/tot:.0f}% | avg trade-from-scan {avg:+.2f}%")
            print(f"  (the >+10% day-close 'hit' is nearly free for top gainers — trade_pct is the scoreboard)")
    c.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recent"
    grade() if cmd == "grade" else recent()
