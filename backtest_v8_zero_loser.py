#!/usr/bin/env python3
"""
Backtest v8.0 ZERO LOSER Strategy
==================================
Tests the exact momentum gates:
- Accumulation > 1.3
- RSI < 60
- Price above MA20 > 0%

Validates: loser=0, win rate, and profit
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# ===== v8.0 ZERO LOSER GATES =====
ACCUM_MIN = 1.3
RSI_MAX = 60
MA20_MIN = 0  # Must be > 0%

# Backtest parameters
HOLD_DAYS = 14  # Days to hold
UNIVERSE_SIZE = 200  # Number of stocks to test
TEST_MONTHS = 3  # Months of historical data


def calculate_rsi(prices, period=14):
    """Calculate RSI"""
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


def calculate_accumulation(df, period=20):
    """Calculate accumulation ratio (up volume / down volume)"""
    if len(df) < period:
        return 1.0

    recent = df.tail(period)

    up_volume = 0
    down_volume = 0

    closes = recent['Close'].values
    volumes = recent['Volume'].values

    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            up_volume += volumes[i]
        elif closes[i] < closes[i-1]:
            down_volume += volumes[i]

    if down_volume == 0:
        return 3.0

    return up_volume / down_volume


def check_momentum_gates(df, idx):
    """
    Check if stock passes v8.0 ZERO LOSER momentum gates at given index

    Returns: (passes, metrics_dict)
    """
    if idx < 30:  # Need at least 30 days of history
        return False, {}

    # Get data up to this point
    historical = df.iloc[:idx+1]

    if len(historical) < 30:
        return False, {}

    closes = historical['Close'].values
    current_price = closes[-1]

    # Calculate MA20
    ma20 = np.mean(closes[-20:])
    price_above_ma20 = ((current_price - ma20) / ma20) * 100

    # Calculate RSI
    rsi = calculate_rsi(closes[-30:], period=14)

    # Calculate Accumulation
    accum = calculate_accumulation(historical, period=20)

    metrics = {
        'price_above_ma20': price_above_ma20,
        'rsi': rsi,
        'accumulation': accum,
        'price': current_price
    }

    # v8.0 ZERO LOSER GATES
    if price_above_ma20 <= MA20_MIN:
        return False, metrics

    if rsi >= RSI_MAX:
        return False, metrics

    if accum <= ACCUM_MIN:
        return False, metrics

    return True, metrics


def backtest_stock(symbol, start_date, end_date):
    """Backtest a single stock"""
    try:
        df = yf.download(symbol, start=start_date, end=end_date, progress=False)

        if df.empty or len(df) < 50:
            return []

        # Flatten columns if MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        trades = []

        # Walk through each day
        for i in range(40, len(df) - HOLD_DAYS):
            passes, metrics = check_momentum_gates(df, i)

            if passes:
                entry_price = df['Close'].iloc[i]
                exit_price = df['Close'].iloc[i + HOLD_DAYS]

                pct_return = ((exit_price - entry_price) / entry_price) * 100

                trades.append({
                    'symbol': symbol,
                    'entry_date': df.index[i].strftime('%Y-%m-%d'),
                    'exit_date': df.index[i + HOLD_DAYS].strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'return_pct': pct_return,
                    'rsi': metrics['rsi'],
                    'accumulation': metrics['accumulation'],
                    'price_above_ma20': metrics['price_above_ma20'],
                    'is_winner': pct_return > 0,
                    'is_loser': pct_return < 0
                })

        return trades

    except Exception as e:
        return []


def get_sp500_symbols():
    """Get S&P 500 symbols"""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        df = tables[0]
        symbols = df['Symbol'].tolist()
        # Clean symbols
        symbols = [s.replace('.', '-') for s in symbols]
        return symbols[:UNIVERSE_SIZE]
    except:
        # Fallback list
        return [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD',
            'NFLX', 'CRM', 'ADBE', 'INTC', 'CSCO', 'ORCL', 'IBM', 'QCOM',
            'TXN', 'AVGO', 'MU', 'AMAT', 'LRCX', 'KLAC', 'MRVL', 'SNPS',
            'CDNS', 'PANW', 'CRWD', 'ZS', 'OKTA', 'DDOG', 'SNOW', 'NET',
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'V', 'MA', 'PYPL',
            'DIS', 'CMCSA', 'NFLX', 'T', 'VZ', 'TMUS', 'CHTR', 'PARA',
            'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'MPC', 'VLO', 'PSX', 'OXY',
            'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD',
            'HD', 'LOW', 'TGT', 'COST', 'WMT', 'AMZN', 'TJX', 'ROST', 'DG',
            'MCD', 'SBUX', 'NKE', 'YUM', 'CMG', 'DRI', 'MAR', 'HLT', 'WYNN',
            'BA', 'CAT', 'DE', 'HON', 'UNP', 'UPS', 'FDX', 'LMT', 'RTX', 'GE'
        ]


def main():
    print("=" * 70)
    print("BACKTEST v8.0 ZERO LOSER STRATEGY")
    print("=" * 70)
    print(f"\nMomentum Gates:")
    print(f"  - Accumulation > {ACCUM_MIN}")
    print(f"  - RSI < {RSI_MAX}")
    print(f"  - Price above MA20 > {MA20_MIN}%")
    print(f"\nHold Period: {HOLD_DAYS} days")
    print(f"Test Period: {TEST_MONTHS} months")
    print(f"Universe: {UNIVERSE_SIZE} stocks")
    print("-" * 70)

    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 60)  # Extra days for warmup

    print(f"\nDate Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # Get symbols
    print("\nFetching stock universe...")
    symbols = get_sp500_symbols()
    print(f"Testing {len(symbols)} stocks")

    # Run backtest in parallel
    all_trades = []
    completed = 0

    print("\nRunning backtest...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(backtest_stock, sym, start_date, end_date): sym
                   for sym in symbols}

        for future in as_completed(futures):
            completed += 1
            trades = future.result()
            all_trades.extend(trades)

            if completed % 20 == 0:
                print(f"  Progress: {completed}/{len(symbols)} stocks, {len(all_trades)} signals found")

    print(f"\nTotal signals found: {len(all_trades)}")

    if not all_trades:
        print("No trades found!")
        return

    # Convert to DataFrame
    df = pd.DataFrame(all_trades)

    # Deduplicate (same stock can't signal on consecutive days)
    df = df.drop_duplicates(subset=['symbol', 'entry_date'])

    print(f"Unique trades after dedup: {len(df)}")

    # ===== RESULTS =====
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    total_trades = len(df)
    winners = df[df['return_pct'] > 0]
    losers = df[df['return_pct'] < 0]
    breakeven = df[df['return_pct'] == 0]

    win_rate = len(winners) / total_trades * 100
    avg_return = df['return_pct'].mean()
    median_return = df['return_pct'].median()

    avg_win = winners['return_pct'].mean() if len(winners) > 0 else 0
    avg_loss = losers['return_pct'].mean() if len(losers) > 0 else 0

    print(f"\n📊 PERFORMANCE SUMMARY:")
    print(f"   Total Trades:    {total_trades}")
    print(f"   Winners:         {len(winners)} ({win_rate:.1f}%)")
    print(f"   Losers:          {len(losers)} ({len(losers)/total_trades*100:.1f}%)")
    print(f"   Breakeven:       {len(breakeven)}")

    print(f"\n💰 RETURNS:")
    print(f"   Avg Return:      {avg_return:+.2f}%")
    print(f"   Median Return:   {median_return:+.2f}%")
    print(f"   Avg Winner:      {avg_win:+.2f}%")
    print(f"   Avg Loser:       {avg_loss:+.2f}%")
    print(f"   Best Trade:      {df['return_pct'].max():+.2f}%")
    print(f"   Worst Trade:     {df['return_pct'].min():+.2f}%")

    # Profit factor
    total_gains = winners['return_pct'].sum() if len(winners) > 0 else 0
    total_losses = abs(losers['return_pct'].sum()) if len(losers) > 0 else 0.01
    profit_factor = total_gains / total_losses

    print(f"\n📈 RISK METRICS:")
    print(f"   Profit Factor:   {profit_factor:.2f}")
    print(f"   Total Gains:     {total_gains:+.2f}%")
    print(f"   Total Losses:    {-total_losses:+.2f}%")

    # Check ZERO LOSER claim
    print("\n" + "=" * 70)
    if len(losers) == 0:
        print("✅ ZERO LOSER VERIFIED! No losing trades!")
    else:
        print(f"❌ Found {len(losers)} losers:")
        print(losers[['symbol', 'entry_date', 'return_pct', 'rsi', 'accumulation', 'price_above_ma20']].to_string())
    print("=" * 70)

    # Show sample trades
    print("\n📋 SAMPLE TRADES (Top 10 by return):")
    top_trades = df.nlargest(10, 'return_pct')
    print(top_trades[['symbol', 'entry_date', 'return_pct', 'rsi', 'accumulation', 'price_above_ma20']].to_string(index=False))

    if len(losers) > 0:
        print("\n📋 LOSING TRADES:")
        print(losers[['symbol', 'entry_date', 'return_pct', 'rsi', 'accumulation', 'price_above_ma20']].to_string(index=False))

    # Monthly breakdown
    print("\n📅 MONTHLY BREAKDOWN:")
    df['month'] = pd.to_datetime(df['entry_date']).dt.to_period('M')
    monthly = df.groupby('month').agg({
        'return_pct': ['count', 'mean', lambda x: (x > 0).sum(), lambda x: (x < 0).sum()]
    }).round(2)
    monthly.columns = ['Trades', 'Avg Return', 'Winners', 'Losers']
    print(monthly.to_string())

    # Save results
    output_file = 'backtest_v8_zero_loser_results.csv'
    df.to_csv(output_file, index=False)
    print(f"\n💾 Results saved to: {output_file}")


if __name__ == '__main__':
    main()
