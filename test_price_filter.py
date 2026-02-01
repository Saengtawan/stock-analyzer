#!/usr/bin/env python3
"""
Test script to verify price filter functionality in premarket scanner
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from src.api.yahoo_finance_client import YahooFinanceClient
from src.screeners.premarket_scanner import PremarketScanner

def test_price_filter():
    """Test that price filter correctly filters stocks below minimum price"""

    print("=" * 80)
    print("Testing Price Filter in Pre-market Scanner")
    print("=" * 80)

    # Initialize clients
    yahoo_client = YahooFinanceClient()
    scanner = PremarketScanner(yahoo_client)

    # Test 1: Filter with $5 minimum (default - should filter penny stocks)
    print("\n📊 Test 1: Scanning with $5 minimum price (default)")
    print("-" * 80)
    result = scanner.scan_premarket_opportunities(
        min_gap_pct=2.0,
        min_price=5.0,
        market_caps=['large', 'mid', 'small'],
        max_stocks=10
    )

    opportunities = result['opportunities']
    print(f"✅ Found {len(opportunities)} opportunities with price >= $5")

    if opportunities:
        print("\nTop 5 stocks:")
        for i, opp in enumerate(opportunities[:5], 1):
            symbol = opp['symbol']
            price = opp['current_price']
            gap = opp['gap_percent']
            confidence = opp['trade_confidence']
            print(f"  {i}. {symbol:6s} - ${price:6.2f} | Gap: {gap:5.2f}% | Confidence: {confidence:3d}")

            # Verify price >= $5
            if price < 5.0:
                print(f"    ⚠️  WARNING: Stock below $5 minimum! (${price:.2f})")

    # Test 2: Filter with $10 minimum (more conservative)
    print("\n\n📊 Test 2: Scanning with $10 minimum price (conservative)")
    print("-" * 80)
    result = scanner.scan_premarket_opportunities(
        min_gap_pct=2.0,
        min_price=10.0,
        market_caps=['large', 'mid', 'small'],
        max_stocks=10
    )

    opportunities = result['opportunities']
    print(f"✅ Found {len(opportunities)} opportunities with price >= $10")

    if opportunities:
        print("\nTop 5 stocks:")
        for i, opp in enumerate(opportunities[:5], 1):
            symbol = opp['symbol']
            price = opp['current_price']
            gap = opp['gap_percent']
            confidence = opp['trade_confidence']
            print(f"  {i}. {symbol:6s} - ${price:6.2f} | Gap: {gap:5.2f}% | Confidence: {confidence:3d}")

            # Verify price >= $10
            if price < 10.0:
                print(f"    ⚠️  WARNING: Stock below $10 minimum! (${price:.2f})")

    # Test 3: Filter with $20 minimum (very conservative)
    print("\n\n📊 Test 3: Scanning with $20 minimum price (very conservative)")
    print("-" * 80)
    result = scanner.scan_premarket_opportunities(
        min_gap_pct=2.0,
        min_price=20.0,
        market_caps=['large', 'mid'],
        max_stocks=10
    )

    opportunities = result['opportunities']
    print(f"✅ Found {len(opportunities)} opportunities with price >= $20")

    if opportunities:
        print("\nTop 5 stocks:")
        for i, opp in enumerate(opportunities[:5], 1):
            symbol = opp['symbol']
            price = opp['current_price']
            gap = opp['gap_percent']
            confidence = opp['trade_confidence']
            print(f"  {i}. {symbol:6s} - ${price:6.2f} | Gap: {gap:5.2f}% | Confidence: {confidence:3d}")

            # Verify price >= $20
            if price < 20.0:
                print(f"    ⚠️  WARNING: Stock below $20 minimum! (${price:.2f})")

    # Verify soft penalty for low-priced stocks
    print("\n\n📊 Test 4: Verify soft penalty for stocks in $5-15 range")
    print("-" * 80)
    print("Stocks in $5-10 range should have -10 confidence penalty")
    print("Stocks in $10-15 range should have -5 confidence penalty")
    print("Stocks $15+ should have no penalty")

    result = scanner.scan_premarket_opportunities(
        min_gap_pct=2.0,
        min_price=5.0,
        market_caps=['large', 'mid', 'small'],
        max_stocks=20
    )

    opportunities = result['opportunities']

    # Group by price ranges
    range_5_10 = [o for o in opportunities if 5 <= o['current_price'] < 10]
    range_10_15 = [o for o in opportunities if 10 <= o['current_price'] < 15]
    range_15_plus = [o for o in opportunities if o['current_price'] >= 15]

    print(f"\n$5-10 range: {len(range_5_10)} stocks (should have -10 confidence)")
    if range_5_10:
        for opp in range_5_10[:3]:
            print(f"  {opp['symbol']:6s} - ${opp['current_price']:6.2f} | Confidence: {opp['trade_confidence']:3d}")

    print(f"\n$10-15 range: {len(range_10_15)} stocks (should have -5 confidence)")
    if range_10_15:
        for opp in range_10_15[:3]:
            print(f"  {opp['symbol']:6s} - ${opp['current_price']:6.2f} | Confidence: {opp['trade_confidence']:3d}")

    print(f"\n$15+ range: {len(range_15_plus)} stocks (no penalty)")
    if range_15_plus:
        for opp in range_15_plus[:3]:
            print(f"  {opp['symbol']:6s} - ${opp['current_price']:6.2f} | Confidence: {opp['trade_confidence']:3d}")

    print("\n" + "=" * 80)
    print("✅ Price filter testing complete!")
    print("=" * 80)

if __name__ == '__main__':
    test_price_filter()
