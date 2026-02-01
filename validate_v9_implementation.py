#!/usr/bin/env python3
"""
Validate v9.0 TRUE ZERO LOSER implementation
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# v9.0 TRUE ZERO LOSER GATES
ACCUM_MIN = 1.3
RSI_MAX = 57
MA50_MIN = 4  # Above MA50 > 4%

HOLD_DAYS = 21
TEST_MONTHS = 6


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
    for i in range(-period, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        elif closes[i] < closes[i-1]:
            down_vol += volumes[i]
    if down_vol == 0:
        return 3.0
    return up_vol / down_vol


def get_universe():
    return [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'AMD', 'INTC', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT', 'LRCX', 'KLAC',
        'CRM', 'ADBE', 'ORCL', 'NOW', 'INTU', 'SNOW', 'DDOG', 'NET', 'ZS',
        'PANW', 'CRWD', 'FTNT',
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'V', 'MA', 'PYPL',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD',
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'DIS',
        'CAT', 'DE', 'HON', 'UNP', 'UPS', 'GE', 'BA', 'RTX',
        'XOM', 'CVX', 'COP', 'SLB',
        'T', 'VZ', 'TMUS', 'CMCSA',
        'NFLX', 'SHOP', 'UBER', 'ABNB'
    ]


def main():
    print("=" * 70)
    print("VALIDATING v9.0 TRUE ZERO LOSER IMPLEMENTATION")
    print("=" * 70)
    print(f"\nGATES:")
    print(f"  Accumulation > {ACCUM_MIN}")
    print(f"  RSI < {RSI_MAX}")
    print(f"  Above MA50 > {MA50_MIN}%")
    print(f"\nHold: {HOLD_DAYS} days")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 70)

    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # Download data
    symbols = get_universe()
    print(f"\nDownloading {len(symbols)} stocks...")

    stock_data = {}
    def download(sym):
        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if df.empty or len(df) < 80:
                return None, sym
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df, sym
        except:
            return None, sym

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(download, sym) for sym in symbols]
        for future in as_completed(futures):
            df, sym = future.result()
            if df is not None:
                stock_data[sym] = df

    print(f"Downloaded: {len(stock_data)} stocks")

    # Generate signals
    trades = []
    for symbol, df in stock_data.items():
        closes = df['Close'].values.flatten()
        volumes = df['Volume'].values.flatten()
        dates = df.index.tolist()

        n = min(len(closes), len(volumes), len(dates))
        if n < 60 + HOLD_DAYS:
            continue

        for i in range(55, n - HOLD_DAYS):
            price = float(closes[i])

            # Calculate metrics
            ma50 = float(np.mean(closes[i-49:i+1]))
            above_ma50 = ((price - ma50) / ma50) * 100

            rsi = calculate_rsi(closes[i-29:i+1], period=14)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

            # Check v9.0 gates
            if accum <= ACCUM_MIN:
                continue
            if rsi >= RSI_MAX:
                continue
            if above_ma50 <= MA50_MIN:
                continue

            # Calculate return
            exit_price = float(closes[i + HOLD_DAYS])
            pct_return = ((exit_price - price) / price) * 100

            entry_date = dates[i]
            if hasattr(entry_date, 'strftime'):
                entry_date = entry_date.strftime('%Y-%m-%d')
            else:
                entry_date = str(entry_date)[:10]

            trades.append({
                'symbol': symbol,
                'entry_date': entry_date,
                'return_pct': pct_return,
                'rsi': rsi,
                'accum': accum,
                'above_ma50': above_ma50
            })

    # Deduplicate
    df_trades = pd.DataFrame(trades)
    if len(df_trades) > 0:
        df_trades['week'] = pd.to_datetime(df_trades['entry_date']).dt.isocalendar().week
        df_trades['year'] = pd.to_datetime(df_trades['entry_date']).dt.year
        df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

    # Results
    print("\n" + "=" * 70)
    print("VALIDATION RESULTS")
    print("=" * 70)

    n_trades = len(df_trades)
    if n_trades == 0:
        print("❌ No trades found")
        return

    n_winners = len(df_trades[df_trades['return_pct'] > 0])
    n_losers = len(df_trades[df_trades['return_pct'] < 0])
    avg_return = df_trades['return_pct'].mean()
    total_return = df_trades['return_pct'].sum()

    print(f"\n📊 PERFORMANCE:")
    print(f"   Total Trades:    {n_trades}")
    print(f"   Winners:         {n_winners} ({n_winners/n_trades*100:.1f}%)")
    print(f"   Losers:          {n_losers} ({n_losers/n_trades*100:.1f}%)")
    print(f"   Avg Return:      {avg_return:.2f}%")
    print(f"   Total Return:    {total_return:.2f}%")

    if n_losers == 0:
        print("\n✅ ZERO LOSER VERIFIED!")
    else:
        print(f"\n⚠️ Has {n_losers} losers:")
        losers = df_trades[df_trades['return_pct'] < 0].nsmallest(5, 'return_pct')
        print(losers[['symbol', 'entry_date', 'return_pct', 'rsi', 'accum', 'above_ma50']].to_string(index=False))

    # Show sample trades
    print("\n📋 SAMPLE WINNING TRADES:")
    winners = df_trades.nlargest(10, 'return_pct')
    print(winners[['symbol', 'entry_date', 'return_pct', 'rsi', 'accum', 'above_ma50']].to_string(index=False))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"""
v9.0 TRUE ZERO LOSER Configuration:
  - Accumulation > {ACCUM_MIN}
  - RSI < {RSI_MAX}
  - Above MA50 > {MA50_MIN}%
  - Hold: {HOLD_DAYS} days

Backtest Results ({TEST_MONTHS} months):
  - Trades: {n_trades}
  - Win Rate: {n_winners/n_trades*100:.1f}%
  - Losers: {n_losers}
  - Avg Return: {avg_return:.2f}%
""")


if __name__ == '__main__':
    main()
