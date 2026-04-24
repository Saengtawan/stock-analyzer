"""
Outcome Updater — fills in pick_outcomes for picks in the journal.

Reads unfilled picks from scan_journal.db, fetches end-of-day data
from intraday_bars_5m (or daily_ohlc for older picks), computes
outcome metrics, and writes to pick_outcomes.

Usage:
    python3 -m src.scan.outcome_updater [--days N]

Or as cron (daily 16:30 ET after market close):
    30 16 * * 1-5 cd /path && python3 -m src.scan.outcome_updater
"""
import sqlite3
import sys
from datetime import datetime
import pytz
from pathlib import Path

ET = pytz.timezone('US/Eastern')
JOURNAL_DB = Path(__file__).resolve().parents[2] / 'data' / 'scan_journal.db'
HIST_DB = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


def get_intraday_outcome(symbol: str, date: str, entry_price: float, sl_price: float,
                         trail_pct: float = 3.0) -> dict:
    """Walk 5-min bars forward from scan time to compute outcome.

    Returns dict with: exit_price, exit_reason, pnl_pct, reached_tp (hit +1%),
    hit_sl, max_gain_pct, max_drawdown_pct.
    """
    conn = sqlite3.connect(str(HIST_DB))
    rows = conn.execute("""
        SELECT time_et, open, high, low, close
        FROM intraday_bars_5m
        WHERE symbol = ? AND date = ?
        ORDER BY time_et
    """, (symbol, date)).fetchall()
    conn.close()

    if not rows:
        return None

    # Find first bar where price touches entry price (simulate fill)
    # For simplicity, assume entry fills at first bar's open or immediately
    peak = entry_price
    max_gain = 0.0
    max_drawdown = 0.0
    reached_tp = False  # did it hit +1%?
    hit_sl = False
    exit_price = None
    exit_reason = None

    tp_price = entry_price * 1.01  # +1% = TP hit target (matches label)

    for te, o, h, l, c in rows:
        # Update peak
        if h > peak:
            peak = h
            gain = (h / entry_price - 1) * 100
            if gain > max_gain:
                max_gain = gain
        # Update drawdown
        dd = (l / entry_price - 1) * 100
        if dd < max_drawdown:
            max_drawdown = dd

        # Check +1% reached
        if h >= tp_price:
            reached_tp = True

        # Check SL (low touches)
        if l <= sl_price and not exit_price:
            exit_price = sl_price
            exit_reason = 'SL'
            hit_sl = True
            break

        # Check trail 1% from peak
        if exit_price is None and peak > entry_price * 1.01:
            trail_stop = peak * (1 - trail_pct / 100)
            if l <= trail_stop:
                exit_price = trail_stop
                exit_reason = 'trail'
                break

    # If no exit triggered, use last bar close (EOD)
    if exit_price is None and rows:
        exit_price = rows[-1][4]
        exit_reason = 'EOD'

    pnl_pct = (exit_price / entry_price - 1) * 100 if exit_price else 0

    return {
        'exit_price': round(exit_price, 2) if exit_price else None,
        'exit_reason': exit_reason,
        'pnl_pct': round(pnl_pct, 3),
        'reached_tp': reached_tp,
        'hit_sl': hit_sl,
        'max_gain_pct': round(max_gain, 3),
        'max_drawdown_pct': round(max_drawdown, 3),
    }


def update_pending(days_back: int = 7) -> int:
    """Fill in outcomes for all picks in last N days without outcome."""
    conn = sqlite3.connect(str(JOURNAL_DB))
    pending = conn.execute("""
        SELECT p.id, p.symbol, p.scan_date, p.entry, p.sl_price, p.trail_pct
        FROM scan_picks p
        LEFT JOIN pick_outcomes o ON p.id = o.pick_id
        WHERE o.pick_id IS NULL
        AND p.scan_date >= date('now', ?)
        ORDER BY p.scan_date DESC
    """, (f'-{days_back} days',)).fetchall()

    print(f"Pending picks: {len(pending)}")
    updated = 0
    skipped = 0

    for pick_id, symbol, scan_date, entry, sl_price, trail_pct in pending:
        # Don't update today's picks (market still open)
        today = datetime.now(ET).strftime('%Y-%m-%d')
        if scan_date == today:
            now_et = datetime.now(ET)
            if now_et.hour < 16:
                skipped += 1
                continue

        # Default trail 3.0 (matches ml_filter 10+ buckets). 09:30 uses 5.0 but that's stored in trail_pct.
        outcome = get_intraday_outcome(symbol, scan_date, entry, sl_price, trail_pct or 3.0)
        if not outcome:
            print(f"  {pick_id} {symbol} {scan_date}: no bars found")
            skipped += 1
            continue

        label = 1 if outcome['pnl_pct'] > 0 else 0
        conn.execute("""
            INSERT OR REPLACE INTO pick_outcomes (
                pick_id, symbol, exit_price, exit_reason, exit_ts,
                pnl_pct, reached_tp, hit_sl, max_gain_pct, max_drawdown_pct,
                outcome_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pick_id, symbol, outcome['exit_price'], outcome['exit_reason'],
            datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S'),
            outcome['pnl_pct'], outcome['reached_tp'], outcome['hit_sl'],
            outcome['max_gain_pct'], outcome['max_drawdown_pct'], label,
        ))
        updated += 1
        if updated % 20 == 0:
            print(f"  updated {updated}")

    conn.commit()
    conn.close()
    print(f"Done. Updated: {updated}, Skipped: {skipped}")
    return updated


if __name__ == '__main__':
    days = 7
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith('--days='):
                days = int(arg.split('=')[1])
    update_pending(days)
