#!/usr/bin/env python3
"""
Portfolio Simulation: v6.1 + Portfolio Management
เงินทุน 200,000 บาท, ซื้อตัวละ 50,000 บาท, ถือได้สูงสุด 4 ตัว
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from api.data_manager import DataManager

dm = DataManager()

# Configuration
INITIAL_CAPITAL = 200000  # บาท
POSITION_SIZE = 50000     # บาท per trade
MAX_POSITIONS = 4
HOLD_DAYS = 14
STOP_LOSS = -0.06  # -6%
NO_REPEAT_DAYS = 30  # ไม่ซื้อหุ้นตัวเดิมภายใน 30 วัน

STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD', 'ORCL',
    'CRM', 'ADBE', 'NOW', 'NFLX', 'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX',
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'BA', 'UPS', 'FDX',
]


def get_metrics(df, idx):
    """Calculate metrics at a specific index"""
    if idx < 50:
        return None

    close = df['close'].iloc[:idx+1]
    high = df['high'].iloc[:idx+1]
    price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 0.0001)))

    # MA20
    ma20 = close.rolling(20).mean().iloc[-1]
    above_ma20 = ((price - ma20) / ma20) * 100

    # Momentum
    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    # 52-week position
    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    # v6.1: Distance from 20d high
    high_20d = high.iloc[-20:].max()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100

    return {
        'rsi': rsi, 'above_ma20': above_ma20,
        'mom_3d': mom_3d, 'mom_20d': mom_20d, 'pos_52w': pos_52w,
        'dist_from_20d_high': dist_from_20d_high,
    }


def passes_v61(m):
    """v6.1 criteria"""
    if m is None:
        return False
    if m['above_ma20'] <= 0:
        return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85:
        return False
    if m['mom_20d'] < 8:
        return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8:
        return False
    if m['rsi'] >= 65:
        return False
    # v6.1: Pullback protection
    if m['dist_from_20d_high'] < -5:
        return False
    return True


def simulate_portfolio(data, start_date, end_date):
    """Simulate portfolio trading"""

    # Get all trading dates
    sample_df = list(data.values())[0]
    all_dates = pd.to_datetime(sample_df['date'])
    trading_dates = all_dates[(all_dates >= start_date) & (all_dates <= end_date)].sort_values()

    # Portfolio state
    capital = INITIAL_CAPITAL
    positions = []  # List of {sym, entry_date, entry_price, shares, position_value}
    trade_history = []
    recent_trades = {}  # sym -> last_exit_date (for no-repeat rule)

    monthly_pnl = {}

    for date in trading_dates:
        date_str = date.strftime('%Y-%m-%d')
        month_key = date.strftime('%Y-%m')

        if month_key not in monthly_pnl:
            monthly_pnl[month_key] = {'trades': 0, 'wins': 0, 'pnl': 0}

        # Check existing positions for exit
        positions_to_remove = []
        for i, pos in enumerate(positions):
            sym = pos['sym']
            if sym not in data:
                continue

            df = data[sym]
            df_dates = pd.to_datetime(df['date'])

            # Find current index
            mask = df_dates == date
            if not mask.any():
                continue
            idx = mask.idxmax()

            current_price = df.loc[idx, 'close']
            current_low = df.loc[idx, 'low']
            days_held = (date - pos['entry_date']).days

            # Check stop loss (intraday)
            pct_change = (current_low - pos['entry_price']) / pos['entry_price']
            hit_stop = pct_change <= STOP_LOSS

            # Check hold period
            should_exit = hit_stop or days_held >= HOLD_DAYS

            if should_exit:
                if hit_stop:
                    exit_price = pos['entry_price'] * (1 + STOP_LOSS)
                else:
                    exit_price = current_price

                pnl_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
                pnl_baht = pos['position_value'] * (pnl_pct / 100)

                capital += pos['position_value'] + pnl_baht

                trade_history.append({
                    'sym': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'days_held': days_held,
                    'pnl_pct': pnl_pct,
                    'pnl_baht': pnl_baht,
                    'stopped': hit_stop,
                })

                monthly_pnl[month_key]['trades'] += 1
                monthly_pnl[month_key]['pnl'] += pnl_baht
                if pnl_pct > 0:
                    monthly_pnl[month_key]['wins'] += 1

                recent_trades[sym] = date
                positions_to_remove.append(i)

        # Remove exited positions
        for i in sorted(positions_to_remove, reverse=True):
            positions.pop(i)

        # Look for new entries (if we have room)
        if len(positions) < MAX_POSITIONS and capital >= POSITION_SIZE:
            candidates = []

            for sym, df in data.items():
                # Skip if already in position
                if any(p['sym'] == sym for p in positions):
                    continue

                # Skip if traded recently (no-repeat rule)
                if sym in recent_trades:
                    days_since = (date - recent_trades[sym]).days
                    if days_since < NO_REPEAT_DAYS:
                        continue

                df_dates = pd.to_datetime(df['date'])
                mask = df_dates == date
                if not mask.any():
                    continue
                idx = mask.idxmax()

                # Check if passes v6.1
                m = get_metrics(df, idx)
                if passes_v61(m):
                    candidates.append({
                        'sym': sym,
                        'price': df.loc[idx, 'close'],
                        'mom_20d': m['mom_20d'],
                    })

            # Sort by mom_20d (strongest first)
            candidates.sort(key=lambda x: x['mom_20d'], reverse=True)

            # Buy top candidates
            for c in candidates:
                if len(positions) >= MAX_POSITIONS or capital < POSITION_SIZE:
                    break

                shares = POSITION_SIZE / c['price']
                positions.append({
                    'sym': c['sym'],
                    'entry_date': date,
                    'entry_price': c['price'],
                    'shares': shares,
                    'position_value': POSITION_SIZE,
                })
                capital -= POSITION_SIZE

    # Close remaining positions at end
    for pos in positions:
        sym = pos['sym']
        if sym not in data:
            continue
        df = data[sym]
        exit_price = df['close'].iloc[-1]
        pnl_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
        pnl_baht = pos['position_value'] * (pnl_pct / 100)

        trade_history.append({
            'sym': sym,
            'entry_date': pos['entry_date'],
            'exit_date': trading_dates.iloc[-1],
            'entry_price': pos['entry_price'],
            'exit_price': exit_price,
            'days_held': (trading_dates.iloc[-1] - pos['entry_date']).days,
            'pnl_pct': pnl_pct,
            'pnl_baht': pnl_baht,
            'stopped': False,
        })

        month_key = trading_dates.iloc[-1].strftime('%Y-%m')
        if month_key in monthly_pnl:
            monthly_pnl[month_key]['trades'] += 1
            monthly_pnl[month_key]['pnl'] += pnl_baht
            if pnl_pct > 0:
                monthly_pnl[month_key]['wins'] += 1

        capital += pos['position_value'] + pnl_baht

    return {
        'trade_history': trade_history,
        'monthly_pnl': monthly_pnl,
        'final_capital': capital,
    }


# Load data
print("Loading data...")
data = {}
for s in STOCKS:
    try:
        df = dm.get_price_data(s, period="2y", interval="1d")
        if df is not None and len(df) >= 280:
            data[s] = df
    except:
        pass

print(f"Loaded {len(data)} stocks\n")

# Run simulation (last 6 months)
sample_df = list(data.values())[0]
all_dates = pd.to_datetime(sample_df['date'])
end_date = all_dates.iloc[-1]
start_date = end_date - timedelta(days=180)

print("="*70)
print(f"PORTFOLIO SIMULATION: v6.1 + Portfolio Management")
print("="*70)
print(f"""
Configuration:
  - Initial Capital: {INITIAL_CAPITAL:,} บาท
  - Position Size: {POSITION_SIZE:,} บาท per trade
  - Max Positions: {MAX_POSITIONS}
  - Hold Period: {HOLD_DAYS} days
  - Stop Loss: {STOP_LOSS*100:.0f}%
  - No Repeat: {NO_REPEAT_DAYS} days

Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}
""")

result = simulate_portfolio(data, start_date, end_date)

# Results
trades = result['trade_history']
df_trades = pd.DataFrame(trades) if trades else pd.DataFrame()

print("="*70)
print("MONTHLY PERFORMANCE")
print("="*70)

print(f"\n{'Month':<10} {'Trades':>8} {'Wins':>8} {'Win%':>8} {'P&L':>15}")
print("-"*55)

total_trades = 0
total_wins = 0
total_pnl = 0

for month, stats in sorted(result['monthly_pnl'].items()):
    if stats['trades'] > 0:
        win_rate = stats['wins'] / stats['trades'] * 100
        pnl_str = f"{stats['pnl']:+,.0f} บาท"
        print(f"{month:<10} {stats['trades']:>8} {stats['wins']:>8} {win_rate:>7.1f}% {pnl_str:>15}")
        total_trades += stats['trades']
        total_wins += stats['wins']
        total_pnl += stats['pnl']

print("-"*55)
if total_trades > 0:
    overall_win_rate = total_wins / total_trades * 100
    print(f"{'TOTAL':<10} {total_trades:>8} {total_wins:>8} {overall_win_rate:>7.1f}% {total_pnl:+,.0f} บาท")

# Trade details
print("\n" + "="*70)
print("TRADE DETAILS")
print("="*70)

if len(df_trades) > 0:
    winners = df_trades[df_trades['pnl_pct'] > 0]
    losers = df_trades[df_trades['pnl_pct'] <= 0]
    stopped = df_trades[df_trades['stopped']]

    print(f"""
Trade Statistics:
  - Total Trades: {len(df_trades)}
  - Winners: {len(winners)} ({len(winners)/len(df_trades)*100:.1f}%)
  - Losers: {len(losers)} ({len(losers)/len(df_trades)*100:.1f}%)
  - Stop Losses Hit: {len(stopped)}
  - Avg Days Held: {df_trades['days_held'].mean():.1f}
  - Avg Win: {winners['pnl_pct'].mean():+.2f}% ({winners['pnl_baht'].mean():+,.0f} บาท)
  - Avg Loss: {losers['pnl_pct'].mean():+.2f}% ({losers['pnl_baht'].mean():+,.0f} บาท) (if any losers)
""") if len(losers) > 0 else print(f"""
Trade Statistics:
  - Total Trades: {len(df_trades)}
  - Winners: {len(winners)} ({len(winners)/len(df_trades)*100:.1f}%)
  - Losers: {len(losers)} ({len(losers)/len(df_trades)*100:.1f}%)
  - Stop Losses Hit: {len(stopped)}
  - Avg Days Held: {df_trades['days_held'].mean():.1f}
  - Avg Win: {winners['pnl_pct'].mean():+.2f}% ({winners['pnl_baht'].mean():+,.0f} บาท)
""")

    print("\nRecent Trades:")
    print(f"{'Symbol':<8} {'Entry':<12} {'Exit':<12} {'Days':>5} {'P&L%':>8} {'P&L บาท':>12} {'Status':<10}")
    print("-"*75)

    for _, t in df_trades.tail(15).iterrows():
        status = "STOP" if t['stopped'] else ("WIN" if t['pnl_pct'] > 0 else "LOSS")
        print(f"{t['sym']:<8} {t['entry_date'].strftime('%Y-%m-%d'):<12} {t['exit_date'].strftime('%Y-%m-%d'):<12} {t['days_held']:>5} {t['pnl_pct']:>+7.1f}% {t['pnl_baht']:>+11,.0f} {status:<10}")

# Final Summary
print("\n" + "="*70)
print("FINAL SUMMARY")
print("="*70)

profit = result['final_capital'] - INITIAL_CAPITAL
roi = (profit / INITIAL_CAPITAL) * 100
monthly_roi = roi / 6  # 6 months

print(f"""
  เงินทุนเริ่มต้น:    {INITIAL_CAPITAL:>15,} บาท
  เงินทุนสุดท้าย:     {result['final_capital']:>15,.0f} บาท
  ─────────────────────────────────────
  กำไร/ขาดทุน:       {profit:>+15,.0f} บาท
  ROI (6 เดือน):     {roi:>+14.1f}%
  ROI เฉลี่ย/เดือน:   {monthly_roi:>+14.1f}%

  Total Trades: {total_trades}
  Win Rate: {overall_win_rate:.1f}%
""")

# Check if DDOG was traded
if len(df_trades) > 0:
    ddog_trades = df_trades[df_trades['sym'] == 'DDOG']
    if len(ddog_trades) > 0:
        print("\nDDOG Trades (with v6.1 pullback protection):")
        for _, t in ddog_trades.iterrows():
            status = "STOP" if t['stopped'] else ("WIN" if t['pnl_pct'] > 0 else "LOSS")
            print(f"  {t['entry_date'].strftime('%Y-%m-%d')} → {t['exit_date'].strftime('%Y-%m-%d')}: {t['pnl_pct']:+.1f}% [{status}]")
    else:
        print("\nDDOG: ไม่มี trade (อาจถูกกรองออกโดย v6.1 pullback protection)")
