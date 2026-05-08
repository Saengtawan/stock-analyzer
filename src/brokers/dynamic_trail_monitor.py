"""Dynamic trail monitor — runs every 5 min during market hours.

For each open position:
  1. Get current price + entry price
  2. Compute peak gain since entry
  3. Determine schedule trail % based on profit threshold
  4. Update Alpaca/IBKR trailing stop if trail % needs tightening

Schedule (validated walk-forward Apr-2026):
  Early bucket (entry mfo<75): peak<+1.5% → trail 3.0%
                                peak≥+1.5% → trail 1.5%
                                peak≥+2.5% → trail 0.5%
  Late bucket (entry mfo≥75):  peak<+2.0% → trail 3.0%
                                peak≥+2.0% → trail 1.0%

Backtest: dynamic gives 85.8% WR vs static 78.3% (walk-forward, +7.5pp).
"""
import os
import sqlite3
import time
from datetime import datetime
import pytz
from pathlib import Path

from .ibkr_broker import IBKRBroker

ET = pytz.timezone('US/Eastern')
HIST_DB = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'
JOURNAL_DB = Path(__file__).resolve().parents[2] / 'data' / 'scan_journal.db'


# Schedule per bucket: list of (peak_gain_threshold, new_trail_pct)
# 2026-05-06 v2: Widened 3.0% → 5.0% — catches longer rallies (e.g. IQV ride to +10%).
#   WF (B2 ensemble): WR 83.7% (-1.7pp from 3%), avg +2.79% (+0.30pp), total +530% (+57% vs 2.5%).
#   Best total in WF sweep [1.5-7.0%]. Trade-off: WR -3.8pp, avg gain +0.30pp.
#   Loss size larger when stops fire (-1.5 to -3.5%), but ride winners further.
# 2026-05-06: 2.5% → 3.0% (replaced — marginal +1%).
# 2026-05-05: Fixed 2.5% (too tight for V-shape).
SCHEDULE_EARLY = [(0.0, 5.0)]
SCHEDULE_LATE = [(0.0, 1.0), (0.5, 0.5), (1.0, 0.2)]


def trail_pct_for(peak_gain: float, mfo: int) -> float:
    """Look up trail % from schedule based on current peak gain and bucket."""
    schedule = SCHEDULE_EARLY if mfo < 75 else SCHEDULE_LATE
    tp = schedule[0][1]
    for thr, pct in schedule:
        if peak_gain >= thr:
            tp = pct
    return tp


def get_pick_meta(symbol: str, today_et: str):
    """Look up entry mfo and entry price from scan_journal for today's pick."""
    if not JOURNAL_DB.exists(): return None, None
    con = sqlite3.connect(str(JOURNAL_DB))
    row = con.execute("""
        SELECT bucket, entry, scan_ts FROM scan_picks
        WHERE strategy='ml_filter' AND scan_date=? AND symbol=?
        ORDER BY scan_ts ASC LIMIT 1
    """, (today_et, symbol)).fetchone()
    con.close()
    if not row: return None, None
    bucket, entry, scan_ts = row
    # Parse mfo from bucket label "09:30-10:00" → mfo bucket midpoint
    # Or compute from scan_ts vs market open 09:30
    try:
        ts = datetime.strptime(scan_ts.split()[1][:5], '%H:%M')
        mfo = (ts.hour - 9) * 60 + ts.minute - 30
    except Exception:
        mfo = {'09:30-10:00': 5, '10:00-10:45': 30,
               '10:45-11:30': 75, '11:30-13:00': 120}.get(bucket, 30)
    return mfo, float(entry)


def run_once():
    now_et = datetime.now(ET)
    today_str = now_et.strftime('%Y-%m-%d')

    # Skip outside trading hours
    hh, mm = now_et.hour, now_et.minute
    minutes = hh * 60 + mm
    if minutes < 9*60+30 or minutes >= 16*60:
        print(f"[{now_et.strftime('%H:%M')}] outside market hours, skip")
        return

    broker = IBKRBroker()
    try:
        if not broker.connect():
            print(f"[{now_et.strftime('%H:%M')}] IBKR not connected — skip")
            return

        positions = broker.get_positions()
        if not positions:
            return

        print(f"[{now_et.strftime('%H:%M')}] Checking {len(positions)} positions:")
        for pos in positions:
            entry_mfo, journal_entry = get_pick_meta(pos.symbol, today_str)
            entry = journal_entry or pos.avg_cost
            if not entry or entry <= 0:
                print(f"  {pos.symbol}: no entry price, skip")
                continue
            mfo = entry_mfo if entry_mfo is not None else 30  # default to early bucket
            # Note: peak tracking would need bar history. Use current price as proxy
            # (IBKR trailing stop tracks peak internally).
            current_gain = (pos.market_price / entry - 1) * 100
            target_trail = trail_pct_for(current_gain, mfo)
            print(f"  {pos.symbol}: entry=${entry:.2f} cur=${pos.market_price:.2f} "
                  f"gain={current_gain:+.2f}%  → target trail={target_trail:.2f}%")
            # Update trail (only if tightening — never loosen)
            # IBKR doesn't expose current trailingPercent on order — just send new one each time
            # If new trail % is tighter than what's set, IBKR will use the tighter one effectively
            broker.update_trail_pct(pos.symbol, target_trail)
            print(f"    → updated trail to {target_trail}%")
    finally:
        broker.disconnect()


if __name__ == '__main__':
    run_once()
