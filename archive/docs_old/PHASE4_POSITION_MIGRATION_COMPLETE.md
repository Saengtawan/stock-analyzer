# Phase 4: Position Storage Migration - COMPLETE ✅

## Summary
เปลี่ยนการเก็บ position data ให้ใช้ **Database เป็น single source of truth** แทน JSON

## Problem (Before)

### Dual Storage with Sync Issues:
- `data/active_positions.json` - Engine เขียนหลัก (atomic write)
- `trade_history.db/active_positions` - Engine sync แบบ "best effort"
- **ปัญหา:** sync fail silently → DB stale data (เคยเจอ AIT stale data)

### Architecture (Before):
```
auto_trading_engine
    ↓
BUY/SELL → positions (in-memory)
    ↓
_save_positions_state() → JSON (primary)
    ↓
_sync_active_positions_db() → DB (best effort, direct SQL)
                              ❌ fail silently

position_manager → อ่านจาก JSON ❌
data_manager → อ่านจาก JSON ❌
web app → อ่านจาก DB ✅ (inconsistent!)
```

## Solution (After)

### Single Source of Truth:
- `trade_history.db/active_positions` - **Primary storage**
- `data/active_positions.json` - Legacy backup (optional, can archive)

### Architecture (After):
```
auto_trading_engine
    ↓
BUY/SELL → positions (in-memory)
    ↓
_save_positions_state() → JSON (legacy backup)
    ↓
_sync_active_positions_db() → PositionRepository.sync_positions_scoped()
    ↓
Database (single source of truth) ✅
    ↓
position_manager.load() → DB ✅
data_manager.get_positions() → DB ✅
web app → DB ✅
```

---

## Changes Made

### Step 1: Fix bugs in position_repository.py ✅
**Already fixed before** - No changes needed
- Line 342: Uses `_save_to_database()` ✅
- Line 367: Uses `_save_to_database([])` ✅

### Step 2: Enhance PositionRepository ✅
**File:** `src/database/repositories/position_repository.py`

**Added new method** `sync_positions_scoped()` (line 369-454):
```python
def sync_positions_scoped(self, positions: List[Position], source_filter: List[str]) -> bool:
    """
    Sync positions for specific sources only (scoped sync).

    - Deletes positions where source IN source_filter AND symbol NOT IN new positions
    - Upserts all positions in the list
    - Does NOT touch positions with other sources (e.g., rapid_trader)
    """
```

**Why scoped?**
- Engine owns: `dip_bounce`, `overnight_gap`, `post_earnings_momentum`
- Rapid Trader owns: `rapid_trader`
- Scoped sync prevents engine from deleting rapid_trader positions

**Modified auto_trading_engine.py** `_sync_active_positions_db()` (line 931-973):
```python
# OLD: Direct SQL execute (50+ lines)
repo.db.execute(f"DELETE FROM active_positions WHERE source IN ...")
repo.db.execute("INSERT OR REPLACE INTO active_positions ...")

# NEW: Use PositionRepository (clean, maintainable)
db_positions = []
for sym, pos in positions_snapshot.items():
    db_pos = DBPosition(...)  # Convert ManagedPosition → DBPosition
    db_positions.append(db_pos)

repo.sync_positions_scoped(db_positions, self._ENGINE_SOURCES)
```

### Step 3: Migrate Readers to DB ✅
**Already done before** - Verified only

**File:** `src/position_manager.py`
- `load()` (line 116-145): Reads from DB via PositionRepository ✅
- `save()` (line 147-149): No-op (engine writes DB) ✅

**File:** `src/api/data_manager.py`
- `get_positions()` (line 596-622): Fallback to DB ✅
- `get_position()` (line 644-667): Fallback to DB ✅
- Priority: Broker API first (if available) → DB fallback

---

## Field Mapping: ManagedPosition ↔ DBPosition

| Engine (ManagedPosition) | Database (Position) |
|--------------------------|---------------------|
| `current_sl_price` | `stop_loss` |
| `entry_time` | `entry_date` |
| `trailing_active` | `trailing_stop` |
| `tp_price` | `take_profit` |
| `entry_mode` | `mode` |
| `entry_regime` | `regime` |
| `days_held` | `day_held` |
| `atr_pct` | `entry_atr_pct` |

---

## Verification

### Test Script: `scripts/test_position_db_integration.py`

**Test Results:**
```
✅ Found 2 positions: FAST, KHC (source=dip_bounce)
✅ Scoped sync successful (created TEST1, cleaned up)
✅ rapid_trader positions protected (scoped sync works)
```

### Manual Verification:
```bash
# 1. Run test
python3 scripts/test_position_db_integration.py

# 2. Check current positions
sqlite3 data/trade_history.db "SELECT symbol, source, qty, entry_price FROM active_positions"

# 3. Verify after BUY/SELL
# Buy a stock → check DB updated immediately (no restart needed)
# Sell a stock → check DB removed immediately
```

---

## Benefits

### Before vs After:
| Aspect | Before | After |
|--------|--------|-------|
| **Source of truth** | JSON (engine) + DB (web) ❌ | DB only ✅ |
| **Consistency** | Can diverge (sync fails) ❌ | Always consistent ✅ |
| **Error handling** | Fail silently ❌ | Repository pattern (logged) ✅ |
| **Code quality** | Direct SQL (50+ lines) ❌ | Repository method (clean) ✅ |
| **Rapid Trader** | Risk of deletion ❌ | Protected (scoped) ✅ |

### Advantages:
1. **Single source of truth** - No more JSON/DB divergence
2. **Immediate consistency** - Web UI sees updates without restart
3. **Better error handling** - Repository logs all failures
4. **Scoped writes** - Engine doesn't touch rapid_trader positions
5. **Cleaner code** - Repository abstraction vs direct SQL

---

## Files Modified

| File | Lines | Change |
|------|-------|--------|
| `src/database/repositories/position_repository.py` | 369-454 | Added `sync_positions_scoped()` |
| `src/auto_trading_engine.py` | 931-973 | Use PositionRepository instead of direct SQL |
| `scripts/test_position_db_integration.py` | NEW | Integration test script |

## Files NOT Modified (Already Migrated)
- `src/position_manager.py` ✅ (already reads DB)
- `src/api/data_manager.py` ✅ (already reads DB)

---

## What's Next (Optional)

### Step 4: Archive JSON Files (after 1-2 days monitoring)
หลังยืนยันว่า DB ทำงานได้ดี:

1. **Archive JSON:**
   ```bash
   mkdir -p data/archive
   mv data/active_positions.json data/archive/active_positions.json.backup_$(date +%Y%m%d)
   ```

2. **Optional: Remove JSON write code**
   - `auto_trading_engine.py` → remove `_save_positions_state()` JSON write
   - Keep `atomic_write_json()` utility (used elsewhere)

3. **Update docs:**
   - Remove references to `active_positions.json`
   - Update architecture diagrams

### Monitoring Checklist:
- [ ] Engine restarts correctly (loads positions from DB)
- [ ] BUY signal → position appears in DB immediately
- [ ] SELL signal → position removed from DB immediately
- [ ] Web UI shows positions correctly (no stale data)
- [ ] Rapid Trader positions not affected by engine sync

---

## Success Criteria ✅

- [x] PositionRepository has `sync_positions_scoped()` method
- [x] Engine uses PositionRepository (no direct SQL)
- [x] Scoped sync protects rapid_trader positions
- [x] position_manager reads from DB
- [x] data_manager reads from DB
- [x] Integration test passes
- [x] Current positions verified (FAST, KHC in DB)

---

**Status:** ✅ COMPLETE (2026-02-21)

**Next Migration:** Pre-filter data (already done in Phase 2B)

**Future Work:** Archive JSON files after monitoring period
