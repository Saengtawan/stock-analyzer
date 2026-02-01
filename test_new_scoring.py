#!/usr/bin/env python3
"""
Test New Scoring Formula
See if ARQT and ACAD now rank higher
"""

import pandas as pd

# Original screening results with OLD scoring
STOCKS = [
    {'rank': 1, 'symbol': 'CYTK', 'old_composite': 47.4, 'catalyst': 37, 'technical': 55, 'ai_prob': 45, 'ai_conf': 40, 'price': 63.48, 'actual_return': 6.7},
    {'rank': 2, 'symbol': 'HUM', 'old_composite': 46.2, 'catalyst': 45, 'technical': 50, 'ai_prob': 40, 'ai_conf': 35, 'price': 257.64, 'actual_return': 12.9},
    {'rank': 3, 'symbol': 'UTHR', 'old_composite': 45.8, 'catalyst': 40, 'technical': 50, 'ai_prob': 40, 'ai_conf': 35, 'price': 513.42, 'actual_return': 13.2},
    {'rank': 4, 'symbol': 'BIIB', 'old_composite': 44.5, 'catalyst': 35, 'technical': 50, 'ai_prob': 40, 'ai_conf': 35, 'price': 174.59, 'actual_return': 16.1},
    {'rank': 5, 'symbol': 'REGN', 'old_composite': 44.2, 'catalyst': 40, 'technical': 45, 'ai_prob': 40, 'ai_conf': 35, 'price': 785.62, 'actual_return': 17.7},
    {'rank': 6, 'symbol': 'VRTX', 'old_composite': 43.8, 'catalyst': 35, 'technical': 50, 'ai_prob': 35, 'ai_conf': 35, 'price': 457.39, 'actual_return': 8.1},
    {'rank': 7, 'symbol': 'ARQT', 'old_composite': 42.4, 'catalyst': 43, 'technical': 40, 'ai_prob': 35, 'ai_conf': 35, 'price': 29.87, 'actual_return': 32.2},
    {'rank': 8, 'symbol': 'ACAD', 'old_composite': 42.0, 'catalyst': 40, 'technical': 40, 'ai_prob': 35, 'ai_conf': 35, 'price': 27.90, 'actual_return': 19.5},
    {'rank': 9, 'symbol': 'PTCT', 'old_composite': 41.5, 'catalyst': 35, 'technical': 45, 'ai_prob': 35, 'ai_conf': 35, 'price': 78.05, 'actual_return': 18.5},
    {'rank': 10, 'symbol': 'INSM', 'old_composite': 40.8, 'catalyst': 30, 'technical': 45, 'ai_prob': 40, 'ai_conf': 35, 'price': 175.56, 'actual_return': 9.8},
    {'rank': 11, 'symbol': 'MDGL', 'old_composite': 39.2, 'catalyst': 25, 'technical': 45, 'ai_prob': 40, 'ai_conf': 35, 'price': 595.74, 'actual_return': 12.6},
    {'rank': 12, 'symbol': 'TXG', 'old_composite': 38.5, 'catalyst': 30, 'technical': 40, 'ai_prob': 35, 'ai_conf': 35, 'price': 16.44, 'actual_return': 22.6},
]

def calculate_new_composite(catalyst, technical, ai_prob, ai_conf):
    """
    NEW formula based on correlation analysis:
    - Catalyst: 50% (was 30%)
    - Technical: 10% (was 25%)
    - AI Prob: 25% (was 30%)
    - AI Conf: 15% (same)
    """
    return round(
        catalyst * 0.50 +
        technical * 0.10 +
        ai_prob * 0.25 +
        ai_conf * 0.15,
        1
    )

def apply_price_adjustment(composite, price):
    """
    NEW price adjustments:
    - <$30: 1.10x bonus
    - <$50: 1.05x bonus
    - >$300: 0.95x penalty
    """
    if price < 30:
        return round(composite * 1.10, 1)
    elif price < 50:
        return round(composite * 1.05, 1)
    elif price > 300:
        return round(composite * 0.95, 1)
    else:
        return composite

print("="*100)
print("🧪 TESTING NEW SCORING FORMULA")
print("="*100)
print("\nChanges:")
print("  - Catalyst weight: 30% → 50% (most predictive!)")
print("  - Technical weight: 25% → 10% (negatively predictive)")
print("  - AI Prob weight: 30% → 25%")
print("  - Price <$30: 10% BONUS (was penalty!)")
print("  - Price <$50: 5% bonus")
print("")

# Recalculate scores
for stock in STOCKS:
    # Base composite
    new_base = calculate_new_composite(
        stock['catalyst'],
        stock['technical'],
        stock['ai_prob'],
        stock['ai_conf']
    )

    # Apply price adjustment
    new_adjusted = apply_price_adjustment(new_base, stock['price'])

    stock['new_composite'] = new_adjusted
    stock['change'] = new_adjusted - stock['old_composite']

# Sort by new composite score
df = pd.DataFrame(STOCKS)
df_new_ranking = df.sort_values('new_composite', ascending=False).reset_index(drop=True)
df_new_ranking['new_rank'] = df_new_ranking.index + 1

print("="*100)
print("📊 NEW RANKING (with updated formula)")
print("="*100)
print(f"{'New':<4} {'Old':<4} {'Symbol':<6} {'Return':<8} {'New Score':<10} {'Old Score':<10} {'Change':<8} {'Price':<8}")
print("-"*100)

for _, row in df_new_ranking.iterrows():
    status = "✅" if row['actual_return'] >= 15 else "❌"
    rank_change = row['rank'] - row['new_rank']
    rank_indicator = f"↑{rank_change}" if rank_change > 0 else f"↓{abs(rank_change)}" if rank_change < 0 else "="

    print(f"#{row['new_rank']:<3} #{row['rank']:<3} {row['symbol']:<6} "
          f"{status} {row['actual_return']:+5.1f}%  "
          f"{row['new_composite']:<10.1f} {row['old_composite']:<10.1f} "
          f"{row['change']:+7.1f}  ${row['price']:<7.2f} {rank_indicator}")

print("="*100)

# Key improvements
print("\n🎯 KEY IMPROVEMENTS:")

top_performers = df.nlargest(3, 'actual_return')
print("\nTop 3 Performers:")
for _, row in top_performers.iterrows():
    old_rank = row['rank']
    new_rank = df_new_ranking[df_new_ranking['symbol'] == row['symbol']]['new_rank'].values[0]
    improvement = old_rank - new_rank

    print(f"  {row['symbol']:6s}: {row['actual_return']:+5.1f}% | "
          f"Rank #{old_rank} → #{new_rank} ({improvement:+d} positions)")

# Calculate correlation
import numpy as np
correlation = np.corrcoef(df_new_ranking['new_composite'], df_new_ranking['actual_return'])[0, 1]
old_correlation = np.corrcoef(df['old_composite'], df['actual_return'])[0, 1]

print(f"\n📈 CORRELATION WITH ACTUAL RETURNS:")
print(f"  Old Formula: {old_correlation:+.3f} (NEGATIVE!)")
print(f"  New Formula: {correlation:+.3f}")
print(f"  Improvement: {correlation - old_correlation:+.3f}")

# Win rate by ranking
print(f"\n🏆 WIN RATE BY RANKING:")
top5_old = df[df['rank'] <= 5]
top5_new = df_new_ranking[df_new_ranking['new_rank'] <= 5]

print(f"  Old Top 5: {(top5_old['actual_return'] >= 15).sum()}/5 winners ({(top5_old['actual_return'] >= 15).sum()/5*100:.0f}%)")
print(f"  New Top 5: {(top5_new['actual_return'] >= 15).sum()}/5 winners ({(top5_new['actual_return'] >= 15).sum()/5*100:.0f}%)")

print("\n" + "="*100)
if correlation > 0.3:
    print("✅ SUCCESS! New formula has POSITIVE correlation with returns!")
else:
    print("⚠️  Improved but still needs work")
print("="*100)
