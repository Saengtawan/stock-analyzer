#!/usr/bin/env python3
"""
PED (Pre-Earnings Drift) filter backtest.

Tests entry windows D-3..D-8 and filter relaxations on 2023-2025 earnings.
Goal: find a config that yields ≥3 trades/month at WR ≥ 55% (current live: 1 trade in 3 months).

Entry: close on D-N (N trading days before earnings)
Exit:  close on D-1 (one trading day before earnings)
Hold:  N-1 trading days

Filters tested:
  baseline:    no filter
  green_day:   close on entry day > prev close
  above_sma20: close >= sma20 * 0.97
  rsi_35_65:   RSI(14) in [35, 65]
  volume_1x:   today vol >= 20d avg vol
  spy_ok:      SPY return on entry day >= -1%
  all_v6.58:   all of the above (current live config)

Universe: stocks with earnings in earnings_history table + daily OHLC available.
Validity: skip events where universe stock is illiquid (price < $5 or vol_avg < 100k).
"""
import sys
import sqlite3
import statistics
from collections import defaultdict
from datetime import date

DB = '/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db'

# Backtest universe: 2023-01-01 .. 2025-12-31 (full WF range; reserve 2026 for live)
START = '2023-01-01'
END   = '2025-12-31'

# Entry windows to test (trading days before earnings)
WINDOWS = [3, 4, 5, 6, 7, 8]


def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def load_events(conn):
    """All earnings events in window, with at least 30 days of OHLC available."""
    cur = conn.execute("""
        SELECT symbol, report_date
        FROM earnings_history
        WHERE report_date BETWEEN ? AND ?
        ORDER BY report_date, symbol
    """, (START, END))
    return [(r['symbol'], r['report_date']) for r in cur.fetchall()]


def load_ohlc_window(conn, symbol, end_date, n_back=30):
    """Get last n_back trading days of OHLC ending at end_date (inclusive)."""
    cur = conn.execute("""
        SELECT date, open, high, low, close, volume
        FROM stock_daily_ohlc
        WHERE symbol = ? AND date <= ?
        ORDER BY date DESC LIMIT ?
    """, (symbol, end_date, n_back))
    rows = cur.fetchall()
    rows.reverse()
    return rows


def load_spy_returns(conn):
    """{date: pct_change} for SPY."""
    cur = conn.execute("""
        SELECT date, close FROM stock_daily_ohlc WHERE symbol='SPY' ORDER BY date
    """)
    rows = cur.fetchall()
    out = {}
    prev = None
    for r in rows:
        if prev is not None and prev > 0:
            out[r['date']] = (r['close'] - prev) / prev * 100
        prev = r['close']
    return out


def rsi14(closes):
    if len(closes) < 15:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[-14:]) / 14
    avg_l = sum(losses[-14:]) / 14
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def evaluate(ohlc, n_back, spy_returns):
    """
    Given OHLC ending at the EARNINGS DAY itself, evaluate D-n entry → D-1 exit.
    Returns dict with features + return, or None if invalid.
    """
    if len(ohlc) < max(n_back + 21, 30):
        return None

    earnings_idx = len(ohlc) - 1   # position of earnings day
    entry_idx = earnings_idx - n_back   # D-N
    exit_idx = earnings_idx - 1    # D-1

    if entry_idx < 20:
        return None  # need 20d for SMA/vol_avg

    entry_row = ohlc[entry_idx]
    exit_row = ohlc[exit_idx]

    entry_close = entry_row['close']
    exit_close = exit_row['close']
    if entry_close <= 0 or exit_close <= 0 or entry_close < 5.0:
        return None

    prev_close = ohlc[entry_idx - 1]['close']
    if prev_close <= 0:
        return None

    # SMA20 + vol_avg using days BEFORE entry (no lookahead)
    closes_pre = [r['close'] for r in ohlc[entry_idx-20:entry_idx]]
    vols_pre = [r['volume'] for r in ohlc[entry_idx-20:entry_idx]]
    sma20 = sum(closes_pre) / 20
    vol_avg = sum(vols_pre) / 20
    if vol_avg < 100_000:
        return None

    # RSI on closes up to entry
    closes_for_rsi = [r['close'] for r in ohlc[max(0, entry_idx-15):entry_idx+1]]
    rsi = rsi14(closes_for_rsi)
    if rsi is None:
        return None

    today_vol = entry_row['volume']
    vol_ratio = today_vol / vol_avg if vol_avg > 0 else 0

    spy_ret = spy_returns.get(entry_row['date'], 0.0)

    return {
        'entry_date': entry_row['date'],
        'entry_close': entry_close,
        'exit_close': exit_close,
        'ret_pct': (exit_close - entry_close) / entry_close * 100,
        'green_day': entry_close > prev_close,
        'above_sma20': entry_close >= sma20 * 0.97,
        'rsi': rsi,
        'rsi_35_65': 35 <= rsi <= 65,
        'volume_1x': vol_ratio >= 1.0,
        'volume_07x': vol_ratio >= 0.7,
        'spy_ok': spy_ret >= -1.0,
    }


def filter_combos(rec):
    """Return dict {filter_name: passes_bool}."""
    return {
        'baseline':       True,
        'green_only':     rec['green_day'],
        'rsi_only':       rec['rsi_35_65'],
        'vol1x_only':     rec['volume_1x'],
        'sma20_only':     rec['above_sma20'],
        'spy_only':       rec['spy_ok'],
        # Combined
        'all_v6.58':      rec['green_day'] and rec['above_sma20'] and rec['rsi_35_65'] and rec['volume_1x'] and rec['spy_ok'],
        # Drop one filter from current
        '_drop_green':    rec['above_sma20'] and rec['rsi_35_65'] and rec['volume_1x'] and rec['spy_ok'],
        '_drop_vol':      rec['green_day'] and rec['above_sma20'] and rec['rsi_35_65'] and rec['spy_ok'],
        '_drop_rsi':      rec['green_day'] and rec['above_sma20'] and rec['volume_1x'] and rec['spy_ok'],
        '_drop_sma':      rec['green_day'] and rec['rsi_35_65'] and rec['volume_1x'] and rec['spy_ok'],
        # Volume relax
        'all_vol_07x':    rec['green_day'] and rec['above_sma20'] and rec['rsi_35_65'] and rec['volume_07x'] and rec['spy_ok'],
    }


def stats(rets):
    if not rets:
        return {'n': 0, 'wr': 0, 'avg': 0, 'med': 0, 'std': 0}
    wins = sum(1 for r in rets if r > 0)
    return {
        'n': len(rets),
        'wr': wins / len(rets) * 100,
        'avg': statistics.mean(rets),
        'med': statistics.median(rets),
        'std': statistics.stdev(rets) if len(rets) > 1 else 0,
    }


def main():
    conn = get_conn()
    print(f"Loading SPY returns ({START}..{END})...")
    spy_ret = load_spy_returns(conn)

    print(f"Loading earnings events ({START}..{END})...")
    events = load_events(conn)
    print(f"  {len(events)} events")

    # Group by (window, filter) → list of returns
    results = defaultdict(list)

    processed = 0
    for symbol, report_date in events:
        # need data for max window + 30d lookback
        ohlc = load_ohlc_window(conn, symbol, report_date, n_back=max(WINDOWS) + 30)
        # find earnings_idx in ohlc — should be last row if report_date is a trading day
        if not ohlc or ohlc[-1]['date'] != report_date:
            # Not a trading day or no data on that day
            continue

        for n in WINDOWS:
            rec = evaluate(ohlc, n, spy_ret)
            if rec is None:
                continue
            combos = filter_combos(rec)
            for name, passes in combos.items():
                if passes:
                    results[(n, name)].append(rec['ret_pct'])
        processed += 1
        if processed % 1000 == 0:
            print(f"  processed {processed}/{len(events)}")

    print(f"\nTotal events processed: {processed}\n")

    # Pretty print
    print(f"{'window':<8} {'filter':<16} {'n':>6} {'WR%':>6} {'avg%':>7} {'med%':>7} {'std%':>7}")
    print("-" * 70)
    for n in WINDOWS:
        for name in ['baseline', 'green_only', 'rsi_only', 'vol1x_only', 'sma20_only', 'spy_only',
                     'all_v6.58', '_drop_green', '_drop_vol', '_drop_rsi', '_drop_sma', 'all_vol_07x']:
            s = stats(results[(n, name)])
            if s['n'] == 0:
                continue
            print(f"D-{n:<6} {name:<16} {s['n']:>6} {s['wr']:>6.1f} {s['avg']:>+7.2f} {s['med']:>+7.2f} {s['std']:>7.2f}")
        print()


if __name__ == '__main__':
    main()
