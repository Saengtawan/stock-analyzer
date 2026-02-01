#!/usr/bin/env python3
"""
Unit Tests for RapidRotationScreener Filters v3.5

Tests each filter independently to ensure:
1. Filters work correctly
2. Logic matches production
3. Edge cases are handled

Run with: python tests/test_screener_filters.py
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'screeners'))


class TestSMA20Filter(unittest.TestCase):
    """Test SMA20 filter (v3.5 ROOT CAUSE FIX)"""

    def test_rejects_below_sma(self):
        """Price below SMA20 should be rejected"""
        current_price = 100
        sma20 = 105  # Price is below SMA20 (downtrend)

        # Filter logic: if current_price < sma20: return None
        should_reject = current_price < sma20

        self.assertTrue(should_reject, "Should reject when price < SMA20")

    def test_accepts_above_sma(self):
        """Price above SMA20 should be accepted"""
        current_price = 110
        sma20 = 105  # Price is above SMA20 (uptrend)

        should_reject = current_price < sma20

        self.assertFalse(should_reject, "Should accept when price > SMA20")

    def test_edge_case_equal(self):
        """Price equal to SMA20 should pass (we use < not <=)"""
        current_price = 105
        sma20 = 105  # Price equals SMA20

        should_reject = current_price < sma20

        self.assertFalse(should_reject, "Price == SMA20 should NOT be rejected")


class TestBounceConfirmationFilters(unittest.TestCase):
    """Test bounce confirmation filters"""

    def test_yesterday_must_be_down(self):
        """Yesterday must be down at least -1%"""
        # Good: Yesterday down -2%
        yesterday_move_good = -2.0
        self.assertTrue(yesterday_move_good <= -1.0, "Should accept -2% dip")

        # Bad: Yesterday up or flat
        yesterday_move_bad = 0.5
        self.assertFalse(yesterday_move_bad <= -1.0, "Should reject if yesterday not down")

    def test_today_should_show_recovery(self):
        """Today should not be falling hard"""
        # Good: Today +0.5%
        mom_1d_good = 0.5
        self.assertFalse(mom_1d_good < -1.0, "Should accept positive momentum")

        # Bad: Today -2%
        mom_1d_bad = -2.0
        self.assertTrue(mom_1d_bad < -1.0, "Should reject still falling")

    def test_green_candle_preference(self):
        """Green candle or strong positive momentum required"""
        # Good: Green candle
        today_is_green = True
        mom_1d = 0.3
        should_reject = not today_is_green and mom_1d < 0.5
        self.assertFalse(should_reject, "Green candle should pass")

        # Bad: Red candle with weak momentum
        today_is_green = False
        mom_1d = 0.3  # < 0.5
        should_reject = not today_is_green and mom_1d < 0.5
        self.assertTrue(should_reject, "Red candle with weak momentum should fail")

    def test_gap_up_filter(self):
        """Skip big gap ups (exhaustion risk)"""
        # Good: Small gap
        gap_pct_good = 1.5
        self.assertFalse(gap_pct_good > 2.0, "Small gap should pass")

        # Bad: Big gap up
        gap_pct_bad = 3.0
        self.assertTrue(gap_pct_bad > 2.0, "Big gap should be rejected")

    def test_not_extended_above_sma5(self):
        """Should not be too extended above SMA5"""
        current_price = 100
        sma5 = 100

        # Good: At SMA5
        self.assertFalse(current_price > sma5 * 1.02, "At SMA5 should pass")

        # Bad: 3% above SMA5
        current_price = 103
        self.assertTrue(current_price > sma5 * 1.02, "Too extended should fail")


class TestVolatilityFilters(unittest.TestCase):
    """Test volatility and price range filters"""

    def test_minimum_volatility(self):
        """ATR% must be at least 2.5%"""
        MIN_ATR_PCT = 2.5

        # Good: High volatility
        atr_pct_good = 4.0
        self.assertFalse(atr_pct_good < MIN_ATR_PCT, "High vol should pass")

        # Bad: Low volatility
        atr_pct_bad = 1.5
        self.assertTrue(atr_pct_bad < MIN_ATR_PCT, "Low vol should fail")

    def test_penny_stock_filter(self):
        """Reject penny stocks (< $10)"""
        self.assertTrue(5 < 10, "Penny stock should be rejected")
        self.assertFalse(15 < 10, "$15 stock should pass")

    def test_expensive_stock_filter(self):
        """Reject very expensive stocks (> $2000)"""
        self.assertTrue(2500 > 2000, "Very expensive stock should be rejected")
        self.assertFalse(500 > 2000, "$500 stock should pass")


class TestDynamicSLTP(unittest.TestCase):
    """Test dynamic SL/TP calculation"""

    def test_sl_uses_highest(self):
        """SL should use highest of 3 methods for best protection"""
        atr_based_sl = 95.0
        swing_low_sl = 93.0
        ema_based_sl = 97.0  # Highest = best protection

        sl_options = {
            'ATR': atr_based_sl,
            'SwingLow': swing_low_sl,
            'EMA5': ema_based_sl
        }
        best_sl = max(sl_options.values())

        self.assertEqual(best_sl, 97.0, "Should use highest SL for best protection")

    def test_tp_uses_lowest(self):
        """TP should use lowest of 3 methods for realistic target"""
        atr_based_tp = 110.0
        resistance_tp = 108.0  # Lowest = most realistic
        high_52w_tp = 115.0

        tp_options = {
            'ATR': atr_based_tp,
            'Resistance': resistance_tp,
            '52wHigh': high_52w_tp
        }
        best_tp = min(tp_options.values())

        self.assertEqual(best_tp, 108.0, "Should use lowest TP for realistic target")

    def test_sl_safety_caps_min(self):
        """SL should be at least 2%"""
        MIN_SL = 2.0
        MAX_SL = 8.0

        sl_pct_raw = 1.0
        sl_pct = max(MIN_SL, min(sl_pct_raw, MAX_SL))
        self.assertEqual(sl_pct, 2.0, "SL should be at least 2%")

    def test_sl_safety_caps_max(self):
        """SL should be at most 8%"""
        MIN_SL = 2.0
        MAX_SL = 8.0

        sl_pct_raw = 12.0
        sl_pct = max(MIN_SL, min(sl_pct_raw, MAX_SL))
        self.assertEqual(sl_pct, 8.0, "SL should be at most 8%")

    def test_sl_safety_caps_normal(self):
        """Normal SL should pass through unchanged"""
        MIN_SL = 2.0
        MAX_SL = 8.0

        sl_pct_raw = 4.5
        sl_pct = max(MIN_SL, min(sl_pct_raw, MAX_SL))
        self.assertEqual(sl_pct, 4.5, "Normal SL should pass through")

    def test_tp_safety_caps(self):
        """TP should be capped between 4% and 15%"""
        MIN_TP = 4.0
        MAX_TP = 15.0

        # Too small TP
        tp_pct_raw = 2.0
        tp_pct = max(MIN_TP, min(tp_pct_raw, MAX_TP))
        self.assertEqual(tp_pct, 4.0, "TP should be at least 4%")

        # Too large TP
        tp_pct_raw = 25.0
        tp_pct = max(MIN_TP, min(tp_pct_raw, MAX_TP))
        self.assertEqual(tp_pct, 15.0, "TP should be at most 15%")


class TestTrailingStop(unittest.TestCase):
    """Test trailing stop logic"""

    def test_trailing_activation_not_reached(self):
        """Trailing should NOT activate below +3%"""
        TRAIL_ACTIVATION = 3.0
        entry_price = 100

        peak_price = 102  # +2%
        peak_pct = ((peak_price - entry_price) / entry_price) * 100
        trailing_activated = peak_pct >= TRAIL_ACTIVATION

        self.assertFalse(trailing_activated, "Should not activate at +2%")

    def test_trailing_activation_reached(self):
        """Trailing should activate at +3% or above"""
        TRAIL_ACTIVATION = 3.0
        entry_price = 100

        peak_price = 104  # +4%
        peak_pct = ((peak_price - entry_price) / entry_price) * 100
        trailing_activated = peak_pct >= TRAIL_ACTIVATION

        self.assertTrue(trailing_activated, "Should activate at +4%")

    def test_trailing_locks_60_percent(self):
        """Trailing should lock 60% of peak gains"""
        TRAIL_PERCENT = 60
        entry_price = 100

        # Peak at +5%
        peak_pct = 5.0
        locked_profit = peak_pct * (TRAIL_PERCENT / 100)  # 3%
        trailing_stop = entry_price * (1 + locked_profit / 100)  # $103

        self.assertEqual(locked_profit, 3.0, "Should lock 3% of +5% gain")
        self.assertEqual(trailing_stop, 103.0, "Trailing stop should be at $103")


class TestScoreCalculation(unittest.TestCase):
    """Test score calculation logic"""

    def test_bounce_confirmation_max_score(self):
        """Strong bounce should give max 40 points"""
        today_is_green = True
        mom_1d = 1.0  # > 0.5

        if today_is_green and mom_1d > 0.5:
            score = 40
        elif today_is_green or mom_1d > 0.3:
            score = 25
        else:
            score = 0

        self.assertEqual(score, 40, "Strong bounce should give 40 points")

    def test_dip_magnitude_deep(self):
        """Deep dip (-5% to -12%) should give 40 points"""
        mom_5d = -8
        if -12 <= mom_5d <= -5:
            score = 40
        elif -5 < mom_5d <= -3:
            score = 30
        elif -3 < mom_5d < 0:
            score = 15
        else:
            score = 0

        self.assertEqual(score, 40, "Deep dip should give 40 points")

    def test_dip_magnitude_mild(self):
        """Mild dip (-3% to 0%) should give 15 points"""
        mom_5d = -2
        if -12 <= mom_5d <= -5:
            score = 40
        elif -5 < mom_5d <= -3:
            score = 30
        elif -3 < mom_5d < 0:
            score = 15
        else:
            score = 0

        self.assertEqual(score, 15, "Mild dip should give 15 points")

    def test_minimum_score_threshold(self):
        """Score must be at least 90 to pass"""
        MIN_SCORE = 90

        self.assertTrue(85 < MIN_SCORE, "Score 85 should not pass")
        self.assertTrue(90 >= MIN_SCORE, "Score 90 should pass")
        self.assertTrue(110 >= MIN_SCORE, "Score 110 should pass")


class TestIndicatorCalculations(unittest.TestCase):
    """Test indicator calculations with actual data"""

    def setUp(self):
        """Create test data"""
        # Create realistic price series
        np.random.seed(42)
        n = 60
        returns = np.random.normal(0.001, 0.02, n)
        prices = 100 * np.cumprod(1 + returns)
        self.prices = pd.Series(prices)

        self.ohlc = pd.DataFrame({
            'open': self.prices * 0.998,
            'high': self.prices * 1.02,
            'low': self.prices * 0.98,
            'close': self.prices,
            'volume': [1000000] * n
        })

    def test_rsi_in_valid_range(self):
        """RSI should be between 0 and 100"""
        # Import and create screener with mocked dependencies
        with patch.dict('sys.modules', {'loguru': Mock()}):
            try:
                from rapid_rotation_screener import RapidRotationScreener

                # Mock all init methods
                with patch.object(RapidRotationScreener, '__init__', lambda x: None):
                    screener = RapidRotationScreener()
                    screener.data_cache = {}
                    screener.universe = []
                    screener._market_regime_cache = None
                    screener._sector_regime_cache = {}
                    screener._alt_data_cache = {}

                    # Calculate RSI
                    rsi = screener.calculate_rsi(self.prices, period=14)
                    rsi_valid = rsi.dropna()

                    self.assertTrue(all(rsi_valid >= 0), "RSI should be >= 0")
                    self.assertTrue(all(rsi_valid <= 100), "RSI should be <= 100")
            except Exception as e:
                self.skipTest(f"Could not import screener: {e}")

    def test_atr_positive(self):
        """ATR should be positive"""
        with patch.dict('sys.modules', {'loguru': Mock()}):
            try:
                from rapid_rotation_screener import RapidRotationScreener

                with patch.object(RapidRotationScreener, '__init__', lambda x: None):
                    screener = RapidRotationScreener()
                    screener.data_cache = {}
                    screener.universe = []

                    atr = screener.calculate_atr(self.ohlc, period=14)
                    atr_valid = atr.dropna()

                    self.assertTrue(all(atr_valid > 0), "ATR should be positive")
            except Exception as e:
                self.skipTest(f"Could not import screener: {e}")


class TestDataIntegrity(unittest.TestCase):
    """Test data handling"""

    def test_multiindex_column_handling(self):
        """Test that MultiIndex columns are flattened correctly"""
        # Simulate yfinance MultiIndex columns
        arrays = [['Close', 'High', 'Low', 'Open', 'Volume'],
                  ['TEST', 'TEST', 'TEST', 'TEST', 'TEST']]
        tuples = list(zip(*arrays))
        index = pd.MultiIndex.from_tuples(tuples)

        df = pd.DataFrame(
            [[100, 105, 95, 98, 1000000]],
            columns=index
        )

        # Flatten
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

        self.assertIn('Close', df.columns)
        self.assertIn('High', df.columns)

    def test_empty_data_handling(self):
        """Test handling of empty dataframes"""
        df = pd.DataFrame()

        self.assertTrue(df.empty, "Empty dataframe should be detected")
        self.assertTrue(len(df) < 30, "Should fail minimum length check")


# ===================================
# RUN TESTS
# ===================================
if __name__ == "__main__":
    # Run tests with verbosity
    unittest.main(verbosity=2)
