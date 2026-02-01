#!/usr/bin/env python3
"""
Comprehensive search for ZERO LOSER configuration with best profit/winrate
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import itertools
warnings.filterwarnings('ignore')

# Extended test parameters
HOLD_DAYS_OPTIONS = [7, 10, 14, 21, 30]
TEST_MONTHS = 4  # 4 months of data


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


def calculate_accumulation(df, period=20):
    if len(df) < period:
        return 1.0
    recent = df.tail(period)
    up_volume = 0
    down_volume = 0
    closes = recent['Close'].values.flatten()
    volumes = recent['Volume'].values.flatten()
    for i in range(1, len(closes)):
        c_curr = float(closes[i])
        c_prev = float(closes[i-1])
        vol = float(volumes[i])
        if c_curr > c_prev:
            up_volume += vol
        elif c_curr < c_prev:
            down_volume += vol
    if down_volume == 0:
        return 3.0
    return up_volume / down_volume


def calculate_momentum(prices, days):
    """Calculate momentum over N days"""
    if len(prices) < days:
        return 0
    p_now = float(prices[-1])
    p_before = float(prices[-days])
    return ((p_now - p_before) / p_before) * 100


def get_metrics_at_index(df, idx):
    """Get all metrics at a given index"""
    if idx < 50:
        return None

    historical = df.iloc[:idx+1]
    if len(historical) < 50:
        return None

    closes = historical['Close'].values.flatten()
    current_price = float(closes[-1])

    # MAs
    ma10 = float(np.mean(closes[-10:]))
    ma20 = float(np.mean(closes[-20:]))
    ma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else ma20

    # RSI
    rsi = calculate_rsi(closes[-30:], period=14)

    # Accumulation
    accum = calculate_accumulation(historical, period=20)

    # Price vs MAs
    above_ma10 = ((current_price - ma10) / ma10) * 100
    above_ma20 = ((current_price - ma20) / ma20) * 100
    above_ma50 = ((current_price - ma50) / ma50) * 100

    # Momentum
    mom_5d = calculate_momentum(closes, 5)
    mom_10d = calculate_momentum(closes, 10)
    mom_20d = calculate_momentum(closes, 20)

    # Volatility (20-day)
    closes_for_vol = closes[-21:]
    returns = np.diff(closes_for_vol) / closes_for_vol[:-1]
    volatility = float(np.std(returns) * 100)

    # Volume ratio (current vs 20-day avg)
    volumes = historical['Volume'].values.flatten()
    vol_avg = float(np.mean(volumes[-20:]))
    vol_ratio = float(volumes[-1]) / vol_avg if vol_avg > 0 else 1

    return {
        'price': current_price,
        'rsi': rsi,
        'accumulation': accum,
        'above_ma10': above_ma10,
        'above_ma20': above_ma20,
        'above_ma50': above_ma50,
        'mom_5d': mom_5d,
        'mom_10d': mom_10d,
        'mom_20d': mom_20d,
        'volatility': volatility,
        'vol_ratio': vol_ratio
    }


def download_stock_data(symbol, start_date, end_date):
    """Download stock data"""
    try:
        df = yf.download(symbol, start=start_date, end=end_date, progress=False)
        if df.empty or len(df) < 60:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # Ensure all columns are 1D series
        for col in df.columns:
            if hasattr(df[col], 'values') and len(df[col].values.shape) > 1:
                df[col] = df[col].values.flatten()
        return df
    except:
        return None


def get_stock_universe():
    """Get diversified stock universe"""
    # Mix of large caps, tech, and growth stocks
    symbols = [
        # Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'NFLX', 'CRM',
        'ADBE', 'INTC', 'CSCO', 'ORCL', 'IBM', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT',
        # Cybersecurity/Cloud
        'PANW', 'CRWD', 'ZS', 'DDOG', 'SNOW', 'NET', 'OKTA',
        # Finance
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'V', 'MA', 'PYPL', 'AXP',
        # Healthcare
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD',
        # Consumer
        'HD', 'LOW', 'TGT', 'COST', 'WMT', 'NKE', 'SBUX', 'MCD',
        # Industrial
        'BA', 'CAT', 'DE', 'HON', 'UNP', 'UPS', 'FDX', 'GE',
        # Energy
        'XOM', 'CVX', 'COP', 'SLB',
        # Communication
        'DIS', 'CMCSA', 'T', 'VZ', 'TMUS'
    ]
    return symbols


def main():
    print("=" * 80)
    print("COMPREHENSIVE ZERO LOSER OPTIMIZATION")
    print("=" * 80)

    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 70)

    print(f"Test Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # Get symbols
    symbols = get_stock_universe()
    print(f"Universe: {len(symbols)} stocks")

    # Download all data
    print("\nDownloading data...")
    stock_data = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(download_stock_data, sym, start_date, end_date): sym for sym in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            data = future.result()
            if data is not None:
                stock_data[sym] = data

    print(f"Downloaded: {len(stock_data)} stocks")

    # Generate all trades with all metrics
    print("\nGenerating trade signals...")
    all_signals = []

    for symbol, df in stock_data.items():
        for hold_days in HOLD_DAYS_OPTIONS:
            for i in range(60, len(df) - hold_days):
                metrics = get_metrics_at_index(df, i)
                if metrics is None:
                    continue

                # Handle potential Series or scalar
                entry_val = df['Close'].iloc[i]
                exit_val = df['Close'].iloc[i + hold_days]
                entry_price = entry_val.item() if hasattr(entry_val, 'item') else float(entry_val)
                exit_price = exit_val.item() if hasattr(exit_val, 'item') else float(exit_val)
                pct_return = ((exit_price - entry_price) / entry_price) * 100

                signal = {
                    'symbol': symbol,
                    'entry_date': df.index[i].strftime('%Y-%m-%d'),
                    'hold_days': int(hold_days),
                    'return_pct': float(pct_return),
                    'price': float(metrics['price']),
                    'rsi': float(metrics['rsi']),
                    'accumulation': float(metrics['accumulation']),
                    'above_ma10': float(metrics['above_ma10']),
                    'above_ma20': float(metrics['above_ma20']),
                    'above_ma50': float(metrics['above_ma50']),
                    'mom_5d': float(metrics['mom_5d']),
                    'mom_10d': float(metrics['mom_10d']),
                    'mom_20d': float(metrics['mom_20d']),
                    'volatility': float(metrics['volatility']),
                    'vol_ratio': float(metrics['vol_ratio'])
                }
                all_signals.append(signal)

    df_signals = pd.DataFrame(all_signals)
    print(f"Total signals: {len(df_signals)}")

    # ===== GRID SEARCH =====
    print("\n" + "=" * 80)
    print("GRID SEARCH FOR OPTIMAL ZERO LOSER CONFIGURATION")
    print("=" * 80)

    # Parameters to search
    accum_range = [1.5, 1.7, 1.8, 2.0, 2.2, 2.5, 3.0]
    rsi_range = [45, 50, 52, 55, 57]
    ma20_range = [0, 1, 2, 3, 4, 5]
    ma50_range = [-5, 0, 2, 5]
    mom_range = [-2, 0, 2, 5]

    best_configs = []

    total_combos = len(accum_range) * len(rsi_range) * len(ma20_range) * len(ma50_range) * len(mom_range) * len(HOLD_DAYS_OPTIONS)
    print(f"Testing {total_combos} combinations...")

    tested = 0
    for hold_days in HOLD_DAYS_OPTIONS:
        df_hold = df_signals[df_signals['hold_days'] == hold_days]

        for accum_min in accum_range:
            for rsi_max in rsi_range:
                for ma20_min in ma20_range:
                    for ma50_min in ma50_range:
                        for mom_min in mom_range:
                            tested += 1

                            filtered = df_hold[
                                (df_hold['accumulation'] > accum_min) &
                                (df_hold['rsi'] < rsi_max) &
                                (df_hold['above_ma20'] > ma20_min) &
                                (df_hold['above_ma50'] > ma50_min) &
                                (df_hold['mom_20d'] > mom_min)
                            ]

                            if len(filtered) < 10:  # Need at least 10 trades
                                continue

                            n_trades = len(filtered)
                            n_losers = len(filtered[filtered['return_pct'] < 0])
                            n_winners = len(filtered[filtered['return_pct'] > 0])
                            avg_return = filtered['return_pct'].mean()

                            if n_losers == 0:  # ZERO LOSER!
                                best_configs.append({
                                    'hold_days': hold_days,
                                    'accum_min': accum_min,
                                    'rsi_max': rsi_max,
                                    'ma20_min': ma20_min,
                                    'ma50_min': ma50_min,
                                    'mom_min': mom_min,
                                    'trades': n_trades,
                                    'winners': n_winners,
                                    'losers': n_losers,
                                    'avg_return': avg_return,
                                    'total_return': avg_return * n_trades
                                })

            if tested % 5000 == 0:
                print(f"  Progress: {tested}/{total_combos}, Found {len(best_configs)} zero loser configs")

    if not best_configs:
        print("\n❌ No zero loser config found with >= 10 trades")
        print("Searching for low loser configs...")

        # Search again with relaxed loser tolerance
        for hold_days in HOLD_DAYS_OPTIONS:
            df_hold = df_signals[df_signals['hold_days'] == hold_days]

            for accum_min in accum_range:
                for rsi_max in rsi_range:
                    for ma20_min in ma20_range:
                        for ma50_min in ma50_range:
                            for mom_min in mom_range:
                                filtered = df_hold[
                                    (df_hold['accumulation'] > accum_min) &
                                    (df_hold['rsi'] < rsi_max) &
                                    (df_hold['above_ma20'] > ma20_min) &
                                    (df_hold['above_ma50'] > ma50_min) &
                                    (df_hold['mom_20d'] > mom_min)
                                ]

                                if len(filtered) < 10:
                                    continue

                                n_trades = len(filtered)
                                n_losers = len(filtered[filtered['return_pct'] < 0])
                                loser_rate = n_losers / n_trades * 100

                                if loser_rate <= 15:  # Max 15% losers
                                    n_winners = len(filtered[filtered['return_pct'] > 0])
                                    avg_return = filtered['return_pct'].mean()

                                    best_configs.append({
                                        'hold_days': hold_days,
                                        'accum_min': accum_min,
                                        'rsi_max': rsi_max,
                                        'ma20_min': ma20_min,
                                        'ma50_min': ma50_min,
                                        'mom_min': mom_min,
                                        'trades': n_trades,
                                        'winners': n_winners,
                                        'losers': n_losers,
                                        'loser_rate': loser_rate,
                                        'avg_return': avg_return,
                                        'total_return': avg_return * n_trades
                                    })

    # Sort by: 1) losers (asc), 2) trades (desc), 3) avg_return (desc)
    configs_df = pd.DataFrame(best_configs)

    if 'loser_rate' not in configs_df.columns:
        configs_df['loser_rate'] = 0

    configs_df = configs_df.sort_values(
        ['losers', 'trades', 'avg_return'],
        ascending=[True, False, False]
    )

    print("\n" + "=" * 80)
    print("🎯 TOP ZERO/LOW LOSER CONFIGURATIONS")
    print("=" * 80)

    print("\n" + configs_df.head(30).to_string(index=False))

    # Select BEST configuration
    if len(configs_df) > 0:
        # Prefer: zero loser > more trades > higher return
        zero_loser_df = configs_df[configs_df['losers'] == 0]

        if len(zero_loser_df) > 0:
            # Among zero losers, pick the one with most trades and best return
            best = zero_loser_df.sort_values(['trades', 'avg_return'], ascending=[False, False]).iloc[0]
            print("\n" + "=" * 80)
            print("✅ BEST ZERO LOSER CONFIGURATION")
            print("=" * 80)
        else:
            # Pick lowest loser rate with reasonable trades
            best = configs_df.iloc[0]
            print("\n" + "=" * 80)
            print("🟡 BEST LOW LOSER CONFIGURATION")
            print("=" * 80)

        print(f"""
Hold Days:      {int(best['hold_days'])}
Accumulation:   > {best['accum_min']}
RSI:            < {int(best['rsi_max'])}
Above MA20:     > {best['ma20_min']}%
Above MA50:     > {best['ma50_min']}%
Momentum 20d:   > {best['mom_min']}%

Results:
  Trades:       {int(best['trades'])}
  Winners:      {int(best['winners'])}
  Losers:       {int(best['losers'])}
  Avg Return:   {best['avg_return']:.2f}%
  Total Return: {best['total_return']:.2f}%
""")

        # Save best config
        best_config = {
            'hold_days': int(best['hold_days']),
            'accum_min': float(best['accum_min']),
            'rsi_max': int(best['rsi_max']),
            'ma20_min': float(best['ma20_min']),
            'ma50_min': float(best['ma50_min']),
            'mom_min': float(best['mom_min']),
            'trades': int(best['trades']),
            'avg_return': float(best['avg_return']),
            'losers': int(best['losers'])
        }

        import json
        with open('best_zero_loser_config.json', 'w') as f:
            json.dump(best_config, f, indent=2)
        print("💾 Saved to: best_zero_loser_config.json")

        # Validate with specific trades
        print("\n📋 SAMPLE TRADES FROM BEST CONFIG:")
        df_hold = df_signals[df_signals['hold_days'] == best['hold_days']]
        validated = df_hold[
            (df_hold['accumulation'] > best['accum_min']) &
            (df_hold['rsi'] < best['rsi_max']) &
            (df_hold['above_ma20'] > best['ma20_min']) &
            (df_hold['above_ma50'] > best['ma50_min']) &
            (df_hold['mom_20d'] > best['mom_min'])
        ].sort_values('return_pct', ascending=False)

        print(validated[['symbol', 'entry_date', 'return_pct', 'rsi', 'accumulation', 'above_ma20']].head(20).to_string(index=False))

        if best['losers'] > 0:
            print("\n⚠️ LOSING TRADES:")
            losers = validated[validated['return_pct'] < 0]
            print(losers[['symbol', 'entry_date', 'return_pct', 'rsi', 'accumulation', 'above_ma20']].to_string(index=False))

    # Save all results
    configs_df.to_csv('zero_loser_optimization_results.csv', index=False)
    print("\n💾 All results saved to: zero_loser_optimization_results.csv")


if __name__ == '__main__':
    main()
