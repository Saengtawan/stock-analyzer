"""
Test ONLY momentum gates for quick market assessment
"""
import sys
import os
import yfinance as yf
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from screeners.growth_catalyst_screener import GrowthCatalystScreener

def test_momentum_gates():
    """Test momentum gates only - no AI, no full analysis"""
    print("=" * 80)
    print(f"🧪 Momentum Gates Test (v4.0)")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 80)

    # Test stocks
    test_stocks = ['MU', 'NVDA', 'AAPL', 'GOOGL', 'META', 'TSLA', 'AMD', 'MSFT',
                   'LRCX', 'ARWR', 'CRM', 'NFLX']

    print(f"\n🔍 Testing {len(test_stocks)} stocks")
    print("\nMomentum Gates (v4.0):")
    print("   • RSI: 35-70")
    print("   • MA50: >-5%")
    print("   • Mom30d: >5%")
    print()

    passed = []
    failed = []

    for symbol in test_stocks:
        try:
            # Download data
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='3mo')

            if len(data) < 50:
                print(f"❌ {symbol}: Insufficient data")
                failed.append({'symbol': symbol, 'reason': 'No data'})
                continue

            # Calculate momentum metrics manually
            price = data['Close'].iloc[-1]
            ma20 = data['Close'].rolling(20).mean().iloc[-1]
            ma50 = data['Close'].rolling(50).mean().iloc[-1]

            # RSI calculation
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]

            # Price above MA
            price_above_ma20 = ((price - ma20) / ma20) * 100
            price_above_ma50 = ((price - ma50) / ma50) * 100

            # Momentum
            price_30d_ago = data['Close'].iloc[-30]
            momentum_30d = ((price - price_30d_ago) / price_30d_ago) * 100

            # Check gates
            rsi_pass = 35 <= current_rsi <= 70
            ma50_pass = price_above_ma50 > -5
            mom30_pass = momentum_30d > 5

            all_pass = rsi_pass and ma50_pass and mom30_pass

            # Print result
            status = "✅" if all_pass else "❌"
            print(f"{status} {symbol:6s} | RSI: {current_rsi:5.1f} {'✓' if rsi_pass else '✗'} | "
                  f"MA50: {price_above_ma50:+6.1f}% {'✓' if ma50_pass else '✗'} | "
                  f"Mom30d: {momentum_30d:+6.1f}% {'✓' if mom30_pass else '✗'}")

            if all_pass:
                passed.append({
                    'symbol': symbol,
                    'rsi': current_rsi,
                    'ma50': price_above_ma50,
                    'mom30d': momentum_30d,
                    'price': price
                })
            else:
                reasons = []
                if not rsi_pass:
                    if current_rsi < 35:
                        reasons.append(f"RSI too low ({current_rsi:.1f})")
                    else:
                        reasons.append(f"RSI too high ({current_rsi:.1f})")
                if not ma50_pass:
                    reasons.append(f"Below MA50 ({price_above_ma50:+.1f}%)")
                if not mom30_pass:
                    reasons.append(f"Weak momentum ({momentum_30d:+.1f}%)")

                failed.append({
                    'symbol': symbol,
                    'reason': ', '.join(reasons)
                })

        except Exception as e:
            print(f"❌ {symbol}: Error - {e}")
            failed.append({'symbol': symbol, 'reason': str(e)})

    # Summary
    print(f"\n{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Passed: {len(passed)}/{len(test_stocks)} stocks ({len(passed)*100//len(test_stocks)}%)")

    if passed:
        print("\nStocks that PASSED all gates:")
        for stock in passed:
            print(f"   • {stock['symbol']:6s} - ${stock['price']:.2f} | "
                  f"RSI: {stock['rsi']:.1f} | MA50: {stock['ma50']:+.1f}% | Mom30d: {stock['mom30d']:+.1f}%")

    print(f"\n❌ Failed: {len(failed)}/{len(test_stocks)} stocks")
    if failed:
        print("\nWhy they failed:")
        for stock in failed:
            print(f"   • {stock['symbol']:6s}: {stock['reason']}")

    # Market assessment
    print(f"\n{'='*80}")
    print(f"💡 MARKET ASSESSMENT")
    print(f"{'='*80}")

    pass_rate = (len(passed) / len(test_stocks)) * 100

    if pass_rate >= 50:
        print(f"✅ GOOD market conditions ({pass_rate:.0f}% pass rate)")
        print(f"   {len(passed)} stocks have strong momentum")
        print("   → Good time to find opportunities!")
    elif pass_rate >= 25:
        print(f"⚠️ MIXED market conditions ({pass_rate:.0f}% pass rate)")
        print(f"   Only {len(passed)} stocks have strong momentum")
        print("   → Be selective with trades")
    else:
        print(f"❌ POOR market conditions ({pass_rate:.0f}% pass rate)")
        print(f"   Only {len(passed)} stocks have strong momentum")
        print("   → Wait for better conditions!")

    # What to do
    print(f"\n{'='*80}")
    print(f"🎯 RECOMMENDATION")
    print(f"{'='*80}")

    if len(passed) >= 3:
        print(f"✅ Trade these {len(passed)} stocks that passed momentum gates!")
        print("\nThey have:")
        print("   • Healthy RSI (35-70) - not oversold/overbought")
        print("   • Above MA50 or close to it")
        print("   • Positive 30-day momentum")
    elif len(passed) > 0:
        print(f"⚠️ Only {len(passed)} stock(s) passed - be cautious")
        print("   Consider waiting for better market conditions")
    else:
        print("❌ NO STOCKS PASSED - DO NOT TRADE")
        print("\nMarket is weak right now:")
        print("   • Stocks are oversold/overbought")
        print("   • Below moving averages")
        print("   • No positive momentum")
        print("\n⏳ Wait 2-3 days and check again")

    return passed, failed

if __name__ == "__main__":
    test_momentum_gates()
