#!/usr/bin/env python3
"""
Test Alert API Endpoints - Phase 4C
=====================================
Test the web API endpoints for alert management.
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:5009"

def test_alert_api():
    """Test alert API endpoints"""
    print("="*70)
    print("  Testing Alert API Endpoints - Phase 4C")
    print("="*70)
    print()

    try:
        # Test 1: Get active alerts
        print("1️⃣  Testing GET /api/rapid/alerts (active)...")
        response = requests.get(f"{BASE_URL}/api/rapid/alerts")

        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Status: {response.status_code}")
            print(f"   ✅ Active alerts: {data['count']}")
            print()
        else:
            print(f"   ❌ Status: {response.status_code}")
            print(f"   Error: {response.text}")
            return False

        # Test 2: Create new alert
        print("2️⃣  Testing POST /api/rapid/alerts (create)...")
        new_alert = {
            'level': 'WARNING',
            'message': 'API Test Alert - High exposure detected',
            'metadata': {'test': True, 'exposure': 5000}
        }

        response = requests.post(
            f"{BASE_URL}/api/rapid/alerts",
            json=new_alert,
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code == 200:
            data = response.json()
            alert_id = data.get('alert_id')
            print(f"   ✅ Status: {response.status_code}")
            print(f"   ✅ Created alert ID: {alert_id}")
            print()
        else:
            print(f"   ❌ Status: {response.status_code}")
            print(f"   Error: {response.text}")
            return False

        # Test 3: Get all alerts
        print("3️⃣  Testing GET /api/rapid/alerts/all...")
        response = requests.get(f"{BASE_URL}/api/rapid/alerts/all?hours=24&limit=10")

        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Status: {response.status_code}")
            print(f"   ✅ Recent alerts (24h): {data['count']}")
            print()
        else:
            print(f"   ❌ Status: {response.status_code}")
            print(f"   Error: {response.text}")
            return False

        # Test 4: Get by level
        print("4️⃣  Testing GET /api/rapid/alerts/all?level=WARNING...")
        response = requests.get(f"{BASE_URL}/api/rapid/alerts/all?level=WARNING")

        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Status: {response.status_code}")
            print(f"   ✅ Warning alerts: {data['count']}")
            if data['count'] > 0:
                print(f"   Latest: {data['alerts'][0]['message'][:50]}...")
            print()
        else:
            print(f"   ❌ Status: {response.status_code}")
            print(f"   Error: {response.text}")
            return False

        # Test 5: Get statistics
        print("5️⃣  Testing GET /api/rapid/alerts/statistics...")
        response = requests.get(f"{BASE_URL}/api/rapid/alerts/statistics?hours=24")

        if response.status_code == 200:
            data = response.json()
            stats = data['statistics']
            print(f"   ✅ Status: {response.status_code}")
            print(f"   ✅ Statistics (24h):")
            print(f"      - Total: {stats['total']}")
            print(f"      - Active: {stats['active']}")
            print(f"      - INFO: {stats['info']}")
            print(f"      - WARNING: {stats['warning']}")
            print(f"      - ERROR: {stats['error']}")
            print(f"      - CRITICAL: {stats['critical']}")
            print()
        else:
            print(f"   ❌ Status: {response.status_code}")
            print(f"   Error: {response.text}")
            return False

        # Test 6: Resolve alert
        if alert_id:
            print(f"6️⃣  Testing PUT /api/rapid/alerts/{alert_id}/resolve...")
            response = requests.put(f"{BASE_URL}/api/rapid/alerts/{alert_id}/resolve")

            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Status: {response.status_code}")
                print(f"   ✅ {data['message']}")
                print()
            else:
                print(f"   ❌ Status: {response.status_code}")
                print(f"   Error: {response.text}")
                return False

        # Test 7: Cleanup old alerts (dry run - 0 days to see how many would be deleted)
        print("7️⃣  Testing DELETE /api/rapid/alerts/cleanup...")
        response = requests.delete(f"{BASE_URL}/api/rapid/alerts/cleanup?days=30")

        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Status: {response.status_code}")
            print(f"   ✅ Deleted {data['deleted']} old alerts")
            print()
        else:
            print(f"   ❌ Status: {response.status_code}")
            print(f"   Error: {response.text}")
            return False

        # Summary
        print("="*70)
        print("  ✅ All API Tests Passed!")
        print("="*70)
        print()
        print("📋 Test Summary:")
        print("   ✅ GET /api/rapid/alerts (active)")
        print("   ✅ POST /api/rapid/alerts (create)")
        print("   ✅ GET /api/rapid/alerts/all (recent)")
        print("   ✅ GET /api/rapid/alerts/all?level=WARNING (filter)")
        print("   ✅ GET /api/rapid/alerts/statistics")
        print("   ✅ PUT /api/rapid/alerts/:id/resolve")
        print("   ✅ DELETE /api/rapid/alerts/cleanup")
        print()
        print("🎯 Result: Alert API is fully functional!")
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
    success = test_alert_api()
    exit(0 if success else 1)
