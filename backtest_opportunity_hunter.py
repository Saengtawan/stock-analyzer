#!/usr/bin/env python3
"""
OPPORTUNITY HUNTER - นักล่าโอกาส

Philosophy:
1. เราซื้อหุ้นเพื่อทำกำไร ไม่ใช่ซื้อหุ้นเดิมๆแล้วหวังว่ามันจะขึ้น
2. หาโอกาสว่าหุ้นตัวไหนจะทำกำไรให้เราได้แน่ๆ แล้วก็แค่ซื้อ
3. ไม่ยึดติดกับหุ้นตัวไหน
4. ไขว่คว้าหาประโยชน์

Approach:
- SCAN ทั้งตลาด หาหุ้นที่กำลังจะขึ้นแน่ๆ
- ไม่สนใจว่าเป็นหุ้นตัวไหน สนใจแค่ว่ามันจะขึ้น
- หา PATTERN ที่บอกว่าหุ้นกำลังจะ BREAKOUT

Key Patterns that predict imminent moves:
1. VOLUME EXPLOSION - Volume เพิ่ม 2x+ ก่อนราคาขึ้น
2. TIGHT CONSOLIDATION - ราคาแน่นมากก่อน breakout
3. ACCUMULATION SPIKE - มีการสะสมหนักมาก
4. SECTOR ROTATION IN - เงินไหลเข้า sector
5. EARNINGS BEAT MOMENTUM - หลังประกาศงบดีแล้วยังขึ้นต่อ
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


# MASSIVE UNIVERSE - 300+ stocks (all major sectors)
UNIVERSE = {
    'Technology': [
        'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'CRM', 'ORCL', 'ADBE', 'INTC', 'CSCO',
        'IBM', 'NOW', 'INTU', 'PANW', 'SNOW', 'DDOG', 'ZS', 'CRWD', 'NET', 'PLTR',
        'WDAY', 'TEAM', 'MDB', 'OKTA', 'ZM', 'TWLO', 'DOCU', 'VEEV', 'TTD', 'FTNT',
    ],
    'Semiconductors': [
        'NVDA', 'AMD', 'AVGO', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'ADI',
        'MCHP', 'NXPI', 'ON', 'MRVL', 'SWKS', 'MPWR', 'ENTG', 'ASML', 'TSM', 'SNPS',
    ],
    'Finance': [
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'TFC', 'COF',
        'AXP', 'V', 'MA', 'BLK', 'SCHW', 'CME', 'ICE', 'SPGI', 'MCO', 'MSCI',
        'CB', 'TRV', 'PGR', 'ALL', 'MET', 'AIG', 'PRU', 'AFL', 'HIG', 'AON',
    ],
    'Industrial': [
        'CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT', 'NOC', 'GD',
        'MMM', 'EMR', 'ETN', 'ITW', 'PH', 'ROK', 'FDX', 'UPS', 'CSX', 'NSC',
        'WM', 'RSG', 'URI', 'GWW', 'FAST', 'PWR', 'JCI', 'TT', 'CARR', 'OTIS',
    ],
    'Healthcare': [
        'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY',
        'AMGN', 'GILD', 'VRTX', 'REGN', 'ISRG', 'MDT', 'SYK', 'ZBH', 'BSX', 'EW',
        'HCA', 'CI', 'HUM', 'CNC', 'CVS', 'MCK', 'CAH', 'ABC', 'WBA', 'IQV',
    ],
    'Consumer_Discretionary': [
        'HD', 'LOW', 'TJX', 'NKE', 'SBUX', 'MCD', 'YUM', 'CMG', 'DPZ', 'ORLY',
        'AZO', 'ROST', 'TGT', 'DG', 'DLTR', 'BBY', 'TSCO', 'ULTA', 'DECK', 'LULU',
        'MAR', 'HLT', 'ABNB', 'BKNG', 'LVS', 'WYNN', 'MGM', 'RCL', 'CCL', 'NCLH',
    ],
    'Consumer_Staples': [
        'WMT', 'COST', 'PG', 'KO', 'PEP', 'PM', 'MO', 'CL', 'EL', 'KMB',
        'GIS', 'K', 'HSY', 'MDLZ', 'SJM', 'CAG', 'CPB', 'HRL', 'TSN', 'KHC',
        'STZ', 'TAP', 'BF.B', 'CHD', 'CLX', 'SYY', 'USFD', 'ADM', 'BG', 'INGR',
    ],
    'Energy': [
        'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PXD', 'MPC', 'VLO', 'PSX', 'OXY',
        'DVN', 'HAL', 'BKR', 'FANG', 'HES', 'APA', 'OVV', 'CTRA', 'MTDR', 'TRGP',
        'WMB', 'KMI', 'OKE', 'ET', 'LNG', 'EPD', 'MPLX', 'PAA', 'ENB', 'TRP',
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


def detect_volume_explosion(volumes, threshold=2.0):
    """Detect volume explosion - volume > 2x average"""
    if len(volumes) < 21:
        return False, 1.0
    recent_vol = volumes[-1]
    avg_vol = np.mean(volumes[-21:-1])
    ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
    return ratio >= threshold, ratio


def detect_tight_consolidation(closes, highs, lows, period=5):
    """Detect tight price consolidation - small range before breakout"""
    if len(closes) < period + 1:
        return False, 0
    recent_range = (max(highs[-period:]) - min(lows[-period:])) / closes[-1] * 100
    return recent_range < 3.0, recent_range  # Less than 3% range


def detect_accumulation_spike(closes, volumes, period=5):
    """Detect strong accumulation in recent days"""
    if len(closes) < period + 1:
        return False, 1.0
    up_vol, down_vol = 0, 0
    for i in range(-period, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        else:
            down_vol += volumes[i]
    ratio = up_vol / down_vol if down_vol > 0 else 3.0
    return ratio >= 2.0, ratio  # Up volume > 2x down volume


def detect_breakout_setup(closes, highs, lows, volumes):
    """
    OPPORTUNITY DETECTION - หาหุ้นที่กำลังจะขึ้น

    Criteria:
    1. Volume explosion OR tight consolidation
    2. Price above MA10 (short term trend)
    3. Recent accumulation
    4. Not overbought (RSI < 65)
    5. Low volatility (ATR < 2.5%)
    """
    if len(closes) < 30:
        return None

    # Basic calculations
    price = float(closes[-1])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:])
    rsi = calc_rsi(closes)
    atr_pct = calc_atr_pct(closes, highs, lows)

    # Pattern detections
    vol_explosion, vol_ratio = detect_volume_explosion(volumes)
    tight_consol, range_pct = detect_tight_consolidation(closes, highs, lows)
    accum_spike, accum_ratio = detect_accumulation_spike(closes, volumes)

    # FILTERS for opportunity
    # 1. Not too volatile (key for -3% SL)
    if atr_pct > 2.5:
        return None

    # 2. Not overbought
    if rsi > 65:
        return None

    # 3. Price above short-term MA
    if price < ma10:
        return None

    # 4. Must have at least ONE of these patterns
    has_pattern = vol_explosion or tight_consol or accum_spike
    if not has_pattern:
        return None

    # 5. Accumulation must be positive
    if accum_ratio < 1.2:
        return None

    # Score the opportunity
    score = 0
    patterns = []

    if vol_explosion:
        score += 30
        patterns.append(f'VOL_EXPLOSION({vol_ratio:.1f}x)')

    if tight_consol:
        score += 25
        patterns.append(f'TIGHT_RANGE({range_pct:.1f}%)')

    if accum_spike:
        score += 25
        patterns.append(f'ACCUMULATION({accum_ratio:.1f}x)')

    # Low volatility bonus
    if atr_pct < 1.5:
        score += 15
        patterns.append(f'LOW_VOL({atr_pct:.1f}%)')
    elif atr_pct < 2.0:
        score += 10

    # RSI in sweet spot
    if 40 <= rsi <= 55:
        score += 10

    return {
        'score': score,
        'patterns': patterns,
        'price': price,
        'rsi': rsi,
        'atr_pct': atr_pct,
        'vol_ratio': vol_ratio,
        'accum_ratio': accum_ratio,
        'range_pct': range_pct,
    }


def run_backtest():
    """Run the opportunity hunter backtest"""
    print("=" * 80)
    print("OPPORTUNITY HUNTER BACKTEST")
    print("นักล่าโอกาส - ไม่ยึดติด ไขว่คว้าหาประโยชน์")
    print("=" * 80)

    # Flatten universe
    all_symbols = []
    symbol_to_sector = {}
    for sector, symbols in UNIVERSE.items():
        for s in symbols:
            if s not in all_symbols:
                all_symbols.append(s)
                symbol_to_sector[s] = sector

    print(f"\nScanning {len(all_symbols)} stocks across {len(UNIVERSE)} sectors")
    print("Looking for: Volume Explosion, Tight Consolidation, Accumulation Spike")

    # Download data
    print("\nDownloading data...")
    all_symbols_str = ' '.join(all_symbols)
    data = yf.download(all_symbols_str, period='2y', progress=True, group_by='ticker')

    # Get SPY for market filter
    spy_data = yf.download('SPY', period='2y', progress=False)
    if isinstance(spy_data.columns, pd.MultiIndex):
        spy_data.columns = spy_data.columns.get_level_values(0)

    # Get VIX
    vix_data = yf.download('^VIX', period='2y', progress=False)
    if isinstance(vix_data.columns, pd.MultiIndex):
        vix_data.columns = vix_data.columns.get_level_values(0)

    # CONFIG
    CONFIG = {
        'hold_days': 7,         # Short hold - capture quick moves
        'stop_loss': -3.0,      # Hard -3% SL
        'target': 6.0,          # +6% target (conservative)
        'top_n': 5,             # Top 5 opportunities
        'vix_max': 22,          # Skip high volatility
    }

    print(f"\nConfiguration:")
    print(f"  Hold: {CONFIG['hold_days']} days")
    print(f"  Stop: {CONFIG['stop_loss']}%")
    print(f"  Target: {CONFIG['target']}%")
    print(f"  VIX max: {CONFIG['vix_max']}")

    # Backtest
    dates = spy_data.index[60:]
    entry_dates = dates[::3]  # Every 3 days (more frequent scanning)

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
                vix_val = 20

            # SPY filter (basic - not too restrictive)
            spy_prices = spy_data['Close'].iloc[:entry_idx+1]
            if len(spy_prices) < 20:
                continue
            spy_ma20 = float(spy_prices.tail(20).mean())
            spy_price = float(spy_prices.iloc[-1])
            if spy_price < spy_ma20 * 0.97:  # SPY not more than 3% below MA20
                continue

            # SCAN ALL STOCKS for opportunities
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

                    # DETECT OPPORTUNITY
                    opp = detect_breakout_setup(closes, highs, lows, volumes)

                    if opp is not None:
                        opportunities.append({
                            'symbol': symbol,
                            'sector': symbol_to_sector.get(symbol, 'Unknown'),
                            **opp
                        })

                except Exception as e:
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
    print("RESULTS - OPPORTUNITY HUNTER")
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

    # Pattern analysis
    print(f"\nPattern Analysis:")
    for pattern in ['VOL_EXPLOSION', 'TIGHT_RANGE', 'ACCUMULATION', 'LOW_VOL']:
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
        monthly_results.append({
            'month': month,
            'trades': len(returns),
            'return': avg_ret,
        })
        status = "✓" if avg_ret > 0 else "✗"
        print(f"{month}: {len(returns):3d} trades, {avg_ret:+6.2f}% {status}")

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

        # Sector analysis
        print("\n" + "-" * 40)
        print("SECTOR PERFORMANCE")
        print("-" * 40)
        for sector in sorted(df['sector'].unique()):
            subset = df[df['sector'] == sector]
            print(f"{sector:25s}: {len(subset):3d} trades, avg {subset['return'].mean():+.2f}%, WR {(subset['return'] > 0).mean()*100:.0f}%")

        # Check target
        print(f"\n{'='*40}")
        avg_m = monthly_df['return'].mean()
        min_m = monthly_df['return'].min()
        if avg_m >= 10 and min_m >= -3:
            print("TARGET MET!")
        else:
            print("Target NOT met yet...")
            print(f"  Need: 10%+ monthly avg, worst >= -3%")
            print(f"  Got: {avg_m:.1f}% avg, worst {min_m:.1f}%")
        print(f"{'='*40}")

    # Save
    df.to_csv('/tmp/opportunity_hunter_trades.csv', index=False)
    print(f"\nTrades saved to: /tmp/opportunity_hunter_trades.csv")

    return df


if __name__ == '__main__':
    run_backtest()
