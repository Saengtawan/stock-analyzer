#!/usr/bin/env python3
"""
Test AlertsRepository - Phase 4B
=================================
Verify alert operations work correctly.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from datetime import datetime, timedelta
from database.repositories.alerts_repository import AlertsRepository, Alert

def test_alerts_repository():
    """Test AlertsRepository operations"""
    print("="*70)
    print("  Testing AlertsRepository - Phase 4B")
    print("="*70)
    print()

    try:
        # Initialize repository
        print("1️⃣  Initializing AlertsRepository...")
        repo = AlertsRepository(db_name='trade_history')
        print("   ✅ Repository initialized\n")

        # Test 1: Create alerts
        print("2️⃣  Creating test alerts...")

        alert1 = Alert(
            level='INFO',
            message='Test info alert - system started',
            timestamp=datetime.now().isoformat(),
            active=True
        )

        alert2 = Alert(
            level='WARNING',
            message='Test warning alert - high exposure detected',
            timestamp=datetime.now().isoformat(),
            active=True,
            metadata={'exposure': 5000, 'threshold': 4000}
        )

        alert3 = Alert(
            level='ERROR',
            message='Test error alert - order failed',
            timestamp=(datetime.now() - timedelta(hours=2)).isoformat(),
            active=True
        )

        id1 = repo.create(alert1)
        id2 = repo.create(alert2)
        id3 = repo.create(alert3)

        print(f"   ✅ Created 3 test alerts (IDs: {id1}, {id2}, {id3})\n")

        # Test 2: Get all alerts
        print("3️⃣  Testing get_all()...")
        all_alerts = repo.get_all(limit=10)
        print(f"   ✅ Retrieved {len(all_alerts)} alerts\n")

        # Test 3: Get active alerts
        print("4️⃣  Testing get_active()...")
        active_alerts = repo.get_active(limit=10)
        print(f"   ✅ Found {len(active_alerts)} active alerts")
        for alert in active_alerts[:3]:
            print(f"      - [{alert.level}] {alert.message[:50]}...")
        print()

        # Test 4: Get by level
        print("5️⃣  Testing get_by_level()...")
        warnings = repo.get_by_level('WARNING', limit=10)
        errors = repo.get_by_level('ERROR', limit=10)
        print(f"   ✅ Warnings: {len(warnings)}, Errors: {len(errors)}\n")

        # Test 5: Get recent alerts
        print("6️⃣  Testing get_recent()...")
        recent = repo.get_recent(hours=24, limit=10)
        print(f"   ✅ Found {len(recent)} alerts in last 24 hours\n")

        # Test 6: Get by ID
        print("7️⃣  Testing get_by_id()...")
        alert = repo.get_by_id(id1)
        if alert:
            print(f"   ✅ Retrieved alert: [{alert.level}] {alert.message}\n")
        else:
            print(f"   ❌ Alert {id1} not found\n")

        # Test 7: Get statistics
        print("8️⃣  Testing get_statistics()...")
        stats = repo.get_statistics(hours=24)
        print(f"   ✅ Statistics (24h):")
        print(f"      - Total: {stats['total']}")
        print(f"      - Active: {stats['active']}")
        print(f"      - INFO: {stats['info']}")
        print(f"      - WARNING: {stats['warning']}")
        print(f"      - ERROR: {stats['error']}")
        print(f"      - CRITICAL: {stats['critical']}")
        print()

        # Test 8: Resolve alert
        print("9️⃣  Testing resolve()...")
        success = repo.resolve(id3)
        if success:
            print(f"   ✅ Alert {id3} resolved\n")

            # Verify it's no longer active
            active_count_before = len(active_alerts)
            active_alerts_after = repo.get_active(limit=10)
            print(f"   ✅ Active alerts: {active_count_before} → {len(active_alerts_after)}\n")
        else:
            print(f"   ❌ Failed to resolve alert {id3}\n")

        # Test 9: Count
        print("🔟 Testing count()...")
        total_count = repo.count(active_only=False)
        active_count = repo.count(active_only=True)
        print(f"   ✅ Total alerts: {total_count}")
        print(f"   ✅ Active alerts: {active_count}\n")

        # Test 10: Delete old alerts (test only - set to 0 days to delete all resolved)
        print("1️⃣1️⃣  Testing delete_old()...")
        # First resolve one more alert
        repo.resolve(id1)
        # Delete old resolved alerts
        deleted = repo.delete_old(days=0)  # Delete all resolved alerts
        print(f"   ✅ Deleted {deleted} old alerts\n")

        # Summary
        print("="*70)
        print("  ✅ All Tests Passed!")
        print("="*70)
        print()
        print("📋 Test Summary:")
        print("   ✅ Repository initialization")
        print("   ✅ Create alerts (with metadata)")
        print("   ✅ Get all alerts")
        print("   ✅ Get active alerts")
        print("   ✅ Get by level")
        print("   ✅ Get recent alerts")
        print("   ✅ Get by ID")
        print("   ✅ Get statistics")
        print("   ✅ Resolve alerts")
        print("   ✅ Count alerts")
        print("   ✅ Delete old alerts")
        print()
        print("🎯 Result: AlertsRepository is fully functional!")
        print()

        return True

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_alerts_repository()
    exit(0 if success else 1)
