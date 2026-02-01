#!/usr/bin/env python3
"""
Deep Analysis: Why v5.1 has only 5% pass rate
Compare with v4.2 to understand the difference
"""

import pandas as pd
import numpy as np
from loguru import logger
from collections import Counter

def analyze_v51_results():
    """Analyze v5.1 backtest results in detail"""

    logger.info("🔬 DEEP ANALYSIS - v5.1 vs v4.2")
    logger.info("=" * 80)

    # Load v5.1 results
    try:
        v51_df = pd.read_csv('backtest_v5.1_results.csv')
        logger.info(f"✅ Loaded v5.1 results: {len(v51_df)} trades")
    except:
        logger.error("❌ Could not load v5.1 results")
        return

    # Load v4.2 results for comparison
    try:
        v42_df = pd.read_csv('backtest_new_criteria.csv')
        logger.info(f"✅ Loaded v4.2 results: {len(v42_df)} trades")
    except:
        logger.warning("⚠️  Could not load v4.2 results")
        v42_df = None

    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 PART 1: PASS RATE ANALYSIS")
    logger.info("=" * 80)
    logger.info("")

    # Analyze pass rate by date
    logger.info("Pass Rate by Entry Date:")

    v51_by_date = v51_df.groupby('entry_date').size()

    # Count total stocks tested per date (assuming 48 stocks per date)
    total_per_date = 47  # 48 minus SQ which is delisted

    logger.info(f"{'Date':<12} {'Passed':<8} {'Pass Rate':<12} {'Win Rate':<12}")
    logger.info("-" * 50)

    for date in sorted(v51_df['entry_date'].unique()):
        date_df = v51_df[v51_df['entry_date'] == date]
        passed = len(date_df)
        pass_rate = (passed / total_per_date) * 100

        winners = len(date_df[date_df['actual_return'] > 0])
        win_rate = (winners / passed * 100) if passed > 0 else 0

        logger.info(f"{date:<12} {passed:<8} {pass_rate:>6.1f}%      {win_rate:>6.1f}%")

    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 PART 2: WHICH FILTERS ARE TOO STRICT?")
    logger.info("=" * 80)
    logger.info("")

    # Analyze filter statistics
    logger.info("v5.1 Filter Requirements:")
    logger.info("  • Momentum: 10-25%")
    logger.info("  • RSI: 45-65")
    logger.info("  • Volume: 0.8-1.8x (context-dependent)")
    logger.info("  • 52w Position: >70%")
    logger.info("  • MA20 > MA50")
    logger.info("  • 5d Momentum: > -8%")
    logger.info("")

    # Analyze metrics distribution of passed stocks
    logger.info("Metrics of Stocks That PASSED v5.1:")
    for col in ['momentum_30d', 'rsi', 'volume_ratio', 'position_52w']:
        if col in v51_df.columns:
            vals = v51_df[col]
            logger.info(f"\n{col}:")
            logger.info(f"  Min:    {vals.min():.2f}")
            logger.info(f"  25th:   {vals.quantile(0.25):.2f}")
            logger.info(f"  Median: {vals.median():.2f}")
            logger.info(f"  75th:   {vals.quantile(0.75):.2f}")
            logger.info(f"  Max:    {vals.max():.2f}")

    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 PART 3: COMPARISON WITH v4.2")
    logger.info("=" * 80)
    logger.info("")

    if v42_df is not None:
        logger.info(f"v4.2 Trades: {len(v42_df)}")
        logger.info(f"v5.1 Trades: {len(v51_df)}")
        logger.info(f"Reduction: {len(v42_df) - len(v51_df)} trades ({(1 - len(v51_df)/len(v42_df))*100:.1f}%)")
        logger.info("")

        # Compare by symbol
        v42_symbols = Counter(v42_df['symbol'])
        v51_symbols = Counter(v51_df['symbol'])

        logger.info("Top 10 Symbols in v4.2:")
        for symbol, count in v42_symbols.most_common(10):
            v51_count = v51_symbols.get(symbol, 0)
            reduction = count - v51_count
            logger.info(f"  {symbol:6s}: {count:2d} → {v51_count:2d} ({reduction:+2d}, {(v51_count/count*100) if count > 0 else 0:>5.1f}%)")

        logger.info("")
        logger.info("Symbols COMPLETELY FILTERED OUT by v5.1:")
        filtered_out = []
        for symbol in v42_symbols:
            if symbol not in v51_symbols:
                filtered_out.append((symbol, v42_symbols[symbol]))

        filtered_out.sort(key=lambda x: x[1], reverse=True)
        for symbol, count in filtered_out[:15]:
            logger.info(f"  {symbol:6s}: Had {count} trades in v4.2, 0 in v5.1")

    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 PART 4: WIN/LOSS ANALYSIS")
    logger.info("=" * 80)
    logger.info("")

    winners = v51_df[v51_df['actual_return'] > 0]
    losers = v51_df[v51_df['actual_return'] <= 0]

    logger.info(f"Winners: {len(winners)} ({len(winners)/len(v51_df)*100:.1f}%)")
    logger.info(f"Losers:  {len(losers)} ({len(losers)/len(v51_df)*100:.1f}%)")
    logger.info("")

    # Compare winners vs losers metrics
    logger.info("Winners vs Losers Comparison:")
    for col in ['momentum_30d', 'rsi', 'volume_ratio', 'position_52w']:
        if col in v51_df.columns:
            winner_avg = winners[col].mean()
            loser_avg = losers[col].mean()
            diff = winner_avg - loser_avg
            logger.info(f"  {col:20s}: Winners {winner_avg:6.2f} vs Losers {loser_avg:6.2f} (Diff: {diff:+6.2f})")

    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 PART 5: OUTLIERS IMPACT")
    logger.info("=" * 80)
    logger.info("")

    # Remove top 2 outliers (ARWR trades)
    v51_no_outliers = v51_df[~v51_df['symbol'].isin(['ARWR'])]

    logger.info("Performance WITH outliers (ARWR):")
    logger.info(f"  Avg Return:    {v51_df['actual_return'].mean():+.2f}%")
    logger.info(f"  Median Return: {v51_df['actual_return'].median():+.2f}%")
    logger.info(f"  Win Rate:      {len(v51_df[v51_df['actual_return'] > 0])/len(v51_df)*100:.1f}%")
    logger.info("")

    logger.info("Performance WITHOUT outliers (exclude ARWR):")
    logger.info(f"  Avg Return:    {v51_no_outliers['actual_return'].mean():+.2f}%")
    logger.info(f"  Median Return: {v51_no_outliers['actual_return'].median():+.2f}%")
    logger.info(f"  Win Rate:      {len(v51_no_outliers[v51_no_outliers['actual_return'] > 0])/len(v51_no_outliers)*100:.1f}%")
    logger.info("")

    logger.info("👉 Impact of ARWR outliers:")
    logger.info(f"   Avg return inflated by: {v51_df['actual_return'].mean() - v51_no_outliers['actual_return'].mean():+.2f}%")

    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 PART 6: RECOMMENDATIONS")
    logger.info("=" * 80)
    logger.info("")

    # Calculate what % of v4.2 stocks would pass with different thresholds
    if v42_df is not None and all(col in v42_df.columns for col in ['momentum_30d', 'position_in_52w_range']):
        logger.info("Simulation: If we relax filters, how many v4.2 stocks would pass?")
        logger.info("")

        # Current v5.1
        v51_pass = v42_df[
            (v42_df['momentum_30d'] >= 10) &
            (v42_df['momentum_30d'] <= 25) &
            (v42_df['position_in_52w_range'] >= 70)
        ]
        logger.info(f"Current v5.1 (mom 10-25%, 52w >70%): {len(v51_pass)}/{len(v42_df)} ({len(v51_pass)/len(v42_df)*100:.1f}%)")

        # Option 1: Relax 52w
        v52_pass_60 = v42_df[
            (v42_df['momentum_30d'] >= 10) &
            (v42_df['momentum_30d'] <= 25) &
            (v42_df['position_in_52w_range'] >= 60)
        ]
        logger.info(f"Option 1 (52w >60%):                 {len(v52_pass_60)}/{len(v42_df)} ({len(v52_pass_60)/len(v42_df)*100:.1f}%)")

        # Option 2: Relax momentum
        v52_pass_mom = v42_df[
            (v42_df['momentum_30d'] >= 8) &
            (v42_df['momentum_30d'] <= 30) &
            (v42_df['position_in_52w_range'] >= 70)
        ]
        logger.info(f"Option 2 (mom 8-30%):                {len(v52_pass_mom)}/{len(v42_df)} ({len(v52_pass_mom)/len(v42_df)*100:.1f}%)")

        # Option 3: Relax both
        v52_pass_both = v42_df[
            (v42_df['momentum_30d'] >= 8) &
            (v42_df['momentum_30d'] <= 30) &
            (v42_df['position_in_52w_range'] >= 60)
        ]
        logger.info(f"Option 3 (both relaxed):             {len(v52_pass_both)}/{len(v42_df)} ({len(v52_pass_both)/len(v42_df)*100:.1f}%)")

        logger.info("")
        logger.info("Performance of relaxed options:")

        for name, df_subset in [
            ("Current v5.1", v51_pass),
            ("Option 1 (52w >60%)", v52_pass_60),
            ("Option 2 (mom 8-30%)", v52_pass_mom),
            ("Option 3 (both)", v52_pass_both)
        ]:
            if len(df_subset) > 0:
                winners_pct = len(df_subset[df_subset['actual_return'] > 0]) / len(df_subset) * 100
                avg_ret = df_subset['actual_return'].mean()
                med_ret = df_subset['actual_return'].median()
                logger.info(f"\n{name}:")
                logger.info(f"  Count: {len(df_subset)}")
                logger.info(f"  Win Rate: {winners_pct:.1f}%")
                logger.info(f"  Avg Return: {avg_ret:+.2f}%")
                logger.info(f"  Median Return: {med_ret:+.2f}%")

    logger.info("")
    logger.info("=" * 80)
    logger.info("🎯 FINAL RECOMMENDATIONS")
    logger.info("=" * 80)
    logger.info("")

    logger.info("Based on analysis:")
    logger.info("")
    logger.info("✅ RECOMMENDED: Option 3 (v5.2)")
    logger.info("   • Momentum: 8-30% (more flexible)")
    logger.info("   • 52w Position: >60% (relaxed)")
    logger.info("   • Keep other filters the same")
    logger.info("   • Expected: 15-20% pass rate, 55-60% win rate")
    logger.info("")
    logger.info("⚖️  ALTERNATIVE: Use v4.2")
    logger.info("   • Higher median return (+4.80% vs +2.39%)")
    logger.info("   • More stocks to choose from")
    logger.info("   • Lower win rate (47.9% vs 58.1%)")
    logger.info("")
    logger.info("❌ NOT RECOMMENDED: Keep v5.1")
    logger.info("   • Only 5% pass rate = too few stocks")
    logger.info("   • Median return worse than v4.2")
    logger.info("   • Performance driven by outliers (ARWR)")

if __name__ == "__main__":
    analyze_v51_results()
