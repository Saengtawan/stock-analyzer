#!/usr/bin/env python3
"""
Analyze why the screener found 0 stocks
- Check market regime (BULL/BEAR filter)
- Find stocks that gained 5%+ this week
- Analyze why they didn't pass the filters
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger

# Suppress warnings
import warnings
warnings.filterwarnings('ignore')

def check_market_regime():
    """Check if market regime is blocking the scan"""
    print("\n" + "="*70)
    print("🧠 MARKET REGIME CHECK")
    print("="*70)

    try:
        from src.market_regime_detector import MarketRegimeDetector
        detector = MarketRegimeDetector()
        regime_info = detector.get_current_regime()

        print(f"\n📊 Current Market Regime:")
        print(f"   Regime: {regime_info['regime']}")
        print(f"   Strength: {regime_info['strength']}/100")
        print(f"   Should Trade: {'✅ YES' if regime_info['should_trade'] else '❌ NO'}")
        print(f"   Position Size: {regime_info['position_size_multiplier']*100:.0f}%")

        if not regime_info['should_trade']:
            print(f"\n⚠️  REASON FOR 0 STOCKS: Regime detector BLOCKED the scan!")
            print(f"   The system won't trade in {regime_info['regime']} market")
            print(f"   This is a protective feature to avoid losses")

        # Show SPY details
        details = regime_info.get('details', {})
        print(f"\n📈 SPY Technical Details:")
        print(f"   SPY vs MA20: {details.get('dist_ma20', 0):+.2f}%")
        print(f"   SPY vs MA50: {details.get('dist_ma50', 0):+.2f}%")
        print(f"   SPY Momentum (5d): {details.get('momentum_5d', 0):+.2f}%")
        print(f"   SPY Momentum (10d): {details.get('momentum_10d', 0):+.2f}%")

        return regime_info

    except Exception as e:
        print(f"⚠️  Could not check regime: {e}")
        return None

def find_this_week_winners():
    """Find stocks that gained 5%+ this week"""
    print("\n" + "="*70)
    print("🔍 STOCKS THAT GAINED 5%+ THIS WEEK")
    print("="*70)

    # Popular stocks to check
    symbols = [
        # Tech giants
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        # Growth stocks
        'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS',
        # AI/Semiconductors
        'AMD', 'AVGO', 'MU', 'AMAT', 'LRCX',
        # Consumer
        'NFLX', 'DIS', 'SBUX', 'NKE', 'DASH', 'UBER',
        # Finance
        'JPM', 'BAC', 'GS', 'MS', 'V', 'MA',
        # Healthcare
        'UNH', 'JNJ', 'PFE', 'ABBV', 'LLY',
        # Energy
        'XOM', 'CVX', 'COP',
        # Recent movers
        'COIN', 'HOOD', 'MSTR', 'RIOT'
    ]

    winners = []

    print("\nChecking 50+ popular stocks for 7-day performance...\n")

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1mo')

            if hist.empty or len(hist) < 7:
                continue

            # 7-day return
            price_7d_ago = hist['Close'].iloc[-7]
            current_price = hist['Close'].iloc[-1]
            return_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100

            # Also check 5-day and 3-day
            return_5d = ((current_price - hist['Close'].iloc[-5]) / hist['Close'].iloc[-5]) * 100 if len(hist) >= 5 else 0
            return_3d = ((current_price - hist['Close'].iloc[-3]) / hist['Close'].iloc[-3]) * 100 if len(hist) >= 3 else 0

            if return_7d >= 5.0:
                winners.append({
                    'symbol': symbol,
                    'return_7d': return_7d,
                    'return_5d': return_5d,
                    'return_3d': return_3d,
                    'current_price': current_price
                })

        except Exception as e:
            continue

    # Sort by 7-day return
    winners.sort(key=lambda x: x['return_7d'], reverse=True)

    print(f"Found {len(winners)} stocks with 5%+ gain in 7 days:\n")
    print(f"{'Rank':<6} {'Symbol':<8} {'7-Day':<10} {'5-Day':<10} {'3-Day':<10} {'Price':<10}")
    print("-" * 70)

    for i, w in enumerate(winners, 1):
        print(f"{i:<6} {w['symbol']:<8} {w['return_7d']:>7.2f}%  {w['return_5d']:>7.2f}%  {w['return_3d']:>7.2f}%  ${w['current_price']:>7.2f}")

    return winners

def analyze_why_not_picked(winners, regime_info):
    """Analyze why these winners weren't picked by the screener"""
    print("\n" + "="*70)
    print("🔬 WHY THESE STOCKS WEREN'T RECOMMENDED")
    print("="*70)

    if not regime_info or not regime_info.get('should_trade'):
        print("\n❌ PRIMARY REASON: Market regime filter BLOCKED all stocks!")
        print("   Even if stocks look good, the system won't recommend them")
        print("   in BEAR/WEAK markets to protect your capital.")
        return

    # If regime is OK, analyze each stock
    print("\nAnalyzing top 5 winners to understand filter failures...\n")

    from src.main import StockAnalyzer
    analyzer = StockAnalyzer()

    for i, winner in enumerate(winners[:5], 1):
        symbol = winner['symbol']
        print(f"\n{i}. {symbol} (+{winner['return_7d']:.1f}% in 7 days)")
        print("-" * 60)

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            hist = ticker.history(period='3mo')

            if hist.empty or len(hist) < 60:
                print(f"   ⚠️  Insufficient data")
                continue

            # Check all filters
            filters_failed = []

            # 1. Price filter
            price = winner['current_price']
            if price < 5:
                filters_failed.append(f"❌ Price ${price:.2f} < $5 minimum")

            # 2. Beta filter (0.8 - 2.0)
            beta = info.get('beta', 1.0)
            if beta and (beta < 0.8 or beta > 2.0):
                filters_failed.append(f"❌ Beta {beta:.2f} outside range [0.8-2.0]")

            # 3. Volatility filter (>25%)
            returns = hist['Close'].pct_change().dropna()
            volatility = returns.std() * (252 ** 0.5) * 100
            if volatility < 25.0:
                filters_failed.append(f"❌ Volatility {volatility:.1f}% < 25% minimum")

            # 4. Relative Strength filter (>0%)
            stock_return_30d = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-30]) - 1) * 100
            try:
                spy = yf.Ticker('SPY')
                spy_hist = spy.history(period='1mo')
                spy_return_30d = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-20]) - 1) * 100
                relative_strength = stock_return_30d - spy_return_30d

                if relative_strength < 0.0:
                    filters_failed.append(f"❌ Relative Strength {relative_strength:.1f}% < 0% (underperforming market)")
            except:
                relative_strength = 0

            # 5. Valuation filter
            pe_ratio = info.get('trailingPE', None)
            forward_pe = info.get('forwardPE', None)

            valuation_issue = False
            if forward_pe and forward_pe > 80:
                filters_failed.append(f"❌ Forward P/E {forward_pe:.1f} > 80 (too expensive)")
                valuation_issue = True
            elif pe_ratio and pe_ratio > 100:
                filters_failed.append(f"❌ P/E {pe_ratio:.1f} > 100 (extremely overvalued)")
                valuation_issue = True

            # 6. Earnings catalyst (INVERTED - earnings soon = bad)
            earnings_date = info.get('earningsDate')
            if earnings_date and isinstance(earnings_date, list) and len(earnings_date) > 0:
                next_earnings = pd.Timestamp(earnings_date[0])
                days_to_earnings = (next_earnings - pd.Timestamp.now()).days

                if 0 < days_to_earnings <= 10:
                    filters_failed.append(f"⚠️  Earnings in {days_to_earnings} days (sell-the-news risk)")
                elif 10 < days_to_earnings <= 20:
                    filters_failed.append(f"⚠️  Earnings in {days_to_earnings} days (moderate risk)")

            # Show results
            if filters_failed:
                print(f"\n   Failed {len(filters_failed)} filter(s):")
                for fail in filters_failed:
                    print(f"   {fail}")
            else:
                print(f"   ✅ Passed all basic filters!")
                print(f"   Note: May have failed AI probability or composite score threshold")

            # Show key metrics
            print(f"\n   Key Metrics:")
            print(f"   • Beta: {beta:.2f} (target: 0.8-2.0)")
            print(f"   • Volatility: {volatility:.1f}% (target: >25%)")
            print(f"   • Relative Strength (30d): {relative_strength:.1f}% (target: >0%)")
            if pe_ratio:
                print(f"   • P/E Ratio: {pe_ratio:.1f}")
            if forward_pe:
                print(f"   • Forward P/E: {forward_pe:.1f}")

        except Exception as e:
            print(f"   ⚠️  Analysis failed: {e}")

def main():
    print("\n" + "="*70)
    print("🔍 DIAGNOSTIC: Why did the screener find 0 stocks?")
    print("="*70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Step 1: Check market regime
    regime_info = check_market_regime()

    # Step 2: Find this week's winners
    winners = find_this_week_winners()

    # Step 3: Analyze why they weren't picked
    if winners:
        analyze_why_not_picked(winners, regime_info)
    else:
        print("\n⚠️  No stocks gained 5%+ this week from the symbols checked")

    # Summary
    print("\n" + "="*70)
    print("📋 SUMMARY")
    print("="*70)

    if regime_info and not regime_info.get('should_trade'):
        print("\n🎯 MAIN REASON: Market Regime Filter")
        print("   The screener is designed to only trade in BULL markets")
        print(f"   Current regime: {regime_info['regime']}")
        print("   This is a PROTECTIVE feature to avoid losses in weak markets")
        print("\n💡 RECOMMENDATION:")
        print("   Wait for market regime to improve before trading")
        print("   The system will automatically resume scanning when conditions are better")
    elif not winners:
        print("\n🎯 REASON: No strong gainers this week")
        print("   The market may be consolidating or rotating sectors")
    else:
        print(f"\n🎯 FOUND {len(winners)} GAINERS but they failed screening filters")
        print("\nCommon reasons:")
        print("   • Low volatility (<25%) - stock too stable for 5% move")
        print("   • Negative relative strength - underperforming market")
        print("   • High valuation (P/E > 100) - too expensive")
        print("   • Beta outside 0.8-2.0 range")
        print("   • Upcoming earnings (sell-the-news risk)")
        print("\n💡 The filters are designed to PROTECT you from false signals")
        print("   Even gainers can fail if they don't meet quality criteria")

if __name__ == "__main__":
    main()
