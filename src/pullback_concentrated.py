#!/usr/bin/env python3
"""
CONCENTRATED PULLBACK SYSTEM - เป้าหมาย 10-15%+ ต่อเดือน

Strategy: FEWER but BETTER trades with LARGER positions

Key changes:
1. Higher catalyst threshold (quality > quantity)
2. Larger positions (up to 35% each)
3. Max 4 positions (concentrated)
4. Only BEST sectors
5. Tighter pullback entry
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


def run_concentrated(
    start_date: str = '2024-01-01',
    end_date: str = '2025-12-31',
    initial_capital: float = 100000,
    verbose: bool = True,
):
    """Concentrated High-Conviction Pullback System"""

    if verbose:
        print("="*70)
        print("💎 CONCENTRATED PULLBACK SYSTEM - HIGH CONVICTION ONLY")
        print("="*70)
        print("Strategy: FEWER trades, LARGER positions, BEST setups")
        print("="*70)

    conn = sqlite3.connect(DB_PATH)

    # Dates
    cursor = conn.execute("""
        SELECT DISTINCT date FROM stock_prices
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date, end_date))
    dates = [row[0] for row in cursor.fetchall()]

    # ONLY TOP 3 sectors (highest WR historically)
    sectors = [
        'Finance_Banks',       # 91% WR
        'Semiconductors',      # Good momentum
        'Healthcare_Pharma',   # Consistent
    ]

    placeholders = ','.join(['?' for _ in sectors])
    cursor = conn.execute(f"""
        SELECT DISTINCT symbol, sector FROM stock_prices
        WHERE sector IN ({placeholders})
    """, sectors)
    stocks = {row[0]: row[1] for row in cursor.fetchall()}

    # Load data
    if verbose:
        print(f"Loading from {len(sectors)} best sectors...")

    stock_data = {}
    for symbol in stocks:
        df = pd.read_sql("""
            SELECT date, open, high, low, close, volume FROM stock_prices
            WHERE symbol = ? AND date >= ? AND date <= ?
            ORDER BY date
        """, conn, params=(symbol, start_date, end_date))
        if len(df) >= 40:
            df.set_index('date', inplace=True)
            stock_data[symbol] = df

    if verbose:
        print(f"Loaded: {len(stock_data)} stocks")

    # Watchlist
    watchlist = {}

    # Portfolio
    portfolio = {'cash': initial_capital, 'positions': [], 'history': []}

    # Monthly tracking
    monthly_data = {}
    current_month = None

    # CONCENTRATED Parameters
    stop_loss = 0.023     # Tight stop (good entry)
    target1 = 0.055       # First target
    target2 = 0.095       # Second target
    target3 = 0.145       # Third target
    max_positions = 4     # CONCENTRATED
    position_pct = 0.30   # LARGER positions
    strong_position_pct = 0.35  # Very large for best setups

    for i, date in enumerate(dates):
        if i < 40:
            continue

        # Track monthly capital
        month = date[:7]
        if month != current_month:
            current_month = month
            total_value = portfolio['cash']
            for pos in portfolio['positions']:
                if pos['symbol'] in stock_data and date in stock_data[pos['symbol']].index:
                    total_value += stock_data[pos['symbol']].loc[date, 'close'] * pos['shares']
            monthly_data[month] = {'start_capital': total_value, 'pnl': 0, 'trades': 0, 'wins': 0}

        # Current total value
        total_value = portfolio['cash']
        for pos in portfolio['positions']:
            if pos['symbol'] in stock_data and date in stock_data[pos['symbol']].index:
                total_value += stock_data[pos['symbol']].loc[date, 'close'] * pos['shares']

        # ===== MANAGE POSITIONS =====
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
            exit_shares = pos['shares']

            if pnl_pct <= -stop_loss:
                exit_reason = 'STOP'
            elif pnl_pct >= target1 and not pos.get('t1'):
                exit_reason = 'T1'
                exit_shares = int(pos['shares'] * 0.28)  # Take less, let it run
                pos['t1'] = True
                pos['stop_price'] = pos['entry_price'] * 1.005
            elif pnl_pct >= target2 and not pos.get('t2'):
                exit_reason = 'T2'
                exit_shares = int(pos['shares'] * 0.40)
                pos['t2'] = True
            elif pnl_pct >= target3:
                exit_reason = 'T3'
            elif pos.get('t1') and pos['highest'] > pos['entry_price'] * 1.07:
                if price < pos['highest'] * 0.96:
                    exit_reason = 'TRAIL'
            elif pos.get('t1'):
                if price < pos.get('stop_price', pos['entry_price']):
                    exit_reason = 'BREAKEVEN'
            elif pos['days'] >= 10 and pnl_pct < 0.012:
                exit_reason = 'TIME'
            elif pos['days'] >= 15:
                exit_reason = 'TIME'

            if exit_reason:
                if exit_shares == 0:
                    exit_shares = pos['shares']

                pnl = (price - pos['entry_price']) * exit_shares

                portfolio['history'].append({
                    'symbol': pos['symbol'],
                    'sector': pos['sector'],
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'entry_price': pos['entry_price'],
                    'exit_price': price,
                    'shares': exit_shares,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct * 100,
                    'exit_reason': exit_reason,
                    'days': pos['days'],
                })

                portfolio['cash'] += price * exit_shares
                pos['shares'] -= exit_shares

                if pos['shares'] <= 0:
                    portfolio['positions'].remove(pos)

                if month in monthly_data:
                    monthly_data[month]['pnl'] += pnl
                    monthly_data[month]['trades'] += 1
                    if pnl > 0:
                        monthly_data[month]['wins'] += 1
            else:
                pos['days'] += 1

        # ===== SCAN FOR HIGH-CONVICTION CATALYSTS =====
        for symbol, df in stock_data.items():
            if date not in df.index:
                continue
            if symbol in watchlist:
                continue
            if any(p['symbol'] == symbol for p in portfolio['positions']):
                continue

            idx = df.index.get_loc(date)
            if idx < 40:
                continue

            closes = df['close'].values[idx-40:idx+1]
            highs = df['high'].values[idx-40:idx+1]
            lows = df['low'].values[idx-40:idx+1]
            volumes = df['volume'].values[idx-40:idx+1]

            price = closes[-1]
            if price < 25:  # Quality stocks only
                continue

            catalyst_score = 0

            # STRICT volume check
            vol_avg = np.mean(volumes[-20:-1])
            vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

            if vol_ratio < 2.2:  # Higher threshold
                continue

            if vol_ratio > 5:
                catalyst_score += 45
            elif vol_ratio > 4:
                catalyst_score += 38
            elif vol_ratio > 3:
                catalyst_score += 30
            elif vol_ratio > 2.2:
                catalyst_score += 22

            # Breakout check
            recent_high = max(closes[-20:-1])
            if closes[-1] > recent_high * 1.03:
                catalyst_score += 35
            elif closes[-1] > recent_high * 1.015:
                catalyst_score += 25
            elif closes[-1] > recent_high:
                catalyst_score += 12

            # Strong momentum
            mom_1d = (closes[-1] / closes[-2] - 1) * 100
            if mom_1d > 6:
                catalyst_score += 30
            elif mom_1d > 4:
                catalyst_score += 22
            elif mom_1d > 2.5:
                catalyst_score += 12

            # HIGH CONVICTION GATE
            if catalyst_score < 55:  # Higher threshold
                continue

            # RSI not overbought
            deltas = np.diff(closes[-15:])
            neg_mean = np.mean(np.maximum(-deltas, 0))
            rsi = 100 - 100/(1 + np.mean(np.maximum(deltas, 0))/neg_mean) if neg_mean > 0 else 50

            if rsi > 74:  # Stricter
                continue

            # ATR check - not too volatile
            tr = [max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1])) for j in range(-14, 0)]
            atr = np.mean(tr)
            atr_pct = atr / price * 100

            if atr_pct > 3.5:  # Not too volatile
                continue

            ma10 = np.mean(closes[-10:])
            pullback_target = max(ma10, price - atr * 1.2)  # Tighter entry

            watchlist[symbol] = {
                'catalyst_date': date,
                'catalyst_price': price,
                'pullback_target': pullback_target,
                'catalyst_score': catalyst_score,
                'sector': stocks.get(symbol, ''),
                'vol_ratio': vol_ratio,
                'expires': i + 5,  # Short window
            }

        # ===== CHECK WATCHLIST FOR PULLBACK ENTRY =====
        if len(portfolio['positions']) >= max_positions:
            continue

        symbols_to_remove = []
        sorted_watchlist = sorted(watchlist.items(), key=lambda x: x[1]['catalyst_score'], reverse=True)

        for symbol, watch in sorted_watchlist:
            if len(portfolio['positions']) >= max_positions:
                break

            if watch['expires'] < i:
                symbols_to_remove.append(symbol)
                continue

            if symbol not in stock_data:
                continue
            df = stock_data[symbol]
            if date not in df.index:
                continue

            price = df.loc[date, 'close']
            low_price = df.loc[date, 'low']

            if low_price <= watch['pullback_target'] * 1.005:  # Tighter entry
                entry_price = min(price, watch['pullback_target'])

                if price < watch['catalyst_price'] * 0.90:  # Not dropped too much
                    symbols_to_remove.append(symbol)
                    continue

                # Large positions for high conviction
                if watch['catalyst_score'] >= 70:
                    pos_pct = strong_position_pct
                elif watch['catalyst_score'] >= 60:
                    pos_pct = position_pct
                else:
                    pos_pct = position_pct * 0.9

                pos_value = total_value * pos_pct
                shares = int(pos_value / entry_price)

                if shares > 0 and portfolio['cash'] >= entry_price * shares:
                    portfolio['positions'].append({
                        'symbol': symbol,
                        'sector': watch['sector'],
                        'entry_date': date,
                        'entry_price': entry_price,
                        'shares': shares,
                        'days': 0,
                        'highest': entry_price,
                        'catalyst_score': watch['catalyst_score'],
                    })
                    portfolio['cash'] -= entry_price * shares
                    symbols_to_remove.append(symbol)

        for s in symbols_to_remove:
            if s in watchlist:
                del watchlist[s]

    conn.close()

    # ===== RESULTS =====
    trades = portfolio['history']
    if not trades:
        if verbose:
            print("No trades")
        return None

    total_pnl = sum(t['pnl'] for t in trades)
    wins = [t for t in trades if t['pnl'] > 0]
    win_rate = len(wins) / len(trades) * 100
    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_pct'] for t in trades if t['pnl'] <= 0]) if len(trades) > len(wins) else 0

    if verbose:
        print("\n" + "="*70)
        print("🏆 CONCENTRATED RESULTS")
        print("="*70)
        print(f"Trades: {len(trades)}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Total P&L: ${total_pnl:+,.2f} ({total_pnl/initial_capital*100:+.1f}%)")
        print(f"Avg Win: {avg_win:+.2f}%")
        print(f"Avg Loss: {avg_loss:+.2f}%")

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

        print("\n📋 EXIT BREAKDOWN:")
        for r, d in sorted(exits.items(), key=lambda x: x[1]['pnl'], reverse=True):
            wr = d['w']/d['n']*100 if d['n'] > 0 else 0
            print(f"  {r:<12} {d['n']:>4} trades, {wr:>5.0f}% WR, ${d['pnl']:>+12,.2f}")

        # Monthly
        print("\n📋 MONTHLY PERFORMANCE:")
        positive = 0
        returns = []
        target_months = 0
        big_months = 0

        for m in sorted(monthly_data.keys()):
            d = monthly_data[m]
            if d['start_capital'] > 0 and d['trades'] > 0:
                pct = d['pnl'] / d['start_capital'] * 100
                returns.append(pct)
                wr = d['wins']/d['trades']*100 if d['trades'] > 0 else 0

                if pct >= 15:
                    emoji = "🔥"
                    big_months += 1
                elif pct >= 10:
                    emoji = "🎯"
                elif pct > 0:
                    emoji = "✅"
                else:
                    emoji = "❌"

                print(f"  {emoji} {m} | {d['trades']:>3} trades | ${d['start_capital']:>10,.0f} | P&L: ${d['pnl']:>+10,.0f} ({pct:>+6.1f}%) | {wr:>4.0f}% WR")

                if d['pnl'] > 0:
                    positive += 1
                if pct >= 10:
                    target_months += 1

        avg_monthly = np.mean(returns) if returns else 0
        median_monthly = np.median(returns) if returns else 0

        print(f"\n  📊 Avg Monthly: {avg_monthly:+.2f}%")
        print(f"  📊 Median Monthly: {median_monthly:+.2f}%")
        print(f"  📈 Best: {max(returns):+.2f}%")
        print(f"  📉 Worst: {min(returns):+.2f}%")
        print(f"  ✅ Positive: {positive}/{len(returns)} ({positive/len(returns)*100:.0f}%)")
        print(f"  🎯 >= 10%: {target_months}/{len(returns)} ({target_months/len(returns)*100:.0f}%)")
        print(f"  🔥 >= 15%: {big_months}/{len(returns)} ({big_months/len(returns)*100:.0f}%)")

        final_value = initial_capital + total_pnl
        print(f"\n🏆 FINAL: ${initial_capital:,.0f} → ${final_value:,.0f} ({(final_value/initial_capital-1)*100:+.1f}%)")

        print("\n" + "="*70)
        if avg_monthly >= 10:
            print(f"  ✅ TARGET ACHIEVED! Avg {avg_monthly:.1f}% >= 10% target")
        elif avg_monthly >= 8:
            print(f"  ⚡ CLOSE! Avg {avg_monthly:.1f}% (target: 10%)")
        else:
            print(f"  ⚠️ Below target. Avg {avg_monthly:.1f}%")

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_monthly': avg_monthly,
        'median_monthly': median_monthly,
    }


if __name__ == '__main__':
    run_concentrated()
