# Legacy JSON Files Archive

**Date:** 2026-02-24  
**Reason:** Database migration complete - all data now in DB as single source of truth

## Archived Files

### 1. pre_filtered.json (158KB)
- **Last Modified:** 2026-02-21 11:12
- **Purpose:** Pre-filtered stock pool from evening scans
- **Status:** No longer written (screeners now read from DB)
- **Migration:** Completed to `pre_filter_sessions` + `filtered_stocks` tables
- **Replacement:** PreFilterRepository.get_filtered_pool()

### 2. pdt_entry_dates.json (49 bytes)
- **Last Modified:** 2026-02-19
- **Purpose:** PDT (Pattern Day Trader) tracking
- **Status:** Migrated to database
- **Migration:** Completed to `pdt_tracking` table (2 entries)
- **Replacement:** PDTRepository

### 3. loss_counters.json (684 bytes)
- **Last Modified:** 2026-02-22
- **Purpose:** Loss tracking and risk management
- **Status:** Migrated to database
- **Migration:** Completed to `loss_tracking` + `sector_loss_tracking` tables
- **Replacement:** LossTrackingRepository

### 4. alerts.json (65KB)
- **Last Modified:** 2026-02-24 04:00
- **Purpose:** Trading alerts and notifications
- **Status:** Legacy (no longer written)
- **Migration:** Database has 2,765 records
- **Replacement:** AlertsRepository

## Database Status

All data types now use database as single source of truth:
- ✅ 11/11 data types migrated
- ✅ All repositories implemented
- ✅ JSON writes removed from code
- ✅ System verified working with DB

## Restoration (if needed)

These files are kept as backup. To restore if absolutely necessary:

```bash
cp archive/2026-02-24_legacy_json/[filename] data/
```

**Warning:** Restoring these files will NOT make them active again. The code no longer writes to these files. Database is the only active storage.

## Verification Period

Migration completed and verified:
- Engine restart: ✅ (2026-02-24 14:44)
- DB read/write: ✅ (all systems working)
- Pre-filter scan: ✅ (Session 24: 232 stocks)
- Position sync: ✅ (0 positions loaded from DB)

Safe to keep archived permanently.
