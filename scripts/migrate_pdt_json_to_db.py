#!/usr/bin/env python3
"""
Migrate PDT Tracking from JSON to Database
Imports data/pdt_entry_dates.json into trade_history.db

Run: python3 scripts/migrate_pdt_json_to_db.py
"""

import sys
import os
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from database.repositories.pdt_repository import PDTRepository


def main():
    """Main migration function"""
    print("="*80)
    print("PDT TRACKING: JSON → DATABASE MIGRATION")
    print("="*80)

    # Initialize repository
    repo = PDTRepository()
    print(f"Database: {repo.db_path}")

    # Load JSON file
    json_file = project_root / "data" / "pdt_entry_dates.json"
    print(f"JSON File: {json_file}")

    if not json_file.exists():
        print(f"❌ JSON file not found: {json_file}")
        print("   Nothing to migrate.")
        return 0

    try:
        with open(json_file, 'r') as f:
            json_data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to read JSON file: {e}")
        return 1

    print(f"\nJSON entries: {len(json_data)}")
    for symbol, entry_date in json_data.items():
        print(f"  - {symbol}: {entry_date}")

    # Migrate to database
    print(f"\nImporting to database...")
    count = repo.import_from_json(json_data)
    print(f"✅ Imported {count}/{len(json_data)} entries")

    # Verify
    print(f"\n" + "="*80)
    print("VERIFICATION")
    print("="*80)

    db_entries = repo.get_all_entries()
    print(f"\nDatabase entries: {len(db_entries)}")
    for symbol, entry_date in db_entries.items():
        print(f"  - {symbol}: {entry_date}")

    # Check active restrictions
    active = repo.get_active_restrictions()
    if active:
        print(f"\n⚠️  Active PDT restrictions (entered today):")
        for symbol in active:
            print(f"  - {symbol} (cannot sell today)")
    else:
        print(f"\n✅ No active PDT restrictions (all symbols can be sold)")

    # Summary
    print(f"\n" + "="*80)
    print("MIGRATION COMPLETE")
    print("="*80)
    print(f"✅ Total entries migrated: {count}")
    print(f"\nNext steps:")
    print(f"1. Verify data integrity (check database)")
    print(f"2. Update pdt_smart_guard.py to use PDTRepository")
    print(f"3. Update auto_trading_engine.py to use PDTRepository")
    print(f"4. Test for 3 days")
    print(f"5. Archive JSON file: mv {json_file} {json_file}.backup")
    print("="*80)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
