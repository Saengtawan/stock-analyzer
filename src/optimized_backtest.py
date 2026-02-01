#!/usr/bin/env python3
"""
OPTIMIZED BACKTEST - เน้น Sector ที่ชนะ

Based on analysis:
- Finance_Banks: Best sector (53% WR)
- Avoid: Energy, Technology (low WR)
- Optimal: ATR < 2%, Momentum 2-8%
"""

import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def run_optimized_backtest(
    start_date: str = '2024-01-01',
    end_date: str = '2025-12-31',
    stop_loss: float = -0.03,
    target_profit: float = 0.06,
    max_positions: int = 5,
    position_size: float = 10000,
    focus_sectors: list = None,
    avoid_sectors: list = None,
):
    """Run optimized backtest focusing on winning sectors"""

    if focus_sectors is None:
        focus_sectors = [
            'Finance_Banks', 'Finance_Diversified', 'Finance_Insurance',
            'Healthcare_Pharma', 'Healthcare_MedDevices', 'Healthcare_Services',
            'Materials_Chemicals', 'Industrial_Machinery', 'Industrial_Transport',
            'Real_Estate_Healthcare', 'Utilities',
        ]

    if avoid_sectors is None:
        avoid_sectors = [
            'Energy_Oil', 'Energy_Midstream', 'Energy_Services',
            'Technology',  # Surprisingly underperforming
        ]

    print("="*70)
    print("OPTIMIZED BACKTEST - Focus on Winning Sectors")
    print("="*70)
    print(f"Period: {start_date} to {end_date}")
    print(f"Stop Loss: {stop_loss*100:.1f}%")
    print(f"Target: {target_profit*100:.1f}%")
    print(f"Max Positions: {max_positions}")
    print(f"Focus Sectors: {len(focus_sectors)}")
    print(f"Avoid Sectors: {len(avoid_sectors)}")
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

    print(f"\nTrading days: {len(dates)}")

    # Get symbols from focus sectors only
    cursor = conn.execute("""
        SELECT DISTINCT symbol, sector FROM stock_prices
        WHERE sector NOT LIKE '%_ETF' AND sector != 'INDICATOR'
    """)
    all_symbols = [(row[0], row[1]) for row in cursor.fetchall()]

    # Filter to focus sectors
    symbol_sectors = {}
    for symbol, sector in all_symbols:
        if any(f in sector for f in focus_sectors):
            if not any(a in sector for a in avoid_sectors):
                symbol_sectors[symbol] = sector

    symbols = list(symbol_sectors.keys())
    print(f"Focus universe: {len(symbols)} symbols")

    # Preload price data
    print("Loading price data...")
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
    portfolio = {
        'cash': 100000,
        'positions': [],
        'history': [],
    }

    monthly_pnl = {}
    starting_capital = 100000

    # Backtest loop
    for i, date in enumerate(dates):
        if i < 30:
            continue

        # Check existing positions - use trailing stop
        for pos in portfolio['positions'][:]:
            if pos['symbol'] not in price_data:
                continue

            df = price_data[pos['symbol']]
            if date not in df.index:
                continue

            current_price = df.loc[date, 'close']
            high_price = df.loc[date, 'high']
            pnl_pct = (current_price / pos['entry_price']) - 1

            # Update highest price
            if current_price > pos.get('highest_price', pos['entry_price']):
                pos['highest_price'] = current_price

            # Trailing stop: Lock in 50% of gains after +3%
            if pos['highest_price'] > pos['entry_price'] * 1.03:
                trailing_stop = pos['highest_price'] * 0.97
                if current_price < trailing_stop:
                    exit_reason = 'TRAIL'
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
                        monthly_pnl[month] = {'pnl': 0, 'trades': 0, 'wins': 0}
                    monthly_pnl[month]['pnl'] += pnl
                    monthly_pnl[month]['trades'] += 1
                    if pnl > 0:
                        monthly_pnl[month]['wins'] += 1
                    continue

            exit_reason = None

            # Check stop loss
            if pnl_pct <= stop_loss:
                exit_reason = 'STOP'

            # Check target
            elif pnl_pct >= target_profit:
                exit_reason = 'TARGET'

            # Check max hold (10 days for faster turnover)
            elif pos['days_held'] >= 10:
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
                    monthly_pnl[month] = {'pnl': 0, 'trades': 0, 'wins': 0}
                monthly_pnl[month]['pnl'] += pnl
                monthly_pnl[month]['trades'] += 1
                if pnl > 0:
                    monthly_pnl[month]['wins'] += 1
            else:
                pos['days_held'] += 1

        # Look for new entries (every 3 days for more opportunities)
        if len(portfolio['positions']) < max_positions and i % 3 == 0:
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

                # Skip penny stocks
                if price < 10:
                    continue

                # Momentum (5-day)
                mom_5d = (closes[-1] / closes[-5] - 1) * 100 if closes[-5] > 0 else 0

                # MA20
                ma20 = np.mean(closes[-20:])
                above_ma = (price / ma20 - 1) * 100

                # ATR %
                tr = []
                for j in range(-14, 0):
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

                # Volume ratio
                vol_avg = np.mean(volumes[-20:-1]) if len(volumes) >= 20 else 1
                vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

                # STRICTER FILTERS
                if atr_pct > 2.0:  # Tighter volatility
                    continue
                if rsi > 65 or rsi < 35:  # Avoid extremes
                    continue
                if above_ma < 1:  # Must be above MA20
                    continue
                if mom_5d < 2 or mom_5d > 8:  # Tighter momentum band
                    continue
                if vol_ratio < 1.0:  # Volume must be above average
                    continue

                # Score
                score = 0
                score += min(30, mom_5d * 5)
                score += max(0, 25 - atr_pct * 10)
                score += min(20, (vol_ratio - 1) * 15)

                # Sector bonus
                sector = symbol_sectors.get(symbol, '')
                if 'Bank' in sector:
                    score += 20
                elif 'Finance' in sector:
                    score += 15
                elif 'Healthcare' in sector or 'Pharma' in sector:
                    score += 15
                elif 'Utilities' in sector:
                    score += 10

                candidates.append({
                    'symbol': symbol,
                    'sector': sector,
                    'price': price,
                    'score': score,
                    'mom_5d': mom_5d,
                    'atr_pct': atr_pct,
                    'vol_ratio': vol_ratio,
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
                            'highest_price': cand['price'],
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

    # Expected value
    ev = (win_rate/100 * avg_win) + ((100-win_rate)/100 * avg_loss)

    # Print results
    print("\n" + "="*70)
    print("OPTIMIZED BACKTEST RESULTS")
    print("="*70)
    print(f"Total Trades: {len(trades)}")
    print(f"Winners: {len(wins)} ({win_rate:.1f}%)")
    print(f"Losers: {len(losses)}")
    print(f"Total P&L: ${total_pnl:+,.2f} ({total_pnl/starting_capital*100:+.1f}%)")
    print(f"Average Win: {avg_win:+.2f}%")
    print(f"Average Loss: {avg_loss:+.2f}%")
    print(f"Expected Value: {ev:+.2f}% per trade")

    # Exit reason breakdown
    exit_reasons = {}
    for t in trades:
        r = t['exit_reason']
        if r not in exit_reasons:
            exit_reasons[r] = {'count': 0, 'pnl': 0, 'wins': 0}
        exit_reasons[r]['count'] += 1
        exit_reasons[r]['pnl'] += t['pnl']
        if t['pnl'] > 0:
            exit_reasons[r]['wins'] += 1

    print("\n" + "="*70)
    print("EXIT REASON BREAKDOWN")
    print("="*70)
    print(f"{'Reason':<10} {'Count':>8} {'Win Rate':>10} {'P&L':>15}")
    print("-"*50)
    for reason in sorted(exit_reasons.keys()):
        data = exit_reasons[reason]
        wr = data['wins'] / data['count'] * 100 if data['count'] > 0 else 0
        print(f"{reason:<10} {data['count']:>8} {wr:>9.0f}% ${data['pnl']:>14,.2f}")

    # Monthly breakdown
    print("\n" + "="*70)
    print("MONTHLY SUMMARY")
    print("="*70)
    print(f"{'Month':<10} {'Trades':>8} {'P&L':>15} {'Monthly %':>10} {'Win Rate':>10}")
    print("-"*60)

    positive_months = 0
    for month in sorted(monthly_pnl.keys()):
        data = monthly_pnl[month]
        wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
        pnl_pct = (data['pnl'] / starting_capital) * 100
        print(f"{month:<10} {data['trades']:>8} ${data['pnl']:>13,.2f} {pnl_pct:>+9.1f}% {wr:>9.0f}%")
        if data['pnl'] > 0:
            positive_months += 1

    print("-"*60)
    avg_monthly = sum(d['pnl'] for d in monthly_pnl.values()) / len(monthly_pnl) if monthly_pnl else 0
    avg_monthly_pct = (avg_monthly / starting_capital) * 100
    print(f"Average Monthly: ${avg_monthly:+,.2f} ({avg_monthly_pct:+.2f}%)")
    print(f"Positive Months: {positive_months}/{len(monthly_pnl)} ({positive_months/len(monthly_pnl)*100:.0f}%)")

    # Final portfolio value
    final_value = starting_capital + total_pnl
    total_return = (final_value / starting_capital - 1) * 100
    annualized = total_return / 2  # ~2 years of data

    print("\n" + "="*70)
    print("PORTFOLIO SUMMARY")
    print("="*70)
    print(f"Starting Capital: ${starting_capital:,.2f}")
    print(f"Ending Value: ${final_value:,.2f}")
    print(f"Total Return: {total_return:+.1f}%")
    print(f"Annualized Return: {annualized:+.1f}%")

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expected_value': ev,
        'monthly': monthly_pnl,
        'positive_months_pct': positive_months/len(monthly_pnl)*100 if monthly_pnl else 0,
        'avg_monthly_pct': avg_monthly_pct,
        'total_return': total_return,
    }


def run_parameter_optimization():
    """Test different parameters to find optimal settings"""
    print("\n" + "="*70)
    print("PARAMETER OPTIMIZATION")
    print("="*70)

    results = []

    # Test different stop loss / target combinations
    for stop in [-0.02, -0.03, -0.04]:
        for target in [0.04, 0.06, 0.08]:
            for max_hold in [7, 10, 14]:
                print(f"\nTesting: Stop={stop*100:.0f}%, Target={target*100:.0f}%, MaxHold={max_hold}")

                # Minimal version of backtest
                result = run_optimized_backtest(
                    stop_loss=stop,
                    target_profit=target,
                )

                if result:
                    results.append({
                        'stop': stop,
                        'target': target,
                        'win_rate': result['win_rate'],
                        'avg_monthly': result['avg_monthly_pct'],
                        'total_return': result['total_return'],
                    })

    # Sort by avg monthly return
    results.sort(key=lambda x: x['avg_monthly'], reverse=True)

    print("\n" + "="*70)
    print("TOP PARAMETER COMBINATIONS")
    print("="*70)
    print(f"{'Stop':>6} {'Target':>8} {'WR':>8} {'Monthly':>10} {'Total':>10}")
    print("-"*50)

    for r in results[:10]:
        print(f"{r['stop']*100:>5.0f}% {r['target']*100:>7.0f}% {r['win_rate']:>7.0f}% {r['avg_monthly']:>+9.2f}% {r['total_return']:>+9.1f}%")


if __name__ == '__main__':
    result = run_optimized_backtest()

    if result:
        print("\n" + "="*70)
        print("KEY METRICS")
        print("="*70)
        print(f"Win Rate: {result['win_rate']:.1f}%")
        print(f"Expected Value: {result['expected_value']:+.2f}% per trade")
        print(f"Average Monthly Return: {result['avg_monthly_pct']:+.2f}%")
        print(f"Positive Months: {result['positive_months_pct']:.0f}%")
        print(f"Total Return (2 years): {result['total_return']:+.1f}%")
