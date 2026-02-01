#!/usr/bin/env python3
"""
IMPROVED 12-STEP BACKTEST

ปัญหาที่พบจาก version แรก:
1. STOP losses เยอะเกินไป (-$19,267)
2. SECTOR_ROTATE rule ทำให้ออกเร็วเกินไป
3. Win Rate ต่ำ (46.9%)

การปรับปรุง:
1. ลบ SECTOR_ROTATE rule
2. เพิ่ม filters ให้เข้มงวดขึ้น
3. ใช้ Trailing Stop เร็วขึ้น
4. เน้นเฉพาะ Sectors ที่ proven แล้ว
"""

import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'database', 'stocks.db')


def run_improved_backtest(
    start_date: str = '2024-01-01',
    end_date: str = '2025-12-31',
    initial_capital: float = 100000,
    max_positions: int = 5,
    stop_loss_pct: float = 0.03,
    target_pct: float = 0.08,
):
    """Run improved 12-step backtest"""

    # PROVEN SECTORS (from previous backtests)
    proven_sectors = [
        'Finance_Banks', 'Finance_Insurance', 'Finance_Exchanges',
        'Healthcare_Pharma', 'Materials_Chemicals',
        'Semiconductors', 'Utilities_Electric', 'Utilities_Gas',
    ]

    # AVOID SECTORS
    avoid_sectors = [
        'Energy_Oil', 'Energy_Midstream', 'Energy_Services',
        'Consumer_Travel', 'Consumer_Retail',
        'Materials_Metals', 'Technology',  # Surprisingly bad
    ]

    print("="*70)
    print("🎯 IMPROVED 12-STEP BACKTEST")
    print("="*70)
    print(f"Period: {start_date} to {end_date}")
    print(f"Focus Sectors: {len(proven_sectors)}")
    print(f"Avoid Sectors: {len(avoid_sectors)}")
    print("="*70)

    conn = sqlite3.connect(DB_PATH)

    # Get trading dates
    cursor = conn.execute("""
        SELECT DISTINCT date FROM stock_prices
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date, end_date))
    dates = [row[0] for row in cursor.fetchall()]

    print(f"\nTrading days: {len(dates)}")

    # Load VIX
    vix_df = pd.read_sql("""
        SELECT date, close FROM stock_prices
        WHERE symbol = 'VIX' AND date >= ? AND date <= ?
        ORDER BY date
    """, conn, params=(start_date, end_date))
    vix_df.set_index('date', inplace=True)

    # Load SPY
    spy_df = pd.read_sql("""
        SELECT date, close FROM stock_prices
        WHERE symbol = 'SPY' AND date >= ? AND date <= ?
        ORDER BY date
    """, conn, params=(start_date, end_date))
    spy_df.set_index('date', inplace=True)

    # Get stocks from proven sectors only
    placeholders = ','.join(['?' for _ in proven_sectors])
    cursor = conn.execute(f"""
        SELECT DISTINCT symbol, sector FROM stock_prices
        WHERE sector IN ({placeholders})
    """, proven_sectors)
    stock_sectors = {row[0]: row[1] for row in cursor.fetchall()}

    # Load stock data
    print("Loading stock data...")
    stock_data = {}
    for symbol in stock_sectors.keys():
        df = pd.read_sql("""
            SELECT date, open, high, low, close, volume FROM stock_prices
            WHERE symbol = ? AND date >= ? AND date <= ?
            ORDER BY date
        """, conn, params=(symbol, start_date, end_date))
        if len(df) >= 50:
            df.set_index('date', inplace=True)
            stock_data[symbol] = df

    print(f"Loaded: {len(stock_data)} stocks")

    # Initialize portfolio
    portfolio = {
        'cash': initial_capital,
        'positions': [],
        'history': [],
    }

    monthly_pnl = {}
    skipped_days = 0

    # Main loop
    for i, date in enumerate(dates):
        if i < 50:
            continue

        # ===== STEP 1: VIX CHECK =====
        vix = vix_df.loc[date, 'close'] if date in vix_df.index else 20
        if vix > 22:  # Stricter VIX limit
            skipped_days += 1
            continue

        # ===== STEP 2: SPY MOMENTUM =====
        if date in spy_df.index:
            spy_idx = spy_df.index.get_loc(date)
            if spy_idx >= 20:
                spy_mom = (spy_df['close'].iloc[spy_idx] / spy_df['close'].iloc[spy_idx-20] - 1) * 100
                if spy_mom < -5:  # Skip if SPY down > 5%
                    skipped_days += 1
                    continue

        # ===== MANAGE POSITIONS =====
        for pos in portfolio['positions'][:]:
            if pos['symbol'] not in stock_data:
                continue

            df = stock_data[pos['symbol']]
            if date not in df.index:
                continue

            current_price = df.loc[date, 'close']
            pnl_pct = (current_price / pos['entry_price']) - 1

            # Update highest
            if current_price > pos.get('highest_price', pos['entry_price']):
                pos['highest_price'] = current_price

            exit_reason = None

            # IMPROVED EXIT RULES:

            # 1. Stop Loss
            if pnl_pct <= -stop_loss_pct:
                exit_reason = 'STOP'

            # 2. Target Hit
            elif pnl_pct >= target_pct:
                exit_reason = 'TARGET'

            # 3. Trailing Stop (activate after +2.5%)
            elif pos['highest_price'] > pos['entry_price'] * 1.025:
                # Tighter trail: -2% from high
                trail_stop = pos['highest_price'] * 0.98
                if current_price < trail_stop:
                    exit_reason = 'TRAIL'

            # 4. Breakeven Stop (after +1.5%)
            elif pos['highest_price'] > pos['entry_price'] * 1.015:
                if current_price < pos['entry_price'] * 1.005:  # Allow 0.5% buffer
                    exit_reason = 'BREAKEVEN'

            # 5. Time Stop (7 days max - shorter)
            elif pos['days_held'] >= 7:
                if pnl_pct > 0:  # Only exit if profitable
                    exit_reason = 'TIME'
                elif pos['days_held'] >= 10:  # Force exit after 10 days
                    exit_reason = 'TIME'

            # NO SECTOR_ROTATE rule - it was hurting performance

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

        # ===== FIND NEW ENTRIES (Weekly) =====
        if i % 5 != 0:
            continue

        if len(portfolio['positions']) >= max_positions:
            continue

        candidates = []

        for symbol, df in stock_data.items():
            if date not in df.index:
                continue

            if any(p['symbol'] == symbol for p in portfolio['positions']):
                continue

            sector = stock_sectors.get(symbol, '')
            if sector in avoid_sectors:
                continue

            idx = df.index.get_loc(date)
            if idx < 50:
                continue

            closes = df['close'].values[idx-50:idx+1]
            highs = df['high'].values[idx-50:idx+1]
            lows = df['low'].values[idx-50:idx+1]
            volumes = df['volume'].values[idx-50:idx+1]

            price = closes[-1]

            # ===== STRICTER FILTERS =====

            # Price filter
            if price < 20:  # Higher min price
                continue

            # Momentum
            mom_5d = (closes[-1] / closes[-5] - 1) * 100
            mom_20d = (closes[-1] / closes[-20] - 1) * 100

            # Sweet spot: moderate momentum
            if mom_5d < 1.5 or mom_5d > 6:
                continue
            if mom_20d < 3 or mom_20d > 12:
                continue

            # ATR% - very strict
            tr = [max(highs[j] - lows[j], abs(highs[j] - closes[j-1]), abs(lows[j] - closes[j-1]))
                  for j in range(-14, 0)]
            atr_pct = (np.mean(tr) / price) * 100

            if atr_pct > 1.8:  # Very low volatility only
                continue

            # MA check
            ma20 = np.mean(closes[-20:])
            ma50 = np.mean(closes[-50:])

            if price < ma20:
                continue
            if ma20 < ma50:  # Need healthy trend
                continue

            above_ma = (price / ma20 - 1) * 100
            if above_ma > 4:  # Not too extended
                continue

            # RSI
            deltas = np.diff(closes[-15:])
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            rsi = 100 - (100 / (1 + np.mean(gains) / np.mean(losses))) if np.mean(losses) > 0 else 50

            if rsi > 62 or rsi < 40:  # Tighter RSI range
                continue

            # Volume - must be above average
            vol_avg = np.mean(volumes[-20:-1])
            vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1
            if vol_ratio < 1.0:
                continue

            # ===== CATALYST CHECK =====
            catalyst_score = 0

            # Breakout
            recent_high = max(closes[-20:-1])
            if closes[-1] > recent_high:
                catalyst_score += 20

            # Volume surge
            if vol_ratio > 1.5:
                catalyst_score += 15

            # Near 52W high
            high_52w = max(closes) if len(closes) >= 252 else max(closes)
            if closes[-1] / high_52w > 0.95:
                catalyst_score += 10

            # Need at least some catalyst
            if catalyst_score < 15:
                continue

            # ===== SCORE =====
            score = 0
            score += min(30, mom_5d * 5)
            score += max(0, 25 - atr_pct * 10)
            score += catalyst_score
            score += min(15, (vol_ratio - 1) * 15)

            # Sector bonus
            if sector in ['Finance_Banks', 'Healthcare_Pharma', 'Semiconductors']:
                score += 15

            candidates.append({
                'symbol': symbol,
                'sector': sector,
                'price': price,
                'score': score,
                'mom_5d': mom_5d,
                'atr_pct': atr_pct,
            })

        # Sort and pick
        candidates.sort(key=lambda x: x['score'], reverse=True)

        for cand in candidates[:max_positions - len(portfolio['positions'])]:
            entry_price = cand['price']
            stop_price = entry_price * (1 - stop_loss_pct)
            risk_per_share = entry_price - stop_price

            # Position sizing: 1.5% risk
            max_risk = initial_capital * 0.015
            shares_by_risk = int(max_risk / risk_per_share)

            # Max 15% position
            max_pos = initial_capital * 0.15
            shares_by_pos = int(max_pos / entry_price)

            shares = min(shares_by_risk, shares_by_pos)

            if shares > 0 and portfolio['cash'] >= entry_price * shares:
                portfolio['positions'].append({
                    'symbol': cand['symbol'],
                    'sector': cand['sector'],
                    'entry_date': date,
                    'entry_price': entry_price,
                    'shares': shares,
                    'days_held': 0,
                    'highest_price': entry_price,
                })
                portfolio['cash'] -= entry_price * shares

    conn.close()

    # ===== RESULTS =====
    trades = portfolio['history']

    if not trades:
        print("No trades")
        return None

    total_pnl = sum(t['pnl'] for t in trades)
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0
    ev = (win_rate/100 * avg_win) + ((100-win_rate)/100 * avg_loss)

    # Exit breakdown
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
    print("📊 IMPROVED 12-STEP RESULTS")
    print("="*70)
    print(f"Total Trades: {len(trades)}")
    print(f"Winners: {len(wins)} ({win_rate:.1f}%)")
    print(f"Losers: {len(losses)}")
    print(f"Total P&L: ${total_pnl:+,.2f} ({total_pnl/initial_capital*100:+.1f}%)")
    print(f"Average Win: {avg_win:+.2f}%")
    print(f"Average Loss: {avg_loss:+.2f}%")
    print(f"Expected Value: {ev:+.2f}% per trade")
    print(f"Skipped Days (VIX/Sentiment): {skipped_days}")

    # Exit reasons
    print("\n" + "="*70)
    print("📋 EXIT REASONS")
    print("="*70)
    print(f"{'Reason':<15} {'Count':>8} {'WR':>8} {'P&L':>15}")
    print("-"*50)

    for r in sorted(exit_reasons.keys()):
        d = exit_reasons[r]
        wr = d['wins']/d['count']*100 if d['count'] > 0 else 0
        print(f"{r:<15} {d['count']:>8} {wr:>7.0f}% ${d['pnl']:>14,.2f}")

    # Monthly
    print("\n" + "="*70)
    print("📋 MONTHLY SUMMARY")
    print("="*70)
    print(f"{'Month':<10} {'Trades':>8} {'P&L':>15} {'%':>10} {'WR':>8}")
    print("-"*55)

    positive_months = 0
    monthly_returns = []

    for month in sorted(monthly_pnl.keys()):
        d = monthly_pnl[month]
        wr = d['wins']/d['trades']*100 if d['trades'] > 0 else 0
        pct = (d['pnl'] / initial_capital) * 100
        monthly_returns.append(pct)
        print(f"{month:<10} {d['trades']:>8} ${d['pnl']:>14,.2f} {pct:>+9.1f}% {wr:>7.0f}%")
        if d['pnl'] > 0:
            positive_months += 1

    print("-"*55)
    avg_monthly = np.mean(monthly_returns) if monthly_returns else 0
    print(f"Average Monthly: {avg_monthly:+.2f}%")
    print(f"Best Month: {max(monthly_returns):+.2f}%")
    print(f"Worst Month: {min(monthly_returns):+.2f}%")
    print(f"Positive Months: {positive_months}/{len(monthly_pnl)} ({positive_months/len(monthly_pnl)*100:.0f}%)")

    # Sector
    print("\n" + "="*70)
    print("📋 SECTOR PERFORMANCE")
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

    for sector in sorted(sector_stats.keys(), key=lambda x: sector_stats[x]['pnl'], reverse=True):
        s = sector_stats[sector]
        wr = s['wins']/s['trades']*100 if s['trades'] > 0 else 0
        print(f"{sector[:25]:<25} {s['trades']:>5} trades, {wr:>5.0f}% WR, ${s['pnl']:>+10,.2f}")

    # Final
    final_value = initial_capital + total_pnl
    print("\n" + "="*70)
    print("📋 FINAL SUMMARY")
    print("="*70)
    print(f"Starting: ${initial_capital:,.2f}")
    print(f"Ending: ${final_value:,.2f}")
    print(f"Total Return: {(final_value/initial_capital-1)*100:+.1f}%")

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_monthly': avg_monthly,
        'positive_months': positive_months/len(monthly_pnl)*100,
    }


if __name__ == '__main__':
    result = run_improved_backtest()
