#!/usr/bin/env python3
"""
Find the final filter to eliminate remaining losers
Analyze what makes winners vs losers different
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')


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
    up_vol, down_vol = 0.0, 0.0
    for i in range(-period+1, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        elif closes[i] < closes[i-1]:
            down_vol += volumes[i]
    return up_vol / down_vol if down_vol > 0 else 3.0


def get_detailed_metrics(closes, highs, lows, volumes, i):
    """Get all possible metrics for analysis"""
    if i < 55:
        return None

    price = float(closes[i])

    # MAs
    ma10 = float(np.mean(closes[i-9:i+1]))
    ma20 = float(np.mean(closes[i-19:i+1]))
    ma50 = float(np.mean(closes[i-49:i+1]))

    dist_ma10 = ((price - ma10) / ma10) * 100
    dist_ma20 = ((price - ma20) / ma20) * 100
    dist_ma50 = ((price - ma50) / ma50) * 100

    # RSI
    rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)

    # Accumulation
    accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

    # Volume surge
    vol_avg = float(np.mean(volumes[i-19:i]))
    vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1.0

    # Momentum
    mom_1d = ((price - float(closes[i-1])) / float(closes[i-1])) * 100 if i >= 1 else 0
    mom_3d = ((price - float(closes[i-3])) / float(closes[i-3])) * 100 if i >= 3 else 0
    mom_5d = ((price - float(closes[i-5])) / float(closes[i-5])) * 100 if i >= 5 else 0
    mom_10d = ((price - float(closes[i-10])) / float(closes[i-10])) * 100 if i >= 10 else 0

    # Distance from 5-day high/low
    high_5d = float(np.max(highs[i-4:i+1]))
    low_5d = float(np.min(lows[i-4:i+1]))
    dist_high_5d = ((high_5d - price) / high_5d) * 100
    dist_low_5d = ((price - low_5d) / low_5d) * 100

    # Distance from 20-day high/low
    high_20d = float(np.max(highs[i-19:i+1]))
    low_20d = float(np.min(lows[i-19:i+1]))
    dist_high_20d = ((high_20d - price) / high_20d) * 100
    dist_low_20d = ((price - low_20d) / low_20d) * 100

    # ATR (volatility)
    tr = []
    for j in range(i-13, i+1):
        if j > 0:
            tr.append(max(
                float(highs[j]) - float(lows[j]),
                abs(float(highs[j]) - float(closes[j-1])),
                abs(float(lows[j]) - float(closes[j-1]))
            ))
    atr = np.mean(tr) if tr else 0
    atr_pct = (atr / price) * 100 if price > 0 else 0

    # Candle size today
    candle_range = (float(highs[i]) - float(lows[i])) / price * 100

    # MA alignment
    ma_aligned = 1 if ma10 > ma20 > ma50 else 0

    # Trend strength (price vs 50 MA slope)
    ma50_5d_ago = float(np.mean(closes[i-54:i-4]))
    ma50_slope = ((ma50 - ma50_5d_ago) / ma50_5d_ago) * 100 if ma50_5d_ago > 0 else 0

    # Week of year (seasonality)
    # day_of_week = 0  # Would need actual date

    return {
        'price': price,
        'rsi': rsi,
        'accum': accum,
        'dist_ma10': dist_ma10,
        'dist_ma20': dist_ma20,
        'dist_ma50': dist_ma50,
        'vol_surge': vol_surge,
        'mom_1d': mom_1d,
        'mom_3d': mom_3d,
        'mom_5d': mom_5d,
        'mom_10d': mom_10d,
        'dist_high_5d': dist_high_5d,
        'dist_low_5d': dist_low_5d,
        'dist_high_20d': dist_high_20d,
        'dist_low_20d': dist_low_20d,
        'atr_pct': atr_pct,
        'candle_range': candle_range,
        'ma_aligned': ma_aligned,
        'ma50_slope': ma50_slope
    }


def main():
    print("=" * 80)
    print("FINDING THE FINAL FILTER")
    print("=" * 80)

    symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'AMD', 'INTC', 'QCOM', 'AVGO', 'CRM', 'ADBE', 'ORCL',
        'JPM', 'BAC', 'GS', 'V', 'MA',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY',
        'HD', 'LOW', 'COST', 'WMT', 'MCD', 'NKE',
        'CAT', 'DE', 'HON', 'GE', 'BA',
        'XOM', 'CVX', 'NFLX', 'DIS', 'T', 'VZ'
    ]

    print(f"\nDownloading {len(symbols)} stocks...")

    stock_data = {}
    for sym in symbols:
        try:
            df = yf.download(sym, period='1y', progress=False)
            if df.empty or len(df) < 100:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            stock_data[sym] = df
        except:
            pass

    print(f"Downloaded: {len(stock_data)} stocks")

    # Base config: v9.1 + Vol>1.2
    ACCUM_MIN = 1.3
    RSI_MAX = 55
    MA20_MIN = 1
    MA50_MIN = 0
    VOL_SURGE_MIN = 1.2
    HOLD_DAYS = 5

    trades = []

    for sym, df in stock_data.items():
        closes = df['Close'].values.flatten()
        volumes = df['Volume'].values.flatten()
        highs = df['High'].values.flatten()
        lows = df['Low'].values.flatten()
        dates = df.index

        n = min(len(closes), len(volumes), len(highs), len(lows), len(dates))

        for i in range(55, n - HOLD_DAYS - 1):
            metrics = get_detailed_metrics(closes, highs, lows, volumes, i)
            if metrics is None:
                continue

            # Apply base gates
            if metrics['accum'] <= ACCUM_MIN:
                continue
            if metrics['rsi'] >= RSI_MAX:
                continue
            if metrics['dist_ma20'] <= MA20_MIN:
                continue
            if metrics['dist_ma50'] <= MA50_MIN:
                continue
            if metrics['vol_surge'] < VOL_SURGE_MIN:
                continue

            # Calculate return
            entry_price = metrics['price']
            exit_price = float(closes[i + HOLD_DAYS])
            pct_return = ((exit_price - entry_price) / entry_price) * 100

            trades.append({
                'symbol': sym,
                'date': dates[i],
                'return': pct_return,
                'is_winner': pct_return > 0,
                **metrics
            })

    df_trades = pd.DataFrame(trades)

    # Deduplicate
    df_trades['week'] = df_trades['date'].dt.isocalendar().week
    df_trades['year'] = df_trades['date'].dt.year
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

    print(f"\nTotal trades: {len(df_trades)}")
    print(f"Winners: {len(df_trades[df_trades['is_winner']])}")
    print(f"Losers: {len(df_trades[~df_trades['is_winner']])}")

    winners = df_trades[df_trades['is_winner']]
    losers = df_trades[~df_trades['is_winner']]

    # Compare metrics
    print("\n" + "=" * 80)
    print("METRIC COMPARISON: WINNERS vs LOSERS")
    print("=" * 80)

    metrics_to_compare = ['rsi', 'accum', 'dist_ma10', 'dist_ma20', 'dist_ma50',
                          'vol_surge', 'mom_1d', 'mom_3d', 'mom_5d', 'mom_10d',
                          'dist_high_5d', 'dist_low_5d', 'dist_high_20d', 'dist_low_20d',
                          'atr_pct', 'candle_range', 'ma_aligned', 'ma50_slope']

    print(f"\n{'Metric':<18} {'Winners':>10} {'Losers':>10} {'Diff':>10} {'Filter?':>15}")
    print("-" * 70)

    filter_ideas = []

    for metric in metrics_to_compare:
        w_mean = winners[metric].mean() if len(winners) > 0 else 0
        l_mean = losers[metric].mean() if len(losers) > 0 else 0
        diff = w_mean - l_mean

        # Suggest filter if significant difference
        suggestion = ""
        if abs(diff) > 0.3:
            if diff > 0:
                suggestion = f"> {l_mean:.2f}"
                filter_ideas.append((metric, '>', l_mean, abs(diff)))
            else:
                suggestion = f"< {l_mean:.2f}"
                filter_ideas.append((metric, '<', l_mean, abs(diff)))

        print(f"{metric:<18} {w_mean:>10.2f} {l_mean:>10.2f} {diff:>+10.2f} {suggestion:>15}")

    # Sort by impact
    filter_ideas.sort(key=lambda x: x[3], reverse=True)

    print("\n" + "=" * 80)
    print("TOP FILTER IDEAS (by difference)")
    print("=" * 80)
    for metric, op, val, diff in filter_ideas[:10]:
        print(f"  {metric} {op} {val:.2f} (diff: {diff:.2f})")

    # Test each filter idea
    print("\n" + "=" * 80)
    print("TESTING INDIVIDUAL FILTERS")
    print("=" * 80)

    print(f"\n{'Filter':<40} {'Trades':>7} {'Win%':>7} {'Losers':>7} {'AvgRet':>8}")
    print("-" * 70)

    for metric, op, val, _ in filter_ideas[:15]:
        if op == '>':
            filtered = df_trades[df_trades[metric] > val]
        else:
            filtered = df_trades[df_trades[metric] < val]

        if len(filtered) < 3:
            continue

        n_trades = len(filtered)
        n_winners = len(filtered[filtered['is_winner']])
        n_losers = n_trades - n_winners
        win_rate = n_winners / n_trades * 100
        avg_ret = filtered['return'].mean()

        print(f"{metric} {op} {val:.2f}".ljust(40) + f"{n_trades:>7} {win_rate:>6.1f}% {n_losers:>7} {avg_ret:>+7.2f}%")

    # Test combined filters
    print("\n" + "=" * 80)
    print("TESTING COMBINED FILTERS")
    print("=" * 80)

    combined_tests = [
        ('mom_1d > 0', lambda x: x['mom_1d'] > 0),
        ('mom_3d > 0', lambda x: x['mom_3d'] > 0),
        ('mom_5d > 0', lambda x: x['mom_5d'] > 0),
        ('dist_high_5d < 2', lambda x: x['dist_high_5d'] < 2),
        ('dist_high_20d < 5', lambda x: x['dist_high_20d'] < 5),
        ('atr_pct < 2', lambda x: x['atr_pct'] < 2),
        ('ma50_slope > 0', lambda x: x['ma50_slope'] > 0),
        ('mom_1d > 0 & mom_3d > 0', lambda x: (x['mom_1d'] > 0) & (x['mom_3d'] > 0)),
        ('dist_high_5d < 1 & mom_3d > 0', lambda x: (x['dist_high_5d'] < 1) & (x['mom_3d'] > 0)),
        ('vol_surge > 1.5 & mom_3d > 0', lambda x: (x['vol_surge'] > 1.5) & (x['mom_3d'] > 0)),
        ('atr_pct < 2.5 & mom_1d > 0', lambda x: (x['atr_pct'] < 2.5) & (x['mom_1d'] > 0)),
        ('ma50_slope > 0.5 & mom_3d > 0', lambda x: (x['ma50_slope'] > 0.5) & (x['mom_3d'] > 0)),
        ('Best: slope>0 & high<3 & mom3d>0', lambda x: (x['ma50_slope'] > 0) & (x['dist_high_5d'] < 3) & (x['mom_3d'] > 0)),
    ]

    print(f"\n{'Filter':<45} {'Trades':>7} {'Win%':>7} {'Losers':>7} {'AvgRet':>8}")
    print("-" * 75)

    for name, filter_func in combined_tests:
        filtered = df_trades[df_trades.apply(filter_func, axis=1)]
        if len(filtered) < 2:
            continue

        n_trades = len(filtered)
        n_winners = len(filtered[filtered['is_winner']])
        n_losers = n_trades - n_winners
        win_rate = n_winners / n_trades * 100
        avg_ret = filtered['return'].mean()

        marker = "✅" if n_losers == 0 else ("⭐" if n_losers <= 2 else "")
        print(f"{marker} {name:<43} {n_trades:>7} {win_rate:>6.1f}% {n_losers:>7} {avg_ret:>+7.2f}%")

    # Grid search for zero loser
    print("\n" + "=" * 80)
    print("GRID SEARCH FOR ZERO LOSER")
    print("=" * 80)

    best_zero_loser = None
    best_low_loser = None

    for mom_3d_min in [0, 0.5, 1, 1.5, 2]:
        for dist_high_max in [1, 1.5, 2, 3, 5]:
            for ma50_slope_min in [-1, 0, 0.2, 0.5, 1]:
                for atr_max in [1.5, 2, 2.5, 3, 5]:
                    filtered = df_trades[
                        (df_trades['mom_3d'] > mom_3d_min) &
                        (df_trades['dist_high_5d'] < dist_high_max) &
                        (df_trades['ma50_slope'] > ma50_slope_min) &
                        (df_trades['atr_pct'] < atr_max)
                    ]

                    if len(filtered) < 3:
                        continue

                    n_losers = len(filtered[~filtered['is_winner']])

                    if n_losers == 0:
                        if best_zero_loser is None or len(filtered) > best_zero_loser['trades']:
                            best_zero_loser = {
                                'mom_3d_min': mom_3d_min,
                                'dist_high_max': dist_high_max,
                                'ma50_slope_min': ma50_slope_min,
                                'atr_max': atr_max,
                                'trades': len(filtered),
                                'avg_return': filtered['return'].mean()
                            }
                    elif n_losers <= 2:
                        if best_low_loser is None or len(filtered) > best_low_loser['trades']:
                            best_low_loser = {
                                'mom_3d_min': mom_3d_min,
                                'dist_high_max': dist_high_max,
                                'ma50_slope_min': ma50_slope_min,
                                'atr_max': atr_max,
                                'trades': len(filtered),
                                'losers': n_losers,
                                'avg_return': filtered['return'].mean()
                            }

    if best_zero_loser:
        print(f"\n✅ ZERO LOSER FOUND!")
        print(f"   Mom 3d > {best_zero_loser['mom_3d_min']}%")
        print(f"   Dist from 5d high < {best_zero_loser['dist_high_max']}%")
        print(f"   MA50 slope > {best_zero_loser['ma50_slope_min']}%")
        print(f"   ATR % < {best_zero_loser['atr_max']}%")
        print(f"\n   Trades: {best_zero_loser['trades']}")
        print(f"   Avg Return: {best_zero_loser['avg_return']:+.2f}%")
    elif best_low_loser:
        print(f"\n⭐ LOW LOSER FOUND ({best_low_loser['losers']} losers):")
        print(f"   Mom 3d > {best_low_loser['mom_3d_min']}%")
        print(f"   Dist from 5d high < {best_low_loser['dist_high_max']}%")
        print(f"   MA50 slope > {best_low_loser['ma50_slope_min']}%")
        print(f"   ATR % < {best_low_loser['atr_max']}%")
        print(f"\n   Trades: {best_low_loser['trades']}")
        print(f"   Avg Return: {best_low_loser['avg_return']:+.2f}%")
    else:
        print("\n❌ No zero/low loser config found with these parameters")

    # Show the losers with their metrics
    print("\n" + "=" * 80)
    print("DETAILED LOSER ANALYSIS")
    print("=" * 80)

    print("\nAll losers and their metrics:")
    for _, r in losers.iterrows():
        date_str = r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date'])[:10]
        print(f"\n  {r['symbol']} {date_str} → {r['return']:+.2f}%")
        print(f"    RSI: {r['rsi']:.1f}, Accum: {r['accum']:.2f}, Vol: {r['vol_surge']:.2f}")
        print(f"    Mom 1d: {r['mom_1d']:+.2f}%, 3d: {r['mom_3d']:+.2f}%, 5d: {r['mom_5d']:+.2f}%")
        print(f"    Dist High 5d: {r['dist_high_5d']:.2f}%, ATR: {r['atr_pct']:.2f}%")
        print(f"    MA50 slope: {r['ma50_slope']:+.2f}%")


if __name__ == '__main__':
    main()
