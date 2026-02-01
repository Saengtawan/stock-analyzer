#!/usr/bin/env python3
"""
ULTRA SELECTIVE BACKTEST - Based on Learnings

KEY LEARNINGS from previous tests:
1. Utilities sector: 72% Win Rate - THE BEST
2. Consumer Discretionary: +1.44% avg - Second best
3. LOW_VOL pattern works with -3% SL
4. TIGHT_RANGE pattern predicts breakouts
5. Too many trades = diluted returns

NEW STRATEGY:
1. SUPER LOW VOL only (ATR < 1.5%)
2. Focus on TOP 3 sectors: Utilities, Consumer Staples, Healthcare
3. Require MULTIPLE patterns (2+ patterns together)
4. Fewer trades, higher quality
5. Longer hold for bigger moves

Philosophy:
- บันทึกทุกอย่างเพื่อเรียนรู้
- ไม่ยึดติด หาโอกาส
- ผิดพลาดแล้วบันทึก สำเร็จก็บันทึก
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
    print("Need yfinance: pip install yfinance")
    sys.exit(1)


# FOCUSED UNIVERSE - Sectors that work + Low volatility stocks
UNIVERSE = {
    # TOP SECTOR: Utilities (72% WR)
    'Utilities': [
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'PEG',
        'WEC', 'ES', 'AWK', 'DTE', 'AEE', 'CMS', 'LNT', 'NI', 'EVRG', 'ATO',
        'FE', 'PPL', 'CNP', 'ETR', 'NRG', 'CEG', 'VST', 'PNW', 'IDA', 'OGE',
    ],
    # Consumer Staples (stable, low vol)
    'Consumer_Staples': [
        'WMT', 'COST', 'PG', 'KO', 'PEP', 'PM', 'MO', 'CL', 'EL', 'KMB',
        'GIS', 'K', 'HSY', 'MDLZ', 'SJM', 'CAG', 'CPB', 'HRL', 'TSN', 'KHC',
        'CHD', 'CLX', 'SYY', 'KR', 'MKC', 'LW', 'POST', 'CASY', 'USFD', 'PFGC',
    ],
    # Healthcare (stable)
    'Healthcare': [
        'JNJ', 'UNH', 'ABT', 'MRK', 'LLY', 'TMO', 'DHR', 'ABBV', 'BMY', 'PFE',
        'AMGN', 'GILD', 'CI', 'HUM', 'CNC', 'CVS', 'MCK', 'CAH', 'VTRS', 'ZTS',
    ],
    # Consumer Discretionary (high returns)
    'Consumer_Discretionary': [
        'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'DG', 'DLTR', 'BBY', 'TSCO', 'ORLY',
        'AZO', 'GPS', 'ANF', 'URBN', 'GRMN', 'POOL', 'WSM', 'RH', 'DECK', 'LULU',
    ],
    # Finance (some stable ones)
    'Finance_Stable': [
        'BRK.B', 'V', 'MA', 'CB', 'TRV', 'PGR', 'ALL', 'AFL', 'MET', 'PRU',
        'MMC', 'AON', 'WTW', 'SPGI', 'MCO', 'MSCI', 'ICE', 'CME', 'NDAQ', 'CBOE',
    ],
    # Industrial (some stable ones)
    'Industrial_Stable': [
        'WM', 'RSG', 'HON', 'MMM', 'EMR', 'ITW', 'PH', 'ROK', 'CMI', 'PCAR',
        'GWW', 'FAST', 'LIN', 'APD', 'SHW', 'ECL', 'PPG', 'CHRW', 'JBHT', 'EXPD',
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


def detect_ultra_patterns(closes, highs, lows, volumes):
    """
    Ultra selective pattern detection

    Requirements:
    1. SUPER LOW VOL (ATR < 1.5%)
    2. At least 2 patterns present
    3. No overbought/oversold
    """
    if len(closes) < 30:
        return None

    price = float(closes[-1])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:])
    rsi = calc_rsi(closes)
    atr_pct = calc_atr_pct(closes, highs, lows)

    # SUPER STRICT: Only ultra-low volatility
    if atr_pct > 1.5:
        return None

    # Not overbought or oversold
    if rsi > 60 or rsi < 35:
        return None

    # Must be in uptrend
    if price < ma20:
        return None

    # Pattern detection
    patterns = []
    score = 0

    # Pattern 1: Volume spike (recent vol > 1.5x avg)
    if len(volumes) > 20:
        recent_vol = np.mean(volumes[-3:])
        avg_vol = np.mean(volumes[-20:-3])
        if avg_vol > 0 and recent_vol / avg_vol >= 1.5:
            patterns.append(f'VOL_SPIKE({recent_vol/avg_vol:.1f}x)')
            score += 25

    # Pattern 2: Tight consolidation (5-day range < 2%)
    if len(closes) > 5:
        range_5d = (max(highs[-5:]) - min(lows[-5:])) / price * 100
        if range_5d < 2.0:
            patterns.append(f'TIGHT({range_5d:.1f}%)')
            score += 25

    # Pattern 3: Accumulation (up vol > down vol)
    if len(closes) > 10:
        up_vol, down_vol = 0, 0
        for i in range(-10, 0):
            if closes[i] > closes[i-1]:
                up_vol += volumes[i]
            else:
                down_vol += volumes[i]
        if down_vol > 0:
            accum = up_vol / down_vol
            if accum >= 1.5:
                patterns.append(f'ACCUM({accum:.1f}x)')
                score += 20

    # Pattern 4: Rising MA (MA10 > MA20 and both rising)
    if len(closes) > 25:
        ma10_5d_ago = np.mean(closes[-15:-5])
        ma20_5d_ago = np.mean(closes[-25:-5])
        if ma10 > ma10_5d_ago and ma20 > ma20_5d_ago and ma10 > ma20:
            patterns.append('RISING_MA')
            score += 15

    # Pattern 5: Near breakout (within 1% of recent high)
    if len(highs) > 20:
        recent_high = max(highs[-20:])
        pct_from_high = (recent_high - price) / price * 100
        if pct_from_high < 1.0:
            patterns.append(f'NEAR_HIGH({pct_from_high:.1f}%)')
            score += 20

    # REQUIRE at least 2 patterns
    if len(patterns) < 2:
        return None

    # Low volatility bonus
    if atr_pct < 1.0:
        score += 15
        patterns.append(f'ULTRA_LOW_VOL({atr_pct:.2f}%)')

    return {
        'score': score,
        'patterns': patterns,
        'price': price,
        'rsi': rsi,
        'atr_pct': atr_pct,
        'above_ma20': ((price - ma20) / ma20) * 100,
    }


def run_backtest():
    """Run ultra selective backtest"""
    print("=" * 80)
    print("ULTRA SELECTIVE BACKTEST")
    print("Based on learnings: Utilities 72% WR, Low Vol works")
    print("=" * 80)

    # Flatten universe
    all_symbols = []
    symbol_to_sector = {}
    for sector, symbols in UNIVERSE.items():
        for s in symbols:
            if s not in all_symbols:
                all_symbols.append(s)
                symbol_to_sector[s] = sector

    print(f"\nFocused Universe: {len(all_symbols)} stocks across {len(UNIVERSE)} sectors")
    print("Focus: Utilities, Consumer Staples, Healthcare, Consumer Discretionary")

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

    # CONFIG - Ultra Selective
    CONFIG = {
        'hold_days': 14,        # 2 weeks hold
        'stop_loss': -3.0,
        'target': 8.0,          # Higher target
        'top_n': 3,             # Only top 3
        'vix_max': 20,          # Stricter VIX
        'atr_max': 1.5,         # Ultra low vol
    }

    print(f"\nUltra Selective Configuration:")
    print(f"  Hold: {CONFIG['hold_days']} days")
    print(f"  Stop: {CONFIG['stop_loss']}%")
    print(f"  Target: {CONFIG['target']}%")
    print(f"  ATR max: {CONFIG['atr_max']}% (ULTRA LOW VOL)")
    print(f"  VIX max: {CONFIG['vix_max']}")
    print(f"  Top N: {CONFIG['top_n']}")

    # Backtest
    dates = spy_data.index[60:]
    entry_dates = dates[::5]  # Weekly entries

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

            # SCAN for ultra-quality opportunities
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

                    if len(closes) < 30:
                        continue

                    # DETECT ultra patterns
                    result = detect_ultra_patterns(closes, highs, lows, volumes)

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
                        'patterns': ','.join(pick['patterns']),
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
    print("RESULTS - ULTRA SELECTIVE")
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

    # Pattern analysis
    print(f"\nPattern Analysis:")
    for pattern in ['VOL_SPIKE', 'TIGHT', 'ACCUM', 'RISING_MA', 'NEAR_HIGH', 'ULTRA_LOW_VOL']:
        subset = df[df['patterns'].str.contains(pattern)]
        if len(subset) > 0:
            print(f"  {pattern}: {len(subset)} trades, avg {subset['return'].mean():.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

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
        status = "✓" if avg_ret > 0 else "✗"
        print(f"{month}: {len(returns):3d} trades, avg {avg_ret:+6.2f}%, total {total_ret:+7.2f}% {status}")

    if monthly_results:
        monthly_df = pd.DataFrame(monthly_results)

        print("\n" + "-" * 40)
        print("MONTHLY STATISTICS")
        print("-" * 40)
        print(f"Average monthly return: {monthly_df['avg_return'].mean():.2f}%")
        print(f"Average monthly total: {monthly_df['total_return'].mean():.2f}%")
        print(f"Best month: {monthly_df['avg_return'].max():.2f}%")
        print(f"Worst month: {monthly_df['avg_return'].min():.2f}%")
        print(f"Std dev: {monthly_df['avg_return'].std():.2f}%")
        print(f"Positive months: {(monthly_df['avg_return'] > 0).sum()}/{len(monthly_df)}")

        # Sector analysis
        print("\n" + "-" * 40)
        print("SECTOR PERFORMANCE")
        print("-" * 40)
        for sector in sorted(df['sector'].unique()):
            subset = df[df['sector'] == sector]
            print(f"{sector:25s}: {len(subset):3d} trades, avg {subset['return'].mean():+.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

        # Check target
        print(f"\n{'='*50}")
        avg_m = monthly_df['avg_return'].mean()
        min_m = monthly_df['avg_return'].min()
        total_m = monthly_df['total_return'].mean()

        print(f"SUMMARY:")
        print(f"  Avg return per trade: {df['return'].mean():.2f}%")
        print(f"  Monthly avg return: {avg_m:.2f}%")
        print(f"  Monthly total return: {total_m:.2f}%")
        print(f"  Worst month: {min_m:.2f}%")

        if avg_m >= 10 and min_m >= -3:
            print("\nTARGET MET!")
        elif total_m >= 10 and min_m >= -3:
            print("\nTARGET MET (by total)!")
        else:
            print(f"\nTarget NOT met yet...")
            print(f"  Need: 10%+ monthly, worst >= -3%")
        print(f"{'='*50}")

    # Save all data
    df.to_csv('/tmp/ultra_selective_trades.csv', index=False)

    # Save detailed learnings
    learnings = {
        'timestamp': datetime.now().isoformat(),
        'config': CONFIG,
        'total_trades': len(df),
        'win_rate': (df['return'] > 0).mean(),
        'avg_return': df['return'].mean(),
        'monthly_avg': monthly_df['avg_return'].mean() if len(monthly_results) > 0 else 0,
        'monthly_total_avg': monthly_df['total_return'].mean() if len(monthly_results) > 0 else 0,
        'worst_month': monthly_df['avg_return'].min() if len(monthly_results) > 0 else 0,
        'best_month': monthly_df['avg_return'].max() if len(monthly_results) > 0 else 0,
        'exit_analysis': {
            'target_pct': len(df[df['exit_reason'] == 'target']) / len(df) * 100,
            'stop_pct': len(df[df['exit_reason'] == 'stop']) / len(df) * 100,
            'hold_pct': len(df[df['exit_reason'] == 'hold']) / len(df) * 100,
        },
        'sector_performance': {
            sector: {
                'trades': len(df[df['sector'] == sector]),
                'avg_return': df[df['sector'] == sector]['return'].mean(),
                'win_rate': (df[df['sector'] == sector]['return'] > 0).mean(),
            }
            for sector in df['sector'].unique()
        },
    }

    with open('/tmp/ultra_selective_learnings.json', 'w') as f:
        json.dump(learnings, f, indent=2)

    print(f"\nTrades saved to: /tmp/ultra_selective_trades.csv")
    print(f"Learnings saved to: /tmp/ultra_selective_learnings.json")

    return df, learnings


if __name__ == '__main__':
    run_backtest()
