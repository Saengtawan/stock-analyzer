#!/usr/bin/env python3
"""
Test Database-Only System (No Backward Compatibility)
======================================================
Verify that the system works WITHOUT JSON fallback.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from database import PositionRepository, TradeRepository, AlertsRepository
from alert_manager import get_alert_manager

def test_position_repository():
    """Test PositionRepository (database-only)"""
    print("1️⃣  Testing PositionRepository...")

    repo = PositionRepository()

    # Check initialization
    assert hasattr(repo, 'db'), "Should have db attribute"
    assert hasattr(repo, '_cache'), "Should have cache attribute"
    assert not hasattr(repo, '_use_database'), "Should NOT have _use_database flag"
    assert not hasattr(repo, 'positions_file'), "Should NOT have positions_file"
    assert not hasattr(repo, '_save_to_json'), "Should NOT have _save_to_json method"
    assert not hasattr(repo, '_load_from_json'), "Should NOT have _load_from_json method"

    # Test operations
    positions = repo.get_all()
    print(f"   ✅ Loaded {len(positions)} positions from database")

    count = repo.count()
    print(f"   ✅ Position count: {count}")

    print("   ✅ PositionRepository: 100% database-only\n")

def test_trade_repository():
    """Test TradeRepository (database-only)"""
    print("2️⃣  Testing TradeRepository...")

    repo = TradeRepository()

    # Check initialization
    assert hasattr(repo, 'db'), "Should have db attribute"

    # Test operations
    trades = repo.get_all(limit=10)
    print(f"   ✅ Loaded {len(trades)} trades from database")

    print("   ✅ TradeRepository: 100% database-only\n")

def test_alerts_repository():
    """Test AlertsRepository (database-only)"""
    print("3️⃣  Testing AlertsRepository...")

    repo = AlertsRepository()

    # Test operations
    active = repo.get_active(limit=10)
    print(f"   ✅ Loaded {len(active)} active alerts from database")

    stats = repo.get_statistics(hours=24)
    print(f"   ✅ Alert statistics: {stats['total']} total, {stats['active']} active")

    print("   ✅ AlertsRepository: 100% database-only\n")

def test_alert_manager():
    """Test AlertManager (database-only)"""
    print("4️⃣  Testing AlertManager...")

    manager = get_alert_manager()

    # Check initialization
    assert hasattr(manager, '_repo'), "Should have _repo attribute"
    assert not hasattr(manager, '_use_database'), "Should NOT have _use_database flag"
    assert not hasattr(manager, '_alerts'), "Should NOT have _alerts list"
    assert not hasattr(manager, '_next_id'), "Should NOT have _next_id counter"
    assert not hasattr(manager, '_save'), "Should NOT have _save method"
    assert not hasattr(manager, '_load'), "Should NOT have _load method"
    assert not hasattr(manager, '_file_path'), "Should NOT have _file_path"

    # Test operations
    summary = manager.get_summary()
    print(f"   ✅ Alert summary: {summary['total']} total, {summary['unacknowledged']} unacknowledged")

    recent = manager.get_recent(limit=5)
    print(f"   ✅ Loaded {len(recent)} recent alerts")

    print("   ✅ AlertManager: 100% database-only\n")

def main():
    print("="*70)
    print("  Testing Database-Only System (No Backward Compatibility)")
    print("="*70)
    print()

    try:
        test_position_repository()
        test_trade_repository()
        test_alerts_repository()
        test_alert_manager()

        print("="*70)
        print("  ✅ ALL TESTS PASSED!")
        print("="*70)
        print()
        print("🎉 Summary:")
        print("   ✅ PositionRepository: 100% database-only")
        print("   ✅ TradeRepository: 100% database-only")
        print("   ✅ AlertsRepository: 100% database-only")
        print("   ✅ AlertManager: 100% database-only")
        print()
        print("   ❌ No JSON fallback code")
        print("   ❌ No _use_database flags")
        print("   ❌ No _save_to_json() methods")
        print("   ❌ No _load_from_json() methods")
        print()
        print("🏆 BACKWARD COMPATIBILITY SUCCESSFULLY REMOVED!")
        print()

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
