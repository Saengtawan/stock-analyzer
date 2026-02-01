#!/usr/bin/env python3
"""
Test Catalyst Improvements - Direct Testing
Test if new momentum and volume surge detection works
"""

import yfinance as yf
import pandas as pd

def test_stock_catalysts(symbol):
    """Test catalyst detection for a single stock"""
    print(f"\n{'='*70}")
    print(f"Testing Catalyst Detection: {symbol}")
    print(f"{'='*70}")

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='1mo')
        info = ticker.info

        if hist.empty:
            print(f"❌ No data")
            return

        current_price = hist['Close'].iloc[-1]

        # Ground truth: 30-day return
        if len(hist) >= 21:
            price_30d_ago = hist['Close'].iloc[0]
            total_return = ((current_price - price_30d_ago) / price_30d_ago) * 100
            max_return = ((hist['High'].max() - price_30d_ago) / price_30d_ago) * 100

            print(f"\n📊 Actual 30-Day Performance:")
            print(f"   Start: ${price_30d_ago:.2f}")
            print(f"   Current: ${current_price:.2f}")
            print(f"   Return: {total_return:+.1f}%")
            print(f"   Max Return: {max_return:+.1f}%")
            print(f"   {'✅ PASSED 15% target!' if max_return >= 15 else '❌ Below 15%'}")

        # Test NEW Catalyst 1: Recent Price Momentum (2-week)
        print(f"\n🚀 NEW CATALYST: Recent Price Momentum")
        if len(hist) >= 10:
            price_10d_ago = hist['Close'].iloc[-10]
            momentum_return = ((current_price - price_10d_ago) / price_10d_ago) * 100

            if momentum_return > 15:
                score = 15
                level = "HIGH"
            elif momentum_return > 8:
                score = 10
                level = "MEDIUM"
            elif momentum_return > 3:
                score = 5
                level = "LOW"
            else:
                score = 0
                level = "NONE"

            print(f"   2-Week Return: {momentum_return:+.1f}%")
            print(f"   Catalyst Score: {score}/15 points")
            print(f"   Impact Level: {level}")

        # Test NEW Catalyst 2: Volume Surge
        print(f"\n📊 NEW CATALYST: Volume Surge")
        recent_volume = info.get('volume', 0)
        avg_volume = info.get('averageVolume', 0)

        if recent_volume > 0 and avg_volume > 0:
            volume_ratio = recent_volume / avg_volume

            if volume_ratio > 2.0:
                score = 10
                level = "HIGH"
            elif volume_ratio > 1.5:
                score = 5
                level = "MEDIUM"
            else:
                score = 0
                level = "NONE"

            print(f"   Recent Volume: {recent_volume:,}")
            print(f"   Avg Volume: {avg_volume:,}")
            print(f"   Volume Ratio: {volume_ratio:.2f}x")
            print(f"   Catalyst Score: {score}/10 points")
            print(f"   Impact Level: {level}")

        # Test NEW Technical: Short-Term Momentum (5-10 days)
        print(f"\n⚡ NEW TECHNICAL: Short-Term Momentum")
        if len(hist) >= 10:
            price_10d_ago = hist['Close'].iloc[-10]
            price_5d_ago = hist['Close'].iloc[-5]
            return_10d = ((current_price - price_10d_ago) / price_10d_ago) * 100
            return_5d = ((current_price - price_5d_ago) / price_5d_ago) * 100

            if return_10d > 10 and return_5d > 5:
                score = 15
                momentum_type = "ACCELERATING"
            elif return_10d > 5:
                score = 10
                momentum_type = "STRONG"
            elif return_5d > 3:
                score = 5
                momentum_type = "BUILDING"
            else:
                score = 0
                momentum_type = "WEAK"

            print(f"   10-Day Return: {return_10d:+.1f}%")
            print(f"   5-Day Return: {return_5d:+.1f}%")
            print(f"   Technical Score: {score}/15 points")
            print(f"   Momentum Type: {momentum_type}")

        # Traditional Catalysts
        print(f"\n📰 TRADITIONAL CATALYSTS:")
        print(f"   Recommendation: {info.get('recommendationKey', 'N/A')}")
        print(f"   Target Price: ${info.get('targetMeanPrice', 0):.2f} (Current: ${current_price:.2f})")
        print(f"   # Analysts: {info.get('numberOfAnalystOpinions', 0)}")
        print(f"   52W Change: {info.get('52WeekChange', 0) * 100:.1f}%")

    except Exception as e:
        print(f"❌ Error: {e}")


print("="*80)
print("🧪 TESTING IMPROVED CATALYST DETECTION")
print("="*80)
print("\nTesting on TSLA and LCID (stocks that performed well but were missed)")

# Test both stocks
for symbol in ['TSLA', 'LCID']:
    test_stock_catalysts(symbol)

print(f"\n{'='*80}")
print("✅ TEST COMPLETE")
print(f"{'='*80}\n")

print("📝 SUMMARY:")
print("   - NEW catalysts should detect recent momentum")
print("   - Volume surge should catch unusual buying")
print("   - Short-term momentum should catch accelerating stocks")
print("   - These improvements should find TSLA (+17%) and LCID (+12.5% peak)")
