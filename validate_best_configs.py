#!/usr/bin/env python3
"""
Validate top ZERO LOSER configurations with more detailed analysis
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# Top configurations to validate
CONFIGS = [
    # Config 1: 14-day, most trades
    {'name': '14d_best', 'hold': 14, 'accum': 1.5, 'rsi': 57, 'ma20': 0, 'ma50': 5, 'mom': 5},
    # Config 2: 30-day, highest return
    {'name': '30d_high_ret', 'hold': 30, 'accum': 1.8, 'rsi': 57, 'ma20': 0, 'ma50': 5, 'mom': 0},
    # Config 3: 7-day, quick
    {'name': '7d_quick', 'hold': 7, 'accum': 1.5, 'rsi': 50, 'ma20': 0, 'ma50': 0, 'mom': 0},
    # Config 4: 21-day balanced
    {'name': '21d_balanced', 'hold': 21, 'accum': 1.5, 'rsi': 55, 'ma20': 0, 'ma50': 5, 'mom': 5},
    # Config 5: 14-day higher accum
    {'name': '14d_strict', 'hold': 14, 'accum': 1.7, 'rsi': 57, 'ma20': 0, 'ma50': 5, 'mom': 5},
]

TEST_MONTHS = 6  # 6 months for more thorough test


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
    up_volume = 0
    down_volume = 0
    for i in range(-period+1, 0):
        if closes[i] > closes[i-1]:
            up_volume += volumes[i]
        elif closes[i] < closes[i-1]:
            down_volume += volumes[i]
    if down_volume == 0:
        return 3.0
    return up_volume / down_volume


def get_stock_universe():
    """Larger universe for validation"""
    return [
        # Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'NFLX', 'CRM',
        'ADBE', 'INTC', 'CSCO', 'ORCL', 'IBM', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT',
        'LRCX', 'KLAC', 'MRVL', 'SNPS', 'CDNS',
        # Cybersecurity/Cloud
        'PANW', 'CRWD', 'ZS', 'DDOG', 'SNOW', 'NET', 'OKTA', 'FTNT', 'SPLK',
        # Finance
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'V', 'MA', 'PYPL', 'AXP', 'BLK', 'SCHW',
        # Healthcare
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD', 'ISRG', 'MDT',
        # Consumer
        'HD', 'LOW', 'TGT', 'COST', 'WMT', 'NKE', 'SBUX', 'MCD', 'DIS', 'CMCSA',
        # Industrial
        'BA', 'CAT', 'DE', 'HON', 'UNP', 'UPS', 'FDX', 'GE', 'MMM', 'RTX',
        # Energy
        'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY',
        # Telecom
        'T', 'VZ', 'TMUS',
        # Additional growth
        'SHOP', 'SQ', 'ROKU', 'TTD', 'UBER', 'LYFT', 'ABNB', 'COIN', 'RBLX'
    ]


def main():
    print("=" * 80)
    print("VALIDATING TOP ZERO LOSER CONFIGURATIONS")
    print("=" * 80)

    # Date range - 6 months
    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 60)

    print(f"Test Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Testing {len(CONFIGS)} configurations\n")

    # Get symbols
    symbols = get_stock_universe()
    print(f"Universe: {len(symbols)} stocks")

    # Download all data
    print("\nDownloading data...")
    stock_data = {}

    def download(sym):
        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if df.empty or len(df) < 60:
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

    print(f"Downloaded: {len(stock_data)} stocks\n")

    # Test each configuration
    results = []

    for config in CONFIGS:
        print(f"\n{'='*60}")
        print(f"Testing: {config['name']}")
        print(f"{'='*60}")
        print(f"  Hold: {config['hold']}d, Accum > {config['accum']}, RSI < {config['rsi']}")
        print(f"  MA20 > {config['ma20']}%, MA50 > {config['ma50']}%, Mom20d > {config['mom']}%")

        trades = []
        hold_days = config['hold']

        for symbol, df in stock_data.items():
            if len(df) < 60 + hold_days:
                continue

            closes = df['Close'].values.flatten()
            volumes = df['Volume'].values.flatten()
            dates = df.index

            for i in range(55, len(df) - hold_days):
                # Calculate metrics
                current_price = float(closes[i])
                ma20 = float(np.mean(closes[i-19:i+1]))
                ma50 = float(np.mean(closes[i-49:i+1]))

                above_ma20 = ((current_price - ma20) / ma20) * 100
                above_ma50 = ((current_price - ma50) / ma50) * 100

                rsi = calculate_rsi(closes[i-29:i+1], period=14)
                accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

                # Momentum 20d
                if i >= 20:
                    mom_20d = ((current_price - float(closes[i-20])) / float(closes[i-20])) * 100
                else:
                    mom_20d = 0

                # Check gates
                if accum <= config['accum']:
                    continue
                if rsi >= config['rsi']:
                    continue
                if above_ma20 <= config['ma20']:
                    continue
                if above_ma50 <= config['ma50']:
                    continue
                if mom_20d <= config['mom']:
                    continue

                # Calculate return
                entry_price = current_price
                exit_price = float(closes[i + hold_days])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

                trades.append({
                    'symbol': symbol,
                    'entry_date': dates[i].strftime('%Y-%m-%d'),
                    'exit_date': dates[i + hold_days].strftime('%Y-%m-%d'),
                    'return_pct': pct_return,
                    'rsi': rsi,
                    'accum': accum,
                    'ma20': above_ma20,
                    'ma50': above_ma50,
                    'mom_20d': mom_20d
                })

        # Deduplicate (same stock, same week)
        df_trades = pd.DataFrame(trades)
        if len(df_trades) > 0:
            df_trades['week'] = pd.to_datetime(df_trades['entry_date']).dt.isocalendar().week
            df_trades = df_trades.drop_duplicates(subset=['symbol', 'week'])

        n_trades = len(df_trades)
        if n_trades == 0:
            print("  ❌ No trades found")
            continue

        n_winners = len(df_trades[df_trades['return_pct'] > 0])
        n_losers = len(df_trades[df_trades['return_pct'] < 0])
        avg_return = df_trades['return_pct'].mean()
        median_return = df_trades['return_pct'].median()
        total_return = df_trades['return_pct'].sum()
        win_rate = n_winners / n_trades * 100

        print(f"\n  📊 RESULTS:")
        print(f"     Trades:      {n_trades}")
        print(f"     Winners:     {n_winners} ({win_rate:.1f}%)")
        print(f"     Losers:      {n_losers}")
        print(f"     Avg Return:  {avg_return:.2f}%")
        print(f"     Median:      {median_return:.2f}%")
        print(f"     Total:       {total_return:.2f}%")

        if n_losers == 0:
            print(f"     ✅ ZERO LOSER!")
        else:
            print(f"     ⚠️ Has {n_losers} losers")
            worst = df_trades.nsmallest(3, 'return_pct')
            print(f"     Worst trades:")
            for _, row in worst.iterrows():
                print(f"       {row['symbol']} {row['entry_date']}: {row['return_pct']:.2f}%")

        results.append({
            'config': config['name'],
            'hold_days': config['hold'],
            'trades': n_trades,
            'winners': n_winners,
            'losers': n_losers,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'total_return': total_return,
            'zero_loser': n_losers == 0
        })

        # Show sample trades
        print(f"\n  📋 TOP 5 TRADES:")
        top5 = df_trades.nlargest(5, 'return_pct')
        for _, row in top5.iterrows():
            print(f"     {row['symbol']:6s} {row['entry_date']}: +{row['return_pct']:.2f}%")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY OF ALL CONFIGURATIONS")
    print("=" * 80)

    results_df = pd.DataFrame(results)
    print(results_df.to_string(index=False))

    # Find best config
    zero_loser_df = results_df[results_df['zero_loser'] == True]
    if len(zero_loser_df) > 0:
        best = zero_loser_df.sort_values(['trades', 'avg_return'], ascending=[False, False]).iloc[0]
        print(f"\n🏆 BEST ZERO LOSER CONFIG: {best['config']}")
        print(f"   Trades: {int(best['trades'])}, Avg Return: {best['avg_return']:.2f}%")
    else:
        # Find lowest loser config
        best = results_df.sort_values(['losers', 'avg_return'], ascending=[True, False]).iloc[0]
        print(f"\n🥈 BEST LOW LOSER CONFIG: {best['config']}")
        print(f"   Trades: {int(best['trades'])}, Losers: {int(best['losers'])}, Avg Return: {best['avg_return']:.2f}%")

    results_df.to_csv('config_validation_results.csv', index=False)
    print("\n💾 Results saved to: config_validation_results.csv")


if __name__ == '__main__':
    main()
