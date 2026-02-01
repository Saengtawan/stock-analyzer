#!/usr/bin/env python3
"""
Test all 3 configurations to find the best one for today's market
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
    up_vol, down_vol = 0.0, 0.0
    for i in range(-period+1, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        elif closes[i] < closes[i-1]:
            down_vol += volumes[i]
    return up_vol / down_vol if down_vol > 0 else 3.0


# Configurations to test
CONFIGS = {
    '5-day (Quick)': {
        'hold': 5,
        'accum': 1.3,
        'rsi': 55,
        'ma20': 1,
        'ma50': 0,
        'stoploss': -3  # Tighter for short hold
    },
    '14-day (Medium)': {
        'hold': 14,
        'accum': 1.3,
        'rsi': 57,
        'ma20': -3,
        'ma50': 6,
        'stoploss': -5
    },
    '21-day (Long)': {
        'hold': 21,
        'accum': 1.0,
        'rsi': 55,
        'ma20': -5,
        'ma50': 4,
        'stoploss': -7  # Wider for longer hold
    }
}

# Large universe
SYMBOLS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'QCOM',
    'TXN', 'AVGO', 'MU', 'AMAT', 'CRM', 'ADBE', 'ORCL', 'NOW', 'SNOW', 'DDOG',
    'NET', 'ZS', 'PANW', 'CRWD', 'JPM', 'BAC', 'WFC', 'GS', 'MS', 'V', 'MA',
    'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'HD', 'LOW',
    'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'DIS', 'CAT', 'DE', 'HON',
    'GE', 'BA', 'XOM', 'CVX', 'T', 'VZ', 'TMUS', 'NFLX', 'UBER', 'ABNB',
    'PYPL', 'SQ', 'SHOP', 'COIN', 'PLTR', 'RBLX', 'U'
]


def main():
    print("=" * 70)
    print("TESTING ALL 3 CONFIGURATIONS")
    print("=" * 70)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=70)

    print(f"\nDownloading {len(SYMBOLS)} stocks...")

    # Download all data
    stock_data = {}
    for sym in SYMBOLS:
        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if df.empty or len(df) < 55:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            stock_data[sym] = df
        except:
            pass

    print(f"Downloaded: {len(stock_data)} stocks\n")

    # Calculate metrics for all stocks
    all_metrics = []
    for sym, df in stock_data.items():
        closes = df['Close'].values.flatten()
        volumes = df['Volume'].values.flatten()

        price = float(closes[-1])
        ma20 = float(np.mean(closes[-20:]))
        ma50 = float(np.mean(closes[-50:]))
        above_ma20 = ((price - ma20) / ma20) * 100
        above_ma50 = ((price - ma50) / ma50) * 100
        rsi = calculate_rsi(closes[-30:], period=14)
        accum = calculate_accumulation(closes, volumes, period=20)

        all_metrics.append({
            'symbol': sym,
            'price': price,
            'rsi': rsi,
            'accum': accum,
            'ma20': above_ma20,
            'ma50': above_ma50
        })

    df_metrics = pd.DataFrame(all_metrics)

    # Test each configuration
    results = {}
    for name, cfg in CONFIGS.items():
        print(f"\n{'='*60}")
        print(f"📊 CONFIG: {name}")
        print(f"{'='*60}")
        print(f"   Hold: {cfg['hold']} days")
        print(f"   Accum > {cfg['accum']}")
        print(f"   RSI < {cfg['rsi']}")
        print(f"   MA20 > {cfg['ma20']}%")
        print(f"   MA50 > {cfg['ma50']}%")
        print(f"   Stop-Loss: {cfg['stoploss']}%")

        # Filter stocks
        passed = df_metrics[
            (df_metrics['accum'] > cfg['accum']) &
            (df_metrics['rsi'] < cfg['rsi']) &
            (df_metrics['ma20'] > cfg['ma20']) &
            (df_metrics['ma50'] > cfg['ma50'])
        ]

        results[name] = {
            'passed': len(passed),
            'cfg': cfg,
            'stocks': passed
        }

        print(f"\n   ✅ Stocks passing: {len(passed)}")

        if len(passed) > 0:
            print(f"\n   Top stocks:")
            passed_sorted = passed.sort_values('accum', ascending=False)
            for _, r in passed_sorted.head(10).iterrows():
                print(f"   {r['symbol']:<6} ${r['price']:>7.2f}  RSI:{r['rsi']:.1f}  Accum:{r['accum']:.2f}  MA20:{r['ma20']:+.1f}%  MA50:{r['ma50']:+.1f}%")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY - WHICH CONFIG IS BEST TODAY?")
    print("=" * 70)

    best_config = None
    best_count = 0

    for name, result in results.items():
        status = "✅" if result['passed'] > 0 else "❌"
        print(f"\n{status} {name}: {result['passed']} stocks pass")

        if result['passed'] > best_count:
            best_count = result['passed']
            best_config = name

    if best_config:
        print(f"\n🏆 BEST CONFIG FOR TODAY: {best_config}")
        cfg = results[best_config]['cfg']
        print(f"""
RECOMMENDED GATES:
  - Accumulation > {cfg['accum']}
  - RSI < {cfg['rsi']}
  - Above MA20 > {cfg['ma20']}%
  - Above MA50 > {cfg['ma50']}%
  - Stop-Loss: {cfg['stoploss']}%
  - Hold: {cfg['hold']} days
""")

        print("📋 STOCKS TO TRADE:")
        stocks = results[best_config]['stocks']
        for _, r in stocks.iterrows():
            stop_price = r['price'] * (1 + cfg['stoploss']/100)
            print(f"   {r['symbol']:<6} Entry: ${r['price']:.2f}  Stop: ${stop_price:.2f} ({cfg['stoploss']}%)")
    else:
        print("\n❌ No config has stocks passing today - market conditions unfavorable")
        print("   Consider waiting for better setup")

    return results


if __name__ == '__main__':
    main()
