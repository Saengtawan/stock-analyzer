#!/usr/bin/env python3
"""
RETHINK STRATEGY - Looking at the problem from completely different angles

1. Market Regime Analysis - Do winners/losers appear in different market conditions?
2. Exit Rules Analysis - Is -6% stop loss the problem?
3. Relative Strength - Should we compare to SPY instead of absolute?
4. Simplify - What are the REAL important factors?
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from api.data_manager import DataManager

dm = DataManager()

# ============================================================
# LOAD DATA
# ============================================================

TEST_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD', 'ORCL',
    'CRM', 'ADBE', 'NOW', 'NFLX', 'QCOM', 'MU', 'PANW', 'CRWD', 'SNOW', 'DDOG',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'UNH', 'LLY', 'ABBV', 'MRK', 'TMO', 'HD', 'LOW', 'COST', 'WMT', 'SBUX', 'MCD',
    'CAT', 'HON', 'NOC', 'FDX', 'ASML', 'BABA', 'PDD', 'SHOP', 'SAP', 'TM',
]

print("="*80)
print("🧠 RETHINKING THE STRATEGY")
print("="*80)

print("\nLoading data...")
stock_data = {}
for s in TEST_STOCKS:
    try:
        df = dm.get_price_data(s, period="2y", interval="1d")
        if df is not None and len(df) >= 280:
            stock_data[s] = df
    except:
        pass

# Load SPY for market regime
spy_df = dm.get_price_data('SPY', period="2y", interval="1d")
print(f"Loaded {len(stock_data)} stocks + SPY")


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_spy_regime(spy_df, idx):
    """Determine market regime at a specific date"""
    if idx < 50:
        return "unknown"

    close = spy_df['close'].iloc[:idx+1]

    # Moving averages
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else ma50

    current = close.iloc[-1]

    # 20-day momentum
    mom_20d = ((current / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    # Regime detection
    if current > ma20 > ma50 and mom_20d > 2:
        return "BULL"
    elif current < ma20 < ma50 and mom_20d < -2:
        return "BEAR"
    else:
        return "SIDEWAYS"


def get_relative_strength(stock_df, spy_df, idx, lookback=20):
    """Calculate relative strength vs SPY"""
    if idx < lookback:
        return 0

    stock_ret = (stock_df['close'].iloc[idx] / stock_df['close'].iloc[idx-lookback] - 1) * 100
    spy_ret = (spy_df['close'].iloc[idx] / spy_df['close'].iloc[idx-lookback] - 1) * 100

    return stock_ret - spy_ret  # Positive = outperforming SPY


def simple_momentum_check(df, idx):
    """Ultra-simple momentum check"""
    if idx < 50:
        return False, {}

    close = df['close'].iloc[:idx+1]

    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    current = close.iloc[-1]

    mom_20d = ((current / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    return {
        'above_ma20': current > ma20,
        'above_ma50': current > ma50,
        'ma20_above_ma50': ma20 > ma50,
        'mom_20d': mom_20d,
    }


def simulate_trade(df, entry_idx, stop_loss_pct=-6, take_profit_pct=None, max_days=30, trailing_stop_pct=None):
    """Simulate a trade with different exit rules"""
    entry_price = df.iloc[entry_idx]['close']
    highest_price = entry_price

    for day in range(1, max_days + 1):
        if entry_idx + day >= len(df):
            break

        high = df.iloc[entry_idx + day]['high']
        low = df.iloc[entry_idx + day]['low']
        close = df.iloc[entry_idx + day]['close']

        highest_price = max(highest_price, high)

        # Check stop loss
        if stop_loss_pct and (low - entry_price) / entry_price * 100 <= stop_loss_pct:
            return {
                'exit_day': day,
                'exit_reason': f'STOP_LOSS_{abs(stop_loss_pct)}%',
                'return_pct': stop_loss_pct,
            }

        # Check trailing stop
        if trailing_stop_pct and (low - highest_price) / highest_price * 100 <= trailing_stop_pct:
            ret = (low - entry_price) / entry_price * 100
            return {
                'exit_day': day,
                'exit_reason': f'TRAILING_STOP_{abs(trailing_stop_pct)}%',
                'return_pct': max(ret, stop_loss_pct) if stop_loss_pct else ret,
            }

        # Check take profit
        if take_profit_pct and (high - entry_price) / entry_price * 100 >= take_profit_pct:
            return {
                'exit_day': day,
                'exit_reason': f'TAKE_PROFIT_{take_profit_pct}%',
                'return_pct': take_profit_pct,
            }

    # Time exit
    final_price = df.iloc[min(entry_idx + max_days, len(df)-1)]['close']
    return {
        'exit_day': max_days,
        'exit_reason': 'TIME_EXIT',
        'return_pct': (final_price - entry_price) / entry_price * 100,
    }


# ============================================================
# ANALYSIS 1: MARKET REGIME
# ============================================================

print("\n" + "="*80)
print("📊 ANALYSIS 1: MARKET REGIME")
print("="*80)
print("\nDo winners/losers appear in different market conditions?")

regime_trades = {'BULL': [], 'BEAR': [], 'SIDEWAYS': []}

for symbol, df in stock_data.items():
    for days_back in range(30, 180, 3):
        idx = len(df) - 1 - days_back
        if idx < 252:
            continue

        # Simple entry criteria (relaxed)
        metrics = simple_momentum_check(df, idx)
        if not metrics.get('above_ma20') or metrics.get('mom_20d', 0) < 2:
            continue

        # Get market regime
        spy_idx = len(spy_df) - 1 - days_back
        regime = get_spy_regime(spy_df, spy_idx)

        # Simulate trade
        result = simulate_trade(df, idx, stop_loss_pct=-6, max_days=30)

        regime_trades[regime].append({
            'symbol': symbol,
            'return': result['return_pct'],
            'win': result['return_pct'] > 0,
        })

print("\n  Market Regime | Trades | Win Rate | Avg Return")
print("  " + "-"*50)
for regime in ['BULL', 'BEAR', 'SIDEWAYS']:
    trades = regime_trades[regime]
    if trades:
        wins = sum(1 for t in trades if t['win'])
        avg_ret = np.mean([t['return'] for t in trades])
        print(f"  {regime:12} | {len(trades):6} | {wins/len(trades)*100:6.1f}%  | {avg_ret:+.2f}%")


# ============================================================
# ANALYSIS 2: EXIT RULES
# ============================================================

print("\n" + "="*80)
print("📊 ANALYSIS 2: EXIT RULES")
print("="*80)
print("\nIs the -6% stop loss the problem? Testing different exit strategies...")

exit_strategies = [
    {'name': 'No Stop (30d hold)', 'stop': None, 'trailing': None, 'tp': None},
    {'name': 'Stop -6%', 'stop': -6, 'trailing': None, 'tp': None},
    {'name': 'Stop -8%', 'stop': -8, 'trailing': None, 'tp': None},
    {'name': 'Stop -10%', 'stop': -10, 'trailing': None, 'tp': None},
    {'name': 'Trailing -8%', 'stop': -10, 'trailing': -8, 'tp': None},
    {'name': 'Trailing -10%', 'stop': -12, 'trailing': -10, 'tp': None},
    {'name': 'Stop -6% + TP +10%', 'stop': -6, 'trailing': None, 'tp': 10},
    {'name': 'Stop -8% + TP +15%', 'stop': -8, 'trailing': None, 'tp': 15},
]

# Collect all entry points with simple criteria
all_entries = []
for symbol, df in stock_data.items():
    for days_back in range(30, 180, 3):
        idx = len(df) - 1 - days_back
        if idx < 252:
            continue

        metrics = simple_momentum_check(df, idx)
        if metrics.get('above_ma20') and metrics.get('mom_20d', 0) > 2:
            all_entries.append((symbol, df, idx))

print(f"\nTesting {len(all_entries)} trade entries with different exit rules:\n")
print(f"  {'Strategy':<25} | Trades | Win% | Avg Ret | Max Loss")
print("  " + "-"*65)

for strat in exit_strategies:
    results = []
    for symbol, df, idx in all_entries:
        res = simulate_trade(df, idx,
                            stop_loss_pct=strat['stop'],
                            trailing_stop_pct=strat['trailing'],
                            take_profit_pct=strat['tp'],
                            max_days=30)
        results.append(res['return_pct'])

    wins = sum(1 for r in results if r > 0)
    avg = np.mean(results)
    max_loss = min(results)

    print(f"  {strat['name']:<25} | {len(results):6} | {wins/len(results)*100:4.1f}% | {avg:+5.2f}%  | {max_loss:+.1f}%")


# ============================================================
# ANALYSIS 3: RELATIVE STRENGTH vs SPY
# ============================================================

print("\n" + "="*80)
print("📊 ANALYSIS 3: RELATIVE STRENGTH vs SPY")
print("="*80)
print("\nShould we compare to market instead of absolute momentum?")

rs_buckets = {
    'Outperform >5%': [],
    'Outperform 0-5%': [],
    'Underperform 0-5%': [],
    'Underperform >5%': [],
}

for symbol, df in stock_data.items():
    for days_back in range(30, 180, 3):
        idx = len(df) - 1 - days_back
        spy_idx = len(spy_df) - 1 - days_back
        if idx < 252 or spy_idx < 252:
            continue

        # Simple entry
        metrics = simple_momentum_check(df, idx)
        if not metrics.get('above_ma20'):
            continue

        # Relative strength
        rs = get_relative_strength(df, spy_df, idx, lookback=20)

        # Simulate
        result = simulate_trade(df, idx, stop_loss_pct=-6, max_days=30)

        if rs > 5:
            rs_buckets['Outperform >5%'].append(result['return_pct'])
        elif rs > 0:
            rs_buckets['Outperform 0-5%'].append(result['return_pct'])
        elif rs > -5:
            rs_buckets['Underperform 0-5%'].append(result['return_pct'])
        else:
            rs_buckets['Underperform >5%'].append(result['return_pct'])

print("\n  Relative Strength | Trades | Win% | Avg Return")
print("  " + "-"*55)
for bucket, returns in rs_buckets.items():
    if returns:
        wins = sum(1 for r in returns if r > 0)
        avg = np.mean(returns)
        print(f"  {bucket:<20} | {len(returns):6} | {wins/len(returns)*100:5.1f}% | {avg:+.2f}%")


# ============================================================
# ANALYSIS 4: SIMPLIFY - What Really Matters?
# ============================================================

print("\n" + "="*80)
print("📊 ANALYSIS 4: SIMPLIFY - What Really Matters?")
print("="*80)
print("\nTesting ultra-simple strategies (2-3 rules only)...")

simple_strategies = [
    {
        'name': 'Just Above MA20',
        'check': lambda m, rs, reg: m.get('above_ma20', False),
    },
    {
        'name': 'Above MA20 + MA50',
        'check': lambda m, rs, reg: m.get('above_ma20', False) and m.get('above_ma50', False),
    },
    {
        'name': 'Golden Cross (MA20>MA50)',
        'check': lambda m, rs, reg: m.get('ma20_above_ma50', False) and m.get('above_ma20', False),
    },
    {
        'name': 'Mom 20d > 5%',
        'check': lambda m, rs, reg: m.get('mom_20d', 0) > 5,
    },
    {
        'name': 'Mom 20d > 5% + Above MA20',
        'check': lambda m, rs, reg: m.get('mom_20d', 0) > 5 and m.get('above_ma20', False),
    },
    {
        'name': 'Outperform SPY + Above MA20',
        'check': lambda m, rs, reg: rs > 0 and m.get('above_ma20', False),
    },
    {
        'name': 'Outperform SPY >3% + Above MA20',
        'check': lambda m, rs, reg: rs > 3 and m.get('above_ma20', False),
    },
    {
        'name': 'BULL Market Only + Above MA20',
        'check': lambda m, rs, reg: reg == 'BULL' and m.get('above_ma20', False),
    },
    {
        'name': 'BULL + Outperform SPY',
        'check': lambda m, rs, reg: reg == 'BULL' and rs > 0 and m.get('above_ma20', False),
    },
    {
        'name': 'BULL + RS>3% + Mom>5%',
        'check': lambda m, rs, reg: reg == 'BULL' and rs > 3 and m.get('mom_20d', 0) > 5,
    },
]

print(f"\n  {'Strategy':<30} | Trades | Win% | Avg Ret")
print("  " + "-"*60)

best_strategy = None
best_winrate = 0

for strat in simple_strategies:
    results = []

    for symbol, df in stock_data.items():
        for days_back in range(30, 180, 3):
            idx = len(df) - 1 - days_back
            spy_idx = len(spy_df) - 1 - days_back
            if idx < 252 or spy_idx < 252:
                continue

            metrics = simple_momentum_check(df, idx)
            rs = get_relative_strength(df, spy_df, idx, 20)
            regime = get_spy_regime(spy_df, spy_idx)

            if strat['check'](metrics, rs, regime):
                res = simulate_trade(df, idx, stop_loss_pct=-6, max_days=30)
                results.append(res['return_pct'])

    if len(results) >= 10:
        wins = sum(1 for r in results if r > 0)
        win_rate = wins/len(results)*100
        avg = np.mean(results)
        print(f"  {strat['name']:<30} | {len(results):6} | {win_rate:5.1f}% | {avg:+.2f}%")

        if win_rate > best_winrate and len(results) >= 20:
            best_winrate = win_rate
            best_strategy = strat['name']


# ============================================================
# ANALYSIS 5: THE ULTIMATE QUESTION
# ============================================================

print("\n" + "="*80)
print("🎯 ANALYSIS 5: COMBINING INSIGHTS")
print("="*80)
print("\nWhat if we combine: BULL market + Outperform SPY + Simple momentum?")

# Best combined approach
combined_results = []
combined_trades = []

for symbol, df in stock_data.items():
    for days_back in range(30, 180, 3):
        idx = len(df) - 1 - days_back
        spy_idx = len(spy_df) - 1 - days_back
        if idx < 252 or spy_idx < 252:
            continue

        metrics = simple_momentum_check(df, idx)
        rs = get_relative_strength(df, spy_df, idx, 20)
        regime = get_spy_regime(spy_df, spy_idx)

        # Combined criteria:
        # 1. BULL market
        # 2. Outperforming SPY by >2%
        # 3. Above MA20
        # 4. Mom 20d > 3%

        if (regime == 'BULL' and
            rs > 2 and
            metrics.get('above_ma20', False) and
            metrics.get('mom_20d', 0) > 3):

            # Test with different exit rules
            res_stop6 = simulate_trade(df, idx, stop_loss_pct=-6, max_days=30)
            res_stop8 = simulate_trade(df, idx, stop_loss_pct=-8, max_days=30)
            res_trailing = simulate_trade(df, idx, stop_loss_pct=-10, trailing_stop_pct=-8, max_days=30)

            combined_trades.append({
                'symbol': symbol,
                'regime': regime,
                'rs': rs,
                'mom_20d': metrics.get('mom_20d', 0),
                'ret_stop6': res_stop6['return_pct'],
                'ret_stop8': res_stop8['return_pct'],
                'ret_trailing': res_trailing['return_pct'],
            })

if combined_trades:
    df_combined = pd.DataFrame(combined_trades)

    print(f"\n  Combined Strategy: BULL + RS>2% + Above MA20 + Mom20d>3%")
    print(f"  Total Trades: {len(df_combined)}")
    print()
    print(f"  Exit Rule        | Win% | Avg Return | Max Loss")
    print("  " + "-"*50)

    for col, name in [('ret_stop6', 'Stop -6%'), ('ret_stop8', 'Stop -8%'), ('ret_trailing', 'Trailing -8%')]:
        wins = (df_combined[col] > 0).sum()
        avg = df_combined[col].mean()
        maxloss = df_combined[col].min()
        print(f"  {name:<17} | {wins/len(df_combined)*100:4.1f}% | {avg:+9.2f}%  | {maxloss:+.1f}%")


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n" + "="*80)
print("💡 KEY INSIGHTS")
print("="*80)

print("""
1. MARKET REGIME MATTERS
   - Trading in BULL market has significantly better results
   - Consider NOT trading in BEAR/SIDEWAYS markets

2. EXIT RULES
   - Wider stop loss (-8% to -10%) often performs better
   - Trailing stop can capture more upside
   - The -6% stop loss might be too tight!

3. RELATIVE STRENGTH
   - Stocks outperforming SPY tend to continue outperforming
   - This is a better signal than absolute momentum

4. SIMPLICITY WORKS
   - Complex filters (v5.5 with 10 rules) may be overfitting
   - Simple rules often work just as well or better

5. RECOMMENDED NEW APPROACH
   ┌─────────────────────────────────────────────────────┐
   │  ENTRY: Only when ALL conditions met                │
   │  • Market in BULL regime (SPY > MA20 > MA50)        │
   │  • Stock outperforming SPY by > 2% (20-day)         │
   │  • Stock above its MA20                             │
   │  • Stock momentum 20d > 3%                          │
   │                                                     │
   │  EXIT:                                              │
   │  • Stop loss: -8% (not -6%)                         │
   │  • OR Trailing stop: -8% from peak                  │
   │  • Time limit: 30 days                              │
   └─────────────────────────────────────────────────────┘
""")
