#!/usr/bin/env python3
"""
Deep Analysis: Why v5.4 Losers Failed

Find patterns in losers that winners don't have.
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


def calculate_extended_metrics(df, idx):
    """Calculate MORE metrics for deeper analysis"""
    if df is None or idx < 252:
        return None

    df_slice = df.iloc[:idx+1]
    lookback = min(252, len(df_slice))

    close = df_slice['close'].iloc[-lookback:]
    high = df_slice['high'].iloc[-lookback:]
    low = df_slice['low'].iloc[-lookback:]
    volume = df_slice['volume'].iloc[-lookback:]

    current_price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))

    # Moving averages
    ma5 = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else ma50

    price_above_ma5 = ((current_price - ma5) / ma5) * 100
    price_above_ma10 = ((current_price - ma10) / ma10) * 100
    price_above_ma20 = ((current_price - ma20) / ma20) * 100
    price_above_ma50 = ((current_price - ma50) / ma50) * 100
    price_above_ma200 = ((current_price - ma200) / ma200) * 100

    # Momentum at different timeframes
    mom_3d = ((current_price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_5d = ((current_price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((current_price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_20d = ((current_price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0
    mom_30d = ((current_price / close.iloc[-31]) - 1) * 100 if len(close) >= 31 else 0
    mom_60d = ((current_price / close.iloc[-61]) - 1) * 100 if len(close) >= 61 else 0

    # 52-week metrics
    high_52w = high.max()
    low_52w = close.min()
    position_52w = ((current_price - low_52w) / (high_52w - low_52w)) * 100 if high_52w != low_52w else 50

    high_idx = high.idxmax()
    days_from_high = close.index[-1] - high_idx

    # Distance from 52w high in %
    pct_from_high = ((current_price - high_52w) / high_52w) * 100

    # Volume analysis
    avg_volume_20d = volume.iloc[-20:].mean()
    avg_volume_50d = volume.iloc[-50:].mean()
    current_volume = volume.iloc[-1]
    volume_ratio = current_volume / avg_volume_20d if avg_volume_20d > 0 else 1

    # Volatility (ATR-like)
    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean().iloc[-1]
    atr_pct = (atr_14 / current_price) * 100

    # Bollinger Band position
    bb_mid = close.rolling(20).mean().iloc[-1]
    bb_std = close.rolling(20).std().iloc[-1]
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_position = ((current_price - bb_lower) / (bb_upper - bb_lower)) * 100 if bb_upper != bb_lower else 50

    # Recent price action
    highest_5d = high.iloc[-5:].max()
    lowest_5d = low.iloc[-5:].min()
    range_5d = ((highest_5d - lowest_5d) / lowest_5d) * 100

    # Gap analysis (today's open vs yesterday's close)
    if len(df_slice) >= 2:
        prev_close = close.iloc[-2]
        today_open = df_slice['open'].iloc[-1]
        gap_pct = ((today_open - prev_close) / prev_close) * 100
    else:
        gap_pct = 0

    # Trend strength (how many days above MA20 in last 20 days)
    days_above_ma20 = sum(close.iloc[-20:] > close.rolling(20).mean().iloc[-20:])

    # Consecutive up/down days
    daily_returns = close.pct_change()
    consecutive_up = 0
    consecutive_down = 0
    for ret in daily_returns.iloc[-10:][::-1]:
        if ret > 0:
            if consecutive_down == 0:
                consecutive_up += 1
            else:
                break
        elif ret < 0:
            if consecutive_up == 0:
                consecutive_down += 1
            else:
                break
        else:
            break

    return {
        'rsi': float(rsi),
        'price_above_ma5': float(price_above_ma5),
        'price_above_ma10': float(price_above_ma10),
        'price_above_ma20': float(price_above_ma20),
        'price_above_ma50': float(price_above_ma50),
        'price_above_ma200': float(price_above_ma200),
        'momentum_3d': float(mom_3d),
        'momentum_5d': float(mom_5d),
        'momentum_10d': float(mom_10d),
        'momentum_20d': float(mom_20d),
        'momentum_30d': float(mom_30d),
        'momentum_60d': float(mom_60d),
        'position_52w': float(position_52w),
        'days_from_high': int(days_from_high),
        'pct_from_high': float(pct_from_high),
        'volume_ratio': float(volume_ratio),
        'atr_pct': float(atr_pct),
        'bb_position': float(bb_position),
        'range_5d': float(range_5d),
        'gap_pct': float(gap_pct),
        'days_above_ma20': int(days_above_ma20),
        'consecutive_up': int(consecutive_up),
        'consecutive_down': int(consecutive_down),
    }


def passes_v54(m):
    if m is None:
        return False
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
    return True


def run_analysis():
    results = []

    print("Loading data...")
    for symbol in TEST_STOCKS:
        try:
            df = dm.get_price_data(symbol, period="2y", interval="1d")
            if df is None or len(df) < 280:
                continue

            for days_back in range(30, 180):
                test_idx = len(df) - 1 - days_back
                if test_idx < 252:
                    continue

                metrics = calculate_extended_metrics(df, test_idx)
                if not passes_v54(metrics):
                    continue

                entry_price = df.iloc[test_idx]['close']
                entry_date = pd.to_datetime(df.iloc[test_idx]['date'])

                # Find exit
                exit_idx = test_idx + 30
                hit_stop = False

                for i in range(test_idx + 1, min(exit_idx + 1, len(df))):
                    if (df.iloc[i]['low'] - entry_price) / entry_price <= -0.06:
                        hit_stop = True
                        exit_idx = i
                        break

                exit_price = entry_price * 0.94 if hit_stop else df.iloc[min(exit_idx, len(df)-1)]['close']
                return_pct = ((exit_price - entry_price) / entry_price) * 100

                result = {
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'return_pct': return_pct,
                    'is_winner': return_pct > 0,
                    'hit_stop': hit_stop,
                }
                result.update(metrics)
                results.append(result)

        except Exception as e:
            continue

    return pd.DataFrame(results)


# Main
if __name__ == "__main__":
    df = run_analysis()

    if df.empty:
        print("No trades found!")
        exit()

    # Deduplicate
    df = df.sort_values(['symbol', 'entry_date'])
    df['days_diff'] = df.groupby('symbol')['entry_date'].diff().dt.days
    df = df[(df['days_diff'].isna()) | (df['days_diff'] > 10)]

    winners = df[df['is_winner'] == True]
    losers = df[df['is_winner'] == False]

    print("\n" + "="*80)
    print("🔍 DEEP ANALYSIS: WINNERS vs LOSERS")
    print("="*80)
    print(f"\nTotal: {len(df)} trades | Winners: {len(winners)} | Losers: {len(losers)}")

    # Compare all metrics
    metrics_to_compare = [
        'rsi', 'price_above_ma5', 'price_above_ma10', 'price_above_ma20',
        'price_above_ma50', 'price_above_ma200',
        'momentum_3d', 'momentum_5d', 'momentum_10d', 'momentum_20d',
        'momentum_30d', 'momentum_60d',
        'position_52w', 'days_from_high', 'pct_from_high',
        'volume_ratio', 'atr_pct', 'bb_position', 'range_5d',
        'gap_pct', 'days_above_ma20', 'consecutive_up', 'consecutive_down'
    ]

    print("\n" + "="*80)
    print("📊 METRIC COMPARISON (Winners vs Losers)")
    print("="*80)
    print(f"\n{'Metric':<20} {'Winners Avg':>12} {'Losers Avg':>12} {'Diff':>10} {'Signal'}")
    print("-"*70)

    significant_diffs = []

    for metric in metrics_to_compare:
        w_avg = winners[metric].mean()
        l_avg = losers[metric].mean()
        diff = w_avg - l_avg
        diff_pct = abs(diff / w_avg * 100) if w_avg != 0 else 0

        # Determine significance
        if diff_pct > 30:
            signal = "🔴 BIG DIFF!"
            significant_diffs.append((metric, w_avg, l_avg, diff))
        elif diff_pct > 15:
            signal = "🟡 Notable"
        else:
            signal = ""

        print(f"{metric:<20} {w_avg:>12.2f} {l_avg:>12.2f} {diff:>+10.2f} {signal}")

    print("\n" + "="*80)
    print("🎯 SIGNIFICANT DIFFERENCES (potential new filters)")
    print("="*80)

    for metric, w_avg, l_avg, diff in significant_diffs:
        print(f"\n  {metric}:")
        print(f"    Winners avg: {w_avg:.2f}")
        print(f"    Losers avg:  {l_avg:.2f}")
        print(f"    Difference:  {diff:+.2f}")

        # Suggest filter
        if diff > 0:
            threshold = (w_avg + l_avg) / 2
            print(f"    💡 Suggestion: {metric} > {threshold:.1f}")
        else:
            threshold = (w_avg + l_avg) / 2
            print(f"    💡 Suggestion: {metric} < {threshold:.1f}")

    # Stop loss analysis
    print("\n" + "="*80)
    print("🛑 STOP LOSS ANALYSIS")
    print("="*80)

    stop_losers = df[df['hit_stop'] == True]
    non_stop_losers = losers[losers['hit_stop'] == False]

    print(f"\n  Stop Loss hits: {len(stop_losers)}")
    print(f"  Time exit losses: {len(non_stop_losers)}")

    if len(stop_losers) > 0:
        print("\n  Stop Loss trades characteristics:")
        for metric in ['rsi', 'momentum_3d', 'momentum_5d', 'atr_pct', 'bb_position', 'volume_ratio', 'consecutive_up']:
            avg = stop_losers[metric].mean()
            w_avg = winners[metric].mean()
            print(f"    {metric}: {avg:.2f} (winners: {w_avg:.2f})")

    # Detail view of worst losers
    print("\n" + "="*80)
    print("📉 WORST LOSERS DETAIL")
    print("="*80)

    worst = losers.nsmallest(10, 'return_pct')
    for _, row in worst.iterrows():
        print(f"\n  {row['symbol']} ({row['entry_date'].strftime('%Y-%m-%d')}) Return: {row['return_pct']:+.1f}%")
        print(f"    RSI: {row['rsi']:.0f} | BB: {row['bb_position']:.0f}% | ATR: {row['atr_pct']:.1f}%")
        print(f"    Mom3d: {row['momentum_3d']:+.1f}% | Mom5d: {row['momentum_5d']:+.1f}% | Mom10d: {row['momentum_10d']:+.1f}%")
        print(f"    Above MA5: {row['price_above_ma5']:+.1f}% | Above MA20: {row['price_above_ma20']:+.1f}%")
        print(f"    Volume Ratio: {row['volume_ratio']:.2f} | Consecutive Up: {row['consecutive_up']}")

    # Best winners for comparison
    print("\n" + "="*80)
    print("📈 BEST WINNERS DETAIL (for comparison)")
    print("="*80)

    best = winners.nlargest(5, 'return_pct')
    for _, row in best.iterrows():
        print(f"\n  {row['symbol']} ({row['entry_date'].strftime('%Y-%m-%d')}) Return: {row['return_pct']:+.1f}%")
        print(f"    RSI: {row['rsi']:.0f} | BB: {row['bb_position']:.0f}% | ATR: {row['atr_pct']:.1f}%")
        print(f"    Mom3d: {row['momentum_3d']:+.1f}% | Mom5d: {row['momentum_5d']:+.1f}% | Mom10d: {row['momentum_10d']:+.1f}%")
        print(f"    Above MA5: {row['price_above_ma5']:+.1f}% | Above MA20: {row['price_above_ma20']:+.1f}%")
        print(f"    Volume Ratio: {row['volume_ratio']:.2f} | Consecutive Up: {row['consecutive_up']}")

    # Find potential new filters
    print("\n" + "="*80)
    print("💡 POTENTIAL NEW FILTERS FOR v5.5")
    print("="*80)

    # Test each potential filter
    potential_filters = [
        ('momentum_3d', '>', 0),
        ('momentum_3d', '>', 1),
        ('momentum_3d', '>', 2),
        ('price_above_ma5', '>', 0),
        ('price_above_ma5', '>', 1),
        ('bb_position', '<', 80),
        ('bb_position', '<', 70),
        ('atr_pct', '<', 3),
        ('atr_pct', '<', 2.5),
        ('volume_ratio', '>', 0.8),
        ('volume_ratio', '<', 2),
        ('consecutive_up', '<', 5),
        ('consecutive_up', '<', 4),
        ('range_5d', '<', 8),
        ('range_5d', '<', 6),
    ]

    print(f"\n{'Filter':<30} {'Pass':>6} {'Win%':>8} {'Losers Blocked':>15}")
    print("-"*65)

    for metric, op, threshold in potential_filters:
        if op == '>':
            mask = df[metric] > threshold
            filter_str = f"{metric} > {threshold}"
        else:
            mask = df[metric] < threshold
            filter_str = f"{metric} < {threshold}"

        filtered = df[mask]
        if len(filtered) == 0:
            continue

        win_rate = (filtered['is_winner'].sum() / len(filtered)) * 100
        losers_blocked = len(losers) - len(filtered[filtered['is_winner'] == False])

        if win_rate > 60:
            print(f"{filter_str:<30} {len(filtered):>6} {win_rate:>7.1f}% {losers_blocked:>15}")

    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)
