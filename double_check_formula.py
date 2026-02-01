#!/usr/bin/env python3
"""
DOUBLE CHECK - ตรวจสอบซ้ำอีกครั้ง
เพราะตัวเลข +27%/month ดีเกินไป ต้องหาจุดผิดพลาด

ตรวจสอบ:
1. Stop-loss ทำงานถูกต้องหรือไม่
2. มี look-ahead bias หรือไม่
3. การคำนวณ return ถูกต้องหรือไม่
4. Realistic trading simulation
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')


def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100.0
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_accumulation(closes, volumes, period=20):
    if len(closes) < period:
        return 1.0
    up_vol, down_vol = 0.0, 0.0
    for i in range(-period+1, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        elif closes[i] < closes[i-1]:
            down_vol += volumes[i]
    return up_vol / down_vol if down_vol > 0 else 3.0


def calculate_atr_pct(closes, highs, lows, i, period=14):
    if i < period:
        return 5.0
    tr = []
    for j in range(i - period + 1, i + 1):
        if j > 0:
            tr.append(max(
                float(highs[j]) - float(lows[j]),
                abs(float(highs[j]) - float(closes[j-1])),
                abs(float(lows[j]) - float(closes[j-1]))
            ))
    atr = np.mean(tr) if tr else 0
    price = float(closes[i])
    return (atr / price) * 100 if price > 0 else 5.0


def main():
    print("=" * 80)
    print("DOUBLE CHECK - ตรวจสอบหาข้อผิดพลาด")
    print("=" * 80)

    CONFIG = {
        'accum_min': 1.2,
        'rsi_max': 58,
        'ma20_min': 0,
        'ma50_min': 0,
        'atr_max': 3.0,
        'hold_days': 5,
        'stop_pct': -2.0
    }

    # ใช้หุ้นน้อยลงเพื่อดูรายละเอียด
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA',
               'JPM', 'BAC', 'V', 'HD', 'CAT', 'XOM']

    print(f"\nDownloading {len(symbols)} stocks...")

    stock_data = {}
    for sym in symbols:
        try:
            df = yf.download(sym, period='1y', progress=False)
            if df.empty or len(df) < 100:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            stock_data[sym] = df
        except:
            pass

    print(f"Downloaded: {len(stock_data)} stocks")

    # ========== DETAILED TRADE LOG ==========
    print("\n" + "=" * 80)
    print("DETAILED TRADE LOG - ดูทุกเทรด")
    print("=" * 80)

    all_trades = []

    for sym, df in stock_data.items():
        closes = df['Close'].values.flatten()
        volumes = df['Volume'].values.flatten()
        highs = df['High'].values.flatten()
        lows = df['Low'].values.flatten()
        dates = df.index

        n = min(len(closes), len(volumes), len(highs), len(lows), len(dates))
        hold_days = CONFIG['hold_days']

        for i in range(55, n - hold_days - 1):
            price = float(closes[i])

            ma20 = float(np.mean(closes[i-19:i+1]))
            ma50 = float(np.mean(closes[i-49:i+1]))
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)
            atr_pct = calculate_atr_pct(closes, highs, lows, i, period=14)

            # Gates
            if accum <= CONFIG['accum_min']:
                continue
            if rsi >= CONFIG['rsi_max']:
                continue
            if above_ma20 <= CONFIG['ma20_min']:
                continue
            if above_ma50 <= CONFIG['ma50_min']:
                continue
            if atr_pct > CONFIG['atr_max']:
                continue

            # REALISTIC TRADE SIMULATION
            entry_price = price
            entry_date = dates[i]

            # Check stop-loss intraday using Low prices
            stop_price = entry_price * (1 + CONFIG['stop_pct'] / 100)
            stopped = False
            exit_price = None
            exit_date = None

            for j in range(1, hold_days + 1):
                if i + j >= n:
                    break

                # Use LOW price to check stop-loss (more realistic)
                day_low = float(lows[i + j])
                day_close = float(closes[i + j])

                if day_low <= stop_price:
                    # Stop-loss triggered - exit at stop price
                    exit_price = stop_price
                    exit_date = dates[i + j]
                    stopped = True
                    break

            if not stopped:
                exit_price = float(closes[i + hold_days])
                exit_date = dates[i + hold_days]

            pct_return = ((exit_price - entry_price) / entry_price) * 100

            all_trades.append({
                'symbol': sym,
                'entry_date': entry_date,
                'exit_date': exit_date,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'return': pct_return,
                'stopped': stopped
            })

    df_trades = pd.DataFrame(all_trades)

    # Deduplicate
    df_trades['week'] = df_trades['entry_date'].dt.isocalendar().week
    df_trades['year'] = df_trades['entry_date'].dt.year
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])
    df_trades = df_trades.sort_values('entry_date')

    print(f"\nTotal trades: {len(df_trades)}")

    # Show first 20 trades
    print("\nFirst 20 trades:")
    print(f"{'Symbol':<6} {'Entry Date':<12} {'Entry':>8} {'Exit':>8} {'Return':>8} {'Status':<8}")
    print("-" * 60)

    for _, t in df_trades.head(20).iterrows():
        entry_str = t['entry_date'].strftime('%Y-%m-%d')
        status = "STOP" if t['stopped'] else "OK"
        print(f"{t['symbol']:<6} {entry_str} ${t['entry_price']:>7.2f} ${t['exit_price']:>7.2f} {t['return']:>+7.2f}% {status}")

    # ========== STATISTICS ==========
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)

    n_trades = len(df_trades)
    n_winners = len(df_trades[df_trades['return'] > 0])
    n_losers = len(df_trades[df_trades['return'] <= 0])
    n_stopped = len(df_trades[df_trades['stopped'] == True])

    avg_winner = df_trades[df_trades['return'] > 0]['return'].mean()
    avg_loser = df_trades[df_trades['return'] <= 0]['return'].mean()
    avg_return = df_trades['return'].mean()
    total_return = df_trades['return'].sum()

    print(f"""
Trades: {n_trades}
Winners: {n_winners} ({n_winners/n_trades*100:.1f}%)
Losers: {n_losers} ({n_losers/n_trades*100:.1f}%)
Stopped: {n_stopped}

Average Winner: {avg_winner:+.2f}%
Average Loser: {avg_loser:+.2f}%
Average Return: {avg_return:+.2f}%

Total Return: {total_return:+.2f}%
Expected Monthly: {total_return/12:+.2f}%
""")

    # ========== CHECK FOR ISSUES ==========
    print("=" * 80)
    print("ISSUE CHECK")
    print("=" * 80)

    issues = []

    # Check 1: Stop-loss working?
    max_loss = df_trades['return'].min()
    if max_loss < CONFIG['stop_pct'] - 0.5:
        issues.append(f"❌ Max loss {max_loss:.2f}% exceeds stop-loss {CONFIG['stop_pct']}%")
    else:
        print(f"✅ Stop-loss working: Max loss = {max_loss:.2f}%")

    # Check 2: Are stopped trades really at stop price?
    stopped_trades = df_trades[df_trades['stopped'] == True]
    if len(stopped_trades) > 0:
        avg_stopped_return = stopped_trades['return'].mean()
        if abs(avg_stopped_return - CONFIG['stop_pct']) > 0.5:
            issues.append(f"❌ Stopped trades avg {avg_stopped_return:.2f}%, expected {CONFIG['stop_pct']}%")
        else:
            print(f"✅ Stopped trades correct: Avg = {avg_stopped_return:.2f}%")

    # Check 3: Unrealistic winners?
    big_winners = df_trades[df_trades['return'] > 20]
    if len(big_winners) > 0:
        print(f"⚠️ Found {len(big_winners)} trades with >20% return in 5 days:")
        for _, t in big_winners.iterrows():
            entry_str = t['entry_date'].strftime('%Y-%m-%d')
            print(f"   {t['symbol']} {entry_str}: {t['return']:+.2f}%")

    # Check 4: Return distribution
    print(f"\nReturn Distribution:")
    print(f"   Min: {df_trades['return'].min():.2f}%")
    print(f"   25%: {df_trades['return'].quantile(0.25):.2f}%")
    print(f"   50%: {df_trades['return'].quantile(0.50):.2f}%")
    print(f"   75%: {df_trades['return'].quantile(0.75):.2f}%")
    print(f"   Max: {df_trades['return'].max():.2f}%")

    # ========== MONTHLY BREAKDOWN ==========
    print("\n" + "=" * 80)
    print("MONTHLY BREAKDOWN")
    print("=" * 80)

    df_trades['month'] = df_trades['entry_date'].dt.to_period('M')
    monthly = df_trades.groupby('month').agg({
        'return': ['count', 'sum', 'mean'],
        'stopped': 'sum'
    }).round(2)
    monthly.columns = ['trades', 'total_return', 'avg_return', 'stopped']

    print(monthly)

    avg_monthly = monthly['total_return'].mean()
    print(f"\nAverage Monthly Return: {avg_monthly:+.2f}%")

    # ========== FINAL VERDICT ==========
    print("\n" + "=" * 80)
    print("FINAL VERDICT")
    print("=" * 80)

    if issues:
        print("\n❌ ISSUES FOUND:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("\n✅ No major issues found")

    if avg_monthly >= 10:
        print(f"\n✅ Formula achieves {avg_monthly:.1f}%/month (target: 10%)")
    else:
        print(f"\n⚠️ Formula achieves only {avg_monthly:.1f}%/month (below 10% target)")


if __name__ == '__main__':
    main()
