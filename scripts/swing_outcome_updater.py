"""
swing_outcome_updater — Compute outcomes for swing_filter picks.

Daily cron: 04:00 BKK (after EOD data ingestion)
  1. Find all swing_filter picks in scan_picks where outcome=NULL
  2. For each pick: check if TP hit, SL hit (n/a), or time stop reached
  3. Compute actual exit price + PnL
  4. Insert into pick_outcomes table

Cron entry:
  0 4 * * 2-6  python3 scripts/swing_outcome_updater.py >> logs/swing_outcome.log 2>&1
"""
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

DB_JOURNAL = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/scan_journal.db')
DB_TRADE = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')


def get_swing_picks_pending():
    """Find swing_filter picks that haven't had outcome computed yet.
    Uses existing pick_outcomes table schema (pick_id PK, no id col)."""
    con = sqlite3.connect(str(DB_JOURNAL))
    df = pd.read_sql("""
        SELECT p.id, p.scan_ts, p.scan_date, p.symbol, p.entry, p.tp_price,
               p.reason, p.ml_prob,
               o.pick_id as outcome_pid
        FROM scan_picks p
        LEFT JOIN pick_outcomes o ON o.pick_id = p.id
        WHERE p.strategy = 'swing_filter'
          AND o.pick_id IS NULL
    """, con)
    con.close()
    return df


def get_history(symbol, start_date, end_date):
    """Load daily OHLC for symbol between dates."""
    con = sqlite3.connect(str(DB_TRADE))
    df = pd.read_sql(
        f"SELECT date, open, high, low, close FROM stock_daily_ohlc "
        f"WHERE symbol = '{symbol}' AND date >= '{start_date}' AND date <= '{end_date}' "
        f"ORDER BY date",
        con
    )
    con.close()
    df['date'] = pd.to_datetime(df['date'])
    return df


def simulate_exit(pick_row, hist, tp_pct=2.0, time_stop_days=7):
    """Walk forward through bars, find exit.
    Returns: (exit_date, exit_price, pnl_pct, exit_reason)
    """
    entry_date = pd.to_datetime(pick_row['scan_date'])
    entry_price = pick_row['entry']
    tp_price = pick_row['tp_price'] if pick_row['tp_price'] else entry_price * (1 + tp_pct / 100)

    # Find bars after entry_date
    future = hist[hist['date'] > entry_date].head(time_stop_days)
    if len(future) == 0:
        return None, None, None, 'no_data'

    for _, bar in future.iterrows():
        # Check TP: high >= tp_price
        if bar['high'] >= tp_price:
            return bar['date'], tp_price, (tp_price / entry_price - 1) * 100, 'tp'

    # Time stop — exit at last close
    last = future.iloc[-1]
    return last['date'], last['close'], (last['close'] / entry_price - 1) * 100, 'time'


def update_outcomes():
    pending = get_swing_picks_pending()
    print(f"Pending swing picks: {len(pending)}")
    if len(pending) == 0:
        return

    con = sqlite3.connect(str(DB_JOURNAL))

    n_updated = 0
    n_skip_pending = 0
    for _, pick in pending.iterrows():
        entry_dt = pd.to_datetime(pick['scan_date'])
        days_since = (datetime.now().date() - entry_dt.date()).days
        if days_since < 1:
            n_skip_pending += 1
            continue

        end_date = (entry_dt + timedelta(days=14)).strftime('%Y-%m-%d')
        hist = get_history(pick['symbol'], pick['scan_date'], end_date)
        if len(hist) == 0:
            continue

        exit_date, exit_price, pnl_pct, exit_reason = simulate_exit(pick, hist)
        if exit_date is None:
            n_skip_pending += 1
            continue
        if exit_date.date() > datetime.now().date() and exit_reason != 'time':
            n_skip_pending += 1
            continue

        # Compute max_gain and max_drawdown across hold period
        max_gain = ((hist['high'].max() / pick['entry']) - 1) * 100
        max_dd = ((hist['low'].min() / pick['entry']) - 1) * 100
        reached_tp = 1 if exit_reason == 'tp' else 0
        hit_sl = 0  # swing_filter has no SL
        outcome_label = 1 if pnl_pct > 0 else 0

        con.execute("""
            INSERT INTO pick_outcomes (pick_id, symbol, exit_price, exit_reason,
                                       exit_ts, pnl_pct, reached_tp, hit_sl,
                                       max_gain_pct, max_drawdown_pct,
                                       outcome_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (int(pick['id']), pick['symbol'], exit_price, exit_reason,
              exit_date.strftime('%Y-%m-%d %H:%M:%S'), pnl_pct,
              reached_tp, hit_sl, max_gain, max_dd, outcome_label))
        n_updated += 1
        days_held = (exit_date.date() - entry_dt.date()).days
        print(f"  {pick['symbol']:6s} entry ${pick['entry']:.2f} → "
              f"exit ${exit_price:.2f} ({pnl_pct:+.2f}%) [{exit_reason}, {days_held}d]")

    con.commit()
    con.close()
    print(f"\n✅ Updated {n_updated} outcomes, {n_skip_pending} still pending")


if __name__ == '__main__':
    update_outcomes()
