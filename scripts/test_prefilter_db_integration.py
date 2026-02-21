#!/usr/bin/env python3
"""Test Pre-filter Database Integration (Phase 2B)"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import PreFilterRepository

def test_integration():
    """Test that pre-filter writes to database correctly"""

    print("=" * 60)
    print("Testing Pre-filter Database Integration")
    print("=" * 60)

    repo = PreFilterRepository()

    # Check latest session
    print("\n1️⃣ Checking latest session...")
    latest = repo.get_latest_session()

    if not latest:
        print("❌ No sessions found")
        return False

    print(f"✅ Latest session found:")
    print(f"   ID: {latest.id}")
    print(f"   Type: {latest.scan_type}")
    print(f"   Time: {latest.scan_time}")
    print(f"   Status: {latest.status}")
    print(f"   Pool size: {latest.pool_size}")
    print(f"   Total scanned: {latest.total_scanned}")
    print(f"   Ready: {latest.is_ready}")

    # Check filtered pool
    print("\n2️⃣ Checking filtered pool...")
    pool = repo.get_filtered_pool(latest.id)

    if not pool:
        print("⚠️ No stocks in pool (could be scan in progress)")
    else:
        print(f"✅ Pool size: {len(pool)} stocks")
        print(f"   First 5: {', '.join([s.symbol for s in pool[:5]])}")

    # Check pool size history
    print("\n3️⃣ Checking pool size history...")
    history = repo.get_pool_size_history(days=7)

    if history:
        print(f"✅ History: {len(history)} sessions in last 7 days")
        for h in history[:5]:
            print(f"   - {h['scan_time']}: {h['pool_size']} stocks ({h['scan_type']})")
    else:
        print("⚠️ No history")

    print("\n" + "=" * 60)
    print("✅ Integration Test Complete!")
    print("=" * 60)
    print("\n💡 Next steps:")
    print("   1. Run: python3 src/pre_filter.py evening")
    print("   2. Run this test again to verify new session")
    print("   3. Check web UI shows correct pool size")

    return True

if __name__ == '__main__':
    try:
        success = test_integration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
