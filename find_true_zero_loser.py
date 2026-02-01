#!/usr/bin/env python3
"""
Find TRUE ZERO LOSER criteria with clean data and strict validation
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

TEST_MONTHS = 6
MIN_TRADES = 15  # Need at least 15 trades for statistical significance


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


def get_stock_universe():
    """Quality stock universe - large caps only"""
    return [
        # Big Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA',
        # Finance
        'JPM', 'BAC', 'WFC', 'GS', 'V', 'MA',
        # Healthcare
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY',
        # Consumer
        'HD', 'COST', 'WMT', 'MCD', 'NKE', 'SBUX',
        # Industrial
        'CAT', 'HON', 'UNP', 'GE',
        # Energy
        'XOM', 'CVX',
        # Telecom
        'T', 'VZ', 'TMUS',
        # Tech Growth
        'AMD', 'NFLX', 'CRM', 'ADBE', 'INTC', 'CSCO', 'ORCL', 'QCOM', 'TXN', 'AVGO',
        # Cloud/Cyber
        'PANW', 'CRWD', 'ZS', 'DDOG', 'SNOW', 'NET',
        # Other
        'DIS', 'CMCSA', 'BA', 'RTX'
    ]


def download_data(symbols, start_date, end_date):
    """Download and clean data"""
    stock_data = {}

    def download(sym):
        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if df.empty or len(df) < 80:
                return None, sym

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Convert to simple arrays
            result = pd.DataFrame({
                'date': df.index,
                'close': df['Close'].values.flatten().astype(float),
                'volume': df['Volume'].values.flatten().astype(float),
                'high': df['High'].values.flatten().astype(float),
                'low': df['Low'].values.flatten().astype(float)
            })
            result = result.set_index('date')

            # Sanity check: no extreme daily moves (>30% = likely bad data)
            daily_returns = result['close'].pct_change().abs()
            if daily_returns.max() > 0.30:
                print(f"  ⚠️ {sym}: Extreme daily move detected, skipping")
                return None, sym

            return result, sym
        except Exception as e:
            return None, sym

    print("Downloading data...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(download, sym) for sym in symbols]
        for future in as_completed(futures):
            df, sym = future.result()
            if df is not None:
                stock_data[sym] = df
                print(f"  ✓ {sym}: {len(df)} days")

    return stock_data


def generate_signals(stock_data, hold_days):
    """Generate all trading signals with metrics"""
    signals = []

    for symbol, df in stock_data.items():
        closes = df['close'].values
        volumes = df['volume'].values
        dates = df.index

        if len(closes) < 60 + hold_days:
            continue

        for i in range(55, len(closes) - hold_days):
            # Calculate metrics at entry point
            price = closes[i]

            # MAs
            ma10 = np.mean(closes[i-9:i+1])
            ma20 = np.mean(closes[i-19:i+1])
            ma50 = np.mean(closes[i-49:i+1])

            above_ma10 = ((price - ma10) / ma10) * 100
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            # RSI
            rsi = calculate_rsi(closes[i-29:i+1], period=14)

            # Accumulation
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

            # Momentum
            mom_5d = ((price - closes[i-5]) / closes[i-5]) * 100 if i >= 5 else 0
            mom_10d = ((price - closes[i-10]) / closes[i-10]) * 100 if i >= 10 else 0
            mom_20d = ((price - closes[i-20]) / closes[i-20]) * 100 if i >= 20 else 0

            # Volatility (10-day)
            returns_10d = np.diff(closes[i-10:i+1]) / closes[i-10:i]
            vol_10d = np.std(returns_10d) * 100

            # Calculate actual return after hold_days
            exit_price = closes[i + hold_days]
            pct_return = ((exit_price - price) / price) * 100

            signals.append({
                'symbol': symbol,
                'entry_date': dates[i],
                'exit_date': dates[i + hold_days],
                'entry_price': price,
                'exit_price': exit_price,
                'return_pct': pct_return,
                'rsi': rsi,
                'accum': accum,
                'above_ma10': above_ma10,
                'above_ma20': above_ma20,
                'above_ma50': above_ma50,
                'mom_5d': mom_5d,
                'mom_10d': mom_10d,
                'mom_20d': mom_20d,
                'vol_10d': vol_10d
            })

    return pd.DataFrame(signals)


def grid_search(df_signals):
    """Find ZERO LOSER configuration through grid search"""
    print("\n" + "=" * 70)
    print("GRID SEARCH FOR TRUE ZERO LOSER")
    print("=" * 70)

    # Extended parameter ranges
    accum_range = np.arange(1.5, 3.5, 0.1)
    rsi_range = [40, 42, 45, 47, 50, 52, 55, 57]
    ma20_range = [0, 1, 2, 3, 4, 5, 6, 7, 8]
    ma50_range = [0, 2, 4, 5, 6, 8, 10]
    mom20_range = [-5, 0, 2, 4, 5, 6, 8, 10]
    vol_range = [0, 1, 2, 3]  # Min volatility

    zero_loser_configs = []
    low_loser_configs = []

    total = len(accum_range) * len(rsi_range) * len(ma20_range) * len(ma50_range) * len(mom20_range) * len(vol_range)
    print(f"Testing {total:,} combinations...")

    tested = 0
    for accum in accum_range:
        for rsi in rsi_range:
            for ma20 in ma20_range:
                for ma50 in ma50_range:
                    for mom20 in mom20_range:
                        for vol in vol_range:
                            tested += 1

                            filtered = df_signals[
                                (df_signals['accum'] > accum) &
                                (df_signals['rsi'] < rsi) &
                                (df_signals['above_ma20'] > ma20) &
                                (df_signals['above_ma50'] > ma50) &
                                (df_signals['mom_20d'] > mom20) &
                                (df_signals['vol_10d'] > vol)
                            ]

                            n = len(filtered)
                            if n < MIN_TRADES:
                                continue

                            n_losers = len(filtered[filtered['return_pct'] < 0])
                            n_winners = len(filtered[filtered['return_pct'] > 0])
                            avg_ret = filtered['return_pct'].mean()
                            min_ret = filtered['return_pct'].min()

                            config = {
                                'accum': round(accum, 1),
                                'rsi': rsi,
                                'ma20': ma20,
                                'ma50': ma50,
                                'mom20': mom20,
                                'vol': vol,
                                'trades': n,
                                'winners': n_winners,
                                'losers': n_losers,
                                'win_rate': n_winners / n * 100,
                                'avg_return': avg_ret,
                                'min_return': min_ret
                            }

                            if n_losers == 0:
                                zero_loser_configs.append(config)
                            elif n_losers <= 2 and avg_ret > 3:
                                low_loser_configs.append(config)

        if tested % 50000 == 0:
            print(f"  Progress: {tested:,}/{total:,}, Zero loser: {len(zero_loser_configs)}, Low loser: {len(low_loser_configs)}")

    return zero_loser_configs, low_loser_configs


def main():
    print("=" * 70)
    print("FINDING TRUE ZERO LOSER CONFIGURATION")
    print("=" * 70)

    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 70)

    print(f"Test Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Min trades required: {MIN_TRADES}")

    # Get and download data
    symbols = get_stock_universe()
    print(f"\nUniverse: {len(symbols)} quality stocks")

    stock_data = download_data(symbols, start_date, end_date)
    print(f"\nDownloaded: {len(stock_data)} stocks with clean data")

    # Test different hold periods
    for hold_days in [7, 10, 14, 21, 30]:
        print(f"\n{'='*70}")
        print(f"TESTING HOLD PERIOD: {hold_days} DAYS")
        print(f"{'='*70}")

        # Generate signals
        df_signals = generate_signals(stock_data, hold_days)
        print(f"Total signals: {len(df_signals)}")

        # Deduplicate by symbol + week
        df_signals['week'] = df_signals['entry_date'].dt.isocalendar().week
        df_signals['year'] = df_signals['entry_date'].dt.year
        df_signals = df_signals.drop_duplicates(subset=['symbol', 'year', 'week'])
        print(f"After dedup: {len(df_signals)}")

        if len(df_signals) < MIN_TRADES:
            print("Not enough signals, skipping")
            continue

        # Grid search
        zero_configs, low_configs = grid_search(df_signals)

        if zero_configs:
            print(f"\n✅ FOUND {len(zero_configs)} ZERO LOSER CONFIGS!")

            # Sort by trades (more is better), then avg return
            df_zero = pd.DataFrame(zero_configs)
            df_zero = df_zero.sort_values(['trades', 'avg_return'], ascending=[False, False])

            print("\nTOP 10 ZERO LOSER CONFIGS:")
            print(df_zero.head(10).to_string(index=False))

            # Save best config
            best = df_zero.iloc[0]
            print(f"\n🏆 BEST ZERO LOSER CONFIG FOR {hold_days}-DAY HOLD:")
            print(f"   Accum > {best['accum']}")
            print(f"   RSI < {best['rsi']}")
            print(f"   Above MA20 > {best['ma20']}%")
            print(f"   Above MA50 > {best['ma50']}%")
            print(f"   Mom 20d > {best['mom20']}%")
            print(f"   Vol 10d > {best['vol']}%")
            print(f"   ---")
            print(f"   Trades: {int(best['trades'])}")
            print(f"   Win Rate: {best['win_rate']:.1f}%")
            print(f"   Avg Return: {best['avg_return']:.2f}%")

            # Save to JSON
            import json
            config_data = {
                'hold_days': hold_days,
                'gates': {
                    'accum_min': float(best['accum']),
                    'rsi_max': int(best['rsi']),
                    'ma20_min': float(best['ma20']),
                    'ma50_min': float(best['ma50']),
                    'mom20_min': float(best['mom20']),
                    'vol_min': float(best['vol'])
                },
                'results': {
                    'trades': int(best['trades']),
                    'winners': int(best['winners']),
                    'losers': 0,
                    'win_rate': float(best['win_rate']),
                    'avg_return': float(best['avg_return'])
                }
            }
            filename = f'zero_loser_{hold_days}d_config.json'
            with open(filename, 'w') as f:
                json.dump(config_data, f, indent=2)
            print(f"   💾 Saved to: {filename}")

            # Validate: show actual trades
            df_filtered = df_signals[
                (df_signals['accum'] > best['accum']) &
                (df_signals['rsi'] < best['rsi']) &
                (df_signals['above_ma20'] > best['ma20']) &
                (df_signals['above_ma50'] > best['ma50']) &
                (df_signals['mom_20d'] > best['mom20']) &
                (df_signals['vol_10d'] > best['vol'])
            ]
            print(f"\n📋 ACTUAL TRADES:")
            print(df_filtered[['symbol', 'entry_date', 'return_pct', 'rsi', 'accum', 'above_ma20']].sort_values('return_pct', ascending=False).to_string(index=False))

        elif low_configs:
            print(f"\n🟡 No zero loser, but found {len(low_configs)} low loser configs")
            df_low = pd.DataFrame(low_configs)
            df_low = df_low.sort_values(['losers', 'trades', 'avg_return'], ascending=[True, False, False])
            print(df_low.head(5).to_string(index=False))
        else:
            print("\n❌ No good config found for this hold period")


if __name__ == '__main__':
    main()
