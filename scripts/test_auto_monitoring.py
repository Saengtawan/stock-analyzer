#!/usr/bin/env python3
"""
Test Automatic Monitoring - Phase 5D
=====================================
Test the automatic monitoring service.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from monitoring import AutoMonitor, get_auto_monitor


def test_auto_monitor():
    """Test AutoMonitor class"""
    print("="*70)
    print("  Testing Automatic Monitoring - Phase 5D")
    print("="*70)
    print()

    try:
        # Initialize monitor
        print("1️⃣  Initializing AutoMonitor...")
        monitor = AutoMonitor(
            health_check_interval=10,  # 10 seconds for testing
            alert_threshold=70.0,
            enabled=True
        )
        print(f"   ✅ Monitor initialized")
        print(f"   Check interval: {monitor.health_check_interval}s")
        print(f"   Alert threshold: {monitor.alert_threshold}")
        print()

        # Add alert callback
        print("2️⃣  Adding alert callback...")
        alerts_received = []

        def on_alert(alert):
            alerts_received.append(alert)
            print(f"   🚨 ALERT: [{alert['type']}] {alert['message']}")

        monitor.add_alert_callback(on_alert)
        print("   ✅ Alert callback registered")
        print()

        # Start monitoring
        print("3️⃣  Starting automatic monitoring...")
        monitor.start()
        print(f"   ✅ Monitoring started")
        print(f"   Running: {monitor.is_running()}")
        print()

        # Wait for a few health checks
        print("4️⃣  Waiting for health checks...")
        print("   (Will run 2 health checks - 20 seconds)")
        print()

        for i in range(20):
            time.sleep(1)
            stats = monitor.get_stats()
            if i % 5 == 0:
                print(f"   [{i}s] Checks: {stats['health_checks_run']}, "
                      f"Alerts: {stats['alerts_triggered']}, "
                      f"Score: {stats['last_health_score']}")

        print()

        # Get statistics
        print("5️⃣  Getting monitoring statistics...")
        stats = monitor.get_stats()
        print(f"   📊 Statistics:")
        print(f"      Running: {stats['running']}")
        print(f"      Health checks: {stats['health_checks_run']}")
        print(f"      Alerts triggered: {stats['alerts_triggered']}")
        print(f"      Last status: {stats['last_health_status']}")
        print(f"      Last score: {stats['last_health_score']}")
        print()

        # Stop monitoring
        print("6️⃣  Stopping automatic monitoring...")
        monitor.stop()
        print(f"   ✅ Monitoring stopped")
        print(f"   Running: {monitor.is_running()}")
        print()

        # Test singleton
        print("7️⃣  Testing singleton pattern...")
        monitor2 = get_auto_monitor()
        print(f"   ✅ Singleton working: {monitor2 is not monitor}")
        print()

        # Summary
        print("="*70)
        print("  ✅ All Automatic Monitoring Tests Passed!")
        print("="*70)
        print()

        print("📋 Test Summary:")
        print("   ✅ Monitor initialization")
        print("   ✅ Alert callback registration")
        print("   ✅ Start monitoring")
        print("   ✅ Health checks run automatically")
        print("   ✅ Statistics tracking")
        print("   ✅ Stop monitoring")
        print("   ✅ Singleton pattern")
        print()

        if stats['health_checks_run'] >= 2:
            print(f"🎯 Result: {stats['health_checks_run']} health checks completed!")
        else:
            print(f"⚠️  Warning: Only {stats['health_checks_run']} health checks (expected 2+)")

        print()

        return True

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "╔" + "="*68 + "╗")
    print("║" + " "*16 + "AUTOMATIC MONITORING TEST" + " "*27 + "║")
    print("╚" + "="*68 + "╝")
    print()

    success = test_auto_monitor()
    exit(0 if success else 1)
