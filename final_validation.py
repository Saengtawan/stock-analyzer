#!/usr/bin/env python3
"""
Final validation of v9.1 VERIFIED ZERO LOSER
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# v9.1 VERIFIED ZERO LOSER CONFIG
ACCUM_MIN = 1.3
RSI_MAX = 55
MA20_MIN = 1
MA50_MIN = 0
HOLD_DAYS = 5


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


def main():
    print("=" * 70)
    print("FINAL VALIDATION: v9.1 VERIFIED ZERO LOSER")
    print("=" * 70)

    print(f"""
CONFIG:
  Accumulation > {ACCUM_MIN}
  RSI          < {RSI_MAX}
  Above MA20   > {MA20_MIN}%
  Above MA50   > {MA50_MIN}%
  Hold         = {HOLD_DAYS} days
""")

    # Download data
    symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'AMD', 'INTC', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT',
        'CRM', 'ADBE', 'ORCL', 'NOW', 'SNOW', 'DDOG', 'NET', 'ZS',
        'PANW', 'CRWD',
        'JPM', 'BAC', 'GS', 'V', 'MA',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN',
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE',
        'CAT', 'DE', 'HON', 'GE', 'BA',
        'XOM', 'CVX',
        'T', 'VZ', 'TMUS',
        'NFLX', 'UBER', 'ABNB'
    ]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=200)

    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Testing {len(symbols)} stocks...")

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
        dates = df.index

        n = min(len(closes), len(volumes), len(dates))
        if n < 60 + HOLD_DAYS:
            continue

        for i in range(55, n - HOLD_DAYS):
            price = float(closes[i])

            ma20 = float(np.mean(closes[i-19:i+1]))
            ma50 = float(np.mean(closes[i-49:i+1]))
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            rsi = calculate_rsi(closes[i-29:i+1], period=14)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

            # Check v9.1 gates
            if accum <= ACCUM_MIN:
                continue
            if rsi >= RSI_MAX:
                continue
            if above_ma20 <= MA20_MIN:
                continue
            if above_ma50 <= MA50_MIN:
                continue

            # Calculate return
            exit_price = float(closes[i + HOLD_DAYS])
            pct_return = ((exit_price - price) / price) * 100

            entry_date = dates[i]
            if hasattr(entry_date, 'strftime'):
                entry_date_str = entry_date.strftime('%Y-%m-%d')
            else:
                entry_date_str = str(entry_date)[:10]

            trades.append({
                'symbol': symbol,
                'entry_date': entry_date_str,
                'return_pct': pct_return,
                'rsi': rsi,
                'accum': accum,
                'above_ma20': above_ma20,
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

    print(f"""
📊 PERFORMANCE:
   Total Trades:    {n_trades}
   Winners:         {n_winners} ({n_winners/n_trades*100:.1f}%)
   Losers:          {n_losers} ({n_losers/n_trades*100:.1f}%)
   Avg Return:      {avg_return:.2f}%
   Total Return:    {total_return:.2f}%
""")

    if n_losers == 0:
        print("✅ ZERO LOSER VERIFIED!")
        print("\n📋 SAMPLE TRADES:")
        sample = df_trades.nlargest(10, 'return_pct')
        print(sample[['symbol', 'entry_date', 'return_pct', 'rsi', 'accum', 'above_ma20']].to_string(index=False))
    else:
        print(f"⚠️ Found {n_losers} losers:")
        losers = df_trades[df_trades['return_pct'] < 0].nsmallest(5, 'return_pct')
        print(losers[['symbol', 'entry_date', 'return_pct', 'rsi', 'accum', 'above_ma20']].to_string(index=False))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"""
v9.1 VERIFIED ZERO LOSER:
  Accum > {ACCUM_MIN}, RSI < {RSI_MAX}, MA20 > {MA20_MIN}%, MA50 > {MA50_MIN}%
  Hold: {HOLD_DAYS} days

Results: {n_trades} trades, {n_losers} losers, {avg_return:.2f}% avg return
Status: {"✅ ZERO LOSER VERIFIED" if n_losers == 0 else "❌ HAS LOSERS"}
""")


if __name__ == '__main__':
    main()
