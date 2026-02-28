"""
Tests for JSON → SQLite DB migration (v6.72)
=============================================
Covers all 5 migrated repositories using temp in-memory SQLite databases.

Run:
    python3 -m pytest tests/database/repositories/test_json_to_db_migration.py -v
"""

import unittest
import tempfile
import os
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / 'src'))

from database.manager import DatabaseManager


# ─────────────────────────────────────────────────────────────────────────────
# Helper: temp-file DatabaseManager (bypasses the global singleton)
# ─────────────────────────────────────────────────────────────────────────────

def make_test_db() -> tuple:
    """Return (DatabaseManager, tmp_path) using a temp file."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp.close()
    db = DatabaseManager(tmp.name)
    return db, tmp.name


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — PreFilterStatusDB
# ─────────────────────────────────────────────────────────────────────────────

class TestPreFilterStatusDB(unittest.TestCase):
    """Test pre_filter_sessions DB read via PreFilterRepository."""

    def setUp(self):
        self.db, self.db_path = make_test_db()
        # Create minimal pre_filter_sessions schema
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS pre_filter_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_type TEXT NOT NULL,
                scan_time TEXT,
                pool_size INTEGER DEFAULT 0,
                total_scanned INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running',
                is_ready INTEGER DEFAULT 0,
                duration_seconds REAL,
                error_message TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS filtered_stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                symbol TEXT,
                sector TEXT,
                score REAL,
                close_price REAL,
                volume_avg_20d REAL,
                atr_pct REAL,
                rsi REAL,
                filter_reason TEXT
            )
        """)

        from database.repositories.pre_filter_repository import PreFilterRepository
        self.repo = PreFilterRepository(_db=self.db)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _insert_session(self, scan_type, pool_size, status='completed', is_ready=1):
        self.db.execute("""
            INSERT INTO pre_filter_sessions
                (scan_type, scan_time, pool_size, total_scanned, status, is_ready, created_at)
            VALUES (?, datetime('now'), ?, 987, ?, ?, datetime('now'))
        """, (scan_type, pool_size, status, is_ready))

    def test_load_from_evening_session(self):
        self._insert_session('evening', 312)
        session = self.repo.get_latest_session(scan_type='evening')
        self.assertIsNotNone(session)
        self.assertEqual(session.pool_size, 312)
        self.assertEqual(session.status, 'completed')
        self.assertTrue(session.is_ready)

    def test_load_from_both_sessions(self):
        self._insert_session('evening', 312)
        self._insert_session('pre_open', 280)
        ev = self.repo.get_latest_session(scan_type='evening')
        po = self.repo.get_latest_session(scan_type='pre_open')
        self.assertEqual(ev.pool_size, 312)
        self.assertEqual(po.pool_size, 280)

    def test_load_empty_returns_none(self):
        session = self.repo.get_latest_session(scan_type='evening')
        self.assertIsNone(session)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — HeartbeatDB
# ─────────────────────────────────────────────────────────────────────────────

class TestHeartbeatDB(unittest.TestCase):
    """Test HeartbeatRepository write/read round-trip."""

    def setUp(self):
        self.db, self.db_path = make_test_db()
        from database.repositories.heartbeat_repository import HeartbeatRepository
        self.repo = HeartbeatRepository(_db=self.db)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_write_and_read(self):
        self.repo.write(state='MONITORING', positions=3, running=True)
        hb = self.repo.read(max_age_seconds=120)
        self.assertEqual(hb['state'], 'MONITORING')
        self.assertEqual(hb['positions'], 3)
        self.assertTrue(hb['running'])
        self.assertIsNotNone(hb['timestamp'])

    def test_fresh_is_not_stale(self):
        self.repo.write(state='SCANNING', positions=0, running=True)
        hb = self.repo.read(max_age_seconds=120)
        self.assertFalse(hb['stale'])
        self.assertTrue(hb['alive'])

    def test_stale_after_max_age(self):
        """Simulate a stale heartbeat by inserting old timestamp directly."""
        old_ts = (datetime.now() - timedelta(seconds=200)).isoformat()
        self.db.execute("""
            INSERT OR REPLACE INTO engine_heartbeat
                (id, timestamp, alive, state, positions, running, updated_at)
            VALUES (1, ?, 1, 'MONITORING', 2, 1, ?)
        """, (old_ts, old_ts))
        hb = self.repo.read(max_age_seconds=120)
        self.assertTrue(hb['stale'])
        self.assertFalse(hb['alive'])

    def test_no_heartbeat_returns_not_alive(self):
        hb = self.repo.read(max_age_seconds=120)
        self.assertFalse(hb['alive'])
        self.assertTrue(hb['stale'])


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — SectorCacheDB
# ─────────────────────────────────────────────────────────────────────────────

class TestSectorCacheDB(unittest.TestCase):
    """Test SectorCacheRepository save_bulk / load_all with TTL."""

    def setUp(self):
        self.db, self.db_path = make_test_db()
        from database.repositories.sector_cache_repository import SectorCacheRepository
        self.repo = SectorCacheRepository(_db=self.db)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _make_cache(self, symbols, age_seconds=0):
        ts = time.time() - age_seconds
        return {sym: {'sector': 'Technology', 'ts': ts, 'status': 'active'} for sym in symbols}

    def test_save_and_load_bulk(self):
        cache = self._make_cache(['AAPL', 'MSFT', 'NVDA'])
        self.repo.save_bulk(cache)
        loaded = self.repo.load_all(ttl_seconds=86400)
        self.assertEqual(set(loaded.keys()), {'AAPL', 'MSFT', 'NVDA'})
        self.assertEqual(loaded['AAPL']['sector'], 'Technology')

    def test_ttl_filters_expired_entries(self):
        fresh = self._make_cache(['AAPL'], age_seconds=0)
        stale = self._make_cache(['TSLA'], age_seconds=90000)  # > 1 day old
        self.repo.save_bulk({**fresh, **stale})
        # Load with 1-day TTL — stale entry should be excluded
        loaded = self.repo.load_all(ttl_seconds=86400)
        self.assertIn('AAPL', loaded)
        self.assertNotIn('TSLA', loaded)

    def test_empty_returns_empty_dict(self):
        result = self.repo.load_all(ttl_seconds=86400)
        self.assertEqual(result, {})


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — DLQDB
# ─────────────────────────────────────────────────────────────────────────────

class TestDLQDB(unittest.TestCase):
    """Test DLQRepository CRUD operations."""

    def setUp(self):
        self.db, self.db_path = make_test_db()
        from database.repositories.dlq_repository import DLQRepository
        self.repo = DLQRepository(_db=self.db)

        from engine.dead_letter_queue import DLQItem, DLQStatus
        self.DLQItem = DLQItem
        self.DLQStatus = DLQStatus

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _make_item(self, item_id='test_op_001', op_type='order_submission',
                   status='pending'):
        return self.DLQItem(
            id=item_id,
            operation_type=op_type,
            operation_data={'symbol': 'AAPL', 'qty': 10},
            error='API timeout',
            context={'account': 'paper'},
            status=status,
            created_at=datetime.now().isoformat(),
            next_retry_at=(datetime.now() + timedelta(minutes=1)).isoformat(),
        )

    def test_add_and_get_all(self):
        item = self._make_item()
        self.repo.add(item)
        rows = self.repo.get_all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], 'test_op_001')
        self.assertEqual(rows[0]['operation_data']['symbol'], 'AAPL')

    def test_retry_increments_count(self):
        item = self._make_item()
        self.repo.add(item)

        item.retry_count = 1
        item.last_retry_at = datetime.now().isoformat()
        item.status = 'retrying'
        self.repo.update(item)

        rows = self.repo.get_all()
        self.assertEqual(rows[0]['retry_count'], 1)
        self.assertEqual(rows[0]['status'], 'retrying')

    def test_resolve_marks_resolved(self):
        item = self._make_item()
        self.repo.add(item)

        item.status = 'resolved'
        item.resolved_at = datetime.now().isoformat()
        item.resolution_note = 'Fixed manually'
        self.repo.update(item)

        rows = self.repo.get_all()
        self.assertEqual(rows[0]['status'], 'resolved')
        self.assertEqual(rows[0]['resolution_note'], 'Fixed manually')

    def test_cleanup_old_items(self):
        # Insert a resolved item with old timestamp
        item = self._make_item()
        item.status = 'resolved'
        item.resolved_at = (datetime.now() - timedelta(days=40)).isoformat()
        self.repo.add(item)

        deleted = self.repo.delete_old(days=30)
        self.assertEqual(deleted, 1)
        self.assertEqual(self.repo.get_all(), [])

    def test_get_statistics(self):
        self.repo.add(self._make_item('id1', status='pending'))
        self.repo.add(self._make_item('id2', status='pending'))

        item3 = self._make_item('id3', status='resolved')
        item3.resolved_at = datetime.now().isoformat()
        self.repo.add(item3)

        stats = self.repo.get_statistics()
        self.assertEqual(stats.get('pending', 0), 2)
        self.assertEqual(stats.get('resolved', 0), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — UniverseDB
# ─────────────────────────────────────────────────────────────────────────────

class TestUniverseDB(unittest.TestCase):
    """Test UniverseRepository save_bulk / get_all / get_symbols."""

    def setUp(self):
        self.db, self.db_path = make_test_db()
        from database.repositories.universe_repository import UniverseRepository
        self.repo = UniverseRepository(_db=self.db)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _make_universe(self, symbols):
        now_ts = time.time()
        return {
            sym: {'sector': 'Technology', 'ts': now_ts, 'status': 'active', 'dollar_vol': 1e7}
            for sym in symbols
        }

    def test_save_bulk_and_get_all(self):
        universe = self._make_universe(['AAPL', 'MSFT', 'NVDA'])
        self.repo.save_bulk(universe)
        loaded = self.repo.get_all()
        self.assertEqual(set(loaded.keys()), {'AAPL', 'MSFT', 'NVDA'})
        self.assertEqual(loaded['AAPL']['sector'], 'Technology')
        self.assertAlmostEqual(loaded['AAPL']['dollar_vol'], 1e7, places=0)

    def test_save_bulk_replaces_existing(self):
        self.repo.save_bulk(self._make_universe(['AAPL', 'MSFT']))
        # Replace with a completely different set
        self.repo.save_bulk(self._make_universe(['TSLA', 'GOOG']))
        loaded = self.repo.get_all()
        self.assertNotIn('AAPL', loaded)
        self.assertIn('TSLA', loaded)
        self.assertIn('GOOG', loaded)

    def test_get_symbols(self):
        self.repo.save_bulk(self._make_universe(['NVDA', 'AAPL', 'MSFT']))
        symbols = self.repo.get_symbols()
        self.assertEqual(symbols, sorted(['NVDA', 'AAPL', 'MSFT']))

    def test_empty_db_returns_empty(self):
        self.assertEqual(self.repo.get_all(), {})
        self.assertEqual(self.repo.get_symbols(), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
