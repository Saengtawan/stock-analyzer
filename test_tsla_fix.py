#!/usr/bin/env python3
"""
Test the fixed get_premarket_data for TSLA
Should now show Dec 15 close ($475.31) instead of stale Dec 12 close ($458.96)
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from api.yahoo_finance_client import YahooFinanceClient

print("=" * 80)
print("Testing FIXED get_premarket_data for TSLA")
print("=" * 80)

client = YahooFinanceClient()

# Test TSLA
pm_data = client.get_premarket_data("TSLA", interval="5m")

if pm_data.get('has_premarket_data'):
    print(f"\n✅ TSLA Pre-market Data:")
    print(f"   Previous Close: ${pm_data['previous_close']:.2f}")
    print(f"   Current PM Price: ${pm_data['current_premarket_price']:.2f}")
    print(f"   Gap: {pm_data['gap_percent']:.2f}% ({pm_data['gap_direction']})")
    print(f"   Gap Amount: ${pm_data['gap_amount']:.2f}")
    print(f"   PM High: ${pm_data['premarket_high']:.2f}")
    print(f"   PM Low: ${pm_data['premarket_low']:.2f}")
    print(f"   PM Volume: {pm_data['premarket_volume']:,}")

    print("\n" + "=" * 80)
    print("EXPECTED:")
    print("   Previous Close: $475.31 (Dec 15)")
    print("   Gap: Should be small (< 1%) if PM price around $471-475")
    print("=" * 80)

    # Verify if it's correct
    if abs(pm_data['previous_close'] - 475.31) < 0.50:
        print("\n✅ SUCCESS! Previous close is correct (Dec 15 close)")
    else:
        print(f"\n❌ FAIL! Previous close is still wrong")
        print(f"   Got: ${pm_data['previous_close']:.2f}")
        print(f"   Expected: ~$475.31")
else:
    print(f"\n❌ Error: {pm_data.get('error', 'Unknown error')}")
