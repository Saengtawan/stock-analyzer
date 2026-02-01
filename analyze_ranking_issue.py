#!/usr/bin/env python3
"""
Analyze Why Ranking Failed
Compare composite scores vs actual performance to find what we're missing
"""

import yfinance as yf
import numpy as np
import pandas as pd

# Latest screening results (12 healthcare/biotech stocks)
STOCKS = [
    {'rank': 1, 'symbol': 'CYTK', 'composite': 47.4, 'catalyst': 37, 'technical': 55, 'ai_prob': 45},
    {'rank': 2, 'symbol': 'HUM', 'composite': 46.2, 'catalyst': 45, 'technical': 50, 'ai_prob': 40},
    {'rank': 3, 'symbol': 'UTHR', 'composite': 45.8, 'catalyst': 40, 'technical': 50, 'ai_prob': 40},
    {'rank': 4, 'symbol': 'BIIB', 'composite': 44.5, 'catalyst': 35, 'technical': 50, 'ai_prob': 40},
    {'rank': 5, 'symbol': 'REGN', 'composite': 44.2, 'catalyst': 40, 'technical': 45, 'ai_prob': 40},
    {'rank': 6, 'symbol': 'VRTX', 'composite': 43.8, 'catalyst': 35, 'technical': 50, 'ai_prob': 35},
    {'rank': 7, 'symbol': 'ARQT', 'composite': 42.4, 'catalyst': 43, 'technical': 40, 'ai_prob': 35},
    {'rank': 8, 'symbol': 'ACAD', 'composite': 42.0, 'catalyst': 40, 'technical': 40, 'ai_prob': 35},
    {'rank': 9, 'symbol': 'PTCT', 'composite': 41.5, 'catalyst': 35, 'technical': 45, 'ai_prob': 35},
    {'rank': 10, 'symbol': 'INSM', 'composite': 40.8, 'catalyst': 30, 'technical': 45, 'ai_prob': 40},
    {'rank': 11, 'symbol': 'MDGL', 'composite': 39.2, 'catalyst': 25, 'technical': 45, 'ai_prob': 40},
    {'rank': 12, 'symbol': 'TXG', 'composite': 38.5, 'catalyst': 30, 'technical': 40, 'ai_prob': 35},
]

TARGET = 15.0

print("="*90)
print("🔍 ANALYZING RANKING FAILURE")
print("="*90)
print(f"Goal: Understand why ARQT (+33.8%) and ACAD (+27.3%) ranked #7 and #8")
print(f"Target: {TARGET}%+ in 30 days")
print("")

results = []

for stock_data in STOCKS:
    symbol = stock_data['symbol']
    rank = stock_data['rank']

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='3mo')
        info = ticker.info

        if hist.empty or len(hist) < 30:
            print(f"#{rank:2d} {symbol:6s}: ⚠️  Insufficient data")
            continue

        # 30-day performance
        price_30d_ago = hist['Close'].iloc[-30]
        price_now = hist['Close'].iloc[-1]
        actual_return = ((price_now - price_30d_ago) / price_30d_ago) * 100

        # Max return
        high_30d = hist['High'].iloc[-30:].max()
        max_return = ((high_30d - price_30d_ago) / price_30d_ago) * 100

        reached_target = max_return >= TARGET

        # Get additional metrics
        market_cap = info.get('marketCap', 0)
        pe_ratio = info.get('trailingPE', 0)

        status = "✅" if reached_target else "❌"

        print(f"#{rank:2d} {symbol:6s}: {status} Max: {max_return:+6.1f}% | Price: ${price_now:7.2f} | "
              f"Composite: {stock_data['composite']:4.1f} | Cat: {stock_data['catalyst']:2d} | "
              f"Tech: {stock_data['technical']:2d} | AI: {stock_data['ai_prob']:2.0f}%")

        results.append({
            'rank': rank,
            'symbol': symbol,
            'price_30d_ago': price_30d_ago,
            'price_now': price_now,
            'actual_return': actual_return,
            'max_return': max_return,
            'reached_target': reached_target,
            'composite': stock_data['composite'],
            'catalyst': stock_data['catalyst'],
            'technical': stock_data['technical'],
            'ai_prob': stock_data['ai_prob'],
            'market_cap': market_cap,
            'pe_ratio': pe_ratio
        })

    except Exception as e:
        print(f"#{rank:2d} {symbol:6s}: ❌ Error - {e}")

print("\n" + "="*90)

# Analyze what predicts success
if results:
    df = pd.DataFrame(results)

    winners = df[df['reached_target'] == True]
    losers = df[df['reached_target'] == False]

    print(f"\n📊 OVERALL RESULTS:")
    print(f"   Win Rate: {len(winners)}/{len(df)} = {len(winners)/len(df)*100:.1f}%")
    print(f"   Avg Max Return: {df['max_return'].mean():+.1f}%")

    print(f"\n🏆 WINNERS ({len(winners)}):")
    for _, r in winners.sort_values('max_return', ascending=False).iterrows():
        print(f"   #{r['rank']:2.0f} {r['symbol']:6s}: {r['max_return']:+6.1f}% | "
              f"Composite: {r['composite']:4.1f} | Cat: {r['catalyst']:2.0f} | "
              f"Tech: {r['technical']:2.0f} | AI: {r['ai_prob']:2.0f}%")

    print(f"\n📉 LOSERS ({len(losers)}):")
    for _, r in losers.sort_values('max_return', ascending=False).iterrows():
        print(f"   #{r['rank']:2.0f} {r['symbol']:6s}: {r['max_return']:+6.1f}% | "
              f"Composite: {r['composite']:4.1f} | Cat: {r['catalyst']:2.0f} | "
              f"Tech: {r['technical']:2.0f} | AI: {r['ai_prob']:2.0f}%")

    # Critical analysis: Compare scores between winners and losers
    print(f"\n🔬 SCORE ANALYSIS:")
    print(f"\n   Winners Avg Scores:")
    print(f"      Composite: {winners['composite'].mean():.1f}")
    print(f"      Catalyst:  {winners['catalyst'].mean():.1f}")
    print(f"      Technical: {winners['technical'].mean():.1f}")
    print(f"      AI Prob:   {winners['ai_prob'].mean():.1f}%")

    print(f"\n   Losers Avg Scores:")
    print(f"      Composite: {losers['composite'].mean():.1f}")
    print(f"      Catalyst:  {losers['catalyst'].mean():.1f}")
    print(f"      Technical: {losers['technical'].mean():.1f}")
    print(f"      AI Prob:   {losers['ai_prob'].mean():.1f}%")

    # Key insight: What differentiates winners?
    print(f"\n💡 KEY INSIGHTS:")

    # Compare top 2 ranked vs top 2 performers
    top_ranked = df.nsmallest(2, 'rank')
    top_performers = df.nlargest(2, 'max_return')

    print(f"\n   Top 2 RANKED:")
    for _, r in top_ranked.iterrows():
        print(f"      #{r['rank']:2.0f} {r['symbol']:6s}: {r['max_return']:+6.1f}% | "
              f"Cat: {r['catalyst']:2.0f} | Tech: {r['technical']:2.0f} | "
              f"Price: ${r['price_now']:6.2f}")

    print(f"\n   Top 2 PERFORMERS (should be ranked #1, #2):")
    for _, r in top_performers.iterrows():
        print(f"      #{r['rank']:2.0f} {r['symbol']:6s}: {r['max_return']:+6.1f}% | "
              f"Cat: {r['catalyst']:2.0f} | Tech: {r['technical']:2.0f} | "
              f"Price: ${r['price_now']:6.2f}")

    # Correlation analysis
    print(f"\n📈 CORRELATION WITH MAX RETURN:")
    print(f"   Composite Score: {df['composite'].corr(df['max_return']):.3f}")
    print(f"   Catalyst Score:  {df['catalyst'].corr(df['max_return']):.3f}")
    print(f"   Technical Score: {df['technical'].corr(df['max_return']):.3f}")
    print(f"   AI Probability:  {df['ai_prob'].corr(df['max_return']):.3f}")

    # Price analysis
    print(f"\n💰 PRICE ANALYSIS:")
    print(f"   Winners Avg Price: ${winners['price_now'].mean():.2f}")
    print(f"   Losers Avg Price:  ${losers['price_now'].mean():.2f}")

    # The smoking gun: Why did ARQT/ACAD rank low?
    arqt = df[df['symbol'] == 'ARQT'].iloc[0] if 'ARQT' in df['symbol'].values else None
    acad = df[df['symbol'] == 'ACAD'].iloc[0] if 'ACAD' in df['symbol'].values else None
    cytk = df[df['symbol'] == 'CYTK'].iloc[0] if 'CYTK' in df['symbol'].values else None
    hum = df[df['symbol'] == 'HUM'].iloc[0] if 'HUM' in df['symbol'].values else None

    if arqt is not None and cytk is not None:
        print(f"\n🚨 SMOKING GUN - Why ARQT ranked #7 instead of #1:")
        print(f"\n   CYTK (Ranked #1, but only {cytk['max_return']:+.1f}%):")
        print(f"      Catalyst:  {cytk['catalyst']:2.0f} pts")
        print(f"      Technical: {cytk['technical']:2.0f} pts ← HIGH TECHNICAL SCORE")
        print(f"      Composite: {cytk['composite']:.1f}")
        print(f"      Price: ${cytk['price_now']:.2f}")

        print(f"\n   ARQT (Ranked #7, but {arqt['max_return']:+.1f}%!):")
        print(f"      Catalyst:  {arqt['catalyst']:2.0f} pts ← HIGHER CATALYST!")
        print(f"      Technical: {arqt['technical']:2.0f} pts ← Lower technical")
        print(f"      Composite: {arqt['composite']:.1f}")
        print(f"      Price: ${arqt['price_now']:.2f} ← MUCH LOWER PRICE")

        print(f"\n   🎯 PROBLEM IDENTIFIED:")
        print(f"      Technical score weighted too heavily!")
        print(f"      CYTK got {cytk['technical'] - arqt['technical']} more technical points")
        print(f"      But ARQT had {arqt['catalyst'] - cytk['catalyst']} more catalyst points")
        print(f"      And ARQT has explosive low price (${arqt['price_now']:.2f} vs ${cytk['price_now']:.2f})")

print("\n" + "="*90)
print("💡 RECOMMENDED FIXES:")
print("="*90)
print("1. INCREASE catalyst weight (it's more predictive of big moves)")
print("2. DECREASE technical weight (less predictive for explosive moves)")
print("3. ADD low-price bonus (stocks <$50 have higher % potential)")
print("4. Consider using catalyst^2 or exponential for high catalyst scores")
print("="*90)
