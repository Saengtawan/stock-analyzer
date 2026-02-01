#!/usr/bin/env python3
"""
Backtest v4.2 with NEW Trailing Stop Fix
Compare: Before (old 5% threshold) vs After (new breakeven protection)
"""

import pandas as pd
import numpy as np
from loguru import logger

logger.info("=" * 80)
logger.info("🔬 BACKTEST v4.2 - WITH vs WITHOUT Trailing Stop Fix")
logger.info("=" * 80)
logger.info("")

# Load v4.2 results
df = pd.read_csv('backtest_new_criteria.csv')

logger.info(f"Loaded: {len(df)} trades from v4.2")
logger.info("")

# ========== SIMULATE OLD TRAILING STOP (5% threshold) ==========
def simulate_old_trailing_stop(entry_price, highest_price, min_return):
    """
    OLD: Trailing stop only activates if profit >5%
    Trailing stop: -3% from peak
    """
    profit_pct = ((highest_price - entry_price) / entry_price) * 100

    if profit_pct > 5.0:
        # Trailing stop active
        trailing_pct = -3.0

        # Calculate exit price if trailing triggered
        # We need to simulate price movement
        # Use min_return to estimate if trailing would have triggered

        # If min_return from peak is worse than -3%, trailing would trigger
        drawdown_from_peak = ((entry_price * (1 + min_return/100)) - highest_price) / highest_price * 100

        if drawdown_from_peak <= trailing_pct:
            # Trailing stop would trigger at peak - 3%
            exit_price = highest_price * (1 + trailing_pct/100)
            exit_return = ((exit_price - entry_price) / entry_price) * 100
            return True, exit_price, exit_return, 'TRAILING_STOP_OLD'

    return False, None, None, None


# ========== SIMULATE NEW TRAILING STOP (Breakeven Protection) ==========
def simulate_new_trailing_stop(entry_price, highest_price, min_return):
    """
    NEW: Trailing stop activates on ANY profit!
    - Profit <2%: Breakeven + 0.5%
    - Profit 2-5%: -4% trailing
    - Profit >5%: -3% trailing
    """
    profit_pct = ((highest_price - entry_price) / entry_price) * 100

    if profit_pct > 0:
        # Calculate trailing threshold
        if profit_pct >= 5.0:
            trailing_pct = -3.0
        elif profit_pct >= 2.0:
            trailing_pct = -4.0
        else:
            # Breakeven + 0.5% buffer, min -1%
            trailing_pct = max(-1.0, -(profit_pct - 0.5))

        # Estimate if trailing would trigger
        # Using min_return as worst case scenario
        exit_price_at_min = entry_price * (1 + min_return/100)
        drawdown_from_peak = ((exit_price_at_min - highest_price) / highest_price) * 100

        if drawdown_from_peak <= trailing_pct:
            # Trailing stop would trigger
            exit_price = highest_price * (1 + trailing_pct/100)
            exit_return = ((exit_price - entry_price) / entry_price) * 100
            return True, exit_price, exit_return, 'TRAILING_STOP_NEW'

    return False, None, None, None


# ========== RUN SIMULATION ==========
logger.info("🔄 Simulating trades with OLD trailing stop (5% threshold)...")
logger.info("")

old_results = []
for idx, row in df.iterrows():
    symbol = row['symbol']
    entry_price = row['entry_price']
    exit_price = row['exit_price']
    actual_return = row['actual_return']
    max_return = row['max_return']
    min_return = row['min_return']

    # Calculate highest price
    highest_price = entry_price * (1 + max_return/100)

    # Simulate old trailing stop
    triggered, new_exit_price, new_return, reason = simulate_old_trailing_stop(
        entry_price, highest_price, min_return
    )

    if triggered:
        old_results.append({
            'symbol': symbol,
            'entry_price': entry_price,
            'original_exit': exit_price,
            'original_return': actual_return,
            'new_exit': new_exit_price,
            'new_return': new_return,
            'max_return': max_return,
            'reason': reason
        })
    else:
        # No change
        old_results.append({
            'symbol': symbol,
            'entry_price': entry_price,
            'original_exit': exit_price,
            'original_return': actual_return,
            'new_exit': exit_price,
            'new_return': actual_return,
            'max_return': max_return,
            'reason': 'NO_CHANGE'
        })

df_old = pd.DataFrame(old_results)

logger.info("🔄 Simulating trades with NEW trailing stop (breakeven protection)...")
logger.info("")

new_results = []
for idx, row in df.iterrows():
    symbol = row['symbol']
    entry_price = row['entry_price']
    exit_price = row['exit_price']
    actual_return = row['actual_return']
    max_return = row['max_return']
    min_return = row['min_return']

    # Calculate highest price
    highest_price = entry_price * (1 + max_return/100)

    # Simulate new trailing stop
    triggered, new_exit_price, new_return, reason = simulate_new_trailing_stop(
        entry_price, highest_price, min_return
    )

    if triggered:
        new_results.append({
            'symbol': symbol,
            'entry_price': entry_price,
            'original_exit': exit_price,
            'original_return': actual_return,
            'new_exit': new_exit_price,
            'new_return': new_return,
            'max_return': max_return,
            'reason': reason
        })
    else:
        # No change
        new_results.append({
            'symbol': symbol,
            'entry_price': entry_price,
            'original_exit': exit_price,
            'original_return': actual_return,
            'new_exit': exit_price,
            'new_return': actual_return,
            'max_return': max_return,
            'reason': 'NO_CHANGE'
        })

df_new = pd.DataFrame(new_results)

# Save results
df_old.to_csv('backtest_v4.2_old_trailing.csv', index=False)
df_new.to_csv('backtest_v4.2_new_trailing.csv', index=False)

# ========== COMPARE RESULTS ==========
logger.info("=" * 80)
logger.info("📊 COMPARISON: OLD vs NEW Trailing Stop")
logger.info("=" * 80)
logger.info("")

# Original (no trailing stop changes)
original_winners = len(df[df['actual_return'] > 0])
original_losers = len(df[df['actual_return'] <= 0])
original_win_rate = original_winners / len(df) * 100
original_avg = df['actual_return'].mean()
original_median = df['actual_return'].median()

logger.info("📌 ORIGINAL (v4.2 without any trailing stop changes):")
logger.info(f"   Trades: {len(df)}")
logger.info(f"   Winners: {original_winners} ({original_win_rate:.1f}%)")
logger.info(f"   Losers: {original_losers}")
logger.info(f"   Avg Return: {original_avg:+.2f}%")
logger.info(f"   Median Return: {original_median:+.2f}%")
logger.info("")

# Old trailing stop
old_winners = len(df_old[df_old['new_return'] > 0])
old_losers = len(df_old[df_old['new_return'] <= 0])
old_win_rate = old_winners / len(df_old) * 100
old_avg = df_old['new_return'].mean()
old_median = df_old['new_return'].median()
old_changed = len(df_old[df_old['reason'] == 'TRAILING_STOP_OLD'])

logger.info("📌 OLD TRAILING STOP (5% threshold):")
logger.info(f"   Trades: {len(df_old)}")
logger.info(f"   Winners: {old_winners} ({old_win_rate:.1f}%)")
logger.info(f"   Losers: {old_losers}")
logger.info(f"   Avg Return: {old_avg:+.2f}%")
logger.info(f"   Median Return: {old_median:+.2f}%")
logger.info(f"   Trades changed by trailing: {old_changed}")
logger.info("")

# New trailing stop
new_winners = len(df_new[df_new['new_return'] > 0])
new_losers = len(df_new[df_new['new_return'] <= 0])
new_win_rate = new_winners / len(df_new) * 100
new_avg = df_new['new_return'].mean()
new_median = df_new['new_return'].median()
new_changed = len(df_new[df_new['reason'] == 'TRAILING_STOP_NEW'])

logger.info("📌 NEW TRAILING STOP (Breakeven Protection):")
logger.info(f"   Trades: {len(df_new)}")
logger.info(f"   Winners: {new_winners} ({new_win_rate:.1f}%)")
logger.info(f"   Losers: {new_losers}")
logger.info(f"   Avg Return: {new_avg:+.2f}%")
logger.info(f"   Median Return: {new_median:+.2f}%")
logger.info(f"   Trades changed by trailing: {new_changed}")
logger.info("")

# ========== IMPROVEMENTS ==========
logger.info("=" * 80)
logger.info("📈 IMPROVEMENTS (NEW vs ORIGINAL)")
logger.info("=" * 80)
logger.info("")

win_rate_improvement = new_win_rate - original_win_rate
avg_improvement = new_avg - original_avg
median_improvement = new_median - original_median

logger.info(f"Win Rate:      {original_win_rate:.1f}% → {new_win_rate:.1f}% ({win_rate_improvement:+.1f}%)")
logger.info(f"Avg Return:    {original_avg:+.2f}% → {new_avg:+.2f}% ({avg_improvement:+.2f}%)")
logger.info(f"Median Return: {original_median:+.2f}% → {new_median:+.2f}% ({median_improvement:+.2f}%)")
logger.info(f"Losers:        {original_losers} → {new_losers} ({new_losers - original_losers:+d})")
logger.info("")

# ========== BIG LOSERS ANALYSIS ==========
logger.info("=" * 80)
logger.info("💀 BIG LOSERS ANALYSIS (< -10%)")
logger.info("=" * 80)
logger.info("")

original_big_losers = df[df['actual_return'] < -10]
new_big_losers = df_new[df_new['new_return'] < -10]

logger.info(f"ORIGINAL: {len(original_big_losers)} big losers")
for _, row in original_big_losers.iterrows():
    logger.info(f"  {row['symbol']:6s}: {row['actual_return']:>7.2f}% (max was {row['max_return']:>6.2f}%)")

logger.info("")
logger.info(f"NEW: {len(new_big_losers)} big losers")
if len(new_big_losers) > 0:
    for _, row in new_big_losers.iterrows():
        logger.info(f"  {row['symbol']:6s}: {row['new_return']:>7.2f}% (max was {row['max_return']:>6.2f}%)")
else:
    logger.info("  🎉 NO BIG LOSERS! All protected by trailing stop!")

logger.info("")

# ========== SPECIFIC CASES ==========
logger.info("=" * 80)
logger.info("🔍 SPECIFIC CASES - How trailing stop helped")
logger.info("=" * 80)
logger.info("")

# Find biggest improvements
df_comparison = df_new.copy()
df_comparison['improvement'] = df_comparison['new_return'] - df_comparison['original_return']
biggest_improvements = df_comparison.nlargest(10, 'improvement')

logger.info("Top 10 Biggest Improvements:")
logger.info(f"{'Symbol':<8} {'Original':<10} {'New':<10} {'Improvement':<12} {'Max Gain'}")
logger.info("-" * 60)

for _, row in biggest_improvements.iterrows():
    if row['improvement'] > 0.1:  # At least 0.1% improvement
        logger.info(
            f"{row['symbol']:<8} "
            f"{row['original_return']:>8.2f}% → "
            f"{row['new_return']:>8.2f}% "
            f"({row['improvement']:>+8.2f}%)  "
            f"Max: {row['max_return']:>6.2f}%"
        )

logger.info("")

# ========== SUMMARY ==========
logger.info("=" * 80)
logger.info("🎯 FINAL SUMMARY")
logger.info("=" * 80)
logger.info("")

if new_win_rate > original_win_rate and new_median > original_median:
    logger.info("✅ GREAT SUCCESS!")
    logger.info(f"   Win rate improved: {win_rate_improvement:+.1f}%")
    logger.info(f"   Median improved: {median_improvement:+.2f}%")
    logger.info(f"   Big losers reduced: {len(original_big_losers)} → {len(new_big_losers)}")
    logger.info("")
    logger.info("🚀 RECOMMENDATION: Deploy new trailing stop to production!")
elif new_win_rate > original_win_rate or new_median > original_median:
    logger.info("✅ GOOD IMPROVEMENT!")
    logger.info(f"   Win rate: {win_rate_improvement:+.1f}%")
    logger.info(f"   Median: {median_improvement:+.2f}%")
    logger.info("")
    logger.info("👍 RECOMMENDATION: Consider deploying (some improvement)")
else:
    logger.info("⚠️ MIXED RESULTS")
    logger.info(f"   Win rate: {win_rate_improvement:+.1f}%")
    logger.info(f"   Median: {median_improvement:+.2f}%")
    logger.info("")
    logger.info("🤔 RECOMMENDATION: Review logic or thresholds")

logger.info("")
logger.info("=" * 80)
logger.info("📁 Results saved:")
logger.info("   backtest_v4.2_old_trailing.csv")
logger.info("   backtest_v4.2_new_trailing.csv")
logger.info("=" * 80)
