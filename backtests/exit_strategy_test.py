#!/usr/bin/env python3
"""
Exit strategy backtest for 10:00+ buckets (1000, 1045, 1130).
Optimized: loads only relevant symbols/dates, processes in chunks.
"""

import sqlite3
import numpy as np
from collections import defaultdict
import sys

DB_PATH = "data/trade_history.db"

# DST boundaries
DST_RANGES = [
    ("2025-03-09", "2025-11-02"),
    ("2026-03-08", "2026-11-01"),
]

def is_edt(date_str):
    for start, end in DST_RANGES:
        if start <= date_str <= end:
            return True
    return False

def time_str_to_mins(t):
    return int(t[:2]) * 60 + int(t[3:5])

ET = lambda h, m: h * 60 + m

BUCKETS = {
    "1000": (ET(10, 0), ET(10, 45)),
    "1045": (ET(10, 45), ET(11, 30)),
    "1130": (ET(11, 30), ET(13, 0)),
}

MARKET_CLOSE = ET(16, 0)
MARKET_OPEN = ET(9, 30)
EOD_EXIT = ET(15, 55)


def define_strategies():
    strategies = []

    # 1. Fixed trails
    for trail in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        strategies.append(('fixed_trail', f'fixed_{trail}%', {'trail': trail}))

    # 2. Decay from entry time
    decays = [
        ('decay_3→2_30m', [(0, 3.0), (30, 2.0)]),
        ('decay_3→1_30m', [(0, 3.0), (30, 1.0)]),
        ('decay_2→1_30m', [(0, 2.0), (30, 1.0)]),
        ('decay_3→2→1_15m/30m', [(0, 3.0), (15, 2.0), (30, 1.0)]),
        ('decay_2→1.5→1_15m/30m', [(0, 2.0), (15, 1.5), (30, 1.0)]),
        ('decay_3→2→1_10m/20m', [(0, 3.0), (10, 2.0), (20, 1.0)]),
        ('decay_2.5→1.5→1_15m/30m', [(0, 2.5), (15, 1.5), (30, 1.0)]),
        ('decay_2→1_15m', [(0, 2.0), (15, 1.0)]),
    ]
    for name, phases in decays:
        strategies.append(('decay_entry', name, {'phases': phases}))

    # 3. Decay from clock time
    clocks = [
        ('clock_3→2@11:00→1@11:30', 3.0, [(ET(11,0), 2.0), (ET(11,30), 1.0)]),
        ('clock_3→2@11:30→1@12:00', 3.0, [(ET(11,30), 2.0), (ET(12,0), 1.0)]),
        ('clock_3→2@12:00→1@12:30', 3.0, [(ET(12,0), 2.0), (ET(12,30), 1.0)]),
        ('clock_3→2@12:00→1@13:00', 3.0, [(ET(12,0), 2.0), (ET(13,0), 1.0)]),
    ]
    for name, initial, thresholds in clocks:
        strategies.append(('decay_clock', name, {'initial': initial, 'thresholds': thresholds}))

    # Continuous decay
    strategies.append(('decay_continuous', 'continuous_3→1_over_30m', {'initial': 3.0, 'divisor': 30, 'floor': 1.0}))
    strategies.append(('decay_continuous', 'continuous_3→1_over_60m', {'initial': 3.0, 'divisor': 60, 'floor': 1.0}))

    # 4. Time-based exit
    for mins in [15, 30, 60]:
        strategies.append(('time_exit', f'hold_{mins}min_sell', {'hold': mins}))

    # 5. Hybrid
    hybrids = [
        ('hybrid_trail2%_30m_sell', 2.0, 30),
        ('hybrid_trail3%_30m_sell', 3.0, 30),
        ('hybrid_trail1.5%_30m_sell', 1.5, 30),
        ('hybrid_trail2%_15m_sell', 2.0, 15),
        ('hybrid_trail2%_60m_sell', 2.0, 60),
    ]
    for name, trail, sell_after in hybrids:
        strategies.append(('hybrid', name, {'trail': trail, 'sell_after': sell_after}))

    return strategies


def get_trail_pct(stype, params, mins_since_entry, bar_et):
    """Get current trail % for a given strategy at given time."""
    if stype == 'fixed_trail':
        return params['trail']
    elif stype == 'decay_entry':
        phases = params['phases']
        trail = phases[0][1]
        for phase_mins, phase_trail in phases:
            if mins_since_entry >= phase_mins:
                trail = phase_trail
        return trail
    elif stype == 'decay_clock':
        trail = params['initial']
        for thresh_et, thresh_trail in params['thresholds']:
            if bar_et >= thresh_et:
                trail = thresh_trail
        return trail
    elif stype == 'decay_continuous':
        raw = params['initial'] - (mins_since_entry / params['divisor'])
        return max(raw, params['floor'])
    elif stype == 'hybrid':
        if mins_since_entry < params['sell_after']:
            return params['trail']
        return None  # signal time_exit
    elif stype == 'time_exit':
        if mins_since_entry >= params['hold']:
            return None  # signal time_exit
        return 999.0  # no trail, just hold
    return 3.0


def simulate_all_strategies(bars_et_mins, bars_high, bars_low, bars_open, bars_close,
                            entry_price, entry_et, strategies):
    """Simulate all strategies on one trade's bars. Returns dict of pnl_pcts."""
    n_bars = len(bars_et_mins)
    n_strats = len(strategies)

    # Track state for each strategy
    peaks = np.full(n_strats, entry_price)
    exited = np.zeros(n_strats, dtype=bool)
    exit_prices = np.full(n_strats, np.nan)

    for i in range(n_bars):
        bar_et = bars_et_mins[i]
        mins_since = bar_et - entry_et
        hi = bars_high[i]
        lo = bars_low[i]
        op = bars_open[i]
        cl = bars_close[i]

        # EOD exit
        if bar_et >= EOD_EXIT:
            for s in range(n_strats):
                if not exited[s]:
                    exit_prices[s] = cl
                    exited[s] = True
            break

        for s in range(n_strats):
            if exited[s]:
                continue

            stype, sname, params = strategies[s]
            trail_pct = get_trail_pct(stype, params, mins_since, bar_et)

            if trail_pct is None:
                # Time exit signal
                exit_prices[s] = op
                exited[s] = True
                continue

            # Update peak
            peaks[s] = max(peaks[s], hi)
            trail_price = peaks[s] * (1 - trail_pct / 100)

            if lo <= trail_price:
                exit_prices[s] = trail_price
                exited[s] = True

        if np.all(exited):
            break

    # Any not exited: use last bar close
    for s in range(n_strats):
        if not exited[s]:
            exit_prices[s] = bars_close[-1]

    pnl_pcts = (exit_prices - entry_price) / entry_price * 100
    return pnl_pcts


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    strategies = define_strategies()
    print(f"Testing {len(strategies)} exit strategies")

    # Step 1: Find all candidate (symbol, date) pairs with 2-5% gain from open
    # First get day opens (09:30 bar)
    print("Finding entries...")

    # For each bucket, we need to handle EDT vs EST
    # EDT dates: time_et for 09:30 ET = '09:30', for 10:00 ET = '10:00'
    # EST dates: time_et for 09:30 ET = '08:30', for 10:00 ET = '09:00'

    # Get all unique dates
    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM intraday_bars_5m WHERE date >= '2025-01-01' AND date <= '2026-04-16' ORDER BY date"
    ).fetchall()]
    print(f"  {len(dates)} trading days")

    # Results
    results = defaultdict(lambda: defaultdict(list))
    entry_counts = defaultdict(int)
    total_entries = 0

    for di, date in enumerate(dates):
        if di % 50 == 0:
            print(f"  Processing day {di+1}/{len(dates)} ({date})... entries so far: {total_entries}", flush=True)

        edt = is_edt(date)
        # Compute time_et offset: for EST, real_et = time_et + 60
        # So time_et = real_et - 60 for EST, time_et = real_et for EDT
        offset = 0 if edt else -60  # time_et = real_et + offset

        # Market open time_et
        open_time_et_mins = MARKET_OPEN + offset
        open_time_et = f"{open_time_et_mins // 60:02d}:{open_time_et_mins % 60:02d}"

        # Load all market-hours bars for this date
        # Market hours: 09:30-16:00 ET
        min_time_et_mins = MARKET_OPEN + offset
        max_time_et_mins = MARKET_CLOSE + offset
        min_time_et = f"{min_time_et_mins // 60:02d}:{min_time_et_mins % 60:02d}"
        max_time_et = f"{max_time_et_mins // 60:02d}:{max_time_et_mins % 60:02d}"

        rows = conn.execute(
            """SELECT symbol, time_et, open, high, low, close
               FROM intraday_bars_5m
               WHERE date = ? AND time_et >= ? AND time_et <= ?
               ORDER BY symbol, time_et""",
            (date, min_time_et, max_time_et)
        ).fetchall()

        if not rows:
            continue

        # Group by symbol
        sym_bars = defaultdict(list)
        for sym, t, o, h, l, c in rows:
            real_et = time_str_to_mins(t) - offset
            sym_bars[sym].append((real_et, o, h, l, c))

        for symbol, bars in sym_bars.items():
            bars.sort(key=lambda x: x[0])

            # Find day open (09:30 bar)
            day_open = None
            for et, o, h, l, c in bars:
                if et == MARKET_OPEN:
                    day_open = o
                    break
            if day_open is None or day_open <= 0:
                continue

            # Check each bucket
            for bucket_name, (bucket_start, bucket_end) in BUCKETS.items():
                # Find first bar in bucket
                entry_bar = None
                for et, o, h, l, c in bars:
                    if et >= bucket_start and et < bucket_end:
                        entry_bar = (et, o, h, l, c)
                        break

                if entry_bar is None:
                    continue

                entry_et, entry_price = entry_bar[0], entry_bar[1]
                if entry_price <= 0:
                    continue

                gain = (entry_price - day_open) / day_open * 100
                if gain < 2.0 or gain > 5.0:
                    continue

                # Get bars after entry
                after_bars = [(et, o, h, l, c) for et, o, h, l, c in bars if et > entry_et]
                if not after_bars:
                    continue

                after_et = np.array([b[0] for b in after_bars])
                after_hi = np.array([b[2] for b in after_bars])
                after_lo = np.array([b[3] for b in after_bars])
                after_op = np.array([b[1] for b in after_bars])
                after_cl = np.array([b[4] for b in after_bars])

                pnls = simulate_all_strategies(
                    after_et, after_hi, after_lo, after_op, after_cl,
                    entry_price, entry_et, strategies
                )

                total_entries += 1
                entry_counts[bucket_name] += 1

                for s_idx, (stype, sname, params) in enumerate(strategies):
                    results[bucket_name][sname].append(pnls[s_idx])

    conn.close()

    # Report
    print(f"\n{'='*110}")
    print(f"EXIT STRATEGY BACKTEST RESULTS — {total_entries} total entries")
    print(f"{'='*110}")

    for bucket in ["1000", "1045", "1130"]:
        bs, be = BUCKETS[bucket]
        print(f"\n{'='*110}")
        print(f"BUCKET {bucket} ({bs//60}:{bs%60:02d}-{be//60}:{be%60:02d} ET) — {entry_counts[bucket]} entries")
        print(f"{'='*110}")

        bucket_results = []
        for sname, pnls in results[bucket].items():
            arr = np.array(pnls)
            n = len(arr)
            if n == 0:
                continue
            wr = np.mean(arr > 0) * 100
            avg = np.mean(arr)
            med = np.median(arr)
            wins = arr[arr > 0]
            losses = arr[arr <= 0]
            avg_win = np.mean(wins) if len(wins) > 0 else 0
            avg_loss = np.mean(losses) if len(losses) > 0 else 0
            bucket_results.append((sname, wr, avg, med, avg_win, avg_loss, n))

        # Sort by WR
        bucket_results.sort(key=lambda x: x[1], reverse=True)

        print(f"\n{'Strategy':<40} {'WR%':>6} {'AvgPnL':>8} {'MedPnL':>8} {'AvgWin':>8} {'AvgLoss':>8} {'N':>6}")
        print("-" * 110)
        for name, wr, avg, med, aw, al, n in bucket_results:
            print(f"{name:<40} {wr:>6.1f} {avg:>8.3f} {med:>8.3f} {aw:>8.3f} {al:>8.3f} {n:>6}")

        print(f"\n--- TOP 5 by WR for {bucket} ---")
        for i, (name, wr, avg, med, aw, al, n) in enumerate(bucket_results[:5]):
            print(f"  #{i+1}: {name:<40} WR={wr:.1f}%  AvgPnL={avg:.3f}%  N={n}")

        print(f"\n--- TOP 5 by AvgPnL for {bucket} ---")
        by_pnl = sorted(bucket_results, key=lambda x: x[2], reverse=True)
        for i, (name, wr, avg, med, aw, al, n) in enumerate(by_pnl[:5]):
            print(f"  #{i+1}: {name:<40} AvgPnL={avg:.3f}%  WR={wr:.1f}%  N={n}")


if __name__ == "__main__":
    run()
