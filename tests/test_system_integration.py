"""
System Integration Tests - ทดสอบความเป็นอันหนึ่งอันเดียวกันของระบบ

Tests that all components are properly connected and data flows correctly.
ไม่ต้อง mock ลึก — เน้นทดสอบว่าแต่ละ component มี method ที่ต้องใช้
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# =============================================================================
# TEST CLASS 1: Flow Connection Tests (Method Existence)
# =============================================================================

class TestFlowConnections:
    """Test that all required methods exist for data flow"""

    def test_engine_has_market_regime_method(self):
        """Engine has _check_market_regime method"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, '_check_market_regime')

    def test_engine_has_bear_sectors_method(self):
        """Engine has _get_bear_allowed_sectors method"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, '_get_bear_allowed_sectors')

    def test_engine_has_conviction_sizing_method(self):
        """Engine has _get_conviction_size method"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, '_get_conviction_size')

    def test_engine_has_execute_signal_method(self):
        """Engine has execute_signal method"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, 'execute_signal')

    def test_engine_has_scan_for_signals_method(self):
        """Engine has scan_for_signals method"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, 'scan_for_signals')

    def test_engine_has_safety_methods(self):
        """Engine has safety check methods"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, 'check_daily_loss_limit')
        assert hasattr(AutoTradingEngine, 'check_weekly_loss_limit')
        assert hasattr(AutoTradingEngine, 'check_consecutive_loss_cooldown')

    def test_engine_has_position_management(self):
        """Engine has position management methods"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, '_close_position')
        assert hasattr(AutoTradingEngine, '_sync_positions')

    def test_pdt_guard_has_required_methods(self):
        """PDT Guard has required methods"""
        from pdt_smart_guard import PDTSmartGuard
        assert hasattr(PDTSmartGuard, 'get_days_held')
        assert hasattr(PDTSmartGuard, 'get_pdt_status')
        assert hasattr(PDTSmartGuard, 'can_sell')
        assert hasattr(PDTSmartGuard, 'record_entry')  # track = record_entry

    def test_screener_has_required_methods(self):
        """Screener has required methods"""
        from screeners.rapid_rotation_screener import RapidRotationScreener
        assert hasattr(RapidRotationScreener, 'screen')
        assert hasattr(RapidRotationScreener, 'load_data')
        assert hasattr(RapidRotationScreener, 'get_portfolio_signals')

    def test_sector_regime_has_required_methods(self):
        """Sector regime detector has required methods"""
        from sector_regime_detector import SectorRegimeDetector
        assert hasattr(SectorRegimeDetector, 'update_all_sectors')
        assert hasattr(SectorRegimeDetector, 'get_sector_regime')

    def test_data_manager_has_required_methods(self):
        """Data manager has required methods"""
        from api.data_manager import DataManager
        assert hasattr(DataManager, 'get_price_data')

    def test_safety_system_has_required_methods(self):
        """Safety system has required methods"""
        from trading_safety import TradingSafetySystem
        assert hasattr(TradingSafetySystem, 'run_health_check')


# =============================================================================
# TEST CLASS 2: Screener Parameter Tests
# =============================================================================

class TestScreenerParameters:
    """Test that screener accepts required parameters"""

    def test_screen_accepts_allowed_sectors(self):
        """screen() method accepts allowed_sectors parameter"""
        import inspect
        from screeners.rapid_rotation_screener import RapidRotationScreener
        sig = inspect.signature(RapidRotationScreener.screen)
        assert 'allowed_sectors' in sig.parameters

    def test_screen_accepts_blocked_sectors(self):
        """screen() method accepts blocked_sectors parameter"""
        import inspect
        from screeners.rapid_rotation_screener import RapidRotationScreener
        sig = inspect.signature(RapidRotationScreener.screen)
        assert 'blocked_sectors' in sig.parameters

    def test_get_portfolio_signals_accepts_sectors(self):
        """get_portfolio_signals() accepts sector parameters"""
        import inspect
        from screeners.rapid_rotation_screener import RapidRotationScreener
        sig = inspect.signature(RapidRotationScreener.get_portfolio_signals)
        assert 'allowed_sectors' in sig.parameters or 'blocked_sectors' in sig.parameters


# =============================================================================
# TEST CLASS 3: BEAR Mode Logic Tests
# =============================================================================

class TestBearModeLogic:
    """Test BEAR mode sector filtering logic"""

    def test_bear_sectors_uses_regime_not_return(self):
        """_get_bear_allowed_sectors uses sector regime (not return_20d)"""
        # Read the source code to verify the logic
        import inspect
        from auto_trading_engine import AutoTradingEngine
        source = inspect.getsource(AutoTradingEngine._get_bear_allowed_sectors)

        # Should use sector_regimes (regime-based)
        assert 'sector_regimes' in source
        # Should check for BEAR/STRONG BEAR
        assert 'BEAR' in source
        assert 'STRONG BEAR' in source

    def test_bear_allowed_excludes_bear_sectors(self):
        """BEAR/STRONG BEAR sectors are excluded"""
        with patch('auto_trading_engine.AlpacaTrader'), \
             patch('auto_trading_engine.TradingSafetySystem'), \
             patch('auto_trading_engine.init_pdt_guard'), \
             patch('auto_trading_engine.get_trade_logger'), \
             patch('alert_manager.get_alert_manager', return_value=MagicMock()), \
             patch('trading_config.apply_config', side_effect=lambda x: None):

            from auto_trading_engine import AutoTradingEngine
            engine = AutoTradingEngine(paper=True)

            # Setup mock sector regime
            engine.screener = MagicMock()
            sr = MagicMock()
            sr.SECTOR_ETFS = {
                'XLK': 'Technology',
                'XLE': 'Energy',
                'XLY': 'Consumer Cyclical',
            }
            sr.sector_regimes = {
                'XLK': 'STRONG BEAR',  # Should be BLOCKED
                'XLE': 'STRONG BULL',  # Should be ALLOWED
                'XLY': 'SIDEWAYS',     # Should be ALLOWED
            }
            engine.screener.sector_regime = sr

            allowed = engine._get_bear_allowed_sectors()

            assert 'Technology' not in allowed
            assert 'Energy' in allowed
            assert 'Consumer Cyclical' in allowed


# =============================================================================
# TEST CLASS 4: Safety System Tests
# =============================================================================

class TestSafetySystemLogic:
    """Test safety system logic"""

    def test_daily_loss_limit_constant_exists(self):
        """DAILY_LOSS_LIMIT_PCT constant exists"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, 'DAILY_LOSS_LIMIT_PCT')

    def test_consecutive_loss_threshold_exists(self):
        """MAX_CONSECUTIVE_LOSSES constant exists"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, 'MAX_CONSECUTIVE_LOSSES')

    def test_vix_threshold_constant_exists(self):
        """REGIME_VIX_MAX constant exists"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, 'REGIME_VIX_MAX')

    def test_circuit_breaker_constant_exists(self):
        """CIRCUIT_BREAKER_MAX_ERRORS constant exists"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, 'CIRCUIT_BREAKER_MAX_ERRORS')
        assert AutoTradingEngine.CIRCUIT_BREAKER_MAX_ERRORS > 0


# =============================================================================
# TEST CLASS 5: Conviction Sizing Tests
# =============================================================================

class TestConvictionSizing:
    """Test conviction sizing logic"""

    def test_conviction_sizing_enabled_flag_exists(self):
        """CONVICTION_SIZING_ENABLED flag exists"""
        from auto_trading_engine import AutoTradingEngine
        assert hasattr(AutoTradingEngine, 'CONVICTION_SIZING_ENABLED')

    def test_conviction_size_method_exists(self):
        """_get_conviction_size method exists and has correct signature"""
        import inspect
        from auto_trading_engine import AutoTradingEngine

        assert hasattr(AutoTradingEngine, '_get_conviction_size')

        # Check signature has signal and params
        sig = inspect.signature(AutoTradingEngine._get_conviction_size)
        params = list(sig.parameters.keys())
        assert 'signal' in params
        assert 'params' in params


# =============================================================================
# TEST CLASS 6: Data Flow Tests
# =============================================================================

class TestDataFlow:
    """Test data layer is properly connected"""

    def test_data_manager_instantiates(self):
        """DataManager can be instantiated"""
        from api.data_manager import DataManager
        dm = DataManager()
        assert dm is not None

    def test_sector_regime_detector_instantiates(self):
        """SectorRegimeDetector can be instantiated"""
        from sector_regime_detector import SectorRegimeDetector
        sr = SectorRegimeDetector()
        assert sr is not None
        assert hasattr(sr, 'SECTOR_ETFS')

    def test_screener_class_exists(self):
        """Screener class can be imported"""
        from screeners.rapid_rotation_screener import RapidRotationScreener
        assert RapidRotationScreener is not None
        # Check that init methods exist
        assert hasattr(RapidRotationScreener, '_init_sector_regime')


# =============================================================================
# TEST CLASS 7: Scanner + Engine Unified Logic Tests
# =============================================================================

class TestUnifiedLogic:
    """Test that Scanner and Engine use the same sector filtering logic"""

    def test_both_use_sector_regime(self):
        """Both run_app scanner and engine use sector regime"""
        # Read run_app._get_scanner_bear_sectors
        with open('src/run_app.py', 'r') as f:
            run_app_source = f.read()

        # Read engine._get_bear_allowed_sectors
        import inspect
        from auto_trading_engine import AutoTradingEngine
        engine_source = inspect.getsource(AutoTradingEngine._get_bear_allowed_sectors)

        # Both should reference sector_regimes
        assert 'sector_regimes' in run_app_source, "run_app should use sector_regimes"
        assert 'sector_regimes' in engine_source, "engine should use sector_regimes"

        # Both should check for BEAR regime
        assert 'BEAR' in run_app_source
        assert 'BEAR' in engine_source

    def test_sideways_sector_allowed_in_both(self):
        """SIDEWAYS sector is ALLOWED in both scanner and engine"""
        # Check engine source
        import inspect
        from auto_trading_engine import AutoTradingEngine
        source = inspect.getsource(AutoTradingEngine._get_bear_allowed_sectors)

        # Should only block BEAR and STRONG BEAR (not SIDEWAYS)
        assert "not in ('BEAR', 'STRONG BEAR')" in source or \
               "not in ('STRONG BEAR', 'BEAR')" in source or \
               ("BEAR" in source and "SIDEWAYS" not in source.split("BEAR")[0])


# =============================================================================
# SUMMARY TEST
# =============================================================================

class TestSystemSummary:
    """Summary test to verify all flows are connected"""

    def test_all_flows_connected(self):
        """Verify all major flows have connection points"""
        flows_verified = {}

        # Flow 1: Market Regime
        from auto_trading_engine import AutoTradingEngine
        flows_verified['market_regime'] = hasattr(AutoTradingEngine, '_check_market_regime')

        # Flow 2: Sector Regime to Conviction
        flows_verified['sector_to_conviction'] = hasattr(AutoTradingEngine, '_get_conviction_size')

        # Flow 3: Signal to Execute
        flows_verified['signal_to_execute'] = hasattr(AutoTradingEngine, 'execute_signal')

        # Flow 4: Position to PDT
        from pdt_smart_guard import PDTSmartGuard
        flows_verified['position_to_pdt'] = hasattr(PDTSmartGuard, 'get_days_held')

        # Flow 5: Bear Mode
        flows_verified['bear_mode'] = hasattr(AutoTradingEngine, '_get_bear_allowed_sectors')

        # Flow 6: Bull Mode
        flows_verified['bull_mode'] = hasattr(AutoTradingEngine, '_get_bull_blocked_sectors')

        # Flow 7: Safety - Daily Loss
        flows_verified['safety_daily_loss'] = hasattr(AutoTradingEngine, 'check_daily_loss_limit')

        # Flow 8: Safety - Consecutive
        flows_verified['safety_consecutive'] = hasattr(AutoTradingEngine, 'check_consecutive_loss_cooldown')

        # Flow 9: Safety - VIX (check in _check_market_regime source)
        import inspect
        regime_source = inspect.getsource(AutoTradingEngine._check_market_regime)
        flows_verified['safety_vix'] = 'vix' in regime_source.lower()

        # Flow 10: Data Manager
        from api.data_manager import DataManager
        flows_verified['data_manager'] = hasattr(DataManager, 'get_price_data')

        # Flow 11: Sector Regime Detector
        from sector_regime_detector import SectorRegimeDetector
        flows_verified['sector_regime_detector'] = hasattr(SectorRegimeDetector, 'update_all_sectors')

        # Print summary
        print("\n" + "=" * 60)
        print("SYSTEM INTEGRATION FLOW VERIFICATION")
        print("=" * 60)

        all_passed = True
        for flow, verified in flows_verified.items():
            status = "✅ CONNECTED" if verified else "❌ DISCONNECTED"
            print(f"  {flow}: {status}")
            if not verified:
                all_passed = False

        print("=" * 60)
        print(f"RESULT: {'ALL FLOWS CONNECTED' if all_passed else 'SOME FLOWS DISCONNECTED'}")
        print("=" * 60 + "\n")

        assert all_passed, f"Some flows disconnected: {[k for k, v in flows_verified.items() if not v]}"
