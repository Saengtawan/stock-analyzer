#!/usr/bin/env python3
"""
BANKS ONLY BACKTEST

PROVEN: Finance_Banks has 62% WR with +1.19% avg return

Problem: Too many stop losses (33%) causing big drawdown months
Solution:
1. Focus ONLY on Banks (best subsector)
2. ULTRA strict volatility filter (ATR < 1.5%)
3. LIMIT trades to reduce drawdown exposure
4. Better timing (stricter entry criteria)

Goal: Reduce stop rate from 33% to <20% = better consistency
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    print("Need yfinance")
    sys.exit(1)


# BANKS ONLY - Most liquid, stable
UNIVERSE = [
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'TFC', 'COF',
    'MTB', 'FITB', 'RF', 'KEY', 'CFG', 'HBAN', 'ZION', 'CMA', 'FHN', 'ALLY',
]


def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_atr_pct(closes, highs, lows, period=14):
    if len(closes) < period + 1:
        return 5.0
    tr = []
    for i in range(-period, 0):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        ))
    atr = np.mean(tr)
    return (atr / closes[-1]) * 100


def detect_bank_opportunity(closes, highs, lows, volumes):
    """
    BANK OPPORTUNITY DETECTION - Ultra strict

    Criteria:
    1. ULTRA LOW volatility (ATR < 1.5%)
    2. Moderate momentum (2%-6%, not chasing)
    3. Volume confirmation
    4. RSI sweet spot (40-60)
    5. Above MA but not overextended
    """
    if len(closes) < 25:
        return None

    price = float(closes[-1])
    ma20 = np.mean(closes[-20:])
    rsi = calc_rsi(closes)
    atr_pct = calc_atr_pct(closes, highs, lows)

    # 5-day momentum
    ret_5d = (closes[-1] / closes[-5] - 1) * 100

    # Extended check
    above_ma = ((price - ma20) / ma20) * 100

    # Volume
    recent_vol = np.mean(volumes[-3:])
    avg_vol = np.mean(volumes[-20:-3])
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

    # ULTRA STRICT CRITERIA
    # 1. ULTRA LOW volatility (KEY for -3% SL)
    if atr_pct > 1.5:
        return None

    # 2. Moderate momentum (not chasing)
    if ret_5d < 2.0 or ret_5d > 6.0:
        return None

    # 3. Above MA but not overextended
    if above_ma < 1.0 or above_ma > 5.0:
        return None

    # 4. RSI sweet spot
    if rsi < 40 or rsi > 60:
        return None

    # 5. Volume confirmation
    if vol_ratio < 0.8:
        return None

    # Score
    score = 0
    score += 40  # Base score for passing strict criteria
    score += max(0, 20 - atr_pct * 10)  # Low vol bonus
    score += min(15, ret_5d * 3)  # Momentum
    score += min(10, vol_ratio * 5)  # Volume

    return {
        'score': score,
        'price': price,
        'ret_5d': ret_5d,
        'vol_ratio': vol_ratio,
        'rsi': rsi,
        'atr_pct': atr_pct,
        'above_ma': above_ma,
    }


def run_backtest():
    """Run banks only backtest"""
    print("=" * 80)
    print("BANKS ONLY BACKTEST")
    print("Focus on 62% WR subsector with ultra-strict volatility filter")
    print("=" * 80)

    print(f"\nBanks Universe: {len(UNIVERSE)} stocks")

    # Download data
    print("\nDownloading data...")
    all_symbols_str = ' '.join(UNIVERSE)
    data = yf.download(all_symbols_str, period='2y', progress=True, group_by='ticker')

    # Get SPY
    spy_data = yf.download('SPY', period='2y', progress=False)
    if isinstance(spy_data.columns, pd.MultiIndex):
        spy_data.columns = spy_data.columns.get_level_values(0)

    # Get VIX
    vix_data = yf.download('^VIX', period='2y', progress=False)
    if isinstance(vix_data.columns, pd.MultiIndex):
        vix_data.columns = vix_data.columns.get_level_values(0)

    # CONFIG - Ultra strict for consistency
    CONFIG = {
        'hold_days': 7,
        'stop_loss': -3.0,
        'target': 4.0,          # Lower target (more achievable)
        'top_n': 2,             # Only 2 trades per entry (limit exposure)
        'vix_max': 18,          # Very strict VIX
    }

    print(f"\nConfiguration (Ultra Strict):")
    print(f"  Hold: {CONFIG['hold_days']} days")
    print(f"  Stop: {CONFIG['stop_loss']}%")
    print(f"  Target: {CONFIG['target']}%")
    print(f"  VIX max: {CONFIG['vix_max']}")
    print(f"  Top N: {CONFIG['top_n']} (limited exposure)")

    # Backtest
    dates = spy_data.index[60:]
    entry_dates = dates[::3]  # Every 3 days

    all_trades = []
    monthly_returns = {}

    print(f"\nScanning {len(entry_dates)} opportunities...")

    for entry_date in entry_dates:
        try:
            entry_idx = list(spy_data.index).index(entry_date)

            # VIX filter (VERY STRICT)
            try:
                vix_val = float(vix_data['Close'].iloc[entry_idx])
                if vix_val > CONFIG['vix_max']:
                    continue
            except:
                vix_val = 16

            # SPY filter (strict - must be above MA)
            spy_prices = spy_data['Close'].iloc[:entry_idx+1]
            if len(spy_prices) < 20:
                continue
            spy_ma20 = float(spy_prices.tail(20).mean())
            spy_price = float(spy_prices.iloc[-1])
            if spy_price < spy_ma20:
                continue

            # SCAN for opportunities
            opportunities = []

            for symbol in UNIVERSE:
                try:
                    if symbol not in data.columns.get_level_values(0):
                        continue

                    stock_data = data[symbol].iloc[:entry_idx+1]
                    closes = stock_data['Close'].dropna().values
                    volumes = stock_data['Volume'].dropna().values
                    highs = stock_data['High'].dropna().values
                    lows = stock_data['Low'].dropna().values

                    if len(closes) < 25:
                        continue

                    # DETECT opportunity
                    result = detect_bank_opportunity(closes, highs, lows, volumes)

                    if result is not None:
                        opportunities.append({
                            'symbol': symbol,
                            **result
                        })

                except:
                    continue

            if not opportunities:
                continue

            # Select TOP opportunities
            opportunities.sort(key=lambda x: x['score'], reverse=True)
            picks = opportunities[:CONFIG['top_n']]

            # Simulate trades
            exit_idx = min(entry_idx + CONFIG['hold_days'], len(spy_data) - 1)

            for pick in picks:
                symbol = pick['symbol']
                entry_price = pick['price']

                try:
                    stock_future = data[symbol]['Close'].iloc[entry_idx:exit_idx+1]
                    stock_high = data[symbol]['High'].iloc[entry_idx:exit_idx+1]
                    stock_low = data[symbol]['Low'].iloc[entry_idx:exit_idx+1]

                    if len(stock_future) < 2:
                        continue

                    stop_price = entry_price * (1 + CONFIG['stop_loss'] / 100)
                    target_price = entry_price * (1 + CONFIG['target'] / 100)

                    exit_price = None
                    exit_reason = 'hold'

                    for i in range(1, len(stock_low)):
                        low = float(stock_low.iloc[i])
                        high = float(stock_high.iloc[i])

                        if low <= stop_price:
                            exit_price = stop_price
                            exit_reason = 'stop'
                            break
                        elif high >= target_price:
                            exit_price = target_price
                            exit_reason = 'target'
                            break

                    if exit_price is None:
                        exit_price = float(stock_future.iloc[-1])

                    ret = (exit_price / entry_price - 1) * 100

                    month_key = entry_date.strftime('%Y-%m')
                    if month_key not in monthly_returns:
                        monthly_returns[month_key] = []
                    monthly_returns[month_key].append(ret)

                    all_trades.append({
                        'date': entry_date.strftime('%Y-%m-%d'),
                        'symbol': symbol,
                        'ret_5d': pick['ret_5d'],
                        'score': pick['score'],
                        'entry': entry_price,
                        'exit': exit_price,
                        'return': ret,
                        'exit_reason': exit_reason,
                        'atr_pct': pick['atr_pct'],
                        'vix': vix_val,
                    })

                except:
                    continue

        except:
            continue

    # RESULTS
    print("\n" + "=" * 80)
    print("RESULTS - BANKS ONLY")
    print("=" * 80)

    if not all_trades:
        print("No trades executed")
        return

    df = pd.DataFrame(all_trades)

    print(f"\nTotal trades: {len(df)}")
    print(f"Win rate: {(df['return'] > 0).mean() * 100:.1f}%")
    print(f"Avg return: {df['return'].mean():.2f}%")
    print(f"Best trade: {df['return'].max():.2f}%")
    print(f"Worst trade: {df['return'].min():.2f}%")

    # Exit analysis
    print(f"\nExit Analysis:")
    for reason in ['target', 'stop', 'hold']:
        subset = df[df['exit_reason'] == reason]
        if len(subset) > 0:
            pct = len(subset)/len(df)*100
            print(f"  {reason}: {len(subset)} ({pct:.0f}%), avg {subset['return'].mean():.2f}%")

    # Stock analysis
    print(f"\nTop Stocks:")
    for symbol in df['symbol'].unique():
        subset = df[df['symbol'] == symbol]
        if len(subset) >= 3:
            print(f"  {symbol:5s}: {len(subset):3d} trades, avg {subset['return'].mean():+.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

    # Monthly
    print("\n" + "-" * 40)
    print("MONTHLY RETURNS")
    print("-" * 40)

    monthly_results = []
    for month, returns in sorted(monthly_returns.items()):
        avg_ret = np.mean(returns)
        total_ret = np.sum(returns)
        monthly_results.append({
            'month': month,
            'trades': len(returns),
            'avg_return': avg_ret,
            'total_return': total_ret,
        })
        status = "✓" if total_ret > 0 else "✗"
        print(f"{month}: {len(returns):3d} trades, avg {avg_ret:+.2f}%, total {total_ret:+7.2f}% {status}")

    if monthly_results:
        monthly_df = pd.DataFrame(monthly_results)

        print("\n" + "-" * 40)
        print("MONTHLY STATISTICS")
        print("-" * 40)
        print(f"Trades per month: {monthly_df['trades'].mean():.1f}")
        print(f"Avg return per trade: {df['return'].mean():.2f}%")
        print(f"Monthly total return avg: {monthly_df['total_return'].mean():.2f}%")
        print(f"Best month: {monthly_df['total_return'].max():.2f}%")
        print(f"Worst month: {monthly_df['total_return'].min():.2f}%")
        print(f"Positive months: {(monthly_df['total_return'] > 0).sum()}/{len(monthly_df)}")

        # Calculate consistency
        neg_months = monthly_df[monthly_df['total_return'] < 0]
        if len(neg_months) > 0:
            avg_neg = neg_months['total_return'].mean()
            print(f"Avg negative month: {avg_neg:.2f}%")

        # Summary
        print(f"\n{'='*50}")
        total_m = monthly_df['total_return'].mean()
        min_m = monthly_df['total_return'].min()

        print(f"SUMMARY:")
        print(f"  Avg return per trade: {df['return'].mean():.2f}%")
        print(f"  Trades per month: {monthly_df['trades'].mean():.1f}")
        print(f"  Monthly total return: {total_m:.2f}%")
        print(f"  Worst month total: {min_m:.2f}%")
        print(f"  Stop rate: {len(df[df['exit_reason'] == 'stop'])/len(df)*100:.0f}%")

        if total_m >= 10 and min_m >= -3:
            print("\n*** TARGET MET! ***")
        elif total_m >= 10 and min_m >= -10:
            print("\n*** CLOSE TO TARGET! Monthly OK, Worst Month needs work ***")
        else:
            print(f"\nTarget NOT met yet...")
            print(f"  Need: 10%+/month, worst >= -3%")
        print(f"{'='*50}")

    # Save
    df.to_csv('/tmp/banks_only_trades.csv', index=False)

    learnings = {
        'timestamp': datetime.now().isoformat(),
        'strategy': 'BANKS_ONLY',
        'config': CONFIG,
        'total_trades': len(df),
        'win_rate': float((df['return'] > 0).mean()),
        'avg_return': float(df['return'].mean()),
        'stop_rate': float(len(df[df['exit_reason'] == 'stop'])/len(df)),
        'monthly_total_avg': float(monthly_df['total_return'].mean()) if len(monthly_results) > 0 else 0,
        'worst_month': float(monthly_df['total_return'].min()) if len(monthly_results) > 0 else 0,
        'best_month': float(monthly_df['total_return'].max()) if len(monthly_results) > 0 else 0,
    }

    with open('/tmp/banks_only_learnings.json', 'w') as f:
        json.dump(learnings, f, indent=2)

    print(f"\nTrades saved to: /tmp/banks_only_trades.csv")
    print(f"Learnings saved to: /tmp/banks_only_learnings.json")

    return df, learnings


if __name__ == '__main__':
    run_backtest()
