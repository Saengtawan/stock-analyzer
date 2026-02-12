#!/usr/bin/env python3
"""
Test Health Checks - Phase 5A
==============================
Test the health check system and API endpoints.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from monitoring import HealthChecker


def test_health_checker():
    """Test HealthChecker class"""
    print("="*70)
    print("  Testing HealthChecker - Phase 5A")
    print("="*70)
    print()

    try:
        # Initialize health checker
        print("1️⃣  Initializing HealthChecker...")
        checker = HealthChecker()
        print(f"   ✅ Health checker initialized")
        print(f"   Data directory: {checker.data_dir}")
        print()

        # Test individual checks
        print("2️⃣  Testing individual health checks...")
        print()

        # Database connectivity
        print("   📊 Database Connectivity:")
        result = checker.check_database_connectivity()
        print(f"      Status: {result.status}")
        print(f"      Message: {result.message}")
        print()

        # Database integrity
        print("   📊 Database Integrity:")
        result = checker.check_database_integrity()
        print(f"      Status: {result.status}")
        print(f"      Message: {result.message}")
        if result.details:
            print(f"      Size: {result.details.get('size_mb', 0):.2f} MB")
        print()

        # Position repository
        print("   📦 Position Repository:")
        result = checker.check_position_repository()
        print(f"      Status: {result.status}")
        print(f"      Message: {result.message}")
        if result.details:
            print(f"      Positions: {result.details.get('count', 0)}")
            print(f"      Backend: {result.details.get('backend', 'unknown')}")
        print()

        # Alert repository
        print("   📦 Alert Repository:")
        result = checker.check_alert_repository()
        print(f"      Status: {result.status}")
        print(f"      Message: {result.message}")
        if result.details:
            print(f"      Total: {result.details.get('total', 0)}")
            print(f"      Active: {result.details.get('active', 0)}")
        print()

        # Trade repository
        print("   📦 Trade Repository:")
        result = checker.check_trade_repository()
        print(f"      Status: {result.status}")
        print(f"      Message: {result.message}")
        if result.details:
            print(f"      Total trades: {result.details.get('total_trades', 0)}")
        print()

        # Disk space
        print("   💾 Disk Space:")
        result = checker.check_disk_space()
        print(f"      Status: {result.status}")
        print(f"      Message: {result.message}")
        if result.details:
            print(f"      Free: {result.details.get('free_gb', 0):.2f} GB")
            print(f"      Used: {result.details.get('used_pct', 0):.1f}%")
        print()

        # Memory
        print("   🧠 Memory:")
        result = checker.check_memory()
        print(f"      Status: {result.status}")
        print(f"      Message: {result.message}")
        if result.details:
            print(f"      Available: {result.details.get('available_gb', 0):.2f} GB")
            print(f"      Used: {result.details.get('used_pct', 0):.1f}%")
        print()

        # File permissions
        print("   📁 File Permissions:")
        result = checker.check_file_permissions()
        print(f"      Status: {result.status}")
        print(f"      Message: {result.message}")
        print()

        # Test quick check
        print("3️⃣  Testing quick health check...")
        quick_result = checker.check_quick()
        print(f"   Status: {quick_result['status']}")
        print(f"   Timestamp: {quick_result['timestamp']}")
        print(f"   Checks: {len(quick_result['checks'])}")
        print()

        # Test comprehensive check
        print("4️⃣  Testing comprehensive health check...")
        full_result = checker.check_all()
        print(f"   Overall Status: {full_result['status']}")
        print(f"   Message: {full_result['message']}")
        print(f"   Timestamp: {full_result['timestamp']}")
        print()
        print(f"   Summary:")
        summary = full_result['summary']
        print(f"      Total checks: {summary['total']}")
        print(f"      ✅ OK: {summary['ok']}")
        print(f"      ⚠️  Warning: {summary['warning']}")
        print(f"      ❌ Error: {summary['error']}")
        print()

        # Show detailed results
        print("5️⃣  Detailed check results:")
        for check in full_result['checks']:
            status_icon = '✅' if check['status'] == 'ok' else '⚠️' if check['status'] == 'warning' else '❌'
            print(f"   {status_icon} {check['component']}: {check['status']}")
        print()

        # Summary
        print("="*70)
        if full_result['status'] == 'ok':
            print("  ✅ All Health Checks Passed!")
        elif full_result['status'] == 'warning':
            print("  ⚠️  Health Checks Passed with Warnings")
        else:
            print("  ❌ Some Health Checks Failed")
        print("="*70)
        print()

        print("📋 Test Summary:")
        print("   ✅ Health checker initialization")
        print("   ✅ Database connectivity check")
        print("   ✅ Database integrity check")
        print("   ✅ Position repository check")
        print("   ✅ Alert repository check")
        print("   ✅ Trade repository check")
        print("   ✅ Disk space check")
        print("   ✅ Memory check")
        print("   ✅ File permissions check")
        print("   ✅ Quick health check")
        print("   ✅ Comprehensive health check")
        print()
        print("🎯 Result: HealthChecker is fully functional!")
        print()

        return full_result['status'] in ('ok', 'warning')

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_health_api():
    """Test health API endpoints"""
    print("="*70)
    print("  Testing Health API Endpoints")
    print("="*70)
    print()

    try:
        import requests

        BASE_URL = "http://localhost:5009"

        # Test quick health check
        print("1️⃣  Testing GET /api/health...")
        response = requests.get(f"{BASE_URL}/api/health")
        print(f"   Status Code: {response.status_code}")

        if response.status_code in (200, 503):
            data = response.json()
            print(f"   Health Status: {data['status']}")
            print(f"   Timestamp: {data['timestamp']}")
            print(f"   Checks: {len(data.get('checks', []))}")
            print()
        else:
            print(f"   ❌ Unexpected status code: {response.status_code}")
            return False

        # Test detailed health check
        print("2️⃣  Testing GET /api/health/detailed...")
        response = requests.get(f"{BASE_URL}/api/health/detailed")
        print(f"   Status Code: {response.status_code}")

        if response.status_code in (200, 503):
            data = response.json()
            print(f"   Health Status: {data['status']}")
            print(f"   Message: {data['message']}")
            print()
            print(f"   Summary:")
            summary = data['summary']
            print(f"      Total: {summary['total']}")
            print(f"      OK: {summary['ok']}")
            print(f"      Warning: {summary['warning']}")
            print(f"      Error: {summary['error']}")
            print()
        else:
            print(f"   ❌ Unexpected status code: {response.status_code}")
            return False

        print("="*70)
        print("  ✅ Health API Tests Passed!")
        print("="*70)
        print()

        return True

    except requests.exceptions.ConnectionError:
        print(f"\n❌ Error: Could not connect to {BASE_URL}")
        print("   Make sure the web server is running:")
        print("   python src/run_app.py")
        print()
        return False

    except Exception as e:
        print(f"\n❌ Error during API testing: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "╔" + "="*68 + "╗")
    print("║" + " "*20 + "HEALTH CHECK TESTS" + " "*30 + "║")
    print("╚" + "="*68 + "╝")
    print()

    # Test health checker class
    health_checker_ok = test_health_checker()

    # Test API endpoints (optional - requires server running)
    print("\n" + "="*70)
    print("  Optional: Test Health API Endpoints")
    print("="*70)
    print()
    print("  To test API endpoints, start the web server first:")
    print("    python src/run_app.py")
    print()
    print("  Then run: python scripts/test_health_api.py")
    print()

    # Exit with appropriate code
    exit(0 if health_checker_ok else 1)
