#!/usr/bin/env python3
"""
Find ZERO LOSER v3 - Comprehensive search with stop-loss and more strategies
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import json
warnings.filterwarnings('ignore')

TEST_MONTHS = 6
MIN_TRADES = 8  # Lower to find more configs


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


def get_sp500_symbols():
    """Get S&P 500 for larger universe"""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        df = tables[0]
        symbols = df['Symbol'].tolist()
        symbols = [s.replace('.', '-') for s in symbols]
        return symbols[:150]  # Top 150
    except:
        return [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD',
            'JPM', 'BAC', 'WFC', 'GS', 'V', 'MA',
            'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY',
            'HD', 'COST', 'WMT', 'MCD', 'NKE', 'SBUX',
            'CAT', 'HON', 'UNP', 'GE',
            'XOM', 'CVX', 'COP',
            'T', 'VZ', 'TMUS',
            'NFLX', 'CRM', 'ADBE', 'INTC', 'CSCO', 'ORCL', 'QCOM', 'TXN', 'AVGO',
            'DIS', 'CMCSA', 'BA', 'RTX'
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
            # Skip stocks with extreme moves
            daily_returns = result['close'].pct_change().abs()
            if daily_returns.max() > 0.25:
                return None, sym
            return result, sym
        except:
            return None, sym

    print("Downloading data...")
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(download, sym) for sym in symbols]
        done = 0
        for future in as_completed(futures):
            df, sym = future.result()
            done += 1
            if df is not None:
                stock_data[sym] = df
            if done % 30 == 0:
                print(f"  Progress: {done}/{len(symbols)}")

    return stock_data


def generate_signals_with_stoploss(stock_data, hold_days, stop_loss_pct=-5):
    """Generate signals with stop-loss applied"""
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

            # Calculate metrics
            ma10 = np.mean(closes[i-9:i+1])
            ma20 = np.mean(closes[i-19:i+1])
            ma50 = np.mean(closes[i-49:i+1])

            above_ma10 = ((price - ma10) / ma10) * 100
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            rsi = calculate_rsi(closes[i-29:i+1], period=14)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

            mom_3d = ((price - closes[i-3]) / closes[i-3]) * 100 if i >= 3 else 0
            mom_5d = ((price - closes[i-5]) / closes[i-5]) * 100 if i >= 5 else 0
            mom_10d = ((price - closes[i-10]) / closes[i-10]) * 100 if i >= 10 else 0
            mom_20d = ((price - closes[i-20]) / closes[i-20]) * 100 if i >= 20 else 0

            vol_avg = np.mean(volumes[i-10:i])
            vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1

            high_20d = np.max(highs[i-19:i+1])
            dist_from_high = ((price - high_20d) / high_20d) * 100

            low_20d = np.min(lows[i-19:i+1])
            range_20d = high_20d - low_20d
            range_position = ((price - low_20d) / range_20d * 100) if range_20d > 0 else 50

            ma_aligned = 1 if (ma10 > ma20 > ma50) else 0

            # RSI trend
            rsi_prev = calculate_rsi(closes[i-34:i-4], period=14)
            rsi_slope = rsi - rsi_prev

            # Calculate return WITH STOP-LOSS
            stop_price = price * (1 + stop_loss_pct / 100)
            exit_price = closes[i + hold_days]
            stopped_out = False

            # Check if stop-loss was hit during holding period
            for j in range(1, hold_days + 1):
                if closes[i + j] <= stop_price:
                    exit_price = stop_price
                    stopped_out = True
                    break

            pct_return = ((exit_price - price) / price) * 100

            # Max gain/drawdown during hold
            max_gain = ((np.max(closes[i:i+hold_days+1]) - price) / price) * 100
            max_dd = ((np.min(closes[i:i+hold_days+1]) - price) / price) * 100

            signals.append({
                'symbol': symbol,
                'entry_date': dates[i],
                'return_pct': pct_return,
                'return_no_sl': ((closes[i + hold_days] - price) / price) * 100,
                'stopped_out': stopped_out,
                'max_gain': max_gain,
                'max_drawdown': max_dd,
                'rsi': rsi,
                'rsi_slope': rsi_slope,
                'accum': accum,
                'above_ma10': above_ma10,
                'above_ma20': above_ma20,
                'above_ma50': above_ma50,
                'mom_3d': mom_3d,
                'mom_5d': mom_5d,
                'mom_10d': mom_10d,
                'mom_20d': mom_20d,
                'vol_surge': vol_surge,
                'dist_from_high': dist_from_high,
                'range_position': range_position,
                'ma_aligned': ma_aligned
            })

    return pd.DataFrame(signals)


def exhaustive_search(df_signals, hold_days):
    """Exhaustive search for zero loser"""
    print(f"\n{'='*70}")
    print(f"EXHAUSTIVE SEARCH FOR {hold_days}-DAY HOLD")
    print(f"{'='*70}")

    configs = []

    # Parameters
    accum_vals = np.arange(1.3, 3.0, 0.1)
    rsi_vals = [40, 42, 45, 47, 50, 52, 55, 57, 60]
    ma20_vals = [-2, 0, 1, 2, 3, 4, 5]
    ma50_vals = [-5, 0, 2, 4, 6, 8]
    mom_vals = [-5, 0, 2, 4, 6]

    total = len(accum_vals) * len(rsi_vals) * len(ma20_vals) * len(ma50_vals) * len(mom_vals)
    print(f"Testing {total:,} basic combinations...")

    tested = 0
    for accum in accum_vals:
        for rsi in rsi_vals:
            for ma20 in ma20_vals:
                for ma50 in ma50_vals:
                    for mom in mom_vals:
                        tested += 1

                        filtered = df_signals[
                            (df_signals['accum'] > accum) &
                            (df_signals['rsi'] < rsi) &
                            (df_signals['above_ma20'] > ma20) &
                            (df_signals['above_ma50'] > ma50) &
                            (df_signals['mom_20d'] > mom)
                        ]

                        n = len(filtered)
                        if n < MIN_TRADES:
                            continue

                        n_losers = len(filtered[filtered['return_pct'] < 0])

                        if n_losers == 0:
                            avg_ret = filtered['return_pct'].mean()
                            configs.append({
                                'type': 'basic',
                                'accum': round(accum, 1),
                                'rsi': rsi,
                                'ma20': ma20,
                                'ma50': ma50,
                                'mom20': mom,
                                'trades': n,
                                'losers': 0,
                                'avg_return': avg_ret
                            })

        if tested % 10000 == 0:
            print(f"  Progress: {tested:,}/{total:,}, Found: {len(configs)}")

    # Additional: MA aligned filter
    print("\nTesting with MA alignment...")
    for accum in accum_vals:
        for rsi in rsi_vals:
            for ma50 in ma50_vals:
                filtered = df_signals[
                    (df_signals['accum'] > accum) &
                    (df_signals['rsi'] < rsi) &
                    (df_signals['above_ma50'] > ma50) &
                    (df_signals['ma_aligned'] == 1)
                ]

                n = len(filtered)
                if n < MIN_TRADES:
                    continue

                n_losers = len(filtered[filtered['return_pct'] < 0])
                if n_losers == 0:
                    avg_ret = filtered['return_pct'].mean()
                    configs.append({
                        'type': 'ma_aligned',
                        'accum': round(accum, 1),
                        'rsi': rsi,
                        'ma50': ma50,
                        'trades': n,
                        'losers': 0,
                        'avg_return': avg_ret
                    })

    # Volume surge filter
    print("Testing with volume surge...")
    for accum in [1.3, 1.5, 1.7, 2.0]:
        for rsi in [45, 50, 55, 60]:
            for vol_surge in [1.2, 1.5, 2.0]:
                for mom in [0, 3, 5]:
                    filtered = df_signals[
                        (df_signals['accum'] > accum) &
                        (df_signals['rsi'] < rsi) &
                        (df_signals['vol_surge'] > vol_surge) &
                        (df_signals['mom_5d'] > mom)
                    ]

                    n = len(filtered)
                    if n < MIN_TRADES:
                        continue

                    n_losers = len(filtered[filtered['return_pct'] < 0])
                    if n_losers == 0:
                        avg_ret = filtered['return_pct'].mean()
                        configs.append({
                            'type': 'vol_surge',
                            'accum': accum,
                            'rsi': rsi,
                            'vol_surge': vol_surge,
                            'mom5d': mom,
                            'trades': n,
                            'losers': 0,
                            'avg_return': avg_ret
                        })

    return configs


def main():
    print("=" * 70)
    print("FINDING ZERO LOSER v3 - Comprehensive + Stop-Loss")
    print("=" * 70)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 70)

    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    symbols = get_sp500_symbols()
    print(f"Universe: {len(symbols)} stocks")

    stock_data = download_data(symbols, start_date, end_date)
    print(f"Downloaded: {len(stock_data)} stocks with clean data")

    all_configs = []

    # Test different holding periods with 5% stop-loss
    for hold_days in [5, 7, 10, 14]:
        print(f"\n\n{'#'*70}")
        print(f"HOLD PERIOD: {hold_days} DAYS (with -5% stop-loss)")
        print(f"{'#'*70}")

        df_signals = generate_signals_with_stoploss(stock_data, hold_days, stop_loss_pct=-5)
        print(f"Total signals: {len(df_signals)}")

        # Deduplicate
        df_signals['week'] = df_signals['entry_date'].dt.isocalendar().week
        df_signals['year'] = df_signals['entry_date'].dt.year
        df_signals = df_signals.drop_duplicates(subset=['symbol', 'year', 'week'])
        print(f"After dedup: {len(df_signals)}")

        # Without stop-loss stats
        losers_no_sl = len(df_signals[df_signals['return_no_sl'] < 0])
        losers_with_sl = len(df_signals[df_signals['return_pct'] < 0])
        print(f"Losers without SL: {losers_no_sl}, with SL: {losers_with_sl}")

        # Search
        configs = exhaustive_search(df_signals, hold_days)

        for c in configs:
            c['hold_days'] = hold_days

        all_configs.extend(configs)

    # Final summary
    if all_configs:
        print("\n" + "=" * 70)
        print("🎯 ALL ZERO LOSER CONFIGURATIONS")
        print("=" * 70)

        df_results = pd.DataFrame(all_configs)
        df_results = df_results.sort_values(['trades', 'avg_return'], ascending=[False, False])

        # Show top 30
        print(df_results.head(30).to_string(index=False))

        # Best config
        best = df_results.iloc[0]
        print(f"\n🏆 BEST ZERO LOSER CONFIG:")
        print(f"   Type:       {best['type']}")
        print(f"   Hold Days:  {best['hold_days']}")
        print(f"   Trades:     {best['trades']}")
        print(f"   Avg Return: {best['avg_return']:.2f}%")
        print(f"   Parameters: {dict(best.drop(['type', 'hold_days', 'trades', 'losers', 'avg_return']))}")

        # Save
        df_results.to_csv('zero_loser_v3_results.csv', index=False)

        # Save best as JSON
        best_config = {
            'hold_days': int(best['hold_days']),
            'type': best['type'],
            'gates': {k: float(v) if isinstance(v, (int, float, np.number)) else v
                     for k, v in best.items()
                     if k not in ['type', 'hold_days', 'trades', 'losers', 'avg_return']},
            'results': {
                'trades': int(best['trades']),
                'losers': 0,
                'avg_return': float(best['avg_return'])
            }
        }
        with open('best_zero_loser_v3.json', 'w') as f:
            json.dump(best_config, f, indent=2)

        print("\n💾 Saved to: zero_loser_v3_results.csv, best_zero_loser_v3.json")
    else:
        print("\n❌ No zero loser configs found")


if __name__ == '__main__':
    main()
