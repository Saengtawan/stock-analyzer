#!/usr/bin/env python3
"""
Test Portfolio System - Check current status
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from portfolio_manager_v3 import PortfolioManagerV3
from datetime import datetime
import json

print("\n" + "="*80)
print("📊 PORTFOLIO SYSTEM STATUS")
print("="*80)

# Initialize portfolio manager
pm = PortfolioManagerV3()

print(f"\nPortfolio File: {pm.portfolio_file}")
print(f"Pre-computed Macro: {'✅ Available' if pm.precomputed_macro else '❌ Not available'}")

# Show current positions
print("\n" + "="*80)
print("💼 ACTIVE POSITIONS")
print("="*80)

active = pm.portfolio.get('active', [])

if not active:
    print("\n⚠️  No active positions")
else:
    print(f"\nTotal: {len(active)} positions")
    print("-" * 80)

    for i, pos in enumerate(active, 1):
        print(f"\n{i}. {pos['symbol']}")
        print(f"   Entry Date:  {pos['entry_date']}")
        print(f"   Entry Price: ${pos['entry_price']:.2f}")
        print(f"   Shares:      {pos.get('shares', 0):.2f}")
        print(f"   Amount:      ${pos.get('amount', 0):.2f}")

        if 'current_price' in pos:
            print(f"   Current:     ${pos['current_price']:.2f}")
            print(f"   P&L:         {pos.get('pnl_pct', 0):+.2f}% (${pos.get('pnl_usd', 0):+.2f})")
            print(f"   Days Held:   {pos.get('days_held', 0)}")

        if 'take_profit' in pos:
            print(f"   Take Profit: ${pos['take_profit']:.2f}")
        if 'stop_loss' in pos:
            print(f"   Stop Loss:   ${pos['stop_loss']:.2f}")

# Show stats
print("\n" + "="*80)
print("📈 PORTFOLIO STATISTICS")
print("="*80)

stats = pm.portfolio.get('stats', {})
print(f"\nTotal Trades:  {stats.get('total_trades', 0)}")
print(f"Win Rate:      {stats.get('win_rate', 0):.1f}%")
print(f"Total P&L:     ${stats.get('total_pnl', 0):+.2f}")
print(f"Avg Return:    {stats.get('avg_return', 0):+.2f}%")
print(f"Wins:          {stats.get('win_count', 0)}")
print(f"Losses:        {stats.get('loss_count', 0)}")

# Show closed positions
closed = pm.portfolio.get('closed', [])
if closed:
    print("\n" + "="*80)
    print("📝 CLOSED POSITIONS")
    print("="*80)
    print(f"\nTotal: {len(closed)} positions")

# Update positions with current prices
print("\n" + "="*80)
print("🔄 UPDATING POSITIONS")
print("="*80)

current_date = datetime.now().strftime('%Y-%m-%d')
print(f"\nUpdating to: {current_date}")

try:
    updates = pm.update_positions(current_date)

    print(f"\n✅ Update complete!")

    # Show holding positions
    holding = updates.get('holding', [])
    print(f"\nHolding: {len(holding)} positions")

    for pos in holding:
        pnl_pct = pos.get('pnl_pct', 0)
        status = "🟢" if pnl_pct > 0 else "🔴" if pnl_pct < 0 else "⚪"
        print(f"  {status} {pos['symbol']}: {pnl_pct:+.2f}% (${pos.get('pnl_usd', 0):+.2f})")

    # Show exit signals
    exit_positions = updates.get('exit_positions', [])
    if exit_positions:
        print(f"\n⚠️  EXIT SIGNALS: {len(exit_positions)} positions")
        for pos in exit_positions:
            print(f"  🚨 {pos['symbol']}: {pos['exit_reason']}")
            print(f"     P&L: {pos.get('pnl_pct', 0):+.2f}%")

    # Show closed
    closed_now = updates.get('closed', [])
    if closed_now:
        print(f"\n📝 AUTO-CLOSED: {len(closed_now)} positions")
        for pos in closed_now:
            print(f"  ✅ {pos['symbol']}: {pos['exit_reason']}")
            print(f"     Final P&L: {pos.get('pnl_pct', 0):+.2f}%")

except Exception as e:
    print(f"\n❌ Error updating positions: {e}")
    import traceback
    traceback.print_exc()

# Get summary
print("\n" + "="*80)
print("📊 SUMMARY")
print("="*80)

try:
    summary = pm.get_summary()

    print(f"\nActive Positions:  {summary.get('active_count', 0)}")
    print(f"Total Value:       ${summary.get('total_value', 0):,.2f}")
    print(f"Total P&L:         ${summary.get('total_pnl', 0):+,.2f}")
    print(f"Total P&L %:       {summary.get('total_pnl_pct', 0):+.2f}%")

    print(f"\nAll-Time Stats:")
    print(f"  Total Trades:    {summary.get('total_trades', 0)}")
    print(f"  Win Rate:        {summary.get('win_rate', 0):.1f}%")
    print(f"  Avg Return:      {summary.get('avg_return', 0):+.2f}%")

except Exception as e:
    print(f"\n❌ Error getting summary: {e}")

print("\n" + "="*80)
print("✅ PORTFOLIO TEST COMPLETE")
print("="*80)

# Show features
print("\n" + "="*80)
print("🎯 PORTFOLIO FEATURES")
print("="*80)

print("""
Portfolio Manager v3.0 - Complete 6-Layer System Integration

Features:
✅ Position Tracking
   • Max 3 positions (same as backtest)
   • $1000 per position
   • Automatic position sizing

✅ Exit Rules (6-Layer System)
   • Hard Stop: -6%
   • Regime Change: BEAR/WEAK market
   • Trailing Stop: -6%/-7% from peak (after 5 days)
   • Max Hold: 30 days
   • Dynamic Stop Tightening: +3% → breakeven, +5% → +2%

✅ Real-time Monitoring
   • Daily price updates
   • Exit signal detection
   • Automatic position closing

✅ Performance Tracking
   • Win rate
   • Average returns
   • Total P&L

✅ Web Interface
   • Portfolio page at /portfolio
   • Real-time updates via API
   • Add/close positions manually

Integration:
• Uses Complete 6-Layer System for analysis
• Pre-computed macro regimes (fast!)
• Market regime detection
• Comprehensive exit rules
""")

print("="*80)
