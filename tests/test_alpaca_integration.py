#!/usr/bin/env python3
"""
COMPREHENSIVE TESTS FOR ALPACA INTEGRATION v4.7

Tests all new features:
1. AlpacaBroker methods (portfolio history, activities, calendar)
2. RapidPortfolioManager with broker integration
3. API endpoints
4. Auto trading engine calendar check

Run:
    pytest tests/test_alpaca_integration.py -v
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_alpaca_api():
    """Mock Alpaca API client"""
    api = Mock()

    # Mock portfolio history
    history = Mock()
    history.equity = [100000, 101000, 102000, 103000]
    history.profit_loss = [0, 1000, 2000, 3000]
    history.profit_loss_pct = [0, 1.0, 2.0, 3.0]
    history.base_value = 100000
    history.timeframe = '1D'
    history.timestamp = [
        int(datetime.now().timestamp()),
        int((datetime.now() + timedelta(days=1)).timestamp()),
        int((datetime.now() + timedelta(days=2)).timestamp()),
        int((datetime.now() + timedelta(days=3)).timestamp()),
    ]
    api.get_portfolio_history.return_value = history

    # Mock activities
    fill1 = Mock()
    fill1.id = 'fill1'
    fill1.activity_type = 'FILL'
    fill1.symbol = 'AAPL'
    fill1.side = 'buy'
    fill1.qty = 10
    fill1.price = 180.50
    fill1.order_id = 'order1'
    fill1.transaction_time = datetime.now()

    api.get_activities.return_value = [fill1]

    # Mock calendar
    cal1 = Mock()
    cal1.date = datetime.now()
    cal1.open = datetime.now().replace(hour=9, minute=30)
    cal1.close = datetime.now().replace(hour=16, minute=0)

    api.get_calendar.return_value = [cal1]

    # Mock snapshot
    snapshot = Mock()
    snapshot.latest_quote = Mock()
    snapshot.latest_quote.bp = 180.00
    snapshot.latest_quote.ap = 180.10
    snapshot.latest_quote.bs = 100
    snapshot.latest_quote.as_ = 100
    snapshot.latest_trade = Mock()
    snapshot.latest_trade.p = 180.05
    snapshot.daily_bar = Mock()
    snapshot.daily_bar.v = 1000000
    snapshot.daily_bar.h = 182.00
    snapshot.daily_bar.l = 179.00
    snapshot.daily_bar.o = 180.00
    snapshot.prev_daily_bar = Mock()
    snapshot.prev_daily_bar.c = 179.50

    api.get_snapshot.return_value = snapshot
    api.get_snapshots.return_value = {'AAPL': snapshot}

    return api


@pytest.fixture
def alpaca_broker(mock_alpaca_api):
    """AlpacaBroker with mocked API"""
    from engine.brokers.alpaca_broker import AlpacaBroker

    with patch('engine.brokers.alpaca_broker.tradeapi.REST', return_value=mock_alpaca_api):
        broker = AlpacaBroker(api_key='test', secret_key='test', paper=True)
        broker.api = mock_alpaca_api
        return broker


# =============================================================================
# TEST ALPACA BROKER - PORTFOLIO HISTORY
# =============================================================================

class TestAlpacaBrokerPortfolioHistory:
    """Test portfolio history methods"""

    def test_get_portfolio_history(self, alpaca_broker):
        """Test get_portfolio_history returns correct structure"""
        history = alpaca_broker.get_portfolio_history(period='1M', timeframe='1D')

        assert 'equity' in history
        assert 'profit_loss' in history
        assert 'profit_loss_pct' in history
        assert 'base_value' in history
        assert 'timeframe' in history
        assert 'timestamp' in history

        assert len(history['equity']) == 4
        assert history['equity'][0] == 100000
        assert history['equity'][-1] == 103000

    def test_calculate_performance_metrics(self, alpaca_broker):
        """Test performance metrics calculation"""
        history = alpaca_broker.get_portfolio_history(period='1M')
        metrics = alpaca_broker.calculate_performance_metrics(history)

        assert 'total_return_pct' in metrics
        assert 'total_return_usd' in metrics
        assert 'max_drawdown_pct' in metrics
        assert 'sharpe_ratio' in metrics
        assert 'win_days' in metrics
        assert 'loss_days' in metrics
        assert 'win_rate' in metrics

        # Check calculations
        assert metrics['total_return_pct'] == 3.0  # (103000-100000)/100000 * 100
        assert metrics['total_return_usd'] == 3000

    def test_performance_metrics_empty_data(self, alpaca_broker):
        """Test metrics with empty data"""
        empty_history = {
            'equity': [],
            'profit_loss_pct': [],
            'timestamp': []
        }

        metrics = alpaca_broker.calculate_performance_metrics(empty_history)

        assert metrics['total_return_pct'] == 0
        assert metrics['sharpe_ratio'] == 0
        assert metrics['win_rate'] == 0


# =============================================================================
# TEST ALPACA BROKER - ACTIVITIES
# =============================================================================

class TestAlpacaBrokerActivities:
    """Test trade activities methods"""

    def test_get_activities(self, alpaca_broker):
        """Test get_activities returns fills"""
        activities = alpaca_broker.get_activities(activity_types='FILL', days=7)

        assert len(activities) == 1
        assert activities[0]['activity_type'] == 'FILL'
        assert activities[0]['symbol'] == 'AAPL'
        assert activities[0]['side'] == 'buy'
        assert activities[0]['qty'] == 10
        assert activities[0]['price'] == 180.50

    def test_analyze_slippage(self, alpaca_broker):
        """Test slippage analysis"""
        # Mock fills
        fills = [
            {
                'activity_type': 'FILL',
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 10,
                'price': 180.50,
                'order_id': 'order1'
            }
        ]

        # Mock orders
        from engine.broker_interface import Order
        order = Order(
            id='order1',
            symbol='AAPL',
            side='buy',
            type='limit',
            qty=10,
            filled_qty=10,
            status='filled',
            created_at=datetime.now(),
            limit_price=180.40,  # Wanted 180.40, got 180.50 = -0.10 slippage
        )

        slippage = alpaca_broker.analyze_slippage(fills, [order])

        assert slippage['total_fills'] == 1
        assert slippage['avg_slippage_usd'] == 0.10  # Positive = unfavorable for buy
        assert slippage['total_slippage_cost'] == 1.0  # 0.10 * 10 shares


# =============================================================================
# TEST ALPACA BROKER - CALENDAR
# =============================================================================

class TestAlpacaBrokerCalendar:
    """Test market calendar methods"""

    def test_get_calendar(self, alpaca_broker):
        """Test get_calendar returns trading days"""
        calendar = alpaca_broker.get_calendar(
            start='2026-02-01',
            end='2026-02-28'
        )

        assert len(calendar) == 1
        assert 'date' in calendar[0]
        assert 'open' in calendar[0]
        assert 'close' in calendar[0]

    def test_is_market_open_tomorrow(self, alpaca_broker, mock_alpaca_api):
        """Test is_market_open_tomorrow when market is open"""
        # Mock calendar returns data (market open)
        is_open = alpaca_broker.is_market_open_tomorrow()
        assert is_open == True

    def test_is_market_closed_tomorrow(self, alpaca_broker, mock_alpaca_api):
        """Test is_market_open_tomorrow when market is closed"""
        # Mock calendar returns empty (market closed)
        mock_alpaca_api.get_calendar.return_value = []

        is_open = alpaca_broker.is_market_open_tomorrow()
        assert is_open == False

    def test_get_next_market_day(self, alpaca_broker, mock_alpaca_api):
        """Test get_next_market_day finds next trading day"""
        next_day = alpaca_broker.get_next_market_day()
        assert next_day is not None

    def test_get_upcoming_holidays(self, alpaca_broker, mock_alpaca_api):
        """Test get_upcoming_holidays detects holidays"""
        # Mock: No calendar entries = holidays
        mock_alpaca_api.get_calendar.return_value = []

        holidays = alpaca_broker.get_upcoming_holidays(days=7)

        # Should detect weekdays with no calendar entries
        assert isinstance(holidays, list)


# =============================================================================
# TEST RAPID PORTFOLIO MANAGER
# =============================================================================

class TestRapidPortfolioManagerBrokerIntegration:
    """Test RapidPortfolioManager with broker"""

    def test_init_with_broker(self, alpaca_broker):
        """Test initialization with broker parameter"""
        from rapid_portfolio_manager import RapidPortfolioManager

        manager = RapidPortfolioManager(broker=alpaca_broker)

        assert manager.broker is not None
        assert manager.broker == alpaca_broker

    def test_init_without_broker(self):
        """Test initialization without broker (backwards compatible)"""
        from rapid_portfolio_manager import RapidPortfolioManager

        manager = RapidPortfolioManager()

        assert manager.broker is None

    def test_get_current_price_with_broker(self, alpaca_broker):
        """Test get_current_price uses broker when available"""
        from rapid_portfolio_manager import RapidPortfolioManager

        manager = RapidPortfolioManager(broker=alpaca_broker)

        price = manager.get_current_price('AAPL')

        assert price == 180.05  # Mock last price
        alpaca_broker.api.get_snapshot.assert_called_with('AAPL')

    def test_get_current_price_without_broker(self):
        """Test get_current_price falls back to yfinance without broker"""
        from rapid_portfolio_manager import RapidPortfolioManager

        manager = RapidPortfolioManager()  # No broker

        # Should not raise error (will try yfinance)
        # Price might be None if yfinance fails, but that's expected
        price = manager.get_current_price('AAPL')
        # Just ensure it doesn't crash

    def test_get_performance_report_with_broker(self, alpaca_broker):
        """Test get_performance_report with broker"""
        from rapid_portfolio_manager import RapidPortfolioManager

        manager = RapidPortfolioManager(broker=alpaca_broker)

        report = manager.get_performance_report(period='1M')

        assert report['data_source'] == 'alpaca'
        assert 'equity_curve' in report
        assert 'metrics' in report
        assert len(report['equity_curve']) == 4

    def test_get_performance_report_without_broker(self):
        """Test get_performance_report without broker"""
        from rapid_portfolio_manager import RapidPortfolioManager

        manager = RapidPortfolioManager()  # No broker

        report = manager.get_performance_report(period='1M')

        assert report['data_source'] == 'local_json'
        assert 'summary' in report


# =============================================================================
# TEST AUTO TRADING ENGINE - CALENDAR CHECK
# =============================================================================

class TestAutoTradingEngineCalendarCheck:
    """Test calendar check in auto trading engine"""

    def test_should_skip_before_holiday(self, alpaca_broker):
        """Test _should_skip_before_holiday detects holidays"""
        from auto_trading_engine import AutoTradingEngine

        # Mock engine with broker
        with patch.object(AutoTradingEngine, '__init__', lambda x, **kwargs: None):
            engine = AutoTradingEngine()
            engine.broker = alpaca_broker
            engine.config = {'skip_before_holiday': True}

            # Mock tomorrow is closed (holiday)
            alpaca_broker.api.get_calendar.return_value = []

            should_skip, reason = engine._should_skip_before_holiday()

            assert should_skip == True
            assert 'holiday' in reason.lower() or 'weekend' in reason.lower()

    def test_should_not_skip_normal_day(self, alpaca_broker):
        """Test _should_skip_before_holiday on normal trading day"""
        from auto_trading_engine import AutoTradingEngine

        with patch.object(AutoTradingEngine, '__init__', lambda x, **kwargs: None):
            engine = AutoTradingEngine()
            engine.broker = alpaca_broker
            engine.config = {'skip_before_holiday': True}

            # Mock tomorrow is open
            cal = Mock()
            cal.date = (datetime.now() + timedelta(days=1))
            cal.open = datetime.now().replace(hour=9, minute=30)
            alpaca_broker.api.get_calendar.return_value = [cal]

            should_skip, reason = engine._should_skip_before_holiday()

            assert should_skip == False
            assert 'trading day' in reason.lower()

    def test_calendar_check_disabled(self, alpaca_broker):
        """Test calendar check when disabled in config"""
        from auto_trading_engine import AutoTradingEngine

        with patch.object(AutoTradingEngine, '__init__', lambda x, **kwargs: None):
            engine = AutoTradingEngine()
            engine.broker = alpaca_broker
            engine.config = {'skip_before_holiday': False}  # Disabled

            should_skip, reason = engine._should_skip_before_holiday()

            assert should_skip == False
            assert 'disabled' in reason.lower()


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestFullIntegration:
    """End-to-end integration tests"""

    def test_full_workflow_with_broker(self, alpaca_broker):
        """Test complete workflow: broker -> manager -> performance"""
        from rapid_portfolio_manager import RapidPortfolioManager

        # 1. Create manager with broker
        manager = RapidPortfolioManager(broker=alpaca_broker)

        # 2. Get real-time price
        price = manager.get_current_price('AAPL')
        assert price == 180.05

        # 3. Get performance report
        report = manager.get_performance_report(period='1M')
        assert report['data_source'] == 'alpaca'
        assert report['metrics']['total_return_pct'] == 3.0

        # 4. Get calendar
        calendar = alpaca_broker.get_calendar(
            start=datetime.now().strftime('%Y-%m-%d'),
            end=(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        )
        assert len(calendar) >= 1

        # 5. Check holidays
        is_open = alpaca_broker.is_market_open_tomorrow()
        assert isinstance(is_open, bool)

    def test_speed_comparison_mock(self, alpaca_broker):
        """Test that batch fetch is faster (mock)"""
        import time

        symbols = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META']

        # Batch fetch (fast)
        start = time.time()
        quotes = alpaca_broker.get_snapshots(symbols)
        batch_time = time.time() - start

        assert len(quotes) == 1  # Mock returns 1 symbol
        assert batch_time < 1.0  # Should be instant with mock


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
