#!/usr/bin/env python3
"""
MOMENTUM CONTINUATION BACKTEST

Philosophy: หาหุ้นที่กำลังวิ่งแล้วและจะวิ่งต่อ

Key Insight: Stocks in motion tend to stay in motion
- Stocks that just broke out often continue
- Stocks with strong recent momentum have higher chance of continuation
- But need to avoid chasing too late (overextended)

Strategy:
1. Find stocks with STRONG recent momentum (5-10 day return > 3%)
2. But NOT overextended (not >8% above MA)
3. With INCREASING volume (confirmation)
4. In the HOTTEST sector (sector rotation)
5. LOW volatility preferred

This is different from previous approaches:
- Instead of predicting breakouts, we RIDE existing momentum
- We're opportunity hunters: ไขว่คว้าหาประโยชน์
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


# LARGE UNIVERSE - All major stocks
UNIVERSE = {
    'Technology': [
        'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'CRM', 'ORCL', 'ADBE', 'INTC', 'CSCO',
        'IBM', 'NOW', 'INTU', 'PANW', 'SNOW', 'DDOG', 'ZS', 'CRWD', 'NET', 'PLTR',
    ],
    'Semiconductors': [
        'NVDA', 'AMD', 'AVGO', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'ADI',
        'MCHP', 'NXPI', 'ON', 'MRVL', 'SWKS',
    ],
    'Finance': [
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'TFC', 'COF',
        'AXP', 'V', 'MA', 'BLK', 'SCHW', 'CME', 'ICE', 'SPGI', 'MCO', 'MSCI',
    ],
    'Industrial': [
        'CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT', 'NOC', 'GD',
        'MMM', 'EMR', 'ETN', 'ITW', 'PH', 'WM', 'RSG', 'FDX', 'UPS', 'CSX',
    ],
    'Healthcare': [
        'JNJ', 'UNH', 'ABT', 'MRK', 'LLY', 'TMO', 'DHR', 'ABBV', 'BMY', 'PFE',
        'AMGN', 'GILD', 'CI', 'HUM', 'CVS', 'MCK', 'ZTS', 'ISRG', 'MDT', 'SYK',
    ],
    'Consumer': [
        'HD', 'LOW', 'TJX', 'NKE', 'SBUX', 'MCD', 'YUM', 'ROST', 'TGT', 'COST',
        'WMT', 'PG', 'KO', 'PEP', 'CL', 'EL', 'ORLY', 'AZO', 'LULU', 'DECK',
    ],
    'Energy': [
        'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'MPC', 'VLO', 'PSX', 'OXY', 'DVN',
    ],
    'Utilities': [
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'PEG',
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


def calc_sector_momentum(data, sector_symbols, entry_idx, lookback=10):
    """Calculate sector momentum"""
    returns = []
    for symbol in sector_symbols:
        try:
            if symbol in data.columns.get_level_values(0):
                closes = data[symbol]['Close'].iloc[:entry_idx+1].dropna().values
                if len(closes) >= lookback:
                    ret = (closes[-1] / closes[-lookback] - 1) * 100
                    returns.append(ret)
        except:
            continue
    return np.mean(returns) if returns else 0


def detect_momentum_continuation(closes, highs, lows, volumes):
    """
    MOMENTUM CONTINUATION DETECTION

    Criteria:
    1. Strong recent momentum (5-day return > 3%)
    2. Not overextended (not >8% above MA20)
    3. Volume confirmation (recent vol > avg)
    4. RSI not overbought (<70)
    5. ATR reasonable (<3%)
    """
    if len(closes) < 25:
        return None

    price = float(closes[-1])
    ma20 = np.mean(closes[-20:])
    rsi = calc_rsi(closes)
    atr_pct = calc_atr_pct(closes, highs, lows)

    # Recent momentum (5-day)
    ret_5d = (closes[-1] / closes[-5] - 1) * 100

    # Extended check
    above_ma = ((price - ma20) / ma20) * 100

    # Volume confirmation
    recent_vol = np.mean(volumes[-3:])
    avg_vol = np.mean(volumes[-20:-3])
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

    # CRITERIA for Momentum Continuation
    # 1. Strong recent momentum (but not too strong to be overextended)
    if ret_5d < 2.0 or ret_5d > 10.0:
        return None

    # 2. Not overextended
    if above_ma > 8.0:
        return None

    # 3. In uptrend
    if above_ma < 0:
        return None

    # 4. Volume confirmation
    if vol_ratio < 1.0:
        return None

    # 5. RSI not overbought
    if rsi > 70:
        return None

    # 6. Low to moderate volatility (prefer lower)
    if atr_pct > 3.0:
        return None

    # Score
    score = 0
    score += min(30, ret_5d * 5)  # Momentum score
    score += min(20, vol_ratio * 10)  # Volume confirmation
    score += max(0, 20 - rsi * 0.3)  # RSI room
    score += max(0, 15 - atr_pct * 5)  # Low vol bonus

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
    """Run momentum continuation backtest"""
    print("=" * 80)
    print("MOMENTUM CONTINUATION BACKTEST")
    print("หาหุ้นที่กำลังวิ่งแล้วและจะวิ่งต่อ")
    print("=" * 80)

    # Flatten universe
    all_symbols = []
    symbol_to_sector = {}
    for sector, symbols in UNIVERSE.items():
        for s in symbols:
            if s not in all_symbols:
                all_symbols.append(s)
                symbol_to_sector[s] = sector

    print(f"\nUniverse: {len(all_symbols)} stocks across {len(UNIVERSE)} sectors")

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

    # CONFIG
    CONFIG = {
        'hold_days': 5,         # Quick hold to capture continuation
        'stop_loss': -3.0,
        'target': 5.0,          # 5% target
        'top_n': 3,             # Top 3 only
        'vix_max': 22,
        'sector_min_mom': 2.0,  # Sector must be up 2%+
    }

    print(f"\nConfiguration:")
    print(f"  Hold: {CONFIG['hold_days']} days")
    print(f"  Stop: {CONFIG['stop_loss']}%")
    print(f"  Target: {CONFIG['target']}%")
    print(f"  Sector min momentum: {CONFIG['sector_min_mom']}%")

    # Backtest
    dates = spy_data.index[60:]
    entry_dates = dates[::3]  # Every 3 days

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

            # SPY filter
            spy_prices = spy_data['Close'].iloc[:entry_idx+1]
            if len(spy_prices) < 20:
                continue
            spy_ma20 = float(spy_prices.tail(20).mean())
            spy_price = float(spy_prices.iloc[-1])
            if spy_price < spy_ma20:
                continue

            # Calculate sector momentums
            sector_momentums = {}
            for sector, symbols in UNIVERSE.items():
                mom = calc_sector_momentum(data, symbols, entry_idx)
                sector_momentums[sector] = mom

            # Get top sectors (only trade in hot sectors)
            top_sectors = sorted(sector_momentums.items(), key=lambda x: x[1], reverse=True)

            # Filter sectors with min momentum
            hot_sectors = [(s, m) for s, m in top_sectors if m >= CONFIG['sector_min_mom']]

            if not hot_sectors:
                continue

            # SCAN for momentum continuation in HOT sectors
            opportunities = []

            for sector_name, sector_mom in hot_sectors[:3]:  # Top 3 sectors
                for symbol in UNIVERSE[sector_name]:
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

                        # DETECT momentum continuation
                        result = detect_momentum_continuation(closes, highs, lows, volumes)

                        if result is not None:
                            result['sector_mom'] = sector_mom
                            opportunities.append({
                                'symbol': symbol,
                                'sector': sector_name,
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
                        'ret_5d': pick['ret_5d'],
                        'sector_mom': pick['sector_mom'],
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
    print("RESULTS - MOMENTUM CONTINUATION")
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

    # Momentum range analysis
    print(f"\n5-Day Momentum Analysis:")
    for low, high in [(2, 4), (4, 6), (6, 8), (8, 10)]:
        subset = df[(df['ret_5d'] >= low) & (df['ret_5d'] < high)]
        if len(subset) > 0:
            print(f"  {low}%-{high}%: {len(subset)} trades, avg {subset['return'].mean():.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

    # Sector momentum analysis
    print(f"\nSector Momentum Analysis:")
    for low, high in [(2, 4), (4, 6), (6, 10)]:
        subset = df[(df['sector_mom'] >= low) & (df['sector_mom'] < high)]
        if len(subset) > 0:
            print(f"  Sector {low}%-{high}%: {len(subset)} trades, avg {subset['return'].mean():.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

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
            print(f"{sector:15s}: {len(subset):3d} trades, avg {subset['return'].mean():+.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

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
            print("\nTARGET MET!")
        else:
            print(f"\nTarget NOT met yet...")
            print(f"  Need: 10%+/month, worst >= -3%")
        print(f"{'='*50}")

    # Save learnings
    df.to_csv('/tmp/momentum_continuation_trades.csv', index=False)

    learnings = {
        'timestamp': datetime.now().isoformat(),
        'strategy': 'MOMENTUM_CONTINUATION',
        'config': CONFIG,
        'total_trades': len(df),
        'win_rate': (df['return'] > 0).mean(),
        'avg_return': df['return'].mean(),
        'monthly_total_avg': monthly_df['total_return'].mean() if len(monthly_results) > 0 else 0,
        'worst_month': monthly_df['total_return'].min() if len(monthly_results) > 0 else 0,
        'best_month': monthly_df['total_return'].max() if len(monthly_results) > 0 else 0,
        'sectors': {
            sector: {
                'trades': len(df[df['sector'] == sector]),
                'avg_return': df[df['sector'] == sector]['return'].mean(),
                'win_rate': (df[df['sector'] == sector]['return'] > 0).mean(),
            }
            for sector in df['sector'].unique()
        }
    }

    with open('/tmp/momentum_continuation_learnings.json', 'w') as f:
        json.dump(learnings, f, indent=2)

    print(f"\nTrades saved to: /tmp/momentum_continuation_trades.csv")
    print(f"Learnings saved to: /tmp/momentum_continuation_learnings.json")

    return df, learnings


if __name__ == '__main__':
    run_backtest()
