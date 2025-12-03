#!/usr/bin/env python3
"""
Test that trailing_stop.py handles None values correctly
"""
from src.analysis.enhanced_features.trailing_stop import TrailingStopManager

# Create instance
manager = TrailingStopManager(symbol="TEST")

# Test 1: Normal values - should work
print("Test 1: Normal values")
try:
    result = manager.analyze(
        entry_price=100.0,
        current_price=105.0,
        original_sl=95.0,
        shares=100
    )
    print(f"✅ Test 1 PASSED - Result: {result['should_move']}")
except Exception as e:
    print(f"❌ Test 1 FAILED - Error: {e}")

# Test 2: None entry_price - should not crash with defensive checks
print("\nTest 2: None entry_price")
try:
    result = manager.analyze(
        entry_price=None,
        current_price=105.0,
        original_sl=95.0,
        shares=100
    )
    print(f"✅ Test 2 PASSED - Handled None entry_price gracefully")
except Exception as e:
    print(f"❌ Test 2 FAILED - Error: {e}")

# Test 3: Zero entry_price - should not crash
print("\nTest 3: Zero entry_price")
try:
    result = manager.analyze(
        entry_price=0,
        current_price=105.0,
        original_sl=95.0,
        shares=100
    )
    print(f"✅ Test 3 PASSED - Handled zero entry_price gracefully")
except Exception as e:
    print(f"❌ Test 3 FAILED - Error: {e}")

print("\n" + "="*70)
print("All tests completed!")
print("="*70)
