#!/usr/bin/env python3
"""
fill_daytrade_outcomes.py — v7.8
===================================
Simulate day trade outcomes from signal_candidate_bars (1m OHLCV).
Runs nightly to build the training dataset for day trade analysis.

Strategy simulated:
  Entry:  9:35 bar open (after ORB forms at 9:30-9:34)
  Exit:   First to trigger — SL hit, TP hit, or EOD 15:55

4 SL/TP scenarios computed per symbol per day (1:2 RR each):
  A: SL=1.5%  TP=3.0%
  B: SL=2.0%  TP=4.0%   ← baseline
  C: SL=2.5%  TP=5.0%
  D: SL=3.0%  TP=6.0%

Also computed:
  - ORB: Opening Range high/low/direction/volume (9:30-9:34)
  - VWAP at entry time (cumulative from 9:30)
  - MFE/MAE: best and worst price from entry to EOD
  - EOD P&L: outcome if held all day (exits 15:55)

After 1 month (22 trading days × ~1000 symbols = ~22,000 rows):
  → Correlate premarket_gap, first_5min_return, market_breadth with WR
  → Optimize SL/TP per market regime
  → Find the feature combination with highest expected value

Cron (TZ=America/New_York):
  55 16 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_daytrade_outcomes.py >> logs/fill_daytrade_outcomes.log 2>&1
"""
import os
import sqlite3
import argparse
from datetime import datetime, timedelta

import pandas as pd
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
ET = ZoneInfo('America/New_York')

# SL/TP scenarios (pct)
SCENARIOS = [
    ('a', 1.5, 3.0),
    ('b', 2.0, 4.0),
    ('c', 2.5, 5.0),
    ('d', 3.0, 6.0),
]

ENTRY_TIME  = '09:35'
ORB_START   = '09:30'
ORB_END     = '09:34'
EOD_EXIT    = '15:55'


def compute_vwap(bars: list[tuple]) -> float | None:
    """Compute VWAP from bars up to and including bar_time. bars = (time_et, open, high, low, close, volume)."""
    tp_vol = 0.0
    vol = 0.0
    for b in bars:
        v = float(b[5]) if b[5] else 0
        tp = (float(b[2]) + float(b[3]) + float(b[4])) / 3
        tp_vol += tp * v
        vol += v
    return tp_vol / vol if vol > 0 else None


def simulate_scenario(bars_after_entry: list[tuple], entry_price: float,
                       sl_pct: float, tp_pct: float) -> tuple[str, float, int]:
    """
    Walk bars from entry. Return (exit_reason, pnl_pct, minutes_to_exit).
    bars_after_entry: list of (time_et, open, high, low, close, volume) starting at 09:36
    """
    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100)

    entry_minutes = _time_to_min(ENTRY_TIME)

    for bar in bars_after_entry:
        time_et = bar[0]
        low     = float(bar[3])
        high    = float(bar[2])
        close   = float(bar[4])
        bar_min = _time_to_min(time_et)
        minutes = bar_min - entry_minutes

        # EOD forced exit
        if time_et >= EOD_EXIT:
            pnl = (close / entry_price - 1) * 100
            return ('EOD', round(pnl, 3), minutes)

        # SL hit (check low first — conservative)
        if low <= sl_price:
            pnl = (sl_price / entry_price - 1) * 100
            return ('SL_HIT', round(pnl, 3), minutes)

        # TP hit
        if high >= tp_price:
            pnl = (tp_price / entry_price - 1) * 100
            return ('TP_HIT', round(pnl, 3), minutes)

    # No exit found (bars ended before 15:55 — partial day data)
    if bars_after_entry:
        last = bars_after_entry[-1]
        pnl = (float(last[4]) / entry_price - 1) * 100
        minutes = _time_to_min(last[0]) - entry_minutes
        return ('EOD', round(pnl, 3), minutes)

    return ('NO_DATA', 0.0, 0)


def _time_to_min(t: str) -> int:
    h, m = map(int, t.split(':'))
    return h * 60 + m


def process_symbol_date(conn: sqlite3.Connection, symbol: str, date: str) -> dict | None:
    """Compute all day trade metrics for one symbol/date."""
    bars = conn.execute("""
        SELECT time_et, open, high, low, close, volume
        FROM signal_candidate_bars
        WHERE symbol = ? AND date = ?
          AND time_et >= '09:30' AND time_et <= '16:00'
        ORDER BY time_et
    """, (symbol, date)).fetchall()

    if not bars:
        return None

    # ── ORB: 9:30-9:34 ────────────────────────────────────────────────────
    orb_bars = [b for b in bars if ORB_START <= b[0] <= ORB_END]
    if not orb_bars:
        return None

    orb_open  = float(orb_bars[0][1])
    orb_high  = max(float(b[2]) for b in orb_bars)
    orb_low   = min(float(b[3]) for b in orb_bars)
    orb_close = float(orb_bars[-1][4])
    orb_vol   = sum(int(b[5]) for b in orb_bars if b[5])

    if orb_open <= 0:
        return None

    orb_range_pct = round((orb_high - orb_low) / orb_open * 100, 3)

    if orb_close > orb_open * 1.001:
        orb_direction = 'BULL'
    elif orb_close < orb_open * 0.999:
        orb_direction = 'BEAR'
    else:
        orb_direction = 'DOJI'

    # ── Entry at 9:35 ─────────────────────────────────────────────────────
    entry_bars = [b for b in bars if b[0] == ENTRY_TIME]
    if not entry_bars:
        # Use first bar after 09:34
        later = [b for b in bars if b[0] > ORB_END]
        if not later:
            return None
        entry_bars = [later[0]]

    entry_bar   = entry_bars[0]
    entry_price = float(entry_bar[1])   # open of entry bar
    if entry_price <= 0:
        return None

    # VWAP at entry (cumulative from 9:30 up to and including entry bar)
    vwap_bars = [b for b in bars if b[0] <= entry_bar[0]]
    vwap_at_entry = compute_vwap(vwap_bars)

    entry_vs_orb  = 'ABOVE' if entry_price > orb_high else ('BELOW' if entry_price < orb_low else 'INSIDE')
    entry_vs_vwap = 'ABOVE' if (vwap_at_entry and entry_price > vwap_at_entry) else 'BELOW'

    # ── Bars after entry ───────────────────────────────────────────────────
    bars_after = [b for b in bars if b[0] > entry_bar[0]]

    # ── Simulate 4 scenarios ──────────────────────────────────────────────
    results = {}
    for name, sl, tp in SCENARIOS:
        exit_r, pnl, mins = simulate_scenario(bars_after, entry_price, sl, tp)
        results[name] = (exit_r, pnl, mins)

    # ── EOD price (15:55 or last bar) ─────────────────────────────────────
    eod_bars = [b for b in bars if b[0] >= EOD_EXIT]
    eod_price = float(eod_bars[0][4]) if eod_bars else float(bars[-1][4])
    eod_pnl   = round((eod_price / entry_price - 1) * 100, 3)

    # ── MFE / MAE from entry ───────────────────────────────────────────────
    mfe = 0.0; mfe_time = None
    mae = 0.0; mae_time = None
    for b in bars_after:
        high_pct = (float(b[2]) / entry_price - 1) * 100
        low_pct  = (float(b[3]) / entry_price - 1) * 100
        if high_pct > mfe:
            mfe = high_pct; mfe_time = b[0]
        if low_pct < mae:
            mae = low_pct; mae_time = b[0]

    # ── Premarket context (from premarket_analysis) ────────────────────────
    pm = conn.execute("""
        SELECT premarket_gap_pct, first_5min_return,
               first_30min_return, premarket_vol_ratio
        FROM premarket_analysis WHERE symbol=? AND date=?
    """, (symbol, date)).fetchone()

    return {
        'orb_open':    round(orb_open, 4),
        'orb_high':    round(orb_high, 4),
        'orb_low':     round(orb_low, 4),
        'orb_close':   round(orb_close, 4),
        'orb_range_pct': orb_range_pct,
        'orb_direction': orb_direction,
        'orb_vol':     orb_vol,
        'entry_price': round(entry_price, 4),
        'entry_vs_orb':  entry_vs_orb,
        'entry_vs_vwap': entry_vs_vwap,
        'vwap_at_entry': round(vwap_at_entry, 4) if vwap_at_entry else None,
        'exit_a': results['a'][0], 'pnl_a': results['a'][1], 'min_a': results['a'][2],
        'exit_b': results['b'][0], 'pnl_b': results['b'][1], 'min_b': results['b'][2],
        'exit_c': results['c'][0], 'pnl_c': results['c'][1], 'min_c': results['c'][2],
        'exit_d': results['d'][0], 'pnl_d': results['d'][1], 'min_d': results['d'][2],
        'eod_price':   round(eod_price, 4),
        'eod_pnl_pct': eod_pnl,
        'mfe_pct':     round(mfe, 3),
        'mae_pct':     round(mae, 3),
        'mfe_time':    mfe_time,
        'mae_time':    mae_time,
        'premarket_gap_pct':   pm['premarket_gap_pct'] if pm else None,
        'first_5min_return':   pm['first_5min_return'] if pm else None,
        'first_30min_return':  pm['first_30min_return'] if pm else None,
        'premarket_vol_ratio': pm['premarket_vol_ratio'] if pm else None,
    }


def main():
    parser = argparse.ArgumentParser(description='Simulate day trade outcomes from 1m bars')
    parser.add_argument('--date', default=None, help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--days', type=int, default=1, help='Days to process (default: 1)')
    parser.add_argument('--symbol', default=None, help='Single symbol (for testing)')
    parser.add_argument('--force', action='store_true', help='Overwrite existing rows')
    args = parser.parse_args()

    target_date = args.date or datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] fill_daytrade_outcomes "
          f"date={target_date} days={args.days}")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    base_dt = datetime.strptime(target_date, '%Y-%m-%d')
    dates = [
        (base_dt - timedelta(days=i)).strftime('%Y-%m-%d')
        for i in range(args.days)
        if (base_dt - timedelta(days=i)).weekday() < 5
    ]

    total_ok = total_skip = 0

    for d in dates:
        if args.symbol:
            symbols = [args.symbol.upper()]
        else:
            # All symbols with bars on this date
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM signal_candidate_bars WHERE date = ?", (d,)
            ).fetchall()
            symbols = [r[0] for r in rows]

            if not args.force:
                existing = set(r[0] for r in conn.execute(
                    "SELECT symbol FROM daytrade_outcomes WHERE date = ?", (d,)
                ).fetchall())
                symbols = [s for s in symbols if s not in existing]

        print(f"\n  --- {d} --- {len(symbols)} symbols")

        rows_to_insert = []
        for sym in symbols:
            data = process_symbol_date(conn, sym, d)
            if data:
                rows_to_insert.append((
                    sym, d,
                    data['orb_open'], data['orb_high'], data['orb_low'],
                    data['orb_close'], data['orb_range_pct'], data['orb_direction'],
                    data['orb_vol'], data['entry_price'],
                    data['entry_vs_orb'], data['entry_vs_vwap'], data['vwap_at_entry'],
                    data['exit_a'], data['pnl_a'], data['min_a'],
                    data['exit_b'], data['pnl_b'], data['min_b'],
                    data['exit_c'], data['pnl_c'], data['min_c'],
                    data['exit_d'], data['pnl_d'], data['min_d'],
                    data['eod_price'], data['eod_pnl_pct'],
                    data['mfe_pct'], data['mae_pct'],
                    data['mfe_time'], data['mae_time'],
                    data['premarket_gap_pct'], data['first_5min_return'],
                    data['first_30min_return'], data['premarket_vol_ratio'],
                ))
                total_ok += 1
            else:
                total_skip += 1

        if rows_to_insert:
            conn.executemany("""
                INSERT OR IGNORE INTO daytrade_outcomes
                    (symbol, date,
                     orb_open, orb_high, orb_low, orb_close,
                     orb_range_pct, orb_direction, orb_vol,
                     entry_price, entry_vs_orb, entry_vs_vwap, vwap_at_entry,
                     exit_a, pnl_a, min_a,
                     exit_b, pnl_b, min_b,
                     exit_c, pnl_c, min_c,
                     exit_d, pnl_d, min_d,
                     eod_price, eod_pnl_pct,
                     mfe_pct, mae_pct, mfe_time, mae_time,
                     premarket_gap_pct, first_5min_return,
                     first_30min_return, premarket_vol_ratio)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows_to_insert)
            conn.commit()
            print(f"    Inserted {len(rows_to_insert)} rows")

    conn.close()
    print(f"\n  Total: ok={total_ok} skipped={total_skip}")
    print("  Done.")


if __name__ == '__main__':
    main()
