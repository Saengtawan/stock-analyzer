#!/usr/bin/env python3
"""
Migrate Outcome Tracker data from JSON files to Database
Imports all JSON files from outcomes/ directory into trade_history.db

Run: python3 scripts/migrate_outcomes_json_to_db.py
"""

import sys
import os
import json
from pathlib import Path
from typing import List, Dict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from database.repositories.outcome_repository import OutcomeRepository


def load_json_files(directory: str, prefix: str) -> List[Dict]:
    """Load all JSON files matching prefix from directory"""
    outcomes = []
    outcomes_dir = Path(directory)

    if not outcomes_dir.exists():
        print(f"❌ Directory not found: {directory}")
        return []

    files = sorted(outcomes_dir.glob(f"{prefix}_*.json"))

    for file_path in files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    outcomes.extend(data)
                    print(f"✅ Loaded {len(data)} records from {file_path.name}")
                else:
                    print(f"⚠️  Skipping {file_path.name}: not a list")
        except Exception as e:
            print(f"❌ Error loading {file_path.name}: {e}")

    return outcomes


def migrate_sell_outcomes(repo: OutcomeRepository, outcomes_dir: str) -> int:
    """Migrate sell_outcomes from JSON to DB"""
    print("\n" + "="*80)
    print("MIGRATING SELL OUTCOMES")
    print("="*80)

    sell_outcomes = load_json_files(outcomes_dir, "sell_outcomes")

    if not sell_outcomes:
        print("No sell outcomes to migrate")
        return 0

    print(f"\nImporting {len(sell_outcomes)} sell outcomes...")
    count = repo.save_sell_outcomes_batch(sell_outcomes)
    print(f"✅ Imported {count}/{len(sell_outcomes)} sell outcomes")

    return count


def migrate_signal_outcomes(repo: OutcomeRepository, outcomes_dir: str) -> int:
    """Migrate signal_outcomes from JSON to DB"""
    print("\n" + "="*80)
    print("MIGRATING SIGNAL OUTCOMES")
    print("="*80)

    signal_outcomes = load_json_files(outcomes_dir, "signal_outcomes")

    if not signal_outcomes:
        print("No signal outcomes to migrate")
        return 0

    print(f"\nImporting {len(signal_outcomes)} signal outcomes...")
    count = repo.save_signal_outcomes_batch(signal_outcomes)
    print(f"✅ Imported {count}/{len(signal_outcomes)} signal outcomes")

    return count


def migrate_rejected_outcomes(repo: OutcomeRepository, outcomes_dir: str) -> int:
    """Migrate rejected_outcomes from JSON to DB"""
    print("\n" + "="*80)
    print("MIGRATING REJECTED OUTCOMES")
    print("="*80)

    rejected_outcomes = load_json_files(outcomes_dir, "rejected_outcomes")

    if not rejected_outcomes:
        print("No rejected outcomes to migrate")
        return 0

    # Map JSON field names to DB schema
    # JSON uses: reject_id, reject_date, reject_type, reject_detail, reject_price
    # DB uses: scan_id, scan_date, scan_type, rejection_reason, scan_price
    mapped_outcomes = []
    for outcome in rejected_outcomes:
        mapped = {
            'scan_id': outcome.get('reject_id'),
            'scan_date': outcome.get('reject_date'),
            'scan_type': outcome.get('reject_type'),
            'rejection_reason': outcome.get('reject_detail'),
            'symbol': outcome.get('symbol'),
            'scan_price': outcome.get('reject_price'),
            'signal_rank': outcome.get('signal_rank'),
            'score': outcome.get('signal_score'),
            'signal_source': outcome.get('signal_source', 'dip_bounce'),
            'outcome_1d': outcome.get('outcome_1d'),
            'outcome_3d': outcome.get('outcome_3d'),
            'outcome_5d': outcome.get('outcome_5d'),
            'outcome_max_gain_5d': outcome.get('outcome_max_gain_5d'),
            'outcome_max_dd_5d': outcome.get('outcome_max_dd_5d'),
            'tracked_at': outcome.get('tracked_at')
        }
        mapped_outcomes.append(mapped)

    print(f"\nImporting {len(mapped_outcomes)} rejected outcomes (with field mapping)...")
    count = repo.save_rejected_outcomes_batch(mapped_outcomes)
    print(f"✅ Imported {count}/{len(mapped_outcomes)} rejected outcomes")

    return count


def verify_migration(repo: OutcomeRepository):
    """Verify data was imported correctly"""
    print("\n" + "="*80)
    print("VERIFICATION")
    print("="*80)

    import sqlite3
    conn = None  # via get_session()

    # Count records
    sell_count = conn.execute("SELECT COUNT(*) FROM sell_outcomes").fetchone()[0]
    signal_count = conn.execute("SELECT COUNT(*) FROM signal_outcomes").fetchone()[0]
    rejected_count = conn.execute("SELECT COUNT(*) FROM rejected_outcomes").fetchone()[0]

    print(f"\nDatabase record counts:")
    print(f"  - sell_outcomes: {sell_count}")
    print(f"  - signal_outcomes: {signal_count}")
    print(f"  - rejected_outcomes: {rejected_count}")
    print(f"  - TOTAL: {sell_count + signal_count + rejected_count}")

    # Sample records
    print(f"\nSample sell outcome:")
    sell_sample = conn.execute("SELECT * FROM sell_outcomes LIMIT 1").fetchone()
    if sell_sample:
        print(f"  trade_id: {sell_sample[1]}, symbol: {sell_sample[2]}, sell_date: {sell_sample[3]}")

    print(f"\nSample signal outcome:")
    signal_sample = conn.execute("SELECT * FROM signal_outcomes LIMIT 1").fetchone()
    if signal_sample:
        print(f"  scan_id: {signal_sample[1]}, symbol: {signal_sample[2]}, scan_date: {signal_sample[3]}")

    print(f"\nSample rejected outcome:")
    rejected_sample = conn.execute("SELECT * FROM rejected_outcomes LIMIT 1").fetchone()
    if rejected_sample:
        print(f"  scan_id: {rejected_sample[1]}, symbol: {rejected_sample[2]}, rejection_reason: {rejected_sample[5]}")

    conn.close()


def main():
    """Main migration function"""
    print("="*80)
    print("OUTCOME TRACKER: JSON → DATABASE MIGRATION")
    print("="*80)

    # Initialize repository
    repo = OutcomeRepository()
    print(f"Database: {repo.db_path}")

    # Define outcomes directory
    outcomes_dir = str(project_root / "outcomes")
    print(f"JSON Directory: {outcomes_dir}")

    # Migrate each type
    sell_count = migrate_sell_outcomes(repo, outcomes_dir)
    signal_count = migrate_signal_outcomes(repo, outcomes_dir)
    rejected_count = migrate_rejected_outcomes(repo, outcomes_dir)

    # Verify
    verify_migration(repo)

    # Summary
    print("\n" + "="*80)
    print("MIGRATION COMPLETE")
    print("="*80)
    print(f"✅ Total records migrated: {sell_count + signal_count + rejected_count}")
    print(f"   - Sell outcomes: {sell_count}")
    print(f"   - Signal outcomes: {signal_count}")
    print(f"   - Rejected outcomes: {rejected_count}")
    print("\nNext steps:")
    print("1. Verify data integrity: python3 scripts/verify_outcome_data.py")
    print("2. Update outcome_tracker.py to use OutcomeRepository")
    print("3. Test cron job with new DB writer")
    print("4. Archive JSON files after confirming DB works")
    print("="*80)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
