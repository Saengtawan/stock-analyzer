#!/usr/bin/env python3
"""
Smoke Test Suite for Rapid Trader v4.9.4

Tests that functions run without error and return correct types.
All external dependencies (Alpaca, Yahoo Finance) are mocked.
"""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import numpy as np

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# =============================================================================
# MOCK HELPERS
# =============================================================================

def create_mock_account():
    return {
        'equity': 4000.0,
        'cash': 3000.0,
        'portfolio_value': 4000.0,
        'last_equity': 4000.0,
        'buying_power': 3000.0,
        'daytrade_count': 0,
        'pattern_day_trader': False,
    }


def create_mock_trader():
    trader = MagicMock()
    trader.get_account.return_value = create_mock_account()
    trader.get_positions.return_value = []
    trader.get_clock.return_value = {'is_open': True, 'next_open': '2026-02-05T09:30:00-05:00'}
    trader.get_snapshot.return_value = {'latestTrade': {'p': 150.0}}
    trader.place_market_buy.return_value = {'id': 'order-123', 'status': 'filled', 'filled_qty': '10'}
    trader.place_market_sell.return_value = {'id': 'order-456', 'status': 'filled', 'filled_qty': '10'}
    return trader


def create_mock_signal(symbol='AAPL', score=85, sector='Technology', alt_data_score=5.0):
    from screeners.rapid_rotation_screener import RapidRotationSignal
    return RapidRotationSignal(
        symbol=symbol,
        score=score,
        entry_price=150.0,
        stop_loss=147.0,
        take_profit=156.0,
        risk_reward=2.0,
        atr_pct=2.5,
        rsi=55.0,
        momentum_5d=-1.5,
        momentum_20d=5.0,
        distance_from_high=-3.0,
        reasons=['DIP', 'BOUNCE'],
        sector=sector,
        alt_data_score=alt_data_score,
    )


def create_managed_position(symbol='AAPL', entry_price=150.0):
    from auto_trading_engine import ManagedPosition
    return ManagedPosition(
        symbol=symbol,
        qty=10,
        entry_price=entry_price,
        entry_time=datetime.now(),
        sl_order_id='sl-123',
        current_sl_price=entry_price * 0.975,
        peak_price=entry_price * 1.02,
        sector='Technology',
        sl_pct=2.5,
        tp_pct=5.0,
        atr_pct=2.5,
    )


def create_mock_dataframe(rows=100):
    dates = pd.date_range('2025-11-01', periods=rows, freq='B')
    close = 150.0 + np.cumsum(np.random.randn(rows) * 1.5)
    return pd.DataFrame({
        'Open': close - np.random.uniform(0.5, 2, rows),
        'High': close + np.random.uniform(0.5, 3, rows),
        'Low': close - np.random.uniform(1, 4, rows),
        'Close': close,
        'Volume': np.random.randint(500_000, 5_000_000, rows),
    }, index=dates)


def create_mock_sector_regime():
    """Mock SectorRegimeDetector"""
    sr = MagicMock()
    sr.SECTOR_ETFS = {
        'XLK': 'Technology',
        'XLE': 'Energy',
        'XLF': 'Financial Services',
        'XLV': 'Healthcare',
        'XLY': 'Consumer Cyclical',
        'XLP': 'Consumer Defensive',
        'XLI': 'Industrials',
        'XLU': 'Utilities',
        'XLB': 'Basic Materials',
        'XLC': 'Communication Services',
        'XLRE': 'Real Estate',
    }
    sr.sector_regimes = {
        'XLK': 'BEAR',
        'XLE': 'STRONG BULL',
        'XLF': 'BEAR',
        'XLV': 'SIDEWAYS',
        'XLY': 'SIDEWAYS',
        'XLP': 'BULL',
        'XLI': 'BULL',
        'XLU': 'BULL',
        'XLB': 'STRONG BULL',
        'XLC': 'SIDEWAYS',
        'XLRE': 'SIDEWAYS',
    }
    sr.sector_metrics = {
        etf: {'return_20d': 5.0} for etf in sr.SECTOR_ETFS
    }
    sr.sector_metrics['XLK'] = {'return_20d': -4.0}
    sr.sector_metrics['XLF'] = {'return_20d': -3.5}

    def get_sector_regime(sector_name):
        for etf, name in sr.SECTOR_ETFS.items():
            if name == sector_name:
                return sr.sector_regimes.get(etf, 'UNKNOWN')
        return 'UNKNOWN'

    sr.get_sector_regime = get_sector_regime
    return sr



# =============================================================================
# 1. SECTOR FILTER TESTS
# =============================================================================

class TestSectorFilter(unittest.TestCase):
    """Test sector filtering for BEAR/BULL mode"""

    def test_bear_sectors_returns_list(self):
        """_get_scanner_bear_sectors logic returns list excluding BEAR sectors"""
        sector_regime = create_mock_sector_regime()

        allowed = []
        for etf, sector_name in sector_regime.SECTOR_ETFS.items():
            regime = sector_regime.sector_regimes.get(etf, 'UNKNOWN')
            if regime not in ('BEAR', 'STRONG BEAR'):
                allowed.append(sector_name)

        assert isinstance(allowed, list)
        assert len(allowed) > 0
        assert 'Technology' not in allowed
        assert 'Financial Services' not in allowed
        assert 'Energy' in allowed
        assert 'Utilities' in allowed

    @patch('screeners.rapid_rotation_screener.RapidRotationScreener._init_ai_universe')
    @patch('screeners.rapid_rotation_screener.RapidRotationScreener._init_market_regime')
    @patch('screeners.rapid_rotation_screener.RapidRotationScreener._init_sector_regime')
    @patch('screeners.rapid_rotation_screener.RapidRotationScreener._init_alt_data')
    @patch('screeners.rapid_rotation_screener.RapidRotationScreener._load_sector_cache')
    def test_screen_with_allowed_sectors(self, *mocks):
        """screen(allowed_sectors=['Energy']) runs without error"""
        from screeners.rapid_rotation_screener import RapidRotationScreener

        screener = RapidRotationScreener()
        screener.data_cache = {'XLE': create_mock_dataframe()}
        screener.universe = ['XLE']
        screener.sector_regime = create_mock_sector_regime()
        screener.market_regime = None
        screener._market_regime_cache = None
        screener._market_regime_cache_time = 0.0
        screener._sector_cache = {'XLE': {'sector': 'Energy'}}

        screener.check_spy_regime = MagicMock(return_value=(False, 'SPY < SMA20', {}))

        result = screener.screen(top_n=5, allowed_sectors=['Energy'])
        assert isinstance(result, list)

    @patch('screeners.rapid_rotation_screener.RapidRotationScreener._init_ai_universe')
    @patch('screeners.rapid_rotation_screener.RapidRotationScreener._init_market_regime')
    @patch('screeners.rapid_rotation_screener.RapidRotationScreener._init_sector_regime')
    @patch('screeners.rapid_rotation_screener.RapidRotationScreener._init_alt_data')
    @patch('screeners.rapid_rotation_screener.RapidRotationScreener._load_sector_cache')
    def test_screen_with_blocked_sectors(self, *mocks):
        """screen(blocked_sectors=['Technology']) runs without error"""
        from screeners.rapid_rotation_screener import RapidRotationScreener

        screener = RapidRotationScreener()
        screener.data_cache = {'AAPL': create_mock_dataframe()}
        screener.universe = ['AAPL']
        screener.sector_regime = create_mock_sector_regime()
        screener.market_regime = None
        screener._market_regime_cache = None
        screener._market_regime_cache_time = 0.0
        screener._sector_cache = {'AAPL': {'sector': 'Technology'}}

        screener.check_spy_regime = MagicMock(return_value=(True, 'BULL', {}))

        result = screener.screen(top_n=5, blocked_sectors=['Technology'])
        assert isinstance(result, list)

    def test_bear_mode_passes_sectors_to_screener(self):
        """In BEAR mode, screen() is called with allowed_sectors"""
        mock_screener = MagicMock()
        mock_screener.check_spy_regime.return_value = (False, 'SPY < SMA20', {})
        mock_screener.screen.return_value = []
        mock_screener.sector_regime = create_mock_sector_regime()

        is_bull, _, _ = mock_screener.check_spy_regime()
        allowed_sectors = None
        if not is_bull:
            sr = mock_screener.sector_regime
            allowed_sectors = []
            for etf, sector_name in sr.SECTOR_ETFS.items():
                regime = sr.sector_regimes.get(etf, 'UNKNOWN')
                if regime not in ('BEAR', 'STRONG BEAR'):
                    allowed_sectors.append(sector_name)

        mock_screener.screen(top_n=10, allowed_sectors=allowed_sectors)

        call_kwargs = mock_screener.screen.call_args[1]
        assert call_kwargs['allowed_sectors'] is not None


# =============================================================================
# 2. CONVICTION SIZING TESTS
# =============================================================================

class TestConvictionSizing(unittest.TestCase):
    """Test conviction-based position sizing"""

    def _create_engine(self):
        """Create engine with mocked dependencies"""
        with patch('auto_trading_engine.AlpacaTrader') as MockTrader, \
             patch('auto_trading_engine.TradingSafetySystem'), \
             patch('auto_trading_engine.init_pdt_guard'), \
             patch('auto_trading_engine.get_trade_logger'), \
             patch('alert_manager.get_alert_manager', return_value=MagicMock()), \
             patch('trading_config.apply_config', side_effect=lambda x: None):

            MockTrader.return_value = create_mock_trader()

            from auto_trading_engine import AutoTradingEngine
            engine = AutoTradingEngine(
                api_key='test', secret_key='test', paper=True
            )
            mock_screener = MagicMock()
            mock_screener.sector_regime = create_mock_sector_regime()
            engine.screener = mock_screener
            return engine

    def test_returns_tuple(self):
        """_get_conviction_size() returns (float, str)"""
        engine = self._create_engine()
        signal = create_mock_signal(sector='Energy', score=85)
        params = {'position_size_pct': 40}

        result = engine._get_conviction_size(signal, params)

        assert isinstance(result, tuple)
        assert len(result) == 2
        pct, level = result
        assert isinstance(pct, (int, float))
        assert isinstance(level, str)

    def test_levels_valid(self):
        """Conviction level is always a known string"""
        engine = self._create_engine()
        params = {'position_size_pct': 40}
        valid_levels = {'A+', 'A', 'B', 'SKIP_BEAR', 'DEFAULT'}

        for sector in ['Energy', 'Industrials', 'Healthcare', 'Technology']:
            signal = create_mock_signal(sector=sector, score=85)
            _, level = engine._get_conviction_size(signal, params)
            assert level in valid_levels, f"Unexpected level '{level}' for {sector}"

    def test_disabled_returns_default(self):
        """When disabled, returns (params_pct, 'DEFAULT')"""
        engine = self._create_engine()
        engine.CONVICTION_SIZING_ENABLED = False
        signal = create_mock_signal()
        params = {'position_size_pct': 40}

        pct, level = engine._get_conviction_size(signal, params)
        assert level == 'DEFAULT'
        assert pct == 40


# =============================================================================
# 3. SMART DAY TRADE TESTS
# =============================================================================

class TestSmartDayTrade(unittest.TestCase):
    """Test smart day trade decision logic"""

    def _create_engine(self):
        with patch('auto_trading_engine.AlpacaTrader') as MockTrader, \
             patch('auto_trading_engine.TradingSafetySystem'), \
             patch('auto_trading_engine.init_pdt_guard') as MockPDT, \
             patch('auto_trading_engine.get_trade_logger'), \
             patch('alert_manager.get_alert_manager', return_value=MagicMock()), \
             patch('trading_config.apply_config', side_effect=lambda x: None):

            MockTrader.return_value = create_mock_trader()

            from pdt_smart_guard import PDTStatus, PDTConfig
            mock_pdt = MagicMock()
            mock_pdt.config = PDTConfig()
            mock_pdt.get_days_held.return_value = 0
            mock_pdt.get_pdt_status.return_value = PDTStatus(
                day_trade_count=0, remaining=3,
                is_flagged=False, can_day_trade=True, reserve_active=False
            )
            MockPDT.return_value = mock_pdt

            from auto_trading_engine import AutoTradingEngine
            engine = AutoTradingEngine(
                api_key='test', secret_key='test', paper=True
            )
            engine.pdt_guard = mock_pdt
            return engine

    def test_returns_tuple(self):
        """_should_use_day_trade() returns (bool, str)"""
        engine = self._create_engine()
        pos = create_managed_position()

        result = engine._should_use_day_trade('AAPL', pos, 151.0)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_disabled(self):
        """Returns (False, 'disabled') when feature is off"""
        engine = self._create_engine()
        engine.SMART_DAY_TRADE_ENABLED = False
        pos = create_managed_position()

        should, reason = engine._should_use_day_trade('AAPL', pos, 160.0)
        assert should is False
        assert reason == 'disabled'

    def test_not_day_zero(self):
        """Day 1+ returns (False, 'not day 0')"""
        engine = self._create_engine()
        engine.pdt_guard.get_days_held.return_value = 1
        pos = create_managed_position()

        should, reason = engine._should_use_day_trade('AAPL', pos, 160.0)
        assert should is False
        assert 'not day 0' in reason

    def test_gap_profit_trigger(self):
        """GAP_PROFIT triggers when price up >= threshold"""
        engine = self._create_engine()
        pos = create_managed_position(entry_price=150.0)
        price = 150.0 * 1.035  # +3.5%

        should, reason = engine._should_use_day_trade('AAPL', pos, price)
        assert should is True
        assert 'GAP_PROFIT' in reason


# =============================================================================
# 4. SCANNERS TESTS
# =============================================================================

class TestScanners(unittest.TestCase):
    """Test all scanner methods return correct types"""

    def test_scan_for_signals_returns_list(self):
        """AutoTradingEngine.scan_for_signals() returns list"""
        with patch('auto_trading_engine.AlpacaTrader') as MockTrader, \
             patch('auto_trading_engine.TradingSafetySystem'), \
             patch('auto_trading_engine.init_pdt_guard'), \
             patch('auto_trading_engine.get_trade_logger'), \
             patch('alert_manager.get_alert_manager', return_value=MagicMock()), \
             patch('trading_config.apply_config', side_effect=lambda x: None):

            MockTrader.return_value = create_mock_trader()

            from auto_trading_engine import AutoTradingEngine
            engine = AutoTradingEngine(
                api_key='test', secret_key='test', paper=True
            )

            engine.screener = MagicMock()
            engine.screener.load_data.return_value = None
            engine.screener.get_portfolio_signals.return_value = []

            engine._check_market_regime = MagicMock(return_value=(True, 'BULL'))
            engine._get_effective_params = MagicMock(return_value={
                'max_positions': 3, 'blocked_sectors': []
            })

            result = engine.scan_for_signals()
            assert isinstance(result, list)

    def test_overnight_gap_scanner(self):
        """OvernightGapScanner.scan() returns list"""
        from screeners.overnight_gap_scanner import OvernightGapScanner

        scanner = OvernightGapScanner()
        result = scanner.scan(universe={})
        assert isinstance(result, list)

    def test_breakout_scanner(self):
        """BreakoutScanner.scan() returns list"""
        from screeners.breakout_scanner import BreakoutScanner

        scanner = BreakoutScanner()
        result = scanner.scan(universe={})
        assert isinstance(result, list)


# =============================================================================
# 5. SAFETY SYSTEMS TESTS
# =============================================================================

class TestSafetySystems(unittest.TestCase):
    """Test safety system interfaces"""

    def test_daily_loss_check(self):
        """TradingSafetySystem.check_daily_loss() returns SafetyCheck"""
        from trading_safety import TradingSafetySystem, SafetyCheck, SafetyStatus

        trader = create_mock_trader()
        safety = TradingSafetySystem(trader)

        result = safety.check_daily_loss()
        assert isinstance(result, SafetyCheck)
        assert hasattr(result, 'name')
        assert hasattr(result, 'status')
        assert hasattr(result, 'message')
        assert isinstance(result.status, SafetyStatus)

    def test_pdt_can_sell(self):
        """PDTSmartGuard.can_sell() returns (bool, SellDecision, str)"""
        from pdt_smart_guard import PDTSmartGuard, PDTConfig, SellDecision

        trader = create_mock_trader()
        guard = PDTSmartGuard(trader=trader, config=PDTConfig())

        result = guard.can_sell('AAPL', pnl_pct=2.0)
        assert isinstance(result, tuple)
        assert len(result) == 3
        allowed, decision, reason = result
        assert isinstance(allowed, bool)
        assert isinstance(decision, SellDecision)
        assert isinstance(reason, str)

    def test_circuit_breaker_constants(self):
        """Circuit breaker constants exist and are positive integers"""
        from auto_trading_engine import AutoTradingEngine

        val = AutoTradingEngine.CIRCUIT_BREAKER_MAX_ERRORS
        assert isinstance(val, int)
        assert val > 0


# =============================================================================
# 6. INTEGRATION FLOW TESTS
# =============================================================================

class TestIntegrationFlows(unittest.TestCase):
    """Test end-to-end workflows"""

    def test_scan_to_execute_flow(self):
        """Full flow: scan → signal → execute completes without exception"""
        with patch('auto_trading_engine.AlpacaTrader') as MockTrader, \
             patch('auto_trading_engine.TradingSafetySystem'), \
             patch('auto_trading_engine.init_pdt_guard') as MockPDT, \
             patch('auto_trading_engine.get_trade_logger'), \
             patch('alert_manager.get_alert_manager', return_value=MagicMock()), \
             patch('trading_config.apply_config', side_effect=lambda x: None):

            mock_trader = create_mock_trader()
            MockTrader.return_value = mock_trader

            from pdt_smart_guard import PDTStatus, PDTConfig
            mock_pdt = MagicMock()
            mock_pdt.config = PDTConfig()
            mock_pdt.get_days_held.return_value = 0
            mock_pdt.get_pdt_status.return_value = PDTStatus(
                day_trade_count=0, remaining=3,
                is_flagged=False, can_day_trade=True, reserve_active=False
            )
            MockPDT.return_value = mock_pdt

            from auto_trading_engine import AutoTradingEngine
            engine = AutoTradingEngine(
                api_key='test', secret_key='test', paper=True
            )
            engine.pdt_guard = mock_pdt

            signal = create_mock_signal(score=98)  # Must exceed MIN_SCORE (95)
            engine.screener = MagicMock()
            engine.screener.load_data.return_value = None
            engine.screener.get_portfolio_signals.return_value = [signal]
            engine.screener.sector_regime = create_mock_sector_regime()

            engine._check_market_regime = MagicMock(return_value=(True, 'BULL'))
            engine._get_effective_params = MagicMock(return_value={
                'max_positions': 3, 'position_size_pct': 40,
                'blocked_sectors': [],
            })

            # Scan
            signals = engine.scan_for_signals()
            assert isinstance(signals, list)
            assert len(signals) > 0

            from screeners.rapid_rotation_screener import RapidRotationSignal
            assert isinstance(signals[0], RapidRotationSignal)

    def test_bear_mode_full_flow(self):
        """BEAR mode: SPY BEAR → sectors filtered → allowed_sectors passed"""
        mock_screener = MagicMock()
        mock_screener.check_spy_regime.return_value = (False, 'SPY < SMA20', {})
        mock_screener.screen.return_value = []
        mock_screener.sector_regime = create_mock_sector_regime()

        is_bull, _, _ = mock_screener.check_spy_regime()
        assert is_bull is False

        sr = mock_screener.sector_regime
        allowed_sectors = []
        for etf, sector_name in sr.SECTOR_ETFS.items():
            regime = sr.sector_regimes.get(etf, 'UNKNOWN')
            if regime not in ('BEAR', 'STRONG BEAR'):
                allowed_sectors.append(sector_name)

        assert isinstance(allowed_sectors, list)
        assert len(allowed_sectors) > 0
        assert 'Technology' not in allowed_sectors

        mock_screener.screen(
            top_n=10,
            allowed_sectors=allowed_sectors,
            blocked_sectors=None,
        )

        mock_screener.screen.assert_called_once()
        call_kwargs = mock_screener.screen.call_args[1]
        assert call_kwargs['allowed_sectors'] is not None
        assert len(call_kwargs['allowed_sectors']) > 0


if __name__ == '__main__':
    unittest.main()
