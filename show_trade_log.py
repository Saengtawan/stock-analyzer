#!/usr/bin/env python3
"""
TRADE LOG & SLIPPAGE ANALYSIS

แสดงประวัติ fills ทั้งหมด พร้อมวิเคราะห์ slippage

Usage:
    python show_trade_log.py [days]

    days: Number of days to look back (default: 7)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from engine.brokers import AlpacaBroker
from datetime import datetime


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7

    print("=" * 80)
    print(f"📜 TRADE LOG & SLIPPAGE ANALYSIS (Last {days} Days)")
    print("=" * 80)

    try:
        # Initialize broker
        broker = AlpacaBroker(paper=True)

        # Get activities
        print(f"\n🔄 Fetching trade history...")
        activities = broker.get_activities(activity_types='FILL,DIV', days=days)

        if not activities:
            print("\n  No trades found in the last {} days".format(days))
            return

        # Separate fills and dividends
        fills = [a for a in activities if a['activity_type'] == 'FILL']
        dividends = [a for a in activities if a['activity_type'] == 'DIV']

        # Display fills
        print("\n" + "=" * 80)
        print(f"📊 TRADE FILLS ({len(fills)} fills)")
        print("=" * 80)
        print(f"  {'Date':<12} {'Time':<8} {'Symbol':<8} {'Side':<6} {'Qty':>6} {'Price':>10}")
        print("  " + "-" * 74)

        total_bought = 0
        total_sold = 0

        for fill in fills:
            dt = datetime.fromisoformat(fill['transaction_time'].replace('Z', '+00:00'))
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M:%S')

            symbol = fill['symbol']
            side = fill['side'].upper()
            qty = fill['qty']
            price = fill['price']

            print(f"  {date_str:<12} {time_str:<8} {symbol:<8} {side:<6} {qty:>6.0f} ${price:>9.2f}")

            if side == 'BUY':
                total_bought += qty * price
            else:
                total_sold += qty * price

        print("\n" + "=" * 80)
        print("💰 FILL SUMMARY")
        print("=" * 80)
        print(f"  Total Bought:  ${total_bought:,.2f}")
        print(f"  Total Sold:    ${total_sold:,.2f}")
        print(f"  Net Flow:      ${total_sold - total_bought:+,.2f}")

        # Slippage analysis
        print("\n" + "=" * 80)
        print("📊 SLIPPAGE ANALYSIS")
        print("=" * 80)

        # Get recent orders for slippage comparison
        orders = broker.get_orders(status='filled')

        if orders:
            slippage_analysis = broker.analyze_slippage(fills, orders)

            print(f"  Total Fills:           {slippage_analysis['total_fills']}")
            print(f"  Avg Slippage:          ${slippage_analysis['avg_slippage_usd']:.4f} per share")
            print(f"  Avg Slippage %:        {slippage_analysis['avg_slippage_pct']:.4f}%")
            print(f"  Total Slippage Cost:   ${slippage_analysis['total_slippage_cost']:+.2f}")
            print(f"  Favorable Fills:       {slippage_analysis['positive_slippage_count']} ✅")
            print(f"  Unfavorable Fills:     {slippage_analysis['negative_slippage_count']}")

            if slippage_analysis['total_fills'] > 0:
                favorable_pct = (slippage_analysis['positive_slippage_count'] / slippage_analysis['total_fills']) * 100
                print(f"  Favorable Fill Rate:   {favorable_pct:.1f}%")

                if abs(slippage_analysis['avg_slippage_usd']) < 0.05:
                    print("\n  ✅ Excellent execution quality!")
                elif abs(slippage_analysis['avg_slippage_usd']) < 0.10:
                    print("\n  ✅ Good execution quality")
                else:
                    print(f"\n  ⚠️  High slippage (${slippage_analysis['avg_slippage_usd']:.4f}) - consider using limit orders")

        # Display dividends if any
        if dividends:
            print("\n" + "=" * 80)
            print(f"💰 DIVIDENDS ({len(dividends)} payments)")
            print("=" * 80)
            print(f"  {'Date':<12} {'Symbol':<8} {'Qty':>6} {'Amount':>10}")
            print("  " + "-" * 40)

            total_div = 0
            for div in dividends:
                dt = datetime.fromisoformat(div['transaction_time'].replace('Z', '+00:00'))
                date_str = dt.strftime('%Y-%m-%d')

                symbol = div['symbol']
                qty = div.get('qty', 0)
                amount = div.get('amount', 0)

                print(f"  {date_str:<12} {symbol:<8} {qty:>6.0f} ${amount:>9.2f}")
                total_div += amount

            print(f"\n  Total Dividends: ${total_div:,.2f}")

        print("\n" + "=" * 80)
        print("✅ Report complete!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
