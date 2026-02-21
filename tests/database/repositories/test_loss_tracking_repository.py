"""
Unit Tests for LossTrackingRepository - Risk Management

Tests loss tracking and risk management functionality including:
- Consecutive loss tracking
- Weekly P&L tracking
- Cooldown management
- Sector-specific loss tracking
- Risk status assessment
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

from database.repositories.loss_tracking_repository import LossTrackingRepository


class TestLossTrackingRepository(unittest.TestCase):
    """Test suite for Loss Tracking Repository"""

    def setUp(self):
        """Create temporary database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Create repository with test database
        self.repo = LossTrackingRepository(db_path=self.db_path)

        # Initialize schema
        self._create_schema()

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _create_schema(self):
        """Create loss tracking table schema"""
        # Read and execute the actual migration SQL
        migration_file = project_root / 'src/database/migrations/005_create_loss_tracking_tables.sql'
        if migration_file.exists():
            with open(migration_file, 'r') as f:
                sql = f.read()
            conn = sqlite3.connect(self.db_path)
            conn.executescript(sql)
            conn.commit()
            conn.close()
        else:
            # Fallback: create minimal schema
            conn = sqlite3.connect(self.db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS loss_tracking (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    consecutive_losses INTEGER NOT NULL DEFAULT 0,
                    weekly_realized_pnl REAL NOT NULL DEFAULT 0.0,
                    weekly_reset_date TEXT,
                    cooldown_until TEXT,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    saved_at TEXT
                );

                INSERT OR IGNORE INTO loss_tracking (id, consecutive_losses, weekly_realized_pnl)
                VALUES (1, 0, 0.0);

                CREATE TABLE IF NOT EXISTS sector_loss_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sector TEXT NOT NULL UNIQUE,
                    losses INTEGER NOT NULL DEFAULT 0,
                    cooldown_until TEXT,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)
            conn.commit()
            conn.close()

    # =========================================================================
    # Test: Get State
    # =========================================================================

    def test_get_state_initial(self):
        """Test getting initial state (zeros)"""
        state = self.repo.get_state()

        self.assertEqual(state['consecutive_losses'], 0)
        self.assertEqual(state['weekly_realized_pnl'], 0.0)
        self.assertIsNone(state['cooldown_until'])
        self.assertIsNone(state['weekly_reset_date'])

    # =========================================================================
    # Test: Increment Losses
    # =========================================================================

    def test_increment_losses_once(self):
        """Test incrementing losses by 1"""
        new_count = self.repo.increment_losses()
        self.assertEqual(new_count, 1)

        # Verify state
        state = self.repo.get_state()
        self.assertEqual(state['consecutive_losses'], 1)

    def test_increment_losses_multiple(self):
        """Test incrementing losses multiple times"""
        self.repo.increment_losses()  # 1
        self.repo.increment_losses()  # 2
        new_count = self.repo.increment_losses()  # 3

        self.assertEqual(new_count, 3)

    # =========================================================================
    # Test: Reset Losses
    # =========================================================================

    def test_reset_losses(self):
        """Test resetting losses after a win"""
        # Increment to 3
        self.repo.increment_losses()
        self.repo.increment_losses()
        self.repo.increment_losses()

        # Reset
        success = self.repo.reset_losses()
        self.assertTrue(success)

        # Verify reset to 0
        state = self.repo.get_state()
        self.assertEqual(state['consecutive_losses'], 0)

    # =========================================================================
    # Test: Update Weekly P&L
    # =========================================================================

    def test_update_weekly_pnl_positive(self):
        """Test adding positive P&L"""
        new_total = self.repo.update_weekly_pnl(100.50)
        self.assertAlmostEqual(new_total, 100.50, places=2)

    def test_update_weekly_pnl_negative(self):
        """Test adding negative P&L (loss)"""
        new_total = self.repo.update_weekly_pnl(-50.25)
        self.assertAlmostEqual(new_total, -50.25, places=2)

    def test_update_weekly_pnl_accumulate(self):
        """Test accumulating multiple P&L changes"""
        self.repo.update_weekly_pnl(100.00)
        self.repo.update_weekly_pnl(-30.50)
        new_total = self.repo.update_weekly_pnl(20.25)

        self.assertAlmostEqual(new_total, 89.75, places=2)

    # =========================================================================
    # Test: Cooldown Management
    # =========================================================================

    def test_set_cooldown(self):
        """Test setting cooldown period"""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        success = self.repo.set_cooldown(tomorrow)
        self.assertTrue(success)

        # Verify cooldown set
        state = self.repo.get_state()
        self.assertEqual(state['cooldown_until'], tomorrow)

    def test_clear_cooldown(self):
        """Test clearing cooldown"""
        # Set cooldown first
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.repo.set_cooldown(tomorrow)

        # Clear it
        success = self.repo.set_cooldown(None)
        self.assertTrue(success)

        # Verify cleared
        state = self.repo.get_state()
        self.assertIsNone(state['cooldown_until'])

    def test_is_in_cooldown_active(self):
        """Test checking active cooldown"""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.repo.set_cooldown(tomorrow)

        self.assertTrue(self.repo.is_in_cooldown())

    def test_is_in_cooldown_expired(self):
        """Test checking expired cooldown"""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.repo.set_cooldown(yesterday)

        self.assertFalse(self.repo.is_in_cooldown())

    def test_is_in_cooldown_none(self):
        """Test checking when no cooldown set"""
        self.assertFalse(self.repo.is_in_cooldown())

    # =========================================================================
    # Test: Reset Weekly
    # =========================================================================

    def test_reset_weekly(self):
        """Test resetting weekly P&L"""
        # Accumulate some P&L
        self.repo.update_weekly_pnl(100.00)
        self.repo.update_weekly_pnl(-50.00)

        # Reset weekly
        next_reset = (date.today() + timedelta(days=7)).isoformat()
        success = self.repo.reset_weekly(next_reset)
        self.assertTrue(success)

        # Verify P&L reset, date updated
        state = self.repo.get_state()
        self.assertAlmostEqual(state['weekly_realized_pnl'], 0.0, places=2)
        self.assertEqual(state['weekly_reset_date'], next_reset)

    # =========================================================================
    # Test: Sector Loss Tracking
    # =========================================================================

    def test_get_sector_losses_no_entry(self):
        """Test getting losses for untracked sector"""
        losses = self.repo.get_sector_losses('Technology')
        self.assertEqual(losses, 0)

    def test_increment_sector_loss(self):
        """Test incrementing sector losses"""
        new_count = self.repo.increment_sector_loss('Technology')
        self.assertEqual(new_count, 1)

        # Increment again
        new_count = self.repo.increment_sector_loss('Technology')
        self.assertEqual(new_count, 2)

    def test_reset_sector_losses(self):
        """Test resetting sector losses"""
        # Increment to 3
        self.repo.increment_sector_loss('Technology')
        self.repo.increment_sector_loss('Technology')
        self.repo.increment_sector_loss('Technology')

        # Reset
        success = self.repo.reset_sector_losses('Technology')
        self.assertTrue(success)

        # Verify reset
        losses = self.repo.get_sector_losses('Technology')
        self.assertEqual(losses, 0)

    def test_set_sector_cooldown(self):
        """Test setting sector cooldown"""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        success = self.repo.set_sector_cooldown('Technology', tomorrow)
        self.assertTrue(success)

        # Verify cooldown
        in_cooldown = self.repo.is_sector_in_cooldown('Technology')
        self.assertTrue(in_cooldown)

    def test_is_sector_in_cooldown_expired(self):
        """Test sector cooldown expiration"""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.repo.set_sector_cooldown('Technology', yesterday)

        in_cooldown = self.repo.is_sector_in_cooldown('Technology')
        self.assertFalse(in_cooldown)

    def test_get_all_sector_losses(self):
        """Test getting all sector data"""
        # Add multiple sectors
        self.repo.increment_sector_loss('Technology')
        self.repo.increment_sector_loss('Technology')
        self.repo.increment_sector_loss('Healthcare')

        sectors = self.repo.get_all_sector_losses()

        self.assertEqual(len(sectors), 2)
        self.assertEqual(sectors['technology']['losses'], 2)
        self.assertEqual(sectors['healthcare']['losses'], 1)

    # =========================================================================
    # Test: Analytics Views
    # =========================================================================

    def test_get_risk_status_normal(self):
        """Test risk status when normal (< 2 losses)"""
        risk = self.repo.get_risk_status()

        self.assertEqual(risk['consecutive_losses'], 0)
        self.assertEqual(risk['risk_level'], 'NORMAL')
        self.assertEqual(risk['cooldown_days_remaining'], 0)

    def test_get_risk_status_elevated(self):
        """Test risk status with 2 losses (elevated)"""
        self.repo.increment_losses()
        self.repo.increment_losses()

        risk = self.repo.get_risk_status()

        self.assertEqual(risk['consecutive_losses'], 2)
        self.assertEqual(risk['risk_level'], 'ELEVATED_RISK')

    def test_get_risk_status_high(self):
        """Test risk status with 3+ losses (high risk)"""
        self.repo.increment_losses()
        self.repo.increment_losses()
        self.repo.increment_losses()

        risk = self.repo.get_risk_status()

        self.assertEqual(risk['consecutive_losses'], 3)
        self.assertEqual(risk['risk_level'], 'HIGH_RISK')

    def test_get_risk_status_cooldown(self):
        """Test risk status during cooldown"""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.repo.set_cooldown(tomorrow)

        risk = self.repo.get_risk_status()

        self.assertEqual(risk['risk_level'], 'COOLDOWN')
        self.assertGreater(risk['cooldown_days_remaining'], 0)

    def test_get_high_risk_sectors(self):
        """Test getting high-risk sectors (2+ losses)"""
        # Add sectors with varying losses
        self.repo.increment_sector_loss('Technology')
        self.repo.increment_sector_loss('Technology')
        self.repo.increment_sector_loss('Technology')  # 3 losses (CRITICAL)

        self.repo.increment_sector_loss('Healthcare')
        self.repo.increment_sector_loss('Healthcare')  # 2 losses (HIGH)

        self.repo.increment_sector_loss('Financials')  # 1 loss (not high risk)

        high_risk = self.repo.get_high_risk_sectors()

        # Should return Technology and Healthcare only
        self.assertEqual(len(high_risk), 2)

        sectors = [s['sector'] for s in high_risk]
        self.assertIn('technology', sectors)
        self.assertIn('healthcare', sectors)

    # =========================================================================
    # Test: Import/Export JSON
    # =========================================================================

    def test_import_from_json(self):
        """Test importing from JSON format"""
        json_data = {
            'consecutive_losses': 2,
            'weekly_realized_pnl': -50.75,
            'cooldown_until': '2026-02-25',
            'weekly_reset_date': '2026-02-28',
            'sector_loss_tracker': {
                'Technology': {'losses': 3, 'cooldown_until': '2026-02-26'},
                'Healthcare': {'losses': 1, 'cooldown_until': None}
            }
        }

        success = self.repo.import_from_json(json_data)
        self.assertTrue(success)

        # Verify main tracking
        state = self.repo.get_state()
        self.assertEqual(state['consecutive_losses'], 2)
        self.assertAlmostEqual(state['weekly_realized_pnl'], -50.75, places=2)
        self.assertEqual(state['cooldown_until'], '2026-02-25')

        # Verify sectors
        sectors = self.repo.get_all_sector_losses()
        self.assertEqual(len(sectors), 2)
        self.assertEqual(sectors['technology']['losses'], 3)
        self.assertEqual(sectors['healthcare']['losses'], 1)

    def test_export_to_json(self):
        """Test exporting to JSON format"""
        # Set up data
        self.repo.increment_losses()
        self.repo.increment_losses()
        self.repo.update_weekly_pnl(-25.50)
        self.repo.increment_sector_loss('Technology')

        json_data = self.repo.export_to_json()

        self.assertEqual(json_data['consecutive_losses'], 2)
        self.assertAlmostEqual(json_data['weekly_realized_pnl'], -25.50, places=2)
        # Sector names stored in lowercase
        self.assertIn('technology', json_data['sector_loss_tracker'])
        self.assertIn('saved_at', json_data)

    # =========================================================================
    # Test: Edge Cases
    # =========================================================================

    def test_sector_name_case_insensitive(self):
        """Test sector names are case-insensitive"""
        self.repo.increment_sector_loss('Technology')
        self.repo.increment_sector_loss('TECHNOLOGY')
        self.repo.increment_sector_loss('technology')

        # All should accumulate to same sector
        losses = self.repo.get_sector_losses('Technology')
        self.assertEqual(losses, 3)

    def test_multiple_operations_transaction_safe(self):
        """Test multiple operations maintain consistency"""
        # Simulate typical workflow
        self.repo.increment_losses()  # Loss 1
        self.repo.update_weekly_pnl(-10.0)
        self.repo.increment_sector_loss('Technology')

        self.repo.increment_losses()  # Loss 2
        self.repo.update_weekly_pnl(-15.0)
        self.repo.increment_sector_loss('Technology')

        # Win - reset
        self.repo.reset_losses()
        self.repo.update_weekly_pnl(50.0)
        self.repo.reset_sector_losses('Technology')

        # Verify final state
        state = self.repo.get_state()
        self.assertEqual(state['consecutive_losses'], 0)
        self.assertAlmostEqual(state['weekly_realized_pnl'], 25.0, places=2)

        losses = self.repo.get_sector_losses('Technology')
        self.assertEqual(losses, 0)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
