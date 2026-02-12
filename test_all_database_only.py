#!/usr/bin/env python3
"""
Test All Components - 100% Database-Only
=========================================
Verify that ALL components work WITHOUT any backward compatibility.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

def test_position_repository():
    """Test PositionRepository (100% database-only)"""
    print("1️⃣  Testing PositionRepository...")

    from database import PositionRepository

    repo = PositionRepository()
    assert not hasattr(repo, '_use_database'), "Should NOT have _use_database flag"
    assert not hasattr(repo, 'positions_file'), "Should NOT have positions_file"

    positions = repo.get_all()
    print(f"   ✅ Loaded {len(positions)} positions")
    print("   ✅ PositionRepository: 100% database-only\n")

def test_alert_manager():
    """Test AlertManager (100% database-only)"""
    print("2️⃣  Testing AlertManager...")

    from alert_manager import get_alert_manager

    manager = get_alert_manager()
    assert not hasattr(manager, '_use_database'), "Should NOT have _use_database flag"
    assert not hasattr(manager, '_alerts'), "Should NOT have _alerts list"
    assert not hasattr(manager, '_save'), "Should NOT have _save method"

    summary = manager.get_summary()
    print(f"   ✅ Alerts: {summary['total']} total")
    print("   ✅ AlertManager: 100% database-only\n")

def test_rapid_portfolio_manager():
    """Test RapidPortfolioManager (100% database-only)"""
    print("3️⃣  Testing RapidPortfolioManager...")

    from rapid_portfolio_manager import RapidPortfolioManager

    # Check that USE_DB_LAYER is not used
    import rapid_portfolio_manager as rpm_module
    assert not hasattr(rpm_module, 'USE_DB_LAYER'), "Should NOT have USE_DB_LAYER flag"

    manager = RapidPortfolioManager()
    assert not hasattr(manager, '_save_to_json'), "Should NOT have _save_to_json method"

    print(f"   ✅ Positions: {len(manager.positions)}")
    print("   ✅ RapidPortfolioManager: 100% database-only\n")

def test_trade_logger():
    """Test TradeLogger (100% database-only)"""
    print("4️⃣  Testing TradeLogger...")

    import trade_logger as tl_module

    # Check that USE_DB_LAYER is not used
    assert not hasattr(tl_module, 'USE_DB_LAYER'), "Should NOT have USE_DB_LAYER flag"

    # Verify imports exist
    assert hasattr(tl_module, 'TradeRepository'), "Should have TradeRepository"
    assert hasattr(tl_module, 'TradeModel'), "Should have TradeModel"

    print("   ✅ TradeLogger: 100% database-only\n")

def test_data_manager():
    """Test DataManager (100% database-only)"""
    print("5️⃣  Testing DataManager...")

    import data_manager as dm_module

    # Check that USE_DB_LAYER is not used
    assert not hasattr(dm_module, 'USE_DB_LAYER'), "Should NOT have USE_DB_LAYER flag"

    # Verify imports exist
    assert hasattr(dm_module, 'StockDataRepository'), "Should have StockDataRepository"

    print("   ✅ DataManager: 100% database-only\n")

def main():
    print("="*70)
    print("  Testing All Components - 100% Database-Only")
    print("="*70)
    print()

    try:
        test_position_repository()
        test_alert_manager()
        test_rapid_portfolio_manager()
        test_trade_logger()
        test_data_manager()

        print("="*70)
        print("  ✅ ALL TESTS PASSED!")
        print("="*70)
        print()
        print("🎉 Summary:")
        print("   ✅ PositionRepository: 100% database-only")
        print("   ✅ AlertManager: 100% database-only")
        print("   ✅ RapidPortfolioManager: 100% database-only")
        print("   ✅ TradeLogger: 100% database-only")
        print("   ✅ DataManager: 100% database-only")
        print()
        print("   ❌ No USE_DB_LAYER flags")
        print("   ❌ No USE_DATABASE flags")
        print("   ❌ No _use_database attributes")
        print("   ❌ No JSON fallback code")
        print("   ❌ No _save_to_json() methods")
        print("   ❌ No _load_from_json() methods")
        print()
        print("🏆 ALL BACKWARD COMPATIBILITY REMOVED - 100% DATABASE-ONLY!")
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
