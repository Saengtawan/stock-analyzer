"""
Trailing Stop Simulator — simulates entry/exit with trailing stops.
Part of Discovery v9.0 True Multi-Strategy System.
"""
import logging
import sqlite3
import numpy as np
from pathlib import Path
from discovery.strategies import StrategySpec, classify_stock, ALL_STRATEGIES

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


def simulate_trade(entry_price: float, daily_bars: list, strategy: StrategySpec) -> dict:
    """Simulate a single trade with trailing stop.

    Args:
        entry_price: entry price (D1 open)
        daily_bars: list of (high, low, close) for D1, D2, ... D5
        strategy: StrategySpec with exit rules

    Returns:
        dict with exit_price, exit_day, exit_reason, pnl_pct
    """
    if entry_price <= 0 or not daily_bars:
        return {'exit_price': entry_price, 'exit_day': 0, 'exit_reason': 'NO_DATA', 'pnl_pct': 0}

    max_high = entry_price
    trail_pct = strategy.trail_pct
    sl_pct = strategy.sl_pct
    sl_price = entry_price * (1 - sl_pct / 100)

    for day_idx, (high, low, close) in enumerate(daily_bars):
        day_num = day_idx + 1  # D1, D2, ...
        if high <= 0 or low <= 0:
            continue

        # Update max high
        if high > max_high:
            max_high = high

        # Check hard SL first (priority)
        if low <= sl_price:
            return {
                'exit_price': round(sl_price, 2),
                'exit_day': day_num,
                'exit_reason': 'SL',
                'pnl_pct': round(-sl_pct, 2),
            }

        # TP_OR_TIME: hit TP% → exit, otherwise hold to max_hold_days
        if strategy.exit_rule == 'TP_OR_TIME':
            tp_pct = 1.0  # 1% TP for momentum (data-validated WR=65%)
            tp_price = entry_price * (1 + tp_pct / 100)
            if high >= tp_price:
                return {
                    'exit_price': round(tp_price, 2),
                    'exit_day': day_num,
                    'exit_reason': 'TP',
                    'pnl_pct': round(tp_pct, 2),
                }

        # D1_CLOSE exit
        if strategy.exit_rule == 'D1_CLOSE' and day_num == 1:
            pnl = (close / entry_price - 1) * 100
            return {
                'exit_price': round(close, 2),
                'exit_day': 1,
                'exit_reason': 'D1_CLOSE',
                'pnl_pct': round(pnl, 2),
            }

        # Trailing stop check
        if strategy.exit_rule == 'TRAIL' and trail_pct > 0:
            trail_stop = max_high * (1 - trail_pct / 100)
            if low <= trail_stop:
                pnl = (trail_stop / entry_price - 1) * 100
                return {
                    'exit_price': round(trail_stop, 2),
                    'exit_day': day_num,
                    'exit_reason': 'TRAIL',
                    'pnl_pct': round(pnl, 2),
                }

        # Max hold days reached → exit at close
        if day_num >= strategy.max_hold_days:
            pnl = (close / entry_price - 1) * 100
            return {
                'exit_price': round(close, 2),
                'exit_day': day_num,
                'exit_reason': 'TIME',
                'pnl_pct': round(pnl, 2),
            }

    # Fallback: exit at last close
    last_close = daily_bars[-1][2] if daily_bars else entry_price
    pnl = (last_close / entry_price - 1) * 100
    return {
        'exit_price': round(last_close, 2),
        'exit_day': len(daily_bars),
        'exit_reason': 'TIME',
        'pnl_pct': round(pnl, 2),
    }


def backtest_strategy(strategy: StrategySpec, max_date: str = None) -> dict:
    """Backtest a strategy on historical data.

    Uses backfill_signal_outcomes + signal_daily_bars.
    """
    conn = sqlite3.connect(str(DB_PATH))
    try:
        date_filter = f"AND b.scan_date <= '{max_date}'" if max_date else ""
        rows = conn.execute(f"""
            SELECT b.scan_date, b.symbol, b.momentum_5d, b.distance_from_20d_high,
                   b.volume_ratio, b.atr_pct, b.vix_at_signal,
                   d1.open as d1o, d1.high as d1h, d1.low as d1l, d1.close as d1c,
                   d2.high as d2h, d2.low as d2l, d2.close as d2c,
                   d3.high as d3h, d3.low as d3l, d3.close as d3c,
                   d4.high as d4h, d4.low as d4l, d4.close as d4c,
                   d5.high as d5h, d5.low as d5l, d5.close as d5c
            FROM backfill_signal_outcomes b
            JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
            JOIN signal_daily_bars d2 ON b.scan_date=d2.scan_date AND b.symbol=d2.symbol AND d2.day_offset=2
            JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
            JOIN signal_daily_bars d4 ON b.scan_date=d4.scan_date AND b.symbol=d4.symbol AND d4.day_offset=4
            JOIN signal_daily_bars d5 ON b.scan_date=d5.scan_date AND b.symbol=d5.symbol AND d5.day_offset=5
            WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0 AND d1.open > 0
            {date_filter}
        """).fetchall()
    finally:
        conn.close()

    trades = []
    for r in rows:
        stock = {
            'momentum_5d': r[2] or 0,
            'distance_from_20d_high': r[3] or -5,
            'volume_ratio': r[4] or 1,
            'atr_pct': r[5] or 3,
        }
        if not strategy.matches(stock):
            continue

        entry = r[7]  # D1 open
        bars = [
            (r[8], r[9], r[10]),    # D1 HLC
            (r[11], r[12], r[13]),  # D2
            (r[14], r[15], r[16]),  # D3
            (r[17], r[18], r[19]),  # D4
            (r[20], r[21], r[22]),  # D5
        ]

        result = simulate_trade(entry, bars, strategy)
        result['scan_date'] = r[0]
        result['symbol'] = r[1]
        trades.append(result)

    if not trades:
        return {'n': 0, 'wr': 0, 'er': 0, 'strategy': strategy.name}

    pnls = np.array([t['pnl_pct'] for t in trades])
    exit_days = np.array([t['exit_day'] for t in trades])
    exit_reasons = [t['exit_reason'] for t in trades]

    return {
        'strategy': strategy.name,
        'n': len(trades),
        'wr': round(float(np.mean(pnls > 0)) * 100, 1),
        'er': round(float(pnls.mean()), 3),
        'median': round(float(np.median(pnls)), 3),
        'avg_hold': round(float(exit_days.mean()), 1),
        'max_dd': round(float(pnls.min()), 2),
        'best': round(float(pnls.max()), 2),
        'exit_breakdown': {
            reason: sum(1 for e in exit_reasons if e == reason)
            for reason in set(exit_reasons)
        },
    }
