"""
Unit Tests for PDTRepository - Pattern Day Trader Tracking

Tests PDT compliance tracking functionality including:
- Adding/removing entries
- Same-day sell prevention (can_sell_today)
- Exit recording
- Cleanup operations
"""

import unittest
import sqlite3
import tempfile
import os
from datetime import date, timedelta
from pathlib import Path
import sys

# Add src to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / 'src'))

from database.repositories.pdt_repository import PDTRepository


class TestPDTRepository(unittest.TestCase):
    """Test suite for PDT Repository"""

    def setUp(self):
        """Create temporary database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Create repository with test database
        self.repo = PDTRepository(db_path=self.db_path)

        # Initialize schema
        self._create_schema()

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _create_schema(self):
        """Create PDT tracking table schema"""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pdt_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                entry_date TEXT NOT NULL,
                entry_time TEXT,
                exit_date TEXT,
                exit_time TEXT,
                same_day_exit INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_pdt_symbol ON pdt_tracking(symbol);
            CREATE INDEX IF NOT EXISTS idx_pdt_entry_date ON pdt_tracking(entry_date);
            CREATE INDEX IF NOT EXISTS idx_pdt_exit_date ON pdt_tracking(exit_date) WHERE exit_date IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_pdt_same_day ON pdt_tracking(same_day_exit) WHERE same_day_exit = 1;

            CREATE VIEW IF NOT EXISTS v_active_pdt_restrictions AS
            SELECT symbol, entry_date, entry_time
            FROM pdt_tracking
            WHERE exit_date IS NULL AND entry_date = date('now');

            CREATE VIEW IF NOT EXISTS v_pdt_violations AS
            SELECT symbol, entry_date, entry_time, exit_date, exit_time
            FROM pdt_tracking
            WHERE same_day_exit = 1
            ORDER BY exit_date DESC;
        """)
        conn.commit()
        conn.close()

    # =========================================================================
    # Test: Add Entry
    # =========================================================================

    def test_add_entry_new_symbol(self):
        """Test adding a new PDT entry"""
        today = date.today()
        success = self.repo.add_entry('AAPL', today)

        self.assertTrue(success)

        # Verify entry exists
        entries = self.repo.get_all_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries['AAPL'], today.isoformat())

    def test_add_entry_duplicate_symbol(self):
        """Test adding duplicate symbol (should update, not fail)"""
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Add first entry
        self.repo.add_entry('AAPL', yesterday)

        # Add again (should update)
        success = self.repo.add_entry('AAPL', today)
        self.assertTrue(success)

        # Should still be 1 entry with updated date
        entries = self.repo.get_all_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries['AAPL'], today.isoformat())

    # =========================================================================
    # Test: Can Sell Today (PDT Protection)
    # =========================================================================

    def test_can_sell_today_same_day_buy(self):
        """Test PDT protection: cannot sell same day"""
        today = date.today()
        self.repo.add_entry('AAPL', today)

        # Should NOT be able to sell today (PDT violation)
        can_sell = self.repo.can_sell_today('AAPL')
        self.assertFalse(can_sell)

    def test_can_sell_today_next_day_buy(self):
        """Test can sell next day (no PDT violation)"""
        yesterday = date.today() - timedelta(days=1)
        self.repo.add_entry('AAPL', yesterday)

        # Should be able to sell today (bought yesterday)
        can_sell = self.repo.can_sell_today('AAPL')
        self.assertTrue(can_sell)

    def test_can_sell_today_no_entry(self):
        """Test can sell if no PDT entry exists"""
        # Should be able to sell (not tracked)
        can_sell = self.repo.can_sell_today('AAPL')
        self.assertTrue(can_sell)

    def test_can_sell_today_already_exited(self):
        """Test can sell if already exited position"""
        today = date.today()
        self.repo.add_entry('AAPL', today)
        self.repo.record_exit('AAPL', today)

        # Should be able to sell (already exited)
        can_sell = self.repo.can_sell_today('AAPL')
        self.assertTrue(can_sell)

    # =========================================================================
    # Test: Record Exit
    # =========================================================================

    def test_record_exit_same_day(self):
        """Test recording same-day exit (PDT violation)"""
        today = date.today()
        self.repo.add_entry('AAPL', today)
        success = self.repo.record_exit('AAPL', today)

        self.assertTrue(success)

        # Verify same_day_exit flag is set
        conn = self.repo._get_connection()
        row = conn.execute(
            "SELECT same_day_exit FROM pdt_tracking WHERE symbol = ?",
            ('AAPL',)
        ).fetchone()
        conn.close()

        self.assertEqual(row['same_day_exit'], 1)

    def test_record_exit_next_day(self):
        """Test recording next-day exit (no violation)"""
        yesterday = date.today() - timedelta(days=1)
        today = date.today()

        self.repo.add_entry('AAPL', yesterday)
        success = self.repo.record_exit('AAPL', today)

        self.assertTrue(success)

        # Verify same_day_exit flag is NOT set
        conn = self.repo._get_connection()
        row = conn.execute(
            "SELECT same_day_exit FROM pdt_tracking WHERE symbol = ?",
            ('AAPL',)
        ).fetchone()
        conn.close()

        self.assertEqual(row['same_day_exit'], 0)

    def test_record_exit_no_entry(self):
        """Test recording exit for non-existent entry (idempotent, returns True)"""
        today = date.today()
        success = self.repo.record_exit('AAPL', today)

        # Should succeed (idempotent - no error even if no entry exists)
        self.assertTrue(success)

        # Verify no entries created
        entries = self.repo.get_all_entries()
        self.assertEqual(len(entries), 0)

    # =========================================================================
    # Test: Remove Entry
    # =========================================================================

    def test_remove_entry_exists(self):
        """Test removing existing entry"""
        today = date.today()
        self.repo.add_entry('AAPL', today)

        success = self.repo.remove_entry('AAPL')
        self.assertTrue(success)

        # Verify entry removed
        entries = self.repo.get_all_entries()
        self.assertEqual(len(entries), 0)

    def test_remove_entry_not_exists(self):
        """Test removing non-existent entry (should succeed, idempotent)"""
        success = self.repo.remove_entry('AAPL')
        self.assertTrue(success)

    # =========================================================================
    # Test: Get Active Restrictions
    # =========================================================================

    def test_get_active_restrictions_today(self):
        """Test getting symbols bought today (active restrictions)"""
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Add entries
        self.repo.add_entry('AAPL', today)       # Active restriction
        self.repo.add_entry('GOOGL', yesterday)  # No restriction

        active = self.repo.get_active_restrictions()

        # Only AAPL should be restricted (returns list of symbols)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0], 'AAPL')

    def test_get_active_restrictions_empty(self):
        """Test getting restrictions when none active"""
        yesterday = date.today() - timedelta(days=1)
        self.repo.add_entry('AAPL', yesterday)

        active = self.repo.get_active_restrictions()
        self.assertEqual(len(active), 0)

    # =========================================================================
    # Test: Cleanup Old Entries
    # =========================================================================

    def test_cleanup_old_entries(self):
        """Test cleaning up entries older than N days"""
        today = date.today()
        old_date = today - timedelta(days=100)

        # Add old and recent entries
        self.repo.add_entry('OLD', old_date)
        self.repo.add_entry('RECENT', today)

        # Record exit for old entry
        self.repo.record_exit('OLD', old_date)

        # Cleanup entries older than 90 days
        deleted = self.repo.cleanup_old_entries(days=90)

        self.assertEqual(deleted, 1)

        # Verify only RECENT remains
        entries = self.repo.get_all_entries()
        self.assertEqual(len(entries), 1)
        self.assertIn('RECENT', entries)

    # =========================================================================
    # Test: Import/Export JSON
    # =========================================================================

    def test_import_from_json(self):
        """Test importing PDT entries from JSON format"""
        json_data = {
            'AAPL': '2026-02-20',
            'GOOGL': '2026-02-19'
        }

        success = self.repo.import_from_json(json_data)
        self.assertTrue(success)

        # Verify both entries imported
        entries = self.repo.get_all_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries['AAPL'], '2026-02-20')
        self.assertEqual(entries['GOOGL'], '2026-02-19')

    def test_export_to_json(self):
        """Test exporting PDT entries to JSON format"""
        today = date.today()
        yesterday = today - timedelta(days=1)

        self.repo.add_entry('AAPL', today)
        self.repo.add_entry('GOOGL', yesterday)

        json_data = self.repo.export_to_json()

        self.assertEqual(len(json_data), 2)
        self.assertEqual(json_data['AAPL'], today.isoformat())
        self.assertEqual(json_data['GOOGL'], yesterday.isoformat())

    # =========================================================================
    # Test: Edge Cases
    # =========================================================================

    def test_multiple_symbols_same_day(self):
        """Test tracking multiple symbols bought on same day"""
        today = date.today()

        self.repo.add_entry('AAPL', today)
        self.repo.add_entry('GOOGL', today)
        self.repo.add_entry('MSFT', today)

        # All should be restricted
        self.assertFalse(self.repo.can_sell_today('AAPL'))
        self.assertFalse(self.repo.can_sell_today('GOOGL'))
        self.assertFalse(self.repo.can_sell_today('MSFT'))

        active = self.repo.get_active_restrictions()
        self.assertEqual(len(active), 3)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
