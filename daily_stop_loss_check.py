#!/usr/bin/env python3
"""
Daily Stop Loss Check Script v1.0

Run this script daily to check all positions against stop loss rules.
Can be scheduled via cron job.

Usage:
    python daily_stop_loss_check.py           # Check only
    python daily_stop_loss_check.py --sell    # Check and auto-sell triggered positions
"""

import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from portfolio_manager import PortfolioManager


def main():
    print("=" * 70)
    print(f"🕐 DAILY STOP LOSS CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    # Load portfolio
    pm = PortfolioManager('portfolio.json')

    # Check if any active positions
    if not pm.portfolio['active']:
        print("\n📭 No active positions in portfolio")
        print("=" * 70)
        return

    print(f"\n📊 Checking {len(pm.portfolio['active'])} active position(s)...\n")

    # Check stop loss
    results = pm.check_stop_loss(
        hard_stop_pct=-6.0,
        warning_pct=-3.0,
        trailing_stop_pct=-5.0,
        time_stop_days=10
    )

    # Check if --sell flag is passed
    auto_sell = '--sell' in sys.argv

    if results['sell_now']:
        print("\n" + "!" * 70)
        print("🚨 ALERT: POSITIONS NEED TO BE SOLD!")
        print("!" * 70)

        for alert in results['sell_now']:
            print(f"""
   Symbol:  {alert['symbol']}
   Entry:   ${alert['entry_price']:.2f}
   Current: ${alert['current_price']:.2f}
   P&L:     {alert['pnl_pct']:+.1f}% (${alert['pnl_usd']:+.2f})
   Reason:  {alert['reason']}
   Action:  🔴 SELL NOW!
""")

        if auto_sell:
            print("\n🔴 AUTO-SELLING triggered positions...")
            pm.auto_stop_loss_sell(confirm=True)
        else:
            print("\n⚠️  Run with --sell flag to auto-sell:")
            print("    python daily_stop_loss_check.py --sell")

    elif results['warning']:
        print("\n" + "=" * 70)
        print("🟡 WARNING: Some positions approaching stop loss")
        print("=" * 70)
        for alert in results['warning']:
            print(f"   {alert['symbol']}: {alert['pnl_pct']:+.1f}% - Monitor closely!")

    else:
        print("\n" + "=" * 70)
        print("✅ All positions are OK!")
        print("=" * 70)

    # Summary
    print(f"""
📊 Summary:
   🔴 Sell Now:  {len(results['sell_now'])}
   🟡 Warning:   {len(results['warning'])}
   🟢 OK:        {len(results['ok'])}
""")

    # Show portfolio stats
    stats = pm.portfolio.get('stats', {})
    if stats.get('total_trades', 0) > 0:
        print(f"""📈 Portfolio Stats:
   Total Trades:  {stats.get('total_trades', 0)}
   Win Rate:      {stats.get('win_rate', 0):.1f}%
   Total P&L:     ${stats.get('total_pnl', 0):+,.2f}
""")


if __name__ == "__main__":
    main()
