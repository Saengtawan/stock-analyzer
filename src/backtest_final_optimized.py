#!/usr/bin/env python3
"""
FINAL OPTIMIZED BACKTEST

Lessons learned:
1. Original 12-step: Too many STOP losses
2. Improved 12-step: Too few trades (filters too strict)

Final approach:
- Focus on PROVEN sectors only
- Moderate filters (not too strict)
- Quick trailing stop
- No VIX blocking (it was hurting more than helping)
"""

import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'database', 'stocks.db')


def run_final_optimized(
    start_date: str = '2024-01-01',
    end_date: str = '2025-12-31',
    initial_capital: float = 100000,
):
    """Run final optimized backtest"""

    # Only trade BEST sectors (from all analysis)
    best_sectors = [
        'Finance_Banks',      # Best overall
        'Finance_Insurance',  # Consistent
        'Healthcare_Pharma',  # High WR
        'Semiconductors',     # Good momentum
    ]

    print("="*70)
    print("🏆 FINAL OPTIMIZED BACKTEST")
    print("="*70)
    print(f"Period: {start_date} to {end_date}")
    print(f"Best Sectors: {', '.join(best_sectors)}")
    print("="*70)

    conn = sqlite3.connect(DB_PATH)

    # Get dates
    cursor = conn.execute("""
        SELECT DISTINCT date FROM stock_prices
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date, end_date))
    dates = [row[0] for row in cursor.fetchall()]

    # Get stocks
    placeholders = ','.join(['?' for _ in best_sectors])
    cursor = conn.execute(f"""
        SELECT DISTINCT symbol, sector FROM stock_prices
        WHERE sector IN ({placeholders})
    """, best_sectors)
    stocks = {row[0]: row[1] for row in cursor.fetchall()}

    # Load data
    print(f"Trading days: {len(dates)}")
    print("Loading data...")

    stock_data = {}
    for symbol in stocks:
        df = pd.read_sql("""
            SELECT date, close, high, low, volume FROM stock_prices
            WHERE symbol = ? AND date >= ? AND date <= ?
            ORDER BY date
        """, conn, params=(symbol, start_date, end_date))
        if len(df) >= 30:
            df.set_index('date', inplace=True)
            stock_data[symbol] = df

    print(f"Loaded: {len(stock_data)} stocks")

    # Portfolio
    portfolio = {'cash': initial_capital, 'positions': [], 'history': []}
    monthly_pnl = {}

    # Parameters
    stop_loss = 0.03
    target = 0.06
    max_positions = 6
    position_pct = 0.12

    for i, date in enumerate(dates):
        if i < 30:
            continue

        total_value = portfolio['cash']
        for pos in portfolio['positions']:
            if pos['symbol'] in stock_data and date in stock_data[pos['symbol']].index:
                total_value += stock_data[pos['symbol']].loc[date, 'close'] * pos['shares']

        # Manage positions
        for pos in portfolio['positions'][:]:
            if pos['symbol'] not in stock_data:
                continue
            df = stock_data[pos['symbol']]
            if date not in df.index:
                continue

            price = df.loc[date, 'close']
            pnl_pct = price / pos['entry_price'] - 1

            if price > pos.get('highest', pos['entry_price']):
                pos['highest'] = price

            exit_reason = None

            # Stop loss
            if pnl_pct <= -stop_loss:
                exit_reason = 'STOP'

            # Target
            elif pnl_pct >= target:
                exit_reason = 'TARGET'

            # Trailing stop after +2%
            elif pos['highest'] > pos['entry_price'] * 1.02:
                if price < pos['highest'] * 0.98:
                    exit_reason = 'TRAIL'

            # Time stop: 7 days if flat, 14 days max
            elif pos['days'] >= 7 and pnl_pct < 0.01:
                exit_reason = 'TIME'
            elif pos['days'] >= 14:
                exit_reason = 'TIME'

            if exit_reason:
                pnl = (price - pos['entry_price']) * pos['shares']
                portfolio['history'].append({
                    'symbol': pos['symbol'],
                    'sector': pos['sector'],
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'entry_price': pos['entry_price'],
                    'exit_price': price,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct * 100,
                    'exit_reason': exit_reason,
                    'days': pos['days'],
                })
                portfolio['cash'] += price * pos['shares']
                portfolio['positions'].remove(pos)

                month = date[:7]
                if month not in monthly_pnl:
                    monthly_pnl[month] = {'pnl': 0, 'trades': 0, 'wins': 0}
                monthly_pnl[month]['pnl'] += pnl
                monthly_pnl[month]['trades'] += 1
                if pnl > 0:
                    monthly_pnl[month]['wins'] += 1
            else:
                pos['days'] += 1

        # Find new entries (every 3 days)
        if i % 3 != 0:
            continue
        if len(portfolio['positions']) >= max_positions:
            continue

        candidates = []

        for symbol, df in stock_data.items():
            if date not in df.index:
                continue
            if any(p['symbol'] == symbol for p in portfolio['positions']):
                continue

            idx = df.index.get_loc(date)
            if idx < 30:
                continue

            closes = df['close'].values[idx-30:idx+1]
            highs = df['high'].values[idx-30:idx+1]
            lows = df['low'].values[idx-30:idx+1]
            volumes = df['volume'].values[idx-30:idx+1]

            price = closes[-1]
            if price < 15:
                continue

            # Momentum
            mom_5d = (closes[-1] / closes[-5] - 1) * 100
            mom_20d = (closes[-1] / closes[-20] - 1) * 100

            if mom_5d < 1 or mom_5d > 8:
                continue
            if mom_20d < 0:
                continue

            # ATR
            tr = [max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1])) for j in range(-14,0)]
            atr_pct = np.mean(tr) / price * 100
            if atr_pct > 2.2:
                continue

            # MA
            ma20 = np.mean(closes[-20:])
            if price < ma20:
                continue
            above_ma = (price / ma20 - 1) * 100
            if above_ma > 5:
                continue

            # RSI
            deltas = np.diff(closes[-15:])
            rsi = 100 - 100/(1 + np.mean(np.maximum(deltas,0))/np.mean(np.maximum(-deltas,0))) if np.mean(np.maximum(-deltas,0)) > 0 else 50
            if rsi > 65:
                continue

            # Volume
            vol_avg = np.mean(volumes[-20:-1])
            vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

            # Score
            score = mom_5d * 5 + (20 - atr_pct * 8) + (vol_ratio - 1) * 10
            if vol_ratio > 1.3:
                score += 10
            if closes[-1] > max(closes[-20:-1]):  # Breakout
                score += 15

            candidates.append({
                'symbol': symbol,
                'sector': stocks.get(symbol, ''),
                'price': price,
                'score': score,
                'atr_pct': atr_pct,
            })

        candidates.sort(key=lambda x: x['score'], reverse=True)

        for c in candidates[:max_positions - len(portfolio['positions'])]:
            pos_value = total_value * position_pct
            shares = int(pos_value / c['price'])

            if shares > 0 and portfolio['cash'] >= c['price'] * shares:
                portfolio['positions'].append({
                    'symbol': c['symbol'],
                    'sector': c['sector'],
                    'entry_date': date,
                    'entry_price': c['price'],
                    'shares': shares,
                    'days': 0,
                    'highest': c['price'],
                })
                portfolio['cash'] -= c['price'] * shares

    conn.close()

    # Results
    trades = portfolio['history']
    if not trades:
        print("No trades")
        return

    total_pnl = sum(t['pnl'] for t in trades)
    wins = [t for t in trades if t['pnl'] > 0]
    win_rate = len(wins) / len(trades) * 100
    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_pct'] for t in trades if t['pnl'] <= 0]) if len(trades) > len(wins) else 0

    # Exit breakdown
    exits = {}
    for t in trades:
        r = t['exit_reason']
        if r not in exits:
            exits[r] = {'n': 0, 'pnl': 0, 'w': 0}
        exits[r]['n'] += 1
        exits[r]['pnl'] += t['pnl']
        if t['pnl'] > 0:
            exits[r]['w'] += 1

    print("\n" + "="*70)
    print("🏆 FINAL RESULTS")
    print("="*70)
    print(f"Trades: {len(trades)}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Total P&L: ${total_pnl:+,.2f} ({total_pnl/initial_capital*100:+.1f}%)")
    print(f"Avg Win: {avg_win:+.2f}%")
    print(f"Avg Loss: {avg_loss:+.2f}%")

    print("\n📋 EXIT BREAKDOWN:")
    for r, d in sorted(exits.items(), key=lambda x: x[1]['pnl'], reverse=True):
        wr = d['w']/d['n']*100 if d['n'] > 0 else 0
        print(f"  {r:<10} {d['n']:>4} trades, {wr:>5.0f}% WR, ${d['pnl']:>+10,.2f}")

    print("\n📋 MONTHLY:")
    positive = 0
    returns = []
    for m in sorted(monthly_pnl.keys()):
        d = monthly_pnl[m]
        pct = d['pnl']/initial_capital*100
        returns.append(pct)
        wr = d['wins']/d['trades']*100 if d['trades'] > 0 else 0
        print(f"  {m} | {d['trades']:>3} trades | ${d['pnl']:>+10,.2f} ({pct:>+5.1f}%) | {wr:>4.0f}% WR")
        if d['pnl'] > 0:
            positive += 1

    print(f"\n  Avg Monthly: {np.mean(returns):+.2f}%")
    print(f"  Best: {max(returns):+.2f}%")
    print(f"  Worst: {min(returns):+.2f}%")
    print(f"  Positive: {positive}/{len(monthly_pnl)} ({positive/len(monthly_pnl)*100:.0f}%)")

    # Sector
    print("\n📋 BY SECTOR:")
    sectors = {}
    for t in trades:
        s = t['sector']
        if s not in sectors:
            sectors[s] = {'n': 0, 'pnl': 0, 'w': 0}
        sectors[s]['n'] += 1
        sectors[s]['pnl'] += t['pnl']
        if t['pnl'] > 0:
            sectors[s]['w'] += 1

    for s, d in sorted(sectors.items(), key=lambda x: x[1]['pnl'], reverse=True):
        wr = d['w']/d['n']*100
        print(f"  {s:<25} {d['n']:>4} trades, {wr:>5.0f}% WR, ${d['pnl']:>+10,.2f}")

    final_value = initial_capital + total_pnl
    print(f"\n🏆 FINAL: ${initial_capital:,.0f} → ${final_value:,.0f} ({(final_value/initial_capital-1)*100:+.1f}%)")


if __name__ == '__main__':
    run_final_optimized()
