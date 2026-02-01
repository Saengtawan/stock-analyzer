#!/usr/bin/env python3
"""
Find ZERO LOSER v2 - Extended search with more metrics
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import itertools
warnings.filterwarnings('ignore')

TEST_MONTHS = 6
MIN_TRADES = 10  # Lower requirement


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
    return [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA',
        'JPM', 'BAC', 'WFC', 'GS', 'V', 'MA',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY',
        'HD', 'COST', 'WMT', 'MCD', 'NKE', 'SBUX',
        'CAT', 'HON', 'UNP', 'GE',
        'XOM', 'CVX',
        'T', 'VZ', 'TMUS',
        'AMD', 'NFLX', 'CRM', 'ADBE', 'INTC', 'CSCO', 'ORCL', 'QCOM', 'TXN', 'AVGO',
        'PANW', 'CRWD', 'ZS', 'DDOG', 'SNOW', 'NET',
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
            daily_returns = result['close'].pct_change().abs()
            if daily_returns.max() > 0.30:
                return None, sym
            return result, sym
        except:
            return None, sym

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(download, sym) for sym in symbols]
        for future in as_completed(futures):
            df, sym = future.result()
            if df is not None:
                stock_data[sym] = df

    return stock_data


def generate_extended_signals(stock_data, hold_days):
    """Generate signals with extended metrics"""
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

            # Basic MAs
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

            # Momentum at various timeframes
            mom_3d = ((price - closes[i-3]) / closes[i-3]) * 100 if i >= 3 else 0
            mom_5d = ((price - closes[i-5]) / closes[i-5]) * 100 if i >= 5 else 0
            mom_10d = ((price - closes[i-10]) / closes[i-10]) * 100 if i >= 10 else 0
            mom_20d = ((price - closes[i-20]) / closes[i-20]) * 100 if i >= 20 else 0

            # Volatility
            returns_10d = np.diff(closes[i-10:i+1]) / closes[i-10:i]
            vol_10d = np.std(returns_10d) * 100

            # Volume surge (today vs 10-day avg)
            vol_avg = np.mean(volumes[i-10:i])
            vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1

            # Distance from 20-day high
            high_20d = np.max(highs[i-19:i+1])
            dist_from_high = ((price - high_20d) / high_20d) * 100

            # Price range position (where price is within 20-day range)
            low_20d = np.min(lows[i-19:i+1])
            range_20d = high_20d - low_20d
            range_position = ((price - low_20d) / range_20d * 100) if range_20d > 0 else 50

            # MA alignment (is MA10 > MA20 > MA50?)
            ma_aligned = 1 if (ma10 > ma20 > ma50) else 0

            # RSI slope (is RSI rising?)
            rsi_prev = calculate_rsi(closes[i-34:i-4], period=14)
            rsi_slope = rsi - rsi_prev

            # Calculate return
            exit_price = closes[i + hold_days]
            pct_return = ((exit_price - price) / price) * 100

            # Track max gain during hold period
            max_price_during_hold = np.max(closes[i:i+hold_days+1])
            max_gain = ((max_price_during_hold - price) / price) * 100

            # Track min (drawdown) during hold period
            min_price_during_hold = np.min(closes[i:i+hold_days+1])
            max_drawdown = ((min_price_during_hold - price) / price) * 100

            signals.append({
                'symbol': symbol,
                'entry_date': dates[i],
                'exit_date': dates[i + hold_days],
                'return_pct': pct_return,
                'max_gain': max_gain,
                'max_drawdown': max_drawdown,
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
                'vol_10d': vol_10d,
                'vol_surge': vol_surge,
                'dist_from_high': dist_from_high,
                'range_position': range_position,
                'ma_aligned': ma_aligned
            })

    return pd.DataFrame(signals)


def smart_grid_search(df_signals, hold_days):
    """Smart grid search focusing on promising areas"""
    print(f"\n{'='*70}")
    print(f"SMART SEARCH FOR {hold_days}-DAY HOLD")
    print(f"{'='*70}")

    best_configs = []

    # Strategy 1: High Accumulation + Low RSI (pullback entry)
    print("\n📊 Strategy 1: High Accumulation + Low RSI (pullback)")
    for accum in np.arange(1.8, 3.5, 0.2):
        for rsi in [40, 45, 48, 50, 52, 55]:
            for ma20 in [0, 2, 4]:
                filtered = df_signals[
                    (df_signals['accum'] > accum) &
                    (df_signals['rsi'] < rsi) &
                    (df_signals['above_ma20'] > ma20) &
                    (df_signals['rsi_slope'] > -5)  # RSI not falling sharply
                ]
                check_config(filtered, accum, rsi, ma20, 0, 0, best_configs, 'pullback')

    # Strategy 2: Strong Momentum + Volume Surge
    print("📊 Strategy 2: Strong Momentum + Volume Surge")
    for accum in np.arange(1.5, 2.5, 0.2):
        for mom in [3, 5, 7, 10]:
            for vol_surge in [1.2, 1.5, 2.0]:
                filtered = df_signals[
                    (df_signals['accum'] > accum) &
                    (df_signals['mom_5d'] > mom) &
                    (df_signals['vol_surge'] > vol_surge) &
                    (df_signals['rsi'] < 65)
                ]
                check_config_v2(filtered, accum, mom, vol_surge, best_configs, 'momentum')

    # Strategy 3: Near Breakout (close to 20-day high)
    print("📊 Strategy 3: Near Breakout")
    for accum in np.arange(1.5, 2.5, 0.2):
        for dist in [-3, -2, -1, 0]:
            for range_pos in [70, 80, 90]:
                filtered = df_signals[
                    (df_signals['accum'] > accum) &
                    (df_signals['dist_from_high'] > dist) &
                    (df_signals['range_position'] > range_pos) &
                    (df_signals['rsi'] < 65) &
                    (df_signals['ma_aligned'] == 1)
                ]
                check_config_v3(filtered, accum, dist, range_pos, best_configs, 'breakout')

    # Strategy 4: MA Aligned + Strong Trend
    print("📊 Strategy 4: MA Aligned + Strong Trend")
    for accum in np.arange(1.5, 2.5, 0.2):
        for ma50 in [2, 4, 6, 8]:
            for rsi in [45, 50, 55]:
                filtered = df_signals[
                    (df_signals['accum'] > accum) &
                    (df_signals['above_ma50'] > ma50) &
                    (df_signals['rsi'] < rsi) &
                    (df_signals['rsi'] > 40) &  # Not oversold
                    (df_signals['ma_aligned'] == 1)
                ]
                check_config_v4(filtered, accum, ma50, rsi, best_configs, 'trend')

    return best_configs


def check_config(filtered, accum, rsi, ma20, ma50, mom, configs, strategy):
    n = len(filtered)
    if n < MIN_TRADES:
        return
    n_losers = len(filtered[filtered['return_pct'] < 0])
    if n_losers <= 1:  # Zero or 1 loser
        avg_ret = filtered['return_pct'].mean()
        configs.append({
            'strategy': strategy,
            'params': f"accum>{accum:.1f}, rsi<{rsi}, ma20>{ma20}",
            'trades': n,
            'losers': n_losers,
            'avg_return': avg_ret,
            'accum': accum,
            'rsi': rsi,
            'ma20': ma20
        })


def check_config_v2(filtered, accum, mom, vol_surge, configs, strategy):
    n = len(filtered)
    if n < MIN_TRADES:
        return
    n_losers = len(filtered[filtered['return_pct'] < 0])
    if n_losers <= 1:
        avg_ret = filtered['return_pct'].mean()
        configs.append({
            'strategy': strategy,
            'params': f"accum>{accum:.1f}, mom5d>{mom}, vol_surge>{vol_surge}",
            'trades': n,
            'losers': n_losers,
            'avg_return': avg_ret,
            'accum': accum,
            'mom': mom,
            'vol_surge': vol_surge
        })


def check_config_v3(filtered, accum, dist, range_pos, configs, strategy):
    n = len(filtered)
    if n < MIN_TRADES:
        return
    n_losers = len(filtered[filtered['return_pct'] < 0])
    if n_losers <= 1:
        avg_ret = filtered['return_pct'].mean()
        configs.append({
            'strategy': strategy,
            'params': f"accum>{accum:.1f}, dist_high>{dist}, range>{range_pos}",
            'trades': n,
            'losers': n_losers,
            'avg_return': avg_ret,
            'accum': accum,
            'dist': dist,
            'range_pos': range_pos
        })


def check_config_v4(filtered, accum, ma50, rsi, configs, strategy):
    n = len(filtered)
    if n < MIN_TRADES:
        return
    n_losers = len(filtered[filtered['return_pct'] < 0])
    if n_losers <= 1:
        avg_ret = filtered['return_pct'].mean()
        configs.append({
            'strategy': strategy,
            'params': f"accum>{accum:.1f}, ma50>{ma50}, rsi<{rsi}, ma_aligned",
            'trades': n,
            'losers': n_losers,
            'avg_return': avg_ret,
            'accum': accum,
            'ma50': ma50,
            'rsi': rsi
        })


def analyze_quick_gains(df_signals):
    """Analyze which configurations lead to quick gains"""
    print("\n" + "=" * 70)
    print("ANALYZING QUICK GAINS (within first few days)")
    print("=" * 70)

    # Find trades where max_gain reached within hold period was > 5%
    quick_winners = df_signals[df_signals['max_gain'] >= 5]
    slow_winners = df_signals[(df_signals['return_pct'] > 0) & (df_signals['max_gain'] < 5)]

    print(f"\nQuick winners (max gain >= 5%): {len(quick_winners)}")
    print(f"Slow winners (final positive but max < 5%): {len(slow_winners)}")

    if len(quick_winners) > 10:
        print("\n📊 QUICK WINNERS characteristics:")
        print(f"   Avg RSI:       {quick_winners['rsi'].mean():.1f}")
        print(f"   Avg Accum:     {quick_winners['accum'].mean():.2f}")
        print(f"   Avg Mom5d:     {quick_winners['mom_5d'].mean():.1f}%")
        print(f"   Avg VolSurge:  {quick_winners['vol_surge'].mean():.2f}")
        print(f"   Avg MA20:      {quick_winners['above_ma20'].mean():.1f}%")

    if len(slow_winners) > 10:
        print("\n📊 SLOW WINNERS characteristics:")
        print(f"   Avg RSI:       {slow_winners['rsi'].mean():.1f}")
        print(f"   Avg Accum:     {slow_winners['accum'].mean():.2f}")
        print(f"   Avg Mom5d:     {slow_winners['mom_5d'].mean():.1f}%")
        print(f"   Avg VolSurge:  {slow_winners['vol_surge'].mean():.2f}")
        print(f"   Avg MA20:      {slow_winners['above_ma20'].mean():.1f}%")


def main():
    print("=" * 70)
    print("FINDING ZERO LOSER v2 - Extended Search")
    print("=" * 70)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 70)

    print(f"Test Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    symbols = get_stock_universe()
    print(f"Universe: {len(symbols)} stocks")

    stock_data = download_data(symbols, start_date, end_date)
    print(f"Downloaded: {len(stock_data)} stocks")

    all_best = []

    for hold_days in [5, 7, 10, 14, 21]:
        df_signals = generate_extended_signals(stock_data, hold_days)
        print(f"\n{hold_days}-day: {len(df_signals)} signals")

        # Deduplicate
        df_signals['week'] = df_signals['entry_date'].dt.isocalendar().week
        df_signals['year'] = df_signals['entry_date'].dt.year
        df_signals = df_signals.drop_duplicates(subset=['symbol', 'year', 'week'])
        print(f"After dedup: {len(df_signals)}")

        # Analyze quick gains
        analyze_quick_gains(df_signals)

        # Search
        configs = smart_grid_search(df_signals, hold_days)

        for c in configs:
            c['hold_days'] = hold_days

        all_best.extend(configs)

    # Summary
    if all_best:
        print("\n" + "=" * 70)
        print("🎯 ALL ZERO/LOW LOSER CONFIGURATIONS FOUND")
        print("=" * 70)

        df_results = pd.DataFrame(all_best)
        df_results = df_results.sort_values(['losers', 'trades', 'avg_return'], ascending=[True, False, False])

        print(df_results.to_string(index=False))

        # Save best one
        best = df_results.iloc[0]
        print(f"\n🏆 BEST CONFIGURATION:")
        print(f"   Strategy:   {best['strategy']}")
        print(f"   Hold Days:  {best['hold_days']}")
        print(f"   Params:     {best['params']}")
        print(f"   Trades:     {best['trades']}")
        print(f"   Losers:     {best['losers']}")
        print(f"   Avg Return: {best['avg_return']:.2f}%")

        df_results.to_csv('zero_loser_v2_results.csv', index=False)
        print("\n💾 Saved to: zero_loser_v2_results.csv")
    else:
        print("\n❌ No zero/low loser configs found")


if __name__ == '__main__':
    main()
