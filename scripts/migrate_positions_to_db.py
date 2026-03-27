#!/usr/bin/env python3
"""
Migrate Positions from JSON to Database
========================================
One-time migration script for Phase 4.

Migrates:
- data/active_positions.json → trade_history.db (active_positions table)
- data/alerts.json → trade_history.db (alerts table)
"""

import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "trade_history.db"
POSITIONS_JSON = PROJECT_ROOT / "data" / "active_positions.json"
ALERTS_JSON = PROJECT_ROOT / "data" / "alerts.json"


def migrate_positions():
    """Migrate active_positions.json to database"""
    print("\n" + "="*70)
    print("  Migrating Positions: JSON → Database")
    print("="*70)
    print()

    if not POSITIONS_JSON.exists():
        print(f"⚠️  JSON file not found: {POSITIONS_JSON}")
        print("   Creating empty positions...")
        return 0

    print(f"📂 Reading: {POSITIONS_JSON}")

    try:
        with open(POSITIONS_JSON) as f:
            data = json.load(f)

        positions = data.get('positions', {})
        print(f"   Found {len(positions)} positions")

        if len(positions) == 0:
            print("   ✅ No positions to migrate")
            return 0

        # Connect to database
        conn = None  # via get_session()
        cursor = conn.cursor()

        migrated = 0
        skipped = 0

        for symbol, pos in positions.items():
            # Skip empty positions
            if not pos.get('symbol') or not pos.get('entry_price'):
                skipped += 1
                continue

            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO active_positions (
                        symbol, entry_date, entry_price, qty,
                        stop_loss, take_profit, peak_price, trough_price,
                        trailing_stop, day_held,
                        sl_pct, tp_pct, entry_atr_pct,
                        sl_order_id, tp_order_id, entry_order_id,
                        sector, source, signal_score,
                        mode, regime, entry_rsi, momentum_5d,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pos.get('symbol', symbol),
                    pos.get('entry_date') or pos.get('entry_time'),
                    pos.get('entry_price'),
                    pos.get('qty') or pos.get('shares', 0),
                    pos.get('stop_loss') or pos.get('current_sl_price'),
                    pos.get('take_profit') or pos.get('tp_price'),
                    pos.get('peak_price') or pos.get('highest_price'),
                    pos.get('trough_price'),
                    1 if pos.get('trailing_active') or pos.get('trailing_stop') else 0,
                    pos.get('day_held') or pos.get('days_held', 0),
                    pos.get('sl_pct'),
                    pos.get('tp_pct'),
                    pos.get('entry_atr_pct') or pos.get('atr_pct'),
                    pos.get('sl_order_id'),
                    pos.get('tp_order_id'),
                    pos.get('entry_order_id'),
                    pos.get('sector'),
                    pos.get('source'),
                    pos.get('signal_score'),
                    pos.get('mode') or pos.get('entry_mode'),
                    pos.get('regime') or pos.get('entry_regime'),
                    pos.get('entry_rsi') or pos.get('rsi'),
                    pos.get('momentum_5d'),
                    datetime.now().isoformat()
                ))

                migrated += 1
                print(f"   ✅ {symbol}: migrated")

            except Exception as e:
                print(f"   ❌ {symbol}: {e}")
                skipped += 1

        conn.commit()
        conn.close()

        print()
        print(f"📊 Migration Summary:")
        print(f"   - Migrated: {migrated}")
        print(f"   - Skipped: {skipped}")
        print(f"   - Total: {len(positions)}")
        print()

        return migrated

    except Exception as e:
        print(f"❌ Error migrating positions: {e}")
        import traceback
        traceback.print_exc()
        return 0


def migrate_alerts():
    """Migrate alerts.json to database"""
    print("\n" + "="*70)
    print("  Migrating Alerts: JSON → Database")
    print("="*70)
    print()

    if not ALERTS_JSON.exists():
        print(f"⚠️  JSON file not found: {ALERTS_JSON}")
        print("   No alerts to migrate")
        return 0

    print(f"📂 Reading: {ALERTS_JSON}")

    try:
        with open(ALERTS_JSON) as f:
            data = json.load(f)

        alerts = data.get('alerts', [])
        print(f"   Found {len(alerts)} alerts")

        if len(alerts) == 0:
            print("   ✅ No alerts to migrate")
            return 0

        # Connect to database
        conn = None  # via get_session()
        cursor = conn.cursor()

        migrated = 0
        skipped = 0

        for alert in alerts:
            try:
                cursor.execute("""
                    INSERT INTO alerts (
                        level, message, timestamp, active,
                        resolved_at, metadata, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert.get('level', 'INFO'),
                    alert.get('message', ''),
                    alert.get('timestamp', datetime.now().isoformat()),
                    1 if alert.get('active', True) else 0,
                    alert.get('resolved_at'),
                    json.dumps(alert.get('metadata', {})) if alert.get('metadata') else None,
                    datetime.now().isoformat()
                ))

                migrated += 1

            except Exception as e:
                print(f"   ❌ Alert migration error: {e}")
                skipped += 1

        conn.commit()
        conn.close()

        print()
        print(f"📊 Migration Summary:")
        print(f"   - Migrated: {migrated}")
        print(f"   - Skipped: {skipped}")
        print(f"   - Total: {len(alerts)}")
        print()

        return migrated

    except Exception as e:
        print(f"❌ Error migrating alerts: {e}")
        import traceback
        traceback.print_exc()
        return 0


def verify_migration():
    """Verify data was migrated correctly"""
    print("\n" + "="*70)
    print("  Verifying Migration")
    print("="*70)
    print()

    try:
        conn = None  # via get_session()
        cursor = conn.cursor()

        # Check positions
        cursor.execute("SELECT COUNT(*) FROM active_positions")
        positions_count = cursor.fetchone()[0]
        print(f"📊 Positions in database: {positions_count}")

        if positions_count > 0:
            cursor.execute("""
                SELECT symbol, entry_price, qty, day_held
                FROM active_positions
                ORDER BY updated_at DESC
                LIMIT 5
            """)
            print("\n   Recent positions:")
            for row in cursor.fetchall():
                print(f"     - {row[0]}: ${row[1]:.2f} × {row[2]} shares (day {row[3]})")

        # Check alerts
        cursor.execute("SELECT COUNT(*) FROM alerts")
        alerts_count = cursor.fetchone()[0]
        print(f"\n📊 Alerts in database: {alerts_count}")

        if alerts_count > 0:
            cursor.execute("""
                SELECT level, COUNT(*) as count
                FROM alerts
                GROUP BY level
                ORDER BY level
            """)
            print("\n   Alerts by level:")
            for row in cursor.fetchall():
                print(f"     - {row[0]}: {row[1]}")

        conn.close()

        print()
        return True

    except Exception as e:
        print(f"❌ Verification error: {e}")
        return False


def main():
    """Run full migration"""
    print("\n" + "╔" + "="*68 + "╗")
    print("║" + " "*20 + "PHASE 4 MIGRATION" + " "*32 + "║")
    print("║" + " "*18 + "JSON → Database" + " "*36 + "║")
    print("╚" + "="*68 + "╝")

    # Check database exists
    if not DB_PATH.exists():
        print(f"\n❌ Database not found: {DB_PATH}")
        print("   Run: python scripts/create_phase4_tables.py")
        return False

    # Migrate positions
    positions_migrated = migrate_positions()

    # Migrate alerts
    alerts_migrated = migrate_alerts()

    # Verify
    success = verify_migration()

    # Summary
    print("\n" + "╔" + "="*68 + "╗")
    if success:
        print("║" + " "*22 + "✅ MIGRATION COMPLETE!" + " "*24 + "║")
    else:
        print("║" + " "*22 + "⚠️  MIGRATION PARTIAL" + " "*25 + "║")
    print("╚" + "="*68 + "╝")
    print()
    print(f"📊 Results:")
    print(f"   - Positions: {positions_migrated} migrated")
    print(f"   - Alerts: {alerts_migrated} migrated")
    print()

    if success:
        print("🎯 Next Steps:")
        print("   1. Test database access with repositories")
        print("   2. Update PositionRepository to database-backed")
        print("   3. Create AlertsRepository")
        print()
        print("⚠️  JSON files kept as backup:")
        print(f"   - {POSITIONS_JSON}")
        print(f"   - {ALERTS_JSON}")
        print("   (Do NOT delete until system is fully tested)")
        print()

    return success


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
