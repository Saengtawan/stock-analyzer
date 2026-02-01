#!/usr/bin/env python3
"""
VOL SPIKE FOCUS BACKTEST

KEY LEARNING: VOL_SPIKE pattern has 70% WIN RATE!

Strategy:
1. Focus ONLY on VOL_SPIKE pattern (proven 70% WR)
2. Trade only Utilities + Finance (best sectors)
3. Trade MORE FREQUENTLY to accumulate gains
4. AVOID Industrial (0% WR)

Goal: If we can make +2% per trade with 5+ trades/month = 10%+/month
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


# FOCUSED: Only sectors that work (Utilities 67% WR, Finance 56% WR)
UNIVERSE = {
    'Utilities': [
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'PEG',
        'WEC', 'ES', 'AWK', 'DTE', 'AEE', 'CMS', 'LNT', 'NI', 'EVRG', 'ATO',
        'FE', 'PPL', 'CNP', 'ETR', 'NRG', 'CEG', 'VST', 'PNW', 'IDA', 'OGE',
    ],
    'Finance_Stable': [
        'V', 'MA', 'CB', 'TRV', 'PGR', 'ALL', 'AFL', 'MET', 'PRU',
        'MMC', 'AON', 'WTW', 'SPGI', 'MCO', 'MSCI', 'ICE', 'CME', 'NDAQ', 'CBOE',
    ],
    'Healthcare': [
        'JNJ', 'UNH', 'ABT', 'MRK', 'LLY', 'TMO', 'DHR', 'ABBV', 'BMY', 'PFE',
        'AMGN', 'GILD', 'CI', 'HUM', 'CNC', 'CVS', 'MCK', 'CAH', 'VTRS', 'ZTS',
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


def detect_vol_spike(closes, volumes, highs, lows):
    """
    VOLUME SPIKE DETECTION - The winning pattern (70% WR)

    Criteria:
    1. Recent volume > 1.5x 20-day average
    2. Price closing higher (bullish volume)
    3. Low volatility (ATR < 2%)
    4. Not overbought (RSI < 65)
    5. In uptrend (above MA20)
    """
    if len(closes) < 25 or len(volumes) < 25:
        return None

    price = float(closes[-1])
    prev_price = float(closes[-2])
    ma20 = np.mean(closes[-20:])
    rsi = calc_rsi(closes)
    atr_pct = calc_atr_pct(closes, highs, lows)

    # Check for volume spike
    recent_vol = float(volumes[-1])
    avg_vol = np.mean(volumes[-21:-1])

    if avg_vol == 0:
        return None

    vol_ratio = recent_vol / avg_vol

    # CRITERIA for Vol Spike
    # 1. Volume > 1.5x average
    if vol_ratio < 1.5:
        return None

    # 2. Price closing higher (bullish)
    if price < prev_price:
        return None

    # 3. Low volatility
    if atr_pct > 2.0:
        return None

    # 4. Not overbought
    if rsi > 65:
        return None

    # 5. In uptrend
    if price < ma20:
        return None

    # Additional quality checks
    # 6. Not too far from MA (not overextended)
    above_ma = ((price - ma20) / ma20) * 100
    if above_ma > 8:  # Not more than 8% above MA
        return None

    # Score based on quality
    score = 0
    score += min(50, vol_ratio * 15)  # Volume ratio
    score += max(0, 25 - atr_pct * 10)  # Low vol bonus
    score += min(20, above_ma * 2)  # Trend strength

    return {
        'score': score,
        'price': price,
        'vol_ratio': vol_ratio,
        'rsi': rsi,
        'atr_pct': atr_pct,
        'above_ma': above_ma,
    }


def run_backtest():
    """Run vol spike focus backtest"""
    print("=" * 80)
    print("VOL SPIKE FOCUS BACKTEST")
    print("Focus on 70% Win Rate pattern")
    print("=" * 80)

    # Flatten universe
    all_symbols = []
    symbol_to_sector = {}
    for sector, symbols in UNIVERSE.items():
        for s in symbols:
            if s not in all_symbols:
                all_symbols.append(s)
                symbol_to_sector[s] = sector

    print(f"\nTargeted Universe: {len(all_symbols)} stocks")
    print("Focus: Utilities (67% WR), Finance (56% WR), Healthcare")

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

    # CONFIG - Optimized for Vol Spike
    CONFIG = {
        'hold_days': 10,        # 2 weeks
        'stop_loss': -3.0,
        'target': 6.0,          # Conservative target
        'top_n': 5,             # More trades
        'vix_max': 22,
    }

    print(f"\nConfiguration:")
    print(f"  Hold: {CONFIG['hold_days']} days")
    print(f"  Stop: {CONFIG['stop_loss']}%")
    print(f"  Target: {CONFIG['target']}%")
    print(f"  Top N: {CONFIG['top_n']}")

    # Backtest - MORE FREQUENT ENTRIES
    dates = spy_data.index[60:]
    entry_dates = dates[::2]  # Every 2 days for more opportunities

    all_trades = []
    monthly_returns = {}

    print(f"\nScanning {len(entry_dates)} opportunities...")

    for entry_date in entry_dates:
        try:
            entry_idx = list(spy_data.index).index(entry_date)

            # VIX filter
            try:
                vix_val = float(vix_data['Close'].iloc[entry_idx])
                if vix_val > CONFIG['vix_max']:
                    continue
            except:
                vix_val = 18

            # SPY filter (basic)
            spy_prices = spy_data['Close'].iloc[:entry_idx+1]
            if len(spy_prices) < 20:
                continue
            spy_ma20 = float(spy_prices.tail(20).mean())
            spy_price = float(spy_prices.iloc[-1])
            if spy_price < spy_ma20 * 0.98:  # Not more than 2% below MA20
                continue

            # SCAN for vol spike opportunities
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

                    # DETECT VOL SPIKE
                    result = detect_vol_spike(closes, volumes, highs, lows)

                    if result is not None:
                        opportunities.append({
                            'symbol': symbol,
                            'sector': symbol_to_sector.get(symbol, 'Unknown'),
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
                        'sector': pick['sector'],
                        'vol_ratio': pick['vol_ratio'],
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
    print("RESULTS - VOL SPIKE FOCUS")
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

    # Vol ratio analysis
    print(f"\nVolume Ratio Analysis:")
    for thresh in [1.5, 2.0, 2.5, 3.0]:
        subset = df[df['vol_ratio'] >= thresh]
        if len(subset) > 0:
            print(f"  Vol >= {thresh}x: {len(subset)} trades, avg {subset['return'].mean():.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

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

        # Sector analysis
        print("\n" + "-" * 40)
        print("SECTOR PERFORMANCE")
        print("-" * 40)
        for sector in sorted(df['sector'].unique()):
            subset = df[df['sector'] == sector]
            print(f"{sector:20s}: {len(subset):3d} trades, avg {subset['return'].mean():+.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

        # Check target
        print(f"\n{'='*50}")
        total_m = monthly_df['total_return'].mean()
        min_m = monthly_df['total_return'].min()

        print(f"SUMMARY:")
        print(f"  Avg return per trade: {df['return'].mean():.2f}%")
        print(f"  Trades per month: {monthly_df['trades'].mean():.1f}")
        print(f"  Monthly total return: {total_m:.2f}%")
        print(f"  Worst month total: {min_m:.2f}%")

        if total_m >= 10 and min_m >= -3:
            print("\nTARGET MET!")
        else:
            print(f"\nTarget NOT met yet...")
            print(f"  Need: 10%+/month, worst >= -3%")
        print(f"{'='*50}")

    # Save
    df.to_csv('/tmp/vol_spike_focus_trades.csv', index=False)
    print(f"\nTrades saved to: /tmp/vol_spike_focus_trades.csv")

    return df


if __name__ == '__main__':
    run_backtest()
