#!/usr/bin/env python3
"""
Deep analysis of v6.1 losers - WHY did they fail?
Find patterns to reduce losers
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from api.data_manager import DataManager

dm = DataManager()

# Large universe (same as backtest)
STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD', 'ORCL',
    'CRM', 'ADBE', 'NOW', 'NFLX', 'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX',
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'BA', 'UPS', 'FDX',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX',
    # More stocks
    'COIN', 'SQ', 'ROKU', 'SNAP', 'PINS', 'UBER', 'LYFT', 'ABNB', 'DASH',
    'ZM', 'DOCU', 'TWLO', 'OKTA', 'U', 'RBLX', 'PATH', 'CFLT', 'MQ',
    'BILL', 'HUBS', 'VEEV', 'WDAY', 'ZI', 'ESTC', 'GTLB', 'DOMO',
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI',
]


def get_metrics(df, idx):
    """Calculate all metrics at a specific index"""
    if idx < 50:
        return None

    close = df['close'].iloc[:idx+1]
    high = df['high'].iloc[:idx+1]
    low = df['low'].iloc[:idx+1]
    volume = df['volume'].iloc[:idx+1]
    price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 0.0001)))

    # MA
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else ma20
    above_ma20 = ((price - ma20) / ma20) * 100
    above_ma50 = ((price - ma50) / ma50) * 100

    # Volume
    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    # Momentum
    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_5d = ((price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    # 52-week position
    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    # v6.1: Distance from 20d high
    high_20d = high.iloc[-20:].max()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100

    # NEW: Additional metrics for analysis
    # Volatility (ATR)
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    atr_pct = (atr / price) * 100

    # Gap from previous close
    prev_close = close.iloc[-2]
    open_today = df['open'].iloc[idx]
    gap_pct = ((open_today - prev_close) / prev_close) * 100

    # Consecutive up/down days
    changes = close.diff().iloc[-5:]
    up_days = (changes > 0).sum()
    down_days = (changes < 0).sum()

    # Distance from MA50
    dist_ma50 = ((price - ma50) / ma50) * 100 if ma50 > 0 else 0

    # Trend strength (MA20 slope)
    ma20_5d_ago = close.rolling(20).mean().iloc[-6] if len(close) >= 26 else ma20
    ma20_slope = ((ma20 - ma20_5d_ago) / ma20_5d_ago) * 100 if ma20_5d_ago > 0 else 0

    return {
        'price': price,
        'rsi': rsi,
        'above_ma20': above_ma20,
        'above_ma50': above_ma50,
        'vol_ratio': vol_ratio,
        'mom_3d': mom_3d,
        'mom_5d': mom_5d,
        'mom_10d': mom_10d,
        'mom_20d': mom_20d,
        'pos_52w': pos_52w,
        'dist_from_20d_high': dist_from_20d_high,
        'atr_pct': atr_pct,
        'gap_pct': gap_pct,
        'up_days': up_days,
        'down_days': down_days,
        'dist_ma50': dist_ma50,
        'ma20_slope': ma20_slope,
    }


def passes_v61(m):
    """v6.1 criteria"""
    if m is None:
        return False
    if m['above_ma20'] <= 0:
        return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85:
        return False
    if m['mom_20d'] < 8:
        return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8:
        return False
    if m['rsi'] >= 70:
        return False
    if m['dist_from_20d_high'] < -5:
        return False
    return True


def simulate_trade(df, idx, hold_days=14, stop_loss=-0.06, target=0.05):
    """Simulate a trade and return details"""
    entry = df.iloc[idx]['close']
    entry_date = pd.to_datetime(df.iloc[idx]['date'])

    max_price = entry
    min_price = entry
    exit_reason = 'HOLD14'
    exit_day = hold_days

    for i in range(1, min(hold_days + 1, len(df) - idx)):
        day_high = df.iloc[idx + i]['high']
        day_low = df.iloc[idx + i]['low']
        day_close = df.iloc[idx + i]['close']

        max_price = max(max_price, day_high)
        min_price = min(min_price, day_low)

        # Check stop loss
        if (day_low - entry) / entry <= stop_loss:
            exit_price = entry * (1 + stop_loss)
            exit_reason = 'STOP'
            exit_day = i
            return {
                'exit_price': exit_price,
                'ret': stop_loss * 100,
                'win': False,
                'exit_reason': exit_reason,
                'exit_day': exit_day,
                'max_gain': ((max_price - entry) / entry) * 100,
                'max_drawdown': ((min_price - entry) / entry) * 100,
            }

        # Check target
        if (day_high - entry) / entry >= target:
            exit_price = entry * (1 + target)
            exit_reason = 'TARGET'
            exit_day = i
            return {
                'exit_price': exit_price,
                'ret': target * 100,
                'win': True,
                'exit_reason': exit_reason,
                'exit_day': exit_day,
                'max_gain': ((max_price - entry) / entry) * 100,
                'max_drawdown': ((min_price - entry) / entry) * 100,
            }

    # Hold period ended
    exit_idx = min(idx + hold_days, len(df) - 1)
    exit_price = df.iloc[exit_idx]['close']
    ret = ((exit_price - entry) / entry) * 100

    return {
        'exit_price': exit_price,
        'ret': ret,
        'win': ret > 0,
        'exit_reason': 'HOLD14',
        'exit_day': hold_days,
        'max_gain': ((max_price - entry) / entry) * 100,
        'max_drawdown': ((min_price - entry) / entry) * 100,
    }


# Load data
print("Loading data...")
data = {}
for s in STOCKS:
    try:
        df = dm.get_price_data(s, period="1y", interval="1d")
        if df is not None and len(df) >= 200:
            data[s] = df
    except:
        pass

print(f"Loaded {len(data)} stocks\n")

# Run backtest and collect all trades
print("="*70)
print("ANALYZING v6.1 LOSERS - ROOT CAUSE")
print("="*70)

all_trades = []

for sym, df in data.items():
    for days_back in range(30, 180, 2):
        idx = len(df) - 1 - days_back
        if idx < 50 or idx + 14 >= len(df):
            continue

        m = get_metrics(df, idx)
        if not passes_v61(m):
            continue

        trade = simulate_trade(df, idx)
        trade['sym'] = sym
        trade['date'] = pd.to_datetime(df.iloc[idx]['date'])
        trade['entry_price'] = df.iloc[idx]['close']

        # Add entry metrics
        for key in m:
            trade[f'entry_{key}'] = m[key]

        all_trades.append(trade)

# Convert to DataFrame
df_trades = pd.DataFrame(all_trades)

# Dedupe
df_trades = df_trades.sort_values(['sym', 'date'])
df_trades['diff'] = df_trades.groupby('sym')['date'].diff().dt.days
df_trades = df_trades[(df_trades['diff'].isna()) | (df_trades['diff'] > 10)]

print(f"\nTotal trades: {len(df_trades)}")

# Separate winners and losers
winners = df_trades[df_trades['win']]
losers = df_trades[~df_trades['win']]

print(f"Winners: {len(winners)} ({len(winners)/len(df_trades)*100:.1f}%)")
print(f"Losers: {len(losers)} ({len(losers)/len(df_trades)*100:.1f}%)")

# Analyze losers
print("\n" + "="*70)
print("LOSER ANALYSIS")
print("="*70)

print("\n1. EXIT REASON BREAKDOWN:")
print("-"*40)
loser_reasons = losers['exit_reason'].value_counts()
for reason, count in loser_reasons.items():
    pct = count / len(losers) * 100
    print(f"   {reason}: {count} ({pct:.1f}%)")

print("\n2. COMPARE ENTRY METRICS: WINNERS vs LOSERS")
print("-"*70)

metrics_to_compare = [
    ('entry_rsi', 'RSI'),
    ('entry_mom_3d', 'Mom 3d (%)'),
    ('entry_mom_5d', 'Mom 5d (%)'),
    ('entry_mom_10d', 'Mom 10d (%)'),
    ('entry_mom_20d', 'Mom 20d (%)'),
    ('entry_pos_52w', '52w Pos (%)'),
    ('entry_dist_from_20d_high', 'Dist 20d High (%)'),
    ('entry_above_ma20', 'Above MA20 (%)'),
    ('entry_above_ma50', 'Above MA50 (%)'),
    ('entry_vol_ratio', 'Vol Ratio'),
    ('entry_atr_pct', 'ATR %'),
    ('entry_gap_pct', 'Gap %'),
    ('entry_up_days', 'Up Days (5d)'),
    ('entry_ma20_slope', 'MA20 Slope (%)'),
]

print(f"{'Metric':<25} {'Winners':>12} {'Losers':>12} {'Diff':>12} {'Signal':>10}")
print("-"*70)

significant_diffs = []

for col, name in metrics_to_compare:
    if col in winners.columns and col in losers.columns:
        w_mean = winners[col].mean()
        l_mean = losers[col].mean()
        diff = l_mean - w_mean

        # Determine if significant
        signal = ""
        if abs(diff) > abs(w_mean * 0.15):  # 15% difference
            if diff > 0:
                signal = "LOSER HIGH"
            else:
                signal = "LOSER LOW"
            significant_diffs.append((name, w_mean, l_mean, diff, signal))

        print(f"{name:<25} {w_mean:>12.2f} {l_mean:>12.2f} {diff:>+12.2f} {signal:>10}")

print("\n3. SIGNIFICANT DIFFERENCES (Potential filters):")
print("-"*70)
if significant_diffs:
    for name, w, l, diff, sig in significant_diffs:
        print(f"   {name}: Winners={w:.2f}, Losers={l:.2f}")
        if sig == "LOSER HIGH":
            print(f"      → Losers มีค่าสูงกว่า → อาจต้องตั้ง UPPER LIMIT")
        else:
            print(f"      → Losers มีค่าต่ำกว่า → อาจต้องตั้ง LOWER LIMIT")
        print()

print("\n4. LOSER DETAILS (Worst 15 trades):")
print("-"*70)

worst = losers.nsmallest(15, 'ret')
print(f"{'Symbol':<8} {'Date':<12} {'Return':>8} {'RSI':>6} {'Mom3d':>8} {'Mom20d':>8} {'52wPos':>8} {'Dist20d':>8} {'UpDays':>7}")
print("-"*90)

for _, row in worst.iterrows():
    print(f"{row['sym']:<8} {row['date'].strftime('%Y-%m-%d'):<12} {row['ret']:>+7.1f}% {row['entry_rsi']:>5.0f} {row['entry_mom_3d']:>+7.1f}% {row['entry_mom_20d']:>+7.1f}% {row['entry_pos_52w']:>7.0f}% {row['entry_dist_from_20d_high']:>+7.1f}% {row['entry_up_days']:>6.0f}")

# Find optimal thresholds
print("\n" + "="*70)
print("5. FINDING OPTIMAL FILTERS TO REDUCE LOSERS")
print("="*70)

def test_filter(df_trades, filter_func, name):
    """Test a filter and return stats"""
    passed = df_trades[df_trades.apply(filter_func, axis=1)]
    if len(passed) == 0:
        return None

    wins = passed['win'].sum()
    total = len(passed)
    losers_count = total - wins

    return {
        'name': name,
        'trades': total,
        'win_rate': wins / total * 100,
        'losers': losers_count,
        'avg_ret': passed['ret'].mean(),
    }

# Test various filters
filters_to_test = [
    # RSI filters
    (lambda r: r['entry_rsi'] < 60, "RSI < 60"),
    (lambda r: r['entry_rsi'] < 55, "RSI < 55"),
    (lambda r: r['entry_rsi'] < 50, "RSI < 50"),

    # Mom 3d filters
    (lambda r: r['entry_mom_3d'] <= 6, "Mom3d <= 6%"),
    (lambda r: r['entry_mom_3d'] <= 5, "Mom3d <= 5%"),
    (lambda r: r['entry_mom_3d'] <= 4, "Mom3d <= 4%"),
    (lambda r: r['entry_mom_3d'] >= 2, "Mom3d >= 2%"),

    # Vol ratio filters
    (lambda r: r['entry_vol_ratio'] >= 1.0, "Vol >= 1.0x"),
    (lambda r: r['entry_vol_ratio'] >= 1.2, "Vol >= 1.2x"),
    (lambda r: r['entry_vol_ratio'] >= 1.5, "Vol >= 1.5x"),

    # Dist from 20d high
    (lambda r: r['entry_dist_from_20d_high'] >= -3, "Dist20d >= -3%"),
    (lambda r: r['entry_dist_from_20d_high'] >= -2, "Dist20d >= -2%"),
    (lambda r: r['entry_dist_from_20d_high'] >= 0, "Dist20d >= 0% (at high)"),

    # ATR filter
    (lambda r: r['entry_atr_pct'] <= 4, "ATR <= 4%"),
    (lambda r: r['entry_atr_pct'] <= 3, "ATR <= 3%"),

    # Consecutive days
    (lambda r: r['entry_up_days'] >= 3, "Up Days >= 3"),
    (lambda r: r['entry_up_days'] <= 4, "Up Days <= 4"),

    # MA50 filter
    (lambda r: r['entry_above_ma50'] > 0, "Above MA50"),
    (lambda r: r['entry_above_ma50'] > 5, "Above MA50 by 5%+"),

    # Combined filters
    (lambda r: r['entry_rsi'] < 60 and r['entry_mom_3d'] <= 5, "RSI<60 + Mom3d<=5%"),
    (lambda r: r['entry_rsi'] < 55 and r['entry_dist_from_20d_high'] >= -2, "RSI<55 + Dist>=-2%"),
    (lambda r: r['entry_vol_ratio'] >= 1.2 and r['entry_atr_pct'] <= 4, "Vol>=1.2x + ATR<=4%"),
]

# Current baseline (v6.1)
baseline = {
    'name': 'v6.1 CURRENT',
    'trades': len(df_trades),
    'win_rate': df_trades['win'].sum() / len(df_trades) * 100,
    'losers': len(losers),
    'avg_ret': df_trades['ret'].mean(),
}

print(f"\n{'Filter':<35} {'Trades':>8} {'Win%':>8} {'Losers':>8} {'AvgRet':>10}")
print("-"*75)
print(f"{baseline['name']:<35} {baseline['trades']:>8} {baseline['win_rate']:>7.1f}% {baseline['losers']:>8} {baseline['avg_ret']:>+9.2f}%")
print("-"*75)

results = []
for filter_func, name in filters_to_test:
    r = test_filter(df_trades, filter_func, name)
    if r:
        results.append(r)

# Sort by lowest losers, then highest win rate
results.sort(key=lambda x: (x['losers'], -x['win_rate']))

for r in results[:20]:
    improvement = ""
    if r['losers'] < baseline['losers']:
        improvement = f" (-{baseline['losers'] - r['losers']} losers)"
    print(f"{r['name']:<35} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['losers']:>8} {r['avg_ret']:>+9.2f}%{improvement}")

# Best combined filter
print("\n" + "="*70)
print("6. RECOMMENDED v6.2 CRITERIA")
print("="*70)

# Find best filter that reduces losers significantly
best_filters = [r for r in results if r['losers'] <= baseline['losers'] * 0.7 and r['trades'] >= 20]
if best_filters:
    best = best_filters[0]
    print(f"""
CURRENT v6.1:
  Trades: {baseline['trades']}, Win Rate: {baseline['win_rate']:.1f}%, Losers: {baseline['losers']}

RECOMMENDED v6.2 (add filter: {best['name']}):
  Trades: {best['trades']}, Win Rate: {best['win_rate']:.1f}%, Losers: {best['losers']}

  Improvement:
  - Losers: {baseline['losers']} → {best['losers']} ({baseline['losers'] - best['losers']} fewer)
  - Win Rate: {baseline['win_rate']:.1f}% → {best['win_rate']:.1f}% ({best['win_rate'] - baseline['win_rate']:+.1f}%)
""")
else:
    # Find any improvement
    improved = [r for r in results if r['losers'] < baseline['losers'] and r['win_rate'] > baseline['win_rate']]
    if improved:
        best = improved[0]
        print(f"""
ปรับปรุงที่แนะนำ: {best['name']}
  Losers: {baseline['losers']} → {best['losers']}
  Win Rate: {baseline['win_rate']:.1f}% → {best['win_rate']:.1f}%
""")
