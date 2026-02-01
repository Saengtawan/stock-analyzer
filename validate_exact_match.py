#!/usr/bin/env python3
"""
Validate with EXACT same logic as original search
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

TEST_MONTHS = 6
MIN_TRADES = 12


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
    up_vol = 0.0
    down_vol = 0.0
    for i in range(-period+1, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        elif closes[i] < closes[i-1]:
            down_vol += volumes[i]
    if down_vol == 0:
        return 3.0
    return up_vol / down_vol


def get_universe():
    """EXACT same universe as find_zero_loser_final.py"""
    return [
        # Big Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        # Semiconductors
        'AMD', 'INTC', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT', 'LRCX', 'KLAC', 'MRVL',
        # Software/Cloud
        'CRM', 'ADBE', 'ORCL', 'NOW', 'INTU', 'WDAY', 'SNOW', 'DDOG', 'NET', 'ZS',
        # Cybersecurity
        'PANW', 'CRWD', 'FTNT', 'OKTA',
        # Networking
        'CSCO', 'ANET',
        # Finance
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'BLK', 'SCHW',
        # Payments
        'V', 'MA', 'PYPL', 'SQ',
        # Healthcare
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD', 'ISRG', 'MDT',
        # Consumer
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'DIS',
        # Industrial
        'CAT', 'DE', 'HON', 'UNP', 'UPS', 'GE', 'MMM', 'BA', 'RTX', 'LMT',
        # Energy
        'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY',
        # Telecom
        'T', 'VZ', 'TMUS', 'CMCSA',
        # Auto/EV
        'GM', 'F', 'RIVN', 'LCID',
        # Streaming/Media
        'NFLX', 'ROKU', 'SPOT',
        # E-commerce/Internet
        'SHOP', 'UBER', 'LYFT', 'ABNB', 'BKNG',
        # Other growth
        'SQ', 'COIN', 'RBLX', 'PLTR', 'U',
    ]


def download_data(symbols, start_date, end_date):
    stock_data = {}

    def download(sym):
        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if df.empty or len(df) < 80:
                return None, sym
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            result = pd.DataFrame({
                'date': df.index,
                'close': df['Close'].values.flatten().astype(float),
                'volume': df['Volume'].values.flatten().astype(float),
                'high': df['High'].values.flatten().astype(float),
                'low': df['Low'].values.flatten().astype(float)
            })
            result = result.set_index('date')
            # SAME filter as original: max 20% daily move
            daily_returns = result['close'].pct_change().abs()
            if daily_returns.max() > 0.20:
                return None, sym
            return result, sym
        except:
            return None, sym

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(download, sym) for sym in symbols]
        for future in as_completed(futures):
            df, sym = future.result()
            if df is not None:
                stock_data[sym] = df

    return stock_data


def generate_signals(stock_data, hold_days):
    """EXACT same logic as find_zero_loser_final.py"""
    signals = []

    for symbol, df in stock_data.items():
        closes = df['close'].values
        volumes = df['volume'].values
        highs = df['high'].values
        lows = df['low'].values
        dates = df.index

        if len(closes) < 60 + hold_days:
            continue

        for i in range(55, len(closes) - hold_days):
            price = closes[i]

            # MAs - SAME calculation
            ma10 = np.mean(closes[i-9:i+1])
            ma20 = np.mean(closes[i-19:i+1])
            ma50 = np.mean(closes[i-49:i+1])

            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            # RSI - SAME calculation
            rsi = calculate_rsi(closes[i-29:i+1], period=14)

            # Accumulation - Using accum_20 (20-day period)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

            # Return
            exit_price = closes[i + hold_days]
            pct_return = ((exit_price - price) / price) * 100

            signals.append({
                'symbol': symbol,
                'entry_date': dates[i],
                'return_pct': pct_return,
                'rsi': rsi,
                'accum_20': accum,
                'above_ma20': above_ma20,
                'above_ma50': above_ma50,
            })

    return pd.DataFrame(signals)


def main():
    print("=" * 70)
    print("EXACT MATCH VALIDATION")
    print("=" * 70)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 70)

    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    symbols = get_universe()
    print(f"Universe: {len(symbols)} stocks")

    stock_data = download_data(symbols, start_date, end_date)
    print(f"Downloaded: {len(stock_data)} stocks (after filtering)")

    # Test 21-day hold config (BEST from search)
    hold_days = 21
    print(f"\nTesting {hold_days}-day hold...")

    df = generate_signals(stock_data, hold_days)
    print(f"Raw signals: {len(df)}")

    # Dedupe by symbol + year + week (SAME as original)
    df['week'] = df['entry_date'].dt.isocalendar().week
    df['year'] = df['entry_date'].dt.year
    df = df.drop_duplicates(subset=['symbol', 'year', 'week'])
    print(f"After dedup: {len(df)}")

    # Test configs from search
    configs = [
        {'accum': 1.3, 'rsi': 57, 'ma20': -3, 'ma50': 4},  # 40 trades, 0 losers
        {'accum': 1.3, 'rsi': 55, 'ma20': -3, 'ma50': 4},  # 29 trades, 0 losers
        {'accum': 1.5, 'rsi': 55, 'ma20': 0, 'ma50': 4},   # Alternative
    ]

    print("\n" + "=" * 70)
    print("TESTING ZERO LOSER CONFIGS")
    print("=" * 70)

    for cfg in configs:
        filtered = df[
            (df['accum_20'] > cfg['accum']) &
            (df['rsi'] < cfg['rsi']) &
            (df['above_ma20'] > cfg['ma20']) &
            (df['above_ma50'] > cfg['ma50'])
        ]

        n = len(filtered)
        if n == 0:
            print(f"\nConfig {cfg}: NO TRADES")
            continue

        n_losers = len(filtered[filtered['return_pct'] < 0])
        n_winners = len(filtered[filtered['return_pct'] > 0])
        avg_ret = filtered['return_pct'].mean()

        status = "✅ ZERO LOSER!" if n_losers == 0 else f"❌ {n_losers} losers"

        print(f"\nConfig: accum>{cfg['accum']}, rsi<{cfg['rsi']}, ma20>{cfg['ma20']}, ma50>{cfg['ma50']}")
        print(f"  Trades: {n}, Winners: {n_winners}, Losers: {n_losers}")
        print(f"  Avg Return: {avg_ret:.2f}%")
        print(f"  Status: {status}")

        if n_losers > 0 and n_losers <= 5:
            print("\n  Losing trades:")
            losers = filtered[filtered['return_pct'] < 0]
            for _, row in losers.iterrows():
                print(f"    {row['symbol']} {str(row['entry_date'])[:10]}: {row['return_pct']:.2f}%")

        if n_losers == 0:
            print("\n  Sample winning trades:")
            winners = filtered.nlargest(5, 'return_pct')
            for _, row in winners.iterrows():
                print(f"    {row['symbol']} {str(row['entry_date'])[:10]}: +{row['return_pct']:.2f}%")


if __name__ == '__main__':
    main()
