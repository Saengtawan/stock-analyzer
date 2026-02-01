#!/usr/bin/env python3
"""
DIFFERENT PERSPECTIVE BACKTEST - หามุมมองที่แตกต่างจากคนอื่น

Key Insights:
1. Most traders chase momentum AFTER it happens
2. We want to find stocks ABOUT TO move (leading signals)
3. Sector rotation: Always trade in THE BEST sector only
4. Low volatility stocks with -3% SL work better
5. Use 200+ stocks across all sectors

Different Perspective Approach:
1. SECTOR LEADER ONLY: Trade only top 1-2 sectors (not diversify)
2. RELATIVE STRENGTH: Find stocks outperforming their sector
3. ACCUMULATION BREAKOUT: Heavy buying before price move
4. LOW VOLATILITY: ATR < 2% works with -3% SL
5. EARLY CYCLE: Enter when sector just starts rotating up
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


# EXPANDED UNIVERSE - 200+ stocks across 11 sectors
UNIVERSE = {
    'Technology': [
        'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'CRM', 'ORCL', 'ADBE', 'INTC', 'CSCO',
        'IBM', 'NOW', 'INTU', 'PANW', 'SNOW', 'DDOG', 'ZS', 'CRWD', 'NET', 'PLTR',
    ],
    'Semiconductors': [
        'NVDA', 'AMD', 'AVGO', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'ADI',
        'MCHP', 'NXPI', 'ON', 'MRVL', 'SWKS', 'MPWR', 'ENTG', 'ASML',
    ],
    'Finance': [
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'TFC', 'COF',
        'AXP', 'V', 'MA', 'BLK', 'SCHW', 'CME', 'ICE', 'SPGI', 'MCO', 'MSCI',
    ],
    'Industrial': [
        'CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT', 'NOC', 'GD',
        'MMM', 'EMR', 'ETN', 'ITW', 'PH', 'ROK', 'FDX', 'UPS', 'CSX', 'NSC',
    ],
    'Healthcare': [
        'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY',
        'AMGN', 'GILD', 'VRTX', 'REGN', 'ISRG', 'MDT', 'SYK', 'ZBH', 'BSX', 'EW',
    ],
    'Consumer_Discretionary': [
        'HD', 'LOW', 'TJX', 'NKE', 'SBUX', 'MCD', 'YUM', 'CMG', 'DPZ', 'ORLY',
        'AZO', 'ROST', 'TGT', 'DG', 'DLTR', 'BBY', 'TSCO', 'ULTA', 'DECK', 'LULU',
    ],
    'Consumer_Staples': [
        'WMT', 'COST', 'PG', 'KO', 'PEP', 'PM', 'MO', 'CL', 'EL', 'KMB',
        'GIS', 'K', 'HSY', 'MDLZ', 'SJM', 'CAG', 'CPB', 'HRL', 'TSN', 'KHC',
    ],
    'Energy': [
        'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PXD', 'MPC', 'VLO', 'PSX', 'OXY',
        'DVN', 'HAL', 'BKR', 'FANG', 'HES', 'APA', 'OVV', 'CTRA', 'MTDR', 'TRGP',
    ],
    'Utilities': [
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'PEG',
        'WEC', 'ES', 'AWK', 'DTE', 'AEE', 'CMS', 'LNT', 'NI', 'EVRG', 'ATO',
    ],
    'Real_Estate': [
        'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'O', 'SPG', 'WELL', 'DLR', 'AVB',
        'EQR', 'VTR', 'ARE', 'MAA', 'UDR', 'ESS', 'INVH', 'SUI', 'ELS', 'SBAC',
    ],
    'Materials': [
        'LIN', 'APD', 'SHW', 'ECL', 'FCX', 'NEM', 'NUE', 'DOW', 'DD', 'PPG',
        'ALB', 'MLM', 'VMC', 'EMN', 'CE', 'IFF', 'FMC', 'MOS', 'CF', 'BALL',
    ],
}


def download_data(symbols, period='2y'):
    """Download all data"""
    print(f"Downloading {len(symbols)} stocks...")
    all_symbols = ' '.join(symbols)

    try:
        data = yf.download(all_symbols, period=period, progress=True, group_by='ticker')
        return data
    except Exception as e:
        print(f"Download error: {e}")
        return None


def calc_sector_momentum(data, sector_symbols, lookback=20):
    """Calculate sector momentum (average return of sector stocks)"""
    returns = []
    for symbol in sector_symbols:
        try:
            if symbol in data.columns.get_level_values(0):
                closes = data[symbol]['Close'].dropna()
                if len(closes) >= lookback:
                    ret = (closes.iloc[-1] / closes.iloc[-lookback] - 1) * 100
                    returns.append(ret)
        except:
            continue
    return np.mean(returns) if returns else 0


def calc_rsi(prices, period=14):
    """Calculate RSI"""
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


def calc_accumulation(closes, volumes, period=20):
    """Calculate accumulation ratio"""
    if len(closes) < period:
        return 1.0
    up_vol, down_vol = 0.0, 0.0
    for i in range(-period+1, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        elif closes[i] < closes[i-1]:
            down_vol += volumes[i]
    return up_vol / down_vol if down_vol > 0 else 3.0


def calc_atr_pct(closes, highs, lows, period=14):
    """Calculate ATR as percentage of price"""
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


def calc_relative_strength(stock_ret, sector_ret):
    """Calculate relative strength vs sector"""
    return stock_ret - sector_ret


def run_backtest():
    """Run the different perspective backtest"""
    print("=" * 80)
    print("DIFFERENT PERSPECTIVE BACKTEST")
    print("หามุมมองที่แตกต่างจากคนอื่น")
    print("=" * 80)

    # Flatten universe
    all_symbols = []
    symbol_to_sector = {}
    for sector, symbols in UNIVERSE.items():
        for s in symbols:
            all_symbols.append(s)
            symbol_to_sector[s] = sector

    print(f"\nUniverse: {len(all_symbols)} stocks across {len(UNIVERSE)} sectors")

    # Download data
    data = download_data(all_symbols, period='2y')
    if data is None:
        return

    # Get SPY for market filter
    spy_data = yf.download('SPY', period='2y', progress=False)
    if isinstance(spy_data.columns, pd.MultiIndex):
        spy_data.columns = spy_data.columns.get_level_values(0)

    # Get VIX for volatility filter
    vix_data = yf.download('^VIX', period='2y', progress=False)
    if isinstance(vix_data.columns, pd.MultiIndex):
        vix_data.columns = vix_data.columns.get_level_values(0)

    # CONFIGURATION - Different Perspective
    CONFIG = {
        'hold_days': 10,        # 10 days (2 weeks)
        'stop_loss': -3.0,      # Hard -3% SL
        'target': 8.0,          # +8% target
        'top_n': 3,             # Top 3 stocks only
        'atr_max': 2.0,         # LOW volatility only!
        'accum_min': 1.5,       # Strong buying
        'rsi_max': 55,
        'rsi_min': 35,
        'vix_max': 22,          # Strict VIX filter
        'sector_momentum_min': 2.0,  # Sector must be up 2%+
        'relative_strength_min': 1.0, # Must beat sector by 1%+
    }

    print(f"\nConfiguration (Different Perspective):")
    print(f"  Hold: {CONFIG['hold_days']} days")
    print(f"  Stop Loss: {CONFIG['stop_loss']}%")
    print(f"  Target: {CONFIG['target']}%")
    print(f"  ATR max: {CONFIG['atr_max']}% (LOW VOL ONLY)")
    print(f"  VIX max: {CONFIG['vix_max']}")
    print(f"  Sector Momentum min: {CONFIG['sector_momentum_min']}%")
    print(f"  Relative Strength min: {CONFIG['relative_strength_min']}%")

    # Backtest period
    dates = spy_data.index[60:]  # Skip first 60 days for warmup

    all_trades = []
    monthly_returns = {}

    # Simulate weekly entry (every 5 trading days)
    entry_dates = dates[::5]

    print(f"\nTesting {len(entry_dates)} entry points...")

    for entry_date in entry_dates:
        try:
            # Get entry date index
            entry_idx = list(spy_data.index).index(entry_date)

            # Check VIX filter
            try:
                vix_val = float(vix_data['Close'].iloc[entry_idx])
                if vix_val > CONFIG['vix_max']:
                    continue  # Skip high volatility periods
            except:
                vix_val = 20

            # Check SPY trend (bull filter)
            spy_prices = spy_data['Close'].iloc[:entry_idx+1]
            if len(spy_prices) < 50:
                continue
            spy_price = float(spy_prices.iloc[-1])
            spy_ma20 = float(spy_prices.tail(20).mean())
            spy_ma50 = float(spy_prices.tail(50).mean())

            if spy_price < spy_ma20 or spy_ma20 < spy_ma50:
                continue  # Not bull market

            # Calculate sector momentums
            sector_momentums = {}
            for sector, symbols in UNIVERSE.items():
                mom = calc_sector_momentum(data.iloc[:entry_idx+1], symbols, lookback=20)
                sector_momentums[sector] = mom

            # Get top 2 sectors (ONLY trade in leaders)
            top_sectors = sorted(sector_momentums.items(), key=lambda x: x[1], reverse=True)[:2]

            # Check if top sector meets minimum momentum
            if top_sectors[0][1] < CONFIG['sector_momentum_min']:
                continue  # No sector is strong enough

            # Scan stocks in top sectors only
            candidates = []

            for sector_name, sector_mom in top_sectors:
                for symbol in UNIVERSE[sector_name]:
                    try:
                        if symbol not in data.columns.get_level_values(0):
                            continue

                        stock_data = data[symbol].iloc[:entry_idx+1]
                        closes = stock_data['Close'].dropna().values
                        volumes = stock_data['Volume'].dropna().values
                        highs = stock_data['High'].dropna().values
                        lows = stock_data['Low'].dropna().values

                        if len(closes) < 55:
                            continue

                        price = float(closes[-1])

                        # Calculate indicators
                        rsi = calc_rsi(closes)
                        accum = calc_accumulation(closes, volumes)
                        atr_pct = calc_atr_pct(closes, highs, lows)

                        # Stock momentum
                        stock_ret = (closes[-1] / closes[-20] - 1) * 100

                        # Relative strength vs sector
                        rel_strength = calc_relative_strength(stock_ret, sector_mom)

                        # MA trend
                        ma20 = np.mean(closes[-20:])
                        above_ma20 = ((price - ma20) / ma20) * 100

                        # FILTERS (Different Perspective)
                        # 1. Low volatility (key for -3% SL)
                        if atr_pct > CONFIG['atr_max']:
                            continue

                        # 2. Strong accumulation
                        if accum < CONFIG['accum_min']:
                            continue

                        # 3. RSI in sweet spot
                        if rsi > CONFIG['rsi_max'] or rsi < CONFIG['rsi_min']:
                            continue

                        # 4. Above MA20
                        if above_ma20 < 2:
                            continue

                        # 5. Relative strength (beat sector)
                        if rel_strength < CONFIG['relative_strength_min']:
                            continue

                        # Score
                        score = 0
                        score += min(30, accum * 10)  # Accumulation
                        score += min(20, rel_strength * 5)  # Relative strength
                        score += max(0, 15 - atr_pct * 5)  # Low vol bonus
                        score += min(15, above_ma20 * 2)  # Trend

                        candidates.append({
                            'symbol': symbol,
                            'sector': sector_name,
                            'price': price,
                            'score': score,
                            'atr_pct': atr_pct,
                            'accum': accum,
                            'rsi': rsi,
                            'rel_strength': rel_strength,
                            'sector_mom': sector_mom,
                        })

                    except Exception as e:
                        continue

            if not candidates:
                continue

            # Select top N
            candidates.sort(key=lambda x: x['score'], reverse=True)
            picks = candidates[:CONFIG['top_n']]

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

                    # Check for stop loss hit
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
                        'entry': entry_price,
                        'exit': exit_price,
                        'return': ret,
                        'exit_reason': exit_reason,
                        'atr_pct': pick['atr_pct'],
                        'accum': pick['accum'],
                        'sector_mom': pick['sector_mom'],
                        'vix': vix_val,
                    })

                except Exception as e:
                    continue

        except Exception as e:
            continue

    # Print results
    print("\n" + "=" * 80)
    print("RESULTS - DIFFERENT PERSPECTIVE")
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
            print(f"  {reason}: {len(subset)} trades, avg {subset['return'].mean():.2f}%")

    # Monthly analysis
    print("\n" + "-" * 40)
    print("MONTHLY RETURNS")
    print("-" * 40)

    monthly_results = []
    for month, returns in sorted(monthly_returns.items()):
        avg_ret = np.mean(returns)
        monthly_results.append({
            'month': month,
            'trades': len(returns),
            'return': avg_ret,
        })
        print(f"{month}: {len(returns)} trades, {avg_ret:+.2f}%")

    if monthly_results:
        monthly_df = pd.DataFrame(monthly_results)

        print("\n" + "-" * 40)
        print("MONTHLY STATISTICS")
        print("-" * 40)
        print(f"Average monthly: {monthly_df['return'].mean():.2f}%")
        print(f"Best month: {monthly_df['return'].max():.2f}%")
        print(f"Worst month: {monthly_df['return'].min():.2f}%")
        print(f"Std dev: {monthly_df['return'].std():.2f}%")
        print(f"Positive months: {(monthly_df['return'] > 0).sum()}/{len(monthly_df)}")

        # Check if target met
        target_met = monthly_df['return'].mean() >= 10 and monthly_df['return'].min() >= -3
        print(f"\n{'='*40}")
        if target_met:
            print("TARGET MET!")
        else:
            print("Target NOT met yet...")
            print(f"  Need: 10%+ monthly avg, min month >= -3%")
            print(f"  Got: {monthly_df['return'].mean():.1f}% avg, min {monthly_df['return'].min():.1f}%")
        print(f"{'='*40}")

    # Sector analysis
    print("\n" + "-" * 40)
    print("SECTOR PERFORMANCE")
    print("-" * 40)
    for sector in df['sector'].unique():
        subset = df[df['sector'] == sector]
        print(f"{sector}: {len(subset)} trades, avg {subset['return'].mean():.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

    # Save results
    df.to_csv('/tmp/different_perspective_trades.csv', index=False)
    print(f"\nTrades saved to: /tmp/different_perspective_trades.csv")

    return df, monthly_df


if __name__ == '__main__':
    run_backtest()
