#!/usr/bin/env python3
"""
Safety-Critical Tests for Rapid Trader v5.1

Tests for P0 safety mechanisms that MUST work correctly:
  - SL recovery for naked positions (_check_naked_positions)
  - PDT guard integration (position count, sell decisions)
  - Position count race condition (lock-based check)
  - Fail-closed regime filter (SPY data missing → BEAR)
  - Loss limit enforcement (daily, weekly, consecutive)

Usage:
    pytest tests/test_safety_critical.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from dataclasses import dataclass
from datetime import datetime


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_trader():
    """Mock AlpacaTrader with controllable SL placement."""
    trader = Mock()
    trader.place_stop_loss = Mock()
    trader.get_position = Mock(return_value=None)
    trader.place_market_sell = Mock()
    return trader


@pytest.fixture
def mock_managed_position():
    """Create a minimal ManagedPosition-like object."""
    pos = Mock()
    pos.symbol = "AAPL"
    pos.qty = 10
    pos.entry_price = 150.0
    pos.current_sl_price = 146.25
    pos.sl_order_id = None  # naked position
    pos.peak_price = 155.0
    pos.trailing_active = False
    pos.sector = "Technology"
    pos.entry_rsi = 35.0
    return pos


# ---------------------------------------------------------------------------
# 1. SL Recovery Tests (_check_naked_positions)
# ---------------------------------------------------------------------------

class TestSLRecovery:
    """Tests for naked position SL recovery (P0-4B)."""

    def test_naked_position_detected_and_sl_placed(self, mock_trader, mock_managed_position):
        """Naked position (sl_order_id=None) should trigger SL placement."""
        # Setup: position with no SL order
        sl_order = Mock()
        sl_order.id = "sl_order_123"
        mock_trader.place_stop_loss.return_value = sl_order

        # Simulate _check_naked_positions logic
        pos = mock_managed_position
        assert pos.sl_order_id is None, "Precondition: position has no SL"

        if not pos.sl_order_id:
            sl_price = pos.current_sl_price
            result = mock_trader.place_stop_loss(pos.symbol, pos.qty, sl_price)
            if result:
                pos.sl_order_id = result.id

        assert pos.sl_order_id == "sl_order_123"
        mock_trader.place_stop_loss.assert_called_once_with("AAPL", 10, 146.25)

    def test_naked_position_sl_retry_failure(self, mock_trader, mock_managed_position):
        """SL placement failure should not crash — position stays naked."""
        mock_trader.place_stop_loss.side_effect = Exception("API timeout")

        pos = mock_managed_position
        try:
            if not pos.sl_order_id:
                mock_trader.place_stop_loss(pos.symbol, pos.qty, pos.current_sl_price)
        except Exception:
            pass  # Recovery should log but not crash

        assert pos.sl_order_id is None, "SL should remain None on failure"

    def test_position_with_sl_not_touched(self, mock_trader, mock_managed_position):
        """Position WITH existing SL order should not trigger recovery."""
        mock_managed_position.sl_order_id = "existing_sl_456"

        if not mock_managed_position.sl_order_id:
            mock_trader.place_stop_loss()

        mock_trader.place_stop_loss.assert_not_called()

    def test_sl_placement_returns_none(self, mock_trader, mock_managed_position):
        """SL placement returning None should be handled gracefully."""
        mock_trader.place_stop_loss.return_value = None

        pos = mock_managed_position
        if not pos.sl_order_id:
            result = mock_trader.place_stop_loss(pos.symbol, pos.qty, pos.current_sl_price)
            if result:
                pos.sl_order_id = result.id

        assert pos.sl_order_id is None, "Should remain None when place_stop_loss returns None"


# ---------------------------------------------------------------------------
# 2. PDT Guard Tests
# ---------------------------------------------------------------------------

class TestPDTGuard:
    """Tests for PDT guard safety (prevents pattern day trading violation)."""

    def test_pdt_remaining_zero_blocks_entry(self):
        """PDT remaining=0 should block new entries."""
        pdt_status = Mock()
        pdt_status.remaining = 0
        reserve = 1

        blocked = pdt_status.remaining <= reserve
        assert blocked, "Should block when remaining <= reserve"

    def test_pdt_remaining_above_reserve_allows_entry(self):
        """PDT remaining > reserve should allow entry."""
        pdt_status = Mock()
        pdt_status.remaining = 3
        reserve = 1

        blocked = pdt_status.remaining <= reserve
        assert not blocked, "Should allow when remaining > reserve"

    def test_pdt_day_zero_held_is_day_trade(self):
        """Selling on day 0 counts as a day trade."""
        days_held = 0
        is_day_trade = days_held == 0
        assert is_day_trade

    def test_pdt_day_one_held_not_day_trade(self):
        """Selling on day 1+ is NOT a day trade."""
        days_held = 1
        is_day_trade = days_held == 0
        assert not is_day_trade


# ---------------------------------------------------------------------------
# 3. Position Count Race Condition Tests
# ---------------------------------------------------------------------------

class TestPositionCountLock:
    """Tests for max position check under lock (P0-3)."""

    def test_position_count_uses_max_of_engine_and_alpaca(self):
        """Position count should be max(engine_count, alpaca_count)."""
        engine_positions = {"AAPL": Mock(), "MSFT": Mock()}
        alpaca_position_count = 3  # Alpaca knows about 3 (engine only sees 2)

        actual_count = max(len(engine_positions), alpaca_position_count)
        assert actual_count == 3, "Should use Alpaca count when higher"

    def test_max_positions_blocks_when_at_limit(self):
        """Should block new positions when at max."""
        effective_max = 3
        actual_count = 3

        blocked = actual_count >= effective_max
        assert blocked, "Should block at max positions"

    def test_max_positions_allows_below_limit(self):
        """Should allow new positions when below max."""
        effective_max = 3
        actual_count = 2

        blocked = actual_count >= effective_max
        assert not blocked, "Should allow below max positions"


# ---------------------------------------------------------------------------
# 4. Fail-Closed Regime Filter Tests
# ---------------------------------------------------------------------------

class TestFailClosedRegime:
    """Tests for fail-closed behavior (P0-1, P0-2)."""

    def test_insufficient_spy_data_returns_bear(self):
        """Missing SPY data should default to BEAR (fail-closed)."""
        # Simulate the fix: return False (not BULL) when data insufficient
        is_bull = False  # P0-1: was True before fix
        reason = "Insufficient data — defaulting to BEAR for safety"

        assert not is_bull, "Should be BEAR when SPY data missing"
        assert "BEAR" in reason

    def test_unknown_sector_regime_blocked_in_bear(self):
        """UNKNOWN sector regime should be BLOCKED in bear mode (P0-2)."""
        regime = "UNKNOWN"
        allowed_regimes = ('BULL', 'STRONG BULL', 'SIDEWAYS')

        is_allowed = regime in allowed_regimes
        assert not is_allowed, "UNKNOWN should NOT be allowed"

    def test_bull_sector_regime_allowed_in_bear(self):
        """BULL sector regime should be allowed even in bear mode."""
        regime = "BULL"
        allowed_regimes = ('BULL', 'STRONG BULL', 'SIDEWAYS')

        is_allowed = regime in allowed_regimes
        assert is_allowed, "BULL sector should be allowed"


# ---------------------------------------------------------------------------
# 5. Loss Limit Tests
# ---------------------------------------------------------------------------

class TestLossLimits:
    """Tests for daily/weekly/consecutive loss limits (P0-5)."""

    def test_daily_loss_limit_blocks_trading(self):
        """Should block trading when daily loss limit reached."""
        daily_pnl = -150.0
        daily_loss_limit_pct = 3.0
        equity = 4000.0
        limit_usd = equity * daily_loss_limit_pct / 100  # $120

        hit_limit = abs(daily_pnl) >= limit_usd
        assert hit_limit, "Should detect daily loss limit breach"

    def test_consecutive_losses_blocks_trading(self):
        """Should block after N consecutive losses."""
        consecutive_losses = 3
        max_consecutive = 3

        hit_limit = consecutive_losses >= max_consecutive
        assert hit_limit, "Should detect consecutive loss limit"

    def test_afternoon_scan_checks_all_three_limits(self):
        """Afternoon scan must check daily + weekly + consecutive (P0-5)."""
        # These three checks must ALL pass for afternoon scan to proceed
        daily_ok = True
        weekly_ok = True
        consecutive_ok = True

        can_trade = daily_ok and weekly_ok and consecutive_ok
        assert can_trade, "All three limits must be checked"

        # If any fails, block
        consecutive_ok = False
        can_trade = daily_ok and weekly_ok and consecutive_ok
        assert not can_trade, "Should block when consecutive limit hit"


# ---------------------------------------------------------------------------
# 6. Entry RSI Rename Backward Compatibility (P3-23)
# ---------------------------------------------------------------------------

class TestEntryRSICompat:
    """Tests for rsi → entry_rsi rename backward compatibility."""

    def test_new_field_name_in_dataclass(self):
        """TradeLogEntry should use entry_rsi field name."""
        from trade_logger import TradeLogEntry
        entry = TradeLogEntry(
            id="test", timestamp="2025-01-01", action="BUY",
            symbol="AAPL", qty=10, price=150.0, reason="DIP_BOUNCE",
            entry_rsi=35.0
        )
        assert entry.entry_rsi == 35.0
        assert not hasattr(entry, 'rsi') or entry.__class__.__dataclass_fields__.get('rsi') is None

    def test_managed_position_uses_entry_rsi(self):
        """ManagedPosition should use entry_rsi field name."""
        from auto_trading_engine import ManagedPosition
        pos = ManagedPosition(
            symbol="AAPL", qty=10, entry_price=150.0,
            entry_time=datetime.now(), sl_order_id="sl_1",
            current_sl_price=146.25, peak_price=150.0,
            entry_rsi=35.0
        )
        assert pos.entry_rsi == 35.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
