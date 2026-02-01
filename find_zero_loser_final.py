#!/usr/bin/env python3
"""
FINAL ZERO LOSER SEARCH - Large universe, all strategies
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


def get_large_universe():
    """Get larger universe of quality stocks"""
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
        'CAT', 'DE', 'HON', 'UNP', 'UPS', 'FDX', 'GE', 'MMM', 'BA', 'RTX', 'LMT',
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
            daily_returns = result['close'].pct_change().abs()
            if daily_returns.max() > 0.20:  # Strict: max 20% daily move
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
            if done % 20 == 0:
                print(f"  {done}/{len(symbols)} done, {len(stock_data)} valid")

    return stock_data


def generate_signals(stock_data, hold_days):
    """Generate signals with all metrics"""
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

            # MAs
            ma10 = np.mean(closes[i-9:i+1])
            ma20 = np.mean(closes[i-19:i+1])
            ma50 = np.mean(closes[i-49:i+1])

            above_ma10 = ((price - ma10) / ma10) * 100
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            # RSI
            rsi = calculate_rsi(closes[i-29:i+1], period=14)

            # Accumulation (different periods)
            accum_10 = calculate_accumulation(closes[:i+1], volumes[:i+1], period=10)
            accum_20 = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

            # Momentum
            mom_3d = ((price - closes[i-3]) / closes[i-3]) * 100 if i >= 3 else 0
            mom_5d = ((price - closes[i-5]) / closes[i-5]) * 100 if i >= 5 else 0
            mom_10d = ((price - closes[i-10]) / closes[i-10]) * 100 if i >= 10 else 0
            mom_20d = ((price - closes[i-20]) / closes[i-20]) * 100 if i >= 20 else 0

            # Volatility
            returns_10d = np.diff(closes[i-10:i+1]) / closes[i-10:i]
            vol_10d = np.std(returns_10d) * 100

            # Volume
            vol_avg = np.mean(volumes[i-10:i])
            vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1

            # Range position
            high_20d = np.max(highs[i-19:i+1])
            low_20d = np.min(lows[i-19:i+1])
            range_20d = high_20d - low_20d
            range_position = ((price - low_20d) / range_20d * 100) if range_20d > 0 else 50
            dist_from_high = ((price - high_20d) / high_20d) * 100

            # MA alignment
            ma_aligned = 1 if (ma10 > ma20 > ma50) else 0

            # ATR (average true range) - volatility measure
            tr = []
            for j in range(i-13, i+1):
                h = highs[j]
                l = lows[j]
                c_prev = closes[j-1]
                tr.append(max(h-l, abs(h-c_prev), abs(l-c_prev)))
            atr_pct = (np.mean(tr) / price) * 100

            # Calculate return
            exit_price = closes[i + hold_days]
            pct_return = ((exit_price - price) / price) * 100

            signals.append({
                'symbol': symbol,
                'entry_date': dates[i],
                'return_pct': pct_return,
                'rsi': rsi,
                'accum_10': accum_10,
                'accum_20': accum_20,
                'above_ma10': above_ma10,
                'above_ma20': above_ma20,
                'above_ma50': above_ma50,
                'mom_3d': mom_3d,
                'mom_5d': mom_5d,
                'mom_10d': mom_10d,
                'mom_20d': mom_20d,
                'vol_10d': vol_10d,
                'vol_surge': vol_surge,
                'range_position': range_position,
                'dist_from_high': dist_from_high,
                'ma_aligned': ma_aligned,
                'atr_pct': atr_pct
            })

    return pd.DataFrame(signals)


def comprehensive_search(df_signals, hold_days):
    """Comprehensive grid search"""
    print(f"\nSearching for {hold_days}-day hold zero loser configs...")

    configs = []

    # Parameter ranges
    accum_vals = np.arange(1.2, 2.8, 0.1)
    rsi_vals = [40, 45, 48, 50, 52, 55, 57, 60, 65]
    ma20_vals = [-3, -2, -1, 0, 1, 2, 3, 4, 5]
    ma50_vals = [-5, 0, 2, 4, 6, 8, 10]

    # Basic search
    for accum in accum_vals:
        for rsi in rsi_vals:
            for ma20 in ma20_vals:
                for ma50 in ma50_vals:
                    filtered = df_signals[
                        (df_signals['accum_20'] > accum) &
                        (df_signals['rsi'] < rsi) &
                        (df_signals['above_ma20'] > ma20) &
                        (df_signals['above_ma50'] > ma50)
                    ]

                    n = len(filtered)
                    if n < MIN_TRADES:
                        continue

                    n_losers = len(filtered[filtered['return_pct'] < 0])
                    if n_losers == 0:
                        avg_ret = filtered['return_pct'].mean()
                        configs.append({
                            'strategy': 'basic',
                            'accum': round(accum, 1),
                            'rsi': rsi,
                            'ma20': ma20,
                            'ma50': ma50,
                            'trades': n,
                            'avg_return': avg_ret
                        })

    # MA aligned + momentum
    for accum in accum_vals:
        for rsi in rsi_vals:
            for ma50 in [0, 2, 4, 6]:
                for mom in [0, 2, 4]:
                    filtered = df_signals[
                        (df_signals['accum_20'] > accum) &
                        (df_signals['rsi'] < rsi) &
                        (df_signals['above_ma50'] > ma50) &
                        (df_signals['mom_10d'] > mom) &
                        (df_signals['ma_aligned'] == 1)
                    ]

                    n = len(filtered)
                    if n < MIN_TRADES:
                        continue

                    n_losers = len(filtered[filtered['return_pct'] < 0])
                    if n_losers == 0:
                        avg_ret = filtered['return_pct'].mean()
                        configs.append({
                            'strategy': 'ma_aligned',
                            'accum': round(accum, 1),
                            'rsi': rsi,
                            'ma50': ma50,
                            'mom10': mom,
                            'trades': n,
                            'avg_return': avg_ret
                        })

    # Near breakout
    for accum in accum_vals:
        for rsi in rsi_vals:
            for dist in [-3, -2, -1, 0]:
                filtered = df_signals[
                    (df_signals['accum_20'] > accum) &
                    (df_signals['rsi'] < rsi) &
                    (df_signals['dist_from_high'] > dist) &
                    (df_signals['ma_aligned'] == 1)
                ]

                n = len(filtered)
                if n < MIN_TRADES:
                    continue

                n_losers = len(filtered[filtered['return_pct'] < 0])
                if n_losers == 0:
                    avg_ret = filtered['return_pct'].mean()
                    configs.append({
                        'strategy': 'breakout',
                        'accum': round(accum, 1),
                        'rsi': rsi,
                        'dist_high': dist,
                        'trades': n,
                        'avg_return': avg_ret
                    })

    # Low volatility + strong trend
    for accum in accum_vals:
        for rsi in [45, 50, 55, 60]:
            for atr in [1, 1.5, 2]:
                for ma50 in [2, 4, 6]:
                    filtered = df_signals[
                        (df_signals['accum_20'] > accum) &
                        (df_signals['rsi'] < rsi) &
                        (df_signals['atr_pct'] < atr) &
                        (df_signals['above_ma50'] > ma50)
                    ]

                    n = len(filtered)
                    if n < MIN_TRADES:
                        continue

                    n_losers = len(filtered[filtered['return_pct'] < 0])
                    if n_losers == 0:
                        avg_ret = filtered['return_pct'].mean()
                        configs.append({
                            'strategy': 'low_vol',
                            'accum': round(accum, 1),
                            'rsi': rsi,
                            'atr': atr,
                            'ma50': ma50,
                            'trades': n,
                            'avg_return': avg_ret
                        })

    return configs


def main():
    print("=" * 70)
    print("FINAL ZERO LOSER SEARCH")
    print("=" * 70)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 70)

    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    symbols = get_large_universe()
    print(f"Universe: {len(symbols)} stocks")

    stock_data = download_data(symbols, start_date, end_date)
    print(f"\nDownloaded: {len(stock_data)} clean stocks")

    all_configs = []

    for hold_days in [5, 7, 10, 14, 21]:
        print(f"\n{'='*60}")
        print(f"HOLD: {hold_days} DAYS")
        print(f"{'='*60}")

        df = generate_signals(stock_data, hold_days)
        print(f"Signals: {len(df)}")

        # Dedupe
        df['week'] = df['entry_date'].dt.isocalendar().week
        df['year'] = df['entry_date'].dt.year
        df = df.drop_duplicates(subset=['symbol', 'year', 'week'])
        print(f"After dedup: {len(df)}")

        # Overall stats
        n_win = len(df[df['return_pct'] > 0])
        n_lose = len(df[df['return_pct'] < 0])
        print(f"Win/Lose: {n_win}/{n_lose} ({n_win/(n_win+n_lose)*100:.1f}% win rate)")

        # Search
        configs = comprehensive_search(df, hold_days)

        for c in configs:
            c['hold_days'] = hold_days
            c['losers'] = 0

        all_configs.extend(configs)
        print(f"Found {len(configs)} zero loser configs")

    # Summary
    if all_configs:
        print("\n" + "=" * 70)
        print("🎯 ALL ZERO LOSER CONFIGURATIONS")
        print("=" * 70)

        df_results = pd.DataFrame(all_configs)
        df_results = df_results.sort_values(['trades', 'avg_return'], ascending=[False, False])

        # Top 30
        print(df_results.head(30).to_string(index=False))

        # Best
        best = df_results.iloc[0]
        print(f"\n{'='*70}")
        print(f"🏆 BEST ZERO LOSER CONFIGURATION")
        print(f"{'='*70}")
        print(f"Strategy:    {best['strategy']}")
        print(f"Hold Days:   {best['hold_days']}")
        print(f"Trades:      {best['trades']}")
        print(f"Avg Return:  {best['avg_return']:.2f}%")
        print(f"Parameters:")
        for k, v in best.items():
            if k not in ['strategy', 'hold_days', 'trades', 'losers', 'avg_return']:
                print(f"  {k}: {v}")

        # Save
        df_results.to_csv('zero_loser_final_results.csv', index=False)

        best_config = dict(best)
        with open('best_zero_loser_final.json', 'w') as f:
            json.dump(best_config, f, indent=2, default=str)

        print(f"\n💾 Saved: zero_loser_final_results.csv, best_zero_loser_final.json")

        # Show recommendation
        print("\n" + "=" * 70)
        print("📋 RECOMMENDED IMPLEMENTATION")
        print("=" * 70)

        # Get top config for each hold period
        for hd in [5, 7, 10, 14]:
            hd_configs = df_results[df_results['hold_days'] == hd]
            if len(hd_configs) > 0:
                top = hd_configs.iloc[0]
                print(f"\n{hd}-DAY HOLD:")
                print(f"  Strategy: {top['strategy']}")
                print(f"  Trades: {top['trades']}, Avg Return: {top['avg_return']:.2f}%")

    else:
        print("\n❌ No zero loser configs found")


if __name__ == '__main__':
    main()
