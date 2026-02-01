#!/usr/bin/env python3
"""
PULLBACK CATALYST SYSTEM - เป้าหมาย 10-15% ต่อเดือน

ปัญหา: STOP losses -$130K ทำลายทุกอย่าง

แก้ไข:
1. PULLBACK ENTRY - ไม่ซื้อตอน breakout, รอ pullback มาที่ support
2. STRONGER FILTERS - เลือกเฉพาะหุ้นที่มี setup ที่ดีมาก
3. BIGGER CATALYST - ต้องมี catalyst แรงมากเท่านั้น
4. TIGHTER STOP - แต่เข้าที่ราคาที่ดีกว่า

Key insight: ซื้อตอน pullback = risk ต่ำกว่า = stop hit น้อยกว่า
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


def run_pullback_system(
    start_date: str = '2024-01-01',
    end_date: str = '2025-12-31',
    initial_capital: float = 100000,
):
    """Pullback-based catalyst system"""

    print("="*70)
    print("🎯 PULLBACK CATALYST SYSTEM")
    print("="*70)
    print("Strategy: Wait for PULLBACK after CATALYST")
    print("="*70)

    conn = sqlite3.connect(DB_PATH)

    # Dates
    cursor = conn.execute("""
        SELECT DISTINCT date FROM stock_prices
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date, end_date))
    dates = [row[0] for row in cursor.fetchall()]

    # Best sectors only
    sectors = ['Finance_Banks', 'Healthcare_Pharma', 'Semiconductors']
    placeholders = ','.join(['?' for _ in sectors])
    cursor = conn.execute(f"""
        SELECT DISTINCT symbol, sector FROM stock_prices
        WHERE sector IN ({placeholders})
    """, sectors)
    stocks = {row[0]: row[1] for row in cursor.fetchall()}

    # Load data
    print(f"Loading {len(stocks)} stocks...")
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

    print(f"Loaded: {len(stock_data)} stocks")

    # Watchlist for pullback entry
    watchlist = {}  # symbol -> {catalyst_date, catalyst_type, trigger_price}

    # Portfolio
    portfolio = {'cash': initial_capital, 'positions': [], 'history': []}
    monthly_pnl = {}

    # Parameters
    stop_loss = 0.025  # -2.5% (tighter because better entry)
    target1 = 0.06     # +6%
    target2 = 0.10     # +10%
    target3 = 0.15     # +15%
    max_positions = 4
    position_pct = 0.25

    for i, date in enumerate(dates):
        if i < 40:
            continue

        # Total value
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

            # Stop loss
            if pnl_pct <= -stop_loss:
                exit_reason = 'STOP'

            # Target 1: Sell 33%
            elif pnl_pct >= target1 and not pos.get('t1'):
                exit_reason = 'T1'
                exit_shares = int(pos['shares'] * 0.33)
                pos['t1'] = True
                # Move stop to breakeven
                pos['stop_price'] = pos['entry_price'] * 1.005

            # Target 2: Sell another 33%
            elif pnl_pct >= target2 and not pos.get('t2'):
                exit_reason = 'T2'
                exit_shares = int(pos['shares'] * 0.5)  # 50% of remaining
                pos['t2'] = True

            # Target 3: Sell all
            elif pnl_pct >= target3:
                exit_reason = 'T3'

            # Trailing stop after T1
            elif pos.get('t1') and pos['highest'] > pos['entry_price'] * 1.08:
                if price < pos['highest'] * 0.97:
                    exit_reason = 'TRAIL'

            # Breakeven stop after T1
            elif pos.get('t1'):
                if price < pos.get('stop_price', pos['entry_price']):
                    exit_reason = 'BREAKEVEN'

            # Time stop
            elif pos['days'] >= 7 and pnl_pct < 0.02:
                exit_reason = 'TIME'
            elif pos['days'] >= 10:
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

                month = date[:7]
                if month not in monthly_pnl:
                    monthly_pnl[month] = {'pnl': 0, 'trades': 0, 'wins': 0}
                monthly_pnl[month]['pnl'] += pnl
                monthly_pnl[month]['trades'] += 1
                if pnl > 0:
                    monthly_pnl[month]['wins'] += 1
            else:
                pos['days'] += 1

        # ===== SCAN FOR CATALYSTS (Add to watchlist) =====
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
            if price < 25:
                continue

            # ===== DETECT STRONG CATALYST =====
            catalyst_score = 0

            # 1. Volume explosion (must have)
            vol_avg = np.mean(volumes[-20:-1])
            vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

            if vol_ratio < 2.0:  # Must have volume
                continue

            if vol_ratio > 4:
                catalyst_score += 40
            elif vol_ratio > 3:
                catalyst_score += 30
            else:
                catalyst_score += 20

            # 2. Breakout
            recent_high = max(closes[-20:-1])
            if closes[-1] > recent_high * 1.03:
                catalyst_score += 30

            # 3. Strong momentum
            mom_1d = (closes[-1] / closes[-2] - 1) * 100
            if mom_1d > 5:
                catalyst_score += 25
            elif mom_1d > 3:
                catalyst_score += 15

            # Need very strong catalyst
            if catalyst_score < 50:
                continue

            # RSI check - not too overbought
            deltas = np.diff(closes[-15:])
            rsi = 100 - 100/(1 + np.mean(np.maximum(deltas,0))/np.mean(np.maximum(-deltas,0))) if np.mean(np.maximum(-deltas,0)) > 0 else 50

            if rsi > 75:
                continue

            # ATR for pullback target
            tr = [max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1])) for j in range(-14, 0)]
            atr = np.mean(tr)

            # Add to watchlist - wait for pullback
            ma10 = np.mean(closes[-10:])
            pullback_target = max(ma10, price - atr * 1.5)  # Pullback to MA10 or 1.5 ATR

            watchlist[symbol] = {
                'catalyst_date': date,
                'catalyst_price': price,
                'pullback_target': pullback_target,
                'catalyst_score': catalyst_score,
                'sector': stocks.get(symbol, ''),
                'vol_ratio': vol_ratio,
                'expires': i + 5,  # Valid for 5 days
            }

        # ===== CHECK WATCHLIST FOR PULLBACK ENTRY =====
        if len(portfolio['positions']) >= max_positions:
            continue

        symbols_to_remove = []

        for symbol, watch in watchlist.items():
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

            # Check if pullback reached
            if low_price <= watch['pullback_target'] * 1.01:
                # PULLBACK ENTRY!
                entry_price = min(price, watch['pullback_target'])

                # Verify still strong
                if price < watch['catalyst_price'] * 0.90:  # Dropped too much
                    symbols_to_remove.append(symbol)
                    continue

                # Position sizing based on catalyst strength
                if watch['catalyst_score'] >= 70:
                    pos_mult = 1.0
                elif watch['catalyst_score'] >= 60:
                    pos_mult = 0.75
                else:
                    pos_mult = 0.5

                pos_value = total_value * position_pct * pos_mult
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
                        'catalyst_price': watch['catalyst_price'],
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
        print("No trades")
        return

    total_pnl = sum(t['pnl'] for t in trades)
    wins = [t for t in trades if t['pnl'] > 0]
    win_rate = len(wins) / len(trades) * 100
    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_pct'] for t in trades if t['pnl'] <= 0]) if len(trades) > len(wins) else 0

    print("\n" + "="*70)
    print("🏆 PULLBACK CATALYST RESULTS")
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

    for m in sorted(monthly_pnl.keys()):
        d = monthly_pnl[m]
        pct = d['pnl']/initial_capital*100
        returns.append(pct)
        wr = d['wins']/d['trades']*100 if d['trades'] > 0 else 0

        emoji = "🎯" if pct >= 10 else "✅" if pct > 0 else "❌"
        print(f"  {emoji} {m} | {d['trades']:>3} trades | ${d['pnl']:>+12,.2f} ({pct:>+7.1f}%) | {wr:>4.0f}% WR")

        if d['pnl'] > 0:
            positive += 1
        if pct >= 10:
            target_months += 1

    avg_monthly = np.mean(returns) if returns else 0
    print(f"\n  📊 Avg Monthly: {avg_monthly:+.2f}%")
    print(f"  📈 Best: {max(returns):+.2f}%")
    print(f"  📉 Worst: {min(returns):+.2f}%")
    print(f"  ✅ Positive: {positive}/{len(monthly_pnl)} ({positive/len(monthly_pnl)*100:.0f}%)")
    print(f"  🎯 Months >= 10%: {target_months}/{len(monthly_pnl)}")

    final_value = initial_capital + total_pnl
    print(f"\n🏆 FINAL: ${initial_capital:,.0f} → ${final_value:,.0f} ({(final_value/initial_capital-1)*100:+.1f}%)")

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_monthly': avg_monthly,
        'target_months': target_months,
    }


if __name__ == '__main__':
    run_pullback_system()
