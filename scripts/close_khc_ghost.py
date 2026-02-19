#!/usr/bin/env python3
"""
Close KHC ghost position - Run when market opens
Ghost fill from Feb 18 11:30 AM that wasn't tracked in DB
"""
import os
import time
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderStatus

load_dotenv()

def close_khc_ghost():
    """Close KHC position that wasn't tracked in our system"""
    client = TradingClient(
        os.getenv('ALPACA_API_KEY'),
        os.getenv('ALPACA_SECRET_KEY'),
        paper=True
    )

    print("🔍 Checking KHC position and orders...")

    # Step 1: Check if position still exists
    try:
        positions = client.get_all_positions()
        khc_pos = next((p for p in positions if p.symbol == 'KHC'), None)

        if not khc_pos:
            print("✅ No KHC position found - already closed or doesn't exist")
            return

        print(f"\n📊 KHC Position:")
        print(f"   Qty: {khc_pos.qty}")
        print(f"   Entry: ${khc_pos.avg_entry_price}")
        print(f"   Current: ${khc_pos.current_price}")
        print(f"   P&L: ${khc_pos.unrealized_pl} ({khc_pos.unrealized_plpc}%)")

    except Exception as e:
        print(f"❌ Error checking position: {e}")
        return

    # Step 2: Cancel all open KHC orders (including stuck SL)
    print("\n🔄 Cancelling all KHC orders...")
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        request = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=['KHC']
        )
        orders = client.get_orders(request)

        for order in orders:
            print(f"   Cancelling order {order.id} ({order.type}, {order.side})")
            client.cancel_order_by_id(order.id)

        # Wait for cancellations to process
        print("   Waiting 3s for cancellations to process...")
        time.sleep(3)

        # Verify all cancelled
        orders_after = client.get_orders(request)
        if orders_after:
            print(f"   ⚠️ {len(orders_after)} orders still pending, waiting 5s more...")
            time.sleep(5)
        else:
            print("   ✅ All orders cancelled")

    except Exception as e:
        print(f"   ⚠️ Error cancelling orders: {e}")

    # Step 3: Close the position
    print("\n📤 Closing KHC position with market order...")
    try:
        order = client.close_position('KHC')
        print(f"✅ Close order submitted!")
        print(f"   Order ID: {order.id}")
        print(f"   Side: {order.side}")
        print(f"   Qty: {order.qty}")
        print(f"   Status: {order.status}")

        # Wait and check final status
        print("\n⏳ Waiting 5s for fill...")
        time.sleep(5)

        final_order = client.get_order_by_id(order.id)
        print(f"\n📋 Final Status:")
        print(f"   Status: {final_order.status}")
        if final_order.filled_avg_price:
            pnl = (float(final_order.filled_avg_price) - float(khc_pos.avg_entry_price)) * int(khc_pos.qty)
            pnl_pct = (pnl / (float(khc_pos.avg_entry_price) * int(khc_pos.qty))) * 100
            print(f"   Fill Price: ${final_order.filled_avg_price}")
            print(f"   P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")

        return final_order

    except Exception as e:
        print(f"❌ Error closing position: {e}")
        print("\n💡 If error persists, manually close via Alpaca web UI")
        return None


if __name__ == "__main__":
    print("=" * 60)
    print("  Close KHC Ghost Position")
    print("  Ghost fill from 2026-02-18 11:30 AM")
    print("=" * 60)
    print()

    # Check market status
    from alpaca.trading.client import TradingClient
    client = TradingClient(
        os.getenv('ALPACA_API_KEY'),
        os.getenv('ALPACA_SECRET_KEY'),
        paper=True
    )
    clock = client.get_clock()

    if not clock.is_open:
        print("⚠️ Market is CLOSED")
        print("   This script should run when market is OPEN")
        print(f"   Next open: {clock.next_open}")
        print()
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            exit(0)

    print()
    close_khc_ghost()
    print()
    print("=" * 60)
    print("Done!")
