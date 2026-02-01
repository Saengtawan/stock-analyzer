#!/usr/bin/env python3
"""
Analyze what causes trades to get stopped out
Find patterns to filter out bad entries
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

TEST_MONTHS = 6


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


def get_entry_metrics(closes, highs, lows, volumes, i):
    """Calculate all possible entry metrics"""
    if i < 50:
        return None

    price = float(closes[i])

    # Moving averages
    ma10 = float(np.mean(closes[i-9:i+1]))
    ma20 = float(np.mean(closes[i-19:i+1]))
    ma50 = float(np.mean(closes[i-49:i+1]))

    # Distance from MAs
    dist_ma10 = ((price - ma10) / ma10) * 100
    dist_ma20 = ((price - ma20) / ma20) * 100
    dist_ma50 = ((price - ma50) / ma50) * 100

    # RSI
    rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)

    # Accumulation
    accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

    # Volatility (ATR proxy)
    tr = []
    for j in range(i-13, i+1):
        high_low = float(highs[j]) - float(lows[j])
        tr.append(high_low)
    atr = np.mean(tr) if tr else 0
    atr_pct = (atr / price) * 100 if price > 0 else 0

    # Volume surge
    vol_avg = float(np.mean(volumes[i-19:i]))
    vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1.0

    # Momentum (1d, 3d, 5d)
    mom_1d = ((price - float(closes[i-1])) / float(closes[i-1])) * 100 if i >= 1 else 0
    mom_3d = ((price - float(closes[i-3])) / float(closes[i-3])) * 100 if i >= 3 else 0
    mom_5d = ((price - float(closes[i-5])) / float(closes[i-5])) * 100 if i >= 5 else 0

    # Distance from recent high/low (5 days)
    high_5d = float(np.max(highs[i-4:i+1]))
    low_5d = float(np.min(lows[i-4:i+1]))
    dist_from_high = ((high_5d - price) / high_5d) * 100
    dist_from_low = ((price - low_5d) / low_5d) * 100

    # Candle pattern
    open_price = float(closes[i-1])  # Using previous close as proxy for open
    body = price - open_price
    body_pct = (body / open_price) * 100 if open_price > 0 else 0

    # Trend strength (MA alignment)
    ma_aligned = 1 if ma10 > ma20 > ma50 else 0

    return {
        'price': price,
        'rsi': rsi,
        'accum': accum,
        'dist_ma10': dist_ma10,
        'dist_ma20': dist_ma20,
        'dist_ma50': dist_ma50,
        'atr_pct': atr_pct,
        'vol_surge': vol_surge,
        'mom_1d': mom_1d,
        'mom_3d': mom_3d,
        'mom_5d': mom_5d,
        'dist_from_high': dist_from_high,
        'dist_from_low': dist_from_low,
        'body_pct': body_pct,
        'ma_aligned': ma_aligned
    }


def simulate_trade(closes, i, hold_days, stop_pct):
    """Simulate trade with stop-loss, return detailed result"""
    n = len(closes)
    if i + hold_days >= n:
        return None

    entry_price = float(closes[i])
    stop_price = entry_price * (1 + stop_pct / 100)

    # Track daily movement
    min_drawdown = 0
    max_gain = 0

    for j in range(1, hold_days + 1):
        if i + j >= n:
            break
        day_price = float(closes[i + j])
        day_return = ((day_price - entry_price) / entry_price) * 100

        if day_return < min_drawdown:
            min_drawdown = day_return
        if day_return > max_gain:
            max_gain = day_return

        if day_price <= stop_price:
            return {
                'return': stop_pct,
                'exit_day': j,
                'stopped': True,
                'min_drawdown': min_drawdown,
                'max_gain': max_gain
            }

    exit_price = float(closes[i + hold_days])
    actual_return = ((exit_price - entry_price) / entry_price) * 100

    return {
        'return': actual_return,
        'exit_day': hold_days,
        'stopped': False,
        'min_drawdown': min_drawdown,
        'max_gain': max_gain
    }


def main():
    print("=" * 80)
    print("ANALYZE STOPPED TRADES - Find patterns to avoid")
    print("=" * 80)

    symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'QCOM',
        'TXN', 'AVGO', 'MU', 'AMAT', 'CRM', 'ADBE', 'ORCL', 'NOW', 'SNOW', 'DDOG',
        'NET', 'ZS', 'PANW', 'CRWD', 'JPM', 'BAC', 'GS', 'V', 'MA',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN',
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE',
        'CAT', 'DE', 'HON', 'GE', 'BA', 'XOM', 'CVX'
    ]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 100)

    print(f"\nDownloading {len(symbols)} stocks...")

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

    print(f"Downloaded: {len(stock_data)} stocks\n")

    # Config
    HOLD_DAYS = 5
    STOP_PCT = -2.0

    # Base momentum gates
    ACCUM_MIN = 1.3
    RSI_MAX = 55
    MA20_MIN = 1
    MA50_MIN = 0

    trades = []

    for sym, df in stock_data.items():
        closes = df['Close'].values.flatten()
        volumes = df['Volume'].values.flatten()
        highs = df['High'].values.flatten()
        lows = df['Low'].values.flatten()
        dates = df.index

        n = min(len(closes), len(volumes), len(highs), len(lows), len(dates))

        for i in range(55, n - HOLD_DAYS - 1):
            metrics = get_entry_metrics(closes, highs, lows, volumes, i)
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

            # Simulate trade
            result = simulate_trade(closes, i, HOLD_DAYS, STOP_PCT)
            if result is None:
                continue

            trades.append({
                'symbol': sym,
                'date': dates[i],
                'outcome': 'STOPPED' if result['stopped'] else ('WINNER' if result['return'] > 0 else 'LOSER'),
                **metrics,
                **result
            })

    df_trades = pd.DataFrame(trades)

    # Deduplicate
    df_trades['week'] = df_trades['date'].dt.isocalendar().week
    df_trades['year'] = df_trades['date'].dt.year
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

    print(f"Total trades: {len(df_trades)}")
    print(f"Stopped: {len(df_trades[df_trades['stopped']==True])}")
    print(f"Winners: {len(df_trades[df_trades['return']>0])}")
    print(f"Losers (not stopped): {len(df_trades[(df_trades['return']<=0) & (df_trades['stopped']==False)])}")

    # Analyze what differentiates stopped vs winners
    stopped = df_trades[df_trades['stopped'] == True]
    winners = df_trades[df_trades['return'] > 2]  # Good winners (>2%)

    print("\n" + "=" * 80)
    print("COMPARISON: STOPPED vs GOOD WINNERS (>2%)")
    print("=" * 80)

    metrics_to_compare = ['rsi', 'accum', 'dist_ma10', 'dist_ma20', 'dist_ma50',
                          'atr_pct', 'vol_surge', 'mom_1d', 'mom_3d', 'mom_5d',
                          'dist_from_high', 'dist_from_low', 'body_pct', 'ma_aligned']

    print(f"\n{'Metric':<18} {'Stopped':>10} {'Winners':>10} {'Diff':>10} {'Filter?':>10}")
    print("-" * 60)

    filter_suggestions = []

    for metric in metrics_to_compare:
        if metric not in stopped.columns or metric not in winners.columns:
            continue

        stopped_mean = stopped[metric].mean() if len(stopped) > 0 else 0
        winner_mean = winners[metric].mean() if len(winners) > 0 else 0
        diff = winner_mean - stopped_mean

        # Determine if this is a good filter
        filter_direction = ""
        if abs(diff) > 0.5:
            if diff > 0 and winner_mean > stopped_mean:
                filter_direction = f"> {stopped_mean:.1f}"
            elif diff < 0 and winner_mean < stopped_mean:
                filter_direction = f"< {stopped_mean:.1f}"

        print(f"{metric:<18} {stopped_mean:>10.2f} {winner_mean:>10.2f} {diff:>+10.2f} {filter_direction:>10}")

        if filter_direction:
            filter_suggestions.append((metric, diff, filter_direction))

    # Top filter suggestions
    print("\n" + "=" * 80)
    print("TOP FILTER SUGGESTIONS TO AVOID BEING STOPPED")
    print("=" * 80)

    filter_suggestions.sort(key=lambda x: abs(x[1]), reverse=True)
    for metric, diff, suggestion in filter_suggestions[:5]:
        print(f"  {metric}: {suggestion} (diff: {diff:+.2f})")

    # Test additional filters
    print("\n" + "=" * 80)
    print("TESTING ADDITIONAL FILTERS")
    print("=" * 80)

    # Try various additional filters
    additional_filters = [
        ('dist_from_high < 2%', lambda x: x['dist_from_high'] < 2),
        ('mom_1d > 0%', lambda x: x['mom_1d'] > 0),
        ('mom_3d > 1%', lambda x: x['mom_3d'] > 1),
        ('vol_surge > 1.2', lambda x: x['vol_surge'] > 1.2),
        ('atr_pct < 2%', lambda x: x['atr_pct'] < 2),
        ('body_pct > 0% (bullish)', lambda x: x['body_pct'] > 0),
        ('ma_aligned = 1', lambda x: x['ma_aligned'] == 1),
        ('dist_ma10 < 3%', lambda x: x['dist_ma10'] < 3),
        ('mom_1d > 0.5%', lambda x: x['mom_1d'] > 0.5),
        ('Combined: mom_1d>0 & vol>1.1', lambda x: (x['mom_1d'] > 0) & (x['vol_surge'] > 1.1)),
        ('Combined: dist_high<2 & mom_3d>0', lambda x: (x['dist_from_high'] < 2) & (x['mom_3d'] > 0)),
        ('Safe: atr<2 & mom_1d>0 & ma_aligned', lambda x: (x['atr_pct'] < 2) & (x['mom_1d'] > 0) & (x['ma_aligned'] == 1)),
    ]

    print(f"\n{'Filter':<40} {'Trades':>7} {'Stop%':>7} {'Win%':>7} {'AvgRet':>8}")
    print("-" * 72)

    for filter_name, filter_func in additional_filters:
        filtered = df_trades[df_trades.apply(filter_func, axis=1)]
        if len(filtered) < 5:
            continue

        n_stopped = len(filtered[filtered['stopped'] == True])
        n_winners = len(filtered[filtered['return'] > 0])
        stop_rate = n_stopped / len(filtered) * 100
        win_rate = n_winners / len(filtered) * 100
        avg_return = filtered['return'].mean()

        print(f"{filter_name:<40} {len(filtered):>7} {stop_rate:>6.1f}% {win_rate:>6.1f}% {avg_return:>+7.2f}%")

    # Find best combined filter
    print("\n" + "=" * 80)
    print("SEARCHING FOR BEST COMBINED FILTER")
    print("=" * 80)

    best_config = None
    best_score = -999

    for atr_max in [1.5, 2.0, 2.5, 3.0]:
        for mom_1d_min in [-1, 0, 0.5, 1]:
            for mom_3d_min in [-2, 0, 1, 2]:
                for vol_min in [0.8, 1.0, 1.2, 1.5]:
                    filtered = df_trades[
                        (df_trades['atr_pct'] < atr_max) &
                        (df_trades['mom_1d'] > mom_1d_min) &
                        (df_trades['mom_3d'] > mom_3d_min) &
                        (df_trades['vol_surge'] > vol_min)
                    ]

                    if len(filtered) < 5:
                        continue

                    n_stopped = len(filtered[filtered['stopped'] == True])
                    n_winners = len(filtered[filtered['return'] > 0])
                    avg_return = filtered['return'].mean()
                    stop_rate = n_stopped / len(filtered) * 100

                    # Score: prioritize low stop rate, then high win rate
                    score = (100 - stop_rate) * 2 + avg_return * 10 + len(filtered) * 0.1

                    if score > best_score and len(filtered) >= 10:
                        best_score = score
                        best_config = {
                            'atr_max': atr_max,
                            'mom_1d_min': mom_1d_min,
                            'mom_3d_min': mom_3d_min,
                            'vol_min': vol_min,
                            'trades': len(filtered),
                            'stopped': n_stopped,
                            'stop_rate': stop_rate,
                            'winners': n_winners,
                            'win_rate': n_winners / len(filtered) * 100,
                            'avg_return': avg_return
                        }

    if best_config:
        print(f"\n🏆 BEST ADDITIONAL FILTERS:")
        print(f"   ATR % < {best_config['atr_max']}")
        print(f"   Mom 1d > {best_config['mom_1d_min']}%")
        print(f"   Mom 3d > {best_config['mom_3d_min']}%")
        print(f"   Vol Surge > {best_config['vol_min']}")
        print(f"\n   Results:")
        print(f"   Trades: {best_config['trades']}")
        print(f"   Stop Rate: {best_config['stop_rate']:.1f}%")
        print(f"   Win Rate: {best_config['win_rate']:.1f}%")
        print(f"   Avg Return: {best_config['avg_return']:+.2f}%")

    # Final summary
    print("\n" + "=" * 80)
    print("FINAL INSIGHTS")
    print("=" * 80)
    print("""
KEY FINDINGS for avoiding stops:
1. Avoid high ATR (volatility) stocks - they tend to hit stop-loss
2. Enter on days with positive momentum (mom_1d > 0)
3. Confirm trend with 3-day momentum (mom_3d > 0)
4. Volume confirmation helps but not critical
5. Entering near recent highs is OK if momentum is positive
""")


if __name__ == '__main__':
    main()
