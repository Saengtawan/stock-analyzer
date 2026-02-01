#!/usr/bin/env python3
"""
Find Optimal v5.5 Filters

Test combinations of new filters found in analysis:
1. momentum_20d > X (Winners: 7.71% vs Losers: 5.12%)
2. bb_position < X (Winners: 79.82% vs Losers: 82.76%)
3. momentum_3d > X (Winners: 2.18% vs Losers: 1.63%)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from api.data_manager import DataManager

dm = DataManager()

TEST_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD', 'ORCL',
    'CRM', 'ADBE', 'NOW', 'NFLX', 'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX',
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'BA', 'UPS', 'FDX',
    'NVO', 'ASML', 'TSM', 'BABA', 'PDD', 'JD', 'TCEHY', 'SAP', 'TM', 'UL',
]


def calculate_metrics(df, idx):
    if df is None or idx < 252:
        return None

    df_slice = df.iloc[:idx+1]
    lookback = min(252, len(df_slice))

    close = df_slice['close'].iloc[-lookback:]
    high = df_slice['high'].iloc[-lookback:]

    current_price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))

    # MAs
    ma20 = close.rolling(20).mean().iloc[-1]

    price_above_ma20 = ((current_price - ma20) / ma20) * 100

    # Momentum
    mom_3d = ((current_price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_5d = ((current_price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((current_price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_20d = ((current_price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0
    mom_30d = ((current_price / close.iloc[-31]) - 1) * 100 if len(close) >= 31 else 0

    # 52w
    high_52w = high.max()
    low_52w = close.min()
    position_52w = ((current_price - low_52w) / (high_52w - low_52w)) * 100 if high_52w != low_52w else 50

    high_idx = high.idxmax()
    days_from_high = close.index[-1] - high_idx

    # Bollinger Band
    bb_mid = close.rolling(20).mean().iloc[-1]
    bb_std = close.rolling(20).std().iloc[-1]
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_position = ((current_price - bb_lower) / (bb_upper - bb_lower)) * 100 if bb_upper != bb_lower else 50

    return {
        'rsi': float(rsi),
        'price_above_ma20': float(price_above_ma20),
        'momentum_3d': float(mom_3d),
        'momentum_5d': float(mom_5d),
        'momentum_10d': float(mom_10d),
        'momentum_20d': float(mom_20d),
        'momentum_30d': float(mom_30d),
        'position_52w': float(position_52w),
        'days_from_high': int(days_from_high),
        'bb_position': float(bb_position),
    }


def passes_filter(m, config):
    """Generic filter checker"""
    if m is None:
        return False

    # v5.4 base filters
    if m['position_52w'] < 55 or m['position_52w'] > 90:
        return False
    if m['days_from_high'] < 50:
        return False
    if m['momentum_30d'] < 6 or m['momentum_30d'] > 16:
        return False
    if m['momentum_10d'] <= 0:
        return False
    if m['momentum_5d'] < 0.5 or m['momentum_5d'] > 12:
        return False
    if m['rsi'] < 45 or m['rsi'] > 62:
        return False
    if m['price_above_ma20'] <= 0:
        return False

    # New filters from config
    if 'mom_20d_min' in config and m['momentum_20d'] < config['mom_20d_min']:
        return False
    if 'bb_max' in config and m['bb_position'] > config['bb_max']:
        return False
    if 'mom_3d_min' in config and m['momentum_3d'] < config['mom_3d_min']:
        return False

    return True


def backtest_config(all_data, config):
    """Backtest a specific configuration"""
    results = []

    for symbol, df in all_data.items():
        if df is None or len(df) < 280:
            continue

        for days_back in range(30, 180):
            test_idx = len(df) - 1 - days_back
            if test_idx < 252:
                continue

            metrics = calculate_metrics(df, test_idx)
            if not passes_filter(metrics, config):
                continue

            entry_price = df.iloc[test_idx]['close']
            entry_date = pd.to_datetime(df.iloc[test_idx]['date'])

            exit_idx = test_idx + 30
            hit_stop = False

            for i in range(test_idx + 1, min(exit_idx + 1, len(df))):
                if (df.iloc[i]['low'] - entry_price) / entry_price <= -0.06:
                    hit_stop = True
                    exit_idx = i
                    break

            exit_price = entry_price * 0.94 if hit_stop else df.iloc[min(exit_idx, len(df)-1)]['close']
            return_pct = ((exit_price - entry_price) / entry_price) * 100

            results.append({
                'symbol': symbol,
                'entry_date': entry_date,
                'return_pct': return_pct,
                'is_winner': return_pct > 0,
            })

    if not results:
        return None

    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(['symbol', 'entry_date'])
    df_results['days_diff'] = df_results.groupby('symbol')['entry_date'].diff().dt.days
    df_results = df_results[(df_results['days_diff'].isna()) | (df_results['days_diff'] > 10)]

    if len(df_results) < 5:
        return None

    return {
        'trades': len(df_results),
        'win_rate': df_results['is_winner'].sum() / len(df_results) * 100,
        'avg_return': df_results['return_pct'].mean(),
        'total_return': df_results['return_pct'].sum(),
        'losers': len(df_results[df_results['is_winner'] == False]),
    }


# Main
if __name__ == "__main__":
    print("Loading all stock data...")

    all_data = {}
    for symbol in TEST_STOCKS:
        try:
            df = dm.get_price_data(symbol, period="2y", interval="1d")
            if df is not None and len(df) >= 280:
                all_data[symbol] = df
        except:
            continue

    print(f"Loaded {len(all_data)} stocks")

    # Test v5.4 baseline
    print("\n" + "="*80)
    print("BASELINE: v5.4")
    print("="*80)

    baseline = backtest_config(all_data, {})
    if baseline:
        print(f"Trades: {baseline['trades']}, Win Rate: {baseline['win_rate']:.1f}%, Avg Return: {baseline['avg_return']:+.2f}%")

    # Test filter combinations
    print("\n" + "="*80)
    print("TESTING FILTER COMBINATIONS")
    print("="*80)

    # Grid search
    results = []

    mom_20d_options = [0, 4, 5, 6, 7]  # Winners avg 7.71, Losers avg 5.12
    bb_max_options = [100, 90, 85, 80, 75]  # Winners avg 79.82, Losers avg 82.76
    mom_3d_options = [0, 1, 1.5, 2]  # Winners avg 2.18, Losers avg 1.63

    total_tests = len(mom_20d_options) * len(bb_max_options) * len(mom_3d_options)
    test_count = 0

    for mom_20d in mom_20d_options:
        for bb_max in bb_max_options:
            for mom_3d in mom_3d_options:
                config = {}
                if mom_20d > 0:
                    config['mom_20d_min'] = mom_20d
                if bb_max < 100:
                    config['bb_max'] = bb_max
                if mom_3d > 0:
                    config['mom_3d_min'] = mom_3d

                result = backtest_config(all_data, config)

                if result and result['trades'] >= 10:  # At least 10 trades
                    results.append({
                        'mom_20d_min': mom_20d,
                        'bb_max': bb_max,
                        'mom_3d_min': mom_3d,
                        **result
                    })

                test_count += 1
                if test_count % 20 == 0:
                    print(f"  Tested {test_count}/{total_tests} combinations...")

    # Sort by win rate
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('win_rate', ascending=False)

    print("\n" + "="*80)
    print("TOP 10 CONFIGURATIONS (by Win Rate)")
    print("="*80)
    print(f"\n{'Mom20d':>8} {'BB Max':>8} {'Mom3d':>8} {'Trades':>8} {'Win%':>8} {'AvgRet':>10} {'Losers':>8}")
    print("-"*70)

    for _, row in results_df.head(10).iterrows():
        print(f"{row['mom_20d_min']:>8.0f} {row['bb_max']:>8.0f} {row['mom_3d_min']:>8.1f} "
              f"{row['trades']:>8.0f} {row['win_rate']:>7.1f}% {row['avg_return']:>+9.2f}% {row['losers']:>8.0f}")

    # Best balanced (high win rate + reasonable trades)
    print("\n" + "="*80)
    print("BEST BALANCED (Win Rate > 65% AND Trades >= 15)")
    print("="*80)

    balanced = results_df[(results_df['win_rate'] >= 65) & (results_df['trades'] >= 15)]
    balanced = balanced.sort_values('avg_return', ascending=False)

    print(f"\n{'Mom20d':>8} {'BB Max':>8} {'Mom3d':>8} {'Trades':>8} {'Win%':>8} {'AvgRet':>10} {'Losers':>8}")
    print("-"*70)

    for _, row in balanced.head(5).iterrows():
        print(f"{row['mom_20d_min']:>8.0f} {row['bb_max']:>8.0f} {row['mom_3d_min']:>8.1f} "
              f"{row['trades']:>8.0f} {row['win_rate']:>7.1f}% {row['avg_return']:>+9.2f}% {row['losers']:>8.0f}")

    # Recommend best
    if len(balanced) > 0:
        best = balanced.iloc[0]
        print("\n" + "="*80)
        print("🏆 RECOMMENDED v5.5 CONFIGURATION")
        print("="*80)
        print(f"""
  v5.5 New Filters:
  -----------------
  • momentum_20d > {best['mom_20d_min']:.0f}%  (Winners avg: 7.71%, Losers avg: 5.12%)
  • bb_position < {best['bb_max']:.0f}%   (Avoid overbought)
  • momentum_3d > {best['mom_3d_min']:.1f}%   (Recent momentum confirmation)

  Expected Results:
  -----------------
  • Trades:     {best['trades']:.0f}
  • Win Rate:   {best['win_rate']:.1f}%
  • Avg Return: {best['avg_return']:+.2f}%
  • Losers:     {best['losers']:.0f}

  Improvement vs v5.4:
  --------------------
  • Win Rate:   {baseline['win_rate']:.1f}% → {best['win_rate']:.1f}% ({best['win_rate'] - baseline['win_rate']:+.1f}%)
  • Avg Return: {baseline['avg_return']:+.2f}% → {best['avg_return']:+.2f}% ({best['avg_return'] - baseline['avg_return']:+.2f}%)
  • Losers:     {baseline['losers']} → {best['losers']:.0f} ({best['losers'] - baseline['losers']:+.0f})
""")
    else:
        # Find best with relaxed criteria
        print("\n  No configuration meets criteria. Best available:")
        best = results_df.iloc[0]
        print(f"  Mom20d > {best['mom_20d_min']:.0f}, BB < {best['bb_max']:.0f}, Mom3d > {best['mom_3d_min']:.1f}")
        print(f"  Trades: {best['trades']:.0f}, Win: {best['win_rate']:.1f}%, Losers: {best['losers']:.0f}")
