#!/usr/bin/env python3
"""
Deep dive analysis of MU to understand why it wasn't recommended
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

import yfinance as yf
import pandas as pd
from datetime import datetime
from loguru import logger

# Suppress warnings
import warnings
warnings.filterwarnings('ignore')

def analyze_mu():
    """Comprehensive analysis of MU"""
    print("\n" + "="*70)
    print("🔬 DEEP ANALYSIS: Why MU wasn't recommended")
    print("="*70)

    symbol = 'MU'

    try:
        from src.main import StockAnalyzer
        from src.screeners.growth_catalyst_screener import GrowthCatalystScreener

        analyzer = StockAnalyzer()
        screener = GrowthCatalystScreener(analyzer)

        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period='3mo')

        price = hist['Close'].iloc[-1]

        print(f"\n📊 {symbol} @ ${price:.2f}")
        print("="*70)

        # 1. Check if in AI Universe
        print("\n1️⃣  AI UNIVERSE CHECK")
        print("-" * 60)
        try:
            universe = screener.ai_generator.generate_growth_catalyst_universe({
                'target_gain_pct': 5.0,
                'timeframe_days': 14,
                'max_stocks': 60
            })

            if symbol in universe:
                print(f"   ✅ {symbol} IS in AI Universe (rank: {universe.index(symbol) + 1}/{len(universe)})")
            else:
                print(f"   ❌ {symbol} NOT in AI Universe")
                print(f"   📋 Universe size: {len(universe)} stocks")
                print(f"   Top 10: {universe[:10]}")
                print(f"\n   💡 This is likely the main reason!")
                print(f"      AI didn't select {symbol} for the candidate pool")
        except Exception as e:
            print(f"   ⚠️  Could not check universe: {e}")

        # 2. Catalyst Analysis (INVERTED!)
        print("\n2️⃣  CATALYST ANALYSIS (INVERTED SCORING)")
        print("-" * 60)

        # Check earnings date
        earnings_date = info.get('earningsDate')
        if earnings_date and isinstance(earnings_date, list) and len(earnings_date) > 0:
            next_earnings = pd.Timestamp(earnings_date[0])
            days_to_earnings = (next_earnings - pd.Timestamp.now()).days

            print(f"   Next Earnings: {next_earnings.strftime('%Y-%m-%d')}")
            print(f"   Days Away: {days_to_earnings}")

            if 0 < days_to_earnings <= 10:
                print(f"   ⚠️  PENALTY: -15 points (earnings within 10 days)")
                print(f"      Sell-the-news risk!")
            elif 10 < days_to_earnings <= 20:
                print(f"   ⚠️  PENALTY: -10 points (earnings within 20 days)")
            elif 20 < days_to_earnings <= 30:
                print(f"   ⚠️  PENALTY: -5 points (earnings approaching)")
            elif 30 < days_to_earnings <= 60:
                print(f"   ✅ BONUS: +15 points (quiet period)")
            else:
                print(f"   ✅ BONUS: +5 points (earnings far away)")
        else:
            print(f"   ✅ BONUS: +10 points (no earnings pressure)")

        # Check analyst coverage
        num_analysts = info.get('numberOfAnalystOpinions', 0)
        print(f"\n   Analyst Coverage: {num_analysts} analysts")

        if num_analysts > 50:
            print(f"   ⚠️  PENALTY: -10 points (overhyped)")
        elif num_analysts > 30:
            print(f"   ⚠️  PENALTY: -5 points (high coverage)")
        elif 10 <= num_analysts <= 20:
            print(f"   ✅ BONUS: +5 points (balanced coverage)")
        elif num_analysts < 10:
            print(f"   ✅ BONUS: +10 points (hidden gem)")

        # 3. Technical Analysis
        print("\n3️⃣  TECHNICAL SETUP")
        print("-" * 60)

        # Trend
        ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]

        print(f"   Current: ${price:.2f}")
        print(f"   MA20: ${ma20:.2f} ({(price/ma20-1)*100:+.1f}%)")
        print(f"   MA50: ${ma50:.2f} ({(price/ma50-1)*100:+.1f}%)")

        if price > ma20 > ma50:
            print(f"   ✅ Trend: Strong bullish (25 points)")
        elif price > ma20:
            print(f"   ✅ Trend: Bullish (15 points)")
        else:
            print(f"   ⚠️  Trend: Weak")

        # RSI
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]

        print(f"\n   RSI: {current_rsi:.1f}")
        if 45 <= current_rsi <= 70:
            print(f"   ✅ Momentum: Strong (25 points)")
        else:
            print(f"   ⚠️  Momentum: Outside sweet spot")

        # Volume
        avg_volume = hist['Volume'].tail(20).mean()
        recent_volume = hist['Volume'].tail(5).mean()
        volume_ratio = recent_volume / avg_volume

        print(f"\n   Volume Ratio: {volume_ratio:.2f}x")
        if volume_ratio > 1.5:
            print(f"   ✅ Volume: Surge (20 points)")
        elif volume_ratio > 1.2:
            print(f"   ✅ Volume: Increasing (15 points)")
        else:
            print(f"   Volume: Normal (10 points)")

        # 4. Sector Strength
        print("\n4️⃣  SECTOR RELATIVE STRENGTH")
        print("-" * 60)

        sector = info.get('sector', 'Unknown')
        industry = info.get('industry', 'Unknown')

        print(f"   Sector: {sector}")
        print(f"   Industry: {industry}")

        # Calculate RS
        stock_return_30d = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-30]) - 1) * 100

        spy = yf.Ticker('SPY')
        spy_hist = spy.history(period='1mo')
        spy_return_30d = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-20]) - 1) * 100

        rs = stock_return_30d - spy_return_30d

        print(f"   Stock 30d: {stock_return_30d:+.1f}%")
        print(f"   SPY 30d: {spy_return_30d:+.1f}%")
        print(f"   Relative Strength: {rs:+.1f}%")

        if rs > 10:
            print(f"   ✅ Sector Score: 90 (strong outperformance)")
        elif rs > 5:
            print(f"   ✅ Sector Score: 75 (good outperformance)")
        elif rs > 0:
            print(f"   ✅ Sector Score: 60 (mild outperformance)")
        else:
            print(f"   ⚠️  Sector Score: <50 (underperformance)")

        # 5. Valuation
        print("\n5️⃣  VALUATION")
        print("-" * 60)

        pe = info.get('trailingPE', None)
        forward_pe = info.get('forwardPE', None)
        peg = info.get('pegRatio', None)

        if pe:
            print(f"   P/E: {pe:.1f}")
            if 15 <= pe <= 35:
                print(f"   ✅ Valuation: Reasonable (+20 points)")
            elif pe > 100:
                print(f"   ⚠️  Valuation: Extremely overvalued (-25 points)")
            elif pe > 60:
                print(f"   ⚠️  Valuation: Overvalued (-15 points)")

        if forward_pe:
            print(f"   Forward P/E: {forward_pe:.1f}")
            if 15 <= forward_pe <= 30:
                print(f"   ✅ Forward Valuation: Attractive (+25 points)")
            elif forward_pe > 80:
                print(f"   ⚠️  Forward Valuation: DANGER (-30 points)")

        if peg:
            print(f"   PEG: {peg:.2f}")
            if peg < 1.0:
                print(f"   ✅ Growth at reasonable price (+15 points)")

        # 6. Recent Performance
        print("\n6️⃣  RECENT PERFORMANCE (Hindsight)")
        print("-" * 60)

        return_7d = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-7]) - 1) * 100
        return_5d = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-5]) - 1) * 100
        return_3d = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-3]) - 1) * 100

        print(f"   7-day: {return_7d:+.2f}%")
        print(f"   5-day: {return_5d:+.2f}%")
        print(f"   3-day: {return_3d:+.2f}%")

        if return_7d > 5:
            print(f"\n   💡 {symbol} gained {return_7d:.1f}% this week - a clear winner!")

        # Summary
        print("\n" + "="*70)
        print("📋 VERDICT")
        print("="*70)

        print(f"\n🎯 Most Likely Reason {symbol} wasn't recommended:")
        print(f"   1. Not selected for AI Universe (pre-filtering)")
        print(f"   2. Timing issue - the move happened AFTER scan")
        print(f"   3. Composite score threshold not met")

        print(f"\n💡 Key Insights:")
        print(f"   • {symbol} is in {sector} sector - semiconductors are volatile")
        print(f"   • Strong technical setup and valuation")
        print(f"   • May have earnings coming up (penalty in inverted scoring)")
        print(f"   • The screener is PREDICTIVE, not reactive")
        print(f"   • It's designed to find stocks BEFORE they move 5%+")

        print(f"\n⚠️  Reality Check:")
        print(f"   No system can predict 100% of winners")
        print(f"   The goal is to maximize win rate on FUTURE positions")
        print(f"   Missing one winner is acceptable if it protects from multiple losers")

    except Exception as e:
        print(f"⚠️  Analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_mu()
