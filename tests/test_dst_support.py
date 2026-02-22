"""
Test Daylight Saving Time (DST) Support

Verifies that the system correctly handles timezone conversion between
EDT (summer) and EST (winter) for US market hours.
"""

import unittest
import pytz
from datetime import datetime
from pathlib import Path
import sys

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from utils.market_hours import (
    MARKET_TIMEZONE,
    get_et_time,
    is_market_hours,
    MARKET_OPEN_TIME,
    MARKET_CLOSE_TIME
)


class TestDSTSupport(unittest.TestCase):
    """Test DST (Daylight Saving Time) handling"""

    def test_timezone_is_us_eastern(self):
        """Verify we're using US/Eastern timezone (auto-handles DST)"""
        self.assertEqual(str(MARKET_TIMEZONE), 'US/Eastern')

    def test_winter_time_est_offset(self):
        """Test winter time (EST = UTC-5)"""
        # February 21, 2026, 10:00 AM ET (winter/EST)
        winter_dt = datetime(2026, 2, 21, 10, 0, 0)
        winter_et = MARKET_TIMEZONE.localize(winter_dt)

        # In winter (EST), offset should be UTC-5
        offset_hours = winter_et.utcoffset().total_seconds() / 3600
        self.assertEqual(offset_hours, -5.0, "Winter should be EST (UTC-5)")

        # Verify timezone name is EST
        self.assertEqual(winter_et.tzname(), 'EST')

    def test_summer_time_edt_offset(self):
        """Test summer time (EDT = UTC-4)"""
        # August 15, 2026, 10:00 AM ET (summer/EDT)
        summer_dt = datetime(2026, 8, 15, 10, 0, 0)
        summer_et = MARKET_TIMEZONE.localize(summer_dt)

        # In summer (EDT), offset should be UTC-4
        offset_hours = summer_et.utcoffset().total_seconds() / 3600
        self.assertEqual(offset_hours, -4.0, "Summer should be EDT (UTC-4)")

        # Verify timezone name is EDT
        self.assertEqual(summer_et.tzname(), 'EDT')

    def test_dst_transition_march_2026(self):
        """Test DST transition: March 8, 2026 (EST → EDT)"""
        # Saturday before transition (EST)
        before = datetime(2026, 3, 7, 12, 0, 0)
        before_et = MARKET_TIMEZONE.localize(before)
        self.assertEqual(before_et.tzname(), 'EST')

        # Monday after transition (EDT) - Note: DST happens Sunday 2am
        after = datetime(2026, 3, 9, 12, 0, 0)
        after_et = MARKET_TIMEZONE.localize(after)
        self.assertEqual(after_et.tzname(), 'EDT')

    def test_dst_transition_november_2026(self):
        """Test DST transition: November 1, 2026 (EDT → EST)"""
        # Saturday before transition (EDT)
        before = datetime(2026, 10, 31, 12, 0, 0)
        before_et = MARKET_TIMEZONE.localize(before)
        self.assertEqual(before_et.tzname(), 'EDT')

        # Monday after transition (EST)
        after = datetime(2026, 11, 2, 12, 0, 0)
        after_et = MARKET_TIMEZONE.localize(after)
        self.assertEqual(after_et.tzname(), 'EST')

    def test_market_hours_independent_of_dst(self):
        """Verify market hours (9:30-16:00 ET) work in both EST and EDT"""
        # Winter (EST): 10:00 AM ET should be market hours
        winter_dt = datetime(2026, 2, 21, 10, 0, 0)
        winter_et = MARKET_TIMEZONE.localize(winter_dt)
        self.assertTrue(is_market_hours(winter_et))

        # Summer (EDT): 10:00 AM ET should be market hours
        summer_dt = datetime(2026, 8, 15, 10, 0, 0)
        summer_et = MARKET_TIMEZONE.localize(summer_dt)
        self.assertTrue(is_market_hours(summer_et))

        # Both should show same market hours (9:30-16:00 ET)
        self.assertEqual(MARKET_OPEN_TIME.hour, 9)
        self.assertEqual(MARKET_OPEN_TIME.minute, 30)
        self.assertEqual(MARKET_CLOSE_TIME.hour, 16)
        self.assertEqual(MARKET_CLOSE_TIME.minute, 0)

    def test_bangkok_to_et_conversion_winter(self):
        """Test Bangkok (GMT+7) to ET conversion in winter (EST)"""
        # February 21, 2026, 21:30 Bangkok time = 09:30 EST (market open)
        bangkok_tz = pytz.timezone('Asia/Bangkok')
        bangkok_dt = datetime(2026, 2, 21, 21, 30, 0)
        bangkok_aware = bangkok_tz.localize(bangkok_dt)

        # Convert to ET
        et_dt = bangkok_aware.astimezone(MARKET_TIMEZONE)

        # Should be 09:30 EST (market open)
        self.assertEqual(et_dt.hour, 9)
        self.assertEqual(et_dt.minute, 30)
        self.assertEqual(et_dt.tzname(), 'EST')

    def test_bangkok_to_et_conversion_summer(self):
        """Test Bangkok (GMT+7) to ET conversion in summer (EDT)"""
        # August 15, 2026, 20:30 Bangkok time = 09:30 EDT (market open)
        bangkok_tz = pytz.timezone('Asia/Bangkok')
        bangkok_dt = datetime(2026, 8, 15, 20, 30, 0)
        bangkok_aware = bangkok_tz.localize(bangkok_dt)

        # Convert to ET
        et_dt = bangkok_aware.astimezone(MARKET_TIMEZONE)

        # Should be 09:30 EDT (market open)
        self.assertEqual(et_dt.hour, 9)
        self.assertEqual(et_dt.minute, 30)
        self.assertEqual(et_dt.tzname(), 'EDT')

    def test_get_et_time_returns_correct_timezone(self):
        """Test that get_et_time() returns timezone-aware datetime"""
        et_now = get_et_time()

        # Should be timezone-aware
        self.assertIsNotNone(et_now.tzinfo)

        # Should be US/Eastern (EST or EDT depending on date)
        self.assertIn(et_now.tzname(), ['EST', 'EDT'])

    def test_dst_schedule_2026(self):
        """Verify 2026 DST schedule matches US rules"""
        # DST starts: 2nd Sunday of March (March 8, 2026) at 2:00 AM
        # DST ends: 1st Sunday of November (November 1, 2026) at 2:00 AM

        # Before DST start (March 7, 2026) - should be EST
        before_start = datetime(2026, 3, 7, 12, 0, 0)
        before_start_et = MARKET_TIMEZONE.localize(before_start)
        self.assertEqual(before_start_et.tzname(), 'EST')

        # After DST start (March 9, 2026) - should be EDT
        after_start = datetime(2026, 3, 9, 12, 0, 0)
        after_start_et = MARKET_TIMEZONE.localize(after_start)
        self.assertEqual(after_start_et.tzname(), 'EDT')

        # Before DST end (October 31, 2026) - should be EDT
        before_end = datetime(2026, 10, 31, 12, 0, 0)
        before_end_et = MARKET_TIMEZONE.localize(before_end)
        self.assertEqual(before_end_et.tzname(), 'EDT')

        # After DST end (November 2, 2026) - should be EST
        after_end = datetime(2026, 11, 2, 12, 0, 0)
        after_end_et = MARKET_TIMEZONE.localize(after_end)
        self.assertEqual(after_end_et.tzname(), 'EST')


class TestMarketHoursFromThailand(unittest.TestCase):
    """Test market hours from Thailand perspective"""

    def setUp(self):
        """Set up Bangkok timezone"""
        self.bangkok_tz = pytz.timezone('Asia/Bangkok')

    def test_market_open_winter_from_bangkok(self):
        """Market opens 21:30 Bangkok time in winter (EST)"""
        # February 21, 2026, 21:30 Bangkok = 09:30 EST
        bangkok_dt = self.bangkok_tz.localize(datetime(2026, 2, 21, 21, 30, 0))
        et_dt = bangkok_dt.astimezone(MARKET_TIMEZONE)

        self.assertEqual(et_dt.hour, 9)
        self.assertEqual(et_dt.minute, 30)
        self.assertTrue(is_market_hours(et_dt))

    def test_market_open_summer_from_bangkok(self):
        """Market opens 20:30 Bangkok time in summer (EDT)"""
        # August 15, 2026, 20:30 Bangkok = 09:30 EDT
        bangkok_dt = self.bangkok_tz.localize(datetime(2026, 8, 15, 20, 30, 0))
        et_dt = bangkok_dt.astimezone(MARKET_TIMEZONE)

        self.assertEqual(et_dt.hour, 9)
        self.assertEqual(et_dt.minute, 30)
        self.assertTrue(is_market_hours(et_dt))

    def test_market_close_winter_from_bangkok(self):
        """Market closes 04:00 Bangkok time (next day) in winter (EST)"""
        # February 22, 2026, 04:00 Bangkok = February 21, 16:00 EST
        bangkok_dt = self.bangkok_tz.localize(datetime(2026, 2, 22, 4, 0, 0))
        et_dt = bangkok_dt.astimezone(MARKET_TIMEZONE)

        self.assertEqual(et_dt.hour, 16)
        self.assertEqual(et_dt.minute, 0)
        # At exactly 16:00, market is just closed
        self.assertFalse(is_market_hours(et_dt))

    def test_market_close_summer_from_bangkok(self):
        """Market closes 03:00 Bangkok time (next day) in summer (EDT)"""
        # August 16, 2026, 03:00 Bangkok = August 15, 16:00 EDT
        bangkok_dt = self.bangkok_tz.localize(datetime(2026, 8, 16, 3, 0, 0))
        et_dt = bangkok_dt.astimezone(MARKET_TIMEZONE)

        self.assertEqual(et_dt.hour, 16)
        self.assertEqual(et_dt.minute, 0)
        # At exactly 16:00, market is just closed
        self.assertFalse(is_market_hours(et_dt))


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
