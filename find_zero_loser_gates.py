#!/usr/bin/env python3
"""
Find optimal gates for ZERO LOSER (or minimal losers)
"""

import pandas as pd
import numpy as np

# Load backtest results
df = pd.read_csv('backtest_v8_zero_loser_results.csv')

print("=" * 70)
print("FINDING OPTIMAL GATES FOR ZERO/MINIMAL LOSERS")
print("=" * 70)

print(f"\nTotal trades: {len(df)}")
print(f"Current losers: {len(df[df['return_pct'] < 0])}")

# Analyze correlation
print("\n📊 CORRELATION WITH RETURN:")
for col in ['rsi', 'accumulation', 'price_above_ma20']:
    corr = df['return_pct'].corr(df[col])
    print(f"  {col}: {corr:.3f}")

# Find optimal thresholds
print("\n" + "=" * 70)
print("GRID SEARCH FOR OPTIMAL GATES")
print("=" * 70)

best_configs = []

for accum_min in [1.5, 1.7, 2.0, 2.5, 3.0]:
    for rsi_max in [50, 55, 45, 40]:
        for ma20_min in [1, 2, 3, 5]:
            filtered = df[
                (df['accumulation'] > accum_min) &
                (df['rsi'] < rsi_max) &
                (df['price_above_ma20'] > ma20_min)
            ]

            if len(filtered) < 5:  # Need at least 5 trades
                continue

            n_trades = len(filtered)
            n_losers = len(filtered[filtered['return_pct'] < 0])
            n_winners = len(filtered[filtered['return_pct'] > 0])
            avg_return = filtered['return_pct'].mean()
            win_rate = n_winners / n_trades * 100 if n_trades > 0 else 0
            loser_rate = n_losers / n_trades * 100 if n_trades > 0 else 0

            best_configs.append({
                'accum_min': accum_min,
                'rsi_max': rsi_max,
                'ma20_min': ma20_min,
                'trades': n_trades,
                'winners': n_winners,
                'losers': n_losers,
                'win_rate': win_rate,
                'loser_rate': loser_rate,
                'avg_return': avg_return
            })

# Sort by loser rate (ascending), then by trades (descending)
configs_df = pd.DataFrame(best_configs)
configs_df = configs_df.sort_values(['loser_rate', 'trades'], ascending=[True, False])

print("\n🎯 TOP 20 CONFIGURATIONS (Sorted by lowest loser rate):")
print(configs_df.head(20).to_string(index=False))

# Zero loser configs
zero_loser = configs_df[configs_df['losers'] == 0]
if len(zero_loser) > 0:
    print("\n✅ ZERO LOSER CONFIGURATIONS:")
    print(zero_loser.to_string(index=False))
else:
    print("\n❌ No zero loser configuration found!")

    # Show best low loser configs
    low_loser = configs_df[configs_df['loser_rate'] <= 30]
    if len(low_loser) > 0:
        print("\n🟡 LOW LOSER CONFIGURATIONS (<30% loser rate):")
        print(low_loser.to_string(index=False))

# Additional analysis
print("\n" + "=" * 70)
print("ANALYSIS: What makes a loser?")
print("=" * 70)

winners = df[df['return_pct'] > 0]
losers = df[df['return_pct'] < 0]

print(f"\n{'Metric':<20} {'Winners Avg':>12} {'Losers Avg':>12} {'Diff':>10}")
print("-" * 56)
for col in ['rsi', 'accumulation', 'price_above_ma20']:
    w_avg = winners[col].mean()
    l_avg = losers[col].mean()
    diff = w_avg - l_avg
    print(f"{col:<20} {w_avg:>12.2f} {l_avg:>12.2f} {diff:>+10.2f}")

# Big losers (< -5%)
print("\n📊 BIG LOSERS (< -5% return) characteristics:")
big_losers = df[df['return_pct'] < -5]
print(f"  Count: {len(big_losers)}")
if len(big_losers) > 0:
    print(f"  Avg RSI: {big_losers['rsi'].mean():.1f}")
    print(f"  Avg Accum: {big_losers['accumulation'].mean():.2f}")
    print(f"  Avg MA20: {big_losers['price_above_ma20'].mean():.1f}%")

# Best performers
print("\n📊 BIG WINNERS (> +10% return) characteristics:")
big_winners = df[df['return_pct'] > 10]
print(f"  Count: {len(big_winners)}")
if len(big_winners) > 0:
    print(f"  Avg RSI: {big_winners['rsi'].mean():.1f}")
    print(f"  Avg Accum: {big_winners['accumulation'].mean():.2f}")
    print(f"  Avg MA20: {big_winners['price_above_ma20'].mean():.1f}%")
