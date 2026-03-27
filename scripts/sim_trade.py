#!/usr/bin/env python3
"""
sim_trade.py — v7.7
====================
Simulate a single trade: given entry, SL%, TP% — replay 1m bars to find outcome.

Usage:
  python3 scripts/sim_trade.py SYMBOL DATE ENTRY_PRICE --sl 3.0 --tp 9.0
  python3 scripts/sim_trade.py NVDA 2026-03-12 875.50 --sl 3.0 --tp 9.0
  python3 scripts/sim_trade.py AAPL 2026-03-12 --from-trades   # use actual trade price

  # With trailing stop:
  python3 scripts/sim_trade.py NVDA 2026-03-12 875.50 --sl 3.0 --trail-pct 2.0 --trail-lock 80.0

  # Multi-day hold (uses signal_candidate_bars across dates):
  python3 scripts/sim_trade.py AMZN 2026-03-11 195.00 --sl 3.0 --tp 9.0 --max-days 5
"""
import os
import sys
import sqlite3
import argparse
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
ET = ZoneInfo('America/New_York')


def load_bars_from_db(conn, symbol: str, dates: list[str]) -> pd.DataFrame:
    """Load 1m bars from signal_candidate_bars for given dates."""
    if not dates:
        return pd.DataFrame()
    placeholders = ','.join('?' * len(dates))
    rows = conn.execute(f"""
        SELECT date, time_et, open, high, low, close, volume
        FROM signal_candidate_bars
        WHERE symbol = ? AND date IN ({placeholders})
        ORDER BY date, time_et
    """, [symbol] + dates).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=['date', 'time_et', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time_et'])
    df = df.set_index('datetime')
    return df


def load_bars_from_yfinance(symbol: str, start_date: str, end_date: str,
                             prepost: bool = True) -> pd.DataFrame:
    """Fallback: download 1m bars from yfinance (max 30 days back)."""
    try:
        end_dt = (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        df = yf.download(symbol, start=start_date, end=end_dt,
                         interval='1m', auto_adjust=True, progress=False, prepost=prepost)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # Convert to ET
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize('UTC').tz_convert(ET)
        else:
            df.index = df.index.tz_convert(ET)
        df.index = df.index.tz_localize(None)
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        print(f"  yfinance error: {e}")
        return pd.DataFrame()


def get_trading_dates(start_date: str, max_days: int) -> list[str]:
    """Get up to max_days weekday dates starting from start_date."""
    dates = []
    d = datetime.strptime(start_date, '%Y-%m-%d')
    while len(dates) < max_days:
        if d.weekday() < 5:
            dates.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)
    return dates


def simulate(symbol: str, entry_date: str, entry_price: float,
             sl_pct: float, tp_pct: float | None,
             trail_pct: float | None = None, trail_lock: float = 80.0,
             max_days: int = 5, entry_time: str = '09:32',
             verbose: bool = True) -> dict:
    """
    Walk through 1m bars from entry. Return outcome dict.

    Returns:
        result: {
            outcome: 'SL_HIT' | 'TP_HIT' | 'TRAIL_STOP' | 'MAX_HOLD' | 'STILL_OPEN',
            exit_price: float,
            exit_datetime: str,
            minutes_to_exit: int,
            days_to_exit: float,
            pnl_pct: float,
            max_gain_pct: float,
            max_loss_pct: float,
        }
    """
    conn = None  # via get_session()
    conn.row_factory = dict

    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100) if tp_pct else None

    dates = get_trading_dates(entry_date, max_days)

    # Try DB first
    df = load_bars_from_db(conn, symbol, dates)
    conn.close()

    if df.empty:
        if verbose:
            print(f"  DB miss — falling back to yfinance ({entry_date} to {dates[-1]})")
        df = load_bars_from_yfinance(symbol, entry_date, dates[-1])

    if df.empty:
        return {'outcome': 'NO_DATA', 'error': 'No 1m bars available'}

    # Filter: start from entry_time on entry_date
    entry_dt_str = f"{entry_date} {entry_time}"
    entry_dt = datetime.strptime(entry_dt_str, '%Y-%m-%d %H:%M')
    df = df[df.index >= entry_dt]

    if df.empty:
        return {'outcome': 'NO_DATA', 'error': f'No bars from {entry_dt_str}'}

    if verbose:
        print(f"\n{'─'*55}")
        print(f"  Symbol:    {symbol}")
        print(f"  Entry:     ${entry_price:.2f}  @  {entry_date} {entry_time} ET")
        print(f"  SL:        ${sl_price:.2f}  (-{sl_pct:.1f}%)")
        if tp_price:
            print(f"  TP:        ${tp_price:.2f}  (+{tp_pct:.1f}%)")
        if trail_pct:
            print(f"  Trailing:  {trail_pct:.1f}% (locks when gain > {trail_lock:.0f}% of TP)")
        print(f"  Max hold:  {max_days} days")
        print(f"  Bars:      {len(df)} 1m bars available")
        print(f"{'─'*55}")

    # Simulation state
    peak_price = entry_price
    trail_active = False
    trail_sl = sl_price
    max_gain = 0.0
    max_loss = 0.0

    for ts, bar in df.iterrows():
        low  = float(bar['low'])
        high = float(bar['high'])
        close = float(bar['close'])

        # Track peak for trailing
        if high > peak_price:
            peak_price = high

        gain_pct = (peak_price / entry_price - 1) * 100
        max_gain = max(max_gain, (high / entry_price - 1) * 100)
        max_loss = min(max_loss, (low / entry_price - 1) * 100)

        # Activate trailing stop
        if trail_pct and tp_price:
            tp_gain = (tp_price / entry_price - 1) * 100
            if gain_pct >= tp_gain * (trail_lock / 100):
                trail_active = True

        if trail_active and trail_pct:
            trail_sl = peak_price * (1 - trail_pct / 100)
            trail_sl = max(trail_sl, sl_price)  # never below hard SL

        active_sl = trail_sl if trail_active else sl_price

        minutes = int((ts - entry_dt).total_seconds() / 60)
        days = minutes / 390  # ~390 trading minutes/day

        # Check SL hit (bar low crosses SL)
        if low <= active_sl:
            exit_price = active_sl
            pnl = (exit_price / entry_price - 1) * 100
            outcome = 'TRAIL_STOP' if trail_active else 'SL_HIT'
            result = {
                'outcome': outcome,
                'exit_price': round(exit_price, 4),
                'exit_datetime': ts.strftime('%Y-%m-%d %H:%M'),
                'minutes_to_exit': minutes,
                'days_to_exit': round(days, 2),
                'pnl_pct': round(pnl, 3),
                'max_gain_pct': round(max_gain, 3),
                'max_loss_pct': round(max_loss, 3),
            }
            if verbose:
                _print_result(result, entry_price, active_sl, tp_price, trail_active)
            return result

        # Check TP hit (bar high crosses TP)
        if tp_price and high >= tp_price:
            exit_price = tp_price
            pnl = (exit_price / entry_price - 1) * 100
            result = {
                'outcome': 'TP_HIT',
                'exit_price': round(exit_price, 4),
                'exit_datetime': ts.strftime('%Y-%m-%d %H:%M'),
                'minutes_to_exit': minutes,
                'days_to_exit': round(days, 2),
                'pnl_pct': round(pnl, 3),
                'max_gain_pct': round(max_gain, 3),
                'max_loss_pct': round(max_loss, 3),
            }
            if verbose:
                _print_result(result, entry_price, active_sl, tp_price, False)
            return result

    # Reached end of bars
    last_close = float(df['close'].iloc[-1])
    last_ts = df.index[-1]
    minutes = int((last_ts - entry_dt).total_seconds() / 60)
    days = minutes / 390
    pnl = (last_close / entry_price - 1) * 100
    result = {
        'outcome': 'MAX_HOLD',
        'exit_price': round(last_close, 4),
        'exit_datetime': last_ts.strftime('%Y-%m-%d %H:%M'),
        'minutes_to_exit': minutes,
        'days_to_exit': round(days, 2),
        'pnl_pct': round(pnl, 3),
        'max_gain_pct': round(max_gain, 3),
        'max_loss_pct': round(max_loss, 3),
    }
    if verbose:
        _print_result(result, entry_price, trail_sl if trail_active else sl_price, tp_price, trail_active)
    return result


def _print_result(r: dict, entry: float, sl: float, tp: float | None, trail: bool):
    emoji = {'SL_HIT': '🔴', 'TP_HIT': '🟢', 'TRAIL_STOP': '🔒',
             'MAX_HOLD': '⏰', 'STILL_OPEN': '⏳', 'NO_DATA': '❓'}.get(r['outcome'], '?')
    print(f"\n  {emoji} {r['outcome']}")
    print(f"  Exit:      ${r['exit_price']:.2f}  ({r['pnl_pct']:+.2f}%)")
    print(f"  Time:      {r['exit_datetime']} ET")
    if r['days_to_exit'] < 1:
        print(f"             → {r['minutes_to_exit']} minutes after entry")
    else:
        print(f"             → {r['days_to_exit']:.1f} trading days after entry")
    print(f"  Peak:      +{r['max_gain_pct']:.2f}%  |  Trough: {r['max_loss_pct']:.2f}%")
    print(f"{'─'*55}")


def main():
    parser = argparse.ArgumentParser(description='Simulate a single trade using 1m bars')
    parser.add_argument('symbol', help='Stock symbol (e.g. NVDA)')
    parser.add_argument('date', help='Entry date YYYY-MM-DD')
    parser.add_argument('entry_price', type=float, nargs='?', default=None,
                        help='Entry price (optional if --from-trades)')
    parser.add_argument('--sl', type=float, default=3.0, help='Stop loss %% (default: 3.0)')
    parser.add_argument('--tp', type=float, default=None, help='Take profit %% (default: none)')
    parser.add_argument('--trail-pct', type=float, default=None,
                        help='Trailing stop %% (e.g. 2.0)')
    parser.add_argument('--trail-lock', type=float, default=80.0,
                        help='%% of TP gain to activate trailing (default: 80)')
    parser.add_argument('--max-days', type=int, default=5,
                        help='Max hold days (default: 5)')
    parser.add_argument('--entry-time', default='09:32',
                        help='Entry time ET HH:MM (default: 09:32)')
    parser.add_argument('--from-trades', action='store_true',
                        help='Look up entry price from trades table')
    args = parser.parse_args()

    symbol = args.symbol.upper()
    entry_price = args.entry_price

    # Look up from trades if requested
    if args.from_trades or entry_price is None:
        conn = None  # via get_session()
        row = conn.execute("""
            SELECT price, date FROM trades
            WHERE symbol = ? AND action = 'BUY'
            AND date >= date(?, '-3 days') AND date <= date(?, '+1 day')
            ORDER BY ABS(julianday(date) - julianday(?))
            LIMIT 1
        """, (symbol, args.date, args.date, args.date)).fetchone()
        conn.close()
        if row:
            entry_price = float(row[0])
            print(f"  Found trade: {symbol} BUY @ ${entry_price} on {row[1]}")
        else:
            print(f"  No trade found for {symbol} near {args.date}")
            sys.exit(1)

    if entry_price is None:
        print("Error: provide entry_price or use --from-trades")
        sys.exit(1)

    simulate(
        symbol=symbol,
        entry_date=args.date,
        entry_price=entry_price,
        sl_pct=args.sl,
        tp_pct=args.tp,
        trail_pct=args.trail_pct,
        trail_lock=args.trail_lock,
        max_days=args.max_days,
        entry_time=args.entry_time,
    )


if __name__ == '__main__':
    main()
