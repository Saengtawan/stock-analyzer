#!/usr/bin/env python3
"""
หาสูตรที่ได้กำไร 10%+ ต่อเดือน
เป้าหมาย:
- เทรดหลายครั้ง/เดือน
- กำไรรวม 10%+/เดือน
- ใช้ stop-loss -2% คุม max loss
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import json
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
    print("หาสูตร 10%+ ต่อเดือน")
    print("=" * 80)

    # ใช้หุ้นมากขึ้นเพื่อให้ได้สัญญาณมากขึ้น
    symbols = [
        # Tech - Mega
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        # Tech - Semis
        'AMD', 'INTC', 'QCOM', 'AVGO', 'MU', 'AMAT', 'LRCX', 'KLAC',
        # Tech - Software
        'CRM', 'ADBE', 'ORCL', 'NOW', 'SNOW', 'DDOG', 'NET', 'ZS', 'PANW', 'CRWD',
        # Finance
        'JPM', 'BAC', 'GS', 'MS', 'WFC', 'C', 'V', 'MA', 'AXP',
        # Healthcare
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD',
        # Retail
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'LULU',
        # Industrial
        'CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT',
        # Energy
        'XOM', 'CVX', 'COP', 'SLB', 'EOG',
        # Telecom/Media
        'T', 'VZ', 'TMUS', 'NFLX', 'DIS', 'CMCSA',
        # Growth
        'UBER', 'ABNB', 'PYPL', 'SHOP', 'SQ', 'COIN', 'PLTR', 'RBLX'
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

    # ทดสอบหลาย config เพื่อหาอันที่ได้ 10%+/เดือน
    CONFIGS = [
        # ผ่อนปรน ATR เพื่อให้ได้เทรดมากขึ้น
        {
            'name': 'ATR<2.5 (More trades)',
            'accum_min': 1.2,
            'rsi_max': 57,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 1.1,
            'atr_max': 2.5,
            'hold_days': 5,
            'stop_pct': -2.0
        },
        {
            'name': 'ATR<3.0 (Even more)',
            'accum_min': 1.2,
            'rsi_max': 58,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 1.0,
            'atr_max': 3.0,
            'hold_days': 5,
            'stop_pct': -2.0
        },
        # Hold สั้นลง = เทรดบ่อยขึ้น
        {
            'name': '3-day hold (Fast)',
            'accum_min': 1.2,
            'rsi_max': 57,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 1.1,
            'atr_max': 2.5,
            'hold_days': 3,
            'stop_pct': -2.0
        },
        # ผ่อนปรนทุกอย่างแต่ใช้ stop-loss คุม
        {
            'name': 'Relaxed + Tight Stop',
            'accum_min': 1.1,
            'rsi_max': 60,
            'ma20_min': -1,
            'ma50_min': -2,
            'vol_surge_min': 1.0,
            'atr_max': 3.0,
            'hold_days': 5,
            'stop_pct': -2.0
        },
        # เน้น momentum แรง
        {
            'name': 'High Momentum',
            'accum_min': 1.3,
            'rsi_max': 60,
            'ma20_min': 2,
            'ma50_min': 3,
            'vol_surge_min': 1.2,
            'atr_max': 3.5,
            'hold_days': 5,
            'stop_pct': -2.0
        },
        # Volume surge สูง = สัญญาณแรง
        {
            'name': 'High Volume Surge',
            'accum_min': 1.2,
            'rsi_max': 58,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 1.5,
            'atr_max': 3.0,
            'hold_days': 5,
            'stop_pct': -2.0
        },
    ]

    results = []

    for config in CONFIGS:
        trades = []

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

                # MAs
                ma20 = float(np.mean(closes[i-19:i+1]))
                ma50 = float(np.mean(closes[i-49:i+1]))
                above_ma20 = ((price - ma20) / ma20) * 100
                above_ma50 = ((price - ma50) / ma50) * 100

                # RSI & Accum
                rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)
                accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

                # Volume surge
                vol_avg = float(np.mean(volumes[i-19:i]))
                vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1.0

                # ATR
                atr_pct = calculate_atr_pct(closes, highs, lows, i, period=14)

                # Apply gates
                if accum <= config['accum_min']:
                    continue
                if rsi >= config['rsi_max']:
                    continue
                if above_ma20 <= config['ma20_min']:
                    continue
                if above_ma50 <= config['ma50_min']:
                    continue
                if vol_surge < config['vol_surge_min']:
                    continue
                if atr_pct > config['atr_max']:
                    continue

                # Calculate return with stop-loss
                entry_price = price
                stop_pct = config['stop_pct']
                stopped = False

                stop_price = entry_price * (1 + stop_pct / 100)
                for j in range(1, hold_days + 1):
                    if i + j >= n:
                        break
                    day_price = float(closes[i + j])
                    if day_price <= stop_price:
                        pct_return = stop_pct
                        stopped = True
                        break
                else:
                    exit_price = float(closes[i + hold_days])
                    pct_return = ((exit_price - entry_price) / entry_price) * 100

                trades.append({
                    'symbol': sym,
                    'date': dates[i],
                    'return': pct_return,
                    'stopped': stopped
                })

        if not trades:
            continue

        df_trades = pd.DataFrame(trades)

        # Deduplicate
        df_trades['week'] = df_trades['date'].dt.isocalendar().week
        df_trades['year'] = df_trades['date'].dt.year
        df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

        n_trades = len(df_trades)
        n_winners = len(df_trades[df_trades['return'] > 0])
        n_losers = len(df_trades[df_trades['return'] <= 0])
        n_stopped = len(df_trades[df_trades['stopped'] == True])
        avg_return = df_trades['return'].mean()
        total_return = df_trades['return'].sum()

        # คำนวณเป็นต่อเดือน (12 เดือน)
        trades_per_month = n_trades / 12
        return_per_month = total_return / 12

        results.append({
            'config': config['name'],
            'trades': n_trades,
            'trades_per_month': trades_per_month,
            'winners': n_winners,
            'losers': n_losers,
            'stopped': n_stopped,
            'win_rate': n_winners / n_trades * 100 if n_trades > 0 else 0,
            'avg_return': avg_return,
            'total_return': total_return,
            'return_per_month': return_per_month
        })

    # แสดงผล
    print("\n" + "=" * 90)
    print("ผลลัพธ์: หาสูตร 10%+ ต่อเดือน")
    print("=" * 90)

    print(f"\n{'Config':<25} {'เทรด/เดือน':>12} {'Win%':>7} {'Loser':>7} {'กำไร/เดือน':>12} {'กำไร/ปี':>10}")
    print("-" * 85)

    for r in sorted(results, key=lambda x: -x['return_per_month']):
        status = "✅" if r['return_per_month'] >= 10 else "❌"
        print(f"{status} {r['config']:<23} {r['trades_per_month']:>10.1f} {r['win_rate']:>6.1f}% {r['losers']:>7} {r['return_per_month']:>+10.2f}% {r['total_return']:>+9.2f}%")

    # หา config ที่ได้ 10%+/เดือน
    good_configs = [r for r in results if r['return_per_month'] >= 10]

    if good_configs:
        print("\n" + "=" * 80)
        print("✅ CONFIG ที่ได้ 10%+ ต่อเดือน:")
        print("=" * 80)
        for r in good_configs:
            print(f"\n🏆 {r['config']}")
            print(f"   เทรด/เดือน: {r['trades_per_month']:.1f}")
            print(f"   Win Rate: {r['win_rate']:.1f}%")
            print(f"   Loser: {r['losers']} (stop-loss -2%)")
            print(f"   กำไร/เดือน: {r['return_per_month']:+.2f}%")
            print(f"   กำไร/ปี: {r['total_return']:+.2f}%")
    else:
        print("\n❌ ไม่มี config ที่ได้ 10%/เดือน")
        print("💡 ลองใช้ config ที่กำไรสูงสุด:")
        best = max(results, key=lambda x: x['return_per_month'])
        print(f"\n🏆 {best['config']}")
        print(f"   เทรด/เดือน: {best['trades_per_month']:.1f}")
        print(f"   กำไร/เดือน: {best['return_per_month']:+.2f}%")

    # Save
    with open('monthly_10pct_search.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)


if __name__ == '__main__':
    main()
