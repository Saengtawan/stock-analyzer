# TODO: Single Source of Truth - Remaining JSON → DB Migration

**Date:** 2026-02-21
**Status:** Analysis Complete

---

## ✅ Already Migrated to Database

| Data | JSON File (Old) | DB Table (New) | Records | Status |
|------|-----------------|----------------|---------|--------|
| Positions | `active_positions.json` | `active_positions` | 2 | ✅ DELETED |
| Trades | `trade_logs/*.json` | `trades` | 498 | ✅ LEGACY (not written) |
| Signals | N/A | `trading_signals` | 212 | ✅ DB ONLY |
| Scan Sessions | N/A | `scan_sessions` | - | ✅ DB ONLY |
| Execution | N/A | `execution_history` | 419 | ✅ DB ONLY |
| Alerts | `alerts.json` | `alerts` | 2,641 | ✅ LEGACY (not written) |
| Outcomes | `outcomes/*.json` | `sell/signal/rejected_outcomes` | 2,546 | ✅ MIGRATED |
| Signal Queue | N/A | `signal_queue` | - | ✅ DB ONLY |
| Pre-filter | N/A | `pre_filter_sessions`, `filtered_stocks` | - | ✅ DB ONLY |

**Total: 9 data types fully migrated ✅**

---

## ⚠️ Still Using JSON (Needs Migration)

### **Priority: HIGH** 🔴

#### 1. Loss Counters & Risk Management
**Current:** `data/loss_counters.json` (684 bytes)
```json
{
  "consecutive_losses": 0,
  "weekly_realized_pnl": -34.18,
  "cooldown_until": "2026-02-13",
  "weekly_reset_date": "2026-02-09",
  "sector_loss_tracker": {
    "healthcare": {"losses": 1, "cooldown_until": null},
    ...
  },
  "saved_at": "2026-02-17T21:43:59"
}
```

**Why migrate:**
- Critical for risk management (consecutive loss tracking)
- Used for trading cooldowns (consecutive_losses >= 3 → pause)
- Sector-specific loss tracking
- **Single source of truth** needed for multi-process access

**Used by:**
- `src/auto_trading_engine.py` (read/write)
- `src/web/app.py` (read for UI display)

**Proposed DB schema:**
```sql
CREATE TABLE loss_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    consecutive_losses INTEGER NOT NULL DEFAULT 0,
    weekly_realized_pnl REAL NOT NULL DEFAULT 0.0,
    cooldown_until TEXT,  -- ISO date
    weekly_reset_date TEXT,  -- ISO date
    updated_at TEXT NOT NULL,

    -- Single row table (id=1 always)
    CONSTRAINT single_row CHECK (id = 1)
);

CREATE TABLE sector_loss_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sector TEXT NOT NULL UNIQUE,
    losses INTEGER NOT NULL DEFAULT 0,
    cooldown_until TEXT,  -- ISO date
    updated_at TEXT NOT NULL
);
```

**Migration complexity:** MEDIUM
- Need to update auto_trading_engine.py
- Need to update web/app.py
- Atomic read/write required (use transactions)

---

#### 2. PDT (Pattern Day Trader) Tracking
**Current:** `data/pdt_entry_dates.json` (49 bytes)
```json
{
  "FAST": "2026-02-14",
  "KHC": "2026-02-19"
}
```

**Why migrate:**
- Regulatory compliance data (SEC Pattern Day Trader rules)
- Tracks symbols with same-day buy/sell to avoid PDT violations
- **Single source of truth** needed for compliance

**Used by:**
- `src/pdt_smart_guard.py` (read/write)
- `src/auto_trading_engine.py` (read)

**Proposed DB schema:**
```sql
CREATE TABLE pdt_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    entry_date TEXT NOT NULL,  -- ISO date
    exit_date TEXT,  -- NULL if still in position
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX idx_pdt_symbol ON pdt_tracking(symbol);
CREATE INDEX idx_pdt_entry_date ON pdt_tracking(entry_date);
```

**Migration complexity:** LOW
- Simple key-value structure
- Update pdt_smart_guard.py
- Update auto_trading_engine.py

---

### **Priority: MEDIUM** 🟡

#### 3. Heartbeat / System Health
**Current:** `data/heartbeat.json` (126 bytes)
```json
{
  "timestamp": "2026-02-21T03:59:53",
  "alive": true,
  "state": "monitoring",
  "positions": 2,
  "running": true
}
```

**Why migrate (or not):**
- ✅ **Good reason to keep JSON:** Temporary status, written every 5 seconds
- ✅ **Good reason to migrate:** Single source for monitoring tools
- 🤔 **Decision:** Keep as JSON (high-frequency writes, temporary data)

**Alternative:** Use DB but with write throttling (1 write/minute max)

**Used by:**
- `src/auto_trading_engine.py` (write every 5s)
- `src/web/app.py` (read for status indicator)
- External monitoring scripts

**Action:** **KEEP AS JSON** (or add DB table with 1-minute throttle)

---

## 📁 Legacy JSON Files (Can Archive)

These files are **not written anymore** by the engine:

```bash
# Archive these after verifying DB has all data
data/alerts.json                  # 65KB - legacy (DB has 2,641 records)
trade_logs/trade_log_*.json       # 18K lines - legacy (DB has 498 records)
outcomes/*.json                   # Migrated to DB (keep 30 days, then archive)
```

**Recommended action:**
```bash
# After 30-day verification period:
mkdir -p archive/2026-02-21_json_migration
mv data/alerts.json archive/2026-02-21_json_migration/
mv trade_logs/*.json archive/2026-02-21_json_migration/trade_logs/
# outcomes already archived via migration script
```

---

## 🟢 OK to Keep as JSON (Cache/Config)

These files are **correctly using JSON:**

```
✅ data/pre_filter_status.json       - Pre-filter run status (OK)
✅ data/cron_status.json             - Cron job monitoring (OK)
✅ data/cron_schedule.json           - Cron schedule config (OK)
✅ data/cache/*.json                 - Cache files (temporary, OK)
✅ data/*_cache.json                 - Various caches (OK)
✅ data/predictions/*.json           - AI predictions (OK)
✅ data/portfolio/*.json             - Portfolio snapshots (OK)
✅ data/logs/app_*.json              - Application logs (OK)
✅ Backtest result JSON files        - Historical analysis (OK)
```

**Reason:** These are either config files, cache files, or historical snapshots (not operational data).

---

## 📊 Migration Priority Summary

| Priority | Data | Current Size | Impact if Fails | Complexity |
|----------|------|--------------|-----------------|------------|
| 🔴 HIGH | Loss Counters | 684 bytes | Trading halts incorrectly | MEDIUM |
| 🔴 HIGH | PDT Tracking | 49 bytes | Regulatory violations | LOW |
| 🟡 MEDIUM | Heartbeat | 126 bytes | Monitoring blind spots | LOW |

---

## 🚀 Implementation Plan

### **Phase 1: PDT Tracking** (Easiest first)
**Effort:** 2-3 hours
**Files to modify:**
- Create migration: `004_create_pdt_tracking_table.sql`
- Create repository: `src/database/repositories/pdt_repository.py`
- Update: `src/pdt_smart_guard.py`
- Update: `src/auto_trading_engine.py`

**Steps:**
1. Create DB schema
2. Create PDTRepository with get/set methods
3. Migrate existing JSON data (2 entries)
4. Update pdt_smart_guard.py to use repository
5. Test for 3 days
6. Archive JSON file

---

### **Phase 2: Loss Tracking** (More complex)
**Effort:** 4-6 hours
**Files to modify:**
- Create migration: `005_create_loss_tracking_tables.sql`
- Create repository: `src/database/repositories/loss_tracking_repository.py`
- Update: `src/auto_trading_engine.py` (multiple locations)
- Update: `src/web/app.py`

**Steps:**
1. Create DB schema (loss_tracking + sector_loss_tracking)
2. Create LossTrackingRepository
3. Migrate existing JSON data
4. Update auto_trading_engine.py read/write logic
5. Update web/app.py UI display
6. Test cooldown logic thoroughly
7. Archive JSON file after 7-day verification

---

### **Phase 3: Heartbeat (Optional)**
**Effort:** 1-2 hours
**Decision:** Keep as JSON OR migrate with throttling

If migrating:
- Create `system_health` table
- Throttle writes to 1/minute (from current 1/5s)
- Keep recent 1000 entries only (auto-cleanup)

**Recommendation:** Keep as JSON (high-frequency temporary data)

---

## ✅ Success Criteria

After migration complete:

- [ ] All operational data in database
- [ ] No silent failures (fail-fast on DB errors)
- [ ] Repository pattern consistent across all tables
- [ ] Legacy JSON files archived (not deleted)
- [ ] 30-day verification period passed
- [ ] Documentation updated (MEMORY.md)
- [ ] All tests passing

**Final state:** True single source of truth for all trading data ✅

---

## 📝 Notes

**Why this matters:**
- Prevents data inconsistency (2 sources = 2 truths)
- Enables multi-process access (no file locking)
- Supports atomic transactions (no partial writes)
- Simplifies monitoring & debugging
- Production-grade reliability

**What's already done:**
- Position storage ✅ (v6.20)
- Outcome tracking ✅ (v1.2)
- Signals & trades ✅ (already in DB)

**What's left:**
- Loss counters (HIGH priority)
- PDT tracking (HIGH priority)
- Heartbeat (MEDIUM priority, optional)

**Estimated total effort:** 8-12 hours for all 3 phases
