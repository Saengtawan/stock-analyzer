# Phase 4: Storage Strategy - PLAN

**Date:** 2026-02-12
**Status:** Planning
**Goal:** Consolidate storage, migrate JSON → SQLite
**Time Estimate:** 8-12 hours (reduced from 20-24h due to Phase 3 work)

---

## 🎯 Executive Summary

### What Phase 3 Already Accomplished:
- ✅ Repository pattern implemented (TradeRepository, PositionRepository, StockDataRepository)
- ✅ Type-safe models (Trade, Position, StockPrice)
- ✅ Connection pooling with DatabaseManager
- ✅ All critical components using repositories

### What's Left for Phase 4:
Phase 3's PositionRepository is still **JSON-backed** (reads/writes active_positions.json).
Phase 4 will migrate it to **database-backed** (SQLite table).

---

## 📊 Current Storage Analysis

### Databases (2 separate files):
```
1. trade_history.db (1.4M)
   - trades table (336 records)
   - Used by: TradeRepository ✅

2. database/stocks.db (38M)
   - stock_prices table (354K records)
   - Used by: StockDataRepository ✅
```

### JSON Files (runtime state):
```
1. active_positions.json (~5K)
   - Current: JSON file
   - Future: SQLite table in trade_history.db
   - Used by: PositionRepository (JSON-backed)

2. alerts.json (65K)
   - Current: JSON file
   - Future: SQLite table in trade_history.db
   - No repository yet - needs creation

3. Cache files (temp data)
   - Keep as JSON (appropriate for cache)
```

### Decision: **KEEP TWO DATABASES**

**Why not consolidate into one:**
1. **Different purposes:**
   - `trade_history.db`: Trading operations (trades, positions, alerts)
   - `stocks.db`: Market data (prices, technical indicators)

2. **Different access patterns:**
   - Trading: Write-heavy, real-time
   - Market data: Read-heavy, batch updates

3. **Simpler backup strategy:**
   - Trading: Daily backups (critical)
   - Market data: Weekly backups (replaceable)

4. **Better performance:**
   - Smaller databases = faster queries
   - Less lock contention

---

## 🎯 Phase 4 Goals (Revised)

### Goal 1: Migrate PositionRepository to Database ✅ PRIORITY
**Current:** JSON-backed (`active_positions.json`)
**Target:** Database-backed (`active_positions` table in `trade_history.db`)

**Benefits:**
- Atomic updates (no partial writes)
- ACID guarantees
- Query capabilities (filter, sort)
- Backup integration
- Consistent with other repositories

### Goal 2: Create AlertsRepository
**Current:** No repository, direct JSON access
**Target:** Database-backed (`alerts` table in `trade_history.db`)

**Benefits:**
- Track alerts history
- Query by level/status
- Automatic cleanup of old alerts
- Integration with monitoring

### Goal 3: Schema Updates
Add tables to `trade_history.db`:
- `active_positions` table
- `alerts` table
- Indexes for performance

---

## 📋 Implementation Plan

### Step 1: Create Database Schema (30 min)

**File:** `scripts/create_phase4_tables.py`

```sql
-- Add to trade_history.db

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
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL CHECK(level IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    resolved_at TEXT,
    metadata TEXT,  -- JSON blob for additional context
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(active);
CREATE INDEX IF NOT EXISTS idx_alerts_level ON alerts(level);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
```

### Step 2: Migrate Existing Data (1 hour)

**File:** `scripts/migrate_positions_to_db.py`

Steps:
1. Read current `active_positions.json`
2. Insert into `active_positions` table
3. Verify data integrity
4. Keep JSON as backup (don't delete yet)

### Step 3: Update PositionRepository (2 hours)

**File:** `src/database/repositories/position_repository.py`

Changes:
1. Change from JSON-backed to database-backed
2. Update `get_all()` to query table
3. Update `create()` to INSERT
4. Update `update()` to UPDATE
5. Update `delete()` to DELETE
6. Keep JSON fallback for safety

**Before (JSON-backed):**
```python
class PositionRepository:
    def __init__(self, json_file: str):
        self.json_file = json_file

    def get_all(self):
        with open(self.json_file) as f:
            data = json.load(f)
        return [Position.from_json_dict(p) for p in data['positions'].values()]
```

**After (Database-backed):**
```python
class PositionRepository:
    def __init__(self, db_name: str = 'trade_history'):
        self.db = get_db_manager(db_name)

    def get_all(self):
        rows = self.db.fetch_all("SELECT * FROM active_positions")
        return [Position.from_row(dict(row)) for row in rows]
```

### Step 4: Create AlertsRepository (2 hours)

**New File:** `src/database/repositories/alerts_repository.py`

Methods:
- `get_active()` - Get active alerts
- `get_by_level(level)` - Get alerts by severity
- `create(alert)` - Create new alert
- `resolve(alert_id)` - Mark alert as resolved
- `cleanup_old(days)` - Delete old resolved alerts

### Step 5: Update Application Code (2 hours)

Files to update:
1. `src/rapid_portfolio_manager.py` - Already partially done ✅
2. `src/auto_trading_engine.py` - Use database-backed PositionRepository
3. `src/web/app.py` - Add alerts endpoints

### Step 6: Migration Script & Testing (2 hours)

1. Create one-time migration script
2. Test data integrity
3. Verify all operations work
4. Performance testing

---

## 📊 Expected Benefits

### Performance:
| Operation | Before (JSON) | After (SQLite) | Improvement |
|-----------|---------------|----------------|-------------|
| Read positions | 5ms | 2ms | +60% faster |
| Update position | 8ms | 3ms | +62% faster |
| Query by symbol | N/A | 1ms | New capability |
| Atomic updates | No | Yes | ✅ ACID |

### Reliability:
- ✅ No partial writes (atomic transactions)
- ✅ ACID guarantees
- ✅ Backup integration
- ✅ Crash recovery

### Capabilities:
- ✅ Query positions by any field
- ✅ Track position history
- ✅ Alert history and analytics
- ✅ Consistent with other data

---

## ⚠️ Migration Risks & Mitigation

### Risk 1: Data Loss During Migration
**Mitigation:**
- Keep JSON files as backup
- Verify data before deleting JSON
- Rollback plan if migration fails

### Risk 2: Application Downtime
**Mitigation:**
- Graceful fallback to JSON
- Test thoroughly before deployment
- Blue-green deployment strategy

### Risk 3: Performance Regression
**Mitigation:**
- Benchmark before/after
- Add indexes for common queries
- Connection pooling already implemented

---

## 📋 Implementation Checklist

### Phase 4A: Schema & Migration (3-4h)
- [ ] Create `active_positions` table
- [ ] Create `alerts` table
- [ ] Migrate existing positions to DB
- [ ] Migrate existing alerts to DB
- [ ] Verify data integrity

### Phase 4B: Repository Updates (3-4h)
- [ ] Update PositionRepository to database-backed
- [ ] Create AlertsRepository
- [ ] Add comprehensive tests
- [ ] Verify backward compatibility

### Phase 4C: Integration (2-3h)
- [ ] Update application code
- [ ] Add API endpoints for alerts
- [ ] Integration testing
- [ ] Performance verification

---

## 📊 Success Criteria

### Must Have:
- ✅ All positions migrated to database
- ✅ Zero data loss
- ✅ All tests passing
- ✅ Performance equal or better
- ✅ Backward compatible (JSON fallback)

### Nice to Have:
- ✅ Alerts repository working
- ✅ API endpoints for alerts
- ✅ Query capabilities demonstrated

---

## 🎯 Time Estimate (Revised)

**Original Estimate:** 20-24 hours (full migration)
**Revised Estimate:** 8-12 hours (JSON → DB for positions & alerts)

**Breakdown:**
- Schema creation: 0.5h
- Data migration: 1h
- PositionRepository update: 2h
- AlertsRepository creation: 2h
- Application updates: 2h
- Testing & verification: 2h
- Documentation: 0.5h
- **Buffer:** 2h

**Total:** 10-12 hours

---

## 📝 Next Steps

1. **Start with Schema Creation** (30 min)
   - Create tables in trade_history.db
   - Add indexes

2. **Migrate Positions** (1 hour)
   - Run migration script
   - Verify data

3. **Update PositionRepository** (2 hours)
   - Change to database-backed
   - Test thoroughly

4. **Create AlertsRepository** (2 hours)
   - New repository
   - Migrate alerts.json

5. **Integration & Testing** (2-3 hours)
   - Update applications
   - Full testing

---

**Status:** Ready to start
**First Task:** Create database schema
**Estimated Session:** 3-4 hours for Phase 4A
