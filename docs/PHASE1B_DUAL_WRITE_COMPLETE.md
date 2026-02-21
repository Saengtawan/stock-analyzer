# ✅ Phase 1B Complete - Dual-Write Implemented

**Date:** 2026-02-20 23:52 ET
**Status:** 🟢 READY FOR TESTING

---

## 📋 Implementation Summary

### ✅ Files Modified (2 files)

1. **`src/auto_trading_engine.py`** - 3 locations updated
   - Line ~1237: `_save_signals_cache()` → Added DB write after JSON
   - Line ~3452: `_save_execution_status()` → Added DB write after JSON
   - Line ~1045: `_save_queue_state()` → Added DB write after JSON
   - Added 3 new methods:
     - `_save_signals_to_db()` (46 lines)
     - `_save_execution_to_db()` (32 lines)
     - `_save_queue_to_db()` (38 lines)

2. **`src/web/app.py`** - 1 location updated
   - Line ~2740: `api_rapid_signals()` → Read from DB first, JSON fallback

### ✅ New Files Created

1. **`scripts/monitor_dual_write.sh`** - Monitoring script
   - Compare JSON vs DB counts
   - Check for errors
   - Daily health checks

---

## 🎯 How It Works

### Write Flow (auto_trading_engine.py)

```
Scan completes
     ↓
[1] _save_signals_cache()
     ├─ Write JSON (existing, atomic)
     └─ Write DB (_save_signals_to_db)  ← NEW
           ├─ Create ScanSession → get session_id
           ├─ Save active signals (trading_signals)
           └─ Save waiting signals (trading_signals)
     ↓
[2] _save_execution_status()
     ├─ Write JSON (existing, atomic)
     └─ Write DB (_save_execution_to_db)  ← NEW
           └─ Save execution records (execution_history)
     ↓
[3] _save_queue_state() (when positions full)
     ├─ Write JSON (existing, atomic)
     └─ Write DB (_save_queue_to_db)  ← NEW
           ├─ Clear old queue
           └─ Save current queue (signal_queue)
```

### Read Flow (web/app.py)

```
UI requests /api/rapid/signals
     ↓
Try DB first
     ├─ Get latest ScanSession
     ├─ Get active signals
     ├─ Get waiting signals
     └─ Build response
     ↓
If DB fails → Fallback to JSON cache
     └─ Read rapid_signals.json (existing)
```

---

## 🔍 Key Features

### Dual-Write Safety

- ✅ **JSON is primary** - System continues if DB fails
- ✅ **Non-fatal errors** - DB failures logged but don't crash engine
- ✅ **Independent writes** - JSON atomic write completes before DB attempt
- ✅ **Monitoring** - Source field shows 'database' or 'json' in response

### Data Consistency

- ✅ **Session tracking** - Each scan creates scan_session with ID
- ✅ **Foreign keys** - Signals link to scan_session, execution links to signal
- ✅ **Status tracking** - Signals marked as active/waiting/executed
- ✅ **Queue replacement** - Full queue replaced on each save (no append bugs)

### Error Handling

```python
try:
    # Write to DB
    sig_repo.create(signal)
except Exception as e:
    logger.error(f"DB write failed (non-fatal): {e}")
    # Continue - JSON is primary
```

- All DB operations wrapped in try/except
- Errors logged with "(non-fatal)" prefix
- Engine continues normally on DB failures

---

## 🧪 Testing

### Manual Test 1: Start Engine & Monitor

```bash
# Terminal 1: Start engine
cd /home/saengtawan/work/project/cc/stock-analyzer
./scripts/start_all.sh

# Terminal 2: Monitor dual-write
watch -n 30 ./scripts/monitor_dual_write.sh
```

**Expected:**
- Signals count matches (JSON == DB)
- Queue count matches
- No DB errors in logs

### Manual Test 2: Compare Counts

```bash
# Check active signals
echo -n "JSON active: "
cat data/cache/rapid_signals.json | jq '.count'

echo -n "DB active: "
sqlite3 data/trade_history.db "SELECT COUNT(*) FROM trading_signals WHERE status='active'"

# Check queue
echo -n "JSON queue: "
cat data/signal_queue.json | jq '.count'

echo -n "DB queue: "
sqlite3 data/trade_history.db "SELECT COUNT(*) FROM signal_queue WHERE status='waiting'"
```

**Expected:** All counts match

### Manual Test 3: Check Scan Sessions

```bash
sqlite3 data/trade_history.db <<EOF
SELECT
    datetime(scan_time, 'localtime') as time,
    session_type,
    signal_count,
    waiting_count,
    market_regime
FROM scan_sessions
ORDER BY scan_time DESC
LIMIT 10;
EOF
```

**Expected:** New scan sessions created every scan

### Manual Test 4: Check Execution History

```bash
sqlite3 data/trade_history.db <<EOF
SELECT
    datetime(timestamp, 'localtime') as time,
    action,
    symbol,
    skip_reason
FROM execution_history
ORDER BY timestamp DESC
LIMIT 20;
EOF
```

**Expected:** Execution records created for each signal

### Manual Test 5: UI Source Check

```bash
# Check if UI is using DB
curl -s http://localhost:5000/api/rapid/signals | jq '.source'
```

**Expected:** `"database"` (if DB working) or `"json"` (if fallback)

---

## 📊 Monitoring Checklist

### Daily Checks (run `./scripts/monitor_dual_write.sh`)

- [ ] Signals count match (JSON == DB)
- [ ] Queue count match (JSON == DB)
- [ ] Latest scan session created
- [ ] Execution history growing
- [ ] No DB errors in logs

### Weekly Analytics

```bash
# Signal quality by regime (last 7 days)
sqlite3 data/trade_history.db <<EOF
SELECT
    market_regime,
    COUNT(*) as signals,
    AVG(score) as avg_score,
    SUM(CASE WHEN execution_result = 'BOUGHT' THEN 1 ELSE 0 END) as bought
FROM trading_signals
WHERE signal_time >= datetime('now', '-7 days')
GROUP BY market_regime;
EOF
```

```bash
# Top skip reasons
sqlite3 data/trade_history.db <<EOF
SELECT
    skip_reason,
    COUNT(*) as count
FROM execution_history
WHERE action = 'SKIPPED_FILTER'
  AND timestamp >= datetime('now', '-7 days')
GROUP BY skip_reason
ORDER BY count DESC
LIMIT 10;
EOF
```

```bash
# Daily conversion rate
sqlite3 data/trade_history.db <<EOF
SELECT
    DATE(timestamp) as date,
    COUNT(*) as total,
    SUM(CASE WHEN action = 'BOUGHT' THEN 1 ELSE 0 END) as bought,
    ROUND(100.0 * SUM(CASE WHEN action = 'BOUGHT' THEN 1 ELSE 0 END) / COUNT(*), 2) as pct
FROM execution_history
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY DATE(timestamp)
ORDER BY date DESC;
EOF
```

---

## 🚨 Troubleshooting

### Issue: Counts Don't Match

**Symptoms:**
```
❌ Signals count MISMATCH!
   Active: JSON=5, DB=0
```

**Diagnosis:**
```bash
# Check for DB write errors
grep "DB.*failed" nohup.out | tail -20

# Check if tables exist
sqlite3 data/trade_history.db ".tables"
```

**Fix:**
- If tables missing → Re-apply migration: `./scripts/apply_migration_001.sh`
- If import errors → Check models/repositories imports
- If permission errors → Check DB file permissions

### Issue: DB Errors in Logs

**Symptoms:**
```
ERROR - DB signals write failed (non-fatal): ...
```

**Diagnosis:**
```bash
# Check specific error
grep "DB.*failed" nohup.out | tail -5
```

**Common causes:**
- Import errors (missing dependencies)
- Schema mismatch (reapply migration)
- Disk space (check `df -h`)
- Lock errors (rare with SQLite)

**Fix:**
- Import errors → `python3 -c "from database.models import TradingSignal; print('OK')"`
- Schema errors → Reapply migration
- Disk space → Clean old data

### Issue: UI Shows JSON Instead of DB

**Symptoms:**
```bash
$ curl http://localhost:5000/api/rapid/signals | jq '.source'
"json"
```

**Diagnosis:**
```bash
# Check if DB has data
sqlite3 data/trade_history.db "SELECT COUNT(*) FROM trading_signals"

# Check web app logs
grep "DB read failed" nohup.out
```

**Fix:**
- If no data → Wait for next scan
- If import errors → Restart web app
- If DB errors → Check logs for details

---

## ⏭️ Next Steps

### Phase 1C: Switch to DB Primary (After 1-2 Weeks)

**Criteria to proceed:**
- ✅ All daily checks passing for 7+ days
- ✅ No DB errors for 7+ days
- ✅ JSON == DB counts verified daily
- ✅ Analytics queries working

**Changes:**
1. Update `src/web/app.py`:
   - Remove JSON fallback (keep for emergency)
   - Log warning if JSON used
2. Update `src/auto_trading_engine.py`:
   - Keep JSON writes as backup
   - Mark JSON as read-only
3. Monitor for 7 more days

### Phase 1D: Remove JSON (After Phase 1C Stable)

**Criteria to proceed:**
- ✅ DB primary stable for 14+ days
- ✅ No JSON fallback usage
- ✅ No regressions

**Changes:**
1. Archive JSON files:
   ```bash
   mkdir -p archive/json_backup_$(date +%Y%m%d)
   mv data/cache/rapid_signals.json archive/json_backup_*/
   mv data/cache/execution_status.json archive/json_backup_*/
   mv data/signal_queue.json archive/json_backup_*/
   ```
2. Remove write operations (comment out, don't delete)
3. Update memory/docs

### Phase 2: State & Monitoring Files

- `data/pre_filtered.json` → `filtered_pool` table
- `data/pre_filter_status.json` → `pre_filter_status` table
- `data/heartbeat.json` → `system_health` table
- `data/alerts.json` → `alerts` table (repository exists!)

---

## ✅ Success Criteria

### Phase 1B - IN PROGRESS
- [x] Code changes implemented
- [x] Syntax validated (no compile errors)
- [x] Monitoring script created
- [ ] Engine running with dual-write (test now)
- [ ] Counts match for 24 hours
- [ ] No errors for 7 days

### Current Status
**Ready to test!** Start engine and run monitoring script.

---

## 📞 Quick Commands

```bash
# Start monitoring
./scripts/monitor_dual_write.sh

# Check recent scans
sqlite3 data/trade_history.db "SELECT datetime(scan_time, 'localtime'), session_type, signal_count FROM scan_sessions ORDER BY scan_time DESC LIMIT 5"

# Check recent executions
sqlite3 data/trade_history.db "SELECT datetime(timestamp, 'localtime'), action, symbol FROM execution_history ORDER BY timestamp DESC LIMIT 10"

# Check DB source in UI
curl -s http://localhost:5000/api/rapid/signals | jq '.source'

# Watch logs for DB errors
tail -f nohup.out | grep --color "DB"
```

---

🎉 **Phase 1B implementation complete! Ready for testing.**
