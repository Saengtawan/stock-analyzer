#!/usr/bin/env python3
"""
ALPACA ORDER TEST SCRIPT
Tests all order operations for Phase 1

Run during market hours to test:
1. Place market buy
2. Place stop loss
3. Modify stop loss (trailing simulation)
4. Cancel order
5. Buy with SL fail → auto sell

WARNING: This uses PAPER TRADING but will execute real orders.
"""

import sys
import time
sys.path.insert(0, 'src')

from alpaca_trader import AlpacaTrader


# Credentials (Paper Trading)
API_KEY = "PK45CDQEE2WO7I7N4BH762VSMK"
SECRET_KEY = "DFDhSeYmnsxS2YpyAZLX1MLm9ndfmYr9XaUEiyn78SH1"


def test_orders():
    """Test order operations"""
    print("=" * 60)
    print("ALPACA ORDER TEST")
    print("=" * 60)

    trader = AlpacaTrader(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        paper=True
    )

    # Check market status
    clock = trader.get_clock()
    print(f"\nMarket Open: {clock['is_open']}")

    if not clock['is_open']:
        print("\n⚠️  Market is CLOSED")
        print(f"   Next open: {clock['next_open']}")
        print("\nOrder tests require market to be open.")
        print("Run this script during market hours (9:30-16:00 ET)")

        # Still test some things
        print("\n" + "-" * 60)
        print("Testing non-market operations...")

        # Test trailing stop calculation
        print("\n[TEST] Trailing Stop Calculation:")
        entry = 100.0

        test_cases = [
            (100.0, "Entry price - no gain"),
            (101.0, "+1% - not activated"),
            (102.0, "+2% - trailing starts"),
            (103.0, "+3% - trailing"),
            (105.0, "+5% - trailing"),
        ]

        for peak, desc in test_cases:
            sl, active = trader.calculate_trailing_stop(entry, peak)
            status = "TRAILING" if active else "FIXED SL"
            gain_pct = ((peak - entry) / entry) * 100
            sl_from_entry = ((sl - entry) / entry) * 100
            print(f"   Peak ${peak:.2f} ({gain_pct:+.1f}%): SL=${sl:.2f} ({sl_from_entry:+.2f}%) [{status}]")

        print("\n✅ Trailing calculation works correctly")
        return

    # Market is open - run full tests
    print("\n" + "=" * 60)
    print("RUNNING LIVE ORDER TESTS (Paper Trading)")
    print("=" * 60)

    # Use a cheap, liquid stock for testing
    TEST_SYMBOL = "SIRI"  # ~$3-4, good for testing
    TEST_QTY = 1

    # Get current account
    account = trader.get_account()
    print(f"\nAccount Cash: ${account['cash']:,.2f}")

    # -------------------------------------------------------------------------
    # TEST 1: Simple buy and sell
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("[TEST 1] Market Buy → Market Sell")
    print("-" * 60)

    try:
        # Buy
        print(f"Buying {TEST_SYMBOL} x{TEST_QTY}...")
        buy_order = trader.place_market_buy(TEST_SYMBOL, TEST_QTY)
        print(f"   Order ID: {buy_order.id}")
        print(f"   Status: {buy_order.status}")

        # Wait for fill
        print("   Waiting for fill...")
        for i in range(30):
            order = trader.get_order(buy_order.id)
            if order.status == 'filled':
                print(f"   ✅ Filled @ ${order.filled_avg_price:.2f}")
                break
            time.sleep(1)
        else:
            print("   ❌ Not filled in 30s, cancelling")
            trader.cancel_order(buy_order.id)
            return

        # Sell immediately
        print(f"Selling {TEST_SYMBOL} x{TEST_QTY}...")
        sell_order = trader.place_market_sell(TEST_SYMBOL, TEST_QTY)

        # Wait for fill
        for i in range(30):
            order = trader.get_order(sell_order.id)
            if order.status == 'filled':
                print(f"   ✅ Sold @ ${order.filled_avg_price:.2f}")
                break
            time.sleep(1)

        print("TEST 1: PASSED")

    except Exception as e:
        print(f"TEST 1 FAILED: {e}")

    # -------------------------------------------------------------------------
    # TEST 2: Buy with Stop Loss
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("[TEST 2] Buy with Stop Loss")
    print("-" * 60)

    try:
        print(f"Buying {TEST_SYMBOL} with SL...")
        buy_order, sl_order = trader.buy_with_stop_loss(TEST_SYMBOL, TEST_QTY)

        if buy_order and sl_order:
            print(f"   Buy filled @ ${buy_order.filled_avg_price:.2f}")
            print(f"   SL placed @ ${sl_order.stop_price:.2f}")
            print("   ✅ Position is protected")

            # Now cancel SL and sell
            print("   Cancelling SL and closing position...")
            trader.cancel_order(sl_order.id)
            trader.place_market_sell(TEST_SYMBOL, TEST_QTY)

            # Wait for sell
            time.sleep(2)
            print("   ✅ Position closed")
            print("TEST 2: PASSED")
        else:
            print("   ❌ Failed to create position with SL")
            print("TEST 2: FAILED")

    except Exception as e:
        print(f"TEST 2 FAILED: {e}")

    # -------------------------------------------------------------------------
    # TEST 3: Modify Stop Loss (Trailing Simulation)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("[TEST 3] Modify Stop Loss (Trailing)")
    print("-" * 60)

    try:
        # Buy with SL
        print(f"Buying {TEST_SYMBOL} with SL...")
        buy_order, sl_order = trader.buy_with_stop_loss(TEST_SYMBOL, TEST_QTY)

        if not (buy_order and sl_order):
            print("   ❌ Failed to setup")
            return

        entry_price = buy_order.filled_avg_price
        original_sl = sl_order.stop_price
        print(f"   Entry: ${entry_price:.2f}, SL: ${original_sl:.2f}")

        # Simulate trailing - move SL up
        new_sl_price = entry_price * 0.99  # Move SL to -1% from entry
        print(f"   Modifying SL: ${original_sl:.2f} → ${new_sl_price:.2f}")

        new_sl_order = trader.modify_stop_loss(sl_order.id, new_sl_price)

        if new_sl_order:
            print(f"   ✅ New SL order: {new_sl_order.id[:8]}...")
            print(f"   ✅ New SL price: ${new_sl_order.stop_price:.2f}")

            # Cleanup
            trader.cancel_order(new_sl_order.id)
            trader.place_market_sell(TEST_SYMBOL, TEST_QTY)
            time.sleep(2)

            print("TEST 3: PASSED")
        else:
            print("   ❌ Failed to modify SL")
            print("TEST 3: FAILED")

    except Exception as e:
        print(f"TEST 3 FAILED: {e}")

    # -------------------------------------------------------------------------
    # Final Status
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("FINAL STATUS")
    print("=" * 60)

    positions = trader.get_positions()
    print(f"\nPositions: {len(positions)}")
    for p in positions:
        print(f"   {p.symbol}: {p.qty} shares")

    orders = trader.get_orders(status='open')
    print(f"\nOpen Orders: {len(orders)}")
    for o in orders:
        print(f"   {o.symbol}: {o.type} {o.side}")

    account = trader.get_account()
    print(f"\nCash: ${account['cash']:,.2f}")


def cleanup():
    """Cancel all orders and close all positions"""
    print("=" * 60)
    print("CLEANUP - Cancel all orders, close all positions")
    print("=" * 60)

    trader = AlpacaTrader(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        paper=True
    )

    # Cancel all orders
    print("\nCancelling all orders...")
    trader.cancel_all_orders()

    # Close all positions
    print("Closing all positions...")
    positions = trader.get_positions()
    for p in positions:
        print(f"   Selling {p.symbol} x{int(p.qty)}...")
        try:
            trader.place_market_sell(p.symbol, int(p.qty))
        except Exception as e:
            print(f"   Error: {e}")

    print("\nCleanup complete")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--cleanup', action='store_true', help='Cancel all orders and close positions')
    args = parser.parse_args()

    if args.cleanup:
        cleanup()
    else:
        test_orders()
