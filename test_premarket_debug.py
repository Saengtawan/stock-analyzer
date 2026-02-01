#!/usr/bin/env python3
"""
Test Pre-market Scanner - Debug why no opportunities found
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
from screeners.premarket_scanner import PremarketScanner
from datetime import datetime
import pytz

def test_premarket_data():
    """Test if we can get pre-market data from Yahoo Finance"""

    print("=" * 80)
    print("PRE-MARKET SCANNER DEBUG TEST")
    print("=" * 80)

    # Check current time
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    print(f"\n1. Current Time (US/Eastern): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"   Day of week: {now.strftime('%A')}")

    current_time = now.time()
    current_day = now.weekday()

    # Check market state
    if current_day >= 5:
        print(f"   ❌ Market Status: WEEKEND (Day {current_day})")
    elif current_time.hour < 4:
        print(f"   ❌ Market Status: CLOSED (before 4:00 AM)")
    elif 4 <= current_time.hour < 9 or (current_time.hour == 9 and current_time.minute < 30):
        print(f"   ✅ Market Status: PRE-MARKET HOURS")
    elif 9 <= current_time.hour < 16 or (current_time.hour == 9 and current_time.minute >= 30):
        print(f"   ⚠️  Market Status: REGULAR HOURS (pre-market data should still be available)")
    else:
        print(f"   ❌ Market Status: AFTER HOURS / CLOSED")

    # Initialize client
    client = YahooFinanceClient()

    # Test with known volatile stocks
    test_symbols = ['TSLA', 'NVDA', 'AAPL', 'MSFT', 'AMD']

    print(f"\n2. Testing Pre-market Data Fetch for {len(test_symbols)} stocks:")
    print("-" * 80)

    for symbol in test_symbols:
        try:
            print(f"\n   Testing {symbol}...")
            pm_data = client.get_premarket_data(symbol, interval="5m")

            if pm_data.get('has_premarket_data'):
                print(f"   ✅ {symbol}: Pre-market data found!")
                print(f"      - Previous Close: ${pm_data['previous_close']:.2f}")
                print(f"      - Current PM Price: ${pm_data['current_premarket_price']:.2f}")
                print(f"      - Gap: {pm_data['gap_percent']:.2f}% ({pm_data['gap_direction']})")
                print(f"      - PM Volume: {pm_data['premarket_volume']:,}")
                print(f"      - PM High/Low: ${pm_data['premarket_high']:.2f} / ${pm_data['premarket_low']:.2f}")

                # Check if meets criteria
                if pm_data['gap_percent'] >= 5.0 and pm_data['gap_direction'] == 'up':
                    print(f"      🎯 MEETS GAP CRITERIA (≥5%)")
                else:
                    print(f"      ⚠️  Does not meet gap criteria (need ≥5% up)")

            else:
                error = pm_data.get('error', 'Unknown error')
                print(f"   ❌ {symbol}: No pre-market data - {error}")

        except Exception as e:
            print(f"   ❌ {symbol}: Error - {e}")

    # Test full scanner
    print("\n" + "=" * 80)
    print("3. Testing Full Pre-market Scanner")
    print("=" * 80)

    try:
        scanner = PremarketScanner(client)

        print("\n   Running scan with relaxed criteria for testing:")
        print("   - Min Gap: 3% (relaxed from 5%)")
        print("   - Min Volume Ratio: 2x (relaxed from 3x)")
        print("   - Market Caps: Large + Mid")
        print("   - Tech Priority: Yes")
        print("   - Max Stocks: 10")

        scan_result = scanner.scan_premarket_opportunities(
            min_gap_pct=3.0,  # Relaxed
            min_volume_ratio=2.0,  # Relaxed
            market_caps=['large', 'mid'],
            prioritize_tech=True,
            max_stocks=10
        )

        opportunities = scan_result['opportunities']
        demo_mode = scan_result['demo_mode']

        print(f"\n   ✅ Scan completed!")
        print(f"   Found {len(opportunities)} opportunities")
        print(f"   Demo Mode: {demo_mode}")

        if opportunities:
            print("\n   Top Opportunities:")
            print("   " + "-" * 76)
            for i, opp in enumerate(opportunities[:5], 1):
                print(f"   {i}. {opp['symbol']:6s} - Gap: {opp['gap_percent']:5.2f}% | "
                      f"Volume: {opp['volume_ratio']:4.1f}x | "
                      f"Score: {opp['gap_score']:.1f}/10 | "
                      f"Rec: {opp['recommendation']}")
        else:
            print("\n   ⚠️  No opportunities found even with relaxed criteria")
            print("\n   Possible reasons:")
            print("   1. Not in pre-market hours (4:00-9:30 AM ET)")
            print("   2. No stocks are gapping up today")
            print("   3. Yahoo Finance not returning pre-market data")
            print("   4. AI universe generation might have failed")

    except Exception as e:
        print(f"\n   ❌ Scanner Error: {e}")
        import traceback
        print("\n   Full traceback:")
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("DEBUG TEST COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    test_premarket_data()
