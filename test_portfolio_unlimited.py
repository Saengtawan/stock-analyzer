#!/usr/bin/env python3
"""
Test Portfolio Unlimited Positions and Remove Function
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from portfolio_manager_v3 import PortfolioManagerV3
from datetime import datetime
import json

print("\n" + "="*80)
print("🧪 TEST: Unlimited Positions + Remove Function")
print("="*80)

# Create a test portfolio
import tempfile
import os

# Create temporary portfolio file
temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
temp_file.write('{"active": [], "closed": [], "stats": {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0, "avg_return": 0.0, "win_count": 0, "loss_count": 0}}')
temp_file.close()

print(f"\nUsing temporary portfolio: {temp_file.name}")

# Initialize with temp file
pm = PortfolioManagerV3(portfolio_file=temp_file.name)

print("\n" + "="*80)
print("TEST 1: Add Multiple Positions (More than 3)")
print("="*80)

test_positions = [
    ('AAPL', 150.00),
    ('MSFT', 380.00),
    ('GOOGL', 140.00),
    ('NVDA', 500.00),
    ('META', 450.00),
    ('TSLA', 250.00),
]

entry_date = '2026-01-01'

print(f"\nAdding {len(test_positions)} positions...")

for symbol, price in test_positions:
    success = pm.add_position(
        symbol=symbol,
        entry_price=price,
        entry_date=entry_date,
        amount=1000
    )
    if success:
        print(f"  ✅ Added {symbol} @ ${price:.2f}")
    else:
        print(f"  ❌ Failed to add {symbol}")

# Check how many were added
active_count = len(pm.portfolio['active'])
print(f"\n📊 Result: {active_count} positions in portfolio")

if active_count >= 4:
    print("✅ PASS: Can add more than 3 positions (old limit removed)")
else:
    print("❌ FAIL: Still limited to 3 positions")

print("\n" + "="*80)
print("TEST 2: Remove Position Function")
print("="*80)

print(f"\nCurrent positions: {active_count}")
print("\nAttempting to remove NVDA...")

removed = pm.remove_position('NVDA')

if removed:
    print("  ✅ NVDA removed successfully")
else:
    print("  ❌ Failed to remove NVDA")

# Check new count
new_count = len(pm.portfolio['active'])
print(f"\nPositions after removal: {new_count}")

if new_count == active_count - 1:
    print("✅ PASS: Remove function works correctly")
else:
    print("❌ FAIL: Remove function not working")

# Verify NVDA is gone
symbols = [p['symbol'] for p in pm.portfolio['active']]
print(f"\nRemaining symbols: {', '.join(symbols)}")

if 'NVDA' not in symbols:
    print("✅ PASS: NVDA confirmed removed")
else:
    print("❌ FAIL: NVDA still in portfolio")

print("\n" + "="*80)
print("TEST 3: Stats Not Affected by Remove")
print("="*80)

stats = pm.portfolio['stats']
print(f"\nTotal Trades: {stats['total_trades']}")
print(f"Win Rate: {stats['win_rate']:.1f}%")
print(f"Total P&L: ${stats['total_pnl']:.2f}")

if stats['total_trades'] == 0:
    print("✅ PASS: Remove doesn't affect stats (not counted as closed trade)")
else:
    print("❌ FAIL: Stats were affected")

print("\n" + "="*80)
print("TEST 4: Try to Remove Non-Existent Position")
print("="*80)

print("\nAttempting to remove XYZ (doesn't exist)...")
removed = pm.remove_position('XYZ')

if not removed:
    print("✅ PASS: Correctly returns False for non-existent position")
else:
    print("❌ FAIL: Should return False")

print("\n" + "="*80)
print("TEST 5: Display Final Portfolio")
print("="*80)

print(f"\nFinal Active Positions: {len(pm.portfolio['active'])}")
print("\nPositions:")

for i, pos in enumerate(pm.portfolio['active'], 1):
    print(f"  {i}. {pos['symbol']:<6} @ ${pos['entry_price']:>7.2f}")

print("\n" + "="*80)
print("✅ ALL TESTS COMPLETE")
print("="*80)

print("\n📝 Summary:")
print(f"  ✅ Can add unlimited positions (tested with {len(test_positions)})")
print(f"  ✅ Remove function works without affecting stats")
print(f"  ✅ Remove returns False for non-existent positions")
print(f"  ✅ Final portfolio has {len(pm.portfolio['active'])} positions")

# Cleanup
os.unlink(temp_file.name)
print(f"\n🗑️  Cleaned up test file: {temp_file.name}")

print("\n" + "="*80)
