#!/usr/bin/env python3
"""
Migrate Loss Counters from JSON to Database
Imports data/loss_counters.json into trade_history.db

Run: python3 scripts/migrate_loss_counters_json_to_db.py
"""

import sys
import os
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from database.repositories.loss_tracking_repository import LossTrackingRepository


def main():
    """Main migration function"""
    print("="*80)
    print("LOSS COUNTERS: JSON → DATABASE MIGRATION")
    print("="*80)

    # Initialize repository
    repo = LossTrackingRepository()
    print(f"Database: {repo.db_path}")

    # Load JSON file
    json_file = project_root / "data" / "loss_counters.json"
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

    # Show current JSON data
    print(f"\n" + "="*80)
    print("CURRENT JSON DATA")
    print("="*80)
    print(json.dumps(json_data, indent=2))

    # Migrate to database
    print(f"\n" + "="*80)
    print("IMPORTING TO DATABASE")
    print("="*80)

    success = repo.import_from_json(json_data)
    if success:
        print(f"✅ Import successful")
    else:
        print(f"❌ Import failed")
        return 1

    # Verify
    print(f"\n" + "="*80)
    print("VERIFICATION")
    print("="*80)

    state = repo.get_state()
    print(f"\nMain tracking:")
    print(f"  - Consecutive losses: {state['consecutive_losses']}")
    print(f"  - Weekly P&L: ${state['weekly_realized_pnl']:.2f}")
    print(f"  - Cooldown until: {state['cooldown_until'] or 'None'}")
    print(f"  - Weekly reset: {state['weekly_reset_date'] or 'None'}")

    sectors = repo.get_all_sector_losses()
    print(f"\nSector tracking ({len(sectors)} sectors):")
    for sector, data in sectors.items():
        cooldown = data['cooldown_until'] or 'None'
        print(f"  - {sector}: {data['losses']} losses, cooldown={cooldown}")

    # Risk status
    risk = repo.get_risk_status()
    print(f"\nRisk status:")
    print(f"  - Risk level: {risk.get('risk_level', 'N/A')}")
    print(f"  - Cooldown days remaining: {risk.get('cooldown_days_remaining', 0):.0f}")

    # Summary
    print(f"\n" + "="*80)
    print("MIGRATION COMPLETE")
    print("="*80)
    print(f"✅ Main tracking: {state['consecutive_losses']} consecutive losses")
    print(f"✅ Sector tracking: {len(sectors)} sectors")
    print(f"\nNext steps:")
    print(f"1. Verify data integrity (check database)")
    print(f"2. Update auto_trading_engine.py to use LossTrackingRepository")
    print(f"3. Update web/app.py if needed")
    print(f"4. Test for 7 days")
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
