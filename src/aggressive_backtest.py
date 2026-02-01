#!/usr/bin/env python3
"""
AGGRESSIVE BACKTEST - Maximum Monthly Returns

Strategy:
1. Focus ONLY on Finance_Banks (best sector)
2. Higher position size
3. Faster turnover
4. Tighter filters
"""

import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def run_aggressive_backtest(
    start_date: str = '2024-01-01',
    end_date: str = '2025-12-31',
    stop_loss: float = -0.03,
    target_profit: float = 0.05,
    max_hold: int = 7,
    max_positions: int = 8,
    position_pct: float = 0.15,  # 15% per position
):
    """Run aggressive backtest focused on banks"""

    # ONLY banks and financial services
    focus_sectors = ['Finance_Banks', 'Finance_Diversified', 'Finance_Insurance', 'Finance_Exchanges']

    print("="*70)
    print("AGGRESSIVE BACKTEST - Banks & Finance Focus")
    print("="*70)
    print(f"Period: {start_date} to {end_date}")
    print(f"Stop Loss: {stop_loss*100:.1f}%")
    print(f"Target: {target_profit*100:.1f}%")
    print(f"Max Hold: {max_hold} days")
    print(f"Max Positions: {max_positions}")
    print(f"Position Size: {position_pct*100:.0f}% of capital")
    print("="*70)

    db_path = os.path.join(DATA_DIR, 'database', 'stocks.db')
    conn = sqlite3.connect(db_path)

    # Get trading dates
    cursor = conn.execute("""
        SELECT DISTINCT date FROM stock_prices
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date, end_date))
    dates = [row[0] for row in cursor.fetchall()]

    # Get symbols from banks/finance
    cursor = conn.execute("""
        SELECT DISTINCT symbol, sector FROM stock_prices
        WHERE sector IN (?, ?, ?, ?)
    """, focus_sectors)
    symbol_sectors = {row[0]: row[1] for row in cursor.fetchall()}
    symbols = list(symbol_sectors.keys())

    print(f"\nTrading days: {len(dates)}")
    print(f"Bank/Finance symbols: {len(symbols)}")

    # Preload price data
    price_data = {}
    for symbol in symbols:
        df = pd.read_sql("""
            SELECT date, open, high, low, close, volume FROM stock_prices
            WHERE symbol = ? AND date >= ? AND date <= ?
            ORDER BY date
        """, conn, params=(symbol, start_date, end_date))
        if len(df) >= 30:
            df.set_index('date', inplace=True)
            price_data[symbol] = df

    print(f"Symbols with data: {len(price_data)}")

    # Initialize portfolio
    starting_capital = 100000
    portfolio = {
        'cash': starting_capital,
        'positions': [],
        'history': [],
    }

    monthly_pnl = {}

    # Backtest loop
    for i, date in enumerate(dates):
        if i < 30:
            continue

        # Calculate current portfolio value
        total_value = portfolio['cash']
        for pos in portfolio['positions']:
            if pos['symbol'] in price_data and date in price_data[pos['symbol']].index:
                total_value += price_data[pos['symbol']].loc[date, 'close'] * pos['shares']

        position_size = total_value * position_pct

        # Check existing positions
        for pos in portfolio['positions'][:]:
            if pos['symbol'] not in price_data:
                continue

            df = price_data[pos['symbol']]
            if date not in df.index:
                continue

            current_price = df.loc[date, 'close']
            pnl_pct = (current_price / pos['entry_price']) - 1

            exit_reason = None

            # Stop loss
            if pnl_pct <= stop_loss:
                exit_reason = 'STOP'

            # Target profit
            elif pnl_pct >= target_profit:
                exit_reason = 'TARGET'

            # Max hold
            elif pos['days_held'] >= max_hold:
                exit_reason = 'TIME'

            if exit_reason:
                pnl = (current_price - pos['entry_price']) * pos['shares']

                trade = {
                    'symbol': pos['symbol'],
                    'sector': pos['sector'],
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'entry_price': pos['entry_price'],
                    'exit_price': current_price,
                    'shares': pos['shares'],
                    'pnl': pnl,
                    'pnl_pct': pnl_pct * 100,
                    'exit_reason': exit_reason,
                    'days_held': pos['days_held'],
                }
                portfolio['history'].append(trade)
                portfolio['cash'] += current_price * pos['shares']
                portfolio['positions'].remove(pos)

                month = date[:7]
                if month not in monthly_pnl:
                    monthly_pnl[month] = {'pnl': 0, 'trades': 0, 'wins': 0, 'value': starting_capital}
                monthly_pnl[month]['pnl'] += pnl
                monthly_pnl[month]['trades'] += 1
                if pnl > 0:
                    monthly_pnl[month]['wins'] += 1
            else:
                pos['days_held'] += 1

        # Look for new entries (every 2 days for aggressive turnover)
        if len(portfolio['positions']) < max_positions and i % 2 == 0:
            candidates = []

            for symbol, df in price_data.items():
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

                if price < 15:  # Min price for banks
                    continue

                # Momentum
                mom_3d = (closes[-1] / closes[-3] - 1) * 100 if closes[-3] > 0 else 0
                mom_5d = (closes[-1] / closes[-5] - 1) * 100 if closes[-5] > 0 else 0

                # MA10 (shorter for faster signals)
                ma10 = np.mean(closes[-10:])
                above_ma = (price / ma10 - 1) * 100

                # ATR %
                tr = []
                for j in range(-10, 0):
                    tr.append(max(highs[j] - lows[j],
                                  abs(highs[j] - closes[j-1]),
                                  abs(lows[j] - closes[j-1])))
                atr_pct = (np.mean(tr) / price) * 100 if price > 0 else 0

                # RSI
                deltas = np.diff(closes[-15:])
                gains = np.where(deltas > 0, deltas, 0)
                losses = np.where(deltas < 0, -deltas, 0)
                avg_gain = np.mean(gains)
                avg_loss = np.mean(losses)
                rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100

                # Volume
                vol_avg = np.mean(volumes[-10:-1])
                vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

                # AGGRESSIVE FILTERS
                if atr_pct > 1.8:  # Very low volatility only
                    continue
                if rsi > 60:  # Not overbought
                    continue
                if above_ma < 0.5:  # Must be above MA10
                    continue
                if mom_3d < 1 or mom_3d > 6:  # Recent momentum
                    continue

                # Score
                score = 0
                score += min(40, mom_3d * 8)
                score += max(0, 30 - atr_pct * 15)
                score += min(20, vol_ratio * 10)

                candidates.append({
                    'symbol': symbol,
                    'sector': symbol_sectors.get(symbol, ''),
                    'price': price,
                    'score': score,
                    'mom_3d': mom_3d,
                    'atr_pct': atr_pct,
                })

            # Sort by score
            candidates.sort(key=lambda x: x['score'], reverse=True)

            for cand in candidates[:max_positions - len(portfolio['positions'])]:
                if portfolio['cash'] >= position_size:
                    shares = int(position_size / cand['price'])
                    if shares > 0:
                        portfolio['positions'].append({
                            'symbol': cand['symbol'],
                            'sector': cand['sector'],
                            'entry_date': date,
                            'entry_price': cand['price'],
                            'shares': shares,
                            'days_held': 0,
                        })
                        portfolio['cash'] -= cand['price'] * shares

    conn.close()

    # Calculate results
    trades = portfolio['history']

    if not trades:
        print("No trades executed")
        return None

    total_pnl = sum(t['pnl'] for t in trades)
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0
    ev = (win_rate/100 * avg_win) + ((100-win_rate)/100 * avg_loss)

    # Print results
    print("\n" + "="*70)
    print("AGGRESSIVE BACKTEST RESULTS")
    print("="*70)
    print(f"Total Trades: {len(trades)}")
    print(f"Winners: {len(wins)} ({win_rate:.1f}%)")
    print(f"Losers: {len(losses)}")
    print(f"Total P&L: ${total_pnl:+,.2f}")
    print(f"Average Win: {avg_win:+.2f}%")
    print(f"Average Loss: {avg_loss:+.2f}%")
    print(f"Expected Value: {ev:+.2f}% per trade")

    # Monthly breakdown
    print("\n" + "="*70)
    print("MONTHLY SUMMARY")
    print("="*70)
    print(f"{'Month':<10} {'Trades':>8} {'P&L':>15} {'Monthly %':>10} {'Win Rate':>10}")
    print("-"*60)

    cumulative_pnl = 0
    positive_months = 0
    monthly_returns = []

    for month in sorted(monthly_pnl.keys()):
        data = monthly_pnl[month]
        wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
        cumulative_pnl += data['pnl']
        # Monthly return based on starting capital
        pnl_pct = (data['pnl'] / starting_capital) * 100
        monthly_returns.append(pnl_pct)
        print(f"{month:<10} {data['trades']:>8} ${data['pnl']:>13,.2f} {pnl_pct:>+9.1f}% {wr:>9.0f}%")
        if data['pnl'] > 0:
            positive_months += 1

    print("-"*60)
    avg_monthly_pct = np.mean(monthly_returns) if monthly_returns else 0
    max_monthly = max(monthly_returns) if monthly_returns else 0
    min_monthly = min(monthly_returns) if monthly_returns else 0

    print(f"Average Monthly: {avg_monthly_pct:+.2f}%")
    print(f"Best Month: {max_monthly:+.2f}%")
    print(f"Worst Month: {min_monthly:+.2f}%")
    print(f"Positive Months: {positive_months}/{len(monthly_pnl)} ({positive_months/len(monthly_pnl)*100:.0f}%)")

    # Final summary
    final_value = starting_capital + total_pnl
    total_return = (final_value / starting_capital - 1) * 100

    print("\n" + "="*70)
    print("PORTFOLIO SUMMARY")
    print("="*70)
    print(f"Starting Capital: ${starting_capital:,.2f}")
    print(f"Ending Value: ${final_value:,.2f}")
    print(f"Total Return: {total_return:+.1f}%")
    print(f"Trades per Month: {len(trades) / len(monthly_pnl):.1f}")

    # Sector breakdown
    print("\n" + "="*70)
    print("SECTOR BREAKDOWN")
    print("="*70)

    sector_stats = {}
    for t in trades:
        s = t['sector']
        if s not in sector_stats:
            sector_stats[s] = {'trades': 0, 'wins': 0, 'pnl': 0}
        sector_stats[s]['trades'] += 1
        sector_stats[s]['pnl'] += t['pnl']
        if t['pnl'] > 0:
            sector_stats[s]['wins'] += 1

    for sector, stats in sorted(sector_stats.items(), key=lambda x: x[1]['pnl'], reverse=True):
        wr = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
        print(f"{sector:<25} {stats['trades']:>5} trades, {wr:>5.0f}% WR, ${stats['pnl']:>+10,.2f}")

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'ev': ev,
        'avg_monthly_pct': avg_monthly_pct,
        'positive_months_pct': positive_months/len(monthly_pnl)*100 if monthly_pnl else 0,
        'total_return': total_return,
        'best_month': max_monthly,
        'worst_month': min_monthly,
    }


def grid_search():
    """Grid search for optimal parameters"""
    print("="*70)
    print("GRID SEARCH - Finding Optimal Parameters")
    print("="*70)

    results = []

    for stop in [-0.02, -0.025, -0.03]:
        for target in [0.04, 0.05, 0.06]:
            for hold in [5, 7, 10]:
                for pos_pct in [0.12, 0.15, 0.20]:
                    print(f"\rTesting: SL={stop*100:.1f}%, T={target*100:.0f}%, H={hold}, P={pos_pct*100:.0f}%", end='')

                    result = run_aggressive_backtest(
                        stop_loss=stop,
                        target_profit=target,
                        max_hold=hold,
                        position_pct=pos_pct,
                    )

                    if result and result['trades'] >= 50:
                        results.append({
                            'stop': stop,
                            'target': target,
                            'hold': hold,
                            'pos_pct': pos_pct,
                            **result
                        })

    # Sort by average monthly return
    results.sort(key=lambda x: x['avg_monthly_pct'], reverse=True)

    print("\n\n" + "="*70)
    print("TOP 10 PARAMETER COMBINATIONS")
    print("="*70)
    print(f"{'SL':>5} {'Target':>7} {'Hold':>5} {'Pos%':>5} {'WR':>6} {'Avg/Mo':>8} {'Best':>7} {'Worst':>7}")
    print("-"*60)

    for r in results[:10]:
        print(f"{r['stop']*100:>4.0f}% {r['target']*100:>6.0f}% {r['hold']:>5} {r['pos_pct']*100:>4.0f}% {r['win_rate']:>5.0f}% {r['avg_monthly_pct']:>+7.2f}% {r['best_month']:>+6.1f}% {r['worst_month']:>+6.1f}%")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--grid':
        grid_search()
    else:
        result = run_aggressive_backtest()

        if result:
            print("\n" + "="*70)
            print("SUMMARY")
            print("="*70)
            print(f"Win Rate: {result['win_rate']:.1f}%")
            print(f"Expected Value: {result['ev']:+.2f}% per trade")
            print(f"Average Monthly: {result['avg_monthly_pct']:+.2f}%")
            print(f"Best Month: {result['best_month']:+.1f}%")
            print(f"Worst Month: {result['worst_month']:+.1f}%")
            print(f"Total Return: {result['total_return']:+.1f}%")
