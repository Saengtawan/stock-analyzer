#!/usr/bin/env python3
"""
ทดสอบกลยุทธ์ที่ filter ตามปัจจัย

Filter:
1. Market: เทรดเฉพาะ SPY > MA20
2. Sector: เฉพาะ Industrial, Consumer, Finance
3. Month: หลีกเลี่ยง Oct, Nov
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
    print("FILTERED STRATEGY TEST")
    print("=" * 80)

    # Download SPY for market trend
    print("\n1. Download market data (SPY)...")
    spy = yf.download('SPY', period='1y', progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_ma20 = spy['Close'].rolling(20).mean()

    # Good sectors only
    SECTORS = {
        'Industrial': ['CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT'],
        'Consumer': ['HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE'],
        'Finance': ['JPM', 'BAC', 'GS', 'MS', 'V', 'MA', 'AXP'],
    }

    all_symbols = []
    symbol_sector = {}
    for sector, stocks in SECTORS.items():
        for sym in stocks:
            all_symbols.append(sym)
            symbol_sector[sym] = sector

    print(f"\n2. Download {len(all_symbols)} stocks from good sectors...")

    stock_data = {}
    for sym in all_symbols:
        try:
            df = yf.download(sym, period='1y', progress=False)
            if df.empty or len(df) < 100:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            stock_data[sym] = df
        except:
            pass

    print(f"   Downloaded: {len(stock_data)} stocks")

    # Config
    CONFIG = {
        'accum_min': 1.2,
        'rsi_max': 58,
        'ma20_min': 0,
        'ma50_min': 0,
        'atr_max': 3.0,
        'hold_days': 5,
        'stop_pct': -2.0
    }

    # Avoid months
    AVOID_MONTHS = [10, 11]  # Oct, Nov

    all_trades = []
    filtered_out = {'market': 0, 'month': 0}

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
            entry_date = dates[i]

            # Filter 1: Market trend
            try:
                spy_close = spy.loc[entry_date, 'Close']
                spy_ma = spy_ma20.loc[entry_date]
                if pd.isna(spy_ma) or spy_close < spy_ma:
                    filtered_out['market'] += 1
                    continue
            except:
                continue

            # Filter 2: Avoid bad months
            if entry_date.month in AVOID_MONTHS:
                filtered_out['month'] += 1
                continue

            # Technical gates
            ma20 = float(np.mean(closes[i-19:i+1]))
            ma50 = float(np.mean(closes[i-49:i+1]))
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)
            atr_pct = calculate_atr_pct(closes, highs, lows, i, period=14)

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

            # Trade with stop-loss
            entry_price = price
            stop_price = entry_price * (1 + CONFIG['stop_pct'] / 100)
            stopped = False

            for j in range(1, hold_days + 1):
                if i + j >= n:
                    break
                day_low = float(lows[i + j])
                if day_low <= stop_price:
                    pct_return = CONFIG['stop_pct']
                    stopped = True
                    break
            else:
                exit_price = float(closes[i + hold_days])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            all_trades.append({
                'symbol': sym,
                'sector': symbol_sector.get(sym, 'Other'),
                'date': entry_date,
                'return': pct_return,
                'stopped': stopped
            })

    df_trades = pd.DataFrame(all_trades)

    # Deduplicate
    df_trades['week'] = df_trades['date'].dt.isocalendar().week
    df_trades['year'] = df_trades['date'].dt.year
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

    print(f"\n3. Filters applied:")
    print(f"   - Filtered by market trend: {filtered_out['market']}")
    print(f"   - Filtered by month: {filtered_out['month']}")
    print(f"   - Final trades: {len(df_trades)}")

    # Results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    if len(df_trades) == 0:
        print("No trades after filtering")
        return

    total = len(df_trades)
    winners = len(df_trades[df_trades['return'] > 0])
    total_return = df_trades['return'].sum()
    avg_return = df_trades['return'].mean()

    # Monthly breakdown
    df_trades['month'] = df_trades['date'].dt.to_period('M')
    n_months = len(df_trades['month'].unique())
    monthly_avg = total_return / n_months if n_months > 0 else 0

    print(f"""
📊 สรุปผลลัพธ์:
   Trades: {total}
   Winners: {winners} ({winners/total*100:.1f}%)
   Total Return: {total_return:+.2f}%
   Monthly Average: {monthly_avg:+.2f}%
""")

    print("Monthly breakdown:")
    for month, group in df_trades.groupby('month'):
        n = len(group)
        w = len(group[group['return'] > 0])
        total_ret = group['return'].sum()
        status = "✅" if total_ret > 0 else "❌"
        print(f"   {status} {month}: {n:>2} trades, {w}W/{n-w}L, Total: {total_ret:>+7.2f}%")

    print("\nSector breakdown:")
    for sector in df_trades['sector'].unique():
        group = df_trades[df_trades['sector'] == sector]
        n = len(group)
        w = len(group[group['return'] > 0])
        total_ret = group['return'].sum()
        avg_ret = group['return'].mean()
        status = "✅" if avg_ret > 0 else "❌"
        print(f"   {status} {sector:<12}: {n:>2} trades, Avg: {avg_ret:>+.2f}%, Total: {total_ret:>+.2f}%")

    # Target check
    print("\n" + "=" * 80)
    print("TARGET CHECK")
    print("=" * 80)

    if monthly_avg >= 10:
        print(f"\n✅ TARGET MET! {monthly_avg:.2f}%/month >= 10%")
    elif monthly_avg >= 8:
        print(f"\n⭐ CLOSE! {monthly_avg:.2f}%/month (target: 10%)")
    else:
        print(f"\n❌ {monthly_avg:.2f}%/month < 10%")


if __name__ == '__main__':
    main()
