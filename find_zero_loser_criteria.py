#!/usr/bin/env python3
"""
GOAL: Find criteria that gives ALMOST ZERO LOSERS
Strategy: Huge universe + Very strict criteria = Quality picks only

1. Use 300+ stocks universe
2. Analyze ALL metrics of winners vs losers
3. Find filters that eliminate losers without killing winners
4. Test combinations to find optimal "zero loser" setup
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from api.data_manager import DataManager

dm = DataManager()

# HUGE UNIVERSE - 300+ stocks
STOCKS = [
    # Mega Cap Tech
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD',
    # Enterprise Tech
    'ORCL', 'CRM', 'ADBE', 'NOW', 'IBM', 'CSCO', 'ACN', 'INTU', 'UBER', 'SQ',
    # Semiconductors
    'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'NXPI', 'MCHP', 'ADI',
    'ON', 'SWKS', 'MPWR', 'MRVL', 'SNPS', 'CDNS', 'ASML', 'TSM',
    # Cloud/SaaS
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    'ZM', 'DOCU', 'TWLO', 'OKTA', 'TEAM', 'SPLK', 'WDAY', 'VEEV', 'HUBS', 'BILL',
    # Streaming/Media
    'NFLX', 'DIS', 'CMCSA', 'WBD', 'PARA', 'ROKU', 'SPOT',
    # Social/Gaming
    'SNAP', 'PINS', 'RBLX', 'EA', 'TTWO', 'U',
    # E-commerce
    'EBAY', 'ETSY', 'W', 'CHWY', 'WISH', 'MELI', 'SE',
    # Fintech
    'V', 'MA', 'AXP', 'COIN', 'HOOD', 'AFRM', 'SOFI', 'UPST',
    # Banks
    'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC', 'USB', 'PNC', 'TFC', 'SCHW',
    # Insurance
    'BRK-B', 'AIG', 'MET', 'PRU', 'ALL', 'TRV', 'PGR', 'CB',
    # Healthcare
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'CVS', 'CI', 'HUM', 'ELV', 'GILD', 'REGN', 'VRTX', 'BIIB', 'MRNA', 'AMGN',
    'BMY', 'ZTS', 'SYK', 'BSX', 'MDT', 'EW', 'DXCM', 'IDXX', 'IQV',
    # Consumer Retail
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'DG', 'DLTR', 'BBY',
    'LULU', 'ULTA', 'NKE', 'GPS', 'ANF', 'AEO', 'URBN', 'FIVE', 'ORLY', 'AZO',
    # Food & Beverage
    'SBUX', 'MCD', 'CMG', 'DPZ', 'YUM', 'QSR', 'DNUT', 'SHAK',
    'KO', 'PEP', 'MNST', 'KDP', 'STZ', 'TAP', 'SAM',
    # Consumer Staples
    'PG', 'CL', 'KMB', 'CLX', 'CHD', 'EL', 'KVUE',
    # Industrial
    'CAT', 'DE', 'HON', 'GE', 'MMM', 'EMR', 'ROK', 'ETN', 'PH', 'ITW',
    'RTX', 'LMT', 'NOC', 'BA', 'GD', 'HII', 'LHX', 'TDG',
    'UPS', 'FDX', 'XPO', 'JBHT', 'CHRW', 'EXPD',
    # Transportation
    'DAL', 'UAL', 'LUV', 'AAL', 'ALK', 'JBLU',
    # Energy
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX', 'HAL',
    'DVN', 'FANG', 'PXD', 'HES', 'MRO', 'APA',
    # Utilities
    'NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE', 'XEL', 'WEC', 'ED',
    # REITs
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'O', 'WELL', 'DLR', 'SPG', 'AVB',
    # China/Intl
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI', 'TME', 'BILI',
    # Travel
    'ABNB', 'BKNG', 'EXPE', 'MAR', 'HLT', 'H', 'RCL', 'CCL', 'NCLH',
    # Auto
    'F', 'GM', 'RIVN', 'LCID', 'TM', 'HMC',
    # Telecom
    'VZ', 'T', 'TMUS',
    # Materials
    'LIN', 'APD', 'SHW', 'ECL', 'DD', 'NEM', 'FCX', 'GOLD',
    # Speculative Growth
    'PATH', 'CFLT', 'GTLB', 'DOMO', 'MQ', 'ESTC', 'FIVN', 'RNG',
    'DASH', 'LYFT', 'GRAB', 'TTD', 'APPS', 'PAYC', 'PCTY',
]


def get_metrics(df, idx):
    """Calculate ALL possible metrics"""
    if idx < 60:
        return None

    close = df['close'].iloc[:idx+1]
    high = df['high'].iloc[:idx+1]
    low = df['low'].iloc[:idx+1]
    volume = df['volume'].iloc[:idx+1]
    open_p = df['open'].iloc[:idx+1]
    price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 0.0001)))

    # Moving Averages
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]

    above_ma10 = ((price - ma10) / ma10) * 100
    above_ma20 = ((price - ma20) / ma20) * 100
    above_ma50 = ((price - ma50) / ma50) * 100

    # MA Trend (is MA20 rising?)
    ma20_5d_ago = close.rolling(20).mean().iloc[-6]
    ma20_slope = ((ma20 - ma20_5d_ago) / ma20_5d_ago) * 100

    # Volume
    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    # Momentum (multiple timeframes)
    mom_1d = ((price / close.iloc[-2]) - 1) * 100
    mom_3d = ((price / close.iloc[-4]) - 1) * 100
    mom_5d = ((price / close.iloc[-6]) - 1) * 100
    mom_10d = ((price / close.iloc[-11]) - 1) * 100
    mom_20d = ((price / close.iloc[-21]) - 1) * 100

    # 52-week position
    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100

    # 20d high/low position
    high_20d = high.iloc[-20:].max()
    low_20d = low.iloc[-20:].min()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100
    pos_20d = ((price - low_20d) / (high_20d - low_20d)) * 100 if high_20d > low_20d else 50

    # ATR (volatility)
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    atr_pct = (atr / price) * 100

    # Gap
    prev_close = close.iloc[-2]
    today_open = open_p.iloc[-1]
    gap_pct = ((today_open - prev_close) / prev_close) * 100

    # Consecutive days
    changes = close.diff().iloc[-5:]
    up_days = (changes > 0).sum()
    down_days = (changes < 0).sum()

    # Price level
    price_level = price

    # Trend consistency (how many of last 10 days closed above MA20)
    ma20_series = close.rolling(20).mean()
    days_above_ma20 = (close.iloc[-10:] > ma20_series.iloc[-10:]).sum()

    # Momentum acceleration (mom_3d vs mom_10d)
    mom_acceleration = mom_3d - (mom_10d / 3.33)  # Normalized

    return {
        'price': price,
        'rsi': rsi,
        'above_ma10': above_ma10,
        'above_ma20': above_ma20,
        'above_ma50': above_ma50,
        'ma20_slope': ma20_slope,
        'vol_ratio': vol_ratio,
        'mom_1d': mom_1d,
        'mom_3d': mom_3d,
        'mom_5d': mom_5d,
        'mom_10d': mom_10d,
        'mom_20d': mom_20d,
        'pos_52w': pos_52w,
        'dist_from_20d_high': dist_from_20d_high,
        'pos_20d': pos_20d,
        'atr_pct': atr_pct,
        'gap_pct': gap_pct,
        'up_days': up_days,
        'down_days': down_days,
        'days_above_ma20': days_above_ma20,
        'mom_acceleration': mom_acceleration,
    }


def passes_v62_balanced(m):
    """Current v6.2 BALANCED"""
    if m is None: return False
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 20: return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8: return False
    if m['rsi'] >= 68: return False
    if m['dist_from_20d_high'] < -5: return False
    if m['vol_ratio'] < 0.9: return False
    return True


def backtest(data, check_func, name):
    """Run backtest and collect detailed results"""
    results = []

    for sym, df in data.items():
        for days_back in range(30, 180, 2):
            idx = len(df) - 1 - days_back
            if idx < 60 or idx + 14 >= len(df):
                continue

            m = get_metrics(df, idx)
            if not check_func(m):
                continue

            entry = df.iloc[idx]['close']
            entry_date = pd.to_datetime(df.iloc[idx]['date'])

            exit_reason = 'HOLD14'
            exit_price = df.iloc[min(idx + 14, len(df)-1)]['close']

            for i in range(1, min(15, len(df) - idx)):
                day_low = df.iloc[idx + i]['low']
                day_high = df.iloc[idx + i]['high']

                if (day_low - entry) / entry <= -0.06:
                    exit_price = entry * 0.94
                    exit_reason = 'STOP'
                    break

                if (day_high - entry) / entry >= 0.05:
                    exit_price = entry * 1.05
                    exit_reason = 'TARGET'
                    break

            ret = ((exit_price - entry) / entry) * 100

            result = {
                'sym': sym, 'date': entry_date, 'ret': ret,
                'win': ret > 0, 'exit_reason': exit_reason,
            }
            # Add all metrics
            for k, v in m.items():
                result[f'entry_{k}'] = v

            results.append(result)

    if not results:
        return None, None

    df_res = pd.DataFrame(results)
    df_res = df_res.sort_values(['sym', 'date'])
    df_res['diff'] = df_res.groupby('sym')['date'].diff().dt.days
    df_res = df_res[(df_res['diff'].isna()) | (df_res['diff'] > 10)]

    n = len(df_res)
    wins = df_res['win'].sum()

    stats = {
        'name': name,
        'trades': n,
        'wins': wins,
        'losers': n - wins,
        'win_rate': wins / n * 100 if n > 0 else 0,
        'avg_ret': df_res['ret'].mean() if n > 0 else 0,
    }

    return stats, df_res


# Load data
print("Loading HUGE universe (300+ stocks)...")
data = {}
for s in STOCKS:
    try:
        df = dm.get_price_data(s, period="1y", interval="1d")
        if df is not None and len(df) >= 200:
            data[s] = df
    except:
        pass

print(f"Loaded {len(data)} stocks\n")

# Get baseline
print("="*80)
print("STEP 1: BASELINE v6.2 BALANCED")
print("="*80)

baseline_stats, baseline_df = backtest(data, passes_v62_balanced, "v6.2 BALANCED")
if baseline_stats:
    print(f"\nBaseline: {baseline_stats['trades']} trades, {baseline_stats['win_rate']:.1f}% WR, {baseline_stats['losers']} losers")

# Analyze losers
print("\n" + "="*80)
print("STEP 2: DEEP LOSER ANALYSIS")
print("="*80)

if baseline_df is not None:
    winners = baseline_df[baseline_df['win']]
    losers = baseline_df[~baseline_df['win']]

    print(f"\nWinners: {len(winners)}, Losers: {len(losers)}")

    # Compare ALL metrics
    metrics = ['entry_rsi', 'entry_mom_3d', 'entry_mom_5d', 'entry_mom_10d', 'entry_mom_20d',
               'entry_pos_52w', 'entry_dist_from_20d_high', 'entry_pos_20d',
               'entry_above_ma20', 'entry_above_ma50', 'entry_ma20_slope',
               'entry_vol_ratio', 'entry_atr_pct', 'entry_gap_pct',
               'entry_up_days', 'entry_days_above_ma20', 'entry_mom_acceleration']

    print(f"\n{'Metric':<28} {'Winners':>12} {'Losers':>12} {'Diff':>12} {'Filter Idea':<25}")
    print("-"*95)

    filter_ideas = []

    for col in metrics:
        if col in winners.columns and col in losers.columns:
            w_mean = winners[col].mean()
            l_mean = losers[col].mean()
            diff = l_mean - w_mean
            diff_pct = abs(diff / (w_mean + 0.0001)) * 100

            idea = ""
            if diff_pct > 15:  # Significant difference
                name = col.replace('entry_', '')
                if diff > 0:
                    idea = f"Try {name} < {l_mean:.1f}"
                    filter_ideas.append((name, '<', l_mean, diff_pct))
                else:
                    idea = f"Try {name} > {l_mean:.1f}"
                    filter_ideas.append((name, '>', l_mean, diff_pct))

            print(f"{col:<28} {w_mean:>12.2f} {l_mean:>12.2f} {diff:>+12.2f} {idea:<25}")

# Find best filters
print("\n" + "="*80)
print("STEP 3: TESTING LOSER-REDUCTION FILTERS")
print("="*80)

def test_filter(df, filter_func, name):
    """Test additional filter on baseline results"""
    passed = df[df.apply(filter_func, axis=1)]
    if len(passed) < 5:
        return None

    wins = passed['win'].sum()
    n = len(passed)

    return {
        'name': name,
        'trades': n,
        'win_rate': wins / n * 100,
        'losers': n - wins,
        'avg_ret': passed['ret'].mean(),
    }

if baseline_df is not None:
    filters_to_test = [
        # RSI filters
        (lambda r: r['entry_rsi'] < 60, "RSI < 60"),
        (lambda r: r['entry_rsi'] < 55, "RSI < 55"),
        (lambda r: r['entry_rsi'] >= 45, "RSI >= 45"),
        (lambda r: 45 <= r['entry_rsi'] < 60, "RSI 45-60"),

        # Momentum filters
        (lambda r: r['entry_mom_3d'] <= 5, "Mom3d <= 5%"),
        (lambda r: r['entry_mom_3d'] <= 4, "Mom3d <= 4%"),
        (lambda r: r['entry_mom_3d'] >= 2, "Mom3d >= 2%"),
        (lambda r: 2 <= r['entry_mom_3d'] <= 5, "Mom3d 2-5%"),

        (lambda r: r['entry_mom_5d'] <= 6, "Mom5d <= 6%"),
        (lambda r: r['entry_mom_5d'] >= 2, "Mom5d >= 2%"),

        (lambda r: r['entry_mom_20d'] <= 15, "Mom20d <= 15%"),
        (lambda r: r['entry_mom_20d'] <= 12, "Mom20d <= 12%"),
        (lambda r: 8 <= r['entry_mom_20d'] <= 15, "Mom20d 8-15%"),

        # Position filters
        (lambda r: r['entry_pos_52w'] >= 65, "52w >= 65%"),
        (lambda r: r['entry_pos_52w'] <= 80, "52w <= 80%"),
        (lambda r: 65 <= r['entry_pos_52w'] <= 80, "52w 65-80%"),

        (lambda r: r['entry_pos_20d'] >= 70, "20d pos >= 70%"),
        (lambda r: r['entry_pos_20d'] >= 80, "20d pos >= 80%"),

        (lambda r: r['entry_dist_from_20d_high'] >= -3, "Dist20d >= -3%"),
        (lambda r: r['entry_dist_from_20d_high'] >= -2, "Dist20d >= -2%"),

        # Trend filters
        (lambda r: r['entry_ma20_slope'] >= 1, "MA20 slope >= 1%"),
        (lambda r: r['entry_ma20_slope'] >= 2, "MA20 slope >= 2%"),

        (lambda r: r['entry_days_above_ma20'] >= 7, "7+ days above MA20"),
        (lambda r: r['entry_days_above_ma20'] >= 8, "8+ days above MA20"),

        # Above MA50
        (lambda r: r['entry_above_ma50'] > 5, "Above MA50 by 5%+"),
        (lambda r: r['entry_above_ma50'] > 8, "Above MA50 by 8%+"),

        # Volume
        (lambda r: r['entry_vol_ratio'] >= 1.0, "Vol >= 1.0x"),
        (lambda r: r['entry_vol_ratio'] >= 1.2, "Vol >= 1.2x"),

        # ATR (volatility)
        (lambda r: r['entry_atr_pct'] <= 3.5, "ATR <= 3.5%"),
        (lambda r: r['entry_atr_pct'] <= 3.0, "ATR <= 3.0%"),
        (lambda r: r['entry_atr_pct'] <= 2.5, "ATR <= 2.5%"),

        # Up days
        (lambda r: r['entry_up_days'] >= 3, "Up days >= 3"),
        (lambda r: r['entry_up_days'] <= 4, "Up days <= 4"),

        # Combined filters
        (lambda r: r['entry_rsi'] < 60 and r['entry_mom_3d'] <= 5, "RSI<60 + Mom3d<=5%"),
        (lambda r: r['entry_mom_20d'] <= 15 and r['entry_atr_pct'] <= 3, "Mom20d<=15% + ATR<=3%"),
        (lambda r: r['entry_pos_20d'] >= 80 and r['entry_rsi'] < 60, "20d pos>=80% + RSI<60"),
        (lambda r: r['entry_ma20_slope'] >= 2 and r['entry_atr_pct'] <= 3, "MA20slope>=2% + ATR<=3%"),
        (lambda r: r['entry_days_above_ma20'] >= 8 and r['entry_mom_3d'] <= 5, "8d>MA20 + Mom3d<=5%"),
    ]

    print(f"\n{'Filter':<40} {'Trades':>8} {'Win%':>8} {'Losers':>8} {'AvgRet':>10}")
    print("-"*80)

    # Baseline
    print(f"{'BASELINE v6.2':<40} {baseline_stats['trades']:>8} {baseline_stats['win_rate']:>7.1f}% {baseline_stats['losers']:>8} {baseline_stats['avg_ret']:>+9.2f}%")
    print("-"*80)

    results = []
    for filter_func, name in filters_to_test:
        r = test_filter(baseline_df, filter_func, name)
        if r:
            results.append(r)

    # Sort by losers (ascending), then win_rate (descending)
    results.sort(key=lambda x: (x['losers'], -x['win_rate']))

    for r in results[:25]:
        improvement = ""
        if r['losers'] < baseline_stats['losers']:
            improvement = f" ✓-{baseline_stats['losers'] - r['losers']}"
        print(f"{r['name']:<40} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['losers']:>8}{improvement} {r['avg_ret']:>+9.2f}%")

# Find optimal combination
print("\n" + "="*80)
print("STEP 4: FINDING OPTIMAL 'NEAR-ZERO LOSER' COMBINATION")
print("="*80)

# Test best combinations
if baseline_df is not None:
    best_combos = [
        # Single best filters
        (lambda r: r['entry_atr_pct'] <= 2.5, "ATR <= 2.5%"),
        (lambda r: r['entry_mom_20d'] <= 12, "Mom20d <= 12%"),
        (lambda r: r['entry_rsi'] < 55, "RSI < 55"),
        (lambda r: r['entry_pos_20d'] >= 80, "20d Pos >= 80%"),

        # Combined for near-zero losers
        (lambda r: r['entry_atr_pct'] <= 3 and r['entry_mom_20d'] <= 15, "ATR<=3% + Mom20d<=15%"),
        (lambda r: r['entry_atr_pct'] <= 2.5 and r['entry_rsi'] < 60, "ATR<=2.5% + RSI<60"),
        (lambda r: r['entry_pos_20d'] >= 80 and r['entry_atr_pct'] <= 3, "20dPos>=80% + ATR<=3%"),
        (lambda r: r['entry_mom_20d'] <= 12 and r['entry_atr_pct'] <= 3, "Mom20d<=12% + ATR<=3%"),

        # Triple combo
        (lambda r: r['entry_atr_pct'] <= 3 and r['entry_mom_20d'] <= 15 and r['entry_rsi'] < 60,
         "ATR<=3% + Mom20d<=15% + RSI<60"),
        (lambda r: r['entry_pos_20d'] >= 80 and r['entry_atr_pct'] <= 3 and r['entry_mom_3d'] <= 5,
         "20dPos>=80% + ATR<=3% + Mom3d<=5%"),
        (lambda r: r['entry_days_above_ma20'] >= 8 and r['entry_atr_pct'] <= 3 and r['entry_mom_20d'] <= 15,
         "8d>MA20 + ATR<=3% + Mom20d<=15%"),
    ]

    print(f"\n{'Combination':<55} {'Trades':>8} {'Win%':>8} {'Losers':>8}")
    print("-"*85)

    combo_results = []
    for filter_func, name in best_combos:
        r = test_filter(baseline_df, filter_func, name)
        if r and r['trades'] >= 10:
            combo_results.append(r)
            marker = "⭐" if r['losers'] <= 3 else ""
            print(f"{name:<55} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['losers']:>8} {marker}")

    # Find best
    combo_results.sort(key=lambda x: (x['losers'], -x['win_rate'], -x['trades']))

    if combo_results:
        best = combo_results[0]
        print(f"\n{'='*85}")
        print("RECOMMENDED v6.3 CRITERIA")
        print("="*85)
        print(f"""
BEST COMBINATION: {best['name']}

Results:
  Trades:   {best['trades']}
  Win Rate: {best['win_rate']:.1f}%
  Losers:   {best['losers']} ({'NEAR ZERO!' if best['losers'] <= 3 else 'LOW' if best['losers'] <= 5 else 'OK'})
  Avg Ret:  {best['avg_ret']:+.2f}%

Improvement from v6.2 BALANCED:
  Losers: {baseline_stats['losers']} → {best['losers']} ({best['losers'] - baseline_stats['losers']:+d})
  Win Rate: {baseline_stats['win_rate']:.1f}% → {best['win_rate']:.1f}%
""")
