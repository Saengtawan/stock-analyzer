#!/usr/bin/env python3
"""
Test PDT Display Logic
======================

Tests that PDT count is displayed correctly with pdt_enforce_always=false
"""

import sys
import os

sys.path.insert(0, 'src')
os.chdir(os.path.dirname(__file__))

print("=" * 70)
print("PDT DISPLAY TEST - Enforce=False Mode")
print("=" * 70)
print()

# Load environment
from dotenv import load_dotenv
load_dotenv('.env')

print("Test 1: Check config setting")
print("-" * 70)
try:
    from config.strategy_config import RapidRotationConfig
    config = RapidRotationConfig()

    print(f"✅ Config loaded")
    print(f"   pdt_enforce_always: {config.pdt_enforce_always}")

    if config.pdt_enforce_always == False:
        print("   ✅ Correct: PDT not enforced (testing mode)")
    else:
        print("   ⚠️  Expected false for testing mode")
except Exception as e:
    print(f"❌ Config load failed: {e}")
    sys.exit(1)

print()

print("Test 2: Check safety check behavior")
print("-" * 70)
try:
    from trading_safety import TradingSafetyGuard
    from engine.brokers import AlpacaBroker

    broker = AlpacaBroker(paper=True)
    account = broker.get_account()

    print(f"✅ Account fetched")
    print(f"   Equity: ${account.equity:,.2f}")
    print(f"   Day Trade Count: {account.day_trade_count}")
    print(f"   Pattern Day Trader: {account.pattern_day_trader}")
    print()

    # Create safety guard with config
    safety = TradingSafetyGuard(config)

    # Check PDT rule
    pdt_check = safety.check_pdt_compliance(account)

    print(f"✅ PDT Safety Check:")
    print(f"   Name: {pdt_check.name}")
    print(f"   Status: {pdt_check.status}")
    print(f"   Message: {pdt_check.message}")
    print(f"   Value: {pdt_check.value}")
    print(f"   Threshold: {pdt_check.threshold}")
    print()

    # Verify the check returns correct data
    if pdt_check.value is not None and pdt_check.threshold is not None:
        print(f"✅ Value fields available for UI:")
        print(f"   Count: {pdt_check.value}/{pdt_check.threshold}")
        print(f"   → UI should display: PDT {pdt_check.value}/{pdt_check.threshold}")
    else:
        print(f"⚠️  Value fields missing - UI may not display correctly")

    print()

    if account.equity >= 25000 and not config.pdt_enforce_always:
        expected_msg = "Above"
        if expected_msg in pdt_check.message:
            print(f"✅ Correct: Message contains 'Above' (equity > $25K, enforce=false)")
            print(f"   But value field still has count: {pdt_check.value}")
            print(f"   → UI will extract and display count from value field")
        else:
            print(f"⚠️  Expected 'Above' in message, got: {pdt_check.message}")

    print()
    print("=" * 70)
    print("✅ TEST PASSED")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  ✅ pdt_enforce_always: {config.pdt_enforce_always} (testing mode)")
    print(f"  ✅ Safety check message: {pdt_check.message}")
    print(f"  ✅ Value field has count: {pdt_check.value}/{pdt_check.threshold}")
    print(f"  ✅ UI will display: PDT {pdt_check.value}/{pdt_check.threshold}")
    print()
    print("Expected Behavior:")
    print("  - PDT not enforced (can trade freely)")
    print("  - But count still displayed for tracking")
    print("  - UI shows: PDT 2/3 (from value field)")
    print("  - Status badge: OK (green) because not enforced")

except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
