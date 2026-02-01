#!/usr/bin/env python3
"""
OPTIMIZE FOR 10%/MONTH
หาพารามิเตอร์ที่ได้ 10%+ ต่อเดือนจริงๆ

แนวคิด:
1. Hold สั้นลง → เทรดบ่อยขึ้น → สะสมกำไรเร็วขึ้น
2. เพิ่มเงื่อนไขให้ winner มากขึ้น
3. หาสมดุลระหว่าง win rate และ frequency
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


def backtest(stock_data, config):
    """Backtest with proper stop-loss using Low prices"""
    all_trades = []

    for sym, df in stock_data.items():
        closes = df['Close'].values.flatten()
        volumes = df['Volume'].values.flatten()
        highs = df['High'].values.flatten()
        lows = df['Low'].values.flatten()
        dates = df.index

        n = min(len(closes), len(volumes), len(highs), len(lows), len(dates))
        hold_days = config['hold_days']

        for i in range(55, n - hold_days - 1):
            price = float(closes[i])

            ma20 = float(np.mean(closes[i-19:i+1]))
            ma50 = float(np.mean(closes[i-49:i+1]))
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)
            atr_pct = calculate_atr_pct(closes, highs, lows, i, period=14)

            vol_avg = float(np.mean(volumes[i-19:i]))
            vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1.0

            # 3-day momentum
            mom_3d = ((price - float(closes[i-3])) / float(closes[i-3])) * 100 if i >= 3 else 0

            # Gates
            if accum <= config['accum_min']:
                continue
            if rsi >= config['rsi_max']:
                continue
            if above_ma20 <= config['ma20_min']:
                continue
            if above_ma50 <= config['ma50_min']:
                continue
            if atr_pct > config['atr_max']:
                continue
            if vol_surge < config.get('vol_min', 0):
                continue
            if mom_3d <= config.get('mom_3d_min', -999):
                continue

            # Trade with realistic stop-loss
            entry_price = price
            stop_price = entry_price * (1 + config['stop_pct'] / 100)
            stopped = False

            for j in range(1, hold_days + 1):
                if i + j >= n:
                    break
                day_low = float(lows[i + j])
                if day_low <= stop_price:
                    pct_return = config['stop_pct']
                    stopped = True
                    break
            else:
                exit_price = float(closes[i + hold_days])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            all_trades.append({
                'symbol': sym,
                'date': dates[i],
                'return': pct_return,
                'stopped': stopped
            })

    if not all_trades:
        return None

    df_trades = pd.DataFrame(all_trades)
    df_trades['week'] = df_trades['date'].dt.isocalendar().week
    df_trades['year'] = df_trades['date'].dt.year
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

    return df_trades


def main():
    print("=" * 80)
    print("OPTIMIZE FOR 10%/MONTH")
    print("=" * 80)

    # ใช้หุ้นมากขึ้นเพื่อได้ signal มากขึ้น
    symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'AMD', 'INTC', 'QCOM', 'AVGO', 'MU',
        'JPM', 'BAC', 'GS', 'V', 'MA',
        'JNJ', 'UNH', 'PFE', 'MRK', 'LLY',
        'HD', 'LOW', 'COST', 'WMT', 'MCD', 'NKE',
        'CAT', 'DE', 'HON', 'GE',
        'XOM', 'CVX', 'NFLX', 'DIS'
    ]

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

    # Grid search for best config
    CONFIGS = [
        # Original v11
        {
            'name': 'v11 Base (5d)',
            'accum_min': 1.2, 'rsi_max': 58,
            'ma20_min': 0, 'ma50_min': 0,
            'atr_max': 3.0, 'hold_days': 5, 'stop_pct': -2.0
        },
        # Shorter hold
        {
            'name': '3-day hold',
            'accum_min': 1.2, 'rsi_max': 58,
            'ma20_min': 0, 'ma50_min': 0,
            'atr_max': 3.0, 'hold_days': 3, 'stop_pct': -2.0
        },
        # Higher momentum requirement
        {
            'name': 'High Momentum',
            'accum_min': 1.3, 'rsi_max': 55,
            'ma20_min': 2, 'ma50_min': 2,
            'atr_max': 2.5, 'hold_days': 5, 'stop_pct': -2.0
        },
        # Volume surge
        {
            'name': 'Vol Surge',
            'accum_min': 1.2, 'rsi_max': 58,
            'ma20_min': 0, 'ma50_min': 0,
            'atr_max': 3.0, 'vol_min': 1.2,
            'hold_days': 5, 'stop_pct': -2.0
        },
        # Positive 3d momentum
        {
            'name': 'Mom 3d > 0',
            'accum_min': 1.2, 'rsi_max': 58,
            'ma20_min': 0, 'ma50_min': 0,
            'atr_max': 3.0, 'mom_3d_min': 0,
            'hold_days': 5, 'stop_pct': -2.0
        },
        # Combined best
        {
            'name': 'Best Combined',
            'accum_min': 1.2, 'rsi_max': 57,
            'ma20_min': 1, 'ma50_min': 1,
            'atr_max': 2.5, 'vol_min': 1.1, 'mom_3d_min': 0,
            'hold_days': 5, 'stop_pct': -2.0
        },
        # Aggressive
        {
            'name': 'Aggressive (3d, tight stop)',
            'accum_min': 1.1, 'rsi_max': 60,
            'ma20_min': 0, 'ma50_min': 0,
            'atr_max': 3.5, 'hold_days': 3, 'stop_pct': -1.5
        },
        # Ultra short
        {
            'name': '2-day scalp',
            'accum_min': 1.2, 'rsi_max': 58,
            'ma20_min': 0, 'ma50_min': 0,
            'atr_max': 3.0, 'hold_days': 2, 'stop_pct': -2.0
        },
    ]

    results = []

    for config in CONFIGS:
        df_trades = backtest(stock_data, config)

        if df_trades is None or len(df_trades) == 0:
            continue

        n_trades = len(df_trades)
        n_winners = len(df_trades[df_trades['return'] > 0])
        total_return = df_trades['return'].sum()
        avg_return = df_trades['return'].mean()

        # Calculate actual months
        first_date = df_trades['date'].min()
        last_date = df_trades['date'].max()
        months = max(1, (last_date - first_date).days / 30)
        monthly_return = total_return / months

        results.append({
            'config': config['name'],
            'trades': n_trades,
            'trades_per_month': n_trades / months,
            'win_rate': n_winners / n_trades * 100,
            'avg_return': avg_return,
            'monthly_return': monthly_return,
            'total_return': total_return
        })

    # Display results
    print("\n" + "=" * 90)
    print("RESULTS")
    print("=" * 90)

    print(f"\n{'Config':<25} {'Trades/M':>10} {'Win%':>8} {'AvgRet':>8} {'Monthly':>10}")
    print("-" * 70)

    for r in sorted(results, key=lambda x: -x['monthly_return']):
        status = "✅" if r['monthly_return'] >= 10 else ("⭐" if r['monthly_return'] >= 7 else "❌")
        print(f"{status} {r['config']:<23} {r['trades_per_month']:>9.1f} {r['win_rate']:>7.1f}% {r['avg_return']:>+7.2f}% {r['monthly_return']:>+9.2f}%")

    # Best config
    best = max(results, key=lambda x: x['monthly_return'])
    print(f"\n🏆 Best: {best['config']}")
    print(f"   Monthly Return: {best['monthly_return']:+.2f}%")
    print(f"   Win Rate: {best['win_rate']:.1f}%")
    print(f"   Trades/Month: {best['trades_per_month']:.1f}")

    # Check if any reaches 10%
    good = [r for r in results if r['monthly_return'] >= 10]
    if good:
        print(f"\n✅ {len(good)} configs achieve 10%+/month!")
    else:
        print(f"\n⚠️ No config achieves 10%/month yet")
        print(f"   Best is {best['monthly_return']:.2f}%/month")
        print(f"\n💡 Options:")
        print(f"   1. Accept lower target (~7-8%/month)")
        print(f"   2. Trade more stocks")
        print(f"   3. Use leverage (risky)")


if __name__ == '__main__':
    main()
