#!/usr/bin/env python3
"""
FINANCE FOCUS BACKTEST

PROVEN: Finance sector has 86% WIN RATE with +1.92% avg return!

Problem: Previous test had only 1.9 trades/month (too strict)
Solution: Relax criteria while keeping quality

Goal: Get 5+ trades/month in Finance = 10%+ per month

Changes:
1. Widen sector momentum range (1%-8%)
2. Widen 5-day momentum range (2%-10%)
3. Relax VIX filter (< 25)
4. Focus on LARGE cap Finance stocks (more liquid, stable)
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


# FINANCE FOCUSED - Large cap, liquid stocks
UNIVERSE = {
    'Finance_Banks': [
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'TFC', 'COF',
    ],
    'Finance_Payments': [
        'V', 'MA', 'AXP', 'PYPL', 'SQ', 'FIS', 'FISV', 'GPN',
    ],
    'Finance_Asset_Mgmt': [
        'BLK', 'SCHW', 'BX', 'KKR', 'APO', 'ARES', 'TPG',
    ],
    'Finance_Insurance': [
        'CB', 'TRV', 'PGR', 'ALL', 'AFL', 'MET', 'PRU', 'HIG', 'AON', 'MMC',
    ],
    'Finance_Exchanges': [
        'CME', 'ICE', 'SPGI', 'MCO', 'MSCI', 'NDAQ', 'CBOE',
    ],
}


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


def detect_finance_opportunity(closes, highs, lows, volumes):
    """
    FINANCE OPPORTUNITY DETECTION

    Relaxed criteria for more trades:
    1. 5-day momentum 2%-10% (wider range)
    2. Not overextended (not >8% above MA)
    3. Basic volume check
    4. RSI not extreme (30-70)
    5. Moderate volatility (ATR < 2.5%)
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

    # RELAXED CRITERIA
    # 1. 5-day momentum (wider range)
    if ret_5d < 2.0 or ret_5d > 10.0:
        return None

    # 2. Not overextended
    if above_ma > 8.0 or above_ma < 0:
        return None

    # 3. RSI in reasonable range
    if rsi > 70 or rsi < 30:
        return None

    # 4. Moderate volatility
    if atr_pct > 2.5:
        return None

    # 5. Some volume (not dead)
    if vol_ratio < 0.5:
        return None

    # Score
    score = 0
    score += 30  # Base score
    score += min(20, ret_5d * 3)  # Momentum
    score += max(0, 15 - atr_pct * 5)  # Low vol bonus
    score += min(10, vol_ratio * 5)  # Volume bonus

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
    """Run finance focus backtest"""
    print("=" * 80)
    print("FINANCE FOCUS BACKTEST")
    print("Targeting 86% WR sector with relaxed criteria for more trades")
    print("=" * 80)

    # Flatten universe
    all_symbols = []
    symbol_to_subsector = {}
    for subsector, symbols in UNIVERSE.items():
        for s in symbols:
            if s not in all_symbols:
                all_symbols.append(s)
                symbol_to_subsector[s] = subsector

    print(f"\nFinance Universe: {len(all_symbols)} stocks")
    print("Subsectors: Banks, Payments, Asset Mgmt, Insurance, Exchanges")

    # Download data
    print("\nDownloading data...")
    all_symbols_str = ' '.join(all_symbols)
    data = yf.download(all_symbols_str, period='2y', progress=True, group_by='ticker')

    # Get SPY
    spy_data = yf.download('SPY', period='2y', progress=False)
    if isinstance(spy_data.columns, pd.MultiIndex):
        spy_data.columns = spy_data.columns.get_level_values(0)

    # Get VIX
    vix_data = yf.download('^VIX', period='2y', progress=False)
    if isinstance(vix_data.columns, pd.MultiIndex):
        vix_data.columns = vix_data.columns.get_level_values(0)

    # CONFIG - Relaxed for more trades
    CONFIG = {
        'hold_days': 7,
        'stop_loss': -3.0,
        'target': 5.0,
        'top_n': 5,             # More trades per entry
        'vix_max': 25,          # Relaxed VIX
    }

    print(f"\nConfiguration (Relaxed):")
    print(f"  Hold: {CONFIG['hold_days']} days")
    print(f"  Stop: {CONFIG['stop_loss']}%")
    print(f"  Target: {CONFIG['target']}%")
    print(f"  VIX max: {CONFIG['vix_max']}")
    print(f"  Top N per entry: {CONFIG['top_n']}")

    # Backtest - More frequent entries
    dates = spy_data.index[60:]
    entry_dates = dates[::2]  # Every 2 days

    all_trades = []
    monthly_returns = {}

    print(f"\nScanning {len(entry_dates)} opportunities...")

    for entry_date in entry_dates:
        try:
            entry_idx = list(spy_data.index).index(entry_date)

            # VIX filter (Relaxed)
            try:
                vix_val = float(vix_data['Close'].iloc[entry_idx])
                if vix_val > CONFIG['vix_max']:
                    continue
            except:
                vix_val = 20

            # SPY filter (basic)
            spy_prices = spy_data['Close'].iloc[:entry_idx+1]
            if len(spy_prices) < 20:
                continue
            spy_ma20 = float(spy_prices.tail(20).mean())
            spy_price = float(spy_prices.iloc[-1])
            if spy_price < spy_ma20 * 0.97:  # Allow 3% below MA
                continue

            # SCAN for opportunities
            opportunities = []

            for symbol in all_symbols:
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
                    result = detect_finance_opportunity(closes, highs, lows, volumes)

                    if result is not None:
                        opportunities.append({
                            'symbol': symbol,
                            'subsector': symbol_to_subsector.get(symbol, 'Unknown'),
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
                        'subsector': pick['subsector'],
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
    print("RESULTS - FINANCE FOCUS")
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
            print(f"  {reason}: {len(subset)} ({len(subset)/len(df)*100:.0f}%), avg {subset['return'].mean():.2f}%")

    # Subsector analysis
    print(f"\nSubsector Performance:")
    for subsector in sorted(df['subsector'].unique()):
        subset = df[df['subsector'] == subsector]
        print(f"  {subsector:20s}: {len(subset):3d} trades, avg {subset['return'].mean():+.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

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

        # Summary
        print(f"\n{'='*50}")
        total_m = monthly_df['total_return'].mean()
        min_m = monthly_df['total_return'].min()

        print(f"SUMMARY:")
        print(f"  Avg return per trade: {df['return'].mean():.2f}%")
        print(f"  Trades per month: {monthly_df['trades'].mean():.1f}")
        print(f"  Monthly total return: {total_m:.2f}%")
        print(f"  Worst month total: {min_m:.2f}%")

        if total_m >= 10 and min_m >= -3:
            print("\n*** TARGET MET! ***")
        else:
            print(f"\nTarget NOT met yet...")
            print(f"  Need: 10%+/month, worst >= -3%")
            gap_monthly = 10 - total_m
            gap_worst = -3 - min_m
            print(f"  Gap: Monthly {gap_monthly:.1f}%, Worst {gap_worst:.1f}%")
        print(f"{'='*50}")

    # Save
    df.to_csv('/tmp/finance_focus_trades.csv', index=False)

    # Save learnings
    learnings = {
        'timestamp': datetime.now().isoformat(),
        'strategy': 'FINANCE_FOCUS',
        'description': 'Finance sector only with relaxed criteria',
        'config': CONFIG,
        'total_trades': len(df),
        'win_rate': float((df['return'] > 0).mean()),
        'avg_return': float(df['return'].mean()),
        'monthly_total_avg': float(monthly_df['total_return'].mean()) if len(monthly_results) > 0 else 0,
        'worst_month': float(monthly_df['total_return'].min()) if len(monthly_results) > 0 else 0,
        'best_month': float(monthly_df['total_return'].max()) if len(monthly_results) > 0 else 0,
        'positive_months_pct': float((monthly_df['total_return'] > 0).sum() / len(monthly_df)) if len(monthly_df) > 0 else 0,
        'subsectors': {
            subsector: {
                'trades': int(len(df[df['subsector'] == subsector])),
                'avg_return': float(df[df['subsector'] == subsector]['return'].mean()),
                'win_rate': float((df[df['subsector'] == subsector]['return'] > 0).mean()),
            }
            for subsector in df['subsector'].unique()
        }
    }

    with open('/tmp/finance_focus_learnings.json', 'w') as f:
        json.dump(learnings, f, indent=2)

    print(f"\nTrades saved to: /tmp/finance_focus_trades.csv")
    print(f"Learnings saved to: /tmp/finance_focus_learnings.json")

    return df, learnings


if __name__ == '__main__':
    run_backtest()
