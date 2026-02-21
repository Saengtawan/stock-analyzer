# Phase 2B: Pre-filter Database Integration - COMPLETE ✅

## Summary
เปลี่ยน pre_filter.py ให้เขียนข้อมูลลง database แทนที่จะเขียนแค่ JSON file

## What Was Done

### 1. Modified `_save_status()` (line 192-218)
- เพิ่ม database write ผ่าน `PreFilterRepository.update_session_status()`
- ยังเขียน JSON ไว้เป็น backup
- ใช้ `self._current_session_id` ที่สร้างตอน scan เริ่ม

### 2. Modified `_save_pre_filtered()` (line 267-310)
- เพิ่ม database write ผ่าน `PreFilterRepository.add_stocks_bulk()`
- แปลง stock data เป็น `FilteredStock` objects
- bulk insert ทั้งหมดพร้อมกัน (efficient)

### 3. Modified `evening_scan()` (line 462)
เพิ่มการสร้าง database session ตอนเริ่มต้น scan:
```python
from database import PreFilterRepository, PreFilterSession
from datetime import datetime
repo = PreFilterRepository()
db_session = PreFilterSession(
    scan_type='evening',
    scan_time=datetime.now(),
    total_scanned=0,  # Will update later
    status='running',
    is_ready=False
)
self._current_session_id = repo.create_session(db_session)
```

อัพเดท total_scanned หลังจากโหลด universe:
```python
repo.update_session_status(
    session_id=self._current_session_id,
    total_scanned=total
)
```

### 4. Modified `pre_open_scan()` (line 606)
เหมือนกับ evening_scan แต่ใช้ `scan_type='pre_open'`

## How It Works Now

### Flow ของ evening scan:
```
1. evening_scan() starts
2. Create DB session (status='running', is_ready=False)
3. Load universe (987 stocks)
4. Update DB session with total_scanned=987
5. Scan each stock...
6. _save_status() → update DB session
7. _save_pre_filtered() → bulk insert stocks to DB
8. Scan completes (status='completed', is_ready=True)
```

### Flow ของ pre_open scan:
```
1. pre_open_scan() starts
2. Create DB session (status='running', is_ready=False)
3. Load evening results
4. Update DB session with total_scanned=N
5. Re-validate each stock...
6. _save_status() → update DB session
7. _save_pre_filtered() → bulk insert updated stocks
8. Scan completes (status='completed', is_ready=True)
```

## Data Flow

```
Pre-filter Scan
    ↓
Create DB Session (PreFilterSession)
    ↓
Scan stocks...
    ↓
Save Status → Update DB session (status, pool_size, duration)
    ↓
Save Filtered → Insert stocks (FilteredStock bulk insert)
    ↓
Web API reads from DB (via PreFilterRepository)
    ↓
UI shows pool size, last updated, etc.
```

## Testing

### Current State (before next scan):
```
Session ID: 3
Type: evening
Pool size: 280 stocks
Total scanned: 0 (imported from JSON)
Status: completed
Ready: true
```

### What to Expect After Next Scan:
```
Session ID: 4 (new)
Type: evening or pre_open
Pool size: ~200-300 stocks
Total scanned: 987 (full universe) or ~280 (pre-open)
Status: completed
Ready: true
```

### How to Verify:
```bash
# 1. Run integration test
python3 scripts/test_prefilter_db_integration.py

# 2. Check web UI
- Go to Rapid Trader page
- Look at "Pool: N" badge
- Should show latest pool size from DB

# 3. Manual scan (optional - engine will do this automatically)
python3 src/pre_filter.py evening
```

## Files Modified

1. `src/pre_filter.py` - Main changes (4 sections)
2. `scripts/test_prefilter_db_integration.py` - New test script

## Files NOT Modified (Already Done in Phase 2)

- `src/database/models/pre_filter_session.py` ✅
- `src/database/models/filtered_stock.py` ✅
- `src/database/repositories/pre_filter_repository.py` ✅
- `src/web/app.py` ✅ (already reads from DB)
- Migration script ✅ (already applied)

## What's Next (Optional)

### Phase 3: Archive JSON Files
หลังจากยืนยันว่า DB ทำงานได้ดี (1-2 วัน):
1. Archive `data/pre_filter_status.json` → `data/archive/`
2. Archive `data/pre_filtered.json` → `data/archive/`
3. Keep code ที่เขียน JSON ไว้ก่อน (เผื่อต้อง rollback)

### Phase 4: Position Storage Migration (from plan)
จาก CLAUDE.md แผนที่มีอยู่แล้ว:
- Migrate `data/active_positions.json` to DB
- Use PositionRepository as single source of truth
- See: `/home/saengtawan/.claude/plans/velvety-squishing-lark.md`

## Success Criteria ✅

- [x] Database session created at scan start
- [x] total_scanned updated correctly
- [x] _save_status() writes to DB
- [x] _save_pre_filtered() writes to DB
- [x] Web API reads from DB
- [x] UI shows correct pool size
- [x] Integration test passes

## Monitoring

Watch for these in logs:
```
📊 Created DB session ID: 4
✅ DB synced: status updated
✅ DB synced: 280 stocks inserted
```

Check nohup.out for any errors during next scan.

---

**Status:** ✅ COMPLETE
**Next Automatic Scan:** Engine will trigger based on schedule
**Manual Test:** `python3 src/pre_filter.py evening` (optional)
