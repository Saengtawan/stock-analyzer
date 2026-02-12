#!/usr/bin/env python3
"""
Test Complete Monitoring System - Phase 5 Final
================================================
Test all monitoring endpoints and functionality.
"""

import requests
import json

BASE_URL = "http://localhost:5009"


def test_monitoring_system():
    """Test complete monitoring system"""
    print("="*70)
    print("  Testing Complete Monitoring System - Phase 5")
    print("="*70)
    print()

    try:
        # Test 1: Health Check
        print("1️⃣  Testing GET /api/health...")
        response = requests.get(f"{BASE_URL}/api/health")
        print(f"   Status Code: {response.status_code}")

        if response.status_code in (200, 503):
            data = response.json()
            print(f"   Health Status: {data['status']}")
            print(f"   ✅ Quick health check working")
            print()
        else:
            print(f"   ❌ Failed")
            return False

        # Test 2: Detailed Health Check
        print("2️⃣  Testing GET /api/health/detailed...")
        response = requests.get(f"{BASE_URL}/api/health/detailed")
        print(f"   Status Code: {response.status_code}")

        if response.status_code in (200, 503):
            data = response.json()
            print(f"   Health Status: {data['status']}")
            print(f"   Message: {data['message']}")
            print(f"   Total Checks: {data['summary']['total']}")
            print(f"   OK: {data['summary']['ok']}, Warning: {data['summary']['warning']}, Error: {data['summary']['error']}")
            print(f"   ✅ Detailed health check working")
            print()
        else:
            print(f"   ❌ Failed")
            return False

        # Test 3: Performance Metrics
        print("3️⃣  Testing GET /api/metrics...")
        response = requests.get(f"{BASE_URL}/api/metrics?hours=24")
        print(f"   Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Metrics endpoint working")
            print(f"   Query count: {data['metrics']['queries']['count']}")
            print(f"   API count: {data['metrics']['api']['count']}")
            print()
        else:
            print(f"   ❌ Failed")
            return False

        # Test 4: Performance Summary
        print("4️⃣  Testing GET /api/metrics/summary...")
        response = requests.get(f"{BASE_URL}/api/metrics/summary")
        print(f"   Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            summary = data['summary']
            print(f"   ✅ Performance summary working")
            print(f"   Health Score: {summary['health_score']}/100")
            print(f"   Status: {summary['status']}")
            print(f"   Avg Query: {summary['avg_query_time_ms']:.2f}ms")
            print(f"   Cache Hit Rate: {summary['cache_hit_rate']:.1f}%")
            print()
        else:
            print(f"   ❌ Failed")
            return False

        # Test 5: Repository Metrics
        print("5️⃣  Testing GET /api/metrics/repositories...")
        response = requests.get(f"{BASE_URL}/api/metrics/repositories?hours=24")
        print(f"   Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Repository metrics working")
            for repo, stats in data['repositories'].items():
                print(f"   {repo}: {stats['count']} queries")
            print()
        else:
            print(f"   ❌ Failed")
            return False

        # Test 6: Unified Monitor Status
        print("6️⃣  Testing GET /api/monitor/status...")
        response = requests.get(f"{BASE_URL}/api/monitor/status")
        print(f"   Status Code: {response.status_code}")

        if response.status_code in (200, 503):
            data = response.json()
            print(f"   ✅ Unified monitor status working")
            print(f"   Overall Status: {data['overall_status']}")
            print(f"   Health Status: {data['health']['status']}")
            print(f"   Performance Score: {data['performance']['health_score']}/100")
            print(f"   Database OK: {data['system']['database_ok']}")
            print(f"   Repositories OK: {data['system']['repositories_ok']}")
            print()
        else:
            print(f"   ❌ Failed")
            return False

        # Test 7: Complete Dashboard
        print("7️⃣  Testing GET /api/monitor/dashboard...")
        response = requests.get(f"{BASE_URL}/api/monitor/dashboard")
        print(f"   Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            dashboard = data['dashboard']
            print(f"   ✅ Complete dashboard working")
            print(f"   Overall Health: {dashboard['overall_health']}")
            print(f"   Performance Score: {dashboard['performance_score']}/100")
            print(f"   Health Checks: {dashboard['health_checks']['summary']['total']}")
            print(f"   Query Stats: {dashboard['metrics_24h']['queries']['count']} queries")
            print()
        else:
            print(f"   ❌ Failed")
            return False

        # Summary
        print("="*70)
        print("  ✅ All Monitoring Endpoints Working!")
        print("="*70)
        print()

        print("📋 Test Summary:")
        print("   ✅ Quick health check")
        print("   ✅ Detailed health check")
        print("   ✅ Performance metrics")
        print("   ✅ Performance summary")
        print("   ✅ Repository metrics")
        print("   ✅ Unified monitor status")
        print("   ✅ Complete dashboard")
        print()
        print("🎯 Result: Complete monitoring system is operational!")
        print()

        return True

    except requests.exceptions.ConnectionError:
        print(f"\n❌ Error: Could not connect to {BASE_URL}")
        print("   Make sure the web server is running:")
        print("   python src/run_app.py")
        print()
        return False

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "╔" + "="*68 + "╗")
    print("║" + " "*15 + "COMPLETE MONITORING SYSTEM TEST" + " "*22 + "║")
    print("╚" + "="*68 + "╝")
    print()

    success = test_monitoring_system()
    exit(0 if success else 1)
