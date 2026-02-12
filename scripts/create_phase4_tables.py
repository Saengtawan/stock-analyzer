#!/usr/bin/env python3
"""
Create Phase 4 Tables - Storage Strategy
=========================================
Adds new tables to trade_history.db for:
- active_positions (migrate from JSON)
- alerts (migrate from JSON)
"""

import sqlite3
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "trade_history.db"

def create_phase4_tables():
    """Create Phase 4 tables in trade_history.db"""
    print("="*70)
    print("  Phase 4: Creating Storage Strategy Tables")
    print("="*70)
    print()

    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return False

    print(f"📂 Database: {DB_PATH}")
    print(f"📊 Size: {DB_PATH.stat().st_size / 1024:.1f} KB")
    print()

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Enable WAL mode for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL")
        print("✅ WAL mode enabled")

        # Table 1: active_positions
        print("\n📦 Creating table: active_positions")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_positions (
                symbol TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                qty INTEGER NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                peak_price REAL,
                trough_price REAL,
                trailing_stop INTEGER DEFAULT 0,
                day_held INTEGER DEFAULT 0,
                sl_pct REAL,
                tp_pct REAL,
                entry_atr_pct REAL,
                sl_order_id TEXT,
                tp_order_id TEXT,
                entry_order_id TEXT,
                sector TEXT,
                source TEXT,
                signal_score INTEGER,
                mode TEXT,
                regime TEXT,
                entry_rsi REAL,
                momentum_5d REAL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                CHECK(qty > 0),
                CHECK(entry_price > 0)
            )
        """)
        print("   ✅ Table created (or already exists)")

        # Table 2: alerts
        print("\n📦 Creating table: alerts")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL CHECK(level IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                resolved_at TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("   ✅ Table created (or already exists)")

        # Indexes
        print("\n📇 Creating indexes...")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_updated
            ON active_positions(updated_at)
        """)
        print("   ✅ idx_positions_updated")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_active
            ON alerts(active)
        """)
        print("   ✅ idx_alerts_active")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_level
            ON alerts(level)
        """)
        print("   ✅ idx_alerts_level")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
            ON alerts(timestamp)
        """)
        print("   ✅ idx_alerts_timestamp")

        conn.commit()

        # Verify tables
        print("\n📊 Verifying schema...")
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN ('active_positions', 'alerts')
            ORDER BY name
        """)
        tables = cursor.fetchall()

        for (table_name,) in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"   ✅ {table_name}: {count} records")

        conn.close()

        print("\n" + "="*70)
        print("  ✅ Phase 4 Tables Created Successfully!")
        print("="*70)
        print()
        print("📋 Summary:")
        print("   - active_positions: Ready for position data")
        print("   - alerts: Ready for alert data")
        print("   - 4 indexes created for performance")
        print()
        print("🎯 Next Steps:")
        print("   1. Run migration script: python scripts/migrate_positions_to_db.py")
        print("   2. Update PositionRepository to database-backed")
        print("   3. Create AlertsRepository")
        print()

        return True

    except Exception as e:
        print(f"\n❌ Error creating tables: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = create_phase4_tables()
    exit(0 if success else 1)
